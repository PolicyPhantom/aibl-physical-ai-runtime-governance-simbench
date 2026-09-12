"""Immutable Phase 4 values and closed parsing; no execution authorization."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from phase3.constants import PHYSICAL_FIELDS
from phase3.identity import canonical_bytes, canonical_sha256

SCHEMA_ID = "P4-DERIVED-INPUT-v1"
RULE_ID = "P4-DERIVATION-RULE-v1"
RECORD_RULE_ID = "P4-PHYSICAL-RECORD-SHA256-v1"
SPEC_ID = "P4-CORE-SCENARIO-SPEC-v1.0-FROZEN"
SPEC_SHA256 = "a7f9318adaf48b949efdf3723ca98017a692a010cea268af1297cff03a6395dc"
AUTH_PATH = "/context/authority/valid_until_tick"
REM_PATH = "/bundle/remediation/observed_at_tick"
RISK_PATH = "/context/risk_records/0/observed_at_tick"
PHYSICAL_PATHS = tuple(f"/physical_observations/{name}/observed_at_tick" for name in PHYSICAL_FIELDS)
DEPENDENT_PATHS = tuple(
    f"/physical_observations/{name}/{field}"
    for name in PHYSICAL_FIELDS for field in ("content_identity", "content_sha256")
)
APPLICATION_PATHS = (AUTH_PATH, REM_PATH, RISK_PATH) + PHYSICAL_PATHS
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "phase4_schemas" / "derived_input_v1.json"
CASE_PATH = Path(__file__).resolve().parents[1] / "phase4_scenarios" / "core_scenarios_v1.json"


class ContractError(ValueError):
    """A supplied value cannot represent the frozen contract."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_number(token):
    raise ContractError(f"non-canonical/inapplicable number: {token}")


def _integer(token):
    if token == "-0":
        raise ContractError("negative zero is not canonical")
    return int(token)


def parse_json(raw: bytes) -> Any:
    """Decode exact UTF-8 JSON; this integer-only contract rejects float syntax."""
    if type(raw) is not bytes:
        raise ContractError("JSON input must be bytes")
    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
                          parse_float=_reject_number, parse_constant=_reject_number,
                          parse_int=_integer)
    except (UnicodeError, ValueError) as exc:
        raise ContractError(str(exc)) from exc


def _json_value(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            _json_value(item)
        return
    raise ContractError("only JSON values with integer numbers are allowed")


@dataclass(frozen=True, slots=True)
class JsonSnapshot:
    """Canonical immutable bytes; each decoded value is a detached copy."""
    raw: bytes

    def __post_init__(self):
        value = parse_json(self.raw)
        _json_value(value)
        object.__setattr__(self, "raw", canonical_bytes(value, exclude_volatile=False))

    @classmethod
    def of(cls, value):
        _json_value(value)
        return cls(canonical_bytes(value, exclude_volatile=False))

    @property
    def value(self):
        return parse_json(self.raw)

    @property
    def sha256(self):
        return canonical_sha256(self.value, exclude_volatile=False)


@dataclass(frozen=True, slots=True)
class SourceMaterial:
    source_id: str
    path: str
    raw_sha256: str
    canonical_sha256: str | None = None
    raw_bytes: bytes = b""

    def __post_init__(self):
        if (type(self.source_id) is not str or type(self.path) is not str
                or type(self.raw_sha256) is not str or type(self.raw_bytes) is not bytes
                or (self.canonical_sha256 is not None and type(self.canonical_sha256) is not str)):
            raise ContractError("immutable source values required")


@dataclass(frozen=True, slots=True)
class BaselineSnapshot:
    source_baseline_id: str
    payload: JsonSnapshot
    source_materials: tuple[SourceMaterial, ...]
    source_baseline_raw_sha256: str | None = None

    def __post_init__(self):
        if type(self.payload) is not JsonSnapshot:
            raise ContractError("immutable baseline payload required")
        materials = tuple(self.source_materials)
        if any(type(m) is not SourceMaterial for m in materials):
            raise ContractError("source material values required")
        object.__setattr__(self, "source_materials", materials)


@dataclass(frozen=True, slots=True)
class ApplicationTarget:
    field_path: str
    old_value: int
    requested_new_value: int
    semantic_change_expected: bool

    def __post_init__(self):
        if self.field_path not in APPLICATION_PATHS:
            raise ContractError("unapproved application path")
        if type(self.old_value) is not int or type(self.requested_new_value) is not int:
            raise ContractError("timestamp must be integer, not bool")
        if type(self.semantic_change_expected) is not bool:
            raise ContractError("semantic flag must be bool")
        if self.semantic_change_expected != (self.old_value != self.requested_new_value):
            raise ContractError("semantic flag mismatch")


@dataclass(frozen=True, slots=True)
class DependentIdentityRule:
    source_payload_path: str
    dependent_field_path: str
    recomputation_rule_id: str = RECORD_RULE_ID

    def __post_init__(self):
        if (self.dependent_field_path not in DEPENDENT_PATHS
                or self.source_payload_path != self.dependent_field_path.rsplit("/", 1)[0]
                or self.recomputation_rule_id != RECORD_RULE_ID):
            raise ContractError("unapproved dependent identity rule")


@dataclass(frozen=True, slots=True)
class DerivedInputProvenance:
    envelope: JsonSnapshot

    def __post_init__(self):
        if type(self.envelope) is not JsonSnapshot:
            raise ContractError("immutable envelope required")
        validate_envelope(self.envelope.value)


@dataclass(frozen=True, slots=True)
class DerivedInput:
    """Candidate derivation; it carries no external approval."""
    payload: JsonSnapshot
    provenance: DerivedInputProvenance


@dataclass(frozen=True, slots=True)
class VerifiedDerivedInput:
    """Reconstruction result, never proof of external input authorization."""
    baseline: BaselineSnapshot
    payload: JsonSnapshot
    provenance: DerivedInputProvenance


@dataclass(frozen=True, slots=True)
class P4CaseSpec:
    case_id: str
    order: int
    parameter_family: str
    boundary_class: str
    parameter_value: int | None
    source_baseline_id: str
    expected_decision: str
    expected_reason: str
    expected_state: str
    expected_effect: str | None
    computed_expected_freshness: str
    repetitions: int = 3

    @property
    def derived_input_id(self):
        return self.case_id.replace("P4-", "P4-DERIVED-", 1)


@dataclass(frozen=True, slots=True)
class P4Slot:
    case_id: str
    attempt_number: int
    batch_id: str
    slot_id: str


@dataclass(frozen=True, slots=True)
class P4Plan:
    identity: str
    cases: tuple[P4CaseSpec, ...]
    slots: tuple[P4Slot, ...]

    def __post_init__(self):
        object.__setattr__(self, "cases", tuple(self.cases))
        object.__setattr__(self, "slots", tuple(self.slots))


@dataclass(frozen=True, slots=True)
class P4AttemptSpec:
    slot: P4Slot
    case: P4CaseSpec
    bindings: JsonSnapshot


@dataclass(frozen=True, slots=True)
class P4AttemptResult:
    spec: P4AttemptSpec
    core_result: JsonSnapshot


@dataclass(frozen=True, slots=True)
class P4Reconciliation:
    result: JsonSnapshot


@dataclass(frozen=True, slots=True)
class P4SessionResult:
    result: JsonSnapshot


def frozen_cases() -> tuple[P4CaseSpec, ...]:
    """Predeclared values from the frozen spec; never observed-result derived."""
    action = "ALL_CURRENT_CONDITIONS_SATISFIED"
    reentry = "ALL_CURRENT_REENTRY_CONDITIONS_SATISFIED"
    rows = [
        ("CTRL-01", "CONTROL", "CONTROL", None, "P3-CTRL-01", "ALLOW", action, "RUNNING", "MOVED_TO_ZONE_B", "CURRENT"),
        ("CTRL-02", "CONTROL", "CONTROL", None, "P3-CTRL-02", "ALLOW", reentry, "RUNNING", "STATE_RESTORATION_ONLY", "CURRENT"),
    ]
    for family, values, baseline in (
        ("AUTH", (999, 1000, 1001), "P3-CTRL-01"),
        ("REM", (994, 995, 996), "P3-CTRL-02"),
        ("PHY", (998, 999, 1000), "P3-CTRL-01"),
        ("RISK", (994, 995, 996), "P3-CTRL-01"),
    ):
        for index, (boundary, value) in enumerate(zip(("STRICT_SIDE", "BOUNDARY", "RELAXED_SIDE"), values), 1):
            stale = index == 1 or (family == "AUTH" and index == 2)
            reason = ({"AUTH": "CURRENT_AUTHORITY_STALE", "REM": "REENTRY_REMEDIATION_EVIDENCE_STALE",
                       "PHY": "AGENT_ACTUAL_ZONE_STALE", "RISK": "CURRENT_RISK_NOT_ESTABLISHED"}[family]
                      if stale else reentry if family == "REM" else action)
            rows.append((f"{family}-{index:02}", family, boundary, value, baseline,
                         "HOLD" if stale else "ALLOW", reason,
                         "SUSPENDED" if stale and family == "REM" else "RUNNING",
                         None if stale else "STATE_RESTORATION_ONLY" if family == "REM" else "MOVED_TO_ZONE_B",
                         "STALE" if stale else "CURRENT"))
    return tuple(P4CaseSpec("P4-" + row[0], order, *row[1:]) for order, row in enumerate(rows, 1))


def case_document():
    from dataclasses import asdict
    return {"schema_id": "P4-CORE-SCENARIOS-v1", "frozen_spec_id": SPEC_ID,
            "frozen_spec_sha256": SPEC_SHA256, "claim_boundary": "SIMULATION_LIMITED",
            "logical_time": {"evaluation": 1000, "command": 1000, "verification": 1001},
            "repetitions_per_case": 3, "total_slots": 42, "hard_ceiling": 60,
            "cases": [dict(asdict(c), derived_input_id=c.derived_input_id) for c in frozen_cases()]}


def load_core_cases(raw: bytes) -> tuple[P4CaseSpec, ...]:
    value = parse_json(raw)
    # Canonical byte comparison also distinguishes booleans from integers.
    if canonical_bytes(value, exclude_volatile=False) != canonical_bytes(case_document(), exclude_volatile=False):
        raise ContractError("core-case representation differs from frozen specification")
    return frozen_cases()


def _schema_validate(value, schema, root, path="$"):
    """The small closed vocabulary used by our local schema; no network refs."""
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ContractError("external schema reference prohibited")
        return _schema_validate(value, root["$defs"][ref.split("/")[-1]], root, path)
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    if "type" in schema and type(value) is not types[schema["type"]]:
        raise ContractError(f"{path}: invalid type")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise ContractError(f"{path}: constant mismatch")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(f"{path}: value not approved")
    if type(value) is dict:
        properties = schema.get("properties", {})
        if not set(schema.get("required", ())).issubset(value):
            raise ContractError(f"{path}: missing fields")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ContractError(f"{path}: unknown fields")
        for key, item in value.items():
            if key in properties:
                _schema_validate(item, properties[key], root, path + "/" + key)
    elif type(value) is list:
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            raise ContractError(f"{path}: array size")
        if schema.get("uniqueItems") and len({canonical_bytes(v, exclude_volatile=False) for v in value}) != len(value):
            raise ContractError(f"{path}: duplicate item")
        for item in value:
            _schema_validate(item, schema.get("items", {}), root, path + "[]")
    elif type(value) is str:
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ContractError(f"{path}: string format")
    elif type(value) is int:
        if value < schema.get("minimum", value):
            raise ContractError(f"{path}: integer range")


def validate_envelope(value):
    _json_value(value)
    schema = parse_json(SCHEMA_PATH.read_bytes())
    _schema_validate(value, schema, schema)
    provenance = value["provenance"]
    targets = provenance["application_targets"]
    if len({t["field_path"] for t in targets}) != len(targets):
        raise ContractError("duplicate application path")
    for target in targets:
        ApplicationTarget(**target)
    rules = provenance["dependent_identity_rules"]
    if len({r["dependent_field_path"] for r in rules}) != len(rules):
        raise ContractError("duplicate dependent path")
    for rule in rules:
        DependentIdentityRule(**rule)
    sources = provenance["source_materials"]
    if len({s["source_id"] for s in sources}) != len(sources):
        raise ContractError("duplicate source")
    return value


def parse_envelope(raw: bytes) -> DerivedInputProvenance:
    value = parse_json(raw)
    validate_envelope(value)
    return DerivedInputProvenance(JsonSnapshot.of(value))
