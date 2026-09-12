from copy import deepcopy
from dataclasses import FrozenInstanceError
import json

import pytest

from phase3.identity import canonical_bytes, canonical_sha256
from phase4.contracts import (
    ApplicationTarget, AUTH_PATH, CASE_PATH, ContractError, DEPENDENT_PATHS,
    JsonSnapshot, PHYSICAL_PATHS, SCHEMA_PATH, case_document, frozen_cases,
    load_core_cases, parse_envelope, parse_json, validate_envelope,
)


def _envelope():
    return {
        "schema_id": "P4-DERIVED-INPUT-v1",
        "provenance": {
            "derived_input_id": "P4-DERIVED-AUTH-01",
            "source_baseline_id": "P3-CTRL-01",
            "source_baseline_payload_sha256": "1" * 64,
            "source_materials": [
                {"source_id": "action_valid", "path": "phase3_scenarios/fixtures/proposals/action_valid.json", "raw_sha256": "2" * 64},
                {"source_id": "common_context", "path": "phase3_scenarios/fixtures/common_context.json", "raw_sha256": "3" * 64},
                {"source_id": "physical_safe", "path": "phase3_scenarios/fixtures/physical_safe.json", "raw_sha256": "4" * 64},
            ],
            "derivation_rule_id": "P4-DERIVATION-RULE-v1",
            "application_targets": [{"field_path": AUTH_PATH, "old_value": 1100,
                                     "requested_new_value": 999, "semantic_change_expected": True}],
            "semantic_changed_paths": [AUTH_PATH],
            "dependent_identity_rules": [],
            "dependent_identity_changed_paths": [],
            "resulting_payload_sha256": "5" * 64,
            "parameter_family": "AUTH", "boundary_class": "STRICT_SIDE",
            "logical_evaluation_time": 1000,
        },
        "wrapper_sha256": "6" * 64,
    }


class TestSchema:
    def test_frozen_fourteen_case_document(self):
        cases = load_core_cases(CASE_PATH.read_bytes())
        assert len(cases) == 14
        assert [c.order for c in cases] == list(range(1, 15))
        assert sum(c.repetitions for c in cases) == 42
        assert [c.case_id for c in cases] == [
            "P4-CTRL-01", "P4-CTRL-02",
            "P4-AUTH-01", "P4-AUTH-02", "P4-AUTH-03",
            "P4-REM-01", "P4-REM-02", "P4-REM-03",
            "P4-PHY-01", "P4-PHY-02", "P4-PHY-03",
            "P4-RISK-01", "P4-RISK-02", "P4-RISK-03",
        ]
        assert [c.parameter_value for c in cases[2:]] == [999, 1000, 1001, 994, 995, 996, 998, 999, 1000, 994, 995, 996]
        assert [c.expected_decision for c in cases] == [
            "ALLOW", "ALLOW", "HOLD", "HOLD", "ALLOW", "HOLD", "ALLOW",
            "ALLOW", "HOLD", "ALLOW", "ALLOW", "HOLD", "ALLOW", "ALLOW"]
        assert cases[11].expected_reason == "CURRENT_RISK_NOT_ESTABLISHED"
        assert cases[8].expected_reason == "AGENT_ACTUAL_ZONE_STALE"

    @pytest.mark.parametrize("field,value", [("total_slots", 43), ("repetitions_per_case", True),
                                            ("unexpected", 1), ("claim_boundary", "PRODUCTION")])
    def test_case_contract_drift_rejected(self, field, value):
        doc = case_document()
        doc[field] = value
        with pytest.raises(ContractError):
            load_core_cases(json.dumps(doc).encode())

    def test_valid_envelope_roundtrip(self):
        envelope = _envelope()
        parsed = parse_envelope(json.dumps(envelope).encode())
        assert parsed.envelope.value == envelope
        assert len(PHYSICAL_PATHS) == 7
        assert len(DEPENDENT_PATHS) == 14

    @pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":{"y":1,"y":2}}',
                                    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e3}',
                                    b'{"x":1000.0}', b'{"x":-0}', b'{"x":01}', b'\xff'])
    def test_strict_json_rejects_ambiguous_input(self, raw):
        with pytest.raises(ContractError):
            parse_json(raw)

    @pytest.mark.parametrize("path", ["/context/authority/new_field", "../authority",
                                     "/context/../authority/valid_until_tick",
                                     "/context/authority/valid_until_tick/",
                                     "/context/authority/~1valid_until_tick",
                                     "/context/risk_records/00/observed_at_tick"])
    def test_unapproved_pointer_rejected(self, path):
        envelope = _envelope()
        envelope["provenance"]["application_targets"][0]["field_path"] = path
        with pytest.raises(ContractError):
            validate_envelope(envelope)

    @pytest.mark.parametrize("location", ["envelope", "provenance", "target", "source"])
    def test_closed_objects(self, location):
        e = _envelope()
        selected = {"envelope": e, "provenance": e["provenance"],
                    "target": e["provenance"]["application_targets"][0],
                    "source": e["provenance"]["source_materials"][0]}[location]
        selected["unapproved"] = "value"
        with pytest.raises(ContractError):
            validate_envelope(e)

    @pytest.mark.parametrize("field", ["old_value", "requested_new_value"])
    def test_bool_is_not_tick(self, field):
        e = _envelope()
        e["provenance"]["application_targets"][0][field] = True
        with pytest.raises(ContractError):
            validate_envelope(e)

    @pytest.mark.parametrize("field,value", [("parameter_family", "STRETCH"),
                                            ("boundary_class", "EXTRA"),
                                            ("logical_evaluation_time", True)])
    def test_unapproved_family_boundary_and_tick(self, field, value):
        e = _envelope()
        e["provenance"][field] = value
        with pytest.raises(ContractError):
            validate_envelope(e)

    def test_duplicate_target_path_even_with_different_data(self):
        e = _envelope()
        other = deepcopy(e["provenance"]["application_targets"][0])
        other["requested_new_value"] = 1001
        e["provenance"]["application_targets"].append(other)
        with pytest.raises(ContractError):
            validate_envelope(e)

    def test_inconsistent_semantic_flag_rejected(self):
        with pytest.raises(ContractError):
            ApplicationTarget(AUTH_PATH, 1100, 999, False)

    def test_snapshot_and_case_are_immutable(self):
        source = {"nested": [1, {"value": 2}]}
        snapshot = JsonSnapshot.of(source)
        source["nested"][1]["value"] = 3
        detached = snapshot.value
        detached["nested"].append(4)
        assert snapshot.value == {"nested": [1, {"value": 2}]}
        with pytest.raises(FrozenInstanceError):
            snapshot.raw = b"null"
        with pytest.raises(FrozenInstanceError):
            frozen_cases()[0].expected_decision = "DENY"

    def test_canonicalization_reuses_p3_without_volatile_exclusion(self):
        value = {"run_id": "retained", "text": "e\u0301", "nested": [2, 1]}
        snapshot = JsonSnapshot.of(value)
        assert snapshot.raw == canonical_bytes(value, exclude_volatile=False)
        assert snapshot.sha256 == canonical_sha256(value, exclude_volatile=False)
        assert snapshot.sha256 != canonical_sha256({"text": "é", "nested": [2, 1]}, exclude_volatile=False)

    def test_schema_explicitly_enumerates_all_dependent_paths(self):
        schema = parse_json(SCHEMA_PATH.read_bytes())
        assert schema["additionalProperties"] is False
        assert schema["$defs"]["provenance"]["additionalProperties"] is False
        assert set(schema["$defs"]["rule"]["properties"]["dependent_field_path"]["enum"]) == set(DEPENDENT_PATHS)


def _baseline(case_id):
    from pathlib import Path
    from phase4.derivation import BASELINE_SOURCES, SOURCE_BINDINGS, resolve_baseline
    root = Path(__file__).resolve().parents[2]
    sources = {name: (root / SOURCE_BINDINGS[name][0]).read_bytes()
               for name in BASELINE_SOURCES[case_id]}
    return resolve_baseline(sources, case_id)


def _derived(case_id):
    from phase4.derivation import derive_input
    case = next(c for c in frozen_cases() if c.case_id == case_id)
    baseline = _baseline(case.source_baseline_id)
    return baseline, case, derive_input(baseline, case)


def _rewrapped(value):
    from phase4.contracts import DerivedInputProvenance
    value["wrapper_sha256"] = canonical_sha256(
        {"schema_id": value["schema_id"], "provenance": value["provenance"]},
        exclude_volatile=False)
    return DerivedInputProvenance(JsonSnapshot.of(value))


class TestDerivation:
    @pytest.mark.parametrize("case_id,path,old,new", [
        ("P4-AUTH-01", AUTH_PATH, 1100, 999),
        ("P4-AUTH-02", AUTH_PATH, 1100, 1000),
        ("P4-AUTH-03", AUTH_PATH, 1100, 1001),
        ("P4-REM-01", "/bundle/remediation/observed_at_tick", 1000, 994),
        ("P4-REM-02", "/bundle/remediation/observed_at_tick", 1000, 995),
        ("P4-REM-03", "/bundle/remediation/observed_at_tick", 1000, 996),
        ("P4-RISK-01", "/context/risk_records/0/observed_at_tick", 1000, 994),
        ("P4-RISK-02", "/context/risk_records/0/observed_at_tick", 1000, 995),
        ("P4-RISK-03", "/context/risk_records/0/observed_at_tick", 1000, 996),
    ])
    def test_exact_application_and_complete_reconstruction(self, case_id, path, old, new):
        from phase4.derivation import changed_paths, verify_derivation
        baseline, case, candidate = _derived(case_id)
        p = candidate.provenance.envelope.value["provenance"]
        assert p["application_targets"] == [{"field_path": path, "old_value": old,
                                             "requested_new_value": new, "semantic_change_expected": True}]
        assert p["semantic_changed_paths"] == [path]
        assert p["dependent_identity_changed_paths"] == []
        assert changed_paths(baseline.payload.value, candidate.payload.value) == {path}
        verified = verify_derivation(baseline, candidate.provenance, candidate.payload, case)
        assert verified.payload.raw == candidate.payload.raw
        if case.parameter_family == "RISK":
            assert candidate.payload.value["context"]["risk_records"][0]["risk_observation_id"] == "RISK-P3-001"

    @pytest.mark.parametrize("case_id", ["P4-CTRL-01", "P4-CTRL-02"])
    def test_controls_retain_payload_and_separate_wrapper(self, case_id):
        from phase4.derivation import verify_derivation
        b, c, d = _derived(case_id)
        p = d.provenance.envelope.value["provenance"]
        assert d.payload.raw == b.payload.raw
        assert p["resulting_payload_sha256"] == p["source_baseline_payload_sha256"]
        assert p["application_targets"] == p["semantic_changed_paths"] == p["dependent_identity_changed_paths"] == []
        assert d.provenance.envelope.value["wrapper_sha256"] != d.payload.sha256
        verify_derivation(b, d.provenance, d.payload, c)

    @pytest.mark.parametrize("mutation", ["authority_scope", "array_order", "added_field", "removed_field",
                                        "physical_identity", "risk_id", "bool_tick"])
    def test_self_rehashed_undeclared_payload_rejected(self, mutation):
        from phase4.derivation import verify_derivation
        b, c, d = _derived("P4-AUTH-01")
        value = d.payload.value
        if mutation == "authority_scope":
            value["context"]["authority"]["scope_target"] = "HUMAN_ZONE"
        elif mutation == "array_order":
            value["context"]["authority"]["scope_request_type"].reverse()
        elif mutation == "added_field":
            value["context"]["run_id"] = "not-a-volatile-exemption"
        elif mutation == "removed_field":
            del value["context"]["policy"]
        elif mutation == "physical_identity":
            value["physical_observations"]["agent_actual_zone"]["content_sha256"] = "0" * 64
        elif mutation == "risk_id":
            value["context"]["risk_records"][0]["risk_observation_id"] = "OTHER"
        else:
            value["tick"] = True
        e = d.provenance.envelope.value
        e["provenance"]["resulting_payload_sha256"] = canonical_sha256(value, exclude_volatile=False)
        with pytest.raises(ContractError):
            verify_derivation(b, _rewrapped(e), JsonSnapshot.of(value), c)

    @pytest.mark.parametrize("field,value", [("semantic_changed_paths", []),
                                            ("source_baseline_payload_sha256", "0" * 64),
                                            ("boundary_class", "RELAXED_SIDE")])
    def test_self_rehashed_false_provenance_rejected(self, field, value):
        from phase4.derivation import verify_derivation
        b, c, d = _derived("P4-AUTH-01")
        e = d.provenance.envelope.value
        e["provenance"][field] = value
        with pytest.raises(ContractError):
            verify_derivation(b, _rewrapped(e), d.payload, c)

    def test_raw_source_identity_verified_before_decode(self):
        from phase4.derivation import resolve_baseline
        b = _baseline("P3-CTRL-01")
        sources = {m.source_id: m.raw_bytes for m in b.source_materials}
        sources["action_valid"] = b"not json"
        with pytest.raises(ContractError, match="raw identity"):
            resolve_baseline(sources, "P3-CTRL-01")

    def test_baseline_hash_alone_and_forged_snapshot_rejected(self):
        from dataclasses import replace
        from phase4.derivation import derive_input
        b, c, d = _derived("P4-RISK-01")
        with pytest.raises(ContractError):
            derive_input(b.payload.sha256, c)
        value = b.payload.value
        value["context"]["risk_records"][0]["risk_observation_id"] = "OTHER"
        forged = replace(b, payload=JsonSnapshot.of(value))
        with pytest.raises(ContractError, match="baseline snapshot"):
            derive_input(forged, c)

    def test_case_cannot_change_parameter_or_expected_result(self):
        from dataclasses import replace
        from phase4.derivation import derive_input
        b, c, d = _derived("P4-AUTH-01")
        for changed in (replace(c, parameter_value=998), replace(c, expected_decision="ALLOW")):
            with pytest.raises(ContractError):
                derive_input(b, changed)

    def test_wrapper_excludes_only_itself(self):
        from phase4.contracts import DerivedInputProvenance
        from phase4.derivation import verify_derivation
        b, c, d = _derived("P4-AUTH-01")
        e = d.provenance.envelope.value
        basis = {"schema_id": e["schema_id"], "provenance": e["provenance"]}
        assert e["wrapper_sha256"] == canonical_sha256(basis, exclude_volatile=False)
        assert e["wrapper_sha256"] != canonical_sha256(e, exclude_volatile=False)
        e["wrapper_sha256"] = "0" * 64
        with pytest.raises(ContractError, match="wrapper"):
            verify_derivation(b, DerivedInputProvenance(JsonSnapshot.of(e)), d.payload, c)


class TestPhysicalIdentityDerivation:
    @pytest.mark.parametrize("case_id,tick", [("P4-PHY-01", 998), ("P4-PHY-02", 999)])
    def test_seven_timestamps_fourteen_dependent_fields(self, case_id, tick):
        from phase3.constants import PHYSICAL_FIELDS
        from phase4.derivation import changed_paths, physical_record_sha256, verify_derivation
        b, c, d = _derived(case_id)
        p = d.provenance.envelope.value["provenance"]
        assert [t["field_path"] for t in p["application_targets"]] == list(PHYSICAL_PATHS)
        assert p["semantic_changed_paths"] == list(PHYSICAL_PATHS)
        assert set(p["dependent_identity_changed_paths"]) == set(DEPENDENT_PATHS)
        assert len(p["dependent_identity_rules"]) == 14
        assert len(changed_paths(b.payload.value, d.payload.value)) == 21
        for name in PHYSICAL_FIELDS:
            record = d.payload.value["physical_observations"][name]
            old = b.payload.value["physical_observations"][name]
            assert record["observed_at_tick"] == tick
            assert record["value"] == old["value"]
            assert record["source_id"] == old["source_id"]
            assert record["max_age_ticks"] == 1
            digest = physical_record_sha256(name, record)
            assert record["content_sha256"] == digest
            assert record["content_identity"] == "sha256:" + digest
            assert digest != old["content_sha256"]
        verify_derivation(b, d.provenance, d.payload, c)

    def test_phy03_noop_has_targets_but_no_changes(self):
        from phase4.derivation import verify_derivation
        b, c, d = _derived("P4-PHY-03")
        p = d.provenance.envelope.value["provenance"]
        assert len(p["application_targets"]) == 7
        assert all(t["old_value"] == t["requested_new_value"] == 1000 for t in p["application_targets"])
        assert p["semantic_changed_paths"] == p["dependent_identity_changed_paths"] == []
        assert b.payload.sha256 == d.payload.sha256
        assert d.provenance.envelope.value["wrapper_sha256"] != d.payload.sha256
        verify_derivation(b, d.provenance, d.payload, c)

    def test_record_hash_excludes_only_two_self_fields(self):
        from phase4.derivation import physical_record_sha256
        b, c, d = _derived("P4-PHY-02")
        record = d.payload.value["physical_observations"]["route_clearance"]
        before = physical_record_sha256("route_clearance", record)
        record["content_sha256"] = "0" * 64
        record["content_identity"] = "changed"
        assert physical_record_sha256("route_clearance", record) == before
        record["run_id"] = "not globally volatile"
        assert physical_record_sha256("route_clearance", record) != before

    @pytest.mark.parametrize("mutation", ["record_swap", "bad_recorded", "bad_computed", "partial_timestamp"])
    def test_physical_candidate_tamper_cannot_self_approve(self, mutation):
        from phase4.derivation import physical_record_sha256, verify_derivation
        b, c, d = _derived("P4-PHY-02")
        value = d.payload.value
        records = value["physical_observations"]
        if mutation == "record_swap":
            records["route_clearance"], records["safety_interlock_status"] = records["safety_interlock_status"], records["route_clearance"]
        elif mutation == "bad_recorded":
            records["route_clearance"]["content_sha256"] = "0" * 64
        elif mutation == "bad_computed":
            records["route_clearance"]["source_id"] = "OTHER"
        else:
            record = records["route_clearance"]
            record["observed_at_tick"] = 1000
            digest = physical_record_sha256("route_clearance", record)
            record["content_sha256"] = digest
            record["content_identity"] = "sha256:" + digest
        e = d.provenance.envelope.value
        e["provenance"]["resulting_payload_sha256"] = canonical_sha256(value, exclude_volatile=False)
        with pytest.raises(ContractError):
            verify_derivation(b, _rewrapped(e), JsonSnapshot.of(value), c)
