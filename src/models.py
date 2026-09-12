"""Small, explicit data models for the deterministic simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Decision(StrEnum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"
    HOLD = "HOLD"
    DENY = "DENY"


class ExecutionResultCode(StrEnum):
    EXECUTED = "EXECUTED"
    EXECUTED_WITH_RESTRICTIONS = "EXECUTED_WITH_RESTRICTIONS"
    HELD = "HELD"
    BLOCKED = "BLOCKED"


class OperationalState(StrEnum):
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"


class RequestType(StrEnum):
    ACTION = "ACTION"
    REENTRY = "REENTRY"


class ReasonCode(StrEnum):
    ALL_CURRENT_CONDITIONS_SATISFIED = "ALL_CURRENT_CONDITIONS_SATISFIED"
    HUMAN_SAFETY_ZONE_PROHIBITED = "HUMAN_SAFETY_ZONE_PROHIBITED"
    AUTHORITY_STALE = "AUTHORITY_STALE"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    POLICY_NOT_APPLICABLE = "POLICY_NOT_APPLICABLE"
    OVERSIGHT_UNAVAILABLE = "OVERSIGHT_UNAVAILABLE"
    BEHAVIOR_OUTSIDE_SCOPE = "BEHAVIOR_OUTSIDE_SCOPE"
    BEHAVIOR_SCOPE_UNRESOLVED = "BEHAVIOR_SCOPE_UNRESOLVED"
    ASSURANCE_NOT_CURRENT = "ASSURANCE_NOT_CURRENT"
    OPERATING_CONDITION_PROHIBITED = "OPERATING_CONDITION_PROHIBITED"
    OPERATING_CONDITION_UNRESOLVED = "OPERATING_CONDITION_UNRESOLVED"
    RISK_STATE_REQUIRES_HOLD = "RISK_STATE_REQUIRES_HOLD"
    SPEED_RESTRICTION_REQUIRED = "SPEED_RESTRICTION_REQUIRED"
    OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY = (
        "OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY"
    )
    REENTRY_NOT_APPLICABLE_WHILE_RUNNING = "REENTRY_NOT_APPLICABLE_WHILE_RUNNING"
    REENTRY_REVALIDATION_FAILED = "REENTRY_REVALIDATION_FAILED"
    REENTRY_REVALIDATION_PASSED = "REENTRY_REVALIDATION_PASSED"
    INVALID_REQUEST = "INVALID_REQUEST"


@dataclass(frozen=True)
class ActionProposal:
    request_type: str | None
    behavior: str | None
    target: str | None
    speed: str | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ActionProposal:
        return cls(
            request_type=value.get("request_type"),
            behavior=value.get("behavior"),
            target=value.get("target"),
            speed=value.get("speed"),
        )

    def is_valid(self) -> bool:
        required = (self.request_type, self.behavior, self.target, self.speed)
        return (
            all(isinstance(item, str) and bool(item) for item in required)
            and self.request_type in {item.value for item in RequestType}
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceContext:
    evaluation_time: str
    assurance_status: str
    authority_status: str
    policy_status: str
    evidence_status: str
    operating_condition: str
    risk_state: str
    oversight_status: str
    behavior_scope: tuple[str, ...]
    behavior_scope_status: str
    operational_state: OperationalState
    policy_version: str
    human_zone_prohibited: bool | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> GovernanceContext:
        return cls(
            evaluation_time=value["evaluation_time"],
            assurance_status=value["assurance_status"],
            authority_status=value["authority_status"],
            policy_status=value["policy_status"],
            evidence_status=value["evidence_status"],
            operating_condition=value["operating_condition"],
            risk_state=value["risk_state"],
            oversight_status=value["oversight_status"],
            behavior_scope=tuple(value["behavior_scope"]),
            behavior_scope_status=value["behavior_scope_status"],
            operational_state=OperationalState(value["operational_state"]),
            policy_version=value["policy_version"],
            human_zone_prohibited=value.get("human_zone_prohibited"),
        )

    def has_required_governance_input(self) -> bool:
        """Reject omission instead of converting required prohibition input to false."""
        return isinstance(self.human_zone_prohibited, bool)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["behavior_scope"] = list(self.behavior_scope)
        result["operational_state"] = self.operational_state.value
        return result


@dataclass(frozen=True)
class PermissionDecision:
    decision: Decision
    reason_codes: tuple[ReasonCode, ...]
    restrictions: tuple[dict[str, str], ...]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_codes": [item.value for item in self.reason_codes],
            "restrictions": [dict(item) for item in self.restrictions],
            "evaluated_at": self.evaluated_at,
        }


@dataclass(frozen=True)
class EnforcementResult:
    execution_result: ExecutionResultCode
    applied_restrictions: tuple[dict[str, str], ...] = ()
    executed_request: dict[str, Any] | None = None
    action_effect: str | None = None

    @property
    def physical_action_performed(self) -> bool:
        return self.execution_result in {
            ExecutionResultCode.EXECUTED,
            ExecutionResultCode.EXECUTED_WITH_RESTRICTIONS,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_result": self.execution_result.value,
            "applied_restrictions": [dict(item) for item in self.applied_restrictions],
            "executed_request": self.executed_request,
            "action_effect": self.action_effect,
            "physical_action_performed": self.physical_action_performed,
        }


@dataclass(frozen=True)
class TransitionResult:
    final_state: OperationalState
    reentry_outcome: str | None = None
    outcome_reason_codes: tuple[ReasonCode, ...] = field(default_factory=tuple)
