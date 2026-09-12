from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from phase2.adapter import AdapterReasonCode, ParseStatus
from phase2.class_b_config import (
    FROZEN_CLASS_B_CONFIG,
    STRUCTURED_OUTPUT_REQUEST_FIELD_ALLOWLIST,
    STRUCTURED_OUTPUT_SCHEMA_IDENTIFIER,
    STRUCTURED_OUTPUT_SCHEMA_NAME,
    STRUCTURED_OUTPUT_SCHEMA_PATH,
    structured_output_recovery_config,
)
from phase2.class_b_runner import build_frozen_proposer
from phase2.live_runner import execute_live_observations
from phase2.lmstudio_bridge import request_model_content
from phase2.provenance import ModelInfo
from phase2.runner import run_phase2_raw
from phase2.scenarios import load_phase2_scenario
from tests.helpers import make_fixture
from tests.phase2.helpers import PROMPT_VERSION, RAW_NORMAL, RUN_TIME


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = PROJECT_ROOT / STRUCTURED_OUTPUT_SCHEMA_PATH
TASK = "Propose one ACTION to MOVE to ZONE_B at NORMAL speed."
SEMANTICALLY_INVALID = (
    '{"request_type":"move","behavior":"move_to",'
    '"target":"ZONE_B","speed":"NORMAL"}'
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.body = json.dumps(
            {"choices": [{"message": {"content": content}}]},
            ensure_ascii=False,
        ).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def transport(content: str) -> str:
    calls = 0

    def opener(request, *, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse(content)

    result = request_model_content(
        "exact rendered prompt",
        config=structured_output_recovery_config(),
        opener=opener,
    )
    assert calls == 1
    return result


@dataclass
class StaticProposer:
    model: ModelInfo
    raw_output: str

    def generate_rendered_prompt(self, rendered_prompt: str) -> str:
        return self.raw_output


def test_so_01_request_body_contains_structured_output() -> None:
    prompt = "exact rendered prompt\n"
    config = structured_output_recovery_config()
    body = config.request_body(prompt)
    schema_from_file = json.loads(SCHEMA_FILE.read_bytes().decode("utf-8"))

    assert frozenset(body) == STRUCTURED_OUTPUT_REQUEST_FIELD_ALLOWLIST
    assert body["model"] == "google/gemma-3n-e4b"
    assert body["messages"] == [{"role": "user", "content": prompt}]
    assert body["temperature"] == 0.7
    assert body["top_p"] == 0.95
    assert body["max_tokens"] == 128
    assert body["n"] == 1
    assert body["stream"] is False
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": STRUCTURED_OUTPUT_SCHEMA_NAME,
            "schema": schema_from_file,
        },
    }
    assert "strict" not in json.dumps(body, sort_keys=True)

    proposer = build_frozen_proposer(config)
    assert "--structured-output-recovery" in proposer.command
    digest_index = proposer.command.index("--expected-schema-sha256") + 1
    assert proposer.command[digest_index] == config.structured_output.schema_sha256


def test_so_02_original_condition_remains_unconstrained() -> None:
    prompt = "exact rendered prompt\n"
    body = FROZEN_CLASS_B_CONFIG.request_body(prompt)
    recovery_body = structured_output_recovery_config().request_body(prompt)

    assert "response_format" not in body
    assert set(recovery_body) - set(body) == {"response_format"}
    assert all(recovery_body[key] == value for key, value in body.items())
    assert FROZEN_CLASS_B_CONFIG.model_info().to_dict().get(
        "response_format_type"
    ) is None
    assert "--structured-output-recovery" not in build_frozen_proposer().command
    original_result = run_phase2_raw(
        RAW_NORMAL,
        make_fixture(scenario_id="original-unconstrained-condition"),
        model=FROZEN_CLASS_B_CONFIG.model_info(),
        prompt_version=PROMPT_VERSION,
        run_time=RUN_TIME,
    )
    assert not {
        "response_format_type",
        "schema_identifier",
        "schema_path",
        "schema_sha256",
    }.intersection(original_result.provenance.to_dict()["model"])


def test_so_03_schema_digest_uses_exact_file_bytes() -> None:
    expected = hashlib.sha256(SCHEMA_FILE.read_bytes()).hexdigest()
    config = structured_output_recovery_config()
    metadata = config.evidence_metadata()

    assert config.structured_output is not None
    assert config.structured_output.schema_sha256 == expected
    assert metadata["schema_sha256"] == expected
    assert metadata["schema_identifier"] == STRUCTURED_OUTPUT_SCHEMA_IDENTIFIER
    assert metadata["schema_path"] == STRUCTURED_OUTPUT_SCHEMA_PATH


def test_so_04_structured_bare_json_passes_transport_unchanged() -> None:
    content = " \n" + RAW_NORMAL + "\r\n"
    assert transport(content) == content


def test_so_05_structurally_valid_semantically_invalid_remains_rejected() -> None:
    raw_output = transport(SEMANTICALLY_INVALID)
    result = run_phase2_raw(
        raw_output,
        make_fixture(scenario_id="structured-output-semantic-rejection"),
        model=structured_output_recovery_config().model_info(),
        prompt_version=PROMPT_VERSION,
        run_time=RUN_TIME,
    )

    assert result.adapter.parse_status == ParseStatus.INVALID
    assert result.adapter.validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE,
    )
    assert result.adapter.normalized_proposal is None
    assert result.provenance.governance_evaluation_status == "NOT_PERFORMED"
    assert result.provenance.governance_receipt_id is None
    assert result.provenance.physical_action == "NONE"
    assert result.phase1_result is None


def test_so_06_valid_structured_proposal_reaches_governance() -> None:
    raw_output = transport(RAW_NORMAL)
    result = run_phase2_raw(
        raw_output,
        make_fixture(scenario_id="structured-output-valid-path"),
        model=structured_output_recovery_config().model_info(),
        prompt_version=PROMPT_VERSION,
        run_time=RUN_TIME,
    )

    assert result.adapter.parse_status == ParseStatus.VALID
    assert result.adapter.normalized_proposal is not None
    assert result.provenance.governance_evaluation_status == "PERFORMED"
    assert result.provenance.enforcement_status == "PERFORMED"
    assert result.provenance.physical_action == "MOVED_TO_ZONE_B"
    assert result.phase1_result is not None
    assert result.phase1_result.receipt["decision"] == "ALLOW"
    assert result.provenance.governance_receipt_id == result.phase1_result.receipt[
        "receipt_id"
    ]


def test_so_07_fenced_json_still_rejected_without_repair() -> None:
    fenced = "```json\n" + RAW_NORMAL + "\n```"
    raw_output = transport(fenced)
    result = run_phase2_raw(
        raw_output,
        make_fixture(scenario_id="structured-output-fenced-rejection"),
        model=structured_output_recovery_config().model_info(),
        prompt_version=PROMPT_VERSION,
        run_time=RUN_TIME,
    )

    assert raw_output == fenced
    assert result.adapter.parse_status == ParseStatus.INVALID
    assert result.adapter.validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_NOT_JSON,
    )
    assert result.phase1_result is None


def test_so_08_evidence_contains_recovery_identity_for_all_five_attempts(
    tmp_path: Path,
) -> None:
    config = structured_output_recovery_config()
    proposer = StaticProposer(config.model_info(), RAW_NORMAL)
    scenario = load_phase2_scenario(
        PROJECT_ROOT / "phase2_scenarios" / "p2_10_deterministic_replay.yaml"
    )
    attempts = execute_live_observations(
        proposer=proposer,
        task_instruction=TASK,
        scenario_document=scenario,
        repeat=5,
        output_dir=tmp_path / "recovery",
        now=lambda: RUN_TIME,
    )

    expected_digest = hashlib.sha256(SCHEMA_FILE.read_bytes()).hexdigest()
    assert len(attempts) == 5
    for attempt in attempts:
        saved_observation = json.loads(
            attempt.observation_path.read_text(encoding="utf-8")
        )
        identity = saved_observation["equivalence_identity"]
        assert identity["protocol_version"] == config.protocol_version
        assert identity["scenario_id"] == "P2-10"
        assert identity["task_instruction"] == TASK
        assert identity["rendered_prompt_sha256"] == (
            attempt.observation.rendered_prompt_sha256
        )
        assert identity["response_format"] == {
            "type": "json_schema",
            "schema_identifier": STRUCTURED_OUTPUT_SCHEMA_IDENTIFIER,
            "schema_path": STRUCTURED_OUTPUT_SCHEMA_PATH,
            "schema_sha256": expected_digest,
        }
        assert identity["sampling_parameters"] == config.sampling_parameters()
        assert identity["omitted_parameters"] == config.omitted_parameters()

        assert attempt.phase2_result is not None
        provenance = attempt.phase2_result.provenance.to_dict()
        assert provenance["model"]["response_format_type"] == "json_schema"
        assert provenance["model"]["schema_identifier"] == (
            STRUCTURED_OUTPUT_SCHEMA_IDENTIFIER
        )
        assert provenance["model"]["schema_path"] == STRUCTURED_OUTPUT_SCHEMA_PATH
        assert provenance["model"]["schema_sha256"] == expected_digest
        assert attempt.phase2_result.phase1_result is not None


def test_recovery_bridge_rejects_schema_digest_mismatch_before_request() -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-B",
            "-m",
            "phase2.lmstudio_bridge",
            "--structured-output-recovery",
            "--expected-schema-sha256",
            "0" * 64,
        ),
        input=b"prompt",
        capture_output=True,
        check=False,
        timeout=10,
    )

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert b"schema digest mismatch" in completed.stderr
