from __future__ import annotations

from copy import deepcopy
from typing import Any


def make_fixture(
    *,
    scenario_id: str = "supplemental",
    request: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    restriction_application_supported: bool = True,
) -> dict[str, Any]:
    fixture: dict[str, Any] = {
        "scenario_id": scenario_id,
        "request": {
            "request_type": "ACTION",
            "behavior": "MOVE",
            "target": "ZONE_B",
            "speed": "NORMAL",
        },
        "governance_context": {
            "evaluation_time": "2026-08-27T15:00:00+09:00",
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
        },
        "restriction_application_supported": restriction_application_supported,
    }
    fixture = deepcopy(fixture)
    if request:
        fixture["request"].update(request)
    if context:
        fixture["governance_context"].update(context)
    return fixture

