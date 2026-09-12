"""Read-only evidence verification against a caller-supplied Trusted Manifest.

Component checks reject static reparse boundaries; they do not eliminate TOCTOU.
The caller remains responsible for establishing the Trusted Manifest's authority.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from .models import EvidenceVerification


def _safe_relative_path(value: str) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("manifest path must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("manifest path must be a safe relative POSIX path")
    return path


def _lstat_no_follow(path: Path) -> os.stat_result:
    return os.lstat(path)


def _reject_reparse(path: Path, metadata: os.stat_result) -> None:
    if stat.S_ISLNK(metadata.st_mode) or (
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise ValueError(f"reparse component rejected: {path}")


def _inspect_root(evidence_root: Path) -> Path:
    if not isinstance(evidence_root, Path) or ".." in evidence_root.parts:
        raise ValueError("evidence root must be a Path without parent traversal")
    # Lexical conversion only; inspect every ancestor before its descendants.
    root = Path(os.path.abspath(os.fspath(evidence_root)))
    for index in range(1, len(root.parts) + 1):
        component = Path(*root.parts[:index])
        metadata = _lstat_no_follow(component)
        _reject_reparse(component, metadata)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"evidence component is not a directory: {component}")
    return root


def _children(directory: Path) -> list[Path]:
    return sorted(directory.iterdir(), key=lambda path: path.name)


def _inventory(root: Path) -> dict[str, tuple[Path, os.stat_result]]:
    files: dict[str, tuple[Path, os.stat_result]] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        directories = []
        for path in _children(directory):
            metadata = _lstat_no_follow(path)
            _reject_reparse(path, metadata)
            relative = path.relative_to(root).as_posix()
            _safe_relative_path(relative)
            if stat.S_ISDIR(metadata.st_mode):
                directories.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                files[relative] = (path, metadata)
            else:
                raise ValueError(f"special evidence entry rejected: {path}")
        pending.extend(reversed(directories))
    return files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_evidence_set(
    evidence_root: Path,
    trusted_manifest: dict[str, Any],
) -> EvidenceVerification:
    """Verify without filling gaps, rewriting files, or changing the manifest."""
    expected: dict[str, dict[str, Any]] = {}
    for record in trusted_manifest["files"]:
        relative = _safe_relative_path(record["relative_path"]).as_posix()
        if relative in expected:
            raise ValueError("duplicate manifest relative_path")
        expected[relative] = record

    root = _inspect_root(evidence_root)
    inventory = _inventory(root)
    actual = set(inventory)
    missing = tuple(sorted(set(expected) - actual))
    unexpected = tuple(sorted(actual - set(expected)))
    mismatched: list[str] = []
    for relative in sorted(set(expected) & actual):
        path, metadata = inventory[relative]
        record = expected[relative]
        if (
            metadata.st_size != int(record["size_bytes"])
            or _sha256(path) != record["sha256"]
        ):
            mismatched.append(relative)

    completeness = "COMPLETE" if not missing and not unexpected else "INCOMPLETE"
    completeness_reason: str | None = None
    if any(
        expected[path].get("role") == "DECISION_RECEIPT"
        for path in missing
    ):
        completeness_reason = "DECISION_RECEIPT_MISSING"
    elif missing:
        completeness_reason = "EXPECTED_EVIDENCE_MISSING"
    elif unexpected:
        completeness_reason = "UNEXPECTED_EVIDENCE_PRESENT"

    integrity = (
        "INTEGRITY_VERIFIED" if not mismatched else "INTEGRITY_FAILURE"
    )
    integrity_reason: str | None = None
    if any(
        expected[path].get("role") == "DECISION_RECEIPT"
        for path in mismatched
    ):
        integrity_reason = "DECISION_RECEIPT_HASH_MISMATCH"
    elif mismatched:
        integrity_reason = "EVIDENCE_HASH_MISMATCH"

    established = (
        "ESTABLISHED"
        if completeness == "COMPLETE"
        and integrity == "INTEGRITY_VERIFIED"
        else "NOT_ESTABLISHED"
    )
    return EvidenceVerification(
        completeness=completeness,
        completeness_reason=completeness_reason,
        present_file_integrity=integrity,
        integrity_reason=integrity_reason,
        full_set_integrity=established,
        missing_paths=missing,
        mismatched_paths=tuple(mismatched),
        unexpected_paths=unexpected,
    )
