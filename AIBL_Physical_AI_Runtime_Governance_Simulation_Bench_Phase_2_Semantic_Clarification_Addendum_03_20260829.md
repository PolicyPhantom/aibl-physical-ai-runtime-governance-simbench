# AIBL Physical AI Runtime Governance — Simulation Bench
## Phase 2 — Semantic Clarification Addendum 03

**Status:** **FROZEN clarification for Phase 2 corrective implementation / pre-Class-B baseline freeze**  
**Date:** 2026-08-29  
**Applies to:** Phase 2 Frozen Design v1.0 + Semantic Clarification Addenda 01–02 + Phase 2 first-pass implementation  
**Trigger:** Independent ChatGPT implementation review + blind Claude implementation review + human cross-review adjudication  
**Implementation stage at trigger:** Deterministic Class A implemented; real local-LLM Class B observation not yet started  
**Phase 1 reopen required:** No  
**Accepted findings addressed:** `P2-ID-01`, `P2-ID-02`, `P2-TD-02`, `P2-SC-12`, `P2-SC-13`

---

# 1. Purpose

This addendum closes the material findings accepted after two independent read-only reviews of the same Phase 2 first-pass implementation snapshot.

The deterministic governance boundary itself did not require reopening.

The accepted findings concern the evidence/runtime boundary that becomes important when real local-LLM Class B observation begins:

1. live evidence files can be silently overwritten across repeated harness executions;
2. a local-runtime invocation failure can terminate the remaining repeat loop and leave no evidence for the failed attempt;
3. one frozen P2-03 restriction-failure branch lacks adapter-mediated deterministic coverage;
4. saved evidence cannot prove that repeated P2-10 observations used the same rendered task prompt;
5. `run_id` does not yet have a frozen identity semantic.

This addendum does not replace the Phase 2 Frozen Design or Addenda 01–02.

It clarifies only the items explicitly defined below.

---

# 2. Cross-Review Finding Mapping

The blind Claude review used `P2-ID-01` for its locally assigned finding.

Because `P2-ID-01` had already been assigned in the earlier ChatGPT independent review, the authoritative Phase 2 ID mapping is:

```text
P2-ID-01
→ Live evidence overwrite / stale-artifact collision risk
→ Origin: ChatGPT independent review

P2-ID-02
→ Invocation failure aborts remaining repeats and leaves no failed-attempt evidence
→ Origin: Claude blind review
→ Claude-local ID: P2-ID-01

P2-TD-02
→ Missing adapter-mediated P2-03 restriction-application-failure coverage
→ Origin: ChatGPT independent review

P2-SC-12
→ P2-10 same-task-prompt evidence not reconstructable
→ Origin: ChatGPT independent review

P2-SC-13
→ run_id observation identity semantics not frozen
→ Origin: ChatGPT independent review
```

Reviewer-local identifiers are preserved in the review records but do not replace the authoritative IDs above.

---

# 3. P2-ID-01 — Collision-Safe Live Evidence Preservation

## 3.1 Frozen Requirement

A Class B live observation harness must never silently overwrite evidence from an earlier harness execution.

Each live harness execution must create a unique:

```text
batch_id
```

and store its evidence in a collision-safe batch scope.

Recommended structure:

```text
outputs/phase2/live/<batch_id>/
    observations/
    raw/
    provenance/
    receipts/
```

Equivalent structures are permitted if the same guarantees are satisfied.

## 3.2 No Silent Overwrite

For any live evidence artifact:

```text
existing path
→ MUST NOT be silently overwritten
```

If a path collision is detected, the implementation must either:

```text
generate a new unique path
```

or:

```text
fail the evidence write explicitly
```

It must not reuse an existing file as though it belonged to the new attempt.

## 3.3 Receipt Isolation

A new invalid or failed attempt must never appear beside a stale receipt that shares the same logical attempt identity.

Batch/run identity must make it impossible for:

```text
new invalid evidence
+
old valid receipt
```

to be mistaken for artifacts from the same observation.

---

# 4. P2-ID-02 — Local Runtime Invocation Failure Evidence

## 4.1 Boundary Distinction

A local-runtime invocation failure occurs **before raw model output reaches the Phase 2 adapter**.

Examples include:

```text
process launch failure
non-zero runtime exit
timeout
OOM / runtime termination surfaced as invocation error
```

This is not:

```text
Adapter INVALID
```

because no adapter input was successfully obtained.

Do not encode invocation failure as a fabricated adapter reason code.

## 4.2 Class B Live Observation Record

Every live invocation attempt must emit one Class B observation record, including failed invocations.

Minimum fields:

```json
{
  "phase": "P2",
  "observation_class": "B",
  "batch_id": "string",
  "attempt_index": 1,
  "run_id": "string",
  "prompt_version": "string",
  "task_instruction": "string",
  "rendered_prompt_sha256": "string",
  "model": {
    "provider": "local",
    "model_name": "string",
    "runtime": "string",
    "runtime_version": "string",
    "sampling_parameters": {}
  },
  "invocation_status": "COMPLETED",
  "raw_output_path": "string-or-null",
  "phase2_provenance_path": "string-or-null",
  "governance_receipt_id": "string-or-null",
  "error": null
}
```

Allowed invocation status values for this Phase 2 cycle:

```text
COMPLETED
INVOCATION_FAILED
```

For `INVOCATION_FAILED`:

```text
raw_output_path        = null
phase2_provenance_path = null
governance_receipt_id  = null
```

and `error` must preserve the available non-secret diagnostic evidence, for example:

```json
{
  "category": "LOCAL_RUNTIME_ERROR",
  "exit_code": null,
  "stderr": "string-or-null",
  "timeout_seconds": null
}
```

The implementation does not need to fabricate raw model output.

## 4.3 Repeat-Loop Behavior

An invocation failure must not automatically terminate all remaining scheduled attempts.

Required behavior:

```text
attempt fails
→ write failed-attempt observation
→ continue to the next scheduled attempt
```

unless the caller explicitly aborts or the harness itself encounters an unrecoverable evidence-write failure.

## 4.4 P2-10 Counting Rule

For P2-10:

```text
invocation attempt
≠ necessarily completed generation
```

The minimum repeated-generation requirement remains:

> at least five completed local-model invocations that produced raw output.

The raw outputs may be adapter-valid or adapter-invalid.

An `INVOCATION_FAILED` attempt is preserved as evidence but does **not** count toward the minimum five completed generations.

The harness is not required to retry indefinitely.

If the configured attempt count ends with fewer than five completed generations, the observation set is valid evidence of what occurred, but:

```text
P2-10 minimum live-generation requirement = NOT YET MET
```

---

# 5. P2-TD-02 — Mandatory P2-03 Restriction-Failure Coverage

The existing successful P2-03 path remains frozen:

```text
RUNNING + ACTION
speed = HIGH
operating_condition = LOW_SPEED_ONLY
restriction application supported
→ RESTRICT
→ SPEED_RESTRICTION_REQUIRED
→ EXECUTED_WITH_RESTRICTIONS
→ RUNNING
```

Phase 2 deterministic Class A coverage must also include the adapter-mediated failure path:

```text
RUNNING + ACTION
speed = HIGH
operating_condition = LOW_SPEED_ONLY
restriction application NOT supported
→ VALID proposal
→ RESTRICT
→ SPEED_RESTRICTION_REQUIRED
→ HELD
→ RUNNING
```

This is a test-coverage correction only.

It does not modify Phase 1 semantics.

---

# 6. P2-SC-12 — Reconstructable Prompt Identity

## 6.1 Requirement

For every Class B live attempt, evidence must be sufficient to determine which task prompt was actually submitted to the local model.

Recording only:

```text
prompt_version
```

is insufficient because the rendered prompt also depends on the task instruction.

## 6.2 Frozen Prompt Evidence

Each Class B live observation record must preserve:

```text
prompt_version
task_instruction
rendered_prompt_sha256
```

`rendered_prompt_sha256` is computed from the exact rendered prompt text passed to the proposer after template + task composition.

No trimming or semantic normalization may occur solely for hashing.

## 6.3 P2-10 Same-Prompt Claim

A set of Class B observations may be claimed to satisfy:

```text
same task prompt
```

only if their:

```text
rendered_prompt_sha256
```

values are identical.

`prompt_version` equality alone is not sufficient.

---

# 7. P2-SC-13 — `run_id` Identity Semantics

## 7.1 Frozen Meaning

For Phase 2:

> **`run_id` identifies one emitted observation / execution attempt.**

It is not a deterministic content hash.

Each new Phase 2 observation record must have a unique `run_id`, even if:

- the same prompt is used;
- the same model output is returned;
- all governance inputs are identical;
- the resulting provenance content is otherwise identical.

## 7.2 Batch Identity

For Class B live observations:

```text
batch_id
```

identifies one harness execution.

```text
attempt_index
```

identifies the ordered attempt inside that batch.

Recommended relation:

```text
batch_id + attempt_index
→ one unique run_id
```

The exact ID-generation mechanism is implementation-defined provided uniqueness is preserved offline and without external services.

## 7.3 Content Identity

If deterministic content identity is useful, it must not overload `run_id`.

A separate field such as:

```text
provenance_digest
```

may be used.

Such a digest does not replace `run_id`.

---

# 8. Evidence Linkage Rules

For a completed invocation:

```text
Class B observation
→ raw output
→ Phase 2 adapter/provenance
→ optional Phase 1 receipt
```

For adapter-valid proposal:

```text
invocation_status       = COMPLETED
raw output              = preserved
Phase 2 provenance      = preserved
governance evaluation   = PERFORMED
Phase 1 receipt         = linked
```

For adapter-invalid proposal:

```text
invocation_status       = COMPLETED
raw output              = preserved
Phase 2 provenance      = preserved
governance evaluation   = NOT_PERFORMED
Phase 1 receipt         = none
```

For invocation failure:

```text
invocation_status       = INVOCATION_FAILED
raw output              = none
Phase 2 provenance      = none
governance evaluation   = NOT_REACHED
Phase 1 receipt         = none
failed-attempt observation = preserved
```

`NOT_REACHED` above describes the live-observation layer only. It is not a new Phase 1 or adapter status.

---

# 9. Required Corrective Regression Tests

Before the Phase 2 Class-A / live-interface baseline is frozen for formal Class B evidence collection, add deterministic tests for at least:

```text
1. two live batches written to the same parent output root
   → first batch artifacts remain unchanged
   → second batch gets distinct batch/run paths

2. valid live attempt followed by invalid attempt in a later batch
   → no stale receipt can be mistaken as belonging to the invalid attempt

3. local runtime failure on attempt 3 of 5
   → attempts 1–2 preserved
   → failed-attempt observation 3 preserved
   → attempts 4–5 are still attempted

4. invocation failure
   → no fabricated raw model output
   → no Phase 2 adapter provenance
   → no Phase 1 receipt

5. P2-03 restriction application unsupported
   → RESTRICT / SPEED_RESTRICTION_REQUIRED / HELD / RUNNING

6. same rendered prompt across repeated live observations
   → identical rendered_prompt_sha256

7. different task instruction under same prompt_version
   → different rendered_prompt_sha256

8. identical model output across five attempts
   → five distinct run_id values
```

Existing Phase 1 tests must remain unchanged and continue to pass.

Existing Phase 2 deterministic governance tests must not be weakened.

---

# 10. Finding Closure Criteria

The accepted findings may be marked resolved only when:

```text
P2-ID-01
→ repeated live batches cannot silently overwrite earlier evidence

P2-ID-02
→ failed invocation emits evidence and does not abort remaining scheduled attempts

P2-TD-02
→ P2-03 restriction-failure branch is adapter-mediated and regression-tested

P2-SC-12
→ live evidence proves rendered prompt identity

P2-SC-13
→ run_id is unique per observation attempt
```

No Phase 1 reopen is required.

---

# 11. Updated Pre-Class-B Freeze Condition

The Phase 2 Class-A / live-interface baseline may be frozen for formal Class B evidence collection only when:

1. Phase 1 regression remains fully passing and unchanged;
2. existing Phase 2 deterministic tests remain fully passing;
3. corrective tests required by this addendum pass;
4. `P2-ID-01`, `P2-ID-02`, `P2-TD-02`, `P2-SC-12`, and `P2-SC-13` are resolved;
5. no new material implementation/specification finding remains open;
6. independent re-review confirms the corrected snapshot.

This is not yet Phase 2 completion.

Real local-LLM Class B observation remains required afterward.

---

# 12. Corrective Implementation Principle

> **The governance boundary must be stable, and the evidence boundary must not silently lose history.**

> **A failed model invocation is itself an observation and must be preserved as such.**

> **Attempt identity and content identity are different concepts.**

> **A repeated-generation claim must be reconstructable from saved evidence, not merely remembered from how the command was run.**

---

# End of Phase 2 Semantic Clarification Addendum 03
