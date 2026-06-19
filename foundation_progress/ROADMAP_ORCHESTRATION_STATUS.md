# FungMod Roadmap Orchestration And Status

## Purpose

This is the durable repo-side handoff record for the orchestrated PR loop.
It summarizes the current PR queue, phase status, completion rules, and
per-PR reporting contract so future agents do not rebuild already completed
scoped work.

This document is active. `old_progress/` remains historical context only and
must not override `AGENTS.md`, `README.md`, the active central-goal document,
the active roadmap documents, `progress.md`, `ARCHITECTURE_DEBT.md`, or
executable code and tests.

## Orchestrated PR Workflow

Use this workflow for each roadmap PR:

1. Maker thread works in its own worktree and branch.
2. Maker reads `AGENTS.md` first, then follows the active source-of-truth order.
3. Maker implements one small PR slice, updates active status docs, updates
   `progress.md`, runs relevant tests, commits, pushes, and opens the PR.
4. Reviewer thread reviews the PR for bugs, overclaims, missing tests, stale
   status, biology-rule violations, and architecture-debt risks.
5. Maker addresses actionable review comments in a comment loop until the PR is
   ready or a blocker is explicit.
6. After checks and review are satisfied, merge the PR.
7. The next maker starts from this tracker, `progress.md`, code, and tests to
   pick the next open PR slice.

## Phase And PR Queue

Current next PR: **PR-03: VALIDATION-DATA-001 first real time-course dataset and model comparison**.

| PR | Phase or slice | Status | Scope boundary |
| --- | --- | --- | --- |
| PR-01 | Roadmap orchestration and phase status tracker | complete once merged | Documentation and focused guardrail tests only. No scientific or numerical behavior changes. |
| PR-02 | CASE-001 researcher-facing enzyme-chain virtual experiment from names | complete once merged | Existing BIO-002 cellulose-like chain is available through the researcher-facing API and standard outputs. No new biology or validation data. |
| PR-03 | VALIDATION-DATA-001 first real time-course dataset and model comparison | current next; blocked/partial after ingestion-gate documentation | Add a sourced real dataset and comparison workflow without overclaiming validation. This gate PR does not add the dataset or complete ingestion. |
| PR-04 | Output/status hardening from active validation findings | queued | Address the next highest active output, provenance, or validation-status gap after PR-03, based on `findings.yaml` and active validation docs. |

If a future orchestrator changes the queue, update this table, explain the
reason in `progress.md`, and keep the current-next-PR line machine-checkable.

## Current Scoped Phase Status

Status labels follow `progress.md`: `complete`, `partial`, `not started`, and
`blocked`.

| Phase or slice | Current status | Evidence | Do not overclaim |
| --- | --- | --- | --- |
| SOURCE-002 notebook-driven SABIO-RK discovery and proposals | complete for scoped offline discovery/proposal workflow | `foundation_progress/SOURCE_002_NOTEBOOK_DISCOVERY.md`, `tests/test_sabiork_discovery_workflow.py`, `notebooks/09_sabiork_discovery_to_registry_proposal.ipynb` | Proposals are review-only; tests and simulation must not call live SABIO-RK. |
| RESOLVE-001 name and alias resolver | complete for strict registry-backed exact and case-insensitive alias resolution | `foundation_progress/RESOLVE_001_NAME_ALIAS_RESOLVER.md`, `tests/test_registry_resolver.py`, `tests/test_virtual_experiment_name_resolution.py` | No fuzzy matching or automatic external fetch on unknown names. |
| ASSEMBLY-001 case-template assembly basics | complete for current Reaction 618 and BIO-001 template-backed assembly basics; partial relative to arbitrary reaction onboarding | `foundation_progress/ASSEMBLY_001_CONFIG_DRIVEN_CASE_ASSEMBLY.md`, `tests/test_registry_case_templates.py`, `tests/test_config_driven_case_assembly.py` | Template metadata does not make exploratory parameters scientific or change process-level stoichiometric semantics outside implemented code. |
| API-003 researcher-facing virtual experiment API | complete for existing registry records, aliases, environment grids, scientific/exploratory modes, and table access | `foundation_progress/API_003_RESEARCHER_VIRTUAL_EXPERIMENT.md`, `tests/test_api003_researcher_virtual_experiment.py`, `tests/test_virtual_experiment_api.py` | Scientific mode means exact non-exploratory inputs, not empirical validation. |
| BIO-READINESS-LITE scaffold | complete for proposal template, validator, and tests | `foundation_progress/BIO_READINESS_LITE.md`, `foundation_progress/templates/BIO_MECHANISM_PROPOSAL_TEMPLATE.yml`, `scripts/validate_bio_readiness_lite.py`, `tests/test_bio_readiness_lite.py` | The scaffold is a gate; it does not approve unsupported mechanisms by itself. |
| BIO-002 reusable two-step extracellular enzyme chain | complete for scoped reusable two-step chain assembly and software verification; partial relative to broad pathway biology | `foundation_progress/BIO_002_ENZYME_CHAIN_DEGRADATION.md`, `foundation_progress/proposals/BIO_002_EXTRACELLULAR_ENZYME_CHAIN.yml`, `tests/test_bio002_extracellular_enzyme_chain.py`, `tests/test_bio002_generic_chain_assembly.py` | No whole-fungus growth, secretion, uptake, biomass, PET, lignin, full lignocellulose, or organism-specific behavior. |
| Phase 2 static balance checks | complete for scoped static metadata, validator, assembly-time balance checks, and corrective process-reaction binding; partial relative to dynamic thermodynamic feasibility | `FUNGMOD_PHASE_2_THERMODYNAMIC_AND_BALANCE_ENFORCEMENT.md`, `progress.md`, `tests/test_static_balance_thermodynamic_validators.py` | No dynamic reaction quotients, activity model, redox potential model, or solver-time thermodynamic enforcement. |
| CASE-001 cellulose-like enzyme-chain virtual experiment | complete once PR-02 is merged for the scoped researcher-facing API path | `foundation_progress/CASE_001_CELLULOSE_ENZYME_CHAIN_DEMO.md`, `tests/test_case001_researcher_enzyme_chain_virtual_experiment.py` | This exposes the existing BIO-002 chain only; it is exploratory and not whole-fungus growth, secretion, uptake, biomass, PET, lignin, full lignocellulose, organism-specific physiology, or empirical validation. |
| VALIDATION-DATA-001 first real time-course dataset | blocked/partial for ingestion | `foundation_progress/VALIDATION_DATA_001_FIRST_TIMECOURSE.md`, `data/experiments/candidate_reviews/resa_buckin_2011_cellobiose_hydrolysis_review.yml`, `data/experiments/candidate_reviews/ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml`, `tests/test_dataset_candidate_review.py`, `tests/test_roadmap_orchestration_status.py` | The gate is documented, but no real dataset, observation CSV, model comparison, residual table, or validation report exists. Resa/Buckin is blocked by missing extractable observation rows and metadata; Ariaeenejad/Frontiers is blocked by unresolved time-axis conflict and missing machine-readable observations. Current next PR remains PR-03 until source-backed numeric observations are ingested in a separate PR. |

## How A Phase Is Marked Complete

A phase can be marked `complete` only for a stated scope after all of these are
true:

- implemented behavior exists in code or the phase is explicitly a
  documentation/status phase;
- executable tests cover the stated behavior or guardrail;
- active docs identify the scope, assumptions, limitations, and evidence;
- `progress.md` records what changed and what did not change;
- relevant roadmap/status docs are reconciled when phase status changes;
- scientific, numerical, and biology claims match executable behavior;
- unsupported values remain explicit, not silently guessed;
- live external APIs are not required in tests or simulation;
- no silent fallback constants are introduced;
- no unsupported biology is emitted or presented as validated.

Partial completion must say what is complete and what remains out of scope.

## Required Per-PR Reporting Fields

Every PR summary and task report must state:

- what changed;
- what did not change;
- tests added or modified;
- commands run and command results;
- scientific behavior impact;
- backward-compatibility impact;
- remaining ambiguities;
- risk level;
- recommended next task.

## Standing Guardrails

- Do not change scientific or numerical behavior in documentation-only
  guardrail/status PRs.
- Do not add biology unless the mechanism is explicitly implemented,
  provenance-backed, maturity-labelled, tested, and honest about limitations.
- Do not call live external APIs from tests or simulation.
- Do not add silent fallback constants.
- Do not treat proposed source records as production registry records.
- Do not treat `old_progress/` as binding implementation guidance; it is
  historical and non-binding.
