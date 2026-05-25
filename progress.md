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

Goal: implement Stage 4 surface-limited PET hydrolysis on top of the validated Stage 0-3 foundation.

Current status: `complete` for Stage 4 surface-limited PET hydrolysis.

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
- Stage 3 substrate metadata:
  - generic `Substrate` and `DegradationProduct` interfaces.
  - `PETSubstrate` with required PET identity, geometry type, degradation products, and provenance-backed material parameters.
  - explicit default preference for heterogeneous surface modelling.
  - explicit unknown defaults for density, crystallinity, amorphous fraction, surface area, geometry size, roughness, and accessible surface area.
  - derived accessible-area helper for metadata bookkeeping only.
- Stage 4 surface-limited PET hydrolysis:
  - Langmuir equilibrium surface coverage.
  - PET surface hydrolysis rate proportional to occupied accessible surface.
  - PET-specific `Reaction` rate-law object.
  - explicit assumptions and limitations.
- Stage 4 benchmark example:
  - `examples/03_pet_surface_hydrolysis.py`
  - fixed-enzyme PET surface hydrolysis to lumped mass-equivalent hydrolysate.
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
  - PET identity, default model preference, unknown parameters, degradation products, unit checks, fraction validation, roughness validation, and accessible-area derivation.
  - PET surface model zero surface area, zero enzyme, zero PET mass, surface-area monotonicity, crystallinity effect, explicit accessible-area override, Langmuir unit checks, and ODE integration.

Validation status:

- Verified on 2026-05-25 with `.venv/bin/python -m pytest`.
- Result: 43 tests passed.
- Verified examples:
  - `.venv/bin/python examples/01_first_order_reaction.py`
  - `.venv/bin/python examples/02_homogeneous_michaelis_menten.py`
  - `.venv/bin/python examples/03_pet_surface_hydrolysis.py`
- Example artifacts were written to:
  - `outputs/example_01_first_order/`
  - `outputs/example_02_homogeneous_michaelis_menten/`
  - `outputs/example_03_pet_surface_hydrolysis/`

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

Status: `complete`

Plan:

- Implement PET substrate properties.
- Represent crystallinity, amorphous fraction, geometry, surface area, roughness, and degradation products.
- Default PET to heterogeneous surface treatment, not dissolved-substrate kinetics.

Implemented:

- `src/fungal_model/substrates/base.py`
- `src/fungal_model/substrates/pet.py`
- `PETSubstrate` records:
  - polymer type
  - repeating unit
  - dominant cleavable bond type
  - density
  - crystallinity
  - amorphous fraction
  - surface area
  - geometry type
  - thickness
  - particle size
  - roughness factor
  - accessible surface area
  - degradation products
  - limitations and references.
- PET defaults:
  - `physical_state="solid_polymer"`
  - `default_degradation_model="heterogeneous_surface"`
  - `is_dissolved_by_default=False`
  - numeric material parameters default to explicit unknown `Parameter` objects.
- `tests/test_pet_substrate.py`

Remaining:

- Stage 4 must implement actual surface-limited PET hydrolysis. Stage 3 only supplies metadata and derived accessible-area bookkeeping.

### Stage 4: Surface-Limited PET Hydrolysis

Status: `complete`

Plan:

- Implement enzyme adsorption/desorption and surface coverage.
- Add modular surface hydrolysis rate laws.
- Validate zero surface area, zero enzyme, zero PET mass, surface-area monotonicity, and crystallinity effect.

Implemented:

- `src/fungal_model/kinetics/langmuir.py`
- `src/fungal_model/kinetics/surface_kinetics.py`
- `langmuir_surface_coverage`
- `surface_hydrolysis_rate`
- `PETSurfaceHydrolysisRateLaw`
- `pet_surface_hydrolysis_assumption`
- `tests/test_surface_pet.py`
- `examples/03_pet_surface_hydrolysis.py`

Model equations:

- `theta = K_ads * E / (1 + K_ads * E)`
- `rate = k_surface * theta * A_accessible`

Important limitations:

- `K_ads` is an equilibrium lumped adsorption parameter, not separate dynamic adsorption/desorption states.
- Accessible surface area is constant during a run.
- PET morphology, crystallinity evolution, erosion, diffusion, enzyme depletion by binding, deactivation, and product inhibition are not yet modelled.
- Product release is currently a mass-equivalent lump in examples; chemically resolved MHET/BHET/TPA/EG product partitioning is not implemented.

Remaining:

- Stage 5 should add temperature and pH dependence with strict provenance and validity-range warnings.

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
