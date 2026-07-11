# Phase 1 Native Execution Path Verification

Date: 2026-06-14

Plan scope: P1.3 from `FUNGMOD_PHASE_1_REPOSITORY_TRUTH_AND_EXECUTION_HARDENING.md`.

Review anchor: P1.3 traced execution paths on
`3538d303c5fbeb1697c584b11d4b6b1109374223`; P1.4 removed the process adapter
bridge, and P1.5 reconciled this report against
`2102710a54279574d7ef0bb2edf5ae19632e84ad`.

This review traces code paths from public entry points to the concrete solver
call. It intentionally does not remove adapters, change numerical methods,
change model parameters, or alter public API behavior.

## Classification Summary

- Supported configured well-mixed workflows execute natively through
  `AssembledModel.run()` and `ProcessODESolver`.
- Configured non-well-mixed geometry does not switch to a legacy solver; it
  fails explicitly with `ProcessODESolver supports only well_mixed geometry`.
- Direct `Reaction`/`SimulationEngine` and `ReactionDiffusionEngine1D` remain
  intentional low-level APIs.
- P1.4 follow-up: concrete `Process.as_reaction()` adapters were removed and
  `FD-006` is resolved.

## Execution Path Matrix

| Entry point | Public/private status | Solver path | Geometry support | Validator path | Legacy dependency | Evidence | Required action |
|---|---|---|---|---|---|---|---|
| `fungal_model.run_configured_model(...)` / `fungal_model.workflows.run_configured_model(...)` | Public supported configured workflow | `run_configured_model` -> `ConfiguredModelRunner.run` -> `ConfiguredProcessAssembler.assemble` -> `assembly.model.run` -> `AssembledModel.run` -> `ProcessODESolver.run` | Well-mixed configured geometry only; `film_1d` or other non-well-mixed geometry fails explicitly in `ProcessODESolver._validate_geometry_supported` | `ConfiguredInputLoader` loads configured validators through `ValidatorRegistry`; `ModelBuilder` attaches them to `AssembledModel`; `ProcessODESolver.run` calls `SimulationResult.validate` | None for supported path | `src/fungal_model/workflows/configured_model.py`, `src/fungal_model/processes/assembly.py`, `src/fungal_model/solvers/process_ode.py`, `tests/test_guardrails_native_execution.py` | Preserve native guardrails; no P1.3 production change needed |
| `ConfiguredModelRunner.run(...)` | Public class, supported orchestrator | Same native path as `run_configured_model` | Same as configured workflow | Same as configured workflow | None for supported path | `src/fungal_model/workflows/configured_model.py`, `tests/test_configured_model_workflow.py` | Preserve |
| `VirtualExperiment.from_registry(...).simulate(...)`, `VirtualExperiment.from_names(...).simulate(...)`, `virtual_experiment(...)` | Public researcher-facing workflow | `VirtualExperiment.simulate` -> `simulate_screen` -> `_run_sample` / `_run_scientific_case_sample` -> `run_configured_model` -> native `ProcessODESolver` | Registry case builders currently emit well-mixed configured geometry for supported simulated cases; unsupported configured geometry would fail through the native solver guard | Uses validators generated into the temporary configured model and executed by configured runner | None for supported simulated cases | `src/fungal_model/api/virtual_experiment.py`, `src/fungal_model/screening/ensemble.py`, `src/fungal_model/screening/case_builder.py`, `tests/test_api003_researcher_virtual_experiment.py`, `tests/test_bio001_surface_cellulose_virtual_experiment.py` | Preserve; future spatial virtual experiments need an explicit new solver route |
| `fungal_model.screening.simulate_screen(...)` | Public screening workflow | Builds per-sample `ModelConfig`; `_run_sample` calls `run_configured_model`; native after that point | Same configured well-mixed support as generated configs | Same configured validator path | None for supported cases | `src/fungal_model/screening/ensemble.py`, `tests/test_registry_ensemble_simulation.py`, `tests/test_registry_ensemble_homogeneous_mm.py` | Preserve |
| `run_extracellular_enzyme_chain_demo(...)` | Public BIO-002 demo helper | Builds chain `ModelConfig`; writes it; calls `run_configured_model`; native after that point | Template declares well-mixed geometry; unsupported geometry would fail through configured native guard | Template/config validators execute through configured runner | None for supported demo path | `src/fungal_model/screening/enzyme_chain.py`, `tests/test_bio002_generic_chain_assembly.py`, `tests/test_bio002_extracellular_enzyme_chain.py` | Preserve arbitrary-length linear support and explicit branching/cycle rejection; scientific interpretation remains template-specific |
| `fungal_model.plugins.pet.run_pet_surface_integration(...)` | Public plugin convenience helper, deprecated but supported | Rewrites plugin config, passes explicit PET substrate registry, calls `run_configured_model`; native after that point | Well-mixed plugin benchmark only | Same configured validator path | No legacy solver; dependency is an explicit plugin registry, not `SimulationEngine` | `src/fungal_model/plugins/pet/workflows.py`, `tests/test_full_integration_workflow.py`, `tests/test_guardrails_native_execution.py` | Preserve until documented replacement is fully preferred |
| `notebooks/examples/00_quickstart.ipynb`, `01_config_entity_inspection.ipynb`, `02_failure_report.ipynb`, `03_configured_outputs.ipynb` | Supported example notebooks | Import package public API and call `run_configured_model`; native configured path | Well-mixed example configs; failure example uses explicit configured failure handling | Same configured validator path when a run succeeds | None; guardrail test rejects direct low-level solver imports/calls | `tests/test_notebooks.py`, `notebooks/examples/*.ipynb` | Preserve notebook guardrails |
| `notebooks/06_sabiork_reaction_618_beta_glucosidase.ipynb`, `notebooks/07_bio001_cellulose_surface_virtual_experiment.ipynb` | Supported researcher notebooks | Use `VirtualExperiment`; native through screening/configured path when simulation executes | Same as virtual-experiment generated configs | Same as virtual-experiment/configured path | None for supported path | `tests/test_sabiork_reaction_618_notebook.py`, `tests/test_bio001_notebook.py`, notebook code cells | Preserve |
| `notebooks/09_sabiork_discovery_to_registry_proposal.ipynb` | Supported discovery notebook, non-execution proposal workflow | No model solver call in notebook code | Not applicable | Not applicable | None | Notebook code inspection; discovery tests | No native execution action |
| `notebooks/.ipynb_checkpoints/06_sabiork_reaction_618_beta_glucosidase-checkpoint.ipynb` | Removed tracked checkpoint artifact, not a supported public notebook contract | P1.5 removed the unsupported checkpoint; supported notebooks are listed separately and covered by notebook tests | Not applicable | Not applicable | None remaining | `git ls-files notebooks/.ipynb_checkpoints/*`; `tests/test_phase1_documentation_sync.py` | Keep checkpoint artifacts out of the tracked project |
| `calibrate_configured_model(...)` | Public synthetic-only configured calibration wrapper | `calibrate_configured_model` -> `_run_with_parameters` -> `run_configured_model`; native configured path for model predictions | Same configured well-mixed support as source config | Same configured validator path for each configured run | None for configured calibration path | `src/fungal_model/calibration/configured.py`, `tests/test_configured_synthetic_calibration.py` | Preserve; Bayesian/global calibration remains out of scope |
| `fit_least_squares(...)` | Public low-level calibration utility | Solver-agnostic callback utility; calls caller-provided `predict` function | Delegated to caller prediction function | Delegated to caller prediction function | None intrinsic | `src/fungal_model/calibration/fitting.py`, `tests/test_calibration.py` | Preserve as solver-agnostic utility |
| `run_monte_carlo(...)` | Public uncertainty utility | Solver-agnostic callback utility; calls caller-provided `predict` function | Delegated to caller prediction function | Delegated to caller prediction function | None intrinsic | `src/fungal_model/uncertainty/monte_carlo.py`, `tests/test_uncertainty_sensitivity.py` | Preserve as solver-agnostic utility |
| `local_sensitivity(...)` | Public sensitivity utility | Solver-agnostic callback utility; calls caller-provided `predict_scalar` function | Delegated to caller prediction function | Delegated to caller prediction function | None intrinsic | `src/fungal_model/uncertainty/sensitivity.py`, `tests/test_uncertainty_sensitivity.py` | Preserve as solver-agnostic utility |
| `AssembledModel.run(...)` | Public low-level native process execution API | Directly instantiates `ProcessODESolver(self).run(RunRequest(...))` | Well-mixed or no geometry only; non-well-mixed geometry raises `ValueError` | Model validators plus request validators are passed to `SimulationResult.validate` | None | `src/fungal_model/processes/assembly.py`, `src/fungal_model/solvers/process_ode.py`, `tests/test_native_assembled_model_run.py` | Preserve |
| `ProcessODESolver.run(...)` | Public native process ODE solver | Direct native process solver; evaluates `Process.rate(...)` and `Process.contributions(...)`, then calls SciPy `solve_ivp` | Well-mixed only; explicit error for other geometry types | Executes validators after result construction | Uses SciPy backend, not legacy FungMod `SimulationEngine` | `src/fungal_model/solvers/process_ode.py`, `tests/test_native_assembled_model_run.py` | Preserve |
| `SimulationEngine.simulate(...)` with `Reaction` objects | Public low-level legacy reaction ODE API through `fungal_model.core` | Direct `Reaction`-based ODE engine using SciPy `solve_ivp` | Well-mixed species ODE; no geometry abstraction | No configured validator loading; callers validate separately | Intentional retained legacy/low-level API | `src/fungal_model/core/simulation.py`, `src/fungal_model/chemistry/reactions.py`, `tests/test_reaction_engine.py`, `tests/test_michaelis_menten.py`, `tests/test_fungal_dynamics.py` | Preserve as low-level API; do not classify obsolete in P1.3 |
| `ReactionDiffusionEngine1D.simulate(...)` | Public low-level spatial transport API | Direct 1D method-of-lines reaction-diffusion engine using `Reaction` and SciPy `solve_ivp` | Explicit 1D uniform grid with boundary conditions; not integrated into configured `AssembledModel.run` | Spatial validators are caller/test applied, not configured validator registry | Intentional retained spatial low-level API | `src/fungal_model/transport/reaction_diffusion.py`, `tests/test_reaction_diffusion.py` | Preserve; future configured spatial routing must be explicit |
| Retired process-to-`Reaction` adapters | Former public/transitional compatibility methods on concrete process classes | Removed in P1.4; process classes no longer convert themselves into legacy `Reaction` objects | Not applicable | Not applicable | None remaining in production process modules | `foundation_progress/validation/PHASE_1_LEGACY_ADAPTER_RETIREMENT.md`, `tests/test_guardrails_native_execution.py` | Preserve retirement guardrail |

## Call-Site Findings

`AssembledModel.run()` is called by the configured runner and direct native
tests. It delegates to `ProcessODESolver` and does not construct `Reaction` or
`SimulationEngine`.

`ProcessODESolver` uses SciPy `solve_ivp` internally as the native process ODE
backend. This is not a regression to the legacy FungMod `SimulationEngine`.

`SimulationEngine` and `Reaction` call sites are confined to the low-level
reaction API, reaction-diffusion engine, and tests for those retained APIs.
They are not used by `src/fungal_model/workflows`, `src/fungal_model/plugins/pet`,
or supported example notebooks.

P1.4 removed `as_reaction()` from `FirstOrderDecayProcess`,
`MassActionProcess`, `HomogeneousMichaelisMentenProcess`, and
`SurfaceCatalysisProcess`. The direct low-level `Reaction` API remains
available, but process classes no longer expose a compatibility bridge into it.

## Validator Trace

Configured validators are loaded from config by `ConfiguredInputLoader` through
`ValidatorRegistry`, attached to the assembled model by `ModelBuilder`, and
executed inside `ProcessODESolver.run()` after the `SimulationResult` is
created. `tests/test_guardrails_native_execution.py` includes a registry-backed
validator trace that proves configured validators run on the result produced by
the native process solver.

## Unsupported Geometry Behavior

`ProcessODESolver._validate_geometry_supported()` permits no geometry or
`geometry_type == "well_mixed"`. Any other geometry raises a `ValueError` that
the configured runner reports as a structured `model_execution` failure. The
P1.3 guardrail test patches the legacy reaction engine and adapters to fail,
then verifies a `film_1d` configured geometry still raises the explicit native
unsupported-geometry error instead of silently changing solver paths.

## P1.3 Test Additions

`tests/test_guardrails_native_execution.py` now covers:

- actual configured well-mixed benchmark runs with tripwires on
  `SimulationEngine` and `Reaction`;
- configured validator execution through a real `ValidatorRegistry`;
- unsupported configured `film_1d` geometry failing explicitly before any
  legacy fallback path can be used;
- source-level guardrails that high-level workflow, PET plugin, and supported
  example notebook paths do not import or call low-level solver shortcuts.

## Remaining Architecture Debt

P1.4 resolved `FD-006 Process-to-Reaction compatibility adapters` by removing
the adapter surface. The direct low-level `Reaction`, `SimulationEngine`, and
`ReactionDiffusionEngine1D` APIs are intentionally retained and are not
classified as obsolete merely because native configured execution exists.
