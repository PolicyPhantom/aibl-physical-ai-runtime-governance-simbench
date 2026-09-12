"""Small immutable Phase 3 result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkspaceAuthorization:
    """Immutable approval data asserted by operator-facing orchestration.

    Possession of this value is not proof of human authorization. The core only
    enforces the supplied boundary and does not construct it from scenario data.
    """

    authorized_workspace_root: Path
    authorization_id: str
    protected_roots: tuple[Path, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorized_workspace_root", Path(self.authorized_workspace_root))
        object.__setattr__(
            self,
            "protected_roots",
            tuple(Path(item) for item in self.protected_roots),
        )


@dataclass(frozen=True)
class AdapterResult:
    status: str
    reason: str | None
    raw_sha256: str
    normalized_proposal: dict[str, str] | None
    duplicate_key: str | None = None
    duplicate_occurrences: int = 0
    source_classification: str | None = None
    phase3_classification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionResult:
    decision: str
    reason: str
    evaluated_at_tick: int
    enforcement: str = "NOT_PERFORMED"
    command_status: str | None = None
    physical_action_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceVerification:
    completeness: str
    completeness_reason: str | None
    present_file_integrity: str
    integrity_reason: str | None
    full_set_integrity: str
    missing_paths: tuple[str, ...] = ()
    mismatched_paths: tuple[str, ...] = ()
    unexpected_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("missing_paths", "mismatched_paths", "unexpected_paths"):
            value[key] = list(value[key])
        return value


@dataclass(frozen=True)
class PhysicalResult:
    command_status: str | None
    command_issued_at_tick: int | None
    expected_state: str | None
    actual_state: str | None
    verification_tick: int
    event: str | None
    execution_result: str
    initial_state: str
    final_state: str
    physical_action_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
