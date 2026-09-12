from __future__ import annotations

import pytest

from src.runner import run_scenario
from tests.helpers import make_fixture


def test_known_behavior_outside_scope_is_denied() -> None:
    result = run_scenario(
        make_fixture(request={"behavior": "LIFT"}, context={"behavior_scope": ["MOVE"]})
    )
    assert result.permission.decision.value == "DENY"
    assert result.receipt["reason_codes"] == ["BEHAVIOR_OUTSIDE_SCOPE"]
    assert result.enforcement.execution_result.value == "BLOCKED"


def test_unresolved_behavior_scope_is_held() -> None:
    result = run_scenario(
        make_fixture(context={"behavior_scope": [], "behavior_scope_status": "UNRESOLVED"})
    )
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == ["BEHAVIOR_SCOPE_UNRESOLVED"]
    assert result.enforcement.execution_result.value == "HELD"


def test_assurance_not_current_action_is_held() -> None:
    result = run_scenario(make_fixture(context={"assurance_status": "NOT_CURRENT"}))
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == ["ASSURANCE_NOT_CURRENT"]
    assert result.enforcement.execution_result.value == "HELD"


@pytest.mark.parametrize(
    ("restriction_supported", "execution", "final_state", "outcome_code", "outcome"),
    [
        (True, "EXECUTED_WITH_RESTRICTIONS", "RUNNING", "REENTRY_REVALIDATION_PASSED", "SUCCESS"),
        (False, "HELD", "SUSPENDED", "REENTRY_REVALIDATION_FAILED", "FAILED"),
    ],
)
def test_restricted_reentry_transition(
    restriction_supported: bool,
    execution: str,
    final_state: str,
    outcome_code: str,
    outcome: str,
) -> None:
    result = run_scenario(
        make_fixture(
            request={"request_type": "REENTRY", "speed": "HIGH"},
            context={
                "operational_state": "SUSPENDED",
                "operating_condition": "LOW_SPEED_ONLY",
            },
            restriction_application_supported=restriction_supported,
        )
    )
    assert result.permission.decision.value == "RESTRICT"
    assert [item.value for item in result.permission.reason_codes] == [
        "SPEED_RESTRICTION_REQUIRED"
    ]
    assert result.enforcement.execution_result.value == execution
    assert result.transition.final_state.value == final_state
    assert result.transition.reentry_outcome == outcome
    assert result.receipt["reason_codes"] == [
        "SPEED_RESTRICTION_REQUIRED",
        outcome_code,
    ]
    if restriction_supported:
        assert result.enforcement.executed_request is not None
        assert result.enforcement.executed_request["speed"] == "LOW"
    else:
        assert not result.enforcement.physical_action_performed


@pytest.mark.parametrize(
    ("kind", "decision", "execution", "final_state"),
    [
        ("ALLOW", "ALLOW", "EXECUTED", "RUNNING"),
        ("HOLD", "HOLD", "HELD", "SUSPENDED"),
        ("DENY", "DENY", "BLOCKED", "SUSPENDED"),
    ],
)
def test_other_reentry_transition_rows(
    kind: str, decision: str, execution: str, final_state: str
) -> None:
    context = {"operational_state": "SUSPENDED"}
    request = {"request_type": "REENTRY"}
    if kind == "HOLD":
        context["authority_status"] = "STALE"
    elif kind == "DENY":
        request["target"] = "HUMAN_ZONE"
        context["human_zone_prohibited"] = True
    result = run_scenario(make_fixture(request=request, context=context))
    assert result.permission.decision.value == decision
    assert result.enforcement.execution_result.value == execution
    assert result.transition.final_state.value == final_state
    assert result.transition.final_state.value in {"RUNNING", "SUSPENDED"}


def test_prohibited_operating_condition_is_denied() -> None:
    result = run_scenario(make_fixture(context={"operating_condition": "PROHIBITED"}))
    assert result.permission.decision.value == "DENY"
    assert result.receipt["reason_codes"] == ["OPERATING_CONDITION_PROHIBITED"]
