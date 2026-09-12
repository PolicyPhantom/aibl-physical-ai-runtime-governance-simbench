# AIBL Physical AI Runtime Governance — Simulation Bench
## Phase 1 — Semantic Clarification Addendum 03

**Status:** Frozen clarification for Phase 1 corrective implementation  
**Date:** 2026-08-27  
**Trigger:** Independent post-implementation adversarial review after Codex reported 44 / 44 tests PASS  
**Implementation state at trigger:** Phase 1 implementation complete; independent review pending  
**Code changes after finding at time of freeze:** None  
**Finding ID:** `P1-SC-06`  
**Classification:** Specification Gap with fail-open implementation manifestation  
**Applies to:** `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Deterministic_Simulation_Frozen_Design_20260827.md`  
**Prior clarifications:**  
- `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_01_20260827.md`
- `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_02_20260827.md`

**Implementation contract:** `AIBL_Simulation_Bench_Phase1_Codex_Implementation_Instruction_20260827.md`

---

# 1. Purpose

This addendum resolves one additional Phase 1 semantic gap identified during independent post-implementation review.

The issue concerns **unresolved or unrecognized operating-condition state**.

The original Phase 1 Frozen Design places material operating conditions in the Step 3 governance preconditions and states that an insufficient, stale, or unresolved current basis must produce `HOLD`.

At the same time, the frozen reason-code set distinguishes:

- explicit prohibited operating condition;
- low-speed restriction;

but does not define a dedicated reason code or deterministic handling rule for an unresolved operating condition.

The implemented permission composer therefore admitted a silent fall-through path in which an unrecognized operating-condition value could reach `ALLOW`.

This addendum freezes the missing semantic before corrective implementation.

---

# 2. Finding P1-SC-06

## 2.1 Observation

During independent adversarial review, the following governance context was evaluated with all other required inputs current and valid:

```text
operating_condition = UNRESOLVED
```

The implementation produced:

```text
Decision          = ALLOW
Reason            = ALL_CURRENT_CONDITIONS_SATISFIED
Execution         = EXECUTED
```

This is inconsistent with the frozen Step 3 rule that unresolved current governance basis must produce `HOLD`.

## 2.2 Classification

```text
Finding ID        = P1-SC-06
Classification    = Specification Gap
Manifestation     = Fail-open implementation behavior
Runtime Finding   = Yes, during independent post-implementation review
Implementation Defect = Secondary manifestation of missing semantic closure
```

The underlying specification gap is the absence of a dedicated, deterministic distinction between:

- known normal operating condition;
- known prohibited operating condition;
- known restriction condition;
- unresolved or unrecognized operating condition.

---

# 3. Frozen Operating-Condition Semantics

For Phase 1, operating-condition handling is frozen as follows.

## 3.1 Known Normal Condition

If:

```text
operating_condition = NORMAL
```

then the operating-condition check itself does not block, hold, or restrict the request.

Evaluation continues to the next applicable governance rule.

---

## 3.2 Known Explicit Prohibition

If:

```text
operating_condition = PROHIBITED
```

then:

```text
Decision    = DENY
Reason Code = OPERATING_CONDITION_PROHIBITED
Execution   = BLOCKED
```

This remains a **Step 2 — Explicit Prohibition** result.

No change is made to the existing prohibition semantic.

---

## 3.3 Known Restriction Condition

If:

```text
operating_condition = LOW_SPEED_ONLY
```

and the requested speed requires modification to satisfy the condition:

```text
Decision    = RESTRICT
Reason Code = SPEED_RESTRICTION_REQUIRED
Restriction = speed <= LOW
```

Runtime Enforcement then applies the already-frozen `RESTRICT` semantics.

No change is made to Addendum 01 or Addendum 02 restriction handling.

---

## 3.4 Unresolved or Unrecognized Operating Condition

If the current operating condition cannot be established as a recognized Phase 1 condition, the request must not silently fall through to `ALLOW`.

This includes:

```text
operating_condition = UNRESOLVED
```

and any non-empty operating-condition value not explicitly recognized by the current frozen Phase 1 rule set.

The required result is:

```text
Decision    = HOLD
Reason Code = OPERATING_CONDITION_UNRESOLVED
Execution   = HELD
```

The new Phase 1 reason code is:

```text
OPERATING_CONDITION_UNRESOLVED
```

This is a **Step 3 — Governance Preconditions** result.

---

# 4. No Fail-Open Default

Phase 1 now freezes the following invariant:

> **An operating-condition value that is not recognized as `NORMAL`, `PROHIBITED`, or an explicitly supported restriction condition must not default to normal permissibility.**

Therefore:

```text
Unknown / unresolved operating condition
  ≠ NORMAL
  ≠ implicit ALLOW
```

Instead:

```text
Unknown / unresolved operating condition
  → HOLD
  → OPERATING_CONDITION_UNRESOLVED
  → no action
```

This rule exists to prevent silent semantic fall-through.

---

# 5. Re-entry Semantics

For:

```text
Initial State = SUSPENDED
Request Type  = REENTRY
```

if the current operating condition is unresolved or unrecognized:

```text
Decision          = HOLD
Reason Codes      = OPERATING_CONDITION_UNRESOLVED
                    + REENTRY_REVALIDATION_FAILED
Execution Result   = HELD
Final State       = SUSPENDED
Re-entry Outcome  = FAILED
```

The cause-specific reason and the re-entry outcome reason must both be preserved.

This follows the reason-code composition principle already frozen in Addendum 01 and the re-entry state semantics frozen in Addendum 02.

---

# 6. Updated Operating-Condition Decision Table

| Operating Condition | Permission Treatment | Reason Code | Enforcement |
|---|---|---|---|
| `NORMAL` | Continue evaluation | none from operating-condition rule | depends on later rules |
| `PROHIBITED` | `DENY` | `OPERATING_CONDITION_PROHIBITED` | `BLOCKED` |
| `LOW_SPEED_ONLY` with restriction required | `RESTRICT` | `SPEED_RESTRICTION_REQUIRED` | restriction must be applied or execution is `HELD` |
| `UNRESOLVED` | `HOLD` | `OPERATING_CONDITION_UNRESOLVED` | `HELD` |
| Any other unrecognized Phase 1 value | `HOLD` | `OPERATING_CONDITION_UNRESOLVED` | `HELD` |

No unrecognized value may silently continue to Step 5 `ALLOW`.

---

# 7. Updated Minimum Reason-Code Set

The Phase 1 reason-code set is extended by:

```text
OPERATING_CONDITION_UNRESOLVED
```

The relevant operating-condition reason codes are now:

```text
OPERATING_CONDITION_PROHIBITED
OPERATING_CONDITION_UNRESOLVED
SPEED_RESTRICTION_REQUIRED
```

Their meanings are distinct:

```text
explicit prohibition
  → OPERATING_CONDITION_PROHIBITED
  → DENY

unresolved / unrecognized current basis
  → OPERATING_CONDITION_UNRESOLVED
  → HOLD

known machine-checkable restriction
  → SPEED_RESTRICTION_REQUIRED
  → RESTRICT
```

---

# 8. Required Regression Tests

Corrective implementation must add explicit regression coverage for P1-SC-06.

## 8.1 Unresolved Operating Condition — ACTION

Verify:

```text
Initial State       = RUNNING
Request Type        = ACTION
Operating Condition = UNRESOLVED
Decision            = HOLD
Reason Code         = OPERATING_CONDITION_UNRESOLVED
Execution           = HELD
Final State         = RUNNING
Physical Action     = none
```

---

## 8.2 Unrecognized Operating Condition — ACTION

Use at least one non-empty value not defined by the Phase 1 rule set.

Verify:

```text
Decision    = HOLD
Reason Code = OPERATING_CONDITION_UNRESOLVED
Execution   = HELD
```

The test must demonstrate that an unknown value cannot fall through to `ALLOW`.

---

## 8.3 Unresolved Operating Condition — REENTRY

Verify:

```text
Initial State       = SUSPENDED
Request Type        = REENTRY
Operating Condition = UNRESOLVED
Decision            = HOLD
Reason Codes        = OPERATING_CONDITION_UNRESOLVED
                      + REENTRY_REVALIDATION_FAILED
Execution           = HELD
Final State         = SUSPENDED
```

---

## 8.4 Determinism

For identical inputs:

```text
same decision
same reason codes
same enforcement result
same final state
```

must be produced.

---

# 9. Findings Log Requirement

Before corrective implementation, `PHASE1_FINDINGS.md` must preserve this finding as a new entry.

Recommended record:

```text
Finding ID: P1-SC-06
Classification: Specification Gap
Observed during: Independent post-implementation adversarial review
Original suite state: 44 / 44 PASS
Observed behavior: unresolved operating condition silently reached ALLOW / EXECUTED
Accepted resolution: HOLD / OPERATING_CONDITION_UNRESOLVED / HELD
Status before correction: Open
```

After correction and regression testing, the same entry may be updated to `Resolved`.

Do not erase the fact that the original 44 / 44 test suite passed before this finding was exposed.

---

# 10. Separate Finding Not Resolved by This Addendum

The independent review also identified a separate implementation issue involving omission of the explicit human-zone prohibition flag.

That issue is **not resolved by this addendum**.

It should be preserved separately as an implementation-defect finding, provisionally:

```text
P1-ID-01 — Missing human-zone prohibition flag defaults to false
```

This addendum introduces no new human-zone semantic.

The existing Phase 1 requirement that the human-zone prohibition flag or equivalent be explicitly represented remains in force.

---

# 11. Authoritative Document Set

After this addendum is added, the authoritative Phase 1 document set becomes:

1. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_0_Frozen_Design_20260827.md`
2. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Deterministic_Simulation_Frozen_Design_20260827.md`
3. `AIBL_Simulation_Bench_Phase1_Codex_Implementation_Instruction_20260827.md`
4. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_01_20260827.md`
5. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_02_20260827.md`
6. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_03_20260827.md`

For `P1-SC-06`, **Addendum 03 takes precedence**.

For `P1-SC-01` through `P1-SC-04`, Addendum 01 remains authoritative.

For `P1-SC-05`, Addendum 02 remains authoritative.

All other frozen semantics remain unchanged.

---

# 12. Corrective Implementation Resume Condition

Corrective implementation may proceed after:

1. this addendum is added to the project;
2. `P1-SC-06` is preserved in `PHASE1_FINDINGS.md`;
3. the separate human-zone implementation defect is preserved before correction.

Codex must then:

- implement the frozen P1-SC-06 rule;
- add the required regression tests;
- correct the separate human-zone implementation defect without inventing new semantics;
- run the complete test suite;
- preserve all prior tests;
- report any new specification ambiguity before resolving it;
- not proceed to Phase 2.

If correction exposes another semantic gap, stop and report it before changing the specification.

---

# 13. Freeze Statement

The following semantic is frozen for the current Phase 1 corrective implementation cycle:

> **Unresolved or unrecognized operating condition is insufficient current governance basis and therefore produces `HOLD`, never implicit `ALLOW`.**

Formally for Phase 1:

```text
Operating Condition = unresolved / unrecognized
  → HOLD
  → OPERATING_CONDITION_UNRESOLVED
  → HELD
```

For re-entry:

```text
SUSPENDED
  + REENTRY
  + unresolved / unrecognized operating condition
  → HOLD
  → OPERATING_CONDITION_UNRESOLVED
  + REENTRY_REVALIDATION_FAILED
  → HELD
  → SUSPENDED
```

Do not silently reinterpret unknown operating-condition values as `NORMAL`.

Do not modify the research semantics merely to make tests pass.

> **Passing all specified tests does not establish semantic completeness.**

> **The goal remains to make the governance logic inspectable, executable, testable, and falsifiable.**

---

# End of Addendum
