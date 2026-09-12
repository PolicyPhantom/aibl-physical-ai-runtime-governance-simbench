from phase3.context import (
    assemble_risk,
    authority_applicable,
    interval_current,
    observation_age,
    observation_current,
    oversight_applicable,
    policy_applicable,
    proposal_scope,
)


PROPOSAL = {
    "request_type": "ACTION",
    "behavior": "MOVE",
    "target": "ZONE_B",
    "speed": "NORMAL",
}

RISK_OBSERVATION_IDS = {
    "RISK-SOURCE-01": "RISK-P3-001",
    "RISK-SOURCE-ALPHA": "RISK-P3-ALPHA",
    "RISK-SOURCE-BETA": "RISK-P3-BETA",
}


def _registry() -> dict:
    return {
        "registry_id": "P3-SOURCE-PRIORITY-REGISTRY-v1",
        "version": "1.0",
        "rules": [],
    }


def _risk(source: str, value: str, rank: int = 10) -> dict:
    return {
        "risk_observation_id": RISK_OBSERVATION_IDS[source],
        "current_risk_state": value,
        "observed_at_tick": 1000,
        "max_age_ticks": 5,
        "source_id": source,
        "source_authority_rank": rank,
        "scope": "MOVE / ZONE_B",
    }


def test_half_open_interval_expires_at_upper_bound():
    record = {
        "valid_from_tick": 900,
        "valid_until_tick": 1000,
        "revoked": False,
        "superseded_by": None,
    }
    assert interval_current(
        record, "valid_from_tick", "valid_until_tick", tick=999
    )
    assert not interval_current(
        record, "valid_from_tick", "valid_until_tick", tick=1000
    )


def test_domain_age_boundary_is_inclusive_and_future_is_invalid():
    current = {"observed_at_tick": 995, "max_age_ticks": 5}
    stale = {"observed_at_tick": 994, "max_age_ticks": 5}
    future = {"observed_at_tick": 1001, "max_age_ticks": 5}
    assert observation_age(current) == 5
    assert observation_current(current)
    assert not observation_current(stale)
    assert not observation_current(future)


def test_equal_authority_risk_conflict_is_not_silently_selected():
    result = assemble_risk(
        [
            _risk("RISK-SOURCE-ALPHA", "ACCEPTABLE"),
            _risk("RISK-SOURCE-BETA", "PROHIBITED"),
        ],
        _registry(),
    )
    assert result["status"] == "CONFLICT_UNRESOLVED"
    assert result["value"] is None
    assert result["sources"] == [
        "RISK-SOURCE-ALPHA",
        "RISK-SOURCE-BETA",
    ]


def test_authority_policy_and_oversight_are_bound_to_the_exact_request_scope():
    authority = {
        "scope_request_type": ["ACTION", "REENTRY"],
        "scope_behavior": "MOVE",
        "scope_target": "ZONE_B",
    }
    policy = {
        "version": "1.0",
        "applicable_behavior": "MOVE",
        "applicable_target": "ZONE_B",
    }
    oversight = {"scope": "MOVE / ZONE_B"}

    assert proposal_scope(PROPOSAL) == "MOVE / ZONE_B"
    assert authority_applicable(authority, PROPOSAL)
    assert policy_applicable(policy, PROPOSAL)
    assert oversight_applicable(oversight, PROPOSAL)
    assert not authority_applicable(
        {**authority, "scope_target": "HUMAN_ZONE"}, PROPOSAL
    )
    assert not policy_applicable(
        {**policy, "version": "2.0"}, PROPOSAL
    )
    assert not oversight_applicable(
        {"scope": "MOVE / HUMAN_ZONE"}, PROPOSAL
    )


def test_risk_metadata_cannot_supply_rank_ttl_or_source_contract():
    baseline = _risk("RISK-SOURCE-01", "ACCEPTABLE")
    for field, value in (
        ("source_authority_rank", 99),
        ("max_age_ticks", 999),
        ("source_id", "UNTRUSTED-SOURCE"),
    ):
        record = dict(baseline)
        record[field] = value
        result = assemble_risk([record], _registry())
        assert result == {
            "status": "NOT_ESTABLISHED",
            "value": None,
            "sources": [],
        }


def test_nonempty_candidate_priority_registry_is_not_trusted():
    registry = _registry()
    registry["rules"] = [
        {
            "scope": "MOVE / ZONE_B",
            "sources": ["RISK-SOURCE-ALPHA", "RISK-SOURCE-BETA"],
            "selected_source": "RISK-SOURCE-ALPHA",
        }
    ]
    result = assemble_risk(
        [
            _risk("RISK-SOURCE-ALPHA", "ACCEPTABLE"),
            _risk("RISK-SOURCE-BETA", "PROHIBITED"),
        ],
        registry,
    )
    assert result["status"] == "NOT_ESTABLISHED"
    assert result["value"] is None
