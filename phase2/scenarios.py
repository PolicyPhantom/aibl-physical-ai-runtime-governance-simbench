"""Minimal deterministic fixture support for the ten frozen Phase 2 scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = PROJECT_ROOT / "phase2_scenarios"


def load_phase2_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_phase1_fixture(
    scenario_id: str,
    case: dict[str, Any],
    *,
    evaluation_time: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "evaluation_time": evaluation_time,
        "assurance_status": "CURRENT",
        "authority_status": "VALID",
        "policy_status": "APPLICABLE",
        "evidence_status": "CURRENT",
        "operating_condition": "NORMAL",
        "risk_state": "NORMAL",
        "oversight_status": "AVAILABLE",
        "behavior_scope": ["MOVE"],
        "behavior_scope_status": "KNOWN",
        "operational_state": "RUNNING",
        "policy_version": "P1.0",
        "human_zone_prohibited": False,
    }
    context.update(case.get("governance_context_overrides", {}))
    return {
        "scenario_id": f"{scenario_id}--{case['case_id']}",
        # The adapter replaces this sentinel before Phase 1 is called.
        "request": {
            "request_type": "ACTION",
            "behavior": "MOVE",
            "target": "ZONE_B",
            "speed": "NORMAL",
        },
        "governance_context": context,
        "restriction_application_supported": case.get(
            "restriction_application_supported", True
        ),
    }

