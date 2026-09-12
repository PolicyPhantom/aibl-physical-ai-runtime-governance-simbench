"""Formal-compatible Class B runner wired only from the frozen configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from phase2.class_b_config import (
    ClassBConfig,
    FROZEN_CLASS_B_CONFIG,
    structured_output_recovery_config,
)
from phase2.live_runner import InvocationStatus, execute_live_observations
from phase2.proposer import LocalCommandProposer
from phase2.scenarios import load_phase2_scenario


def build_frozen_proposer(
    config: ClassBConfig = FROZEN_CLASS_B_CONFIG,
) -> LocalCommandProposer:
    command = [sys.executable, "-B", "-m", "phase2.lmstudio_bridge"]
    if config.structured_output is not None:
        command.extend(
            [
                "--structured-output-recovery",
                "--expected-schema-sha256",
                config.structured_output.schema_sha256,
            ]
        )
    return LocalCommandProposer(
        command=tuple(command),
        model=config.model_info(),
        timeout_seconds=config.process_timeout_seconds,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run frozen Phase 2 Class B observations through LM Studio."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument(
        "--structured-output-recovery",
        action="store_true",
        help="Use the frozen Structured-Output Recovery request condition.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/phase2/live")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    config = (
        structured_output_recovery_config()
        if args.structured_output_recovery
        else FROZEN_CLASS_B_CONFIG
    )
    scenario_document = load_phase2_scenario(args.scenario)
    results = execute_live_observations(
        proposer=build_frozen_proposer(config),
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
