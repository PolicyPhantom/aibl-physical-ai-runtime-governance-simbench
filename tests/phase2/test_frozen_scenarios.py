from __future__ import annotations

from pathlib import Path

import pytest

from phase2.runner import run_class_a_document
from phase2.scenarios import load_phase2_scenario


SCENARIO_DIR = Path(__file__).resolve().parents[2] / "phase2_scenarios"
SCENARIO_PATHS = sorted(SCENARIO_DIR.glob("p2_*.yaml"))


@pytest.mark.parametrize("path", SCENARIO_PATHS, ids=lambda path: path.stem)
def test_frozen_phase2_scenario(path: Path) -> None:
    document = load_phase2_scenario(path)
    results = run_class_a_document(document)
    repeats = int(document.get("deterministic_replays", 1))
    expected_sequence = [
        case["expected"] for case in document["cases"] for _ in range(repeats)
    ]
    assert len(results) == len(expected_sequence)

    for result, expected in zip(results, expected_sequence, strict=True):
        assert result.adapter.parse_status.value == expected["parse_status"]
        if expected["parse_status"] == "INVALID":
            assert result.phase1_result is None
            assert list(result.provenance.validation_reason_codes) == expected[
                "validation_reason_codes"
            ]
            assert (
                result.provenance.governance_evaluation_status
                == expected["governance_evaluation_status"]
            )
            assert result.provenance.final_operational_state == expected["final_state"]
        else:
            assert result.phase1_result is not None
            receipt = result.phase1_result.receipt
            assert receipt["decision"] == expected["decision"]
            assert receipt["reason_codes"] == expected["reason_codes"]
            assert receipt["execution_result"] == expected["execution_result"]
            assert receipt["final_state"] == expected["final_state"]

    if document.get("deterministic_replays"):
        assert results[0].adapter == results[1].adapter
        assert results[0].phase1_result == results[1].phase1_result
        assert (
            results[0].provenance.provenance_digest
            == results[1].provenance.provenance_digest
        )
        assert results[0].provenance.run_id != results[1].provenance.run_id


def test_exactly_ten_frozen_phase2_scenario_documents_exist() -> None:
    assert len(SCENARIO_PATHS) == 10
