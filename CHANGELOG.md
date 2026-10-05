# Changelog

All notable public releases of FungMod are documented here.

## [Unreleased]

### Added

- Gelain 2020 cross-solver reproduction (`docs/gelain-cross-solver.md`): the
  registry hydrolysis candidate exported as a three-condition PEtab problem and
  reproduced in COPASI under a frozen plan. COPASI's time courses agree with
  the compiled core to 1.7e-8 of sigma at FungMod's optimum; COPASI then finds
  an objective 1.3 percent lower, which FungMod evaluates to the same value, so
  the recorded stage A optimum is an optimiser stopping point, reported as
  such (`copasi_improves`).
- `fungal_model.standards.copasi`: import a FungMod PEtab problem with
  COPASI's PEtab importer (in a fresh interpreter), rewrite the column weights
  from sigma to `1/sigma^2`, tighten the integrator, simulate, fit locally and
  from seeded random starts, and re-evaluate every optimum on the PEtab
  objective. New optional extra `copasi`.
- `conditions_to_petab`: multi-condition PEtab export from assembled models
  with condition columns for species and parameters that differ between
  conditions and explicit noise scales per observable.
- SBML export of `proportional_synthesis`, of parameter-bound stoichiometric
  coefficients (`CoefficientBinding` on product maps, written as separate
  reactions so the parameter stays live) and of assay-activity units (named
  dimensionless unit definitions, listed in the model notes);
  `to_sbml(names_as_ids=True)`.
- Gelain 2020 model-criticism study (`docs/gelain-model-criticism.md`): a
  frozen, digest-pinned plan comparing an induction state, a soluble product
  pool with Monod uptake and product inhibition, and conversion-dependent
  accessibility against the registry hydrolysis candidate;
  `fungal_model.research.gelain_criticism` composes the variants from the
  registry base configuration, runs whole-condition least-squares holdouts
  with the v2 screen (stage A) and posterior sampling with identifiability
  and coverage (stage B); `scripts/run_gelain_2020_model_criticism.py`.
  Results are not yet recorded.
- Generic `substrate_reactivity` rate modifier
  (`fungal_model.modifiers.reactivity`): rate times `(S / S_ref)^n` after the
  Kadam 2004 substrate reactivity factor, with a compiled kernel and config
  builder; tested on a non-cellulose toy process.
- `posterior_predictive_coverage` in `fungal_model.calibration.bayesian`: the
  fraction of fitted observations inside the central posterior predictive
  interval with measurement noise.
- Bayesian calibration and identifiability (`docs/bayesian-calibration.md`):
  `fungal_model.calibration.bayesian` samples the posterior of a configured
  or registry case with the Goodman-Weare affine-invariant ensemble move over
  explicit `log_uniform`/`uniform` priors and explicit `GaussianObservationError`
  models, optionally with noise-scale multipliers (one per observable or one
  shared by a declared group) labelled `estimated_from_residuals`; reports
  integrated autocorrelation times,
  effective sample sizes and a declared convergence rule; classifies every
  parameter with declared thresholds (`identified`, `weakly_identified`,
  `bounded_above_only`, `bounded_below_only`, `prior_dominated`); computes a
  finite-difference Fisher information at the best sample and posterior
  predictive bands; and pools within-time replicate scatter into a
  measured-evidence error model. `fungal_model.calibration.compiled_predictor`
  evaluates configured conditions on the compiled core by rebuilding the
  config per candidate, and `fungal_model.screening.registry_case_config_factory`
  (with `resolve_registry_case` and `build_resolved_case_config`) rebuilds a
  registry case with exact value overrides so that template-derived
  coefficients follow the fitted symbol.
- Recorded posterior-sampling study of the *T. harzianum* P49P11 cellulose
  registry case (`data/benchmarks/gelain_2020_bayesian/`,
  `scripts/run_gelain_2020_bayesian_calibration.py`,
  `fungal_model.research.gelain_bayesian`): nine constants, three loadings,
  v2 bounds as log-uniform priors, assumed error model with one sampled shared
  scale multiplier, checkpointed parallel run, thinned posterior samples and
  identifiability verdicts recorded in the provenance of the nine calibrated
  registry records without changing their point values; a per-observable
  multiplier variant is recorded as an unconverged sensitivity study that
  diagnoses the biomass/cellulose misfit.
- Candidate review `pakula_2016_t_reesei_protein_load_review.yml` (status
  `proposed`, no values) for replicate-level cultivation data.
- Environment response laws (`docs/environment-response.md`): Rosso cardinal
  temperature (`temperature_cardinal_rosso`, CTMI) and cardinal pH
  (`ph_cardinal_rosso`, CPM) modifiers (`fungal_model.kinetics.cardinal`,
  `fungal_model.modifiers.cardinal`); a diprotic pH-ionization
  Michaelis-Menten process law (`ph_ionization_michaelis_menten`,
  `fungal_model.kinetics.ionization`, `fungal_model.processes.ionization`)
  matching the SABIO-RK pH-dependent law form; and a first-order Arrhenius
  thermal-inactivation process law (`thermal_inactivation`,
  `fungal_model.kinetics.inactivation`, `fungal_model.processes.inactivation`).
  All compile to numeric kernels, validate their parameters, require sources,
  and warn outside declared measured ranges. Factories, config builders,
  configured-output rows and two non-biological toy configs are included.
- Registry templates bind the new modifiers through role fields and the new
  process laws through their `process_type`; the environment entity is
  generated for every condition a bound law reads. Assembled configs record
  `provenance.environment_response`; `RegistryCaseEnsemble` carries it and
  the virtual-experiment tables derive `environment_effect_status:
  active_response_model` from it, list the laws in
  `environment_response_model`, and allow environment ranking only when every
  condition that varies across the screen is covered by a law or
  condition-specific records.
- First registry case with an active response law: *Phanerochaete
  chrysosporium* K-3 BGL1A on cellobiose over pH 4 to 8 (SABIO-RK Reaction 618
  entry 38522, Tsukada et al. 2008). Fungus, five environment, compatibility
  and template records, eight `literature_processed` constants copied verbatim
  from the archived raw export (SHA-256 recorded) and two explicit
  `exploratory_prior` loading assumptions; exploratory mode only.
- Candidate review for *T. harzianum* cardinal temperatures
  (`data/experiments/candidate_reviews/trichoderma_harzianum_cardinal_growth_review.yml`),
  proposed with no transcribed values.

- First whole-organism registry case: *Trichoderma harzianum* P49P11 on
  Celufloc 200 cellulose (Gelain 2020) runs in `scientific` mode through
  `VirtualExperiment` with biomass, filter-paper and beta-glucosidase activity,
  cellulose and two closure-ledger trajectories. Fungus, enzyme-class,
  substrate, three culture-condition, compatibility and template records plus
  nine `calibrated` parameter records (artifact path, SHA-256, training
  conditions, rank diagnostics and at-bound flags) and four deposited initial
  conditions (`docs/organism-physiology.md`).
- `culture_physiology` case-template family
  (`fungal_model.screening.culture_physiology`): generic multi-process
  assembly with `biomass` and indexed `ledger_*` state roles, product-map
  coefficients bound to parameter roles (`parameter_role`,
  `complement_of_parameter_role`), a build-time closure check and fail-closed
  role accounting; registered as a `scientific`/`toy` assembler.
- `proportional_synthesis` process (`ProportionalSynthesisProcess`,
  `ProportionalSynthesisFactory`): producer-proportional formation of a
  product pool with optional saturable induction, compiled to a numeric
  kernel, with a non-biological toy config
  (`data/model_configs/toy_proportional_synthesis_dissolved.yml`).
- Assay-activity base units in the core registry: `filter_paper_unit` (`FPU`)
  and `beta_glucosidase_assay_unit` (`BGU`); the Gelain research units
  `gelain_fpu`/`gelain_beta_u` are now aliases of them.
- Compiled well-mixed model core (`fungal_model.solvers.compile_assembled_model`):
  units resolve once at build time, stoichiometry is probed from
  `Process.contributions` and checked for linearity, and every shipped process
  and modifier supplies a numeric rate kernel. Dynamic Gibbs constraints compile
  to a float feasibility test. `solver_metadata["kernel"]` records each
  process's kernel kind; processes without a kernel use an explicit, exact
  unit-aware fallback. Trajectories and evaluation counts are unchanged on every
  packaged config; solves are 6 to 60 times faster.

- Opt-in balanced secretion–digestion–growth feedback with seven dynamic pools,
  explicit protein synthesis costs, chemically retained inactive protein,
  substrate allocation and batch degradation thresholds. Illustrative kinetics
  remain separate from measured total-protein output.
- Checksummed Jørgensen 2009 primary data, entire-strain protein-output holdouts,
  an offline coupled-culture runner and four plots, including a kinetic
  sensitivity envelope. No whole-fungus validation or registry promotion.
- Opt-in conserved growth/maintenance respiration with nitrogen/oxygen limitation,
  gas transfer, batch/chemostat dynamics, open material balances and explicit
  unmet-maintenance diagnostics. Complete sourced energies are required for entropy.
- Two checksummed A. niger primary datasets, training-only Pirt holdouts,
  external-regime challenges, error-corner sensitivity and four reproducible plots.
  Inconsistent source cells remain quarantined; whole-fungus validation is open.

- Unit-bearing per-state solver tolerances and first-step control across main
  engines; sparse Cartesian Jacobians for supported local spatial dynamics.
- Sourced closed detailed-balance reaction networks with analytic Jacobians,
  independent free-energy equilibrium, conservation and entropy diagnostics.
- Reproducible four-solver replay of 33 existing culture holdouts and plots;
  explicit refinement resolves a BDF depletion failure without clipping.
- Conservation-law macrochemical balance in `fungal_model.chemistry`: solves
  overall exchange stoichiometry from element and charge conservation and forms
  reaction energies and an entropy budget from sourced formation energies. A
  constraint layer only; it predicts no rate or yield.
- Joint Gelain culture/activity benchmark with published-equation refits,
  activity-driven hydrolysis and retained dry-mass alternatives, 33 condition
  holdouts, explicit covariance sensitivity, profile loss and conditional
  bootstrap. FPU and pNPG activity remain separate assay dimensions.
- Generic sourced Gaussian covariance and single-response censoring, plus
  frozen model/observation/scope/criteria contracts for independent validation.
  Current culture models retain explicit missing-evidence status.

- Added the bounded Gelain 2020 T. harzianum culture benchmark: unit-aware source
  reproduction, an explicitly exploratory growth/loss model, six whole-condition
  holdouts, weighting sensitivity, frozen artifacts and cross-solver checks.
  Missing replicate uncertainty and substantial cellulose prediction errors
  remain explicit; no validated organism model or registry promotion is claimed.

### Changed

- `EnvironmentGrid` runtime cases and the virtual-experiment registry overlay
  no longer assert that temperature and pH are inert; their status is the
  status before assembly and the assembled case decides. Metadata-only
  behaviour is unchanged for cases that bind no law.
- The runtime-grid overlay no longer copies condition-specific records that
  differ only by registry environment (the three Gelain cellulose loadings):
  a grid over *T. harzianum* reports the loading as missing and lists the
  symbol under `ambiguous_condition_specific_symbols` instead of silently
  taking one condition's value.
- `beta_glucosidase` enzyme class lists `ph_ionization_michaelis_menten` as a
  compatible process; the SABIO-RK rice-enzyme case still selects plain
  Michaelis-Menten.

- Compiled models evaluate every rate at `max(state, 0)` (recorded as
  `negative_state_policy` in `solver_metadata["kernel"]`) so that a pool can be
  consumed to depletion without the solver's trial iterates raising; the
  integrated trajectory is never clipped and the `non_negative` validator still
  reports accepted states below tolerance. Process rates recorded at output
  points use the same projection. The unit-aware `Process.rate` API stays
  strict for caller-supplied negative states.
- Modelability no longer marks a case underparameterized because an organism
  carries an enzyme class that does not target the requested substrate; such
  classes are reported as known, unused items when another class reaches a
  compatible process. Registry compatibility selection skips enzyme classes
  without a compatibility record instead of raising.
- `ProcessODESolver` integrates the compiled right-hand side. Environment-only
  rate modifiers are evaluated once per run, so their source-range warnings fire
  once rather than at every right-hand-side evaluation. `_record_process_rates`
  reuses compiled kernels for unconstrained processes.

### Fixed

- The cross-engine reference simulator compiles kinetic laws from their L3
  infix text instead of libSBML `ASTNode` objects, so SBML round-trip and
  trajectory checks no longer fail once `libsedml` has been imported in the
  same process (SWIG proxy registry clash). Unsupported constructs still raise
  `SbmlExportError`, now at compile time.
- Repository data and documentation are read as UTF-8 explicitly; Windows
  no longer decodes `±` and non-ASCII text with cp1252. Frozen-artifact
  manifest paths compare as POSIX on every platform.
- The Gelain joint holdout replay test propagates the prediction tolerance
  into its score comparison instead of using a fixed 1e-6 absolute tolerance
  that activity predictions of order 1e3 U/L could not meet under current
  SciPy. Frozen artifacts are unchanged.
- Analytic piecewise Jacobians for resource-limited and integrated cultures
  prevent finite-difference perturbation overflow in non-feedback ledger states
  during depletion. Rate laws and conservation equations are unchanged.
- Incomplete/nonfinite main-engine integrations now raise `IntegrationError`
  instead of returning partial trajectories. Invalid numerical controls reject.
- Reversible net flux uses `expm1` to avoid cancellation near equilibrium.
- Fixed mixed-unit SBML trajectories, preserved PEtab training/validation/holdout separation, and rejected missing or zero export noise scales. Regenerate older affected exports.
- Fixed thermodynamic scalar typing and pinned the checked Pyright version for local/CI parity.
- Consolidated exploratory inhibition runners through shared unit-aware package integration and the configured inhibition kernel (FD-008 resolved).
- Added explicit-noise grid profile likelihood and checksum-bound frozen-prediction evaluation with raw replicate evidence. Independent empirical validation remains pending on suitable external data.
- Corrected configured calibration when uncertainty units differ from observation units.

- Removed the pNPG Michaelis constant from the cellobiose cross-source fit;
  the unknown cellobiose constant is estimated with explicit limitations.
- Comparison statistics now require an explicit fitted-parameter count for
  reduced chi-square and omit undefined values. Configured calibration records
  the training count and preserves pointwise uncertainties instead of averaging.
  Partial uncertainty fails explicitly; entirely unknown scales remain unweighted.
- Research runners check solver/optimizer success and nested-model consistency,
  verify reference trajectories against the configured package path, and report
  descriptive results instead of automatic mechanism conclusions. Research
  summary schemas are now `2.0.0`; regenerate historical study outputs.
- Added warnings for approximate confidence intervals outside optimizer bounds,
  reconciled literature-calibration guidance, and extended quality gates to
  research runners. No new empirical validation or biological mechanism is claimed.

### Added

- `fungal_model.chemistry.haldane`: Haldane relations tying reversible
  Michaelis-Menten parameters to the equilibrium constant, with
  `equilibrium_constant_from_gibbs`, `reverse_vmax_from_haldane`, and
  `check_haldane_consistency`. Given a sourced standard Gibbs energy and three
  measured parameters the fourth is determined rather than fitted, which removes
  a degree of freedom exactly where kinetic data is scarce. Scoped to uni-uni
  mechanisms; multi-substrate reactions are rejected, not approximated.
- `fungal_model.fungi.energetics.GibbsEnergyYieldBound`: a thermodynamic ceiling
  on biomass yield, `Y_max = |dG_catabolic| / dG_anabolic`. Wired into
  `FungalCouplingModel` as an opt-in `yield_bound`, so a configured yield that
  would create free energy is rejected before the model can run. Both Gibbs
  energies must be sourced; the bound invents no energy value.
- `fungal_model.capability`: genome-derived enzymatic capability resolution.
  A curated, literature-sourced CAZy family to enzyme-class map
  (`data_registry/cazyme_families/cazyme_family_map.yml`, 18 families), an
  offline dbCAN `overview.txt` parser, and a resolver that separates capabilities
  FungMod can model from capabilities the organism has but FungMod cannot, and
  family-diagnostic assignments from family-polyspecific ones. Presence and
  absence only: a test asserts the output carries no rate or kinetic constant.

- Two further literature sources, taking the repository to three independent
  sources, seven series, and four enzyme preparations across three kinetic
  regimes. `scripts/digitize_ariaeenejad_2020_figure_6.py` adds a 17-point,
  380 h PersiBGL1 series (Ariaeenejad 2020, CC BY);
  `scripts/digitize_cao_2015_figure_5a.py` adds two 6-point, 10 h series for
  wild-type Bgl6 and mutant M3 at 10 % w/v cellobiose (Cao 2015, CC BY 4.0).
  Both digitizers verify their axis calibration against values each source
  states in prose, independently of the figure, and refuse to write otherwise.
- `scripts/run_cross_source_structural_test.py`, which fits the shared rate-law
  structure to five selected series with and without enzyme deactivation, and
  reports numerical diagnostics for both fits without asserting identifiability.
- The Ariaeenejad 2020 candidate review moves from blocked to
  `approved_for_ingestion`, with a `resolution_review` block recording that the
  time-axis conflict was resolved by the figure's own x-axis label. The original
  blocked verdict is retained as the audit trail and marked superseded.

### Findings

- Earlier cross-source structural-adequacy and deactivation-warranted claims
  are superseded by the research-analysis corrections above. Training residuals
  and local Jacobian diagnostics do not establish those conclusions. The
  PersiBGL1 fit previously used a Michaelis constant from a different substrate;
  regenerate results with the corrected exploratory parameterization.
- Resa and Buckin (2011) is confirmed paywalled with no extractable observations
  and remains blocked.

- Three additional digitized series from Alvarez-Gonzalez et al. (2022)
  Supplementary Figure S1, taking the repository from nine to thirty-six real
  literature observations across all four series of that figure
  (`scripts/digitize_alvarez_gonzalez_2022_figure_s1.py`). The script verifies
  the supplementary PDF SHA-256 and refuses to write unless it first reproduces
  the previously committed Figure S1A filled-square series within the declared
  0.6 mM digitization resolution (achieved: 0.273 mM).
- A held-out condition study (`scripts/run_alvarez_gonzalez_2022_holdout_prediction.py`)
  predicting the three previously undigitized series from the publication's own
  Model 3 parameters with no FungMod fit.
- A two-stage calibration study
  (`scripts/run_alvarez_gonzalez_2022_stage2_calibration.py`) fitting FungMod
  parameters on one series and predicting the held-out conditions.
- Configured calibration now accepts `literature_raw` and `literature_processed`
  datasets in addition to `synthetic`, through an explicit
  `CALIBRATABLE_DATASET_MATURITIES` allowlist. Toy, framework, calibrated, and
  validated maturities still fail closed. A literature calibration records
  `dataset_maturity` and carries parameter-estimation assumptions and a
  non-validation warning instead of the synthetic-fixture wording.
- Within-source prediction residuals differ across substrate and nominal enzyme
  loadings. They do not establish general parameter transferability or uniquely
  attribute discrepancies to mechanism structure.
- A model-free comparison of the two panels gives an apparent enzyme scaling of
  `[E]^0.28`, against the `V_max = k_cat * [E]` linearity the configured model
  assumes. Recorded as an unsupported capability rather than tuned away.
- The Figure S1 caption's panel-B unit (`296.1 mg/mL` against panel A's
  `59.2 mg/L`) is refuted as printed by the data: it implies exhaustion of the
  222 mM charge in about 0.19 s against 36.66 mM observed at 60 min. The mg/L
  reading is adopted as an explicitly recorded assumption; the printed value and
  unit are preserved verbatim in the dataset records.
- In the four-parameter fit, the approximate interval for positive `K_i` extends
  outside its admissible range. This flags an unsuitable local interval or weak
  identification, not a negative physical constant. Fixing it at the source's
  point estimate is a conditional model choice, not new measurement evidence.

- SBML Level 3 export for the supported well-mixed kinetic processes
  (first-order decay, mass action, and homogeneous Michaelis-Menten) via the
  optional `standards` extra (`fungmod.standards.to_sbml`,
  `model_config_to_sbml`, `write_sbml`).
- Cross-engine trajectory checks: an independent reference SBML integrator and
  `cross_engine_trajectory_check`, confirming exported SBML reproduces FungMod's
  own solver trajectories to solver tolerance.
- SED-ML Level 1 Version 4 simulation export (`fungmod.standards.to_sedml`) and
  COMBINE archive (`.omex`) generation (`write_combine_archive`,
  `model_config_to_combine_archive`) bundling the SBML model with its SED-ML
  time course into one portable, byte-reproducible file.
- PEtab export for calibration cases (`fungmod.standards.calibration_config_to_petab`):
  writes a complete PEtab problem (SBML model, observable/measurement/condition/
  parameter tables, and `problem.yaml`) from a calibration config, with
  measurement values and times converted to the model's units. The result passes
  `petab.lint_problem`.
- SBO terms (added automatically by kinetic role) and MIRIAM annotation support
  (`MiriamAnnotation`, `to_sbml(annotations=...)`) in the SBML export.
- A BioModels-ready deposit for the SABIO-RK Reaction 618 β-glucosidase case
  (`fungmod.standards.write_biomodels_deposit`): annotated SBML (ChEBI, EC,
  UniProt, KEGG, MetaNetX, NCBI Taxonomy, PubMed), a COMBINE archive, and a
  submission README. Curated Km/kcat; initial concentrations are explicit
  assumptions.

### Fixed

- `fungmod.<subpackage>` nested imports (e.g. `fungmod.core.units`) now resolve
  to the exact same module object as `fungal_model.<subpackage>`, so shared
  state such as the pint unit registry is not duplicated across a registry
  boundary.

### Scientific scope

- SBML export refuses (rather than silently approximates) models with
  unsupported processes, rate-modifier wrappers, or dynamic thermodynamic
  constraints, so an exported model always matches FungMod's behaviour.

## [0.1.1] — 2026-08-01

### Added

- Packaged, provenance-labelled parameter input for five purified fungal
  beta-glucosidases reported on cellobiose at matched assay conditions.
- A deterministic full notebook with configured dynamic glucose inhibition,
  2:1 glucose stoichiometry, inhibition-free counterfactuals, scenario
  summaries, figures, validators, diagnostics, and manifests.
- One provenance-matched, no-refit comparison with nine digitized literature
  time-course observations.
- A generic coupled hydrolysis/substrate-transglycosylation process and one
  provenance-backed *Phanerochaete chrysosporium* BGL1B configuration.
- A minimal exploratory well-mixed fungal-process coupling API.
- Uniform Cartesian 2D/3D finite-volume reaction diffusion.
- Constant-activity-coefficient nonideal reversible thermodynamics with local
  detailed balance.
- Independent-input variance-based global sensitivity with Saltelli
  first-order and Jansen total-order estimators.
- A publication-oriented calibration evidence audit whose software pass never
  authorizes a publication claim.

### Changed

- Removed the tracked package-resource mirror. Source distributions now stage
  canonical `data/` and `data_registry/` bytes deterministically into wheels.

### Scientific scope

- The new cases model purified enzymes labelled by fungal source, not
  whole-fungus physiology.
- Literature parameters remain separate from the explicit 10 nM showcase dose
  and starting-concentration assumptions.
- The time-course comparison uses source-model parameters and observations
  from the same publication without refitting; it is not independent
  validation, and digitization resolution is not experimental uncertainty.
- The fungal coupling remains an artificial software-tested composition, not
  organism-specific physiology or whole-organism validation.
- Transglycosylation product identity/re-hydrolysis, empirical parameter
  distributions, correlated-input sensitivity, publication-grade biological
  calibration, model discrepancy, and organism ranking remain unavailable.

## [0.1.0] — 2026-07-30

### Added

- PyPI distribution name `fungmod` with Python 3.11–3.13 metadata.
- `fungmod` convenience import namespace while retaining `fungal_model`.
- Immutable wheel-packaged registry, frozen source evidence, and example data.
- Public `default_registry_path()`, `example_data_path()`, and
  `package_data_path()` helpers.
- Installed-wheel fallback for the default virtual-experiment registry,
  frozen SABIO-RK Reaction 618 source proposal, configured example paths, and
  PET plugin benchmark assets.
- Artificial, framework-labelled dynamic-thermodynamics showcase configuration.
- Full zero-to-report and advanced-capabilities notebooks.
- MkDocs Material documentation configured for Read the Docs.
- Deterministic notebook/resource drift checks and isolated-wheel smoke tests.
- Trusted Publishing release workflow and expanded CI release gates.

### Scientific scope

- No new organism-specific biology or empirical validation data were added.
- The advanced inhibition and thermodynamic examples are artificial software
  benchmarks with explicit provenance, maturity, assumptions, and limitations.
- Existing exploratory ranges remain exploratory; they were not reclassified
  as calibration or validation evidence.

[Unreleased]: https://github.com/felixlaga/FungMod/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/felixlaga/FungMod/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/felixlaga/FungMod/releases/tag/v0.1.0
