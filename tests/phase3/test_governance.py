from copy import deepcopy
import json
from pathlib import Path

from phase3.governance import evaluate_action


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "phase3_scenarios" / "fixtures"
PROPOSAL = {
    "request_type": "ACTION",
    "behavior": "MOVE",
    "target": "ZONE_B",
    "speed": "NORMAL",
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_current_action_is_allowed():
    result = evaluate_action(
        PROPOSAL, _load("common_context.json"), _load("physical_safe.json")
    )
    assert (result.decision, result.reason) == (
        "ALLOW",
        "ALL_CURRENT_CONDITIONS_SATISFIED",
    )


def test_stale_authority_holds_without_execution():
    context = _load("common_context.json")
    context["authority"]["valid_until_tick"] = 1000
    result = evaluate_action(PROPOSAL, context, _load("physical_safe.json"))
    assert (result.decision, result.reason) == (
        "HOLD",
        "CURRENT_AUTHORITY_STALE",
    )
    assert result.physical_action_count == 0


def test_equal_rank_conflict_holds_without_selecting_prohibited_or_acceptable():
    context = _load("common_context.json")
    baseline = context["risk_records"][0]
    context["risk_records"] = [
        {
            **deepcopy(baseline),
            "risk_observation_id": "RISK-P3-ALPHA",
            "source_id": "RISK-SOURCE-ALPHA",
            "current_risk_state": "ACCEPTABLE",
        },
        {
            **deepcopy(baseline),
            "risk_observation_id": "RISK-P3-BETA",
            "source_id": "RISK-SOURCE-BETA",
            "current_risk_state": "PROHIBITED",
        },
    ]
    result = evaluate_action(PROPOSAL, context, _load("physical_safe.json"))
    assert (result.decision, result.reason) == (
        "HOLD",
        "RISK_CONTEXT_CONFLICT_UNRESOLVED",
    )


def test_ordinary_action_while_suspended_is_phase3_deny():
    context = _load("common_context.json")
    context["operational_state"] = "SUSPENDED"
    result = evaluate_action(PROPOSAL, context, _load("physical_safe.json"))
    assert (result.decision, result.reason) == (
        "DENY",
        "OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY",
    )
    assert result.physical_action_count == 0


def test_scope_mismatched_authority_holds_without_execution():
    context = _load("common_context.json")
    context["authority"]["scope_target"] = "HUMAN_ZONE"
    result = evaluate_action(PROPOSAL, context, _load("physical_safe.json"))
    assert (result.decision, result.reason) == (
        "HOLD",
        "CURRENT_AUTHORITY_NOT_APPLICABLE",
    )
    assert result.command_status is None
    assert result.physical_action_count == 0


def test_untrusted_or_incomplete_context_metadata_is_not_established():
    cases = (
        ("authority", "source_id", "UNTRUSTED", "CURRENT_AUTHORITY_NOT_ESTABLISHED"),
        ("policy", "source_id", None, "CURRENT_POLICY_NOT_ESTABLISHED"),
        ("policy", "version", "2.0", "CURRENT_POLICY_NOT_ESTABLISHED"),
        ("oversight", "max_age_ticks", 999, "CURRENT_OVERSIGHT_NOT_ESTABLISHED"),
    )
    for section, field, value, expected_reason in cases:
        context = _load("common_context.json")
        context[section][field] = value
        result = evaluate_action(PROPOSAL, context, _load("physical_safe.json"))
        assert (result.decision, result.reason) == ("HOLD", expected_reason)
        assert result.command_status is None
        assert result.physical_action_count == 0


def test_candidate_risk_rank_and_priority_rule_are_not_authoritative():
    ranked = _load("common_context.json")
    ranked["risk_records"][0]["source_authority_rank"] = 999
    ranked_result = evaluate_action(PROPOSAL, ranked, _load("physical_safe.json"))
    assert (ranked_result.decision, ranked_result.reason) == (
        "HOLD",
        "CURRENT_RISK_NOT_ESTABLISHED",
    )

    prioritized = _load("common_context.json")
    prioritized["source_priority_registry"]["rules"] = [
        {
            "scope": "MOVE / ZONE_B",
            "sources": ["RISK-SOURCE-01"],
            "selected_source": "RISK-SOURCE-01",
        }
    ]
    priority_result = evaluate_action(
        PROPOSAL, prioritized, _load("physical_safe.json")
    )
    assert (priority_result.decision, priority_result.reason) == (
        "HOLD",
        "CURRENT_RISK_NOT_ESTABLISHED",
    )
