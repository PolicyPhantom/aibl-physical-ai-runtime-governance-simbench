"""CLI and harness for observations from an already-configured local model."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Sequence
import uuid

from phase2.proposer import (
    LocalCommandProposer,
    LocalRuntimeError,
    PROMPT_VERSION,
    render_prompt,
)
from phase2.provenance import ModelInfo, create_run_id
from phase2.runner import Phase2RunResult, run_phase2_raw
from phase2.scenarios import build_phase1_fixture, load_phase2_scenario


class InvocationStatus(StrEnum):
    COMPLETED = "COMPLETED"
    INVOCATION_FAILED = "INVOCATION_FAILED"


@dataclass(frozen=True)
class LiveObservationRecord:
    phase: str
    observation_class: str
    batch_id: str
    attempt_index: int
    run_id: str
    prompt_version: str
    task_instruction: str
    rendered_prompt_sha256: str
    model: ModelInfo
    invocation_status: InvocationStatus
    raw_output_path: str | None
    phase2_provenance_path: str | None
    governance_receipt_id: str | None
    error: dict[str, Any] | None
    equivalence_identity: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["model"] = self.model.to_dict()
        result["invocation_status"] = self.invocation_status.value
        if self.equivalence_identity is None:
            result.pop("equivalence_identity")
        return result


@dataclass(frozen=True)
class LiveAttemptResult:
    observation: LiveObservationRecord
    observation_path: Path
    phase2_result: Phase2RunResult | None


def create_batch_id() -> str:
    """Return an offline-unique identity for one live harness execution."""
    return "p2b-" + uuid.uuid4().hex


def _relative_artifact_path(path: Path, batch_dir: Path) -> str:
    return path.relative_to(batch_dir).as_posix()


def _write_new(path: Path, content: str) -> None:
    """Create one evidence artifact and fail explicitly on any collision."""
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)


def _structured_output_equivalence_identity(
    *,
    scenario_id: str,
    task_instruction: str,
    rendered_prompt_sha256: str,
    model: ModelInfo,
) -> dict[str, Any] | None:
    if model.response_format_type is None:
        return None
    required = {
        "protocol_version": model.protocol_version,
        "endpoint": model.endpoint,
        "api_route": model.api_route,
        "artifact_identifier": model.artifact_identifier,
        "quantization": model.quantization,
        "omitted_parameters": model.omitted_parameters,
        "schema_identifier": model.schema_identifier,
        "schema_path": model.schema_path,
        "schema_sha256": model.schema_sha256,
    }
    missing = sorted(key for key, value in required.items() if value is None)
    if missing:
        raise ValueError(
            "structured-output equivalence identity is incomplete: "
            + ", ".join(missing)
        )
    return {
        "protocol_version": model.protocol_version,
        "scenario_id": scenario_id,
        "task_instruction": task_instruction,
        "prompt_version": PROMPT_VERSION,
        "rendered_prompt_sha256": rendered_prompt_sha256,
        "model": {
            "provider": model.provider,
            "model_name": model.model_name,
            "runtime": model.runtime,
            "runtime_version": model.runtime_version,
            "artifact_identifier": model.artifact_identifier,
            "quantization": model.quantization,
        },
        "transport": {
            "endpoint": model.endpoint,
            "api_route": model.api_route,
        },
        "sampling_parameters": model.sampling_parameters,
        "omitted_parameters": model.omitted_parameters,
        "response_format": {
            "type": model.response_format_type,
            "schema_identifier": model.schema_identifier,
            "schema_path": model.schema_path,
            "schema_sha256": model.schema_sha256,
        },
    }


def execute_live_observations(
    *,
    proposer: LocalCommandProposer,
    task_instruction: str,
    scenario_document: dict,
    repeat: int,
    output_dir: Path,
    now: Callable[[], str] | None = None,
) -> list[LiveAttemptResult]:
    if repeat < 1:
        raise ValueError("repeat must be at least one")
    clock = now or (lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    case = scenario_document["cases"][0]
    fixture = build_phase1_fixture(
        scenario_document["scenario_id"],
        case,
        evaluation_time=scenario_document["evaluation_time"],
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_id = create_batch_id()
    batch_dir = output_dir / batch_id
    batch_dir.mkdir(exist_ok=False)
    observation_dir = batch_dir / "observations"
    raw_dir = batch_dir / "raw"
    provenance_dir = batch_dir / "provenance"
    receipt_dir = batch_dir / "receipts"
    for directory in (observation_dir, raw_dir, provenance_dir, receipt_dir):
        directory.mkdir()

    rendered_prompt = render_prompt(task_instruction)
    rendered_prompt_sha256 = hashlib.sha256(
        rendered_prompt.encode("utf-8")
    ).hexdigest()
    equivalence_identity = _structured_output_equivalence_identity(
        scenario_id=scenario_document["scenario_id"],
        task_instruction=task_instruction,
        rendered_prompt_sha256=rendered_prompt_sha256,
        model=proposer.model,
    )

    results: list[LiveAttemptResult] = []
    for index in range(1, repeat + 1):
        try:
            raw_output = proposer.generate_rendered_prompt(rendered_prompt)
        except LocalRuntimeError as exc:
            run_id = create_run_id()
            stem = f"attempt-{index:04d}-{run_id}"
            observation = LiveObservationRecord(
                phase="P2",
                observation_class="B",
                batch_id=batch_id,
                attempt_index=index,
                run_id=run_id,
                prompt_version=PROMPT_VERSION,
                task_instruction=task_instruction,
                rendered_prompt_sha256=rendered_prompt_sha256,
                model=proposer.model,
                invocation_status=InvocationStatus.INVOCATION_FAILED,
                raw_output_path=None,
                phase2_provenance_path=None,
                governance_receipt_id=None,
                error=exc.to_evidence(),
                equivalence_identity=equivalence_identity,
            )
            observation_path = observation_dir / f"{stem}.json"
            _write_new(
                observation_path,
                json.dumps(observation.to_dict(), indent=2, ensure_ascii=False)
                + "\n",
            )
            results.append(LiveAttemptResult(observation, observation_path, None))
            continue

        result = run_phase2_raw(
            raw_output,
            fixture,
            model=proposer.model,
            prompt_version=PROMPT_VERSION,
            run_time=clock(),
        )
        run_id = result.provenance.run_id
        stem = f"attempt-{index:04d}-{run_id}"
        raw_path = raw_dir / f"{stem}.txt"
        provenance_path = provenance_dir / f"{stem}.json"
        _write_new(raw_path, raw_output)
        _write_new(
            provenance_path,
            json.dumps(result.provenance.to_dict(), indent=2, ensure_ascii=False)
            + "\n",
        )
        if result.phase1_result is not None:
            _write_new(
                receipt_dir / f"{stem}.json",
                json.dumps(
                    result.phase1_result.receipt, indent=2, ensure_ascii=False
                )
                + "\n",
            )
        observation = LiveObservationRecord(
            phase="P2",
            observation_class="B",
            batch_id=batch_id,
            attempt_index=index,
            run_id=run_id,
            prompt_version=PROMPT_VERSION,
            task_instruction=task_instruction,
            rendered_prompt_sha256=rendered_prompt_sha256,
            model=proposer.model,
            invocation_status=InvocationStatus.COMPLETED,
            raw_output_path=_relative_artifact_path(raw_path, batch_dir),
            phase2_provenance_path=_relative_artifact_path(
                provenance_path, batch_dir
            ),
            governance_receipt_id=(
                result.phase1_result.receipt["receipt_id"]
                if result.phase1_result is not None
                else None
            ),
            error=None,
            equivalence_identity=equivalence_identity,
        )
        observation_path = observation_dir / f"{stem}.json"
        _write_new(
            observation_path,
            json.dumps(observation.to_dict(), indent=2, ensure_ascii=False) + "\n",
        )
        results.append(LiveAttemptResult(observation, observation_path, result))
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Phase 2 observations through an existing local CLI model."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--runtime-version", required=True)
    parser.add_argument("--artifact-identifier")
    parser.add_argument("--sampling-json", default="{}")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/phase2/live"))
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Local command after --; it must read stdin and write raw output to stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    command = tuple(args.command[1:] if args.command[:1] == ["--"] else args.command)
    if not command:
        raise SystemExit("a local runtime command is required after --")
    sampling = json.loads(args.sampling_json)
    if not isinstance(sampling, dict):
        raise SystemExit("--sampling-json must decode to an object")
    proposer = LocalCommandProposer(
        command=command,
        model=ModelInfo(
            provider="local",
            model_name=args.model_name,
            runtime=args.runtime,
            runtime_version=args.runtime_version,
            sampling_parameters=sampling,
            artifact_identifier=args.artifact_identifier,
        ),
    )
    scenario_document = load_phase2_scenario(args.scenario)
    results = execute_live_observations(
        proposer=proposer,
        task_instruction=args.task,
        scenario_document=scenario_document,
        repeat=args.repeat,
        output_dir=args.output_dir,
    )
    completed = sum(
        result.observation.invocation_status == InvocationStatus.COMPLETED
        for result in results
    )
    failed = len(results) - completed
    valid = sum(
        result.phase2_result is not None
        and result.phase2_result.phase1_result is not None
        for result in results
    )
    invalid = completed - valid
    print(
        f"batch_id={results[0].observation.batch_id} attempts={len(results)} "
        f"completed={completed} invocation_failed={failed} "
        f"valid={valid} invalid={invalid}"
    )
    if scenario_document["scenario_id"] == "P2-10":
        status = "MET" if completed >= 5 else "NOT_YET_MET"
        print(f"p2_10_minimum_live_generation_requirement={status}")


if __name__ == "__main__":
    main()
