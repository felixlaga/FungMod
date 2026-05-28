# FungMod Progress

This is the active progress ledger for the long-term architecture roadmap in
`FungMod_long_term_architecture_roadmap.md`.

Update this file whenever a feature, test, example, notebook, or architectural
milestone changes. The goal is that a future reader can quickly answer:

- what FungMod can do today;
- what is still only a roadmap item;
- what scientific assumptions are implemented;
- what failure modes are tested;
- which examples and tests prove the current behavior.

Status key:

- `complete`: implemented and tested for the stated scope.
- `partial`: useful infrastructure exists, but the roadmap stage is not fully complete.
- `not started`: no new long-term-roadmap implementation exists yet.
- `blocked`: implementation needs a decision, dependency, or sourced data.

## Foundation-First Reset: Milestone 1 Governance Gate

Date: 2026-05-27

Status: `complete` for the initial governance and architecture guardrail scope.

Completed in this foundation-first pass:

- Added `ARCHITECTURE_DEBT.md` as the required containment register for
  temporary architecture compromises.
- Documented the current narrow transitional debts:
  - `FD-001`: legacy PET workflow still exported from generic workflows;
  - `FD-002`: PET-only substrate branch in YAML loading;
  - `FD-003`: `AssembledModel.run()` is still non-native execution debt.
- Added guardrail tests for:
  - PET/product hardcoding in generic source paths;
  - shortcut/fallback patterns in high-risk modules;
  - current and next-milestone public API expectations.
- Added a GitHub PR template requiring scope, tests, limitations, shortcut
  removal, architecture debt, and progress-doc updates.
- Added a minimal GitHub Actions CI workflow that installs `.[dev]` and runs
  `pytest`.
- Updated the notebook test path to the actual `notebooks/examples/` location
  so notebook smoke checks execute rather than failing on discovery.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 7 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 160 passed.

Next foundation milestone: Milestone 2, generic public API names
(`run_configured_model`, `load_model_config`, and future `ProcessLibrary`)
without faking runnable implementation.

## Foundation-First Reset: Milestone 2 Generic Public API

Date: 2026-05-27

Status: `complete` for generic-first public API introduction.

Completed in this foundation-first pass:

- Added `src/fungal_model/io/model_config.py` with a real `ModelConfig`,
  `load_model_config`, and top-level generic model-config validation.
- Added `src/fungal_model/workflows/configured_model.py` with
  `run_configured_model`.
- Made `run_configured_model` load the generic config and fail with a
  structured `ConfiguredModelRunReport` until registry loading, process
  factories, native `AssembledModel.run()`, and configured output bundles exist.
- Added `ProcessLibrary` as the public foundation process-library name over
  current already-built process objects.
- Exposed `load_model_config`, `run_configured_model`, `ProcessLibrary`,
  `ModelConfig`, `ConfiguredModelExecutionError`, and
  `ConfiguredModelRunReport` from top-level `fungal_model`.
- Removed `run_pet_surface_integration` and `PETSurfaceWorkflowConfig` from
  top-level `fungal_model` exports.
- Kept the legacy PET workflow available from `fungal_model.workflows` and made
  it emit a `DeprecationWarning`.
- Updated README workflow guidance to point at the generic configured-model API.
- Updated `ARCHITECTURE_DEBT.md` with `FD-004` for the structural preflight
  runner boundary.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_full_integration_workflow.py`
- Result: 12 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 162 passed.

Next foundation milestone: Milestone 3, registry-based loading for substrates,
geometries, product maps, and validators.

## Foundation-First Reset: Milestone 3 Registry-Based Loading

Date: 2026-05-27

Status: `complete` for the initial registry-based loader boundary.

Completed in this foundation-first pass:

- Added neutral config parameter parsing in `src/fungal_model/io/parameters.py`.
- Added `src/fungal_model/io/registries.py` with:
  - `SubstrateLoaderRegistry`;
  - `GeometryLoaderRegistry`;
  - `ProductMapRegistry`;
  - `ValidatorRegistry`;
  - `RegistryLookupError`.
- Changed `load_substrate` to delegate through `SubstrateLoaderRegistry`.
- Changed `load_geometry` to delegate through `GeometryLoaderRegistry`.
- Added default non-PET substrate loaders for `generic_solid` and
  `generic_dissolved` foundation benchmark configs.
- Added default geometry loaders for `well_mixed` and `film_1d`.
- Added default product-map loaders for `one_to_one` and `stoichiometric`
  configured state mappings.
- Added default validator loaders for `non_negative` and `mass_balance`.
- Added `src/fungal_model/plugins/pet/` with explicit PET substrate loader
  registration.
- Migrated the legacy PET integration workflow and PET config tests to use the
  explicit PET plugin registry.
- Resolved architecture debt `FD-002`: the generic YAML substrate loader no
  longer imports PET or branches on PET.
- Updated README loader guidance to describe the registry boundary.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_registry_based_loading.py tests/test_config_io.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_full_integration_workflow.py`
- Result: 24 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 168 passed.

Next foundation milestone: Milestone 4, model config object expansion for
homogeneous, PET plugin, and dummy non-PET configs.

## Foundation-First Reset: Milestone 4 Model Config Objects

Date: 2026-05-27

Status: `complete` for generic model-config object loading.

Completed in this foundation-first pass:

- Expanded `src/fungal_model/io/model_config.py` from top-level validation into
  structured config objects:
  - `ConfigReference`;
  - `EntityConfigRefs`;
  - `ParameterSetConfig`;
  - `ProcessConfig`;
  - `InitialStateConfig`;
  - `TimeConfig`;
  - `ValidatorConfig`;
  - `OutputConfig`.
- Kept `load_model_config` generic and made it return structured sections
  without executing loaders, factories, or solvers.
- Added canonical foundation model-config shells:
  - `data/model_configs/toy_homogeneous_ab.yml`;
  - `data/model_configs/toy_surface_pet_plugin.yml`;
  - `data/model_configs/toy_surface_dummy_non_pet.yml`.
- The plugin surface config and dummy non-PET surface config use the same
  `surface_catalysis` process shape and configured state mappings.
- Updated schema validation so `model_config` records are treated as
  config-of-configs rather than raw parameter-set files.
- Added `tests/test_model_config_loading.py`.
- Updated README data/config guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_model_config_loading.py tests/test_config_io.py tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 174 passed.

Next foundation milestone: Milestone 5, product-map configs and loader path
for configured product-state mappings.

## Foundation-First Reset: Milestone 5 Product-Map Configs

Date: 2026-05-27

Status: `complete` for file-backed product-map config loading.

Completed in this foundation-first pass:

- Added `src/fungal_model/io/product_maps.py` with `load_product_map`.
- Extended `ProductReleaseMap` with optional `name`, `maturity`, and `source`
  metadata while preserving existing process compatibility.
- Updated `ProductMapRegistry` loaders to preserve product-map metadata from
  config files.
- Added canonical product-map configs:
  - `data/product_maps/toy_surface_plugin_mass_equivalent.yml`;
  - `data/product_maps/toy_surface_dummy_mass_equivalent.yml`.
- Updated the plugin surface and dummy non-PET surface model configs to
  reference product-map files instead of embedding product maps inline.
- Added tests proving product maps load from files, preserve arbitrary state
  names, fail on unknown map types, and are referenced from surface model
  configs.
- Updated README data/config guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_product_map_configs.py tests/test_model_config_loading.py tests/test_registry_based_loading.py tests/test_config_io.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 31 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 178 passed.

Next foundation milestone: Milestone 6, process factory library foundation.

## Foundation-First Reset: Milestone 6 Process Factory Library

Date: 2026-05-27

Status: `complete` for the foundation process-factory layer.

Completed in this foundation-first pass:

- Added `src/fungal_model/processes/factories.py` with:
  - `BuildDecision`;
  - `ProcessBuildContext`;
  - `ProcessFactory`;
  - `FirstOrderFactory`;
  - `MassActionFactory`;
  - `HomogeneousMichaelisMentenFactory`;
  - `SurfaceCatalysisFactory`;
  - `default_foundation_factories`.
- Extended `ProcessLibrary` so it can register factories, reject duplicate
  factories, return a factory by process type, build decisions, and build
  process objects from structured `ProcessConfig` entries.
- Kept existing `ProcessRegistry` behavior intact for already-built process
  objects.
- Verified that:
  - homogeneous `toy_homogeneous_ab.yml` builds through the first-order factory;
  - plugin surface and dummy non-PET surface configs build through the same
    generic surface factory;
  - mass-action and homogeneous Michaelis-Menten factories build generic process
    objects;
  - missing state units/product maps produce structured `BuildDecision`
    failures;
  - the factory module contains no plugin imports or domain names.
- Updated `run_configured_model` preflight reporting so it now names missing
  process-factory wiring, not a missing process-factory library.
- Updated README process-library guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_process_factory_library.py tests/test_model_config_loading.py tests/test_product_map_configs.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 29 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 188 passed.

Next foundation milestone: Milestone 7, native `AssembledModel.run()`.

## Current Roadmap Slice

Current active milestone: **Milestones 1-10 complete for the first roadmap
implementation slice**.

Status: `complete` for the tested scope documented below. Remaining work is
future expansion beyond the first long-term architecture pass.

Completed milestone: **Milestone 2: Generic result object**.

Milestone 2 status: `complete` for the first standardized result/export scope.

Completed in Milestone 2:

- Added `src/fungal_model/results/result.py`.
- Added `src/fungal_model/results/__init__.py`.
- Exposed roadmap `SimulationResult` from top-level `fungal_model`.
- Added a standard result wrapper that can be built from:
  - existing well-mixed ODE results;
  - existing 1D reaction-diffusion results.
- Added state and rate accessors:
  - `state(name)`
  - `rate(name)`
- Added validation attachment and validation report export.
- Added plot methods:
  - `plot_state`
  - `plot_states`
  - `plot_rates`
  - `plot_mass_balance`
- Added standardized output saving:
  - `record.json`
  - `model_assembly_report.json`
  - `assumptions.json`
  - `parameters.csv`
  - `validation_report.json`
  - `solver_report.json`
  - `state_trajectories.csv`
  - `process_rates.csv`
  - `derived_quantities.csv`
  - `figures/state_trajectories.png`
  - `figures/process_rates.png`
  - optional `figures/mass_balance.png`
  - `logs/warnings.txt`
  - `logs/provenance_report.md`
- Updated examples 01-06 to save standardized result outputs while preserving
  their existing legacy files and plots.
- Added `tests/test_results.py`.

Milestone 2 verification:

- `./.venv/bin/python -m pytest tests/test_results.py tests/test_simulation_record.py`
- Result: 4 passed.
- Re-ran examples 01-06 successfully.

Completed milestone: **Milestone 3: Generic homogeneous kinetics**.

Milestone 3 status: `complete` for the first generic homogeneous process scope.

Completed in Milestone 3:

- Added `src/fungal_model/processes/homogeneous.py`.
- Added generic homogeneous process classes:
  - `FirstOrderDecayProcess`
  - `MassActionProcess`
  - `HomogeneousMichaelisMentenProcess`
- Added `homogeneous_process_assumption`.
- Added `as_reaction()` adapters so the new process classes can run through the
  existing ODE `SimulationEngine` before the future process solver exists.
- Updated process and top-level package exports.
- Migrated examples 01 and 02 to build reactions from generic homogeneous
  process classes.
- Added `tests/test_homogeneous_processes.py`.

Milestone 3 behavior now available:

- First-order homogeneous decay/product formation can be declared as a generic
  process and converted into a runnable `Reaction`.
- Generic mass-action processes check state units and rate units.
- Generic homogeneous Michaelis-Menten processes support:
  - classic `Vmax * S / (Km + S)`;
  - enzyme-explicit `kcat * E * S / (Km + S)`;
  - required parameter declarations for model assembly.
- Homogeneous process assumptions stay generic and do not mention PET.

Milestone 3 verification:

- `./.venv/bin/python -m pytest tests/test_homogeneous_processes.py tests/test_michaelis_menten.py tests/test_reaction_engine.py`
- Result: 16 passed.
- Re-ran examples 01 and 02 successfully after migration.

Completed milestone: **Milestone 4: Generic surface process refactor**.

Milestone 4 status: `complete` for the first generic surface-process scope.

Completed in Milestone 4:

- Added `src/fungal_model/processes/surface.py`.
- Added generic surface process components:
  - `AccessibleSitePool`
  - `AccessibleSurfaceAreaModel`
  - `LangmuirAdsorptionModel`
  - `EquilibriumSurfaceCoverageModel`
  - `SurfaceCatalysisModel`
  - `ProductReleaseMap`
  - `SurfaceCatalysisProcess`
  - `BondCleavageProcess` alias
  - `surface_catalysis_rate`
- Added `PETAccessibleSurfaceAreaModel` to `src/fungal_model/substrates/pet.py`.
- Added `pet_product_release_map` for the current mass-equivalent PET benchmark.
- Refactored `PETSurfaceHydrolysisRateLaw` so no-modifier PET surface
  hydrolysis delegates to a generic `SurfaceCatalysisProcess`.
- Kept environmental PET scaling working by applying temperature/pH modifiers
  around the generic `surface_catalysis_rate`.
- Updated process, substrate, and top-level exports.
- Added `tests/test_generic_surface_processes.py`.
- Updated `README.md` with the new roadmap capabilities and limitations.

Milestone 4 behavior now available:

- A generic surface catalysis process can run a dummy non-PET solid substrate.
- Generic surface modules do not import PET-specific modules.
- PET exposes accessibility and product-release composition pieces instead of
  making the generic surface machinery live inside PET.
- PET can still run through the existing `PETSurfaceHydrolysisRateLaw` API.
- PET can also expose its generic composed process through
  `PETSurfaceHydrolysisRateLaw.as_generic_process()`.
- Missing PET accessible surface area still fails honestly.
- The PET mass-equivalent benchmark product map can be checked for mass
  conservation.

Milestone 4 verification:

- `./.venv/bin/python -m pytest tests/test_generic_surface_processes.py tests/test_surface_pet.py tests/test_environmental_modifiers.py`
- Result: 26 passed.
- Re-ran examples 03-06 successfully after the generic surface refactor.

Completed milestone: **Milestone 5: Environment object and modifiers**.

Milestone 5 status: `complete` for the first environment/modifier scope.

Completed in Milestone 5:

- Added `src/fungal_model/entities/environment.py`.
- Added `src/fungal_model/entities/__init__.py`.
- Added `Environment` with temperature, pH, oxygen, water activity, nutrient,
  ionic-strength, pressure, boundary-condition, validity-label, source, notes,
  and assumptions fields.
- Added environment validation and unit checks.
- Added `src/fungal_model/modifiers/`.
- Added environment-driven modifiers:
  - `TemperatureModifier`
  - `PHModifier`
  - `WaterActivityModifier`
  - `OxygenModifier`
  - `ProductInhibitionModifier`
- Added explicit assumptions for water activity, oxygen limitation, and product
  inhibition modifiers.
- Exposed environment and modifiers from top-level `fungal_model`.
- Added `tests/test_environment_modifiers.py`.

Milestone 5 behavior now available:

- Modifiers read environmental values from an `Environment` object rather than
  loose parameters.
- Temperature and pH modifiers reuse the existing Arrhenius and Gaussian pH
  implementations.
- Water activity can explicitly block rates below a sourced threshold.
- Oxygen can explicitly limit rates through a Monod-style activity.
- Product inhibition can explicitly reduce rates from a named product state.

Milestone 5 verification:

- `./.venv/bin/python -m pytest tests/test_environment_modifiers.py tests/test_environmental_modifiers.py`
- Result: 16 passed.

Completed milestone: **Milestone 6: Geometry abstraction**.

Milestone 6 status: `complete` for the first geometry abstraction scope.

Completed in Milestone 6:

- Added `src/fungal_model/geometry/`.
- Added base `Geometry` metadata object.
- Added functional `WellMixedGeometry`.
- Added functional `Film1DGeometry` wrapping the existing `UniformGrid1D`.
- Added explicit metadata placeholders:
  - `ParticleGeometry`
  - `SlabGeometry`
  - `PorousMediumGeometry`
- Added geometry assumptions and provenance/source checks.
- Exposed geometry classes from top-level `fungal_model`.
- Added `tests/test_geometry_abstractions.py`.

Milestone 6 behavior now available:

- Well-mixed models can carry explicit volume, optional surface area, and
  area/volume ratio metadata.
- 1D film models can carry explicit grid and boundary-condition metadata.
- Particle, slab, and porous-medium objects record metadata honestly without
  pretending solver support exists.

Milestone 6 verification:

- `./.venv/bin/python -m pytest tests/test_geometry_abstractions.py tests/test_reaction_diffusion.py`
- Result: 11 passed.

Completed milestone: **Milestone 7: Fungus/enzyme/process compatibility**.

Milestone 7 status: `complete` for the first compatibility-matching scope.

Completed in Milestone 7:

- Added `src/fungal_model/entities/enzyme.py`.
- Added explicit `Enzyme` entity with:
  - enzyme class;
  - target bond types;
  - target substrate names/classes;
  - catalytic and adsorption parameter sets;
  - pH/temperature profile placeholders;
  - validity labels;
  - assumptions, source, and notes.
- Added `Enzyme.compatible_with_substrate`.
- Extended `EnzymeProfile` with `compatible_capabilities`.
- Extended `Fungus` with explicit `uptake_capabilities` and
  `can_assimilate_product`.
- Extended `ModelBuilder` and `ModelAssemblyContext` with `enzymes`.
- Added `CompatibilityIssue` to assembly reports.
- Added assembly failure for incompatible mechanisms through
  `InvalidMechanismError`.
- Added compatibility checks for generic surface-catalysis processes:
  - missing catalyst entity;
  - incompatible enzyme/substrate/bond pairing;
  - fungus lacking a matching enzyme capability.
- Exposed `Enzyme` and `CompatibilityIssue` from package exports.
- Added `tests/test_enzyme_compatibility.py`.
- Updated `README.md`.

Milestone 7 behavior now available:

- Isolated enzyme surface systems can assemble without a fungus when a
  compatible enzyme entity is supplied.
- Living-fungus surface systems require the fungus to declare a compatible
  enzyme capability.
- Incompatible enzyme, substrate, and target-bond pairings fail with structured
  assembly reports.
- Product uptake/assimilation capability is explicit on the fungus.
- Living-fungus process assembly can block on unknown secretion parameters.

Milestone 7 verification:

- `./.venv/bin/python -m pytest tests/test_enzyme_compatibility.py tests/test_process_assembly.py tests/test_fungal_dynamics.py`
- Result: 24 passed.

Completed in this slice:

- Added structured assembly errors in `src/fungal_model/core/errors.py`:
  - `ModelAssemblyError`
  - `MissingProcessError`
  - `MissingParameterError`
  - `IncompatibleUnitsError`
  - `InvalidMechanismError`
- Added generic process contracts in `src/fungal_model/processes/base.py`:
  - `Process`
  - `StateVariableSpec`
  - `ParameterRequirement`
  - `ValidityDomain`
- Added a generic registry in `src/fungal_model/processes/registry.py`:
  - `ProcessRegistry`
  - `MissingProcessIssue`
  - empty `ProcessRegistry.default()` for the current milestone
- Added model assembly scaffolding in `src/fungal_model/processes/assembly.py`:
  - `ModelAssemblyContext`
  - `ProcessMatch`
  - `ParameterIssue`
  - `AssemblyReport`
  - `AssembledModel`
  - `ModelBuilder`
- Added `src/fungal_model/processes/__init__.py` exports.
- Updated top-level package exports in `src/fungal_model/__init__.py`.
- Updated core exports in `src/fungal_model/core/__init__.py`.
- Added assembly tests in `tests/test_process_assembly.py`.

Milestone 1 behavior now available:

- A model can request named process types.
- A `ProcessRegistry` can match registered generic processes.
- Missing mechanisms fail with `MissingProcessError`.
- Missing parameters fail with `MissingParameterError`.
- Explicitly unknown parameters fail instead of receiving fallback constants.
- Missing provenance fails in scientific mode.
- Unsourced parameters are allowed only with `allow_unsourced_for_testing=True`.
- Incompatible parameter units fail separately with `IncompatibleUnitsError`.
- Assembly reports are both machine-readable (`to_dict`) and human-readable
  (`human_readable`).
- A successful assembly produces an `AssembledModel` containing matched
  processes, state variables, parameters, assumptions, validators, solver
  settings, and the assembly report.

Important deliberate limitation:

- `AssembledModel.run()` is a placeholder. Solver-backed execution through the
  process architecture belongs to later milestones. Current runnable models
  still use the existing `SimulationEngine` and `ReactionDiffusionEngine1D`.

Milestone 1 tests added:

- missing process gives a structured report;
- matched process with absent parameter gives a structured missing-parameter
  report;
- unknown parameter value blocks assembly;
- missing parameter provenance blocks assembly;
- testing escape hatch for unsourced parameters is explicit;
- incompatible units are reported separately;
- successful assembly exports state variables, assumptions, solver settings,
  and report data;
- generic process modules do not import PET-specific modules.

Verification:

- `./.venv/bin/python -m pytest tests/test_process_assembly.py`
- Result: 8 passed.

Full-suite verification for this slice:

- `./.venv/bin/python -m pytest`
- Result: 108 passed.

## Current Codebase Capability Inventory

### Scientific Governance

Status: `complete` for the existing foundation.

FungMod can:

- represent scientific parameters with names, symbols, values, units,
  uncertainties, sources, confidence levels, notes, and measurement methods;
- represent unknown parameters explicitly with `value=None`;
- require provenance before scientific runs;
- allow unsourced values only through explicit testing escape hatches;
- serialize parameter sets to JSON and YAML;
- represent modelling assumptions separately from parameters;
- enforce unit-bearing quantities through a shared `pint` registry.

Core files:

- `src/fungal_model/core/parameters.py`
- `src/fungal_model/core/provenance.py`
- `src/fungal_model/core/assumptions.py`
- `src/fungal_model/core/units.py`
- `src/fungal_model/core/errors.py`

### Existing Well-Mixed Solver

Status: `complete` for deterministic ODE reaction systems.

FungMod can:

- run deterministic well-mixed ODE models through `SimulationEngine`;
- use generic `Reaction` objects with unit-checked rate laws;
- validate reaction provenance before scientific execution;
- require unit-bearing initial states and simulation times;
- record solver settings and solver metadata;
- return unit-bearing `SimulationResult` objects;
- create reproducible `SimulationRecord` JSON outputs.

Current limitation:

- This solver works with `Reaction` objects, not yet with the new
  process-centered `AssembledModel`.

Core files:

- `src/fungal_model/chemistry/reactions.py`
- `src/fungal_model/core/simulation.py`

### Validation

Status: `partial` relative to the long-term roadmap; substantial existing
foundation is implemented.

FungMod can validate:

- non-negativity;
- weighted mass balance;
- carbon conservation;
- oxygen limitation;
- biomass yield bounds;
- limiting-case suites;
- selected spatial checks for 1D diffusion and reaction-diffusion models.

Current limitations:

- Validation results do not yet use the roadmap's richer severity/residual
  schema everywhere.
- Validators are not yet automatically attached by the new `ModelBuilder`.
- Thermodynamic feasibility is metadata-supported but not solver-enforced.

Core files:

- `src/fungal_model/core/validators.py`
- `src/fungal_model/validation/`

### Homogeneous Kinetics

Status: `complete` for the existing dissolved-substrate benchmark layer;
`partial` relative to the future process architecture.

FungMod can:

- compute homogeneous Michaelis-Menten rates;
- compute enzyme-explicit Michaelis-Menten rates;
- wrap homogeneous kinetics as `Reaction` rate laws;
- check low-substrate, high-substrate, zero-substrate, zero-enzyme, and unit
  limiting cases.

Current limitations:

- Homogeneous process classes can adapt to the existing ODE `Reaction` engine,
  but `AssembledModel.run()` is still a future native process solver.
- PET is explicitly not treated as a valid dissolved-substrate default.

Core files:

- `src/fungal_model/kinetics/michaelis_menten.py`

### Surface and PET Kinetics

Status: `partial`.

FungMod can:

- represent PET as a solid polyester substrate with explicit unknown material
  parameters by default;
- derive accessible PET surface area from supplied surface area, roughness, and
  amorphous fraction/crystallinity metadata;
- compute Langmuir equilibrium surface coverage;
- run a PET-specific surface hydrolysis rate law through the existing
  `Reaction` engine;
- apply Arrhenius temperature and Gaussian pH modifiers to the PET surface
  hydrolysis rate law.

Current limitations:

- Generic surface catalysis exists and PET composes it through
  `PETAccessibleSurfaceAreaModel`, but the workflow still executes through the
  current ODE reaction adapter rather than a native process solver.
- PET product release is still represented in examples and the integration
  workflow as a simplified lumped mass-equivalent hydrolysate where noted.
- Dynamic adsorption/desorption states, evolving morphology, and resolved
  MHET/BHET/TPA/EG product stoichiometry remain future work.

Core files:

- `src/fungal_model/substrates/pet.py`
- `src/fungal_model/kinetics/langmuir.py`
- `src/fungal_model/kinetics/surface_kinetics.py`
- `src/fungal_model/kinetics/arrhenius.py`
- `src/fungal_model/kinetics/ph.py`

### Universal Substrate Metadata

Status: `partial`.

FungMod can:

- represent generic substrate metadata through `Substrate`;
- represent degradation products without assuming assimilation;
- create explicit unknown parameter sets for substrate metadata;
- expose placeholder metadata classes for cellulose, lignin, starch, and
  chitin;
- keep PET marked as the only currently partial substrate with an implemented
  process path.

Current limitations:

- Placeholder substrates do not yet assemble into scientific kinetic models.
- Substrate maturity levels from the roadmap are conceptually present through
  `completeness`, but not yet enforced by the new process registry.

Core files:

- `src/fungal_model/substrates/base.py`
- `src/fungal_model/substrates/pet.py`
- `src/fungal_model/substrates/cellulose.py`
- `src/fungal_model/substrates/lignin.py`
- `src/fungal_model/substrates/starch.py`
- `src/fungal_model/substrates/chitin.py`

### Fungal Dynamics

Status: `partial`.

FungMod can:

- represent basic fungus metadata;
- represent enzyme capabilities and enzyme profiles;
- model enzyme secretion from active biomass;
- model enzyme production cost;
- model enzyme decay;
- model active-biomass maintenance loss;
- gate product uptake and growth through explicit product-assimilation
  evidence;
- prevent non-assimilable products from causing biomass growth.

Current limitations:

- Fungi and enzymes now participate in model-builder compatibility matching,
  but the builder does not yet auto-generate full living-fungus ODE systems.
- Living-fungus simulations still use existing `Reaction` rate laws rather than
  native process-registry solver execution.

Core files:

- `src/fungal_model/fungi/base.py`
- `src/fungal_model/fungi/enzyme_profile.py`
- `src/fungal_model/fungi/growth.py`
- `src/fungal_model/fungi/metabolism.py`

### Stoichiometry and Thermodynamics

Status: `partial`.

FungMod can:

- parse elemental formula strings;
- represent stoichiometric reaction metadata;
- detect balanced and unbalanced stoichiometry;
- represent carbon-content metadata for state variables;
- represent oxygen-demand metadata;
- represent Gibbs free energy estimates with provenance.

Current limitations:

- Gibbs free energy is not yet enforced as a thermodynamic feasibility
  constraint during solving.
- Redox balance is not yet implemented as a process or validator beyond the
  current oxygen-demand checks.

Core files:

- `src/fungal_model/chemistry/stoichiometry.py`
- `src/fungal_model/chemistry/thermodynamics.py`

### Spatial Transport

Status: `partial`.

FungMod can:

- represent a uniform 1D finite-volume grid;
- represent no-flux, fixed-value, and periodic boundary conditions;
- compute a 1D finite-volume diffusion operator;
- run a 1D method-of-lines reaction-diffusion model;
- validate no-flux conservation, gradient smoothing, and high-diffusion
  well-mixed behavior.

Current limitations:

- Geometry metadata is now exposed through the roadmap `Geometry` hierarchy,
  but transport is not yet a `DiffusionProcess` assembled by `ModelBuilder`.
- 2D/3D, porous media, advection, and dynamic surface/volume coupling are not
  implemented.

Core files:

- `src/fungal_model/transport/geometry.py`
- `src/fungal_model/transport/diffusion.py`
- `src/fungal_model/transport/reaction_diffusion.py`

### Calibration

Status: `partial`.

FungMod can:

- compute unit-aware residuals;
- split sequential train/validation data;
- fit selected parameters with bounded least squares;
- report failed optimizer/model runs without hiding them;
- serialize fit results, residuals, covariance diagnostics, approximate
  confidence intervals where valid, and warnings.

Current limitations:

- Bayesian calibration is a placeholder.
- Calibration is generic but not yet integrated into the future result/output
  system.

Core files:

- `src/fungal_model/calibration/residuals.py`
- `src/fungal_model/calibration/fitting.py`
- `src/fungal_model/calibration/bayesian.py`

### Uncertainty and Sensitivity

Status: `partial`.

FungMod can:

- run Monte Carlo uncertainty propagation for normal, uniform, and lognormal
  parameter uncertainty specifications;
- preserve sample provenance;
- summarize output quantiles;
- run local finite-difference sensitivity analysis with dimensional and
  normalized sensitivities.

Current limitations:

- Global sensitivity is not implemented.
- Uncertainty bands are not yet integrated with a first-class roadmap
  `SimulationResult` plotting system.

Core files:

- `src/fungal_model/uncertainty/monte_carlo.py`
- `src/fungal_model/uncertainty/sensitivity.py`

### Examples

Status: `complete` for the current runnable example set.

Current examples demonstrate:

- first-order well-mixed reaction;
- homogeneous Michaelis-Menten dissolved-substrate benchmark;
- PET surface hydrolysis;
- PET surface hydrolysis with temperature and pH modifiers;
- fungal enzyme secretion and product-coupled growth;
- 1D PET film enzyme diffusion and local hydrolysis;
- Stage 12 wrapper examples for the current canonical examples.

Current limitations:

- Examples now save standardized result outputs, but most still use the
  existing solver/rate-law architecture rather than native process-centered
  solver execution.

Core files:

- `examples/`

### Notebooks

Status: `complete` for the first required notebook/smoke-test scope.

Implemented notebooks:

- `notebooks/00_quickstart.ipynb`
- `notebooks/01_process_library_demo.ipynb`
- `notebooks/02_surface_hydrolysis_demo.ipynb`
- `notebooks/03_fungus_on_pet_demo.ipynb`
- `notebooks/04_reaction_diffusion_demo.ipynb`
- `notebooks/05_calibration_and_uncertainty_demo.ipynb`

Important rule:

- Notebooks must import package code and demonstrate workflows. They must not
  contain core model implementation.
- `tests/test_notebooks.py` enforces that notebooks import `fungal_model`, do
  not define core classes/rate laws, and the quickstart notebook can execute as
  a smoke test.

### Data and Configuration

Status: `complete` for the first YAML schema/loader scope.

Implemented top-level folders:

- `data/fungi/`
- `data/substrates/`
- `data/enzymes/`
- `data/environments/`
- `data/geometries/`
- `data/parameters/`
- `data/experiments/`

Current behavior:

- YAML configs load into `Environment`, `Enzyme`, `Fungus`, `Substrate`,
  `Geometry`, and `ParameterSet` objects.
- Configs require top-level provenance and parameter-level source,
  measurement-method, confidence, notes, validity-range, units, and value
  fields.
- Unknown values remain explicit `value: null` inputs and become unknown
  `Parameter` objects instead of guessed numbers.

## Long-Term Roadmap Status

### Milestone 1: Process base classes

Status: `complete` for the skeleton scope.

Done:

- Process contracts.
- Process registry.
- Model builder skeleton.
- Structured assembly report.
- Structured assembly errors.
- Missing process and missing parameter tests.

Remaining future expansion:

- Entity-aware compatibility matching.
- Process-to-solver execution.
- Automatic validator selection.

### Milestone 2: Generic result object

Status: `complete` for the first standardized result/export scope.

Implemented:

- `src/fungal_model/results/result.py`
- `src/fungal_model/results/__init__.py`
- standardized `results.SimulationResult`
- ODE and reaction-diffusion wrapper constructors
- report/table/log/figure export
- result-generated plots
- tests in `tests/test_results.py`

Still required:

- make the roadmap result object the native output of all solvers rather than
  a wrapper around current solver results;
- add specialized plots for carbon, oxygen, spatial profiles, uncertainty
  bands, and calibration diagnostics.

### Milestone 3: Generic homogeneous kinetics

Status: `complete` for the first generic homogeneous process scope.

Implemented:

- `HomogeneousMichaelisMentenProcess`
- `MassActionProcess`
- `FirstOrderDecayProcess`
- `as_reaction()` adapters for current ODE engine execution
- examples 01 and 02 migrated to generic process classes
- tests in `tests/test_homogeneous_processes.py`

Still required:

- native process solver execution through `AssembledModel.run()`;
- richer process-rate recording from homogeneous processes.

### Milestone 4: Generic surface process refactor

Status: `complete` for the first generic surface-process scope.

Implemented:

- generic adsorption model in process form;
- generic surface catalysis/bond cleavage process;
- accessible site/surface model;
- product release map;
- PET accessibility adapter;
- PET migration to generic process composition;
- dummy non-PET substrate surface test.

Still required:

- dynamic adsorption/desorption states;
- resolved PET product maps beyond the current mass-equivalent benchmark;
- dynamic morphology/accessibility evolution;
- full entity compatibility matching for enzyme class, target bond, substrate,
  environment, and geometry.

### Milestone 5: Environment object and modifiers

Status: `complete` for the first environment/modifier scope.

Implemented:

- `Environment` entity.
- Temperature, pH, water activity, oxygen, and product inhibition modifiers.
- Tests in `tests/test_environment_modifiers.py`.

Still required:

- richer modifier plots and automatic modifier selection during assembly.

### Milestone 6: Geometry abstraction

Status: `complete` for the first geometry abstraction scope.

Implemented:

- roadmap `Geometry` hierarchy;
- functional well-mixed and 1D film geometry wrappers;
- particle, slab, and porous-medium metadata placeholders;
- tests in `tests/test_geometry_abstractions.py`.

Still required:

- process-native diffusion assembly and richer geometry-specific solvers.

### Milestone 7: Fungus/enzyme/process compatibility

Status: `complete` for the first compatibility-matching scope.

Implemented:

- explicit enzyme entities;
- compatibility matching between fungus, enzyme, substrate bond, and surface
  catalysis processes;
- clear assembly failures for missing biological capability;
- tests in `tests/test_enzyme_compatibility.py`.

Still required:

- broader environment and geometry compatibility rules for every process type.

### Milestone 8: Notebooks

Status: `complete` for the first required notebook/smoke-test scope.

Implemented:

- `/notebooks`;
- required six notebooks;
- notebook structure and smoke tests in `tests/test_notebooks.py`.

Still required:

- richer executed notebook snapshots as workflows mature.

### Milestone 9: Data/config schemas

Status: `complete` for the first YAML schema/loader scope.

Implemented:

- YAML loaders;
- JSON export helper;
- schema validation;
- example configs with provenance;
- unknown-value handling in config files;
- tests in `tests/test_config_io.py`.

Still required:

- full versioned schemas and broader literature-backed config libraries.

### Milestone 10: First full integration workflow

Status: `complete` for the first config-driven PET surface integration scope.

Implemented:

- `src/fungal_model/workflows/pet_surface_integration.py`;
- one fungus/enzyme/PET/environment/geometry workflow assembled through the
  registry and model builder;
- standardized output folder with reports, tables, logs, figures, input
  configs, and entity JSON snapshots;
- validation and process-rate plots;
- honest failure when accessible PET surface area is missing;
- honest failure when enzyme/substrate metadata are incompatible;
- tests in `tests/test_full_integration_workflow.py`.

Still required:

- native execution through `AssembledModel.run()`;
- resolved PET product chemistry;
- broader living-fungus dynamics assembled from configs.

## Anti-Cheating Checklist Status

Implemented in current tests:

- missing process fails with `MissingProcessError`;
- missing parameter fails with `MissingParameterError`;
- missing provenance fails in scientific assembly mode;
- incompatible units fail with `IncompatibleUnitsError`;
- generic process modules do not import PET-specific modules;
- generic surface hydrolysis works with PET and a dummy non-PET substrate;
- PET composes generic surface processes through a PET accessibility adapter;
- incompatible fungus/substrate/enzyme pairings fail in model assembly;
- non-assimilable product cannot cause biomass growth;
- roadmap result object saves standardized files, plots, logs, and reports;
- notebooks import from `fungal_model` and do not define core rate laws/classes;
- zero enzyme, zero accessible surface, zero substrate, and zero PET mass checks
  exist for current PET rate-law tests;
- high diffusion approaches well-mixed behavior in existing spatial tests.

Still required:

- oxygen cannot be consumed if oxygen process is absent or unavailable;
- native process-solver execution through `AssembledModel.run()`;
- resolved product stoichiometry for PET surface hydrolysis.

## How To Verify

Focused Milestone 1 tests:

```bash
.venv/bin/python -m pytest tests/test_process_assembly.py
```

Full test suite:

```bash
.venv/bin/python -m pytest
```

Current focused verification:

- 2026-05-26: `tests/test_process_assembly.py` passed with 8 tests.

Current full-suite verification:

- 2026-05-26: full test suite passed with 141 tests after Milestones 5-7.
- 2026-05-26: full test suite passed with 153 tests after Milestones 8-10.

Completed milestone: **Milestone 8: Notebooks**.

Milestone 8 status: `complete` for the first required notebook/smoke-test scope.

Completed in Milestone 8:

- Added top-level `/notebooks`.
- Added required notebooks:
  - `notebooks/00_quickstart.ipynb`
  - `notebooks/01_process_library_demo.ipynb`
  - `notebooks/02_surface_hydrolysis_demo.ipynb`
  - `notebooks/03_fungus_on_pet_demo.ipynb`
  - `notebooks/04_reaction_diffusion_demo.ipynb`
  - `notebooks/05_calibration_and_uncertainty_demo.ipynb`
- The quickstart notebook creates entities, assembles a generic PET surface
  process, runs through the current ODE engine, validates, plots, and saves
  standardized outputs.
- Added `tests/test_notebooks.py`.

Milestone 8 verification:

- `./.venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.

Completed milestone: **Milestone 9: Data/config schemas**.

Milestone 9 status: `complete` for the first YAML schema/loader scope.

Completed in Milestone 9:

- Added top-level data folders:
  - `data/fungi/`
  - `data/substrates/`
  - `data/enzymes/`
  - `data/environments/`
  - `data/geometries/`
  - `data/parameters/`
  - `data/experiments/`
- Added example configs:
  - `data/substrates/pet_film.yml`
  - `data/substrates/cellulose_powder.yml`
  - `data/fungi/toy_pet_fungus.yml`
  - `data/fungi/pleurotus_ostreatus.yml`
  - `data/enzymes/petase_like.yml`
  - `data/environments/lab_30C_pH7.yml`
  - `data/geometries/well_mixed_100ml.yml`
  - `data/geometries/pet_film_1d.yml`
  - `data/parameters/pet_surface_benchmark.yml`
  - `data/experiments/synthetic_pet_surface.yml`
- Added `src/fungal_model/io/`.
- Added schema validation in `src/fungal_model/io/schema.py`.
- Added YAML loaders in `src/fungal_model/io/yaml_loader.py`.
- Added JSON export helper in `src/fungal_model/io/json_export.py`.
- Exposed loaders from top-level `fungal_model`.
- Added `tests/test_config_io.py`.

Milestone 9 behavior now available:

- YAML configs must include top-level provenance fields.
- Parameter entries must include source, measurement method, confidence level,
  notes, validity range, units, and value.
- Unknown values remain `value: null` and load as explicit unknown parameters.
- Example configs can load into `Environment`, `Enzyme`, `PETSubstrate`,
  `Fungus`, `WellMixedGeometry`, `Film1DGeometry`, and `ParameterSet`.

Milestone 9 verification:

- `./.venv/bin/python -m pytest tests/test_config_io.py`
- Result: 6 passed.

Most recently completed milestone: **Milestone 10: First full integration workflow**.

Milestone 10 status: `complete` for the first config-driven PET surface
integration scope.

Completed in Milestone 10:

- Added `src/fungal_model/workflows/pet_surface_integration.py`.
- Added `src/fungal_model/workflows/__init__.py`.
- Exposed `PETSurfaceWorkflowConfig` and `run_pet_surface_integration` from
  top-level `fungal_model`.
- The workflow loads the example configs for:
  - PET film substrate;
  - PETase-like enzyme;
  - toy PET-capable fungus;
  - lab temperature/pH environment;
  - well-mixed geometry;
  - PET surface benchmark parameters.
- The workflow assembles generic surface catalysis through `ModelBuilder` and
  `ProcessRegistry`.
- The workflow runs the assembled process through the current ODE adapter,
  validates non-negativity and mass balance, records process-rate trajectories,
  and wraps the run in standardized `results.SimulationResult`.
- The workflow saves the full standardized output folder plus:
  - `input_configs.json`
  - `substrate.json`
  - `enzyme.json`
  - `fungus.json`
  - `environment.json`
  - `geometry.json`
- Added `tests/test_full_integration_workflow.py`.

Milestone 10 behavior now available:

- A complete config-driven PET surface run can be launched from
  `run_pet_surface_integration(output_dir)`.
- Missing accessible PET surface area fails before simulation with
  `MissingParameterError` and a structured assembly report.
- Incompatible enzyme/substrate metadata fails before simulation with
  `InvalidMechanismError` and structured compatibility issues.
- The saved output folder contains reports, tables, figures, logs, provenance,
  input config references, and entity snapshots.

Milestone 10 verification:

- `./.venv/bin/python -m pytest tests/test_full_integration_workflow.py`
- Result: 3 passed.

## Foundation-First Reset: Milestone 7 Native AssembledModel.run

Date: 2026-05-27

Milestone 7 status: `complete` for the first native assembled-model execution
scope.

Completed in Milestone 7:

- Added `src/fungal_model/solvers/process_ode.py`.
- Added `RunRequest` and `ProcessODESolver`.
- Implemented `AssembledModel.run()` as a real public execution method.
- `AssembledModel.run()` now delegates to the process ODE solver and returns a
  standardized `SimulationResult`.
- The solver builds derivatives from registered process `rate()` and
  `contributions()` methods.
- Process-rate trajectories are recorded into `SimulationResult.process_rates`.
- Model-level and request-level validators are run against the result.
- Unsupported geometry and mismatched initial states fail before simulation
  with structural `ValueError` messages.
- Resolved architecture debt `FD-003`; the shortcut guardrail no longer
  allowlists public `NotImplementedError` in `AssembledModel.run()`.

Milestone 7 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_native_assembled_model_run.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_public_api.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 192 passed.

Next milestone:

- Milestone 8: wire the generic `run_configured_model` workflow into config
  loading, registries, process factories, `AssembledModel.run()`, result
  validation, and output-bundle saving.

## Foundation-First Reset: Milestone 8 Generic run_configured_model

Date: 2026-05-27

Milestone 8 status: `complete` for the first generic configured-model
execution scope.

Completed in Milestone 8:

- Implemented `run_configured_model` as the generic workflow orchestrator.
- Configured runs now load substrates, geometries, product maps, validators,
  fungi, enzymes, environments, and parameter sets from the config contract.
- Plugin-backed substrate loading remains explicit through caller-supplied
  registries; the generic workflow does not import plugin loaders.
- Added `merge_parameter_sets` with duplicate-identical acceptance and
  duplicate-conflict rejection.
- Configured process entries build through `ProcessLibrary` factories and then
  assemble through `ModelBuilder`.
- Configured execution calls `AssembledModel.run()` and returns
  `SimulationResult`.
- Output saving uses the standard `SimulationResult.save()` bundle and adds
  `input_model_config.json` plus `configured_model_run.json`.
- Added a toy generic surface catalyst config so the dummy non-plugin surface
  benchmark exercises entity compatibility without substrate-specific biology.
- Resolved architecture debt `FD-004`.

Milestone 8 behavior now available:

- `run_configured_model("data/model_configs/toy_homogeneous_ab.yml")` runs the
  homogeneous benchmark through the generic workflow.
- `run_configured_model("data/model_configs/toy_surface_dummy_non_pet.yml")`
  runs the dummy non-plugin surface benchmark through the same workflow.
- `run_configured_model("data/model_configs/toy_surface_pet_plugin.yml",
  substrate_registry=pet_substrate_loader_registry())` runs the explicit plugin
  benchmark through the same workflow.
- Running the plugin config without the explicit registry fails structurally at
  input loading instead of creating a generic substrate-specific branch.

Milestone 8 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_model_config_loading.py tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 198 passed.
- `rg -n "SimulationEngine|ReactionDiffusionEngine|solve_ivp" src/fungal_model/workflows src/fungal_model/plugins/pet`
- Result: no matches.
- Generic PET-hardcoding scan over core/process/results/modifiers/io/workflows
  source paths.
- Result: no matches.

Next milestone:

- Milestone 9: remove or relocate the deprecated direct PET workflow path so
  workflows no longer call lower-level solvers directly.

## Foundation-First Reset: Milestone 9 Workflow Solver Isolation

Date: 2026-05-28

Milestone 9 status: `complete` for workflow-level solver isolation.

Completed in Milestone 9:

- Removed `src/fungal_model/workflows/pet_surface_integration.py`.
- Removed `PETSurfaceWorkflowConfig` and `run_pet_surface_integration` from
  `fungal_model.workflows`.
- Added `src/fungal_model/plugins/pet/workflows.py` as the plugin-local
  compatibility helper.
- The PET plugin helper materializes a generic model config and delegates to
  `run_configured_model` with `pet_substrate_loader_registry()`.
- The plugin helper no longer constructs processes, reactions, or low-level
  solvers directly.
- Tightened `tests/test_guardrails_no_hardcoding.py` by removing the legacy
  PET allowlist for generic workflow paths.
- Resolved architecture debt `FD-001`.

Milestone 9 behavior now available:

- `fungal_model.workflows` exports only generic configured-model workflow
  names.
- PET-specific convenience execution lives under `fungal_model.plugins.pet`.
- Generic workflow source paths no longer contain PET-specific workflow names,
  hardcoded PET states, or direct low-level solver imports.

Milestone 9 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_full_integration_workflow.py tests/test_configured_model_workflow.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_public_api.py tests/test_guardrails_no_shortcuts.py`
- Result: 16 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 198 passed.

Next milestone:

- Milestone 10: harden the result/output foundation for configured runs,
  including complete output metadata and snapshots for generic configs.

## Foundation-First Reset: Milestone 10 Result/Output Foundation

Date: 2026-05-28

Milestone 10 status: `complete` for configured-run output bundles.

Completed in Milestone 10:

- Hardened configured-run output saving around `SimulationResult.save()`.
- Added `configured_metadata.json` with config name, mode, maturity, result
  label, model version, state count, process-rate count, and validation
  summary.
- Expanded `configured_model_run.json` with state names, process-rate names,
  validation summary, and solver metadata.
- Added `process_build_decisions.json` so factory decisions are inspectable.
- Added `initial_state.json`, `time_grid.json`, `validators.json`, and
  `merged_parameters.json`.
- Added `entity_snapshots/` with snapshots for configured fungi, substrates,
  enzymes, environments, geometries, and product maps.
- Added `output_manifest.json` listing the complete saved bundle.
- Updated configured workflow tests so homogeneous, plugin, and non-plugin
  foundation configs all prove the complete output bundle exists.

Milestone 10 behavior now available:

- Every configured foundation benchmark saves a complete output folder.
- Mode and maturity are visible without opening the source config.
- Users can inspect config, entity, parameter, process-build, validation, solver,
  trajectory, plot, and provenance artifacts from the output directory.

Milestone 10 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_full_integration_workflow.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 17 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 199 passed.
- Notebook JSON validation for all four foundation notebooks.
- Result: passed.
- Notebook direct-solver/core-implementation scan.
- Result: no matches.

Next milestone:

- Milestone 11: notebook foundation for generic quickstart, config/entity
  inspection, failure reports, and configured output inspection.

## Foundation-First Reset: Milestone 11 Notebook Foundation

Date: 2026-05-28

Milestone 11 status: `complete` for foundation notebook smoke coverage.

Completed in Milestone 11:

- Replaced the old roadmap notebooks with foundation-first notebooks under
  `notebooks/examples/`.
- Added a generic quickstart notebook that runs
  `data/model_configs/toy_homogeneous_ab.yml` through `run_configured_model`.
- Added a config/entity inspection notebook for the dummy non-plugin surface
  benchmark.
- Added a structured failure-report notebook that captures the expected plugin
  registry failure as a `ConfiguredModelRunReport`.
- Added a configured-output inspection notebook that reads the manifest,
  metadata, build decisions, validators, and result state names.
- Tightened notebook tests so required notebooks import package code, call the
  generic configured workflow, avoid core class/rate-law/solver definitions,
  and execute every foundation notebook smoke path.

Milestone 11 behavior now available:

- Notebooks demonstrate the generic workflow instead of constructing low-level
  solvers.
- Failure handling and output inspection are documented as runnable examples.
- Notebook smoke tests create quickstart, failure-report, and output-inspection
  artifacts under `outputs/`.

Milestone 11 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 199 passed.

Next milestone:

- Milestone 12: package quality and CI discipline, including initial linting,
  type-checking, coverage, and README/CI alignment.
