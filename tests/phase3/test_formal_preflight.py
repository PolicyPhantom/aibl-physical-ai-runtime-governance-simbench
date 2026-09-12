from dataclasses import replace
import hashlib
import sys

import pytest

from phase3 import formal_preflight as fp
from phase3.constants import SCENARIO_ORDER
from phase3.runner import WorkspaceBoundaryError
from tests.phase3.test_evidence_writer import ROOT, authorization, attempt_path, file_bytes
from tests.phase3.test_formal_materials import trusted_fixture

HEAD = "84c5f2205495201f08d9503affc61ab33c1e99a7"


def checked(expected, observed, kind):
    return fp.ObservationCheck(
        fp.expectation(approved=expected, basis="unit-approved-checkpoint"),
        fp.observation(observed=observed, state="OBSERVED", source_kind=kind,
                       reference="unit-observation-record", actor="UNIT-OPERATOR"),
    )


def observed_change(check, **changes):
    return replace(check, observation=replace(check.observation, **changes))


def preflight_input(tmp_path, plan_identity="unit-plan"):
    materials = []
    for case_id in ("P3-C-01", "P3-C-02"):
        trusted, _, _ = trusted_fixture(tmp_path, case_id)
        manifest_path = trusted.root.parent / "trusted_manifest.json"
        manifest_path.write_bytes(trusted.manifest_bytes)
        fp.create_local_manifest_anchor(
            manifest_path=manifest_path, approved_trusted_root=trusted.approved_trusted_root,
            manifest_id=trusted.manifest["manifest_id"], fixture_id=trusted.fixture_id,
            protected_roots=(ROOT,), approval_id="UNIT-ANCHOR-APPROVAL",
        )
        materials.append(fp.MaterialAnchor(trusted, manifest_path, fp.ExternalAnchorRecord(
            "unit-external-reference", trusted.manifest_sha256, "2026-09-09T12:00:00+09:00",
            "UNIT-OPERATOR", fp.PRE_FORMAL,
        )))
    git = dict(head=HEAD, branch="main", tracked_count=140, remote_count=0,
               tracked_changes=[], staged_changes=[])
    runtime = dict(python_executable=sys.executable, python_version=sys.version.split()[0],
                   execution_actor="UNIT-OPERATOR", execution_boundary="UNIT-TEMP")
    return fp.collect_formal_preflight(
        plan_identity=plan_identity,
        git=checked(git, git, "COMMAND_OUTPUT"),
        runtime=checked(runtime, runtime, "RUNTIME_INSPECTION"),
        logical_config=checked(fp.FROZEN_CONFIG, fp.FROZEN_CONFIG, "CONFIG_INSPECTION"),
        authorization=authorization(tmp_path),
        slots=[fp.OutputSlot("unit-session", f"batch-{case}", case, attempt, attempt_path(tmp_path, case, attempt))
               for case in SCENARIO_ORDER for attempt in range(1, 6)],
        materials=materials, workspace_observation=fp.observation(
            observed={"root": str(tmp_path), "authorization_id": "UNIT-AUTH",
                      "protected_roots": [str(ROOT), str(tmp_path / "phase3_trusted")]},
            state="OBSERVED", source_kind="FILESYSTEM_INSPECTION",
            reference="unit-output-plan-inspection", actor="UNIT-OPERATOR"),
    )


def test_anchor_raw_identity_and_existing_matching_unchanged(tmp_path):
    value = preflight_input(tmp_path)
    material = value.materials[0]
    trusted = material.trusted
    path = fp.anchor_location(trusted.approved_trusted_root, trusted.manifest["manifest_id"])
    before = path.read_bytes()
    record = fp.create_local_manifest_anchor(
        manifest_path=material.manifest_path, approved_trusted_root=trusted.approved_trusted_root,
        manifest_id=trusted.manifest["manifest_id"], fixture_id=trusted.fixture_id,
        protected_roots=(ROOT,), approval_id="unit",
    )
    assert not record.created
    assert path.read_bytes() == before
    assert record.manifest_sha256 == hashlib.sha256(material.manifest_path.read_bytes()).hexdigest()


def test_anchor_uses_raw_bytes_not_reserialization_and_never_overwrites(tmp_path):
    value = preflight_input(tmp_path)
    material = value.materials[0]
    trusted = material.trusted
    anchor = fp.anchor_location(trusted.approved_trusted_root, trusted.manifest["manifest_id"])
    before = anchor.read_bytes()
    material.manifest_path.write_bytes(b" " + material.manifest_path.read_bytes())
    with pytest.raises(ValueError, match="differs"):
        fp.create_local_manifest_anchor(
            manifest_path=material.manifest_path, approved_trusted_root=trusted.approved_trusted_root,
            manifest_id=trusted.manifest["manifest_id"], fixture_id=trusted.fixture_id,
            protected_roots=(ROOT,), approval_id="unit",
        )
    assert anchor.read_bytes() == before
    assert not fp.evaluate_formal_preflight(value).ready_for_human_go


@pytest.mark.parametrize("field", ["head", "branch", "tracked_count", "remote_count", "tracked_changes", "staged_changes"])
def test_git_mismatch_is_not_ready(tmp_path, field):
    import json
    value = preflight_input(tmp_path)
    expected = json.loads(value.git.expectation.approved_bytes)
    changed = expected | {field: "wrong"}
    changed_value = replace(value, git=checked(expected, changed, "COMMAND_OUTPUT"))
    assert not fp.evaluate_formal_preflight(changed_value).ready_for_human_go


@pytest.mark.parametrize("field", ["git", "runtime"])
def test_unknown_observation_rejected(tmp_path, field):
    value = preflight_input(tmp_path)
    item = getattr(value, field)
    result = fp.evaluate_formal_preflight(replace(value, **{field: observed_change(item, observed_bytes=None)}))
    assert not result.ready_for_human_go


def test_runtime_and_config_mismatch(tmp_path):
    value = preflight_input(tmp_path)
    assert not fp.evaluate_formal_preflight(replace(value, runtime=observed_change(value.runtime, observed_bytes=b"{}"))).ready_for_human_go
    bad_config = fp.FROZEN_CONFIG | {"T_EVAL": 1001}
    assert not fp.evaluate_formal_preflight(replace(value, logical_config=checked(
        bad_config, bad_config, "CONFIG_INSPECTION"))).ready_for_human_go


@pytest.mark.parametrize("fault", ["hash", "status", "one", "local"])
def test_anchor_mapping_failures(tmp_path, fault):
    value = preflight_input(tmp_path)
    material = value.materials[0]
    if fault == "one":
        value = replace(value, materials=(material,))
    elif fault == "local":
        fp.anchor_location(material.trusted.approved_trusted_root, material.trusted.manifest["manifest_id"]).write_bytes(b"0" * 64)
    else:
        external = replace(material.external, **({"manifest_sha256": "0" * 64} if fault == "hash" else {"status": "EXECUTED"}))
        value = replace(value, materials=(replace(material, external=external), value.materials[1]))
    assert not fp.evaluate_formal_preflight(value).ready_for_human_go


def test_output_collision_protection_and_reparse(tmp_path, monkeypatch):
    value = preflight_input(tmp_path)
    collision = value.slots[0].output_root
    collision.mkdir(parents=True)
    assert not fp.evaluate_formal_preflight(value).ready_for_human_go
    protected = replace(value.authorization, protected_roots=(tmp_path,))
    assert not fp.evaluate_formal_preflight(replace(value, authorization=protected)).ready_for_human_go
    monkeypatch.setattr(fp, "validate_output_root", lambda *a, **kw: (_ for _ in ()).throw(WorkspaceBoundaryError("reparse")))
    assert not fp.evaluate_formal_preflight(value).ready_for_human_go


def test_ready_is_read_only_and_snapshots_observations(tmp_path):
    value = preflight_input(tmp_path)
    before = file_bytes(tmp_path)
    result = fp.evaluate_formal_preflight(value)
    assert result.ready_for_human_go, result.blocking_reasons
    assert file_bytes(tmp_path) == before
    assert not (tmp_path / "phase3_evidence").exists()
    expected = {"head": HEAD}
    record = checked(expected, expected, "COMMAND_OUTPUT")
    expected["head"] = "changed"
    assert b"changed" not in record.expectation.approved_bytes
    assert b"changed" not in record.observation.observed_bytes


@pytest.mark.parametrize("state", ["UNKNOWN", "UNOBSERVED", "", None])
def test_ir03_equal_values_without_completed_observation_not_ready(tmp_path, state):
    value = preflight_input(tmp_path)
    changed = observed_change(value.runtime, state=state)
    assert changed.expectation.approved_bytes == changed.observation.observed_bytes
    assert not fp.evaluate_formal_preflight(replace(value, runtime=changed)).ready_for_human_go


@pytest.mark.parametrize("field", ["python_executable", "python_version", "execution_actor", "execution_boundary"])
def test_ir03_equal_unknown_runtime_sentinel_not_ready(tmp_path, field):
    import json
    value = preflight_input(tmp_path)
    runtime = json.loads(value.runtime.expectation.approved_bytes) | {field: "UNKNOWN"}
    assert not fp.evaluate_formal_preflight(replace(value, runtime=checked(
        runtime, runtime, "RUNTIME_INSPECTION"))).ready_for_human_go


@pytest.mark.parametrize("changes", [
    {"source_kind": "I checked it"}, {"source_kind": ""},
    {"reference": ""}, {"reference": None}, {"actor": "UNKNOWN"},
])
def test_ir03_source_kind_and_reference_required(tmp_path, changes):
    value = preflight_input(tmp_path)
    assert not fp.evaluate_formal_preflight(replace(value,
        runtime=observed_change(value.runtime, **changes))).ready_for_human_go


def test_ir03_missing_expectation_basis_rejected(tmp_path):
    value = preflight_input(tmp_path)
    runtime = replace(value.runtime, expectation=replace(value.runtime.expectation, basis=""))
    assert not fp.evaluate_formal_preflight(replace(value, runtime=runtime)).ready_for_human_go


def test_ir03_distinct_records_ready_without_execution(tmp_path, monkeypatch):
    from phase3 import formal_session
    value = preflight_input(tmp_path)
    assert value.runtime.expectation.basis != value.runtime.observation.reference
    monkeypatch.setattr(formal_session, "run_scenario", lambda *a, **kw: pytest.fail("core probe"))
    monkeypatch.setattr(formal_session, "run_formal_session", lambda *a, **kw: pytest.fail("session started"))
    before = file_bytes(tmp_path)
    assert fp.evaluate_formal_preflight(value).ready_for_human_go
    assert file_bytes(tmp_path) == before
