"""Phase 3 action governance profile without Phase 1/2 mutation."""

from __future__ import annotations

from typing import Any

from .constants import ALLOW, DENY, HOLD, RUNNING, SUSPENDED, T_EVAL
from .context import (
    CURRENT,
    NOT_ESTABLISHED,
    assemble_risk,
    authority_applicable,
    authority_status,
    oversight_applicable,
    oversight_status,
    policy_applicable,
    policy_status,
    proposal_scope,
)
from .models import DecisionResult
from .physical import PhysicalIdentityExpectation, evaluate_physical_bundle


def evaluate_action(
    proposal: dict[str, str],
    context: dict[str, Any],
    physical_observations: dict[str, dict[str, Any]],
    *,
    tick: int = T_EVAL,
    physical_identity_expectation: PhysicalIdentityExpectation | None = None,
) -> DecisionResult:
    """Evaluate inputs that have already crossed the core trust boundary."""
    if not isinstance(proposal, dict) or not isinstance(context, dict):
        return DecisionResult(HOLD, "ACTION_CONTEXT_NOT_ESTABLISHED", tick)
    if proposal.get("request_type") != "ACTION":
        return DecisionResult(HOLD, "ACTION_REQUEST_REQUIRED", tick)
    if context.get("operational_state") == SUSPENDED:
        return DecisionResult(
            DENY,
            "OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY",
            tick,
        )
    if context.get("operational_state") != RUNNING:
        return DecisionResult(HOLD, "OPERATIONAL_STATE_UNRESOLVED", tick)

    scope = proposal_scope(proposal)
    if scope is None:
        return DecisionResult(HOLD, "ACTION_SCOPE_NOT_ESTABLISHED", tick)

    authority = context.get("authority", {})
    current_authority = authority_status(authority, tick=tick)
    if current_authority == NOT_ESTABLISHED:
        return DecisionResult(HOLD, "CURRENT_AUTHORITY_NOT_ESTABLISHED", tick)
    if current_authority != CURRENT:
        return DecisionResult(HOLD, "CURRENT_AUTHORITY_STALE", tick)
    if not authority_applicable(authority, proposal):
        return DecisionResult(HOLD, "CURRENT_AUTHORITY_NOT_APPLICABLE", tick)

    policy = context.get("policy", {})
    current_policy = policy_status(policy, tick=tick)
    if current_policy == NOT_ESTABLISHED:
        return DecisionResult(HOLD, "CURRENT_POLICY_NOT_ESTABLISHED", tick)
    if current_policy != CURRENT:
        return DecisionResult(HOLD, "CURRENT_POLICY_STALE", tick)
    if not policy_applicable(policy, proposal):
        return DecisionResult(HOLD, "CURRENT_POLICY_NOT_APPLICABLE", tick)

    risk = assemble_risk(
        context.get("risk_records", []),
        context.get("source_priority_registry", {}),
        tick=tick,
        scope=scope,
    )
    if risk["status"] == "CONFLICT_UNRESOLVED":
        return DecisionResult(HOLD, "RISK_CONTEXT_CONFLICT_UNRESOLVED", tick)
    if risk["status"] != "RESOLVED" and risk["status"] != "RESOLVED_BY_FROZEN_PRIORITY":
        return DecisionResult(HOLD, "CURRENT_RISK_NOT_ESTABLISHED", tick)
    if risk["value"] == "PROHIBITED":
        return DecisionResult(DENY, "CURRENT_RISK_PROHIBITED", tick)
    if risk["value"] != "ACCEPTABLE":
        return DecisionResult(HOLD, "CURRENT_RISK_NOT_ESTABLISHED", tick)

    oversight = context.get("oversight", {})
    current_oversight = oversight_status(oversight, tick=tick)
    if current_oversight == NOT_ESTABLISHED:
        return DecisionResult(HOLD, "CURRENT_OVERSIGHT_NOT_ESTABLISHED", tick)
    if current_oversight != CURRENT:
        return DecisionResult(HOLD, "CURRENT_OVERSIGHT_STALE", tick)
    if not oversight_applicable(oversight, proposal):
        return DecisionResult(HOLD, "CURRENT_OVERSIGHT_NOT_APPLICABLE", tick)

    physical_block = evaluate_physical_bundle(
        physical_observations, tick=tick, scope=scope,
        physical_identity_expectation=physical_identity_expectation,
    )
    if physical_block is not None:
        return physical_block

    return DecisionResult(
        ALLOW,
        "ALL_CURRENT_CONDITIONS_SATISFIED",
        tick,
        enforcement="PERMITTED",
    )
