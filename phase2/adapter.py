"""Strict deterministic Phase 2 proposal parser / adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.models import ActionProposal


class ParseStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


class AdapterReasonCode(StrEnum):
    LLM_OUTPUT_NOT_JSON = "LLM_OUTPUT_NOT_JSON"
    LLM_OUTPUT_TOP_LEVEL_NOT_OBJECT = "LLM_OUTPUT_TOP_LEVEL_NOT_OBJECT"
    LLM_OUTPUT_DUPLICATE_KEY = "LLM_OUTPUT_DUPLICATE_KEY"
    LLM_OUTPUT_MISSING_REQUIRED_FIELD = "LLM_OUTPUT_MISSING_REQUIRED_FIELD"
    LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE = "LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE"
    LLM_OUTPUT_INVALID_FIELD_TYPE = "LLM_OUTPUT_INVALID_FIELD_TYPE"
    LLM_OUTPUT_UNRECOGNIZED_VALUE = "LLM_OUTPUT_UNRECOGNIZED_VALUE"
    LLM_OUTPUT_UNSUPPORTED_FIELD = "LLM_OUTPUT_UNSUPPORTED_FIELD"
    LLM_OUTPUT_FORBIDDEN_GOVERNANCE_FIELD = (
        "LLM_OUTPUT_FORBIDDEN_GOVERNANCE_FIELD"
    )
    # Reserved by the frozen v1.0 specification; strict v1.0 never emits it.
    LLM_OUTPUT_MULTIPLE_ACTIONS_AMBIGUOUS = "LLM_OUTPUT_MULTIPLE_ACTIONS_AMBIGUOUS"


REQUIRED_FIELDS = frozenset({"request_type", "behavior", "target", "speed"})
FORBIDDEN_FIELDS = frozenset(
    {
        "decision",
        "reason_codes",
        "restrictions",
        "execution_result",
        "applied_restrictions",
        "action_effect",
        "assurance_status",
        "authority_status",
        "policy_status",
        "evidence_status",
        "operating_condition",
        "risk_state",
        "oversight_status",
        "behavior_scope",
        "operational_state",
        "human_zone_prohibited",
        "evaluation_time",
        "evaluated_at",
        "policy_version",
        "rule_version",
        "initial_state",
        "final_state",
        "receipt_id",
        "governance_receipt_id",
    }
)
REQUEST_TYPES = frozenset({"ACTION", "REENTRY"})
VOCABULARY = {
    "behavior": frozenset({"MOVE", "LIFT"}),
    "target": frozenset({"ZONE_B", "HUMAN_ZONE"}),
    "speed": frozenset({"LOW", "NORMAL", "HIGH"}),
}


@dataclass(frozen=True)
class AdapterResult:
    parse_status: ParseStatus
    raw_output: str
    normalized_proposal: ActionProposal | None
    validation_reason_codes: tuple[AdapterReasonCode, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "parse_status": self.parse_status.value,
            "raw_output": self.raw_output,
            "normalized_proposal": (
                self.normalized_proposal.to_dict()
                if self.normalized_proposal is not None
                else None
            ),
            "validation_reason_codes": [
                item.value for item in self.validation_reason_codes
            ],
        }


def _invalid(raw_output: str, reason: AdapterReasonCode) -> AdapterResult:
    return AdapterResult(ParseStatus.INVALID, raw_output, None, (reason,))


def adapt(raw_output: str) -> AdapterResult:
    """Parse and validate one complete raw response in the frozen fail-fast order."""
    duplicate_key_detected = False

    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal duplicate_key_detected
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                duplicate_key_detected = True
            result[key] = value
        return result

    def reject_non_json_constant(value: str) -> None:
        raise ValueError(f"Non-JSON constant: {value}")

    # Step 1: the entire response must decode as exactly one JSON value.
    try:
        parsed = json.loads(
            raw_output,
            object_pairs_hook=object_pairs_hook,
            parse_constant=reject_non_json_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return _invalid(raw_output, AdapterReasonCode.LLM_OUTPUT_NOT_JSON)

    # Step 2: the top-level JSON value must be an object.
    if not isinstance(parsed, dict):
        return _invalid(raw_output, AdapterReasonCode.LLM_OUTPUT_TOP_LEVEL_NOT_OBJECT)

    # Step 3: reject duplicate keys detected in any parsed JSON object.
    if duplicate_key_detected:
        return _invalid(raw_output, AdapterReasonCode.LLM_OUTPUT_DUPLICATE_KEY)

    fields = frozenset(parsed)

    # Step 4: exact, case-sensitive forbidden governance/control names.
    if fields & FORBIDDEN_FIELDS:
        return _invalid(
            raw_output, AdapterReasonCode.LLM_OUTPUT_FORBIDDEN_GOVERNANCE_FIELD
        )

    # Step 5: every other extra top-level field is unsupported.
    if fields - REQUIRED_FIELDS:
        return _invalid(raw_output, AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_FIELD)

    # Step 6: all four proposal fields are required.
    if REQUIRED_FIELDS - fields:
        return _invalid(
            raw_output, AdapterReasonCode.LLM_OUTPUT_MISSING_REQUIRED_FIELD
        )

    # Step 7: every proposal value must be a JSON string.
    if any(not isinstance(parsed[field], str) for field in REQUIRED_FIELDS):
        return _invalid(raw_output, AdapterReasonCode.LLM_OUTPUT_INVALID_FIELD_TYPE)

    # Step 8: request_type uses its dedicated unsupported-string reason.
    if parsed["request_type"] not in REQUEST_TYPES:
        return _invalid(
            raw_output, AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE
        )

    # Step 9: other proposal strings must match their exact frozen vocabularies.
    if any(parsed[field] not in values for field, values in VOCABULARY.items()):
        return _invalid(raw_output, AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE)

    proposal = ActionProposal.from_dict(parsed)
    return AdapterResult(ParseStatus.VALID, raw_output, proposal, ())
