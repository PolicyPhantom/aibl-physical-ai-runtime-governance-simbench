from __future__ import annotations

from pathlib import Path

from src.runner import load_scenario, run_scenario
from tests.helpers import make_fixture


def test_unresolved_operating_condition_action_is_held() -> None:
    result = run_scenario(make_fixture(context={"operating_condition": "UNRESOLVED"}))
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == ["OPERATING_CONDITION_UNRESOLVED"]
    assert result.enforcement.execution_result.value == "HELD"
    assert result.transition.final_state.value == "RUNNING"
    assert not result.enforcement.physical_action_performed


def test_unrecognized_nonempty_operating_condition_is_held() -> None:
    result = run_scenario(
        make_fixture(context={"operating_condition": "UNRECOGNIZED_PHASE1_VALUE"})
    )
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == ["OPERATING_CONDITION_UNRESOLVED"]
    assert result.enforcement.execution_result.value == "HELD"
    assert not result.enforcement.physical_action_performed


def test_unresolved_operating_condition_reentry_fails_closed() -> None:
    result = run_scenario(
        make_fixture(
            request={"request_type": "REENTRY"},
            context={
                "operational_state": "SUSPENDED",
                "operating_condition": "UNRESOLVED",
            },
        )
    )
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == [
        "OPERATING_CONDITION_UNRESOLVED",
        "REENTRY_REVALIDATION_FAILED",
    ]
    assert result.enforcement.execution_result.value == "HELD"
    assert result.transition.final_state.value == "SUSPENDED"
    assert result.transition.reentry_outcome == "FAILED"
    assert not result.enforcement.physical_action_performed


def test_missing_human_zone_prohibition_input_is_invalid_and_held() -> None:
    fixture = make_fixture(request={"target": "HUMAN_ZONE"})
    fixture["governance_context"].pop("human_zone_prohibited")
    result = run_scenario(fixture)
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == ["INVALID_REQUEST"]
    assert result.enforcement.execution_result.value == "HELD"
    assert result.transition.final_state.value == "RUNNING"
    assert result.receipt["governance_context"]["human_zone_prohibited"] is None
    assert not result.enforcement.physical_action_performed


def test_frozen_human_zone_scenario_still_denies_with_explicit_input() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "scenario_02_human_zone_deny.yaml"
    )
    fixture = load_scenario(path)
    assert fixture["governance_context"]["human_zone_prohibited"] is True
    result = run_scenario(fixture)
    assert result.permission.decision.value == "DENY"
    assert result.receipt["reason_codes"] == ["HUMAN_SAFETY_ZONE_PROHIBITED"]
    assert result.enforcement.execution_result.value == "BLOCKED"


def test_unresolved_operating_condition_result_is_deterministic() -> None:
    fixture = make_fixture(
        scenario_id="p1-sc-06-determinism",
        context={"operating_condition": "UNRESOLVED"},
    )
    first = run_scenario(fixture)
    second = run_scenario(fixture)
    assert first.permission == second.permission
    assert first.enforcement == second.enforcement
    assert first.transition == second.transition
    assert first.receipt == second.receipt
