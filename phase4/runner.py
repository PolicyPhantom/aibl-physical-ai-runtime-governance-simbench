"""Phase 4 approved-input binding and one-shot lower-level evaluation.

External expected hashes are trust inputs supplied by the authorized operator,
never inferred from candidate observations. These values are not a signature or
proof of human approval. Session/GO verification is owned by phase4.session.
"""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import re

from phase3.governance import evaluate_action
from phase3.reentry import evaluate_reentry, apply_reentry
from phase3.physical import PhysicalIdentityExpectation, execute_allowed_move
from phase3.identity import canonical_bytes, canonical_sha256, raw_sha256
from .boundary import AttemptBoundary, BoundaryError
from .contracts import (ContractError, JsonSnapshot, P4CaseSpec, P4Plan, P4Slot,
                        SPEC_SHA256, RULE_ID, SCHEMA_PATH, VerifiedDerivedInput,
                        frozen_cases, load_core_cases, CASE_PATH, parse_json)
from .derivation import derive_input, resolve_baseline, verify_derivation

def digest(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}",value) is None:
        raise ContractError("external SHA-256 binding required")
    return value

def closed(value,fields):
    if type(value) is not dict or set(value)!=set(fields):
        raise ContractError("closed control fields mismatch")

@dataclass(frozen=True,slots=True)
class ApprovedInputs:
    raw: bytes
    expected_raw_sha256: str

    def __post_init__(self):
        digest(self.expected_raw_sha256)
        if type(self.raw) is not bytes or raw_sha256(self.raw)!=self.expected_raw_sha256:
            raise ContractError("approved manifest raw identity mismatch")
        doc=parse_json(self.raw)
        closed(doc,("schema_id","frozen_spec_sha256","derivation_rule_id","derivation_schema_sha256","cases"))
        if (doc["schema_id"]!="P4-APPROVED-INPUTS-v1" or doc["frozen_spec_sha256"]!=SPEC_SHA256
                or doc["derivation_rule_id"]!=RULE_ID
                or doc["derivation_schema_sha256"]!=raw_sha256(SCHEMA_PATH.read_bytes())):
            raise ContractError("manifest/spec/schema binding mismatch")
        if type(doc["cases"]) is not list or len(doc["cases"])!=14:
            raise ContractError("fourteen approved manifest entries required")
        for entry,case in zip(doc["cases"],frozen_cases()):
            closed(entry,("case_id","derived_input_id","source_baseline_id","source_baseline_payload_sha256",
                          "source_materials","payload_sha256","wrapper_sha256","physical_identity_expectation"))
            if (entry["case_id"]!=case.case_id or entry["derived_input_id"]!=case.derived_input_id
                    or entry["source_baseline_id"]!=case.source_baseline_id):
                raise ContractError("manifest case mapping mismatch")
            for field in ("payload_sha256","wrapper_sha256","source_baseline_payload_sha256"):digest(entry[field])
            expected=entry["physical_identity_expectation"]
            if case.parameter_family=="PHY":
                PhysicalIdentityExpectation(expected)
            elif expected is not None:
                raise ContractError("physical expectation only for Physical sweep")

    @property
    def document(self):
        return parse_json(self.raw)

    def entry(self,case_id):
        return next(entry for entry in self.document["cases"] if entry["case_id"]==case_id)


@dataclass(frozen=True,slots=True)
class PreparedInput:
    case: P4CaseSpec
    verified: VerifiedDerivedInput
    approved: ApprovedInputs
    physical_expectation: PhysicalIdentityExpectation | None


def bind_physical_identity(verified,approved,case):
    if type(approved) is not ApprovedInputs or type(verified) is not VerifiedDerivedInput:
        raise ContractError("verified input and externally bound manifest required")
    p=verified.provenance.envelope.value["provenance"]
    entry=approved.entry(case.case_id)
    expected={key:entry[key] for key in ("source_baseline_id","source_baseline_payload_sha256","source_materials")}
    actual={key:p[key] for key in expected}
    if canonical_bytes(expected,exclude_volatile=False)!=canonical_bytes(actual,exclude_volatile=False):
        raise ContractError("approved source binding mismatch")
    if (entry["derived_input_id"]!=p["derived_input_id"] or entry["payload_sha256"]!=verified.payload.sha256
            or entry["wrapper_sha256"]!=verified.provenance.envelope.value["wrapper_sha256"]):
        raise ContractError("manifest payload/wrapper/case mismatch")
    if case.parameter_family!="PHY":
        return None
    # Construct expectations only from the separately hash-bound manifest.
    expectation=PhysicalIdentityExpectation(entry["physical_identity_expectation"])
    records=verified.payload.value["physical_observations"]
    for name,expected_hash in expectation.entries:
        if records[name]["content_sha256"]!=expected_hash or records[name]["content_identity"]!="sha256:"+expected_hash:
            raise ContractError("approved Physical expectation mismatch")
    return expectation


def prepare_input(case_id,source_bytes,approved):
    case=next((c for c in frozen_cases() if c.case_id==case_id),None)
    if case is None:raise ContractError("unapproved case")
    baseline=resolve_baseline(source_bytes,case.source_baseline_id)
    candidate=derive_input(baseline,case)
    verified=verify_derivation(baseline,candidate.provenance,candidate.payload,case)
    expected=bind_physical_identity(verified,approved,case)
    return PreparedInput(case,verified,approved,expected)


def load_frozen_plan(raw,expected_raw_sha256):
    if raw_sha256(raw)!=digest(expected_raw_sha256):raise ContractError("plan raw identity mismatch")
    doc=parse_json(raw)
    closed(doc,("schema_id","session_id","frozen_spec_sha256","core_cases_sha256","repetitions","attempt_count","hard_max","manifest_sha256"))
    if (doc["schema_id"]!="P4-PLAN-v1" or doc["frozen_spec_sha256"]!=SPEC_SHA256
            or doc["core_cases_sha256"]!=raw_sha256(CASE_PATH.read_bytes())
            or type(doc["repetitions"]) is not int or doc["repetitions"]!=3
            or type(doc["attempt_count"]) is not int or doc["attempt_count"]!=42
            or type(doc["hard_max"]) is not int or doc["hard_max"]!=60):
        raise ContractError("frozen plan mismatch")
    from .boundary import batch_id,safe_segment
    safe_segment(doc["session_id"]);digest(doc["manifest_sha256"])
    cases=load_core_cases(CASE_PATH.read_bytes())
    slots=tuple(P4Slot(c.case_id,n,batch_id(doc["session_id"],c.case_id),
                      f"{c.case_id}-attempt-{n:02}") for c in cases for n in range(1,4))
    return P4Plan(expected_raw_sha256,cases,slots)


def start_record(prepared,boundary,session_binding):
    return {"schema_id":"P4-ATTEMPT-START-v1","session_id":boundary.session.session_id,
            "case_id":prepared.case.case_id,"batch_id":boundary.batch_id,
            "attempt_number":boundary.attempt_number,"slot_id":f"{prepared.case.case_id}-attempt-{boundary.attempt_number:02}",
            "derived_input_id":prepared.case.derived_input_id,
            "payload_sha256":prepared.verified.payload.sha256,
            "wrapper_sha256":prepared.verified.provenance.envelope.value["wrapper_sha256"],
            "manifest_sha256":prepared.approved.expected_raw_sha256,
            "physical_identity_expectation":None if prepared.physical_expectation is None else prepared.physical_expectation.to_dict(),
            "output_path":str(boundary.directory.path),"session_binding":session_binding}


@dataclass(frozen=True,slots=True)
class EvaluationPermit:
    """Issued only after exclusive, fsynced, read-back-verified start records."""
    prepared: PreparedInput
    boundary: AttemptBoundary
    binding: JsonSnapshot
    marker: bytes


_issued_permits={}
def initialize_attempt(prepared,boundary,session_binding):
    if type(prepared) is not PreparedInput or type(boundary) is not AttemptBoundary:
        raise ContractError("prepared input and attempt boundary required")
    boundary.validate()
    if boundary.case_id!=prepared.case.case_id:raise ContractError("attempt/case mismatch")
    # Required session-binding shape is also checked by the later preflight.
    closed(session_binding,("session_id","plan_sha256","human_go_sha256","code_head",
                           "manifest_sha256","workspace_authorization_id","ordered_slots_sha256","procedure_sha256","preflight_sha256"))
    if (session_binding["session_id"]!=boundary.session.session_id
            or session_binding["manifest_sha256"]!=prepared.approved.expected_raw_sha256
            or session_binding["workspace_authorization_id"]!=boundary.session.authorization.authorization_id):
        raise ContractError("session binding mismatch")
    for name in ("plan_sha256","human_go_sha256","manifest_sha256","ordered_slots_sha256","procedure_sha256","preflight_sha256"):
        digest(session_binding[name])
    if not re.fullmatch("[0-9a-f]{40}",session_binding["code_head"]):raise ContractError("code identity required")
    session_path=boundary.session.directory.path/"session_start.json"
    if session_path.is_symlink():raise BoundaryError("session marker symlink")
    if parse_json(session_path.read_bytes())!=session_binding:raise ContractError("session start binding mismatch")
    # Revalidate the immutable derivation and external expectation before consuming a slot.
    verify_derivation(prepared.verified.baseline,prepared.verified.provenance,prepared.verified.payload,prepared.case)
    expected=bind_physical_identity(prepared.verified,prepared.approved,prepared.case)
    if expected!=prepared.physical_expectation:raise ContractError("prepared expectation substituted")
    spec_dir=boundary.directory.path/"00_spec"
    os.mkdir(spec_dir)
    marker=canonical_bytes(start_record(prepared,boundary,session_binding),exclude_volatile=False)
    path=spec_dir/"attempt_start.json"
    with path.open("xb") as f:f.write(marker);f.flush();os.fsync(f.fileno())
    if path.read_bytes()!=marker:raise ContractError("attempt start read-back mismatch")
    boundary.validate()
    permit=EvaluationPermit(prepared,boundary,JsonSnapshot.of(session_binding),marker)
    _issued_permits[id(permit)]=(permit,False)
    return permit


def evaluate_once(permit):
    state=_issued_permits.get(id(permit))
    if type(permit) is not EvaluationPermit or state is None or state[0] is not permit or state[1]:
        raise ContractError("unused issued evaluation permit required")
    permit.boundary.validate()
    root=permit.boundary.directory.path
    if (root/"00_spec"/"attempt_start.json").read_bytes()!=permit.marker:
        raise ContractError("attempt start changed")
    if parse_json((permit.boundary.session.directory.path/"session_start.json").read_bytes())!=permit.binding.value:
        raise ContractError("session start changed")
    # Consume before invoking governance: exceptions never restore permission.
    _issued_permits[id(permit)]=(permit,True)
    prepared=permit.prepared
    payload=prepared.verified.payload.value
    case=prepared.case
    if case.source_baseline_id=="P3-CTRL-02":
        decision=evaluate_reentry(payload["bundle"],tick=payload["tick"])
        transition=apply_reentry(payload["bundle"],decision)
        final_state=transition["final_state"];physical=None
        effect="STATE_RESTORATION_ONLY" if decision.decision=="ALLOW" else None
        initial_state="SUSPENDED"
    else:
        decision=evaluate_action(payload["proposal"],payload["context"],payload["physical_observations"],
                                 tick=payload["tick"],physical_identity_expectation=prepared.physical_expectation)
        physical=None;final_state=initial_state="RUNNING";effect=None
        if decision.decision=="ALLOW":
            physical=execute_allowed_move(decision,actual_state="ZONE_B").to_dict()
            final_state=physical["final_state"];effect=physical["execution_result"]
    validation={"physical_identity_expectation":None if prepared.physical_expectation is None else prepared.physical_expectation.to_dict(),
                "approved_input_manifest_identity":prepared.approved.expected_raw_sha256,
                "case_id":case.case_id,"derived_input_id":case.derived_input_id,
                "resulting_payload_sha256":prepared.verified.payload.sha256,
                "identity_route":"P3_DEFAULT" if prepared.physical_expectation is None else "P4_APPROVED_MANIFEST"}
    result={"case_id":case.case_id,"decision":decision.to_dict(),"initial_state":initial_state,
            "final_state":final_state,"effect":effect,"physical_result":physical,
            "physical_action_count":0 if physical is None else physical["physical_action_count"],
            "decision_basis":{"evaluated_input":payload,"validation_context":validation},
            "claim_boundary":"SIMULATION_LIMITED"}
    result["result_sha256"]=canonical_sha256(result,exclude_volatile=False)
    return JsonSnapshot.of(result)
