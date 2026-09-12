"""Seven-observation validation and deterministic post-command monitoring."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from .constants import (
    ALLOW,
    DENY,
    HOLD,
    CORE_SCOPE,
    PHYSICAL_CONTENT_SHA256,
    PHYSICAL_CURRENTNESS_RULE_ID,
    PHYSICAL_FIELDS,
    PHYSICAL_MAX_AGE_TICKS,
    PHYSICAL_PROHIBITED_VALUES,
    PHYSICAL_RECORD_FIELDS,
    PHYSICAL_SAFE_VALUES,
    PHYSICAL_SOURCE_IDS,
    RUNNING,
    SUSPENDED,
    T_COMMAND,
    T_EVAL,
    T_VERIFY,
)
from .context import observation_current
from .identity import canonical_sha256
from .models import DecisionResult, PhysicalResult


_CONTENT_IDENTITY_FIELDS = frozenset({"content_identity", "content_sha256"})


@dataclass(frozen=True, slots=True, init=False)
class PhysicalIdentityExpectation:
    """Externally supplied identity expectations, not proof of human approval.

    The caller must verify its separate approved manifest/control chain.
    Candidate observations are never used to construct this value here.
    """

    entries: tuple[tuple[str, str], ...]

    def __init__(self, expected: Mapping[str, str]) -> None:
        if not isinstance(expected, Mapping):
            raise TypeError("Physical identity expectation requires a mapping")
        copied = dict(expected)
        if set(copied) != set(PHYSICAL_FIELDS):
            raise ValueError("Physical identity expectation requires all seven records")
        if any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
               for value in copied.values()):
            raise ValueError("Physical identity expectation requires lowercase SHA-256")
        object.__setattr__(self, "entries", tuple((name, copied[name]) for name in PHYSICAL_FIELDS))

    def expected_sha256(self, field: str) -> str:
        return self.entries[PHYSICAL_FIELDS.index(field)][1]

    def to_dict(self) -> dict[str, str]:
        return dict(self.entries)


def _content_identity_valid(
    field: str,
    observation: dict[str, Any],
    physical_identity_expectation: PhysicalIdentityExpectation | None = None,
) -> bool:
    expected = (PHYSICAL_CONTENT_SHA256[field] if physical_identity_expectation is None
                else physical_identity_expectation.expected_sha256(field))
    payload = {
        key: value
        for key, value in observation.items()
        if key not in _CONTENT_IDENTITY_FIELDS
    }
    try:
        calculated = canonical_sha256(
            {
                "observation_name": field,
                "record": payload,
            },
            exclude_volatile=False,
        )
    except (TypeError, ValueError):
        return False
    return (
        calculated == expected
        and observation.get("content_sha256") == expected
        and observation.get("content_identity") == f"sha256:{expected}"
    )


def _metadata_valid(
    field: str,
    observation: dict[str, Any],
    *,
    scope: str,
) -> bool:
    observed_at_tick = observation.get("observed_at_tick")
    max_age_ticks = observation.get("max_age_ticks")
    return (
        observation.get("source_id") == PHYSICAL_SOURCE_IDS[field]
        and isinstance(observed_at_tick, int)
        and not isinstance(observed_at_tick, bool)
        and isinstance(max_age_ticks, int)
        and not isinstance(max_age_ticks, bool)
        and max_age_ticks == PHYSICAL_MAX_AGE_TICKS
        and observation.get("scope") == scope
        and observation.get("currentness_rule_id")
        == PHYSICAL_CURRENTNESS_RULE_ID
    )


def evaluate_physical_bundle(
    observations: dict[str, dict[str, Any]],
    *,
    tick: int = T_EVAL,
    scope: str = CORE_SCOPE,
    physical_identity_expectation: PhysicalIdentityExpectation | None = None,
) -> DecisionResult | None:
    """Validate trusted internal observations; return a block or safe None."""
    if physical_identity_expectation is not None and type(physical_identity_expectation) is not PhysicalIdentityExpectation:
        raise TypeError("PhysicalIdentityExpectation or None required")
    if not isinstance(observations, dict):
        return DecisionResult(HOLD, "PHYSICAL_OBSERVATIONS_INVALID", tick)
    for field in PHYSICAL_FIELDS:
        if field not in observations:
            reason = (
                "TARGET_ZONE_OCCUPANCY_MISSING"
                if field == "target_zone_occupancy"
                else f"{field.upper()}_MISSING"
            )
            return DecisionResult(HOLD, reason, tick)
    if set(observations) != set(PHYSICAL_FIELDS):
        return DecisionResult(HOLD, "PHYSICAL_OBSERVATIONS_INVALID", tick)

    for field in PHYSICAL_FIELDS:
        observation = observations[field]
        if not isinstance(observation, dict):
            return DecisionResult(
                HOLD, f"{field.upper()}_METADATA_NOT_ESTABLISHED", tick
            )
        unknown_fields = set(observation) - PHYSICAL_RECORD_FIELDS
        metadata_fields = PHYSICAL_RECORD_FIELDS - {
            "value",
            "content_identity",
            "content_sha256",
        }
        if unknown_fields or not metadata_fields.issubset(observation) or not _metadata_valid(
            field, observation, scope=scope
        ):
            return DecisionResult(
                HOLD, f"{field.upper()}_METADATA_NOT_ESTABLISHED", tick
            )
        value = observation.get("value")
        if not isinstance(value, str) or not value or value == "UNKNOWN":
            return DecisionResult(
                HOLD, f"{field.upper()}_VALUE_NOT_ESTABLISHED", tick
            )
        if value in PHYSICAL_PROHIBITED_VALUES.get(field, frozenset()):
            return DecisionResult(
                DENY, f"{field.upper()}_EXPLICITLY_PROHIBITED", tick
            )
        if value != PHYSICAL_SAFE_VALUES[field]:
            return DecisionResult(
                HOLD, f"{field.upper()}_VALUE_NOT_ESTABLISHED", tick
            )
        if not {"content_identity", "content_sha256"}.issubset(observation) or not _content_identity_valid(
            field, observation, physical_identity_expectation
        ):
            return DecisionResult(
                HOLD, f"{field.upper()}_CONTENT_IDENTITY_NOT_ESTABLISHED", tick
            )
        if not observation_current(observation, tick=tick):
            return DecisionResult(HOLD, f"{field.upper()}_STALE", tick)
    return None


def execute_allowed_move(
    decision: DecisionResult,
    *,
    actual_state: str,
    initial_state: str = RUNNING,
    verification_tick: int = T_VERIFY,
) -> PhysicalResult:
    if decision.decision != ALLOW:
        raise ValueError("physical command requires an ALLOW decision")
    if initial_state != RUNNING:
        raise ValueError("physical command requires RUNNING state")
    if (
        not isinstance(verification_tick, int)
        or isinstance(verification_tick, bool)
        or verification_tick != T_VERIFY
    ):
        raise ValueError("physical verification requires the frozen T_VERIFY")

    if actual_state == "ZONE_B":
        return PhysicalResult(
            command_status="ISSUED",
            command_issued_at_tick=T_COMMAND,
            expected_state="ZONE_B",
            actual_state=actual_state,
            verification_tick=verification_tick,
            event=None,
            execution_result="MOVED_TO_ZONE_B",
            initial_state=initial_state,
            final_state=RUNNING,
            physical_action_count=1,
        )
    return PhysicalResult(
        command_status="ISSUED",
        command_issued_at_tick=T_COMMAND,
        expected_state="ZONE_B",
        actual_state=actual_state,
        verification_tick=verification_tick,
        event="PHYSICAL_STATE_MISMATCH_DETECTED",
        execution_result="EFFECT_MISMATCH",
        initial_state=initial_state,
        final_state=SUSPENDED,
        physical_action_count=1,
    )
