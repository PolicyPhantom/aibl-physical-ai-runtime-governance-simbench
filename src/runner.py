"""Offline runner for the six frozen Phase 1 scenarios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.enforcement import enforce
from src.models import (
    ActionProposal,
    EnforcementResult,
    GovernanceContext,
    PermissionDecision,
    TransitionResult,
)
from src.permission import compose_permission
from src.receipts import create_receipt, reconstruct
from src.transition import transition_state


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = PROJECT_ROOT / "scenarios"
RECEIPT_DIR = PROJECT_ROOT / "outputs" / "receipts"


@dataclass(frozen=True)
class SimulationResult:
    permission: PermissionDecision
    enforcement: EnforcementResult
    transition: TransitionResult
    receipt: dict[str, Any]


def load_scenario(path: Path) -> dict[str, Any]:
    # JSON is intentionally used as the strict, standard-library YAML subset.
    return json.loads(path.read_text(encoding="utf-8"))


def run_scenario(fixture: dict[str, Any]) -> SimulationResult:
    proposal = ActionProposal.from_dict(fixture["request"])
    context = GovernanceContext.from_dict(fixture["governance_context"])
    permission = compose_permission(proposal, context)
    enforcement = enforce(
        proposal,
        permission,
        restriction_application_supported=fixture.get(
            "restriction_application_supported", True
        ),
    )
    state_result = transition_state(proposal, context, permission, enforcement)
    receipt = create_receipt(
        fixture["scenario_id"],
        proposal,
        context,
        permission,
        enforcement,
        state_result,
    )
    return SimulationResult(permission, enforcement, state_result, receipt)


def main() -> None:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(SCENARIO_DIR.glob("scenario_*.yaml")):
        fixture = load_scenario(path)
        result = run_scenario(fixture)
        reconstruct(result.receipt)
        output = RECEIPT_DIR / f"{fixture['scenario_id']}.json"
        output.write_text(
            json.dumps(result.receipt, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"{fixture['scenario_id']}: {result.permission.decision.value} / "
            f"{result.enforcement.execution_result.value} / "
            f"{result.transition.final_state.value}"
        )


if __name__ == "__main__":
    main()
