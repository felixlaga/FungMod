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
- a minimal first-order `A -> B` benchmark example,
- a homogeneous Michaelis-Menten toy-substrate benchmark example.

It does not yet implement PET hydrolysis kinetics, surface-limited polymer reaction rates, fungal growth, enzyme secretion, spatial transport, calibration, or uncertainty propagation. Those stages are documented in `progress.md` and should be added only after the earlier layer has tests and validation.

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
```

Each example saves a plot, simulation record, validation report, and assumptions file under `outputs/`.

## Current Limitations

- Only well-mixed ODE systems are supported.
- Michaelis-Menten kinetics currently means homogeneous dissolved-substrate kinetics only.
- PET is currently a substrate metadata object only. It defaults to a heterogeneous surface-degradation modelling preference, but Stage 4 kinetics are not implemented yet.
- PET must not be treated with the homogeneous Michaelis-Menten layer except as an explicitly labelled artificial benchmark.
- The reaction engine assumes each reaction rate can be converted into every affected species unit per simulation time unit.
- Mass-balance validation requires the caller to provide conserved weights when species do not share directly compatible units.
- Solver tolerances are numerical settings, not physical parameters, and are recorded in the simulation record.
