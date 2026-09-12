from copy import deepcopy

from phase3.constants import VOLATILE_FIELDS
from phase3.identity import canonical_sha256
from phase3.replay import compare_results


def _set_decision_identity(value: dict) -> None:
    identity_input = {
        key: deepcopy(item)
        for key, item in value.items()
        if key != "decision_identity" and key not in VOLATILE_FIELDS
    }
    value["decision_identity"] = canonical_sha256(
        identity_input, exclude_volatile=False
    )


def _set_evaluated_input_identity(value: dict) -> None:
    basis = value["decision_basis"]
    basis["evaluated_input_identity"] = canonical_sha256(
        basis["evaluated_input"], exclude_volatile=False
    )


def _result() -> dict:
    value = {
        "scenario_id": "P3-B-01",
        "raw_sha256": "a" * 64,
        "perturbation_identity": "b" * 64,
        "adapter": {"status": "VALID", "reason": None},
        "normalized_proposal": {"request_type": "ACTION"},
        "governance": {
            "decision": "HOLD",
            "reason": "CURRENT_AUTHORITY_STALE",
        },
        "verification": None,
        "enforcement": "NOT_PERFORMED",
        "command_status": None,
        "physical_result": None,
        "physical_action_count": 0,
        "receipt_present": True,
        "initial_state": "RUNNING",
        "final_state": "RUNNING",
        "followup": None,
        "decision_basis": {
            "scenario_contract_identity": "c" * 64,
            "fixture_identities": {
                "proposal_raw_sha256": "a" * 64,
                "common_context": "d" * 64,
            },
            "evaluation_stage": "ACTION_GOVERNANCE",
            "evaluated_input": {
                "context": {
                    "authority_source": "AUTHORITY-REGISTRY-01",
                    "run_id": "decision-input-run-1",
                },
                "tick": 1000,
            },
            "evaluated_input_identity": "",
        },
        "run_id": "run-1",
        "attempt_number": 1,
    }
    _set_evaluated_input_identity(value)
    _set_decision_identity(value)
    return value


def test_permitted_volatile_variance_does_not_change_decision_identity():
    reference = _result()
    candidate = deepcopy(reference)
    candidate["run_id"] = "run-2"
    candidate["attempt_number"] = 2
    _set_decision_identity(candidate)
    comparison = compare_results(reference, candidate)
    assert comparison["must_match"]
    assert comparison["differing_fields"] == []
    assert reference["decision_identity"] == candidate["decision_identity"]
    assert comparison["reference_identity_valid"]
    assert comparison["candidate_identity_valid"]
    assert comparison["reference_evaluated_input_identity_valid"]
    assert comparison["candidate_evaluated_input_identity_valid"]


def test_decision_variance_is_detected():
    reference = _result()
    candidate = deepcopy(reference)
    candidate["governance"]["decision"] = "ALLOW"
    _set_decision_identity(candidate)
    comparison = compare_results(reference, candidate)
    assert not comparison["must_match"]
    assert "governance" in comparison["differing_fields"]
    assert "decision_identity" in comparison["differing_fields"]


def test_every_decision_bearing_result_field_participates_in_replay():
    reference = _result()
    candidate = deepcopy(reference)
    candidate["physical_action_count"] = 1
    _set_decision_identity(candidate)
    comparison = compare_results(reference, candidate)
    assert not comparison["must_match"]
    assert "physical_action_count" in comparison["differing_fields"]
    assert "decision_identity" in comparison["differing_fields"]


def test_stale_embedded_decision_identity_is_rejected():
    reference = _result()
    candidate = deepcopy(reference)
    candidate["receipt_present"] = False
    comparison = compare_results(reference, candidate)
    assert not comparison["must_match"]
    assert "receipt_present" in comparison["differing_fields"]
    assert "decision_identity" in comparison["differing_fields"]
    assert comparison["reference_identity_valid"]
    assert not comparison["candidate_identity_valid"]


def test_modified_evaluated_input_with_stale_hash_is_rejected():
    reference = _result()
    candidate = deepcopy(reference)
    candidate["decision_basis"]["evaluated_input"]["context"][
        "authority_source"
    ] = "CANDIDATE-SOURCE"
    comparison = compare_results(reference, candidate)
    assert not comparison["must_match"]
    assert "decision_basis" in comparison["differing_fields"]
    assert not comparison["candidate_evaluated_input_identity_valid"]
    assert not comparison["candidate_identity_valid"]


def test_modified_basis_and_recomputed_hashes_still_differs_from_reference():
    reference = _result()
    candidate = deepcopy(reference)
    candidate["decision_basis"]["evaluated_input"]["context"]["run_id"] = (
        "decision-input-run-2"
    )
    _set_evaluated_input_identity(candidate)
    _set_decision_identity(candidate)
    comparison = compare_results(reference, candidate)
    assert not comparison["must_match"]
    assert "decision_basis" in comparison["differing_fields"]
    assert "decision_identity" in comparison["differing_fields"]
    assert comparison["candidate_evaluated_input_identity_valid"]
    assert comparison["candidate_identity_valid"]
    assert reference["decision_identity"] != candidate["decision_identity"]


def test_modified_stored_basis_hash_is_rejected_even_with_new_decision_identity():
    reference = _result()
    candidate = deepcopy(reference)
    candidate["decision_basis"]["evaluated_input_identity"] = "f" * 64
    _set_decision_identity(candidate)
    comparison = compare_results(reference, candidate)
    assert not comparison["must_match"]
    assert "decision_basis" in comparison["differing_fields"]
    assert not comparison["candidate_evaluated_input_identity_valid"]
    assert comparison["candidate_identity_valid"]
