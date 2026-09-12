"""Deterministic Phase 2 adapter-to-Phase-1 integration runner."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from phase2.adapter import AdapterResult, ParseStatus, adapt
from phase2.provenance import ModelInfo, ProvenanceRecord, create_provenance
from phase2.proposer import LocalCommandProposer, PROMPT_VERSION as LIVE_PROMPT_VERSION
from phase2.scenarios import (
    PROJECT_ROOT,
    SCENARIO_DIR,
    build_phase1_fixture,
    load_phase2_scenario,
)
from src.runner import SimulationResult, run_scenario


@dataclass(frozen=True)
class Phase2RunResult:
    adapter: AdapterResult
    provenance: ProvenanceRecord
    phase1_result: SimulationResult | None


CLASS_A_MODEL = ModelInfo(
    provider="local",
    model_name="class-a-fixture",
    runtime="deterministic-fixture",
    runtime_version="P2.0",
    sampling_parameters={"temperature": 0},
    artifact_identifier=None,
)
PROMPT_VERSION = "phase2_action_proposal_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase2"


def run_phase2_raw(
    raw_output: str,
    phase1_fixture: dict[str, Any],
    *,
    model: ModelInfo,
    prompt_version: str,
    run_time: str,
) -> Phase2RunResult:
    """Run one controlled or live raw proposal through the frozen boundary."""
    adapter_result = adapt(raw_output)
    scenario_id = phase1_fixture["scenario_id"]
    initial_state = phase1_fixture["governance_context"]["operational_state"]

    if adapter_result.parse_status == ParseStatus.INVALID:
        provenance = create_provenance(
            scenario_id=scenario_id,
            model=model,
            prompt_version=prompt_version,
            run_time=run_time,
            raw_llm_output=raw_output,
            parse_status=adapter_result.parse_status.value,
            validation_reason_codes=tuple(
                item.value for item in adapter_result.validation_reason_codes
            ),
            normalized_proposal=None,
            initial_operational_state=initial_state,
            governance_evaluation_status="NOT_PERFORMED",
            enforcement_status="NOT_PERFORMED",
            physical_action="NONE",
            final_operational_state=initial_state,
            governance_receipt_id=None,
        )
        return Phase2RunResult(adapter_result, provenance, None)

    assert adapter_result.normalized_proposal is not None
    fixture = deepcopy(phase1_fixture)
    fixture["request"] = adapter_result.normalized_proposal.to_dict()
    phase1_result = run_scenario(fixture)
    enforcement = phase1_result.enforcement
    physical_action = enforcement.action_effect or "NONE"
    provenance = create_provenance(
        scenario_id=scenario_id,
        model=model,
        prompt_version=prompt_version,
        run_time=run_time,
        raw_llm_output=raw_output,
        parse_status=adapter_result.parse_status.value,
        validation_reason_codes=(),
        normalized_proposal=adapter_result.normalized_proposal.to_dict(),
        initial_operational_state=initial_state,
        governance_evaluation_status="PERFORMED",
        enforcement_status="PERFORMED",
        physical_action=physical_action,
        final_operational_state=phase1_result.transition.final_state.value,
        governance_receipt_id=phase1_result.receipt["receipt_id"],
    )
    return Phase2RunResult(adapter_result, provenance, phase1_result)


def run_live_task(
    proposer: LocalCommandProposer,
    task_instruction: str,
    phase1_fixture: dict[str, Any],
    *,
    run_time: str,
) -> Phase2RunResult:
    """Generate one raw response locally, then apply the deterministic boundary."""
    raw_output = proposer.generate(task_instruction)
    return run_phase2_raw(
        raw_output,
        phase1_fixture,
        model=proposer.model,
        prompt_version=LIVE_PROMPT_VERSION,
        run_time=run_time,
    )


def run_class_a_document(document: dict[str, Any]) -> list[Phase2RunResult]:
    results: list[Phase2RunResult] = []
    repeats = int(document.get("deterministic_replays", 1))
    for case in document["cases"]:
        fixture = build_phase1_fixture(
            document["scenario_id"],
            case,
            evaluation_time=document["evaluation_time"],
        )
        for _ in range(repeats):
            results.append(
                run_phase2_raw(
                    case["raw_output"],
                    fixture,
                    model=CLASS_A_MODEL,
                    prompt_version=PROMPT_VERSION,
                    run_time=document["run_time"],
                )
            )
    return results


def _write_class_a_result(
    scenario_id: str, index: int, result: Phase2RunResult
) -> None:
    provenance_dir = OUTPUT_DIR / "provenance" / "class_a"
    receipt_dir = OUTPUT_DIR / "receipts" / "class_a"
    provenance_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{scenario_id.lower()}-{index:02d}"
    (provenance_dir / f"{stem}.json").write_text(
        json.dumps(result.provenance.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if result.phase1_result is not None:
        (receipt_dir / f"{stem}.json").write_text(
            json.dumps(
                result.phase1_result.receipt, indent=2, ensure_ascii=False
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> None:
    for path in sorted(SCENARIO_DIR.glob("p2_*.yaml")):
        document = load_phase2_scenario(path)
        results = run_class_a_document(document)
        for index, result in enumerate(results, start=1):
            _write_class_a_result(document["scenario_id"], index, result)
            decision = (
                result.phase1_result.permission.decision.value
                if result.phase1_result is not None
                else "NOT_PERFORMED"
            )
            print(
                f"{document['scenario_id']}[{index}]: "
                f"{result.adapter.parse_status.value} / {decision} / "
                f"{result.provenance.final_operational_state}"
            )


if __name__ == "__main__":
    main()
