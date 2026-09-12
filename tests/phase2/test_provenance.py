from __future__ import annotations

import json

import pytest

from phase2.provenance import reconstruct_phase2
from phase2.runner import run_phase2_raw
from tests.helpers import make_fixture
from tests.phase2.helpers import PROMPT_VERSION, RAW_NORMAL, RUN_TIME, model_info


def execute(raw: str):
    return run_phase2_raw(
        raw,
        make_fixture(scenario_id="provenance-test"),
        model=model_info(),
        prompt_version=PROMPT_VERSION,
        run_time=RUN_TIME,
    )


def test_valid_provenance_links_phase1_receipt() -> None:
    result = execute(RAW_NORMAL)
    assert result.phase1_result is not None
    assert (
        result.provenance.governance_receipt_id
        == result.phase1_result.receipt["receipt_id"]
    )
    assert result.provenance.governance_evaluation_status == "PERFORMED"
    assert result.provenance.enforcement_status == "PERFORMED"
    reconstructed = reconstruct_phase2(
        result.provenance.to_dict(), result.phase1_result.receipt
    )
    assert reconstructed["permission_decision"] == "ALLOW"
    assert reconstructed["raw_llm_output"] == RAW_NORMAL
    assert reconstructed["normalized_proposal"]["behavior"] == "MOVE"


def test_invalid_provenance_has_no_receipt_and_unchanged_state() -> None:
    result = execute("[]")
    assert result.phase1_result is None
    encoded = json.loads(json.dumps(result.provenance.to_dict()))
    assert encoded["parse_status"] == "INVALID"
    assert encoded["validation_reason_codes"] == [
        "LLM_OUTPUT_TOP_LEVEL_NOT_OBJECT"
    ]
    assert encoded["normalized_proposal"] is None
    assert encoded["initial_operational_state"] == encoded[
        "final_operational_state"
    ]
    assert encoded["governance_receipt_id"] is None
    reconstructed = reconstruct_phase2(encoded)
    assert reconstructed["governance_evaluation_status"] == "NOT_PERFORMED"
    assert reconstructed["permission_decision"] is None


def test_reconstruction_rejects_wrong_governance_receipt_link() -> None:
    result = execute(RAW_NORMAL)
    assert result.phase1_result is not None
    wrong = dict(result.phase1_result.receipt)
    wrong["receipt_id"] = "wrong"
    with pytest.raises(ValueError, match="receipt link"):
        reconstruct_phase2(result.provenance.to_dict(), wrong)


def test_class_a_replay_is_deterministic() -> None:
    first = execute(RAW_NORMAL)
    second = execute(RAW_NORMAL)
    assert first.adapter == second.adapter
    assert first.phase1_result == second.phase1_result
    assert first.provenance.run_id != second.provenance.run_id
    assert first.provenance.provenance_digest == second.provenance.provenance_digest


def test_provenance_is_json_serializable_and_records_required_metadata() -> None:
    record = json.loads(json.dumps(execute(RAW_NORMAL).provenance.to_dict()))
    assert record["phase"] == "P2"
    assert record["scenario_id"] == "provenance-test"
    assert record["model"]["provider"] == "local"
    assert record["model"]["sampling_parameters"] == {"temperature": 0}
    assert record["prompt_version"] == PROMPT_VERSION
    assert record["run_time"] == RUN_TIME
    assert record["run_id"].startswith("p2-")
    assert len(record["provenance_digest"]) == 64
