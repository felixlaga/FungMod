# FungMod Phase 1 — Repository Truth, Instruction Cleanup, and Native Execution Hardening

**Status:** Complete
**Priority:** Critical prerequisite  
**Primary purpose:** Make the repository's active instructions, audit findings, documentation, and execution architecture agree with the code that actually exists before starting further scientific expansion.
**Completed:** 2026-06-15 after P1.1-P1.5 reconciliation, adapter retirement,
documentation synchronization, and local quality-gate verification.

## 1. Why this phase comes first

The audit identifies native process-solver integration as the immediate critical milestone. That recommendation no longer matches the current repository state:

- `ConfiguredModelRunner.run()` already executes `assembly.model.run(...)`.
- `AssembledModel.run()` delegates to `ProcessODESolver`.
- `ProcessODESolver` evaluates native `Process.rate(...)` and `Process.contributions(...)`.
- Configured validators are attached to the assembled model and executed on the result.
- The current progress ledger reports substantially more tests and stronger quality gates than the audit describes.

The audit's broader scientific conclusion is still useful: FungMod is not yet a generally validated, publication-grade simulator for arbitrary fungus–substrate–environment combinations. However, implementation work must begin from the current repository state, not from stale architectural findings.

A second problem is instructional drift. Historical documents still contain blanket rules such as “do not add biology before the foundation is complete,” while the repository now contains BIO-001 and BIO-002 work and the foundation gate is marked complete. These old rules can misdirect Codex even when they are stored under `old_progress/`.

## 2. Phase objective

Create one unambiguous source of truth for developers and Codex, verify every claimed critical audit finding against the current `main` branch, and lock the native process execution path so that future work cannot silently regress to legacy `Reaction`-based workflows.

## 3. Binding principles

1. **Do not invent biological facts.**
2. **Biology is allowed when it is explicitly modeled, provenance-backed, maturity-labelled, tested, and documented.**
3. **Unsupported biology must fail honestly or be labelled exploratory.**
4. **Historical foundation-first documents are non-binding.**
5. **Generic code must not hardcode PET, cellulose, a specific enzyme, or a specific organism.**
6. **No fallback scientific constants or silent toy parameters.**
7. **No broad rewrite without targeted tests and a documented migration path.**
8. **Current behavior must be derived from executable code and tests, not only from progress documents.**
9. **Every removed compatibility path must have evidence that no supported public workflow depends on it.**
10. **All changes must preserve reproducibility, provenance, units, and failure behavior.**

## 4. Scope

### In scope

- Establishing an authoritative Codex/developer instruction file.
- Removing or rewriting obsolete blanket “no biology” instructions from active documentation.
- Clearly marking `old_progress/` material as archived and non-binding.
- Updating tests that enforce obsolete wording rather than current behavior.
- Revalidating audit findings against the current repository.
- Correcting audit-finding statuses and evidence.
- Verifying all supported public workflows use native `AssembledModel.run()`.
- Identifying and deprecating/removing unused `Process -> Reaction` compatibility adapters.
- Adding regression guardrails against reintroducing legacy execution.
- Synchronizing README, progress, architecture-debt, and quality-gate claims.
- Repairing machine-readable audit artifacts so they are actually parseable.

### Out of scope

- New substrate-specific mechanisms.
- New fungal physiology or intracellular metabolism.
- New literature parameters.
- Thermodynamic enforcement implementation.
- New environmental response functions.
- Bayesian calibration or global sensitivity analysis.
- 2D/3D transport.
- Major public API redesign.

Those belong to later phases after the repository truth and execution architecture are stable.

## 5. Work packages

## P1.1 — Authoritative instructions and biology-rule cleanup

Create a root-level `AGENTS.md` that defines the current binding rules for Codex and contributors.

It must:

- identify the active source-of-truth documents;
- state that `old_progress/` is historical and non-binding;
- replace the blanket prohibition on biology with the rule that unsupported, unsourced, or unimplemented biology is forbidden;
- preserve the useful no-shortcut rules:
  - no substrate-specific branches in generic modules;
  - no silent fallback constants;
  - no toy data presented as scientific;
  - no untested “generic” claims;
  - no hidden implementation in notebooks;
  - no unsupported public API placeholders;
- define the required report format for every Codex task.

Also:

- add or update `old_progress/README.md` with a prominent archive warning;
- update active roadmap text that still says biology cannot start when that gate has already been passed;
- update tests that assert obsolete phrases from archived documents;
- add a guardrail test ensuring active instruction files do not contain a blanket ban on adding biology.

### Acceptance criteria

- A developer reading only `AGENTS.md` knows which documents are binding.
- Active documents contain no unconditional “do not add biology” rule.
- Active documents still prohibit invented or unsupported biology.
- Historical files remain available but are clearly non-binding.
- No test requires obsolete foundation-era wording.
- All existing quality gates pass.

## P1.2 — Audit finding reconciliation

Create a current finding-status matrix based on the present `main` branch.

For every critical/high finding:

- classify it as `confirmed`, `partially_resolved`, `resolved`, `stale`, or `needs_manual_verification`;
- link the exact current files and tests;
- distinguish engineering completeness from scientific validation;
- record the commit SHA used for verification;
- avoid changing status based only on `progress.md`.

At minimum, re-evaluate:

- native process-solver integration;
- thermodynamic enforcement;
- environmental response implementation and validation;
- substrate coverage;
- multi-step process-chain generality;
- validation severity/residual reporting;
- public API existence;
- CI, coverage, Ruff, and Pyright claims.

Repair `findings.yaml` so a standard YAML parser can load it. Unquoted scalar values beginning with backticks currently break parsing.

### Acceptance criteria

- The finding catalogue parses successfully.
- Every critical/high finding has current evidence.
- Resolved or stale findings are not presented as open critical blockers.
- Scientific limitations remain explicit even when engineering findings are resolved.

## P1.3 — Native execution path verification

Map every supported execution entry point:

- `VirtualExperiment`;
- `run_configured_model`;
- plugin convenience helpers;
- notebooks;
- calibration and uncertainty wrappers;
- reaction-diffusion workflows;
- direct low-level solver APIs.

For each path, document whether it uses:

- native `AssembledModel.run()` / `ProcessODESolver`;
- a deliberately retained legacy solver;
- an unsupported or transitional path.

Add tests proving that public configured workflows do not instantiate the legacy `SimulationEngine` and do not convert processes into `Reaction` objects.

### Acceptance criteria

- All supported well-mixed configured workflows use native process execution.
- Unsupported geometries fail explicitly.
- Remaining legacy paths are private, documented, and assigned an exit plan.
- Public-path regression tests fail if legacy execution is reintroduced.

## P1.4 — Legacy adapter retirement

Inspect methods such as `as_reaction()` and helper functions that construct `Reaction` objects from `Process` objects.

For each adapter:

- prove whether it is used by supported code;
- remove it if unused;
- otherwise mark it explicitly as legacy, isolate it outside the generic execution path, and document its removal milestone.

Do not remove the low-level `Reaction` engine merely because a native process solver exists. It may remain as an independent low-level API if it has a clearly defined supported purpose.

### Acceptance criteria

- No unexplained process-to-reaction compatibility adapter remains.
- Removing adapters does not change supported numerical outputs.
- Direct legacy-engine tests remain only if the engine is intentionally supported.
- Public workflow documentation no longer implies that adapters are the main path.

## P1.5 — Documentation and quality-gate synchronization

Status: complete in Phase 1 Task 5.

Update:

- `README.md`;
- `progress.md`;
- `ARCHITECTURE_DEBT.md`;
- active roadmap documents;
- current capability tables;
- test/coverage/type-check claims.

Resolve internal contradictions, for example where one section says cellulose is only a placeholder while another section documents BIO-001 cellulose support.

### Acceptance criteria

- Capability statements are internally consistent.
- Quality-gate numbers are current or described without hardcoded counts.
- The documented public API matches imports and tests.
- Limitations distinguish:
  - implemented;
  - technically verified;
  - scientifically validated;
  - exploratory;
  - unsupported.

## 6. Phase completion gate

Phase 1 is complete only when:

- [x] `AGENTS.md` exists and defines the current binding rules.
- [x] `old_progress/` is explicitly archived and non-binding.
- [x] No active instruction contains a blanket prohibition on biology.
- [x] Active instructions prohibit unsupported or invented biology.
- [x] `findings.yaml` parses with a standard YAML parser.
- [x] All critical/high audit findings have current statuses and code evidence.
- [x] All supported configured well-mixed workflows use native process execution.
- [x] Legacy adapters are removed or explicitly contained.
- [x] Native-path regression tests exist.
- [x] README, progress, roadmap, and architecture debt agree.
- [x] Ruff passes.
- [x] Pyright passes under the repository configuration.
- [x] The full test suite passes.
- [x] Coverage remains at or above the repository gate.
- [x] The final Codex report lists changes, non-changes, remaining debt, tests, files, and risks.

## 7. Required Codex report format

Every task in this phase must end with the information below. Individual task
prompts may specialize the exact headings while preserving the same reporting
content.

```text
Summary:
What changed:
What did not change:
Current behavior verified:
Obsolete instruction or shortcut removed:
Remaining instruction or architecture debt:
Tests added or changed:
Commands run:
Results:
Files touched:
Scientific behavior impact:
Backward-compatibility impact:
Risk level:
Recommended next task:
```

## 8. Recommended sequence

1. P1.1 — Authoritative instructions and biology-rule cleanup.
2. P1.2 — Audit finding reconciliation.
3. P1.3 — Native execution path verification.
4. P1.4 — Legacy adapter retirement.
5. P1.5 — Documentation and quality-gate synchronization.

This order prevents Codex from performing later work under contradictory or obsolete instructions.
