"""Strict Phase 3 proposal boundary over exact raw bytes."""

from __future__ import annotations

import json
from typing import Any

from .constants import (
    INVALID,
    PROPOSAL_FIELDS,
    PROPOSAL_VOCABULARY,
    REQUEST_TYPES,
    VALID,
)
from .identity import raw_sha256
from .models import AdapterResult


class DuplicateKeyError(ValueError):
    def __init__(self, key: str, occurrences: int) -> None:
        super().__init__(key)
        self.key = key
        self.occurrences = occurrences


def _pairs_to_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    counts: dict[str, int] = {}
    for key, value in pairs:
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 1:
            raise DuplicateKeyError(key, counts[key])
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON constant: {value}")


def _invalid(
    digest: str,
    reason: str,
    *,
    duplicate_key: str | None = None,
    duplicate_occurrences: int = 0,
    source_classification: str | None = None,
) -> AdapterResult:
    return AdapterResult(
        status=INVALID,
        reason=reason,
        raw_sha256=digest,
        normalized_proposal=None,
        duplicate_key=duplicate_key,
        duplicate_occurrences=duplicate_occurrences,
        source_classification=source_classification,
        phase3_classification=reason,
    )


def adapt_proposal(raw: bytes) -> AdapterResult:
    """Decode and validate one complete object; never repair or retry."""
    digest = raw_sha256(raw)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _invalid(digest, "LLM_OUTPUT_NOT_JSON")

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_pairs_to_object,
            parse_constant=_reject_constant,
        )
    except DuplicateKeyError as exc:
        return _invalid(
            digest,
            "LLM_OUTPUT_DUPLICATE_KEY",
            duplicate_key=exc.key,
            duplicate_occurrences=exc.occurrences,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return _invalid(digest, "LLM_OUTPUT_NOT_JSON")

    if not isinstance(parsed, dict):
        return _invalid(digest, "LLM_OUTPUT_TOP_LEVEL_NOT_OBJECT")
    fields = frozenset(parsed)
    if fields - PROPOSAL_FIELDS:
        return _invalid(digest, "LLM_OUTPUT_UNSUPPORTED_FIELD")
    if PROPOSAL_FIELDS - fields:
        return _invalid(digest, "LLM_OUTPUT_MISSING_REQUIRED_FIELD")
    if any(not isinstance(parsed[field], str) for field in PROPOSAL_FIELDS):
        return _invalid(digest, "LLM_OUTPUT_INVALID_FIELD_TYPE")
    if parsed["request_type"] not in REQUEST_TYPES:
        return _invalid(digest, "LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE")
    for field, vocabulary in PROPOSAL_VOCABULARY.items():
        if parsed[field] not in vocabulary:
            return _invalid(
                digest,
                "LLM_OUTPUT_UNSUPPORTED_VALUE",
                source_classification="LLM_OUTPUT_UNRECOGNIZED_VALUE",
            )

    normalized = {field: parsed[field] for field in sorted(PROPOSAL_FIELDS)}
    return AdapterResult(
        status=VALID,
        reason=None,
        raw_sha256=digest,
        normalized_proposal=normalized,
    )