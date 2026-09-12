"""Post-WP03 bridge compatibility; no Phase 4 runner or Formal session."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import inspect
import json
from pathlib import Path

import pytest

from phase3.constants import PHYSICAL_CONTENT_SHA256, PHYSICAL_FIELDS
from phase3.governance import evaluate_action
from phase3.identity import canonical_sha256
from phase3.physical import PhysicalIdentityExpectation, evaluate_physical_bundle

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "phase3_scenarios" / "fixtures"
PROPOSAL = {"request_type": "ACTION", "behavior": "MOVE", "target": "ZONE_B", "speed": "NORMAL"}


def _physical():
    return json.loads((FIXTURES / "physical_safe.json").read_bytes())


def _context():
    return json.loads((FIXTURES / "common_context.json").read_bytes())


def _approved_fixture(tick):
    """Test-only approved fixture, prepared independently of later tampering."""
    records = _physical()
    approved = {}
    for name in PHYSICAL_FIELDS:
        record = records[name]
        record["observed_at_tick"] = tick
        digest = canonical_sha256(
            {"observation_name": name, "record": {k: v for k, v in record.items()
                                                if k not in {"content_identity", "content_sha256"}}},
            exclude_volatile=False)
        record["content_sha256"] = digest
        record["content_identity"] = "sha256:" + digest
        approved[name] = digest
    return records, PhysicalIdentityExpectation(approved)


def _reason(result):
    return None if result is None else (result.decision, result.reason)


class TestBridgeCompatibility:
    def test_optional_arguments_are_keyword_only_and_none_by_default(self):
        for function in (evaluate_action, evaluate_physical_bundle):
            param = inspect.signature(function).parameters["physical_identity_expectation"]
            assert param.kind is inspect.Parameter.KEYWORD_ONLY
            assert param.default is None

    @pytest.mark.parametrize("kind", ["safe", "missing", "unknown", "null", "metadata", "prohibited", "identity", "stale"])
    def test_omitted_and_explicit_none_preserve_p3(self, kind):
        records = _physical()
        if kind == "missing":
            del records["target_zone_occupancy"]
        elif kind == "unknown":
            records["route_clearance"]["value"] = "UNKNOWN"
        elif kind == "null":
            records = None
        elif kind == "metadata":
            records["route_clearance"]["source_id"] = "UNTRUSTED"
        elif kind == "prohibited":
            records["route_clearance"]["value"] = "BLOCKED"
        elif kind == "identity":
            records["route_clearance"]["content_sha256"] = "0" * 64
        elif kind == "stale":
            records["agent_actual_zone"]["observed_at_tick"] = 998
        assert evaluate_physical_bundle(records) == evaluate_physical_bundle(records, physical_identity_expectation=None)
        assert evaluate_action(PROPOSAL, _context(), records) == evaluate_action(
            PROPOSAL, _context(), records, physical_identity_expectation=None)

    def test_complete_p3_expectation_matches_default(self):
        expected = PhysicalIdentityExpectation(PHYSICAL_CONTENT_SHA256)
        assert evaluate_physical_bundle(_physical(), physical_identity_expectation=expected) is None
        assert evaluate_action(PROPOSAL, _context(), _physical(), physical_identity_expectation=expected) == evaluate_action(
            PROPOSAL, _context(), _physical())

    @pytest.mark.parametrize("tick,reason", [(998, ("HOLD", "AGENT_ACTUAL_ZONE_STALE")), (999, None), (1000, None)])
    def test_approved_timestamp_boundaries(self, tick, reason):
        records, expected = _approved_fixture(tick)
        assert _reason(evaluate_physical_bundle(records, physical_identity_expectation=expected)) == reason
        decision = evaluate_action(PROPOSAL, _context(), records, physical_identity_expectation=expected)
        assert _reason(decision) == (reason or ("ALLOW", "ALL_CURRENT_CONDITIONS_SATISFIED"))
        if tick != 1000:
            assert _reason(evaluate_physical_bundle(records)) == (
                "HOLD", "AGENT_ACTUAL_ZONE_CONTENT_IDENTITY_NOT_ESTABLISHED")

    @pytest.mark.parametrize("invalid", [{}, {"agent_actual_zone": "0" * 64}, [], None, True])
    def test_empty_incomplete_nonmapping_rejected(self, invalid):
        with pytest.raises((TypeError, ValueError)):
            PhysicalIdentityExpectation(invalid)

    @pytest.mark.parametrize("invalid", ["0" * 63, "0" * 65, "G" * 64, "A" * 64, True, None, b"0" * 64])
    def test_invalid_digest_rejected(self, invalid):
        expected = dict(PHYSICAL_CONTENT_SHA256)
        expected["route_clearance"] = invalid
        with pytest.raises(ValueError):
            PhysicalIdentityExpectation(expected)

    def test_extra_or_swapped_record_name_rejected(self):
        expected = dict(PHYSICAL_CONTENT_SHA256)
        expected["extra"] = "0" * 64
        with pytest.raises(ValueError):
            PhysicalIdentityExpectation(expected)
        expected = dict(PHYSICAL_CONTENT_SHA256)
        expected["ROUTE_CLEARANCE"] = expected.pop("route_clearance")
        with pytest.raises(ValueError):
            PhysicalIdentityExpectation(expected)

    @pytest.mark.parametrize("invalid", [{}, dict(PHYSICAL_CONTENT_SHA256), lambda *args: True])
    def test_no_mapping_or_callback_shortcut(self, invalid):
        with pytest.raises(TypeError):
            evaluate_physical_bundle(_physical(), physical_identity_expectation=invalid)
        with pytest.raises(TypeError):
            evaluate_action(PROPOSAL, _context(), _physical(), physical_identity_expectation=invalid)

    def test_expectation_is_detached_and_immutable(self):
        source = dict(PHYSICAL_CONTENT_SHA256)
        expected = PhysicalIdentityExpectation(source)
        source["agent_actual_zone"] = "0" * 64
        exported = expected.to_dict()
        exported["agent_actual_zone"] = "1" * 64
        assert expected.to_dict() == dict(PHYSICAL_CONTENT_SHA256)
        assert tuple(name for name, digest in expected.entries) == PHYSICAL_FIELDS
        with pytest.raises(FrozenInstanceError):
            expected.entries = ()
        with pytest.raises(TypeError):
            expected.entries[0] = ("agent_actual_zone", "0" * 64)

    @pytest.mark.parametrize("name", PHYSICAL_FIELDS)
    @pytest.mark.parametrize("field", ["content_sha256", "content_identity"])
    def test_bad_recorded_identity_rejected_for_every_record(self, name, field):
        records, expected = _approved_fixture(999)
        records[name][field] = "0" * 64
        assert _reason(evaluate_physical_bundle(records, physical_identity_expectation=expected)) == (
            "HOLD", name.upper() + "_CONTENT_IDENTITY_NOT_ESTABLISHED")

    @pytest.mark.parametrize("name", PHYSICAL_FIELDS)
    def test_bad_computed_identity_rejected_before_freshness(self, name):
        records, expected = _approved_fixture(999)
        records[name]["observed_at_tick"] = 998
        assert _reason(evaluate_physical_bundle(records, physical_identity_expectation=expected)) == (
            "HOLD", name.upper() + "_CONTENT_IDENTITY_NOT_ESTABLISHED")

    def test_bad_approved_map_and_hash_swap_rejected(self):
        records, expected = _approved_fixture(999)
        wrong = expected.to_dict()
        wrong["agent_actual_zone"] = "0" * 64
        assert _reason(evaluate_physical_bundle(records, physical_identity_expectation=PhysicalIdentityExpectation(wrong))) == (
            "HOLD", "AGENT_ACTUAL_ZONE_CONTENT_IDENTITY_NOT_ESTABLISHED")
        wrong = expected.to_dict()
        wrong["agent_actual_zone"], wrong["agent_motion_state"] = wrong["agent_motion_state"], wrong["agent_actual_zone"]
        assert _reason(evaluate_physical_bundle(records, physical_identity_expectation=PhysicalIdentityExpectation(wrong))) == (
            "HOLD", "AGENT_ACTUAL_ZONE_CONTENT_IDENTITY_NOT_ESTABLISHED")

    def test_record_swap_preserves_metadata_rejection(self):
        records, expected = _approved_fixture(999)
        records["route_clearance"], records["safety_interlock_status"] = (
            records["safety_interlock_status"], records["route_clearance"])
        assert _reason(evaluate_physical_bundle(records, physical_identity_expectation=expected)) == (
            "HOLD", "ROUTE_CLEARANCE_METADATA_NOT_ESTABLISHED")

    @pytest.mark.parametrize("kind,reason", [
        ("metadata", ("HOLD", "AGENT_ACTUAL_ZONE_METADATA_NOT_ESTABLISHED")),
        ("unknown", ("HOLD", "AGENT_ACTUAL_ZONE_VALUE_NOT_ESTABLISHED")),
        ("prohibited", ("DENY", "TARGET_ZONE_OCCUPANCY_EXPLICITLY_PROHIBITED")),
        ("identity", ("HOLD", "AGENT_ACTUAL_ZONE_CONTENT_IDENTITY_NOT_ESTABLISHED")),
    ])
    def test_metadata_value_identity_order_unchanged(self, kind, reason):
        records, expected = _approved_fixture(999)
        if kind == "metadata":
            records["agent_actual_zone"]["source_id"] = "UNTRUSTED"
            records["agent_actual_zone"]["value"] = "UNKNOWN"
        elif kind == "unknown":
            records["agent_actual_zone"]["value"] = "UNKNOWN"
        elif kind == "prohibited":
            records["target_zone_occupancy"]["value"] = "OCCUPIED"
        else:
            records["agent_actual_zone"]["content_sha256"] = "0" * 64
        assert _reason(evaluate_physical_bundle(records, physical_identity_expectation=expected)) == reason

    @pytest.mark.parametrize("until,reason", [
        (999, ("HOLD", "CURRENT_AUTHORITY_STALE")),
        (1000, ("HOLD", "CURRENT_AUTHORITY_STALE")),
        (1001, ("ALLOW", "ALL_CURRENT_CONDITIONS_SATISFIED")),
    ])
    def test_authority_half_open_comparator_unchanged(self, until, reason):
        context = _context()
        context["authority"]["valid_until_tick"] = until
        assert _reason(evaluate_action(PROPOSAL, context, _physical(),
                                      physical_identity_expectation=PhysicalIdentityExpectation(PHYSICAL_CONTENT_SHA256))) == reason

    @pytest.mark.parametrize("tick,reason", [
        (994, ("HOLD", "CURRENT_RISK_NOT_ESTABLISHED")),
        (995, ("ALLOW", "ALL_CURRENT_CONDITIONS_SATISFIED")),
        (996, ("ALLOW", "ALL_CURRENT_CONDITIONS_SATISFIED")),
    ])
    def test_risk_inclusive_comparator_unchanged(self, tick, reason):
        context = _context()
        context["risk_records"][0]["observed_at_tick"] = tick
        assert _reason(evaluate_action(PROPOSAL, context, _physical(),
                                      physical_identity_expectation=PhysicalIdentityExpectation(PHYSICAL_CONTENT_SHA256))) == reason

    def test_action_order_still_blocks_before_physical(self):
        records, expected = _approved_fixture(998)
        records["agent_actual_zone"]["content_sha256"] = "0" * 64
        context = _context()
        context["authority"]["valid_until_tick"] = 1000
        assert _reason(evaluate_action(PROPOSAL, context, records, physical_identity_expectation=expected)) == (
            "HOLD", "CURRENT_AUTHORITY_STALE")
        context["operational_state"] = "SUSPENDED"
        assert _reason(evaluate_action(PROPOSAL, context, records, physical_identity_expectation=expected)) == (
            "DENY", "OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY")

    def test_candidate_cannot_replace_external_expectation(self):
        approved_records, approved = _approved_fixture(999)
        candidate_records, other = _approved_fixture(1000)
        # Candidate hashes are internally valid, but not the separately supplied expectation.
        assert _reason(evaluate_physical_bundle(candidate_records, physical_identity_expectation=approved)) == (
            "HOLD", "AGENT_ACTUAL_ZONE_CONTENT_IDENTITY_NOT_ESTABLISHED")
        assert approved.to_dict() != other.to_dict()
        assert evaluate_physical_bundle(approved_records, physical_identity_expectation=approved) is None

    def test_argument_forwarded_as_same_immutable_object(self, monkeypatch):
        import phase3.governance as governance
        records, expected = _approved_fixture(999)
        seen = []
        original = governance.evaluate_physical_bundle
        def inspect_call(observations, **kwargs):
            seen.append(kwargs["physical_identity_expectation"])
            return original(observations, **kwargs)
        monkeypatch.setattr(governance, "evaluate_physical_bundle", inspect_call)
        result = governance.evaluate_action(PROPOSAL, _context(), records, physical_identity_expectation=expected)
        assert result.decision == "ALLOW"
        assert len(seen) == 1 and seen[0] is expected


# Development-only approval fixtures, separate from candidate runtime inputs.
def p4_materials():
    from phase4.contracts import frozen_cases, SPEC_SHA256, RULE_ID, SCHEMA_PATH
    from phase4.derivation import SOURCE_BINDINGS, BASELINE_SOURCES, resolve_baseline, derive_input
    from phase4.runner import ApprovedInputs
    from phase3.identity import canonical_bytes, raw_sha256
    sources={name:(ROOT/path).read_bytes() for name,(path,digest) in SOURCE_BINDINGS.items()}
    entries=[]
    for case in frozen_cases():
        selected={name:sources[name] for name in BASELINE_SOURCES[case.source_baseline_id]}
        baseline=resolve_baseline(selected,case.source_baseline_id)
        derived=derive_input(baseline,case)
        p=derived.provenance.envelope.value["provenance"]
        expectation=None
        if case.parameter_family=="PHY":
            expectation={name:derived.payload.value["physical_observations"][name]["content_sha256"] for name in PHYSICAL_FIELDS}
        entries.append({"case_id":case.case_id,"derived_input_id":case.derived_input_id,
            "source_baseline_id":case.source_baseline_id,"source_baseline_payload_sha256":baseline.payload.sha256,
            "source_materials":p["source_materials"],"payload_sha256":derived.payload.sha256,
            "wrapper_sha256":derived.provenance.envelope.value["wrapper_sha256"],
            "physical_identity_expectation":expectation})
    manifest={"schema_id":"P4-APPROVED-INPUTS-v1","frozen_spec_sha256":SPEC_SHA256,
        "derivation_rule_id":RULE_ID,"derivation_schema_sha256":raw_sha256(SCHEMA_PATH.read_bytes()),"cases":entries}
    raw=canonical_bytes(manifest,exclude_volatile=False)
    # Only this test fixture acts as the operator's approved expected hash.
    return sources,ApprovedInputs(raw,raw_sha256(raw))


def p4_prepared(case_id,sources,approved):
    from phase4.contracts import frozen_cases
    from phase4.derivation import BASELINE_SOURCES
    from phase4.runner import prepare_input
    case=next(c for c in frozen_cases() if c.case_id==case_id)
    return prepare_input(case_id,{n:sources[n] for n in BASELINE_SOURCES[case.source_baseline_id]},approved)


def p4_plan(approved,session_id="DEV-S01"):
    from phase4.contracts import CASE_PATH,SPEC_SHA256
    from phase3.identity import canonical_bytes,raw_sha256
    return canonical_bytes({"schema_id":"P4-PLAN-v1","session_id":session_id,
        "frozen_spec_sha256":SPEC_SHA256,"core_cases_sha256":raw_sha256(CASE_PATH.read_bytes()),
        "repetitions":3,"attempt_count":42,"hard_max":60,"manifest_sha256":approved.expected_raw_sha256},exclude_volatile=False)


def p4_started(tmp_path,prepared,attempt=1):
    import os
    from phase3.identity import canonical_bytes,raw_sha256
    from phase4.boundary import WorkspaceAuthorization,create_session_directory,create_attempt_directory
    from phase4.runner import initialize_attempt,load_frozen_plan
    auth=WorkspaceAuthorization(tmp_path,"DEV-WORKSPACE",(tmp_path.parent/"protected",))
    session=create_session_directory(auth,"DEV-S01")
    planraw=p4_plan(prepared.approved)
    plan=load_frozen_plan(planraw,raw_sha256(planraw))
    binding={"session_id":"DEV-S01","plan_sha256":raw_sha256(planraw),
        "human_go_sha256":"a"*64,"code_head":"b"*40,"manifest_sha256":prepared.approved.expected_raw_sha256,
        "workspace_authorization_id":auth.authorization_id,
        "ordered_slots_sha256":canonical_sha256([s.slot_id for s in plan.slots],exclude_volatile=False),
        "procedure_sha256":"c"*64,"preflight_sha256":"d"*64}
    with (session.directory.path/"session_start.json").open("xb") as f:
        f.write(canonical_bytes(binding,exclude_volatile=False));f.flush();os.fsync(f.fileno())
    boundary=create_attempt_directory(session,prepared.case.case_id,attempt)
    return initialize_attempt(prepared,boundary,binding)


class TestRunnerIntegration:
    @pytest.mark.parametrize("case_id", [
        "P4-CTRL-01","P4-CTRL-02","P4-AUTH-01","P4-AUTH-02","P4-AUTH-03",
        "P4-REM-01","P4-REM-02","P4-REM-03","P4-PHY-01","P4-PHY-02","P4-PHY-03",
        "P4-RISK-01","P4-RISK-02","P4-RISK-03"])
    def test_frozen_tuples_and_actual_validation_context(self,tmp_path,case_id,monkeypatch):
        import phase4.runner as runner
        sources,approved=p4_materials()
        prepared=p4_prepared(case_id,sources,approved)
        calls=[]
        original=runner.evaluate_reentry if prepared.case.source_baseline_id=="P3-CTRL-02" else runner.evaluate_action
        def counted(*args,**kwargs):
            calls.append(kwargs.get("physical_identity_expectation"))
            return original(*args,**kwargs)
        monkeypatch.setattr(runner,"evaluate_reentry" if prepared.case.source_baseline_id=="P3-CTRL-02" else "evaluate_action",counted)
        permit=p4_started(tmp_path,prepared)
        result=runner.evaluate_once(permit).value
        case=prepared.case
        assert (result["decision"]["decision"],result["decision"]["reason"],result["final_state"],result["effect"]) == (
            case.expected_decision,case.expected_reason,case.expected_state,case.expected_effect)
        assert len(calls)==1
        assert calls[0] is prepared.physical_expectation
        context=result["decision_basis"]["validation_context"]
        assert context["physical_identity_expectation"]==(None if prepared.physical_expectation is None else prepared.physical_expectation.to_dict())
        assert result["decision_basis"]["evaluated_input"]==prepared.verified.payload.value
        with pytest.raises(ValueError):runner.evaluate_once(permit)
        assert len(calls)==1

    def test_manifest_raw_hash_is_external_and_cannot_be_self_replaced(self):
        from phase4.runner import ApprovedInputs
        from phase3.identity import canonical_bytes
        sources,approved=p4_materials()
        doc=approved.document
        doc["cases"][0]["payload_sha256"]="0"*64
        with pytest.raises(ValueError):
            ApprovedInputs(canonical_bytes(doc,exclude_volatile=False),approved.expected_raw_sha256)

    @pytest.mark.parametrize("field",["payload_sha256","wrapper_sha256","source_baseline_payload_sha256","physical_identity_expectation"])
    def test_separately_bound_but_inconsistent_manifest_rejected(self,field):
        from phase4.runner import ApprovedInputs
        from phase3.identity import canonical_bytes,raw_sha256
        sources,approved=p4_materials()
        doc=approved.document
        entry=doc["cases"][9]
        if field=="physical_identity_expectation":entry[field]["route_clearance"]="0"*64
        else:entry[field]="0"*64
        raw=canonical_bytes(doc,exclude_volatile=False)
        other=ApprovedInputs(raw,raw_sha256(raw))
        with pytest.raises(ValueError):p4_prepared("P4-PHY-02",sources,other)

    def test_plan_exactly_three_repetitions(self):
        from phase4.runner import load_frozen_plan
        from phase3.identity import canonical_bytes,raw_sha256
        sources,approved=p4_materials()
        raw=p4_plan(approved)
        plan=load_frozen_plan(raw,raw_sha256(raw))
        assert len(plan.slots)==len({s.slot_id for s in plan.slots})==42
        doc=json.loads(raw);doc["repetitions"]=4
        raw=canonical_bytes(doc,exclude_volatile=False)
        with pytest.raises(ValueError):load_frozen_plan(raw,raw_sha256(raw))

    def test_tampered_start_marker_prevents_governance(self,tmp_path,monkeypatch):
        import phase4.runner as runner
        sources,approved=p4_materials()
        permit=p4_started(tmp_path,p4_prepared("P4-PHY-02",sources,approved))
        marker=permit.boundary.directory.path/"00_spec"/"attempt_start.json"
        marker.write_bytes(b"{}")
        monkeypatch.setattr(runner,"evaluate_action",lambda *a,**k:pytest.fail("governance called"))
        with pytest.raises(ValueError):runner.evaluate_once(permit)

    def test_exception_consumes_permit_without_retry(self,tmp_path,monkeypatch):
        import phase4.runner as runner
        sources,approved=p4_materials()
        permit=p4_started(tmp_path,p4_prepared("P4-CTRL-01",sources,approved))
        calls=[]
        def fail(*a,**k):calls.append(1);raise RuntimeError("injected")
        monkeypatch.setattr(runner,"evaluate_action",fail)
        with pytest.raises(RuntimeError):runner.evaluate_once(permit)
        with pytest.raises(ValueError):runner.evaluate_once(permit)
        assert len(calls)==1
