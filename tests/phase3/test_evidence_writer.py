from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from phase3 import evidence_writer as ew
from phase3.constants import SCENARIO_ORDER
from phase3.models import WorkspaceAuthorization
from phase3.runner import (
    WorkspaceBoundaryError, prepare_attempt_boundary, run_scenario, validate_output_root,
    bind_prepared_attempt,
)

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    directory = ROOT / "phase3_scenarios"
    load = lambda name: json.loads((directory / "fixtures" / name).read_text(encoding="utf-8"))
    return {
        "cases": json.loads((directory / "core_scenarios_v1.json").read_text(encoding="utf-8"))["cases"],
        "proposals": {
            name: (directory / "fixtures" / "proposals" / f"{name}.json").read_bytes()
            for name in ("action_valid", "reentry_valid", "duplicate_key", "unsupported_value")
        },
        "common_context": load("common_context.json"),
        "physical_safe": load("physical_safe.json"),
        "reentry_current": load("reentry_current.json"),
    }


def authorization(tmp_path):
    return WorkspaceAuthorization(tmp_path, "UNIT-AUTH", (ROOT, tmp_path / "phase3_trusted"))


def attempt_path(tmp_path, case_id, attempt=1):
    return tmp_path / "phase3_evidence" / "unit-session" / f"batch-{case_id}" / case_id / f"attempt-{attempt:02d}"


def start(tmp_path, case_id="P3-CTRL-01", attempt=1):
    data = inputs()
    case = next(item for item in data["cases"] if item["scenario_id"] == case_id)
    return ew.initialize_attempt_tree(
        output_root=attempt_path(tmp_path, case_id, attempt),
        authorization=authorization(tmp_path), session_id="unit-session",
        batch_id=f"batch-{case_id}", case_id=case_id, attempt=attempt,
        spec_snapshot=case, proposal_raw_bytes=data["proposals"][case["proposal_fixture"]],
        references={"spec": "unit-reference", "fixture": case["proposal_fixture"]},
    )


def evaluate(handle, verification=None):
    data = inputs()
    boundary = handle.boundary
    case = next(item for item in data.pop("cases") if item["scenario_id"] == boundary.scenario_id)
    return run_scenario(
        case, **data, output_root=handle.attempt_root,
        workspace_authorization=boundary.authorization, session_id=boundary.session_id,
        batch_id=boundary.batch_id, attempt_number=boundary.attempt_number,
        evidence_verification=verification, prepared_boundary=boundary,
    )


def file_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_prepared_default_rejection_and_single_consumption(tmp_path):
    handle = start(tmp_path)
    b = handle.boundary
    with pytest.raises(WorkspaceBoundaryError):
        validate_output_root(b.output_root, b.authorization, session_id=b.session_id,
                             batch_id=b.batch_id, scenario_id=b.scenario_id, attempt_number=1)
    result = evaluate(handle)
    assert result["governance"]["decision"] == "ALLOW"
    with pytest.raises(WorkspaceBoundaryError):
        evaluate(handle)


def test_copied_or_wrong_prepared_identity_rejected(tmp_path):
    handle = start(tmp_path)
    b = handle.boundary
    for token, batch in ((replace(b), b.batch_id), (b, "another-batch")):
        with pytest.raises(WorkspaceBoundaryError):
            validate_output_root(b.output_root, b.authorization, session_id=b.session_id,
                                 batch_id=batch, scenario_id=b.scenario_id,
                                 attempt_number=1, prepared_boundary=token)


def test_new_leaf_and_exact_raw_and_no_reuse(tmp_path):
    handle = start(tmp_path)
    raw = inputs()["proposals"]["action_valid"]
    assert (handle.attempt_root / "01_input/raw_proposal.bin").read_bytes() == raw
    assert {p.name for p in handle.attempt_root.iterdir()} == set(ew.LAYOUT)
    with pytest.raises(WorkspaceBoundaryError):
        start(tmp_path)


@pytest.mark.parametrize("case_id", ["P3-A-01", "P3-A-02"])
def test_invalid_has_no_fabricated_receipt(tmp_path, case_id):
    handle = start(tmp_path, case_id)
    result = evaluate(handle)
    summary = ew.finalize_attempt_tree(handle, core_result=result, reconciliation={"accepted": True})
    assert summary.collection_complete
    assert not (handle.attempt_root / "04_governance/decision_receipt.json").exists()
    saved = json.loads((handle.attempt_root / "08_reconstruction/core_result.json").read_bytes())
    assert saved == result
    assert saved["governance"] == "NOT_PERFORMED"


def test_mismatch_preserves_decision_and_separate_identities(tmp_path):
    handle = start(tmp_path, "P3-E-02")
    first = ew.append_attempt_event(handle, event={"observation": "before"})
    path = handle.attempt_root / first.relative_path
    before = path.read_bytes()
    result = evaluate(handle)
    summary = ew.finalize_attempt_tree(handle, core_result=result, reconciliation={"accepted": True})
    assert summary.collection_complete
    assert path.read_bytes() == before
    assert hashlib.sha256(before).hexdigest() == first.sha256
    receipt = json.loads((handle.attempt_root / "04_governance/decision_receipt.json").read_bytes())
    assert receipt["decision"] == "ALLOW"
    saved = json.loads((handle.attempt_root / "06_physical/outcome.json").read_bytes())
    assert saved["final_state"] == "SUSPENDED"
    assert saved["followup"]["decision"]["decision"] == "DENY"
    identity = json.loads((handle.attempt_root / "08_reconstruction/identity.json").read_bytes())
    assert identity["canonical_identity"] != identity["raw_sha256"]
    with pytest.raises(ew.WriterFailure):
        ew.append_attempt_event(handle, event={})
    with pytest.raises(ew.WriterFailure):
        ew.finalize_attempt_tree(handle, core_result=result, reconciliation={})


def test_attempt_isolation_and_failure_preserves_initial(tmp_path):
    first, second = start(tmp_path), start(tmp_path, attempt=2)
    before = file_bytes(first.attempt_root)
    ew.record_attempt_failure(second, reason="evaluation failed")
    assert file_bytes(first.attempt_root) == before
    assert (second.attempt_root / "01_input/raw_proposal.bin").exists()
    assert (second.attempt_root / "00_spec/spec.json").exists()
    with pytest.raises(ew.WriterFailure):
        ew.append_attempt_event(second, event={})


@pytest.mark.parametrize("relative", [
    "01_input/c_working/decision_receipt.json", "../phase3_trusted/manifest.json",
    "phase3_trusted/manifest.json", "outputs/file.json",
])
def test_ownership_rejected(tmp_path, relative):
    handle = start(tmp_path)
    with pytest.raises(ew.WriterFailure):
        ew._put(handle, relative, b"x")


def test_protected_and_reparse_output_rejected_before_creation(tmp_path, monkeypatch):
    handle = start(tmp_path)
    b = handle.boundary
    with pytest.raises(WorkspaceBoundaryError):
        prepare_attempt_boundary(attempt_path(tmp_path, b.scenario_id, 2),
            WorkspaceAuthorization(tmp_path, "bad", (tmp_path,)),
            session_id=b.session_id, batch_id=b.batch_id, scenario_id=b.scenario_id, attempt_number=2)
    original = ew._inspect_existing_components
    def reject(path):
        if path == handle.attempt_root:
            raise WorkspaceBoundaryError("reparse component rejected")
        return original(path)
    monkeypatch.setattr(ew, "_inspect_existing_components", reject)
    with pytest.raises(WorkspaceBoundaryError):
        ew.append_attempt_event(handle, event={})


def test_partial_writer_and_failure_record_failures_surface(tmp_path, monkeypatch):
    handle = start(tmp_path)
    result = evaluate(handle)
    original = ew.write_new
    def fail(path, data):
        if path.name == "adapter.json":
            raise OSError("simulated write failure")
        original(path, data)
    monkeypatch.setattr(ew, "write_new", fail)
    with pytest.raises(ew.WriterFailure, match="simulated"):
        ew.finalize_attempt_tree(handle, core_result=result, reconciliation={"accepted": True})
    assert (handle.attempt_root / "08_reconstruction/core_result.json").exists()
    assert (handle.attempt_root / "01_input/raw_proposal.bin").exists()
    monkeypatch.setattr(ew, "write_new", lambda *args: (_ for _ in ()).throw(OSError("failure record failed")))
    with pytest.raises(ew.WriterFailure, match="failure record failed"):
        ew.record_attempt_failure(handle, reason="original failure")


def reserve(tmp_path, attempt=1):
    return prepare_attempt_boundary(
        attempt_path(tmp_path, "P3-CTRL-01", attempt), authorization(tmp_path),
        session_id="unit-session", batch_id="batch-P3-CTRL-01", scenario_id="P3-CTRL-01",
        attempt_number=attempt,
    )


def test_ir01_duplicate_reservation_and_independent_attempt(tmp_path):
    first = reserve(tmp_path)
    with pytest.raises(WorkspaceBoundaryError, match="reserved"):
        reserve(tmp_path)
    # Windows case aliases and another approval ID must not duplicate the path reservation.
    with pytest.raises(WorkspaceBoundaryError, match="reserved"):
        prepare_attempt_boundary(Path(str(first.output_root).upper()),
            replace(first.authorization, authorization_id="ANOTHER-APPROVAL"),
            session_id="UNIT-SESSION", batch_id="BATCH-P3-CTRL-01",
            scenario_id="P3-CTRL-01", attempt_number=1)
    second = reserve(tmp_path, 2)
    assert first.output_root != second.output_root
    first.output_root.mkdir(parents=True)
    with pytest.raises(WorkspaceBoundaryError):
        bind_prepared_attempt(replace(first), first.output_root)
    bind_prepared_attempt(first, first.output_root)


def test_ir01_consumption_cannot_be_replaced(tmp_path):
    handle = start(tmp_path)
    evaluate(handle)
    with pytest.raises(WorkspaceBoundaryError):
        reserve(tmp_path)
    with pytest.raises(WorkspaceBoundaryError):
        bind_prepared_attempt(handle.boundary, handle.attempt_root)
    # Even removal of the occupied pathname cannot reset the in-process reservation.
    handle.attempt_root.rename(handle.attempt_root.with_name("consumed-retained"))
    with pytest.raises(WorkspaceBoundaryError, match="reserved"):
        reserve(tmp_path)


def test_ir02_binding_requires_exact_root_and_bound_state(tmp_path):
    boundary = reserve(tmp_path)
    boundary.output_root.mkdir(parents=True)
    wrong = tmp_path / "wrong-root"
    wrong.mkdir()
    with pytest.raises(WorkspaceBoundaryError, match="binding"):
        bind_prepared_attempt(boundary, wrong)
    with pytest.raises(WorkspaceBoundaryError, match="identity or lifecycle"):
        validate_output_root(boundary.output_root, boundary.authorization,
            session_id=boundary.session_id, batch_id=boundary.batch_id,
            scenario_id=boundary.scenario_id, attempt_number=1, prepared_boundary=boundary)
    bind_prepared_attempt(boundary, boundary.output_root)
    assert validate_output_root(boundary.output_root, boundary.authorization,
        session_id=boundary.session_id, batch_id=boundary.batch_id,
        scenario_id=boundary.scenario_id, attempt_number=1, prepared_boundary=boundary) == boundary.output_root


def test_ir02_normal_directory_replacement_rejected_before_evaluation(tmp_path, monkeypatch):
    import phase3.runner as runner
    handle = start(tmp_path)
    original = handle.attempt_root
    old_identity = (original.stat().st_dev, original.stat().st_ino)
    original.rename(original.with_name("original-retained"))
    original.mkdir()
    new_identity = (original.stat().st_dev, original.stat().st_ino)
    assert old_identity != new_identity and old_identity[1] and new_identity[1]
    monkeypatch.setattr(runner, "adapt_proposal", lambda *a, **kw: pytest.fail("core evaluation reached"))
    with pytest.raises(WorkspaceBoundaryError, match="directory identity"):
        evaluate(handle)


def test_ir04_result_persistence_once_and_complete_finalize(tmp_path):
    handle = start(tmp_path, "P3-E-02")
    result = evaluate(handle)
    artifact = ew.persist_core_result(handle, core_result=result)
    raw = (handle.attempt_root / artifact.relative_path).read_bytes()
    assert json.loads(raw) == result
    assert artifact.sha256 == hashlib.sha256(raw).hexdigest()
    with pytest.raises(ew.WriterFailure, match="already persisted"):
        ew.persist_core_result(handle, core_result=result)
    summary = ew.finalize_attempt_tree(handle, reconciliation={"accepted": True})
    assert summary.collection_complete
    assert (handle.attempt_root / artifact.relative_path).read_bytes() == raw
