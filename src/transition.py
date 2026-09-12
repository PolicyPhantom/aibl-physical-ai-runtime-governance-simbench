"""Frozen Phase 1 operational state transitions."""

from __future__ import annotations

from src.models import (
    ActionProposal,
    Decision,
    EnforcementResult,
    ExecutionResultCode,
    GovernanceContext,
    OperationalState,
    PermissionDecision,
    ReasonCode,
    RequestType,
    TransitionResult,
)


def transition_state(
    proposal: ActionProposal,
    context: GovernanceContext,
    permission: PermissionDecision,
    enforcement: EnforcementResult,
) -> TransitionResult:
    """Apply only the explicitly frozen state-transition rules."""
    if context.operational_state == OperationalState.RUNNING:
        return TransitionResult(final_state=OperationalState.RUNNING)

    if proposal.request_type == RequestType.ACTION:
        return TransitionResult(final_state=OperationalState.SUSPENDED)

    if proposal.request_type != RequestType.REENTRY:
        return TransitionResult(final_state=OperationalState.SUSPENDED)

    if (
        permission.decision == Decision.ALLOW
        and enforcement.execution_result == ExecutionResultCode.EXECUTED
    ):
        return TransitionResult(
            final_state=OperationalState.RUNNING,
            reentry_outcome="SUCCESS",
        )

    if permission.decision == Decision.RESTRICT:
        if (
            enforcement.execution_result
            == ExecutionResultCode.EXECUTED_WITH_RESTRICTIONS
        ):
            return TransitionResult(
                final_state=OperationalState.RUNNING,
                reentry_outcome="SUCCESS",
                outcome_reason_codes=(ReasonCode.REENTRY_REVALIDATION_PASSED,),
            )
        return TransitionResult(
            final_state=OperationalState.SUSPENDED,
            reentry_outcome="FAILED",
            outcome_reason_codes=(ReasonCode.REENTRY_REVALIDATION_FAILED,),
        )

    return TransitionResult(
        final_state=OperationalState.SUSPENDED,
        reentry_outcome="FAILED",
    )

