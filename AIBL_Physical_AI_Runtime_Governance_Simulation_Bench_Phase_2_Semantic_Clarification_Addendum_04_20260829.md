# AIBL Physical AI Runtime Governance — Simulation Bench
## Phase 2 — Semantic Clarification Addendum 04

**Status:** **FROZEN clarification for final pre-Class-B corrective implementation**  
**Date:** 2026-08-29  
**Applies to:** Phase 2 Frozen Design v1.0 + Semantic Clarification Addenda 01–03  
**Trigger:** Independent pre-Class-B re-review after Addendum 03 corrective implementation  
**Implementation stage at trigger:** Class A / live-interface corrected baseline; Class B not yet started  
**Phase 1 reopen required:** No  
**Finding addressed:** `P2-ID-03`

---

# 1. Purpose

This addendum closes one remaining local-runtime interface finding identified during independent pre-Class-B re-review.

The deterministic governance boundary, adapter semantics, Phase 1 integration, and Addendum 03 findings remain unchanged and resolved.

The remaining issue exists at the local CLI stdout decoding boundary before raw model output reaches the adapter.

---

# 2. Finding P2-ID-03 — Local CLI Stdout Decode Failure

## 2.1 Observation

The local command proposer currently treats stdout as UTF-8 text.

A subprocess may:

```text
launch successfully
exit with status 0
emit stdout bytes that are not valid UTF-8
```

If that decode failure escapes as `UnicodeDecodeError`, the invocation can terminate before the Class B failed-attempt evidence path is reached.

This violates the Addendum 03 requirement that every scheduled live invocation attempt produce an observation record, including invocation failures.

---

# 3. Frozen Local CLI Encoding Contract

For Phase 2 v1.0:

> **The local CLI proposer interface contract requires stdout model output to be UTF-8 text.**

The harness must not guess, auto-detect, or silently transcode alternative encodings.

A stdout byte stream that cannot be decoded as UTF-8 is an invocation/interface failure.

It is not:

```text
Adapter INVALID
```

because no valid raw text input has reached the adapter.

---

# 4. Required Failure Semantics

A UTF-8 stdout decode failure must be converted into the existing local-runtime failure path.

Required behavior:

```text
stdout UTF-8 decode failure
→ LocalRuntimeError
→ invocation_status = INVOCATION_FAILED
→ failed-attempt observation preserved
→ raw output = none
→ Phase 2 adapter provenance = none
→ governance evaluation = NOT_REACHED
→ Phase 1 receipt = none
→ continue remaining scheduled attempts
```

No fabricated replacement text may be passed to the adapter.

No replacement-character decoding such as:

```text
errors="replace"
```

may silently convert undecodable bytes into proposal text for Phase 2 v1.0.

---

# 5. Failure Evidence

The failed-attempt observation should preserve non-secret diagnostic information sufficient to reconstruct the interface failure.

At minimum, the error evidence must distinguish this condition from:

- non-zero runtime exit;
- process launch failure;
- timeout.

Recommended category:

```text
LOCAL_RUNTIME_DECODE_ERROR
```

or an equivalent structured subtype under the existing `LOCAL_RUNTIME_ERROR` family.

The exact internal exception class structure is implementation-defined provided the saved evidence is deterministic and inspectable.

---

# 6. Required Regression Test

Add at least one deterministic subprocess-based regression test with this shape:

```text
1. start local command successfully
2. accept prompt input
3. emit stdout bytes invalid under UTF-8
4. exit status = 0
```

Expected:

```text
attempt 1 = INVOCATION_FAILED
failed-attempt observation exists
raw output does not exist
Phase 2 adapter provenance does not exist
Phase 1 receipt does not exist
later scheduled attempts continue
```

If the test schedules multiple attempts, at least one later attempt must demonstrate continuation after the decode failure.

Existing Addendum 03 corrective tests must remain passing.

Existing Phase 1 tests must remain unchanged and passing.

---

# 7. Non-Findings Retained as Design Notes

The following observations from independent re-review are not material findings for this Phase 2 cycle:

1. `run_live_task` remains older scaffolding while `execute_live_observations` is the authoritative Class B batch-evidence path.
2. Class A fixed-path evidence may overwrite its previous deterministic verification snapshot because Class A is reproducible verification output rather than accumulating live observation evidence.

These are not corrective requirements in Addendum 04.

---

# 8. Closure Criteria

`P2-ID-03` may be marked:

```text
RESOLVED — PRE-CLASS-B
```

only when:

1. UTF-8 stdout is explicit as the local CLI output contract;
2. decode failure is contained as a local-runtime invocation failure;
3. failed-attempt evidence is preserved;
4. no fabricated raw output / adapter provenance / receipt is created;
5. remaining scheduled attempts continue;
6. the regression test passes;
7. Phase 1 remains unchanged;
8. no new material finding is introduced.

---

# 9. Final Pre-Class-B Freeze Condition

After `P2-ID-03` is resolved and independently re-reviewed with no new material finding, the baseline may be declared:

> **PHASE 2 CLASS-A / LIVE-INTERFACE BASELINE — FROZEN FOR CLASS B**

This declaration is not Phase 2 completion.

Real local-LLM Class B observation remains required afterward.

---

# 10. Final Principle

> **A transport failure must not masquerade as model output.**

> **Encoding assumptions belong to the interface contract, not to silent parser behavior.**

> **Every scheduled live attempt must leave inspectable evidence of what happened at the boundary.**

---

# End of Phase 2 Semantic Clarification Addendum 04
