from dataclasses import replace
import json

import pytest

from phase3 import formal_session as fs
from phase3 import formal_preflight as fp
from phase3.constants import SCENARIO_ORDER
from tests.phase3.test_evidence_writer import inputs, file_bytes
from tests.phase3.test_formal_preflight import HEAD, preflight_input, observed_change


def session_setup(tmp_path):
    preflight = preflight_input(tmp_path)
    data = inputs()
    registry = {"registry_id": "P3-CORE-SCENARIOS-v1", "version": "1.0",
                "formal_execution": False, "cases": data.pop("cases")}
    before = file_bytes(tmp_path)
    plan = fs.build_formal_session_plan(
        session_id="unit-session", candidate_head=HEAD, scenario_registry=registry,
        case_batches={case: f"batch-{case}" for case in SCENARIO_ORDER},
        inputs=data, trusted=tuple(item.trusted for item in preflight.materials),
        authorization=preflight.authorization,
    )
    assert file_bytes(tmp_path) == before
    preflight = replace(preflight, plan_identity=plan.identity, slots=plan.slots)
    go = fs.FormalGoApproval(
        "UNIT-GO", True, "2026-09-09T12:01:00+09:00", "UNIT-OPERATOR",
        plan.session_id, plan.identity, HEAD, fs.manifest_bindings(plan),
        fs.workspace_identity(plan.authorization),
    )
    return plan, preflight, go


def test_plan_exact60_batches_inputs_and_pure_creation(tmp_path):
    plan, preflight, go = session_setup(tmp_path)
    assert len(plan.attempts) == 60
    assert len({item.case_batch_id for item in plan.attempts}) == 12
    assert [(item.case_id, item.attempt) for item in plan.attempts] == [
        (case, attempt) for case in SCENARIO_ORDER for attempt in range(1, 6)
    ]
    assert all(item.experiment_id == item.case_id for item in plan.attempts)
    assert not (tmp_path / "phase3_evidence").exists()
    data = fs._inputs(plan)
    data["common_context"]["authority"]["valid_until_tick"] = 0
    assert fs._inputs(plan)["common_context"]["authority"]["valid_until_tick"] == 1100


@pytest.mark.parametrize("fault", ["none", "false", "plan", "head", "materials", "workspace", "preflight"])
def test_no_matching_approval_or_preflight_no_preparation(tmp_path, monkeypatch, fault):
    plan, preflight, go = session_setup(tmp_path)
    if fault == "none":
        go = None
    elif fault == "false":
        go = replace(go, approved=False)
    elif fault == "plan":
        go = replace(go, plan_identity="wrong")
    elif fault == "head":
        go = replace(go, candidate_head="0" * 40)
    elif fault == "materials":
        go = replace(go, manifest_hashes=())
    elif fault == "workspace":
        go = replace(go, workspace_identity="wrong")
    else:
        preflight = replace(preflight, git=observed_change(preflight.git, observed_bytes=None))
    def forbidden(*args, **kwargs):
        pytest.fail("preparation or core called without matching GO and preflight")
    monkeypatch.setattr(fs.writer, "initialize_attempt_tree", forbidden)
    monkeypatch.setattr(fs, "run_scenario", forbidden)
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "NOT_AUTHORIZED"
    assert result.core_call_count == 0
    assert not (tmp_path / "phase3_evidence").exists()


def test_normal60_real_c_paths_writer_replay_and_no_second_start(tmp_path, monkeypatch):
    plan, preflight, go = session_setup(tmp_path)
    original = fs.run_scenario
    calls, verifications = [], []
    def observe(case, **kwargs):
        calls.append((case["scenario_id"], kwargs["attempt_number"]))
        assert kwargs["common_context"]["authority"]["valid_until_tick"] == 1100
        if case["scenario_id"].startswith("P3-C-"):
            assert kwargs["evidence_verification"] is not None
            verifications.append(kwargs["evidence_verification"])
        else:
            assert kwargs["evidence_verification"] is None
        return original(case, **kwargs)
    monkeypatch.setattr(fs, "run_scenario", observe)
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "COMPLETED", (result.stop_reason, result.failure_record_error)
    assert result.core_call_count == 60 and result.retry_count == 0
    assert calls == [(case, attempt) for case in SCENARIO_ORDER for attempt in range(1, 6)]
    assert len(verifications) == 10
    assert all(item.collection_complete for item in result.attempts)
    for item in plan.attempts:
        assert (item.output_root / "08_reconstruction/core_result.json").exists()
    second = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert second.status == "NOT_AUTHORIZED" and second.core_call_count == 0
    assert len(calls) == 60


@pytest.mark.parametrize("fault", ["core", "replay", "state", "writer", "failure_record"])
def test_stop_no_next_attempt_or_retry(tmp_path, monkeypatch, fault):
    plan, preflight, go = session_setup(tmp_path)
    original = fs.run_scenario
    calls = []
    def changed(case, **kwargs):
        calls.append(case["scenario_id"])
        if fault in {"core", "failure_record"}:
            raise ValueError("simulated core divergence")
        result = original(case, **kwargs)
        if fault == "state":
            result["initial_state"] = "SUSPENDED"
        return result
    monkeypatch.setattr(fs, "run_scenario", changed)
    if fault == "replay":
        monkeypatch.setattr(fs, "compare_results", lambda *args: {"must_match": False})
    if fault in {"writer", "failure_record"}:
        monkeypatch.setattr(fs.writer, "finalize_attempt_tree",
                            lambda *a, **kw: (_ for _ in ()).throw(ValueError("writer failure")))
    if fault == "failure_record":
        monkeypatch.setattr(fs.writer, "record_attempt_failure",
                            lambda *a, **kw: (_ for _ in ()).throw(ValueError("failure record failure")))
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "SESSION_STOPPED"
    assert result.core_call_count == 1 and result.retry_count == 0
    assert len(calls) == 1
    assert all(item.status == "NOT_RUN_AFTER_STOP" for item in result.attempts[1:])
    assert not plan.attempts[1].output_root.exists()
    assert (plan.attempts[0].output_root / "01_input/raw_proposal.bin").exists()
    if fault == "failure_record":
        assert "failure record failure" in result.failure_record_error
    else:
        assert result.failure_record_error is None
    if fault in {"replay", "state"}:
        assert result.attempts[0].collection_complete
        finding = json.loads((plan.attempts[0].output_root / "09_findings/finding.json").read_bytes())
        assert finding["finding"] == "FROZEN_RESULT_DIVERGENCE"


def test_c_preparation_failure_has_zero_core_call_for_that_slot(tmp_path, monkeypatch):
    plan, preflight, go = session_setup(tmp_path)
    preparations = []
    def fail(**kwargs):
        preparations.append(kwargs["case_id"])
        raise ValueError("C preparation failure")
    monkeypatch.setattr(fs.materials, "prepare_c_evidence_attempt", fail)
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "SESSION_STOPPED"
    assert result.core_call_count == 30
    assert result.attempts[30].core_called is False
    assert result.attempts[31].status == "NOT_RUN_AFTER_STOP"
    assert preparations == ["P3-C-01"]
    assert not plan.attempts[31].output_root.exists()


def test_final_writer_failure_cannot_be_completed(tmp_path, monkeypatch):
    plan, preflight, go = session_setup(tmp_path)
    original = fs.writer.finalize_attempt_tree
    calls = 0
    def fail_last(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 60:
            raise ValueError("final writer failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(fs.writer, "finalize_attempt_tree", fail_last)
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "SESSION_STOPPED"
    assert result.core_call_count == 60
    assert not result.attempts[-1].collection_complete


def test_occupied_output_is_rejected_before_session(tmp_path):
    plan, preflight, go = session_setup(tmp_path)
    plan.attempts[0].output_root.mkdir(parents=True)
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "NOT_AUTHORIZED" and result.core_call_count == 0


def test_anchor_change_stops_before_next_preparation(tmp_path, monkeypatch):
    plan, preflight, go = session_setup(tmp_path)
    original = fs.writer.finalize_attempt_tree
    def change_after_first(*args, **kwargs):
        result = original(*args, **kwargs)
        trusted = preflight.materials[0].trusted
        fp.anchor_location(trusted.approved_trusted_root, trusted.manifest["manifest_id"]).write_bytes(b"0" * 64)
        return result
    monkeypatch.setattr(fs.writer, "finalize_attempt_tree", change_after_first)
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "SESSION_STOPPED" and result.core_call_count == 1
    assert "local anchor mismatch" in result.stop_reason
    assert not plan.attempts[1].output_root.exists()
    assert all(item.status == "NOT_RUN_AFTER_STOP" for item in result.attempts[2:])


@pytest.mark.parametrize("stage", ["replay", "expected"])
def test_ir04_returned_result_survives_reconciliation_exception(tmp_path, monkeypatch, stage):
    plan, preflight, go = session_setup(tmp_path)
    original = fs.run_scenario
    returned = []
    def observe_core(*args, **kwargs):
        result = original(*args, **kwargs)
        returned.append(result)
        return result
    monkeypatch.setattr(fs, "run_scenario", observe_core)
    result_path = plan.attempts[0].output_root / "08_reconstruction/core_result.json"
    def fail(*args):
        assert json.loads(result_path.read_bytes()) == returned[0]
        assert result_path.with_name("core_result_artifact.json").exists()
        raise ValueError(f"{stage} exception after result saved")
    monkeypatch.setattr(fs, "compare_results" if stage == "replay" else "_expected_matches", fail)
    result = fs.run_formal_session(plan=plan, preflight=preflight, human_go=go)
    assert result.status == "SESSION_STOPPED" and result.core_call_count == 1
    assert len(returned) == 1 and result.retry_count == 0
    assert json.loads(result_path.read_bytes()) == returned[0]
    assert result.failure_record_error is None
    failure = plan.attempts[0].output_root / "09_findings/failure.json"
    assert stage in json.loads(failure.read_bytes())["finding"]
    assert not plan.attempts[1].output_root.exists()
    assert all(item.status == "NOT_RUN_AFTER_STOP" for item in result.attempts[1:])
