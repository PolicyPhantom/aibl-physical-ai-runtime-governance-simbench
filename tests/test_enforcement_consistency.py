from __future__ import annotations

from src.models import (
    ActionProposal,
    Decision,
    PermissionDecision,
    ReasonCode,
)
from src.enforcement import enforce
from src.permission import SPEED_LOW_RESTRICTION
from src.runner import run_scenario
from tests.helpers import make_fixture


PROPOSAL = ActionProposal("ACTION", "MOVE", "ZONE_B", "HIGH")
TIME = "2026-08-27T15:00:00+09:00"


def decision(
    value: Decision,
    reason: ReasonCode,
    restrictions: tuple[dict[str, str], ...] = (),
) -> PermissionDecision:
    return PermissionDecision(value, (reason,), restrictions, TIME)


def test_allow_executes() -> None:
    result = enforce(
        PROPOSAL,
        decision(Decision.ALLOW, ReasonCode.ALL_CURRENT_CONDITIONS_SATISFIED),
    )
    assert result.execution_result.value == "EXECUTED"
    assert result.physical_action_performed


def test_restrict_executes_only_after_application() -> None:
    permission = decision(
        Decision.RESTRICT,
        ReasonCode.SPEED_RESTRICTION_REQUIRED,
        (SPEED_LOW_RESTRICTION,),
    )
    result = enforce(PROPOSAL, permission)
    assert result.execution_result.value == "EXECUTED_WITH_RESTRICTIONS"
    assert result.executed_request is not None
    assert result.executed_request["speed"] == "LOW"
    assert result.applied_restrictions == permission.restrictions


def test_restrict_application_failure_is_held_without_action() -> None:
    permission = decision(
        Decision.RESTRICT,
        ReasonCode.SPEED_RESTRICTION_REQUIRED,
        (SPEED_LOW_RESTRICTION,),
    )
    result = enforce(PROPOSAL, permission, restriction_application_supported=False)
    assert permission.decision == Decision.RESTRICT
    assert result.execution_result.value == "HELD"
    assert not result.physical_action_performed
    assert result.executed_request is None


def test_unrecognized_restriction_is_held_without_action() -> None:
    permission = decision(
        Decision.RESTRICT,
        ReasonCode.SPEED_RESTRICTION_REQUIRED,
        ({"field": "unknown", "operator": "=", "value": "x"},),
    )
    result = enforce(PROPOSAL, permission)
    assert result.execution_result.value == "HELD"
    assert not result.physical_action_performed


def test_hold_and_deny_never_act() -> None:
    hold = enforce(
        PROPOSAL, decision(Decision.HOLD, ReasonCode.AUTHORITY_STALE)
    )
    deny = enforce(
        PROPOSAL,
        decision(Decision.DENY, ReasonCode.HUMAN_SAFETY_ZONE_PROHIBITED),
    )
    assert hold.execution_result.value == "HELD"
    assert deny.execution_result.value == "BLOCKED"
    assert not hold.physical_action_performed
    assert not deny.physical_action_performed


def test_malformed_request_is_safely_held() -> None:
    result = run_scenario(make_fixture(request={"behavior": None}))
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == ["INVALID_REQUEST"]
    assert result.enforcement.execution_result.value == "HELD"
    assert not result.enforcement.physical_action_performed

