# AIBL Physical AI Runtime Governance — Simulation Bench
## Phase 2 — Semantic Clarification Addendum 02

**Status:** **FROZEN clarification for Phase 2 pre-implementation**  
**Date:** 2026-08-28  
**Applies to:** Phase 2 Frozen Design v1.0 + Semantic Clarification Addendum 01  
**Trigger:** Codex read-only re-review after Addendum 01  
**Implementation state at trigger:** Not started  
**Finding resolved:** `P2-SC-11`  
**Phase 1 reopen required:** No

---

# 1. Purpose

This addendum resolves one remaining Phase 2 reason-code conflict identified during read-only re-review.

The conflict concerns string values for `request_type`, especially empty, case-variant, and whitespace-padded values.

---

# 2. Finding P2-SC-11 — Empty `request_type` Reason-Code Conflict

Addendum 01 froze both:

```text
request_type is a string but not ACTION or REENTRY
→ LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE
```

and the general string-value example:

```text
field present as ""
→ LLM_OUTPUT_UNRECOGNIZED_VALUE
```

Without further clarification, the following input is ambiguous:

```json
{
  "request_type": "",
  "behavior": "MOVE",
  "target": "ZONE_B",
  "speed": "NORMAL"
}
```

Phase 2 v1.0 requires exactly one deterministic adapter reason code, so this conflict must be closed before implementation.

---

# 3. Frozen Field-Specific String Semantics

For Phase 2 v1.0, string-value validation is field-specific.

## 3.1 `request_type`

If `request_type` is present and is a string, but does not exactly equal:

```text
ACTION
REENTRY
```

then:

```text
Adapter = INVALID
Reason  = LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE
```

This includes:

```text
""
"action"
"reentry"
"ACTION "
" ACTION"
"REENTRY "
```

No trimming, case-folding, synonym mapping, or semantic repair is permitted.

## 3.2 `behavior`, `target`, and `speed`

If any of these fields is present as a string but does not exactly match its frozen Phase 2 vocabulary, then:

```text
Adapter = INVALID
Reason  = LLM_OUTPUT_UNRECOGNIZED_VALUE
```

This includes empty strings, case variants, and inner leading/trailing whitespace.

Examples:

```text
behavior = ""
behavior = "move"
target   = "ZONE_B "
speed    = "LOW "
speed    = "low"
```

---

# 4. Required Mapping

The following mappings are authoritative:

```text
request_type absent
→ LLM_OUTPUT_MISSING_REQUIRED_FIELD

request_type = null / non-string
→ LLM_OUTPUT_INVALID_FIELD_TYPE

request_type = "" / case variant / whitespace variant / other unsupported string
→ LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE

behavior / target / speed absent
→ LLM_OUTPUT_MISSING_REQUIRED_FIELD

behavior / target / speed = null / non-string
→ LLM_OUTPUT_INVALID_FIELD_TYPE

behavior / target / speed = "" / case variant / whitespace variant / unknown string
→ LLM_OUTPUT_UNRECOGNIZED_VALUE
```

The Addendum 01 general empty-string example must therefore be read as applying to `behavior`, `target`, and `speed`, not to `request_type`.

---

# 5. Regression Requirement

Phase 2 deterministic adapter tests must include at least:

```text
request_type = ""
request_type = "action"
request_type = "ACTION "
behavior = ""
behavior = "move"
target = "ZONE_B "
speed = ""
speed = "LOW "
```

Expected reason codes must follow the field-specific rules above.

---

# 6. Implementation Resume Condition

After this addendum is accepted:

```text
P2-SC-11 = RESOLVED — PRE-IMPLEMENTATION
```

The authoritative Phase 2 specification set becomes:

1. Phase 2 Frozen Design v1.0
2. Phase 2 Semantic Clarification Addendum 01
3. Phase 2 Semantic Clarification Addendum 02
4. completed Phase 0 / Phase 1 authoritative baseline

No Phase 1 reopen is required.

A final read-only specification re-review may now determine whether the Phase 2 specification is ready for an implementation instruction.

---

# 7. Freeze Statement

> **`request_type` has its own unsupported-string reason code.**

> **Other proposal vocabulary fields use `LLM_OUTPUT_UNRECOGNIZED_VALUE` for unsupported strings.**

> **No string normalization is permitted in Phase 2 v1.0.**

---

# End of Phase 2 Semantic Clarification Addendum 02
