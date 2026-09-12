# AIBL Physical AI Runtime Governance — Simulation Bench
## Phase 1 — Semantic Clarification Addendum 01

**Status:** Frozen clarification for Phase 1 implementation  
**Date:** 2026-08-27  
**Trigger:** Codex pre-implementation specification review  
**Implementation state at trigger:** Not started  
**Code changes before finding:** None  
**Applies to:** `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Deterministic_Simulation_Frozen_Design_20260827.md`  
**Implementation contract:** `AIBL_Simulation_Bench_Phase1_Codex_Implementation_Instruction_20260827.md`

---

# 1. Purpose

This addendum resolves four semantic stop conditions identified during the pre-implementation review of Phase 1.

The findings were detected before Python implementation, scenario fixture creation, or test execution began.

The purpose of this document is to make the affected semantics explicit before implementation resumes.

This addendum does **not** replace the Phase 1 Frozen Design.

It modifies or clarifies only the four items listed below. All other Phase 1 semantics, evaluation order, scenarios, non-goals, constraints, and Done Criteria remain unchanged.

Where this addendum conflicts with the earlier Frozen Design on one of these four specific points, this addendum governs that point for Phase 1 implementation.

---

# 2. Finding Summary

| ID | Finding | Classification | Resolution |
|---|---|---|---|
| `P1-SC-01` | `RUNNING + REENTRY` had a frozen decision but no explicit final-state rule | Specification Gap | Explicit no-op transition: final state remains `RUNNING` |
| `P1-SC-02` | Behavior-scope semantics could map to either `DENY` or `HOLD` | Ambiguous Semantics | Separate explicit out-of-scope prohibition from unresolved scope information |
| `P1-SC-03` | Non-current assurance had no dedicated minimum reason code | Specification Gap | Add `ASSURANCE_NOT_CURRENT` |
| `P1-SC-04` | `RESTRICT` enforcement consistency did not explicitly distinguish successful restriction application from application failure | Ambiguous Semantics | Preserve `RESTRICT`; failed restriction application produces `HELD` and no action |

---

# 3. Clarification P1-SC-01 — `RUNNING + REENTRY`

## 3.1 Frozen Behavior

For:

```text
Operational State = RUNNING
Request Type      = REENTRY
```

the required result is now explicitly frozen as:

```text
Decision          = HOLD
Reason Code       = REENTRY_NOT_APPLICABLE_WHILE_RUNNING
Execution Result   = HELD
Initial State     = RUNNING
Final State       = RUNNING
```

## 3.2 State-Transition Rule

The following explicit no-op transition is added for Phase 1:

```text
RUNNING + REENTRY
  → RUNNING
```

This rule does **not** permit re-entry evaluation while the system is already running.

It exists only to make the final operational state explicit and reconstructable.

## 3.3 Invariant

> A `REENTRY` request while `RUNNING` must not enter normal permission evaluation and must not alter operational state.

---

# 4. Clarification P1-SC-02 — Behavior Scope

The original Frozen Design included behavior scope in both explicit prohibition evaluation and governance precondition evaluation.

For Phase 1, the semantics are separated as follows.

## 4.1 Explicitly Outside Permitted Scope

If the requested behavior is known and is explicitly outside the permitted behavior scope:

```text
Decision    = DENY
Reason Code = BEHAVIOR_OUTSIDE_SCOPE
Execution   = BLOCKED
```

This is a Step 2 — Explicit Prohibition result.

Example:

```text
Requested behavior = LIFT
Permitted scope     = ["MOVE"]
Scope status        = known and authoritative
```

Result:

```text
DENY / BEHAVIOR_OUTSIDE_SCOPE / BLOCKED
```

## 4.2 Scope Information Unresolved or Insufficient

If the system cannot establish the applicable behavior scope because scope information is missing, unresolved, stale-equivalent, or otherwise insufficient:

```text
Decision    = HOLD
Reason Code = BEHAVIOR_SCOPE_UNRESOLVED
Execution   = HELD
```

This is a Step 3 — Governance Preconditions result.

The new Phase 1 reason code is:

```text
BEHAVIOR_SCOPE_UNRESOLVED
```

## 4.3 Distinction

The frozen distinction is:

```text
Known prohibited scope
  → DENY / BEHAVIOR_OUTSIDE_SCOPE

Unknown, unresolved, or insufficient scope basis
  → HOLD / BEHAVIOR_SCOPE_UNRESOLVED
```

Malformed requests remain governed by the existing `INVALID_REQUEST` rule.

---

# 5. Clarification P1-SC-03 — Assurance Not Current

`assurance_status` is a required governance precondition.

The following Phase 1 reason code is added:

```text
ASSURANCE_NOT_CURRENT
```

If assurance is not current, sufficient, or otherwise valid for the present evaluation:

```text
Decision    = HOLD
Reason Code = ASSURANCE_NOT_CURRENT
Execution   = HELD
```

This is a Step 3 — Governance Preconditions result.

## 5.1 Re-entry Use

For a `SUSPENDED + REENTRY` evaluation, if revalidation fails because assurance is not current:

```text
Decision          = HOLD
Reason Codes      = ASSURANCE_NOT_CURRENT
                    + REENTRY_REVALIDATION_FAILED
Execution Result   = HELD
Final State       = SUSPENDED
```

The cause-specific reason code and the re-entry outcome code must both be preserved.

## 5.2 Reason-Code Principle

`REENTRY_REVALIDATION_FAILED` must not substitute for the underlying cause.

Where a distinct current-basis failure is known, preserve both:

```text
cause-specific reason
+
REENTRY_REVALIDATION_FAILED
```

This preserves reconstructability of why re-entry failed.

---

# 6. Clarification P1-SC-04 — `RESTRICT` Application Failure

The Permission Composer and Runtime Enforcer remain logically separate.

A `RESTRICT` decision means the requested behavior is permissible only if the stated machine-checkable restriction is successfully applied.

## 6.1 Restriction Applied Successfully

```text
Permission Decision = RESTRICT
Restriction         = explicit and machine-checkable
Application         = successful
Execution Result     = EXECUTED_WITH_RESTRICTIONS
```

The restricted action may execute.

## 6.2 Restriction Cannot Be Applied

If the Permission Composer returns `RESTRICT`, but the Runtime Enforcer cannot apply or validate the required restriction:

```text
Permission Decision = RESTRICT
Execution Result     = HELD
Applied Action      = none
```

The Permission Decision must **not** be silently changed to `ALLOW`.

The Runtime Enforcer must **not** recompute governance policy.

The Runtime Enforcer must **not** execute the unrestricted action.

## 6.3 Phase 1 Enforcement Consistency Rule

The enforcement matrix is clarified as:

| Permission Decision | Enforcement Outcome |
|---|---|
| `ALLOW` | `EXECUTED` |
| `RESTRICT` + restriction successfully applied | `EXECUTED_WITH_RESTRICTIONS` |
| `RESTRICT` + required restriction cannot be applied | `HELD` |
| `HOLD` | `HELD` |
| `DENY` | `BLOCKED` |

`RESTRICT + HELD` is therefore a valid Phase 1 enforcement outcome **only when the required restriction could not be applied**.

This is an enforcement failure path, not a new permission decision.

---

# 7. Updated Minimum Reason-Code Set

The Phase 1 minimum reason-code set is extended by two codes:

```text
ASSURANCE_NOT_CURRENT
BEHAVIOR_SCOPE_UNRESOLVED
```

The resulting set is:

```text
ALL_CURRENT_CONDITIONS_SATISFIED
HUMAN_SAFETY_ZONE_PROHIBITED
AUTHORITY_STALE
EVIDENCE_STALE
POLICY_NOT_APPLICABLE
OVERSIGHT_UNAVAILABLE
BEHAVIOR_OUTSIDE_SCOPE
BEHAVIOR_SCOPE_UNRESOLVED
ASSURANCE_NOT_CURRENT
OPERATING_CONDITION_PROHIBITED
RISK_STATE_REQUIRES_HOLD
SPEED_RESTRICTION_REQUIRED
OPERATIONAL_STATE_SUSPENDED_REQUIRES_REENTRY
REENTRY_NOT_APPLICABLE_WHILE_RUNNING
REENTRY_REVALIDATION_FAILED
REENTRY_REVALIDATION_PASSED
INVALID_REQUEST
```

For simultaneous non-conflicting conditions, preserve all applicable reason codes unless an explicit earlier evaluation step terminates evaluation.

---

# 8. Supplemental Regression Requirements

Implementation must include tests covering the four clarified semantics.

## 8.1 `RUNNING + REENTRY`

Verify:

```text
HOLD
REENTRY_NOT_APPLICABLE_WHILE_RUNNING
HELD
RUNNING → RUNNING
```

## 8.2 Behavior Scope

Test both:

```text
Known outside scope
  → DENY / BEHAVIOR_OUTSIDE_SCOPE / BLOCKED
```

and:

```text
Scope unresolved
  → HOLD / BEHAVIOR_SCOPE_UNRESOLVED / HELD
```

## 8.3 Assurance Not Current

Verify:

```text
ACTION + ASSURANCE_NOT_CURRENT
  → HOLD / ASSURANCE_NOT_CURRENT / HELD
```

and at least one failed re-entry case:

```text
SUSPENDED + REENTRY + ASSURANCE_NOT_CURRENT
  → HOLD
  → ASSURANCE_NOT_CURRENT
  → REENTRY_REVALIDATION_FAILED
  → HELD
  → SUSPENDED
```

## 8.4 Restriction Application Failure

Verify:

```text
Decision = RESTRICT
Restriction cannot be applied
Execution = HELD
No unrestricted action occurs
Permission decision remains RESTRICT
```

---

# 9. Findings Classification

These four items are classified as:

```text
Pre-Implementation Specification Findings
```

They are **not** runtime findings.

No implementation defect existed at the time they were identified because implementation had not started.

The record should preserve the sequence:

```text
Frozen Design
  ↓
Pre-Implementation Review
  ↓
Semantic Stop Conditions Detected
  ↓
Human Clarification
  ↓
Addendum Freeze
  ↓
Implementation Resume
```

---

# 10. Implementation Resume Condition

Codex may resume Phase 1 implementation only after treating this addendum as an additional authoritative Phase 1 document.

The authoritative document set for implementation becomes:

1. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_0_Frozen_Design_20260827.md`
2. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Deterministic_Simulation_Frozen_Design_20260827.md`
3. `AIBL_Simulation_Bench_Phase1_Codex_Implementation_Instruction_20260827.md`
4. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_01_20260827.md`

For the four semantic points resolved here, **Addendum 01 takes precedence**.

For all other Phase 1 matters, the original Frozen Design and Implementation Instruction remain unchanged.

---

# 11. Freeze Statement

The four clarifications in this addendum are frozen for the current Phase 1 implementation cycle.

Do not silently reinterpret them during implementation.

If implementation reveals a new semantic gap, bypass, inconsistency, or undefined case:

```text
Observe
  ↓
Record
  ↓
Reproduce
  ↓
Classify
  ↓
Stop if specification judgment is required
  ↓
Human decision
  ↓
Regression test
```

Do not modify the research semantics merely to make tests pass.

> **The goal remains to make the governance logic inspectable, executable, testable, and falsifiable.**

---

# End of Addendum
