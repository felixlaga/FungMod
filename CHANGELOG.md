# Changelog

All notable public releases of FungMod are documented here.

## [Unreleased]

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
  sources, five series, and four enzyme preparations across three kinetic
  regimes. `scripts/digitize_ariaeenejad_2020_figure_6.py` adds a 17-point,
  380 h PersiBGL1 series (Ariaeenejad 2020, CC BY);
  `scripts/digitize_cao_2015_figure_5a.py` adds two 6-point, 10 h series for
  wild-type Bgl6 and mutant M3 at 10 % w/v cellobiose (Cao 2015, CC BY 4.0).
  Both digitizers verify their axis calibration against values each source
  states in prose, independently of the figure, and refuse to write otherwise.
- `scripts/run_cross_source_structural_test.py`, which fits the shared rate-law
  structure to every series with and without enzyme deactivation, and screens
  each fit for identifiability by bound proximity and Jacobian conditioning.
- The Ariaeenejad 2020 candidate review moves from blocked to
  `approved_for_ingestion`, with a `resolution_review` block recording that the
  time-axis conflict was resolved by the figure's own x-axis label. The original
  blocked verdict is retained as the audit trail and marked superseded.

### Findings

- One rate-law structure is adequate across all three sources. Identified fits
  reach 0.21 % to 6.29 % of series scale. One of five series, the Alvarez-Gonzalez
  70 g/L condition, is flagged DEGENERATE when fitted alone because K_m runs to
  its search bound: that condition is predictable from other data but not
  identifiable from its own curve.
- Enzyme deactivation is warranted for wild-type Bgl6 (fitted half-life 4.2 h in
  a 10 h assay, 39 % RMSE reduction) but not for its engineered mutant M3, and
  not for any Alvarez-Gonzalez series. The framework recovered this distinction
  from progress curves alone; it is consistent with the source publication's own
  point that M3 is the more robust variant.
- The PersiBGL1 fit reproduces the observed plateau with a product-inhibition
  constant near 34 mM, which contradicts that source's claim of a glucose
  inhibition constant near 8.8 M. Recorded as an unexplained discrepancy.
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
- Model parameters transfer across initial substrate concentration but not
  across enzyme loading. Predicting the 70 g/L series at the training enzyme
  loading, with no parameter changed, gives 1.28% relative RMSE. Both panel-B
  series, at a nominal five-fold enzyme loading, show 9/9 positive residuals and
  are not repaired by refitting.
- A model-free comparison of the two panels gives an apparent enzyme scaling of
  `[E]^0.28`, against the `V_max = k_cat * [E]` linearity the configured model
  assumes. Recorded as an unsupported capability rather than tuned away.
- The Figure S1 caption's panel-B unit (`296.1 mg/mL` against panel A's
  `59.2 mg/L`) is refuted as printed by the data: it implies exhaustion of the
  222 mM charge in about 0.19 s against 36.66 mM observed at 60 min. The mg/L
  reading is adopted as an explicitly recorded assumption; the printed value and
  unit are preserved verbatim in the dataset records.
- In the four-parameter fit, the substrate-inhibition constant `K_i` is
  unidentified from a single progress curve: its approximate 95% interval spans
  negative values. Dropping it tightens the `V_max` standard error 2.5-fold and
  improves held-out accuracy.

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
