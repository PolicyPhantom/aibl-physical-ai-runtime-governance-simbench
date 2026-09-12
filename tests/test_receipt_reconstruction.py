from __future__ import annotations

import json
from pathlib import Path

from src.receipts import reconstruct
from src.runner import load_scenario, run_scenario
from tests.helpers import make_fixture


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios"


def test_every_frozen_request_emits_json_serializable_receipt() -> None:
    for path in sorted(SCENARIO_DIR.glob("scenario_*.yaml")):
        result = run_scenario(load_scenario(path))
        encoded = json.dumps(result.receipt, sort_keys=True)
        decoded = json.loads(encoded)
        assert decoded["receipt_id"].startswith("p1-")
        assert decoded["scenario_id"] == path.stem


def test_receipt_only_reconstruction_answers_frozen_questions() -> None:
    result = run_scenario(make_fixture())
    reconstructed = reconstruct(json.loads(json.dumps(result.receipt)))
    assert reconstructed == {
        "requested_behavior": "MOVE",
        "request": {
            "request_type": "ACTION",
            "behavior": "MOVE",
            "target": "ZONE_B",
            "speed": "NORMAL",
        },
        "initial_operational_state": "RUNNING",
        "rule_version": "P1.0",
        "authority_status": "VALID",
        "evidence_status": "CURRENT",
        "operating_condition": "NORMAL",
        "risk_state": "NORMAL",
        "permission_decision": "ALLOW",
        "reason_codes": ["ALL_CURRENT_CONDITIONS_SATISFIED"],
        "restrictions": [],
        "enforcement_result": "EXECUTED",
        "applied_restrictions": [],
        "reentry_outcome": None,
        "final_state": "RUNNING",
    }


def test_restricted_reentry_reconstructs_without_runtime_memory() -> None:
    result = run_scenario(
        make_fixture(
            request={"request_type": "REENTRY", "speed": "HIGH"},
            context={
                "operational_state": "SUSPENDED",
                "operating_condition": "LOW_SPEED_ONLY",
            },
        )
    )
    reconstructed = reconstruct(json.loads(json.dumps(result.receipt)))
    assert reconstructed["permission_decision"] == "RESTRICT"
    assert reconstructed["reason_codes"] == [
        "SPEED_RESTRICTION_REQUIRED",
        "REENTRY_REVALIDATION_PASSED",
    ]
    assert reconstructed["applied_restrictions"]
    assert reconstructed["reentry_outcome"] == "SUCCESS"
    assert reconstructed["final_state"] == "RUNNING"


def test_failed_restricted_reentry_reconstructs_without_runtime_memory() -> None:
    result = run_scenario(
        make_fixture(
            request={"request_type": "REENTRY", "speed": "HIGH"},
            context={
                "operational_state": "SUSPENDED",
                "operating_condition": "LOW_SPEED_ONLY",
            },
            restriction_application_supported=False,
        )
    )
    reconstructed = reconstruct(json.loads(json.dumps(result.receipt)))
    assert reconstructed["permission_decision"] == "RESTRICT"
    assert reconstructed["reason_codes"] == [
        "SPEED_RESTRICTION_REQUIRED",
        "REENTRY_REVALIDATION_FAILED",
    ]
    assert reconstructed["enforcement_result"] == "HELD"
    assert reconstructed["applied_restrictions"] == []
    assert reconstructed["reentry_outcome"] == "FAILED"
    assert reconstructed["final_state"] == "SUSPENDED"


def test_identical_inputs_produce_identical_complete_results() -> None:
    fixture = make_fixture(scenario_id="determinism")
    first = run_scenario(fixture)
    second = run_scenario(fixture)
    assert first.permission == second.permission
    assert first.enforcement == second.enforcement
    assert first.transition == second.transition
    assert first.receipt == second.receipt
