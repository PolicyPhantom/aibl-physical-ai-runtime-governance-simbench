"""Readiness evaluation of explicitly sourced observations; no execution authorization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .constants import SCENARIO_ORDER
from .evidence_writer import normal_path, separate, snapshot, write_new
from .formal_materials import FIXTURES, TrustedFixture, validate_trusted_fixture
from .models import WorkspaceAuthorization
from .runner import _safe_layout_segment, validate_output_root

PRE_FORMAL = "PRE-FORMAL / NOT YET EXECUTED"
FROZEN_CONFIG = {
    "T_EVAL": 1000, "T_COMMAND": 1000, "T_VERIFY": 1001, "policy_version": "1.0",
    "priority_registry_version": "1.0", "risk_max_age": 5, "oversight_max_age": 5,
    "remediation_max_age": 5, "physical_max_age": 1,
}


@dataclass(frozen=True)
class Expectation:
    approved_bytes: bytes
    basis: str


@dataclass(frozen=True)
class Observation:
    observed_bytes: bytes | None
    state: str
    source_kind: str
    reference: str
    actor: str


@dataclass(frozen=True)
class ObservationCheck:
    expectation: Expectation
    observation: Observation


def expectation(*, approved: Mapping, basis: str) -> Expectation:
    return Expectation(snapshot(approved), basis)


def observation(*, observed: Mapping | None, state: str, source_kind: str,
                reference: str, actor: str) -> Observation:
    """Snapshot caller records, not cryptographic or non-forgeable attestation."""
    return Observation(None if observed is None else snapshot(observed), state,
                       source_kind, reference, actor)


def _known_text(value) -> bool:
    return isinstance(value, str) and value.strip().upper() not in {
        "", "UNKNOWN", "UNOBSERVED", "UNAVAILABLE", "MISSING", "NONE", "NULL",
        "N/A", "NOT_OBSERVED", "NOT_MEASURED", "NOT_RUN",
    }


def _observed(item: Observation, kind: str) -> bool:
    return (isinstance(item, Observation) and item.state == "OBSERVED"
            and item.source_kind == kind and _known_text(item.reference)
            and _known_text(item.actor) and item.observed_bytes is not None)


def _source(item: Observation) -> str:
    if not isinstance(item, Observation):
        return "UNOBSERVED"
    return f"{item.source_kind}:{item.actor}:{item.reference}"


@dataclass(frozen=True)
class OutputSlot:
    session_id: str
    batch_id: str
    case_id: str
    attempt: int
    output_root: Path


@dataclass(frozen=True)
class ExternalAnchorRecord:
    reference: str
    manifest_sha256: str
    recorded_at: str
    operator: str
    status: str


@dataclass(frozen=True)
class MaterialAnchor:
    trusted: TrustedFixture
    manifest_path: Path
    external: ExternalAnchorRecord


@dataclass(frozen=True)
class LocalAnchorRecord:
    path: Path
    manifest_sha256: str
    created: bool


@dataclass(frozen=True)
class FormalPreflightInput:
    plan_identity: str
    git: ObservationCheck
    runtime: ObservationCheck
    logical_config: ObservationCheck
    authorization: WorkspaceAuthorization
    slots: tuple[OutputSlot, ...]
    materials: tuple[MaterialAnchor, ...]
    workspace_observation: Observation


@dataclass(frozen=True)
class FormalPreflightResult:
    ready_for_human_go: bool
    blocking_reasons: tuple[str, ...]
    plan_identity: str
    candidate_head: str
    manifest_hashes: tuple[tuple[str, str], ...]
    observation_sources: tuple[str, ...]


def anchor_location(approved_trusted_root: Path, manifest_id: str) -> Path:
    normal_path(approved_trusted_root, directory=True)
    if approved_trusted_root.name != "phase3_trusted":
        raise ValueError("trusted root layout mismatch")
    _safe_layout_segment(manifest_id, "manifest_id")
    return approved_trusted_root / "anchors" / f"{manifest_id}.sha256"


def create_local_manifest_anchor(
    *, manifest_path: Path, approved_trusted_root: Path, manifest_id: str,
    fixture_id: str, protected_roots: tuple[Path, ...], approval_id: str,
) -> LocalAnchorRecord:
    if not approval_id or fixture_id not in FIXTURES.values():
        raise ValueError("explicit material-preparation approval required")
    expected = approved_trusted_root / "fixtures" / fixture_id / "trusted_manifest.json"
    if manifest_path != expected:
        raise ValueError("manifest path differs from approved layout")
    separate(manifest_path, tuple(protected_roots))
    raw = normal_path(manifest_path, directory=False).read_bytes()
    manifest = json.loads(raw)
    if manifest["manifest_id"] != manifest_id or manifest["fixture_set_id"] != fixture_id:
        raise ValueError("manifest identity mismatch")
    digest = hashlib.sha256(raw).hexdigest()
    path = anchor_location(approved_trusted_root, manifest_id)
    separate(path, tuple(protected_roots))
    normal_path(path.parent)
    if path.exists():
        existing = normal_path(path, directory=False).read_bytes()
        if existing not in (digest.encode("ascii"), (digest + "\n").encode("ascii")):
            raise ValueError("existing anchor differs")
        return LocalAnchorRecord(path, digest, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_new(path, (digest + "\n").encode("ascii"))
    return LocalAnchorRecord(path, digest, True)


def collect_formal_preflight(
    *, plan_identity: str, git: ObservationCheck, runtime: ObservationCheck,
    logical_config: ObservationCheck, authorization: WorkspaceAuthorization,
    slots, materials, workspace_observation: Observation,
) -> FormalPreflightInput:
    """Snapshot supplied facts; this function does not measure Git or runtime."""
    return FormalPreflightInput(plan_identity, git, runtime, logical_config,
                                authorization, tuple(slots), tuple(materials),
                                workspace_observation)


def _matches(item: ObservationCheck, label: str, reasons: list[str]) -> dict:
    try:
        expected = json.loads(item.expectation.approved_bytes)
        if not isinstance(expected, dict):
            raise ValueError("expected observation must be an object")
        kind = {"GIT": "COMMAND_OUTPUT", "RUNTIME": "RUNTIME_INSPECTION", "CONFIG": "CONFIG_INSPECTION"}[label]
        if (not _known_text(item.expectation.basis)
                or not _observed(item.observation, kind)
                or json.loads(item.observation.observed_bytes) != expected):
            reasons.append(f"{label}_UNKNOWN_OR_MISMATCH")
        return expected
    except (TypeError, ValueError, AttributeError):
        reasons.append(f"{label}_INVALID")
        return {}


def validate_material_anchor(material: MaterialAnchor) -> tuple[str, str]:
    """Recheck the approved bytes and both anchor records without writing."""
    trusted = material.trusted
    validate_trusted_fixture(trusted)
    manifest_path = trusted.approved_trusted_root / "fixtures" / trusted.fixture_id / "trusted_manifest.json"
    if material.manifest_path != manifest_path:
        raise ValueError("manifest location mismatch")
    raw = normal_path(manifest_path, directory=False).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != trusted.manifest_sha256 or raw != trusted.manifest_bytes:
        raise ValueError("raw manifest differs from approved snapshot")
    identity = trusted.manifest["manifest_id"]
    anchor = anchor_location(trusted.approved_trusted_root, identity)
    if normal_path(anchor, directory=False).read_bytes() not in (
        digest.encode("ascii"), (digest + "\n").encode("ascii")
    ):
        raise ValueError("local anchor mismatch")
    external = material.external
    if (
        external.manifest_sha256 != digest or external.status != PRE_FORMAL
        or not external.reference or not external.recorded_at or not external.operator
    ):
        raise ValueError("external pre-Formal anchor mismatch or unknown")
    return identity, digest


def evaluate_formal_preflight(value: FormalPreflightInput) -> FormalPreflightResult:
    reasons: list[str] = []
    expected_git = _matches(value.git, "GIT", reasons)
    if (
        set(expected_git) != {"head", "branch", "tracked_count", "remote_count", "tracked_changes", "staged_changes"}
        or not isinstance(expected_git.get("head"), str) or len(expected_git.get("head", "")) != 40
        or expected_git.get("branch") != "main" or expected_git.get("remote_count") != 0
        or expected_git.get("tracked_changes") != [] or expected_git.get("staged_changes") != []
        or not isinstance(expected_git.get("tracked_count"), int) or expected_git["tracked_count"] <= 0
    ):
        reasons.append("GIT_EXPECTATION_INVALID")
    runtime = _matches(value.runtime, "RUNTIME", reasons)
    if set(runtime) != {"python_executable", "python_version", "execution_actor", "execution_boundary"} or not all(
        _known_text(item) for item in runtime.values()
    ):
        reasons.append("RUNTIME_EXPECTATION_INVALID")
    config = _matches(value.logical_config, "CONFIG", reasons)
    if config != FROZEN_CONFIG:
        reasons.append("FROZEN_CONFIG_MISMATCH")
    workspace = value.workspace_observation
    workspace_basis = {
        "root": str(value.authorization.authorized_workspace_root),
        "authorization_id": value.authorization.authorization_id,
        "protected_roots": [str(path) for path in value.authorization.protected_roots],
    }
    if (not _observed(workspace, "FILESYSTEM_INSPECTION")
            or workspace.observed_bytes != snapshot(workspace_basis) or not value.plan_identity):
        reasons.append("OBSERVATION_BINDING_MISSING")
    expected_order = [(case, attempt) for case in SCENARIO_ORDER for attempt in range(1, 6)]
    if [(item.case_id, item.attempt) for item in value.slots] != expected_order:
        reasons.append("OUTPUT_PLAN_ORDER")
    if len({item.batch_id for item in value.slots}) != 12:
        reasons.append("CASE_BATCH_COUNT")
    for slot in value.slots:
        try:
            validate_output_root(
                slot.output_root, value.authorization, session_id=slot.session_id,
                batch_id=slot.batch_id, scenario_id=slot.case_id, attempt_number=slot.attempt,
            )
        except (ValueError, OSError) as exc:
            reasons.append(f"OUTPUT_BOUNDARY:{slot.case_id}:{slot.attempt}:{exc}")
            break
    hashes = []
    if len(value.materials) != 2 or {item.trusted.fixture_id for item in value.materials} != set(FIXTURES.values()):
        reasons.append("REQUIRED_C_MATERIALS_MISSING_OR_DUPLICATE")
    for material in value.materials:
        try:
            hashes.append(validate_material_anchor(material))
        except (ValueError, OSError, KeyError) as exc:
            reasons.append(f"MATERIAL_ANCHOR:{exc}")
    return FormalPreflightResult(
        not reasons, tuple(reasons), value.plan_identity, expected_git.get("head", ""),
        tuple(sorted(hashes)),
        (_source(value.git.observation), _source(value.runtime.observation),
         _source(value.logical_config.observation), _source(workspace)),
    )
