from __future__ import annotations

import pytest

from src.runner import run_scenario
from tests.helpers import make_fixture


@pytest.mark.parametrize(
    ("state", "request_type", "decision", "reason", "execution", "final_state"),
    [
        (
            "RUNNING",
            "ACTION",
            "ALLOW",
            "ALL_CURRENT_CONDITIONS_SATISFIED",
            "EXECUTED",
            "RUNNING",
        ),
        (
            "RUNNING",
            "REENTRY",
            "HOLD",
            "REENTRY_NOT_APPLICABLE_WHILE_RUNNING",
            "HELD",
            "RUNNING",
        ),
        (
            "SUSPENDED",
            "ACTION",
            "HOLD",
            "OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY",
            "HELD",
            "SUSPENDED",
        ),
        (
            "SUSPENDED",
            "REENTRY",
            "ALLOW",
            "REENTRY_REVALIDATION_PASSED",
            "EXECUTED",
            "RUNNING",
        ),
    ],
)
def test_full_state_request_matrix(
    state: str,
    request_type: str,
    decision: str,
    reason: str,
    execution: str,
    final_state: str,
) -> None:
    result = run_scenario(
        make_fixture(
            request={"request_type": request_type},
            context={"operational_state": state},
        )
    )
    assert result.permission.decision.value == decision
    assert [item.value for item in result.permission.reason_codes] == [reason]
    assert result.enforcement.execution_result.value == execution
    assert result.transition.final_state.value == final_state


def test_state_compatibility_precedes_explicit_prohibition() -> None:
    result = run_scenario(
        make_fixture(
            request={"target": "HUMAN_ZONE"},
            context={
                "operational_state": "SUSPENDED",
                "human_zone_prohibited": True,
            },
        )
    )
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == [
        "OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY"
    ]
    assert not result.enforcement.physical_action_performed

