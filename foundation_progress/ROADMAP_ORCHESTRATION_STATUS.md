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

Current next PR: **PR-22: PRODUCT-001 provenance/limitations report ergonomics**.

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
| PR-07 | BIO-003 mechanism expansion through generic process laws | complete for the scoped researcher-facing reversible-product-inhibition example once merged; broad BIO-003 remains partial/software-tested | Add more biology only as implemented, provenance-backed, maturity-labelled, tested process laws. Prefer reusable mechanism families over case-specific fungus branches. |
| PR-08 | PRODUCT-001 virtual-experiment report writer | complete once merged for the scoped Markdown report writer; PRODUCT-001 remains partial | Add a researcher-facing Markdown report writer over existing standard output tables. No new biology, solver behavior, validation data, calibration, or empirical comparison claims. |
| PR-09 | PRODUCT-001 HTML report wrapper | complete once merged for the scoped optional HTML sidecar; PRODUCT-001 remains partial | Add a tiny browser-viewable HTML sidecar around the existing Markdown report and standard output folder links. No new biology, solver behavior, validation data, calibration, empirical comparison claims, or hidden report logic. |
| PR-10 | PRODUCT-001 report-folder index/navigation | complete once merged for the scoped optional report-folder index; PRODUCT-001 remains partial | Add an opt-in report-folder `index.html` linking the existing Markdown report, optional HTML report, standard CSV tables, output manifest, and quicklook figures when present. No new biology, solver behavior, validation data, calibration, empirical comparison claims, scientific reinterpretation, or hidden report logic. |
| PR-11 | PRODUCT-001 screen-comparison summary ergonomics | complete once merged for the scoped derived-output summary; PRODUCT-001 remains partial | Add a derived `comparison_summary.csv` over existing final-metric and threshold rows, with machine-readable comparison/ranking guardrails and recommended next actions. No new biology, solver behavior, validation data, calibration, empirical comparison claims, unsupported ranking, inferred environment response, or hidden report logic. |
| PR-12 | PRODUCT-001 comparison/report-output example notebook | complete once merged for the scoped example notebook; PRODUCT-001 remains partial | Add a public-API notebook that writes existing standard outputs and reports, inspects `comparison_summary.csv`, and explains metadata-only environment-grid guardrails. No new biology, solver behavior, validation data, calibration, empirical comparison claims, unsupported ranking, inferred environment response, or notebook-only scientific logic. |
| PR-13 | THERMO-003 entropy-production-rate notebook coverage | complete once merged for the scoped notebook-coverage slice | Extend the configured-output thermodynamics notebook to inspect existing entropy-production-rate JSON/CSV fields from explicit configured metadata. No new equations, inferred thermodynamics, inferred activities/Q/concentrations, redox model, electron-balance model, validation claim, or solver-time enforcement. |
| PR-14 | THERMO-003 configured entropy-budget summary | complete once merged for the scoped JSON-summary slice; THERMO-003 remains partial | Add a top-level `thermodynamic_summary.json` budget over existing explicit `entropy_production_rate_metadata` rows, counting only numeric `joule / second / kelvin` entropy-rate values. No inferred thermodynamics, solver-time enforcement, validation data, registry biology, or CSV row-schema change. |
| PR-15 | THERMO-003 entropy-budget output notebook inspection | complete once merged for the scoped notebook-inspection slice; THERMO-003 remains partial | Extend the configured-output diagnostics notebook to inspect the new entropy-budget JSON fields from explicit configured metadata. No new equations, inferred thermodynamics, solver-time enforcement, validation data, or notebook-only scientific logic. |
| PR-16 | PRODUCT-001 uncertainty-band output ergonomics | complete once merged for the scoped derived-output/report slice; PRODUCT-001 remains partial | Add `uncertainty_summary.csv`, `DegradationScreenResult.uncertainty_summary()`, report visibility, and schema/data-dictionary coverage over existing sampled-parameter and summary-metric rows. No validation data, calibration, empirical comparison, inferred environment responses, posterior uncertainty claim, or solver/model changes. |
| PR-17 | PRODUCT-001 trajectory-quantile output ergonomics | complete once merged for the scoped derived-output/report slice; PRODUCT-001 remains partial | Add `trajectory_quantiles.csv`, `DegradationScreenResult.trajectory_quantiles()`, report visibility, and schema/data-dictionary coverage over existing `time_series_long.csv` rows. No new biology, solver behavior, validation data, calibration, empirical comparison, inferred environment responses, posterior uncertainty claim, or silent fallback constants. |
| PR-18 | PRODUCT-001 trajectory-quantile example and quicklook ergonomics | complete once merged for the scoped example/quicklook inspection slice; PRODUCT-001 remains partial | Add a public-API trajectory-quantile example notebook and a presentation-only trajectory-band quicklook figure over existing standard output tables. No hidden notebook science, new biology, solver behavior, validation data, calibration, empirical comparison, inferred environment responses, posterior uncertainty claim, CSV row-contract change, or silent fallback constants. |
| PR-19 | PRODUCT-001 degradation-rate quicklook/report ergonomics | complete once merged for the scoped quicklook/report inspection slice; PRODUCT-001 remains partial | Add a presentation-only `degradation_rate_vs_time.png` quicklook and Markdown/HTML/index report visibility over existing `time_series_long.csv` `degradation_rate` rows. No hidden notebook science, new biology, solver behavior, validation data, calibration, empirical comparison, inferred environment responses, posterior uncertainty claim, solver/model changes, CSV row-contract change, or silent fallback constants. |
| PR-20 | PRODUCT-001 threshold-time inspection/report ergonomics | complete once merged for the scoped report-inspection slice; PRODUCT-001 remains partial | Improve threshold-time inspection and report ergonomics from existing `threshold_times.csv`, `summary_metrics.csv`, and report/index paths. No validation data, calibration, empirical comparison, inferred environment responses, posterior uncertainty claim, solver/model changes, hidden notebook science, schema version change, CSV row-contract change, or silent fallback constants. |
| PR-21 | THERMO-003 explicit thermodynamic-summary report ergonomics | complete once merged for the scoped report-inspection slice; THERMO-003 remains partial | Add Markdown, HTML, and report-folder index visibility for existing configured-output `thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts. No inferred activities, inferred reaction quotients, inferred concentrations, redox model, electron-balance model, validation data, empirical comparison, solver-time enforcement, hidden notebook science, schema change, CSV row-contract change, or silent fallback constants. |
| PR-22 | PRODUCT-001 provenance/limitations report ergonomics | current next; PRODUCT-001 remains partial | Improve report/index inspection of existing provenance, limitation, missing-parameter, or suggested-experiment tables. No validation data, calibration, empirical comparison, inferred environment response, solver/model behavior, schema change, hidden notebook science, or silent fallback constants. |
| PR-23 | VALIDATION-DATA-001 first real time-course dataset and model comparison | deferred | Add sourced observations only after simulator outputs are mature enough that comparison is meaningful. Validation, calibration, and empirical comparison claims require real observations. |

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
| PRODUCT-001 build-first exploratory virtual-experiment expansion | partial | `README.md`, `foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`, `foundation_progress/FUNGMOD_NEXT_PHASES_ROADMAP.md`, `src/fungal_model/api/quicklook.py`, `src/fungal_model/api/report.py`, `src/fungal_model/api/result_tables.py`, `notebooks/examples/10_virtual_experiment_product_tour.ipynb`, `notebooks/examples/13_screen_comparison_summary_example.ipynb`, `notebooks/examples/14_trajectory_quantiles_example.ipynb`, `tests/test_api003_researcher_virtual_experiment.py`, `tests/test_guardrails_public_api.py`, `tests/test_notebooks.py`, `tests/test_roadmap_orchestration_status.py`, `tests/test_virtual_experiment_api.py`, `tests/test_virtual_experiment_environment_grid.py` | Build simulator capability before validation. The top-level `environment_grid(...)` helper improves researcher ergonomics for runtime pH/temperature/oxygen grids, but grid values remain metadata-only unless an explicit response law or condition-specific parameter record is active. The `assumption_summary.csv` output makes exploratory assumptions, uncertain inputs, blockers, and follow-up suggestions inspectable. The `modelability_items.csv` output exposes all known, uncertain, missing, and incompatible preflight facts with allowed-use policy. `write_preflight_report(...)` writes diagnostic CSVs for blocked preflight cases without simulating them. Preflight policy columns expose assessed mode, simulation eligibility, blocking reason, and recommended next action. `mechanism_summary.csv` exposes active process laws and rate modifiers, maturity, assumptions, limitations, and provenance. `comparison_summary.csv` derives screen-comparison rows from existing final-metric and threshold tables while preserving `comparison_allowed`, `ranking_allowed`, `ranking_blocking_reason`, and `recommended_next_action` guardrails; metadata-only environment grids remain blocked from ranking or response-plot interpretation. `uncertainty_summary.csv` derives sampled-parameter and output-metric quantile rows from existing standard tables while preserving allowed-use, uncertainty-band status, and interpretation guardrails; these rows are not validation, calibration, empirical confidence intervals, or posterior uncertainty. `trajectory_quantiles.csv` derives p05/p50/p95 trajectory bands from existing `time_series_long.csv` sample rows while preserving allowed-use, trajectory-band status, and interpretation guardrails; these rows are not validation data, calibration evidence, empirical confidence intervals, posterior uncertainty, inferred environment response, or new simulation behavior. `trajectory_quantile_bands.png` is a presentation-only quicklook generated from `trajectory_quantiles.csv`; it is not validation, calibration, empirical comparison, or posterior uncertainty. `degradation_rate_vs_time.png` is a presentation-only quicklook generated from existing `time_series_long.csv` `degradation_rate` rows, and the report now includes a bounded degradation-rate inspection section over those existing rows; neither adds validation, calibration, empirical comparison, a new rate law, or solver/model behavior. The report threshold section now exposes existing `threshold_times.csv` rows and `summary_metrics.csv` threshold quantiles with guardrails; these are simulated threshold summaries, not observed degradation endpoints, validation data, calibration results, or empirical comparisons. `write_report(...)` renders a deterministic Markdown report from existing standard tables and optional quicklook paths, `include_html=True` writes a simple escaped HTML sidecar, and `include_index=True` writes an escaped report-folder index linking the Markdown report, optional HTML report, standard CSV tables, `output_manifest.json`, and optional quicklook figures. These report artifacts do not add validation, calibration, empirical-comparison, scientific reinterpretation, hidden report logic, unsupported ranking, or inferred-science claims. `10_virtual_experiment_product_tour.ipynb` demonstrates the public API and output tables without validation claims, `13_screen_comparison_summary_example.ipynb` demonstrates guarded report-output and `comparison_summary.csv` inspection without ranking metadata-only environment grids, and `14_trajectory_quantiles_example.ipynb` demonstrates trajectory-quantile table inspection plus presentation-only quicklook generation. The report utilities now expose existing configured-output thermodynamic summary artifacts in Markdown, HTML, and index paths with explicit no-inference and no-enforcement guardrails. The next build-first slice should improve provenance, limitation, missing-parameter, or suggested-experiment report ergonomics from existing standard output tables. Outputs may be exploratory only when assumptions, ranges, provenance, uncertainty, missing mechanisms, and limitations remain explicit. |
| THERMO-003 dynamic thermodynamic and entropy constraints | partial after explicit reaction-quotient Gibbs validator, configured entropy-production-rate metadata diagnostic, configured thermodynamic JSON/CSV summary outputs, configured-output diagnostics notebook coverage for explicit-Q, entropy-rate rows, entropy-budget JSON fields, and report/index visibility for existing summary artifacts | `ARCHITECTURE_DEBT.md`, `src/fungal_model/api/report.py`, `tests/test_static_balance_thermodynamic_validators.py`, `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`, `tests/test_notebooks.py` | Prefer first-principles/generic constraints over case-specific fungus models. Current support computes `delta_g = delta_g_standard + R*T*ln(Q)` and `-delta_g/T` only from explicit caller-supplied Q/T metadata, and computes `entropy_production_rate = -condition_specific_delta_gibbs * reaction_extent_rate / temperature` only from explicit configured delta-G/rate/temperature metadata. Configured runs summarize those diagnostics in `thermodynamic_summary.json` and `thermodynamic_summary.csv`; the JSON summary also reports an aggregate entropy budget over numeric explicit entropy-rate rows with units exactly `joule / second / kelvin`, leaving missing or non-numeric values unevaluated. The notebook and report paths demonstrate configured explicit-Q, entropy-production-rate, entropy-budget, and summary-artifact inspection without hidden implementation. They do not infer activities, reaction quotients, concentrations, redox potentials, electron balances, validation evidence, or solver-time feasibility. |
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
