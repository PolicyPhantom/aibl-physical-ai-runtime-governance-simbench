from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from phase3 import formal_materials as fm
from phase3 import evidence_writer as ew
from phase3.constants import EVIDENCE_VERIFICATION_SHA256
from phase3.identity import canonical_sha256
from phase3.runner import WorkspaceBoundaryError
from tests.phase3.test_evidence_writer import ROOT, start, evaluate, file_bytes, inputs


def trusted_fixture(tmp_path, case_id="P3-C-01"):
    fixture_id = fm.FIXTURES[case_id]
    trusted_root = tmp_path / "phase3_trusted"
    root = trusted_root / "fixtures" / fixture_id / "evidence"
    root.mkdir(parents=True)
    templates = json.loads((ROOT / "phase3_scenarios/fixtures/evidence_fixture_templates.json").read_bytes())
    contract = next(item for item in templates["templates"] if item["fixture_set_id"] == fixture_id)
    decision = contract["historical_decision"]
    reason = contract["historical_reason"]
    proposal_name = "action_valid" if case_id == "P3-C-01" else "reentry_valid"
    raw = {
        "raw_proposal.json": inputs()["proposals"][proposal_name],
        "adapter.json": b'{"status":"VALID"}\n',
        "context.json": b'{"evaluation_tick":1000}\n',
        "decision_receipt.json": ('{ "note": "DENY elsewhere", "decision" : "' + decision + '", "reason":"' + reason + '" }\n').encode(),
        "enforcement.json": b'{"status":"NOT_PERFORMED"}\n',
        "state.json": b'{"state":"SUSPENDED"}\n',
    }
    roles = ("RAW_PROPOSAL", "ADAPTER_RESULT", "CONTEXT_SNAPSHOT", "DECISION_RECEIPT",
             "ENFORCEMENT_RESULT", "STATE_RESULT")
    files = []
    for (name, data), role in zip(raw.items(), roles):
        (root / name).write_bytes(data)
        files.append(fm.TrustedFileSpec(name, role))
    arguments = dict(
        root=root, approved_trusted_root=trusted_root, fixture_id=fixture_id,
        protected_roots=(ROOT,), approval_id="UNIT-FIXTURE-APPROVAL",
        source_classification="PHASE3_GENERATED",
    )
    manifest = fm.build_trusted_manifest(
        **arguments, manifest_id=f"unit-{case_id}", experiment_scope=case_id, files=files,
    )
    prepared = fm.prepare_trusted_fixture_input(
        **arguments, manifest=manifest,
        expected_manifest_sha256=hashlib.sha256(ew.snapshot(manifest)).hexdigest(),
    )
    return prepared, arguments, files


def test_manifest_schema_fields_determinism_and_snapshot(tmp_path):
    trusted, args, files = trusted_fixture(tmp_path)
    first = fm.build_trusted_manifest(**args, manifest_id="unit-P3-C-01", experiment_scope="P3-C-01", files=files)
    second = fm.build_trusted_manifest(**args, manifest_id="unit-P3-C-01", experiment_scope="P3-C-01", files=list(reversed(files)))
    schema = json.loads((ROOT / "phase3_schemas/trusted_manifest_v1.schema.json").read_text())
    assert set(first) == set(schema["required"])
    assert ew.snapshot(first) == ew.snapshot(second) == trusted.manifest_bytes
    first["files"][0]["sha256"] = "0" * 64
    assert trusted.manifest["files"][0]["sha256"] != "0" * 64


@pytest.mark.parametrize("case_id", ["P3-C-01", "P3-C-02"])
def test_real_c_preparation_and_core_connection(tmp_path, case_id):
    trusted, _, _ = trusted_fixture(tmp_path, case_id)
    before = file_bytes(trusted.root)
    handle = start(tmp_path, case_id)
    prepared = fm.prepare_c_evidence_attempt(case_id=case_id, trusted=trusted, boundary=handle.boundary)
    verification = prepared.verification.to_dict()
    assert canonical_sha256(verification, exclude_volatile=False) == EVIDENCE_VERIFICATION_SHA256[case_id]
    assert file_bytes(trusted.root) == before
    working = file_bytes(prepared.working_root)
    if case_id == "P3-C-01":
        assert set(before) - set(working) == {"decision_receipt.json"}
        assert verification["completeness"] == "INCOMPLETE"
    else:
        assert set(working) == set(before)
        expected = before["decision_receipt.json"].replace(b'"decision" : "DENY"', b'"decision" : "ALLOW"')
        assert working["decision_receipt.json"] == expected
        assert verification["present_file_integrity"] == "INTEGRITY_FAILURE"
    for path in set(before) & set(working) - {"decision_receipt.json"}:
        assert before[path] == working[path]
    result = evaluate(handle, verification)
    assert result["verification"] == verification
    assert result["governance"]["decision"] == "HOLD"
    summary = ew.finalize_attempt_tree(handle, core_result=result, reconciliation={"accepted": True})
    assert summary.collection_complete
    assert file_bytes(prepared.working_root) == working


@pytest.mark.parametrize("fault", ["extra", "changed", "missing"])
def test_baseline_preverification_failure(tmp_path, fault):
    trusted, _, _ = trusted_fixture(tmp_path)
    if fault == "extra":
        (trusted.root / "extra.json").write_bytes(b"{}")
    elif fault == "changed":
        (trusted.root / "context.json").write_bytes(b"bad")
    else:
        (trusted.root / "context.json").unlink()
    with pytest.raises(ValueError, match="pre-verification"):
        fm.validate_trusted_fixture(trusted)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "path", "pair", "schema"])
def test_invalid_manifest_contract(tmp_path, fault):
    trusted, args, files = trusted_fixture(tmp_path)
    manifest = trusted.manifest
    if fault == "missing":
        manifest["files"].pop()
    elif fault == "duplicate":
        manifest["files"][0]["role"] = manifest["files"][1]["role"]
    elif fault == "path":
        manifest["files"][0]["relative_path"] = "../escape"
    elif fault == "pair":
        manifest["fixture_set_id"] = fm.FIXTURES["P3-C-02"]
    else:
        manifest["paper_field"] = True
    with pytest.raises(ValueError):
        fm.prepare_trusted_fixture_input(**args, manifest=manifest,
            expected_manifest_sha256=hashlib.sha256(ew.snapshot(manifest)).hexdigest())


def test_protected_phase2_source_and_non_c_rejected(tmp_path):
    trusted, args, files = trusted_fixture(tmp_path)
    for changed in (dict(source_classification="PHASE2_FORMAL"), dict(protected_roots=(trusted.root,))):
        with pytest.raises(ValueError):
            fm.build_trusted_manifest(**(args | changed), manifest_id="m", experiment_scope="P3-C", files=files)
    handle = start(tmp_path)
    with pytest.raises(ValueError):
        fm.prepare_c_evidence_attempt(case_id="P3-CTRL-01", trusted=trusted, boundary=handle.boundary)
    handle = start(tmp_path, "P3-C-02")
    with pytest.raises(ValueError):
        fm.prepare_c_evidence_attempt(case_id="P3-C-02", trusted=trusted, boundary=handle.boundary)


def test_destination_collision_and_reparse(tmp_path, monkeypatch):
    trusted, _, _ = trusted_fixture(tmp_path)
    handle = start(tmp_path, "P3-C-01")
    fm.prepare_c_evidence_attempt(case_id="P3-C-01", trusted=trusted, boundary=handle.boundary)
    with pytest.raises(ValueError, match="collision"):
        fm.prepare_c_evidence_attempt(case_id="P3-C-01", trusted=trusted, boundary=handle.boundary)
    original = fm.normal_path
    def reject(path, **kwargs):
        if path == handle.attempt_root / ew.C_WORKING:
            raise WorkspaceBoundaryError("reparse destination")
        return original(path, **kwargs)
    monkeypatch.setattr(fm, "normal_path", reject)
    with pytest.raises(WorkspaceBoundaryError):
        fm.prepare_c_evidence_attempt(case_id="P3-C-01", trusted=trusted, boundary=handle.boundary)


def test_partial_copy_failure_retains_baseline_and_partial_files(tmp_path, monkeypatch):
    trusted, _, _ = trusted_fixture(tmp_path)
    before = file_bytes(trusted.root)
    handle = start(tmp_path, "P3-C-01")
    original = fm.write_new
    def fail(path, data):
        if path.name == "context.json":
            raise OSError("copy failure")
        original(path, data)
    monkeypatch.setattr(fm, "write_new", fail)
    with pytest.raises(OSError, match="copy failure"):
        fm.prepare_c_evidence_attempt(case_id="P3-C-01", trusted=trusted, boundary=handle.boundary)
    assert file_bytes(trusted.root) == before
    assert (handle.attempt_root / ew.C_WORKING / "adapter.json").exists()


def test_unexpected_real_verification_is_not_replaced(tmp_path, monkeypatch):
    trusted, _, _ = trusted_fixture(tmp_path)
    handle = start(tmp_path, "P3-C-01")
    original = fm.verify_evidence_set
    def changed(root, manifest):
        if root != trusted.root:
            (root / "unexpected").write_bytes(b"x")
        return original(root, manifest)
    monkeypatch.setattr(fm, "verify_evidence_set", changed)
    with pytest.raises(ValueError, match="unexpected real"):
        fm.prepare_c_evidence_attempt(case_id="P3-C-01", trusted=trusted, boundary=handle.boundary)


@pytest.mark.parametrize("case_id", ["P3-C-01", "P3-C-02"])
@pytest.mark.parametrize("fault", ["decision", "reason", "proposal"])
def test_ir05_correct_hash_wrong_historical_semantics_rejected(tmp_path, case_id, fault):
    trusted, args, files = trusted_fixture(tmp_path, case_id)
    name = "raw_proposal.json" if fault == "proposal" else "decision_receipt.json"
    path = trusted.root / name
    value = json.loads(path.read_bytes())
    if fault == "proposal":
        value["request_type"] = "REENTRY" if case_id == "P3-C-01" else "ACTION"
    elif fault == "decision":
        value["decision"] = "DENY" if case_id == "P3-C-01" else "ALLOW"
    else:
        value["reason"] = "ALL_CURRENT_REENTRY_CONDITIONS_SATISFIED"
    path.write_bytes(ew.snapshot(value))
    manifest = fm.build_trusted_manifest(**args, manifest_id=f"unit-{case_id}", experiment_scope=case_id, files=files)
    assert fm.verify_evidence_set(trusted.root, manifest).full_set_integrity == "ESTABLISHED"
    with pytest.raises(ValueError, match="historical"):
        fm.prepare_trusted_fixture_input(**args, manifest=manifest,
            expected_manifest_sha256=hashlib.sha256(ew.snapshot(manifest)).hexdigest())
