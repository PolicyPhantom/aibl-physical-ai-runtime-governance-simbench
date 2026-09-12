"""Thin stateless transport bridge for the frozen local LM Studio endpoint."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from phase2.class_b_config import (
    ClassBConfig,
    FROZEN_CLASS_B_CONFIG,
    structured_output_recovery_config,
)


class BridgeError(RuntimeError):
    """No usable UTF-8 model content reached the Phase 2 adapter boundary."""


class RejectRedirectHandler(HTTPRedirectHandler):
    """Fail the original request instead of issuing a redirect request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(
            req.full_url,
            code,
            "HTTP redirects are prohibited",
            headers,
            fp,
        )


def _open_without_redirects(request: Request, *, timeout: float):
    """Create a fresh stateless opener that cannot follow a Location target."""
    return build_opener(RejectRedirectHandler()).open(request, timeout=timeout)


def _decode_envelope(response_body: bytes) -> dict[str, object]:
    try:
        response_text = response_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BridgeError("response body is not valid UTF-8") from exc
    try:
        envelope = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise BridgeError("response envelope is not valid JSON") from exc
    if not isinstance(envelope, dict):
        raise BridgeError("response envelope must be a JSON object")
    return envelope


def _unwrap_content(response_body: bytes) -> str:
    envelope = _decode_envelope(response_body)
    choices = envelope.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise BridgeError("response envelope must contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise BridgeError("response choice must be an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise BridgeError("response choice must contain a message object")
    if "content" not in message:
        raise BridgeError("response message is missing content")
    content = message["content"]
    if not isinstance(content, str):
        raise BridgeError("response message content must be a string")
    return content


def request_model_content(
    rendered_prompt: str,
    *,
    config: ClassBConfig = FROZEN_CLASS_B_CONFIG,
    opener: Callable[..., object] = _open_without_redirects,
) -> str:
    """Make exactly one request and unwrap only choices[0].message.content."""
    request_body = config.request_body(rendered_prompt)
    encoded_body = json.dumps(
        request_body,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        config.request_url,
        data=encoded_body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=config.http_timeout_seconds) as response:
            response_body = response.read()
    except HTTPError as exc:
        raise BridgeError(f"LM Studio returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise BridgeError(f"LM Studio transport failure: {exc}") from exc
    if not isinstance(response_body, bytes):
        raise BridgeError("LM Studio response body must be bytes")
    return _unwrap_content(response_body)


def main(*, config: ClassBConfig = FROZEN_CLASS_B_CONFIG) -> int:
    try:
        try:
            rendered_prompt = sys.stdin.buffer.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BridgeError("stdin prompt is not valid UTF-8") from exc
        content = request_model_content(rendered_prompt, config=config)
        try:
            encoded_content = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise BridgeError("model content cannot be represented as UTF-8") from exc
    except BridgeError as exc:
        sys.stderr.write(f"LM Studio bridge failure: {exc}\n")
        return 2

    sys.stdout.buffer.write(encoded_content)
    return 0


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transport one exact rendered prompt to local LM Studio."
    )
    parser.add_argument("--structured-output-recovery", action="store_true")
    parser.add_argument("--expected-schema-sha256")
    args = parser.parse_args(argv)

    if args.expected_schema_sha256 and not args.structured_output_recovery:
        parser.error(
            "--expected-schema-sha256 requires --structured-output-recovery"
        )

    config = (
        structured_output_recovery_config()
        if args.structured_output_recovery
        else FROZEN_CLASS_B_CONFIG
    )
    if (
        args.expected_schema_sha256
        and config.structured_output is not None
        and config.structured_output.schema_sha256
        != args.expected_schema_sha256
    ):
        sys.stderr.write(
            "LM Studio bridge failure: structured-output schema digest mismatch\n"
        )
        return 2
    return main(config=config)


if __name__ == "__main__":
    raise SystemExit(cli())
