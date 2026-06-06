# FungMod Foundation-First Roadmap: Start Here

## Purpose

This folder replaces a biology-first roadmap. FungMod should not yet focus on fungal pathways, PETase literature values, cellulose/lignin mechanisms, substrate-specific rate laws, or real biological calibration. Those require papers and careful parameter extraction later.

The immediate goal is to build a clean, generic, deeply tested scientific modeling framework that is at least Atmodeller-level in package architecture, model execution, configuration, validation, outputs, notebooks, documentation, CI, and guardrails.

Long-term foundation target:

> A user can load a model config, assemble a model from generic entities/processes/parameters, run it through a native model object, validate it, save a complete result bundle, inspect assumptions/provenance, and get structured failure reports when something is missing.

No PET-specific execution path should be needed for this.

Long-term general target (only build out specifics fof biology after foundation is perfected):

> Given any fungus, substrate, environment, geometry, and sourced parameters, FungMod can assemble the appropriate physical processes, run the model, validate the result, generate interpretable outputs, and honestly fail when mechanisms or parameters are missing.

## What “Atmodeller-level” means here

It does not mean copying Atmodeller's physics. It means matching its software maturity pattern: installable package, documented public API, notebooks, native solving interface, structured output, reproducible examples, tests, CI, type/lint discipline, and clear limitations.

## Current baseline to transform

FungMod already has useful components: parameters, provenance, assumptions, ODE/reaction-diffusion machinery, process scaffolding, `ModelBuilder`, `ProcessRegistry`, `SimulationResult`, generic homogeneous and surface process components, YAML configs, notebooks, and a PET workflow.

Treat these as unfinished foundation items:

- `AssembledModel.run()` must become the native execution path.
- `run_pet_surface_integration` must stop being central.
- `load_substrate` must become registry-based and non-PET capable.
- workflows must stop manually constructing low-level solvers.
- product maps, state names, validators, and outputs must be config-driven.
- process construction must happen through factories, not hand-bound PET adapters.
- notebooks must demonstrate generic APIs, not workaround paths.
- CI and architecture guardrail tests must block regressions.

## Immediate priority order

1. Add hard guardrail tests.
2. Remove PET from generic execution paths.
3. Implement native `AssembledModel.run()`.
4. Implement generic `run_configured_model()`.
5. Implement registry-based entity/config loading.
6. Implement factory-based process construction.
7. Make PET only one plugin/example.
8. Add non-PET dummy workflows through the exact same path.
9. Make results, validation, notebooks, docs, and CI robust.

## How Codex must proceed

Codex must work milestone by milestone:

1. Pick one milestone.
2. Write failing guardrail/failure tests first.
3. Implement the smallest change that passes those tests.
4. Run the full test suite.
5. Update progress docs.
6. Stop.

Bad task: “Make FungMod Atmodeller-level.”

Good task: “Implement substrate loader registry only. Add PET and non-PET tests. Do not touch solvers.”

## Foundation success criterion

The foundation is ready for biology when these all work through the same generic path:

```python
run_configured_model("data/model_configs/toy_homogeneous_ab.yml")
run_configured_model("data/model_configs/toy_surface_pet_plugin.yml")
run_configured_model("data/model_configs/toy_surface_dummy_non_pet.yml")
```

and unsupported cases fail with structured reports rather than silent guesses.
