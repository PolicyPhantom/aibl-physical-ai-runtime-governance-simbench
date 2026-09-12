from __future__ import annotations

import json
from pathlib import Path
import sys

from phase2.live_runner import InvocationStatus, execute_live_observations
from phase2.proposer import LocalCommandProposer
from phase2.provenance import ModelInfo
from phase2.scenarios import load_phase2_scenario
from tests.phase2.helpers import RAW_NORMAL, RUN_TIME


def subprocess_model(command_code: str) -> LocalCommandProposer:
    return LocalCommandProposer(
        command=(sys.executable, "-B", "-c", command_code),
        model=ModelInfo(
            provider="local",
            model_name="utf8-boundary-fixture",
            runtime="python-subprocess-fixture",
            runtime_version=sys.version.split()[0],
            sampling_parameters={"temperature": 0},
            artifact_identifier=None,
        ),
        timeout_seconds=10,
    )


def test_invalid_utf8_stdout_is_failed_attempt_and_later_attempt_continues(
    tmp_path: Path,
) -> None:
    counter = tmp_path / "attempt-counter.txt"
    command_code = (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.stdin.buffer.read()\n"
        f"path = Path({str(counter)!r})\n"
        "attempt = int(path.read_text(encoding='utf-8')) if path.exists() else 0\n"
        "path.write_text(str(attempt + 1), encoding='utf-8')\n"
        "if attempt == 0:\n"
        "    sys.stdout.buffer.write(b'\\xff')\n"
        "else:\n"
        f"    sys.stdout.write({RAW_NORMAL!r})\n"
    )
    scenario = load_phase2_scenario(
        Path(__file__).resolve().parents[2]
        / "phase2_scenarios"
        / "p2_01_normal_structured_movement.yaml"
    )

    attempts = execute_live_observations(
        proposer=subprocess_model(command_code),
        task_instruction="Move normally to ZONE_B.",
        scenario_document=scenario,
        repeat=2,
        output_dir=tmp_path / "live",
        now=lambda: RUN_TIME,
    )

    failed, continued = attempts
    batch_dir = failed.observation_path.parents[1]
    assert failed.observation.invocation_status == InvocationStatus.INVOCATION_FAILED
    assert failed.observation.error == {
        "category": "LOCAL_RUNTIME_DECODE_ERROR",
        "exit_code": None,
        "stderr": None,
        "timeout_seconds": None,
    }
    assert failed.observation.raw_output_path is None
    assert failed.observation.phase2_provenance_path is None
    assert failed.observation.governance_receipt_id is None
    assert failed.phase2_result is None
    assert failed.observation_path.exists()

    saved_failure = json.loads(
        failed.observation_path.read_text(encoding="utf-8")
    )
    assert saved_failure["invocation_status"] == "INVOCATION_FAILED"
    assert saved_failure["error"]["category"] == "LOCAL_RUNTIME_DECODE_ERROR"

    assert continued.observation.attempt_index == 2
    assert continued.observation.invocation_status == InvocationStatus.COMPLETED
    assert continued.phase2_result is not None
    assert continued.phase2_result.phase1_result is not None
    assert len(list((batch_dir / "observations").glob("*.json"))) == 2
    assert len(list((batch_dir / "raw").glob("*.txt"))) == 1
    assert len(list((batch_dir / "provenance").glob("*.json"))) == 1
    assert len(list((batch_dir / "receipts").glob("*.json"))) == 1
