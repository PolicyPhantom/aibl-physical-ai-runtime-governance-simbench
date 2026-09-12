from __future__ import annotations

import hashlib
import json
from pathlib import Path

from phase2.live_runner import InvocationStatus, execute_live_observations
from phase2.proposer import LocalRuntimeError, PROMPT_VERSION, render_prompt
from phase2.provenance import ModelInfo
from phase2.runner import run_phase2_raw
from phase2.scenarios import load_phase2_scenario
from tests.helpers import make_fixture
from tests.phase2.helpers import RAW_NORMAL, RUN_TIME, model_info


class SequenceProposer:
    def __init__(self, outcomes: list[str | LocalRuntimeError]) -> None:
        self.outcomes = iter(outcomes)
        self.prompts: list[str] = []
        self.model = ModelInfo(
            provider="local",
            model_name="sequence-fixture",
            runtime="in-process-test-double",
            runtime_version="1",
            sampling_parameters={"temperature": 0},
            artifact_identifier=None,
        )

    def generate_rendered_prompt(self, rendered_prompt: str) -> str:
        self.prompts.append(rendered_prompt)
        outcome = next(self.outcomes)
        if isinstance(outcome, LocalRuntimeError):
            raise outcome
        return outcome


def scenario() -> dict:
    return load_phase2_scenario(
        Path(__file__).resolve().parents[2]
        / "phase2_scenarios"
        / "p2_01_normal_structured_movement.yaml"
    )


def run_batch(tmp_path: Path, outcomes: list[str | LocalRuntimeError], task: str):
    return execute_live_observations(
        proposer=SequenceProposer(outcomes),
        task_instruction=task,
        scenario_document=scenario(),
        repeat=len(outcomes),
        output_dir=tmp_path,
        now=lambda: RUN_TIME,
    )


def batch_snapshot(batch_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(batch_dir).as_posix(): path.read_bytes()
        for path in sorted(batch_dir.rglob("*"))
        if path.is_file()
    }


def test_two_live_batches_preserve_first_and_use_distinct_paths(tmp_path: Path) -> None:
    first = run_batch(tmp_path, [RAW_NORMAL], "Move normally to ZONE_B.")
    first_dir = tmp_path / first[0].observation.batch_id
    before = batch_snapshot(first_dir)

    second = run_batch(tmp_path, [RAW_NORMAL], "Move normally to ZONE_B.")
    second_dir = tmp_path / second[0].observation.batch_id

    assert first_dir != second_dir
    assert batch_snapshot(first_dir) == before
    assert first[0].observation.run_id != second[0].observation.run_id
    assert set(first_dir.rglob("*")).isdisjoint(set(second_dir.rglob("*")))


def test_later_invalid_batch_cannot_inherit_stale_receipt(tmp_path: Path) -> None:
    valid = run_batch(tmp_path, [RAW_NORMAL], "Move normally to ZONE_B.")
    invalid = run_batch(tmp_path, ["not json"], "Move normally to ZONE_B.")
    valid_dir = tmp_path / valid[0].observation.batch_id
    invalid_dir = tmp_path / invalid[0].observation.batch_id

    assert len(list((valid_dir / "receipts").glob("*.json"))) == 1
    assert invalid[0].observation.governance_receipt_id is None
    assert list((invalid_dir / "receipts").glob("*.json")) == []
    assert invalid[0].observation.run_id != valid[0].observation.run_id


def test_failure_on_attempt_three_is_recorded_and_later_attempts_continue(
    tmp_path: Path,
) -> None:
    failure = LocalRuntimeError(
        "runtime exited",
        exit_code=7,
        stderr="fixture failure",
        timeout_seconds=None,
    )
    attempts = run_batch(
        tmp_path,
        [RAW_NORMAL, RAW_NORMAL, failure, RAW_NORMAL, RAW_NORMAL],
        "Move normally to ZONE_B.",
    )
    batch_dir = tmp_path / attempts[0].observation.batch_id

    assert [item.observation.attempt_index for item in attempts] == [1, 2, 3, 4, 5]
    assert attempts[2].observation.invocation_status == InvocationStatus.INVOCATION_FAILED
    assert attempts[2].observation.error == {
        "category": "LOCAL_RUNTIME_ERROR",
        "exit_code": 7,
        "stderr": "fixture failure",
        "timeout_seconds": None,
    }
    assert attempts[2].observation.raw_output_path is None
    assert attempts[2].observation.phase2_provenance_path is None
    assert attempts[2].observation.governance_receipt_id is None
    assert attempts[2].phase2_result is None
    assert attempts[3].observation.invocation_status == InvocationStatus.COMPLETED
    assert attempts[4].observation.invocation_status == InvocationStatus.COMPLETED
    assert len(list((batch_dir / "observations").glob("*.json"))) == 5
    assert len(list((batch_dir / "raw").glob("*.txt"))) == 4
    assert len(list((batch_dir / "provenance").glob("*.json"))) == 4


def test_invocation_failure_has_no_fabricated_downstream_artifacts(
    tmp_path: Path,
) -> None:
    failure = LocalRuntimeError(
        "runtime timed out",
        stderr=None,
        timeout_seconds=5,
    )
    attempts = run_batch(
        tmp_path,
        [failure],
        "Move normally to ZONE_B.",
    )
    attempt = attempts[0]
    batch_dir = tmp_path / attempt.observation.batch_id

    assert attempt.observation.invocation_status == InvocationStatus.INVOCATION_FAILED
    assert attempt.observation.raw_output_path is None
    assert attempt.observation.phase2_provenance_path is None
    assert attempt.observation.governance_receipt_id is None
    assert attempt.phase2_result is None
    assert list((batch_dir / "raw").iterdir()) == []
    assert list((batch_dir / "provenance").iterdir()) == []
    assert list((batch_dir / "receipts").iterdir()) == []
    saved = json.loads(attempt.observation_path.read_text(encoding="utf-8"))
    assert saved["error"] == {
        "category": "LOCAL_RUNTIME_ERROR",
        "exit_code": None,
        "stderr": None,
        "timeout_seconds": 5,
    }


def test_p2_03_restriction_application_unsupported_is_adapter_mediated() -> None:
    raw_high = RAW_NORMAL.replace('"NORMAL"', '"HIGH"')
    fixture = make_fixture(
        scenario_id="P2-03-restriction-failure",
        context={"operating_condition": "LOW_SPEED_ONLY"},
        restriction_application_supported=False,
    )
    result = run_phase2_raw(
        raw_high,
        fixture,
        model=model_info(),
        prompt_version=PROMPT_VERSION,
        run_time=RUN_TIME,
    )

    assert result.adapter.parse_status.value == "VALID"
    assert result.phase1_result is not None
    assert result.phase1_result.receipt["decision"] == "RESTRICT"
    assert result.phase1_result.receipt["reason_codes"] == [
        "SPEED_RESTRICTION_REQUIRED"
    ]
    assert result.phase1_result.receipt["execution_result"] == "HELD"
    assert result.phase1_result.receipt["final_state"] == "RUNNING"


def test_same_rendered_prompt_has_same_hash_across_attempts(tmp_path: Path) -> None:
    task = "Move normally to ZONE_B."
    attempts = run_batch(tmp_path, [RAW_NORMAL] * 5, task)
    expected = hashlib.sha256(render_prompt(task).encode("utf-8")).hexdigest()

    assert {item.observation.rendered_prompt_sha256 for item in attempts} == {
        expected
    }
    for item in attempts:
        saved = json.loads(item.observation_path.read_text(encoding="utf-8"))
        assert saved["task_instruction"] == task
        assert saved["rendered_prompt_sha256"] == expected


def test_different_task_under_same_prompt_version_has_different_hash(
    tmp_path: Path,
) -> None:
    first = run_batch(tmp_path, [RAW_NORMAL], "Move normally to ZONE_B.")
    second = run_batch(tmp_path, [RAW_NORMAL], "Move slowly to ZONE_B.")

    assert first[0].observation.prompt_version == second[0].observation.prompt_version
    assert (
        first[0].observation.rendered_prompt_sha256
        != second[0].observation.rendered_prompt_sha256
    )


def test_identical_output_across_five_attempts_has_distinct_run_ids(
    tmp_path: Path,
) -> None:
    attempts = run_batch(tmp_path, [RAW_NORMAL] * 5, "Move normally to ZONE_B.")
    run_ids = [item.observation.run_id for item in attempts]

    assert len(set(run_ids)) == 5
    assert all(
        item.phase2_result is not None
        and item.phase2_result.provenance.run_id == item.observation.run_id
        for item in attempts
    )
