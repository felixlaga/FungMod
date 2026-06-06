# Foundation-Only Milestone Sequence

## Rule

No real biology milestones appear here. Do not add real biology until this sequence is complete or explicitly waived.

## Milestone 1: Governance and guardrails

Deliverables: roadmap folder, `ARCHITECTURE_DEBT..md`, PR template, guardrail tests.
Do not take shortcuts. If a temporary compromise is absolutely unavoidable, stop and document it in ARCHITECTURE_DEBT.md with a reason, risk, test coverage, and removal milestone. Do not hide it in code comments.

Done when tests fail if PET is added to generic modules.

## Milestone 2: Generic public API

Deliverables: `run_configured_model`, `load_model_config`, `ProcessLibrary` names introduced; PET workflow moved toward plugin/example/deprecated wrapper.

Done when top-level API is generic-first.

## Milestone 3: Registry-based loading

Deliverables: substrate/geometry/product-map/validator registries; PET and non-PET loaders.

Done when no PET-only loader branch remains.

## Milestone 4: Model config object

Deliverables: config schema, time/initial-state/validator/process configs.

Done when homogeneous, PET plugin, and non-PET dummy configs load.

## Milestone 5: Product map configs

Deliverables: ProductMap, loader, mass-equivalent benchmark maps.

Done when workflows no longer hardcode `hydrolysate`.

## Milestone 6: Process factory library

Deliverables: ProcessFactory, BuildDecision, ProcessLibrary, first-order/homogeneous/surface factories.

Done when configs build processes through factories.

## Milestone 7: Native `AssembledModel.run()`

Deliverables: run interface, ODE RHS construction, rate recording, validation attachment, `SimulationResult` output.

Done when assembled model runs homogeneous and surface benchmark.

## Milestone 8: Generic `run_configured_model`

Deliverables: load config, entities, parameters, process factories, assemble, run, save.

Done when same function runs homogeneous, PET plugin, and non-PET surface benchmarks.

## Milestone 9: Remove direct solver calls from workflows

Deliverables: workflows call `model.run`; solver usage isolated in solver layer.

Done when generic workflow source does not import low-level engines.

## Milestone 10: Result/output foundation

Deliverables: full output folder, config/entity snapshots, validation, plots, mode/maturity labels.

Done when every configured model saves a complete output bundle.

## Milestone 11: Notebook foundation

Deliverables: generic quickstart, config/entity, failure report, and outputs notebooks.

Done when notebooks import package code only and smoke tests pass.

## Milestone 12: CI/package quality

Deliverables: GitHub Actions, ruff, pyright initial, coverage, branch protection, README update.

Done when CI blocks shortcut regressions.

## Milestone 13: Foundation review

Done when all foundation examples run, outputs inspect cleanly, guardrails pass, and no public placeholders remain.

## Explicitly deferred

Do not implement real PETase kinetics, fungal growth physiology, cellulose/lignin/chitin mechanisms, metabolism, real literature calibration, or real biological parameter sets before this sequence is complete.
