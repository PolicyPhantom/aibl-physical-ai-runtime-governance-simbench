"""Phase 3 raw and canonical decision-bearing identities."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

from .constants import VOLATILE_FIELDS


def raw_sha256(raw: bytes) -> str:
    """Hash exact received bytes without decoding or normalization."""
    if not isinstance(raw, bytes):
        raise TypeError("raw proposal identity requires bytes")
    return hashlib.sha256(raw).hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def decision_bearing(value: Any) -> Any:
    """Remove only the frozen closed volatile-field list."""
    if isinstance(value, dict):
        return {
            key: decision_bearing(item)
            for key, item in value.items()
            if key not in VOLATILE_FIELDS
        }
    if isinstance(value, list):
        return [decision_bearing(item) for item in value]
    if isinstance(value, tuple):
        return [decision_bearing(item) for item in value]
    return value


def canonical_bytes(value: Any, *, exclude_volatile: bool = True) -> bytes:
    selected = decision_bearing(value) if exclude_volatile else value
    normalized = _normalize(selected)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def canonical_sha256(value: Any, *, exclude_volatile: bool = True) -> str:
    return hashlib.sha256(
        canonical_bytes(value, exclude_volatile=exclude_volatile)
    ).hexdigest()