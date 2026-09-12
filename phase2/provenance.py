"""Phase 2 model/adapter provenance and linked receipt reconstruction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any
import uuid

from src.receipts import reconstruct as reconstruct_phase1


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model_name: str
    runtime: str
    runtime_version: str
    sampling_parameters: dict[str, Any]
    artifact_identifier: str | None = None
    protocol_version: str | None = None
    endpoint: str | None = None
    api_route: str | None = None
    quantization: str | None = None
    omitted_parameters: dict[str, str] | None = None
    response_format_type: str | None = None
    schema_identifier: str | None = None
    schema_path: str | None = None
    schema_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }


@dataclass(frozen=True)
class ProvenanceRecord:
    phase: str
    run_id: str
    provenance_digest: str
    scenario_id: str
    model: ModelInfo
    prompt_version: str
    run_time: str
    raw_llm_output: str
    parse_status: str
    validation_reason_codes: tuple[str, ...]
    normalized_proposal: dict[str, Any] | None
    initial_operational_state: str
    governance_evaluation_status: str
    enforcement_status: str
    physical_action: str
    final_operational_state: str
    governance_receipt_id: str | None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in (
            "response_format_type",
            "schema_identifier",
            "schema_path",
            "schema_sha256",
        ):
            if result["model"].get(key) is None:
                result["model"].pop(key, None)
        result["validation_reason_codes"] = list(self.validation_reason_codes)
        return result


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def create_run_id() -> str:
    """Return an offline-unique identity for one Phase 2 observation attempt."""
    return "p2-" + uuid.uuid4().hex


def create_provenance(
    *,
    scenario_id: str,
    model: ModelInfo,
    prompt_version: str,
    run_time: str,
    raw_llm_output: str,
    parse_status: str,
    validation_reason_codes: tuple[str, ...],
    normalized_proposal: dict[str, Any] | None,
    initial_operational_state: str,
    governance_evaluation_status: str,
    enforcement_status: str,
    physical_action: str,
    final_operational_state: str,
    governance_receipt_id: str | None,
) -> ProvenanceRecord:
    body = {
        "phase": "P2",
        "scenario_id": scenario_id,
        "model": model.to_dict(),
        "prompt_version": prompt_version,
        "run_time": run_time,
        "raw_llm_output": raw_llm_output,
        "parse_status": parse_status,
        "validation_reason_codes": list(validation_reason_codes),
        "normalized_proposal": normalized_proposal,
        "initial_operational_state": initial_operational_state,
        "governance_evaluation_status": governance_evaluation_status,
        "enforcement_status": enforcement_status,
        "physical_action": physical_action,
        "final_operational_state": final_operational_state,
        "governance_receipt_id": governance_receipt_id,
    }
    provenance_digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
    return ProvenanceRecord(
        run_id=create_run_id(),
        provenance_digest=provenance_digest,
        **body,
    )


def reconstruct_phase2(
    provenance: dict[str, Any],
    governance_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconstruct the model/adapter boundary and optional governance result."""
    receipt_id = provenance["governance_receipt_id"]
    if receipt_id is None:
        if governance_receipt is not None:
            raise ValueError("invalid proposal provenance must not link a receipt")
        governance = None
    else:
        if governance_receipt is None or governance_receipt.get("receipt_id") != receipt_id:
            raise ValueError("governance receipt link does not match provenance")
        governance = reconstruct_phase1(governance_receipt)

    return {
        "phase": provenance["phase"],
        "run_id": provenance["run_id"],
        "provenance_digest": provenance.get("provenance_digest"),
        "scenario_id": provenance["scenario_id"],
        "model": provenance["model"],
        "prompt_version": provenance["prompt_version"],
        "run_time": provenance["run_time"],
        "raw_llm_output": provenance["raw_llm_output"],
        "parse_status": provenance["parse_status"],
        "validation_reason_codes": provenance["validation_reason_codes"],
        "normalized_proposal": provenance["normalized_proposal"],
        "initial_operational_state": provenance["initial_operational_state"],
        "governance_evaluation_status": provenance[
            "governance_evaluation_status"
        ],
        "enforcement_status": provenance["enforcement_status"],
        "physical_action": provenance["physical_action"],
        "final_operational_state": provenance["final_operational_state"],
        "governance_receipt_id": receipt_id,
        "permission_decision": (
            governance["permission_decision"] if governance is not None else None
        ),
        "governance": governance,
    }
