"""Small vendor-neutral interface to an already-configured local CLI runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from phase2.provenance import ModelInfo


PROMPT_VERSION = "phase2_action_proposal_v1"
PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "phase2_action_proposal_v1.txt"
)


class LocalRuntimeError(RuntimeError):
    """The configured local command could not produce a raw response."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "LOCAL_RUNTIME_ERROR",
        exit_code: int | None = None,
        stderr: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.exit_code = exit_code
        self.stderr = stderr
        self.timeout_seconds = timeout_seconds

    def to_evidence(self) -> dict[str, object]:
        return {
            "category": self.category,
            "exit_code": self.exit_code,
            "stderr": self.stderr,
            "timeout_seconds": self.timeout_seconds,
        }


def load_prompt_template(path: Path = PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def render_prompt(task_instruction: str, template: str | None = None) -> str:
    prompt_template = template if template is not None else load_prompt_template()
    marker = "{{TASK_INSTRUCTION}}"
    if prompt_template.count(marker) != 1:
        raise ValueError("prompt template must contain exactly one task marker")
    return prompt_template.replace(marker, task_instruction)


@dataclass(frozen=True)
class LocalCommandProposer:
    """Call a local command that reads the prompt from stdin and writes raw output."""

    command: tuple[str, ...]
    model: ModelInfo
    timeout_seconds: float = 120.0

    def generate_rendered_prompt(self, rendered_prompt: str) -> str:
        """Submit a prompt and require the local CLI stdout contract to be UTF-8."""
        try:
            completed = subprocess.run(
                self.command,
                input=rendered_prompt.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise LocalRuntimeError(
                f"local runtime timed out after {self.timeout_seconds} seconds",
                stderr=stderr,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except OSError as exc:
            raise LocalRuntimeError(
                f"local runtime invocation failed: {exc}",
                stderr=str(exc),
            ) from exc
        if completed.returncode != 0:
            diagnostic = completed.stderr.decode(
                "utf-8", errors="replace"
            ).strip()
            raise LocalRuntimeError(
                f"local runtime exited with {completed.returncode}: {diagnostic}",
                exit_code=completed.returncode,
                stderr=diagnostic or None,
            )
        try:
            return completed.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LocalRuntimeError(
                "local runtime stdout is not valid UTF-8",
                category="LOCAL_RUNTIME_DECODE_ERROR",
            ) from exc

    def generate(self, task_instruction: str) -> str:
        return self.generate_rendered_prompt(render_prompt(task_instruction))
