"""Frozen Phase 1 Governance Permission Composition (G)."""

from __future__ import annotations

from src.models import (
    ActionProposal,
    Decision,
    GovernanceContext,
    OperationalState,
    PermissionDecision,
    ReasonCode,
    RequestType,
)


SPEED_LOW_RESTRICTION = {"field": "speed", "operator": "<=", "value": "LOW"}


def _decision(
    context: GovernanceContext,
    decision: Decision,
    reasons: list[ReasonCode],
    restrictions: tuple[dict[str, str], ...] = (),
) -> PermissionDecision:
    return PermissionDecision(
        decision=decision,
        reason_codes=tuple(reasons),
        restrictions=restrictions,
        evaluated_at=context.evaluation_time,
    )


def compose_permission(
    proposal: ActionProposal, context: GovernanceContext
) -> PermissionDecision:
    """Evaluate one proposal in the frozen order without enforcement concerns."""
    if not proposal.is_valid() or not context.has_required_governance_input():
        return _decision(context, Decision.HOLD, [ReasonCode.INVALID_REQUEST])

    # Step 1: request/state compatibility.
    if (
        context.operational_state == OperationalState.RUNNING
        and proposal.request_type == RequestType.REENTRY
    ):
        return _decision(
            context,
            Decision.HOLD,
            [ReasonCode.REENTRY_NOT_APPLICABLE_WHILE_RUNNING],
        )
    if (
        context.operational_state == OperationalState.SUSPENDED
        and proposal.request_type == RequestType.ACTION
    ):
        return _decision(
            context,
            Decision.HOLD,
            [ReasonCode.OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY],
        )

    is_reentry = (
        context.operational_state == OperationalState.SUSPENDED
        and proposal.request_type == RequestType.REENTRY
    )

    # Step 2: explicit prohibitions. Preserve all applicable codes in fixed order.
    prohibitions: list[ReasonCode] = []
    if proposal.target == "HUMAN_ZONE" and context.human_zone_prohibited:
        prohibitions.append(ReasonCode.HUMAN_SAFETY_ZONE_PROHIBITED)
    if context.operating_condition == "PROHIBITED":
        prohibitions.append(ReasonCode.OPERATING_CONDITION_PROHIBITED)
    if (
        context.behavior_scope_status == "KNOWN"
        and proposal.behavior not in context.behavior_scope
    ):
        prohibitions.append(ReasonCode.BEHAVIOR_OUTSIDE_SCOPE)
    if prohibitions:
        return _decision(context, Decision.DENY, prohibitions)

    # Step 3: current governance preconditions.
    precondition_failures: list[ReasonCode] = []
    if context.assurance_status != "CURRENT":
        precondition_failures.append(ReasonCode.ASSURANCE_NOT_CURRENT)
    if context.authority_status != "VALID":
        precondition_failures.append(ReasonCode.AUTHORITY_STALE)
    if context.policy_status != "APPLICABLE":
        precondition_failures.append(ReasonCode.POLICY_NOT_APPLICABLE)
    if context.evidence_status != "CURRENT":
        precondition_failures.append(ReasonCode.EVIDENCE_STALE)
    if context.oversight_status != "AVAILABLE":
        precondition_failures.append(ReasonCode.OVERSIGHT_UNAVAILABLE)
    if context.behavior_scope_status != "KNOWN":
        precondition_failures.append(ReasonCode.BEHAVIOR_SCOPE_UNRESOLVED)
    if context.operating_condition not in {"NORMAL", "PROHIBITED", "LOW_SPEED_ONLY"}:
        precondition_failures.append(ReasonCode.OPERATING_CONDITION_UNRESOLVED)
    if context.risk_state != "NORMAL":
        precondition_failures.append(ReasonCode.RISK_STATE_REQUIRES_HOLD)
    if precondition_failures:
        if is_reentry:
            precondition_failures.append(ReasonCode.REENTRY_REVALIDATION_FAILED)
        return _decision(context, Decision.HOLD, precondition_failures)

    # Step 4: explicit machine-checkable restrictions. Re-entry outcome is
    # added only after enforcement, because success depends on application.
    if context.operating_condition == "LOW_SPEED_ONLY" and proposal.speed != "LOW":
        return _decision(
            context,
            Decision.RESTRICT,
            [ReasonCode.SPEED_RESTRICTION_REQUIRED],
            (SPEED_LOW_RESTRICTION,),
        )

    # Step 5: allow.
    reason = (
        ReasonCode.REENTRY_REVALIDATION_PASSED
        if is_reentry
        else ReasonCode.ALL_CURRENT_CONDITIONS_SATISFIED
    )
    return _decision(context, Decision.ALLOW, [reason])
