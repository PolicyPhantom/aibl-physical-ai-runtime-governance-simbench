from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from typing import Iterator
from urllib.error import URLError

import pytest

from phase2.class_b_config import (
    FROZEN_CLASS_B_CONFIG,
    OMITTED_REQUEST_FIELDS,
    REQUEST_FIELD_ALLOWLIST,
)
from phase2.class_b_runner import build_frozen_proposer
from phase2.live_runner import InvocationStatus, execute_live_observations
from phase2.lmstudio_bridge import BridgeError, request_model_content
from phase2.proposer import LocalCommandProposer
from phase2.scenarios import load_phase2_scenario
from tests.phase2.helpers import RAW_NORMAL, RUN_TIME


@dataclass(frozen=True)
class ResponseSpec:
    body: bytes
    status: int = 200
    content_type: str = "application/json"
    headers: tuple[tuple[str, str], ...] = ()


@contextmanager
def local_server(
    responses: list[ResponseSpec],
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    records: list[dict[str, object]] = []
    queue = list(responses)

    class Handler(BaseHTTPRequestHandler):
        def _respond(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            records.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": dict(self.headers.items()),
                    "body": self.rfile.read(length),
                }
            )
            response = queue.pop(0)
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
            self._respond()

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            self._respond()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def response_with_content(content: str) -> ResponseSpec:
    return ResponseSpec(
        json.dumps(
            {"choices": [{"message": {"content": content}}]},
            ensure_ascii=False,
        ).encode("utf-8")
    )


def redirect_response(status: int, target: str) -> ResponseSpec:
    return ResponseSpec(
        body=b"redirects are transport failures",
        status=status,
        headers=(("Location", target),),
    )


def config_for(endpoint: str):
    return replace(FROZEN_CLASS_B_CONFIG, endpoint=endpoint)


def bridge_command(endpoint: str) -> tuple[str, ...]:
    code = (
        "from dataclasses import replace\n"
        "from phase2.class_b_config import FROZEN_CLASS_B_CONFIG\n"
        "from phase2.lmstudio_bridge import main\n"
        f"config = replace(FROZEN_CLASS_B_CONFIG, endpoint={endpoint!r})\n"
        "raise SystemExit(main(config=config))\n"
    )
    return (sys.executable, "-B", "-c", code)


def scenario() -> dict:
    return load_phase2_scenario(
        Path(__file__).resolve().parents[2]
        / "phase2_scenarios"
        / "p2_01_normal_structured_movement.yaml"
    )


def test_frozen_request_body_allowlist_and_evidence_share_configuration() -> None:
    prompt = "  exact rendered prompt\n日本語\n"
    config = FROZEN_CLASS_B_CONFIG
    body = config.request_body(prompt)
    metadata = config.evidence_metadata()
    model = config.model_info().to_dict()

    assert body == {
        "model": "google/gemma-3n-e4b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 128,
        "n": 1,
        "stream": False,
    }
    assert frozenset(body) == REQUEST_FIELD_ALLOWLIST
    assert REQUEST_FIELD_ALLOWLIST == frozenset(
        {"model", "messages", "temperature", "top_p", "max_tokens", "n", "stream"}
    )
    assert frozenset(OMITTED_REQUEST_FIELDS) == frozenset(
        {"seed", "stop", "logit_bias", "frequency_penalty", "presence_penalty"}
    )
    assert not set(OMITTED_REQUEST_FIELDS).intersection(body)
    assert metadata["model_id"] == body["model"] == model["model_name"]
    assert metadata["sampling_parameters"] == {
        key: body[key] for key in ("temperature", "top_p", "max_tokens", "n", "stream")
    }
    assert model["sampling_parameters"] == metadata["sampling_parameters"]
    assert model["protocol_version"] == metadata["protocol_version"]
    assert model["endpoint"] == metadata["endpoint"]
    assert model["api_route"] == metadata["api_route"]
    assert model["quantization"] == metadata["quantization"]
    assert model["omitted_parameters"] == metadata["omitted_parameters"]


def test_formal_proposer_is_derived_from_frozen_configuration() -> None:
    proposer = build_frozen_proposer()
    assert proposer.model.to_dict() == FROZEN_CLASS_B_CONFIG.model_info().to_dict()
    assert proposer.timeout_seconds == FROZEN_CLASS_B_CONFIG.process_timeout_seconds
    assert proposer.command[-2:] == ("-m", "phase2.lmstudio_bridge")


def test_exact_prompt_is_posted_and_valid_envelope_is_unwrapped() -> None:
    prompt = "\n Exact rendered prompt — unchanged \n"
    content = '{"request_type":"ACTION"}'
    with local_server([response_with_content(content)]) as (endpoint, records):
        result = request_model_content(prompt, config=config_for(endpoint))

    assert result == content
    assert len(records) == 1
    record = records[0]
    assert record["path"] == "/v1/chat/completions"
    assert json.loads(record["body"]) == config_for(endpoint).request_body(prompt)
    assert record["headers"]["Content-Type"] == "application/json; charset=utf-8"


@pytest.mark.parametrize(
    "content",
    [
        "```json\n{\"request_type\":\"ACTION\"}\n```",
        "Here is the JSON: {\"request_type\":\"ACTION\"}",
        " \n\t{\"request_type\":\"ACTION\"}\r\n ",
        "",
    ],
    ids=["markdown-fence", "prose-wrapper", "outer-whitespace", "empty"],
)
def test_model_content_is_preserved_without_repair(content: str) -> None:
    with local_server([response_with_content(content)]) as (endpoint, _):
        result = request_model_content("prompt", config=config_for(endpoint))
    assert result == content


@pytest.mark.parametrize(
    "response",
    [
        ResponseSpec(b"{"),
        ResponseSpec(b"\xff"),
        ResponseSpec(b"[]"),
        ResponseSpec(b"{}"),
        ResponseSpec(b'{"choices":[]}'),
        ResponseSpec(
            b'{"choices":[{"message":{"content":"one"}},{"message":{"content":"two"}}]}'
        ),
        ResponseSpec(b'{"choices":[{}]}'),
        ResponseSpec(b'{"choices":[{"message":{}}]}'),
        ResponseSpec(b'{"choices":[{"message":{"content":null}}]}'),
    ],
    ids=[
        "malformed-json",
        "invalid-utf8",
        "non-object-envelope",
        "missing-choices",
        "zero-choices",
        "multiple-choices",
        "missing-message",
        "missing-content",
        "non-string-content",
    ],
)
def test_unusable_response_envelope_is_transport_failure(
    response: ResponseSpec,
) -> None:
    with local_server([response]) as (endpoint, records):
        with pytest.raises(BridgeError):
            request_model_content("prompt", config=config_for(endpoint))
    assert len(records) == 1


def test_http_error_fails_once_without_hidden_retry() -> None:
    with local_server([ResponseSpec(b'{"error":"failed"}', status=503)]) as (
        endpoint,
        records,
    ):
        with pytest.raises(BridgeError, match="HTTP 503"):
            request_model_content("prompt", config=config_for(endpoint))
    assert len(records) == 1


@pytest.mark.parametrize("failure", [URLError("refused"), TimeoutError("timed out")])
def test_connection_and_timeout_failures_are_contained(failure: Exception) -> None:
    calls = 0

    def failing_opener(request, *, timeout):
        nonlocal calls
        calls += 1
        raise failure

    with pytest.raises(BridgeError):
        request_model_content(
            "prompt",
            config=FROZEN_CLASS_B_CONFIG,
            opener=failing_opener,
        )
    assert calls == 1


def test_repeated_calls_are_fresh_stateless_single_turn_requests() -> None:
    with local_server(
        [response_with_content("first"), response_with_content("second")]
    ) as (endpoint, records):
        config = config_for(endpoint)
        assert request_model_content("prompt one", config=config) == "first"
        assert request_model_content("prompt two", config=config) == "second"

    assert len(records) == 2
    bodies = [json.loads(record["body"]) for record in records]
    assert bodies[0]["messages"] == [{"role": "user", "content": "prompt one"}]
    assert bodies[1]["messages"] == [{"role": "user", "content": "prompt two"}]
    assert all("Cookie" not in record["headers"] for record in records)


def test_bridge_subprocess_writes_exact_model_content_only() -> None:
    content = " \n```json\n{}\n```\n "
    prompt = "exact stdin prompt\n"
    with local_server([response_with_content(content)]) as (endpoint, records):
        completed = subprocess.run(
            bridge_command(endpoint),
            input=prompt.encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=10,
        )

    assert completed.returncode == 0
    assert completed.stdout == content.encode("utf-8")
    assert completed.stderr == b""
    assert json.loads(records[0]["body"])["messages"] == [
        {"role": "user", "content": prompt}
    ]


def test_bridge_failure_becomes_observation_and_next_attempt_continues(
    tmp_path: Path,
) -> None:
    responses = [ResponseSpec(b"not-json"), response_with_content(RAW_NORMAL)]
    with local_server(responses) as (endpoint, records):
        config = config_for(endpoint)
        proposer = LocalCommandProposer(
            command=bridge_command(endpoint),
            model=config.model_info(),
            timeout_seconds=10,
        )
        attempts = execute_live_observations(
            proposer=proposer,
            task_instruction="Move normally to ZONE_B.",
            scenario_document=scenario(),
            repeat=2,
            output_dir=tmp_path / "live",
            now=lambda: RUN_TIME,
        )

    failed, continued = attempts
    batch_dir = failed.observation_path.parents[1]
    assert len(records) == 2
    assert failed.observation.invocation_status == InvocationStatus.INVOCATION_FAILED
    assert failed.observation.raw_output_path is None
    assert failed.observation.phase2_provenance_path is None
    assert failed.observation.governance_receipt_id is None
    assert failed.phase2_result is None
    assert continued.observation.invocation_status == InvocationStatus.COMPLETED
    assert continued.phase2_result is not None
    assert continued.phase2_result.provenance.raw_llm_output == RAW_NORMAL
    assert continued.phase2_result.phase1_result is not None
    assert len(list((batch_dir / "observations").glob("*.json"))) == 2
    assert len(list((batch_dir / "raw").glob("*.txt"))) == 1
    assert len(list((batch_dir / "provenance").glob("*.json"))) == 1
    assert len(list((batch_dir / "receipts").glob("*.json"))) == 1


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_is_rejected_without_contacting_target(status: int) -> None:
    with local_server([response_with_content("must not be reached")]) as (
        redirect_target,
        target_records,
    ):
        with local_server([redirect_response(status, redirect_target + "/sentinel")]) as (
            endpoint,
            initial_records,
        ):
            completed = subprocess.run(
                bridge_command(endpoint),
                input=b"exact prompt",
                capture_output=True,
                check=False,
                timeout=10,
            )

    assert len(initial_records) == 1
    assert target_records == []
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert b"LM Studio bridge failure" in completed.stderr
    assert str(status).encode("ascii") in completed.stderr


def test_redirect_failure_is_observed_and_later_attempt_continues(
    tmp_path: Path,
) -> None:
    with local_server([response_with_content("must not be reached")]) as (
        redirect_target,
        target_records,
    ):
        responses = [
            redirect_response(302, redirect_target + "/sentinel"),
            response_with_content(RAW_NORMAL),
        ]
        with local_server(responses) as (endpoint, initial_records):
            config = config_for(endpoint)
            proposer = LocalCommandProposer(
                command=bridge_command(endpoint),
                model=config.model_info(),
                timeout_seconds=10,
            )
            attempts = execute_live_observations(
                proposer=proposer,
                task_instruction="Move normally to ZONE_B.",
                scenario_document=scenario(),
                repeat=2,
                output_dir=tmp_path / "live",
                now=lambda: RUN_TIME,
            )

    failed, continued = attempts
    batch_dir = failed.observation_path.parents[1]
    assert len(initial_records) == 2
    assert target_records == []
    assert failed.observation.invocation_status == InvocationStatus.INVOCATION_FAILED
    assert failed.observation.raw_output_path is None
    assert failed.observation.phase2_provenance_path is None
    assert failed.observation.governance_receipt_id is None
    assert failed.phase2_result is None
    assert continued.observation.invocation_status == InvocationStatus.COMPLETED
    assert continued.phase2_result is not None
    assert continued.phase2_result.phase1_result is not None
    assert len(list((batch_dir / "observations").glob("*.json"))) == 2
    assert len(list((batch_dir / "raw").glob("*.txt"))) == 1
    assert len(list((batch_dir / "provenance").glob("*.json"))) == 1
    assert len(list((batch_dir / "receipts").glob("*.json"))) == 1
