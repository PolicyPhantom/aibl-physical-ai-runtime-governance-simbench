"""Conjunctive ten-element Phase 3 re-entry evaluation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .constants import (
    ALLOW,
    DENY,
    HOLD,
    MATERIAL_CHANGE_FIELDS,
    MATERIAL_CHANGE_SOURCE_ID,
    REENTRY_ELEMENTS,
    REMEDIATION_FIELDS,
    REMEDIATION_MAX_AGE_TICKS,
    REMEDIATION_SOURCE_ID,
    RUNNING,
    SUSPENDED,
    SUSPENSION_EVENT_ID,
    SUSPENSION_INTERVAL_START_TICK,
    T_EVAL,
)
from .context import (
    CURRENT,
    NOT_ESTABLISHED,
    assemble_risk,
    authority_applicable,
    authority_status,
    observation_current,
    oversight_applicable,
    oversight_status,
    policy_applicable,
    policy_status,
    proposal_scope,
)
from .models import DecisionResult
from .physical import evaluate_physical_bundle


_EVIDENCE_FIELDS = frozenset(
    {
        "completeness",
        "completeness_reason",
        "present_file_integrity",
        "integrity_reason",
        "full_set_integrity",
        "missing_paths",
        "mismatched_paths",
        "unexpected_paths",
    }
)


def evaluate_reentry(
    bundle: dict[str, Any],
    *,
    tick: int = T_EVAL,
) -> DecisionResult:
    """Evaluate a bundle that has already crossed the core trust boundary."""
    if not isinstance(bundle, dict):
        return DecisionResult(HOLD, "REENTRY_REQUIRED_ELEMENT_MISSING", tick)
    if "pre_decision_operational_state" not in bundle:
        return DecisionResult(
            HOLD, "REENTRY_PRE_DECISION_STATE_NOT_VERIFIED", tick
        )
    missing = [
        key
        for key in REENTRY_ELEMENTS
        if key != "pre_decision_operational_state" and key not in bundle
    ]
    if missing:
        return DecisionResult(HOLD, "REENTRY_REQUIRED_ELEMENT_MISSING", tick)

    pre_decision_state = bundle["pre_decision_operational_state"]
    if not isinstance(pre_decision_state, str) or pre_decision_state not in {
        RUNNING,
        SUSPENDED,
    }:
        return DecisionResult(
            HOLD, "REENTRY_PRE_DECISION_STATE_NOT_VERIFIED", tick
        )
    if pre_decision_state != SUSPENDED:
        return DecisionResult(DENY, "REENTRY_STATE_INCOMPATIBLE", tick)

    request = bundle["normalized_request"]
    if not isinstance(request, dict):
        return DecisionResult(DENY, "REENTRY_REQUEST_INCOMPATIBLE", tick)
    if request.get("request_type") != "REENTRY":
        return DecisionResult(DENY, "REENTRY_REQUEST_INCOMPATIBLE", tick)

    scope = proposal_scope(request)
    if scope is None:
        return DecisionResult(DENY, "REENTRY_REQUEST_INCOMPATIBLE", tick)

    authority = bundle["authority"]
    current_authority = authority_status(authority, tick=tick)
    if current_authority == NOT_ESTABLISHED:
        return DecisionResult(HOLD, "CURRENT_AUTHORITY_NOT_ESTABLISHED", tick)
    if current_authority != CURRENT:
        return DecisionResult(HOLD, "CURRENT_AUTHORITY_STALE", tick)
    if not authority_applicable(authority, request):
        return DecisionResult(HOLD, "CURRENT_AUTHORITY_NOT_APPLICABLE", tick)

    policy = bundle["policy"]
    current_policy = policy_status(policy, tick=tick)
    if current_policy == NOT_ESTABLISHED:
        return DecisionResult(HOLD, "CURRENT_POLICY_NOT_ESTABLISHED", tick)
    if current_policy != CURRENT:
        return DecisionResult(HOLD, "CURRENT_POLICY_STALE", tick)
    if not policy_applicable(policy, request):
        return DecisionResult(HOLD, "CURRENT_POLICY_NOT_APPLICABLE", tick)

    risk = assemble_risk(
        bundle["risk_records"],
        bundle.get("source_priority_registry", {"rules": []}),
        tick=tick,
        scope=scope,
    )
    if risk["status"] == "CONFLICT_UNRESOLVED":
        return DecisionResult(HOLD, "RISK_CONTEXT_CONFLICT_UNRESOLVED", tick)
    if risk["status"] not in {"RESOLVED", "RESOLVED_BY_FROZEN_PRIORITY"}:
        return DecisionResult(HOLD, "CURRENT_RISK_NOT_ESTABLISHED", tick)
    if risk["value"] == "PROHIBITED":
        return DecisionResult(DENY, "CURRENT_RISK_PROHIBITED", tick)
    if risk["value"] != "ACCEPTABLE":
        return DecisionResult(HOLD, "CURRENT_RISK_NOT_ESTABLISHED", tick)

    oversight = bundle["oversight"]
    current_oversight = oversight_status(oversight, tick=tick)
    if current_oversight == NOT_ESTABLISHED:
        return DecisionResult(HOLD, "CURRENT_OVERSIGHT_NOT_ESTABLISHED", tick)
    if current_oversight != CURRENT:
        return DecisionResult(HOLD, "CURRENT_OVERSIGHT_STALE", tick)
    if not oversight_applicable(oversight, request):
        return DecisionResult(HOLD, "CURRENT_OVERSIGHT_NOT_APPLICABLE", tick)

    conditions = bundle["operational_physical_conditions"]
    if not isinstance(conditions, dict) or set(conditions) != {
        "operational_condition",
        "physical_observations",
    }:
        return DecisionResult(HOLD, "CURRENT_OPERATING_CONDITION_NOT_ESTABLISHED", tick)
    if conditions.get("operational_condition") != "SAFE":
        return DecisionResult(HOLD, "CURRENT_OPERATING_CONDITION_NOT_ESTABLISHED", tick)
    physical_block = evaluate_physical_bundle(
        conditions.get("physical_observations", {}), tick=tick, scope=scope
    )
    if physical_block is not None:
        return physical_block

    remediation = bundle["remediation"]
    if (
        not isinstance(remediation, dict)
        or set(remediation) != REMEDIATION_FIELDS
        or remediation.get("suspension_event_id") != SUSPENSION_EVENT_ID
        or remediation.get("source_id") != REMEDIATION_SOURCE_ID
        or remediation.get("max_age_ticks") != REMEDIATION_MAX_AGE_TICKS
        or remediation.get("cause_binding_valid") is not True
        or not isinstance(remediation.get("observed_at_tick"), int)
        or isinstance(remediation.get("observed_at_tick"), bool)
    ):
        return DecisionResult(
            HOLD, "REENTRY_SUSPENSION_EVENT_BINDING_NOT_ESTABLISHED", tick
        )
    if not observation_current(remediation, tick=tick):
        return DecisionResult(
            HOLD, "REENTRY_REMEDIATION_EVIDENCE_STALE", tick
        )
    if remediation.get("resolution_status") != "RESOLVED":
        return DecisionResult(HOLD, "REENTRY_REMEDIATION_NOT_ESTABLISHED", tick)

    verification = bundle["evidence_verification"]
    if not isinstance(verification, dict) or set(verification) != _EVIDENCE_FIELDS or not (
        verification.get("completeness") == "COMPLETE"
        and verification.get("present_file_integrity") == "INTEGRITY_VERIFIED"
        and verification.get("full_set_integrity") == "ESTABLISHED"
    ):
        return DecisionResult(HOLD, "CURRENT_EVIDENCE_NOT_VERIFIED", tick)

    changes = bundle["material_condition_changes"]
    if (
        not isinstance(changes, dict)
        or set(changes) != MATERIAL_CHANGE_FIELDS
        or changes.get("suspension_event_id") != SUSPENSION_EVENT_ID
        or changes.get("source_id") != MATERIAL_CHANGE_SOURCE_ID
    ):
        return DecisionResult(
            HOLD, "REENTRY_SUSPENSION_EVENT_BINDING_NOT_ESTABLISHED", tick
        )
    interval_values = (
        changes.get("interval_start_tick"),
        changes.get("interval_end_tick"),
        changes.get("reviewed_at_tick"),
    )
    if (
        not all(isinstance(value, int) and not isinstance(value, bool) for value in interval_values)
        or changes.get("interval_start_tick") != SUSPENSION_INTERVAL_START_TICK
        or changes.get("interval_end_tick") != tick
        or changes.get("reviewed_at_tick") != tick
    ):
        return DecisionResult(
            HOLD, "REENTRY_SUSPENSION_INTERVAL_NOT_ESTABLISHED", tick
        )
    if changes.get("material_changes_complete") is not True:
        return DecisionResult(HOLD, "MATERIAL_CHANGE_REVIEW_INCOMPLETE", tick)

    return DecisionResult(
        ALLOW,
        "ALL_CURRENT_REENTRY_CONDITIONS_SATISFIED",
        tick,
        enforcement="STATE_RESTORATION_ONLY",
    )


def apply_reentry(
    bundle: dict[str, Any],
    decision: DecisionResult,
) -> dict[str, Any]:
    """Apply only SUSPENDED-to-RUNNING restoration; never issue MOVE."""
    restored = (
        decision.decision == ALLOW
        and bundle.get("pre_decision_operational_state") == SUSPENDED
    )
    final_state = "RUNNING" if restored else SUSPENDED
    return {
        "initial_state": bundle.get("pre_decision_operational_state"),
        "final_state": final_state,
        "state_restoration": restored,
        "physical_command": None,
        "physical_action_count": 0,
    }


def with_verification(
    bundle: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    updated = deepcopy(bundle)
    updated["evidence_verification"] = deepcopy(verification)
    return updated
