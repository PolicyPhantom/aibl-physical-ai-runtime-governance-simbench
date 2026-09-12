"""Verify persisted Phase 4 evidence without rerunning governance."""
from __future__ import annotations
import base64
from dataclasses import asdict

from phase3.adapter import adapt_proposal
from phase3.identity import canonical_bytes,canonical_sha256,raw_sha256
from .contracts import ContractError,JsonSnapshot,DerivedInputProvenance,parse_json
from .derivation import resolve_baseline,verify_derivation
from .runner import ApprovedInputs,prepare_input,closed
from .evidence import PRE,RESULT,FINAL,START,INVENTORY,safe_read,list_artifacts

def _read(root,path):return parse_json(safe_read(root,path))
def equal(actual,expected,detail):
    if canonical_bytes(actual,exclude_volatile=False)!=canonical_bytes(expected,exclude_volatile=False):
        raise ContractError(detail)

def verify_core(root,approved):
    if type(approved) is not ApprovedInputs:raise ContractError("external approved manifest required")
    references=_read(root,"00_spec/references.json")
    closed(references,("source_baseline_id","baseline_payload","source_materials","approved_manifest_raw_base64","approved_manifest_sha256"))
    raw=base64.b64decode(references["approved_manifest_raw_base64"],validate=True)
    if raw!=approved.raw or references["approved_manifest_sha256"]!=approved.expected_raw_sha256:
        raise ContractError("saved manifest/external binding mismatch")
    materials=references["source_materials"]
    if type(materials) is not list or len({m["source_id"] for m in materials})!=len(materials):
        raise ContractError("source material set mismatch")
    sources={m["source_id"]:base64.b64decode(m["raw_base64"],validate=True) for m in materials}
    spec=_read(root,"00_spec/spec.json")
    closed(spec,("case","attempt_number","batch_id","session_binding"))
    prepared=prepare_input(spec["case"]["case_id"],sources,approved)
    equal(spec["case"],asdict(prepared.case),"frozen pre-execution spec changed")
    equal(references["baseline_payload"],prepared.verified.baseline.payload.value,"saved baseline mismatch")
    for actual,expected in zip(materials,prepared.verified.baseline.source_materials):
        equal(actual,{"source_id":expected.source_id,"path":expected.path,"raw_sha256":expected.raw_sha256,
            "canonical_sha256":expected.canonical_sha256,"raw_base64":base64.b64encode(expected.raw_bytes).decode("ascii")},"source record mismatch")
    if references["source_baseline_id"]!=prepared.case.source_baseline_id:raise ContractError("baseline ID mismatch")
    result=_read(root,"08_reconstruction/core_result.json")
    closed(result,("case_id","decision","initial_state","final_state","effect","physical_result",
                   "physical_action_count","decision_basis","claim_boundary","result_sha256"))
    expected_hash=canonical_sha256({k:v for k,v in result.items() if k!="result_sha256"},exclude_volatile=False)
    if result["result_sha256"]!=expected_hash:raise ContractError("result identity mismatch")
    artifact=_read(root,"08_reconstruction/core_result_artifact.json")
    raw_result=safe_read(root,"08_reconstruction/core_result.json")
    equal(artifact,{"raw_sha256":raw_sha256(raw_result),"bytes":len(raw_result)},"core result artifact mismatch")
    if result["case_id"]!=prepared.case.case_id or result["claim_boundary"]!="SIMULATION_LIMITED":
        raise ContractError("result case/claim mismatch")
    reentry=prepared.case.source_baseline_id=="P3-CTRL-02"
    if result["initial_state"]!=("SUSPENDED" if reentry else "RUNNING"):
        raise ContractError("initial state mismatch")
    decision=result["decision"]
    closed(decision,("decision","reason","evaluated_at_tick","enforcement","command_status","physical_action_count"))
    if (type(decision["evaluated_at_tick"]) is not int or decision["evaluated_at_tick"]!=1000
            or decision["command_status"] is not None or type(decision["physical_action_count"]) is not int
            or decision["physical_action_count"]!=0):
        raise ContractError("decision time/action contract mismatch")
    enforcement=("STATE_RESTORATION_ONLY" if reentry else "PERMITTED") if decision["decision"]=="ALLOW" else "NOT_PERFORMED"
    if decision["enforcement"]!=enforcement:raise ContractError("decision enforcement mismatch")
    moving=not reentry and decision["decision"]=="ALLOW"
    if type(result["physical_action_count"]) is not int or result["physical_action_count"]!=int(moving):
        raise ContractError("physical action count mismatch")
    if moving:
        equal(result["physical_result"],{"command_status":"ISSUED","command_issued_at_tick":1000,
            "expected_state":"ZONE_B","actual_state":"ZONE_B","verification_tick":1001,
            "event":None,"execution_result":"MOVED_TO_ZONE_B","initial_state":"RUNNING",
            "final_state":"RUNNING","physical_action_count":1},"physical effect contract mismatch")
    elif result["physical_result"] is not None:
        raise ContractError("unpermitted physical effect")
    actual_payload=JsonSnapshot.of(result["decision_basis"]["evaluated_input"])
    provenance=DerivedInputProvenance(JsonSnapshot.of(_read(root,"00_spec/derived_input_provenance.json")))
    verify_derivation(prepared.verified.baseline,provenance,actual_payload,prepared.case)
    expected_context={"physical_identity_expectation":None if prepared.physical_expectation is None else prepared.physical_expectation.to_dict(),
        "approved_input_manifest_identity":approved.expected_raw_sha256,"case_id":prepared.case.case_id,
        "derived_input_id":prepared.case.derived_input_id,"resulting_payload_sha256":prepared.verified.payload.sha256,
        "identity_route":"P3_DEFAULT" if prepared.physical_expectation is None else "P4_APPROVED_MANIFEST"}
    equal(result["decision_basis"],{"evaluated_input":prepared.verified.payload.value,"validation_context":expected_context},"actual expectation/input binding mismatch")
    equal(_read(root,"03_context/decision_basis.json"),result["decision_basis"],"saved decision basis mismatch")
    equal(_read(root,"04_governance/decision_receipt.json"),result["decision"],"receipt mismatch")
    equal(_read(root,"05_enforcement/enforcement.json"),{"effect":result["effect"],"physical_action_count":result["physical_action_count"]},"enforcement mismatch")
    equal(_read(root,"08_reconstruction/identity.json"),{"result_sha256":expected_hash,
        "payload_sha256":prepared.verified.payload.sha256,"manifest_sha256":approved.expected_raw_sha256},"identity artifact mismatch")
    proposal=prepared.verified.baseline.source_materials[0].raw_bytes
    if safe_read(root,"01_input/raw_proposal.bin")!=proposal:raise ContractError("raw proposal mismatch")
    equal(_read(root,"01_input/raw_identity.json"),{"sha256":raw_sha256(proposal),"bytes":len(proposal)},"raw identity mismatch")
    equal(_read(root,"02_adapter/adapter.json"),adapt_proposal(proposal).to_dict(),"adapter mismatch")
    from .boundary import batch_id
    start=_read(root,START)
    expected_start={"schema_id":"P4-ATTEMPT-START-v1","session_id":spec["session_binding"]["session_id"],
        "case_id":prepared.case.case_id,"batch_id":spec["batch_id"],"attempt_number":spec["attempt_number"],
        "slot_id":f"{prepared.case.case_id}-attempt-{spec['attempt_number']:02}",
        "derived_input_id":prepared.case.derived_input_id,"payload_sha256":prepared.verified.payload.sha256,
        "wrapper_sha256":provenance.envelope.value["wrapper_sha256"],"manifest_sha256":approved.expected_raw_sha256,
        "physical_identity_expectation":expected_context["physical_identity_expectation"],
        "output_path":str(root),"session_binding":spec["session_binding"]}
    equal(start,expected_start,"start/result binding mismatch")
    if type(spec["attempt_number"]) is not int or spec["attempt_number"] not in (1,2,3):
        raise ContractError("attempt number mismatch")
    if (spec["batch_id"]!=batch_id(start["session_id"],prepared.case.case_id)
            or root.name!=f"attempt-{spec['attempt_number']:02}" or root.parent.name!=prepared.case.case_id
            or root.parent.parent.name!=spec["batch_id"] or root.parent.parent.parent.name!=start["session_id"]):
        raise ContractError("saved output mapping mismatch")
    equal(_read(root,"04_governance/stage.json"),{"stage":"REENTRY_GOVERNANCE" if prepared.case.source_baseline_id=="P3-CTRL-02" else "ACTION_GOVERNANCE"},"stage mismatch")
    if result["physical_result"] is not None:
        equal(_read(root,"06_physical/outcome.json"),result["physical_result"],"physical artifact mismatch")
    elif "06_physical/outcome.json" in list_artifacts(root):
        raise ContractError("unexpected physical artifact")
    actual=(result["decision"]["decision"],result["decision"]["reason"],result["final_state"],result["effect"])
    expected=(prepared.case.expected_decision,prepared.case.expected_reason,prepared.case.expected_state,prepared.case.expected_effect)
    return {"transition_match":actual==expected,"expected":list(expected),"observed":list(actual),
            "reconstruction":"PASS","identity":"PASS","result_sha256":expected_hash}

def verify_attempt(root,approved,expected_inventory_sha256=None):
    inventory=_read(root,INVENTORY)
    closed(inventory,("schema_id","status","artifacts","inventory_sha256"))
    if inventory["schema_id"]!="P4-ATTEMPT-INVENTORY-v1":raise ContractError("inventory schema mismatch")
    basis={k:v for k,v in inventory.items() if k!="inventory_sha256"}
    if inventory["inventory_sha256"]!=canonical_sha256(basis,exclude_volatile=False):raise ContractError("inventory self identity mismatch")
    if expected_inventory_sha256 is not None and raw_sha256(safe_read(root,INVENTORY))!=expected_inventory_sha256:
        raise ContractError("external inventory identity mismatch")
    entries=inventory["artifacts"]
    if type(entries) is not list:raise ContractError("inventory list required")
    listed=[]
    for entry in entries:
        closed(entry,("path","bytes","sha256"))
        if entry["path"]==INVENTORY or entry["path"] in listed:raise ContractError("inventory duplicate/self cycle")
        raw=safe_read(root,entry["path"])
        if type(entry["bytes"]) is not int or len(raw)!=entry["bytes"] or raw_sha256(raw)!=entry["sha256"]:
            raise ContractError("inventory artifact identity mismatch")
        listed.append(entry["path"])
    if set(list_artifacts(root))!=set(listed)|{INVENTORY}:raise ContractError("inventory missing/extra coverage")
    if inventory["status"]!="COMPLETED":raise ContractError("attempt did not complete")
    if not (PRE|RESULT|FINAL|{START}).issubset(listed):raise ContractError("incomplete evidence")
    reconciliation=verify_core(root,approved)
    if not reconciliation["transition_match"]:raise ContractError("frozen expected result mismatch")
    equal(_read(root,"08_reconstruction/reconciliation.json"),reconciliation,"reconciliation mismatch")
    equal(_read(root,"07_verification/verification.json"),{"reconstruction":"PASS","identity":"PASS"},"verification status mismatch")
    if any(p.startswith("09_findings/") for p in listed):raise ContractError("finding in successful attempt")
    return reconciliation

def compare_attempts(left,right,approved):
    """Persisted replay equivalence only; never invoke governance."""
    a=verify_attempt(left,approved);b=verify_attempt(right,approved)
    ra=_read(left,"08_reconstruction/core_result.json");rb=_read(right,"08_reconstruction/core_result.json")
    if ra["case_id"]!=rb["case_id"]:raise ContractError("different cases are not replay-equivalent")
    equal(ra,rb,"same-case replay mismatch")
    return {"replay":"PASS","result_sha256":a["result_sha256"]}
