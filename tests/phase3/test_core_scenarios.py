from copy import deepcopy
import json
from pathlib import Path

import pytest

import phase3.runner as runner
from phase3.constants import SCENARIO_ORDER, VOLATILE_FIELDS
from phase3.identity import canonical_sha256
from phase3.models import WorkspaceAuthorization
from phase3.runner import CoreBoundaryError, run_scenario


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "phase3_scenarios"
SCHEMAS = ROOT / "phase3_schemas"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _core_inputs():
    registry = _json(SCENARIOS / "core_scenarios_v1.json")
    proposal_dir = SCENARIOS / "fixtures" / "proposals"
    proposals = {
        name: (proposal_dir / f"{name}.json").read_bytes()
        for name in (
            "action_valid",
            "reentry_valid",
            "duplicate_key",
            "unsupported_value",
        )
    }
    return (
        registry["cases"],
        proposals,
        _json(SCENARIOS / "fixtures" / "common_context.json"),
        _json(SCENARIOS / "fixtures" / "physical_safe.json"),
        _json(SCENARIOS / "fixtures" / "reentry_current.json"),
    )


def _verification(scenario_id: str) -> dict | None:
    if scenario_id == "P3-C-01":
        return {
            "completeness": "INCOMPLETE",
            "completeness_reason": "DECISION_RECEIPT_MISSING",
            "present_file_integrity": "INTEGRITY_VERIFIED",
            "integrity_reason": None,
            "full_set_integrity": "NOT_ESTABLISHED",
            "missing_paths": ["decision_receipt.json"],
            "mismatched_paths": [],
            "unexpected_paths": [],
        }
    if scenario_id == "P3-C-02":
        return {
            "completeness": "COMPLETE",
            "completeness_reason": None,
            "present_file_integrity": "INTEGRITY_FAILURE",
            "integrity_reason": "DECISION_RECEIPT_HASH_MISMATCH",
            "full_set_integrity": "NOT_ESTABLISHED",
            "missing_paths": [],
            "mismatched_paths": ["decision_receipt.json"],
            "unexpected_paths": [],
        }
    return None


def _authorization(tmp_path: Path) -> WorkspaceAuthorization:
    return WorkspaceAuthorization(
        authorized_workspace_root=tmp_path,
        authorization_id="OPERATOR-AUTH-TEST-001",
        protected_roots=(ROOT,),
    )


def _output_root(tmp_path: Path, scenario_id: str) -> Path:
    return (
        tmp_path
        / "phase3_evidence"
        / "session-01"
        / "batch-01"
        / scenario_id
        / "attempt-01"
    )


def test_twelve_frozen_cases_are_evaluated_once_in_fixed_order(tmp_path):
    cases, proposals, common, physical, reentry = _core_inputs()
    assert tuple(case["scenario_id"] for case in cases) == SCENARIO_ORDER
    assert len(cases) == 12

    results = {}
    for case in cases:
        verification = _verification(case["scenario_id"])
        result = run_scenario(
            case,
            proposals=proposals,
            common_context=common,
            physical_safe=physical,
            reentry_current=reentry,
            output_root=_output_root(tmp_path, case["scenario_id"]),
            workspace_authorization=_authorization(tmp_path),
            session_id="session-01",
            batch_id="batch-01",
            attempt_number=1,
            evidence_verification=verification,
        )
        results[case["scenario_id"]] = result
        identity_input = {
            key: value
            for key, value in result.items()
            if key != "decision_identity" and key not in VOLATILE_FIELDS
        }
        assert canonical_sha256(
            identity_input, exclude_volatile=False
        ) == result["decision_identity"]
        basis = result["decision_basis"]
        assert canonical_sha256(
            basis["evaluated_input"], exclude_volatile=False
        ) == basis["evaluated_input_identity"]
        assert len(result["perturbation_identity"]) == 64
        expected = case["expected"]
        assert result["adapter"]["status"] == expected["adapter"]
        assert result["final_state"] == expected["final_state"]
        if expected["adapter"] == "INVALID":
            assert result["adapter"]["reason"] == expected["reason"]
            assert result["governance"] == "NOT_PERFORMED"
            assert result["receipt_present"] is False
        else:
            assert result["governance"]["decision"] == expected["decision"]
            assert result["governance"]["reason"] == expected["reason"]
            assert result["receipt_present"] is True

    assert results["P3-CTRL-01"]["physical_result"]["execution_result"] == (
        "MOVED_TO_ZONE_B"
    )
    assert results["P3-CTRL-02"]["physical_result"] is None
    assert results["P3-CTRL-02"]["enforcement"] == "STATE_RESTORATION_ONLY"
    assert results["P3-C-01"]["verification"]["completeness"] == "INCOMPLETE"
    assert (
        results["P3-C-02"]["verification"]["present_file_integrity"]
        == "INTEGRITY_FAILURE"
    )
    assert results["P3-E-01"]["command_status"] is None
    mismatch = results["P3-E-02"]
    assert mismatch["command_status"] == "ISSUED"
    assert mismatch["physical_result"]["event"] == (
        "PHYSICAL_STATE_MISMATCH_DETECTED"
    )
    assert mismatch["physical_result"]["execution_result"] == "EFFECT_MISMATCH"
    assert mismatch["physical_result"]["command_issued_at_tick"] == 1000
    assert mismatch["physical_result"]["verification_tick"] == 1001
    assert mismatch["followup"]["decision"]["decision"] == "DENY"
    assert mismatch["followup"]["physical_action_count"] == 0
    assert results["P3-CTRL-01"]["physical_result"]["command_issued_at_tick"] == 1000
    assert results["P3-B-01"]["decision_basis"]["evaluated_input"]["context"][
        "authority"
    ]["valid_until_tick"] == 1000
    assert results["P3-D-01"]["decision_basis"]["evaluated_input"]["bundle"][
        "remediation"
    ]["observed_at_tick"] == 994
    assert "target_zone_occupancy" not in results["P3-E-01"]["decision_basis"][
        "evaluated_input"
    ]["physical_observations"]
    adapter_basis = results["P3-A-01"]["decision_basis"]
    assert adapter_basis["evaluation_stage"] == "ADAPTER"
    assert set(adapter_basis["evaluated_input"]) == {"raw_proposal_hex"}
    assert set(adapter_basis["fixture_identities"]) == {"proposal_raw_sha256"}


def test_mutated_case_is_rejected_before_adapter_or_any_downstream_stage(
    tmp_path, monkeypatch
):
    cases, proposals, common, physical, reentry = _core_inputs()
    case = deepcopy(cases[0])
    case["expected"]["reason"] = "CANDIDATE_SUPPLIED_REASON"

    def unexpected_call(*args, **kwargs):
        raise AssertionError("evaluation stage must not be called")

    for name in (
        "adapt_proposal",
        "evaluate_action",
        "execute_allowed_move",
        "evaluate_reentry",
        "apply_reentry",
    ):
        monkeypatch.setattr(runner, name, unexpected_call)

    with pytest.raises(CoreBoundaryError) as rejected:
        run_scenario(
            case,
            proposals=proposals,
            common_context=common,
            physical_safe=physical,
            reentry_current=reentry,
            output_root=_output_root(tmp_path, case["scenario_id"]),
            workspace_authorization=_authorization(tmp_path),
            session_id="session-01",
            batch_id="batch-01",
            attempt_number=1,
        )
    assert rejected.value.code == "CORE_SCENARIO_DIVERGENCE"


def test_non_nfc_hash_collision_is_rejected_before_adapter_or_downstream(
    tmp_path, monkeypatch
):
    cases, proposals, common, physical, reentry = _core_inputs()
    changed_common = deepcopy(common)
    changed_common["risk_records"][0]["source_id"] = "RIS\u212a-SOURCE-01"
    assert canonical_sha256(
        changed_common, exclude_volatile=False
    ) == canonical_sha256(common, exclude_volatile=False)

    observed_calls = []

    def unexpected_call(*args, **kwargs):
        observed_calls.append("called")
        raise AssertionError("NFC rejection must precede all later stages")

    for name in (
        "validate_output_root",
        "adapt_proposal",
        "evaluate_action",
        "execute_allowed_move",
        "evaluate_reentry",
        "apply_reentry",
    ):
        monkeypatch.setattr(runner, name, unexpected_call)

    with pytest.raises(CoreBoundaryError) as rejected:
        run_scenario(
            cases[0],
            proposals=proposals,
            common_context=changed_common,
            physical_safe=physical,
            reentry_current=reentry,
            output_root=_output_root(tmp_path, cases[0]["scenario_id"]),
            workspace_authorization=_authorization(tmp_path),
            session_id="session-01",
            batch_id="batch-01",
            attempt_number=1,
        )

    assert rejected.value.code == "CORE_SCENARIO_DIVERGENCE"
    assert "non-NFC string value" in str(rejected.value)
    assert observed_calls == []


def test_non_nfc_keys_and_values_are_rejected_across_structured_core_inputs(
    tmp_path,
):
    cases, proposals, common, physical, reentry = _core_inputs()
    c01 = next(case for case in cases if case["scenario_id"] == "P3-C-01")

    changed_case = deepcopy(cases[0])
    changed_case["\u212aey"] = "candidate"

    changed_proposals = dict(proposals)
    changed_proposals["action_valid_\u212a"] = changed_proposals.pop("action_valid")

    changed_physical = deepcopy(physical)
    changed_physical["\u212aey"] = "candidate"

    changed_reentry = deepcopy(reentry)
    changed_reentry["risk_records"][0]["source_id"] = "RIS\u212a-SOURCE-01"

    changed_verification = _verification("P3-C-01")
    assert changed_verification is not None
    changed_verification["missing_paths"][0] = "decision_receipt.\u212ason"

    variants = (
        (changed_case, proposals, common, physical, reentry, None),
        (cases[0], changed_proposals, common, physical, reentry, None),
        (cases[0], proposals, common, changed_physical, reentry, None),
        (cases[0], proposals, common, physical, changed_reentry, None),
        (c01, proposals, common, physical, reentry, changed_verification),
    )
    for (
        case_input,
        proposal_input,
        common_input,
        physical_input,
        reentry_input,
        verification_input,
    ) in variants:
        with pytest.raises(CoreBoundaryError) as rejected:
            run_scenario(
                case_input,
                proposals=proposal_input,
                common_context=common_input,
                physical_safe=physical_input,
                reentry_current=reentry_input,
                output_root=_output_root(tmp_path, case_input["scenario_id"]),
                workspace_authorization=_authorization(tmp_path),
                session_id="session-01",
                batch_id="batch-01",
                attempt_number=1,
                evidence_verification=verification_input,
            )
        assert rejected.value.code == "CORE_SCENARIO_DIVERGENCE"
        assert "non-NFC" in str(rejected.value)


def test_mutated_raw_and_baseline_fixtures_are_core_boundary_errors(tmp_path):
    cases, proposals, common, physical, reentry = _core_inputs()
    case = cases[0]
    variants = []

    changed_proposals = dict(proposals)
    changed_proposals["action_valid"] += b" "
    variants.append((changed_proposals, common, physical, reentry))

    changed_common = deepcopy(common)
    changed_common["authority"]["source_id"] = "UNTRUSTED"
    variants.append((proposals, changed_common, physical, reentry))

    changed_physical = deepcopy(physical)
    changed_physical["route_clearance"]["run_id"] = "candidate-run"
    variants.append((proposals, common, changed_physical, reentry))

    changed_reentry = deepcopy(reentry)
    changed_reentry["pre_decision_operational_state"] = None
    variants.append((proposals, common, physical, changed_reentry))

    for proposal_input, common_input, physical_input, reentry_input in variants:
        with pytest.raises(CoreBoundaryError) as rejected:
            run_scenario(
                case,
                proposals=proposal_input,
                common_context=common_input,
                physical_safe=physical_input,
                reentry_current=reentry_input,
                output_root=_output_root(tmp_path, case["scenario_id"]),
                workspace_authorization=_authorization(tmp_path),
                session_id="session-01",
                batch_id="batch-01",
                attempt_number=1,
            )
        assert rejected.value.code == "CORE_SCENARIO_DIVERGENCE"


def test_candidate_verification_and_later_caller_mutation_cannot_replace_basis(tmp_path):
    cases, proposals, common, physical, reentry = _core_inputs()
    c01 = next(case for case in cases if case["scenario_id"] == "P3-C-01")
    verification = _verification("P3-C-01")
    assert verification is not None
    verification["missing_paths"] = []
    with pytest.raises(CoreBoundaryError):
        run_scenario(
            c01,
            proposals=proposals,
            common_context=common,
            physical_safe=physical,
            reentry_current=reentry,
            output_root=_output_root(tmp_path, "P3-C-01"),
            workspace_authorization=_authorization(tmp_path),
            session_id="session-01",
            batch_id="batch-01",
            attempt_number=1,
            evidence_verification=verification,
        )

    b01 = next(case for case in cases if case["scenario_id"] == "P3-B-01")
    result = run_scenario(
        b01,
        proposals=proposals,
        common_context=common,
        physical_safe=physical,
        reentry_current=reentry,
        output_root=_output_root(tmp_path, "P3-B-01"),
        workspace_authorization=_authorization(tmp_path),
        session_id="session-01",
        batch_id="batch-01",
        attempt_number=1,
    )
    common["authority"]["source_id"] = "MUTATED_AFTER_RETURN"
    assert result["decision_basis"]["evaluated_input"]["context"]["authority"][
        "source_id"
    ] == "AUTHORITY-REGISTRY-01"


def test_result_schema_closed_volatile_properties_are_optional_and_typed():
    schema = _json(SCHEMAS / "scenario_result_v1.schema.json")
    approved_optional = {
        "formal_session_id": {"type": "string"},
        "case_batch_id": {"type": "string"},
        "run_id": {"type": "string"},
        "attempt_number": {"type": "integer"},
        "execution_timestamp": {"type": "string"},
        "absolute_evidence_path": {"type": "string"},
    }

    assert set(approved_optional) == set(VOLATILE_FIELDS)
    assert schema["additionalProperties"] is False
    assert {
        name: schema["properties"][name] for name in approved_optional
    } == approved_optional
    assert set(approved_optional).isdisjoint(schema["required"])
