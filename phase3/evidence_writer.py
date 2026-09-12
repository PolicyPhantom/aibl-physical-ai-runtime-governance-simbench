"""Attempt artifact persistence only; no governance or verification evaluation."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from weakref import WeakKeyDictionary

from .identity import canonical_bytes
from .models import WorkspaceAuthorization
from .runner import (
    PreparedBoundary, _inspect_existing_components, _paths_overlap,
    _safe_layout_segment, prepare_attempt_boundary, bind_prepared_attempt,
)

LAYOUT = (
    "00_spec", "01_input", "02_adapter", "03_context", "04_governance",
    "05_enforcement", "06_physical", "07_verification", "08_reconstruction",
    "09_findings",
)
C_WORKING = Path("01_input") / "c_working"


class WriterFailure(ValueError):
    def __init__(self, message: str, handle: AttemptEvidenceHandle | None = None):
        super().__init__(message)
        self.handle = handle


def snapshot(value: Any) -> bytes:
    """Private canonical snapshot; callers receive decoded copies, never aliases."""
    return canonical_bytes(value, exclude_volatile=False)


def normal_path(path: Path, *, directory: bool | None = None) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute non-traversing path required")
    metadata = _inspect_existing_components(path)
    if directory is True and (metadata is None or not stat.S_ISDIR(metadata.st_mode)):
        raise ValueError("normal existing directory required")
    if directory is False and (metadata is None or not stat.S_ISREG(metadata.st_mode)):
        raise ValueError("normal existing file required")
    return path


def separate(path: Path, protected_roots: tuple[Path, ...]) -> None:
    normal_path(path)
    if not protected_roots:
        raise ValueError("explicit protection boundary required")
    for protected in protected_roots:
        if _paths_overlap(path, protected):
            raise ValueError("protected overlap")
        normal_path(protected)


def write_new(path: Path, data: bytes) -> None:
    normal_path(path.parent, directory=True)
    normal_path(path)
    if _inspect_existing_components(path) is not None:
        raise ValueError("artifact collision")
    with path.open("xb") as stream:
        stream.write(data)


@dataclass(frozen=True, eq=False)
class AttemptEvidenceHandle:
    boundary: PreparedBoundary

    @property
    def attempt_root(self) -> Path:
        return self.boundary.output_root


@dataclass(frozen=True)
class EvidenceArtifact:
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class AttemptEvidenceSummary:
    attempt_root: Path
    artifacts: tuple[EvidenceArtifact, ...]
    collection_complete: bool


_handles: WeakKeyDictionary = WeakKeyDictionary()


def _state(handle: AttemptEvidenceHandle, *, writable: bool = True) -> dict:
    if not isinstance(handle, AttemptEvidenceHandle) or handle not in _handles:
        raise WriterFailure("unknown attempt handle")
    state = _handles[handle]
    if writable and state["status"] != "OPEN":
        raise WriterFailure("attempt is closed", handle)
    normal_path(handle.attempt_root, directory=True)
    separate(handle.attempt_root, handle.boundary.authorization.protected_roots)
    return state


def _put(handle: AttemptEvidenceHandle, relative: str, data: bytes) -> EvidenceArtifact:
    state = _state(handle)
    parts = relative.split("/")
    if (
        len(parts) != 2 or parts[0] not in LAYOUT
        or any(part in {"", ".", ".."} or "\\" in part or ":" in part for part in parts)
    ):
        raise WriterFailure("artifact is outside Writer ownership", handle)
    _safe_layout_segment(parts[1], "artifact name")
    path = handle.attempt_root.joinpath(*parts)
    try:
        write_new(path, data)
        artifact = EvidenceArtifact(relative, len(data), hashlib.sha256(data).hexdigest())
        state["artifacts"].append(artifact)
        return artifact
    except Exception as exc:
        state["status"] = "FAILED"
        raise WriterFailure(str(exc), handle) from exc


def initialize_attempt_tree(
    *, output_root: Path, authorization: WorkspaceAuthorization,
    session_id: str, batch_id: str, case_id: str, attempt: int,
    spec_snapshot: Mapping[str, object], proposal_raw_bytes: bytes,
    references: Mapping[str, object],
) -> AttemptEvidenceHandle:
    if not isinstance(proposal_raw_bytes, bytes):
        raise WriterFailure("raw input must be bytes")
    spec_bytes, reference_bytes = snapshot(spec_snapshot), snapshot(references)
    boundary = prepare_attempt_boundary(
        output_root, authorization, session_id=session_id, batch_id=batch_id,
        scenario_id=case_id, attempt_number=attempt,
    )
    handle = AttemptEvidenceHandle(boundary)
    try:
        output_root.mkdir(parents=True, exist_ok=False)
        _handles[handle] = {"status": "OPEN", "artifacts": [], "event": 0}
        bind_prepared_attempt(boundary, output_root)
        for name in LAYOUT:
            path = output_root / name
            normal_path(path)
            path.mkdir()
        _put(handle, "00_spec/spec.json", spec_bytes)
        _put(handle, "00_spec/references.json", reference_bytes)
        _put(handle, "01_input/raw_proposal.bin", proposal_raw_bytes)
        _put(handle, "01_input/raw_identity.json", snapshot({
            "raw_sha256": hashlib.sha256(proposal_raw_bytes).hexdigest(),
        }))
        return handle
    except Exception as exc:
        if handle in _handles:
            _handles[handle]["status"] = "FAILED"
        raise WriterFailure(str(exc), handle) from exc


def append_attempt_event(handle: AttemptEvidenceHandle, *, event: Mapping[str, object]) -> EvidenceArtifact:
    state = _state(handle)
    state["event"] += 1
    return _put(handle, f"06_physical/event-{state['event']:04d}.json", snapshot(event))


def record_attempt_failure(handle: AttemptEvidenceHandle, *, reason: str) -> EvidenceArtifact:
    state = _state(handle, writable=False)
    if state["status"] == "FINALIZED" or state.get("failure_recorded"):
        raise WriterFailure("failure already recorded or attempt finalized", handle)
    # A distinct failure artifact is not a retry of the failed artifact write.
    state["status"] = "OPEN"
    try:
        artifact = _put(handle, "09_findings/failure.json", snapshot({
            "finding": reason, "collection_complete": False,
        }))
        state["failure_recorded"] = True
        return artifact
    finally:
        state["status"] = "FAILED"


def persist_core_result(
    handle: AttemptEvidenceHandle, *, core_result: Mapping[str, object],
) -> EvidenceArtifact:
    """Save the complete return value before any replay/reconciliation can fail."""
    state = _state(handle)
    if "core_result" in state:
        raise WriterFailure("core result already persisted", handle)
    result = json.loads(snapshot(core_result))
    if result.get("scenario_id") != handle.boundary.scenario_id:
        raise WriterFailure("result belongs to another case", handle)
    artifact = _put(handle, "08_reconstruction/core_result.json", snapshot(result))
    state["core_result"] = snapshot(result)
    _put(handle, "08_reconstruction/core_result_artifact.json", snapshot({
        "relative_path": artifact.relative_path, "size_bytes": artifact.size,
        "sha256": artifact.sha256,
    }))
    return artifact


def finalize_attempt_tree(
    handle: AttemptEvidenceHandle, *, reconciliation: Mapping[str, object],
    core_result: Mapping[str, object] | None = None,
) -> AttemptEvidenceSummary:
    state = _state(handle)
    # Preserve the original direct Writer API; Session uses the explicit stage.
    if core_result is not None:
        persist_core_result(handle, core_result=core_result)
    if "core_result" not in state:
        raise WriterFailure("core result must be persisted before finalization", handle)
    result = json.loads(state["core_result"])
    _put(handle, "02_adapter/adapter.json", snapshot({
        "adapter": result["adapter"], "normalized_proposal": result["normalized_proposal"],
    }))
    _put(handle, "03_context/decision_basis.json", snapshot(result["decision_basis"]))
    _put(handle, "04_governance/stage.json", snapshot({"governance": result["governance"]}))
    if result["receipt_present"]:
        if not isinstance(result["governance"], dict):
            raise WriterFailure("receipt has no evaluated decision", handle)
        _put(handle, "04_governance/decision_receipt.json", snapshot(result["governance"]))
    elif result["governance"] != "NOT_PERFORMED" or result["normalized_proposal"] is not None:
        raise WriterFailure("invalid absent-receipt representation", handle)
    _put(handle, "05_enforcement/enforcement.json", snapshot({
        "enforcement": result["enforcement"], "command_status": result["command_status"],
        "physical_action_count": result["physical_action_count"],
    }))
    _put(handle, "06_physical/outcome.json", snapshot({
        key: result[key] for key in ("physical_result", "initial_state", "final_state", "followup")
    }))
    if result["physical_result"] is not None:
        append_attempt_event(handle, event=result["physical_result"])
    _put(handle, "07_verification/verification.json", snapshot({
        "verification": result["verification"],
        "applicable": result["verification"] is not None,
    }))
    _put(handle, "08_reconstruction/identity.json", snapshot({
        "canonical_identity": result["decision_identity"],
        "raw_sha256": result["raw_sha256"],
    }))
    _put(handle, "08_reconstruction/reconciliation.json", snapshot(reconciliation))
    finding = "NO_FINDING" if reconciliation.get("accepted") is True else "FROZEN_RESULT_DIVERGENCE"
    _put(handle, "09_findings/finding.json", snapshot({"finding": finding}))
    # The inventory describes prior artifacts. Its own identity is in the return record.
    _put(handle, "08_reconstruction/inventory.json", snapshot([
        {"relative_path": item.relative_path, "size_bytes": item.size, "sha256": item.sha256}
        for item in state["artifacts"]
    ]))
    state["status"] = "FINALIZED"
    return AttemptEvidenceSummary(handle.attempt_root, tuple(state["artifacts"]), True)
