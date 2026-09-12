from dataclasses import FrozenInstanceError
import ast
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

import phase3.runner as runner
from phase3.models import WorkspaceAuthorization
from phase3.runner import WorkspaceBoundaryError, validate_output_root


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "phase3_schemas"


def _authorization(tmp_path: Path, *protected_roots: Path) -> WorkspaceAuthorization:
    return WorkspaceAuthorization(
        authorized_workspace_root=tmp_path,
        authorization_id="OPERATOR-AUTH-TEST-001",
        protected_roots=tuple(protected_roots) or (ROOT,),
    )


def _attempt(tmp_path: Path, scenario_id: str = "P3-CTRL-01") -> Path:
    return (
        tmp_path
        / "phase3_evidence"
        / "session-01"
        / "batch-01"
        / scenario_id
        / "attempt-01"
    )


def _validate(path: Path, authorization: WorkspaceAuthorization) -> Path:
    return validate_output_root(
        path,
        authorization,
        session_id="session-01",
        batch_id="batch-01",
        scenario_id="P3-CTRL-01",
        attempt_number=1,
    )


def test_runner_accepts_operator_authorized_fixed_layout_without_creating_it(tmp_path):
    candidate = _attempt(tmp_path)
    accepted = _validate(candidate, _authorization(tmp_path))
    assert accepted == candidate
    assert not candidate.exists()


def test_workspace_authorization_is_immutable_operator_input(tmp_path):
    authorization = _authorization(tmp_path)
    assert isinstance(authorization.protected_roots, tuple)
    with pytest.raises(FrozenInstanceError):
        authorization.authorization_id = "candidate-replacement"


def test_wrong_layout_attempt_range_and_existing_attempt_are_rejected(tmp_path):
    authorization = _authorization(tmp_path)
    with pytest.raises(WorkspaceBoundaryError) as wrong_layout:
        _validate(tmp_path / "attempt-01", authorization)
    assert wrong_layout.value.code == "OPERATOR_WORKSPACE_BOUNDARY_REJECTED"

    with pytest.raises(WorkspaceBoundaryError):
        validate_output_root(
            _attempt(tmp_path),
            authorization,
            session_id="session-01",
            batch_id="batch-01",
            scenario_id="P3-CTRL-01",
            attempt_number=0,
        )

    existing = _attempt(tmp_path)
    existing.mkdir(parents=True)
    with pytest.raises(WorkspaceBoundaryError):
        _validate(existing, authorization)


def test_protected_overlap_is_bidirectional_and_windows_case_insensitive(tmp_path):
    candidate = _attempt(tmp_path)
    protected_cases = (
        candidate.parent,
        candidate / "protected-child",
        Path(str(candidate).upper()),
    )
    for protected in protected_cases:
        with pytest.raises(WorkspaceBoundaryError):
            _validate(candidate, _authorization(tmp_path, protected))


def test_reparse_is_rejected_from_nonfollowing_metadata_before_resolution(
    tmp_path, monkeypatch
):
    candidate = _attempt(tmp_path)
    actual_lstat = runner._lstat_no_follow

    def marked_lstat(path):
        observed = actual_lstat(path)
        if runner._windows_parts(Path(path)) == runner._windows_parts(tmp_path):
            return SimpleNamespace(
                st_mode=observed.st_mode,
                st_file_attributes=0x400,
            )
        return observed

    monkeypatch.setattr(runner, "_lstat_no_follow", marked_lstat)
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("resolve must not be called")
        ),
    )
    with pytest.raises(WorkspaceBoundaryError) as rejected:
        _validate(candidate, _authorization(tmp_path))
    assert rejected.value.code == "OPERATOR_WORKSPACE_BOUNDARY_REJECTED"


def test_ancestor_reparse_stops_before_root_or_descendant_metadata_access(
    tmp_path, monkeypatch
):
    candidate = _attempt(tmp_path)
    marked_ancestor = tmp_path.parent
    actual_lstat = runner._lstat_no_follow
    observed_paths = []

    def marked_lstat(path):
        observed_path = Path(path)
        observed_paths.append(observed_path)
        observed = actual_lstat(observed_path)
        if runner._windows_parts(observed_path) == runner._windows_parts(
            marked_ancestor
        ):
            return SimpleNamespace(
                st_mode=observed.st_mode,
                st_file_attributes=0x400,
            )
        return observed

    monkeypatch.setattr(runner, "_lstat_no_follow", marked_lstat)
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("resolve must not be called")
        ),
    )

    with pytest.raises(WorkspaceBoundaryError) as rejected:
        _validate(candidate, _authorization(tmp_path))

    assert rejected.value.code == "OPERATOR_WORKSPACE_BOUNDARY_REJECTED"
    root_parts = runner._windows_parts(tmp_path)
    assert runner._windows_parts(observed_paths[-1]) == runner._windows_parts(
        marked_ancestor
    )
    assert not any(
        runner._windows_parts(path)[: len(root_parts)] == root_parts
        for path in observed_paths
    )


def test_phase3_package_has_no_network_process_or_cli_path():
    package = ROOT / "phase3"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )
    forbidden = (
        "import requests",
        "import socket",
        "urllib.request",
        "subprocess",
        "if __name__ ==",
    )
    assert all(item not in source for item in forbidden)
    core = {
        "__init__", "adapter", "constants", "context", "evidence", "governance",
        "identity", "models", "physical", "reentry", "replay", "runner",
    }
    formal = {"formal_materials", "evidence_writer", "formal_session", "formal_preflight"}
    assert {path.stem for path in package.glob("*.py")} == core | formal
    for name in core:
        tree = ast.parse((package / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not (set(alias.name.split(".")) & formal) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (set((node.module or "").split(".")) & formal)
                assert all(alias.name not in formal for alias in node.names)


def test_changed_json_schemas_are_valid_and_paths_are_posix_relative():
    trusted = json.loads(
        (SCHEMAS / "trusted_manifest_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    result = json.loads(
        (SCHEMAS / "scenario_result_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )

    path_pattern = trusted["properties"]["files"]["items"]["properties"][
        "relative_path"
    ]["pattern"]
    assert re.fullmatch(path_pattern, "nested/decision_receipt.json")
    assert re.fullmatch(path_pattern, "../decision_receipt.json") is None
    assert re.fullmatch(path_pattern, "nested\\decision_receipt.json") is None
    assert re.fullmatch(
        result["properties"]["scenario_id"]["pattern"], "P3-CTRL-01"
    )
    assert "perturbation_identity" in result["required"]
    assert "decision_basis" in result["required"]
    assert result["properties"]["decision_basis"]["additionalProperties"] is False
    physical_branch = result["properties"]["physical_result"]["oneOf"][1]
    assert "command_issued_at_tick" in physical_branch["required"]
    assert physical_branch["properties"]["command_issued_at_tick"]["const"] == 1000
    assert physical_branch["properties"]["verification_tick"]["const"] == 1001
