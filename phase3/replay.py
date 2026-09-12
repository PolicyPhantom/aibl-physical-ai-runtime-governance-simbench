"""Comparison of already produced Phase 3 results; no execution loop."""

from __future__ import annotations

from typing import Any

from .constants import SCENARIO_RESULT_MUST_MATCH_FIELDS, VOLATILE_FIELDS
from .identity import canonical_sha256


MUST_MATCH_FIELDS = SCENARIO_RESULT_MUST_MATCH_FIELDS


def _calculated_decision_identity(result: dict[str, Any]) -> str:
    identity_input = {
        key: value
        for key, value in result.items()
        if key != "decision_identity" and key not in VOLATILE_FIELDS
    }
    return canonical_sha256(identity_input, exclude_volatile=False)


def _evaluated_input_identity_valid(result: dict[str, Any]) -> bool:
    basis = result.get("decision_basis")
    if not isinstance(basis, dict) or "evaluated_input" not in basis:
        return False
    stored_identity = basis.get("evaluated_input_identity")
    if not isinstance(stored_identity, str):
        return False
    try:
        calculated = canonical_sha256(
            basis["evaluated_input"], exclude_volatile=False
        )
    except (TypeError, ValueError):
        return False
    return stored_identity == calculated


def compare_results(
    reference: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    differences = []
    for field in MUST_MATCH_FIELDS:
        if (
            field not in reference
            or field not in candidate
            or reference[field] != candidate[field]
        ):
            differences.append(field)

    reference_identity = _calculated_decision_identity(reference)
    candidate_identity = _calculated_decision_identity(candidate)
    reference_identity_valid = (
        reference.get("decision_identity") == reference_identity
    )
    candidate_identity_valid = (
        candidate.get("decision_identity") == candidate_identity
    )
    if (
        not reference_identity_valid or not candidate_identity_valid
    ) and "decision_identity" not in differences:
        differences.append("decision_identity")

    reference_basis_valid = _evaluated_input_identity_valid(reference)
    candidate_basis_valid = _evaluated_input_identity_valid(candidate)
    if (
        not reference_basis_valid or not candidate_basis_valid
    ) and "decision_basis" not in differences:
        differences.append("decision_basis")

    return {
        "must_match": not differences,
        "differing_fields": differences,
        "reference_decision_identity": reference_identity,
        "candidate_decision_identity": candidate_identity,
        "reference_identity_valid": reference_identity_valid,
        "candidate_identity_valid": candidate_identity_valid,
        "reference_evaluated_input_identity_valid": reference_basis_valid,
        "candidate_evaluated_input_identity_valid": candidate_basis_valid,
    }
