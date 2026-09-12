"""In-process single-scenario evaluator with a closed output boundary."""

from __future__ import annotations

import os
import stat
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any
from weakref import WeakKeyDictionary

from .adapter import adapt_proposal
from .constants import (
    ALLOW,
    BASELINE_FIXTURE_SHA256,
    CORE_SCENARIO_INITIAL_STATE,
    CORE_SCENARIO_PRIMARY_DELTA,
    CORE_SCENARIO_PROPOSAL_FIXTURE,
    CORE_SCENARIO_SHA256,
    EVIDENCE_VERIFICATION_SHA256,
    INVALID,
    NOT_PERFORMED,
    PROPOSAL_RAW_SHA256,
    PROTECTED_OUTPUT_PARTS,
    RUNNING,
    SCENARIO_ORDER,
    SUSPENDED,
    T_EVAL,
    T_VERIFY,
    VOLATILE_FIELDS,
)
from .governance import evaluate_action
from .identity import canonical_sha256, raw_sha256
from .models import WorkspaceAuthorization
from .physical import execute_allowed_move
from .reentry import apply_reentry, evaluate_reentry, with_verification


class CoreBoundaryError(ValueError):
    code = "CORE_SCENARIO_DIVERGENCE"


class WorkspaceBoundaryError(ValueError):
    code = "OPERATOR_WORKSPACE_BOUNDARY_REJECTED"


@dataclass(frozen=True, eq=False)
class PreparedBoundary:
    """Process-local, single-evaluation permit; not proof of human approval."""

    output_root: Path
    authorization: WorkspaceAuthorization
    session_id: str
    batch_id: str
    scenario_id: str
    experiment_id: str
    attempt_number: int


_prepared_boundaries: WeakKeyDictionary = WeakKeyDictionary()
# Reservations survive token consumption for this process only.
_prepared_attempts: dict[tuple, dict] = {}
_prepared_paths: dict[tuple[str, ...], tuple] = {}


def _attempt_identity(boundary: PreparedBoundary) -> tuple:
    authorization = boundary.authorization
    canonical = lambda path: _windows_parts(_absolute_lexical(path, "prepared path"))
    return (
        authorization.authorization_id, canonical(authorization.authorized_workspace_root),
        tuple(sorted(canonical(path) for path in authorization.protected_roots)),
        canonical(boundary.output_root), boundary.session_id.casefold(),
        boundary.batch_id.casefold(), boundary.experiment_id.casefold(),
        boundary.scenario_id.casefold(), boundary.attempt_number,
    )


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    if not stat.S_ISDIR(metadata.st_mode) or not metadata.st_ino:
        _workspace_reject("stable directory identity unavailable")
    return metadata.st_dev, metadata.st_ino


def _prepared_state(boundary: PreparedBoundary) -> dict:
    key = _prepared_boundaries.get(boundary)
    state = _prepared_attempts.get(key)
    if (state is None or state["token"] is not boundary
            or key != _attempt_identity(boundary)):
        _workspace_reject("prepared boundary not issued or identity changed")
    return state


def bind_prepared_attempt(boundary: PreparedBoundary, created_root: Path) -> None:
    """Bind the created directory's device/file identity; no filesystem writes."""
    state = _prepared_state(boundary)
    root = _absolute_lexical(created_root, "created attempt")
    if state["status"] != "ISSUED" or _windows_parts(root) != _windows_parts(boundary.output_root):
        _workspace_reject("prepared binding path or lifecycle mismatch")
    metadata = _inspect_existing_components(root)
    if metadata is None:
        _workspace_reject("created attempt unavailable for binding")
    state["directory_identity"] = _directory_identity(metadata)
    state["status"] = "BOUND"
    try:
        validate_output_root(
            root, boundary.authorization, session_id=boundary.session_id,
            batch_id=boundary.batch_id, scenario_id=boundary.scenario_id,
            attempt_number=boundary.attempt_number, prepared_boundary=boundary,
        )
    except Exception:
        state["status"] = "REJECTED"
        raise


def prepare_attempt_boundary(
    output_root: Path,
    authorization: WorkspaceAuthorization,
    *,
    session_id: str,
    batch_id: str,
    scenario_id: str,
    attempt_number: int,
) -> PreparedBoundary:
    root = validate_output_root(
        output_root, authorization, session_id=session_id, batch_id=batch_id,
        scenario_id=scenario_id, attempt_number=attempt_number,
    )
    boundary = PreparedBoundary(
        root, authorization, session_id, batch_id, scenario_id,
        scenario_id, attempt_number,
    )
    key = _attempt_identity(boundary)
    path_key = _windows_parts(root)
    if key in _prepared_attempts or path_key in _prepared_paths:
        _workspace_reject("attempt identity already reserved")
    _prepared_boundaries[boundary] = key
    _prepared_attempts[key] = {"token": boundary, "status": "ISSUED", "directory_identity": None}
    _prepared_paths[path_key] = key
    return boundary


def _core_reject(detail: str) -> None:
    raise CoreBoundaryError(detail)


def _workspace_reject(detail: str) -> None:
    raise WorkspaceBoundaryError(detail)


def _absolute_lexical(path: Path, label: str) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        _workspace_reject(f"{label} must be an absolute Path")
    return Path(os.path.abspath(os.fspath(path)))


def _lstat_no_follow(path: Path) -> os.stat_result:
    return os.lstat(path)


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return stat.S_ISLNK(stat_result.st_mode) or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _inspect_existing_components(path: Path) -> os.stat_result | None:
    """Inspect existing components in order without following a reparse point."""
    parts = path.parts
    for index in range(1, len(parts) + 1):
        component = Path(*parts[:index])
        try:
            component_stat = _lstat_no_follow(component)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise WorkspaceBoundaryError(
                f"cannot inspect workspace component without following: {component}"
            ) from exc
        if _is_reparse(component_stat):
            _workspace_reject(f"reparse component rejected: {component}")
        if index < len(parts) and not stat.S_ISDIR(component_stat.st_mode):
            _workspace_reject(f"non-directory workspace ancestor rejected: {component}")
    return component_stat


def _windows_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in PureWindowsPath(str(path)).parts)


def _paths_overlap(left: Path, right: Path) -> bool:
    left_parts = _windows_parts(left)
    right_parts = _windows_parts(right)
    return (
        left_parts[: len(right_parts)] == right_parts
        or right_parts[: len(left_parts)] == left_parts
    )


def _safe_layout_segment(value: Any, label: str) -> str:
    allowed = frozenset(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
    )
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or PureWindowsPath(value).parts != (value,)
        or any(character not in allowed for character in value)
        or value[-1] in {".", " "}
        or value.split(".", 1)[0].casefold() in reserved
        or value.casefold() in PROTECTED_OUTPUT_PARTS
    ):
        _workspace_reject(f"invalid {label}")
    return value


def validate_output_root(
    output_root: Path,
    authorization: WorkspaceAuthorization,
    *,
    session_id: str,
    batch_id: str,
    scenario_id: str,
    attempt_number: int,
    prepared_boundary: PreparedBoundary | None = None,
) -> Path:
    """Enforce an operator-supplied workspace boundary without writing it.

    This function validates approval data; it does not establish that a human
    issued the approval represented by that data.
    """
    if not isinstance(authorization, WorkspaceAuthorization):
        _workspace_reject("workspace authorization is required")
    if not isinstance(authorization.authorization_id, str) or not authorization.authorization_id:
        _workspace_reject("authorization_id is not established")
    if not authorization.protected_roots:
        _workspace_reject("protected_roots are not established")
    if (
        not isinstance(attempt_number, int)
        or isinstance(attempt_number, bool)
        or not 1 <= attempt_number <= 5
    ):
        _workspace_reject("attempt_number must be within 1..5")

    session = _safe_layout_segment(session_id, "session_id")
    batch = _safe_layout_segment(batch_id, "batch_id")
    scenario = _safe_layout_segment(scenario_id, "scenario_id")
    if scenario not in SCENARIO_ORDER:
        _workspace_reject("scenario_id is outside the frozen registry")

    root_input = authorization.authorized_workspace_root
    output_input = output_root
    protected_inputs = authorization.protected_roots
    for path, label in (
        (root_input, "authorized_workspace_root"),
        (output_input, "output_root"),
        *((item, "protected_root") for item in protected_inputs),
    ):
        if not isinstance(path, Path) or not path.is_absolute():
            _workspace_reject(f"{label} must be an absolute Path")

    # abspath is lexical only: no component is resolved or read here.
    root = _absolute_lexical(root_input, "authorized_workspace_root")
    output = _absolute_lexical(output_input, "output_root")
    protected = tuple(
        _absolute_lexical(item, "protected_root") for item in protected_inputs
    )
    root_stat = _inspect_existing_components(root)
    if root_stat is None:
        _workspace_reject("authorized workspace root is unavailable")
    if not stat.S_ISDIR(root_stat.st_mode):
        _workspace_reject("authorized workspace root is not a directory")

    expected = root / "phase3_evidence" / session / batch / scenario / (
        f"attempt-{attempt_number:02d}"
    )
    if _windows_parts(output) != _windows_parts(expected):
        _workspace_reject("output_root does not match the fixed evidence layout")
    if any(_paths_overlap(output, item) for item in protected):
        _workspace_reject("output_root overlaps a protected root")
    output_stat = _inspect_existing_components(output)
    for path in protected:
        _inspect_existing_components(path)
    if prepared_boundary is not None:
        boundary = prepared_boundary
        if (
            not isinstance(boundary, PreparedBoundary)
            or boundary.authorization != authorization
            or boundary.output_root != output
            or boundary.session_id != session_id
            or boundary.batch_id != batch_id
            or boundary.scenario_id != scenario_id
            or boundary.experiment_id != scenario_id
            or boundary.attempt_number != attempt_number
        ):
            _workspace_reject("prepared boundary identity or lifecycle mismatch")
        if output_stat is None or not stat.S_ISDIR(output_stat.st_mode):
            _workspace_reject("prepared attempt is not an existing normal directory")
        state = _prepared_state(boundary)
        if state["status"] != "BOUND" or state["directory_identity"] != _directory_identity(output_stat):
            _workspace_reject("prepared directory identity or lifecycle mismatch")
    elif output_stat is not None:
        _workspace_reject("attempt leaf already exists")
    return output


def _finish(result: dict[str, Any]) -> dict[str, Any]:
    identity_input = {
        key: value
        for key, value in result.items()
        if key != "decision_identity" and key not in VOLATILE_FIELDS
    }
    result["decision_identity"] = canonical_sha256(
        identity_input, exclude_volatile=False
    )
    return result


def _perturbation_identity(scenario_id: str) -> str:
    return canonical_sha256(
        {
            "scenario_id": scenario_id,
            "primary_delta": CORE_SCENARIO_PRIMARY_DELTA[scenario_id],
        },
        exclude_volatile=False,
    )


def _canonical_identity(value: Any, label: str) -> str:
    try:
        return canonical_sha256(value, exclude_volatile=False)
    except (TypeError, ValueError) as exc:
        raise CoreBoundaryError(f"{label} is not canonicalizable") from exc


def _assert_nfc_structured(value: Any, label: str) -> None:
    """Reject non-NFC structured input without normalizing or rebuilding it."""
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            _core_reject(f"{label} contains a non-NFC string value")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and unicodedata.normalize("NFC", key) != key:
                _core_reject(f"{label} contains a non-NFC object key")
            _assert_nfc_structured(item, label)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_nfc_structured(item, label)


def _validate_core_inputs(
    scenario: Any,
    proposals: Any,
    common_context: Any,
    physical_safe: Any,
    reentry_current: Any,
    evidence_verification: Any,
) -> str:
    for label, value in (
        ("scenario", scenario),
        ("proposals", proposals),
        ("common_context", common_context),
        ("physical_safe", physical_safe),
        ("reentry_current", reentry_current),
        ("evidence_verification", evidence_verification),
    ):
        _assert_nfc_structured(value, label)

    if not isinstance(scenario, dict):
        _core_reject("scenario must be an object")
    scenario_id = scenario.get("scenario_id")
    if not isinstance(scenario_id, str) or scenario_id not in CORE_SCENARIO_SHA256:
        _core_reject("scenario is outside the frozen twelve-case registry")
    if _canonical_identity(scenario, "scenario") != CORE_SCENARIO_SHA256[scenario_id]:
        _core_reject("scenario contract differs from the frozen case")

    if not isinstance(proposals, dict) or set(proposals) != set(PROPOSAL_RAW_SHA256):
        _core_reject("proposal fixture set differs from the frozen four-file set")
    for fixture_name, expected_identity in PROPOSAL_RAW_SHA256.items():
        raw = proposals.get(fixture_name)
        if not isinstance(raw, bytes) or raw_sha256(raw) != expected_identity:
            _core_reject(f"proposal fixture differs: {fixture_name}")

    baseline_values = {
        "common_context": common_context,
        "physical_safe": physical_safe,
        "reentry_current": reentry_current,
    }
    for fixture_name, value in baseline_values.items():
        if not isinstance(value, dict) or _canonical_identity(
            value, fixture_name
        ) != BASELINE_FIXTURE_SHA256[fixture_name]:
            _core_reject(f"baseline fixture differs: {fixture_name}")

    expected_verification = EVIDENCE_VERIFICATION_SHA256.get(scenario_id)
    if expected_verification is None:
        if evidence_verification is not None:
            _core_reject("verification input is not part of this frozen case")
    elif not isinstance(evidence_verification, dict) or _canonical_identity(
        evidence_verification, "evidence_verification"
    ) != expected_verification:
        _core_reject("evidence verification differs from the frozen case input")
    return scenario_id


def _decision_basis(
    scenario_id: str,
    fixture_identities: dict[str, str],
    evaluation_stage: str,
    evaluated_input: dict[str, Any],
) -> dict[str, Any]:
    snapshot = deepcopy(evaluated_input)
    return {
        "scenario_contract_identity": CORE_SCENARIO_SHA256[scenario_id],
        "fixture_identities": deepcopy(fixture_identities),
        "evaluation_stage": evaluation_stage,
        "evaluated_input": snapshot,
        "evaluated_input_identity": canonical_sha256(
            snapshot, exclude_volatile=False
        ),
    }


def _invalid_result(
    scenario_id: str,
    perturbation_identity: str,
    adapted: dict[str, Any],
    initial_state: str,
    raw: bytes,
) -> dict[str, Any]:
    return _finish(
        {
            "scenario_id": scenario_id,
            "raw_sha256": adapted["raw_sha256"],
            "perturbation_identity": perturbation_identity,
            "adapter": {
                "status": adapted["status"],
                "reason": adapted["reason"],
                "duplicate_key": adapted["duplicate_key"],
                "duplicate_occurrences": adapted["duplicate_occurrences"],
                "source_classification": adapted["source_classification"],
                "phase3_classification": adapted["phase3_classification"],
            },
            "normalized_proposal": None,
            "governance": NOT_PERFORMED,
            "verification": None,
            "enforcement": NOT_PERFORMED,
            "command_status": None,
            "physical_result": None,
            "physical_action_count": 0,
            "receipt_present": False,
            "initial_state": initial_state,
            "final_state": initial_state,
            "followup": None,
            "decision_basis": _decision_basis(
                scenario_id,
                {"proposal_raw_sha256": adapted["raw_sha256"]},
                "ADAPTER",
                {"raw_proposal_hex": raw.hex()},
            ),
        }
    )


def run_scenario(
    scenario: dict[str, Any],
    *,
    proposals: dict[str, bytes],
    common_context: dict[str, Any],
    physical_safe: dict[str, Any],
    reentry_current: dict[str, Any],
    output_root: Path,
    workspace_authorization: WorkspaceAuthorization,
    session_id: str,
    batch_id: str,
    attempt_number: int,
    evidence_verification: dict[str, Any] | None = None,
    prepared_boundary: PreparedBoundary | None = None,
) -> dict[str, Any]:
    """Evaluate exactly one supplied scenario once; never write or retry."""
    try:
        scenario = deepcopy(scenario)
        proposals = deepcopy(proposals)
        common_context = deepcopy(common_context)
        physical_safe = deepcopy(physical_safe)
        reentry_current = deepcopy(reentry_current)
        evidence_verification = deepcopy(evidence_verification)
    except Exception as exc:
        raise CoreBoundaryError("core inputs could not be snapshotted") from exc
    scenario_id = _validate_core_inputs(
        scenario,
        proposals,
        common_context,
        physical_safe,
        reentry_current,
        evidence_verification,
    )
    validate_output_root(
        output_root,
        workspace_authorization,
        session_id=session_id,
        batch_id=batch_id,
        scenario_id=scenario_id,
        attempt_number=attempt_number,
        prepared_boundary=prepared_boundary,
    )
    if prepared_boundary is not None:
        _prepared_state(prepared_boundary)["status"] = "CONSUMED"
    perturbation_identity = _perturbation_identity(scenario_id)

    raw = proposals[CORE_SCENARIO_PROPOSAL_FIXTURE[scenario_id]]
    adapted_model = adapt_proposal(raw)
    adapted = adapted_model.to_dict()
    initial_state = CORE_SCENARIO_INITIAL_STATE[scenario_id]
    if adapted_model.status == INVALID:
        return _invalid_result(
            scenario_id, perturbation_identity, adapted, initial_state, raw
        )

    proposal = adapted_model.normalized_proposal
    assert proposal is not None

    if scenario_id in {
        "P3-CTRL-02",
        "P3-C-01",
        "P3-C-02",
        "P3-D-01",
        "P3-D-02",
    }:
        bundle = deepcopy(reentry_current)
        bundle["normalized_request"] = deepcopy(proposal)
        bundle["pre_decision_operational_state"] = initial_state
        if scenario_id == "P3-D-01":
            bundle["remediation"]["observed_at_tick"] = 994
        if scenario_id == "P3-D-02":
            bundle["risk_records"][0]["current_risk_state"] = "PROHIBITED"
        if scenario_id in {"P3-C-01", "P3-C-02"}:
            assert evidence_verification is not None
            bundle = with_verification(bundle, evidence_verification)

        reentry_evaluated_input = {
            "bundle": deepcopy(bundle),
            "tick": T_EVAL,
        }
        decision = evaluate_reentry(bundle)
        transition = apply_reentry(bundle, decision)
        fixture_identities = {
            "proposal_raw_sha256": adapted["raw_sha256"],
            "reentry_current": BASELINE_FIXTURE_SHA256["reentry_current"],
        }
        if evidence_verification is not None:
            fixture_identities["evidence_verification"] = EVIDENCE_VERIFICATION_SHA256[
                scenario_id
            ]
        result = {
            "scenario_id": scenario_id,
            "raw_sha256": adapted["raw_sha256"],
            "perturbation_identity": perturbation_identity,
            "adapter": {"status": adapted["status"], "reason": adapted["reason"]},
            "normalized_proposal": proposal,
            "governance": decision.to_dict(),
            "verification": deepcopy(evidence_verification),
            "enforcement": decision.enforcement,
            "command_status": None,
            "physical_result": None,
            "physical_action_count": 0,
            "receipt_present": True,
            "initial_state": initial_state,
            "final_state": transition["final_state"],
            "followup": None,
            "decision_basis": _decision_basis(
                scenario_id,
                fixture_identities,
                "REENTRY_GOVERNANCE",
                reentry_evaluated_input,
            ),
        }
        return _finish(result)

    context = deepcopy(common_context)
    context["operational_state"] = initial_state
    physical = deepcopy(physical_safe)
    if scenario_id == "P3-B-01":
        context["authority"]["valid_until_tick"] = 1000
    elif scenario_id == "P3-B-02":
        context["risk_records"] = [
            {
                "risk_observation_id": "RISK-P3-ALPHA",
                "current_risk_state": "ACCEPTABLE",
                "observed_at_tick": 1000,
                "max_age_ticks": 5,
                "source_id": "RISK-SOURCE-ALPHA",
                "source_authority_rank": 10,
                "scope": "MOVE / ZONE_B",
            },
            {
                "risk_observation_id": "RISK-P3-BETA",
                "current_risk_state": "PROHIBITED",
                "observed_at_tick": 1000,
                "max_age_ticks": 5,
                "source_id": "RISK-SOURCE-BETA",
                "source_authority_rank": 10,
                "scope": "MOVE / ZONE_B",
            },
        ]
    elif scenario_id == "P3-E-01":
        physical.pop("target_zone_occupancy")

    action_evaluated_input = {
        "proposal": deepcopy(proposal),
        "context": deepcopy(context),
        "physical_observations": deepcopy(physical),
        "tick": T_EVAL,
        "followup_evaluation": None,
    }
    decision = evaluate_action(proposal, context, physical)
    physical_result: dict[str, Any] | None = None
    followup: dict[str, Any] | None = None
    final_state = initial_state
    command_status: str | None = None
    physical_action_count = 0
    enforcement = NOT_PERFORMED

    if decision.decision == ALLOW:
        actual_state = "ZONE_A" if scenario_id == "P3-E-02" else "ZONE_B"
        outcome = execute_allowed_move(
            decision,
            actual_state=actual_state,
            initial_state=initial_state,
            verification_tick=T_VERIFY,
        )
        physical_result = outcome.to_dict()
        final_state = outcome.final_state
        command_status = outcome.command_status
        physical_action_count = outcome.physical_action_count
        enforcement = "PERFORMED"
        if scenario_id == "P3-E-02":
            followup_context = deepcopy(common_context)
            followup_context["operational_state"] = SUSPENDED
            followup_physical = deepcopy(physical_safe)
            action_evaluated_input["followup_evaluation"] = {
                "proposal": deepcopy(proposal),
                "context": deepcopy(followup_context),
                "physical_observations": deepcopy(followup_physical),
                "tick": T_EVAL,
            }
            followup_decision = evaluate_action(
                proposal, followup_context, followup_physical
            )
            followup = {
                "decision": followup_decision.to_dict(),
                "enforcement": NOT_PERFORMED,
                "physical_action_count": 0,
                "final_state": SUSPENDED,
            }

    result = {
        "scenario_id": scenario_id,
        "raw_sha256": adapted["raw_sha256"],
        "perturbation_identity": perturbation_identity,
        "adapter": {"status": adapted["status"], "reason": adapted["reason"]},
        "normalized_proposal": proposal,
        "governance": decision.to_dict(),
        "verification": None,
        "enforcement": enforcement,
        "command_status": command_status,
        "physical_result": physical_result,
        "physical_action_count": physical_action_count,
        "receipt_present": True,
        "initial_state": initial_state,
        "final_state": final_state,
        "followup": followup,
        "decision_basis": _decision_basis(
            scenario_id,
            {
                "proposal_raw_sha256": adapted["raw_sha256"],
                "common_context": BASELINE_FIXTURE_SHA256["common_context"],
                "physical_safe": BASELINE_FIXTURE_SHA256["physical_safe"],
            },
            "ACTION_GOVERNANCE",
            action_evaluated_input,
        ),
    }
    return _finish(result)
