# FungMod Progress

This file is the handoff ledger for the modelling framework. Update it at the
end of each completed task or stage so a new agent can continue without
guessing what was done, tested, or intentionally deferred.

Status key:

- `complete`: implemented and tested for the intended stage scope.
- `partial`: some infrastructure exists, but the stage is not scientifically complete.
- `not started`: no functional model layer implemented.
- `blocked`: progress needs a dependency, decision, or data source.

## Current Deliverable

Goal: implement Stage 2 basic enzyme kinetics on top of the validated Stage 0/1 foundation.

Current status: `complete` for Stage 2 basic enzyme kinetics.

Implemented:

- `pyproject.toml` with package metadata and dependencies.
- `src/fungal_model` package skeleton.
- Stage 0 governance objects:
  - `Parameter`
  - `ParameterSet`
  - `Assumption`
  - `SimulationRecord`
  - shared `pint` unit registry and unit helpers.
- Stage 1 reaction ODE infrastructure:
  - generic `Reaction`
  - `SimulationEngine`
  - `SolverSettings`
  - unit-aware state conversion and rate-law checks.
- Validators:
  - non-negativity
  - mass balance
  - limiting-case framework.
- Minimal benchmark example:
  - `examples/01_first_order_reaction.py`
  - closed first-order `A -> B` system.
- Stage 2 homogeneous enzyme kinetics:
  - `michaelis_menten_rate`
  - `enzyme_explicit_michaelis_menten_rate`
  - `MichaelisMentenRateLaw`
  - `EnzymeExplicitMichaelisMentenRateLaw`
  - explicit homogeneous dissolved-substrate assumption.
- Stage 2 benchmark example:
  - `examples/02_homogeneous_michaelis_menten.py`
  - dissolved toy substrate `S -> P`.
- Tests:
  - parameter provenance and unknown values
  - unit compatibility
  - reaction engine execution
  - reaction provenance enforcement
  - mass balance
  - non-negativity
  - limiting-case suite
  - simulation record serialization.
  - Michaelis-Menten low-substrate, high-substrate, zero-substrate, zero-enzyme, unit, and ODE-engine behavior.

Validation status:

- Verified on 2026-05-25 with `.venv/bin/python -m pytest`.
- Result: 24 tests passed.
- Verified examples:
  - `.venv/bin/python examples/01_first_order_reaction.py`
  - `.venv/bin/python examples/02_homogeneous_michaelis_menten.py`
- Example artifacts were written to:
  - `outputs/example_01_first_order/`
  - `outputs/example_02_homogeneous_michaelis_menten/`

## Stage Roadmap

### Stage 0: Scientific Governance Layer

Status: `complete`

Plan:

- Enforce parameter provenance.
- Represent unknown values explicitly.
- Separate assumptions from parameters.
- Save reproducible simulation records.
- Require explicit testing escape hatch for unsourced parameters.

Implemented:

- `src/fungal_model/core/parameters.py`
- `src/fungal_model/core/assumptions.py`
- `src/fungal_model/core/simulation.py`
- `src/fungal_model/core/logging.py`
- `src/fungal_model/core/provenance.py`
- `src/fungal_model/core/units.py`

Remaining:

- Add richer provenance schema later if literature metadata needs structured DOI/authors/year fields.

### Stage 1: General ODE Reaction Engine

Status: `complete`

Plan:

- Implement deterministic `dx/dt = F(x, t, theta)` engine.
- Support unit-aware species, reactions, rate laws, and SciPy solvers.
- Validate non-negativity, mass balance, and limiting cases.
- Provide one minimal mass-conserving example.

Implemented:

- `src/fungal_model/chemistry/reactions.py`
- `SimulationEngine` in `src/fungal_model/core/simulation.py`
- validators in `src/fungal_model/core/validators.py`
- validation re-export modules under `src/fungal_model/validation`
- `examples/01_first_order_reaction.py`

Remaining:

- Add Stage 2 kinetics only after preserving these tests.

### Stage 2: Basic Enzyme Kinetics

Status: `complete`

Plan:

- Add homogeneous Michaelis-Menten kinetics.
- Add enzyme-explicit `kcat * E * S / (Km + S)` form.
- Clearly label homogeneous PET use as a benchmark only.
- Add low-substrate, high-substrate, zero-enzyme, zero-substrate, and units tests.

Implemented:

- `src/fungal_model/kinetics/michaelis_menten.py`
- Homogeneous dissolved-substrate assumption helper.
- Direct quantity functions for classic and enzyme-explicit forms.
- Callable rate-law objects for use with `Reaction`.
- `tests/test_michaelis_menten.py`
- `examples/02_homogeneous_michaelis_menten.py`

Remaining:

- Do not expand this homogeneous layer into PET realism. Stage 3 should introduce PET as a substrate object, and Stage 4 should add heterogeneous surface-limited PET hydrolysis.

### Stage 3: PET Substrate Module

Status: `not started`

Plan:

- Implement PET substrate properties.
- Represent crystallinity, amorphous fraction, geometry, surface area, roughness, and degradation products.
- Default PET to heterogeneous surface treatment, not dissolved-substrate kinetics.

### Stage 4: Surface-Limited PET Hydrolysis

Status: `not started`

Plan:

- Implement enzyme adsorption/desorption and surface coverage.
- Add modular surface hydrolysis rate laws.
- Validate zero surface area, zero enzyme, zero PET mass, surface-area monotonicity, and crystallinity effect.

### Stage 5: Temperature And pH Dependence

Status: `not started`

Plan:

- Add Arrhenius scaling with required activation energy and provenance.
- Add optional pH activity profile with measured-range warnings.
- Mark missing high-temperature enzyme deactivation as a limitation until implemented.

### Stage 6: Fungal Enzyme Secretion And Biomass

Status: `not started`

Plan:

- Introduce fungus object after enzyme-only PET model works.
- Track active/dormant/dead biomass, secreted enzyme, substrate, products, and optional oxygen.
- Enforce enzyme production cost and no growth without assimilable carbon/energy.

### Stage 7: Thermodynamic And Stoichiometric Consistency

Status: `not started`

Plan:

- Track stoichiometry, carbon balance, oxygen demand, approximate Gibbs energy where available, and biomass-yield constraints.
- Reject impossible growth when carbon, energy, oxygen, or yield constraints are violated.

### Stage 8: Spatial Reaction-Diffusion Model

Status: `not started`

Plan:

- Start with 1D finite differences, then 2D.
- Track substrate, enzyme, biomass, oxygen, and products as fields.
- Keep boundary conditions explicit.

### Stage 9: Universal Substrate Engine

Status: `not started`

Plan:

- Generalize substrate representation.
- Add PET, cellulose, lignin, starch, and chitin subclasses with explicit completeness levels.
- Do not imply equal maturity across substrates.

### Stage 10: Calibration And Validation Against Data

Status: `not started`

Plan:

- Add least-squares fitting, residual plots, parameter bounds, train/validation split, and confidence intervals where possible.
- Later add Bayesian calibration and posterior predictive checks.

### Stage 11: Uncertainty And Sensitivity

Status: `not started`

Plan:

- Add Monte Carlo sampling, local sensitivity, and later global sensitivity.
- Report uncertainty bands and sensitivity rankings.

### Stage 12: Examples

Status: `partial`

Plan:

- Example 1: homogeneous Michaelis-Menten toy substrate.
- Example 2: surface-limited PET hydrolysis.
- Example 3: PET hydrolysis with Arrhenius temperature dependence.
- Example 4: fungal enzyme secretion without growth from products.
- Example 5: fungal growth only from assimilable products.
- Example 6: 1D spatial PET film with enzyme diffusion.

Implemented:

- A preliminary Stage 1 first-order `A -> B` benchmark. This is not one of the final Stage 12 biological examples; it is a foundation check.
- Stage 2 dissolved homogeneous Michaelis-Menten toy benchmark. This is not PET and is explicitly labelled as a dissolved-substrate benchmark.

## Handoff Notes

- Do not implement PET or fungal biology until Stage 0 and Stage 1 tests pass.
- Do not add numerical values for biological or polymer parameters without provenance.
- If a value is needed but unknown, create a `Parameter` with `value=None`, source text explaining that the value is missing, and `confidence_level="unknown"`.
- Use `allow_unsourced_for_testing=True` only in tests or explicitly artificial benchmarks.
- Keep later-stage placeholder modules honest: they should not expose fake model behaviour.
