"""Phase 4 attempt evidence, exclusive artifacts and inventory-last lifecycle."""
from __future__ import annotations
from dataclasses import asdict
import base64
import os
from pathlib import PurePosixPath
import stat

from phase3.adapter import adapt_proposal
from phase3.identity import canonical_bytes, raw_sha256, canonical_sha256
from .boundary import BoundaryError, inspect_directory
from .contracts import ContractError, JsonSnapshot
from .runner import EvaluationPermit, _issued_permits

PRE={"00_spec/spec.json","00_spec/references.json","00_spec/derived_input_provenance.json",
     "01_input/raw_proposal.bin","01_input/raw_identity.json","02_adapter/adapter.json"}
RESULT={"03_context/decision_basis.json","04_governance/stage.json","04_governance/decision_receipt.json",
        "05_enforcement/enforcement.json","08_reconstruction/core_result.json",
        "08_reconstruction/core_result_artifact.json","08_reconstruction/identity.json"}
FINAL={"07_verification/verification.json","08_reconstruction/reconciliation.json"}
OPTIONAL={"06_physical/outcome.json","06_physical/event-0001.json","09_findings/finding.json","09_findings/failure.json"}
START="00_spec/attempt_start.json"
INVENTORY="08_reconstruction/inventory.json"
ALLOWED=frozenset(PRE|RESULT|FINAL|OPTIONAL|{START,INVENTORY})

def safe_read(root,relative):
    if relative not in ALLOWED:raise BoundaryError("unapproved evidence leaf")
    path=root.joinpath(*PurePosixPath(relative).parts)
    inspect_directory(path.parent)
    info=os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise BoundaryError("evidence leaf reparse/type violation")
    return path.read_bytes()

def list_artifacts(root):
    result=[]
    allowed_dirs={str(PurePosixPath(p).parent) for p in ALLOWED}
    for current,dirs,files in os.walk(root,followlinks=False):
        for name in dirs:
            path=type(root)(current)/name
            relative=path.relative_to(root).as_posix()
            if relative not in allowed_dirs:raise BoundaryError("unexpected evidence directory")
            inspect_directory(path)
        for name in files:
            path=type(root)(current)/name
            relative=path.relative_to(root).as_posix()
            safe_read(root,relative)
            result.append(relative)
    return sorted(result)

class EvidenceWriter:
    def __init__(self,permit):
        state=_issued_permits.get(id(permit))
        if type(permit) is not EvaluationPermit or state is None or state[0] is not permit or state[1]:
            raise ContractError("writer requires unused issued permit")
        self.permit=permit;self.root=permit.boundary.directory.path
        permit.boundary.validate()
        if list_artifacts(self.root)!=[START] or safe_read(self.root,START)!=permit.marker:
            raise ContractError("unexpected initial attempt artifacts")
        self.written={START:raw_sha256(permit.marker)}
        self.phase="STARTED"

    def _write(self,relative,raw,*,inventory=False):
        self.permit.boundary.validate()
        if self.phase=="FINALIZED" or (self.root/INVENTORY).exists():
            raise ContractError("write after inventory prohibited")
        if relative not in ALLOWED or relative==START or (relative==INVENTORY and not inventory):
            raise ContractError("artifact not authorized")
        path=self.root/relative
        try:os.mkdir(path.parent)
        except FileExistsError:inspect_directory(path.parent)
        with path.open("xb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
        if safe_read(self.root,relative)!=raw:raise ContractError("artifact read-back mismatch")
        self.written[relative]=raw_sha256(raw)

    def _json(self,path,value):
        self._write(path,canonical_bytes(value,exclude_volatile=False))

    def persist_pre_evaluation(self):
        if self.phase!="STARTED":raise ContractError("pre-evaluation lifecycle mismatch")
        p=self.permit.prepared
        self._json("00_spec/spec.json",{"case":asdict(p.case),"attempt_number":self.permit.boundary.attempt_number,
            "batch_id":self.permit.boundary.batch_id,"session_binding":self.permit.binding.value})
        materials=[{"source_id":m.source_id,"path":m.path,"raw_sha256":m.raw_sha256,
                    "canonical_sha256":m.canonical_sha256,"raw_base64":base64.b64encode(m.raw_bytes).decode("ascii")}
                   for m in p.verified.baseline.source_materials]
        self._json("00_spec/references.json",{"source_baseline_id":p.verified.baseline.source_baseline_id,
            "baseline_payload":p.verified.baseline.payload.value,"source_materials":materials,
            "approved_manifest_raw_base64":base64.b64encode(p.approved.raw).decode("ascii"),
            "approved_manifest_sha256":p.approved.expected_raw_sha256})
        self._json("00_spec/derived_input_provenance.json",p.verified.provenance.envelope.value)
        raw=p.verified.baseline.source_materials[0].raw_bytes
        self._write("01_input/raw_proposal.bin",raw)
        self._json("01_input/raw_identity.json",{"sha256":raw_sha256(raw),"bytes":len(raw)})
        self._json("02_adapter/adapter.json",adapt_proposal(raw).to_dict())
        self.phase="PRE_EVALUATION"

    def persist_result(self,result):
        state=_issued_permits.get(id(self.permit))
        if self.phase!="PRE_EVALUATION" or state is None or not state[1] or type(result) is not JsonSnapshot:
            raise ContractError("complete result requires consumed evaluation permit")
        r=result.value
        # Persist the complete result first, before reconciliation.
        self._json("08_reconstruction/core_result.json",r)
        self._json("08_reconstruction/core_result_artifact.json",{"raw_sha256":raw_sha256(result.raw),"bytes":len(result.raw)})
        self._json("03_context/decision_basis.json",r["decision_basis"])
        self._json("04_governance/stage.json",{"stage":"REENTRY_GOVERNANCE" if r["initial_state"]=="SUSPENDED" else "ACTION_GOVERNANCE"})
        self._json("04_governance/decision_receipt.json",r["decision"])
        self._json("05_enforcement/enforcement.json",{"effect":r["effect"],"physical_action_count":r["physical_action_count"]})
        if r["physical_result"] is not None:
            self._json("06_physical/outcome.json",r["physical_result"])
            if r["physical_result"]["event"] is not None:
                self._json("06_physical/event-0001.json",{"event":r["physical_result"]["event"]})
        self._json("08_reconstruction/identity.json",{"result_sha256":r["result_sha256"],
            "payload_sha256":self.permit.prepared.verified.payload.sha256,
            "manifest_sha256":self.permit.prepared.approved.expected_raw_sha256})
        self.phase="RESULT_PERSISTED"

    def reconcile_and_finalize(self):
        if self.phase!="RESULT_PERSISTED":raise ContractError("result must precede reconciliation")
        from .verification import verify_core
        try:
            reconciliation=verify_core(self.root,self.permit.prepared.approved)
        except Exception as exc:
            self._json("09_findings/failure.json",{"kind":"VERIFICATION_FAILURE","detail":str(exc)})
            self.finalize("FAILED")
            raise
        self._json("07_verification/verification.json",{"reconstruction":"PASS","identity":"PASS"})
        self._json("08_reconstruction/reconciliation.json",reconciliation)
        status="COMPLETED" if reconciliation["transition_match"] else "FAILED"
        if status=="FAILED":
            self._json("09_findings/finding.json",{"kind":"EXPECTED_RESULT_MISMATCH","details":reconciliation})
        self.finalize(status)
        if status!="COMPLETED":raise ContractError("expected result mismatch")
        return reconciliation

    def record_failure(self,detail):
        if self.phase=="FINALIZED":raise ContractError("write after inventory prohibited")
        self._json("09_findings/failure.json",{"kind":"RUNTIME_OR_PERSISTENCE_FAILURE","detail":str(detail)})
        self.finalize("FAILED")

    def finalize(self,status):
        if status not in ("COMPLETED","FAILED"):raise ContractError("terminal state required")
        if status=="COMPLETED" and not (PRE|RESULT|FINAL|{START}).issubset(self.written):
            raise ContractError("incomplete successful evidence")
        actual=list_artifacts(self.root)
        if set(actual)!=set(self.written):raise ContractError("unexpected/missing artifact before inventory")
        entries=[]
        for p in actual:
            raw=safe_read(self.root,p)
            if raw_sha256(raw)!=self.written[p]:raise ContractError("artifact changed before inventory")
            entries.append({"path":p,"bytes":len(raw),"sha256":raw_sha256(raw)})
        basis={"schema_id":"P4-ATTEMPT-INVENTORY-v1","status":status,"artifacts":entries}
        basis["inventory_sha256"]=canonical_sha256(basis,exclude_volatile=False)
        self._write(INVENTORY,canonical_bytes(basis,exclude_volatile=False),inventory=True)
        self.phase="FINALIZED"
