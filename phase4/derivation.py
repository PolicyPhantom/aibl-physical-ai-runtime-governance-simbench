"""Exact frozen input derivation and reconstruction, without governance calls.

Candidate identities are not approvals. The later runner must bind a separately
approved manifest before supplying any PhysicalIdentityExpectation.
"""
from __future__ import annotations

from dataclasses import asdict
from types import MappingProxyType
from typing import Mapping

from phase3.adapter import adapt_proposal
from phase3.constants import BASELINE_FIXTURE_SHA256, PHYSICAL_FIELDS, PROPOSAL_RAW_SHA256
from phase3.identity import canonical_bytes, canonical_sha256, raw_sha256
from .contracts import (
    ApplicationTarget, AUTH_PATH, BaselineSnapshot, ContractError, DEPENDENT_PATHS,
    DependentIdentityRule, DerivedInput, DerivedInputProvenance, JsonSnapshot,
    P4CaseSpec, PHYSICAL_PATHS, RECORD_RULE_ID, REM_PATH, RISK_PATH, RULE_ID,
    SCHEMA_ID, SourceMaterial, VerifiedDerivedInput, frozen_cases, parse_json,
)

# Exact raw identities of the committed source files at the frozen base HEAD.
# Fixture canonical identities remain the existing phase3 constants.
SOURCE_BINDINGS = MappingProxyType({
    "action_valid": ("phase3_scenarios/fixtures/proposals/action_valid.json",
                     "ba08aa8d968150679a5ed8344064058838d070dad2e9affe606f1bde25ee8645"),
    "reentry_valid": ("phase3_scenarios/fixtures/proposals/reentry_valid.json",
                      "66ab67ddf6e7de124d5585c65470f7c8d3f31d069d0cc860c8125c1af0aba044"),
    "common_context": ("phase3_scenarios/fixtures/common_context.json",
                       "050c9283f4940fe998e38700184c71006bb3b191a3b37e2848ec24ad0a06ac59"),
    "physical_safe": ("phase3_scenarios/fixtures/physical_safe.json",
                      "0925daaf06af13e049db2de8103282cca05342f8d49cb64aebfd08dcc5244c3b"),
    "reentry_current": ("phase3_scenarios/fixtures/reentry_current.json",
                        "7765e61a26446b61e054e607f62b9e620fb893539d1200d3fe12d140961ed1c6"),
})
BASELINE_SOURCES = MappingProxyType({
    "P3-CTRL-01": ("action_valid", "common_context", "physical_safe"),
    "P3-CTRL-02": ("reentry_valid", "reentry_current"),
})


def resolve_baseline(source_bytes: Mapping[str, bytes], source_baseline_id: str) -> BaselineSnapshot:
    """Verify raw source identities before decoding or building a baseline."""
    if source_baseline_id not in BASELINE_SOURCES:
        raise ContractError("unapproved source baseline")
    required = BASELINE_SOURCES[source_baseline_id]
    if set(source_bytes) != set(required):
        raise ContractError("exact baseline source set required")
    decoded = {}
    materials = []
    for name in required:
        raw = source_bytes[name]
        if type(raw) is not bytes:
            raise ContractError("source snapshot must be bytes")
        path, expected = SOURCE_BINDINGS[name]
        if raw_sha256(raw) != expected:
            raise ContractError(f"source raw identity mismatch: {name}")
        value = parse_json(raw)
        digest = canonical_sha256(value, exclude_volatile=False)
        if name in BASELINE_FIXTURE_SHA256 and digest != BASELINE_FIXTURE_SHA256[name]:
            raise ContractError(f"baseline canonical identity mismatch: {name}")
        if name in PROPOSAL_RAW_SHA256 and raw_sha256(raw) != PROPOSAL_RAW_SHA256[name]:
            raise ContractError("proposal raw identity mismatch")
        decoded[name] = value
        materials.append(SourceMaterial(name, path, expected, digest, raw))
    proposal_name = required[0]
    adapted = adapt_proposal(source_bytes[proposal_name])
    if adapted.status != "VALID" or adapted.normalized_proposal is None:
        raise ContractError("baseline proposal is not valid")
    if source_baseline_id == "P3-CTRL-01":
        context = decoded["common_context"]
        context["operational_state"] = "RUNNING"
        payload = {"proposal": adapted.normalized_proposal, "context": context,
                   "physical_observations": decoded["physical_safe"],
                   "tick": 1000, "followup_evaluation": None}
    else:
        bundle = decoded["reentry_current"]
        bundle["normalized_request"] = adapted.normalized_proposal
        bundle["pre_decision_operational_state"] = "SUSPENDED"
        payload = {"bundle": bundle, "tick": 1000}
    # Composite payload: no claim that a single raw source file represents it.
    return BaselineSnapshot(source_baseline_id, JsonSnapshot.of(payload), tuple(materials))


def _verified_baseline(baseline):
    if type(baseline) is not BaselineSnapshot:
        raise ContractError("baseline material required, not just a hash")
    names = [m.source_id for m in baseline.source_materials]
    if len(set(names)) != len(names):
        raise ContractError("duplicate baseline source")
    reconstructed = resolve_baseline({m.source_id: m.raw_bytes for m in baseline.source_materials},
                                     baseline.source_baseline_id)
    if baseline != reconstructed:
        raise ContractError("baseline snapshot/material binding mismatch")
    return reconstructed


def _case(case):
    if type(case) is not P4CaseSpec:
        raise ContractError("frozen case required")
    matched = next((c for c in frozen_cases() if c.case_id == case.case_id), None)
    if (matched is None or canonical_bytes(asdict(case), exclude_volatile=False)
            != canonical_bytes(asdict(matched), exclude_volatile=False)):
        raise ContractError("case differs from frozen contract")
    return matched


def _get(payload, path):
    current = payload
    for part in path.split("/")[1:]:
        if type(current) is list:
            if part != "0" or not current:
                raise ContractError("unapproved array access")
            current = current[0]
        elif type(current) is dict and part in current:
            current = current[part]
        else:
            raise ContractError("application path missing; implicit creation prohibited")
    return current


def _set_existing(payload, path, value):
    parent_path, leaf = path.rsplit("/", 1)
    parent = _get(payload, parent_path)
    if type(parent) is not dict or leaf not in parent:
        raise ContractError("implicit field creation prohibited")
    parent[leaf] = value


def changed_paths(before, after, prefix=""):
    """Exact typed leaf differences; no globally excluded identity fields."""
    if type(before) is not type(after):
        return {prefix}
    if type(before) is dict:
        paths = set()
        for key in set(before) | set(after):
            escaped = key.replace("~", "~0").replace("/", "~1")
            path = prefix + "/" + escaped
            if key not in before or key not in after:
                paths.add(path)
            else:
                paths.update(changed_paths(before[key], after[key], path))
        return paths
    if type(before) is list:
        if len(before) != len(after):
            return {prefix}
        paths = set()
        for index, (old, new) in enumerate(zip(before, after)):
            paths.update(changed_paths(old, new, prefix + "/" + str(index)))
        return paths
    return set() if before == after else {prefix}


def physical_record_sha256(name, record):
    if name not in PHYSICAL_FIELDS or type(record) is not dict:
        raise ContractError("unknown physical record")
    return canonical_sha256(
        {"observation_name": name, "record": {k: v for k, v in record.items()
                                            if k not in {"content_identity", "content_sha256"}}},
        exclude_volatile=False,
    )


def _reconstruct(baseline, case):
    baseline = _verified_baseline(baseline)
    case = _case(case)
    if case.source_baseline_id != baseline.source_baseline_id:
        raise ContractError("case/baseline mismatch")
    payload = baseline.payload.value
    paths = {"CONTROL": (), "AUTH": (AUTH_PATH,), "REM": (REM_PATH,),
             "RISK": (RISK_PATH,), "PHY": PHYSICAL_PATHS}[case.parameter_family]
    if case.parameter_family == "RISK":
        risks = payload["context"]["risk_records"]
        if len(risks) != 1 or risks[0].get("risk_observation_id") != "RISK-P3-001":
            raise ContractError("risk record identity/index binding mismatch")
    targets, semantic, dependent, rules = [], [], [], []
    for path in paths:
        old = _get(payload, path)
        expected_old = 1100 if case.parameter_family == "AUTH" else 1000
        if type(old) is not int or old != expected_old:
            raise ContractError("baseline application old value mismatch")
        target = ApplicationTarget(path, old, case.parameter_value, old != case.parameter_value)
        targets.append(asdict(target))
        _set_existing(payload, path, case.parameter_value)
        if target.semantic_change_expected:
            semantic.append(path)
    if case.parameter_family == "PHY":
        # All fourteen rules are declared even for the approved PHY-03 no-op.
        for name in PHYSICAL_FIELDS:
            source = "/physical_observations/" + name
            for field in ("content_identity", "content_sha256"):
                rules.append(asdict(DependentIdentityRule(source, source + "/" + field)))
            if source + "/observed_at_tick" in semantic:
                record = payload["physical_observations"][name]
                digest = physical_record_sha256(name, record)
                record["content_identity"] = "sha256:" + digest
                record["content_sha256"] = digest
                dependent.extend((source + "/content_identity", source + "/content_sha256"))
    if changed_paths(baseline.payload.value, payload) != set(semantic) | set(dependent):
        raise ContractError("reconstructed delta outside approved exact paths")
    materials = []
    for item in baseline.source_materials:
        entry = {"source_id": item.source_id, "path": item.path, "raw_sha256": item.raw_sha256}
        if item.canonical_sha256 is not None:
            entry["canonical_sha256"] = item.canonical_sha256
        materials.append(entry)
    provenance = {
        "derived_input_id": case.derived_input_id,
        "source_baseline_id": baseline.source_baseline_id,
        "source_baseline_payload_sha256": baseline.payload.sha256,
        "source_materials": materials, "derivation_rule_id": RULE_ID,
        "application_targets": targets, "semantic_changed_paths": semantic,
        "dependent_identity_rules": rules, "dependent_identity_changed_paths": dependent,
        "resulting_payload_sha256": canonical_sha256(payload, exclude_volatile=False),
        "parameter_family": case.parameter_family, "boundary_class": case.boundary_class,
        "logical_evaluation_time": 1000,
    }
    envelope = {"schema_id": SCHEMA_ID, "provenance": provenance}
    envelope["wrapper_sha256"] = canonical_sha256(envelope, exclude_volatile=False)
    return DerivedInput(JsonSnapshot.of(payload), DerivedInputProvenance(JsonSnapshot.of(envelope)))


def derive_input(baseline: BaselineSnapshot, case: P4CaseSpec) -> DerivedInput:
    """Produce an unapproved candidate from only frozen application operations."""
    return _reconstruct(baseline, case)


def verify_derivation(baseline: BaselineSnapshot, provenance: DerivedInputProvenance,
                      derived_payload: JsonSnapshot, case: P4CaseSpec) -> VerifiedDerivedInput:
    """Reconstruct every field and verify the three delta sets plus identities."""
    if type(provenance) is not DerivedInputProvenance or type(derived_payload) is not JsonSnapshot:
        raise ContractError("immutable candidate payload and provenance required")
    expected = _reconstruct(baseline, case)
    envelope = provenance.envelope.value
    wrapper_basis = {"schema_id": envelope["schema_id"], "provenance": envelope["provenance"]}
    if canonical_sha256(wrapper_basis, exclude_volatile=False) != envelope["wrapper_sha256"]:
        raise ContractError("wrapper identity mismatch")
    if derived_payload.raw != expected.payload.raw:
        raise ContractError("full derived payload reconstruction mismatch")
    if provenance.envelope.raw != expected.provenance.envelope.raw:
        raise ContractError("provenance reconstruction mismatch")
    p = envelope["provenance"]
    actual = changed_paths(baseline.payload.value, derived_payload.value)
    if actual != set(p["semantic_changed_paths"]) | set(p["dependent_identity_changed_paths"]):
        raise ContractError("actual change paths mismatch")
    if actual & set(DEPENDENT_PATHS) != set(p["dependent_identity_changed_paths"]):
        raise ContractError("dependent change paths mismatch")
    return VerifiedDerivedInput(baseline, derived_payload, provenance)
