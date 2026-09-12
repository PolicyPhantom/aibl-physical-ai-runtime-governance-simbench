# AIBL Physical AI Runtime Governance — Simulation Bench

Version: 1.0.0

GitHub: https://github.com/PolicyPhantom/aibl-physical-ai-runtime-governance-simbench

Zenodo DOI (reserved): https://doi.org/10.5281/zenodo.22719249

This package is the prepared v1.0.0 release artifact.
Publication is controlled separately from artifact construction.

Claim boundary: SIMULATION_LIMITED.

A deterministic Python reference simulation of runtime-governance boundaries.
The bench asks whether an action or state-restoration request is currently
permissible under explicitly fixed authority, risk, freshness and physical
observation conditions. It records decision-bearing inputs and reconstructable
evidence. It does not control real equipment.

## Status and scope

- Phase 1: deterministic permission composition, enforcement and state transition.
- Phase 2: strict proposal parsing, model provenance and deterministic integration.
  A historical, optional local LM Studio / Gemma bridge is retained in the source.
  Real-LLM integration is deferred for the current public baseline; it is not
  needed to reproduce the deterministic tests.
- Phase 3: adversarial input/evidence checks and controlled session infrastructure.
- Phase 4: closed / accepted, as supplied by the project owner.
  The first Formal session completed 42 of 42 attempts, with zero retries.

The Phase 4 core question is whether frozen governance decisions change as
specified at strict, boundary and relaxed freshness values, while input identity,
provenance and physical expectations remain bound to the approved material.
There are 14 fixed cases, with three repetitions per case: two controls and
authority, remediation, physical-observation and risk freshness sweeps.

The private Formal session is a deterministic simulation: 42 completed attempts
are not 42 independent real-world safety trials. Private Formal controls, anchors,
workspaces and implementation records are intentionally not distributed here.
The historical design documents describe their original dated state; current
project status is summarized here and in RELEASE_NOTES.md.

## Quick start

Python 3.11 or newer is documented by the project. The historical validation
environment and carried-forward result are recorded in RELEASE_NOTES.md; other
platforms are not claimed to be validated by that result.

From an extracted copy, create an environment if desired and install the test
requirements through your approved package source:

~~~text
python -m pip install -r requirements.txt
python -B -m pytest -q -p no:cacheprovider --import-mode=importlib tests
~~~

Installing dependencies may require network access. The deterministic tests do
not require external network access, a model download or a running LM Studio.
The importlib mode avoids collisions between same-named Phase 3/4 test modules.
Some Phase 2 bridge tests create temporary loopback-only HTTP servers.
Tests also create temporary evidence and subprocess fixtures, including deliberate
crash/restart-inspection cases; these are development tests, not Formal runs.
Use a new temporary output location when specifying pytest's --basetemp option.

Runtime Python imports use only the standard library. pytest is the direct test
dependency. The .yaml scenario files use JSON notation and are loaded with the
standard-library JSON parser, so PyYAML is not required.

Do not invoke live runners or Formal session APIs as a quick-start test. A public
source export is not a Human GO or authorization to use any existing evidence
workspace.

## Repository structure

| Path | Purpose |
| --- | --- |
| src/, scenarios/ | Phase 1 logic and six deterministic fixtures |
| phase2/, phase2_scenarios/, phase2_schemas/, prompts/ | Proposal boundary, local bridge and deterministic Phase 2 inputs |
| phase3/, phase3_scenarios/, phase3_schemas/, phase3_docs/ | Adversarial validation, evidence/session support and design documents |
| phase4/, phase4_scenarios/, phase4_schemas/ | Four freshness families, fixed cases and session/evidence orchestration |
| tests/ | Phase 1-4 regression and controlled fixture tests |
| Phase0 _Phase1 _docs/, Phase1 _Addendum 01–03/ | Earlier public design and semantic clarification documents |
| root-level Phase 2 design documents | Original design/addenda; no invented phase2_docs directory |
| PUBLIC_RELEASE_MANIFEST.json | File identities, canonical origin and explicit exclusions |

Phase 4's public overview is provided here and in RELEASE_NOTES.md. No separate
canonical phase4_docs directory was present in the source commit.

## Optional historical local-model components

The retained Phase 2 configuration names LM Studio 0.4.16 (Build 2) and
google/gemma-3n-e4b with a Q4_K_M GGUF artifact. These are historical identifiers,
not bundled software or a recommendation to download or deploy them.
Applications, installers, weights and private live model evidence are excluded.
Their applicable terms must be checked separately before acquisition, use or
redistribution. This project's MIT license does not relicense external products.

## Limitations

- Fixed synthetic fixtures, logical ticks and deterministic outcomes only.
- No claim of production safety, real-world reliability, rare-event coverage,
  real-time performance, formal verification or patentability.
- Filesystem identity checks and fsync do not eliminate TOCTOU or prove
  power-loss durability. Session operations need a controlled Windows workspace.
- Phase 3/4 boundary code retains its frozen Windows path rules, including
  non-personal protected-root constants. Portability is not implied.
- Verification and reconstruction share implementation lineage; assurance is
  not fully independent.
- Hashes identify bytes; they do not themselves prove ownership or Human approval.
- Dated design references to private human-maintained anchors remain historical
  descriptions. No private Notion export or external anchor is required for tests.
- AI-assisted implementation and review are documented in the project's history;
  those records do not establish independent certification.

## License and citation

The project release material is licensed under the MIT License; see LICENSE.
Copyright (c) 2026 Ryoji Inoue. Separately acquired dependencies retain their own
licenses and are not bundled in this artifact.

Use CITATION.cff to cite version 1.0.0, dated 2026-09-12. The GitHub repository
and reserved Zenodo DOI are listed above. Artifact preparation does not indicate
that the repository or DOI record has been published.
