# Release notes — 1.0.0-rc1

Private candidate dated 2026-09-12 for a proposed version 1.0.0 release.
Canonical source commit: 4fd8970cf09474fc076a80b7cc4760437bd2de17.
No GitHub release, Zenodo DOI or public announcement has been made by this build.

## Phase 1–4 status

Phase 1 supplies deterministic permission, enforcement and state transitions.
Phase 2 supplies strict proposal parsing, provenance, deterministic integration
and an optional historical local-model bridge. Current public reproduction uses
fixed inputs; real-LLM integration is deferred for this baseline.
Phase 3 adds adversarial validation and controlled evidence/session infrastructure.
Phase 4 is closed / accepted according to the project-owner status supplied for
RC1. Its first Formal session completed 42/42 attempts across 14 fixed cases,
three attempts per case, governance call count 42 and retry count 0.
Post-run verification checked all 42 attempt inventories, expected transitions,
session inventory bindings and 28 replay comparisons covering all 14 cases.

The Formal summary is an accepted historical result, not a new Formal run in
this candidate build. Private controls, external anchors and evidence are not
included and cannot be independently inspected from this source-only package.

## Public export changes

Runtime source, test source, schemas, prompts and deterministic input fixtures
retain their canonical bytes. README is replaced with current public guidance.
MIT LICENSE, CITATION.cff, these release notes and a public file manifest are added.
Private operational documents, baseline/attestation records, the Phase 2 live
evidence review and all untracked/ignored material are excluded. The manifest
lists every excluded tracked file and its category.

Public design documents retain their original filenames and historical status.
No missing documentation directories are invented. Synthetic unsafe-path tests,
loopback endpoints and frozen non-personal protection constants remain intact.
This build neither rewrites research semantics nor updates frozen source hashes.

## Third-party boundary

No dependencies, LM Studio application/installers, model weights, GGUF binaries,
private model-output evidence, Python distribution or Git distribution are bundled.
The optional LM Studio/Gemma integration retains historical identifiers only;
applicable external terms remain separate from this project's MIT license.
pytest and its dependencies must be provided separately under their own licenses.

## Claims and compatibility

Claim boundary: SIMULATION_LIMITED.
The result concerns fixed synthetic fixtures and logical time. It makes no claim
of real-world safety, reliability, rare-event rates, production readiness,
formal verification, patentability or real-time performance.
Windows filesystem protection and crash tests do not prove elimination of TOCTOU
or power-loss durability. Same-family reconstruction limits independence.
Python 3.11+ is documented; this candidate validates only the environment below.

## Candidate validation

Measured on Windows with Python 3.14.3 and pytest 8.4.2:
614 collected, 614 passed, 0 failed, 0 errors, 0 skipped; pytest exit code 0.
The complete public suite ran once with importlib mode, plugin autoload disabled,
cacheprovider disabled and a fresh basetemp outside the release tree. All source,
test, fixture and schema bytes remained unchanged after the run.

The documented equivalent command is:

~~~text
python -B -m pytest -q -p no:cacheprovider --import-mode=importlib tests
~~~

Loopback-only HTTP tests and deliberate development crash fixtures were included.
No optional LM Studio/Gemma runtime was invoked; no integration test was silently
skipped. No external service or new Formal session was invoked by this build.
Private JUnit/stdout/stderr and temporary test artifacts are outside this archive.
