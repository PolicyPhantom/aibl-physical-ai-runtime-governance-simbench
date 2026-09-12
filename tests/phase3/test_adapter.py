from pathlib import Path

from phase3.adapter import adapt_proposal


ROOT = Path(__file__).resolve().parents[2]
PROPOSALS = ROOT / "phase3_scenarios" / "fixtures" / "proposals"


def _raw(name: str) -> bytes:
    return (PROPOSALS / name).read_bytes()


def test_valid_action_preserves_exact_raw_identity():
    raw = _raw("action_valid.json")
    result = adapt_proposal(raw)
    assert raw == (
        b'{"request_type":"ACTION","behavior":"MOVE","target":"ZONE_B",'
        b'"speed":"NORMAL"}\n'
    )
    assert result.status == "VALID"
    assert result.reason is None
    assert result.normalized_proposal == {
        "behavior": "MOVE",
        "request_type": "ACTION",
        "speed": "NORMAL",
        "target": "ZONE_B",
    }
    assert len(result.raw_sha256) == 64


def test_duplicate_key_is_rejected_before_normalization():
    result = adapt_proposal(_raw("duplicate_key.json"))
    assert result.status == "INVALID"
    assert result.reason == "LLM_OUTPUT_DUPLICATE_KEY"
    assert result.duplicate_key == "target"
    assert result.duplicate_occurrences == 2
    assert result.normalized_proposal is None


def test_unsupported_value_uses_explicit_phase3_mapping():
    result = adapt_proposal(_raw("unsupported_value.json"))
    assert result.status == "INVALID"
    assert result.reason == "LLM_OUTPUT_UNSUPPORTED_VALUE"
    assert result.source_classification == "LLM_OUTPUT_UNRECOGNIZED_VALUE"
    assert result.phase3_classification == "LLM_OUTPUT_UNSUPPORTED_VALUE"
    assert result.normalized_proposal is None