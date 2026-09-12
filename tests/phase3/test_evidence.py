import hashlib
import stat
from copy import deepcopy
from types import SimpleNamespace

import pytest
import phase3.evidence as evidence
from pathlib import Path

from phase3.evidence import verify_evidence_set


def _record(path: Path, root: Path, role: str) -> dict:
    data = path.read_bytes()
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "role": role,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_identity": "sha256:" + hashlib.sha256(data).hexdigest(),
    }


def _evidence(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "working-evidence"
    root.mkdir()
    proposal = root / "raw_proposal.json"
    receipt = root / "decision_receipt.json"
    state = root / "state_result.json"
    proposal.write_bytes(b'{"request_type":"REENTRY"}\n')
    receipt.write_bytes(b'{"decision":"DENY"}\n')
    state.write_bytes(b'{"final_state":"SUSPENDED"}\n')
    manifest = {
        "manifest_id": "TEST-MANIFEST",
        "manifest_version": "1.0",
        "fixture_set_id": "TEST-FIXTURE",
        "experiment_scope": "P3-C",
        "created_before_formal_run": True,
        "files": [
            _record(receipt, root, "DECISION_RECEIPT"),
            _record(proposal, root, "RAW_PROPOSAL"),
            _record(state, root, "STATE_RESULT"),
        ],
    }
    manifest["files"].sort(key=lambda item: item["relative_path"])
    return root, manifest


def test_complete_set_is_integrity_verified(tmp_path):
    root, manifest = _evidence(tmp_path)
    result = verify_evidence_set(root, manifest)
    assert result.completeness == "COMPLETE"
    assert result.present_file_integrity == "INTEGRITY_VERIFIED"
    assert result.full_set_integrity == "ESTABLISHED"


def test_missing_receipt_is_incomplete_but_present_files_verify(tmp_path):
    root, manifest = _evidence(tmp_path)
    (root / "decision_receipt.json").unlink()
    result = verify_evidence_set(root, manifest)
    assert result.completeness == "INCOMPLETE"
    assert result.completeness_reason == "DECISION_RECEIPT_MISSING"
    assert result.present_file_integrity == "INTEGRITY_VERIFIED"
    assert result.full_set_integrity == "NOT_ESTABLISHED"
    assert result.missing_paths == ("decision_receipt.json",)


def test_altered_receipt_is_complete_but_integrity_fails(tmp_path):
    root, manifest = _evidence(tmp_path)
    (root / "decision_receipt.json").write_bytes(b'{"decision":"ALLOW"}\n')
    result = verify_evidence_set(root, manifest)
    assert result.completeness == "COMPLETE"
    assert result.present_file_integrity == "INTEGRITY_FAILURE"
    assert result.integrity_reason == "DECISION_RECEIPT_HASH_MISMATCH"
    assert result.full_set_integrity == "NOT_ESTABLISHED"

def _forbidden(*args, **kwargs):
    raise AssertionError("operation must not be reached")


def _marked(metadata, mode=None, attributes=0):
    return SimpleNamespace(
        st_mode=metadata.st_mode if mode is None else mode,
        st_size=metadata.st_size,
        st_file_attributes=attributes,
    )


@pytest.mark.parametrize("boundary", ["ancestor", "root"])
@pytest.mark.parametrize("kind", ["reparse", "symlink"])
def test_root_boundary_stops_before_descendant_access(tmp_path, monkeypatch, boundary, kind):
    root, manifest = _evidence(tmp_path)
    target = tmp_path if boundary == "ancestor" else root
    original = evidence._lstat_no_follow
    calls = []

    def inspect(path):
        calls.append(path)
        if path == target:
            return _marked(
                original(path),
                mode=stat.S_IFLNK if kind == "symlink" else None,
                attributes=0x400 if kind == "reparse" else 0,
            )
        return original(path)

    monkeypatch.setattr(evidence, "_lstat_no_follow", inspect)
    monkeypatch.setattr(evidence, "_children", _forbidden)
    monkeypatch.setattr(evidence, "_sha256", _forbidden)
    monkeypatch.setattr(Path, "resolve", _forbidden)
    monkeypatch.setattr(Path, "open", _forbidden)
    with pytest.raises(ValueError, match="reparse"):
        verify_evidence_set(root, manifest)
    assert calls[-1] == target
    assert not any(target in path.parents for path in calls)


@pytest.mark.parametrize("entry_kind", ["file", "directory"])
@pytest.mark.parametrize("mark", ["reparse", "symlink", "special"])
def test_tree_entry_is_rejected_before_target_access(tmp_path, monkeypatch, entry_kind, mark):
    root, manifest = _evidence(tmp_path)
    target = root / "000-boundary"
    if entry_kind == "directory":
        target.mkdir()
        (target / "sentinel").write_bytes(b"do not read")
    else:
        target.write_bytes(b"do not read")
    original = evidence._lstat_no_follow
    original_children = evidence._children
    metadata_calls = []
    enumeration_calls = []

    def inspect(path):
        metadata_calls.append(path)
        result = original(path)
        if path == target:
            mode = {"symlink": stat.S_IFLNK, "special": stat.S_IFIFO}.get(mark)
            return _marked(result, mode=mode, attributes=0x400 if mark == "reparse" else 0)
        return result

    def children(path):
        enumeration_calls.append(path)
        assert path != target and target not in path.parents
        return original_children(path)

    monkeypatch.setattr(evidence, "_lstat_no_follow", inspect)
    monkeypatch.setattr(evidence, "_children", children)
    monkeypatch.setattr(evidence, "_sha256", _forbidden)
    monkeypatch.setattr(Path, "open", _forbidden)
    with pytest.raises(ValueError, match="reparse|special"):
        verify_evidence_set(root, manifest)
    assert enumeration_calls == [root]
    assert metadata_calls[-1] == target
    assert not any(target in path.parents for path in metadata_calls)


@pytest.mark.parametrize("boundary", ["ancestor", "root"])
@pytest.mark.parametrize("failure", ["missing", "denied", "not-directory"])
def test_root_inspection_failure_stops_immediately(tmp_path, monkeypatch, boundary, failure):
    root, manifest = _evidence(tmp_path)
    target = tmp_path if boundary == "ancestor" else root
    original = evidence._lstat_no_follow
    calls = []

    def inspect(path):
        calls.append(path)
        if path == target:
            if failure == "missing":
                raise FileNotFoundError(str(path))
            if failure == "denied":
                raise PermissionError(str(path))
            return _marked(original(path), mode=stat.S_IFREG)
        return original(path)

    exception = {"missing": FileNotFoundError, "denied": PermissionError,
                 "not-directory": ValueError}[failure]
    monkeypatch.setattr(evidence, "_lstat_no_follow", inspect)
    monkeypatch.setattr(evidence, "_children", _forbidden)
    monkeypatch.setattr(evidence, "_sha256", _forbidden)
    with pytest.raises(exception):
        verify_evidence_set(root, manifest)
    assert calls[-1] == target
    assert not any(target in path.parents for path in calls)


@pytest.mark.parametrize("stage", ["enumeration", "metadata", "hash"])
def test_tree_access_errors_are_not_reported_as_success(tmp_path, monkeypatch, stage):
    root, manifest = _evidence(tmp_path)

    def denied(*args, **kwargs):
        raise PermissionError("test access denied")

    if stage == "enumeration":
        monkeypatch.setattr(evidence, "_children", denied)
        monkeypatch.setattr(evidence, "_sha256", _forbidden)
    elif stage == "metadata":
        original = evidence._lstat_no_follow

        def inspect(path):
            if path.parent == root:
                denied()
            return original(path)

        monkeypatch.setattr(evidence, "_lstat_no_follow", inspect)
        monkeypatch.setattr(evidence, "_sha256", _forbidden)
    else:
        monkeypatch.setattr(evidence, "_sha256", denied)
    with pytest.raises(PermissionError):
        verify_evidence_set(root, manifest)


@pytest.mark.parametrize("relative", [
    None, 7, "", "/receipt.json", "C:/receipt.json", "C:receipt.json",
    "//server/share/receipt.json", "nested\\receipt.json", "receipt:stream",
    "../receipt.json", "nested/../receipt.json", "./receipt.json",
    "nested/./receipt.json", "nested//receipt.json", "nested/", "bad\x00name",
])
def test_invalid_manifest_paths_fail_before_filesystem_access(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(evidence, "_lstat_no_follow", _forbidden)
    monkeypatch.setattr(evidence, "_children", _forbidden)
    monkeypatch.setattr(evidence, "_sha256", _forbidden)
    with pytest.raises(ValueError):
        verify_evidence_set(tmp_path, {"files": [{"relative_path": relative}]})


def test_duplicate_manifest_paths_fail_before_filesystem_access(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_lstat_no_follow", _forbidden)
    record = {"relative_path": "receipt.json"}
    with pytest.raises(ValueError, match="duplicate"):
        verify_evidence_set(tmp_path, {"files": [record, dict(record)]})


def test_parent_traversal_root_fails_before_filesystem_access(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_lstat_no_follow", _forbidden)
    with pytest.raises(ValueError, match="parent traversal"):
        verify_evidence_set(tmp_path / ".." / "other", {"files": []})


def test_nested_evidence_and_manifest_remain_unchanged(tmp_path):
    root, manifest = _evidence(tmp_path)
    nested = root / "nested" / "deeper"
    nested.mkdir(parents=True)
    extra = nested / "observation.json"
    extra.write_bytes(b'{"observed":true}\n')
    manifest["files"].append(_record(extra, root, "OBSERVATION"))
    manifest["files"].sort(key=lambda record: record["relative_path"])
    before_manifest = deepcopy(manifest)
    before_paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
    before_bytes = {path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*") if path.is_file()}
    result = verify_evidence_set(root, manifest)
    assert result.completeness == "COMPLETE"
    assert result.present_file_integrity == "INTEGRITY_VERIFIED"
    assert result.full_set_integrity == "ESTABLISHED"
    assert manifest == before_manifest
    assert sorted(path.relative_to(root).as_posix() for path in root.rglob("*")) == before_paths
    assert {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()} == before_bytes


def test_ordinary_unexpected_file_preserves_existing_reason(tmp_path):
    root, manifest = _evidence(tmp_path)
    (root / "unexpected.txt").write_bytes(b"extra")
    result = verify_evidence_set(root, manifest)
    assert result.completeness == "INCOMPLETE"
    assert result.completeness_reason == "UNEXPECTED_EVIDENCE_PRESENT"
    assert result.present_file_integrity == "INTEGRITY_VERIFIED"
    assert result.full_set_integrity == "NOT_ESTABLISHED"
    assert result.unexpected_paths == ("unexpected.txt",)


def test_relative_root_is_lexical_without_resolve(tmp_path, monkeypatch):
    root, manifest = _evidence(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "resolve", _forbidden)
    result = verify_evidence_set(Path(root.name), manifest)
    assert result.full_set_integrity == "ESTABLISHED"
