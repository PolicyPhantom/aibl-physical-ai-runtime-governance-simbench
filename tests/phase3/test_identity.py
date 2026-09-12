import hashlib

from phase3.identity import (
    canonical_bytes,
    canonical_sha256,
    decision_bearing,
    raw_sha256,
)


def test_canonical_json_is_nfc_sorted_compact_utf8_and_one_lf():
    value = {"z": [2, 1], "a": "e\u0301"}
    encoded = canonical_bytes(value)
    assert encoded == '{"a":"é","z":[2,1]}\n'.encode("utf-8")
    assert not encoded.startswith(b"\xef\xbb\xbf")
    assert not encoded.endswith(b"\n\n")
    assert canonical_sha256(value) == hashlib.sha256(encoded).hexdigest()


def test_only_closed_volatile_fields_are_excluded():
    value = {
        "decision": "ALLOW",
        "reason": "ALL_CURRENT_CONDITIONS_SATISFIED",
        "run_id": "volatile",
        "nested": {
            "attempt_number": 5,
            "final_state": "RUNNING",
            "policy_version": "1.0",
        },
    }
    selected = decision_bearing(value)
    assert "run_id" not in selected
    assert "attempt_number" not in selected["nested"]
    assert selected["decision"] == "ALLOW"
    assert selected["reason"] == "ALL_CURRENT_CONDITIONS_SATISFIED"
    assert selected["nested"]["final_state"] == "RUNNING"
    assert selected["nested"]["policy_version"] == "1.0"


def test_raw_identity_hashes_bytes_without_normalization():
    raw = b'{"x":"e\xcc\x81"}\r\n'
    assert raw_sha256(raw) == hashlib.sha256(raw).hexdigest()