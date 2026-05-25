# FungMod

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
```

Each example saves a plot, simulation record, validation report, and assumptions file under `outputs/`.

## Current Limitations

- Only well-mixed ODE systems are supported.
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
- PET must not be treated with the homogeneous Michaelis-Menten layer except as an explicitly labelled artificial benchmark.
- The reaction engine assumes each reaction rate can be converted into every affected species unit per simulation time unit.
- Mass-balance validation requires the caller to provide conserved weights when species do not share directly compatible units.
- Solver tolerances are numerical settings, not physical parameters, and are recorded in the simulation record.
