from __future__ import annotations

import pytest

from phase2.adapter import AdapterReasonCode, FORBIDDEN_FIELDS, ParseStatus, adapt
from tests.phase2.helpers import RAW_NORMAL


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "Here is my proposal: " + RAW_NORMAL,
        "```json\n" + RAW_NORMAL + "\n```",
        RAW_NORMAL + " trailing text",
        RAW_NORMAL + RAW_NORMAL,
    ],
)
def test_complete_response_parse_failures(raw: str) -> None:
    result = adapt(raw)
    assert result.parse_status == ParseStatus.INVALID
    assert result.validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_NOT_JSON,
    )
    assert result.normalized_proposal is None


@pytest.mark.parametrize("raw", ["[]", "null", '"plain string"', "123", "true"])
def test_valid_json_non_object(raw: str) -> None:
    result = adapt(raw)
    assert result.validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_TOP_LEVEL_NOT_OBJECT,
    )


def test_duplicate_key_is_rejected_without_last_value_winning() -> None:
    raw = RAW_NORMAL.replace(
        '"speed":"NORMAL"', '"speed":"LOW","speed":"HIGH"'
    )
    result = adapt(raw)
    assert result.validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_DUPLICATE_KEY,
    )
    assert result.normalized_proposal is None
    assert result.raw_output == raw


def test_duplicate_key_inside_nested_object_is_still_rejected_first() -> None:
    raw = (
        '{"request_type":"ACTION","behavior":{"x":1,"x":2},'
        '"target":"ZONE_B","speed":"NORMAL"}'
    )
    assert adapt(raw).validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_DUPLICATE_KEY,
    )


@pytest.mark.parametrize("field", sorted(FORBIDDEN_FIELDS))
def test_every_frozen_forbidden_field_name_is_rejected(field: str) -> None:
    raw = RAW_NORMAL[:-1] + f',"{field}":"supplied-by-model"' + "}"
    assert adapt(raw).validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_FORBIDDEN_GOVERNANCE_FIELD,
    )


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (
            '{"request_type":"ACTION","behavior":"MOVE","target":"ZONE_B",'
            '"speed":"NORMAL","decision":"ALLOW"}',
            AdapterReasonCode.LLM_OUTPUT_FORBIDDEN_GOVERNANCE_FIELD,
        ),
        (
            '{"request_type":"ACTION","behavior":"MOVE","target":"ZONE_B",'
            '"speed":"NORMAL","Decision":"ALLOW"}',
            AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_FIELD,
        ),
        (
            '{"request_type":"ACTION","behavior":"MOVE","target":"ZONE_B",'
            '"speed":"NORMAL","notes":"x"}',
            AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_FIELD,
        ),
        (
            '{"request_type":"ACTION","behavior":"MOVE","target":"ZONE_B",'
            '"speed":"NORMAL","permission":"ALLOW"}',
            AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_FIELD,
        ),
        (
            '{"request_type":"ACTION","behavior":"MOVE","speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_MISSING_REQUIRED_FIELD,
        ),
        (
            '{"request_type":"ACTION","behavior":null,"target":"ZONE_B",'
            '"speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_INVALID_FIELD_TYPE,
        ),
        (
            '{"request_type":"ACTION","behavior":[],"target":"ZONE_B",'
            '"speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_INVALID_FIELD_TYPE,
        ),
        (
            '{"request_type":"START","behavior":"MOVE","target":"ZONE_B",'
            '"speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE,
        ),
        (
            '{"request_type":"ACTION","behavior":"TELEPORT","target":"ZONE_B",'
            '"speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE,
        ),
        (
            '{"request_type":"ACTION","behavior":"MOVE","target":"ZONE_C",'
            '"speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE,
        ),
        (
            '{"request_type":"ACTION","behavior":"MOVE","target":"ZONE_B",'
            '"speed":"MAXIMUM_PLUS"}',
            AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE,
        ),
    ],
)
def test_schema_and_vocabulary_failures(
    raw: str, reason: AdapterReasonCode
) -> None:
    result = adapt(raw)
    assert result.validation_reason_codes == (reason,)
    assert len(result.validation_reason_codes) == 1


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (
            '{"behavior":"MOVE","target":"ZONE_B","speed":"NORMAL",'
            '"decision":"ALLOW","notes":"x"}',
            AdapterReasonCode.LLM_OUTPUT_FORBIDDEN_GOVERNANCE_FIELD,
        ),
        (
            '{"behavior":"MOVE","target":"ZONE_B","speed":"NORMAL",'
            '"notes":"x"}',
            AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_FIELD,
        ),
        (
            '{"request_type":3,"behavior":"TELEPORT","target":"ZONE_B",'
            '"speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_INVALID_FIELD_TYPE,
        ),
        (
            '{"request_type":"START","behavior":"TELEPORT","target":"ZONE_B",'
            '"speed":"NORMAL"}',
            AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE,
        ),
    ],
)
def test_multiple_defects_use_frozen_fail_fast_precedence(
    raw: str, reason: AdapterReasonCode
) -> None:
    result = adapt(raw)
    assert result.validation_reason_codes == (reason,)


def test_duplicate_key_precedes_forbidden_field() -> None:
    raw = (
        '{"request_type":"ACTION","request_type":"REENTRY",'
        '"behavior":"MOVE","target":"ZONE_B","speed":"NORMAL",'
        '"decision":"ALLOW"}'
    )
    assert adapt(raw).validation_reason_codes == (
        AdapterReasonCode.LLM_OUTPUT_DUPLICATE_KEY,
    )
