# FungMod

FungMod is a scientific Python codebase for building a physically grounded fungal-substrate degradation model. The long-term target is a modular API that can simulate a fungus, substrate, environment, geometry, and parameter set without hiding assumptions or provenance.

This repository currently implements only the foundation:

- unit-aware parameters and parameter sets,
- explicit assumptions and simulation records,
- a generic deterministic ODE reaction engine,
- non-negativity, mass-balance, and limiting-case validation helpers,
- a minimal first-order `A -> B` benchmark example.

It does not yet implement PET, fungal growth, enzyme secretion, spatial transport, calibration, or uncertainty propagation. Those stages are documented in `progress.md` and should be added only after the earlier layer has tests and validation.

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

## Run The First Example

```bash
python examples/01_first_order_reaction.py
```

The example saves a plot, simulation record, validation report, and assumptions file under `outputs/example_01_first_order/`.

## Current Limitations

- Only well-mixed ODE systems are supported.
- The reaction engine assumes each reaction rate can be converted into every affected species unit per simulation time unit.
- Mass-balance validation requires the caller to provide conserved weights when species do not share directly compatible units.
- Solver tolerances are numerical settings, not physical parameters, and are recorded in the simulation record.

