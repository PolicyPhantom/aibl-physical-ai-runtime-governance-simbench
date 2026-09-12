"""Frozen Phase 1 Runtime Enforcement (F)."""

from __future__ import annotations

from src.models import (
    ActionProposal,
    Decision,
    EnforcementResult,
    ExecutionResultCode,
    PermissionDecision,
)
from src.permission import SPEED_LOW_RESTRICTION


def _effect(proposal: dict[str, object]) -> str:
    if proposal["request_type"] == "REENTRY":
        return "REENTRY_ENFORCED"
    return f"MOVED_TO_{proposal['target']}"


def enforce(
    proposal: ActionProposal,
    permission: PermissionDecision,
    *,
    restriction_application_supported: bool = True,
) -> EnforcementResult:
    """Enforce the decision without recomputing governance policy."""
    if permission.decision == Decision.ALLOW:
        request = proposal.to_dict()
        return EnforcementResult(
            ExecutionResultCode.EXECUTED,
            executed_request=request,
            action_effect=_effect(request),
        )

    if permission.decision == Decision.RESTRICT:
        supported = (
            restriction_application_supported
            and permission.restrictions == (SPEED_LOW_RESTRICTION,)
            and proposal.speed in {"NORMAL", "HIGH"}
        )
        if not supported:
            return EnforcementResult(ExecutionResultCode.HELD)
        request = proposal.to_dict()
        request["speed"] = "LOW"
        return EnforcementResult(
            ExecutionResultCode.EXECUTED_WITH_RESTRICTIONS,
            applied_restrictions=permission.restrictions,
            executed_request=request,
            action_effect=_effect(request),
        )

    if permission.decision == Decision.HOLD:
        return EnforcementResult(ExecutionResultCode.HELD)
    return EnforcementResult(ExecutionResultCode.BLOCKED)

