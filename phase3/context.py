"""Deterministic currentness and conflict assembly."""

from __future__ import annotations

from typing import Any

from .constants import (
    AUTHORITY_FIELDS,
    AUTHORITY_ID,
    AUTHORITY_SOURCE_ID,
    CORE_POLICY_VERSION,
    CORE_SCOPE,
    OVERSIGHT_ASSIGNMENT_ID,
    OVERSIGHT_FIELDS,
    OVERSIGHT_MAX_AGE_TICKS,
    OVERSIGHT_SOURCE_ID,
    POLICY_FIELDS,
    POLICY_ID,
    POLICY_SOURCE_ID,
    RISK_FIELDS,
    RISK_MAX_AGE_TICKS,
    RISK_SOURCE_CONTRACTS,
    SOURCE_PRIORITY_REGISTRY_FIELDS,
    SOURCE_PRIORITY_REGISTRY_ID,
    SOURCE_PRIORITY_REGISTRY_VERSION,
    T_EVAL,
)


CURRENT = "CURRENT"
STALE = "STALE"
NOT_ESTABLISHED = "NOT_ESTABLISHED"


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _has_exact_fields(record: Any, fields: frozenset[str]) -> bool:
    return isinstance(record, dict) and set(record) == fields


def interval_current(
    record: dict[str, Any],
    start_field: str,
    end_field: str,
    *,
    tick: int = T_EVAL,
) -> bool:
    if not isinstance(record, dict):
        return False
    start = record.get(start_field)
    end = record.get(end_field)
    if not _is_integer(start) or not _is_integer(end):
        return False
    return (
        start <= tick < end
        and not bool(record.get("revoked", False))
        and record.get("superseded_by") is None
    )


def observation_age(
    record: dict[str, Any],
    observed_field: str = "observed_at_tick",
    *,
    tick: int = T_EVAL,
) -> int:
    observed = record.get(observed_field)
    if not _is_integer(observed):
        raise ValueError("observation tick must be an integer")
    return tick - observed


def observation_current(
    record: dict[str, Any],
    observed_field: str = "observed_at_tick",
    *,
    tick: int = T_EVAL,
) -> bool:
    if not isinstance(record, dict):
        return False
    maximum_age = record.get("max_age_ticks")
    if not _is_integer(maximum_age) or maximum_age < 0:
        return False
    try:
        age = observation_age(record, observed_field, tick=tick)
    except ValueError:
        return False
    return 0 <= age <= maximum_age


def authority_status(record: dict[str, Any], *, tick: int = T_EVAL) -> str:
    if not _has_exact_fields(record, AUTHORITY_FIELDS):
        return NOT_ESTABLISHED
    if (
        record.get("authority_id") != AUTHORITY_ID
        or record.get("source_id") != AUTHORITY_SOURCE_ID
        or not isinstance(record.get("status"), str)
        or not _is_integer(record.get("valid_from_tick"))
        or not _is_integer(record.get("valid_until_tick"))
        or not isinstance(record.get("revoked"), bool)
        or (
            record.get("superseded_by") is not None
            and not isinstance(record.get("superseded_by"), str)
        )
        or not isinstance(record.get("scope_request_type"), list)
        or not all(
            isinstance(item, str) and item
            for item in record.get("scope_request_type", [])
        )
        or not isinstance(record.get("scope_behavior"), str)
        or not isinstance(record.get("scope_target"), str)
    ):
        return NOT_ESTABLISHED
    if record["status"] != "VALID" or not interval_current(
        record, "valid_from_tick", "valid_until_tick", tick=tick
    ):
        return STALE
    return CURRENT


def authority_current(record: dict[str, Any], *, tick: int = T_EVAL) -> bool:
    return authority_status(record, tick=tick) == CURRENT


def policy_status(record: dict[str, Any], *, tick: int = T_EVAL) -> str:
    if not _has_exact_fields(record, POLICY_FIELDS):
        return NOT_ESTABLISHED
    if (
        record.get("policy_id") != POLICY_ID
        or record.get("source_id") != POLICY_SOURCE_ID
        or record.get("version") != CORE_POLICY_VERSION
        or not _is_integer(record.get("effective_from_tick"))
        or not _is_integer(record.get("effective_until_tick"))
        or (
            record.get("superseded_by") is not None
            and not isinstance(record.get("superseded_by"), str)
        )
        or not isinstance(record.get("applicable_behavior"), str)
        or not isinstance(record.get("applicable_target"), str)
    ):
        return NOT_ESTABLISHED
    if not interval_current(
        record, "effective_from_tick", "effective_until_tick", tick=tick
    ):
        return STALE
    return CURRENT


def policy_current(record: dict[str, Any], *, tick: int = T_EVAL) -> bool:
    return policy_status(record, tick=tick) == CURRENT


def proposal_scope(proposal: dict[str, Any]) -> str | None:
    if not isinstance(proposal, dict):
        return None
    behavior = proposal.get("behavior")
    target = proposal.get("target")
    if not isinstance(behavior, str) or not isinstance(target, str):
        return None
    return f"{behavior} / {target}"


def authority_applicable(
    record: dict[str, Any],
    proposal: dict[str, Any],
) -> bool:
    if not isinstance(record, dict) or not isinstance(proposal, dict):
        return False
    request_types = record.get("scope_request_type")
    return (
        isinstance(request_types, list)
        and proposal.get("request_type") in request_types
        and record.get("scope_behavior") == proposal.get("behavior")
        and record.get("scope_target") == proposal.get("target")
    )


def policy_applicable(
    record: dict[str, Any],
    proposal: dict[str, Any],
) -> bool:
    if not isinstance(record, dict) or not isinstance(proposal, dict):
        return False
    return (
        record.get("version") == CORE_POLICY_VERSION
        and record.get("applicable_behavior") == proposal.get("behavior")
        and record.get("applicable_target") == proposal.get("target")
    )


def oversight_applicable(
    record: dict[str, Any],
    proposal: dict[str, Any],
) -> bool:
    if not isinstance(record, dict):
        return False
    scope = proposal_scope(proposal)
    return scope is not None and record.get("scope") == scope


def oversight_status(record: dict[str, Any], *, tick: int = T_EVAL) -> str:
    if not _has_exact_fields(record, OVERSIGHT_FIELDS):
        return NOT_ESTABLISHED
    if (
        record.get("oversight_assignment_id") != OVERSIGHT_ASSIGNMENT_ID
        or record.get("source_id") != OVERSIGHT_SOURCE_ID
        or not isinstance(record.get("status"), str)
        or not _is_integer(record.get("confirmed_at_tick"))
        or record.get("max_age_ticks") != OVERSIGHT_MAX_AGE_TICKS
        or not isinstance(record.get("scope"), str)
    ):
        return NOT_ESTABLISHED
    if record["status"] != "ACTIVE" or not observation_current(
        record, "confirmed_at_tick", tick=tick
    ):
        return STALE
    return CURRENT


def oversight_current(record: dict[str, Any], *, tick: int = T_EVAL) -> bool:
    return oversight_status(record, tick=tick) == CURRENT


def _priority_registry_valid(registry: Any) -> bool:
    return (
        _has_exact_fields(registry, SOURCE_PRIORITY_REGISTRY_FIELDS)
        and registry.get("registry_id") == SOURCE_PRIORITY_REGISTRY_ID
        and registry.get("version") == SOURCE_PRIORITY_REGISTRY_VERSION
        and registry.get("rules") == []
    )


def _risk_metadata_valid(record: Any, scope: str) -> bool:
    if not _has_exact_fields(record, RISK_FIELDS):
        return False
    source_id = record.get("source_id")
    source_contract = (
        RISK_SOURCE_CONTRACTS.get(source_id)
        if isinstance(source_id, str)
        else None
    )
    risk_state = record.get("current_risk_state")
    return (
        source_contract is not None
        and record.get("risk_observation_id") == source_contract[0]
        and record.get("source_authority_rank") == source_contract[1]
        and record.get("max_age_ticks") == RISK_MAX_AGE_TICKS
        and record.get("scope") == scope
        and isinstance(risk_state, str)
        and risk_state in {"ACCEPTABLE", "PROHIBITED"}
        and _is_integer(record.get("observed_at_tick"))
    )


def _priority_choice(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    scope: str,
) -> dict[str, Any] | None:
    # The frozen registry is deliberately empty. Equal-rank disagreement cannot
    # be resolved by caller-supplied priority metadata.
    if not _priority_registry_valid(registry) or not candidates or not scope:
        return None
    return None


def assemble_risk(
    records: list[dict[str, Any]],
    registry: dict[str, Any],
    *,
    tick: int = T_EVAL,
    scope: str = CORE_SCOPE,
) -> dict[str, Any]:
    """Assemble already trusted internal risk records without dynamic defaults."""
    if (
        not isinstance(records, list)
        or not records
        or not _priority_registry_valid(registry)
        or not all(_risk_metadata_valid(item, scope) for item in records)
    ):
        return {"status": "NOT_ESTABLISHED", "value": None, "sources": []}
    if not all(observation_current(item, tick=tick) for item in records):
        return {"status": "STALE_OR_MISSING", "value": None, "sources": []}

    current = records

    highest_rank = max(item["source_authority_rank"] for item in current)
    candidates = [
        item
        for item in current
        if item["source_authority_rank"] == highest_rank
    ]
    values = {item["current_risk_state"] for item in candidates}
    if len(values) == 1:
        return {
            "status": "RESOLVED",
            "value": next(iter(values)),
            "sources": sorted(item["source_id"] for item in candidates),
        }

    selected = _priority_choice(candidates, registry, scope)
    if selected is None:
        return {
            "status": "CONFLICT_UNRESOLVED",
            "value": None,
            "sources": sorted(item["source_id"] for item in candidates),
        }
    return {
        "status": "RESOLVED_BY_FROZEN_PRIORITY",
        "value": selected["current_risk_state"],
        "sources": [selected["source_id"]],
    }
