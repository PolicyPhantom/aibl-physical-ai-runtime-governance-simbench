from __future__ import annotations

import pytest

from src.runner import run_scenario
from tests.helpers import make_fixture


@pytest.mark.parametrize(
    ("authority", "evidence", "decision", "reasons", "execution"),
    [
        ("VALID", "CURRENT", "ALLOW", ["ALL_CURRENT_CONDITIONS_SATISFIED"], "EXECUTED"),
        ("STALE", "CURRENT", "HOLD", ["AUTHORITY_STALE"], "HELD"),
        ("VALID", "STALE", "HOLD", ["EVIDENCE_STALE"], "HELD"),
        (
            "STALE",
            "STALE",
            "HOLD",
            ["AUTHORITY_STALE", "EVIDENCE_STALE"],
            "HELD",
        ),
    ],
)
def test_authority_evidence_matrix(
    authority: str,
    evidence: str,
    decision: str,
    reasons: list[str],
    execution: str,
) -> None:
    result = run_scenario(
        make_fixture(
            context={"authority_status": authority, "evidence_status": evidence}
        )
    )
    assert result.permission.decision.value == decision
    assert result.receipt["reason_codes"] == reasons
    assert result.enforcement.execution_result.value == execution
    if decision != "ALLOW":
        assert not result.enforcement.physical_action_performed


@pytest.mark.parametrize(
    ("context_change", "expected_reason"),
    [
        ({"assurance_status": "NOT_CURRENT"}, "ASSURANCE_NOT_CURRENT"),
        ({"authority_status": "STALE"}, "AUTHORITY_STALE"),
        ({"policy_status": "NOT_APPLICABLE"}, "POLICY_NOT_APPLICABLE"),
        ({"evidence_status": "STALE"}, "EVIDENCE_STALE"),
        ({"oversight_status": "UNAVAILABLE"}, "OVERSIGHT_UNAVAILABLE"),
        ({"behavior_scope_status": "UNRESOLVED"}, "BEHAVIOR_SCOPE_UNRESOLVED"),
        ({"risk_state": "REQUIRES_HOLD"}, "RISK_STATE_REQUIRES_HOLD"),
    ],
)
def test_reentry_requires_current_validation(
    context_change: dict[str, str], expected_reason: str
) -> None:
    context = {"operational_state": "SUSPENDED", **context_change}
    result = run_scenario(
        make_fixture(request={"request_type": "REENTRY"}, context=context)
    )
    assert result.permission.decision.value == "HOLD"
    assert result.receipt["reason_codes"] == [
        expected_reason,
        "REENTRY_REVALIDATION_FAILED",
    ]
    assert result.enforcement.execution_result.value == "HELD"
    assert result.transition.final_state.value == "SUSPENDED"


def test_explicit_prohibition_precedes_stale_preconditions() -> None:
    result = run_scenario(
        make_fixture(
            request={"target": "HUMAN_ZONE"},
            context={"human_zone_prohibited": True, "authority_status": "STALE"},
        )
    )
    assert result.permission.decision.value == "DENY"
    assert result.receipt["reason_codes"] == ["HUMAN_SAFETY_ZONE_PROHIBITED"]

