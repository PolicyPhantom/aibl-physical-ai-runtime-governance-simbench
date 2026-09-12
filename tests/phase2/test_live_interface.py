from __future__ import annotations

import sys
from pathlib import Path

import pytest

from phase2.proposer import (
    LocalCommandProposer,
    LocalRuntimeError,
    PROMPT_VERSION,
    load_prompt_template,
    render_prompt,
)
from phase2.provenance import ModelInfo
from phase2.live_runner import execute_live_observations
from phase2.runner import run_live_task
from phase2.scenarios import load_phase2_scenario
from tests.helpers import make_fixture
from tests.phase2.helpers import RAW_NORMAL, RUN_TIME


def fake_model(command_code: str) -> LocalCommandProposer:
    return LocalCommandProposer(
        command=(sys.executable, "-B", "-c", command_code),
        model=ModelInfo(
            provider="local",
            model_name="deterministic-interface-fixture",
            runtime="python-subprocess-fixture",
            runtime_version=sys.version.split()[0],
            sampling_parameters={"temperature": 0},
            artifact_identifier=None,
        ),
        timeout_seconds=10,
    )


def test_versioned_prompt_preserves_proposal_only_boundary() -> None:
    template = load_prompt_template()
    prompt = render_prompt("Move normally to ZONE_B.", template)
    assert PROMPT_VERSION == "phase2_action_proposal_v1"
    assert "Move normally to ZONE_B." in prompt
    assert "exactly one JSON object" in prompt
    assert "permission decision" in prompt
    assert "{{TASK_INSTRUCTION}}" not in prompt


def test_local_command_interface_passes_raw_output_to_governance() -> None:
    code = f"import sys; sys.stdin.read(); print({RAW_NORMAL!r}, end='')"
    result = run_live_task(
        fake_model(code),
        "Move normally to ZONE_B.",
        make_fixture(scenario_id="local-interface-fixture"),
        run_time=RUN_TIME,
    )
    assert result.provenance.raw_llm_output == RAW_NORMAL
    assert result.provenance.prompt_version == PROMPT_VERSION
    assert result.phase1_result is not None
    assert result.phase1_result.receipt["decision"] == "ALLOW"


def test_local_command_failure_does_not_fabricate_model_output() -> None:
    proposer = fake_model("import sys; sys.stderr.write('failed'); raise SystemExit(7)")
    with pytest.raises(LocalRuntimeError, match="exited with 7") as captured:
        proposer.generate("Move normally to ZONE_B.")
    assert captured.value.to_evidence() == {
        "category": "LOCAL_RUNTIME_ERROR",
        "exit_code": 7,
        "stderr": "failed",
        "timeout_seconds": None,
    }


def test_live_observation_harness_preserves_five_linked_runs(tmp_path: Path) -> None:
    code = f"import sys; sys.stdin.read(); print({RAW_NORMAL!r}, end='')"
    scenario = load_phase2_scenario(
        Path(__file__).resolve().parents[2]
        / "phase2_scenarios"
        / "p2_01_normal_structured_movement.yaml"
    )
    results = execute_live_observations(
        proposer=fake_model(code),
        task_instruction="Move normally to ZONE_B.",
        scenario_document=scenario,
        repeat=5,
        output_dir=tmp_path,
        now=lambda: RUN_TIME,
    )
    assert len(results) == 5
    assert all(result.phase2_result is not None for result in results)
    assert all(
        result.phase2_result.phase1_result is not None for result in results
    )
    batch_dir = tmp_path / results[0].observation.batch_id
    assert len(list((batch_dir / "observations").glob("*.json"))) == 5
    assert len(list((batch_dir / "raw").glob("*.txt"))) == 5
    assert len(list((batch_dir / "provenance").glob("*.json"))) == 5
    assert len(list((batch_dir / "receipts").glob("*.json"))) == 5
