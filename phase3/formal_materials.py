"""Approved Phase 3 fixture inputs and isolated C working copies.

Approval/provenance records are operator assertions, not cryptographic attestation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .constants import EVIDENCE_VERIFICATION_SHA256
from .evidence import _safe_relative_path, verify_evidence_set
from .evidence_writer import C_WORKING, normal_path, separate, snapshot, write_new
from .identity import canonical_sha256
from .models import EvidenceVerification
from .runner import PreparedBoundary, _paths_overlap, validate_output_root

FIXTURES = {"P3-C-01": "P3-EVID-FIX-ALLOW-001", "P3-C-02": "P3-EVID-FIX-DENY-001"}
ROLES = frozenset({
    "RAW_PROPOSAL", "ADAPTER_RESULT", "CONTEXT_SNAPSHOT", "DECISION_RECEIPT",
    "ENFORCEMENT_RESULT", "STATE_RESULT",
})


def historical_contract(fixture_id: str) -> dict:
    """Use the tracked template and frozen Core Specification fixture table."""
    path = Path(__file__).parent.parent / "phase3_scenarios/fixtures/evidence_fixture_templates.json"
    templates = json.loads(normal_path(path, directory=False).read_bytes())
    if templates.get("template_set_id") != "P3-EVIDENCE-FIXTURE-TEMPLATES-v1":
        raise ValueError("frozen historical template identity mismatch")
    matches = [item for item in templates["templates"] if item["fixture_set_id"] == fixture_id]
    if len(matches) != 1 or fixture_id not in FIXTURES.values():
        raise ValueError("historical fixture mapping unknown")
    # Frozen specification table: ALLOW ACTION control; DENY REENTRY baseline.
    kinds = {FIXTURES["P3-C-01"]: "ACTION", FIXTURES["P3-C-02"]: "REENTRY"}
    return matches[0] | {"request_type": kinds[fixture_id]}


def _historical_semantics(root: Path, fixture_id: str, manifest: dict) -> None:
    contract = historical_contract(fixture_id)
    def unique_pairs(items):
        value = {}
        for key, entry in items:
            if key in value:
                raise ValueError("duplicate historical semantic field")
            value[key] = entry
        return value
    def role_value(role):
        record = next(item for item in manifest["files"] if item["role"] == role)
        raw = normal_path(root / record["relative_path"], directory=False).read_bytes()
        return json.loads(raw, object_pairs_hook=unique_pairs)
    receipt = role_value("DECISION_RECEIPT")
    proposal = role_value("RAW_PROPOSAL")
    if (not isinstance(receipt, dict)
            or receipt.get("decision") != contract["historical_decision"]
            or receipt.get("reason") != contract["historical_reason"]):
        raise ValueError("historical receipt decision/reason differs from frozen fixture")
    if not isinstance(proposal, dict) or proposal.get("request_type") != contract["request_type"]:
        raise ValueError("historical proposal kind differs from frozen fixture")


@dataclass(frozen=True)
class TrustedFileSpec:
    relative_path: str
    role: str


@dataclass(frozen=True)
class TrustedFixture:
    root: Path
    approved_trusted_root: Path
    fixture_id: str
    manifest_bytes: bytes
    manifest_sha256: str
    approval_id: str
    source_classification: str
    protected_roots: tuple[Path, ...]

    @property
    def manifest(self) -> dict:
        return json.loads(self.manifest_bytes)


@dataclass(frozen=True)
class PreparedEvidenceAttempt:
    case_id: str
    working_root: Path
    boundary: PreparedBoundary
    trusted: TrustedFixture
    verification: EvidenceVerification


def validate_manifest(manifest: Mapping[str, object]) -> dict:
    value = json.loads(snapshot(manifest))
    if set(value) != {
        "manifest_id", "manifest_version", "fixture_set_id", "experiment_scope",
        "created_before_formal_run", "files",
    }:
        raise ValueError("manifest fields differ from schema")
    if value["manifest_version"] != "1.0" or value["created_before_formal_run"] is not True:
        raise ValueError("manifest version or preparation state invalid")
    for field in ("manifest_id", "fixture_set_id", "experiment_scope"):
        if not isinstance(value[field], str) or not value[field]:
            raise ValueError("manifest identity missing")
    records = value["files"]
    if not isinstance(records, list) or not records:
        raise ValueError("manifest files missing")
    paths, roles = [], []
    for record in records:
        if set(record) != {"relative_path", "role", "size_bytes", "sha256", "content_identity"}:
            raise ValueError("manifest file fields differ from schema")
        _safe_relative_path(record["relative_path"])
        size = record["size_bytes"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError("invalid size")
        digest = record["sha256"]
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("invalid SHA-256")
        if not isinstance(record["content_identity"], str) or not re.fullmatch(
            "sha256:[0-9a-f]{64}", record["content_identity"]
        ):
            raise ValueError("invalid content identity")
        paths.append(record["relative_path"])
        roles.append(record["role"])
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        raise ValueError("manifest paths unordered or duplicate")
    if len(roles) != len(ROLES) or set(roles) != ROLES:
        raise ValueError("missing or duplicate required role")
    receipt = next(record for record in records if record["role"] == "DECISION_RECEIPT")
    if receipt["relative_path"] != "decision_receipt.json":
        raise ValueError("receipt path differs from frozen core verification binding")
    return value


def _source_boundary(root, approved_trusted_root, fixture_id, protected_roots, approval_id, source_classification):
    if fixture_id not in FIXTURES.values() or not approval_id or source_classification != "PHASE3_GENERATED":
        raise ValueError("approved Phase 3 fixture provenance required")
    normal_path(approved_trusted_root, directory=True)
    if approved_trusted_root.name != "phase3_trusted":
        raise ValueError("trusted root layout mismatch")
    if root != approved_trusted_root / "fixtures" / fixture_id / "evidence":
        raise ValueError("fixture root layout mismatch")
    separate(root, tuple(protected_roots))
    normal_path(root, directory=True)


def build_trusted_manifest(
    *, root: Path, approved_trusted_root: Path, fixture_id: str, manifest_id: str,
    experiment_scope: str, files: Sequence[TrustedFileSpec],
    protected_roots: tuple[Path, ...], approval_id: str, source_classification: str,
) -> dict:
    _source_boundary(root, approved_trusted_root, fixture_id, protected_roots, approval_id, source_classification)
    records = []
    for item in tuple(files):
        relative = _safe_relative_path(item.relative_path)
        path = normal_path(root.joinpath(*relative.parts), directory=False)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        records.append({
            "relative_path": item.relative_path, "role": item.role, "size_bytes": len(data),
            "sha256": digest, "content_identity": "sha256:" + digest,
        })
    return validate_manifest({
        "manifest_id": manifest_id, "manifest_version": "1.0",
        "fixture_set_id": fixture_id, "experiment_scope": experiment_scope,
        "created_before_formal_run": True,
        "files": sorted(records, key=lambda item: item["relative_path"]),
    })


def prepare_trusted_fixture_input(
    *, root: Path, approved_trusted_root: Path, fixture_id: str,
    manifest: Mapping[str, object], expected_manifest_sha256: str,
    protected_roots: tuple[Path, ...], approval_id: str, source_classification: str,
) -> TrustedFixture:
    _source_boundary(root, approved_trusted_root, fixture_id, protected_roots, approval_id, source_classification)
    value = validate_manifest(manifest)
    if value["fixture_set_id"] != fixture_id:
        raise ValueError("fixture / manifest pairing mismatch")
    encoded = snapshot(value)
    if hashlib.sha256(encoded).hexdigest() != expected_manifest_sha256:
        raise ValueError("manifest identity mismatch")
    result = verify_evidence_set(root, value)
    if result.full_set_integrity != "ESTABLISHED":
        raise ValueError("trusted baseline pre-verification failed")
    _historical_semantics(root, fixture_id, value)
    return TrustedFixture(root, approved_trusted_root, fixture_id, encoded,
                          expected_manifest_sha256, approval_id, source_classification,
                          tuple(protected_roots))


def validate_trusted_fixture(trusted: TrustedFixture) -> None:
    if not isinstance(trusted, TrustedFixture):
        raise ValueError("prepared trusted fixture required")
    prepare_trusted_fixture_input(
        root=trusted.root, approved_trusted_root=trusted.approved_trusted_root,
        fixture_id=trusted.fixture_id, manifest=trusted.manifest,
        expected_manifest_sha256=trusted.manifest_sha256,
        protected_roots=trusted.protected_roots, approval_id=trusted.approval_id,
        source_classification=trusted.source_classification,
    )


def _alter_receipt(raw: bytes) -> bytes:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate receipt key")
            result[key] = value
        return result
    text = raw.decode("utf-8", errors="strict")
    parsed = json.loads(text, object_pairs_hook=pairs)
    if not isinstance(parsed, dict) or parsed.get("decision") != "DENY":
        raise ValueError("C-02 requires original DENY receipt")
    decoder = json.JSONDecoder()
    position = len(text) - len(text.lstrip())
    position += 1
    while True:
        while text[position].isspace() or text[position] == ",":
            position += 1
        key, position = decoder.raw_decode(text, position)
        while text[position].isspace():
            position += 1
        if text[position] != ":":
            raise ValueError("invalid receipt")
        position += 1
        while text[position].isspace():
            position += 1
        start = position
        _, position = decoder.raw_decode(text, position)
        if key == "decision":
            return (text[:start] + '"ALLOW"' + text[position:]).encode("utf-8")


def prepare_c_evidence_attempt(
    *, case_id: str, trusted: TrustedFixture, boundary: PreparedBoundary,
) -> PreparedEvidenceAttempt:
    if case_id not in FIXTURES or trusted.fixture_id != FIXTURES[case_id]:
        raise ValueError("C case / fixture pairing mismatch")
    if boundary.scenario_id != case_id:
        raise ValueError("attempt identity mismatch")
    validate_output_root(
        boundary.output_root, boundary.authorization, session_id=boundary.session_id,
        batch_id=boundary.batch_id, scenario_id=case_id,
        attempt_number=boundary.attempt_number, prepared_boundary=boundary,
    )
    validate_trusted_fixture(trusted)
    working = boundary.output_root / C_WORKING
    separate(working, boundary.authorization.protected_roots + (trusted.approved_trusted_root,))
    normal_path(working)
    if working.exists():
        raise ValueError("C working subtree collision")
    manifest = trusted.manifest
    baseline = {
        item["relative_path"]: (trusted.root / item["relative_path"]).read_bytes()
        for item in manifest["files"]
    }
    try:
        working.mkdir()
        for relative, raw in baseline.items():
            target = working / relative
            normal_path(target.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            write_new(target, raw)
        receipt = working / "decision_receipt.json"
        normal_path(receipt, directory=False)
        if case_id == "P3-C-01":
            receipt.unlink()
        else:
            altered = _alter_receipt(receipt.read_bytes())
            # This is the one authorized working-copy mutation, not a repair.
            with receipt.open("wb") as stream:
                stream.write(altered)
        verification = verify_evidence_set(working, manifest)
        if canonical_sha256(verification.to_dict(), exclude_volatile=False) != EVIDENCE_VERIFICATION_SHA256[case_id]:
            raise ValueError("unexpected real verification result")
        return PreparedEvidenceAttempt(case_id, working, boundary, trusted, verification)
    finally:
        validate_trusted_fixture(trusted)
        if any((trusted.root / path).read_bytes() != raw for path, raw in baseline.items()):
            raise ValueError("trusted baseline changed during preparation")
