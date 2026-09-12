"""Decision Receipt generation and receipt-only reconstruction."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.models import (
    ActionProposal,
    EnforcementResult,
    GovernanceContext,
    PermissionDecision,
    TransitionResult,
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def create_receipt(
    scenario_id: str,
    proposal: ActionProposal,
    context: GovernanceContext,
    permission: PermissionDecision,
    enforcement: EnforcementResult,
    transition: TransitionResult,
) -> dict[str, Any]:
    reason_codes = [item.value for item in permission.reason_codes]
    reason_codes.extend(item.value for item in transition.outcome_reason_codes)
    body: dict[str, Any] = {
        "scenario_id": scenario_id,
        "evaluation_time": context.evaluation_time,
        "rule_version": context.policy_version,
        "request": proposal.to_dict(),
        "governance_context": context.to_dict(),
        "decision": permission.decision.value,
        "reason_codes": reason_codes,
        "restrictions": [dict(item) for item in permission.restrictions],
        "execution_result": enforcement.execution_result.value,
        "enforcement": enforcement.to_dict(),
        "initial_state": context.operational_state.value,
        "final_state": transition.final_state.value,
        "reentry_outcome": transition.reentry_outcome,
    }
    body["receipt_id"] = "p1-" + hashlib.sha256(_canonical(body).encode()).hexdigest()[:20]
    return {"receipt_id": body.pop("receipt_id"), **body}


def reconstruct(receipt: dict[str, Any]) -> dict[str, Any]:
    """Answer the ten frozen reconstruction questions from a receipt alone."""
    request = receipt["request"]
    context = receipt["governance_context"]
    return {
        "requested_behavior": request["behavior"],
        "request": request,
        "initial_operational_state": receipt["initial_state"],
        "rule_version": receipt["rule_version"],
        "authority_status": context["authority_status"],
        "evidence_status": context["evidence_status"],
        "operating_condition": context["operating_condition"],
        "risk_state": context["risk_state"],
        "permission_decision": receipt["decision"],
        "reason_codes": receipt["reason_codes"],
        "restrictions": receipt["restrictions"],
        "enforcement_result": receipt["execution_result"],
        "applied_restrictions": receipt["enforcement"]["applied_restrictions"],
        "reentry_outcome": receipt["reentry_outcome"],
        "final_state": receipt["final_state"],
    }

