# FungMod

Before implementing any new feature, read:
foundation_progress/00_START_HERE_FOUNDATION_FIRST.md
foundation_progress/01_CODEX_NO_SHORTCUT_CONTRACT.md
foundation_progress/02_GUARDRAILS_AND_TESTS_SPEC.md
foundation_progress/11_MILESTONE_SEQUENCE_FOUNDATION_ONLY.md

Do not implement real biology yet. First complete the foundation milestones: remove hardcoding, implement native model execution, implement generic configured workflows, add guardrails, and make the package architecture Atmodeller-grade.


FungMod is a scientific Python codebase for building a physically grounded fungal-substrate degradation model. The long-term target is a modular API that can simulate a fungus, substrate, environment, geometry, and parameter set without hiding assumptions or provenance.

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
- a first config-driven PET surface integration workflow that assembles
  fungus/enzyme/substrate/environment/geometry metadata through the process
  registry and saves a full standardized output bundle,
- a minimal first-order `A -> B` benchmark example,
- a homogeneous Michaelis-Menten toy-substrate benchmark example.
- a PET surface-hydrolysis benchmark example.
- a PET temperature/pH modifier benchmark example.
- a fungal enzyme secretion and product-coupled growth benchmark example.
- a 1D PET film enzyme-diffusion benchmark example.

It does not yet implement full thermodynamic flux analysis, resolved intracellular metabolism, 2D/3D spatial models, calibration, or uncertainty propagation. Those stages are documented in `progress.md` and should be added only after the earlier layer has tests and validation.

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

## Run The Examples

```bash
python examples/01_first_order_reaction.py
python examples/02_homogeneous_michaelis_menten.py
python examples/03_pet_surface_hydrolysis.py
python examples/04_pet_temperature_ph.py
python examples/05_fungal_enzyme_secretion_and_growth.py
python examples/06_spatial_pet_film_enzyme_diffusion.py
python examples/stage12_01_homogeneous_michaelis_menten.py
python examples/stage12_02_pet_surface_model.py
python examples/stage12_03_pet_with_temperature.py
python examples/stage12_04_fungal_enzyme_secretion.py
python examples/stage12_05_fungal_growth_from_assimilable_products.py
python examples/stage12_06_spatial_pet_film.py
```

Each example saves a plot, simulation record, validation report, and assumptions file under `outputs/`.

## Notebooks

The `notebooks/` folder contains the first roadmap notebook set:

- `00_quickstart.ipynb`
- `01_process_library_demo.ipynb`
- `02_surface_hydrolysis_demo.ipynb`
- `03_fungus_on_pet_demo.ipynb`
- `04_reaction_diffusion_demo.ipynb`
- `05_calibration_and_uncertainty_demo.ipynb`

Notebook tests check that notebooks import `fungal_model`, avoid defining core
rate laws/classes inline, and execute the quickstart smoke path.

## Data And Configs

Top-level YAML configs live under `data/model_configs/`, `data/fungi/`,
`data/substrates/`, `data/enzymes/`, `data/environments/`, `data/geometries/`,
`data/parameters/`, and `data/experiments/`. Loaders are exposed from
`fungal_model` as `load_fungus`, `load_substrate`, `load_enzyme`,
`load_environment`, `load_geometry`, and `load_parameter_set`.

Foundation model-config shells are available for:

- `data/model_configs/toy_homogeneous_ab.yml`
- `data/model_configs/toy_surface_pet_plugin.yml`
- `data/model_configs/toy_surface_dummy_non_pet.yml`

All three load through `load_model_config`. They are framework benchmarks, not
scientific biology.

Product maps live under `data/product_maps/` and are loaded through
`load_product_map`. They carry configured state names and benchmark maturity
metadata, so product release mappings do not have to be embedded in process
code or a substrate-specific workflow.

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
from fungal_model import ConfiguredModelExecutionError, load_model_config, run_configured_model

config = load_model_config("path/to/model_config.yml")
try:
    run_configured_model("path/to/model_config.yml")
except ConfiguredModelExecutionError as exc:
    report = exc.report.to_dict()
```

At the current foundation stage, `load_model_config` validates the generic
top-level config contract. `run_configured_model` remains a structural preflight
boundary while config-driven assembly and output-bundle wiring are completed.
Native execution itself is available through `AssembledModel.run()`.

The older PET surface integration remains available from
`fungal_model.workflows` as a deprecated compatibility workflow for existing
tests and examples.

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
- The generic configured workflow still does not assemble, run, validate, and
  save a complete output bundle from model configs end to end.
- The standardized `results.SimulationResult` is now native output for
  `AssembledModel.run()` and still wraps older adapter workflows.
- Generic surface catalysis now exists, and PET composes it through a PET
  accessibility adapter, but resolved PET product chemistry and dynamic
  morphology remain future work.
- Geometry abstractions currently wrap well-mixed and 1D film cases; particle,
  slab, and porous-medium geometries are honest metadata placeholders.
- Enzyme/fungus compatibility matching checks declared capabilities, but it
  does not yet auto-build full living-fungus ODE systems from entities.
- The config-driven PET integration workflow is a deprecated compatibility
  slice; the generic configured workflow is the main foundation path.
- PET must not be treated with the homogeneous Michaelis-Menten layer except as an explicitly labelled artificial benchmark.
- The reaction engine assumes each reaction rate can be converted into every affected species unit per simulation time unit.
- Mass-balance validation requires the caller to provide conserved weights when species do not share directly compatible units.
- Solver tolerances are numerical settings, not physical parameters, and are recorded in the simulation record.
