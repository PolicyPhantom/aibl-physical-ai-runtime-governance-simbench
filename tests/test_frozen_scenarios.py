from __future__ import annotations

from pathlib import Path

import pytest

from src.runner import load_scenario, run_scenario


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios"
SCENARIOS = sorted(SCENARIO_DIR.glob("scenario_*.yaml"))


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda path: path.stem)
def test_frozen_scenario(path: Path) -> None:
    fixture = load_scenario(path)
    result = run_scenario(fixture)
    expected = fixture["expected"]

    assert result.permission.decision.value == expected["decision"]
    assert [code.value for code in result.permission.reason_codes] == expected[
        "reason_codes"
    ]
    assert [dict(item) for item in result.permission.restrictions] == expected[
        "restrictions"
    ]
    assert result.enforcement.execution_result.value == expected["execution_result"]
    assert result.transition.final_state.value == expected["final_state"]
    assert result.receipt["evaluation_time"] == "2026-08-27T15:00:00+09:00"
    assert result.receipt["rule_version"] == "P1.0"

    if "applied_speed" in expected:
        assert result.enforcement.executed_request is not None
        assert result.enforcement.executed_request["speed"] == expected["applied_speed"]


def test_exactly_six_frozen_scenarios_exist() -> None:
    assert len(SCENARIOS) == 6

