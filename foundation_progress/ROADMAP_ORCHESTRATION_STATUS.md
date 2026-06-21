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

Current next PR: **PR-07: BIO-003 registry-backed product inhibition assembly**.

Validation remains important, but it is no longer allowed to block the core
simulator roadmap. The current priority is to build the virtual-experiment
engine so it can honestly generate degradation curves from implemented
mechanisms, thermodynamic/entropy constraints, explicit assumptions, and
uncertainty ranges. Real time-course observations are required later for
calibration, validation, and empirical comparison claims; they are not required
before improving the simulator itself.

| PR | Phase or slice | Status | Scope boundary |
| --- | --- | --- | --- |
| PR-01 | Roadmap orchestration and phase status tracker | complete once merged | Documentation and focused guardrail tests only. No scientific or numerical behavior changes. |
| PR-02 | CASE-001 researcher-facing enzyme-chain virtual experiment from names | complete once merged | Existing BIO-002 cellulose-like chain is available through the researcher-facing API and standard outputs. No new biology or validation data. |
| PR-03 | VALIDATION-DATA-001 ingestion gate | complete for blocker/gate documentation; dataset ingestion deferred | The repo records why the known candidate sources are not ingestable. No dataset was added, and no validation claim was made. |
| PR-04 | Build-first roadmap reframe | complete once merged | Documentation and focused guardrail tests only. Move validation behind simulator capability work without deleting validation from the roadmap. |
| PR-05 | PRODUCT-001 build-first exploratory virtual-experiment expansion | partial after environment-grid helper, assumption-summary outputs, modelability-item outputs, preflight report writer, preflight policy columns, mechanism-summary outputs, and a product-tour notebook | Expand the researcher-facing simulator toward the central product: broader fungus/source + substrate + environment inputs, explicit exploratory priors, complete degradation curves, uncertainty bands, provenance, limitations, and missing-mechanism reports. |
| PR-06 | THERMO-003 dynamic thermodynamic and entropy constraints | complete for the scoped explicit-Q/entropy diagnostics notebook and configured-output diagnostics to date; broader THERMO-003 remains partial | Add general thermodynamic feasibility, entropy/irreversibility accounting, or energy-dissipation constraints where they can be implemented generically and tested without fungus- or substrate-specific shortcuts. |
| PR-07 | BIO-003 mechanism expansion through generic process laws | current next; partial/software-tested for configured and registry-backed reversible product inhibition where explicit records exist | Add more biology only as implemented, provenance-backed, maturity-labelled, tested process laws. Prefer reusable mechanism families over case-specific fungus branches. |
| PR-08 | VALIDATION-DATA-001 first real time-course dataset and model comparison | deferred | Add sourced observations only after simulator outputs are mature enough that comparison is meaningful. Validation, calibration, and empirical comparison claims require real observations. |

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
| Phase 2 static balance checks | complete for scoped static metadata, validator, assembly-time balance checks, and corrective process-reaction binding; partial relative to dynamic thermodynamic feasibility | `FUNGMOD_PHASE_2_THERMODYNAMIC_AND_BALANCE_ENFORCEMENT.md`, `progress.md`, `tests/test_static_balance_thermodynamic_validators.py` | Explicit caller-supplied reaction-quotient Gibbs checks now exist, but there is still no inferred activity model, redox potential model, or solver-time thermodynamic enforcement. |
| CASE-001 cellulose-like enzyme-chain virtual experiment | complete once PR-02 is merged for the scoped researcher-facing API path | `foundation_progress/CASE_001_CELLULOSE_ENZYME_CHAIN_DEMO.md`, `tests/test_case001_researcher_enzyme_chain_virtual_experiment.py` | This exposes the existing BIO-002 chain only; it is exploratory and not whole-fungus growth, secretion, uptake, biomass, PET, lignin, full lignocellulose, organism-specific physiology, or empirical validation. |
| PRODUCT-001 build-first exploratory virtual-experiment expansion | partial | `README.md`, `foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`, `foundation_progress/FUNGMOD_NEXT_PHASES_ROADMAP.md`, `notebooks/examples/10_virtual_experiment_product_tour.ipynb`, `tests/test_api003_researcher_virtual_experiment.py`, `tests/test_guardrails_public_api.py`, `tests/test_notebooks.py`, `tests/test_roadmap_orchestration_status.py`, `tests/test_virtual_experiment_api.py`, `tests/test_virtual_experiment_environment_grid.py` | Build simulator capability before validation. The top-level `environment_grid(...)` helper improves researcher ergonomics for runtime pH/temperature/oxygen grids, but grid values remain metadata-only unless an explicit response law or condition-specific parameter record is active. The `assumption_summary.csv` output makes exploratory assumptions, uncertain inputs, blockers, and follow-up suggestions inspectable. The `modelability_items.csv` output exposes all known, uncertain, missing, and incompatible preflight facts with allowed-use policy. `write_preflight_report(...)` writes diagnostic CSVs for blocked preflight cases without simulating them. Preflight policy columns expose assessed mode, simulation eligibility, blocking reason, and recommended next action. `mechanism_summary.csv` exposes active process laws and rate modifiers, maturity, assumptions, limitations, and provenance. `10_virtual_experiment_product_tour.ipynb` demonstrates the public API and output tables without validation claims. Outputs may be exploratory only when assumptions, ranges, provenance, uncertainty, missing mechanisms, and limitations remain explicit. |
| THERMO-003 dynamic thermodynamic and entropy constraints | partial after explicit reaction-quotient Gibbs validator, configured entropy-production-rate metadata diagnostic, configured thermodynamic JSON/CSV summary outputs, and a configured-output diagnostics notebook | `ARCHITECTURE_DEBT.md`, `tests/test_static_balance_thermodynamic_validators.py`, `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`, `tests/test_notebooks.py` | Prefer first-principles/generic constraints over case-specific fungus models. Current support computes `delta_g = delta_g_standard + R*T*ln(Q)` and `-delta_g/T` only from explicit caller-supplied Q/T metadata, and computes `entropy_production_rate = -condition_specific_delta_gibbs * reaction_extent_rate / temperature` only from explicit configured delta-G/rate/temperature metadata. Configured runs summarize those diagnostics in `thermodynamic_summary.json` and `thermodynamic_summary.csv`; the notebook demonstrates configured explicit-Q outputs without hidden implementation. It does not infer activities, reaction quotients, concentrations, redox potentials, electron balances, validation evidence, or solver-time feasibility. |
| BIO-003 generic mechanism expansion | partial/software-tested for configured and registry-backed reversible product inhibition where explicit records exist, with researcher-facing example coverage for this scoped target | `AGENTS.md`, `foundation_progress/BIO_READINESS_LITE.md`, `foundation_progress/BIO_003_GENERIC_PROCESS_LAWS.md`, `foundation_progress/proposals/BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml`, `notebooks/examples/12_reversible_product_inhibition_example.ipynb`, `tests/test_process_factory_library.py`, `tests/test_configured_model_workflow.py`, `tests/test_config_driven_case_assembly.py`, `tests/test_product_inhibition_examples.py`, `tests/test_notebooks.py` | Biology may expand only through explicit mechanisms with provenance, maturity labels, tests, and honest limitations. Generic reversible product inhibition can now be attached to configured processes and registry-backed case templates with explicit `product_state` and positive unit-compatible `K_i`; missing or non-positive `K_i` remains explicit/blocking. The example uses an explicit exploratory `K_i` fixture and is not validation, calibration, toxicity, uptake, secretion, biomass, physiology, or multi-product inhibition evidence. No fungus-specific branches in generic modules. |
| VALIDATION-DATA-001 first real time-course dataset | deferred; blocked/partial for ingestion | `foundation_progress/VALIDATION_DATA_001_FIRST_TIMECOURSE.md`, `data/experiments/candidate_reviews/resa_buckin_2011_cellobiose_hydrolysis_review.yml`, `data/experiments/candidate_reviews/ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml`, `tests/test_dataset_candidate_review.py`, `tests/test_roadmap_orchestration_status.py` | The gate is documented, but no real dataset, observation CSV, model comparison, residual table, or validation report exists. Real observations are required for validation/calibration/comparison claims, not for building exploratory simulator capability. |

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
