# FungMod

Before changing the codebase, start with the active directive:

- `foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`
- `foundation_progress/FUNGMOD_NEXT_PHASES_ROADMAP.md`

Historical foundation-first plans are archived under `old_progress/`. They are
useful context, but the active goal is now the virtual-experiment engine:
simulate degradation dynamics over time without hiding assumptions,
uncertainty, provenance, missing inputs, or unsupported biology.

FungMod is a scientific Python codebase for building a physically grounded
fungal- and enzyme-mediated substrate-degradation virtual-experiment engine.
The long-term target is a modular API that can simulate a fungus or enzyme
source, substrate, environment, and parameter set without inventing biological
facts.

This repository currently implements the validated foundation plus the first
basic kinetics layer:

- unit-aware parameters and parameter sets,
- explicit assumptions and simulation records,
- a generic deterministic ODE reaction engine,
- non-negativity, mass-balance, and limiting-case validation helpers,
- homogeneous dissolved-substrate Michaelis-Menten rate laws,
- PET substrate metadata with explicit unknown physical parameters,
- a minimal heterogeneous PET surface-hydrolysis rate law,
- Arrhenius temperature scaling with validity-range warnings,
- Gaussian pH activity scaling with validity-range warnings,
- minimal fungal metadata, enzyme secretion, enzyme decay, maintenance, and product-coupled biomass growth,
- stoichiometric and thermodynamic metadata interfaces,
- carbon conservation, oxygen limitation, and biomass-yield validation checks,
- 1D finite-volume reaction-diffusion with explicit boundary conditions,
- universal substrate metadata interfaces with PET, cellulose, lignin, starch, and chitin substrate classes,
- least-squares calibration utilities with train/validation residual reporting,
- Monte Carlo uncertainty propagation and local sensitivity analysis,
- process-centered assembly scaffolding with structured missing-process,
  missing-parameter, and incompatible-unit reports,
- a standardized result/export object that writes reports, CSV tables, logs,
  and figures,
- generic homogeneous process classes for first-order, mass-action, and
  Michaelis-Menten benchmark models,
- generic surface adsorption/catalysis process components that can run with PET
  or a dummy non-PET substrate,
- explicit `Environment`, `Geometry`, and `Enzyme` entities for process-centered
  assembly,
- environment-driven temperature, pH, water-activity, oxygen, and product
  inhibition modifiers,
- compatibility checks for enzyme/substrate/bond/fungus pairings during model
  assembly,
- a top-level notebook set that imports package code rather than redefining
  core model logic,
- human-editable YAML config folders for fungi, substrates, enzymes,
  environments, geometries, parameters, and experiments,
- schema-checked config loaders with explicit unknown-value handling,
- an optional PET plugin convenience helper that delegates to the generic
  configured workflow with an explicit plugin registry,
- software-test benchmark configs that are explicitly non-scientific;
- a registry-backed exploratory virtual-experiment API for Reaction 618 and
  the controlled BIO-001 surface-degradation pilot;
- schema-versioned virtual-experiment output tables with provenance,
  limitations, missing-parameter, suggested-experiment, and range-use fields;
- an offline-first SABIO-RK source adapter that loads frozen kinetic-law
  snapshots and writes review-only proposed records without mutating the
  simulation registry.

It does not yet implement full thermodynamic flux analysis, resolved intracellular
metabolism, 2D/3D spatial models, publication-grade calibration against
curated biological datasets, or global uncertainty analysis. Those stages are
documented in `progress.md` and should be added only after the current virtual
experiment layer has tests, provenance, and validation.

## Scientific Philosophy

The model is designed to fail honestly. Physical quantities carry units. Parameters require provenance before a scientific simulation can run, unless a test explicitly sets `allow_unsourced_for_testing=True`. Missing values are represented as missing values rather than guessed numbers. Validation failures are returned as results, not hidden.

## Install

```bash
python3 -m pip install -e ".[dev]"
```

## Test

```bash
pytest
```

## Quality Gates

CI is required before merging. The CI workflow installs `.[dev]` and runs the
package-quality gates below:

```bash
python -m ruff check src tests
python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml
```

The current Pyright gate resolves imports from the active Python interpreter
and enables the main argument, assignment, return, operator, call, attribute,
and type-form diagnostics. Optional member access remains the active typing
ratchet documented in `ARCHITECTURE_DEBT.md`.
Coverage currently has an 80% minimum gate.

Branch protection expectations are documented in `.github/BRANCH_PROTECTION.md`.
The protected default branch should require pull requests, passing CI,
up-to-date branches, no force pushes, and no unaudited direct bypass.

## Run A Virtual Experiment

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_registry(
    fungi=["sabiork_beta_glucosidase_source"],
    substrates=["cellobiose"],
    environments=["sabiork_reaction_618_selected_conditions"],
)

result = study.simulate(mode="exploratory", n_samples=128)
```

The standard output folder includes long-format time series, final states,
final metrics, threshold times, sampled parameters, summary metrics,
provenance, limitations, missing-parameter and suggested-experiment tables, and
a versioned data dictionary/schema. Exploratory priors remain allowed, but the
tables mark them as assumptions rather than literature-curated values.

## Foundation Public API

The stable foundation API is intentionally generic-first. These names are
supported from top-level `fungal_model` for config loading, model assembly,
execution, and result inspection:

- `run_configured_model`
- `load_model_config`
- `load_substrate`
- `load_geometry`
- `load_product_map`
- `load_parameter_set`
- `ModelBuilder`
- `AssembledModel`
- `ProcessLibrary`
- `ProcessRegistry`
- `ProcessODESolver`
- `RunRequest`
- `SimulationResult`
- `Parameter`
- `ParameterSet`

PET-specific convenience helpers are not part of the top-level public API.
They live under `fungal_model.plugins.pet`, where plugin users can explicitly
import `pet_substrate_loader_registry`, `PETSurfaceWorkflowConfig`, and
`run_pet_surface_integration`.

## Notebooks

The `notebooks/examples/` folder contains software-test notebooks only. They
exercise configured workflow plumbing and use toy fixtures; they are not
researcher-facing scientific examples:

- `00_quickstart.ipynb`
- `01_config_entity_inspection.ipynb`
- `02_failure_report.ipynb`
- `03_configured_outputs.ipynb`

Notebook tests check that notebooks import `fungal_model`, avoid defining core
rate laws/classes or low-level solvers inline, and execute every foundation
notebook smoke path.

## Data And Configs

Top-level YAML configs live under `data/model_configs/`, `data/fungi/`,
`data/substrates/`, `data/enzymes/`, `data/environments/`, `data/geometries/`,
`data/parameters/`, and `data/experiments/`. Loaders are exposed from
`fungal_model` as `load_fungus`, `load_substrate`, `load_enzyme`,
`load_environment`, `load_geometry`, and `load_parameter_set`.

Toy and synthetic assets in `data/` are software-test or example fixtures, not
scientific records. They remain available for tests and configured-workflow
examples, but researcher-facing work should start from the registry-backed
virtual-experiment API and inspect table provenance before interpreting any
output.

Internal software-test model-config shells include:

- `data/model_configs/toy_homogeneous_ab.yml`
- `data/model_configs/toy_surface_pet_plugin.yml`
- `data/model_configs/toy_surface_dummy_non_pet.yml`

All three load through `load_model_config`. They are framework benchmarks, not
scientific biology.

Product maps live under `data/product_maps/` and are loaded through
`load_product_map`. They carry configured state names and benchmark maturity
metadata, so product release mappings do not have to be embedded in process
code or a substrate-specific workflow.

Source discovery is intentionally separate from simulation. `SabioRKSource`
loads frozen SABIO-RK kinetic-law snapshots by default and can refresh only
through an explicit live-fetch hook. Proposed product maps, parameter records,
and process-compatibility records are written for human review under a proposal
bundle; they are not silently committed into the simulation registry. Use
`scripts/fetch_sabiork_kinlaw_entries.py` to freeze raw SABIO-RK exports and
`scripts/propose_sabiork_source_records.py` to create review-only proposal
artifacts from a frozen snapshot.

Foundation process configs can be built through `ProcessLibrary.default_foundation()`.
The current library provides factories for first-order, mass-action,
homogeneous Michaelis-Menten, and generic surface-catalysis benchmark
processes. These are framework mechanisms, not organism- or substrate-specific
biology.

Assembled process models now support native well-mixed execution through
`AssembledModel.run()`. The method delegates to `ProcessODESolver`, returns a
standard `SimulationResult`, records process-rate trajectories, runs supplied
validators, and rejects unsupported geometry instead of silently switching
execution paths.

Substrate, geometry, product-map, and validator loading now goes through
registries. The default substrate registry is generic-first and supports
foundation benchmark substrates such as `generic_solid` and
`generic_dissolved`. PET substrate loading is available only through the
explicit PET plugin registry:

```python
from fungal_model import load_substrate
from fungal_model.plugins.pet import pet_substrate_loader_registry

substrate = load_substrate(
    "data/substrates/pet_film.yml",
    registry=pet_substrate_loader_registry(),
)
```

Configs are intentionally provenance-heavy. Top-level records and parameter
entries must include source, measurement method, confidence, notes, validity
range, units, and value fields. Unknown scientific values should be written as
`value: null`; loaders preserve them as explicit unknown parameters.

## Integration Workflow

The generic configured-model API is the public workflow entry point:

```python
from fungal_model import load_model_config, run_configured_model

config = load_model_config("path/to/model_config.yml")
result = run_configured_model("path/to/model_config.yml")
```

`run_configured_model` now loads entities through registries, merges configured
and entity parameter sets, builds processes through `ProcessLibrary`, assembles
a `ModelBuilder`, executes through `AssembledModel.run()`, validates the
`SimulationResult`, and saves the standard output bundle when an output
directory is configured.

Configured output folders include the core `SimulationResult` files plus
configuration-facing artifacts:

- `input_model_config.json`
- `configured_model_run.json`
- `configured_metadata.json`
- `process_build_decisions.json`
- `initial_state.json`
- `time_grid.json`
- `validators.json`
- `merged_parameters.json`
- `entity_snapshots/`
- `output_manifest.json`

Plugin-backed configured runs use explicit registry injection. The bundled PET
plugin config is an internal software-test fixture, not a scientific PET
degradation record.

The older PET convenience entry point now lives under
`fungal_model.plugins.pet` and delegates to `run_configured_model`; the generic
`fungal_model.workflows` package stays substrate-neutral.

## Current Limitations

- Well-mixed ODE systems and an initial 1D reaction-diffusion engine are supported.
- Michaelis-Menten kinetics currently means homogeneous dissolved-substrate kinetics only.
- PET surface hydrolysis currently uses a minimal equilibrium Langmuir coverage model with constant accessible surface area.
- PET product release is represented as a lumped mass-equivalent hydrolysate in the Stage 4 example, not resolved MHET/BHET/TPA/EG chemistry.
- Temperature scaling currently uses Arrhenius acceleration only; enzyme thermal deactivation is recorded as a limitation and is not implemented.
- pH activity currently uses an empirical Gaussian profile; mechanistic ionization chemistry is not implemented.
- Fungal growth currently uses a simple assimilable-product uptake law; oxygen, transporters, toxicity, regulation, and intracellular metabolism are not modelled.
- Enzyme production has an explicit active-biomass cost, but the cost parameter is lumped and must be sourced before scientific use.
- Stage 7 oxygen handling is currently a validation check against available oxygen, not a coupled oxygen state in the ODE model.
- Gibbs free energy values are metadata with provenance; full thermodynamic feasibility constraints are not yet enforced by the solver.
- Spatial modelling is currently 1D finite-volume method-of-lines only.
- Stage 8 diffusion fields are unit-aware, but geometry is a simple uniform 1D grid; 2D, variable geometry, and true volume/area coupling are not implemented.
- PET is the only substrate marked `partial`; cellulose, lignin, starch, and chitin are Stage 9 `placeholder` metadata classes with unknown physical parameters and no default degradation model.
- Universal substrate modules record bond classes, required enzyme classes, and product classes, but they do not implement substrate-specific kinetics, accessibility models, thermodynamic constraints, or assimilation evidence.
- Calibration utilities are generic least-squares tools; no literature data are bundled and no parameters are calibrated by default.
- Monte Carlo and local sensitivity utilities require explicit uncertainty/perturbation specifications; Bayesian calibration and global sensitivity are not implemented.
- `AssembledModel.run()` currently supports well-mixed process ODE execution;
  unsupported geometry fails before simulation.
- The generic configured workflow currently supports foundation process
  factories and well-mixed execution; unsupported process types and geometry
  fail before simulation.
- The standardized `results.SimulationResult` is now native output for
  `AssembledModel.run()` and still wraps older non-workflow adapters.
- Generic surface catalysis now exists, and PET composes it through a PET
  accessibility adapter, but resolved PET product chemistry and dynamic
  morphology remain future work.
- Geometry abstractions currently wrap well-mixed and 1D film cases; particle,
  slab, and porous-medium geometries are honest metadata placeholders.
- Enzyme/fungus compatibility matching checks declared capabilities, but it
  does not yet auto-build full living-fungus ODE systems from entities.
- The PET plugin convenience helper is a deprecated compatibility slice; the
  generic configured workflow is the main foundation path.
- PET must not be treated with the homogeneous Michaelis-Menten layer except as an explicitly labelled artificial benchmark.
- The reaction engine assumes each reaction rate can be converted into every affected species unit per simulation time unit.
- Mass-balance validation requires the caller to provide conserved weights when species do not share directly compatible units.
- Solver tolerances are numerical settings, not physical parameters, and are recorded in the simulation record.
