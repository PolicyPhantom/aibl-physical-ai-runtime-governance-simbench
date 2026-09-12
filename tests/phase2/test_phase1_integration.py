from __future__ import annotations

import pytest

from phase2.runner import run_phase2_raw
from tests.helpers import make_fixture
from tests.phase2.helpers import PROMPT_VERSION, RAW_NORMAL, RUN_TIME, model_info


def run(raw: str, *, request=None, context=None, restriction_supported=True):
    fixture = make_fixture(
        scenario_id="phase2-integration",
        request=request,
        context=context,
        restriction_application_supported=restriction_supported,
    )
    return run_phase2_raw(
        raw,
        fixture,
        model=model_info(),
        prompt_version=PROMPT_VERSION,
        run_time=RUN_TIME,
    )


@pytest.mark.parametrize(
    ("raw", "context", "decision", "reason", "execution", "final_state"),
    [
        (
            RAW_NORMAL,
            {},
            "ALLOW",
            "ALL_CURRENT_CONDITIONS_SATISFIED",
            "EXECUTED",
            "RUNNING",
        ),
        (
            RAW_NORMAL.replace('"ZONE_B"', '"HUMAN_ZONE"'),
            {"human_zone_prohibited": True},
            "DENY",
            "HUMAN_SAFETY_ZONE_PROHIBITED",
            "BLOCKED",
            "RUNNING",
        ),
        (
            RAW_NORMAL.replace('"NORMAL"', '"HIGH"'),
            {"operating_condition": "LOW_SPEED_ONLY"},
            "RESTRICT",
            "SPEED_RESTRICTION_REQUIRED",
            "EXECUTED_WITH_RESTRICTIONS",
            "RUNNING",
        ),
        (
            RAW_NORMAL.replace('"MOVE"', '"LIFT"'),
            {},
            "DENY",
            "BEHAVIOR_OUTSIDE_SCOPE",
            "BLOCKED",
            "RUNNING",
        ),
    ],
)
def test_p2_01_through_p2_04_governance_paths(
    raw, context, decision, reason, execution, final_state
) -> None:
    result = run(raw, context=context)
    assert result.phase1_result is not None
    assert result.phase1_result.permission.decision.value == decision
    assert reason in result.phase1_result.receipt["reason_codes"]
    assert result.phase1_result.enforcement.execution_result.value == execution
    assert result.phase1_result.transition.final_state.value == final_state


def test_running_reentry_matrix_branch_is_preserved() -> None:
    raw = RAW_NORMAL.replace('"ACTION"', '"REENTRY"')
    result = run(raw)
    assert result.phase1_result is not None
    assert result.phase1_result.receipt["decision"] == "HOLD"
    assert result.phase1_result.receipt["reason_codes"] == [
        "REENTRY_NOT_APPLICABLE_WHILE_RUNNING"
    ]
    assert result.phase1_result.receipt["execution_result"] == "HELD"
    assert result.phase1_result.receipt["final_state"] == "RUNNING"


def test_suspended_action_is_preserved() -> None:
    result = run(RAW_NORMAL, context={"operational_state": "SUSPENDED"})
    assert result.phase1_result is not None
    assert result.phase1_result.receipt["decision"] == "HOLD"
    assert result.phase1_result.receipt["reason_codes"] == [
        "OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY"
    ]
    assert result.phase1_result.receipt["final_state"] == "SUSPENDED"


@pytest.mark.parametrize(
    ("restriction_supported", "speed", "condition", "decision", "execution", "final_state", "outcome"),
    [
        (True, "NORMAL", "NORMAL", "ALLOW", "EXECUTED", "RUNNING", "SUCCESS"),
        (
            True,
            "HIGH",
            "LOW_SPEED_ONLY",
            "RESTRICT",
            "EXECUTED_WITH_RESTRICTIONS",
            "RUNNING",
            "SUCCESS",
        ),
        (
            False,
            "HIGH",
            "LOW_SPEED_ONLY",
            "RESTRICT",
            "HELD",
            "SUSPENDED",
            "FAILED",
        ),
    ],
)
def test_p2_09_reentry_branches(
    restriction_supported,
    speed,
    condition,
    decision,
    execution,
    final_state,
    outcome,
) -> None:
    raw = RAW_NORMAL.replace('"ACTION"', '"REENTRY"').replace(
        '"NORMAL"', f'"{speed}"'
    )
    result = run(
        raw,
        context={
            "operational_state": "SUSPENDED",
            "operating_condition": condition,
        },
        restriction_supported=restriction_supported,
    )
    assert result.phase1_result is not None
    receipt = result.phase1_result.receipt
    assert receipt["decision"] == decision
    assert receipt["execution_result"] == execution
    assert receipt["final_state"] == final_state
    assert receipt["reentry_outcome"] == outcome
    if decision == "RESTRICT":
        expected_outcome_code = (
            "REENTRY_REVALIDATION_PASSED"
            if restriction_supported
            else "REENTRY_REVALIDATION_FAILED"
        )
        assert receipt["reason_codes"] == [
            "SPEED_RESTRICTION_REQUIRED",
            expected_outcome_code,
        ]


def test_invalid_adapter_output_never_reaches_phase1() -> None:
    result = run("not json")
    assert result.phase1_result is None
    assert result.provenance.governance_evaluation_status == "NOT_PERFORMED"
    assert result.provenance.enforcement_status == "NOT_PERFORMED"
    assert result.provenance.governance_receipt_id is None
    assert result.provenance.initial_operational_state == "RUNNING"
    assert result.provenance.final_operational_state == "RUNNING"
