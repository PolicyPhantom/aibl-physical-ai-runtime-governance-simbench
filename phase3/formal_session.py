"""Explicitly authorized, offline orchestration around the unchanged core semantics."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from weakref import WeakKeyDictionary

from . import evidence_writer as writer
from . import formal_materials as materials
from .constants import (
    BASELINE_FIXTURE_SHA256, CORE_SCENARIO_SHA256, PROPOSAL_RAW_SHA256, SCENARIO_ORDER,
)
from .formal_preflight import (
    FormalPreflightInput, OutputSlot, evaluate_formal_preflight, validate_material_anchor,
)
from .identity import canonical_sha256, raw_sha256
from .models import WorkspaceAuthorization
from .replay import compare_results
from .runner import _assert_nfc_structured, _safe_layout_segment, run_scenario


@dataclass(frozen=True)
class FormalAttemptPlan:
    order: int
    case_id: str
    case_batch_id: str
    experiment_id: str
    attempt: int
    case_bytes: bytes
    output_root: Path


@dataclass(frozen=True, eq=False)
class FormalSessionPlan:
    session_id: str
    candidate_head: str
    attempts: tuple[FormalAttemptPlan, ...]
    inputs_bytes: bytes
    trusted: tuple[materials.TrustedFixture, ...]
    authorization: WorkspaceAuthorization
    identity: str

    @property
    def slots(self) -> tuple[OutputSlot, ...]:
        return tuple(OutputSlot(self.session_id, item.case_batch_id, item.case_id,
                                item.attempt, item.output_root) for item in self.attempts)


@dataclass(frozen=True)
class FormalGoApproval:
    approval_id: str
    approved: bool
    approved_at: str
    operator: str
    session_id: str
    plan_identity: str
    candidate_head: str
    manifest_hashes: tuple[tuple[str, str], ...]
    workspace_identity: str


@dataclass(frozen=True)
class AttemptOutcome:
    case_id: str
    attempt: int
    status: str
    core_called: bool
    collection_complete: bool


@dataclass(frozen=True)
class FormalSessionResult:
    status: str
    attempts: tuple[AttemptOutcome, ...]
    core_call_count: int
    retry_count: int
    stop_reason: str | None
    failure_record_error: str | None


_sessions: WeakKeyDictionary = WeakKeyDictionary()


def workspace_identity(authorization: WorkspaceAuthorization) -> str:
    return canonical_sha256({
        "root": str(authorization.authorized_workspace_root),
        "authorization_id": authorization.authorization_id,
        "protected_roots": [str(path) for path in authorization.protected_roots],
    }, exclude_volatile=False)


def manifest_bindings(plan: FormalSessionPlan) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((item.manifest["manifest_id"], item.manifest_sha256) for item in plan.trusted))


def build_formal_session_plan(
    *, session_id: str, candidate_head: str, scenario_registry: dict,
    case_batches: dict[str, str], inputs: dict, trusted: tuple[materials.TrustedFixture, ...],
    authorization: WorkspaceAuthorization,
) -> FormalSessionPlan:
    _safe_layout_segment(session_id, "session_id")
    if len(candidate_head) != 40 or any(char not in "0123456789abcdef" for char in candidate_head):
        raise ValueError("candidate HEAD required")
    _assert_nfc_structured(scenario_registry, "registry")
    _assert_nfc_structured(inputs, "inputs")
    cases = scenario_registry["cases"]
    if (
        scenario_registry.get("registry_id") != "P3-CORE-SCENARIOS-v1"
        or scenario_registry.get("version") != "1.0"
        or tuple(item["scenario_id"] for item in cases) != SCENARIO_ORDER
        or set(case_batches) != set(SCENARIO_ORDER) or len(set(case_batches.values())) != 12
    ):
        raise ValueError("frozen registry / twelve case batches required")
    for case in cases:
        if canonical_sha256(case, exclude_volatile=False) != CORE_SCENARIO_SHA256[case["scenario_id"]]:
            raise ValueError("case contract changed")
    if set(inputs) != {"proposals", "common_context", "physical_safe", "reentry_current"}:
        raise ValueError("complete frozen input set required")
    if set(inputs["proposals"]) != set(PROPOSAL_RAW_SHA256):
        raise ValueError("four exact proposal fixtures required")
    for name, digest in PROPOSAL_RAW_SHA256.items():
        if raw_sha256(inputs["proposals"][name]) != digest:
            raise ValueError("raw proposal changed")
    for name, digest in BASELINE_FIXTURE_SHA256.items():
        if canonical_sha256(inputs[name], exclude_volatile=False) != digest:
            raise ValueError("baseline changed")
    if len(trusted) != 2 or {item.fixture_id for item in trusted} != set(materials.FIXTURES.values()):
        raise ValueError("two separate trusted fixture mappings required")
    if len({item.manifest["manifest_id"] for item in trusted}) != 2:
        raise ValueError("manifest identities must distinguish fixtures")
    encoded = writer.snapshot(inputs | {
        "proposals": {name: raw.hex() for name, raw in inputs["proposals"].items()},
    })
    attempts = []
    for case in cases:
        case_id = case["scenario_id"]
        batch = _safe_layout_segment(case_batches[case_id], "case_batch_id")
        for attempt in range(1, 6):
            # In this frozen core, experiment_id is explicitly the case_id.
            root = authorization.authorized_workspace_root / "phase3_evidence" / session_id / batch / case_id / f"attempt-{attempt:02d}"
            attempts.append(FormalAttemptPlan(len(attempts) + 1, case_id, batch, case_id,
                                              attempt, writer.snapshot(case), root))
    identity = canonical_sha256({
        "session": session_id, "head": candidate_head,
        "workspace": workspace_identity(authorization), "inputs": hashlib.sha256(encoded).hexdigest(),
        "slots": [{
            "order": item.order, "case": item.case_id, "batch": item.case_batch_id,
            "experiment": item.experiment_id, "attempt": item.attempt,
            "case_identity": hashlib.sha256(item.case_bytes).hexdigest(), "output": str(item.output_root),
        } for item in attempts],
        "materials": sorted((item.fixture_id, item.manifest_sha256, item.manifest["manifest_id"],
                             str(item.root), item.approval_id) for item in trusted),
    }, exclude_volatile=False)
    plan = FormalSessionPlan(session_id, candidate_head, tuple(attempts), encoded,
                             tuple(trusted), authorization, identity)
    _sessions[plan] = "NEW"
    return plan


def _inputs(plan: FormalSessionPlan) -> dict:
    values = json.loads(plan.inputs_bytes)
    values["proposals"] = {name: bytes.fromhex(raw) for name, raw in values["proposals"].items()}
    return values


def _go_matches(plan, human_go) -> bool:
    return isinstance(human_go, FormalGoApproval) and (
        human_go.approved is True and bool(human_go.approval_id)
        and bool(human_go.approved_at) and bool(human_go.operator)
        and human_go.session_id == plan.session_id and human_go.plan_identity == plan.identity
        and human_go.candidate_head == plan.candidate_head
        and human_go.manifest_hashes == manifest_bindings(plan)
        and human_go.workspace_identity == workspace_identity(plan.authorization)
    )


def _expected_matches(case, result) -> bool:
    expected = case["expected"]
    observed = {
        "adapter": result["adapter"]["status"], "final_state": result["final_state"],
        "command_status": result["command_status"],
    }
    if result["adapter"]["status"] == "INVALID":
        observed.update(reason=result["adapter"]["reason"], governance=result["governance"])
        if (result["governance"] != "NOT_PERFORMED" or result["enforcement"] != "NOT_PERFORMED"
                or result["receipt_present"] or result["normalized_proposal"] is not None
                or result["physical_action_count"] != 0):
            return False
    else:
        observed.update(decision=result["governance"]["decision"], reason=result["governance"]["reason"])
        if not result["receipt_present"]:
            return False
    physical = result["physical_result"]
    observed["physical_result"] = None if physical is None else physical["execution_result"]
    observed["event"] = None if physical is None else physical["event"]
    observed["followup_decision"] = None if result["followup"] is None else result["followup"]["decision"]["decision"]
    verification = result["verification"]
    if verification is not None:
        missing = verification["completeness"] == "INCOMPLETE"
        observed["verification"] = verification["completeness"] if missing else verification["present_file_integrity"]
        observed["verification_reason"] = verification["completeness_reason"] if missing else verification["integrity_reason"]
    if any(observed.get(key) != value for key, value in expected.items()):
        return False
    executing = case["scenario_id"] in {"P3-CTRL-01", "P3-E-02"}
    if result["physical_action_count"] != int(executing):
        return False
    if not executing and result["command_status"] is not None:
        return False
    if case["scenario_id"] == "P3-CTRL-02" and result["enforcement"] != "STATE_RESTORATION_ONLY":
        return False
    if case["scenario_id"] == "P3-E-02" and (
        result["followup"]["physical_action_count"] != 0
        or result["followup"]["enforcement"] != "NOT_PERFORMED"
        or physical["expected_state"] != "ZONE_B" or physical["actual_state"] != "ZONE_A"
    ):
        return False
    return result["initial_state"] == case["initial_state"]


def run_formal_session(
    *, plan: FormalSessionPlan, human_go: FormalGoApproval,
    preflight: FormalPreflightInput,
) -> FormalSessionResult:
    def unstarted(reason):
        return FormalSessionResult("NOT_AUTHORIZED", tuple(
            AttemptOutcome(item.case_id, item.attempt, "NOT_RUN", False, False)
            for item in plan.attempts
        ), 0, 0, reason, None)
    if _sessions.get(plan) != "NEW":
        return unstarted("session plan reused or not issued")
    if not _go_matches(plan, human_go):
        return unstarted("Human GO does not bind this plan")
    readiness = evaluate_formal_preflight(preflight)
    if (
        not readiness.ready_for_human_go or readiness.plan_identity != plan.identity
        or readiness.candidate_head != plan.candidate_head
        or readiness.manifest_hashes != manifest_bindings(plan)
        or preflight.slots != plan.slots or preflight.authorization != plan.authorization
        or {item.trusted for item in preflight.materials} != set(plan.trusted)
    ):
        return unstarted("preflight not ready or does not bind this plan")
    _sessions[plan] = "STARTED"
    outcomes = []
    references = {}
    calls = 0
    for position, item in enumerate(plan.attempts):
        handle = None
        called = False
        collection_complete = False
        try:
            if not _go_matches(plan, human_go):
                raise ValueError("authorization applicability changed")
            for material in preflight.materials:
                validate_material_anchor(material)
            values = _inputs(plan)
            case = json.loads(item.case_bytes)
            handle = writer.initialize_attempt_tree(
                output_root=item.output_root, authorization=plan.authorization,
                session_id=plan.session_id, batch_id=item.case_batch_id, case_id=item.case_id,
                attempt=item.attempt, spec_snapshot=case,
                proposal_raw_bytes=values["proposals"][case["proposal_fixture"]],
                references={"plan_identity": plan.identity, "run_id": f"{plan.session_id}:{item.order}",
                            "manifest_hashes": manifest_bindings(plan),
                            "observation_sources": readiness.observation_sources},
            )
            verification = None
            if item.case_id in materials.FIXTURES:
                trusted = next(value for value in plan.trusted if value.fixture_id == materials.FIXTURES[item.case_id])
                prepared = materials.prepare_c_evidence_attempt(
                    case_id=item.case_id, trusted=trusted, boundary=handle.boundary,
                )
                verification = prepared.verification.to_dict()
            calls += 1
            called = True
            result = run_scenario(
                case, **values, output_root=item.output_root,
                workspace_authorization=plan.authorization, session_id=plan.session_id,
                batch_id=item.case_batch_id, attempt_number=item.attempt,
                evidence_verification=verification, prepared_boundary=handle.boundary,
            )
            writer.persist_core_result(handle, core_result=result)
            replay = compare_results(references.get(item.case_id, result), result)
            accepted = _expected_matches(case, result) and replay["must_match"]
            summary = writer.finalize_attempt_tree(
                handle,
                reconciliation={"accepted": accepted, "replay": replay},
            )
            collection_complete = summary.collection_complete
            if not summary.collection_complete or not accepted:
                raise ValueError("material frozen-result or replay divergence")
            references.setdefault(item.case_id, result)
            outcomes.append(AttemptOutcome(item.case_id, item.attempt, "COMPLETED", True, True))
        except Exception as exc:
            failure_error = None
            handle = handle or getattr(exc, "handle", None)
            if handle is not None and not collection_complete:
                try:
                    writer.record_attempt_failure(handle, reason=str(exc))
                except Exception as record_exc:
                    failure_error = str(record_exc)
            elif handle is None:
                failure_error = "attempt initialization failed before a usable evidence handle"
            outcomes.append(AttemptOutcome(item.case_id, item.attempt, "STOPPED", called, collection_complete))
            outcomes.extend(AttemptOutcome(rest.case_id, rest.attempt, "NOT_RUN_AFTER_STOP", False, False)
                            for rest in plan.attempts[position + 1:])
            _sessions[plan] = "STOPPED"
            return FormalSessionResult("SESSION_STOPPED", tuple(outcomes), calls, 0, str(exc), failure_error)
    _sessions[plan] = "COMPLETED"
    return FormalSessionResult("COMPLETED", tuple(outcomes), calls, 0, None, None)
