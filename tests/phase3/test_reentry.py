from copy import deepcopy
import json
from pathlib import Path

from phase3.reentry import apply_reentry, evaluate_reentry


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT / "phase3_scenarios" / "fixtures" / "reentry_current.json"
)


def _bundle() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_all_ten_current_elements_restore_state_only():
    bundle = _bundle()
    decision = evaluate_reentry(bundle)
    transition = apply_reentry(bundle, decision)
    assert (decision.decision, decision.reason) == (
        "ALLOW",
        "ALL_CURRENT_REENTRY_CONDITIONS_SATISFIED",
    )
    assert transition == {
        "initial_state": "SUSPENDED",
        "final_state": "RUNNING",
        "state_restoration": True,
        "physical_command": None,
        "physical_action_count": 0,
    }


def test_stale_remediation_is_hold_and_remains_suspended():
    bundle = _bundle()
    bundle["remediation"]["observed_at_tick"] = 994
    decision = evaluate_reentry(bundle)
    transition = apply_reentry(bundle, decision)
    assert (decision.decision, decision.reason) == (
        "HOLD",
        "REENTRY_REMEDIATION_EVIDENCE_STALE",
    )
    assert transition["final_state"] == "SUSPENDED"


def test_current_prohibited_risk_is_deny():
    bundle = _bundle()
    bundle["risk_records"][0]["current_risk_state"] = "PROHIBITED"
    decision = evaluate_reentry(bundle)
    assert (decision.decision, decision.reason) == (
        "DENY",
        "CURRENT_RISK_PROHIBITED",
    )
    assert apply_reentry(bundle, decision)["final_state"] == "SUSPENDED"


def test_unverified_evidence_is_hold_without_partial_scoring():
    bundle = deepcopy(_bundle())
    bundle["evidence_verification"] = {
        "completeness": "INCOMPLETE",
        "present_file_integrity": "INTEGRITY_VERIFIED",
        "full_set_integrity": "NOT_ESTABLISHED",
    }
    decision = evaluate_reentry(bundle)
    assert (decision.decision, decision.reason) == (
        "HOLD",
        "CURRENT_EVIDENCE_NOT_VERIFIED",
    )


def test_material_change_record_must_bind_to_the_remediated_suspension():
    bundle = _bundle()
    bundle["material_condition_changes"]["suspension_event_id"] = (
        "SUSPENSION-P3-OTHER"
    )
    decision = evaluate_reentry(bundle)
    assert (decision.decision, decision.reason) == (
        "HOLD",
        "REENTRY_SUSPENSION_EVENT_BINDING_NOT_ESTABLISHED",
    )
    assert apply_reentry(bundle, decision)["final_state"] == "SUSPENDED"


def test_suspension_interval_must_equal_the_frozen_event_interval():
    bundle = _bundle()
    bundle["material_condition_changes"]["interval_start_tick"] = 991
    decision = evaluate_reentry(bundle)
    assert (decision.decision, decision.reason) == (
        "HOLD",
        "REENTRY_SUSPENSION_INTERVAL_NOT_ESTABLISHED",
    )
    assert apply_reentry(bundle, decision)["final_state"] == "SUSPENDED"


def test_remediation_source_must_bind_to_the_frozen_suspension_event():
    bundle = _bundle()
    bundle["remediation"]["source_id"] = "UNTRUSTED-REVIEW"
    decision = evaluate_reentry(bundle)
    assert (decision.decision, decision.reason) == (
        "HOLD",
        "REENTRY_SUSPENSION_EVENT_BINDING_NOT_ESTABLISHED",
    )


def test_missing_or_null_pre_decision_state_is_hold_not_exception_or_deny():
    missing = _bundle()
    missing.pop("pre_decision_operational_state")
    missing_decision = evaluate_reentry(missing)
    assert (missing_decision.decision, missing_decision.reason) == (
        "HOLD",
        "REENTRY_PRE_DECISION_STATE_NOT_VERIFIED",
    )

    null_value = _bundle()
    null_value["pre_decision_operational_state"] = None
    null_decision = evaluate_reentry(null_value)
    assert (null_decision.decision, null_decision.reason) == (
        "HOLD",
        "REENTRY_PRE_DECISION_STATE_NOT_VERIFIED",
    )


def test_verified_running_pre_decision_state_is_incompatible_deny():
    bundle = _bundle()
    bundle["pre_decision_operational_state"] = "RUNNING"
    decision = evaluate_reentry(bundle)
    assert (decision.decision, decision.reason) == (
        "DENY",
        "REENTRY_STATE_INCOMPATIBLE",
    )
