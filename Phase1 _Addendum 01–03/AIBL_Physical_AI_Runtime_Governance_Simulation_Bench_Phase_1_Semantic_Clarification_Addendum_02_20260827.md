# AIBL Physical AI Runtime Governance — Simulation Bench
## Phase 1 — Semantic Clarification Addendum 02

**Status:** Frozen clarification for Phase 1 implementation  
**Date:** 2026-08-27  
**Trigger:** Codex re-evaluation after Semantic Clarification Addendum 01  
**Implementation state at trigger:** Not started  
**Code changes before finding:** None  
**Finding ID:** `P1-SC-05`  
**Applies to:** `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Deterministic_Simulation_Frozen_Design_20260827.md`  
**Prior clarification:** `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_01_20260827.md`  
**Implementation contract:** `AIBL_Simulation_Bench_Phase1_Codex_Implementation_Instruction_20260827.md`

---

# 1. Purpose

This addendum resolves one additional semantic stop condition identified after Addendum 01 was applied and Codex re-evaluated the Phase 1 specification.

The issue concerns the final operational state for:

```text
Initial State = SUSPENDED
Request Type  = REENTRY
Decision      = RESTRICT
```

The original Phase 1 design defines:

- `SUSPENDED + REENTRY` as fresh re-entry evaluation;
- `RESTRICT` as a valid permission decision;
- successful restriction application as `EXECUTED_WITH_RESTRICTIONS`;
- successful re-entry as `SUSPENDED → RUNNING`;
- failed re-entry as `SUSPENDED → SUSPENDED`;
- no state transition without an explicit rule.

However, the original design does not explicitly state whether a successfully enforced `RESTRICT` result during re-entry constitutes successful re-entry.

This addendum freezes that missing semantic.

---

# 2. Finding P1-SC-05

## 2.1 Finding

A `SUSPENDED + REENTRY` request proceeds to fresh permission evaluation.

Because the Phase 1 permission composer can return `RESTRICT`, the following path is valid:

```text
SUSPENDED
  ↓
REENTRY
  ↓
fresh permission evaluation
  ↓
RESTRICT
```

The missing question was:

```text
If the required restriction is successfully applied,
does the system transition to RUNNING or remain SUSPENDED?
```

This ambiguity prevents deterministic final-state reconstruction.

## 2.2 Classification

```text
Classification: Specification Gap
Stage: Pre-Implementation Specification Review
Runtime Finding: No
Implementation Defect: No
```

---

# 3. Frozen Re-entry Success Semantics

For Phase 1, re-entry success is defined by both:

1. the fresh permission result; and
2. whether the corresponding runtime enforcement succeeds.

The frozen rule is:

> **Successful re-entry occurs when fresh revalidation produces an executable permission and the Runtime Enforcer successfully enforces that permission.**

For Phase 1, this includes:

```text
ALLOW + EXECUTED
```

and:

```text
RESTRICT + EXECUTED_WITH_RESTRICTIONS
```

Both constitute successful re-entry.

---

# 4. `ALLOW` Re-entry

The existing successful re-entry path remains unchanged.

```text
Initial State     = SUSPENDED
Request Type      = REENTRY
Decision          = ALLOW
Execution Result   = EXECUTED
Final State       = RUNNING
Re-entry Outcome  = SUCCESS
```

Required re-entry outcome reason:

```text
REENTRY_REVALIDATION_PASSED
```

---

# 5. `RESTRICT` Re-entry — Restriction Applied Successfully

If fresh re-entry evaluation returns `RESTRICT` and the required restriction is successfully validated and applied:

```text
Initial State     = SUSPENDED
Request Type      = REENTRY
Decision          = RESTRICT
Execution Result   = EXECUTED_WITH_RESTRICTIONS
Final State       = RUNNING
Re-entry Outcome  = SUCCESS
```

The operational state therefore transitions:

```text
SUSPENDED → RUNNING
```

The restriction remains explicit in the Permission Decision, Enforcement Result, and Decision Receipt.

Phase 1 does **not** introduce a third operational state such as `RESTRICTED_RUNNING`.

The system is `RUNNING`, but the evaluated action is executed only under the explicit restriction attached to that decision.

## 5.1 Reason Codes

Preserve both:

1. the restriction-specific reason code; and
2. the re-entry outcome code.

Example:

```text
SPEED_RESTRICTION_REQUIRED
REENTRY_REVALIDATION_PASSED
```

This allows reconstruction of both:

- why the action was restricted; and
- why re-entry was considered successful.

---

# 6. `RESTRICT` Re-entry — Restriction Application Failure

If fresh re-entry evaluation returns `RESTRICT` but the Runtime Enforcer cannot validate or apply the required restriction:

```text
Initial State     = SUSPENDED
Request Type      = REENTRY
Decision          = RESTRICT
Execution Result   = HELD
Final State       = SUSPENDED
Re-entry Outcome  = FAILED
```

The operational state therefore remains:

```text
SUSPENDED → SUSPENDED
```

The Permission Decision remains `RESTRICT`.

The Runtime Enforcer must not:

- silently upgrade `RESTRICT` to `ALLOW`;
- execute the unrestricted action;
- recompute governance policy.

The re-entry attempt fails because the permission could not be successfully enforced under its required restriction.

Required re-entry outcome reason:

```text
REENTRY_REVALIDATION_FAILED
```

Preserve the restriction-specific reason code as well where applicable.

---

# 7. `HOLD` and `DENY` During Re-entry

For completeness, Phase 1 freezes the following re-entry outcomes.

## 7.1 `HOLD`

```text
Initial State     = SUSPENDED
Request Type      = REENTRY
Decision          = HOLD
Execution Result   = HELD
Final State       = SUSPENDED
Re-entry Outcome  = FAILED
```

## 7.2 `DENY`

```text
Initial State     = SUSPENDED
Request Type      = REENTRY
Decision          = DENY
Execution Result   = BLOCKED
Final State       = SUSPENDED
Re-entry Outcome  = FAILED
```

Neither `HOLD` nor `DENY` may restore action capability.

---

# 8. Frozen Re-entry Transition Matrix

For `Initial State = SUSPENDED` and `Request Type = REENTRY`:

| Permission Decision | Enforcement Result | Final State | Re-entry Outcome |
|---|---|---|---|
| `ALLOW` | `EXECUTED` | `RUNNING` | Successful |
| `RESTRICT` | `EXECUTED_WITH_RESTRICTIONS` | `RUNNING` | Successful |
| `RESTRICT` | `HELD` | `SUSPENDED` | Failed |
| `HOLD` | `HELD` | `SUSPENDED` | Failed |
| `DENY` | `BLOCKED` | `SUSPENDED` | Failed |

No other Phase 1 re-entry transition is implied.

---

# 9. Decision Receipt Requirement

For all `REENTRY` requests, the Decision Receipt must allow reconstruction of:

- initial state;
- permission decision;
- restriction, if any;
- enforcement result;
- applied restriction, if any;
- re-entry success or failure basis;
- final state.

For successful restricted re-entry, the receipt must make it possible to reconstruct:

```text
SUSPENDED
  ↓
REENTRY
  ↓
RESTRICT
  ↓
restriction successfully applied
  ↓
EXECUTED_WITH_RESTRICTIONS
  ↓
RUNNING
```

For failed restricted re-entry:

```text
SUSPENDED
  ↓
REENTRY
  ↓
RESTRICT
  ↓
restriction could not be applied
  ↓
HELD
  ↓
SUSPENDED
```

No hidden runtime state may be required to determine the final state.

---

# 10. Supplemental Regression Requirements

Implementation must include explicit tests for the clarified branch.

## 10.1 Successful Restricted Re-entry

Verify:

```text
Initial State   = SUSPENDED
Request         = REENTRY
Decision        = RESTRICT
Restriction     = successfully applied
Execution       = EXECUTED_WITH_RESTRICTIONS
Final State     = RUNNING
```

Also verify:

```text
REENTRY_REVALIDATION_PASSED
```

is preserved together with the restriction-specific reason code.

## 10.2 Failed Restricted Re-entry

Verify:

```text
Initial State   = SUSPENDED
Request         = REENTRY
Decision        = RESTRICT
Restriction     = cannot be applied
Execution       = HELD
Final State     = SUSPENDED
```

Also verify:

```text
REENTRY_REVALIDATION_FAILED
```

is preserved and no unrestricted action occurs.

## 10.3 Determinism

For identical frozen inputs:

```text
same decision
same reason codes
same enforcement result
same final state
```

must be produced.

---

# 11. Implementation Resume Condition

After this addendum is added, the authoritative document set becomes:

1. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_0_Frozen_Design_20260827.md`
2. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Deterministic_Simulation_Frozen_Design_20260827.md`
3. `AIBL_Simulation_Bench_Phase1_Codex_Implementation_Instruction_20260827.md`
4. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_01_20260827.md`
5. `AIBL_Physical_AI_Runtime_Governance_Simulation_Bench_Phase_1_Semantic_Clarification_Addendum_02_20260827.md`

For `P1-SC-05`, **Addendum 02 takes precedence**.

For `P1-SC-01` through `P1-SC-04`, Addendum 01 remains authoritative.

For all other Phase 1 matters, the original Frozen Design and Implementation Instruction remain unchanged.

Codex may resume implementation after confirming that this clarification resolves the previously reported stop condition.

If another specification judgment is required, stop and report it before implementation.

---

# 12. Freeze Statement

The semantics defined in this addendum are frozen for the current Phase 1 implementation cycle.

The following rule is now explicit:

> **Restricted re-entry is successful only when the required restriction is actually enforced.**

Therefore:

```text
RESTRICT + EXECUTED_WITH_RESTRICTIONS
  → successful re-entry
  → RUNNING
```

while:

```text
RESTRICT + HELD
  → failed re-entry
  → SUSPENDED
```

No additional operational state is introduced.

Do not reinterpret these semantics merely to make tests pass.

> **The goal remains to make the governance logic inspectable, executable, testable, and falsifiable.**

---

# End of Addendum
