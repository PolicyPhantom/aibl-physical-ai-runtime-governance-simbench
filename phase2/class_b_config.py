"""Frozen single source of truth for the first formal Phase 2 Class B cycle."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from phase2.provenance import ModelInfo


REQUEST_FIELD_ALLOWLIST = frozenset(
    {"model", "messages", "temperature", "top_p", "max_tokens", "n", "stream"}
)
STRUCTURED_OUTPUT_REQUEST_FIELD_ALLOWLIST = REQUEST_FIELD_ALLOWLIST | {
    "response_format"
}
OMITTED_REQUEST_FIELDS = (
    "seed",
    "stop",
    "logit_bias",
    "frequency_penalty",
    "presence_penalty",
)
UNCONTROLLED_PARAMETER_STATUS = "not explicitly controlled by this protocol"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRUCTURED_OUTPUT_RESPONSE_FORMAT_TYPE = "json_schema"
STRUCTURED_OUTPUT_SCHEMA_NAME = "aibl_phase2_proposal"
STRUCTURED_OUTPUT_SCHEMA_IDENTIFIER = "aibl_phase2_proposal_structural_v1"
STRUCTURED_OUTPUT_SCHEMA_PATH = (
    "phase2_schemas/aibl_phase2_proposal_structural_v1.json"
)


@dataclass(frozen=True)
class StructuredOutputSpec:
    response_format_type: str
    schema_name: str
    schema_identifier: str
    schema_path: str
    schema_sha256: str
    schema: dict[str, Any]

    @classmethod
    def load(cls) -> "StructuredOutputSpec":
        schema_file = PROJECT_ROOT / STRUCTURED_OUTPUT_SCHEMA_PATH
        schema_bytes = schema_file.read_bytes()
        schema = json.loads(schema_bytes.decode("utf-8"))
        if not isinstance(schema, dict):
            raise ValueError("structured-output schema must be a JSON object")
        return cls(
            response_format_type=STRUCTURED_OUTPUT_RESPONSE_FORMAT_TYPE,
            schema_name=STRUCTURED_OUTPUT_SCHEMA_NAME,
            schema_identifier=STRUCTURED_OUTPUT_SCHEMA_IDENTIFIER,
            schema_path=STRUCTURED_OUTPUT_SCHEMA_PATH,
            schema_sha256=hashlib.sha256(schema_bytes).hexdigest(),
            schema=schema,
        )

    def request_field(self) -> dict[str, Any]:
        return {
            "type": self.response_format_type,
            "json_schema": {
                "name": self.schema_name,
                "schema": deepcopy(self.schema),
            },
        }

    def evidence_metadata(self) -> dict[str, str]:
        return {
            "response_format_type": self.response_format_type,
            "schema_identifier": self.schema_identifier,
            "schema_path": self.schema_path,
            "schema_sha256": self.schema_sha256,
        }


@dataclass(frozen=True)
class ClassBConfig:
    protocol_version: str
    runtime_name: str
    runtime_version: str
    endpoint: str
    api_route: str
    model_id: str
    artifact_identifier: str
    quantization: str
    temperature: float
    top_p: float
    max_tokens: int
    n: int
    stream: bool
    http_timeout_seconds: float
    process_timeout_seconds: float
    structured_output: StructuredOutputSpec | None = None

    @property
    def request_url(self) -> str:
        return self.endpoint + self.api_route

    def sampling_parameters(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "n": self.n,
            "stream": self.stream,
        }

    def omitted_parameters(self) -> dict[str, str]:
        return {
            name: UNCONTROLLED_PARAMETER_STATUS for name in OMITTED_REQUEST_FIELDS
        }

    def request_body(self, rendered_prompt: str) -> dict[str, Any]:
        """Construct a fresh request for the selected frozen condition."""
        body = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": rendered_prompt}],
            **self.sampling_parameters(),
        }
        allowlist = REQUEST_FIELD_ALLOWLIST
        if self.structured_output is not None:
            body["response_format"] = self.structured_output.request_field()
            allowlist = STRUCTURED_OUTPUT_REQUEST_FIELD_ALLOWLIST
        assert frozenset(body) == allowlist
        return body

    def evidence_metadata(self) -> dict[str, Any]:
        metadata = {
            "protocol_version": self.protocol_version,
            "provider": "local",
            "runtime": self.runtime_name,
            "runtime_version": self.runtime_version,
            "endpoint": self.endpoint,
            "api_route": self.api_route,
            "model_id": self.model_id,
            "artifact_identifier": self.artifact_identifier,
            "quantization": self.quantization,
            "sampling_parameters": self.sampling_parameters(),
            "omitted_parameters": self.omitted_parameters(),
        }
        if self.structured_output is not None:
            metadata.update(self.structured_output.evidence_metadata())
        return metadata

    def model_info(self) -> ModelInfo:
        metadata = self.evidence_metadata()
        return ModelInfo(
            provider=metadata["provider"],
            model_name=metadata["model_id"],
            runtime=metadata["runtime"],
            runtime_version=metadata["runtime_version"],
            sampling_parameters=metadata["sampling_parameters"],
            artifact_identifier=metadata["artifact_identifier"],
            protocol_version=metadata["protocol_version"],
            endpoint=metadata["endpoint"],
            api_route=metadata["api_route"],
            quantization=metadata["quantization"],
            omitted_parameters=metadata["omitted_parameters"],
            response_format_type=metadata.get("response_format_type"),
            schema_identifier=metadata.get("schema_identifier"),
            schema_path=metadata.get("schema_path"),
            schema_sha256=metadata.get("schema_sha256"),
        )


FROZEN_CLASS_B_CONFIG = ClassBConfig(
    protocol_version="Phase2-ClassB-Live-Observation-v1.0",
    runtime_name="LM Studio",
    runtime_version="0.4.16 (Build 2)",
    endpoint="http://127.0.0.1:1234",
    api_route="/v1/chat/completions",
    model_id="google/gemma-3n-e4b",
    artifact_identifier="gemma-3n-E4B-it-Q4_K_M.gguf",
    quantization="Q4_K_M",
    temperature=0.7,
    top_p=0.95,
    max_tokens=128,
    n=1,
    stream=False,
    http_timeout_seconds=120.0,
    process_timeout_seconds=130.0,
)


@lru_cache(maxsize=1)
def structured_output_recovery_config() -> ClassBConfig:
    """Load the distinct recovery condition without altering the original path."""
    return replace(
        FROZEN_CLASS_B_CONFIG,
        structured_output=StructuredOutputSpec.load(),
    )
