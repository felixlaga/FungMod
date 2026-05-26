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

Goal: complete Stages 10, 11, and 12 on top of the validated Stage 0-9 foundation.

Current status: `complete` for Stages 10, 11, and 12.

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
- Stage 5 environmental modifiers:
  - Arrhenius absolute prefactor form.
  - Arrhenius reference-rate scaling form.
  - universal gas constant as a sourced `Parameter`.
  - validity-range warnings for temperature extrapolation.
  - Gaussian pH activity profile.
  - validity-range warnings for pH extrapolation.
  - environmental modifier composition with `PETSurfaceHydrolysisRateLaw`.
- Stage 5 benchmark example:
  - `examples/04_pet_temperature_ph.py`
  - fixed-enzyme PET surface hydrolysis with Arrhenius temperature scaling and Gaussian pH activity.
- Stage 6 fungal layer:
  - `Fungus` metadata object.
  - `EnzymeProfile` and `EnzymeCapability`.
  - complete fungal `ParameterSet` helper with unknown defaults.
  - enzyme secretion rate `dE/dt = alpha_E * B_active`.
  - enzyme production active-biomass cost.
  - first-order extracellular enzyme decay.
  - first-order active biomass maintenance loss.
  - product assimilation evidence gate.
  - product uptake and biomass yield helper.
- Stage 6 benchmark example:
  - `examples/05_fungal_enzyme_secretion_and_growth.py`
  - active biomass secretes enzyme, pays secretion/maintenance costs, hydrolyses PET, and grows only from explicitly assimilable lumped hydrolysate.
- Stage 7 stoichiometric and thermodynamic layer:
  - elemental formula parsing and reaction stoichiometry metadata.
  - carbon content metadata for state species.
  - oxygen demand metadata for aerobic processes.
  - Gibbs free energy estimate metadata with provenance and optional known-value checks.
  - carbon conservation validator.
  - oxygen limitation validator.
  - biomass yield limit validator.
  - Stage 7 validators added to the Stage 6 fungal benchmark validation report.
- Stage 8 spatial layer:
  - explicit 1D finite-volume uniform grid.
  - explicit no-flux, fixed-value, and periodic boundary conditions.
  - finite-volume 1D diffusion operator.
  - spatial reaction-diffusion method-of-lines engine.
  - spatial simulation record.
  - spatial validators for gradient smoothing, no-flux integral conservation, and well-mixed average comparison.
- Stage 8 benchmark example:
  - `examples/06_spatial_pet_film_enzyme_diffusion.py`
  - 1D PET film with fixed enzyme boundary, enzyme diffusion, and local PET surface hydrolysis.
- Stage 9 universal substrate engine:
  - generic substrate physical-parameter specification helper.
  - universal substrate fields for water-activity dependence and thermodynamic metadata.
  - explicit placeholder substrate classes for cellulose, lignin, starch, and chitin.
  - PET remains the only `partial` substrate and keeps its heterogeneous surface-model default.
  - cellulose, lignin, starch, and chitin expose identity, bond classes, broad enzyme-class requirements, product classes, unknown physical parameters, assumptions, limitations, and references.
  - placeholder substrates use `default_degradation_model="unknown"` and do not imply kinetics or assimilation.
- Stage 10 calibration layer:
  - unit-aware residual computation and plotting.
  - deterministic train/validation split helper.
  - bounded least-squares calibration wrapper.
  - explicit fittable parameter bounds as provenance-backed `Parameter` objects.
  - fit result serialization with training residuals, validation residuals, covariance diagnostics, approximate confidence intervals where identifiable, optimizer metadata, and warnings for reused validation data or raw-unit residual scaling.
  - failed model/optimizer runs are reported as `success=False` results.
- Stage 11 uncertainty and sensitivity layer:
  - Monte Carlo uncertainty propagation for normal, uniform, and lognormal parameter uncertainty specifications.
  - reproducible sampling when a seed is supplied and explicit warnings when no seed is supplied.
  - summary quantiles for uncertainty bands.
  - local finite-difference sensitivity analysis with dimensional derivatives, normalized sensitivities, rankings, and saved reports.
- Stage 12 canonical examples:
  - `examples/stage12_01_homogeneous_michaelis_menten.py`
  - `examples/stage12_02_pet_surface_model.py`
  - `examples/stage12_03_pet_with_temperature.py`
  - `examples/stage12_04_fungal_enzyme_secretion.py`
  - `examples/stage12_05_fungal_growth_from_assimilable_products.py`
  - `examples/stage12_06_spatial_pet_film.py`
  - `examples/stage12_common.py`
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
  - Arrhenius reference-rate identity at reference temperature, temperature monotonicity within range, out-of-range warnings, prefactor units, pH optimum activity, pH out-of-range warnings, positive pH width, ODE integration with environmental modifiers, missing activation energy handling, and pH profile source enforcement.
  - fungal metadata unknown-parameter handling, fungal parameter unit checks, no biomass/no enzyme production, enzyme production biomass cost, enzyme decay, maintenance-driven active biomass decline, no product/no growth, non-assimilable product/no growth, and assimilable product/growth.
  - elemental formula parsing, balanced/unbalanced stoichiometry detection, Gibbs provenance, Gibbs exergonic metadata, unknown carbon fraction handling, carbon conservation pass/fail cases, oxygen sufficiency/deficit checks, and biomass yield limit pass/fail cases.
  - finite-volume no-flux conservation, missing boundary rejection, diffusion smoothing, zero-diffusion local ODE behavior, high-diffusion/well-mixed average agreement, and fixed-value boundary behaviour.
  - universal substrate completeness levels, placeholder unknown-parameter handling, product-assimilation non-claims, bond/enzyme metadata, PET maturity preservation, serialization fields, unit-checked parameter overrides, and lignin ordered-fraction caveat.
  - least-squares fit recovery, validation-data reuse warnings, unit rejection for residuals and bounds, failed-fit reporting, and calibration-source enforcement.
  - Monte Carlo reproducibility, uncertainty-band widening with wider input uncertainty, uncertainty provenance enforcement, uncertainty unit checks, local sensitivity ranking, and zero-base relative sensitivity rejection.

Validation status:

- Verified on 2026-05-25 with `.venv/bin/python -m pytest`.
- Result: 100 tests passed.
- Verified examples:
  - `.venv/bin/python examples/01_first_order_reaction.py`
  - `.venv/bin/python examples/02_homogeneous_michaelis_menten.py`
  - `.venv/bin/python examples/03_pet_surface_hydrolysis.py`
  - `.venv/bin/python examples/04_pet_temperature_ph.py`
  - `.venv/bin/python examples/05_fungal_enzyme_secretion_and_growth.py`
  - `.venv/bin/python examples/06_spatial_pet_film_enzyme_diffusion.py`
  - `.venv/bin/python examples/stage12_01_homogeneous_michaelis_menten.py`
  - `.venv/bin/python examples/stage12_02_pet_surface_model.py`
  - `.venv/bin/python examples/stage12_03_pet_with_temperature.py`
  - `.venv/bin/python examples/stage12_04_fungal_enzyme_secretion.py`
  - `.venv/bin/python examples/stage12_05_fungal_growth_from_assimilable_products.py`
  - `.venv/bin/python examples/stage12_06_spatial_pet_film.py`
- Example artifacts were written to:
  - `outputs/example_01_first_order/`
  - `outputs/example_02_homogeneous_michaelis_menten/`
  - `outputs/example_03_pet_surface_hydrolysis/`
  - `outputs/example_04_pet_temperature_ph/`
  - `outputs/example_05_fungal_enzyme_secretion_and_growth/`
  - `outputs/example_06_spatial_pet_film_enzyme_diffusion/`
  - `outputs/stage12_01_homogeneous_michaelis_menten/`
  - `outputs/stage12_02_pet_surface_model/`
  - `outputs/stage12_03_pet_with_temperature/`
  - `outputs/stage12_04_fungal_enzyme_secretion/`
  - `outputs/stage12_05_fungal_growth_from_assimilable_products/`
  - `outputs/stage12_06_spatial_pet_film/`
  - Stage 7 validation results are included in the Stage 6 fungal benchmark validation report.

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

Status: `complete`

Plan:

- Add Arrhenius scaling with required activation energy and provenance.
- Add optional pH activity profile with measured-range warnings.
- Mark missing high-temperature enzyme deactivation as a limitation until implemented.

Implemented:

- `src/fungal_model/kinetics/arrhenius.py`
- `src/fungal_model/kinetics/ph.py`
- `EnvironmentalValidityWarning`
- `arrhenius_rate_constant`
- `arrhenius_reference_scaled_rate`
- `ArrheniusReferenceTemperatureScaler`
- `gaussian_ph_activity`
- `GaussianPHActivityProfile`
- optional temperature and pH scaling inside `PETSurfaceHydrolysisRateLaw`
- `tests/test_environmental_modifiers.py`
- `examples/04_pet_temperature_ph.py`

Model equations:

- `k(T) = A * exp(-Ea / (R*T))`
- `k(T) = k_ref * exp((-Ea/R) * (1/T - 1/T_ref))`
- `activity_pH = exp(-0.5 * ((pH - pH_opt) / sigma_pH)^2)`

Important limitations:

- Arrhenius scaling does not include enzyme thermal deactivation.
- The model warns outside measured temperature ranges but still returns a value so failed extrapolation is visible to callers.
- Gaussian pH activity is empirical and does not model ionization chemistry.
- pH out-of-range evaluations warn but are not automatically rejected.

Remaining:

- Stage 6 should introduce fungal enzyme secretion and biomass only after preserving the enzyme-only PET model tests.

### Stage 6: Fungal Enzyme Secretion And Biomass

Status: `complete`

Plan:

- Introduce fungus object after enzyme-only PET model works.
- Track active/dormant/dead biomass, secreted enzyme, substrate, products, and optional oxygen.
- Enforce enzyme production cost and no growth without assimilable carbon/energy.

Implemented:

- `src/fungal_model/fungi/base.py`
- `src/fungal_model/fungi/enzyme_profile.py`
- `src/fungal_model/fungi/growth.py`
- `src/fungal_model/fungi/metabolism.py`
- `Fungus`
- `EnzymeProfile`
- `EnzymeCapability`
- `EnzymeSecretionRateLaw`
- `EnzymeProductionCostRateLaw`
- `EnzymeDecayRateLaw`
- `BiomassMaintenanceRateLaw`
- `ProductAssimilation`
- `ProductUptakeRateLaw`
- `biomass_yield_coefficient`
- `tests/test_fungal_dynamics.py`
- `examples/05_fungal_enzyme_secretion_and_growth.py`

Model equations:

- `dE/dt = alpha_E * B_active - delta_E * E`
- active biomass cost from enzyme secretion is proportional to `alpha_E * B_active`
- active biomass maintenance loss is `m_B * B_active`
- product uptake is `q_product * product * B_active`, gated by explicit assimilability evidence
- biomass production from uptake uses a configured yield `Y_B`

Important limitations:

- Dormant biomass is tracked as a state but no dormancy transition model is implemented yet.
- Oxygen is described in fungal metadata but not modelled as a state or limiter.
- Product assimilation is a binary evidence gate; transporters, intracellular pathways, toxicity, repression, and thermodynamics are not modelled yet.
- Biomass yield is constrained to 0-1 but full carbon/energy balance is deferred to Stage 7.
- Enzyme secretion cost is a lumped parameter that must be sourced before scientific use.

Remaining:

- Stage 7 should add thermodynamic and stoichiometric consistency, including carbon balance, oxygen demand, and physical yield constraints.

### Stage 7: Thermodynamic And Stoichiometric Consistency

Status: `complete`

Plan:

- Track stoichiometry, carbon balance, oxygen demand, approximate Gibbs energy where available, and biomass-yield constraints.
- Reject impossible growth when carbon, energy, oxygen, or yield constraints are violated.

Implemented:

- `src/fungal_model/chemistry/stoichiometry.py`
- `src/fungal_model/chemistry/thermodynamics.py`
- `src/fungal_model/validation/stoichiometry.py`
- `ElementalComposition`
- `StoichiometricTerm`
- `StoichiometricReactionMetadata`
- `CarbonContent`
- `OxygenDemand`
- `GibbsFreeEnergyEstimate`
- `validate_carbon_conservation`
- `validate_oxygen_limitation`
- `validate_biomass_yield_limit`
- `tests/test_stoichiometry_thermodynamics.py`
- Stage 7 validators included in `examples/05_fungal_enzyme_secretion_and_growth.py`

Current enforcement:

- Carbon in tracked species cannot exceed initial tracked carbon plus explicit external carbon.
- Aerobic substrate consumption can be checked against configured oxygen availability or an initial oxygen state.
- Biomass yield can be checked against a configured maximum yield.
- Stoichiometric reaction metadata can report elemental balance when formulas are supplied.
- Gibbs free energy estimates can be recorded with units, provenance, conditions, and exergonic metadata.

Important limitations:

- Full thermodynamic flux analysis is not implemented.
- Gibbs free energy estimates are metadata and are not yet solver constraints.
- Oxygen is still not coupled as a dynamic limiter in the ODE equations.
- Carbon validation depends on supplied carbon fractions and tracked state species.
- Energy source checks are not complete; Stage 7 provides the interface for Gibbs estimates but does not reject all energetically impossible growth yet.

Remaining:

- Stage 8 should add spatial reaction-diffusion only after preserving the ODE, PET, fungal, and stoichiometric validation tests.

### Stage 8: Spatial Reaction-Diffusion Model

Status: `complete`

Plan:

- Start with 1D finite differences, then 2D.
- Track substrate, enzyme, biomass, oxygen, and products as fields.
- Keep boundary conditions explicit.

Implemented:

- `src/fungal_model/transport/geometry.py`
- `src/fungal_model/transport/diffusion.py`
- `src/fungal_model/transport/reaction_diffusion.py`
- `src/fungal_model/validation/spatial.py`
- `BoundaryCondition`
- `BoundaryConditions1D`
- `UniformGrid1D`
- `finite_volume_laplacian_1d`
- `ReactionDiffusionEngine1D`
- `ReactionDiffusionResult1D`
- `ReactionDiffusionRecord`
- `validate_diffusion_smooths_gradient`
- `validate_no_flux_spatial_integral_conserved`
- `validate_spatial_average_close_to_expected`
- `tests/test_reaction_diffusion.py`
- `examples/06_spatial_pet_film_enzyme_diffusion.py`

Current checks:

- Diffusion smooths gradients in a diffusion-only run.
- No-flux boundaries conserve the discrete spatial integral for diffusion.
- Zero diffusion reproduces independent local ODE behavior.
- Spatial average agrees with a well-mixed linear reaction benchmark.
- Boundary conditions are explicit and missing boundaries are rejected.

Important limitations:

- Only 1D uniform finite-volume grids are implemented.
- 2D and 3D are not implemented.
- Geometry does not yet include true cross-sectional area, volume, porosity, or film-surface coupling.
- The spatial PET example uses a per-cell accessible surface area benchmark.
- Oxygen and biomass fields can be represented but no spatial fungal ecology example is implemented yet.

Remaining:

- Stage 9 has generalized substrate representation across PET, cellulose, lignin, starch, and chitin with explicit completeness levels. Stages 10-12 now add calibration, uncertainty/sensitivity, and canonical examples. Future work should move beyond the planned scaffold into real data ingestion, literature curation, and model validation against experiments.

### Stage 9: Universal Substrate Engine

Status: `complete`

Plan:

- Generalize substrate representation.
- Add PET, cellulose, lignin, starch, and chitin subclasses with explicit completeness levels.
- Do not imply equal maturity across substrates.

Implemented:

- Extended `src/fungal_model/substrates/base.py` with:
  - `SubstrateParameterSpec`
  - unknown substrate-parameter construction helper
  - unit-checked substrate `ParameterSet` construction helper
  - universal `water_activity_dependence` field
  - universal `thermodynamic_data` field
  - substrate parameter accessor.
- Added placeholder substrate modules:
  - `src/fungal_model/substrates/cellulose.py`
  - `src/fungal_model/substrates/lignin.py`
  - `src/fungal_model/substrates/starch.py`
  - `src/fungal_model/substrates/chitin.py`
- Each placeholder substrate records:
  - chemical class and physical state
  - bond classes and accessible bond classes
  - broad required enzyme classes
  - degradation product classes
  - product assimilability as unknown
  - density, porosity, crystallinity or ordered-fraction metadata, surface area, accessible surface area, and water-activity threshold as explicitly unknown `Parameter` objects.
- Updated `src/fungal_model/substrates/__init__.py` exports.
- Added `tests/test_universal_substrates.py`.

Current scientific scope:

- PET remains `completeness="partial"` and defaults to heterogeneous surface modelling.
- Cellulose, lignin, starch, and chitin are `completeness="placeholder"` and use `default_degradation_model="unknown"`.
- No substrate-specific kinetics, product assimilation, thermodynamic feasibility, or accessibility models were added for the placeholder substrates.

Important limitations:

- Cellulose lacks degree-of-polymerization, fibril morphology, enzyme synergy, and lignocellulose matrix coupling.
- Lignin lacks bond-frequency distributions, redox mediator chemistry, oxygen/redox coupling, radical chemistry, and resolved product chemistry.
- Starch lacks gelatinization, granule morphology, amylose/amylopectin ratio, and adsorption/hydrolysis kinetics.
- Chitin lacks polymorph, acetylation/chitosan conversion, nitrogen assimilation, enzyme synergy, and adsorption/hydrolysis kinetics.

Validation:

- Verified on 2026-05-25 with `.venv/bin/python -m pytest`.
- Result: 88 tests passed.
- Re-ran examples 01-06 successfully after Stage 9 export changes.

### Stage 10: Calibration And Validation Against Data

Status: `complete`

Plan:

- Add least-squares fitting, residual plots, parameter bounds, train/validation split, and confidence intervals where possible.
- Later add Bayesian calibration and posterior predictive checks.

Implemented:

- `src/fungal_model/calibration/residuals.py`
  - `CalibrationResiduals`
  - `residuals_between`
  - `sequential_train_validation_split`
  - residual JSON export and residual plotting.
- `src/fungal_model/calibration/fitting.py`
  - `FittableParameter`
  - `fit_least_squares`
  - `LeastSquaresCalibrationResult`
  - provenance-backed optimizer diagnostic constants.
- `tests/test_calibration.py`

Current enforcement:

- Fitted parameters must already be known, sourced `Parameter` objects.
- Parameter bounds are themselves `Parameter` objects and must carry units and provenance.
- Calibration source is required.
- Train and validation residuals are both recorded.
- If validation indices are omitted, the result explicitly warns that validation reused training data.
- Failed model/optimizer calls return `success=False` calibration reports.
- Approximate covariance and 95 percent intervals are reported only when residual degrees of freedom and Jacobian rank allow it.

Important limitations:

- Only deterministic least-squares calibration is implemented.
- Bayesian calibration remains a placeholder.
- Confidence intervals are linearized approximations, not full posterior uncertainty.
- Identifiability diagnostics are rank-based and basic.
- The framework does not include real experimental datasets yet.

### Stage 11: Uncertainty And Sensitivity

Status: `complete`

Plan:

- Add Monte Carlo sampling, local sensitivity, and later global sensitivity.
- Report uncertainty bands and sensitivity rankings.

Implemented:

- `src/fungal_model/uncertainty/monte_carlo.py`
  - `ParameterUncertaintySpec`
  - `run_monte_carlo`
  - `MonteCarloResult`
  - normal, uniform, and lognormal parameter uncertainty propagation.
- `src/fungal_model/uncertainty/sensitivity.py`
  - `LocalSensitivitySpec`
  - `local_sensitivity`
  - `LocalSensitivityResult`
  - dimensional derivatives, normalized sensitivities, and rankings.
- `tests/test_uncertainty_sensitivity.py`

Current enforcement:

- Uncertainty specifications require a source.
- Distribution parameters are unit-checked against the nominal parameter.
- Monte Carlo runs record the random seed; if no seed is supplied, the result warns that exact reproducibility is absent.
- Failed samples are recorded rather than suppressed.
- Wider input uncertainty is preserved in wider output intervals in the tested benchmark.
- Local sensitivity rejects zero base parameter values for relative perturbations.

Important limitations:

- Global sensitivity analysis is not implemented.
- Monte Carlo sampling does not impose physical constraints beyond the distribution supplied by the caller.
- Correlated parameter uncertainty is not implemented.
- Uncertainty summaries are empirical quantiles, not Bayesian credible intervals unless the input samples are defined that way.

### Stage 12: Examples

Status: `complete`

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
- Canonical Stage 12 wrappers and outputs:
  - `examples/stage12_01_homogeneous_michaelis_menten.py`
  - `examples/stage12_02_pet_surface_model.py`
  - `examples/stage12_03_pet_with_temperature.py`
  - `examples/stage12_04_fungal_enzyme_secretion.py`
  - `examples/stage12_05_fungal_growth_from_assimilable_products.py`
  - `examples/stage12_06_spatial_pet_film.py`
- Stage 12 example 4 is a distinct no-growth secretion example:
  - active biomass secretes enzyme,
  - enzyme hydrolyses PET,
  - biomass pays secretion and maintenance costs,
  - no product assimilation reaction is present,
  - validation reports whether active biomass avoids positive growth.
- Each Stage 12 example writes a plot, simulation record, validation report, and assumptions file.

Validation:

- Verified on 2026-05-25 with `.venv/bin/python -m pytest`.
- Result: 100 tests passed.
- Verified all six canonical Stage 12 scripts run successfully.

## Handoff Notes

- Do not implement PET or fungal biology until Stage 0 and Stage 1 tests pass.
- Do not add numerical values for biological or polymer parameters without provenance.
- If a value is needed but unknown, create a `Parameter` with `value=None`, source text explaining that the value is missing, and `confidence_level="unknown"`.
- Use `allow_unsourced_for_testing=True` only in tests or explicitly artificial benchmarks.
- Keep later-stage placeholder modules honest: they should not expose fake model behaviour.
