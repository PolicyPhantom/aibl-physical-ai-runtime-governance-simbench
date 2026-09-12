# Phase 1 Findings Log

Five pre-implementation specification findings were preserved and resolved by the
frozen Semantic Clarification Addenda. Two post-implementation findings from the
independent adversarial review were preserved before correction and are now resolved.

## Finding P1-SC-01

**Date:** 2026-08-27  
**Scenario / Test:** `RUNNING + REENTRY` final-state review  
**Expected:** A deterministic, reconstructable final state  
**Observed:** The decision was frozen as `HOLD`, but no explicit final-state rule existed  
**Reproducible:** Yes  
**Classification:** Specification Gap  
**Impact:** Receipt final state could not be implemented without judgment  
**Candidate Resolution:** Add an explicit no-op transition  
**Accepted Resolution:** `RUNNING + REENTRY → RUNNING` in Addendum 01  
**Regression Test Added:** `test_full_state_request_matrix`  
**Status:** Resolved

## Finding P1-SC-02

**Date:** 2026-08-27  
**Scenario / Test:** Behavior-scope evaluation-order review  
**Expected:** A unique `HOLD` or `DENY` meaning  
**Observed:** Behavior scope appeared in both prohibition and precondition evaluation  
**Reproducible:** Yes  
**Classification:** Ambiguous Semantics  
**Impact:** The same scope failure could map to different permissions  
**Candidate Resolution:** Separate known prohibition from unresolved scope basis  
**Accepted Resolution:** Known outside scope is `DENY`; unresolved scope is `HOLD`, per Addendum 01  
**Regression Test Added:** `test_known_behavior_outside_scope_is_denied`, `test_unresolved_behavior_scope_is_held`  
**Status:** Resolved

## Finding P1-SC-03

**Date:** 2026-08-27  
**Scenario / Test:** Non-current assurance reason-code review  
**Expected:** An explicit recovery/revalidation reason  
**Observed:** Assurance was mandatory but had no dedicated reason code  
**Reproducible:** Yes  
**Classification:** Specification Gap  
**Impact:** Assurance-based holds were not reconstructable by cause  
**Candidate Resolution:** Add an assurance-specific reason  
**Accepted Resolution:** `ASSURANCE_NOT_CURRENT` in Addendum 01  
**Regression Test Added:** `test_assurance_not_current_action_is_held`, `test_reentry_requires_current_validation`  
**Status:** Resolved

## Finding P1-SC-04

**Date:** 2026-08-27  
**Scenario / Test:** `RESTRICT` enforcement consistency review  
**Expected:** Safe behavior when a required restriction cannot be applied  
**Observed:** The consistency table did not explicitly admit the frozen `HELD` failure path  
**Reproducible:** Yes  
**Classification:** Ambiguous Semantics  
**Impact:** Enforcement consistency could be interpreted in two ways  
**Candidate Resolution:** Preserve `RESTRICT`, perform no action, return `HELD`  
**Accepted Resolution:** Frozen in Addendum 01  
**Regression Test Added:** `test_restrict_application_failure_is_held_without_action`  
**Status:** Resolved

## Finding P1-SC-05

**Date:** 2026-08-27  
**Scenario / Test:** Restricted re-entry state-transition review  
**Expected:** A deterministic final state after successful restricted enforcement  
**Observed:** `RESTRICT + EXECUTED_WITH_RESTRICTIONS` was not classified as successful or failed re-entry  
**Reproducible:** Yes  
**Classification:** Specification Gap  
**Impact:** Restricted re-entry final state could not be reconstructed uniquely  
**Candidate Resolution:** Define success using executable permission plus successful enforcement  
**Accepted Resolution:** Successful restricted re-entry reaches `RUNNING`; failed application remains `SUSPENDED`, per Addendum 02  
**Regression Test Added:** `test_restricted_reentry_transition`, `test_restricted_reentry_reconstructs_without_runtime_memory`  
**Status:** Resolved

## Finding P1-SC-06

**Date:** 2026-08-27  
**Scenario / Test:** Independent post-implementation adversarial review  
**Original Suite State:** 44 / 44 PASS  
**Expected:** Unresolved operating condition must produce `HOLD / OPERATING_CONDITION_UNRESOLVED / HELD`  
**Observed:** An unresolved or unrecognized operating condition reached `ALLOW / EXECUTED`  
**Reproducible:** Yes  
**Classification:** Specification Gap  
**Impact:** An insufficient operating-condition basis could fail open and perform an action  
**Candidate Resolution:** Add a Step 3 hold for unresolved and unrecognized operating conditions  
**Accepted Resolution:** Addendum 03  
**Regression Test Added:** `test_unresolved_operating_condition_action_is_held`, `test_unrecognized_nonempty_operating_condition_is_held`, `test_unresolved_operating_condition_reentry_fails_closed`, `test_unresolved_operating_condition_result_is_deterministic`  
**Status Before Correction:** Open  
**Status:** Resolved

## Finding P1-ID-01

**Date:** 2026-08-27  
**Scenario / Test:** Independent post-implementation adversarial review  
**Original Suite State:** 44 / 44 PASS  
**Expected:** The required human-zone prohibition input must be explicitly represented  
**Observed:** A missing human-zone prohibition input defaulted to false and could fail open  
**Reproducible:** Yes  
**Classification:** Implementation Defect  
**Impact:** `target = HUMAN_ZONE` with missing prohibition input could reach `ALLOW / EXECUTED`  
**Candidate Resolution:** Require explicit representation and use the existing `INVALID_REQUEST` validation path  
**Accepted Resolution:** Require explicit representation; no implicit false default  
**Regression Test Added:** `test_missing_human_zone_prohibition_input_is_invalid_and_held`, `test_frozen_human_zone_scenario_still_denies_with_explicit_input`  
**Status Before Correction:** Open  
**Status:** Resolved

## Finding Template

### Finding P1-XX

**Date:**  
**Scenario / Test:**  
**Expected:**  
**Observed:**  
**Reproducible:** Yes / No  
**Classification:** Specification Gap / Implementation Defect / Ambiguous Semantics / Test Defect / Other  
**Impact:**  
**Candidate Resolution:**  
**Accepted Resolution:**  
**Regression Test Added:**  
**Status:** Open / Resolved
