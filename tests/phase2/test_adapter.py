from __future__ import annotations

import pytest

from phase2.adapter import AdapterReasonCode, ParseStatus, adapt
from tests.phase2.helpers import RAW_NORMAL


def test_valid_normal_object() -> None:
    result = adapt(RAW_NORMAL)
    assert result.parse_status == ParseStatus.VALID
    assert result.validation_reason_codes == ()
    assert result.normalized_proposal is not None
    assert result.normalized_proposal.to_dict() == {
        "request_type": "ACTION",
        "behavior": "MOVE",
        "target": "ZONE_B",
        "speed": "NORMAL",
    }
    assert result.raw_output == RAW_NORMAL


def test_outer_whitespace_is_allowed_and_preserved() -> None:
    raw = " \r\n\t" + RAW_NORMAL + "\n "
    result = adapt(raw)
    assert result.parse_status == ParseStatus.VALID
    assert result.raw_output == raw


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("request_type", "", AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE),
        ("request_type", "action", AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE),
        ("request_type", "ACTION ", AdapterReasonCode.LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE),
        ("behavior", "", AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE),
        ("behavior", "move", AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE),
        ("target", "ZONE_B ", AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE),
        ("speed", "", AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE),
        ("speed", "LOW ", AdapterReasonCode.LLM_OUTPUT_UNRECOGNIZED_VALUE),
    ],
)
def test_field_specific_string_semantics(
    field: str, value: str, reason: AdapterReasonCode
) -> None:
    raw = (
        '{"request_type":"ACTION","behavior":"MOVE",'
        '"target":"ZONE_B","speed":"LOW"}'
    )
    import json

    value_object = json.loads(raw)
    value_object[field] = value
    result = adapt(json.dumps(value_object))
    assert result.parse_status == ParseStatus.INVALID
    assert result.validation_reason_codes == (reason,)


def test_lift_is_recognized_by_adapter() -> None:
    raw = RAW_NORMAL.replace('"MOVE"', '"LIFT"')
    result = adapt(raw)
    assert result.parse_status == ParseStatus.VALID
    assert result.normalized_proposal is not None
    assert result.normalized_proposal.behavior == "LIFT"


def test_reserved_multiple_action_reason_is_never_used_by_v1_adapter() -> None:
    samples = [
        RAW_NORMAL + RAW_NORMAL,
        "[" + RAW_NORMAL + "," + RAW_NORMAL + "]",
        RAW_NORMAL.replace('"speed":"NORMAL"', '"speed":"LOW","speed":"HIGH"'),
    ]
    for raw in samples:
        assert (
            AdapterReasonCode.LLM_OUTPUT_MULTIPLE_ACTIONS_AMBIGUOUS
            not in adapt(raw).validation_reason_codes
        )

