# FungMod Phase 2 - Thermodynamic and Balance Enforcement Design

Status: implementation plan only.

Date: 2026-06-15

Related findings:

- `P1-AUDIT-THERMO-001`: full thermodynamic feasibility is not enforced by the solver.
- `P1-AUDIT-BALANCE-001`: elemental, charge, and redox balance enforcement is incomplete.

This plan does not implement production enforcement, add scientific values, or
change numerical behavior. It defines the staged implementation path needed to
turn the confirmed Phase 1 thermodynamic and balance blockers into explicit,
provenance-backed, testable FungMod capabilities.

## 1. Current Repository State

Phase 1 is complete. The native configured execution path is:

`run_configured_model` -> `ConfiguredModelRunner.run` ->
`ConfiguredProcessAssembler.assemble` -> `AssembledModel.run` ->
`ProcessODESolver.run`.

Current thermodynamic and balance behavior is intentionally limited:

- `src/fungal_model/chemistry/thermodynamics.py` stores a sourced
  `GibbsFreeEnergyEstimate` and can report whether a known stored value is
  negative.
- `src/fungal_model/chemistry/stoichiometry.py` parses simple elemental
  formulas, stores reaction metadata, checks elemental residuals, stores carbon
  fractions, and stores oxygen-demand metadata.
- `src/fungal_model/core/validators.py` provides boolean `ValidationResult`
  objects for non-negativity, weighted mass balance, carbon conservation,
  oxygen limitation, and biomass-yield limits.
- `ValidatorRegistry.default()` can load only `non_negative` and
  `mass_balance` from model configs.
- `SimulationResult` stores validation results and writes
  `validation_report.json`; it can already serialize mapping-like validation
  payloads, which gives a backward-compatible path for richer future reports.
- `ConfiguredOutputWriter` summarizes validators using the existing `passed`
  boolean, so unknown/inconclusive checks need explicit migration rules.

Current code does not:

- calculate reaction quotients;
- calculate dynamic reaction Gibbs energy over a trajectory;
- enforce thermodynamic feasibility during rate evaluation or ODE solving;
- distinguish standard, condition-specific, and dynamic Gibbs energy in the
  type system;
- validate charge balance;
- validate electron or redox balance;
- automatically attach balance validators for every process;
- prove that product maps are chemically balanced unless a caller supplies the
  necessary metadata and validator.

## 2. Design Principles

1. No invented chemistry. FungMod must never fabricate delta G values, redox
   potentials, formulas, charges, activities, activity coefficients, molar
   masses, electron counts, or biological data.
2. Metadata is not enforcement. A stored negative Gibbs value is evidence about
   a stated estimate under stated conditions; it is not dynamic thermodynamic
   validation.
3. Unknown is first-class. Missing formulas, charges, electron bookkeeping,
   activities, or provenance must produce `inconclusive`, `unknown`, or
   `unsupported` outcomes, not silent pass/fail guesses.
4. Enforcement is staged. Phase 2 should first support explicit metadata and
   residual reporting, then condition-specific Gibbs metadata, and only later
   reaction quotients and activity-aware dynamic Gibbs checks.
5. Balance checks are generic. No PET-, cellulose-, enzyme-, fungus-, or
   mechanism-specific branches may be added to core chemistry, validators,
   assembly, or solver modules.
6. Scientific mode must be stricter than exploratory mode. Exploratory runs may
   emit limitations and suggested experiments for unknown checks; scientific
   runs must not call a case thermodynamically or chemically validated when
   required metadata is absent.
7. Backward compatibility should be preserved unless a migration is explicitly
   justified and tested.

## 3. Gibbs Energy Semantics

FungMod needs three separate concepts. They must not share one ambiguous field.

### 3.1 Standard Gibbs Energy

Standard reaction Gibbs energy is a reference-state quantity for a reaction,
usually written as standard delta G or transformed standard delta G. In FungMod
terms, it must include:

- reaction identifier and stoichiometric participants;
- whether the value is untransformed standard, transformed biochemical
  standard, or another named convention;
- reference temperature;
- reference pressure when relevant;
- pH convention when transformed;
- ionic strength and magnesium or buffer conventions when relevant;
- units compatible with energy per amount, normally `joule / mole`;
- source, measurement/estimation method, uncertainty when available, and
  limitations.

Standard Gibbs energy does not depend on the simulated state concentrations at
time `t`. A negative stored standard value can support a metadata statement
like "exergonic under the stated reference convention", but it cannot prove
trajectory-level thermodynamic feasibility.

### 3.2 Condition-Specific Gibbs Energy

Condition-specific Gibbs energy is a stored or derived estimate under a named,
fixed set of conditions, such as assay temperature, pH, ionic strength, buffer,
or assumed activities. It may fold in transformations relative to a standard
reference.

It must include:

- all fields required for standard Gibbs energy when it is derived from a
  standard reference;
- the actual condition vector used;
- whether concentrations or activities were fixed, assumed, measured, or not
  used;
- provenance for every condition and assumption;
- a statement of whether it is comparable to the model environment.

Condition-specific Gibbs energy can support an assembly-time or preflight
metadata check only when the stored conditions are compatible with the modeled
environment. It still does not validate the changing trajectory unless a
reaction quotient is computed from dynamic state activities.

### 3.3 Dynamic Reaction Gibbs Energy

Dynamic reaction Gibbs energy is a time-dependent quantity computed from the
current simulated state:

`reaction_delta_g(t) = reference_delta_g + R * T(t) * ln(Q(t))`

where `Q(t)` is the reaction quotient built from species activities and
stoichiometric coefficients.

Dynamic thermodynamic validation requires all of the following:

- a chemically meaningful stoichiometric reaction;
- compatible state-to-species mapping;
- reference Gibbs metadata with provenance;
- temperature at each checked time point;
- activity model for every participating species;
- unit conversion from model states into activity or concentration;
- explicit treatment of solids, solvents, catalysts, enzymes, and omitted
  species;
- numerical tolerances for near-equilibrium behavior;
- a directionality policy that relates process flux sign to
  `reaction_delta_g(t)`.

FungMod cannot honestly perform this check with current data except for
future cases that explicitly provide all required metadata. It must never treat
`GibbsFreeEnergyEstimate.is_exergonic()` as dynamic validation.

## 4. What FungMod Can Honestly Enforce With Current Data

Current data and code support only a narrow set of honest checks:

- provenance/unit validation for stored `GibbsFreeEnergyEstimate` values;
- simple elemental balance checks for reactions whose species all have
  explicit `ElementalComposition` metadata;
- weighted mass-balance checks when the caller supplies conserved weights;
- carbon conservation checks when the caller supplies `CarbonContent` entries;
- oxygen-demand checks when the caller supplies `OxygenDemand` and available
  oxygen information;
- biomass-yield limit checks when the caller supplies both yield and maximum
  yield parameters.

Current data and code do not support honest global enforcement of:

- charge balance for arbitrary product maps;
- electron or redox balance;
- dynamic thermodynamic feasibility;
- thermodynamic flux analysis;
- activity-corrected reaction quotients;
- validated redox-coupled oxygen metabolism;
- automatic balance validation for all registry cases.

Therefore Phase 2 must begin by making missing metadata visible and
machine-readable, not by blocking existing exploratory runs based on absent
chemical data.

## 5. Balance Semantics

### 5.1 Species Identity

Balance checks must operate on chemical species metadata, not only on state
variable names. A state variable such as `released_product_amount` may be a
lumped proxy, mass-equivalent bucket, or unresolved product class. It is not
automatically a chemical species.

Future metadata must distinguish:

- model state name;
- chemical species or lumped pool identifier;
- compartment or phase when relevant;
- amount basis, such as mole, kilogram, activity, concentration, or arbitrary
  equivalent;
- whether the state is a catalyst/enzyme that should appear in the reaction
  equation or a modifier that should not be consumed;
- whether the state is a proxy that cannot participate in chemical balance.

### 5.2 Elemental Balance

Elemental balance means the sum of each element on the product side equals the
sum on the reactant side after applying stoichiometric coefficients.

Required metadata:

- stoichiometric coefficients;
- elemental composition for every non-exempt participant;
- provenance for each formula or structured element-count record;
- explicit exemption policy for catalysts, solvents, omitted species, or
  lumped pools.

Residual:

- assembly-time residual: `sum_products(nu_i * element_count_i) -
  sum_reactants(nu_i * element_count_i)`, in atom equivalents per reaction
  event;
- post-simulation residual: conserved element total over time, in amount of
  element or equivalent units, only when state quantities can be converted to a
  common amount basis.

If any participant lacks composition, the result is inconclusive, not passed.

### 5.3 Charge Balance

Charge balance means net charge on products equals net charge on reactants
after applying stoichiometric coefficients.

Required metadata:

- net charge for every non-exempt participant;
- charge convention and protonation state;
- pH or biochemical transformation convention when charge depends on pH;
- provenance for charge assignments.

Residual:

- assembly-time residual in elementary-charge equivalents per reaction event;
- post-simulation residual in charge-equivalent amount units only when state
  quantities have a mole basis or an explicit equivalent conversion.

Missing charge or ambiguous protonation yields inconclusive. FungMod must not
infer charges from names or formulas.

### 5.4 Electron And Redox Balance

Electron/redox balance means electrons are neither created nor destroyed across
the declared redox reaction, after accounting for explicit electron donors,
electron acceptors, half-reaction electrons, or oxidation-state changes.

Required metadata must use one of these explicit approaches:

- explicit half-reaction electron counts;
- per-species oxidation-state/electron-equivalent metadata sufficient to
  compute electron transfer;
- explicit redox-couple records with donor, acceptor, electron count, and
  provenance.

Oxygen demand is not redox balance. An `OxygenDemand` validator can say whether
tracked substrate consumption exceeds available oxygen under a supplied demand
coefficient. It cannot prove electron balance, redox potential feasibility, or
respiratory coupling.

Missing electron metadata yields inconclusive. Incorrect electron residuals
yield failed. Unimplemented redox-coupled metabolism yields unsupported when a
user requests that enforcement.

## 6. Outcome Model

The existing `ValidationResult` has `passed: bool`. Phase 2 should extend the
validation payload without breaking existing code.

Recommended future fields:

- `name`: stable validator name;
- `status`: one of `passed`, `failed`, `inconclusive`, `not_applicable`,
  `unsupported`, or `skipped`;
- `passed`: backward-compatible boolean;
- `severity`: one of `info`, `warning`, `error`, or `blocker`;
- `message`: short human-readable explanation;
- `details`: machine-readable residuals, tolerances, units, provenance, and
  missing metadata;
- `required`: whether this check is required for the current mode;
- `mode_policy`: mode-specific handling that was applied.

Backward-compatible `passed` semantics:

- `passed`: `True`;
- `not_applicable`: `True` only when the non-applicability is explicit and
  provenance-backed;
- `failed`: `False`;
- `inconclusive`: `False` when the check is required, otherwise `True` only for
  legacy summary compatibility if paired with `status = inconclusive` and
  `severity = warning`;
- `unsupported`: `False` when requested;
- `skipped`: `True` only when the user did not request the check and the mode
  does not require it.

The output summary must not collapse `inconclusive` into "validated". New
summary code should report counts by `status` and `severity`.

## 7. Residuals, Tolerances, Units, And Provenance

### 7.1 Residual Fields

Every balance or thermodynamic check should report:

- `residual_name`;
- `residual_value`;
- `residual_units`;
- `absolute_tolerance`;
- `absolute_tolerance_units`;
- `relative_tolerance`;
- `scale_value`;
- `scale_units`;
- `max_abs_residual`;
- `max_relative_residual`;
- `time_of_max_residual` for trajectory checks;
- `status`;
- `severity`;
- `missing_metadata`;
- `provenance_refs`.

### 7.2 Tolerances

Use explicit numerical tolerances, not hidden constants:

- assembly-time stoichiometric residual default may start from
  `DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE`, but future validators should
  allow per-check overrides;
- post-simulation conserved-total residuals may start from
  `DEFAULT_VALIDATION_RELATIVE_TOLERANCE`;
- dynamic Gibbs near-equilibrium tolerance must be explicit and unit-bearing,
  for example `joule / mole`;
- activity lower bounds used to avoid `log(0)` must be explicit numerical
  solver conventions and reported as such, not chemical facts.

Any default tolerance must be documented as a numerical convention and included
in validation outputs.

### 7.3 Units

Balance units must be explicit:

- formula stoichiometry residuals: element atom equivalents per reaction event;
- charge residuals: elementary-charge equivalents per reaction event;
- electron residuals: electron equivalents per reaction event;
- trajectory element totals: mole element, kilogram element equivalent, or a
  declared equivalent unit;
- Gibbs energies: `joule / mole` or compatible units;
- reaction quotients: dimensionless.

If state quantities cannot be converted to a common basis, the check is
inconclusive. FungMod must not convert mass to moles without an explicit molar
mass or species-equivalent conversion.

### 7.4 Provenance Requirements

Every enforcing check must record provenance for:

- formulas or structured element counts;
- charges and protonation conventions;
- electron counts, oxidation states, redox couples, or half reactions;
- standard or condition-specific Gibbs estimates;
- condition vectors used for thermodynamic estimates;
- activity models and activity coefficients;
- molar masses or conversion factors;
- external flux or open-system declarations;
- tolerance choices when not using defaults.

Scientific mode must reject required enforcing checks that rely on
`source = None`, toy sources, or exploratory priors. Exploratory mode may run
with explicit exploratory assumptions and must surface them in limitations and
suggested-experiment outputs.

## 8. Mode Behavior

FungMod currently uses model config modes `toy`, `exploratory`, `scientific`,
and `strict`, while `VirtualExperiment` exposes `exploratory` and
`scientific`.

### 8.1 Toy Mode

Toy mode may use unsourced test fixtures only when explicitly allowed by the
existing testing pathways. Balance and thermodynamic validators may run as
software tests, but outputs must remain labelled toy/framework benchmark.

### 8.2 Exploratory Mode

Exploratory mode may simulate when thermodynamic or balance metadata is
incomplete, provided the missing data are explicit in validation outputs,
limitations, missing-parameter tables, or suggested-experiment tables.

Exploratory mode should:

- fail on definite contradictions that are checked and marked `severity =
  error` only if the user requested enforcement;
- otherwise record `failed` or `inconclusive` checks without suppressing output;
- never label an inconclusive case as thermodynamically validated.

### 8.3 Scientific Mode

Scientific mode means exact, non-exploratory current registry records and
implemented mechanisms. It does not mean empirically validated.

For thermodynamic and balance enforcement, scientific mode should eventually:

- require all applicable assembly-time elemental and charge checks to pass;
- require redox checks to pass when the mechanism declares redox chemistry;
- require thermodynamic metadata checks when a process declares
  thermodynamic-direction constraints;
- reject unknown or exploratory required metadata;
- reject stored negative Gibbs metadata as sufficient proof of dynamic
  thermodynamic feasibility unless dynamic activity-aware checks are
  implemented and pass.

Until these gates are implemented, scientific outputs must continue to state
that thermodynamic feasibility is not fully enforced.

### 8.4 Strict Configured Mode

Strict configured mode currently raises when validators fail. Future strict
behavior should raise when a configured validator returns:

- `failed` with `severity` `error` or `blocker`;
- `inconclusive` when `required = true`;
- `unsupported` when requested.

Optional warning-level inconclusive checks may be recorded without raising if
the config marks them optional.

## 9. Assembly-Time Versus Post-Simulation Checks

### 9.1 Assembly-Time Checks

Assembly-time checks run before ODE integration. They should be used for
metadata and structural feasibility:

- process/product-map participants are declared;
- state roles map to chemical species or declared lumped proxies;
- stoichiometric coefficients are finite and positive on each side;
- formulas are present and sourced for elemental enforcement;
- charges are present and sourced for charge enforcement;
- electron/redox metadata are present and sourced for redox enforcement;
- standard or condition-specific Gibbs metadata are present when a process
  declares a thermodynamic constraint;
- modeled environment is compatible with condition-specific thermodynamic
  metadata;
- required validators are registered and configured for the selected mode.

Assembly-time checks should write to the assembly report and configured failure
details when they block a run.

### 9.2 Post-Simulation Checks

Post-simulation checks run on `SimulationResult` trajectories:

- non-negative states;
- conserved weighted totals;
- conserved element totals when state-to-species conversions are known;
- conserved charge totals when charge equivalents are known;
- conserved electron totals or donor/acceptor budgets when redox metadata are
  known;
- dynamic reaction Gibbs energy and flux direction when activities are known;
- solver drift residuals and time of maximum residual.

Post-simulation checks should be saved in `validation_report.json` and future
structured residual tables. They should not modify state trajectories after the
fact.

### 9.3 Solver-Time Enforcement

Solver-time enforcement, such as clipping fluxes near equilibrium or rejecting
forward flux when dynamic delta G is positive, is a later milestone. It should
not be introduced until dynamic Gibbs checks can be computed and reported
without changing rates.

The first implementation should be observe-and-report, then block-at-mode-gate,
then optionally constrain flux in a separately reviewed milestone.

## 10. Required Schemas And Data Model

### 10.1 Chemistry Metadata

Add explicit metadata types before enforcement:

- `ChemicalSpeciesMetadata`
  - `species_id`
  - `name`
  - `formula` or structured `element_counts`
  - `net_charge`
  - `charge_convention`
  - `molar_mass`
  - `phase`
  - `is_lumped_pool`
  - `is_catalyst`
  - `provenance`
  - `limitations`
- `ReactionParticipantMetadata`
  - `species_id`
  - `state_name`
  - `coefficient`
  - `side`
  - `role`
  - `include_in_balance`
  - `exemption_reason`
- `ReactionBalanceMetadata`
  - `reaction_id`
  - `participants`
  - `balance_requirements`
  - `external_fluxes`
  - `open_system_terms`
  - `provenance`
- `RedoxMetadata`
  - explicit half-reaction electrons or oxidation-state/electron-equivalent
    records
  - donor/acceptor roles
  - provenance
- `ThermodynamicReference`
  - `reaction_id`
  - `reference_type`: `standard`, `transformed_standard`, or
    `condition_specific`
  - `delta_g`
  - `conditions`
  - `source`
  - `uncertainty`
  - `limitations`
- `ActivityModel`
  - `species_id`
  - `state_name`
  - `activity_type`
  - `standard_state`
  - `activity_coefficient`
  - `conversion_parameter_refs`
  - `provenance`

### 10.2 Registry Records

Extend registry data only through versioned schema changes:

- add optional species metadata records or a species metadata section;
- add optional reaction metadata records separate from process compatibility;
- allow `ProcessCompatibilityRecord` or case templates to reference reaction
  metadata IDs;
- add mode policy flags for which checks are required;
- keep existing parameter records unchanged unless a migration explicitly
  moves thermodynamic values into a new record type.

Do not overload `ParameterRecord` with reaction thermodynamics unless the value
is truly a parameter used by a process. Thermodynamic references are metadata
and should have their own provenance semantics.

### 10.3 Model Config Schema

Add optional config sections in a backward-compatible way:

- `chemistry_metadata`
- `reaction_metadata`
- `balance_checks`
- `thermodynamic_checks`
- validator settings:
  - `validator_type: elemental_balance`
  - `validator_type: charge_balance`
  - `validator_type: redox_balance`
  - `validator_type: thermodynamic_metadata`
  - `validator_type: dynamic_thermodynamic_feasibility`

Existing configs with only `non_negative` and `mass_balance` must keep loading
and running.

### 10.4 Process Metadata

Extend `Process` metadata without changing process rate laws:

- optional reaction metadata reference;
- optional state-to-species mapping;
- optional thermodynamic policy:
  - `none`
  - `metadata_only`
  - `post_simulation_check`
  - `solver_enforced` in a later milestone only;
- optional balance requirements:
  - element
  - charge
  - redox.

This should not change `Process.rate()` or `Process.contributions()` in the
first enforcement milestone.

## 11. Required APIs

Introduce APIs in small layers:

1. Pure chemistry functions:
   - `element_balance_residual(metadata)`
   - `charge_balance_residual(metadata)`
   - `electron_balance_residual(metadata)`
   - `validate_reaction_balance(metadata, requirements, tolerances)`
2. Metadata validation:
   - `validate_thermodynamic_reference(reference)`
   - `compare_reference_conditions(reference, environment)`
3. Result validators:
   - `validate_element_conservation(result, metadata, tolerances)`
   - `validate_charge_conservation(result, metadata, tolerances)`
   - `validate_redox_budget(result, metadata, tolerances)`
   - `validate_dynamic_reaction_gibbs(result, metadata, activity_models,
     tolerances)`
4. Registry/config loaders:
   - loader functions for new metadata records;
   - `ValidatorRegistry` entries for the new validator types.
5. Output helpers:
   - richer validation summaries by status/severity;
   - optional residual CSV writers.

All APIs must accept explicit metadata. None should infer chemical facts from
state names.

## 12. Required Outputs

Configured and virtual-experiment outputs should eventually include:

- `validation_report.json` with status/severity-rich entries;
- `balance_checks.csv` for assembly and trajectory balance residuals;
- `thermodynamic_checks.csv` for Gibbs metadata and dynamic checks;
- `balance_residuals_long.csv` for time-indexed residuals when applicable;
- `thermodynamic_timeseries.csv` for dynamic delta G and reaction quotient
  values when applicable;
- assembly report sections for missing or incompatible chemistry metadata;
- standard-table limitations for missing formulas, charges, redox metadata,
  activity models, or thermodynamic references;
- suggested-experiment rows for required missing values.

Existing files should remain present. New files should be additive unless a
versioned output-schema migration explicitly states otherwise.

## 13. Migration Rules

1. Existing `GibbsFreeEnergyEstimate` remains a metadata type during migration.
   It may later become a compatibility wrapper around `ThermodynamicReference`.
2. Existing `ValidationResult` remains valid. New validators may return
   mappings or an extended dataclass that serializes to the same core fields
   plus `status`, `severity`, and residual fields.
3. Existing model configs keep loading. New chemistry sections are optional
   until a later scientific-mode gate requires them.
4. Existing mass-balance validators keep their current meaning. They must not
   be renamed to elemental balance because they are conserved-weight checks,
   not chemical formula checks.
5. Existing product maps remain product maps. Chemical stoichiometry claims
   require explicit species metadata and provenance.
6. Existing exploratory BIO-001 and BIO-002 outputs must remain labelled
   exploratory and must not become thermodynamically validated just because a
   metadata field exists.
7. Scientific-mode changes require targeted tests that show unknown or
   exploratory thermodynamic/balance metadata blocks only the cases that claim
   those checks are required.

## 14. Test Requirements

### 14.1 Unit Tests

Add tests for:

- formula metadata provenance requirements;
- unsupported formula syntax and structured element counts;
- element residual pass/fail/inconclusive cases;
- charge residual pass/fail/inconclusive cases;
- electron/redox residual pass/fail/inconclusive cases;
- Gibbs reference type validation;
- condition mismatch reporting;
- dynamic Gibbs refusing to run without activities;
- dynamic Gibbs residual calculation for an artificial fully specified toy
  reaction.

### 14.2 Registry And Config Tests

Add tests for:

- loading chemistry metadata records;
- loading reaction metadata records;
- config sections remaining optional;
- new validator types registered through `ValidatorRegistry`;
- unknown validator types still failing structurally;
- scientific mode rejecting required unknown metadata;
- exploratory mode recording unknown metadata without hiding it.

### 14.3 Assembly Tests

Add tests for:

- assembly report includes missing formula/charge/redox metadata;
- assembly blocks scientific required checks with missing metadata;
- assembly does not block existing toy/exploratory configs when no new checks
  are requested;
- process metadata references arbitrary reaction IDs without hardcoded
  substrate or enzyme names.

### 14.4 Result And Output Tests

Add tests for:

- status/severity-rich validation serialization;
- validation summaries count passed, failed, inconclusive, unsupported, and
  skipped separately;
- strict mode raises on failed required checks;
- strict mode raises on inconclusive required checks;
- configured output bundles include residual tables when checks run;
- virtual-experiment output schemas document new residual tables.

### 14.5 Guardrail Tests

Add tests that fail if:

- a negative stored Gibbs value is treated as dynamic thermodynamic validation;
- core modules infer formula, charge, electron count, or activity from species
  names;
- generic balance code contains substrate-, enzyme-, fungus-, or
  mechanism-specific branches;
- unknown chemistry metadata silently passes a required scientific check.

## 15. Milestones

### P2.1 - Design And Catalogue Pointer

Create this design document and point `findings.yaml` and `progress.md` to it.
Do not resolve the blocker.

### P2.2 - Status-Rich Validation Contract

Extend validation result semantics to support `status`, `severity`,
`required`, and residual fields while preserving existing boolean `passed`
callers.

Exit criteria:

- existing validators still pass current tests;
- result and configured-output summaries report status counts;
- strict mode behavior is tested for failed and inconclusive required checks.

### P2.3 - Explicit Reaction And Species Metadata

Add schema-backed species, participant, and reaction metadata with provenance.
Do not add real biological values unless they are sourced and scoped.

Exit criteria:

- artificial test reactions can pass/fail/inconclusive elemental and charge
  balance checks;
- existing configs remain compatible;
- no core hardcoding is introduced.

### P2.4 - Assembly-Time Balance Checks

Wire optional reaction metadata into process and model assembly.

Exit criteria:

- assembly reports missing/incompatible metadata;
- scientific required checks block when metadata is absent or inconsistent;
- exploratory runs record limitations instead of silently passing.

### P2.5 - Post-Simulation Balance Validators

Add trajectory-level element, charge, and redox budget validators for fully
specified toy cases and explicit configured cases.

Exit criteria:

- residual time series are written;
- units and tolerances are reported;
- open-system declarations are handled as explicit `not_applicable` or
  externally balanced cases.

### P2.6 - Thermodynamic Reference Metadata

Separate standard, transformed standard, and condition-specific Gibbs
references.

Exit criteria:

- stored Gibbs metadata validates reference conventions and provenance;
- condition/environment mismatch produces inconclusive or failed metadata
  checks according to policy;
- negative stored Gibbs is reported only as metadata, not dynamic validation.

### P2.7 - Dynamic Gibbs Observation

Implement dynamic reaction Gibbs calculation only for fully specified artificial
or curated cases with explicit activity models.

Exit criteria:

- reaction quotient is dimensionless and provenance-backed;
- dynamic delta G time series is reported;
- flux-direction checks are observe-and-report, not solver-constraining.

### P2.8 - Scientific Mode Gate

Require applicable thermodynamic and balance checks for scientific claims where
the mechanism declares them.

Exit criteria:

- exact scientific cases with required missing metadata are rejected;
- exploratory cases remain runnable with explicit limitations;
- virtual-experiment outputs include missing metadata and suggested experiment
  rows.

### P2.9 - Solver-Time Thermodynamic Constraints

Only after P2.7 and P2.8, evaluate whether any solver-time flux constraints are
appropriate.

Exit criteria:

- separate design review;
- numerical behavior changes are intentionally versioned;
- tests compare unconstrained and constrained behavior;
- documentation explains the physical assumptions and limitations.

## 16. Open Decisions

- Whether to represent formulas primarily as strings, structured element-count
  mappings, or both.
- Whether charge and protonation metadata live on species records, reaction
  records, or condition-specific species forms.
- How to represent lumped product pools that cannot be chemically balanced.
- How to map mass-valued solid states to mole-based reaction quotients without
  inventing molar mass or accessible-site conversions.
- Whether open-system external fluxes should be declared in model config,
  reaction metadata, process metadata, or all three.
- How strict configured mode should treat warning-level inconclusive optional
  checks in legacy summary booleans.
- Whether thermodynamic reference records should be stored in the registry or
  loaded as data files first.

## 17. Non-Goals For This Task

This task does not:

- add production validators;
- add redox potentials;
- add delta G values;
- add activity models;
- add formulas or charges for real registry species;
- change solver rates;
- change configured-model behavior;
- change virtual-experiment behavior;
- mark `P1-AUDIT-THERMO-001` or `P1-AUDIT-BALANCE-001` resolved.
