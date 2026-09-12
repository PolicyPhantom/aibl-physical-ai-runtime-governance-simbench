"""Frozen Phase 3 constants and closed vocabularies."""

from types import MappingProxyType

T_EVAL = 1000
T_COMMAND = 1000
T_VERIFY = 1001

CORE_SCOPE = "MOVE / ZONE_B"
CORE_POLICY_VERSION = "1.0"
SOURCE_PRIORITY_REGISTRY_ID = "P3-SOURCE-PRIORITY-REGISTRY-v1"
SOURCE_PRIORITY_REGISTRY_VERSION = "1.0"
SOURCE_PRIORITY_REGISTRY_FIELDS = frozenset({"registry_id", "version", "rules"})

AUTHORITY_ID = "AUTH-P3-001"
AUTHORITY_SOURCE_ID = "AUTHORITY-REGISTRY-01"
AUTHORITY_FIELDS = frozenset(
    {
        "authority_id",
        "status",
        "valid_from_tick",
        "valid_until_tick",
        "revoked",
        "superseded_by",
        "scope_request_type",
        "scope_behavior",
        "scope_target",
        "source_id",
    }
)
POLICY_ID = "P3-POLICY-001"
POLICY_SOURCE_ID = "POLICY-REGISTRY-01"
POLICY_FIELDS = frozenset(
    {
        "policy_id",
        "version",
        "effective_from_tick",
        "effective_until_tick",
        "superseded_by",
        "applicable_behavior",
        "applicable_target",
        "source_id",
    }
)
OVERSIGHT_ASSIGNMENT_ID = "OVERSIGHT-P3-001"
OVERSIGHT_SOURCE_ID = "OVERSIGHT-REGISTRY-01"
OVERSIGHT_MAX_AGE_TICKS = 5
OVERSIGHT_FIELDS = frozenset(
    {
        "oversight_assignment_id",
        "status",
        "confirmed_at_tick",
        "max_age_ticks",
        "scope",
        "source_id",
    }
)
RISK_MAX_AGE_TICKS = 5
RISK_FIELDS = frozenset(
    {
        "risk_observation_id",
        "current_risk_state",
        "observed_at_tick",
        "max_age_ticks",
        "source_id",
        "source_authority_rank",
        "scope",
    }
)
RISK_SOURCE_CONTRACTS = MappingProxyType(
    {
        "RISK-SOURCE-01": ("RISK-P3-001", 10),
        "RISK-SOURCE-ALPHA": ("RISK-P3-ALPHA", 10),
        "RISK-SOURCE-BETA": ("RISK-P3-BETA", 10),
    }
)

RUNNING = "RUNNING"
SUSPENDED = "SUSPENDED"

ALLOW = "ALLOW"
RESTRICT = "RESTRICT"
HOLD = "HOLD"
DENY = "DENY"
VALID = "VALID"
INVALID = "INVALID"
NOT_PERFORMED = "NOT_PERFORMED"

SCENARIO_ORDER = (
    "P3-CTRL-01",
    "P3-CTRL-02",
    "P3-A-01",
    "P3-A-02",
    "P3-B-01",
    "P3-B-02",
    "P3-C-01",
    "P3-C-02",
    "P3-D-01",
    "P3-D-02",
    "P3-E-01",
    "P3-E-02",
)

# These identities bind each full frozen case object, including expected outcome.
# The runner uses the trusted maps below after validation; it never derives its
# execution contract from caller-supplied case fields.
CORE_SCENARIO_SHA256 = MappingProxyType(
    {
        "P3-CTRL-01": "016f590bae43058464b68927eff738b75b51c036d17105dcff792ba53479986b",
        "P3-CTRL-02": "c14dc249d0e8b7de81f5b4dd1b4aae3edaa6aefd1b94cb0dc1292e6f338ea0bb",
        "P3-A-01": "5580f82886664456d7afc4a942a6a8a289b04021f9e727e3c93b166430ad6d75",
        "P3-A-02": "31460a4222a62ac24f8c415e166556a9dff37a7abde7ad18b79e80113236cabb",
        "P3-B-01": "bca1342b50dfbc6a85aede6c62a334d37aa14b7be609767f1d0f61b13b326fe3",
        "P3-B-02": "5f305aaeebfe85d760bab624266583392ba515b7a6934a0c875122af37d3dbcc",
        "P3-C-01": "f476bd775a37af8ee87e69930540892fc5490ebda021ff6462a828f1baa819d4",
        "P3-C-02": "8fd78de310145072ce1bb71e5639573f8174cd83753400ddf8009e7f26a1f92a",
        "P3-D-01": "285b9ca10ce22682c3c9f662873086fbe41937ab46a40cf0424b42e87b207c19",
        "P3-D-02": "576c898c33f3d5ff93a8b7fe4927f3f0c059d73041f59beed6ba7e738b0fcf86",
        "P3-E-01": "e960441508fb047672ebd14933167c73f8e7101c6772bf6c1166e657726f2557",
        "P3-E-02": "6fdbd8fce5ae13164e96e118fa70edfebb36b44bac617feeb2144d2b34cc283a",
    }
)
CORE_SCENARIO_PROPOSAL_FIXTURE = MappingProxyType(
    {
        "P3-CTRL-01": "action_valid",
        "P3-CTRL-02": "reentry_valid",
        "P3-A-01": "duplicate_key",
        "P3-A-02": "unsupported_value",
        "P3-B-01": "action_valid",
        "P3-B-02": "action_valid",
        "P3-C-01": "reentry_valid",
        "P3-C-02": "reentry_valid",
        "P3-D-01": "reentry_valid",
        "P3-D-02": "reentry_valid",
        "P3-E-01": "action_valid",
        "P3-E-02": "action_valid",
    }
)
CORE_SCENARIO_INITIAL_STATE = MappingProxyType(
    {
        "P3-CTRL-01": "RUNNING",
        "P3-CTRL-02": "SUSPENDED",
        "P3-A-01": "RUNNING",
        "P3-A-02": "RUNNING",
        "P3-B-01": "RUNNING",
        "P3-B-02": "RUNNING",
        "P3-C-01": "SUSPENDED",
        "P3-C-02": "SUSPENDED",
        "P3-D-01": "SUSPENDED",
        "P3-D-02": "SUSPENDED",
        "P3-E-01": "RUNNING",
        "P3-E-02": "RUNNING",
    }
)
CORE_SCENARIO_PRIMARY_DELTA = MappingProxyType(
    {
        "P3-CTRL-01": "NONE",
        "P3-CTRL-02": "NONE",
        "P3-A-01": "SECOND_TARGET_OCCURRENCE",
        "P3-A-02": "SPEED_NORMAL_TO_TURBO",
        "P3-B-01": "AUTHORITY_VALID_UNTIL_1100_TO_1000",
        "P3-B-02": "EQUAL_AUTHORITY_RISK_CONFLICT",
        "P3-C-01": "DECISION_RECEIPT_MISSING",
        "P3-C-02": "DECISION_RECEIPT_HASH_MISMATCH",
        "P3-D-01": "REMEDIATION_OBSERVED_TICK_1000_TO_994",
        "P3-D-02": "RISK_ACCEPTABLE_TO_PROHIBITED",
        "P3-E-01": "TARGET_ZONE_OCCUPANCY_ABSENT",
        "P3-E-02": "ACTUAL_STATE_ZONE_B_TO_ZONE_A_AT_T_VERIFY",
    }
)
PROPOSAL_RAW_SHA256 = MappingProxyType(
    {
        "action_valid": "ba08aa8d968150679a5ed8344064058838d070dad2e9affe606f1bde25ee8645",
        "duplicate_key": "fd2ac3f5f6159fbd9e5c7dd186eadfd4d558d1e221d17c6fa8050b799551c5f5",
        "reentry_valid": "66ab67ddf6e7de124d5585c65470f7c8d3f31d069d0cc860c8125c1af0aba044",
        "unsupported_value": "de89f0be9b226852af4cf484ac6d05aa837b5f39096525e906fab7ee0680a146",
    }
)
BASELINE_FIXTURE_SHA256 = MappingProxyType(
    {
        "common_context": "7f3ed27edae65682c2b2af8262f9ee97f907b357c01a3a914fb73cfd7bf36146",
        "physical_safe": "7190eded705a442d31a03acae29d7c56d930abe481b4690945df9eb49690af72",
        "reentry_current": "285eafd146a01288949c6ed9cb407e5e33efae6904131fb2020001bed6803588",
    }
)
EVIDENCE_VERIFICATION_SHA256 = MappingProxyType(
    {
        "P3-C-01": "d9e448cde0db5791cb5b95c79c2f9da1d2c0584e6bcef2a7b82864c0feaceaaf",
        "P3-C-02": "ae12845d177001bbb36a1d305111f352ed9428c20a6445ae04322f31ac7a97b3",
    }
)

PROPOSAL_FIELDS = frozenset({"request_type", "behavior", "target", "speed"})
REQUEST_TYPES = frozenset({"ACTION", "REENTRY"})
PROPOSAL_VOCABULARY = MappingProxyType({
    "behavior": frozenset({"MOVE", "LIFT"}),
    "target": frozenset({"ZONE_B", "HUMAN_ZONE"}),
    "speed": frozenset({"LOW", "NORMAL", "HIGH"}),
})

PHYSICAL_FIELDS = (
    "agent_actual_zone",
    "agent_motion_state",
    "target_zone_occupancy",
    "route_clearance",
    "human_proximity_status",
    "actuator_readiness",
    "safety_interlock_status",
)
PHYSICAL_RECORD_FIELDS = frozenset(
    {
        "value",
        "source_id",
        "observed_at_tick",
        "max_age_ticks",
        "scope",
        "currentness_rule_id",
        "content_identity",
        "content_sha256",
    }
)
PHYSICAL_SOURCE_IDS = MappingProxyType(
    {
        "agent_actual_zone": "POSITION-SENSOR-01",
        "agent_motion_state": "MOTION-SENSOR-01",
        "target_zone_occupancy": "ZONE-B-SENSOR-01",
        "route_clearance": "ROUTE-SENSOR-01",
        "human_proximity_status": "PROXIMITY-SENSOR-01",
        "actuator_readiness": "ACTUATOR-STATUS-01",
        "safety_interlock_status": "SAFETY-INTERLOCK-01",
    }
)
PHYSICAL_MAX_AGE_TICKS = 1
PHYSICAL_CURRENTNESS_RULE_ID = "P3-FRESHNESS-PHYSICAL-001"
PHYSICAL_SAFE_VALUES = MappingProxyType({
    "agent_actual_zone": "ZONE_A",
    "agent_motion_state": "STATIONARY",
    "target_zone_occupancy": "CLEAR",
    "route_clearance": "CLEAR",
    "human_proximity_status": "NONE_DETECTED",
    "actuator_readiness": "READY",
    "safety_interlock_status": "CLEAR",
})
PHYSICAL_CONTENT_SHA256 = MappingProxyType({
    "agent_actual_zone": (
        "2edb44ee420c68594449a7ca0bf23d1dc8a08fa45485cdb0c1ce03473573dd94"
    ),
    "agent_motion_state": (
        "cec8019fb274ad5b321b63cedb3fc791d4625b5c5802d9db30d1852ac4ea9beb"
    ),
    "target_zone_occupancy": (
        "bf7cc69aa53d4ca327e793ae54aaa30eb164504d716cc1d78c6b4803537d35a7"
    ),
    "route_clearance": (
        "335d3c94c4208df9adc922a2aa32e42f3bd6f67db53d9f798fafa71541b5c329"
    ),
    "human_proximity_status": (
        "e6b8012986bc2f570010ad4f237912efba8a2a8a689f8435428f0458b328a108"
    ),
    "actuator_readiness": (
        "760931b5730e08ffdd9f844e83fdfa671e5eca78f8d602ab0b7709298a8acfa1"
    ),
    "safety_interlock_status": (
        "43d1c0807c8055073626a728216cef726204d290dac34e46a905c5e52cafa288"
    ),
})
PHYSICAL_PROHIBITED_VALUES = MappingProxyType({
    "agent_motion_state": frozenset({"UNCONTROLLED_MOTION"}),
    "target_zone_occupancy": frozenset({"OCCUPIED"}),
    "route_clearance": frozenset({"BLOCKED"}),
    "human_proximity_status": frozenset({"HUMAN_PRESENT"}),
    "actuator_readiness": frozenset({"NOT_READY"}),
    "safety_interlock_status": frozenset({"BLOCKED"}),
})

REENTRY_ELEMENTS = (
    "normalized_request",
    "authority",
    "policy",
    "risk_records",
    "oversight",
    "operational_physical_conditions",
    "remediation",
    "evidence_verification",
    "material_condition_changes",
    "pre_decision_operational_state",
)
SUSPENSION_EVENT_ID = "SUSPENSION-P3-001"
SUSPENSION_INTERVAL_START_TICK = 990
REMEDIATION_SOURCE_ID = "REMEDIATION-REVIEW-01"
REMEDIATION_MAX_AGE_TICKS = 5
REMEDIATION_FIELDS = frozenset(
    {
        "suspension_event_id",
        "resolution_status",
        "observed_at_tick",
        "max_age_ticks",
        "source_id",
        "cause_binding_valid",
    }
)
MATERIAL_CHANGE_SOURCE_ID = "CHANGE-REVIEW-01"
MATERIAL_CHANGE_FIELDS = frozenset(
    {
        "suspension_event_id",
        "interval_start_tick",
        "interval_end_tick",
        "reviewed_at_tick",
        "material_changes_complete",
        "source_id",
    }
)

VOLATILE_FIELDS = frozenset(
    {
        "formal_session_id",
        "case_batch_id",
        "run_id",
        "attempt_number",
        "execution_timestamp",
        "absolute_evidence_path",
    }
)

SCENARIO_RESULT_MUST_MATCH_FIELDS = (
    "scenario_id",
    "raw_sha256",
    "perturbation_identity",
    "adapter",
    "normalized_proposal",
    "governance",
    "verification",
    "enforcement",
    "command_status",
    "physical_result",
    "physical_action_count",
    "receipt_present",
    "initial_state",
    "final_state",
    "followup",
    "decision_basis",
    "decision_identity",
)

PROTECTED_OUTPUT_PARTS = frozenset(
    {"outputs", "phase3_trusted", ".pytest_cache", "__pycache__"}
)
