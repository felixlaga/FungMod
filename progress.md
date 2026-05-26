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

## Current Roadmap Slice

Current active milestone: **Milestone 1: Process base classes**.

Status: `complete` for the Milestone 1 skeleton scope.

Most recently completed milestone: **Milestone 2: Generic result object**.

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

Most recently completed milestone: **Milestone 3: Generic homogeneous kinetics**.

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

Most recently completed milestone: **Milestone 4: Generic surface process refactor**.

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

- Homogeneous kinetics are still exposed as rate-law classes, not as
  `HomogeneousMichaelisMentenProcess`.
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

- The surface hydrolysis process is still PET-specific
  (`PETSurfaceHydrolysisRateLaw`).
- The roadmap-required generic `SurfaceCatalysisProcess`,
  `AccessibleSurfaceAreaModel`, `ProductReleaseMap`, and dummy non-PET surface
  integration are not implemented yet.
- PET product release is still represented in examples as a simplified lumped
  hydrolysate where noted.

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

- Fungi are not yet full roadmap entities with taxonomy, oxygen dependence,
  environmental tolerance metadata, and model-builder compatibility matching.
- Enzymes are not yet standalone roadmap entities.
- Living-fungus simulations still use existing `Reaction` rate laws rather than
  process-registry assembly.

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

- Geometry is not yet exposed through the roadmap's `Geometry` entity hierarchy.
- Transport is not yet a `DiffusionProcess` assembled by `ModelBuilder`.
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

Status: `partial`.

Current examples demonstrate:

- first-order well-mixed reaction;
- homogeneous Michaelis-Menten dissolved-substrate benchmark;
- PET surface hydrolysis;
- PET surface hydrolysis with temperature and pH modifiers;
- fungal enzyme secretion and product-coupled growth;
- 1D PET film enzyme diffusion and local hydrolysis;
- Stage 12 wrapper examples for the current canonical examples.

Current limitations:

- Examples still use the existing solver/rate-law architecture, not the new
  process-centered assembly system.
- Output folders are useful but not yet standardized to the roadmap's complete
  `outputs/run_name/` structure.

Core files:

- `examples/`

### Notebooks

Status: `not started`.

Required by roadmap:

- `notebooks/00_quickstart.ipynb`
- `notebooks/01_process_library_demo.ipynb`
- `notebooks/02_surface_hydrolysis_demo.ipynb`
- `notebooks/03_fungus_on_pet_demo.ipynb`
- `notebooks/04_reaction_diffusion_demo.ipynb`
- `notebooks/05_calibration_and_uncertainty_demo.ipynb`

Important rule:

- Notebooks must import package code and demonstrate workflows. They must not
  contain core model implementation.

### Data and Configuration

Status: `not started` for the long-term roadmap.

Required top-level folders:

- `data/fungi/`
- `data/substrates/`
- `data/enzymes/`
- `data/environments/`
- `data/geometries/`
- `data/parameters/`
- `data/experiments/`

Current note:

- The package has `src/fungal_model/data/README.md`, but the roadmap's
  top-level human-editable data/config system and schema validation are not yet
  implemented.

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

Status: `partial`.

Existing related work:

- Arrhenius and pH modifier logic exists.

Still required:

- `Environment` entity;
- modifiers that read from environment objects;
- water activity, oxygen, and product inhibition modifiers in the roadmap
  architecture;
- modifier plots in result outputs.

### Milestone 6: Geometry abstraction

Status: `partial`.

Existing related work:

- 1D finite-volume grid and boundary conditions exist.

Still required:

- roadmap `Geometry` hierarchy;
- well-mixed, film, particle, slab, and porous-medium objects;
- common model interface for well-mixed and spatial examples.

### Milestone 7: Fungus/enzyme/process compatibility

Status: `not started` for the new registry layer.

Existing related work:

- fungus metadata and enzyme profile classes exist.

Still required:

- explicit enzyme entities;
- compatibility matching between fungus, enzyme, substrate bond, environment,
  geometry, and process;
- clear assembly failures for missing biological capability.

### Milestone 8: Notebooks

Status: `not started`.

Still required:

- create `/notebooks`;
- add required notebooks;
- add smoke/execution tests where practical.

### Milestone 9: Data/config schemas

Status: `not started`.

Still required:

- YAML/JSON loaders;
- schema validation;
- example configs with provenance;
- unknown-value handling in config files.

### Milestone 10: First full integration workflow

Status: `not started`.

Still required:

- one fungus/enzyme/PET/environment/geometry workflow assembled through the
  registry and model builder;
- full output folder;
- validation and plots;
- honest failure when PET parameters or processes are missing.

## Anti-Cheating Checklist Status

Implemented in current tests:

- missing process fails with `MissingProcessError`;
- missing parameter fails with `MissingParameterError`;
- missing provenance fails in scientific assembly mode;
- incompatible units fail with `IncompatibleUnitsError`;
- generic process modules do not import PET-specific modules;
- non-assimilable product cannot cause biomass growth;
- zero enzyme, zero accessible surface, zero substrate, and zero PET mass checks
  exist for current PET rate-law tests;
- high diffusion approaches well-mixed behavior in existing spatial tests.

Still required:

- generic surface hydrolysis works with PET and a dummy non-PET substrate;
- PET plugin uses generic processes;
- incompatible fungus/substrate/enzyme pairing fails in model assembly;
- oxygen cannot be consumed if oxygen process is absent or unavailable;
- roadmap result object saves standardized files and plots;
- notebooks import from `fungal_model` and do not define core rate laws/classes.

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

- 2026-05-26: full test suite passed with 123 tests after Milestones 2-4.
