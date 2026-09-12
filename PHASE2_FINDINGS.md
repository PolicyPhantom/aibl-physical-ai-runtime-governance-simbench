# Phase 2 Findings Log

The eleven pre-implementation specification findings below were resolved before
Phase 2 code was written. Runtime, implementation, test, and model findings must be
appended before correction; this history must not be erased.

## Finding P2-SC-01

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Ambiguous Semantics  
**Finding:** Raw-output extraction and explanatory wrappers were not strict enough.  
**Accepted Resolution:** Accept exactly one top-level JSON object with outer whitespace only; reject prose, fences, wrappers, and trailing content.  
**Authoritative Reference:** Phase 2 Frozen Design v1.0  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-02

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Ambiguous Semantics  
**Finding:** Adapter vocabulary recognition and Phase 1 permission scope were not separated.  
**Accepted Resolution:** Recognized `LIFT` reaches Phase 1 scope evaluation; unknown vocabulary is adapter-invalid.  
**Authoritative Reference:** Phase 2 Frozen Design v1.0  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-03

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Gap  
**Finding:** Adapter-invalid state and evidence semantics were incomplete.  
**Accepted Resolution:** Governance and enforcement are `NOT_PERFORMED`, state is unchanged, and no Phase 1 receipt is created.  
**Authoritative Reference:** Phase 2 Frozen Design v1.0  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-04

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Ambiguous Semantics  
**Finding:** Extra and self-declared governance fields could be ignored or rejected.  
**Accepted Resolution:** Strict four-field allowlist; governance fields and other extras are rejected with distinct adapter reasons.  
**Authoritative Reference:** Phase 2 Frozen Design v1.0  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-05

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Gap  
**Finding:** Valid JSON non-object top-level values lacked a unique reason.  
**Accepted Resolution:** `LLM_OUTPUT_TOP_LEVEL_NOT_OBJECT`.  
**Authoritative Reference:** Phase 2 Semantic Clarification Addendum 01  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-06

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Gap  
**Finding:** Duplicate JSON keys could create parser-dependent intent.  
**Accepted Resolution:** Reject every duplicate key with `LLM_OUTPUT_DUPLICATE_KEY`.  
**Authoritative Reference:** Phase 2 Semantic Clarification Addendum 01  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-07

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Conflict  
**Finding:** Multiple candidates mapped to conflicting adapter reasons.  
**Accepted Resolution:** Concatenated objects are `NOT_JSON`, arrays are `TOP_LEVEL_NOT_OBJECT`, duplicate keys are `DUPLICATE_KEY`; `MULTIPLE_ACTIONS_AMBIGUOUS` is reserved.  
**Authoritative Reference:** Phase 2 Semantic Clarification Addendum 01  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-08

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Gap  
**Finding:** Multiple simultaneous adapter defects had no deterministic aggregation rule.  
**Accepted Resolution:** Fail fast in the frozen order and emit exactly one reason.  
**Authoritative Reference:** Phase 2 Semantic Clarification Addendum 01  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-09

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Gap  
**Finding:** The forbidden governance-field category was open-ended.  
**Accepted Resolution:** Use the frozen exact case-sensitive set; all other extras are unsupported fields.  
**Authoritative Reference:** Phase 2 Semantic Clarification Addendum 01  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-10

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Gap  
**Finding:** Deterministic acceptance and live-model observation had no unique completion rule.  
**Accepted Resolution:** Class A is normative; Class B is observational with one valid live proposal and five repeated runs minimum.  
**Authoritative Reference:** Phase 2 Semantic Clarification Addendum 01  
**Status:** Resolved — Pre-Implementation

## Finding P2-SC-11

**Date:** 2026-08-28  
**Stage:** Pre-Implementation  
**Classification:** P2-SC — Specification Conflict  
**Finding:** Empty and variant `request_type` strings mapped to two reasons.  
**Accepted Resolution:** Unsupported `request_type` strings use `LLM_OUTPUT_UNSUPPORTED_REQUEST_TYPE`; unsupported behavior/target/speed strings use `LLM_OUTPUT_UNRECOGNIZED_VALUE`.  
**Authoritative Reference:** Phase 2 Semantic Clarification Addendum 02  
**Status:** Resolved — Pre-Implementation

## Finding P2-TD-01

**Date:** 2026-08-28  
**Scenario / Test:** Adapter-only test collection after adapter implementation  
**Model / Runtime:** Not applicable  
**Prompt Version:** Not applicable  
**Expected:** Adapter tests collect without requiring later Phase 2 components  
**Observed:** Shared test helper imported the not-yet-implemented provenance module during collection  
**Raw Output Preserved:** Not applicable  
**Reproducible:** Yes  
**Classification:** P2-TD  
**Impact:** Violated the frozen implementation order by coupling adapter tests to provenance  
**Phase 1 Baseline Affected:** No  
**Candidate Resolution:** Make model-metadata test construction a lazy helper so adapter tests remain independent  
**Accepted Resolution:** Model metadata construction moved behind a lazy helper; adapter-only tests no longer import provenance  
**Regression Test Added:** Existing adapter-only invocation reproduces the collection boundary  
**Status:** Resolved

## Finding P2-ID-01

**Date:** 2026-08-29  
**Scenario / Test:** Repeated Class B harness executions sharing one output root  
**Model / Runtime:** Any configured local model/runtime  
**Prompt Version:** `phase2_action_proposal_v1`  
**Expected:** Every harness execution has a unique batch scope and no existing evidence is silently overwritten  
**Observed:** Live artifacts used fixed `raw`, `provenance`, and `receipts` paths with repeat-index filenames, so a later execution could overwrite an earlier execution  
**Raw Output Preserved:** No — earlier output could be replaced  
**Reproducible:** Yes  
**Classification:** P2-ID  
**Impact:** Class B evidence history and receipt isolation were not collision-safe  
**Phase 1 Baseline Affected:** No  
**Candidate Resolution:** Add unique batch identity, batch-scoped artifact directories, unique run paths, and exclusive evidence writes  
**Accepted Resolution:** Each harness execution now creates an offline-unique batch directory; attempt artifacts use unique run paths and exclusive creation; receipts remain isolated inside their originating batch  
**Regression Test Added:** `test_two_live_batches_preserve_first_and_use_distinct_paths`; `test_later_invalid_batch_cannot_inherit_stale_receipt`  
**Status:** Resolved

## Finding P2-ID-02

**Date:** 2026-08-29  
**Scenario / Test:** Local runtime failure during a repeated Class B harness execution  
**Model / Runtime:** Any configured local model/runtime  
**Prompt Version:** `phase2_action_proposal_v1`  
**Expected:** Preserve one failed-attempt observation and continue later scheduled attempts  
**Observed:** `LocalRuntimeError` escaped the loop, terminated remaining attempts, and emitted no failed-attempt evidence  
**Raw Output Preserved:** Not applicable — invocation failed before output reached the adapter  
**Reproducible:** Yes  
**Classification:** P2-ID  
**Impact:** Invocation failures and subsequent scheduled attempts were absent from the evidence set  
**Phase 1 Baseline Affected:** No  
**Candidate Resolution:** Record `INVOCATION_FAILED` without fabricated adapter input, provenance, or receipt, then continue the repeat loop  
**Accepted Resolution:** Runtime failures now emit `INVOCATION_FAILED` observation evidence with structured diagnostics and no fabricated downstream artifacts; later attempts continue  
**Regression Test Added:** `test_failure_on_attempt_three_is_recorded_and_later_attempts_continue`; `test_invocation_failure_has_no_fabricated_downstream_artifacts`  
**Status:** Resolved

## Finding P2-TD-02

**Date:** 2026-08-29  
**Scenario / Test:** Adapter-mediated P2-03 restriction application failure  
**Model / Runtime:** Deterministic Class A fixture  
**Prompt Version:** `phase2_action_proposal_v1`  
**Expected:** `RESTRICT / SPEED_RESTRICTION_REQUIRED / HELD / RUNNING` when restriction application is unsupported  
**Observed:** Phase 2 tests covered only successful P2-03 restriction enforcement  
**Raw Output Preserved:** Yes  
**Reproducible:** Yes  
**Classification:** P2-TD  
**Impact:** One frozen enforcement branch lacked adapter-mediated regression coverage  
**Phase 1 Baseline Affected:** No  
**Candidate Resolution:** Add the required Phase 2 integration test without changing Phase 1 semantics  
**Accepted Resolution:** Added an adapter-mediated failure case to the P2-03 Class A fixture and a dedicated integration regression  
**Regression Test Added:** `test_p2_03_restriction_application_unsupported_is_adapter_mediated` and P2-03 frozen-scenario case `speed-restrict-application-unsupported`  
**Status:** Resolved

## Finding P2-SC-12

**Date:** 2026-08-29  
**Scenario / Test:** Reconstructing the exact task prompt used by Class B attempts  
**Model / Runtime:** Any configured local model/runtime  
**Prompt Version:** `phase2_action_proposal_v1`  
**Expected:** Observation evidence preserves task instruction and SHA-256 of the exact rendered prompt submitted  
**Observed:** Only `prompt_version` was recorded; task-dependent prompt identity could not be proven  
**Raw Output Preserved:** Yes for completed invocations  
**Reproducible:** Yes  
**Classification:** P2-SC  
**Impact:** P2-10 same-prompt claims were not reconstructable from saved evidence  
**Phase 1 Baseline Affected:** No  
**Candidate Resolution:** Record `task_instruction` and exact rendered-prompt SHA-256 for every live attempt  
**Accepted Resolution:** Every Class B attempt records the task instruction and SHA-256 of the exact rendered prompt passed to the proposer  
**Regression Test Added:** `test_same_rendered_prompt_has_same_hash_across_attempts`; `test_different_task_under_same_prompt_version_has_different_hash`  
**Status:** Resolved

## Finding P2-SC-13

**Date:** 2026-08-29  
**Scenario / Test:** Repeated identical Phase 2 observations  
**Model / Runtime:** Deterministic Class A fixture and any Class B runtime  
**Prompt Version:** `phase2_action_proposal_v1`  
**Expected:** One unique `run_id` per emitted observation/execution attempt  
**Observed:** `run_id` was a deterministic content hash and repeated identical attempts reused the same identity  
**Raw Output Preserved:** Yes  
**Reproducible:** Yes  
**Classification:** P2-SC  
**Impact:** Attempt identity and content identity were conflated  
**Phase 1 Baseline Affected:** No  
**Candidate Resolution:** Generate an offline-unique `run_id` per attempt and preserve deterministic identity separately as `provenance_digest`  
**Accepted Resolution:** Every Phase 2 attempt receives an offline-unique UUID-based `run_id`; deterministic content identity is preserved separately as `provenance_digest`  
**Regression Test Added:** `test_identical_output_across_five_attempts_has_distinct_run_ids`; deterministic replay tests now require distinct run IDs and matching content digests  
**Status:** Resolved

## Finding P2-ID-03

**Date:** 2026-08-29  
**Scenario / Test:** Successful local subprocess emits stdout bytes invalid under UTF-8  
**Model / Runtime:** Local CLI / deterministic Python subprocess fixture  
**Prompt Version:** `phase2_action_proposal_v1`  
**Expected:** Decode failure is contained as an invocation/interface failure, failed-attempt evidence is saved without downstream artifacts, and later attempts continue  
**Observed:** `subprocess.run(..., text=True, encoding="utf-8")` could raise `UnicodeDecodeError` outside the existing `LocalRuntimeError` handling path  
**Raw Output Preserved:** Not applicable — no valid UTF-8 text reached the adapter  
**Reproducible:** Yes  
**Classification:** P2-ID  
**Impact:** One scheduled Class B attempt could terminate the harness without observation evidence  
**Phase 1 Baseline Affected:** No  
**Candidate Resolution:** Convert strict UTF-8 stdout decode failure into a distinguishable `LocalRuntimeError` subtype/category and reuse the Addendum 03 failed-attempt continuation path  
**Accepted Resolution:** Local CLI stdout is captured as bytes and decoded exactly once with strict UTF-8; decode failure becomes `LocalRuntimeError` evidence category `LOCAL_RUNTIME_DECODE_ERROR` and reuses the Addendum 03 failed-attempt continuation path  
**Regression Test Added:** `test_invalid_utf8_stdout_is_failed_attempt_and_later_attempt_continues` uses a successful subprocess that accepts prompt input, emits invalid UTF-8 on attempt 1, exits zero, and emits valid UTF-8 on attempt 2  
**Status:** Resolved — Pre-Class-B

## Class B Stop Record — Missing Authoritative Protocol Artifact

**Date:** 2026-08-30  
**Stage:** LM Studio Bridge Pre-Implementation  
**Candidate Classification:** P2-CB-SC — exact numeric ID intentionally unassigned because the frozen protocol review history is unavailable  
**Expected:** `AIBL_Simulation_Bench_Phase2_ClassB_Live_Observation_Protocol_v1.0_FROZEN_20260830.md` is present and can be reviewed before implementation  
**Observed:** The required authoritative protocol file is absent from the project workspace and the available Codex attachment area; the Implementation Instruction and Freeze Record Correction 01 both refer to it but do not reproduce Sections 1–21 in full  
**Reproducible:** Yes  
**Impact:** The complete Class B protocol, its review-history identifiers, evidence-set requirements, and freeze conditions cannot be authoritatively verified; proceeding would require silently assuming that the bridge instruction is a complete substitute  
**Phase 1 Baseline Affected:** No  
**Frozen Adapter Affected:** No  
**Required Human Action:** Add the exact frozen protocol artifact named above to the project folder, then resume the pre-implementation review  
**Code / Test / Prompt / Evidence Changes:** None  
**Resolution Evidence:** The exact frozen protocol artifact was added on 2026-08-30 and read in full; Sections 1–21 are consistent with Freeze Record Correction 01 and the LM Studio Bridge Implementation Instruction  
**Finding Identity:** Document-set completeness issue only; not assigned a new semantic finding ID  
**Status:** Resolved — Pre-Implementation Resumed

## Finding P2-CB-ID-01

**Date:** 2026-08-30  
**Scenario / Test:** Frozen LM Studio endpoint returns an HTTP redirect response  
**Model / Runtime:** LM Studio bridge transport / Python standard-library `urllib`  
**Protocol Version:** Phase 2 Class B Live Observation Protocol v1.0  
**Expected:** One invocation sends exactly one POST to `http://127.0.0.1:1234/v1/chat/completions`; redirects or any additional destination are rejected as transport failure  
**Observed:** The bridge currently uses the default `urllib.request.urlopen`, whose default opener includes `HTTPRedirectHandler`; a 30x response may therefore trigger an implicit follow-up request to the `Location` target  
**Raw Output Preserved:** Not applicable — finding is at the pre-adapter HTTP boundary  
**Reproducible:** Yes — default opener composition is locally inspectable without contacting LM Studio  
**Classification:** P2-CB-ID  
**Impact:** A single bridge invocation may make more than one HTTP request or leave the frozen endpoint, violating the frozen endpoint restriction and no-hidden-retry/request requirement  
**Phase 1 Baseline Affected:** No  
**Frozen Adapter Affected:** No  
**Candidate Resolution:** Use an explicit no-redirect opener/handler, classify every redirect as bridge failure, and add deterministic redirect regression coverage  
**Accepted Resolution:** Adjudication accepted the finding as an implementation defect; the bridge now creates a fresh opener with `RejectRedirectHandler`, rejects redirects as HTTP transport failures, and never requests the `Location` target  
**Regression Test Added:** `test_redirect_is_rejected_without_contacting_target` covers 301/302/303/307/308; `test_redirect_failure_is_observed_and_later_attempt_continues` covers LocalRuntimeError containment and continuation  
**Corrective Verification:** Redirect tests 6 passed; bridge tests 28 passed; Phase 1 50 passed; Phase 2 131 passed; combined 181 passed; Phase 1 protected hash mismatches 0  
**Status:** Resolved — Ready for Independent Post-Fix Review

## Finding Template

### Finding P2-XX

**Date:**  
**Scenario / Test:**  
**Model / Runtime:**  
**Prompt Version:**  
**Expected:**  
**Observed:**  
**Raw Output Preserved:** Yes / No  
**Reproducible:** Yes / No / Variable  
**Classification:** P2-SC / P2-ID / P2-TD / P2-MO / P2-P1  
**Impact:**  
**Phase 1 Baseline Affected:** Yes / No / Unknown  
**Candidate Resolution:**  
**Accepted Resolution:**  
**Regression Test Added:**  
**Status:** Open / Resolved
