from copy import deepcopy
import json
from pathlib import Path

from phase3.identity import canonical_sha256
from phase3.models import DecisionResult
from phase3.physical import evaluate_physical_bundle, execute_allowed_move


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "phase3_scenarios" / "fixtures" / "physical_safe.json"


def _physical() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_complete_current_safe_bundle_has_no_block():
    assert evaluate_physical_bundle(_physical()) is None


def test_self_rewritten_observation_hash_cannot_replace_frozen_identity():
    observations = deepcopy(_physical())
    observation = observations["route_clearance"]
    observation["source_id"] = "UNTRUSTED-SOURCE"
    identity_input = {
        "observation_name": "route_clearance",
        "record": {
            key: value
            for key, value in observation.items()
            if key not in {"content_identity", "content_sha256"}
        },
    }
    digest = canonical_sha256(identity_input, exclude_volatile=False)
    observation["content_identity"] = "sha256:" + digest
    observation["content_sha256"] = digest

    result = evaluate_physical_bundle(observations)
    assert (result.decision, result.reason) == (
        "HOLD",
        "ROUTE_CLEARANCE_METADATA_NOT_ESTABLISHED",
    )


def test_physical_observations_must_match_the_requested_scope():
    result = evaluate_physical_bundle(
        _physical(), scope="MOVE / HUMAN_ZONE"
    )
    assert (result.decision, result.reason) == (
        "HOLD",
        "AGENT_ACTUAL_ZONE_METADATA_NOT_ESTABLISHED",
    )


def test_missing_occupancy_holds_and_never_defaults_to_clear():
    observations = deepcopy(_physical())
    observations.pop("target_zone_occupancy")
    result = evaluate_physical_bundle(observations)
    assert (result.decision, result.reason) == (
        "HOLD",
        "TARGET_ZONE_OCCUPANCY_MISSING",
    )
    assert result.command_status is None
    assert result.physical_action_count == 0


def test_post_command_mismatch_preserves_allow_and_suspends():
    permission = DecisionResult(
        "ALLOW", "ALL_CURRENT_CONDITIONS_SATISFIED", 1000
    )
    outcome = execute_allowed_move(permission, actual_state="ZONE_A")
    assert permission.decision == "ALLOW"
    assert outcome.command_status == "ISSUED"
    assert outcome.command_issued_at_tick == 1000
    assert outcome.expected_state == "ZONE_B"
    assert outcome.actual_state == "ZONE_A"
    assert outcome.verification_tick == 1001
    assert outcome.event == "PHYSICAL_STATE_MISMATCH_DETECTED"
    assert outcome.execution_result == "EFFECT_MISMATCH"
    assert outcome.final_state == "SUSPENDED"


def test_matching_post_command_observation_records_effect():
    permission = DecisionResult(
        "ALLOW", "ALL_CURRENT_CONDITIONS_SATISFIED", 1000
    )
    outcome = execute_allowed_move(permission, actual_state="ZONE_B")
    assert outcome.execution_result == "MOVED_TO_ZONE_B"
    assert outcome.command_issued_at_tick == 1000
    assert outcome.verification_tick == 1001
    assert outcome.final_state == "RUNNING"


def test_unknown_record_key_is_metadata_not_established_even_if_volatile_named():
    observations = deepcopy(_physical())
    observations["route_clearance"]["run_id"] = "candidate-run"
    result = evaluate_physical_bundle(observations)
    assert (result.decision, result.reason) == (
        "HOLD",
        "ROUTE_CLEARANCE_METADATA_NOT_ESTABLISHED",
    )


def test_stored_physical_hash_mismatch_is_content_identity_not_established():
    observations = deepcopy(_physical())
    observations["route_clearance"]["content_sha256"] = "0" * 64
    result = evaluate_physical_bundle(observations)
    assert (result.decision, result.reason) == (
        "HOLD",
        "ROUTE_CLEARANCE_CONTENT_IDENTITY_NOT_ESTABLISHED",
    )


def test_null_physical_value_is_not_established_without_command():
    observations = deepcopy(_physical())
    observations["route_clearance"]["value"] = None
    result = evaluate_physical_bundle(observations)
    assert (result.decision, result.reason) == (
        "HOLD",
        "ROUTE_CLEARANCE_VALUE_NOT_ESTABLISHED",
    )
    assert result.command_status is None
    assert result.physical_action_count == 0
