# FungMod Progress

This is the active progress ledger for the virtual-experiment directive in
`foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md`.

Historical foundation-first and long-term roadmap notes are archived under
`old_progress/`; they are context, not the active starting point.

Older dated entries in this ledger preserve the project state and wording from
the time they were written. They do not override `AGENTS.md` or the current
biology rule.

Update this file whenever a feature, test, example, notebook, or architectural
milestone changes. The goal is that a future reader can quickly answer:

- what FungMod can do today;
- what is still only a roadmap item;
- what scientific assumptions are implemented;
- what failure modes are tested;
- which examples and tests prove the current behavior.

Status key:

- `complete`: implemented and tested for the stated scope.
- `partial`: useful infrastructure exists, but the roadmap stage is not fully complete.
- `not started`: no new long-term-roadmap implementation exists yet.
- `blocked`: implementation needs a decision, dependency, or sourced data.

## USERDATA-003 Enzyme Repertoire From A Genome Annotation

Status: `complete` for the stated scope (2026-10-06); the third increment of
the user-supplied-data route. It connects the existing genome capability
resolver to virtual experiments: "fungus X on substrate Y in conditions Z"
can now take the strain's enzyme classes from its genome annotation instead of
a hand-written `enzymes.csv`, and every resolved class that can act on a
dataset substrate but has no kinetics becomes an explicit, named measurement
request. No rate is ever inferred from a genome.

Changed:

- `api/user_data.py`: optional `genomes.csv` (`strain_id`, `annotation_file`,
  `annotation_tool`, `source`, optional `min_tools_agreeing`). The annotation
  file is a dbCAN `overview.txt` addressed relative to the dataset directory
  (absolute paths, `..`, backslashes and symbolic links leaving the directory
  refused; missing files refused); its bytes enter the dataset digest and
  `file_digests`. `annotation_tool` must be dbCAN followed by a version, which
  is recorded as given; other tools and a missing version are refused. One
  annotation per strain, strain declared in `strains.csv`. Families are
  resolved with `CapabilityResolver` and the curated family map against the
  base registry's enzyme classes. Classes with a registry record join the
  strain's declared classes before kinetics and responses are checked (evidence
  "genome annotation (dbCAN, N genes, families ...)", source from the row); an
  explicit `enzymes.csv` row wins and the genome evidence is recorded beside it
  in the fungus record. Classes without a record go to
  `unmodellable_enzyme_classes` (class, families, gene count, specificity,
  reason) and families without a class to `unmapped_families`; neither
  produces a record. Gap requests of genome-only classes end with "; the class
  was inferred from the dbCAN annotation (families ...)", plus a note for
  polyspecific families, and their provenance carries `class_evidence:
  genome_annotation`. With `genomes.csv`, `enzymes.csv` may hold only its
  header; a strain whose annotation resolves no class with a record and that
  has no explicit row is refused, naming the classes found. `UserDataset`
  gains `genome_annotations`, `genome_resolved_classes`,
  `unmodellable_enzyme_classes`, `unmapped_families` (in `to_dict()`) and
  `summary()`. Datasets without `genomes.csv` generate byte-identical records
  (the USERDATA-002 snapshot test passes unchanged).
- Consensus rule: the existing code has no multi-tool threshold;
  `families_from_overview` counts a family called in any tool column. That is
  the default, applied per gene. `min_tools_agreeing` (user-given, between one
  and the number of tool columns present) requires that many tool columns to
  call the family for the same gene. No threshold is chosen by FungMod.
- `capability/dbcan.py`: `parse_overview` and `DbcanOverview.family_genes`
  (per-gene calls, gene counts, the optional threshold; refuses a header
  without `Gene ID` or a tool column, repeated or blank gene identifiers, rows
  wider than the header, files without calls). `capability/resolution.py`:
  `default_family_map_path`. The family map's two citations containing ": "
  were unquoted YAML and loaded as mappings; they are now quoted (no mapping
  changed).
- `api/virtual_experiment.py`: `VirtualExperiment.user_dataset_summary`;
  `to_dict()` (and so `virtual_experiment_summary.json`) lists
  `genome_resolved_classes`, `unmodellable_enzyme_classes` and
  `unmapped_families` beside `user_dataset_id` (`null` without user data);
  `write_preflight_report` also writes `user_dataset_genome_resolution.json`
  when the dataset has a `genomes.csv`.
- Docs: `docs/user-data.md` genome-annotation section (format, consensus rule,
  three outcomes, gaps, outputs, limits), `docs/capabilities.md` (the genome
  route is connected but assigns no rates), README user-data sentence,
  changelog.

Tests: `tests/test_user_data_genome.py` (30 tests) with the fixture
`tests/fixtures/user_data/genome_case/` (a hand-written dbCAN overview in the
documented format, marked in its README as a format fixture with synthetic
gene identifiers, not a real genome; `enzymes.csv` header only, no kinetic
values). With the shipped registry: `beta_glucosidase` (GH1, GH3, three genes,
polyspecific) and `cellulase_generic` (GH5) join the strain;
cellobiohydrolase, endo_xylanase, glucoamylase and laccase are listed as
unmodellable and generate nothing; CBM1 and GT2 are unmapped; the four
beta-glucosidase gaps on cellobiose carry the genome-aware request; preflight
is `underparameterized` in both modes with the requests as suggested
experiments and the preflight report writes the genome JSON; scientific and
exploratory simulation are refused. An explicit `enzymes.csv` row wins with
both pieces of evidence. With an in-memory registry extended by a test-only
glucoamylase record, GH15 resolves to a class on the non-cellulose substrate
maltose with its own gaps, and user estimates for beta-glucosidase make the
cellobiose case run in exploratory mode (substrate falls, product is twice the
substrate consumed) while the maltose case stays underparameterized. Also:
`min_tools_agreeing` 2 and 3 change the classes and gene counts, and 4, 0 and
"two" are refused; refusals for an absolute path, an escaping path, a symbolic
link out of the directory, a missing file, an unknown tool, a tool without a
version, an undeclared strain, a second annotation for a strain, a malformed
header and a repeated gene; the digest changes when one annotation byte
changes; datasets and experiments without a genome report empty or `null`
lists; no genome-derived entry carries a rate; `parse_overview` keeps the
family set of `families_from_overview`. The no-hardcoding guardrail forbids
the new fixture's class and substrate words in `api/user_data.py`.

Not changed: no process law, modifier, solver, registry record, family
mapping, output table schema (still `1.8.0`) or shipped preflight text; the
resolver's `require_diagnostic` filter is not exposed; user data never
reaches `data_registry`.

Scientific impact: a strain's enzyme repertoire can come from its genome
annotation with every class traced to its genes, families, tool version and
file digest, while kinetics stay explicit unknowns with measurement requests
until measured or curated values are supplied. Classes FungMod cannot model
are reported, not dropped or invented.

Non-specific coverage: the shipped registry has no record for any family-map
class acting on a non-cellulose substrate (its mapped classes with a record
are `beta_glucosidase` and `cellulase_generic`), so the non-cellulose case
uses a test-only in-memory glucoamylase record on maltose; no such record is
shipped.

Limitations: dbCAN `overview.txt` only, from the dataset directory, no
download; family-level mapping (18 families, polyspecific families give
candidates, `EC#` unused); only classes with a registry record are added;
gene counts are annotated genes, not expression; no annotation date column.

Recommended next task: curated registry enzyme-class records for the
family-map classes that the genome route reports as unmodellable
(cellobiohydrolase, endo-xylanase, LPMO), each with its own provenance and
compatibility, so that annotations resolve to more modellable classes; then
user time-course tables.

## USERDATA-002 Vmax, Activity And Environment Responses In User Data

Status: `complete` for the stated scope (2026-10-06); the second increment of
the user-supplied-data route. It removes the two largest practical barriers of
USERDATA-001: most laboratories report a maximum rate, a specific activity or
an assay activity rather than `kcat`, and kinetics depend on temperature and
pH.

Changed:

- Generic (`screening/case_builder.py`): `RegistryRoleSet` and
  `RegistryProcessAssembler.alternative_role_sets`, `role_set_for` and
  `parameter_roles_for`. The homogeneous Michaelis-Menten assembler accepts
  either `{km, kcat, substrate_initial_concentration,
  enzyme_initial_concentration}` (primary, unchanged) or `{km, vmax,
  substrate_initial_concentration}` with template state roles `substrate` and
  `product` only; the compatibility record's `parameter_roles` select the set,
  and binding two complete sets is refused. `_enzyme_kinetics_config_data`
  takes the selected state roles (the process `vmax` form of
  `HomogeneousMichaelisMentenFactory` already existed). `screening/ensemble.py`
  and `api/result_tables.py` ask the assembler for the role set instead of the
  primary roles. `modelability.py` needed no change (it reads the
  compatibility's `required_parameters`).
- `api/user_data.py`: `kinetics.csv` quantities `vmax` (method required),
  `specific_activity`, `enzyme_loading`, `assay_activity` and columns
  `activity_substrate`, `activity_saturating`; per case one rate form (kcat
  with an enzyme concentration, or Vmax) and one Vmax route (explicit row;
  `specific_activity` x `enzyme_loading` as a derived record computed with
  pint, listing both rows, the formula and the conversion, maturity the weaker
  input's under `USER_DATASET_MATURITY_ORDER`, one range input scaled, two
  ranges refused; or an assay activity accepted only on the case substrate at
  saturation); one form per enzyme class and substrate. Optional
  `responses.csv` (`RESPONSE_LAWS`: `temperature_cardinal_rosso`,
  `ph_cardinal_rosso`, `temperature_arrhenius_reference`, all existing
  template modifiers): parameters complete and unique, dimensions checked, the
  law's own domain checked by evaluating the implemented law, one law per
  condition and pair, `design` evidence refused, and the reference-condition
  rule (kinetic constants at the law's optimum or reference temperature,
  exactly, within the row's own `reference_tolerance`, or declared with
  `kinetics_at_reference = yes`). Laws are bound as
  `process_state_metadata.process_modifiers` of the generated template with
  condition-independent parameter records (temperatures in kelvin), the whole
  law at its weakest row's maturity; other strains of the pair get law gaps.
  Gap requests follow the started rate form, or name both forms ("Measure kcat
  and the enzyme concentration ..., or Vmax (or a specific activity and enzyme
  loading)."). Datasets without the new quantities or `responses.csv` generate
  byte-identical records.
- Docs: `docs/user-data.md` (quantities, rate forms, the three Vmax routes and
  their refusals, `responses.csv`, reference-condition rule, maturity
  ordering, gaps, limitations), a cross-reference in
  `docs/environment-response.md`, README subsection and capability row,
  changelog.

Tests: `tests/test_user_data_v2.py` (51 tests) with the fixture
`tests/fixtures/user_data/oxidase_case/` (a laccase-like oxidase class on the
`phenolic_oh` bond of a dissolved user substrate, specific activity in
umol/min/mg and loading in mg/L, cardinal temperature 10/50/70 degC and pH
3/5/8 laws, estimates only): the derived Vmax equals 12 umol/min/mg x 0.05
mg/L = 0.6 uM/min and lists both rows; weaker-maturity cases; exploratory
simulation runs; an `EnvironmentGrid` over 20, 50 and 65 degC is fastest at
50 degC and its initial rates match the CTMI factors computed in the test
(0.15625, 0.47265625) to 1e-9, with `active_response_model`; a pH grid matches
the CPM; an Arrhenius binding matches exp(-Ea/R (1/T - 1/T_ref)); scientific
mode refused for estimates and reached with measured kinetics and laws; the
Vmax form reproduces the kcat form on the Reaction 618 re-entry when Vmax =
kcat x E (largest difference 5e-14 mM against a solver bound of 2e-7 mM); 25
refusal cases; gap requests; law gaps for a second strain; a pair mixing rate
forms refused; laws checked against the existing modifier roles; and a
snapshot test that the shipped Reaction 618 and BGL1A configs, the
USERDATA-001 scientific config and the USERDATA-001 generated records are
byte-identical to the code before this change
(`tests/fixtures/user_data/assembled_config_snapshots.json`, taken from the
base commit). In `tests/test_user_data_import.py` three expectations that
asserted the lifted v1 refusals now assert the replacements (a `vmax` row next
to an enzyme concentration, an unsupported `timecourse.csv`, a `vmax` row
without its method); the guardrail forbids the new fixture's enzyme and
substrate words in `api/user_data.py`.

Not changed: no process law, modifier, solver, registry file, shipped record,
output table schema or shipped preflight text; shipped cases assemble
byte-identically; user data never reaches `data_registry`.

Scientific impact: user data can now state the rate a laboratory measured and
how it depends on temperature and pH, through laws FungMod already implements,
with derived values traceable to their rows and the weakest evidence carried
through. Nothing is converted between substrates, from sub-saturating assays,
or between molar and mass units.

Limitations: one rate form per enzyme class and substrate; the Vmax form has
no enzyme state (no enzyme loss or dilution); assay activities are read per
volume of the simulated system; laws scale the rate only (Km and
concentrations are not rescaled), one per condition, no Gaussian pH, oxygen,
water-activity or thermal-inactivation laws from user tables, and no Arrhenius
validity bounds; laws are bound per enzyme class and substrate, so other
strains of the pair need the law's parameters.

Recommended next task: user time-course tables (`timecourse.csv`) compared
against the simulated trajectories with the existing comparison metrics, then
fitting of user kinetic constants to them.

## USERDATA-001 User-Supplied Enzyme And Kinetics Tables Into Virtual Experiments

Status: `complete` for the stated scope (2026-10-06); the first increment of
the user-supplied-data route of the product goal ("the user names fungus X,
substrate Y and conditions Z, and FungMod assembles the enzymes and kinetic
parameters from stored data, from user-supplied data, or fetched, and
simulates").

Changed:

- `fungal_model.api.user_data`: `load_user_dataset(path, registry=...)`,
  `UserDataset` (`dataset_id`, `digest`, `records`, `overlay(base)`,
  `to_dict()`) and `UserDataError` (`issues`: file, spreadsheet row, column,
  message; every issue is collected before raising). A directory holds
  `user_dataset.yml` (dataset id, contributor, date, source, required time
  grid) and `strains.csv`, `enzymes.csv`, optional `enzyme_classes.csv`,
  `substrates.csv`, `conditions.csv`, `kinetics.csv`; any other CSV is refused.
  Validation covers units (pint), the dimension of each quantity, molar versus
  mass concentrations (a molar mass would be needed), finite nonnegative
  values with positive `km`, ranges, duplicate and exact-versus-range
  conflicts, undeclared references, registry name collisions, pH 0 to 14,
  dissolved substrates, explicit mol/mol yields, and `vmax`/activity rows
  (refused, never converted).
- Generated records, all `<dataset_id>__`-prefixed and built through
  `load_registry_record_mapping`: a fungus per strain; a namespaced enzyme
  class per declared class (a registry parent's bond classes, substrate classes
  and EC number copied, the parent ID in provenance only); user substrates
  (registry substrates are referenced, not copied); an environment per
  condition (kelvin with the original value in the notes); a homogeneous
  Michaelis-Menten compatibility and case template per compatible class and
  substrate, mirroring the Reaction 618 template, `scientific` only when every
  bound parameter record is exact and scientific-eligible; a parameter record
  per kinetics row (`user_measured`, `user_reported_literature`,
  `user_design_value` with scientific use when exact and exploratory screening
  when a range; `estimate` rows as `exploratory_prior`); and a
  `user_dataset_gap` unknown with a `measurement_request` for every missing
  role of every strain, class, substrate and condition.
- `fungal_model.provenance`: the reserved `fungmod_user_dataset` namespace
  (curator authoring refuses it; `classify_parameter_provenance` still
  returns `generic`).
- `VirtualExperiment.from_registry`, `from_names` and `virtual_experiment`
  take `user_data` (directory or `UserDataset`): the base registry is loaded,
  the dataset overlaid, names resolved on the overlay, then any
  `EnvironmentGrid` overlay applied. `user_dataset_id` and
  `user_dataset_digest` are kept on the experiment and written to
  `virtual_experiment_summary.json` and `output_manifest.json` (`null` without
  user data). Exported from `fungal_model.api`, `fungal_model` and `fungmod`.
- Generic: a missing parameter whose record carries a `measurement_request`
  is suggested with that text by `assess_modelability` and the standard table
  writer (`missing_item_suggestion`); shipped behaviour is unchanged.
  `parameter_source_class` and mechanism maturity label the new maturities.
- Docs: `docs/user-data.md` (in the nav), README subsection and public API
  list, capability row, API reference section, changelog.

Tests: `tests/test_user_data_import.py` (28 tests) with fixtures
`tests/fixtures/user_data/esterase_case/` (a user-defined carboxylesterase on
a user-defined aryl ester, estimates only: exploratory preflight modelable,
scientific blocked, exploratory simulation degrades substrate and releases
product) and `tests/fixtures/user_data/literature_reentry/` (the SABIO-RK
Reaction 618 selected entry re-entered as literature values with design
concentrations: scientific simulation satisfies the integrated
Michaelis-Menten relation within a solver-tolerance bound and product equals
twice the substrate consumed); a gap case; eleven validation cases plus
collection of all issues at once; registry bytes unchanged; production-factory
round trips; digest stability; the shipped registry's preflight suggestions
unchanged. Guardrail tests now cover `api/user_data.py` (no-hardcoding,
no-shortcuts, no organism/substrate/enzyme tokens), the public API lists the
new names, and the reserved-key authoring test includes the new namespace.

Not changed: no process law, solver, registry file, shipped record, output
table schema (still `1.8.0`), simulation authorization rule or shipped
preflight text. User data never reaches `data_registry`.

Scientific impact: users can now simulate their own enzyme kinetics with
provenance per value. Scientific mode on user data means exact inputs with
the stated evidence types, not validation; FungMod does not verify user
values against any source.

Limitations: homogeneous Michaelis-Menten on dissolved substrates only; `kcat`
and an enzyme concentration are required (no `vmax`, no activity units); no
molar/mass conversion and mol/mol yields only; no response laws, cocktails,
chains, time-course data or fitting; one substrate per substrate class for
each enzyme class; the standard deviation is provenance, not a sampling
distribution; a copied registry EC number makes EC resolution of enzyme
classes ambiguous on the overlaid registry; no promotion into the shared
registry.

Recommended next task: accept `vmax` with an explicit, sourced enzyme amount
or a specific-activity conversion record, then response-law tables
(temperature and pH) bound through the existing template modifiers.

## SPATIAL-002 Axisymmetric Geometry, Colony Observables And The Cardinal Water-Activity Law

Status: `complete` for the stated scope (2026-10-06); the first three items of
stage 0 of the colony comparison plan (COLONY-001).

- `SpatialGrid.axisymmetric(radius, cells)`: a one-axis radial grid for a
  colony with circular symmetry; cells are annuli (`cell_measures`,
  `measure_dimension` 2), the divergence takes per-face weights
  (`face_weights`), the axis face carries no flux, `spatial_integral` and
  `occupied_measure` use the per-cell measures. Every continuum process runs
  unchanged on either geometry; the artificial colony builder takes
  `geometry="axisymmetric"`.
- `fungal_model.mycelium.observation`: `colony_count_outside_disc`,
  `colony_hull_radius`, `colony_hull_area`, `disc_area_in_square`,
  `circle_length_in_square`; the hull radius is the farthest detected cell
  centre in both geometries so that they agree to within a cell.
- `cardinal_water_activity_activity` and `CardinalWaterActivityModifier`
  (`water_activity_cardinal_rosso_robinson`): the cardinal family with
  inflection on water activity with the maximum fixed at one (Rosso and
  Robinson 2001), the CTMI arithmetic shared with the temperature law; factory,
  template roles, configured-output row and docs table.
- Jacobians: LSODA on a one-axis grid integrates in cell-major order with a
  banded Jacobian (half-bandwidth `2 F - 1`), the same trajectory at a
  fraction of the cost (the plan's radial model: about 220 s to 4 s per 62 h
  solve); BDF and Radau receive a coloured finite-difference sparse Jacobian
  on the nearest-neighbour pattern with a fixed step, after scipy's adaptive
  estimator overflowed and failed on the clipped fields.
- `fungal_model.research.colony_comparison` and
  `scripts/run_de_ligne_2019_colony_comparison.py`: stage 0 of COLONY-001;
  plan loading with digest verification, observations under the row rules,
  the per-series error model (pooled below fifteen readable rows), the plan's
  `colony_reserve_v1` model built from a caller's parameter values on either
  geometry with the inoculum-only initial fields, the two observables, and
  `run_stage_0` recording error models, timing, grid, solver and symmetry
  checks that cite the plan digest; `check` recomputes the error models.
- Tests: `tests/test_mycelium_core.py` (annular cells and refusals; radial
  diffusion conserves and matches the planar Gaussian; area units),
  `tests/test_colony_comparison_stage0.py` (digest verification refuses a
  tampered dataset; observations follow the row rules; error models fit,
  floor and pool; the model builds on both geometries with the inoculum
  only; observables start at the disc; a reduced stage 0 records checks
  citing the plan),
  `tests/test_mycelium_colony.py` (radial colony against the two-dimensional
  colony on the window observables), `tests/test_colony_observation.py`
  (closed forms, counts, hull radius and area in both geometries),
  `tests/test_cardinal_response_laws.py` (the law's shape and refusals; the
  modifier reads the environment, folds into a constant kernel, builds from
  config and refuses a missing cardinal symbol).

Measured: the two-dimensional artificial colony on 80 x 80 cells of 0.125 mm
takes minutes per 10 h with LSODA's dense backend Jacobian, the radial colony
on 283 cells of 0.025 mm under half a minute; the plan's calibration grid is
the radial one.

What it is not: no fit, no data comparison, no organism parameter; the
water-activity law's exponent is the CTMI's and the equality of a surface
water activity with an equilibrium relative humidity is the plan's declared
assumption, not a measurement.

## COLONY-001 Frozen Plan For The De Ligne 2019 Colony Comparison

Status: `partial` (plan frozen 2026-10-06 and amended once the same day, before any check was recorded, to make the area operator's detection density a grid-independent constant; stage 0 core pieces built under SPATIAL-002, the runner and the recorded checks not; no fit run).

`data/benchmarks/de_ligne_2019_colony/plan.json` (SHA-256
`ea6e2e7270b809fee092655f7e6882cf266e16d86d955c276ba5e2edc5ad959e`, pinned by
`tests/test_colony_comparison_plan.py`) declares the within-study transfer test
of the continuum mycelium (SPATIAL-001) against DATA-003 before anything is
run: an axisymmetric geometry on the scan window with the inoculum disc, the
`colony_reserve_v1` model (tips, hyphae, internal reserve, inoculum reserve;
one environment activity per condition scaling extension and branching, every
other parameter shared; a two-activity comparison variant), the two
observation operators (tips outside the disc; the window-truncated disc of the
outermost detected hyphae as the convex-hull area), a per-series linear error
model fitted to the readable bars, the four held-out conditions (each
temperature and humidity level once), stages 0 to D, the decision rules and
the four-phrase outcome vocabulary, the excluded claims and the amendment rule.
`docs/colony-comparison.md` is the page. The feasibility run that sized the
plan (the artificial colony on a 40 x 40 mm Cartesian grid, 62 h) took about
three minutes per solve, so stage 0 starts with the axisymmetric grid.

Recommended next task: stage 0 (axisymmetric grid with the Cartesian agreement
check, observation operators, the cardinal water-activity law, the error-model
fit, the runner with `--check`, the measured budget), then stage A for
*C. puteana*.

## DATA-003 De Ligne 2019 Colony Growth Dataset Ingested From Figures

Status: `complete` for the stated scope (2026-10-06).

Scope: the colony-expansion target for the spatial mycelium core (SPATIAL-001).
De Ligne et al. 2019 (IMA Fungus 10:7, DOI `10.1186/s43008-019-0009-3`, CC BY
4.0) measured the mycelial area and the number of hyphal tips of *Coniophora
puteana* MUCL 11662 and *Rhizoctonia solani* AG4-HG-I S010-1 on an inert
Petri-dish surface, hourly for 62 h, under sixteen temperature-humidity
conditions, as the mean of four replicates with standard-deviation bars. The
data exist only as raster panels in additional files 2 to 5.

What exists:

- `data/experiments/source_intake/de_ligne_2019/`: the article and the five
  additional files downloaded by the owner, preserved with SHA-256 digests in
  `manifest.json`, plus `digitized_panels.csv`, the per-panel extraction table.
- `scripts/digitize_de_ligne_2019_figures.py`: verifies the digests, extracts
  the embedded panels, verifies the legend colour order, calibrates each axis
  from the equally spaced gridlines with the frame bottom as the verified
  y zero, classifies the four staggered series by hue, locates the disc
  markers with a background-penalised template so partly hidden discs still
  give their centre, reads each error bar through occluders and accepts an end
  only where its cap is visible, merges the two appearances of every condition
  (temperature panel and humidity panel) and checks three prose statements of
  the article before writing; `--check` reproduces the committed files.
- `data/experiments/literature/de_ligne_2019_colony_growth/`: four
  `literature_processed` datasets (species x quantity), sixteen condition
  series each, 3954 observations in total; every row stores both panel
  readings, their difference, the digitization resolution and a flag column
  with a glossary in the metadata.
- Tests: `tests/test_de_ligne_2019_dataset.py` (files, schema, loader,
  flags, bounded panel disagreement, panel coverage, the article's statements,
  the review record, manifest digests, documentation, and the extractor's
  reproduction when `pypdfium2` and Pillow are installed);
  `tests/test_literature_schema_contract.py` and
  `tests/test_dataset_candidate_review.py` updated.

What it is not: no model comparison, no observation operator from hyphal
density fields to scanned area or graph-derived tip count, no parameters, no
validation. The sixteen conditions of a species are one experiment; agreement
across them is within-study transfer. Standard deviations are empty where the
bar was hidden behind the marker or unreadable (flagged), and the small
panels of figures S3 to S5 leave many bars unreadable because the four series
are staggered by little more than a pixel.

Recommended next task: declare the observation operator and a frozen
calibrate-and-hold-out plan over the sixteen conditions, then run the
continuum model against one species.

## SPATIAL-001 A Continuum Mycelium On A Compiled Spatial Core

Date: 2026-10-06

Status: complete for the first slice of step 6 (exploratory). A fungus can
now occupy space in FungMod: `fungal_model.mycelium` compiles field
processes for hyphal growth on a uniform grid to numpy kernels, verified
against analytic and conservation results. Nothing in it is parameterised
for an organism; the owner decided to start step 6 before the transfer
test of step 5.3, and the module says so in its maturity label.

Changed:

- `mycelium/grid.py`: `SpatialGrid` (one to three axes, `no_flux` or
  `periodic` per axis, cell widths in metres, measures, coordinates).
- `mycelium/operators.py`: conservative finite-volume operators on plain
  arrays (face values and gradients, harmonic face mean, first-order upwind
  advective flux, divergence, diffusive tendency, drift face velocities,
  spatial integral).
- `mycelium/fields.py`: `FieldSpec`, `FieldKernelContext` (field slots and
  parameters converted once at compile time), the kernel types.
- `mycelium/processes.py`: the `FieldProcess` contract (fields read and
  changed, parameter requirements, assumptions, validity, failure modes,
  `compile_tendency`, optional `compile_rate`, `to_dict`).
- `mycelium/hyphae.py`: ten generic processes in the continuum forms of
  Edelstein (1982) and Boswell et al. (2003), each functional form declared
  as this implementation's choice with its limitations: `TipExtension`
  (hyphae gain `v n`; `v` constant or saturating in an internal substrate;
  an optional cost drawn only from that substrate, so it cannot overdraw),
  `TipMotion` (diffusion plus drift up or down a declared field, upwind),
  `LateralBranching` (`b rho` or `b rho s`), `DichotomousBranching`,
  `Anastomosis` (`-a n rho`), `FirstOrderLoss` (optionally into a product
  field), `LocalUptake` (linear or saturating), `Translocation` (diffusive
  plus an active term up the tip-density gradient), `LocalSecretion`
  (optionally saturating with a cost), `FieldDiffusion`;
  `continuum_process_types()`.
- `mycelium/model.py`: `MyceliumModel.compile` (refuses missing fields,
  incompatible units, missing parameters, negative rates and non-positive
  half-saturations), `CompiledMyceliumModel` (`rhs` at `max(field, 0)`,
  `rates`, nearest-neighbour sparsity for implicit methods other than
  LSODA, `simulate` through `solve_checked`), `MyceliumResult`
  (`spatial_integral`, `occupied_measure`, `front_position`,
  `results_summary` with maturity, assumptions and limitations),
  `total_amount` for conservation ledgers.
- `mycelium/benchmarks.py`: `artificial_colony_model` (two dimensions, all
  substrate-coupled processes) and `artificial_front_model` (the
  one-dimensional Edelstein system), round framework-benchmark values with
  `testing` confidence.
- `docs/spatial-mycelium.md` (new, in the navigation), `docs/api.md`,
  `docs/capabilities.md`, `docs/paper-readiness.md`, `docs/compiled-core.md`,
  `README.md`, `CHANGELOG.md`, `ARCHITECTURE_DEBT.md` (FD-009 narrowed),
  the state document (step 6 status).
- Tests: `tests/test_mycelium_core.py` (grid validation, operators against
  the transport Laplacian in two and three dimensions, upwind conservation
  and non-negativity, boundary faces, harmonic mean, process registry and
  declarations, refusals of partial or overdrawing options, compile-time
  checks, two unit systems against a closed form, every mechanism's
  tendency in its declared units, negative-field policy, result API);
  `tests/test_mycelium_colony.py` (pulled-front speed within 5 percent of
  `2 sqrt(D alpha)` approached from below, colony conservation to 1e-7,
  monotone expansion, symmetry to 1e-10, LSODA/BDF/RK45 agreement to 2e-4,
  right-hand-side time bound, translocation conservation and active
  transport towards tips).

Not changed: the 1D and N-D reaction-diffusion engines, every well-mixed
process, every registry record, every recorded study. Scientific impact:
none; no organism or substrate is claimed and the module is exploratory.
Backward compatibility: additive (a new package and docs page). Risk: low
for code; the scientific risk is misuse of artificial parameters as if
measured, which the maturity label, the `testing` confidence and the
scientific-mode refusal guard against.

Commands run (venv, Python 3.11): `ruff check src tests scripts/run_*.py
scripts/reproduce_paper.py`; `pyright` (whole package); `mkdocs build
--strict`; `pytest tests/test_mycelium_core.py tests/test_mycelium_colony.py`
(18 passed) with the reaction-diffusion, hygiene and guardrail modules;
results in the PR.

Measured: 0.4 ms per right-hand side at 50 x 50 cells and four fields; the
40 x 40 colony over 24 hours in 19 s with LSODA and 39 s with BDF on the
sparse pattern; the unit-aware engines took 66 ms per right-hand side at
200 cells.

Remaining ambiguities: the active translocation and tropism terms are
declared forms, not reproductions of any paper's equations; the extent of a
colony depends on a threshold the caller declares; the harmonic-mean gating
of translocation by hyphal density was tried and removed because it starves
the tip zone, which the docs record.

Recommended next task: a sparse compiled Jacobian for the spatial core so
that colony solves are fast enough for calibration; then, once the owner
supplies the De Ligne et al. 2019 time series and the Boswell 2003
parameter table, a registry-parameterised *R. solani* case under a frozen
plan comparing colony area and tip counts over time.

## CRIT-004 Amendment 4: The M2 Chain From The Converged Fit And Its Holdout Posteriors

Date: 2026-10-06

Status: complete. The criticism plan's fourth dated amendment (digest
`9897ab11...` to `7952e010...`) gives the soluble-product-pool chain the
length and the starting point its first run lacked and gives the plan's
holdout posteriors sampler settings and an output convention; both were run
and recorded. The scientific outcome for M2 does not change: it improves
the fit but its constants stay unidentified, and its chain still misses the
convergence rule.

Finding: the M2 all-condition chain re-run from the converged stage A fit
(28 walkers, 36000 steps, 8000 burn-in, 7.7 hours across five resumed runs)
does not converge by the declared rule. Its integrated autocorrelation times
grew to 824 to 1393 steps (first chain: 368 to 529) against 28000
post-burn-in steps, while every effective sample size (563 to 951) passes;
mean acceptance 0.194; 431 641 of 1 008 028 posterior evaluations (43
percent) failed to integrate and were rejected. The shared noise multiplier's
interval is [1.63, 2.23] (median 1.89): below the baseline's 2.25, still
excluding 1.0 (R2 fails). The added constants: `mu` bounded below only, `Ks`
and `Ki` prior dominated, `P0` bounded below only (R3 fails). The nine
common constants keep their BAYES-001 classes, which the first chain (yield
0.18 at its centre) had degraded. Coverage with measurement noise 91 of 96.
Outcome: improves fit but unidentified (R1, not R3), provisional.

Holdout posteriors (amendment 4, recorded 2026-10-06): three M2 chains of 8000 steps (2000 burn-in, 28 walkers) with one cellulose loading held out of the likelihood, each centred on the fold's stage A fit; held-out posterior predictive coverage at 95 percent with measurement noise (400 draws): 10 g/L held out 22/32, 69 percent (biomass 8/8, substrate 8/8, FPase 2/8, beta-glucosidase 4/8; multiplier [1.23, 1.78]; acceptance 0.214; largest tau 500 of 6000 post-burn-in steps); 20 g/L held out 32/32, 100 percent (biomass 8/8, substrate 8/8, FPase 8/8, beta-glucosidase 8/8; multiplier [1.87, 2.90]; acceptance 0.182; largest tau 565 of 6000 post-burn-in steps); 30 g/L held out 19/32, 59 percent (biomass 5/8, substrate 8/8, FPase 3/8, beta-glucosidase 3/8; multiplier [1.26, 1.86]; acceptance 0.203; largest tau 491 of 6000 post-burn-in steps). No fold converges by the declared rule; the added constants keep their one-sided or prior-dominated classes in every fold. Verdict unchanged: improves fit but unidentified, provisional.

Changed:

- `data/benchmarks/gelain_2020_criticism/plan.json`: amendment 4
  (`stage_B_posterior.sampler.model_overrides` for M2, `holdout_sampler`,
  the compute cap); `tests/test_gelain_criticism_plan.py` pins the new digest
  and the amendment chain, checks the override and the holdout settings and
  the internal consistency of every `holdout_<condition>/` folder (held-out
  condition recorded, fitted and held-out coverage kept apart).
- `calibration/bayesian.py`: the posterior predictive and the coverage take
  an explicit list of conditions that may include held-out ones and list
  them in the output. `research/gelain_criticism.py`: `sampler_settings`
  reads the per-model override and the holdout sampler; the study builder
  takes a held-out condition, trains on the others, centres on that fold's
  stage A fit, scores the held-out loading by coverage and records the
  fitted and held-out ids and both coverages apart; the runner script gains
  `--hold-out`.
- `results/stage_b/M2_soluble_product_pool/`: the chain re-recorded (the
  first chain's summary stays in CRIT-002 and CRIT-003);
  `holdout_gelain_2020_cellulose_{10,20,30}gl/` (new).
- `paper/tables/table_4_criticism_stage_b.{md,tex}` and both manifests
  regenerated (the plan digest with amendment 4 enters the figure manifest);
  `paper/paper.tex` (stage B paragraph and the limitations bullet);
  `docs/gelain-model-criticism.md` (amendment 4, the M2 chain, the holdout
  posteriors, the summary); the study README; `CHANGELOG.md`; the state
  document (item 2).
- Tests: `tests/test_bayesian_calibration.py` (toy held-out coverage lists
  the held-out condition and scores it apart), `tests/test_gelain_criticism_study.py`
  (the override and the holdout settings resolve from the plan; a tiny
  holdout study end to end records the held-out id and both coverages).
- `data/benchmarks/gelain_2020_petab/plan.json`: a second dated amendment
  (`cfb8c9a6...` to `11dfe158...`) re-pins the criticism plan's digest; the
  sections the PEtab study reads are unchanged, so it records
  `results_remain_valid` and the PEtab results stand.
  `tests/test_gelain_petab.py` pins the new digest and accepts a recorded
  result only under a digest that every later amendment declares still
  valid; the PEtab README and `docs/gelain-cross-solver.md` describe it.

Not changed: any rule, bound, prior, error model or threshold of the plan;
stage A; the M1 and M3 chains; BAYES-001; any registry record. Scientific
impact: the M2 verdict stays "improves fit but unidentified (R1, not R3)"
and provisional; the inadequacy factor it leaves is now 1.89 rather than
1.94; the holdout posteriors add the per-fold coverage the plan declared.
Backward compatibility: `posterior_predictive_coverage` and the study
builder gain optional arguments; recorded M2 files are replaced under the
amendment rule. Risk: low for code; the scientific finding is the point.

Commands run (venv, Python 3.11): `ruff check src tests scripts/run_*.py
scripts/reproduce_paper.py`; `pyright` (whole package); `mkdocs build
--strict`; `python scripts/reproduce_paper.py tables` and `check`;
`pytest` on the criticism, Bayesian, paper and hygiene modules; the M2
chain (5 resumed runs) and three holdout chains through
`scripts/run_gelain_2020_model_criticism.py stage-b`; results in the PR.

Remaining ambiguities: 43 percent of the M2 chain's proposals failed to
integrate; the sampler rejects them as non-finite, which is correct for the
posterior but slows mixing, and the failing region of the added constants is
not characterised. The M2 chain would need about 70000 post-burn-in steps
for the rule if the autocorrelation did not grow further.

Recommended next task: step 5 item 3, cross-study transfer, once the owner
verifies a second dataset; until then the paper's limitations name the
single dataset and the provisional M2 verdicts.

## PAPER-002 The Manuscript In LaTeX With Generated Table Fragments And PDF Figures

Date: 2026-10-06

Status: complete. The software paper is a LaTeX manuscript that includes
its tables and figures from generated files; the Markdown draft is replaced,
not kept in parallel, so there is one manuscript to edit.

Changed:

- `paper/paper.tex` (new, replaces `paper/paper.md`): the same text as the
  Markdown draft, converted (natbib author-year citations from
  `paper/paper.bib`, `\texttt` for identifiers, math for the tolerances
  and the ODE), with the five tables pulled in by `\input` from
  `paper/tables/*.tex` and the four figures by `\includegraphics` from
  `paper/figures/*.pdf`, each referenced by label in the text. The
  reproducibility section now says that the tables and figures are
  generated LaTeX fragments and PDFs and that the test suite fails when
  the manuscript stops including one. Draft-status note dated 2026-10-06.
- `research/paper_tables.py`: `latex_escape`, `latex_inline` (Markdown
  code spans become `\texttt`, underscores may break inside narrow
  columns), `PaperTable.latex_file_name` and `rendered_latex` (a `table`
  float with `\footnotesize`, `\tabcolsep` 4pt, the title as caption,
  the label `tab:<name>`, one full-width `tabularx` per pipe table whose
  columns with cells longer than 11 characters wrap with widths
  proportional to their content between a floor and a cap, and the notes
  as a paragraph); `write_tables` writes the `.tex` next to the `.md`,
  `check_tables` checks it, the manifest names it (`latex_file`).
  `MARKDOWN_MARKER`, `LATEX_MARKER`.
- `research/paper_figures.py`: `PaperFigure.pdf_file_name`, `render` with
  `fmt="pdf"` (creator marker, no creation or modification date),
  `write_figures` writes the PDF, `check_figures` requires it with the
  marker (`PDF_MARKER`, the module name, because PDF string literals
  escape the parentheses of the full generator string), the manifest names
  it (`pdf_file`).
- `paper/tables/*.tex` (new, five), `paper/figures/*.pdf` (new, four), both
  manifests regenerated.
- `Makefile`: `paper-pdf` (latexmk in `paper/`); `.gitignore`: the LaTeX
  build products; `scripts/reproduce_paper.py` help text;
  `docs/reproducing-the-paper.md` (manuscript, both table formats, both
  figure formats, a section on building the manuscript, CI wording);
  `CHANGELOG.md`; the state document (item 6).
- Tests: `tests/test_paper_tables.py` (regeneration byte-identical for the
  `.tex` too; the manuscript includes and references every table and does
  not mention the Markdown draft; `latex_inline` escapes every special
  character and sets code spans in typewriter; every LaTeX table is a
  captioned float with one `tabularx` per pipe table whose `hsize` factors
  sum to the X count; a tampered or missing `.tex` is reported; both
  formats carry their marker); `tests/test_paper_figures.py` (the PDF is
  regenerated with the marker and without dates; the manuscript includes
  and references every figure's PDF; a tampered or missing PDF is
  reported).

Not changed: any recorded result, table content, figure data or study; the
Markdown tables and SVG figures are still written and checked. Scientific
impact: none. Backward compatibility: the manifests gain one key per entry
(`latex_file`, `pdf_file`); `paper/paper.md` no longer exists.

Commands run (venv, Python 3.11, TeX Live 2023 with latexmk): `ruff check`
on the changed modules, tests and script: passed; `pyright` on them: 0
errors; `python scripts/reproduce_paper.py tables`; `make paper-pdf`
(latexmk): 13 pages, no overfull or underfull boxes after the column
weighting; `pytest tests/test_paper_tables.py tests/test_paper_figures.py`:
17 passed; the whole-package gates are reported in the PR.

Remaining ambiguities: the PDF and SVG bytes depend on the matplotlib
version and are compared for presence and marker only, like the SVG
before; the manuscript's narrative sentences are still not checked word by
word.

Recommended next task: finish the amendment 4 M2 chain and its holdout
posteriors, then refresh the tables, figures and the manuscript text that
depend on the M2 stage B verdict (the amendment-4 branch must merge this
one first, since it edits the manuscript).

## CORE-002 Compiled Jacobian From Per-Process Gradients

Date: 2026-10-05

Status: complete, opt-in. The FD-009 exit item "compiled models can supply
a Jacobian" is met without moving any recorded result.

Changed:

- `core/kernels.py`: `JacobianKernel`. `processes/base.py`:
  `Process.compile_jacobian(context)` returning the gradient of the rate
  kernel with respect to the numeric state vector, or `None`.
- `solvers/compiled.py`: `CompiledProcess.gradient` and `jacobian_kind`
  (`analytic` or `finite_difference`); `CompiledModel.jacobian(t, y)` sums
  stoichiometric column times gradient, evaluated at the projected state and
  masked by the projection's derivative; the finite-difference fallback
  perturbs only the states a process declares, one-sided at the
  non-negative boundary, relative step 1e-6; the kernel summary records
  `jacobian_kernels` and `analytic_jacobian_count`. A thermodynamically
  constrained or quantity-wrapped rate is always differentiated numerically.
- Analytic gradients: `FirstOrderDecayProcess`, `MassActionProcess`
  (reactants and catalysts by the product rule; an order below one at a zero
  state returns zero, documented), `HomogeneousMichaelisMentenProcess` (both
  forms), `ProportionalSynthesisProcess` (constitutive and induced),
  `ResourceLimitedGrowthProcess`, `ResourceLimitedMaintenanceProcess`,
  `CostedSecretionProcess` (the classes' one-sided derivatives at the
  capacity-equals-demand kink, through `ClosureConstants.capacity_gradient`
  and `budget_gradient`), `DilutionExchangeProcess`, `GasTransferProcess`.
- `core/numerics.py`: `SolverSettings.jacobian`
  (`finite_difference_by_backend`, the default, or `compiled`), validated,
  serialised only when set; `uses_jacobian`. `solvers/process_ode.py`: the
  implicit methods receive `compiled.jacobian` when asked and the run
  records `kernel["jacobian"] = "compiled_process_gradients"`.
- `docs/compiled-core.md` (new section), `ARCHITECTURE_DEBT.md` (FD-009
  exit item), `CHANGELOG.md`.
- Tests: `tests/test_compiled_jacobian.py` (new): the assembled matrix
  equals finite differences of the compiled right-hand side on every
  packaged config at the initial state and random perturbations; the simple
  laws and the closure report analytic kinds, modifier-wrapped and
  constrained processes finite differences; catalysed mass action with a
  fractional order; integration with the compiled Jacobian reproduces the
  backend-difference trajectory on the toy chemostat (BDF) and the
  `DegradingCulture` native analytic-Jacobian trajectory to 1e-7; explicit
  methods ignore the option; settings validation and serialisation; a
  process offering only a rate is differentiated numerically and recorded.

Not changed: any default, any recorded result, any rate law. Scientific
impact: none. Backward compatibility: additive (`SolverSettings` gains a
defaulted field; the kernel summary gains two keys). Risk: low.

Remaining ambiguities: making the compiled Jacobian the default for implicit
methods would move trajectories within solver tolerance and therefore the
recorded study artifacts; that is a decision for a dated re-run, not a
code default. Rate modifiers have no gradient hooks yet (finite differences
apply).

Recommended next task: finish the amendment 4 M2 chain; then decide whether
a future study plan declares `jacobian: compiled`.

## REPRO-002 The Paper's Figures From The Recorded Results

Date: 2026-10-05

Status: complete. The reproducibility package now regenerates the paper's
figures as well as its tables with one command.

Changed:

- `research/paper_figures.py` (new): `PaperFigure` (the plotted numbers, a
  draw callable, sources with digests, key numbers); builders for the
  whole-condition holdouts on the three cellulose loadings (published means
  against the frozen held-out predictions of the hydrolysis candidate and
  the re-fitted published equations, v2 primary scenario), the posterior
  predictive bands of BAYES-001 (median and 5 to 95 percent band per
  loading and observable with the published means), the stage A screen of
  the criticism study (change in pooled held-out error per observable and
  pooled, relative to M0, against the plan's thresholds, both scenarios)
  and the cross-solver objectives (recorded optimum, COPASI's local fit,
  ten random starts); `write_figures`, `check_figures`, `manifest_for`,
  `render` (SVG with the generator as creator and no date).
- `paper/figures/` (new): four SVGs, four data JSONs and `manifest.json`.
- `scripts/reproduce_paper.py`: `tables` writes the figures too
  (`--figures-directory`), `check` checks them; `Makefile` help text;
  `paper/paper.md` cites each figure next to its table;
  `docs/reproducing-the-paper.md`; `CHANGELOG.md`.
- `tests/test_paper_figures.py` (new): committed data and manifest match
  the recorded results; regeneration elsewhere is byte-identical for the
  data and the manifest and produces SVGs with the marker; manifest digests
  name the files on disk; every figure is cited by the paper; key numbers
  agree with the data; builders refuse missing results; a tampered data
  file or SVG is reported.

Not changed: any recorded result, table or study. The figures plot recorded
numbers; the measured points come from the reviewed literature datasets.
Scientific impact: none. Backward compatibility: additive. Risk: low.

Remaining ambiguities: SVG bytes are not compared across matplotlib
versions; the data files are the reproducible artifact.

Recommended next task: finish the amendment 4 M2 chain and its holdout
posteriors, then refresh the tables, figures and paper text that depend on
the M2 stage B verdict.

## CAL-002 Declared Finite-Difference Step In The Public Least-Squares API

Date: 2026-10-05

Status: complete. The follow-up recorded in CRIT-003: `fit_least_squares`
gains `diff_step`, `ftol`, `xtol` and `gtol` (default `None`, scipy's
values, so no existing calibration changes) with validation and the declared
values recorded in `optimizer_metadata` (`finite_difference_step`, the three
tolerances, `method`, and a note that undeclared options are scipy's
defaults). The docstring states why an adaptive integrator's step noise
needs a declared step. Tests: the declared options are passed and recorded,
the default path records `None`, and non-positive, non-finite or too-large
values refuse. No recorded result uses the public function with these
options; the model-criticism study keeps its own plan-declared settings.

## UNIFY-001 Culture Physiology As Generic Processes On The Compiled Core

Date: 2026-10-05

Status: complete for step 5 item 5. The closure and the chemostat exchanges
of `ResourceLimitedCulture` and `DegradingCulture` are generic, registrable
processes with numeric kernels; `FungalCouplingModel` composes existing
generic processes; all three classes integrate on the compiled core with
parity against their native right-hand sides, which they keep (an analytic
Jacobian for the two Pirt/Monod classes; `Reaction` objects with Python rate
laws for the coupling model's legacy path).

Changed:

- `processes/culture.py` (new): `ResourceLimitedGrowthProcess`
  (`(1-f) Y max(capacity-m, 0) N/(K_N+N) X`), `ResourceLimitedMaintenanceProcess`
  (`min(m, capacity) X`), `CostedSecretionProcess`
  (`f max(capacity-m, 0) N/(K_N+N) y X`) with `capacity = q S/(K_S+S) O/(K_O+O)`,
  explicit `stoichiometry` (formula units per unit extent) and an optional
  extent ledger; `DilutionExchangeProcess` (`D (c_feed - c)`) and
  `GasTransferProcess` (`k_La (c_sat - c)`) with an optional boundary ledger.
  Every process has a unit-aware `rate`, a numeric `compile_rate`, linear
  `contributions`, assumptions, validity labels and failure modes; half-
  saturations must be positive, fractions in [0, 1], pools non-negative.
- `processes/factories.py`: five factories reading `states`, `parameters`
  and `stoichiometry` from config, reporting missing fields and unit
  mismatches; registered in `default_foundation_factories` (13 types).
  `io/model_config.py`: `ProcessConfig.stoichiometry` (serialized only when
  present, so existing configs round-trip unchanged).
- `data/model_configs/toy_resource_limited_chemostat.yml` (new): the five
  types on abstract pools (resource, cells, nutrient, acceptor, product) in
  millimolar and hours, picked up by the compiled-core parity and
  shipped-kernel tests like every packaged config.
- `fungi/respiration.py`, `fungi/degradation.py`: `compiled_processes()`,
  `compiled_parameters()` (the classes' own `Parameter` objects, the
  secretion yield of the solved pathway and one `feed:<pool>` parameter per
  pool; a symbol used twice refuses), `simulate_compiled()`; `simulate`
  refactored into integration and trajectory construction so both paths
  share the ledger, conservation residual and diagnostics code; trajectory
  diagnostics gain `engine` (`native_right_hand_side` or
  `compiled_process_core`) and, for the compiled path, the kernel summary.
  Hydrolysis maps to enzyme-explicit `HomogeneousMichaelisMentenProcess`,
  inactivation to `MassActionProcess`; both carry their extent ledger as a
  product with coefficient one.
- `processes/homogeneous.py`: `MassActionProcess(catalysts=...)`, species
  that enter the rate law with an order but are not consumed (a catalyst may
  also be a product; never a reactant); the factory reads
  `states.catalysts`; `standards/sbml.py` lists catalysts as modifiers and
  includes them in the kinetic law and its unit conversion.
- `fungi/coupling.py`: `compiled_processes(degradation)` (secretion as
  `proportional_synthesis`, decay as `first_order_decay`, the secretion cost
  and maintenance as first-order `mass_action` conversions of active into
  inactive biomass, uptake as `mass_action` in the product catalysed by
  active biomass with the declared yield; the degradation is supplied as
  processes because `Reaction` rate laws are Python callables),
  `compiled_parameters()` (the union plus the derived `alpha_E_c_E` with the
  weaker confidence of its two inputs and both sources), `simulate_compiled()`.
- `ARCHITECTURE_DEBT.md` (FD-009 narrowed), `docs/compiled-core.md`,
  `docs/degrading-culture.md`, `docs/respiration-benchmark.md`,
  `docs/organism-physiology.md`, `CHANGELOG.md`, the state document (item 5).
- Tests: `tests/test_coupling_compiled.py` (new; catalysed mass action:
  rate, contributions, kernel in another unit system, autocatalysis allowed
  and catalytic reactants refused, analytic solution, factory config, SBML
  modifiers with a cross-engine trajectory check; the coupling model's
  compiled path against the legacy engine with non-zero secretion cost and
  maintenance, its refusals, and the zero-cost benchmark);
  `tests/test_culture_processes.py` (new; kernels equal unit-aware
  rates on abstract pools in two unit systems, shared post-maintenance
  budget, analytic mixed steady state of the exchanges, refusals, factories
  from config and their missing-field reports, the packaged config through
  the configured workflow, native-versus-compiled parity for both classes in
  batch and chemostat operation and for the alternative chemistry at 1e-6
  relative (macOS differed from Linux by 1.6e-7 on one cumulative-exchange
  element at 1e-7), duplicate symbols refuse);
  `tests/test_process_factory_library.py` and
  `tests/test_compiled_process_models.py` expect the five new types.

Not changed: any rate law, constant, recorded result or the native
`simulate` trajectories (the existing 83 culture tests pass unchanged apart
from the added diagnostics key). No organism record binds the new processes;
the registry template families are untouched.

Scientific impact: none on recorded results; the closure now has one
implementation usable by configs, the registry and the classes. Backward
compatibility: additive (`ProcessConfig` gains an optional field; trajectory
diagnostics gain keys). Risk: low.

Remaining ambiguities: the compiled core has no analytic Jacobian, so the
two Pirt/Monod classes keep their native path for stiff methods; the
coupling model's legacy `reactions()` path stays for caller-supplied
`Reaction` laws until the legacy engine is retired.

Recommended next task: a Jacobian for compiled models (process kernels
supplying partial derivatives, finite differences otherwise, recorded in the
kernel summary), after which the classes' native paths can go; then the
first organism record that parameterizes the closure.

## REPRO-001 Reproducibility Package For The Software Paper

Date: 2026-10-05

Status: complete for the tooling half of step 5 item 6. The paper's five
tables are generated from the recorded study results by one command with a
digest manifest; the same command offers tiers of reproduction up to a full
re-run; the runtime closure is pinned and CI installs the built wheel with
network access disabled. The tagged release with a DOI, the domain review
and an independent walkthrough remain open and need people.

Changed:

- `research/paper_tables.py` (new): one builder per table (joint holdouts
  of v2, BAYES-001 identifiability, criticism stage A, criticism stage B,
  cross-solver), each returning the Markdown, its source files with SHA-256
  digests and the key numbers the text quotes; `write_tables`,
  `check_tables` (committed tables and manifest against the recorded
  results and the sources' digests); `verify_recorded_results` (digest
  chains of every study against its plan and amendment log, frozen held-out
  predictions, stage B artifacts, the cross-solver plan's sources, the
  compiled-core objective at the recorded cross-solver optimum to 1e-7, the
  projected gradient of the recorded baseline fit below 1e-2 in log space);
  `projected_gradient_norm`.
- `paper/tables/` (new): the five tables and `manifest.json`, generated, with
  a do-not-edit marker on each.
- `scripts/reproduce_paper.py` (new): tiers `tables`, `check`, `verify`
  (seconds to a minute), `stage-a` (re-run stage A and the COPASI
  reproduction into `outputs/paper_reproduction/`, compare held-out errors to
  1e-6, screens, outcome and objectives; about two hours) and `full` (every
  study through its own script, compared on verdict-level fields; a day).
- `Makefile`: `paper-tables`, `paper-check`, `paper-verify`,
  `paper-stage-a`, `paper-full`, `wheelhouse`, `install-offline`;
  `.github/workflows/ci.yml` package job downloads the pinned closure into a
  wheelhouse and installs the wheel with `--no-index`; `.gitignore` ignores
  `wheelhouse/`.
- `paper/paper.md`: every results section cites its table; the
  reproducibility section describes the command, its tiers and the offline
  install, and leaves the DOI pending.
- `docs/reproducing-the-paper.md` (new, in the navigation),
  `docs/paper-readiness.md` (item 6 status), `CHANGELOG.md`, the state
  document (item 6 status).
- `tests/test_paper_tables.py` (new): committed tables and manifest match
  the recorded results; regeneration elsewhere is byte-identical; manifest
  digests name the files on disk; every table is cited by the paper; key
  numbers agree with the tables; missing results refuse; a tampered table is
  reported; the generator marker is present.

Not changed: any recorded result, plan, rate law or constant. The tables
format recorded numbers; the verification recomputes two quantities from
recorded artifacts and otherwise checks digests.

Commands: `ruff check` passed; `pyright` 0 errors on the new module and
script; `mkdocs build --strict` passed; `pytest tests/test_paper_tables.py
tests/test_repository_hygiene.py tests/test_quality_config.py
tests/test_release_configuration.py`: 24 passed; `scripts/reproduce_paper.py
verify`: 9 of 9 checks passed in 2 s on this container. The `stage-a` and
`full` tiers were not run here (they re-run studies recorded in CRIT-003
and earlier on the same code); the offline wheel install runs in CI.
Scientific impact: none. Backward compatibility: additive. Risk: low.

Remaining ambiguities: the lock file was generated on CPython 3.13 macOS;
`pip download` on the CI interpreter resolves the pinned versions to that
platform's wheels, so the offline install proves installability from a
pinned closure, not bit-for-bit identity across platforms.

Recommended next task: step 5 item 5 (unify the three whole-fungus classes)
while the amendment 4 M2 chain runs; then the preprint's figures through the
same generator.

## CRIT-003 Stage A Optimiser Declared, Stage A Re-Run, Cross-Solver Outcome Reproduced

Date: 2026-10-05

Status: complete. The model-criticism plan's stage A optimiser was stopping
above the minimum; amendment 3 (digest `9897ab11...`) declares the settings
that were missing, stage A was re-run for every model and scenario under it,
the PEtab cross-solver plan was amended (digest `cfb8c9a6...`) to the new
reference fit and its reproduction re-run with outcome `reproduced`, and the
recorded stage B verdicts were refreshed against the new screen. The
scientific verdict for the soluble product pool (M2) changes from "not
supported (fails R1)" to "improves fit but unidentified (R1, not R3)".

Finding (from PETAB-001): COPASI reached an objective 1.3 percent below
FungMod's recorded M0 optimum and FungMod evaluated that point to the same
value. Diagnosis on M0 before any variant was refitted: every recorded start
had stopped on scipy's step tolerance (status 3) after 20 to 60 evaluations,
not on the 250-evaluation cap; the cost gradient at the recorded point was
0.18 along `qF` and 0.09 along `k_h` in log space (not stationary); with
scipy's default difference step (about 1.5e-8) the residual-derivative
norms for `K_ind` and `kB` were fifteen times their converged values (3.77
against 0.24, 2.5e-3 against 1.6e-4) because the differences were
dominated by the adaptive ODE integrator's step noise, so the trust region
collapsed; tightening ftol, xtol and gtol alone (1e-10, 1e-12, xtol off)
changed nothing. A log-space difference step of 1e-3, which the v2 plan had
declared and this plan omitted, took the midpoint start to cost 1.98804,
below COPASI's 1.98841, with restarts no longer improving it.

Changed:

- `data/benchmarks/gelain_2020_criticism/plan.json`: amendment 3 adds
  `stage_A_least_squares.optimiser` (method unchanged; log-space difference
  step 1e-3; ftol, xtol, gtol 1e-10; up to three restarts of the best start
  until the relative cost decrease is below 1e-6) with the diagnosis and the
  consequences in its reason. No rule, bound, model or other setting changed.
- `research/gelain_criticism.py`: `OptimiserSettings` (read from the plan,
  every field required), `fit_model(..., optimiser=...)` passes the step and
  tolerances to scipy, restarts the best start from its own solution and
  records every start and restart; `run_stage_a` records the settings in
  `inputs.json` and the report; `profile_model` takes the same settings;
  `refresh_stage_b_verdicts` recomputes a recorded posterior's verdicts
  against the stage A comparison on disk, rewrites `verdicts.json`, the
  decision-rule block of `report.md` and the digests of those two files;
  `scripts/run_gelain_2020_model_criticism.py refresh-verdicts`.
- `data/benchmarks/gelain_2020_petab/plan.json`: one dated amendment replaces
  the criticism-plan and reference-fit digests (new reference cost
  1.9880359493158402, objective 3.9760718986316803); gates, settings and
  outcomes unchanged.
- Results replaced: `gelain_2020_criticism/results/stage_a/` (every model and
  scenario, with M2's profiles) and `gelain_2020_petab/results/`. Stage B
  folders: `verdicts.json`, the decision-rule lines of `report.md` and the
  two digests in `artifacts.json` for M2 (R1 now true); M1 and M3 unchanged.
- `standards/copasi.py` (merged from the PEtab branch): the COPASI import
  helper restores `LC_CTYPE`, because COPASI's static initialiser resets the
  C locale and switched Python's text encoding to ASCII for the rest of a
  test session.
- Tests: `tests/test_gelain_criticism_plan.py` (new digest and amendment
  tuple, the optimiser block, recorded stage A files carry the declared
  settings and restarts, stage B verdicts' R1 equals the stage A screen on
  disk, the refresh helper on a copied folder); `tests/test_gelain_criticism_study.py`
  (`OptimiserSettings` refusals, settings recorded in the tiny stage A run,
  the recorded M0 primary fit is stationary: projected cost gradient norm in
  log space below 1e-2); `tests/test_gelain_petab.py` (new digest, the
  amendment, a cross-platform tolerance of 1e-7 on the objective check).
- `docs/gelain-model-criticism.md`, `docs/gelain-cross-solver.md`, both
  benchmark READMEs, `CHANGELOG.md`, the state document (items 2 and 4),
  `paper/paper.md` (criticism, cross-solver and limitation paragraphs).

Not changed: any rate law, registry record, bound, prior, error model or
decision rule; BAYES-001 and the v2 results; the stage B chains and their
samples, summaries and coverage.

Stage A under amendment 3 (`results/stage_a/`, five starts, 250
evaluations, every fit full rank, every all-condition start at the same cost
except two of M2's five in local minima):

| Model | Scenario | Held-out MSE | vs M0 | Screen |
| --- | --- | --- | --- | --- |
| M0 | primary | 0.0918 | | reference |
| M0 | correlated | 0.0932 | | reference |
| M1 | primary | 0.0917 | +0.1% | failed (substrate +210%) |
| M1 | correlated | 0.0961 | -3.0% | failed (substrate +312%) |
| M2 | primary | 0.0703 | +23.4% | passed (every observable better) |
| M2 | correlated | 0.0689 | +26.1% | passed (every observable better) |
| M3 | primary | 0.0920 | -0.2% | failed (no improvement) |
| M3 | correlated | 0.0979 | -5.0% | failed (substrate +12%) |

The first run (CRIT-001, digest `9bb36f8d...`) had M0 0.0907, M1 0.0882
(+2.7%), M2 0.0695 (+23.4% with biomass 31% worse) and M3 0.0979; its M2
verdict rested on the biomass clause, which the converged fit does not
trigger (biomass 25% better). M2's all-condition fit: cost 1.414 against
M0's 1.988; `Y` 0.46, `kd` 0.025/h, `mu` 0.23/h, `Ks` 0.0016 g/L, `Ki` 47
g/L, `P0` on its 3 g/L upper bound, `K_ind`, `kF`, `kB` on their lower
bounds. Profiles for M2 (`profiles_primary.json`, nuisance-reoptimised cost at the fitted value times 0.5, 1 and 2; reference 1.4135): `Y`, `qF`, `qB`, `kd` and the lower half of `mu` and `P0` raise the cost clearly (1.50 to 1.85), `k_h` and `Kh` mildly (1.43 to 1.45), while `Ks`, `Ki`, `kF`, `kB` and `K_ind` are flat (within 1e-3 of the reference at both factors), which agrees with the stage B classes for the pool's constants; several nuisance refits reached 1.4132, 2e-4 below the reference, so the all-condition fit sits in a valley where the declared restart tolerance of 1e-6 stops earlier than the warm-started profile refits do, and that is reported rather than smoothed over.

Cross-solver reproduction re-run (`gelain_2020_petab/results/`, plan
`cfb8c9a6...`): simulation agreement 1.6e-8 of sigma, objectives within
2e-8; COPASI's local fit 3.976071799 against FungMod's 3.976071899
(relative difference 2.5e-8, gate 1e-3); every parameter within 1e-4
relative; best random start 3.9768, none below the local fit. Outcome
`reproduced`.

Stage B refresh (`refresh-verdicts`): M2 R1 true, outcome "improves fit but
unidentified (R1, not R3)" (R2 and R3 unchanged: multiplier [1.65, 2.87];
`mu`, `Ks`, `Ki` prior dominated, `P0` bounded below only); M1 and M3 R1
false, outcomes unchanged. The chains were not re-run: their initial centre
is a starting point rather than a result, they are already reported as
unconverged and provisional, and M2's chain started from the superseded
fit, which is stated in the docs and the paper.

Commands: `ruff check src tests scripts/run_*.py` passed; `pyright` 0
errors; `mkdocs build --strict` passed; stage A re-run (M0 8 min, M1 and
M3 about 13 min each, M2 70 min plus profiles); COPASI reproduction 72 s;
criticism, PEtab, COPASI and culture-benchmark tests (see the PR for
counts); full `pytest` on the PR head reported in the PR. Scientific
impact: the M2 verdict changes as stated; nothing is promoted beyond
retrospective fit; the stage A optimum of the baseline is now stationary
and reproduced by an independent solver. Backward compatibility:
`fit_model` and `profile_model` require `optimiser`; fit files gain
`optimiser` and `restarts`; `inputs.json` gains `optimiser`. Risk: low for
code; the scientific finding is the point.

Remaining ambiguities: the M2 posterior was sampled from the superseded
centre and did not converge; the public `fit_least_squares` API still uses
scipy's default difference step (follow-up).

Recommended next task: a dated amendment 4 for an M2 stage B chain centred
on the converged fit, with a compute budget above the two-hour cap, so that
R3 for the one mechanism that passes R1 rests on a chain that started where
the holdouts point.

## PETAB-001 Cross-Solver Reproduction Of The Gelain Fit Through PEtab And COPASI

Date: 2026-10-05

Status: complete for step 5 item 4 of the software-paper plan. The registry
hydrolysis candidate (`M0_baseline` of CRIT-001) is exported as a
three-condition PEtab problem and reproduced in COPASI under a frozen plan.
Outcome in the plan's vocabulary: `copasi_improves`.

Changed:

- `standards/sbml.py`: exports `proportional_synthesis` (a source reaction
  with the producer and inducer as modifiers); writes product coefficients
  bound to a parameter as separate reactions whose kinetic law multiplies the
  rate by the parameter or its complement, refusing a coefficient that
  disagrees with the parameter's value; writes assay-activity base units
  (`core.units.ASSAY_BASE_UNITS`) as named dimensionless unit definitions and
  lists them in the model notes; `to_sbml(names_as_ids=True)`.
- `processes/surface.py`: `CoefficientBinding` and
  `ProductReleaseMap.coefficient_bindings`; `io/registries.py` loads them;
  `screening/culture_physiology.py` records them for every product-map
  coefficient derived from a parameter role (`coefficient_bindings` next to
  `coefficient_provenance`); `HomogeneousMichaelisMentenProcess` carries
  `product_coefficient_bindings` and the factory passes them. Descriptive
  only: every simulation still uses the numeric coefficients.
- `standards/petab.py`: `conditions_to_petab` with `PetabCondition`,
  `PetabObservable` and `PetabParameter`: one shared SBML model (structure
  compared with values zeroed), condition columns for species and parameters
  whose values differ, constant noise scales in `noiseFormula` and per-row
  `noiseParameters` otherwise, bounds and nominal values on the linear scale.
- `standards/copasi.py` (new, optional extra `copasi`): converts with COPASI's
  PEtab importer in a fresh interpreter (libSBML's SWIG proxies clash with
  libsedml's in one process), checks that every fit item addresses a model
  value, rewrites the dependent-column weights from the importer's `sigma` to
  `1/sigma^2` with per-experiment normalisation off, sets LSODA to relative
  1e-9 and absolute 1e-12, simulates every condition, fits from the nominal
  values and from log-uniform seeded starts, and re-evaluates every optimum on
  the PEtab objective from COPASI time courses.
- `research/gelain_petab.py`, `scripts/run_gelain_2020_petab_reproduction.py`,
  `data/benchmarks/gelain_2020_petab/` (plan, README, results),
  `docs/gelain-cross-solver.md`, nav, `docs/standards.md`, capability map,
  README, `CHANGELOG.md`; `pyproject.toml` extra `copasi`, installed by CI.
- `research/gelain_criticism.py`: variant product maps declare their own
  coefficient bindings (M2's uptake map binds the yield; the hydrolysis map
  has none) instead of inheriting the template's. No numerical change.

Not changed: every rate law, parameter value, registry record, prior, error
model, stage A and stage B result of CRIT-001, BAYES-001 and earlier; the
existing single-condition PEtab export; the reference simulator.

Plan: `data/benchmarks/gelain_2020_petab/plan.json`, SHA-256
`a0f8abe9561ad1936a2ef06055cd7af8a04cf4902008790d0a14c3cb58f3184a`, frozen
2026-10-05 before any COPASI run and pinned by `tests/test_gelain_petab.py`.
Sources and digests: criticism plan `6849c8b3...`, Bayesian plan
`9574fccc...`, observations `cc8cda93...`, reference fit (stage A M0 primary)
`7877ba47...`. Gates: simulation agreement (max abs difference / sigma 1e-4,
objective 1e-5); optimum agreement (objective 1e-3). Parameter differences
reported, not gated. One extra reported quantity was added after the first
run and is not a gate: FungMod's objective at COPASI's best point.

Results (recorded 2026-10-05, `results/comparison.json`, `results/report.md`;
COPASI 4.48.309, basico 0.87, importer 1.0.9):

- FungMod's objective on the exported problem at the nominal values is
  4.030662656, twice the recorded stage A cost (relative difference below
  1e-9): the PEtab problem is the stage A primary problem.
- Simulation at FungMod's optimum: worst |COPASI - FungMod| / sigma 1.7e-8
  over the 96 measurements; objectives 4.030662654 and 4.030662656 (relative
  difference 5e-10). Gate passed.
- Optimum: COPASI's local Levenberg-Marquardt fit from FungMod's optimum
  reaches 3.9803 (13 991 evaluations); ten random starts reach 3.9768 to
  4.0800, best 3.9768 (start 2). FungMod's recorded optimum 4.0307 is 1.3
  percent higher, above the 0.1 percent tolerance: outcome `copasi_improves`.
- Cross-check: FungMod's compiled core evaluates COPASI's best point to
  3.97682321 against COPASI's 3.97682324 (7e-9). The solvers agree; the stage
  A optimiser (scipy `least_squares` in log space, five starts, default
  tolerances, 30 evaluations) stopped early. COPASI's optimum sits on the
  lower bounds of `K_ind`, `kF` and `kB` and moves along the `k_h`/`Kh`
  direction stage A and BAYES-001 flagged as weakly determined (`k_h` 0.0127
  to 0.0180, `Kh` 10.5 to 16.3, `Y` 0.372 to 0.406).

Tests added: `tests/test_standards_sbml.py` (synthesis export and reference
check, bound coefficients stay symbolic and respond to the parameter, refusal
of inconsistent bindings, assay units as named dimensionless definitions,
`names_as_ids`); `tests/test_standards_petab.py` (multi-condition export:
condition columns, noise forms, unmeasured values, structural mismatch,
validation, condition-specific parameters); `tests/test_standards_copasi.py`
(toy two-condition problem: COPASI recovers the generating parameter, the
objective agrees with FungMod and a closed form, weights rewritten, reader
refusals); `tests/test_gelain_petab.py` (plan digest, sources, exported
problem versus the plan and lint, FungMod objective equals the stage A
objective, recorded results consistent with the gates, COPASI reproduction
from the nominal values).

Commands run (venv, Python 3.11): `ruff check src tests scripts/run_*.py`
passed; `pyright` 0 errors; `mkdocs build --strict` passed; the affected test
modules passed (see the PR for counts); the full suite result is in the PR.
`python scripts/run_gelain_2020_petab_reproduction.py` (82 s) wrote the
results above.

Scientific impact: a cross-solver reproduction of one fit, and a finding that
FungMod's stage A optimiser stops above the minimum on this problem. No
verdict of CRIT-001 or BAYES-001 changes by itself: stage A compares models
fitted with the same optimiser and BAYES-001 samples the posterior. Backward
compatibility: `ProductReleaseMap` and `HomogeneousMichaelisMentenProcess`
gain optional fields with empty defaults; registry-case configs gain a
`coefficient_bindings` key on product maps; the SBML exporter accepts one more
process type and no longer refuses assay units.

Risk: low to moderate. The weight correction depends on COPASI's semantics as
measured here (objective = sum of weight x squared residual, weight read from
the column scale) and is tested on the toy problem against a closed form.

Recommended next task: tighten the stage A optimiser (finishing step with
tight `ftol`/`xtol`/`gtol`, more starts, or a bounded Levenberg-Marquardt
finish) under a dated amendment of the criticism plan, re-run stage A and
check whether any R1 verdict changes; then resume stage B (M2 chain, then M1
and M3) and record identifiability and coverage.

Addendum 2026-10-05 (hosted CI on the recorded head): importing COPASI
resets the C locale to `C`, which switched Python's preferred text encoding to
ASCII for the rest of the test session and failed the culture-benchmark docs
check on Linux and macOS once the `copasi` extra was installed; the import
helper now restores `LC_CTYPE`, the COPASI test modules skip through it, a
regression test runs in a fresh interpreter, and the docs read names UTF-8.
The FungMod-objective check tolerates platform floating-point differences
(relative 1e-7; macOS differed from Linux by 1e-8). No scientific or numerical
behaviour changed.

## CRIT-001 Gelain Model-Criticism Study: Plan Frozen

Date: 2026-10-05

Status: plan frozen and the study machinery implemented and tested; no fit,
sample or score has been recorded under it yet. This is step 5 item 2 of the
software-paper plan.
Development fits during implementation (tiny-budget tests, one timing fit per
model) were not recorded and inform no decision.

Changed:

- `data/benchmarks/gelain_2020_criticism/plan.json` (SHA-256
  `9bb36f8d53d8dad66fd53beda9239ac1b1984c028018ff885ac44d9620921c4e`): four models
  (M0 registry baseline; M1 induction state; M2 soluble product pool with
  Monod uptake, product inhibition and an explicit unmeasured initial soluble
  carbon; M3 conversion-dependent accessibility after Kadam 2004), every
  parameter with bounds, units and role, the shared assumed error model with
  one sampled noise multiplier, stage A least-squares whole-condition holdouts
  with the v2 complexity screen and profiles, stage B posterior sampling with
  the BAYES-001 identifiability thresholds and posterior predictive coverage,
  decision rules R1 to R4, a four-word outcome vocabulary, excluded claims and
  an amendment rule.
  Amendment 2 (same day, after stage A was recorded and before any chain ran):
  the walker rule of at least two walkers per sampled dimension, so M2 samples
  with 28 walkers; previous digest `9bb36f8d53d8dad66fd53beda9239ac1b1984c028018ff885ac44d9620921c4e`.
  Amendment 1 (same day, before any run): machine-readable error-model fields
  and config symbols; previous digest `8b368ac8d6b683f688907c0bb38d4b5a3d2730d29a7b8ca4c37d92db1e187c7e`.
- `data/benchmarks/gelain_2020_criticism/README.md`: what the plan is and is
  not, and what each model needs before it can run.
- `tests/test_gelain_criticism_plan.py`: pins the digest, the data digests,
  the parameter counts (9, 10, 13, 10), positivity of every bound, the
  flagging of every added parameter, the decision rules and the claim
  boundaries, and that no results directory exists yet.

- `src/fungal_model/research/gelain_criticism.py` (later the same day):
  composes the four variants from the registry base configuration for each
  loading (M1 adds an induced pool through proportional synthesis and
  first-order loss; M2 adds a soluble product state, a second enzyme-explicit
  Michaelis-Menten uptake process with the yield product map, the
  product-inhibition modifier and an explicit initial pool; M3 adds the
  reactivity modifier to hydrolysis), runs stage A (multi-start log-space
  least squares on training loadings only, frozen held-out predictions that
  cite the plan digest, the v2 screen against M0, profiles) and stage B
  (priors from the plan's bounds, the shared noise multiplier, checkpointed
  ensemble sampling, identifiability, posterior predictive bands and
  coverage). `scripts/run_gelain_2020_model_criticism.py` drives both stages.
- `src/fungal_model/modifiers/reactivity.py`: generic `substrate_reactivity`
  rate modifier, rate times `(S / S_ref)^n` with provenance to Kadam, Rydholm
  and McMillan (2004); config builder in `processes/rate_modifiers.py` and
  factory registration; the factor is zero at or below zero substrate.
- `src/fungal_model/calibration/bayesian.py`: `posterior_predictive_coverage`.
- `docs/gelain-model-criticism.md` and the changelog.

Not changed: every model, registry record, benchmark result and frozen
artifact; the registry case itself (variants are composed at run time and
run in exploratory mode with the study as the source of every added value).

Tests: five plan-contract tests; `tests/test_substrate_reactivity_modifier.py`
(analytic activity, invalid constants, config builder errors, compiled kernel
against the analytic solution of a non-cellulose toy process);
`tests/test_gelain_criticism_study.py` (plan to variant mapping, M0 parity
with the Bayesian study predictor at the frozen fit, every variant integrates
and closes its declared mass balance, the variant configs declare their
additions honestly, scoring statistics, fit-model error paths, a tiny stage A
end to end with digest-cited frozen predictions);
`test_posterior_predictive_coverage_tracks_the_error_model` in
`tests/test_bayesian_calibration.py`. Commands: `pytest
tests/test_gelain_criticism_plan.py tests/test_repository_hygiene.py
tests/test_quality_config.py` (see the PR for the result).

Scientific impact: none yet; the plan commits the study to its decision rules
before data are touched. Backward compatibility: unaffected.

Ambiguities: M2's initial soluble carbon `P0` is an explicit unknown standing
in for inoculum and medium carry-over that the deposit does not measure; M3
needs a new generic modifier before it can run; stage B holdout posteriors are
capped by compute and may be reported as not run. Risk: low.

Results (stage A, recorded 2026-10-05, plan digest `9bb36f8d53d8...`):

- Mean normalized held-out MSE, primary scenario: M0 0.0907, M1 0.0882
  (+2.7 percent, substrate 13 percent worse), M2 0.0695 (+23.4 percent, biomass
  31 percent worse), M3 0.0979 (-7.9 percent, both activities worse). Every fit
  had full practical rank.
- Verdicts under the preregistered rules: M1 not supported; M2 not supported
  under R1 (fails only the per-observable clause: it fits substrate and both
  activities clearly better by giving up biomass, removing biomass loss,
  lowering the yield to 0.18 and pushing the unmeasured initial soluble pool to
  2.9 g/L near its declared ceiling); M3 not supported. The biomass/cellulose
  tension of BAYES-001 is not resolved by any of the three additions; it moves.
- No profiles were run because no model passed the screen. Stage B
  all-condition posteriors for the three additions follow; M0 reuses BAYES-001.

Next task: finish stage B within the compute cap, record identifiability and
coverage for each addition, and carry the verdicts into the paper plan.

## CRIT-002 Gelain Model-Criticism Study: Stage B Posteriors Recorded

Date: 2026-10-05

Status: complete for stage B under the plan's compute cap. The M2, M1 and
M3 all-condition posteriors are recorded under the frozen plan (digest
`6849c8b3...`); M0 reuses BAYES-001. None of the three chains meets the
convergence rule at the planned length, so every stage B verdict is
provisional as the plan requires. Two code defects found while recording
are fixed and tested. Step 5 item 2's gate (frozen plan, per-mechanism
identifiability table, failed candidates reported) is met with that
provisional label.

Changed:

- `research/gelain_criticism.py`: the variant config factory merges the
  variant's fixed constants into every candidate, so the posterior sampler
  (which supplies only the fitted symbols) no longer drops M1's `k_z` and
  start every walker at a non-finite posterior; `stage_b_verdicts` applies
  R2 (multiplier interval contains 1.0) and R3 (every added parameter
  identified or weakly identified) and combines them with the recorded stage
  A screen into the plan's outcome vocabulary, labelled provisional when the
  chain missed the convergence rule; `render_stage_b_report` reads the
  recorded summary and identifiability fields (it crashed on M2's first
  completion) and prints tau, bound contacts, the multiplier interval, the
  rules and coverage; `write_posterior_outputs` adds `verdicts.json` to the
  digested artifacts.
- `tests/test_gelain_criticism_study.py`: posterior studies of M1 and M3 are
  finite at a candidate (M1 has the fixed constant); the verdict helper
  follows the rules on synthetic results. `tests/test_gelain_criticism_plan.py`:
  every recorded stage B folder cites the plan chain, labels unconverged
  chains provisional, uses the outcome vocabulary and matches its digests.
- `docs/gelain-model-criticism.md` (stage B section), benchmark README.

Not changed: the plan, stage A results, any rate law or constant.

M2 result (`results/stage_b/M2_soluble_product_pool/`, 28 walkers, 8000
steps, 2000 burn-in, two resumed runs totalling 2 h 35 min wall-clock against
the plan's 2 h cap): not converged (tau 368 to 529 with 6000 post-burn-in
steps; ESS 318 to 457; mean acceptance 0.174, minimum 0.071), verdicts
provisional. R2 fails (multiplier median 1.94, interval [1.65, 2.87]). R3
fails (`mu`, `Ks`, `Ki` prior dominated; `P0` bounded below only, median
2.8 g/L against a 3 g/L bound). Common constants: `qF`, `qB` identified;
`k_h`, `kd` weakly identified; `Kh` bounded below only; `K_ind`, `kB`
bounded above only; `Y`, `kF` prior dominated. Coverage 95/96 at 95 percent
with measurement noise. Outcome: not supported (fails R1).

M1 result (`results/stage_b/M1_induction_state/`, 24 walkers, 8000 steps,
49 min wall-clock): not converged (tau 267 to 340 with 6000 post-burn-in
steps; ESS 423 to 540; mean acceptance 0.264), verdicts provisional. R2
fails (multiplier median 2.16, interval [1.87, 2.53]; baseline 2.25). R3
passes: `kz_loss` weakly identified (median 0.053 per hour, interval
[0.024, 0.58]). Common constants: `Y`, `kd`, `qF`, `qB` identified; `k_h`,
`Kh` weakly identified; `K_ind` bounded above only; `kF`, `kB` prior
dominated. Coverage 91/96 (cellulase 19/24). Outcome: not supported (fails
R1). The chain's report was re-rendered after the renderer fix; the
sampler and analysis outputs are those of the single run.

M3 result (`results/stage_b/M3_conversion_dependent_accessibility/`, 24
walkers, 8000 steps, 42 min wall-clock): not converged (tau 232 to 371 with
6000 post-burn-in steps; ESS 388 to 620; mean acceptance 0.290), verdicts
provisional. R2 fails (multiplier median 2.24, interval [1.94, 2.62]). R3
fails: `n` bounded above only (median 0.13, interval [0.053, 0.46], prior
[0.05, 3]). Common constants keep the baseline's classes. Coverage 91/96.
Outcome: not supported (fails R1).

Across the additions: none passes R1, none restores adequacy under R2, and
only M1's `kz_loss` is (weakly) identified under R3. The hydrolysis
candidate's biomass/cellulose misfit is not explained by an induction
memory, a soluble product pool with inhibition, or conversion-dependent
accessibility as declared.

Commands: `ruff check` passed; `pyright` 0 errors; criticism tests (see the
PR). Scientific impact: the soluble-pool mechanism neither restores adequacy
nor is identified by the duplicate means; nothing is promoted. Backward
compatibility: `write_posterior_outputs` writes one more file. Risk: low.

Recommended next task: tighten the stage A optimiser under a dated
amendment (PETAB-001 finding) and re-run stage A; chains longer than the
planned 8000 steps would need a second amendment and more than the 2 h cap.

## CI-001 Cross-Platform Quality-Gate Repair

Date: 2026-10-05

Status: complete for the three failure groups that were red on `main` on
Linux, macOS and Windows. No scientific or numerical behaviour changed; no
frozen artifact changed.

Changed:

- `standards/cross_engine.py`: the reference SBML simulator compiles each
  kinetic law from its L3 infix text (`+ - * / ^` and `pow`) with a small
  recursive-descent parser instead of walking libSBML `ASTNode` objects.
  SWIG keeps one proxy registry per process, so once `libsedml` had been
  imported by the SED-ML tests every kinetic-law node came back as a
  `libsedml.ASTNode` and no longer matched libSBML's `AST_*` constants. Ten
  SBML tests therefore failed on every platform whenever the full suite ran,
  and passed when run alone. Unsupported constructs now fail at compile time
  with the same `SbmlExportError`; unknown symbols are rejected before
  integration. `compile_kinetic_formula` is public and documented.
- `tests/test_gelain_joint_artifacts.py`: the frozen holdout replay compared
  scores at an absolute tolerance of 1e-6 although the predictions themselves
  are only required to replay to 2e-6 relative. Activity predictions of order
  1e3 U/L therefore failed by 1.1e-5 under current SciPy. The score tolerance
  is now the prediction tolerance propagated per observable
  (2e-6 x max|prediction| + 1e-6); the worst observed ratio across all 33
  folds and three statistics is 0.004. Manifest paths compare as POSIX.
- UTF-8 is explicit when reading repository data and documentation in
  `research/respiration_benchmark.py`, `research/secretion_benchmark.py`,
  `research/gelain_joint.py`, `research/gelain_culture.py`,
  `calibration/model_validation.py` (read and write, for symmetry),
  `scripts/prepare_respiration_data.py` and the affected tests. Windows
  decoded these files as cp1252 and mangled `±`.

Not changed: every model, solver, registry record, benchmark result and
frozen artifact; the SBML export itself; the SED-ML and COMBINE exporters.

Tests added (`tests/test_standards_sbml.py`):

- `test_reference_formula_compiler_covers_the_emitted_grammar`
- `test_reference_formula_compiler_rejects_what_fungmod_never_emits`
- `test_cross_engine_check_survives_libsedml_proxy_registration`

Commands run:

- `ruff check src tests scripts/run_*.py`: all checks passed.
- `pyright --pythonpath <venv python>`: 0 errors.
- `pytest tests/test_standards_sedml_combine.py tests/test_standards_sbml.py
  tests/test_standards_biomodels.py tests/test_gelain_joint_artifacts.py
  tests/test_public_experimental_data.py tests/test_quality_config.py
  tests/test_respiration_benchmark.py tests/test_secretion_benchmark.py
  tests/test_scoped_model_validation.py` (SED-ML first, so the proxy clash is
  exercised): 101 passed.
- `pytest` (full suite, Linux): 1703 passed, 0 failed in 17 min 22 s (main: 1685 passed, 11 failed; the seven new
  test cases account for the difference).
- Windows and macOS could not run locally; the encoding and path changes are
  verified on hosted CI.

Scientific impact: none. Backward compatibility: `simulate_reference_sbml`
and `cross_engine_trajectory_check` keep their signatures and error type; the
removed private AST walker had no public callers.

Ambiguities: none known. Risk: low.

Next task: merge this into `main`, bring `main` into the PR chain (#77 to #80)
so every job re-runs green, then merge the chain in order.

## PAPER-001 Software-Paper Plan Without A Wet Lab

Date: 2026-10-05

Status: plan recorded on the owner's decision. No code, data, test or numerical
behaviour changed.

Changed:

- `foundation_progress/FUNGMOD_STATE_AND_NEXT_STEPS_2026-10-04.md`: step 5 is
  now the software-and-methods-paper plan on published data, with six ordered
  items and exit gates (green CI and merged chain; Gelain model criticism;
  cross-study transfer from the literature; PEtab cross-solver reproduction;
  whole-fungus class unification; reproducibility package and preprint), a
  statement of what the paper may and may not claim, and an "After step 6"
  note that keeps modelling all fungi as the long-term goal measured in
  validated cases.
- `foundation_progress/FUNGMOD_NEXT_PHASES_ROADMAP.md`: dated decision note
  superseding the wet-lab step in the 2026-10-04 sequence.
- `foundation_progress/TRANSFER_DATASET_SURVEY_2026-10-05.md`: AI-assisted,
  abstract-level survey of candidate transfer datasets with a verification
  caveat on every item. Bottom line: no open raw-data deposit of a submerged
  Trichoderma cellulose batch with biomass, substrate and enzyme time courses
  other than Gelain 2020 was found; the usable candidates (Saez 2002 with
  Schell 2002, Velkovska 1997, Delabona 2016) are figure digitizations.

Not changed: every executable module, dataset, registry record and test.

Tests: none; documentation only.

Scientific impact: none. Backward compatibility: unaffected.

Ambiguities: the survey could not open any publisher or repository page, so
strain, conditions, replicate structure and licences of the candidates are
unverified; a person with normal web access must confirm them before any
candidate is registered. Risk: low.

Next task: CI-001 (cross-platform quality-gate repair, in progress on
`claude/ci-green`), then merge the PR chain, then the frozen plan for the
Gelain model-criticism study.

## BAYES-001 Bayesian Calibration And Identifiability On The Compiled Core

Date: 2026-10-05

Status: `partial` for step 4 of
`foundation_progress/FUNGMOD_STATE_AND_NEXT_STEPS_2026-10-04.md`. The
posterior-sampling machinery, the compiled-core predictor and the first
recorded identifiability study are `complete` for their stated scope. The
replicate-recovery half of the step is `blocked`: the Gelain 2020 deposit holds
no individual replicates or standard deviations, and the session's network
policy denied every publisher and repository host, so Pakula 2016 is recorded
as a candidate review only. Jacobians and parameter sensitivities are `not
started`; sampling is gradient-free on the compiled core. Step 4 was started on
the owner's instruction although ENV-003 left no sourced organism-level
temperature response; the machinery does not depend on one.

Changed:

- Added `calibration/bayesian.py` (replacing the placeholder):
  `PriorSpecification` (`log_uniform`/`uniform`, unit-bearing bounds, mandatory
  source), `NoiseScalePrior` (log-uniform multiplier on the supplied standard
  deviations of one observable or of a labelled group sharing one multiplier),
  `ObservedCondition`, `build_bayesian_problem` (log posterior in sampled
  coordinates; prediction failures give `-inf` and are counted),
  `run_ensemble_sampler` (Goodman-Weare affine-invariant stretch move,
  half-ensemble updates, pluggable `map_function`, progress callbacks, exact
  resume through `EnsembleRun.extend`), Sokal/emcee integrated autocorrelation
  times, effective sample sizes and a declared convergence rule,
  `classify_identifiability` with `IdentifiabilityCriteria` (`identified`,
  `weakly_identified`, `bounded_above_only`, `bounded_below_only`,
  `prior_dominated`; default thresholds one quarter, three quarters and two
  percent bound contact, recorded in every result),
  `local_information_analysis` (finite-difference Fisher information at the
  best sample, eigenvalues, practical rank, least constrained combination),
  `posterior_predictive`, `pooled_replicate_standard_deviation`,
  `sample_posterior`, `BayesianCalibrationResult` with `to_dict`/`save`
  carrying the method sources and the claim boundary.
- Added `calibration/compiled_predictor.py`: `ConfiguredConditionPredictor`
  rebuilds a condition's `ModelConfig` through a factory per candidate, loads,
  assembles, compiles and integrates it at the observation times on the
  compiled core and converts the declared state to the observable's units;
  `inline_parameter_config_factory` for plain configs.
- `screening/case_builder.py`: `resolve_registry_case`,
  `build_resolved_case_config` (exact value overrides; errors for unknown
  symbols, non-exact records and non-finite values) and
  `registry_case_config_factory`, so a fitted symbol reaches template-derived
  coefficients (the culture template bakes the yield into the product map).
  `build_model_config_from_registry_case` delegates to them with no overrides.
- Added `research/gelain_bayesian.py`,
  `scripts/run_gelain_2020_bayesian_calibration.py` (`--plan`, `--processes`,
  checkpoint and resume), `scripts/record_gelain_bayesian_verdicts.py` and
  `data/benchmarks/gelain_2020_bayesian/` (primary plan, per-observable
  variant plan, README, `results/`, `results_per_observable_scales/`).
  Primary study (24 walkers x 24000 steps, burn-in 4000, converged by the
  declared rule: autocorrelation times 227 to 339 steps against 20000 post-
  burn-in steps, effective sample sizes 1414 to 2119): five of nine constants
  identified (k_h, Y, kd, qF, qB), Kh bounded below only, K_ind, kF, kB bounded
  above only; shared noise multiplier 2.25 (1.95 to 2.63), so the residuals are
  about 2.2 times the assumed level; six of nine frozen point values lie inside
  their credible intervals.
- Per-observable sensitivity variant (40 walkers x 6000 steps, burn-in 1500,
  not converged by the declared rule, cited by nothing): with independent
  multipliers the sampler leaves the least-squares region, inflates the
  biomass multiplier to about 5.4 (3.2 to 7.5), tightens the substrate
  multiplier to about 0.5 and moves the yield to the lower edge of its box
  with the specific activities about five times higher; under the declared
  unit-scale error model that region is far worse than the frozen fit (log
  posterior -781 against -572) and eight of nine frozen point values lie
  outside its 95 percent intervals. It is recorded as a misfit diagnosis: the
  hydrolysis candidate cannot fit biomass and cellulose simultaneously at the
  assumed 10 percent error.
- Registry provenance: the nine calibrated T. harzianum records gain a
  `bayesian_identifiability` block (artifact, digest, benchmark id, class,
  posterior median, credible interval, whether the point value lies inside
  it, convergence, error-model evidence); their exact point values are
  unchanged.
- Candidate review `pakula_2016_t_reesei_protein_load_review.yml` (status
  `proposed`, no values).
- Docs: `docs/bayesian-calibration.md` (new), `docs/api.md`,
  `docs/capabilities.md`, `docs/calibration-evidence.md`,
  `docs/scientific-integrity.md`, `docs/organism-physiology.md`, README,
  CHANGELOG, `ARCHITECTURE_DEBT.md` (`FD-010`), roadmap and state-document
  notes.

Not changed: every registry parameter value, the scientific-mode trajectories
of the organism case, the least-squares, profile-likelihood and evidence-audit
APIs, the output schema, validators, solver settings, the compiled core (still
no Jacobians or parameter sensitivities), the research models and the frozen
v2 artifacts.

Tests added: `tests/test_bayesian_calibration.py` (12: analytic Gaussian
posterior recovery with Fisher eigenvalues, classifier thresholds on
constructed samples, sampled identified/one-sided/flat parameters, per-
observable and shared noise-scale estimation against the residual level,
pooled replicate deviations, AR(1) autocorrelation time, exact resume,
posterior predictive bands, toy configured model end to end with
serialization and seed reproducibility, invalid inputs);
`tests/test_gelain_bayesian_study.py` (6: plan and priors against the v2
bounds and the variant plan, observations and assumed errors, predictor parity
with the public scientific run and the yield override reaching the product
map, end-to-end study with checkpoint and resume, frozen primary artifact
consistent with its inputs and the registry provenance, variant artifact
labelled and uncited); `tests/test_dataset_candidate_review.py` listing.

Commands run and results: `python scripts/run_gelain_2020_bayesian_calibration.py
--output <dir> --processes 4 --checkpoint-every 500` (primary: 24 walkers x
24000 steps, resumed twice from its checkpoint, converged; the per-observable
variant with `--plan data/benchmarks/gelain_2020_bayesian/plan_per_observable_scales.json`,
40 x 6000, not converged); `python scripts/record_gelain_bayesian_verdicts.py`
(nine records updated); `ruff check src tests scripts/run_*.py
scripts/record_gelain_bayesian_verdicts.py` passed; `pyright` on the changed
modules, scripts and tests: 0 errors; `mkdocs build --strict` passed;
`pytest tests/test_gelain_bayesian_study.py tests/test_bayesian_calibration.py
tests/test_organism_registry_case.py`: 29 passed; the 28 test modules that use
the screening, calibration and candidate-review packages: 404 passed; the full
`pytest` run: 1792 passed, 11 failed, all eleven the pre-existing Linux set
(ten SBML tests under python-libsbml 5.21 and the Gelain holdout replay
drift), both frozen-artifact tests passing; full `pyright`: 0 errors.

Scientific behavior impact: no scientific-mode output changes; no registry
value changes. The repository now states, with a recorded artifact, which of
the nine T. harzianum hydrolysis-candidate constants the Gelain duplicate means
identify under the declared error model (k_h, Y, kd, qF, qB), which are one-
sided (Kh below; K_ind, kF, kB above) and that the assumed 10 percent error
understates the residuals by a factor of about 2.2. These are conditional
statements, labelled as such in the registry provenance and the artifact's
claim boundary.

Backward-compatibility impact: `fungal_model.calibration.bayesian` replaces a
placeholder, so nothing depended on it; `fungal_model.screening` gains
exports; `build_model_config_from_registry_case` keeps its signature and
output; the study plan schema is new (`1.0.0`). No output schema or registry
value changed.

Remaining ambiguities and risk: the error model is an assumption and the
shared multiplier conflates measurement error with model misfit; verdicts are
conditional on the prior box, the error model and a finite chain; the
per-observable variant shows a biomass/cellulose tension that replicate data
or a structural change must resolve; likelihood evaluations rebuild the config
per candidate (`FD-010`); replicate recovery stays blocked. Risk level:
medium, because new scientific statements enter the registry provenance; they
are labelled conditional and change no value.

Recommended next task: obtain replicate-level data with their own error
estimates (authors for Gelain; Pakula additional files once the network
allows) and rerun the study with a measured error model; in parallel, treat the
biomass/cellulose tension as a model-adequacy question (maintenance, product
inhibition or a cellulose-accessibility term) before step 5, and reduce
`FD-010` with parameter sensitivities on the compiled core.

## ENV-003 Bound Environment Response Laws

Date: 2026-10-05

Status: `partial` for step 3 of the state document. The laws are `complete`
(implemented, compiled, tested, bindable, reported). One sourced binding is
`complete` at enzyme level (BGL1A pH response, exploratory mode). The
organism-level bindings (cardinal temperature and pH for T. harzianum, thermal
inactivation of its activity pools) are `blocked` on sourced data: the
repository holds none and the session's network policy denied every publisher
host.

Changed:

- Added `kinetics/cardinal.py`: Rosso CTMI temperature activity and CPM pH
  activity (dimensionless, one at the optimum, zero at and beyond the cardinal
  bounds), with ordering checks and the CTMI denominator condition
  `T_opt >= (T_min + T_max) / 2`. Added `modifiers/cardinal.py`:
  `CardinalTemperatureModifier` (`temperature_cardinal_rosso`) and
  `CardinalPHModifier` (`ph_cardinal_rosso`) with build-time constant folding.
- Added `kinetics/ionization.py` and `processes/ionization.py`:
  `PHIonizationMichaelisMentenProcess` (`ph_ionization_michaelis_menten`),
  `v = E kcat(pH) S / (Km(pH) + S)` with `kcat(pH) = k0 / f_es(pH)` and
  `Km(pH) = Km0 f_e(pH) / f_es(pH)`, the SABIO-RK pH-dependent law form kept
  verbatim (product of the two ionization terms), optional measured pH bounds,
  numeric kernel, `effective_constants()` diagnostics, factory.
- Added `kinetics/inactivation.py` and `processes/inactivation.py`:
  `ThermalInactivationProcess` (`thermal_inactivation`), first-order loss of an
  active pool with `k_d(T)` in the Arrhenius reference form, optional inactive
  pool for closure, optional measured temperature bounds, numeric kernel,
  factory. Both new factories are in `default_foundation_factories()`.
- `processes/rate_modifiers.py`, `processes/factories.py`,
  `workflows/configured_outputs.py`: config builders, requirement collection,
  limitations and configured-metadata rows for the two cardinal modifiers;
  `configured_process_laws` rows for the two process laws.
- `screening/template_environment_modifiers.py`: one vocabulary for modifier
  and process-law environment conditions (`ENVIRONMENT_MODIFIER_CONDITIONS`,
  `PROCESS_ENVIRONMENT_CONDITIONS`); cardinal modifier branches; the inline
  environment entity now also covers conditions read by process laws;
  `environment_response_summary()` builds the per-condition law summary.
  `screening/parameter_resolution.py` maps the cardinal role fields.
- `screening/case_builder.py`: the homogeneous Michaelis-Menten assembler is
  generalized to one enzyme-kinetics builder parameterized by process type and
  parameter fields; a `ph_ionization_michaelis_menten` assembler is registered
  (`scientific`/`toy`, ten required roles including the measured pH bounds);
  every assembled config records `provenance.environment_response`.
  `screening/culture_physiology.py` passes its process types to the
  environment-entity builder.
- `screening/ensemble.py`: `RegistryCaseEnsemble.environment_response`
  (default empty) carries the assembled summary into result tables.
- `api/result_tables.py`: `environment_effect_status` is
  `active_response_model` when the assembled case binds a law; the policy
  allows comparison, ranking and response plots only when every condition that
  varies across the screened environments (temperature, pH, oxygen, water
  activity) is covered; `environment_response_model` lists `condition:law`
  pairs; new `environment_effect` and `ph_response` limitation rows; mechanism
  texts for the pH law. `api/environment_grid.py` and
  `api/virtual_experiment.py` no longer claim that grid values are inert; the
  grid status is the status before assembly. The runtime-grid overlay no
  longer copies condition-specific records whose only difference is the
  environment (for example the three Gelain cellulose loadings): such a grid
  case reports the role as missing and names the symbols under
  `ambiguous_condition_specific_symbols` instead of silently taking one
  condition's value.
- Registry: `phanerochaete_chrysosporium_k3` fungus, five
  `tsukada_2008_bgl1a_assay_30c_ph{4..8}` environments,
  `phanerochaete_bgl1a_cellobiose_ph_ionization_mm` compatibility,
  `phanerochaete_bgl1a_cellobiose_ph_ionization_template`, eight
  `literature_processed` constants copied verbatim from SABIO-RK entry 38522
  (k0, Km0, pKe1, pKe2, pKes1, pKes2, pH 4 and 8 bounds; raw export SHA-256 on
  every record; deposited deviations in notes) and two `exploratory_prior`
  loading assumptions (5 mM cellobiose, 1 micromolar enzyme). The
  `beta_glucosidase` enzyme class lists the new process.
- Two toy configs (`toy_ph_ionization_dissolved.yml`,
  `toy_thermal_inactivation_dissolved.yml`); candidate review
  `trichoderma_harzianum_cardinal_growth_review.yml` (status `proposed`, no
  values); docs (`docs/environment-response.md`, capability map, virtual
  experiment concepts, README, registry README, SABIO README), `CHANGELOG.md`,
  roadmap and state-document status notes.

Not changed: every existing registry parameter value, the T. harzianum
template (its temperature and pH remain metadata), the SABIO-RK rice-enzyme
case (still plain Michaelis-Menten, still `metadata_only` on grids), the
curated SABIO-RK range files, the output schema version, validators,
tolerances, solver settings, research models and frozen artifacts. The
Arrhenius and Gaussian modifiers keep their equations and assumption texts.

Tests added or modified:

- `tests/test_cardinal_response_laws.py` (new, 6): CTMI and CPM closed forms,
  bounds, Celsius input, rejections (ordering, sub-midpoint optimum, missing
  source), modifier activity and constant kernels, a generic first-order
  process wrapped by both cardinal modifiers with compiled parity and an
  analytic solve, config-builder field checks.
- `tests/test_ph_ionization_process.py` (new, 12): rate and effective
  constants against a verbatim transcription of the deposited SABIO-RK
  formula at five pH values, helper functions and pKa ordering, environment
  and input fail-closed paths, out-of-range warning, compiled parity across
  mixed units and product coefficients, compiled solve against an independent
  `solve_ivp` integration, factory decisions, toy config.
- `tests/test_thermal_inactivation_process.py` (new, 7): Arrhenius reference
  form, fail-closed inputs, measured-range warning, compiled parity, analytic
  exponential decay with closed ledger, factory decisions, toy config closed
  form.
- `tests/test_bgl1a_ph_response_case.py` (new, 6): registry constants equal
  the raw export bit for bit and record its SHA-256 (`data/kinetic_records/**`
  is now `-text` in `.gitattributes` so Windows checkouts keep the exact bytes,
  as the other checksummed snapshots already do); modelability exploratory
  modelable, scientific underparameterized on exactly the two assumptions, the
  sibling SABIO case unchanged; the assembled case binds the law and records
  `environment_response`; the public pH series reports `active_response_model`
  with ranking allowed, pH 6 fastest and pH 8 slowest half-conversion, and the
  pH 5 trajectory matches an independent integration of the deposited law; a
  temperature-varying grid keeps the law but blocks ranking with a guardrail
  naming temperature, a pH 9 grid warns, a pH-only grid allows ranking;
  scientific mode is blocked.
- `tests/test_organism_registry_case.py`: a runtime grid over T. harzianum
  reports the initial loading as missing in both modes and names the
  ambiguous symbol instead of selecting one of the three loadings.
- `tests/test_process_factory_library.py`, `tests/test_compiled_process_models.py`,
  `tests/test_sabiork_reaction_618_registry_case.py`,
  `tests/test_dataset_candidate_review.py`: factory set, shipped
  numeric-kernel set, enzyme-class process list and candidate-review listing
  extended.

Commands run and results:

- `ruff check src tests scripts/run_*.py`: passed.
- `pyright`: 0 errors.
- `mkdocs build --strict`: passed.
- Targeted: `pytest tests/test_cardinal_response_laws.py tests/test_thermal_inactivation_process.py tests/test_ph_ionization_process.py tests/test_bgl1a_ph_response_case.py`: 31 passed.
- Registry/screening/API/config/guardrail subset (27 modules): 401 passed,
  1 failed before the enzyme-class assertion in
  `tests/test_sabiork_reaction_618_registry_case.py` was updated; that module
  and the grid, API, organism and BGL1A modules (80 tests) re-ran green after
  the overlay change.
- Full `pytest` (SBML cross-engine module excluded as on CORE-001): 1772
  passed, 12 failed in 13m40s (Python 3.11, scipy 1.17.1, libsbml 5.21.2).
  Eleven failures are the pre-existing set recorded under CORE-001 (ten
  SBML standards/BioModels tests under python-libsbml 5.21 and the Gelain
  holdout replay drift); the twelfth was the candidate-review directory
  listing, whose test was updated during the run and re-ran green (19
  passed). All 32 added tests pass.
- Public path timing: the five-condition exploratory BGL1A pH series,
  tables and report complete in about 4 s.

Scientific behavior impact: a registry case can now change its dynamics with
pH through a sourced law, and the tables say exactly which condition acts
through which law. For the BGL1A case the half-conversion time among the
registry points is shortest at pH 6 and longest at pH 8, following the
deposited pKa values; cases outside pH 4-8 run with a recorded validity
warning. No existing case changes numerically: the T. harzianum and SABIO
rice cases bind no law and keep identical trajectories and statuses.
Deviation from the step-3 wording: the sourced binding is enzyme-level pH
response, not organism-level growth response, and no temperature law is bound
to any case.

Backward compatibility: public APIs are additive, with one behavioural
change: a runtime `EnvironmentGrid` over a case whose condition-specific
records span several registry environments (only T. harzianum today) is now
`underparameterized` instead of silently running with one condition's value.
`RegistryCaseEnsemble`
gains a defaulted field and a `to_dict` key; assembled configs gain
`provenance.environment_response`; the `environment_response_model` column
now carries `condition:law` pairs for active cases (previously the status
string, which no shipped case produced); the environment-grid overlay
provenance no longer carries an `environment_effect_status` key. The
`compatible_processes` tuple of the `beta_glucosidase` enzyme class gains one
entry.

Remaining ambiguities and risk: moderate. The BGL1A loadings are assumptions,
so absolute times are scenario values and only the pH ordering is sourced;
the deposited deviations are recorded but not propagated (exact records).
The cardinal and inactivation laws have no sourced binding, so grids over
temperature for T. harzianum still report `metadata_only`. Varying-condition
gating compares registry condition values literally (a kelvin and a Celsius
record of the same temperature would count as varying).

Recommended next task: with a network policy that allows publisher hosts,
retrieve and archive the cardinal-growth candidate (and a thermal-stability
source for the Gelain activity pools), fit the CTMI with a recorded artifact,
author the records, and bind `temperature_cardinal_rosso` and
`thermal_inactivation` in the T. harzianum template; then step 4
(identifiability and Bayesian calibration on the compiled core).

## ORG-001 First Whole-Organism Registry Case

Date: 2026-10-05

Status: `complete` for step 2's definition of done with one stated deviation
(no measured product pool; see "Scientific behavior impact"). The remaining
`DegradingCulture` closures (resource-limited growth, maintenance, costed
secretion) and the A. niger / T. reesei organism records are `blocked` on data,
not on code, and are recorded below.

Changed:

- Added `processes/physiology.py`: `ProportionalSynthesisProcess`
  (`process_type: proportional_synthesis`), producer-proportional formation of
  one product pool with optional saturable induction
  (`rate = q P` or `q P I / (K_I + I)`), product-only contributions, numeric
  kernel, and `ProportionalSynthesisFactory` registered in
  `default_foundation_factories()`. Tested on dissolved millimolar chemistry
  and on assay-activity units.
- Added assay-activity base dimensions to `core/units.py`:
  `filter_paper_unit` (`FPU`) and `beta_glucosidase_assay_unit` (`BGU`), not
  convertible to mass, molarity or each other. `research/gelain_models.py`
  now defines `gelain_fpu` and `gelain_beta_u` as aliases of them.
- Added `screening/culture_physiology.py`: the `culture_physiology` template
  family. A template declares state roles (`substrate`, `biomass`, `enzyme`,
  indexed `enzyme_*` and `ledger_*`), ordered generic process templates with
  state-role and parameter-role bindings, stoichiometric product maps whose
  coefficients may reference a parameter role or its complement, a closure
  ledger checked at build time, state identities and inline entities. Fail
  closed on unused or unresolved roles, unregistered process types,
  unbalanced product maps and undeclared identities. Registered as a
  `scientific`/`toy` assembler in `screening/case_builder.py`.
- `registry/records.py`: `biomass` added to the allowed case-template state
  roles; `ledger_*` added to the indexed-role pattern.
- `screening/modelability.py`: enzyme classes of a fungus that do not target
  the requested substrate are reported as known, unused items when another
  class reaches a compatible process; they block only when no class does.
  `select_registry_case_compatibility` skips classes without a compatibility
  record instead of raising.
- `solvers/compiled.py` and `solvers/process_ode.py`: rates are evaluated at
  `max(state, 0)` (`NEGATIVE_STATE_POLICY`, recorded in
  `solver_metadata["kernel"]`) both in the right-hand side and when recording
  process rates at output points. The integrated trajectory is never clipped;
  the `non_negative` validator reports accepted states below tolerance. The
  unit-aware `Process.rate` stays strict. Without this, the generic
  Michaelis-Menten law could not be integrated to substrate depletion: the
  solver's trial iterates near zero raised inside the right-hand side.
- `api/result_tables.py`: mechanism, maturity and limitation text for
  `culture_physiology` cases (`software_tested_retrospectively_calibrated_unvalidated`,
  `retrospective_calibration` limitation rows).
- Registry records (`data_registry/`): fungus `trichoderma_harzianum_p49p11`
  (strain, DOIs, two enzyme classes, no invented physiology field); enzyme
  class `cellulase_total_filter_paper_activity` (Ghose 1987 assay pool);
  substrate `cellulose_celufloc_200` (`cellulose_particulate`, explicit unknown
  surface area and crystallinity, no product); environments
  `gelain_2020_cellulose_batch_{10,20,30}gl` (302.15 K, pH 5.0, dissolved
  oxygen unknown above 30 percent, loading, 1.9 L); compatibility
  `trichoderma_harzianum_cellulose_culture_physiology` (13 roles); template
  `trichoderma_harzianum_cellulose_culture_template` (six processes, dry-mass
  closure ledger, suggested experiments); nine `calibrated` parameter records
  copied at full precision from
  `data/benchmarks/gelain_2020_v2/results/full_fits/cellulose_hydrolysis_primary.json`
  (SHA-256 recorded, training conditions, rank 9/9, condition number,
  at-bound flags for `K_ind`, `kF`, `kB`) with explicit
  `allowed_use: scientific_or_exploratory_when_all_other_inputs_are_valid`;
  five `literature_processed` initial-condition records from the deposited
  workbooks (initial biomass, loading per condition, zero initial activities).
- Added `data/model_configs/toy_proportional_synthesis_dissolved.yml`
  (non-biological toy exercising the new process through the configured
  workflow and the compiled-core parity tests).
- Docs: `docs/organism-physiology.md` (new, in nav), `docs/compiled-core.md`
  (negative-state policy), `docs/capabilities.md`, `README.md`,
  `data_registry/README.md`, `CHANGELOG.md`, `ARCHITECTURE_DEBT.md` (FD-009
  narrowed), roadmap and state-document status notes.

Not changed: every other registry record, config, notebook, output schema
version, validator, `SolverSettings`, tolerances, the legacy engines, the
physiology classes, the research models' equations and frozen artifacts, the
Gelain joint comparison, calibration and validation behavior. No fitted value
was re-estimated; the registry copies the frozen artifact.

Tests added or modified:

- `tests/test_organism_registry_case.py` (new): organism record and sourced
  capabilities; calibrated records equal the frozen artifact bit for bit with
  matching units and the recorded SHA-256; all three conditions modelable in
  scientific mode through the cellulase class only; the configured model
  reproduces `research.gelain_models.simulate_candidate(model="hydrolysis")`
  for all three loadings (`rtol 1e-6`, scaled `atol 1e-7`) with a closed
  dry-mass ledger and near-complete cellulose consumption; the public
  `VirtualExperiment` scientific run writes biomass, two enzyme-activity,
  substrate and ledger roles, computed 10/50/90 percent threshold times,
  the retrospective-calibration limitation and the `scientific_exact_unvalidated`
  run label; exploratory mode samples nothing on exact records; withdrawing
  one calibrated record fails closed at preflight, builder and public API;
  unused or unresolved template roles are rejected.
- `tests/test_proportional_synthesis_process.py` (new): closed-form law,
  constitutive form, partial-induction and distinct-state rejection,
  negative-state and invalid-constant errors, compiled kernel parity across
  mixed units, analytic solve, factory decisions, toy config analytic check.
- `tests/test_compiled_process_models.py`: `proportional_synthesis` added to
  the shipped numeric-kernel set; the negative-state test now asserts the
  projection policy (compiled RHS at a negative trial state equals the
  reference at the projected state; the unit-aware reference still raises) and
  a new depletion test integrates a first-order pool over many lifetimes.
- `tests/test_modelability_report.py`: multi-enzyme-class fungus stays
  modelable with the non-targeting class reported as unused.
- `tests/test_registry_case_builder.py`, `tests/test_process_factory_library.py`:
  assembler and factory sets extended.

Commands run and results:

- `ruff check src tests scripts/run_*.py`: passed.
- `pyright`: 0 errors.
- `mkdocs build --strict`: passed.
- Targeted: `pytest tests/test_proportional_synthesis_process.py tests/test_organism_registry_case.py tests/test_modelability_report.py tests/test_registry_case_builder.py tests/test_compiled_process_models.py tests/test_process_factory_library.py`: 120 passed.
- Registry/screening/API/maturity/guardrail subset (29 modules): 548 passed,
  1 failed (`test_gelain_joint_artifacts.py::test_every_frozen_holdout_replays_with_training_only_scales_and_matching_scores`,
  the pre-existing scipy 1.17 replay drift of 4.43e-6 against the 2e-6 gate
  recorded under CORE-001; unchanged by this work).
- Full `pytest`: 1738 passed, 11 failed in 13m05s (Python 3.11, numpy 2.4.6,
  scipy 1.17.1, libsbml 5.21.2). The 11 failures are exactly the pre-existing
  set recorded under CORE-001 (ten SBML cross-engine/BioModels tests under
  python-libsbml 5.21 and the Gelain holdout replay drift); the 21 added tests
  all pass.
- Public path timing: the three-condition scientific `VirtualExperiment` run,
  tables, quick-look plots and report complete in about 5.5 s.

Scientific behavior impact: a new organism case becomes runnable in
`scientific` mode; its trajectories equal the frozen research candidate.
No existing config changes numerically: the non-negative projection only
affects right-hand-side evaluations at trial states below zero, which no
packaged config reaches (parity tests still report identical trajectories and
evaluation counts). Deviation from the step-2 wording: the Gelain data hold no
measured product, so the case tracks consumed cellulose not retained as
biomass as an explicit closure ledger rather than a product pool; output
tables mark product metrics `not_applicable`.

Backward compatibility: public APIs are additive. `CASE_TEMPLATE_ALLOWED_STATE_ROLES`
gains `biomass`; modelability reports for multi-class fungi change from
`underparameterized` to the status of the targeting class (no shipped fungus
had more than one class). Compiled RHS behaviour at negative trial states
changes from raising to projecting; the `solver_metadata["kernel"]` summary
gains `negative_state_policy`. The `gelain_fpu`/`gelain_beta_u` units keep
their non-convertibility and now also convert 1:1 to `FPU`/`BGU`.

Remaining ambiguities and risk: moderate. The calibrated constants are a
retrospective fit that failed the comparison's observable-worsening screen in
the primary scenario and has three constants at bounds; the registry says so
on every record, but a reader of `time_series_long.csv` alone sees exact
trajectories. The `culture_physiology` family has one real template; its
contract will move when a second organism arrives. Environment records carry
temperature and pH as metadata only.

Recommended next task: step 3 of the state document, bind cardinal-temperature
and pH response laws to this organism's processes with sourced parameters and
enzyme thermal inactivation; in parallel, intake Pakula 2016 (T. reesei time
courses) and resolve A. niger enzyme-class evidence so a second organism can be
registered, then promote the Pirt/Monod closures as processes against it.

## CORE-001 Compiled Well-Mixed Process Core

Date: 2026-10-04

Status: `complete` for the well-mixed `Process` path (step 1, first slice).
The legacy `Reaction` engine, the spatial engines, the physiology classes and
the research models remain on their own integrators (`FD-009`).

Changed:

- Added `core/kernels.py`: `KernelContext` (state index, state units, time
  unit, parameters, environment, geometry; build-time conversion factors and
  parameter values) and the `RateKernel` contract.
- Added `solvers/compiled.py`: `compile_assembled_model` builds
  `dy/dt = N v(t, y)` on plain floats. `N` is probed from
  `Process.contributions` at three rates and must be linear in the rate; each
  column already carries the rate-unit to state-unit-per-time conversion.
  Kernel kinds `numeric`, `numeric_thermodynamic`, `quantity_wrapped` and
  `quantity_wrapped_thermodynamic` are recorded per process in
  `CompiledModel.summary()`.
- Added `Process.compile_rate(context)` (default `None`) and numeric kernels on
  `FirstOrderDecayProcess`, `MassActionProcess`,
  `HomogeneousMichaelisMentenProcess`, `SurfaceCatalysisProcess`,
  `SubstrateTransglycosylationProcess` and `RateModifierProcess` (which also
  gained a `rate_units` property). Kernels reproduce the unit-aware arithmetic
  in the same operation order and raise the same errors for negative states.
- Added `compile_activity(context)` on all eight modifiers. Product,
  competitive, Haldane and coupled inhibition compile to float algebra;
  temperature, pH, oxygen and water activity fold to a constant through the
  modifier's own `activity` (`modifiers.base.constant_activity_kernel`).
- Added `DynamicThermodynamicConstraint.compile_feasibility(context)`, a float
  mirror of `evaluate`, so thermodynamic blocking stays numeric at solver time.
- `ProcessODESolver.run` compiles once per run and integrates the compiled
  right-hand side; `ProcessODESolver.compile(request)` exposes the compiled
  model; `solver_metadata["kernel"]` records the kernel summary. Process-rate
  trajectories at returned time points reuse the kernels; constrained
  processes are still re-evaluated through the unit-aware `enforce` so the
  recorded activities, quotients and Gibbs energies are unchanged.
- Documentation: `docs/compiled-core.md` (nav under Core concepts), capability
  map row, README limitation bullet, `CHANGELOG.md`, `ARCHITECTURE_DEBT.md`
  `FD-009`.

Not changed:

- Rate laws, parameters, registry records, configs, notebooks, output
  schemas, validators, `SolverSettings`, `solve_checked`, tolerances, failure
  semantics, clipping policy (none), thermodynamic diagnostics, the legacy
  `SimulationEngine`, the spatial engines, the physiology classes, research
  models, calibration or validation behavior.

Tests added:

- `tests/test_compiled_process_models.py` (32 tests): compiled right-hand side
  and trajectories equal the unit-aware reference on every packaged model
  config with identical `nfev`; every kernel matches its process rate
  pointwise; kernel kinds and numeric thermodynamic enforcement are recorded;
  all shipped process types compile numerically (architecture-debt boundary);
  a process without a kernel uses the recorded wrapped path and matches the
  numeric path to 1e-12; nonlinear contributions and unknown states are
  rejected; mixed units (micromolar states, per-minute constant, hour time
  grid) resolve at build time and match the closed form; environment
  modifiers fold to constants that match the reference and still warn
  outside their source range; negative states raise the same error text;
  `KernelContext` and constraint-process checks.

Commands run and results (venv, Python 3.11, numpy 2.4.6, scipy 1.17.1,
pint 0.25.3, libsbml 5.21.2):

- Parity script over all ten `data/model_configs/*.yml`: maximum relative
  right-hand-side difference 0, maximum relative trajectory difference 0,
  identical `nfev`; compiled versus unit-aware solve times 19/252, 5/198,
  8/478, 1.5/27, 1.4/39, 1.8/65, 1.6/51, 0.6/3.5, 0.8/17, 0.6/3.6 ms.
- `ruff check src tests scripts/run_*.py`: passed.
- `pyright`: 0 errors.
- `mkdocs build --strict`: passed.
- `pytest tests/test_compiled_process_models.py`: 32 passed.
- `pytest` (full suite): 1717 passed, 11 failed in 18m44s. The 11 failures
  are exactly the pre-existing set recorded in STATE-2026-10-04 (ten SBML
  cross-engine/BioModels tests under libsbml 5.21, one frozen Gelain holdout
  replay at 4.4e-6 against the 2e-6 gate under scipy 1.17); the count rises
  from 1685 to 1717 passed by the 32 new tests. Hosted CI on the PR head
  reproduces the same 11/1717 on ubuntu for Python 3.11 and 3.12, and
  `main`'s own CI is red with the same SBML failures.

Scientific behavior impact: none intended; the compiled path is verified to
reproduce the unit-aware path bit-for-bit on every packaged config, and the
same stiff-solver finite-difference Jacobian is used. Two observable
non-scientific differences: environment-range warnings fire once per run, and
`solver_metadata` gains a `kernel` entry.

Backward compatibility: public APIs unchanged; `_state_units` in
`solvers/process_ode.py` is now an alias of `solvers.compiled.resolve_state_units`;
third-party `Process` subclasses without `compile_rate` keep working through
the recorded wrapped path.

Measured public-path effect: a configured run's integration is now a few
milliseconds; the remaining ~0.6 s per ensemble sample is per-sample bundle
writing, chiefly three matplotlib figures per sample in
`SimulationResult.save`. That is a screening output-policy question, not a
solver one, and was left unchanged here.

Risk: low for numerics (exact parity, same backend, same tolerances);
moderate for maintenance because each new process must ship a kernel or
accept the recorded slow path, which the boundary test makes visible.

Recommended next task: CORE-002, express `Reaction` rate laws and the
`FungalCouplingModel` physiology as processes or builders that emit the
compiled representation, add an optional analytic Jacobian hook to
`compile_rate`, then move the spatial engines onto compiled per-cell kernels;
afterwards reduce per-sample figure output in registry ensembles.

## STATE-2026-10-04 Verified State Assessment And Next-Step Sequence

Date: 2026-10-04

Status: `complete` for the documentation task. No code, data, registry, or
scientific behavior changed.

Changed:

- Added `foundation_progress/FUNGMOD_STATE_AND_NEXT_STEPS_2026-10-04.md`: the
  verified state of the repository on `main` at `50f8496`, the measured
  registry coverage, a solver/engine inventory with per-RHS timings, the gaps
  to a validated whole-fungus model, and an ordered next-step sequence.
- Added the assessment to the `AGENTS.md` active source-of-truth order after
  the roadmap, and a dated status note at the top of the roadmap status list.

Not changed:

- Source code, tests, registry records, configs, notebooks, benchmarks.

Verification recorded in the assessment (venv on Python 3.11, numpy 2.4.6,
scipy 1.17.1, pint 0.25.3, libsbml 5.21.2):

- `ruff check src tests scripts/run_*.py`: passed.
- `pyright`: 0 errors.
- `pytest`: 1685 passed, 11 failed in 18m41s. The failures are dependency and
  test-order sensitivity, not model defects: nine SBML cross-engine/unit tests
  pass in isolation and fail only in the full run; the BioModels round-trip
  fails under libsbml 5.21; one frozen Gelain holdout replays to 4.4e-6
  relative difference against the 2e-6 gate under scipy 1.17.
- Registry enumeration: 27 combinations, 3 runnable in exploratory mode, 0 in
  scientific mode; 0 shipped case templates bind an environment response law.
- Timing: `SimulationEngine` and `ProcessODESolver` cost about 0.5 ms per
  right-hand-side evaluation against 16 us for the same model in plain numpy;
  the 1D reaction-diffusion engine spends 66 ms per evaluation at 200 cells;
  the public Reaction 618 ensemble costs about 0.8 s per sample.

Scientific behavior impact: none. Backward compatibility: none.

Risk: low (documentation only).

Recommended next task: CORE-001, a compiled well-mixed model core with
build-time unit resolution, a stoichiometric matrix probed from
`Process.contributions`, numeric rate kernels for every shipped process, an
explicit recorded fallback for processes without kernels, and parity tests
against the unit-aware path.

## DIGESTION-001 Conserved Secretion And Extracellular Digestion

Date: 2026-10-03

Status: implemented for the explicitly exploratory coupled mechanism and bounded
protein-output comparison. Full fungal physiology and organism validation remain open.

Changed:

- Added `fungi/degradation.py`: seven chemically declared pools couple growth,
  substrate maintenance, protein synthesis, extracellular hydrolysis and
  inactivation. Growth and secretion share one post-maintenance uptake budget.
  Active/inactive protein preserves atoms/charge, and all feed, respiratory and
  reservoir exchanges have integrated ledgers. Batch degradation thresholds
  reject flowing cultures and retain unreached values as null. Formula-mass
  allocation conversion requires explicit yields and an observation mapping.
- Added analytic piecewise Jacobians to the integrated model and existing
  resource-limited respiration. A 33-point parameter sweep initially failed
  with `IntegrationError: RHS returned invalid shape or nonfinite derivatives
  at time 46.118755793777986.` SciPy BDF finite-difference Jacobian perturbations
  overflowed in non-feedback ledger states. Analytic derivatives eliminate the
  unnecessary perturbations; tolerances and biology were not altered to hide
  the failure. The failed preview folder is retained separately from completed
  results. Independent finite differences verify the full augmented Jacobians.
- Added `research/secretion_benchmark.py`, an explicit illustrative chemical
  assembly, offline extraction and benchmark scripts, plus four reproducible
  plots. The new Jorgensen 2009 primary XML (doi:10.1186/1471-2164-10-44,
  CC-BY-2.0) and all Table 1 rows retain hashes, original values, SDs, units,
  footnotes, sequential-culture dependence and provenance.
- Updated README, capability boundaries, active roadmap, changelog, package
  manifest and MkDocs navigation. Detailed mechanism, limits, commands and
  compatibility are in `docs/degrading-culture.md`.

Results:

- Holding out each entire strain, including both carbon conditions, gives
  protein-output RMSE 0.586931 for a pooled effective ratio versus 0.207002
  mg/(g dry biomass h) for carbon-source-dependent ratios (64.7% reduction).
  Nominal growth 0.16/h and carbon-source identity are supplied predictors.
  Four group means summarize 12 steady states in six culture runs. Only two
  strain folds exist; the more flexible comparator has two coefficients versus
  one and one training mean per carbon per fold. Neither the growth-associated
  mechanism nor a non-growth intercept is identified. SDs are retained, not
  treated as confidence intervals or independent likelihood weights.
- Four illustrative coupled scenarios close the open atom/charge ledger to
  3.35e-15 mol/L; maximum BDF/tighter-Radau pool difference is 3.01e-10 mol/L.
  Software tests also cover LSODA and DOP853. Zero secretion with no initial
  active enzyme gives no polymer conversion. Oxygen/nitrogen limitation can
  leave released sugar unused while extracellular hydrolysis continues.
- The allocation sweep covers 33 fractions. More secretion speeds digestion
  but reduces final biomass under these assumptions. Nine explicit catalytic
  capacity/inactivation combinations give 90% removal times 5.02–46.56 h.
  These are illustrative sensitivity results, not empirical forecasts, a
  confidence interval, fitted kinetics or a demonstrated biological optimum.
- Completed artifacts: `outputs/degrading-culture-2026-10-03-final/`.
  All four plots were visually inspected. All 191 source hashes and nine
  artifact hashes match the completed run. Output directories are ignored;
  primary sources, code and reproducible extraction are packaged.

Scientific behavior impact: new opt-in balanced secretion/hydrolysis feedback.
Growth, maintenance, uptake and gas-transfer laws in the existing respiration
API remain mathematically unchanged. Analytic Jacobians change step choices
and roundoff; diagnostics add a Jacobian field. No unsupported energy or
viability output is introduced. Complete common-state formation energies and
activities remain mandatory before reporting physiological entropy/free energy.

Unchanged: existing configured VirtualExperiment behavior, registry defaults,
prior source calibrations, public scalar solver controls, remote Git state and
published packages. No organism-specific branch was added to generic/core
modules. No total-protein/FPU/transcript-to-active-enzyme conversion is inferred.
No new living-fungus model is automatically constructed from entity metadata.

Tests added: `tests/test_degrading_culture.py`,
`tests/test_secretion_benchmark.py`, `tests/test_degrading_culture_benchmark.py`.
They cover resource starvation, one shared uptake budget, balanced pathways,
materially different polyester/nitrate chemistry, enzyme-only catalysis,
no-bootstrap behavior, analytic decay/dilution, solver agreement, reduction to
prior respiration, derivative checks, threshold and unit/provenance failures,
source fidelity/tampering, whole-strain leakage, the entire allocation and
kinetic sweep, and preservation of existing evidence. 44 tests added in total.

Commands and results:

- Focused pytest on the three new files plus `tests/test_respiration.py`:
  82 passed in 5.67 s.
- Full `pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`:
  1696 passed in 506.74 s; total coverage 85.26% (80% gate passed).
- `ruff check src tests scripts/prepare_secretion_data.py scripts/run_degrading_culture_benchmark.py`:
  passed. `pyright --pythonpath .venv/bin/python`: zero errors/warnings.
  `git diff --check`: passed.
- `prepare_secretion_data.py --check`: two source/extract checksums passed.
  `prepare_respiration_data.py --check`: three passed.
  `prepare_public_experimental_data.py --check`: 19 extracts verified.
- `run_degrading_culture_benchmark.py --output outputs/degrading-culture-2026-10-03-final`:
  completed all four figures, trajectories, sweep, holdouts and manifests.
- `mkdocs build --strict`: passed. `check_packaged_resources.py`: passed.
- `python -m build --outdir /private/tmp/fungmod-digestion-dist`: wheel and
  sdist passed; `twine check` passed both. Built-wheel resource check: 226
  canonical resources present once with identical bytes. The new extractor,
  runner, documentation and primary XML are also present once in the sdist.
- Installed the wheel with `--no-deps --ignore-installed --target` into a fresh
  temporary directory. From `/private/tmp`, isolated `python -I` imported that
  installation, checked the packaged primary-data hashes, ran the empirical
  holdouts and a coupled BDF simulation with conserved exchange: passed.
  Pip disabled its unwritable user cache automatically; installation succeeded.

Remaining ambiguities: net extracellular protein versus biosynthesis, active
fraction and composition, synthesis yield, kinetic capacities/affinities,
induction/repression, storage, adsorption, pH, organic-product secretion,
death/recycling, hyphal geometry and thermochemistry. No new quality gate is
blocked. Software risk: moderate for new coupled API; organism-level scientific
extrapolation risk: high until matched data and independent validation exist.
Recommended next task: recover matched dynamic cultivation/protein-composition
supplements (Pakula 2016 is a candidate), resolve active-protein observation
mapping and induction/storage, then connect hyphal tips/branching to spatial
transport with measured geometry. The Pakula paper motivates protein cost but
is not numerical validation in this batch.

## RESPIRATION-001 Conserved Physiology And New Primary Data

Date: 2026-10-03

Status: implemented for the bounded growth/respiration component and new-data
comparison. Full-fungus prediction and broad empirical validation remain open.

Changed:

- Added `fungi/respiration.py`: sourced growth and non-growth substrate
  maintenance pathways solved from atom/charge conservation, a resource-limited
  batch/chemostat model, dissolved oxygen/gas transfer, nitrogen limitation,
  explicit reservoirs, integrated boundary/reaction ledgers and unmet
  maintenance diagnostics. Complete sourced energies are mandatory for an
  entropy budget, and negative entropy in an operating pathway rejects.
- Added `research/respiration_benchmark.py` for training-only nonnegative Pirt
  fitting, checksum-bound data loading and study-specific glucose/ammonium
  assembly. No organism-specific logic was added to generic/core modules.
- Retrieved two CC-BY primary XML articles for A. niger NW185 (Lameiras 2015,
  doi:10.1007/s11306-015-0781-z; Lameiras et al. 2017,
  doi:10.1007/s00449-017-1854-3). Preserved source hashes, roles, quoted errors,
  unit transformations, attribution and suspicious cells. Added deterministic
  offline extraction/checking and an offline four-figure benchmark runner.
- Documented mechanism assumptions, commands, API, results, compatibility and
  next experiments in `docs/respiration-benchmark.md`; updated capability,
  roadmap, changelog, navigation and source-distribution packaging.

Results:

- Four retrospective leave-one-dilution-out fits use only unreconciled 2015
  glucose uptake; oxygen/CO2 are never fitted. Nominal growth mu = dilution is
  an explicit predictor. RMSE improves from 1.556 to 0.386 (glucose, 75.2%),
  21.524 to 16.464 (oxygen, 23.5%) and 12.995 to 8.563 (CO2, 34.1%), all in
  mmol/(Cmol biomass h). The comparator is an explicit growth-only hypothesis,
  not every existing FungMod model. Four conditions are not twelve independent
  experiments, and holdouts within one paper are not independent laboratories.
- All-condition point calibration gives Y = 3.655858 Cmol biomass/mol glucose
  and m = 2.391421 mmol glucose/(Cmol biomass h). Across 256 plus/minus
  reported-error corners, 96 fits reach m = 0 and 16 require oxygen production
  or carbon fixation in growth. Those 16 remain flagged; the aerobic subset
  has Y 2.851637–5.654259 and m 0–15.074991 in the stated units. This is an
  assumption sensitivity envelope, not a confidence interval or posterior.
- Frozen transfer to the 2017 glucose batch reference overpredicts uptake
  16.4%, oxygen 41.4%, CO2 50.1%. Different pH/regime and possible biomass
  composition changes remain confounded. Rates were reconciled, so this does
  not independently test conservation. Six single-substrate and eleven
  mixed-substrate conditions are preserved for clearly labelled challenges.
- Published CO2 and TOC cells at 2017 dilution 0.16/h are retained verbatim and
  quarantined from scoring. Supplemental verification remains unavailable:
  Springer download returned `URLError: nodename nor servname provided, or not
  known`; Europe PMC supplementaryFiles timed out after 45 seconds. The two
  primary XML downloads and their usable tables succeeded; no omitted digits
  or supplemental measurements were guessed.
- Three explicitly illustrative dynamic scenarios exercise aerated growth,
  low oxygen transfer and nitrogen limitation. Maximum open atom/charge
  residual is 6.22e-16 mol/L and maximum Radau/BDF pool disagreement is
  3.24e-10 mol/L. Unmet maintenance after depletion is visible; no survival,
  dormancy or death output is inferred. Kinetic affinities/capacities, transfer
  and initial states are assumptions, not experimental trajectories.

Tests added: `test_respiration.py`, `test_respiration_benchmark.py`. Current
focused run: 52 passed. Coverage includes four integrators, conservation,
analytic sterile chemostat/gas transfer, washout, depletion, limiting resources,
charged ammonium and materially different ethanol/nitrate chemistry, unit and
source guards, entropy requirements, exact source extraction and tamper checks,
holdout/gas/reconciled-data leakage prevention, sensitivity and artifact preservation.

Commands/results (local verification, not hosted CI):

- `.venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing
  --cov-report=xml`: 1,649 passed in 505.81 s; 85.01% coverage.
- Final `.venv/bin/python -m pytest -q tests/test_respiration.py
  tests/test_respiration_benchmark.py --cov=fungal_model --cov-append
  --cov-report=term --cov-report=xml`: 52 passed in 5.18 s; 85.12% coverage.
  This includes the final maintenance-demand guard and three added runner tests.
  Final collection is 1,652 tests; all are covered by full and final focused runs.
- `.venv/bin/python -m ruff check src tests scripts/run_*.py
  scripts/prepare_respiration_data.py`: passed. Initial semicolon-style findings
  were corrected. `.venv/bin/python -m pyright --pythonpath .venv/bin/python`:
  zero errors; optional parameter-value and Pint addition typing were narrowed
  without disabling checks.
- `.venv/bin/python scripts/prepare_respiration_data.py --check`: three
  source/extract hashes and exact extraction pass.
  `.venv/bin/python scripts/prepare_public_experimental_data.py --check`:
  all 19 historical extracts still match.
- `.venv/bin/python -m mkdocs build --strict`: passed.
- `MPLCONFIGDIR=/private/tmp/fungmod-mpl .venv/bin/python
  scripts/run_respiration_benchmark.py --output
  outputs/respiration-expansion-2026-10-03-final`: complete. All four figures
  inspected; final figures are byte-identical to the inspected images. Final
  input/implementation/artifact hashes independently verified. Earlier output
  bundles remain preserved; the final bundle is the report reference.
- `.venv/bin/python -m build --outdir /private/tmp/fungmod-respiration-dist`:
  wheel and sdist built. `python -m twine check` passed both archives.
  `scripts/check_built_distribution_resources.py` verifies 222 canonical
  resources exactly once and byte-identical in the new wheel.
- Installed-wheel smoke in `/private/tmp/fungmod-respiration-wheel`, with
  `--ignore-installed --no-deps` and execution from `/private/tmp` with `-I`:
  isolated package/resource paths, all source hashes, Pirt calibration,
  respiration, Radau dynamics and open conservation pass.
- `git diff --check`: passed. No verification command remains blocked.
  Only the optional supplemental-data downloads failed for the exact reasons
  above; their unverified contents remain unused.

Scientific behavior impact: new explicit two-pathway physiology and operating
conditions, with conditional empirical exchange-rate testing. Rates are not
inferred from free energy. No fungal thermochemical values, unidentified TOC
chemistry, replicate errors or regulation parameters are invented.

Backward compatibility/unchanged: additive advanced API; previous solver,
thermodynamic, macrochemical and benchmark work is preserved. Existing fungal
coupling, active-to-inactive maintenance, registry, configured workflow defaults
and numerical outputs are not replaced. No registry promotion, release, commit
or push. Automatic secretion integration would require consistent chemical
bookkeeping to avoid counting carbon/energy twice.

Remaining ambiguity/risk: moderate scientific-interpretation risk; low API
compatibility risk because opt-in. Four conditions cannot identify full
physiology. Carbon secretion, composition changes, mixed-substrate regulation,
starvation/death, morphology and spatial enzyme–resource coupling remain open.
Recommended next task: obtain matched dynamic sugar/biomass/N/O2/CO2/TOC data,
biomass composition and viable biomass with raw replicate covariance, then
identify uptake/regulatory and secretion mechanisms before whole-fungus integration.

## SOLVER-THERMO-002 Coupled Free Energy And Numerical Accuracy

Date: 2026-10-03

Status: complete for this bounded solver/thermodynamic expansion and data replay.
Perfect, organism-general or empirically validated prediction remains unestablished.

Changed:

- Added shared numerical contracts in `core/numerics.py`: explicit per-state
  unit-bearing absolute tolerances, first/max-step control, validation and
  rejection of incomplete/nonfinite integrations. Existing SolverSettings import
  paths remain available. Main reaction, native process and 1D/2D/3D engines use
  the shared boundary; joint culture models accept the same optional controls.
- Added sparse Cartesian Jacobian structure for BDF/Radau on cell-local 1D
  reaction/diffusion and pure ND diffusion. Arbitrary field-wide ND reactions
  retain dense differentiation because their locality cannot be inferred.
- Added `DetailedBalanceNetwork`, `DetailedBalanceReaction` and
  `DetailedBalanceTrajectory` over the pre-existing macrochemical balance work.
  Explicit formation chemical potentials determine every reverse scale, enforce
  cycle consistency, and produce free-energy/entropy diagnostics. Element and
  charge conservation are mandatory. An analytic Jacobian supports stiff
  integration; a separate convex free-energy stationarity solve finds positive
  equilibrium while preserving all stoichiometric conservation laws.
- Fixed near-equilibrium cancellation in the existing reversible rate with
  `expm1`. Added the offline `run_solver_thermodynamic_audit.py` runner and
  documented its API, compatibility, evidence limits and results in
  `docs/solver-thermodynamic-audit.md`.

Results:

- Reused 144 reviewed Gelain measurements and all 33 frozen retrospective
  condition/model/scenario holdouts. No parameters were refitted. 264 scored
  integration attempts retain the initial failures and explicit refinements.
- One initial BDF run failed the existing negativity guard at depletion
  (-4.80e-11 g/L). Explicit substrate atol 1e-14 g/L and max step 0.1 h reduce
  this to -2.48e-15 g/L without clipping or weakening the guard. All 132 refined
  four-solver runs pass. Maximum training-scaled solver disagreement is
  5.114e-9, versus substantial measured model-data errors; maximum difference
  from historical frozen predictions is 2.249e-7.
- Best existing primary published-equation model pooled biomass/substrate RMSE
  remains 0.4583/1.0047 g/L (glycerol), 0.7617/1.1615 g/L (cellulose); cellulose
  activities are 83.82 FPU/L and 149.72 pNPG U/L. Numerical improvement does not
  materially improve biological prediction in these cases.
- The separately labelled artificial closed cycle conserves elements to
  2.7e-15 mol/L and reaches the independently solved equilibrium (scaled
  residual 1.95e-16), with decreasing free energy and positive entropy production.
  It is software verification, never experimental evidence.
- Local output bundles under `outputs/solver-thermodynamic-audit-2026-10-03*`
  contain four inspected figures, prediction/diagnostic JSON, a thermodynamic
  CSV, software versions, input/implementation hashes and artifact checksums.

Tests added/modified: `test_solver_numerics.py`, `test_detailed_balance_network.py`,
`test_solver_audit.py`, and `test_nonideal_reversible_thermodynamics.py`. Coverage
includes analytic trajectories, a charged nonlinear catalyst reaction, independent
finite-difference gradients/Jacobians, equilibrium, zero-concentration limits,
trace-state accuracy, sparse spatial conservation, invalid inputs and solver
failure, real depletion, and held-out evidence guards. Pre-existing macrochemical
work and its tests were preserved.

Commands/results (local, not hosted CI):

- `.venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing
  --cov-report=xml`: 1,594 passed in 524.91 s; 84.82% coverage.
- Final focused run of the four files above plus `test_gelain_joint.py` and
  `test_gelain_joint_artifacts.py`, with `--cov-append`: 78 passed; 85.05%
  coverage. This covers the later research controls and six added tests;
  collection is 1,600 tests, all covered by full and final focused runs.
- `.venv/bin/python -m ruff check src tests scripts/run_*.py`: passed.
- `.venv/bin/python -m pyright --pythonpath .venv/bin/python`: zero errors.
- `.venv/bin/python -m mkdocs build --strict`: passed.
- `.venv/bin/python scripts/prepare_public_experimental_data.py --check`:
  all 19 extracts match checksum-pinned sources.
- `.venv/bin/python scripts/run_solver_thermodynamic_audit.py --output
  outputs/solver-thermodynamic-audit-2026-10-03-verified`: completed; plots inspected;
  all input, final implementation and artifact hashes verified. All four plots
  are byte-identical to the inspected figures.
- `.venv/bin/python -m build --outdir /private/tmp/fungmod-solver-dist`:
  wheel and sdist built; Twine passed both; resource check verifies all 217
  canonical resources exactly once and byte-identical. The installed wheel in
  `/private/tmp/fungmod-solver-wheel`, executed from `/private/tmp` with `-I`,
  passes network integration/equilibrium, named tolerances and entropy checks.
  An initial install saw the same version in inherited site packages and skipped;
  an explicit `--ignore-installed --no-deps` install and import-path assertion
  verified the actual built wheel.
- Final post-cleanup numerical/spatial regression: 37 passed.
- `git diff --check`: passed. No verification command remains blocked.

An initial test invocation named nonexistent `tests/test_simulation.py` and ran
no tests; actual engine tests and the full suite subsequently passed. The first
uniform-tolerance audit intentionally stopped at the BDF negativity failure;
its cause and both control settings are retained above and in the final runner.
A SciPy callable-Jacobian type-stub mismatch was resolved with a local annotation,
not by removing the Jacobian or suppressing the repository type checker.

Scientific behavior impact: additive closed ideal-dilute fixed-volume isothermal
mass-action thermodynamics plus more explicit numerical control. No thermochemical
parameters, fungal mechanism, heat/gas state, registry data, culture equation,
empirical uncertainty or biological maturity was inferred or changed. Existing
successful scalar-setting runs and import paths remain compatible. Failed partial
main-engine results now raise IntegrationError; invalid/sub-machine numerical
controls reject. The old v1 culture and inhibition research equations are unchanged.

Remaining ambiguities: missing matched formation energies, gas exchange,
calorimetry, raw culture replicates and independent validation; weakly identified
cellulose model parameters. Equilibrium requires a strictly positive initial
class; entropy at zero concentrations is unavailable. Nonideal, open-culture,
variable-temperature and spatial thermodynamic coupling are not implemented by
this network API. No extremal entropy principle supplies biological kinetics.

Risk: moderate (stricter numerical failure semantics; potential interpretation
of artificial physics tests as biology). Recommended next task: source matched
thermochemistry and gas/heat measurements, constrain a reduced culture model,
and preregister an independent raw-replicate comparison before increasing its
biological claims. No commit, push, release or deployment was requested/performed.

## THERMO-BASE-001 Conservation-Law Macrochemical Balance And Entropy Budget

Date: 2026-10-03

Status: `complete` for one bounded low-level chemistry contract. Coupling it
into configured or whole-fungus models, and any yield estimate, are `not started`.

Motivation: a user-directed step toward organism-general modelling by working at
the level every organism shares. Element conservation, charge conservation, and
the second law hold for any fungus without organism-specific measurement, so
they are implemented as a constraint layer beneath the kinetic process laws.

Changed:

- Added `src/fungal_model/chemistry/macrochemistry.py` with
  `MacrochemicalSpecies`, `MacrochemicalBalance`, `MacrochemicalSolution`,
  `MacrochemicalEntropyBudget`, and `MacrochemicalBalanceError`, exported from
  `fungal_model.chemistry`.
- `MacrochemicalBalance.solve(...)` solves every unfixed signed coefficient of
  an overall conversion from the element-plus-charge conservation matrix. It
  fails closed when conservation leaves degrees of freedom (reporting how many
  more coefficients must be fixed) or cannot be satisfied (reporting residuals).
- A solution forms the reaction Gibbs energy and enthalpy from sourced
  formation energies, and an entropy budget at a caller-supplied extent rate
  and temperature: `sigma = -delta_r G * rate / T`, split exactly into entropy
  exported as heat and entropy change of exchanged matter when enthalpies exist.
- `solve_for_reaction_gibbs(...)` solves the one extra coefficient that gives a
  stated sourced reaction Gibbs energy: zero is the reversible limit (a yield
  ceiling derived from formation energies), a negative target is a stated
  dissipation.
- A solution converts to `StoichiometricReactionMetadata`, so the existing
  static element and charge validators accept solved reactions unchanged.
- Added the capability row in `docs/capabilities.md`.

What did not change: no existing process law, solver, configured workflow,
registry record, output schema, `GibbsEnergyYieldBound`, or `FungalCouplingModel`
behaviour. No formation energy, biomass composition, yield, dissipation value,
or organism record was added. No rate is derived from thermodynamics and no
extremal principle such as maximum entropy production is used. Formation
energies are combined as given for their declared conditions with no activity,
concentration, pH, ionic-strength, or temperature correction.

Tests added: `tests/test_macrochemical_balance.py` (16 cases) covers complete
oxidation from conservation alone, a materially different charged inorganic
redox reaction, artificial growth exchange stoichiometry, acceptance by the
existing static validators, underdetermined and inconsistent balances, unknown
or scale-free fixed coefficients, missing provenance, hand-checked reaction
energies, missing conditions or formation energies, the entropy-budget identity
and units, second-law violation flagging, reversible-limit and stated-dissipation
solves, and fixed maturity. Biomass composition and all energies in the tests
are labelled artificial.

Scientific behavior impact: additive only. Callers can derive oxygen, carbon
dioxide, water, and nitrogen exchange for a stated yield instead of leaving the
unassimilated mass unresolved, and can check a conversion against the second law.

Backward compatibility: additive public chemistry API; nothing existing changes.

Remaining ambiguities: biomass elemental composition and formation energy are
organism- and condition-dependent inputs that must be sourced per case. Standard
formation energies differ from in-culture values; no transformation is applied.
The rank test uses NumPy's default singular-value tolerance.

Risk level: low for software; moderate interpretation risk if a solved balance
is read as a prediction, contained by fixed exploratory maturity, mandatory
sources, fail-closed solving, and artificial-only tests.

Recommended next task: wire the balance into `FungalCouplingModel` as an opt-in
so uptake resolves oxygen demand and carbon dioxide, water, and heat release as
explicit states, with the yield ceiling derived from sourced formation energies.

## CULTURE-BENCHMARK-002 Joint Activity Models And Scoped Validation

Date: 2026-09-28

Status: the five requested software workstreams are implemented. Empirical model
validation remains incomplete; scientific maturity is not promoted by fit quality.

Changed:

- Added source-scoped model comparison on all 144 non-initial Gelain means:
  published equations refitted only on training conditions, activity-driven
  hydrolysis alternatives and retained dry-mass observation hypotheses.
- Kept FPU and pNPG activity in distinct assay dimensions. Removed one exact
  latent-state scale symmetry from the published cellulose equations by an
  algebraic coordinate change; shared the unchanged source mass-rate kernel
  with v1. No unsupported viable/dead-cell or concentration output is emitted.
- Added generic sourced Gaussian covariance and known single-component left
  censoring, separately labelled assumed-covariance sensitivity, multi-start
  fits, rank/bound diagnostics, nuisance-reoptimized profiles and conditional
  bootstrap. Unknown SD, replicates and detection limits remain explicit.
- Added frozen model/parameter/observation/scope/criteria contracts composing the
  independent raw-replicate evaluator. Actual observation times and mappings
  are checked. Synthetic tests and evidence declarations cannot promote status.
- Added offline benchmark orchestration, input/implementation/result hashes,
  preserved predictions before scoring, all failed attempts, signed residuals,
  figures, direct dependency pins and per-model validation-readiness packets.
- Added public documentation and the active roadmap update. Preserved the v1
  results as a historical comparison rather than silently replacing them.

Recorded scientific result:

- 33 complete condition holdouts, 11 descriptive full fits, 132 starts; six
  starts fail. All folds pass independent-solver and tolerance checks, with
  maximum scaled solver difference 2.25e-7 (criterion 1e-5).
- Published equations give the lowest primary holdout loss in both families.
  Glycerol pooled biomass/substrate RMSE is 0.458/1.005 g/L. Cellulose pooled
  biomass/substrate/activity RMSE is 0.762 g/L, 1.162 g/L, 83.8 FPU/L and
  149.7 pNPG U/L. The difficult 30 g/L substrate holdout improves from v1's
  7.4446 to 1.6207 g/L; at 24 h it predicts 16.9647 vs 15.7340 measured.
- Cellulose published-model practical rank falls to 19/20 in one fold and
  profile refitting lowers the descriptive objective from 0.19135 to 0.18980.
  This model fails the predefined complexity screen despite better prediction.
  Both hydrolysis candidates fail the primary per-observable worsening screen.
- Profiles complete and both assumed-noise bootstraps converge on 20/20 draws.
  These are conditional diagnostics, never empirical confidence/coverage claims.
- Source activity differences reach 22.34 FPU/L and 19.65 pNPG U/L. Exact activity
  parity is not established; mass projection and limiting cases are verified.

Tests added/modified: generic non-biological covariance/censoring and scoped
validation tests; culture limiting cases, assay units, source projection parity,
synthetic recovery, measured-error fitting and preservation through profiles,
serialized-noise rejection, bootstrap failure handling, immutable
holdout predictions and malformed-input rejection. Existing v1 and source-intake
regressions continue to verify their contracts.

Commands/results (local; no hosted CI or publication claim):

- `.venv/bin/python scripts/prepare_public_experimental_data.py --check`: all
  19 extracts match checksum-pinned sources.
- `.venv/bin/python scripts/run_gelain_2020_joint_benchmark.py --output
  outputs/gelain-joint-v2-complete --workers 3`: completed; 33/33 numerically
  checked folds, 11 full fits, all profiles and 40 conditional bootstrap refits.
  Comparisons, profiles and bootstrap draws match the preceding independent
  runs exactly. Final input, implementation and artifact hashes match.
- `.venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing
  --cov-report=xml`: 1,521 passed in 1,174.74 s; coverage 84.67%.
- Final focused regression run on observation errors, joint models, scoped
  validation, joint artifacts, v1, public data and independent validation:
  96 passed. With `--cov-append`, reported coverage is 84.76% (80% gate).
  This covers the final measured-error profile fix and the five artifact/noise
  cases added after the full run began.
- `pytest -q tests/test_packaged_distribution.py
  tests/test_gelain_joint_artifacts.py`: 9 passed, including a new actual source
  archive build, extraction, offline 19-file verification and runner CLI check.
  Final collection is 1,527 tests: all are covered by the full and follow-up
  runs. The workstream adds 49 cases and modifies the packaging regression file.
- `.venv/bin/python -m ruff check src tests scripts/run_*.py`: passed.
- `.venv/bin/python -m pyright --pythonpath .venv/bin/python`: zero errors.
- `.venv/bin/python -m mkdocs build --strict`: passed.
- `.venv/bin/python -m build --outdir /tmp/fungmod-joint-release-dist`:
  wheel and source archive built. `python -m twine check` passed both.
  `scripts/check_built_distribution_resources.py` verifies all 217 resources
  exactly once and byte-identical to canonical data.
- Fresh `/tmp/fungmod-joint-wheel` environment installed the final wheel and
  executed from `/tmp`: all 144 observations available; 33 frozen predictions
  and scores replay with maximum absolute difference zero; all artifact hashes,
  11 readiness packets, final code hashes and error-model round trips verified.
- `git diff --check`: passed.

The source archive now includes both culture runners, the deterministic
extractor and documentation. An initial no-isolation packaging test could not
run because `wheel` was absent from the local interpreter; the test now uses
the project's isolated PEP 517 build. Two simultaneous source builds briefly
collided in setuptools' shared staging directory; the final release build ran
sequentially and passed. A process-status diagnostic was initially sandbox-denied;
its scoped read-only retry succeeded. No verification command remains blocked.

Unchanged and compatibility: existing configured model APIs, registry contents,
and scientific maturity labels are unchanged by this workstream. The v1 source
kernel refactor preserves its predictions. New research APIs, error models and
validation contracts are additive. Pre-existing uncommitted work is retained.
No release, remote push, hosted CI or human review is claimed by this entry.

Remaining ambiguities: no raw individual cultures, measured SD/covariance,
known detection limits, matched independent experiment, prespecified biological
acceptance criteria or independent domain review. Source inhibition switches
and fixed-step output still differ numerically in the activities. Media
co-substrates and retained-mass physiology are unresolved; no whole-fungus claim.
Risk: moderate for interpreting the scientific models; contained and tested
for software use. Recommended next task: reduce/constrain the cellulose model's
unsupported parameters, preregister the reduced comparison and obtain matched
independent cultures with raw replicates before attempting model validation.

## CULTURE-BENCHMARK-001 Bounded Culture Model And Condition Holdouts

Date: 2026-09-28

Status: complete for the explicitly exploratory benchmark. Independent biological
validation, empirical uncertainty and a full fungal organism model remain incomplete.

Changed:

- Added `research.gelain_culture`: unit/provenance-checked source X/S/A projection
  and a four-parameter effective Monod growth/apparent-yield/biomass-loss hypothesis.
  Equations live in package code, with source-specific logic outside generic/core.
- Reproduced all six deposited source trajectories within 9.19e-7 g/L. Kept the
  glycerol paper/deposited-code death-law discrepancy explicit: the retained tiny
  Kd changes late biomass by about 0.815 g/L at 20 g/L glycerol.
- Preserved two additional source simulation workbooks under a separate manifest
  role. Deterministic extraction now produces sixteen files, including separate
  source parameter/simulation references. None becomes experimental observations.
- Added the fixed retrospective plan and offline runner. Six whole-condition
  holdouts x two weighting choices, four starts per fit, plus two descriptive
  all-condition fits: 56 optimizer starts, two unsuccessful starts retained.
  Training-only normalization, frozen predictions before scoring, input/software
  hashes, per-observable residuals, Jacobian/bound diagnostics and figures are
  recorded under `data/benchmarks/gelain_2020/results/`.
- Held-out primary biomass RMSE spans 0.8726–2.4796 g/L; substrate RMSE spans
  0.8983–7.4446 g/L. Each improves on the weak constant-state comparator. The
  cellulose 30 g/L substrate error changes to 3.4869 with equal-g/L weighting,
  while biomass error worsens to 2.8906. This is material model/error-assumption
  sensitivity, not a useful-accuracy or validation pass.
- All twelve predictions passed DOP853 and tighter-LSODA verification (maximum
  differences 2.06e-6 and 2.02e-6 g/L respectively). Software tolerances do not
  define biological acceptance thresholds.
- Found and inspected the author's thesis. Recovered dry-mass/acid-treatment
  assay details and discussion of possible high-cellulose assay interference.
  It reports 5/40 g/L cellulose trials during estimation before their use for
  extrapolation; record that selection history, not blind source validation.
  Stored URL/hash/page evidence in `thesis_review.json`, without redistributing
  the full thesis. Individual duplicates, full SD arrays, detection limits and
  omitted condition arrays were not recovered. No author was contacted.

Unchanged and scientific behavior impact:

- Existing fungal coupling, configured engine, registry, enzyme studies and
  their numerical behavior are unchanged by this task. Earlier uncommitted
  research-integrity and data-intake work was preserved.
- This adds a source-scoped experimental hypothesis, not a mechanistic
  intracellular/oxygen/hyphal model. No activity-to-enzyme conversion, viable
  biomass assumption, physical carbon closure, confidence interval or registry
  promotion is introduced. Loss weights are explicitly not measurement SD.
- Backward compatibility is additive; existing public APIs/schemas are unchanged.
  The new study/report schema is version 1. Broader generic applicability is not claimed.

Tests added: 25 cases in `tests/test_gelain_culture_benchmark.py`, covering unit
equivalence, analytical limits, apparent-yield conservation, invalid input and
solver failures, all-source parity, explicit observation mapping, artificial
fit recovery, reproducibility, all-start failure, training-only split isolation,
freeze-before-score and recorded artifact/score integrity. Existing source-extraction
tests now also verify simulation references separately from experiments.

Commands/results:

- `.venv/bin/python scripts/prepare_public_experimental_data.py --check`: 16
  deterministic extracts verified against pinned original sources.
- `MPLCONFIGDIR=/tmp/fungmod-mpl .venv/bin/python scripts/run_gelain_2020_culture_benchmark.py --output outputs/gelain-culture-benchmark-verified`:
  all 12 retrospective folds and two descriptive fits completed; results copied
  to the preserved snapshot. The first run gave the same scientific results.
- `MPLCONFIGDIR=/tmp/fungmod-mpl .venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`:
  **1,477 passed**, 475.97 s, **84.65%** coverage (80% required). This full run
  preceded addition of the final artifact-replay test; the final focused run
  below includes that additional test. Current collection is 1,478 tests.
- `MPLCONFIGDIR=/tmp/fungmod-mpl .venv/bin/python -m pytest -q tests/test_gelain_culture_benchmark.py tests/test_public_experimental_data.py`:
  **37 passed**, including artifact replay. No refitting is required in the
  artifact regression; it recomputes predictions/scores and checks all hashes.
- `.venv/bin/python -m ruff check src tests scripts/run_*.py`: passed.
- `.venv/bin/python -m pyright --pythonpath .venv/bin/python`: 0 errors/warnings.
- `MPLCONFIGDIR=/tmp/fungmod-mpl .venv/bin/python -m mkdocs build --strict`: passed.
- `.venv/bin/python scripts/check_packaged_resources.py`, `.venv/bin/python -m build`
  and `.venv/bin/python -m twine check dist/fungmod-0.1.1-py3-none-any.whl dist/fungmod-0.1.1.tar.gz`:
  canonical staging, isolated wheel/sdist build and metadata validation passed.
- Fresh `/tmp/fungmod-culture-wheel` venv installation from the wheel (with
  dependencies resolved), followed by offline execution from `/tmp`: all six
  packaged conditions, 12 predictions/scores and artifact hashes verified. New
  NumPy 2.5.3/SciPy 1.18.1 reproduced stored scores exactly in this check;
  benchmark fitting used NumPy 2.4.6/SciPy 1.17.1, Python 3.13.11.
- Figure visually inspected: six panels, source means and holdout predictions,
  readable units/legend and explicit unavailable uncertainty. Source equation
  and thesis method/selection pages also visually checked.
- A training-only optimizer pilot exhausted its 300-evaluation cap using default
  finite differences; the explicit derivative step was fixed before holdout
  scoring and recorded in the plan. Two capped starts remain in final results.
- The initial thesis `curl -fL --max-time 50 https://research.tudelft.nl/files/69958981/PhD_Thesis_Lucas_Gelain.pdf`
  returned HTTP 403. The public repository file download succeeded. The Mendeley
  V1 web page and PDF web-reader fetches were unavailable; local V2/archive/PDF
  inspection supplied the evidence. No quality gate remained blocked.

Remaining ambiguities: domain review, assay bias/covariance, raw replicate
variation, censoring, inoculum variability, physiology behind effective loss,
cellulose accessibility/hydrolysis, and parameter identifiability without a
defensible error model. Hosted CI and independent human reproduction were not
performed. Changes remain local and uncommitted.

Risk: moderate for scientific misuse; low compatibility risk. Numerical/source
reproduction is strong, but substantial residuals prevent a predictive-biology
claim. Recommended next task: obtain domain review and matched raw measurements,
then predeclare a bounded lag/loss or hydrolysis comparison while retaining this
baseline. Do not relabel these now-inspected six conditions as blind validation.

## PUBLIC-DATA-001 Public Experiments And Paper Readiness

Date: 2026-09-28

Status: public source acquisition, reviewed extraction and local verification
complete. No model was fitted or independently biologically validated here.

Changed:

- Fetched Gelain 2020 Mendeley V2 archive, its open-access article, and Novy
  2021 Figshare secretome workbook/metadata. Preserved twelve source files
  (about 2.4 MB), URLs, licensing and SHA-256 hashes in
  `data/experiments/source_intake/manifest.json`.
- Extracted 162 source entries from six experimental culture workbooks,
  separating 144 published mean measurements from 18 initial conditions.
  The archive's `data.xlsx` outputs are simulations and are excluded.
- Added an ingestion review and six `literature_processed` datasets: twelve
  biomass/substrate series, 96 observations, for T. harzianum P49P11. No
  individual duplicates or SD arrays were available. Missing uncertainty is
  explicit; 54 h source/Methods discrepancy and nonmonotone values remain.
- Retained culture enzyme activities in FPU/L and U/L in source intake,
  without inventing a conversion to enzyme concentrations. Extracted 232
  populated secretome rows as normalized spectra, without turning endpoint
  abundance into secretion rates. Recorded the source header/count discrepancy.
- Added a deterministic, offline, checksum-verifying extraction script, tests,
  documentation and a current paper/whole-fungus roadmap. Verified JOSS's
  current public-history rule and GitHub repository creation date separately.

Unchanged: this task alters no simulation equations, rate constants, registry
biology, calibration results, prior evidence labels or public API. Earlier
RESEARCH-INTEGRITY-002 changes remain in the working tree. No research outcome,
human review, external replication, publication acceptance or organism-level
validation is claimed. Nothing was committed or pushed in this data task.

Tests added/modified: source SHA-256 failure; exact extract reproduction;
dataset units/maturity/missing errors and initial-condition exclusion; source
cell traceability and simulation exclusion; retained reversals/activity units;
secretome endpoint boundary; review and documentation contracts; explicit
reviewed-source allowlists updated.

Commands and results:

- `python scripts/prepare_public_experimental_data.py --check`: 14 extracts
  reproduced from verified source bytes.
- `pytest -q tests/test_public_experimental_data.py tests/test_literature_schema_contract.py tests/test_dataset_candidate_review.py tests/test_packaged_distribution.py tests/test_quality_config.py`:
  59 passed. An earlier run found two expected explicit source-list failures;
  the lists were updated after the new review/schema checks passed.
- `pytest -q tests/test_phase1_documentation_sync.py tests/test_public_experimental_data.py`:
  18 passed (overlaps the intake tests above).
- `ruff check scripts/prepare_public_experimental_data.py tests/test_public_experimental_data.py tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py`:
  passed.
- `python scripts/check_packaged_resources.py`: passed.
- `mkdocs build --strict --site-dir /tmp/fungmod-data-intake/site`: passed.
- `python -m build --wheel --outdir /tmp/fungmod-data-intake/dist`: passed;
  `twine check` passed. The first `--no-isolation` attempt could not build
  because the environment lacked `wheel`; the normal isolated build resolved
  that dependency and succeeded.
- Installed the built wheel under `/tmp/fungmod-data-intake/installed` with
  `pip --no-deps`, then loaded all six new datasets from `/tmp` with the wheel
  first on PYTHONPATH: 96 observations and the source manifest verified. This
  checks wheel contents using the existing scientific dependencies, not a
  completely fresh dependency environment.
- `git diff --check`: passed. The full numerical suite was not rerun for this
  data/docs-only slice; preceding numerical quality results remain recorded
  under RESEARCH-INTEGRITY-002. Hosted CI has not run on these uncommitted changes.

Access limitations: ordinary Mendeley HTTP requests returned 403; its normal
browser download succeeded. A further PeerJ 8792 supplementary dataset could
not be fetched (direct requests 403, PMC browser challenge, Europe PMC
supplementary endpoint 502). Its values were not ingested. Two exploratory
file reads initially used nonexistent filenames and were corrected using
repository file discovery; no required verification remains blocked.

Scientific impact: additional empirical inputs, not changed predictions.
Backward compatibility: existing APIs and datasets unchanged; distribution
includes the new source/data assets. Risk: low software risk, moderate
scientific interpretation risk due to missing errors and assay mapping.
Remaining ambiguities: raw duplicate availability, source validation-condition
data, source sampling/count discrepancies, assay observation operators and
documented public-history start date. Recommended next task: one bounded
T. harzianum culture benchmark with reviewed observation mapping, followed by
replicate recovery and frozen predictive tests. See `docs/paper-readiness.md`.

## RESEARCH-INTEGRITY-002 Export Fidelity And Research Diagnostics

Date: 2026-09-28

Status: software implementation and local quality gates complete.
Independent empirical validation remains blocked on suitable external data.

Changed:

- Encoded explicit SBML numeric unit conversions for parameter/state expressions
  and reaction contributions. Equivalent per-minute/per-second and molar/millimolar
  inputs reproduce native trajectories; heterogeneous compatible state units
  also preserve output magnitudes. Parameter records retain original units.
- PEtab exports only training observations into the estimation problem, writes
  validation and unused holdout observations separately, and records split/noise
  policy metadata. Unknown/zero/nonfinite noise scales fail before writing.
  Added bounds checks, collision-safe parameter identity mapping and packaged
  example resolution outside the checkout.
- Corrected three thermodynamic scalar conversions rejected by CI's Pyright
  1.1.414 and pinned that checker version in the development dependencies.
- Moved both exploratory research runners onto a shared unit-aware progress
  integrator; its inhibition denominator is also used by the configured modifier.
  Source/hypothesis rationale and stoichiometry are explicit. Exponential activity
  loss remains an exploratory mathematical hypothesis. FD-008 is resolved for
  duplication, without promoting the hypothesis into registered biology.
- Added grid profile likelihood with fixed explicit Gaussian observation scales,
  local nuisance-parameter reoptimization, failed-point records, and diagnostics
  for a better optimum than the reference fit. Configured calibration profiles
  training data only and saves reports in optimizer metadata. No automatic
  confidence bounds or global identifiability verdicts are emitted.
- Added checksum-bound prediction freezing and independent-data scoring without
  refitting. The evidence gate requires sourced criteria, raw replicate means,
  positive experimental uncertainty and preparation/independence declarations.
  Synthetic tests require opt-in and cannot set empirical criteria met.
- Corrected a related configured-calibration defect: uncertainty magnitudes now
  use their declared uncertainty units before conversion to observation units.
- Documented APIs, raw-replicate intake, boundaries, migration requirements and
  capability status. No preparation-matched independent dataset was supplied.
  A targeted lookup of the Alvarez-Gonzalez paper and its indexed supplements
  found the published curves/parameter tables, but did not establish availability
  of suitable independent raw replicates; no data were invented or relabelled.

Tests added/modified: mixed-unit SBML trajectory parity; PEtab split/holdout,
missing-noise, identifier collision and outside-checkout regressions; configured
uncertainty-unit/profile integration; shared progress conservation for an
artificial 1:1 system and existing 2:1 source parity; analytical/flat/failing
profile curves; frozen-artifact, raw replicate, preparation and uncertainty
validation failures; documentation and tooling contracts.

Verification (artifacts under `/tmp/fungmod-improvements/`):

- Focused standards/thermodynamics group: 47 passed.
- Existing research-runner guardrails after consolidation: 13 passed.
- Profiles/shared progress/provenance-backed inhibition: 28 passed.
- Independent validation/configured calibration/standards integration: 45 passed.
- Final PEtab/quality/independent validation follow-up: 28 passed.
- Ruff and pinned Pyright: passed (zero type errors/warnings).
- Strict MkDocs and deterministic release notebook checks: passed.
- Wheel and source distribution build, Twine checks and canonical resource checks:
  passed; wheel contains 82 exact canonical resources.
- Final rebuilt-wheel smoke outside the checkout: passed. Imported the new APIs,
  ran shared progress integration and exported the packaged PEtab example with
  four training rows and separately preserved validation. This smoke used the
  installed wheel plus existing dependencies, not fresh dependency resolution.
- Full coverage command:
  `MPLCONFIGDIR=/tmp/fungmod-improvements/mpl XDG_CACHE_HOME=/tmp/fungmod-improvements/cache .venv/bin/python -m pytest -q --cov=fungal_model --cov-report=term --cov-report=json:/tmp/fungmod-improvements/coverage.json`.
  Result: **1438 passed in 756.26 seconds; 84.48% coverage**, above the 80% gate.
  Three PEtab regressions added after collection passed in the final 28-test
  follow-up; current collection contains 1441 tests. The last path/identifier
  corrections were also verified in that fresh targeted run, pinned type check,
  rebuilt wheel, and outside-checkout smoke. No full-suite failures or skips.
- Final roadmap/instruction/documentation contracts: 21 passed.
- Both cross-source and mechanism-hypothesis CLI runs: passed under the shared
  integration contract; report outputs remain under the temporary artifact root.
- A first targeted test command referenced nonexistent
  `tests/test_enzyme_inhibition.py` and collected no tests; corrected to
  `tests/test_provenance_backed_inhibition_laws.py`, which passed in the group above.
- Optional process inspection with `ps` was unavailable (`zsh: operation not
  permitted: ps`); test execution/output remained accessible through its existing
  session and log. No required quality command is blocked.
- An initial outside-checkout PEtab wheel smoke exposed a real path-resolution
  failure. It was fixed and covered by a regression before rebuilding the wheel.

What did not change: observations, source snapshots, production registry values,
base configured kinetic equations, existing user-owned outputs, package release
version, or empirical validation status. No commit/push or publication performed
in this implementation pass.

Scientific behavior impact: export trajectories now respect input units;
PEtab no longer fits on validation/holdout responses; missing noise is explicit;
calibration weights change correctly for differing uncertainty units. Native
inhibition arithmetic is shared without changing the equation. New profiles and
validation reports are conditional diagnostics, not new biological evidence.

Backward compatibility: public entry points remain; PEtab adds separate tables
and metadata and now rejects missing/zero uncertainty and invalid bounds.
Affected old exports must be regenerated. Profile and frozen-prediction APIs
are additive; optional profile metadata is added to calibration reports.

Remaining ambiguity and risk: moderate numerical/export compatibility risk,
contained by analytical, unit-invariance and failure-path tests. Independent
preparation identity, experimental chronology and a justified noise model need
external evidence. Profile grids use local optimization and cannot prove global
identifiability. Frozen hashes prove artifact identity, not empirical truth.

Recommended next task: supply an archived prospective plan and preparation-matched
raw training/independent validation replicates with analytical uncertainty, then
run the frozen-prediction workflow. Remote CI must run on the new changes after
publication to the repository; only the equivalent local gates are verified here.

## RESEARCH-ANALYSIS-001 Correctness And Evidence Boundaries

Date: 2026-09-11

Status: complete for the confirmed software and reporting defects; final quality
gate results are recorded below. Independent biological validation remains
pending and was not replaced by software tests.

Changed:

- Removed the cross-source study's transfer of the PersiBGL1 pNPG `K_m` to
  cellobiose. Cellobiose `K_m` is now an explicitly exploratory fitted parameter;
  omitted substrate inhibition is an explicit hypothesis rather than a large
  numerical stand-in constant.
- Added an optional `fitted_parameter_count` to model/dataset comparison.
  Reduced chi-square is emitted only with a known count, complete scales, and
  positive `n - p`. Configured calibration passes the training parameter count
  and zero for held-out observations. Missing counts remain unknown.
- Preserved observation-shaped uncertainty through weighting, unit conversion,
  and train/validation slicing. Partial or invalid uncertainty is rejected;
  fully unknown uncertainty stays unweighted with a warning. Added warnings for
  untruncated approximate intervals extending outside optimizer bounds.
- Added deterministic multiple-start fitting to the cross-source runner,
  including the feasible base model in extended-model optimization. Both
  research hypothesis runners check convergence/integration and reference
  trajectory consistency. They report descriptive residuals and numerical
  diagnostics, not confirmation, falsification, or biological identifiability.
- Blocked stage-2 held-out predictions after unsuccessful calibration. Removed
  synthetic-only wording from shared caller-supplied initial guesses and bounds.
- Reconciled the seven-series inventory, literature-calibration guidance,
  superseded mechanism claims, active roadmap status, and output migration notes.
  Lint and Pyright now include `scripts/run_*.py`; existing duplicate study rate
  laws are explicitly contained as `FD-008`, with trajectory and failure tests.

Tests added/modified: comparison tests cover explicit/unknown/exhausted degrees
of freedom; calibration tests cover an analytical heteroscedastic fit, unit
conversion and noncontiguous uncertainty slicing, invalid scales, unchanged
untruncated intervals with warnings, and configured weighting. New
`test_cross_source_structural_study.py` and `test_research_runner_guardrails.py`
cover complete source-model trajectory parity, the pNPG exclusion, nested-fit
regression, solver and optimizer failures, stage-2 failure gating, and bounded
JSON conclusions. Quality-contract tests cover research-runner gates and
documentation. Existing literature metadata tests remain active.

Verification:

- Focused scientific/runner/documentation regression group: 98 passed.
- Final calibration and quality-contract tests, including the additional
  interval regression: 20 passed.
- `.venv/bin/python -m ruff check src tests scripts/run_*.py`: passed.
- `.venv/bin/python -m pyright --pythonpath /Users/felix/Documents/GitHub/FungMod/.venv/bin/python`:
  passed, zero errors/warnings.
- `.venv/bin/python -m mkdocs build --strict --site-dir /tmp/fungmod-fixes/site`:
  passed.
- Cross-source, stage-2 calibration, and mechanism-hypothesis CLI runners:
  passed with new outputs under `/tmp/fungmod-fixes/`. Regenerated stage-2
  training degrees of freedom are 5 (four parameters) and 6 (three parameters);
  corresponding reduced chi-square values are 0.0854527 and 0.0711714.
- Packaged-resource staging identity and deterministic release-notebook checks:
  passed.
- `.venv/bin/python -m build --outdir /tmp/fungmod-fixes/dist` and
  `.venv/bin/python -m twine check /tmp/fungmod-fixes/dist/*`: passed for the
  wheel and source distribution. Built-wheel resource verification confirmed
  82 canonical resources with identical bytes.
- Installed the wheel without dependencies into `/tmp/fungmod-fixes/wheel-installed`
  and ran Python from `/tmp` using that package plus existing environment
  dependencies. Verified the wheel import path, corrected weighted residuals,
  and a seeded two-sample registry virtual experiment outside the checkout.
  This was not a fresh dependency-resolution test or a remote CI run.
- Full-suite command:
  `MPLCONFIGDIR=/tmp/fungmod-fixes/mpl XDG_CACHE_HOME=/tmp/fungmod-fixes/cache .venv/bin/python -m pytest -q --cov=fungal_model --cov-report=term --cov-report=json:/tmp/fungmod-fixes/coverage.json`.
  Result: **1401 passed in 687.93 seconds; 84.46% coverage**, exceeding the 80%
  gate. The additional interval regression added after this run's collection
  passed in the final 20-test calibration/quality check above. No required
  local command remained blocked. Full output: `/tmp/fungmod-fixes/full-tests.log`.

What did not change: literature observations, source snapshots, production
registry values, public configured kinetic laws, empirical validation status,
and existing user-owned output folders. No new biological mechanism or dataset
was added, and no scientific publication was performed.

Scientific behavior impact: affected study parameter estimates and statistics
change; heterogeneous uncertainty now changes calibration weights correctly.
Base configured simulation equations are unchanged. Improved numerical fitting
does not resolve the empirical panel-B discrepancy or establish a mechanism.

Backward compatibility: existing comparison calls remain callable, but reduced
chi-square now requires explicit degrees-of-freedom context. Partial uncertainty
that previously inherited an average now fails. Research summaries use schema
`2.0.0` and remove old mechanism/identifiability verdict fields; regenerate old
study artifacts. Scalar low-level residual scales remain supported.

Remaining ambiguity and risk: moderate numerical/interpretation risk from
changed estimation and reporting semantics. Digitization resolution is not
experimental uncertainty, source-unit ambiguities remain unresolved, local
optimizer diagnostics do not prove identifiability, and arbitrary whole-fungus
prediction remains unsupported. `FD-008` records remaining study-law duplication.

Recommended next task: obtain preparation-matched raw replicate observations
and analytical uncertainty for one enzyme/substrate system, predeclare fit and
predictive criteria, and evaluate untouched conditions or independent experiments.
Integrate any selected extension through the package under the biology rule.

## CALIBRATION-EVIDENCE-001 Publication-Oriented Evidence Audit

Date: 2026-08-01

Status: `complete` for a bounded software audit; publication-grade biological
calibration remains `blocked` on independent evidence and external review.

Completed in this pass: added an audit over existing least-squares results with
explicit analysis-plan, dataset, validation-relationship, residual-scale, and
model evidence; provenance-bearing training-density, error-ratio, and residual-
correlation criteria; rank, covariance, interval, and bound diagnostics; exact
machine-readable blockers; and deterministic JSON/Markdown output. A software
pass and publication authorization are separate fields, and authorization is
always false.

Tests added: `tests/test_calibration_evidence.py` verifies an artificial fit can
pass the declared software criteria without authorizing publication, while
reused training data, missing evidence, rank/covariance/interval failures, and
unsourced criteria block or fail explicitly.

What did not change: no parameter was fit to a bundled biological dataset, no
default adequacy threshold was introduced, no source was labelled independent
without evidence, and no publication, validation, or transferability claim was
made.

Scientific behavior impact: none on model equations or existing calibration;
the additive audit makes the evidence boundary machine-readable.

Backward compatibility: additive calibration API and documentation only.

Remaining ambiguity: study-specific criteria and publication fitness require a
prospective plan and external scientific judgement. The existing same-source
time-course comparison lacks independent validation and experimental
uncertainty.

Risk level: low numerical risk and moderate interpretation risk, contained by
explicit criteria, exact blockers, and a fixed false publication-authorization
field.

Recommended next task: acquire an independently sourced experiment with raw
replicate observations and analytical uncertainty before fitting a biological
case.

## UNCERTAINTY-GLOBAL-001 Variance-Based Global Sensitivity

Date: 2026-08-01

Status: `complete` for independent provenance-bearing input distributions and
one scalar unit-aware output; broader uncertainty analysis remains `partial`.

Completed in this pass: added two-independent-matrix pick-freeze sampling,
published Saltelli first-order and Jansen total-order estimators, optional
equal-tailed row-bootstrap intervals, deterministic seed and exact model-
evaluation reporting, total-order ranking, JSON export, unit checks, and exact
design-row failure reporting. Finite-sample estimates remain un-clipped so
convergence problems are not hidden.

Tests added: `tests/test_global_sensitivity.py` checks the analytical Ishigami
first- and total-order indices, bootstrap intervals, exact evaluation count,
determinism, JSON export, zero-output-variance failure, exact model-failure
location, duplicate-symbol rejection, and visible un-clipped estimates.

What did not change: no empirical uncertainty distribution, biological
parameter, calibration, validation dataset, posterior inference, correlated-
input estimator, second-order index, quasi-random design, or surrogate model
was added.

Scientific behavior impact: callers can quantify variance contributions for a
scalar prediction when they explicitly supply independent, sourced parameter
distributions. The artificial benchmark verifies software behavior only.

Backward compatibility: additive public uncertainty API only.

Remaining ambiguity: convergence and sample-size adequacy are model-specific;
reported bootstrap intervals quantify Monte Carlo resampling variability, not
empirical parameter uncertainty or biological confidence.

Risk level: moderate interpretation risk, contained by provenance validation,
fail-closed evaluation, method citations, exact design metadata, and no
clipping.

Recommended next task: acquire a defensible joint empirical parameter
distribution before interpreting global indices for a biological system.

## THERMO-003 Explicit Nonideal Reversible Flux

Date: 2026-08-01

Status: `complete` for one bounded low-level reaction contract; broad THERMO-003
and configured nonideal/reversible assembly remain `partial`.

Completed in this pass: added explicit constant activity-coefficient records,
nonideal activity/Q/Gibbs/affinity/equilibrium diagnostics, and a signed local-
detailed-balance rate wrapper using
`r_reverse/r_forward = exp(delta_g/RT)`. Every participant requires exactly one
positive sourced coefficient; standard Gibbs energy, temperature, gas constant,
standard concentration, activity floor, equilibrium tolerance, and sources are
all explicit.

Tests added: `tests/test_nonideal_reversible_thermodynamics.py` verifies the
exact `RT ln(gamma_product/gamma_reactant)` Gibbs shift, zero net flux at a
nonideal equilibrium, forward and reverse directions, conservation and
relaxation to equilibrium in the generic ODE engine, and failure on missing or
nonpositive coefficients. Existing configured thermodynamic gates remain green.

What did not change: configured thermodynamic assembly still uses its ideal-
dilute forward-rate blocking contract. No activity coefficient is inferred;
there is no Debye-Huckel/Davies/Pitzer model, state-dependent ionic strength,
activation barrier, coupled-network optimization, electrochemical gradient,
dynamic temperature, biological parameter, or empirical validation.

Scientific behavior impact: callers can opt into a signed reversible rate for
one reaction using their own sourced constant activity coefficients and one-way
kinetic scale. Applicability to an empirical composite rate law is not assumed.

Backward compatibility: additive low-level chemistry APIs; existing configured
and low-level thermodynamic behavior is unchanged.

Remaining ambiguity: local detailed balance constrains the reverse/forward
ratio but does not determine the forward activation kinetics or prove an
empirical composite law is elementary.

Risk level: moderate scientific-use risk, contained by exact explicit inputs,
provenance checks, no inference, equilibrium tests, and separate opt-in API.

Recommended next task: add a configured schema only after a real reaction has
sourced activity coefficients and defensible forward/reverse kinetic meaning.

## SPATIAL-ND-001 Uniform Cartesian 2D/3D Reaction-Diffusion

Date: 2026-08-01

Status: `complete` for the bounded uniform-grid numerical scope; broad spatial
fungal morphology remains `partial`.

Completed in this pass: added explicit 2D/3D Cartesian grids, per-axis no-flux,
periodic, and fixed-value boundary pairs, finite-volume Laplacians and spatial
integrals, plus a method-of-lines reaction-diffusion engine that reuses generic
unit-aware local `Reaction` objects. Field shapes, boundary/diffusion mappings,
axis provenance, coefficient units, nonnegativity, and local reaction output
shapes all fail closed.

Tests added: `tests/test_reaction_diffusion_nd.py` covers exact no-flux discrete
conservation in 2D, an analytical discrete periodic Fourier-mode decay,
3D conservation/smoothing, zero-diffusion agreement with independent local
ODE behavior, and rejection of 4D/implicit-boundary configurations. Existing
1D tests remain green.

What did not change: no irregular/curvilinear mesh, advection, porous-medium
closure, adaptive refinement, moving boundary, colony morphology, spatial
secretion biology, empirical spatial dataset, calibration, or validation.

Scientific behavior impact: callers can now run explicit uniform 2D and 3D
reaction-diffusion software experiments; the new tests verify numerical
contracts only and introduce no biological parameter or geometry claim.

Backward compatibility: additive transport APIs; the 1D engine is unchanged.

Remaining ambiguity: cell-centered fixed-value faces use the existing half-cell
finite-volume convention; nonlinear stiffness and mesh-convergence adequacy
remain case-specific responsibilities.

Risk level: moderate numerical-use risk, contained by exact shapes, units,
boundary declarations, conservation tests, and an analytical eigenmode test.

Recommended next task: add mesh-refinement/convergence studies for a real
spatial dataset before interpreting local gradients scientifically.

## WHOLE-FUNGUS-COUPLING-001 Minimal Well-Mixed Coupling

Date: 2026-08-01

Status: `complete` for the bounded exploratory composition; organism-level
fungal physiology remains `partial`.

Completed in this pass: added `FungalCouplingModel`, which composes a caller-
supplied sourced extracellular degradation reaction with existing secretion,
enzyme decay, secretion cost, assimilable-product uptake, biomass-yield, and
maintenance laws. Assembly requires a matching enzyme capability, exactly one
matching assimilable-product record, complete sourced fungal parameters,
non-overlapping additional parameters, distinct states, and the fixed
`exploratory_software_tested` maturity.

Tests added: `tests/test_fungal_coupling.py` covers the complete artificial
trajectory, zero-biomass limiting case, missing enzyme capability, explicitly
non-assimilable product, parameter collision, and false-maturity rejection.

What did not change: no organism-specific parameter, production registry
record, intracellular metabolic network, oxygen state, transporter, regulation,
morphology, toxicity, spatial secretion, empirical calibration, or organism-
level validation was added.

Scientific behavior impact: existing minimal fungal rate laws can now run in a
single explicit well-mixed system instead of requiring callers to hand-compose
the reactions. All biological applicability still comes from caller-supplied
evidence and parameters.

Backward compatibility: additive public API only.

Remaining ambiguity: the open-system mass not converted to biomass is not
resolved into respiration products, and the lumped secretion-cost coefficient
does not represent intracellular resource allocation.

Risk level: moderate interpretation risk, contained by fixed exploratory
maturity, exact capability gates, source checks, and artificial-only tests.

Recommended next task: add a provenance-backed organism/culture dataset only
after secretion, uptake, yield, maintenance, and oxygen measurements are all
available for the same experimental system.

## FD-007 Canonical Build-Time Resource Staging

Date: 2026-08-01

Status: `complete`; the tracked wheel-resource mirror is removed.

Completed in this pass:

- Added a deterministic setuptools `build_py` hook that stages the canonical
  repository `data/` and `data_registry/` trees into wheel `_resources/`.
- Added source-distribution manifest entries so an sdist can build the same
  wheel without a repository checkout.
- Changed source/editable installs to resolve the canonical roots directly,
  while installed wheels continue to use bounded package-owned paths.
- Replaced source/mirror parity checks with clean temporary staging and exact
  relative-path/SHA-256 comparison, then removed all 69 mirrored tracked files.

Tests added or modified: release-configuration, packaged-distribution,
literature-dataset, and architecture-debt tests now enforce the single-source
layout. Distribution gates build an sdist and wheel, inspect packaged resource
identity, and run the existing installed-wheel smoke outside the checkout.

What did not change: no scientific record, parameter, model equation, solver,
registry content, configured result, or public resource-helper signature
changed.

Scientific behavior impact: none; canonical and built resource bytes remain
identical.

Backward compatibility: public resource paths and writable-copy guidance are
unchanged. Private source-tree paths under `src/fungal_model/_resources/` are
removed; callers must use the documented helpers or canonical roots.

Remaining ambiguity: reproducible archive timestamps still depend on the
standard Python build frontend and its environment; resource content and paths
are deterministic and identity-checked.

Risk level: low scientific risk and moderate packaging risk, contained by
sdist-to-wheel and isolated-wheel verification.

Recommended next task: publish and install v0.1.1 from PyPI after the pending
Trusted Publisher is registered.

## BIO-003 Coupled Substrate Transglycosylation

Date: 2026-08-01

Status: `complete` for the bounded coupled hydrolysis/substrate-
transglycosylation process and one provenance-backed fungal enzyme
configuration; broad BIO-003 remains `partial`.

Completed in this pass:

- Added a generic two-branch process law with the shared denominator
  `Km_h + S + S^2/Km_t`, explicit enzyme state, and branch-specific turnover.
- Made product maps own the distinct one-substrate hydrolysis and two-substrate
  transfer stoichiometries; the core process contains no fungus, enzyme, or
  substrate-specific branch.
- Added a machine-checkable biology proposal and an installed
  *Phanerochaete chrysosporium* BGL1B cellobiose configuration using published
  hydrolysis and transglycosylation point estimates.
- Exposed the configured law, equation, parameters, source, maturity, and
  limitations in standard configured-output metadata.

Tests added or modified:

- Added unit, dimension, low/high-substrate, conservation, and failure-mode
  tests for the generic process.
- Added proposal, resource, exact-parameter, configured-run, metadata, and
  glucose-equivalent balance tests for the fungal enzyme configuration.
- Extended the process-factory library and active roadmap status contracts.

What did not change: no transfer-product linkage was inferred, no transfer-
product re-hydrolysis, multiple acceptors, whole-fungus growth, secretion,
uptake, biomass, transport, regulation, calibration, empirical validation, or
production applicability was added.

Scientific behavior impact: source-backed initial-rate hydrolysis and
substrate-transglycosylation branches can now compete in configured virtual
experiments. The installed trajectory uses an explicit unresolved
trisaccharide-equivalent pool and FungMod-selected enzyme dose/time grid, so it
is exploratory rather than a reconstruction of a source observation.

Backward compatibility: additive process type, configuration, product maps,
metadata fields, documentation, and tests. Existing process behavior and
output columns are unchanged.

Remaining ambiguity: the selected point estimates do not establish transfer-
product time-course behavior, product distribution, parameter uncertainty, or
whole-organism applicability.

Risk level: moderate scientific-interpretation risk, contained by a required
primary source, fixed maturity label, explicit unresolved product pool, and
failure-closed configuration checks.

Recommended next task: find an independent transglycosylation product time
course with defined analytical uncertainty before fitting or validation.

## VALIDATION-DATA-001 Provenance-Matched Time-Course Comparison

Date: 2026-08-01

Status: `complete` for the bounded first same-source, no-calibration comparison;
independent validation remains unavailable.

Completed in this pass:

- Added a configured Alvarez-Gonzalez 2022 cellobiose-hydrolysis case using the
  paper's exact Model 3 combined substrate and double competitive product-
  inhibition law and point estimates.
- Derived `Vmax=19.72544 mM/min` transparently from the reported
  `kcat=333.2 micromole/min/mg` and `59.2 mg/L` enzyme dose.
- Added `scripts/run_literature_time_course_comparison.py`, which persists the
  configured-model bundle and generic comparison artifacts including
  `model_comparison.csv`, residuals, metrics, snapshots, mappings, validation
  JSON/Markdown, and figures.
- Compared without FungMod fitting: nine points, RMSE approximately
  `1.07877 mM`, with glucose produced at explicit 2:1 stoichiometry.

Tests added or modified:

- Added `tests/test_literature_time_course_comparison.py` for exact source
  parameters, no-calibration scope, executable installed-resource config,
  numerical comparison, conservation, and complete persisted bundles.
- Extended generic comparison tests for machine-readable comparison rows and
  bounded Markdown validation reporting.
- Updated active phase-status contracts.

What did not change: no parameter fitting, independent validation, whole-fungus
model, organism identity, source parameter uncertainty, or experimental error-
bar interpretation was added.

Scientific behavior impact: one new generic combined-inhibition modifier now
supports the exact published denominator, and one source-specific exploratory
configuration uses it. The model is limited to the selected commercial enzyme
preparation and assay.

Backward compatibility: additive modifier/configuration, output artifacts,
script, documentation, and tests. Existing comparison artifacts remain and the
new CSV/Markdown files are additive.

Remaining ambiguity: the commercial formulation's organism and fitted-
parameter uncertainties are unstated; plotted error bars are not defined. The
0.6 mM values are digitization resolution only, so chi-square fields are not
experimental goodness-of-fit evidence.

Risk level: moderate scientific-interpretation risk, contained by exploratory
maturity, explicit scope, no refitting, and validation disclaimers.

Recommended next task: acquire an independent or held-out time course with
defined experimental uncertainty before making validation or generalization
claims.

## VALIDATION-DATA-001 First Literature Time Course Ingestion

Date: 2026-08-01

Status: `partial`; first source-backed dataset ingested, provenance-matched
model comparison pending.

Completed in this pass:

- Added a nine-point literature-raw cellobiose concentration time course from
  Alvarez-Gonzalez et al. (2022), DOI `10.3390/catal12010080`, Supplementary
  Figure S1A's 20 g/L filled-square free-enzyme series.
- Recorded the source PDF checksum, exact figure/series, sampling times, assay
  conditions, rendered axis calibration, marker-centre pixels, conversion,
  extraction software/date, exclusions, and a conservative 0.6 mM
  digitization-resolution estimate.
- Kept the commercial preparation's organism unknown because the 2022 source
  does not state it directly, and separated digitization error from unavailable
  experimental uncertainty.
- Updated the active data contract and validation status from blocked
  ingestion to partial comparison work.

Tests added or modified:

- Added `tests/test_literature_time_course_dataset.py` for both literature and
  runtime dataset schemas, exact observations, scope labels, reproducible pixel
  conversion, and packaged-resource identity.
- Updated literature-directory and active-status contract tests.

What did not change: no process law, parameter, solver behavior, calibration,
model comparison, residual table, validation report, organism identity, or
whole-fungus claim was added.

Scientific behavior impact: none. This is observation ingestion only. The
dataset may support a bounded no-calibration comparison after the paper's
combined inhibition law is implemented exactly.

Backward compatibility: additive dataset, documentation, and tests only.

Remaining ambiguity: source error bars are visible but their statistic is not
defined, and the commercial formulation's biological source is unstated. The
stored uncertainty is digitization resolution only.

Risk level: moderate scientific-interpretation risk, contained by raw maturity,
unknown organism metadata, explicit extraction provenance, and no validation
claim.

Recommended next task: implement the publication's exact combined substrate
and double product-inhibition law, then generate a provenance-matched
comparison bundle without fitting.

## SHOWCASE-001 Five Purified Fungal Beta-Glucosidases On Cellobiose

Date: 2026-07-31

Status: `complete` in the current checkout for one in-depth, installed-package
notebook covering five literature-reported purified-enzyme source cases.

Completed in this pass:

- Added
  `data/showcases/five_fungal_beta_glucosidases.yml` with five matched 50 °C,
  pH 5 parameter rows attributed to Bohlin et al. (2010) through the open
  Teugjas and Väljamäe (2013) Table 5 transcription.
- Added the deterministic
  `notebooks/examples/22_five_fungal_beta_glucosidases.ipynb`.
- The notebook generates inspectable configured models for purified
  beta-glucosidases sourced from *Aspergillus fumigatus*,
  *Chaetomium globosum*, *Emericella nidulans*, *Neurospora crassa*, and
  *Penicillium brasilianum* on dissolved cellobiose.
- Every case uses the same generic homogeneous Michaelis-Menten process,
  provenance-bound competitive glucose-inhibition modifier, explicit 2:1
  glucose stoichiometry, assay context, 10 mM starting cellobiose, and
  explicitly assumed 10 nM standardized enzyme dose.
- Added matched no-inhibition counterfactuals, conditional trajectory and
  threshold summaries, figures, validation/conservation/solver audits, normal
  per-run manifests, and a cross-case showcase manifest.
- Added docs and release-note coverage that distinguishes purified-enzyme
  source labels from whole-fungus models and blocks organism ranking.

Tests added or modified:

- Added `tests/test_fungal_beta_glucosidase_showcase.py` for exact five-row
  parameter transcription, source identity, units, maturity, stoichiometry,
  scenario assumptions, and limitation wording.
- Extended `tests/test_release_notebooks.py` for deterministic generation,
  public configured-workflow use, full execution, counterfactual coverage,
  provenance, and no-shortcut/no-whole-fungus guardrails.

What did not change: no generic/core equation, solver, output schema,
scientific-mode admission rule, production registry record, whole-fungus
physiology, culture protocol, empirical time-course dataset, calibration, or
validation claim was added.

Scientific behavior impact: five new exploratory configured scenarios expose
existing homogeneous Michaelis-Menten, competitive inhibition, and
stoichiometric product behavior with literature-reported parameters.
Transglycosylation, enzyme inactivation, preparation effects, secretion,
uptake, growth, transport, and model discrepancy remain unrepresented.
Parameter uncertainty remains explicit as unavailable.

Backward compatibility: additive packaged data, notebook, tests, and
documentation only; existing APIs, configs, registry resolution, output
schemas, and numerical behavior are unchanged.

Remaining ambiguity: the open transcription attributes the selected rows to
the primary comparative study, but no uncertainty values were transcribed.
Conditional scenario comparisons are allowed under the matched setup;
organism or real-preparation ranking remains blocked.

Risk level: low-to-moderate. Existing numerical laws are unchanged; the main
risk is overinterpreting reduced purified-enzyme trajectories as organism
performance, which the data, notebook, tests, and docs explicitly prohibit.

Recommended next task: ingest empirical cellobiose/glucose time courses for
one purified enzyme through the existing validation-data review workflow, or
implement and source a generic transglycosylation mechanism before expanding
the comparative claim.

## PUBLIC-RELEASE-001 Installable Package, Documentation, And Full Notebooks

Date: 2026-07-30

Status: `complete` in the current checkout for the first public alpha
distribution and documentation surface.

Completed in this pass:

- Renamed the unpublished distribution from `fungal-model` to the available
  PyPI project name `fungmod` at version `0.1.0`, while retaining the
  `fungal_model` implementation namespace and adding a `fungmod` convenience
  namespace.
- Added complete Python package metadata, MIT license text, project URLs,
  supported Python classifiers, notebook/docs extras, and build/twine tooling.
- Added immutable wheel-packaged mirrors of the registry, frozen SABIO-RK
  source evidence, and example data/configs, plus public bounded path helpers
  and installed-wheel path resolution.
- Added an artificial, framework-labelled configured example that exercises
  dynamic reaction quotient/Gibbs evaluation, required electron-balance
  binding, native solver-time forward-rate blocking, conservation,
  static-condition entropy-rate diagnostics, solver metadata, and output
  manifests without adding biological evidence.
- Added deterministic full notebooks
  `20_zero_to_complete_virtual_experiment.ipynb` and
  `21_advanced_capabilities.ipynb`, covering zero-to-report and
  provenance-to-thermodynamics workflows through public APIs.
- Added a strict MkDocs Material site and Read the Docs v2 configuration with
  install, quickstart, concepts, output reference, notebooks, configured-model
  tutorial, capability map, scientific-integrity guidance, API reference, and
  release notes.
- Added CI/release contracts for notebook execution, documentation builds,
  wheel/sdist checks, isolated installation smoke, and PyPI Trusted
  Publishing.

Tests added or modified:

- Added `tests/test_packaged_distribution.py` for namespace/version,
  resource-drift, path-containment, non-checkout registry/config execution,
  and frozen-source discovery contracts.
- Added `tests/test_release_notebooks.py` for deterministic notebook
  generation, public-API/no-shortcut guardrails, scientific-scope wording, and
  full cell execution.
- Added release/docs/package contract assertions and CI jobs.

What did not change: no production biological record, mechanism law, solver
equation, empirical dataset, calibration result, scientific-mode eligibility,
or validation claim was added. The dynamic thermodynamic showcase uses
artificial testing inputs and existing implemented behavior only.

Scientific behavior impact: no existing scientific behavior changed. The
default registry and example assets can now be located after wheel
installation; advanced examples expose already implemented mechanics under
explicit framework-benchmark labels.

Backward compatibility: the `fungal_model` import namespace remains supported.
The distribution name change affects only installation metadata and is safe
because neither `fungmod` nor `fungal-model` had an existing PyPI release at
the audited time. Relative repository data paths retain their current
behavior; packaged fallback occurs only for known shipped `data/` and
`data_registry/` assets when the relative path does not exist.

Remaining ambiguity and risk: Read the Docs project import and first PyPI
Trusted Publisher registration are provider-owned setup gates. The package
resource mirror is byte-checked against repository data and recorded as
contained debt in `ARCHITECTURE_DEBT.md`.

Risk level: medium release/process risk, low scientific-behavior risk.

Recommended next task: after the release artifacts, PyPI installation, and
hosted documentation are verified, select a new roadmap slice only by explicit
user direction.

## PR-59 Final PRODUCT-001 Integration

Date: 2026-07-30

Status: `complete` in the current checkout for the final scoped integration of
already implemented simulator evidence into standard researcher-facing
outputs.

Completed in this pass:

- Bumped the additive standard output contract to schema version `1.8.0`.
- Added explicit `process_rate.<process_id>` rows to
  `time_series_long.csv`, preserving every process identity in multi-process
  models while retaining the legacy `degradation_rate` and
  `product_release_rate` presentation aliases.
- Copied persisted `derived_quantities.csv` trajectories into namespaced
  `derived_quantity.<name>` rows with explicit thermodynamic activity,
  reaction-quotient, Gibbs-energy, and enforcement-flag roles.
- Extended `thermodynamic_diagnostics.csv` with the configured dynamic-Q,
  redox-energy, electron-balance, solver-enforcement, binding, evaluation
  count, blocking count, and Gibbs-extrema evidence already written by PR-57.
- Updated the Markdown/HTML report text and row detail rendering so it can
  display copied dynamic thermodynamic evidence without claiming to infer,
  recompute, revalidate, or apply enforcement.
- Synchronized the active README, roadmap, status, next-step, validation-gate,
  and machine-checkable status contracts. No further PR is selected for the
  user-scoped queue after PR-59.

Tests added or modified:

- Extended virtual-experiment API tests for every newly copied thermodynamic
  summary/row field and each derived-quantity semantic role.
- Added a multi-process registry-chain test proving all process rates retain
  explicit identity in the standard long table while legacy aliases remain.
- Updated schema-version, report guardrail, and active-status contract tests.

What did not change: no equation, modifier, process law, solver RHS behavior,
thermodynamic evaluation, registry record, biological identity, parameter,
validation dataset, calibration result, empirical comparison, or simulation
authorization changed. Missing configured artifacts still produce no invented
rows or values.

Scientific behavior impact: none. This slice copies and labels evidence already
persisted by configured simulation. It does not independently calculate or
enforce thermodynamics and does not add a biological claim.

Backward compatibility: existing columns and legacy rate aliases remain.
Schema `1.8.0` adds rows and columns, so consumers that incorrectly assume
fixed row counts should select by `state`, `state_role`, or `source`. New
namespaces prevent collisions with simulated state names.

Remaining ambiguity and risk: legacy `degradation_rate` and
`product_release_rate` remain compatibility presentation aliases and cannot
identify every process in a multi-process system; the new
`process_rate.<process_id>` rows are authoritative for that purpose. Derived
quantities are trusted only as copied simulation artifacts and are not
recomputed by the PRODUCT table writer.

Risk level: low-to-medium output-contract risk, bounded by an additive schema
minor version, collision-resistant namespaces, retained legacy rows, focused
multi-process/thermodynamic tests, and no numerical-behavior change.

Recommended next task: none in the user-scoped queue. After PR-59 is reviewed,
verified, and merged, stop rather than inventing another roadmap item.

Verification:

- Focused thermodynamic bridge and multi-process rate-identity tests:
  `2 passed in 9.90s`.
- Focused output, thermodynamic, and status regression initially reached
  `90 passed, 2 failed in 21.17s`; both failures were stale status-text
  assertions. The corrected status/API/report subset passed
  `14 passed in 11.70s`.
- Canonical pytest with coverage: `1216 passed in 452.84s`; total coverage
  `83.95%`, above the required `80%`.
- Ruff over `src tests`: passed.
- Pyright with the venv interpreter: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## PR-58 Broader Provenance-Backed Biological Laws

Date: 2026-07-30

Status: `complete` after PR #73 merged as `68c715b` for competitive and
Haldane substrate-inhibition laws on explicitly matched homogeneous
Michaelis-Menten processes.

Completed in this pass:

- Added `CompetitiveInhibitionModifier` using
  `v = Vmax*S / (Km*(1 + I/Ki) + S)`.
- Added `SubstrateInhibitionModifier` using the Haldane form
  `v = Vmax*S / (Km + S + S^2/Ki)`.
- Required exact base-process type, substrate-state, and Michaelis-constant
  ownership plus finite nonnegative states and positive unit-compatible
  parameters.
- Required a nonblank primary-law source and the explicit
  `literature_backed_software_tested` maturity label for both laws.
- Added assumptions, limitations, parameter/state requirements, failure modes,
  serialization, configured metadata, and fail-closed rejection of unsupported
  combined inhibition.
- Added BIO-readiness proposals and two materially different artificial
  configured benchmarks.

Tests added or modified:

- Added direct equation tests for competitive and Haldane factors.
- Added configured solver/output tests for both artificial benchmark systems.
- Added failure tests for missing primary provenance, nonpositive parameters,
  non-Michaelis-Menten base processes, and mismatched substrate/Km ownership.
- Added machine-checkable proposal and active-status coverage.

What did not change: no production registry record, production biological
identity, case applicability, whole-fungus growth, secretion, uptake, toxicity,
parameter inference, validation dataset, calibration, empirical comparison, or
simulation authorization changed. The existing reversible product-inhibition
modifier and all existing configs retain their behavior.

Scientific behavior impact: only configs that explicitly select one of the new
complete modifier contracts change numerical rates. The cited primary studies
support the selected equation in their study systems; they do not support the
artificial fixture parameters or establish applicability to a FungMod
production case.

Backward compatibility: existing modifier types and configs remain unchanged.
The new modifier types are additive and opt-in. Unsupported composition fails
before execution instead of silently multiplying mechanistically incomplete
rate laws.

Remaining ambiguity and risk: these are reduced single-substrate rate laws.
Competitive inhibition supports one inhibitor; the Haldane law does not
identify a molecular inhibitory complex. Mixed, uncompetitive, irreversible,
time-dependent, allosteric, multiple-inhibitor, transport, and whole-organism
effects remain unsupported. Production use requires separately curated
parameter and applicability evidence.

Risk level: medium scientific risk, bounded by primary-law citations, mandatory
maturity/provenance, exact base-law ownership, unit and positivity checks,
closed composition, artificial labels, and no production records.

Recommended next task: PR-59, integrate already implemented solver diagnostics
and trajectories into standard PRODUCT-001 researcher outputs without adding a
new mechanism or scientific claim.

Verification:

- PR-58 implementation/factory focused suite: `31 passed in 9.80s`.
- Final PR-58 biological-law/factory/roadmap focused suite: `41 passed in
  10.23s`.
- Both new BIO-003 proposals: readiness validation passed.
- Broad full pytest regression: `1215 passed in 219.92s`.
- Canonical pytest with coverage: `1215 passed in 431.91s`; total coverage
  `83.94%`, above the required `80%`.
- Ruff over `src tests`: passed.
- Pyright with the venv interpreter: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## PR-57 Dynamic Thermodynamic Feasibility And Solver Enforcement

Date: 2026-07-30

Status: `complete` after PR #72 merged as `ae8a5a3` for optional explicit
single-reaction ideal-dilute activity/Q evaluation and native forward-rate
enforcement.

Completed in this pass:

- Added a structured optional `thermodynamic_constraints` model-config section
  that binds one constraint to one assembled process, one explicit reaction,
  and one required passing electron/redox balance check.
- Added immutable activity participant, dynamic constraint, and evaluation
  contracts for molar state activities, reaction quotient, standard and
  state-specific Gibbs energy, favorability, and blocking evidence.
- Required exact sourced scalar parameters for temperature, gas constant,
  standard concentration, explicit positive activity floor, nonnegative Gibbs
  tolerance, and either direct standard Gibbs energy or the complete
  `delta_g_standard = -n*F*E_standard` redox input set.
- Required explicit reaction-participant state names, exact verified
  state/species binding, compatible molar concentration units, positive
  stoichiometric coefficients, unique IDs, nonblank provenance references,
  and the sole supported `block_unfavorable_forward_rate` enforcement mode.
- Applied the constraint after the native process rate is evaluated and before
  its contributions are accumulated at every internal
  `ProcessODESolver` RHS call. The same enforced rate is recorded in
  `process_rates`.
- Added standard derived trajectories for per-constraint activities, Q,
  `ln(Q)`, dynamic Gibbs energy, favorability, and rate-blocking flags.
- Added assembly-report ownership, solver metadata, a
  `dynamic_thermodynamic_feasibility` validation row, and configured
  thermodynamic JSON/CSV summary flags/fields for direct or redox-derived
  energy, electron binding, and solver enforcement.

Tests added or modified:

- Added an artificial first-order `A -> B` molar framework fixture whose zero
  standard Gibbs energy stops the forward process near equal activities,
  while the otherwise identical unconstrained model continues converting.
- Exercised both direct standard-Gibbs and redox-derived standard-energy paths
  through configured assembly, native solver execution, derived trajectories,
  assembly/solver metadata, validation results, and output artifacts.
- Added fail-closed tests for an unsupported activity model, missing parameter
  provenance, unknown process ownership, non-concentration state units, and a
  failed bound electron balance.
- Preserved existing configured/native/static-thermodynamic regression
  coverage for models that do not declare a dynamic constraint.

What did not change: no production case template, registry biology, parameter
record, organism/substrate identity, existing process rate law, default solver
setting, validation dataset, calibration, empirical comparison, or simulation
authorization changed. No thermodynamic constraint is inferred for an
existing config.

Scientific behavior impact: only configs that explicitly opt into the complete
constraint contract change numerical behavior. For those configs, an
unfavorable nonnegative forward process rate is set to zero at solver time.
The artificial equilibrium fixture is software evidence only, not a measured
or validated biological reaction.

Backward compatibility: existing configs omit `thermodynamic_constraints` and
retain their prior assembly, solver, process-rate, validation, and output
behavior. Existing configured thermodynamic metadata diagnostics remain
supported; dynamic rows and derived quantities are additive when configured.

Remaining ambiguity and risk: the activity model is ideal dilute and uses one
explicit common standard concentration plus explicit numerical floor. Reverse
rates, nonideal activity coefficients, coupled-network optimization,
electrochemical gradients, environmental-temperature trajectories,
multi-constraint ownership per process, and empirical validity are
unsupported. A hard forward-rate boundary is numerically discontinuous and is
bounded here by native solver regression and explicit returned blocking
evidence.

Risk level: medium scientific/numerical risk, bounded by opt-in ownership,
complete sourced inputs, passing static electron/binding evidence, closed
methods, exact unit checks, no defaults, artificial tests, and unchanged
existing configurations.

Recommended next task: PR-58, implement broader biological laws only after
selecting mechanisms with primary provenance, explicit parameter and maturity
contracts, assumptions, limitations, and materially different generic tests.

Verification:

- Dynamic/configured/native/static-thermodynamic/roadmap focused regression:
  `130 passed in 16.15s`.
- Broad full pytest regression: `1202 passed in 222.76s`.
- Ruff over the repository's documented `src` and `tests` gate: `All checks
  passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1202 passed in 531.22s`; total coverage
  `83.91%`, above the required `80%`.
- `git diff --check`: passed.

## PR-56 Branching And Cyclic Enzyme-Pathway Assembly

Date: 2026-07-30

Status: `complete` after PR #71 merged as `caa0a17` for explicit linear,
branching, and cyclic graphs over already implemented configured process laws.

Completed in this pass:

- Replaced the linear-only topology parser with an explicit registry-owned
  `topology_type` contract admitting only `linear`, `branching`, or `cyclic`.
- Derived directed state-role edges from each distinct process-owned
  stoichiometric map while retaining one explicit implemented rate-law input
  and allowing one or more explicit product edges.
- Added fail-closed validation for graph connectivity, substrate reachability,
  distinct runtime topology states, process/map role agreement, declared
  branch/cycle shape, map ownership, endpoints, and conservation.
- Preserved stricter ordered, contiguous, acyclic, one-product semantics for
  templates that declare `linear`.
- Emitted process/map-owned edges, entry roles, terminal roles, and actual
  branch/cycle flags in inspectable `case_template.chain_topology` metadata.
- Kept the production BIO-002 template explicitly linear and unchanged in its
  processes, scientific metadata, parameters, state names, stoichiometry,
  outputs, and numerical behavior.

Tests added or modified:

- Added a test-local artificial branching graph with one process producing two
  conserved downstream states; it assembles and runs through the standard
  configured solver.
- Added a test-local artificial cyclic graph with an explicit conserved return
  edge and terminal product edge; it assembles and runs through the same path.
- Added fail-closed tests for missing topology type, a declared branching graph
  without a branch, and a declared cyclic graph without a cycle.
- Updated the existing artificial three-step and production two-step topology
  assertions for explicit edges and entry/terminal roles while preserving
  existing malformed-linear rejection coverage.

What did not change: no production biological identity, production parameter,
source record, process rate law, numerical equation, solver setting, output
table schema, validation data, calibration, empirical comparison, or
simulation authorization changed. Graph fixtures are artificial software
evidence only.

Scientific behavior impact: existing production runs are unchanged. New graph
execution occurs only when templates explicitly own every process, map, state,
coefficient, parameter, topology type, and conservation weight and the process
laws already exist.

Backward compatibility: the existing BIO-002 helper signatures, production
linear configuration, process/state IDs, outputs, and two-step behavior remain
supported. `case_template.chain_topology` gains additive edge and
entry/terminal metadata. Enzyme-pathway templates must now declare their
topology type explicitly instead of receiving an implicit linear default.

Remaining ambiguity and risk: graph execution does not make a pathway
biologically supported. Multi-reactant rate-law semantics, broader pathway
laws, whole-fungus physiology, and empirical validity remain separate
provenance-backed work. Dynamic thermodynamic feasibility is not yet enforced
by the solver.

Risk level: medium architecture risk, bounded by explicit topology ownership,
pre-execution graph/conservation checks, executable conserved branch/cycle
fixtures, preserved linear regressions, and no production biology changes.

Recommended next task: PR-57, implement explicit provenance-bound activity or
reaction-quotient inputs, dynamic Gibbs feasibility, redox/electron balance,
and solver-time process enforcement without inferred chemistry or silent
constants.

Verification:

- Focused BIO-002 linear/branching/cyclic and roadmap suite: `39 passed in
  16.37s`.
- Broader pathway/configuration/registry/roadmap regression suite: `198 passed
  in 28.14s`.
- Ruff over the repository's documented `src` and `tests` gate: `All checks
  passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1192 passed in 485.32s`; total coverage
  `83.99%`, above the required `80%`.
- `git diff --check`: passed.

## PR-55 Arbitrary Reaction Onboarding And Assembly

Date: 2026-07-30

Status: `complete` after PR #70 merged as `6b3d275` for arbitrary reactions
using the already implemented homogeneous Michaelis-Menten process law.
Unsupported process laws remain explicit blockers.

Completed in this pass:

- Removed all Reaction 618, SABIO-RK, cellobiose, and beta-glucosidase tokens
  from the generic registry case builder.
- Moved homogeneous config name/mode/maturity, process ID, parameter-set ID,
  product-map name, state roles, initial conditions, yields, time grid,
  provenance, enzyme/substrate metadata, parameters, and output roles to
  explicit registry/template ownership.
- Preserved the public `RegistryProcessAssembler.deterministic_mode` contract
  while adding explicit supported-request modes. Homogeneous templates may be
  toy or scientific, but the request must match the template's declared mode.
- Required canonical process/config/parameter-set/product-map identity and
  explicit provenance source/confidence. Missing identities, malformed
  provenance, request/template mode mismatch, incomplete parameters, and
  unsupported process laws fail without fallback.
- Added a materially different artificial homogeneous reaction that assembles
  and simulates through the standard public registry case path. It is labelled
  throughout as software-test-only and is not production registry data.

Tests added or modified:

- Added assembly/simulation coverage for the second artificial reaction,
  template-owned IDs/states/product yield/provenance, and no Reaction 618
  leakage.
- Added fail-closed coverage for missing process identity and
  request/template mode mismatch.
- Added a generic-source guard that prevents Reaction 618, SABIO-RK,
  cellobiose, or beta-glucosidase display tokens from returning to
  `case_builder.py`.
- Kept Reaction 618, BIO-001, registry template, registry builder, and
  configured execution regressions in the focused gate.

What did not change: no production biology, production parameter, source
record, numerical rate law, stoichiometric contribution behavior, solver,
output schema, validation dataset, calibration, empirical comparison,
scientific-validation status, or simulation authorization changed. The
artificial fixture is test-local.

Scientific behavior impact: none for existing cases. Reaction 618 continues to
use its existing explicit template, process/product-map identities,
parameters, provenance, states, yield, and time grid. New reactions run only
when every required record is explicit and the selected process law is already
implemented.

Backward compatibility: existing `deterministic_mode` inspection and Reaction
618 scientific assembly remain supported. Homogeneous assembly additionally
admits explicit toy templates. Requests whose mode disagrees with template
mode now fail rather than returning a config whose declared mode differs from
the request.

Remaining ambiguity and risk: registry generality does not imply mechanism
generality. A new rate law still requires its own provenance-backed,
maturity-labelled implementation and tests. Branching and cyclic pathway
topology remains unsupported until PR-56.

Risk level: low-to-medium architecture risk, bounded by unchanged implemented
rate laws, explicit template ownership, a materially different test case,
hardcoding guardrails, mode matching, no production-data additions, and
existing-case regression coverage.

Recommended next task: PR-56, extend registry-owned enzyme-pathway topology
from ordered linear chains to explicit branching and cyclic graphs while
preserving component ownership, supported-law checks, stoichiometry,
conservation, parameters, limitations, and honest failure states.

Verification:

- Focused assembly/registry/Reaction 618/hardcoding suite: `101 passed in
  16.80s`.
- Ruff over `src` and `tests`: `All checks passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1186 passed in 415.03s`; total coverage
  `83.95%` (required `80%`).
- `git diff --check`: passed.

## PR-54 CURATION-001 Authenticated Curator Signatures

Date: 2026-07-30

Status: `complete` after PR #69 merged as `35a3ecb`. This completes
CURATION-001 for its defined review, authoring, authentication,
promotion-planning, and transactional-apply workflow. It does not complete
scientific validation or authorize simulation.

Completed in this pass:

- Added a closed versioned Ed25519 signature contract for exact
  `curation_manifest.json` bytes. The signature is written atomically as a
  deterministic sibling sidecar so the curation bundle's closed internal
  inventory remains unchanged; the manifest continues to bind every owned
  artifact checksum.
- Added explicit `TrustedCuratorKey` bindings and
  `load_authenticated_curation_bundle(...)`. Trust is caller-owned and binds
  one key ID, Ed25519 public key, and curator identity. The signature envelope,
  public-key digest, exact manifest digest, signature bytes, and every explicit
  decision curator must agree.
- Added `AuthenticatedCurationBundle.reload()` and revalidation at
  `author_parameter_record(...)`, `author_registry_records(...)`, and
  `plan_registry_promotion(...)` use boundaries.
- Kept SHA-256 scoped to consistency checking. The signature result explicitly
  records `production_registry_mutated`, `scientific_validation_claimed`, and
  `simulation_authorized` as false; true or malformed envelope values fail
  closed.
- Kept unsigned `LoadedCurationBundle` use backward compatible and
  distinguishable. A detached promotion plan remains digest-confirmed
  review/apply evidence and does not independently prove curator
  authentication.

Tests added or modified:

- Added signature coverage for the authenticated authoring-to-planning path,
  exact-manifest byte binding, tampered signatures, untrusted keys, forbidden
  validation/authorization claims, mismatched decision-curator identity,
  reload stability, and package-root exports.
- Updated the active roadmap status contract to mark CURATION-001 complete for
  its defined workflow and select PR-55 arbitrary reaction onboarding and
  assembly.

What did not change: no private-key storage, global trust registry, certificate
authority, key revocation, registry mutation, plan/apply schema, scientific
field, parameter, mechanism, process law, numerical method, solver, configured
model, output schema, validation data, calibration, empirical comparison, or
automatic simulation authorization changed.

Scientific behavior impact: none. Signature verification authenticates exact
manifest authorship against caller-supplied trust. It does not establish that
the signed biology, parameters, decisions, or promoted records are
scientifically valid.

Backward compatibility: `LoadedCurationBundle`, in-memory curation results,
existing authored bundles, promotion plans, and apply behavior remain
supported. Authenticated loading is opt-in. The only new runtime dependency is
`cryptography>=42.0`.

Remaining ambiguity and risk: callers own curator identity, public-key
distribution, key rotation, and revocation policy; FungMod deliberately does
not invent a PKI or global curator authority. A signature sibling must remain
available with the bundle for later authentication. Downstream detached plans
retain their existing digest contract but not independent signature evidence.

Risk level: medium security/workflow risk, bounded by Ed25519-only key types,
domain-separated exact-byte signing, closed sidecar fields, explicit caller
trust, exact curator matching, fail-closed verification, and use-boundary
reloads.

Recommended next task: PR-55, generalize arbitrary reaction onboarding and
assembly through explicit generic source, registry, template, and supported
mechanism contracts without reaction-specific branches or silent fallback
values.

Verification:

- Focused curation/signature/authoring/promotion/roadmap suite: `233 passed in
  114.45s`.
- Ruff over `src` and `tests`: `All checks passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1181 passed in 431.38s`; total coverage
  `83.95%`, above the required `80.0%`.
- `git diff --check`: passed.

## PR-53 CURATION-001 Product-Map Registry Ownership

Date: 2026-07-30

Status: `complete` after PR #68 merged as `19baedd`. At that checkpoint,
CURATION-001 remained `partial` only for authenticated curator signatures.

Completed in this pass:

- Added the index-owned `data_registry/product_maps/product_maps.yml`
  destination and a strict `ProductMapRecord` schema owned by
  `FungModRegistry`.
- Added production loading and exact single-record loader support for explicit
  `one_to_one` and `stoichiometric` maps. Reactant/product state names and
  finite positive float coefficients are required exactly; integers, booleans,
  missing mappings, unsupported types, and invalid coefficients fail closed.
- Added explicit conversion from a validated storage record to the existing
  runtime `ProductReleaseMap` without translating participant identities or
  coefficients.
- Extended `author_registry_records(...)`, promotion planning, written-plan
  validation, and transactional apply to the index-declared `product_maps`
  destination through the existing source-identity, reserved audit/digest,
  loader-fidelity, no-overwrite, drift, staging, rollback, and no-mutation
  controls.

Tests added or modified:

- Extended registry loading, record-authoring, promotion-plan, and
  transactional-apply coverage for product-map storage ownership, explicit
  coefficient typing, exact destination resolution, runtime conversion, and
  copied-registry apply.
- Updated the active roadmap status contract to select PR-54 authenticated
  curator signatures.

What did not change: the indexed product-map file contains no scientific
records. No source participant is automatically mapped to a runtime state, no
stoichiometry is inferred or converted, and no process law, solver, configured
model, output schema, validation data, calibration, empirical comparison,
scientific-validation status, or automatic simulation authorization changed.

Scientific behavior impact: none until a caller explicitly selects a valid
promoted map and converts it to the existing runtime type. The conversion
preserves the exact stored states and coefficients.

Backward compatibility: registry indexes without a `product_maps` key still
load with an empty product-map mapping. Existing file-backed and inline config
product-map loaders retain their behavior. Promotion into product maps is now
available only where the current index explicitly declares the destination.

Remaining ambiguity and risk: exact schema and loader fidelity do not prove
that curator-supplied state identities or stoichiometry are scientifically
correct. SHA-256 still proves internal consistency only and does not
authenticate the curator.

Risk level: medium scientific-metadata risk, bounded by explicit float-only
coefficients, no participant conversion, strict loader round trips, reserved
integrity evidence, no overwrite, full staged-registry validation, and copied
registry apply tests.

Recommended next task: PR-54, add an authenticated curator-signature and
trusted-public-key verification contract while keeping checksums scoped to
internal consistency.

Verification:

- Focused registry/authoring/promotion/apply/roadmap suites: `164 passed`.
- Ruff over `src` and `tests`: `All checks passed!`.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1172 passed in 513.75s`; total coverage
  `83.96%`, above the required `80.0%`.
- `git diff --check`: passed.

## PR-52 CURATION-001 Non-Parameter Registry-Record Authoring

Date: 2026-07-30

Status: `complete` after PR #67 merged as `5da611b` for the five index-backed
non-parameter record families. PR-51 is `complete` after PR #66 merged as
`bef938f`. At that checkpoint CURATION-001 remained `partial` for product-map destination
ownership and curator authentication/signatures.

Completed in this pass:

- Added public `author_registry_records(...)`,
  `CuratorAuthoredRegistryResult`, and a versioned
  `fungmod_registry_record_authoring` audit contract for `fungi`,
  `substrates`, `enzyme_classes`, `process_compatibility`, and
  `case_templates`.
- Required one explicitly accepted source record per complete curator-authored
  production target, preserved nonconflicting source identity, rejected
  pre-populated reserved provenance, and bound the source, target, curation,
  result provenance, destination family, safety flags, and record/result
  digests.
- Restricted target maturity to the explicit `exploratory_metadata` and
  `literature_metadata` labels; authoring cannot claim validated or unrestricted
  maturity.
- Added a public single-record production-loader entry point and required exact
  loader round-trip fidelity. Fields that would be dropped, synthesized,
  defaulted, or type-changed fail before promotion planning.
- Extended in-memory, checksum-written, promotion-plan, and transactional-apply
  validation so generic `CurationResult` objects cannot spoof the specialized
  authoring namespace and every authored record is independently revalidated.
- Kept product maps outside this bridge because the production registry index
  still has no declared product-map owner or destination.

Tests added or modified:

- `tests/test_registry_record_authoring.py` covers all five supported families,
  checksum-loaded written sources, source reload and checksum failure, raw-path
  rejection, product-map rejection, source-identity conflicts, dropped-field
  rejection, in-memory tamper detection, namespace-spoof rejection, public
  exports, promotion planning, and transactional apply against a copied
  registry.
- Existing curation review, parameter authoring, promotion plan/apply, registry
  loading, configured workflow, biology, numerical, and no-shortcut tests
  remain applicable.

What did not change: no production registry file, registry version, package
version, source evidence, scientific field, parameter, process law, solver,
simulation admission policy, output schema, notebook, validation data,
calibration, or empirical comparison changed. Authoring and planning do not
apply a registry mutation, and no record is called scientifically validated or
automatically simulation-authorized.

Scientific behavior impact: none. This is an administrative source-to-loader
bridge for complete curator-supplied metadata. It does not infer biological
capabilities, substrate structure, process compatibility, case behavior, or
missing values.

Backward compatibility: existing ordinary curation, ParameterRecord authoring,
written bundle loading, promotion planning, and apply contracts retain their
public behavior. The new reserved provenance namespace only rejects attempts
to pre-populate or spoof the new specialized contract.

Remaining ambiguity and risk: a production loader can prove schema and
round-trip fidelity, not biological truth. Curators remain responsible for
every authored scientific field. Product maps remain blocked until ownership,
storage schema, loader, and index destination are explicit. SHA-256 digests
prove internal consistency only; curator authentication is still absent.

Risk level: medium administrative/scientific-metadata risk, bounded by explicit
acceptance, source identity, closed supported types, reserved provenance,
deterministic digests, exact loader fidelity, full prospective-registry
validation, no overwrite, copied-registry apply tests, and no mutation during
authoring or planning.

Recommended next task: PR-53, define production product-map record ownership,
an index-declared destination and loader schema, then admit curator-authored
product maps through the same source identity, integrity, planning, and
transactional-apply controls.

Verification:

- Focused authoring suite: `13 passed`.
- Authoring plus promotion plan/apply suites: `120 passed`.
- Ruff over the repository's configured gate, `src` and `tests`: `All checks
  passed!`. A broader ad hoc scan also reports 17 existing E402 import-order
  violations in notebooks and `scripts/propose_sabiork_source_records.py`;
  those unrelated files were not changed in this slice.
- Pyright with the documented venv interpreter: `0 errors, 0 warnings, 0
  informations`.
- Canonical pytest with coverage: `1171 passed in 411.07s`; total coverage
  `83.95%`, above the required `80.0%`.
- `git diff --check`: passed.

## PR-51 CURATION-001 Versioned Nonidentity Parameter Conversion Registry

Date: 2026-07-30

Status: `complete` after PR #66 merged as `bef938f` for the bounded nonidentity
ParameterRecord conversion slice. PR-50 is `complete` after PR #65 merged as
`933d2c8`. At that point CURATION-001 remained `partial` for
non-parameter authoring, product-map destination ownership, and curator
authentication.

Completed in this pass:

- Added public immutable `ParameterConversionMethod` and
  `ParameterConversionRegistry` contracts with an exact registry schema
  version and unique named methods.
- Added the registered
  `pint_unit_conversion_decimal_places_half_even_12_v1` method. It accepts
  finite floats only, parses explicit source and target units with Pint,
  rejects identical unit text and incompatible dimensionality, converts
  deterministically, and applies 12-decimal-place half-even rounding.
- Extended `author_parameter_record(...)` so an explicitly accepted source may
  use that registered nonidentity method. Original/source/normalized values and
  units remain type-exact; converted and target values/units must match the
  registered-method recomputation type-exactly.
- Bound the method identifier, version, rounding policy, input value/unit,
  converted value/unit, target value/unit, and conversion policy into the
  existing authoring audit and digest. In-memory and written promotion planning
  independently revalidate the conversion.
- Preserved `identity_no_conversion` behavior and its existing written bundle
  summary contract.

Tests added or modified:

- `tests/test_parameter_conversion.py` covers public exports, registry version,
  the named method policy, deterministic conversion, unknown and duplicate
  methods, nonfinite values, unparseable units, incompatible dimensions, and
  identical unit text.
- `tests/test_parameter_record_authoring.py` covers registered conversion
  authoring, audit content, in-memory and written promotion planning, exact
  recomputation, dimensional rejection, identical-unit rejection, and
  unregistered-method rejection.
- Existing identity, authored-bundle, adversarial mutation, apply, storage-only,
  loader, selector, provenance, and no-mutation tests remain applicable.

What did not change: no registry record, source evidence, production
parameter, registry version, package version, curation decision, promotion
transaction, process law, solver, biology, validation data, calibration,
empirical comparison, output table, or notebook behavior. No conversion is
selected implicitly and no live source access occurs.

Scientific behavior impact: additive administrative unit transcription only.
The registered method performs dimensionally compatible unit conversion; it
does not validate the source value, improve evidence quality, infer a
parameter, fit a model, make a value transferable, or authorize simulation.

Backward compatibility: existing identity authoring retains its exact method
identifier, audit policy, summary flag, and result behavior. Previously
unsupported nonidentity methods continue to fail unless they exactly match a
registered versioned method and recomputation.

Remaining ambiguity and risk: Pint unit parsing defines dimensional
compatibility but not biological comparability. The fixed rounding policy is
explicit and deterministic, not a statement about measurement precision.
Non-parameter authoring, product-map promotion, and curator authentication
remain unsupported.

Risk level: medium administrative/scientific-transcription risk, bounded by a
closed method registry, explicit units, dimensional checks, deterministic
recomputation, exact audit/digest binding, storage-only output, promotion
revalidation, and no registry mutation during authoring.

Recommended next task: PR-52, a non-parameter curator-authored registry-record
bridge for the index-backed record families. Preserve exact source identity,
closed record schemas, destination ownership, loader fidelity, conservative
allowed-use/maturity policy, and no mutation; keep product maps separate until
their destination contract exists.

Verification:

- Full conversion and parameter-authoring suites:
  `119 passed in 113.85s`.
- Ruff: `All checks passed!`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Canonical pytest with coverage:
  `1158 passed in 534.68s`; total coverage `84.08%`, above the required
  `80.0%`.
- `git diff --check`: passed.

## PR-50 CURATION-001 Checksum-Loaded Written Source Authoring

Date: 2026-07-30

Status: `complete` in the current checkout for the bounded loaded-source
authoring slice. PR-49 is `complete` after PR #64 merged as `bbe2ee6`.
CURATION-001 remains `partial` for nonidentity conversion, non-parameter
authoring, product-map destination ownership, and curator authentication.

Completed in this pass:

- Extended `author_parameter_record(...)` to accept either its existing
  validated in-memory `CurationResult` or a public `LoadedCurationBundle`.
- Re-loads the owned manifest through `load_curation_bundle(...)` at authoring
  time and uses only the freshly reconstructed `CurationResult`. This rechecks
  exact inventory, checksums, path/symlink containment, and deterministic
  shared semantics after loading and before authoring.
- Kept raw bundle and manifest paths unsupported at the authoring boundary so
  callers cannot skip the explicit public loading step.
- Preserved every PR-48 source, curator, frozen snapshot, ordered URL,
  identity-only value/unit, closed provenance, storage-only allowed-use,
  registry-context, selector, loader-fidelity, authoring-digest, and
  no-mutation constraint.

Tests added or modified:

- `tests/test_parameter_record_authoring.py` proves loaded written input
  authors the exact same deterministic result and digest as its in-memory
  source, leaves the copied registry unchanged, and still rejects raw paths.
- The same suite proves a bundle modified after loading is revalidated and
  rejected at authoring time.
- `tests/test_roadmap_orchestration_status.py` synchronizes PR-49 merge,
  PR-50 completion and scope, remaining CURATION-001 limits, and the PR-51
  follow-up.

What did not change: no source value, converted value, target value, unit,
parameter policy, registry record, registry version, package version,
promotion classification, apply transaction, process law, solver, biology,
validation data, calibration, empirical comparison, output table, or notebook
behavior. No live source access occurs.

Scientific behavior impact: none. Written-source authoring reconstructs the
same administrative identity transcription already supported in memory. It
does not infer or convert values, validate science, authorize simulation, or
make a parameter transferable.

Backward compatibility: additive accepted input type. Existing in-memory
`CurationResult` callers retain their exact behavior. Raw paths continue to
fail, now with an error that directs callers to the checksum-loaded bundle
contract.

Remaining ambiguity and risk: `LoadedCurationBundle` is not proof of curator
identity; checksums prove internal consistency only. Nonidentity conversion
requires an explicit versioned method registry, parseable units, dimensional
compatibility, deterministic recomputation, and a closed rounding policy.
Non-parameter authoring and product-map promotion remain unsupported.

Risk level: low-to-medium administrative integrity. The only new path is
reduced to the already validated in-memory result after a second public-loader
pass and retains all downstream authoring validation and no-mutation behavior.

Recommended next task: PR-51, a versioned nonidentity ParameterRecord
conversion registry. Admit only explicit named conversions with parseable
source/target units, compatible dimensions, deterministic recomputation from
the source value, and an explicit rounding policy. Add no guessed conversion,
registry mutation, validation claim, or broader record support.

Verification:

- Focused authoring, curation, and roadmap suites:
  `162 passed in 105.19s`.
- Ruff: `All checks passed!`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Canonical pytest with coverage:
  `1148 passed in 396.78s`; total coverage `84.10%`, above the required
  `80.0%`.
- `git diff --check`: passed.

## PR-49 CURATION-001 Reusable Public Curation-Bundle Loader

Date: 2026-07-30

Status: `complete` in the current checkout for the bounded public-loader
slice. PR-48 is `complete` after PR #63 merged as `764d1e4`. CURATION-001
remains `partial` for direct written input to specialized authoring,
nonidentity conversion, non-parameter authoring, and product-map destination
ownership.

Completed in this pass:

- Added top-level `load_curation_bundle(...)` and
  `LoadedCurationBundle`. The loader accepts an owned curation directory or
  its exact `curation_manifest.json`, returns the reconstructed
  `CurationResult`, and exposes the already-read manifest, verified artifact
  paths, parsed YAML/CSV payloads, report text, and accepted records for
  workflow-specific validation.
- Centralized the written curation manifest, schema, exact artifact inventory,
  SHA-256, path traversal, symlink, containment, JSON/YAML/CSV/text parsing,
  summary-count, shared record-envelope, cross-artifact, and deterministic
  report checks in `fungal_model.api.curation`.
- Rewired `plan_registry_promotion(...)` to reuse that loader for every written
  curation input. Parameter-authoring bundles continue through their stronger
  closed workflow validator after the shared integrity pass; the loader does
  not replace the independent authoring digest, audit-schema, frozen-source,
  registry-context, selector, or apply-time checks.
- Kept the trust boundary explicit: manifest checksums prove internal
  consistency and detect changes relative to the manifest. They do not
  authenticate a curator or establish cryptographic authorship.
- Rejected undeclared bundle files in addition to missing or unexpected
  manifest declarations, and preserved rejection of path traversal and any
  symlink component before bundle content is trusted.

Tests added or modified:

- `tests/test_curation_review.py` now covers public directory and manifest
  loading, deterministic reconstruction/rewrite, top-level exports,
  checksum failure, checksum-refreshed cross-artifact semantic drift,
  undeclared artifacts, and symlinked inputs.
- Existing curation, promotion-plan, promotion-apply, and parameter-authoring
  tests continue to exercise the shared loader through the planner, including
  adversarial checksum-valid authored-bundle mutations that must reach the
  stronger specialized validator.
- `tests/test_roadmap_orchestration_status.py` synchronizes PR-48 completion,
  PR-49 completion and scope, remaining CURATION-001 limits, and the PR-50
  follow-up.

What did not change: no registry record, parameter value, unit, maturity,
allowed-use policy, registry version, package version, curation decision
semantics, promotion classification, apply transaction, process law, solver,
biology, validation data, calibration, empirical comparison, output table, or
notebook behavior. No live source access occurs.

Scientific behavior impact: none. Loading a bundle reconstructs administrative
review artifacts only. It does not make their contents current or correct
science, validation evidence, calibration evidence, transferable parameters,
or simulation-authorized inputs.

Backward compatibility: additive public API. Written promotion inputs now pass
through the shared loader and newly reject undeclared sibling artifacts or
cross-artifact disagreement even when an attacker refreshes manifest
checksums. Valid generic and specialized curation bundles retain their
existing promotion behavior and error boundaries.

Remaining ambiguity and risk: `author_parameter_record(...)` still accepts
only an in-memory `CurationResult`; direct written source input needs a
separate explicit API contract. Checksums remain unauthenticated. Nonidentity
conversion requires a closed conversion-method registry, unit parsing,
dimensional compatibility, exact recomputation, and rounding policy.
Non-parameter records and product-map promotion remain unsupported or blocked
as documented.

Risk level: medium for administrative bundle integrity, bounded by exact owned
inventory, checksum, path/symlink, shared semantic reconstruction, existing
specialized authoring validation, and no mutation/apply behavior in the
loader.

Recommended next task: PR-50, a bounded written-source input path for
identity-only parameter authoring that accepts only a successfully
`load_curation_bundle(...)`-validated source result and preserves every PR-48
authoring constraint. Add no conversion, registry mutation, scientific
transformation, validation claim, or broader record support.

Verification:

- Focused documentation and roadmap synchronization suites:
  `15 passed in 0.06s`.
- Ruff: `All checks passed!`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Canonical pytest with coverage:
  `1147 passed in 395.49s`; total coverage `84.10%`, above the required
  `80.0%`.
- `git diff --check`: passed.

## PR-48 CURATION-001 Identity-Only Curator-Authored ParameterRecord Bridge

Date: 2026-07-14

Status: `current` for the bounded PARAMETER-only identity-authoring slice.
PR-47 is `complete` after PR #62 merged as `b1ebb860`. CURATION-001 remains
`partial` for nonidentity conversions and non-parameter source records.

Completed in this pass:

- Added top-level `author_parameter_record(...)` for a validated in-memory
  `CurationResult`, one explicitly selected accepted PARAMETER source record,
  one complete curator-authored production mapping, and an explicit registry
  index. It returns `CuratorAuthoredParameterResult` without registry mutation
  or apply.
- Restricted conversion to `identity_no_conversion`. Original, source,
  normalized, converted, and target values must be finite floats and
  type-exactly equal; their units must be identical nonblank strings. Bools,
  integers, numeric strings, nonfinite values, unknown/range/distribution
  `ValueSpec` forms, and nonidentity methods fail closed.
- Required complete accepted-curation evidence and exact source identity:
  proposal record id, database, entry/reaction ids, query, source field,
  snapshot path, exact one-URL or ordered multi-page `source_url`/`source_urls`
  cardinality from frozen fetch metadata,
  frozen snapshot SHA256, curator, date, reason, limitations, and
  pending-promotion decision policy. Snapshot bytes and frozen URL evidence are
  revalidated before authoring and planning.
- Required every loader-emitted production field, all explicit null selectors,
  every exact `ValueSpec` field, closed maturity/allowed-use/range policies,
  a closed non-validation confidence label, exact source parameter
  symbol/value/units, and full outer source/curator
  provenance. Loader-dropped, synthesized, defaulted, or type-coerced mappings
  are rejected by exact production-loader round-trip comparison.
- Resolved effective enzyme/substrate classes from every non-null entity id,
  rejected class/entity disagreements, and required exactly one process
  compatibility record matching the effective combination and the explicit
  source/curator runtime parameter-role key. The authored result records the
  registry index identity, a complete registry-tree digest, resolved classes,
  compatibility record id, and role key; it isolates
  itself from later input mutation, and revalidates its authoring digest,
  selectors, and planning registry when passed to `plan_registry_promotion(...)`.
- Preserved the dual representation: accepted source/curation evidence is
  durable `fungmod_parameter_bridge` audit metadata, while only the complete
  curator-authored `ParameterRecord` is the loader and promotion target. The
  specialized result reuses `CurationResult.write()` for deterministic,
  checksummed output already consumable by promotion planning.
- Persisted result-level proposal limitations in manifest, summary, all three
  decision YAML payloads, both decision CSV tables, bridge audit, and the
  deterministic full report. Specialized planning reconstructs every semantic
  artifact from the authored result and requires exact headers, keys, and
  values. Public SHA256 checksums prove internal bundle consistency, not
  external curator identity or cryptographic authorship.
- Closed the full authored summary key/value schema, including every mutation,
  validation, simulation, provenance, and limitation claim, and compare it
  against manifest, accepted payload, bridge audit, and report representations.
  Removing removable workflow labels cannot downgrade a parameter candidate
  whose intrinsic target/curation provenance still has the authoring shape;
  planning rejects it, apply independently rejects a legacy/reconstructed
  generic plan lacking the bridge audit, and the shared runtime authorization
  predicate blocks an externally installed relabelled record.
- Reconciled frozen SABIO metadata as one offline structure: page/request/URL
  cardinality and immutable raw-page order, page numbers, URLs, regular files,
  unique exact `raw/page_NNNN.json` identities, byte sizes, and checksums must
  agree. Collapsed or path-aliased multi-page metadata fails.
- Bound source query, source snapshot path, proposal limitations, every
  original/source/normalized/converted/target value and unit representation,
  singular and plural source aliases, acceptance evidence, and every closed
  policy field into exact-key audit schemas and the result digest. Both
  authoring-owned provenance keys and outer mutation/validation/simulation
  safety claims are rejected on input. Curator-authored outer provenance now
  uses a closed identity-only field set, so validation, calibration,
  empirical-status, simulation-readiness, authorization, or nested claim
  aliases cannot be added alongside the owned false safety audit.
- Made simulation admission one centralized authorization-and-mode predicate
  used by modelability and every simulation parameter resolution path.
  `registry_storage_only_no_simulation_authorization` and reserved authoring
  evidence remain mode-independent blockers. Scientific mode accepts only the
  exact canonical scientific permission; exploratory and toy modes use closed
  explicit permission sets. Empty, unknown, negative, and near-match strings
  fail closed before ranking.
- Centralized mode-aware parameter eligibility and the complete dynamic ranking
  key across modelability, ensemble sampling/runtime, deterministic case
  assembly, and result-table/mechanism reconstruction. Ineligible records are
  filtered before ranking; explicit records are rejected rather than silently
  substituted. Exploratory and scientific value-kind preferences remain
  mode-specific, while selector, exploratory-prior, and calibrated-maturity
  tie-breaks now agree for identical admitted candidates; authorization is no
  longer a ranking preference because unauthorized records cannot enter a
  candidate set.
- Added one neutral exact-template role resolver used by modelability/preflight,
  ensemble/public runtime, deterministic assembly, direct chain assembly, and
  result reconstruction. CASE-001 consumes its exact role-to-record IDs without
  fallback and rejects mapping, symbol, nonnegative/exact-or-sampleable value,
  selector/component-identity, environment, authorization, mode, and process
  drift.
  The outer process compatibility binds every ordered process-template ID to a
  unique exact component compatibility record. Structural process `state_roles`
  resolve through canonical `state_species` enzyme-entity or substrate IDs;
  registry entities, enzyme capabilities, and the bound compatibility determine
  each component's class pair, process, bond, and role-symbol authority.
  Role/record selectors are assertions only, and `component_selectors` shadow
  metadata is rejected. Process parameters and parameter-backed catalyst/
  substrate initial states must match that independently resolved owning slot.
  This rejects a coherent whole-role-group rewrite even when contracts, records,
  and selector assertions are changed together.
  Kinetic role ownership is derived from component `process_templates` and
  conflicting metadata is rejected. Initial-state roles instead use an honest
  per-role record-scope contract; they do not claim a kinetic process owner.
  The BIO-002 cellulase initial-state record retains its declared surface-process
  scope because it initializes the surface-release component; BIO-001 uses the
  separate `bio001_cellulase_initial_concentration_prior` record. That storage/
  applicability scope does not make the initial condition a surface-kinetic
  parameter.
- Added intrinsic `component_only` scope for component process compatibilities
  and one registry-level authority graph validated at load and again on every
  compatibility query. Component records require exactly one ordered outer
  owner, complete unique semantic role content, canonical non-whitespace IDs,
  no nesting or standalone case-template claim, and exact process-template
  coverage. Standalone records keep their existing omitted/default scope in
  serialization; corrupt or removed incoming bindings cannot reclassify a
  marked component as an authoring or simulation candidate.
- Cross-bound the configured outer template substrate entity ID to the exact
  registry substrate identity consumed by the outer process's canonical
  `state_species` slot; the same-class alternate-ID attack cannot pass by
  parking the configured ID on an unused state.
  Component compatibility now requires exact semantic key-to-symbol mappings
  for parameter-backed catalyst/substrate initial states and nested modifiers,
  rather than accepting symbol membership under a renamed key. The same shared
  resolver rejects these drifts in modelability, ensemble/public simulation,
  deterministic/direct assembly, and result reconstruction; a materially
  different copied-registry three-step chain covers both initial-state and
  nested product-inhibition role rewrites.
- Preserved caller-supplied required roles when compatibility is present and
  anchored implemented direct process parameters to process-type-owned
  canonical fields. Explicit templates reject missing direct roles, coherent
  semantic-key renames, and duplicate role reuse before modelability or
  assembly. Every initial-state `parameter_role` and `units_from_role` must also
  retain an explicit parameter record, so coherent outer-compatibility and
  template truncation fails during preflight instead of later assembly. Optional
  nested modifiers and dynamic fallback retain their existing contracts.
  Malformed list-valued compatibility roles and component binding IDs now
  produce `RegistryValidationError` instead of raw `TypeError`.
- Centralized one parameter-provenance classifier across planning, apply, and
  runtime. A reserved `fungmod_parameter_bridge` namespace always requires full
  independent bridge schema/digest/policy validation at apply; the reserved
  `fungmod_curation` namespace and distinctive nested source evidence remain
  mode-independently non-simulatable even when malformed. Ordinary outer
  `curator`, `curation_date`, and `parameter_role` metadata alone remain generic.
- Kept written source curation input out of scope. Shared canonicalization,
  type-exact comparison, round-trip difference, SHA256, full-tree hashing, and
  symlink helpers live in one internal integrity module and are reused by
  registry promotion; provenance classification lives in one neutral shared
  module used by plan, apply, and runtime. No parallel curation-bundle parser
  was added.
- The frozen SABIO-RK test completes explicit identity curation in a test-owned
  proposal copy, re-authors canonical EntryID 35622 kcat using the existing
  canonical record id, removes that target only from a copied temporary
  registry, and produces one ADDABLE plan. Production `data_registry/` is
  byte-checked as unchanged and no apply occurs.

Tests added or modified: `tests/test_parameter_record_authoring.py` covers the
real frozen SABIO path, in-memory and written-result planning, deterministic
checksums, rechecksummed authored-bundle tampering, post-result mutation,
unsupported written input, source acceptance/blocker/type failures, exact
identity conversion, bool/int/string/nonfinite values, blank fields, source
identity and snapshot digest conflicts, conservative policies, complete
`ValueSpec` and loader fidelity, selector compatibility, malformed and nested
bridge evidence at plan/apply/runtime, exact written-envelope/report closure,
ordinary curator-metadata compatibility, aliased raw pages, unsafe output paths,
planning-registry revalidation, and public exports.
`tests/test_roadmap_orchestration_status.py` synchronizes PR-47 completion,
PR-48 current scope, remaining CURATION-001 limits, and the PR-49 follow-up.

What did not change: no production registry parameter record, value, unit,
maturity, allowed-use policy, or version; no package version,
curation decision semantics, valid generic promotion transaction behavior, process law, solver,
biology, validation data,
calibration, or empirical comparison. The SABIO source adapter performs no
network access here. Its proposal payload now adds explicit `parameter_role`
and normalizes the SABIO `Km` role to runtime key `km`, alongside exact frozen
URL provenance; source values and units are unchanged.

Scientific behavior impact: no new scientific result. The frozen SABIO case
proves deterministic extraction, explicit identity mapping, provenance,
loader fidelity, and copied-registry planning only. It is not current/correct
science, validation, calibration, prediction, transferability evidence, or
simulation authorization.

Backward compatibility: the public API and result/error types are additive,
but behavior is not purely additive. SABIO proposal payloads gain explicit
`parameter_role`, with `Km` normalized to runtime role key `km`; malformed
multi-page frozen metadata is newly rejected. Parameter candidates with the
intrinsic authoring provenance shape require the specialized contract even if
labels are removed, and outer provenance safety claims are rejected. Existing
generic curation, planning, and apply inputs without that shape retain their
contracts. Deliberate safety change: parameters retaining either reserved
authoring/curation provenance namespace are mode-independently non-simulatable;
ordinary outer curator/date/role metadata alone remains generic. An exact
`registry_storage_only_no_simulation_authorization` parameter is now rejected
by modelability/preflight in every mode. Parameter simulation admission now uses
closed exact `allowed_use` sets, so prior ad hoc, empty, negative, or near-match
strings no longer authorize a mode. Explicit chain templates with
`parameter_record_ids` must also provide complete `parameter_role_contracts`;
the outer compatibility must provide exact ordered component-compatibility
bindings, component compatibilities must carry intrinsic `component_only` scope
with exactly one registry-validated owner, each configured substrate and
the configured outer substrate and each parameter-backed component state must
resolve through the exact structurally consumed canonical registry ID,
initial-state/modifier symbols require exact semantic compatibility keys,
direct process fields must satisfy the implemented process-type schema without
omission, renaming, or role aliasing, role/record selectors are assertions only,
and the old
ownership-like `parameter_role_process_types` shape is rejected.
CASE-001 initial-state records declare exact storage/reuse process scope, while
kinetic owners are derived only from component process templates.

Remaining ambiguity and risk: nonidentity conversions require a separate
closed conversion-method registry, unit parsing, dimensional compatibility,
exact recomputation, and rounding policy; they are rejected here. Written
curation input remains deferred until the existing private bundle parser can be
made reusable without duplication. Non-parameter curation records remain
unsupported. Registry locks remain relevant only at apply, which this API does
not invoke.

Risk level: high for scientific provenance and schema integrity, bounded by an
identity-only policy, exact type checks, frozen-byte digest verification,
loader and selector revalidation, immutable result copies, adversarial tests,
and no mutation/apply path.

Recommended next task after PR-48 merges: PR-49, a reusable public
checksum-validated curation-bundle loader that centralizes the existing
manifest/checksum/path contract before any specialized authoring API accepts a
written source bundle. Add no scientific transformation or registry mutation.

Verification:

- Focused authoring, source-provider, promotion-apply, direct chain, and roadmap
  status suite: 171 passed in 28.59s.
- Broader authoring, source, curation, promotion, modelability, ensemble,
  case-builder, chain, and VirtualExperiment suite: 320 passed in 49.74s before
  the final apply-time regression; the canonical suite below includes that
  regression and all focused coverage.
- Final-review authoring/resolver/registry/status regression suite: 230 passed
  in 126.33s; the complete explicit CASE-001 malformation matrix passed 35
  tests in 10.37s after its expected diagnostics were aligned with the stronger
  exact process-role and consumed-substrate checks.
- Canonical full pytest: 1144 passed in 249.30s on the final code.
- Focused Ruff: passed.
- Full Ruff: passed for `src` and `tests`.
- Full Pyright with the shared venv interpreter selected explicitly: 0 errors,
  0 warnings, 0 informations. The bare worktree invocation could not resolve
  `pint` because isolated worktrees do not contain the main checkout's
  `.venv`; the repository-documented `--pythonpath` equivalent passed.
- `git diff --check`: passed.

## PR-47 CURATION-001 Digest-Confirmed Transactional Apply

Date: 2026-07-13

Status: `complete` for the bounded transactional apply slice after PR #62
merged as `b1ebb860`; PR-46 is complete after PR #61 merged as `2b6c639`.
CURATION-001 remains `partial`, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added top-level `apply_registry_promotion(...)` for an in-memory
  `RegistryPromotionPlan` or its owned written bundle. Written apply requires
  an explicit current registry index and never uses manifest absolute paths as
  write destinations.
- Intentionally advanced the promotion-plan schema from `1.0.0` to `2.0.0`.
  Planning now inserts deterministic non-scientific
  `provenance.fungmod_curation` audit metadata into each addable prospective
  record and binds every regular registry-root file into before/prospective
  digests. Pre-PR-47 written `1.0.0` bundles are rejected at apply rather than
  silently reinterpreted.
- Revalidates the exact plan/confirmation digest, candidate and prospective
  consistency, accepted curation metadata, ISO date, source provenance,
  source-identity consistency between target and curator provenance, blockers,
  loader fidelity, current index SHA, full before-root digest, every
  target before hash, index destinations, path/root/symlink/shared-target
  safety, no-overwrite state, and `load_registry(...)` immediately before the
  transaction.
- Requires a strict numeric current `MAJOR.MINOR.PATCH` version and exactly the
  next patch version. Apply changes only the index version and exact planned
  target bytes; package version and all scientific fields remain unchanged.
- Copies the complete registry root into a same-filesystem sibling stage,
  preserves unrelated regular files, rejects unsafe symlinks/special entries,
  validates the full staged registry, verifies promoted runtime records
  type-exactly, and records exact changed-file before/after hashes.
- Uses an atomic exclusive sibling lock for cooperating single-writer and
  reentrant exclusion. The directory-level swap retains a byte-exact backup
  through installed version/digest/runtime verification, rolls back
  deterministically on injected failure or interruption, reconciles source,
  backup, and stage state from validated on-disk digests, verifies rollback
  digest/loader state, preserves recovery copies when rollback is unproven, and
  reports committed cleanup failures without implying rollback.
- Added `RegistryPromotionApplyResult` with old/new versions, confirmed
  `plan_digest`/`confirmation_digest`, before/planned/applied registry digests,
  exact changed files/hashes, applied and exact-duplicate IDs, transaction,
  rollback, and backup-cleanup status, plus explicit
  `production_registry_mutated: true`,
  `scientific_validation_claimed: false`, and
  `simulation_authorized: false`.
- Kept product maps blocked pending a destination contract, conflicts and
  blocked candidates non-applicable, exact duplicates no-op only, and at least
  one addable record mandatory. Plan summaries/manifests now report
  `apply_available: true` only for at least one addable with no conflict or
  blocked candidate. No receipt is written to a hidden location.

Tests added or modified: `tests/test_registry_promotion_apply.py` exercises
in-memory and written-bundle success on copied registries, parameter and fungus
record types, exact confirmation, plan and artifact tampering, schema
compatibility, index/target/unrelated drift, conflict/blocked/no-addable plans,
strict patch versions, unsafe destinations, untrusted manifest absolute paths,
durable audit provenance, unchanged scientific fields and target allowed-use,
complete staged loading, byte-exact commit rollback, rollback failure,
`KeyboardInterrupt`/`SystemExit` after backup rename, before install rename,
and during installed-runtime verification, committed backup/lock cleanup
failure truthfulness, concurrent/reentrant lock refusal, debris cleanup, and
public exports. The repository's real
`data_registry/` is never an apply target in tests.
`tests/test_registry_promotion_plan.py` now covers schema `2.0.0`, deterministic
audit metadata, source-identity contradiction blocking, candidate-derived
applicability, and unchanged raw exact-duplicate semantics.
`tests/test_roadmap_orchestration_status.py` keeps PR-46 completion, PR-47
current status, partial CURATION-001 status, PR-48 curation bridge follow-up,
and deferred validation wording synchronized.

What did not change: no repository `data_registry/` record or version, package
version, source-provider/curation decision, simulation eligibility, process
law, solver, thermodynamic behavior, biology, parameter value/unit/maturity,
validation data, calibration, or empirical comparison changed.

Scientific behavior impact: none. This is an administrative production
registry mutation contract over exact reviewed bytes. Promotion is not
scientific validation and does not authorize simulation.

Backward compatibility: the public apply API/result types are additive, but
promotion-plan schema `2.0.0` intentionally supersedes preview-only written
schema `1.0.0`. Existing `1.0.0` bundles remain readable review artifacts but
must be regenerated before apply. Planning now includes audit metadata in
addable prospective YAML and full-root digests; exact-duplicate raw-content
classification remains unchanged.

Remaining ambiguity and risk: the lock is cooperative between callers using
this API; external filesystem writers cannot be forced to honor it, so source
digests are rechecked immediately before swap. Directory swaps assume local
same-filesystem rename semantics. Rollback failure is fail-closed and reports
the exact backup/stage paths and preserves the stage container because
automatic recovery cannot then be proven.
Product-map destination ownership remains undefined and blocked. Exact
duplicates remain no-op and therefore do not rewrite an existing production
record solely to attach this plan's curation audit.

Risk level: high for filesystem integrity, bounded by copied-registry
adversarial tests, full-tree staging, digest rechecks, locking, installed-state
verification, deterministic rollback, and explicit cleanup-state reporting;
scientific risk is low because no scientific content is inferred or changed.

Recommended next task after PR-47 merges: PR-48, a bounded CURATION-001
curator-authored source-to-production registry-record bridge/schema workflow.
Make an explicit frozen source record transformable into the exact existing
production loader schema through curator-authored fields and conversion
metadata only. Add no guessed conversion, fallback/default, invented science,
automatic promotion, simulation authorization, validation data, calibration,
or empirical claim.

Verification:

- Focused registry-promotion plan/apply and roadmap-status suite: 109 passed in
  22.71s.
- Broad registry, curation, source-provider, researcher-API, and status suite:
  273 passed in 40.93s.
- Full suite from scratch with coverage: 904 passed in 179.71s; total coverage
  84.52% against the required 80% gate, with
  `src/fungal_model/api/registry_promotion.py` at 80%.
- Full Ruff: passed for `src` and `tests`.
- Full Pyright: 0 errors, 0 warnings, 0 informations.
- Unstaged and staged diff checks: passed.

## PR-46 CURATION-001 Registry-Promotion Preview Plan

Date: 2026-07-13

Status: `complete` for the bounded registry-promotion preview/plan after PR #61
merged as `2b6c639`; PR-45 is complete after PR #60 merged as `5ac7864`.

Completed in this pass:

- Added top-level `plan_registry_promotion(...)` support for an in-memory
  `CurationResult` or a written owned curation bundle. Written inputs verify the
  curation manifest kind/schema and every declared artifact checksum before
  accepted records are read.
- Limited consideration to explicit accepted decisions. Rejected, deferred,
  omitted, blocked, malformed, and non-owned inputs cannot enter a plan.
- Mapped curation `parameter_records` only to the registry index's `parameters`
  key and resolved every supported destination solely from the supplied
  `registry_index.yml` records mapping. Traversal, absolute/out-of-root paths,
  symlink components, shared target files, malformed record files, and missing
  destinations fail or remain explicitly blocked.
- Added deterministic per-record `addable`, `exact_duplicate`, `conflict`, and
  `blocked_unsupported` classifications. Existing IDs are never overwritten;
  product maps are blocked as `unsupported_pending_destination_contract`
  because they remain outside the registry index.
- Preserved accepted target-record fields without scientific inference or
  transformation while keeping curator-decision metadata separately visible in
  the plan. Each addable candidate is validated through the actual
  `load_registry(...)` path in a temporary copied registry and must round-trip
  to the exact candidate mapping through the loaded record's existing
  `to_dict()` schema. Unknown fields that loaders would silently drop and
  omitted fields they would synthesize/default are blocked. Scalar comparisons
  are recursively type-exact, so booleans, integers, and floats cannot silently
  compare equal after loader conversion. Exact duplicates remain raw
  stored-content comparisons with the same scalar-type fidelity before this
  addable-only fidelity gate.
- Revalidated every accepted record against the existing CURATION-001 contract:
  unresolved `missing_fields` or `reasons` and incomplete source provenance are
  rejected for both in-memory and checksum-valid written bundles.
- Added exact prospective YAML content, target paths, before/post SHA-256
  values, an unchanged-registry digest, a prospective full-registry digest, and
  a deterministic plan digest. The complete combined prospective registry is
  loaded and validated again before a plan is returned.
- Added optional deterministic `promotion_plan.json`,
  `candidate_classifications.yml`, `promotion_report.md`, and
  `prospective_registry/` review artifacts with transactional replacement only
  for an existing folder carrying the owned plan manifest kind/version. Output
  paths that equal, descend from, or contain a registry root are rejected before
  replacement, and write-time digest verification rejects mutated nested plan
  payloads before creating output.
- Kept the API preview-only: there is no `apply()` path, production registry
  mutation, record overwrite, simulation promotion, version bump policy,
  scientific validation claim, live API behavior, biology, solver, calibration,
  or validation-data change. Digest-confirmed transactional apply and version
  policy remain PR-47 concerns.

Tests added or modified: `tests/test_registry_promotion_plan.py` covers a
schema-valid addable parameter, byte-for-byte registry immutability, exact
duplicate/no-op, same-ID conflict, unsupported product maps, reject/defer
exclusion, valid and checksum-tampered written bundles, malformed/non-owned
bundles, index traversal/symlink/out-of-root destinations, target-schema and
loader-fidelity failures for unknown and omitted/defaulted fields, prospective
full-registry validation failures, type-exact boolean/integer-versus-float
comparisons, accepted-record blocker and provenance revalidation for memory and
checksum-valid written bundles, shared ISO-date validation for accepted records
from both input forms, deterministic digests/artifacts, refusal after plan
mutation, safe owned output replacement, bidirectional registry-root overlap
refusal with byte-preservation proof, and public exports.
`tests/test_roadmap_orchestration_status.py` keeps the PR-45/PR-46/PR-47 queue,
partial CURATION-001 status, and deferred validation wording synchronized.

What did not change: `data_registry/`, registry versions, source proposal or
curation-decision behavior, simulation eligibility, live-source behavior,
process laws, solver and thermodynamic behavior, biology, parameters, units,
validation data, calibration, and empirical comparison are unchanged.

Scientific behavior impact: none. This slice validates and previews exact file
content only; it does not establish scientific validity or authorize any record
for simulation.

Backward compatibility: all existing source-provider, curation, registry, and
simulation APIs remain unchanged. The preview API, result types, and artifacts
are additive, and no apply method exists.

Remaining ambiguity and risk: registry version policy and the exact
digest-confirmed transactional apply authorization remain intentionally
undefined until PR-47. Product-map destination ownership also remains undefined
and therefore blocked. Human curator decisions remain outside software
validation.

Risk level: moderate. The runtime scope is isolated from production mutation,
but it introduces security-sensitive path/checksum handling and exact
prospective file/digest contracts that PR-47 may later consume.

Recommended next task: review and merge PR-46, then implement PR-47 as a
separately reviewed digest-confirmed transactional apply operation with an
explicit version policy, rollback behavior, and unchanged no-overwrite/path
boundaries. Keep validation deferred until source-backed observations satisfy
its evidence gate.

Verification:

- Focused registry-promotion plan suite: 34 passed.
- Focused promotion/curation/orchestration suite: 84 passed.
- Combined promotion/curation/registry-loading/public/status suite: 104 passed.
- Broad curation, registry, public-API, instruction, hygiene, source-provider,
  virtual-experiment, and roadmap suite: 223 passed.
- `MPLCONFIGDIR=/private/tmp/fungmod-mpl-cache PYTHONPATH=src /Users/felix/Documents/GitHub/FungMod/.venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
  - Result: 838 passed in 127.10 seconds; total coverage 84.74%, above
    the required 80%; `registry_promotion.py` coverage 80%.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache PYTHONPATH=src /Users/felix/Documents/GitHub/FungMod/.venv/bin/python -m ruff check src tests`
  - Result: all checks passed. The main checkout interpreter is used because
    ignored virtual environments are not copied into git worktrees.
- `PYTHONPATH=src /Users/felix/Documents/GitHub/FungMod/.venv/bin/python -m pyright --pythonpath /Users/felix/Documents/GitHub/FungMod/.venv/bin/python`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## PR-45 CURATION-001 Source-Proposal Review And Decision Bundle

Date: 2026-07-13

Status: `complete` for the bounded proposal-review and curator-decision bundle
after PR #60 merged as `5ac7864`; PR-44 is complete after PR #59,
CURATION-001 remains `partial`, and
VALIDATION-DATA-001 remains `deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added top-level `review_source_proposal(...)` support for either an in-memory
  `RegistryProposal` or its written `proposal_manifest.json` bundle through one
  normalization and validation path.
- Added per-record `eligible_for_review` versus `blocked_excluded`
  classification with exact missing fields and typed record-specific schema
  reasons. Unknown biology, parameters, units, and review-required fields
  remain explicit and are never filled or inferred.
- Required every proposed product-map substrate/product participant
  stoichiometry to parse as a finite positive number. Product yields must be
  finite positive numerics, map unambiguously to product participant names or
  ids through the existing SABIO token normalization, and match participant
  stoichiometry within `1e-12` relative tolerance and zero absolute tolerance.
  Float-conversion overflow from oversized JSON integers is classified as
  malformed rather than aborting review. No stoichiometric conversion or
  fallback is performed.
- Added explicit `accept`, `reject`, and `defer` decisions requiring curator
  identity, reason, ISO curation date, closed review-only/pending-promotion
  allowed use, and limitations. Acceptance additionally requires complete
  source database, snapshot-or-URL, entry provenance, and explicit original
  and converted parameter values/units/conversion method. Reject/defer may
  preserve provenance blockers. Every omitted decision remains deferred, and
  blocked records cannot be accepted.
- Added deterministic `curation_report.md`, `eligible_records.csv`,
  `excluded_records.csv`, `proposed_registry_records.yml`,
  `accepted_registry_records.yml`, `rejected_registry_records.yml`, and
  checksummed `curation_manifest.json` artifacts with canonical serialization
  and transactional repeated-write replacement only for directories carrying
  the expected owned curation manifest kind/version.
- Preserved proposed record values and metadata verbatim, including source and
  normalized values/units plus conversion metadata when present. Accepted
  artifacts add a curator decision block but retain review-only separation.
- Rejected malformed manifests, duplicate record IDs, unknown decisions,
  incomplete decision metadata, unknown decision record IDs, path traversal,
  symlinks in every existing input/output path component, unowned output
  directories, and writes beneath `data_registry/`.
- Exported the concise API at top level and added a README example with the
  explicit non-promotion boundary.

Tests added or modified: `tests/test_curation_review.py` covers normal frozen
SABIO-RK review, all-deferred default behavior, explicit accepted/rejected
decisions, exact blockers, provenance, value/unit/conversion preservation,
registry immutability, deterministic transactional outputs and checksums,
malformed/duplicate/path/decision failures, owned output replacement, canonical
serialization, full path-component symlink rejection, strict product-map
participant/yield stoichiometry and consistency, and offline socket
containment. Oversized participant stoichiometry and yield integers are covered
as blocked records that cannot be accepted but can be explicitly rejected or
deferred.
`tests/test_roadmap_orchestration_status.py` keeps PR-44/PR-45, partial
CURATION-001, future promotion, and deferred validation wording synchronized.

What did not change: `data_registry/`, simulation eligibility, source proposal
generation, live-source behavior, parser behavior, process laws, solver and
thermodynamic behavior, biology, parameters, units, validation data,
calibration, and empirical comparison are unchanged.

Scientific behavior impact: none. This slice validates proposal structure and
records human decisions only. It does not establish scientific validity or
authorize simulation.

Backward compatibility: all existing source-provider, proposal, registry, and
simulation APIs remain unchanged. The curation API and artifacts are additive.

Remaining ambiguity and risk: curator decisions still require human scientific
judgment. Acceptance in this bundle is not production registry promotion, and
CURATION-001 remains partial until a separate explicit promotion operation is
implemented and reviewed.

Risk level: low to moderate. Runtime scope is isolated from simulation and the
production registry, while file/bundle validation and replacement behavior are
new public surfaces.

Recommended next task after this completed slice: implement PR-46 as a bounded
registry-promotion preview plan with explicit destination control and
registry-schema validation, leaving digest-confirmed transactional apply and
version policy to PR-47. Keep validation deferred until source-backed
observations satisfy its evidence gate.

Verification:

- Focused curation, source-provider, and discovery suite: 75 passed.
- Broad curation, SABIO-RK source/discovery/parser/fetch, Reaction 618,
  registry, public-API, instruction-hierarchy, and roadmap suite: 169 passed.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache .venv/bin/python -m ruff check src tests`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath .venv/bin/python`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.
- Unfiltered full coverage gate: 773 passed, 1 failed; total coverage 84.85%.
  The sole failure was the unrelated repository-hygiene assertion because the
  ignored pre-existing
  `notebooks/examples/.ipynb_checkpoints/10_virtual_experiment_product_tour-checkpoint.ipynb`
  remains in the shared workspace with a 2026-06-20 timestamp. PR-45 did not
  create, modify, delete, or stage it.
- Review-correction full coverage gate before the final product-map P1,
  excluding only that unrelated workspace-hygiene assertion: 783 passed,
  1 deselected; total coverage 84.93%. The curation module had 88%
  branch-aware coverage at that checkpoint. The final product-map P1 then ran
  the focused, broad, Ruff, Pyright, and diff gates requested above.
- One initial broad-suite command named nonexistent
  `tests/test_active_instruction_docs.py` and collected no tests; it was
  corrected to `tests/test_active_instruction_hierarchy.py` in the green broad
  run. A module-targeted coverage command also hit a NumPy collection error;
  the repository-standard `--cov=fungal_model` commands collected and ran
  normally.

## PR-44 Researcher Source-Provider Onboarding UX

Date: 2026-07-12

Status: `complete` after PR #59 merged for the bounded public SABIO-RK provider
UX slice; PR-43 is complete after PR #58, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added top-level `source_proposal(provider="sabiork", ...)` onboarding that
  requires only one friendly scientific selector and returns the existing
  review-only `RegistryProposal`.
- Reused existing `SabioRKSource` discovery, parsing, filtering, and proposal
  generation. Common `reaction_id`, EC number, enzyme, substrate,
  organism/source, and entry identifiers derive the source query without
  exposing raw Solr syntax in the new API.
- Moved the existing SABIO-RK HTTP/freeze implementation into the package and
  kept the fetch CLI as a thin wrapper, so explicit `refresh=True` freezes the
  raw response plus fetch metadata through one implementation.
- Hardened the review follow-up so every refresh writes a unique query-specific
  snapshot bundle. Exact HTTP page bodies remain separate under `raw/`, the
  parser reads `derived/combined_export.json`, and `fetch_metadata.json` binds
  every artifact with SHA-256 checksums instead of sharing or overwriting files.
- Applied the official SABIO-RK query semantics: all text terms are quoted,
  embedded quotes/backslashes are escaped, boolean/operator text remains
  literal inside quotes, the documented `Enzymename` field is used, and SABIO
  reaction/entry IDs accept only positive unquoted decimal forms.
- Removed `live_fetcher` from the new top-level `source_proposal(...)`
  signature so public refresh cannot bypass shared freeze/provenance handling.
  The legacy `SabioRKSource(live_fetcher=...)` hook remains backward compatible.
- Kept SABIO-RK keyless: no credential is required, read, used, stored, or
  included in query/cache/proposal artifacts. A supplied credential fails with
  a redacted provider-specific error before any filesystem or transport action.
- Unknown providers list only `sabiork`; no BRENDA, CAZy, or other provider is
  claimed.

Tests added or modified: `tests/test_source_provider_api.py` covers the minimal
no-key call, injected fake transport refresh/freeze, friendly query derivation,
official quote/backslash/operator escaping, strict numeric IDs, two-query
immutable bundle/metadata pairing, multi-page raw preservation and checksums,
secret redaction and non-persistence, review-only proposal gate, production
registry immutability, unknown provider, missing selector, public-signature
containment, and refresh failure. Existing SABIO-RK adapter/discovery/fetch and
public-API guardrails remain covered.

What did not change: existing `SabioRKSource` and `live_fetcher` signatures,
source parsing/proposal schemas, production registry records, simulation and
test network behavior, biology, solver behavior, thermodynamics, validation
data, calibration, and empirical comparison are unchanged.

Scientific behavior impact: none. Source records remain review-only proposals
and are never trusted or promoted into simulation automatically. Live refresh
is explicit and outside simulation/tests.

Backward compatibility: the existing `SabioRKSource` constructor,
`live_fetcher` hook, parser/proposal behavior, and fetch CLI command remain
available. The fetch CLI now writes its returned export and metadata inside a
unique nested bundle instead of shared output filenames. The unmerged new
top-level API intentionally removes its custom-fetcher bypass before release.

Remaining ambiguity and risk: SABIO-RK source completeness and scientific
suitability still require human review. Only SABIO-RK is implemented, and live
service behavior remains external to offline verification.

Recommended next task: implement PR-45 as a bounded CURATION-001
source-proposal review and explicit decision bundle without production registry
promotion.

Verification:

- Focused source/public/status suite after the review follow-up: 64 passed.
- Broad SABIO-RK, Reaction 618, notebook, registry, public-API, virtual-
  experiment, active-instruction, repository-hygiene, and roadmap suite after
  the review follow-up: 140 passed.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache .venv/bin/python -m ruff check src tests scripts/fetch_sabiork_kinlaw_entries.py`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath .venv/bin/python`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## PR-43 Process-Bound Entropy-Production-Rate Timeseries

Date: 2026-07-12

Status: `complete` after PR #58 merged for the bounded THERMO-003
configured-output diagnostics slice; PR-42 is complete after PR #57, and
broader THERMO-003 remains `partial`.

Completed in this pass:

- Added a typed optional
  `outputs.entropy_production_rate_timeseries` configured contract that binds a
  known process id to explicit sourced condition-specific delta Gibbs,
  positive temperature, reaction-extent-rate interpretation, target
  extent-rate units, provenance refs, and an optional sourced unit-bearing
  native-rate conversion.
- Derived `entropy_production_rate(t) = -DeltaG * extent_rate(t) / T` after the
  solver finishes, from the native `SimulationResult.process_rates` trajectory
  only. Direct molar extent-rate trajectories and explicitly converted mass
  rates are covered by artificial framework benchmarks.
- Added configured `entropy_production_rate_timeseries.json` and `.csv`
  artifacts with process/time/value/units/provenance/status/guardrail fields,
  automatic output-manifest inclusion, and Markdown/HTML/index report
  visibility.
- Added explicit failures for unknown configured processes, absent native
  trajectories, incompatible or undefined units, nonpositive temperature,
  non-finite or misaligned trajectories, and unsupported metadata. No default
  conversion or inferred value is used.

Tests added or modified: `tests/test_configured_model_workflow.py` covers the
converted-rate path, direct molar-rate path, artifact schema and values,
manifest/report visibility, and each required failure boundary.

What did not change: the ODE right-hand side, process rate laws, solver
settings, state trajectories, native process-rate trajectories, existing
scalar `entropy_production_rate_metadata` validator and thermodynamic-summary
row contract, validation/calibration behavior, and biology are unchanged.

Scientific behavior impact: additive diagnostics only. Delta G remains a
caller-supplied condition-specific constant for each configured diagnostic;
there is no inferred Q/activity/concentration/redox/electron balance, dynamic
Delta G, energy gate, or solver-time thermodynamic enforcement.

Backward compatibility: existing configs emit no new artifact and follow the
same result/output behavior. Existing scalar entropy metadata remains
supported unchanged. The new contract is opt-in and rejects incomplete or
dimensionally dishonest metadata.

Remaining ambiguity and risk: callers remain responsible for the scientific
meaning and provenance of the declared process-rate-to-reaction-extent mapping.
The software verifies units and explicit metadata, not empirical validity or
whether a constant condition-specific Delta G is appropriate across a run.

Recommended next task: review and merge PR-43 as the bounded process-rate
diagnostics slice while keeping THERMO-003 partial. Then take the requested
provider UX as a separately scoped PR-44 rather than adding it to this
thermodynamics slice.

Verification:

- Focused configured-workflow suite: 44 passed.

## PR-42 Arbitrary-Length Linear Enzyme-Chain Assembly

Date: 2026-07-12

Status: `complete` after PR #57 merged for the bounded arbitrary-length linear
enzyme-chain assembly slice.

Completed in this pass:

- Replaced the exactly-two-process guard in the registry/template-driven
  extracellular enzyme-chain assembler with explicit ordered linear-topology
  validation for two or more process templates.
- Added bounded indexed intermediate/catalyst/enzyme state-role support while
  preserving every existing case-template role and schema version.
- Require one unique one-reactant/one-product stoichiometric map per ordered
  process, exact process/map state-role agreement, contiguous step order,
  unique topology states, and `substrate`/`product` endpoints.
- Emit the validated process, product-map, role, and state sequences as
  inspectable `case_template.chain_topology` config metadata.
- Reject fewer than two steps, process/map count mismatches, repeated process
  or product-map IDs, disconnected/reordered steps, branching maps, cycles,
  repeated states, and process/map role mismatches before model execution.
- Extended the unrelated copied-registry framework benchmark to three process
  steps, four topology states, three catalyst states, explicit conservation
  weights, an existing product-inhibition modifier on the third step, and the
  existing configured execution/standard-table path. The fixture is artificial
  software evidence only, not scientific or validation data.
- Preserved the existing BIO-002 two-step template, configured process/state
  IDs, researcher-facing CASE-001 API path, conservation semantics, modifiers,
  provenance, maturity, assumptions, limitations, and standard output labels.
- Updated README capability text, BIO-002 documentation, roadmap/status queue,
  validation-gate wording, and Phase 1 finding status so arbitrary-length
  linear support is explicit while branching and cycles remain unsupported.

Tests added or modified: expanded
`tests/test_bio002_generic_chain_assembly.py` for three-step assembly/execution,
conservation and output semantics, third-step modifier mapping, minimum-length,
disconnected, branching, cyclic, and malformed topology rejection; preserved
the existing BIO-002 and researcher API regression suites.

No new rate law, production constant, empirical record, validation data,
calibration claim, inferred parameter, hidden notebook science,
substrate/fungus-specific generic branch, or scientific validation claim was
added. Existing two-step scientific/numerical behavior and public helper
signatures are backward compatible. The new behavior is limited to templates
that previously failed solely because they declared more than two valid linear
steps.

Remaining ambiguity and risk: the schema intentionally supports only ordered
acyclic linear topology. Branching, converging multi-reactant steps, cycles,
and general pathway graphs remain unsupported and must not be claimed.

Recommended next task: implement PR-43 as a bounded process-bound
entropy-production-rate configured-output diagnostic from native process-rate
trajectories only when explicit dimensionally compatible metadata are present.

Verification:

- Focused chain baseline before edits: 21 passed.
- Focused chain/registry/API/modifier suite: 54 passed.
- Broad relevant suite spanning chain assembly, modifier mapping, registry
  templates, BIO readiness, modelability, ensembles, public APIs, environment
  grids, hardcoding guardrails, roadmap status, and findings: 130 passed.
- `RUFF_CACHE_DIR=/private/tmp/fungmod-ruff-cache .venv/bin/python -m ruff check src tests`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath "$(.venv/bin/python -c 'import sys; print(sys.executable)')"`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.
- Unfiltered full coverage gate before the final additional malformed-topology
  test: 700 passed, 1 failed, total coverage 84.63%. The sole failure was
  `test_no_notebook_checkpoints_remain_in_working_tree` because the ignored
  pre-existing file
  `notebooks/examples/.ipynb_checkpoints/10_virtual_experiment_product_tour-checkpoint.ipynb`
  remains in the shared workspace. Its filesystem timestamp is 2026-06-20 and
  PR-42 did not create, modify, delete, or stage it.
- Final-tree full coverage gate excluding only that unrelated workspace-hygiene
  assertion: 701 passed, 1 deselected; total coverage 84.64%.
- One initial broad-suite command named nonexistent `tests/test_modelability.py`
  and collected no tests; it was corrected to `tests/test_modelability_report.py`
  in the 130-test green run above.

## PR-41 Pyright Optional-Member-Access Ratchet

Date: 2026-07-11

Status: `complete` for the global optional-member-access typing ratchet once
merged; PR-40 is complete after PR #55, FD-005 is resolved, and
VALIDATION-DATA-001 remains `deferred; blocked/partial` for ingestion.

Completed in this pass:

- Enabled Pyright `reportOptionalMemberAccess` globally in
  `pyrightconfig.json` without disabling or weakening another diagnostic.
- Quantified the pre-change baseline at 35 optional-member-access errors across
  11 modules: configured calibration, calibration fitting, stoichiometry, core
  validators, Gaussian pH kinetics, PET substrate metadata, diffusion,
  transport geometry, Monte Carlo uncertainty, local sensitivity, and static
  balance workflow helpers.
- Narrowed nullable `Parameter.quantity` and optional uncertainty parameters
  with precise local `Quantity`/`Parameter` annotations after existing
  validation contracts. No value was defaulted, guessed, ignored, or cast to
  `Any`.
- Updated the README quality-gate text, architecture-debt register, Phase 1 QA
  finding, active roadmap/status queue, validation gate, and focused quality
  and roadmap guardrail tests.
- Recorded PR-40 complete after PR #55 and made PR-41 the current-next PR while
  keeping validation deferred behind its evidence gate.

No scientific equation, parameter value, quantity conversion, numerical
tolerance, solver path, model output, validation data, calibration result,
biology record, notebook behavior, public API, or output schema changed. The
narrowing uses runtime-neutral precise annotations where existing validation
already establishes non-null state, so no reachable control-flow boundary was
changed and no new behavioral test was warranted.

Recommended next task: add the bounded public-API conservation diagnostics
example notebook previously identified after PR-40, using only the standard
table/accessor and header-only guardrail without changing configured-output
artifacts or scientific behavior.

## PR-40 Virtual-Experiment Conservation Diagnostics Bridge

Date: 2026-07-11

Status: `complete` for the scoped PR-40 standard-table/accessor bridge after PR
#55 merged; PR-39 is complete after PR #54, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added `conservation_diagnostics.csv` as a standard virtual-experiment output
  table with schema/data-dictionary coverage in output schema version `1.7.0`.
- Added `DegradationScreenResult.conservation_diagnostics()` for loading the
  standard table without rerunning simulations.
- The table is populated only by reading existing per-sample configured-output
  `conservation_diagnostics.json` and `conservation_diagnostics.csv` artifacts
  from sample bundle directories.
- Rows copy artifact-presence flags, top-level configured conservation
  diagnostics fields, configured row fields, and explicit interpretation
  guardrails.
- If no configured conservation diagnostics artifacts exist, the standard
  table is written header-only rather than inferring conservation metadata.
- Added Markdown, HTML, report-folder index, and output-manifest visibility
  while preserving configured-output conservation artifact generation and row
  behavior unchanged.
- Added focused virtual-experiment tests for package-generated artifact-field
  copying, the header-only no-artifact case, accessor/schema/report visibility,
  and queue/status contracts.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-39 is complete after
  PR #54 and PR-40 is the current conservation diagnostics bridge slice.

No conserved quantity, tolerance, pass/fail threshold, validation rule,
validation evidence, chemistry, thermodynamics, calibration, empirical
comparison, biology record, solver behavior, scientific numerical behavior,
configured-output conservation artifact schema, or hidden notebook science
changed.

Recommended next task: add a bounded public-API conservation diagnostics
example notebook over the standard table/accessor and its header-only guardrail,
without changing configured-output artifacts or scientific behavior.

## PR-39 Virtual-Experiment Solver Diagnostics Bridge

Date: 2026-07-10

Status: `complete` for the scoped PR-39 standard-table/accessor bridge after PR
#54 merged; PR-38 is complete after PR #53, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added `solver_diagnostics.csv` as a standard virtual-experiment output table
  with schema/data-dictionary coverage in output schema version `1.6.0`.
- Added `DegradationScreenResult.solver_diagnostics()` for loading the standard
  table without rerunning simulations.
- The table is populated only by reading existing per-sample configured-output
  `solver_diagnostics.json` and `solver_diagnostics.csv` artifacts from sample
  bundle directories.
- Rows copy artifact-presence flags, top-level configured solver diagnostics
  metadata, configured row fields, and explicit allowed-use/interpretation
  guardrails.
- If no configured solver diagnostics artifacts exist, the standard table is
  written header-only rather than inferring solver metadata.
- Added report/index standard-table visibility while preserving the existing
  configured-output report links for configured `solver_diagnostics.json` and
  `solver_diagnostics.csv` artifacts.
- Updated focused virtual-experiment tests to prove both the header-only
  no-artifact case and the artifact-derived row case.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-38 is complete after
  PR #53 and PR-39 is the current solver diagnostics bridge slice.

No solver behavior, numerical quality threshold, validation rule, calibration
routine, empirical comparison claim, validation data, biology record,
thermodynamic enforcement, hidden notebook science, silent fallback constant,
scientific inference, configured-output row schema, or notebook behavior
changed.

Recommended next task: continue build-first simulator capability work,
preferably with a bounded mechanism, thermodynamic inspectability, or
table-derived output ergonomics slice, rather than validation ingestion.

## PR-38 Solver Diagnostics Example Notebook

Date: 2026-07-10

Status: `complete` for the scoped PR-38 solver diagnostics example notebook
after PR #53 merged; PR-37 is complete after PR #52, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added `notebooks/examples/19_solver_diagnostics_example.ipynb` as a public
  configured-workflow example over package-generated configured solver
  diagnostics artifacts.
- The notebook runs the existing configured workflow to inspect
  `solver_diagnostics.json`, `solver_diagnostics.csv`, and report/index links
  for the normal metadata path.
- The notebook also demonstrates the explicit header-only/no-metadata
  guardrail by using package workflow helpers to write a bundle whose JSON
  reports `status: unavailable` and whose CSV keeps headers without row-level
  diagnostics.
- Updated notebook inventory/smoke tests so the new notebook remains
  package-output-driven, does not define hidden solver/rate-law logic, and
  verifies normal metadata, no-metadata, and report/index visibility paths.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-37 is complete after
  PR #52 and PR-38 is the current solver diagnostics example-notebook slice.

No solver behavior, numerical threshold, validation rule, calibration routine,
empirical comparison claim, validation data, biology record, thermodynamic
enforcement, hidden notebook science, silent fallback constant, scientific
inference, configured-output row schema, or report-generation behavior changed.

Recommended next task: choose another small build-first simulator capability
slice, preferably a bounded generic mechanism, thermodynamic inspectability, or
table-derived output ergonomics follow-up, rather than validation ingestion.

## PR-37 Solver Diagnostics Visibility Follow-Up

Date: 2026-07-10

Status: `complete` for the scoped PR-37 solver diagnostics visibility
follow-up after PR #52 merged; the current next task is PR-38 solver
diagnostics example notebook, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added Markdown report visibility for existing configured-output
  `solver_diagnostics.json` and `solver_diagnostics.csv` artifacts when
  `write_report(...)` is pointed at a configured-output folder.
- Added optional HTML report and report-folder index links for those existing
  solver diagnostics artifacts, matching the established configured-output
  artifact navigation pattern.
- Kept the section presentation-only and metadata-derived: it summarizes the
  existing JSON status, metadata-availability state, missing solver-metadata
  fields, and existing CSV rows without interpreting numerical quality.
- Added focused configured-output tests for the available-metadata and
  header-only/no-metadata solver diagnostics visibility paths.
- Updated active README, roadmap/status docs, validation-gate current-next
  wording, and roadmap orchestration status tests so PR-36 is complete after
  PR #51 and PR-37 is the selected visibility follow-up.

No solver behavior, numerical threshold, validation rule, calibration routine,
empirical comparison claim, validation data, biology record, thermodynamic
enforcement, hidden notebook science, silent fallback constant, scientific
inference, output generation behavior, or configured-output row schema changed.

Recommended next task: choose another small build-first simulator capability
slice, preferably the PR-38 solver diagnostics example notebook, rather than
validation ingestion.

## PR-36 Configured-Output Solver Diagnostics

Date: 2026-07-06

Status: `complete` for the scoped PR-36 configured-output solver diagnostics
slice after PR #51 merged; the current next task is PR-37 solver diagnostics
visibility follow-up, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added `solver_diagnostics.json` and `solver_diagnostics.csv` to configured
  result bundles.
- Derived diagnostics only from existing configured run metadata, solver
  settings, solver metadata, time-grid/evaluation counts, state counts, and
  process counts already available on the configured workflow result/model.
- Recorded config/run identity, model version, state/process counts, configured
  time-grid bounds and evaluation count, result time-point count, solver
  backend, method, success/status/message, nfev/njev/nlu, tolerances, optional
  max step, allowed-use text, and interpretation guardrails where solver
  metadata exists.
- Wrote deterministic header-only CSV plus JSON `status: unavailable` behavior
  when solver metadata is absent.
- Updated configured-output tests, manifest expectations, active README
  capability text, roadmap/status docs, validation-gate current-next wording,
  and roadmap orchestration status tests.

No solver behavior, numerical threshold, validation rule, calibration routine,
empirical comparison claim, validation data, biology record, thermodynamic
enforcement, hidden notebook science, silent fallback constant, or scientific
inference was added.

Recommended next task: complete PR-37 as a small simulator diagnostics
visibility follow-up that remains metadata/table-derived and improves
configured bundle navigation without changing solver or scientific behavior.

## PR-35 Repository Hygiene Guardrail Extension

Date: 2026-07-06

Status: `complete` for the scoped PR-35 repository hygiene guardrail extension
after PR #50 merged; PR-36 configured-output solver diagnostics is the current
next build-first simulator diagnostics slice, and VALIDATION-DATA-001 remains
`deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added a `.gitignore` rule for generated
  `foundation_progress/FUNGMOD_PROGRESS_REPORT_*.html` snapshots while leaving
  the tracked final-goal HTML plan allowed.
- Extended the git-backed repository hygiene test to reject tracked generated
  artifacts already covered by `.gitignore`, including Python/tool caches,
  coverage artifacts, build/dist/htmlcov/output folders, egg-info metadata,
  bytecode, logs, temporary files, `.DS_Store`, notebook checkpoints, and
  generated progress-report HTML snapshots.
- Added explicit guardrail assertions that generated progress-report HTML
  snapshots are ignored and that
  `foundation_progress/FUNGMOD_FINAL_GOAL_PR_PLAN_2026_06_20.html` remains
  tracked and allowed.
- Updated active roadmap/status docs and roadmap orchestration tests so PR-34
  is complete after PR #49, PR-35 is the current hygiene guardrail extension,
  and the recommended next task is a simulator-building diagnostics follow-up.

No code behavior, solver behavior, validation rule, calibration routine,
notebook output, validation data, biology record, thermodynamics, empirical
comparison claim, scientific output schema, or numerical behavior changed.

Recommended next task: complete PR-36 configured-output solver diagnostics as
a focused simulator diagnostics slice that improves inspectability without
changing scientific or numerical behavior unless explicitly tested.

## PR-34 Configured-Output Conservation/Drift Diagnostics

Date: 2026-07-06

Status: `complete` for the scoped PR-34 configured-output conservation/drift
diagnostics slice after PR #49 merged; broader solver diagnostics remain a
follow-up, and VALIDATION-DATA-001 remains `deferred; blocked/partial` for
ingestion.

Completed in this pass:

- Added `conservation_diagnostics.json` and `conservation_diagnostics.csv` to
  configured result bundles.
- Derived diagnostics only from existing `SimulationResult` state trajectories
  and explicit configured `mass_balance` validators that declare
  `conserved_weights`.
- Recorded validator id, optional `closed_system`, weighted state metadata,
  initial and final conserved totals, final drift, maximum absolute drift,
  relative maximum drift when the initial total is finite and nonzero, units,
  row status/reason, and allowed-use text.
- Wrote deterministic header-only CSV plus JSON `evaluated_count: 0` behavior
  when no explicit configured mass-balance weights are present.
- Kept missing-state and incompatible-unit behavior explicit rather than
  silently coercing diagnostics.
- Updated configured-output tests, manifest expectations, active README
  capability text, roadmap/status docs, validation-gate current-next wording,
  and roadmap orchestration status tests.

No validation data, calibration routine, empirical comparison claim, fitted
curve, new validation rule, solver equation, threshold change, thermodynamic
enforcement, biology record, hidden notebook science, or silent fallback
constant was added.

Recommended next task: after PR-34 merged, complete the focused PR-35
repository hygiene guardrail extension, then choose a simulator-building
diagnostics follow-up that improves inspectability without changing scientific
or numerical behavior unless explicitly tested.

## PR-33 Chain-Template Explicit Environment Modifier Assembly

Date: 2026-07-05

Status: `complete` for the scoped PR-33 chain-template explicit environment
modifier assembly slice once merged; broader environment-response biology
remains explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Extended BIO-002-style chain process-template assembly so explicit
  per-process `modifiers` records can emit configured
  `temperature_arrhenius_reference`, `ph_gaussian`, `oxygen_monod`, and
  `water_activity_threshold` modifiers using the same existing configured
  modifier field names as PR-31.
- Added explicit chain environment context handling through an optional
  `environment_id` builder argument and the researcher-facing registry case
  environment id. Chain templates with environment modifiers now fail if no
  explicit environment id is supplied by the caller or template metadata.
- Added package-generated configured environment entities for chain configs
  when environment modifiers require runtime environment values, sourced only
  from exact registry environment conditions.
- Shared the registry-template environment modifier assembly helper between
  one-process case-template assembly and chain process-template assembly so the
  same explicit role, exact ValueSpec, oxygen-units, and environment-source
  guardrails apply.
- Added copied-registry tests proving chain process templates emit
  temperature/pH and oxygen/water-activity modifiers, expose exact environment
  snapshots and configured metadata, change process-rate inspection outputs,
  and fail clearly for missing role fields, unresolved roles, missing
  environment context, missing environment conditions, non-exact environment
  values, and missing oxygen units.

No validation data, calibration routine, empirical comparison claim, fitted
temperature, pH, oxygen, or water-activity response curve, organism-specific
physiology, inferred environment response, oxygen consumption state, gas
transfer, redox balance, anaerobic metabolism, substrate water-binding model,
EnvironmentGrid behavior change, new response law, solver-time thermodynamic
enforcement, hidden notebook science, or silent fallback constant was added.

Recommended next task: choose a focused PR-34 simulator diagnostics slice, such
as solver diagnostics or conservation/drift diagnostics, unless review finds a
smaller follow-up in the chain-template modifier path.

## PR-32 Repository Hygiene Cleanup

Date: 2026-07-05

Status: `complete` for the scoped repository hygiene cleanup after PR #47
merged; no scientific, numerical, solver, notebook-output, validation-data,
calibration, or biology behavior changed.

Completed in this pass:

- Removed the tracked generated macOS metadata files `.DS_Store`,
  `data/.DS_Store`, `data/experiments/.DS_Store`,
  `data/experiments/synthetic/.DS_Store`,
  `foundation_progress/.DS_Store`, `notebooks/.DS_Store`,
  `notebooks/examples/.DS_Store`, `old_progress/.DS_Store`, and
  `src/.DS_Store`.
- Updated `.gitignore` so `.DS_Store` files and notebook checkpoint
  directories remain untracked in future worktrees.
- Added `tests/test_repository_hygiene.py` to assert that generated metadata
  files such as `.DS_Store`, `.pyc`, `__pycache__`, and
  `.ipynb_checkpoints` are not tracked by git.
- Updated the active roadmap/status current-next wording after PR #46 so
  PR-31 was treated as merged and the cleanup slice became the
  machine-checkable PR-32 current next item until PR #47 merged.

No `old_progress/` content, scientific fixtures, validation datasets, notebook
outputs, solver behavior, response-law behavior, calibration path, or biology
records were changed or deleted beyond the tracked `.DS_Store` metadata file.

Recommended next task: after PR-32 merges, choose a scoped PR-33 simulator
building slice such as chain-template explicit environment modifier assembly,
or a focused solver diagnostics slice. Revisit VALIDATION-DATA-001 only if
source-backed numeric time-course observations satisfying the active evidence
gate are available.

## PR-30 Configured Oxygen And Water-Activity Modifier Example Notebook

Date: 2026-07-05

Status: `complete` for the scoped PR-30 public configured-workflow example
notebook slice after PR #45 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added
  `notebooks/examples/18_configured_oxygen_water_modifiers_example.ipynb` to
  demonstrate configured `oxygen_monod` and `water_activity_threshold` rate
  modifiers through `run_configured_model(...)` and package-generated
  configured outputs.
- The notebook creates a temporary artificial framework-benchmark config from
  the existing homogeneous software-test benchmark, adds explicit artificial
  oxygen half-saturation and minimum water-activity parameter records, and
  keeps the source labelled as non-biological software-test data.
- The notebook inspects `configured_metadata.json`, `assumptions.json`,
  `merged_parameters.json`, `entity_snapshots/`, `input_model_config.json`,
  and `process_rates.csv` so explicit modifier parameters, oxygen units, and
  explicit environment oxygen/water-activity values are visible from
  configured workflow outputs.
- Updated notebook inventory/smoke tests so the new notebook remains
  JSON-valid, public-API/configured-runner only, free of hidden rate laws or
  solver logic, and executable with temporary outputs.
- Updated active README and roadmap/status docs so PR-29 is complete after
  PR #44, PR-30 is the build-first oxygen/water-activity configured modifier
  example notebook slice selected after PR #44, and VALIDATION-DATA-001
  remains deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, fitted
oxygen or water-activity response curve, organism-specific physiology, inferred
environment response, oxygen consumption state, gas transfer, redox balance,
anaerobic metabolism, substrate water-binding model, EnvironmentGrid behavior
change, solver/model behavior, registry biology record, hidden notebook
science, thermodynamic enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## PR-31 Registry-Backed Explicit Environment Modifier Assembly

Date: 2026-07-05

Status: `complete` for the scoped PR-31 registry-backed explicit environment
modifier assembly slice after PR #46 merged; broader environment-response
biology remains explicit-config only, chain-template environment modifier
support remains a follow-up, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Extended one-process registry case-template assembly so explicit
  `process_modifiers` records can emit configured
  `temperature_arrhenius_reference`, `ph_gaussian`, `oxygen_monod`, and
  `water_activity_threshold` modifiers using existing configured modifier
  field names.
- Added builder checks that modifier records must supply required role fields,
  roles must resolve to explicit parameter records, oxygen modifiers must
  declare `oxygen_units`, and required registry environment conditions must be
  present and exact before a model config is emitted.
- Added package-generated environment config references for one-process
  registry configs when explicit environment modifiers require runtime
  environment values, sourced only from the registry environment record.
- Allowed configured input loading to consume inline environment config data,
  matching the existing inline entity pattern for other configured entities.
- Added copied-registry tests proving temperature/pH and oxygen/water-activity
  one-process template modifiers emit configured metadata, environment entity
  snapshots, and inspectable process-rate changes, plus clear builder failures
  for unresolved roles, missing environment conditions, non-exact environment
  values, and missing oxygen units.
- Inspected `src/fungal_model/screening/enzyme_chain.py`; chain templates
  still support explicit product-inhibition modifiers only. Extending the same
  environment modifier records to chain templates needs a follow-up slice so
  chain-specific environment record selection and entity emission can stay
  explicit and tested.

No validation data, calibration routine, empirical comparison claim, fitted
temperature, pH, oxygen, or water-activity response curve, organism-specific
physiology, inferred environment response, oxygen consumption state, gas
transfer, redox balance, anaerobic metabolism, substrate water-binding model,
EnvironmentGrid behavior change, new response law, solver-time thermodynamic
enforcement, hidden notebook science, or silent fallback constant was added.

Recommended next task: complete the scoped PR-32 repository hygiene cleanup,
then choose a scoped follow-up such as chain-template explicit environment
modifier assembly, or revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available.

## PR-29 Explicit Oxygen And Water-Activity Configured Modifiers

Date: 2026-07-04

Status: `complete` for the scoped PR-29 configured oxygen and water-activity
modifier slice after PR #44 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Wired existing `OxygenModifier` and `WaterActivityModifier` response laws
  into configured process modifier construction through `oxygen_monod` and
  `water_activity_threshold` process modifiers.
- Configured generic processes now expose explicit parameter requirements for
  positive oxygen half-saturation symbols and minimum water-activity threshold
  symbols, using caller-supplied oxygen concentration units rather than inferred
  defaults.
- Configured output metadata now records explicit oxygen and water-activity
  modifier rows with maturity labels and limitations, while preserving existing
  product-inhibition and pH/temperature metadata.
- Added focused process-factory and configured-workflow tests proving explicit
  oxygen and water-activity modifiers change configured generic process rates
  when explicit parameters and environment values are supplied.
- Added guardrail tests for missing configured modifier fields, missing required
  parameters, missing environment oxygen/water-activity values, missing
  environment entities, non-positive oxygen half-saturation, and unsupported
  modifier types.
- Updated active README and roadmap/status docs so PR-28 is complete after
  PR #43, PR-29 is the build-first explicit oxygen/water-activity configured
  modifier slice selected after PR #43, and VALIDATION-DATA-001 remains
  deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, fitted
oxygen or water-activity response curve, organism-specific physiology, inferred
environment response, oxygen consumption state, gas transfer, redox balance,
anaerobic metabolism, substrate water-binding model, EnvironmentGrid behavior
change, registry biology record, hidden notebook science, solver-time
thermodynamic enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## PR-28 Configured Environment Modifier Example Notebook

Date: 2026-07-04

Status: `complete` for the scoped PR-28 public configured-workflow example
notebook slice after PR #43 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added `notebooks/examples/17_configured_environment_modifiers_example.ipynb`
  to demonstrate configured `temperature_arrhenius_reference` and
  `ph_gaussian` rate modifiers through `run_configured_model(...)` and
  package-generated configured outputs.
- The notebook creates a temporary artificial framework-benchmark config from
  the existing homogeneous software-test benchmark, adds explicit artificial
  Arrhenius and Gaussian pH parameter records, and keeps the source labelled as
  non-biological software-test data.
- The notebook inspects `configured_metadata.json`, `assumptions.json`,
  `merged_parameters.json`, `entity_snapshots/`, `input_model_config.json`,
  and `process_rates.csv` so explicit modifier parameters and explicit
  environment temperature/pH values are visible from configured workflow
  outputs.
- Updated notebook inventory/smoke tests so the new notebook remains
  JSON-valid, public-API/configured-runner only, free of hidden rate laws or
  solver logic, and executable with temporary outputs.
- Updated active README and roadmap/status docs so PR-27 is complete after
  PR #42, PR-28 is the current build-first environment-modifier example
  notebook slice, and VALIDATION-DATA-001 remains deferred behind the evidence
  gate.

No validation data, calibration routine, empirical comparison claim, fitted
pH/temperature response curve, organism-specific physiology, inferred
environment response, runtime EnvironmentGrid behavior change, solver/model
behavior, registry biology record, hidden notebook science, oxygen/redox
behavior, thermodynamic enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## PR-27 Explicit Configured Environmental Rate Modifiers

Date: 2026-07-04

Status: `complete` for the scoped PR-27 configured environment-modifier slice
after PR #42 merged; broader environment-response biology remains
explicit-config only, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Wired existing `TemperatureModifier` and `PHModifier` response laws into
  configured process modifier construction through
  `temperature_arrhenius_reference` and `ph_gaussian` process modifiers.
- Configured generic processes now expose explicit parameter requirements for
  Arrhenius activation/reference temperature symbols and Gaussian pH
  optimum/width symbols, including optional configured validity-bound symbols.
- Configured output metadata now records explicit pH/temperature modifier rows
  with maturity labels and limitations, while preserving existing
  product-inhibition metadata.
- Added focused process-factory and configured-workflow tests proving explicit
  pH/temperature modifiers change configured generic process rates when
  explicit parameters and environment values are supplied.
- Added guardrail tests for missing configured modifier symbols, missing
  required parameters, missing environment pH/temperature values, and
  unsupported modifier types.
- Updated active README and roadmap/status docs so PR-26 is complete after
  PR #41, PR-27 is the build-first explicit environment-modifier slice, and
  VALIDATION-DATA-001 remains deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, fitted
pH/temperature response curve, organism-specific physiology, inferred
environment response, runtime EnvironmentGrid behavior change, solver law,
registry biology record, hidden notebook science, solver-time thermodynamic
enforcement, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next small build-first simulator/output slice.

## THERMO-003 Virtual-Experiment Thermodynamic Diagnostics Example Notebook

Date: 2026-07-01

Status: `complete` for the scoped PR-26 example-notebook slice once merged;
broader THERMO-003 remains `partial` for dynamic thermodynamic and entropy
constraints, and VALIDATION-DATA-001 remains `deferred; blocked/partial` for
ingestion.

Completed in this pass:

- Added `notebooks/examples/16_thermodynamic_diagnostics_example.ipynb` as a
  public-API example for the standard `thermodynamic_diagnostics.csv` table and
  `DegradationScreenResult.thermodynamic_diagnostics()` accessor.
- The notebook demonstrates the normal header-only/no-artifact case for
  virtual-experiment samples that have no configured thermodynamic summary
  artifacts.
- The notebook then uses `run_configured_model(...)` to generate package-owned
  `thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts from
  explicit configured metadata, copies only those artifacts into a
  virtual-experiment sample bundle, and reruns the standard table writer.
- Updated notebook smoke tests so the new example remains public-API-only,
  executable with temporary outputs, and bounded to existing configured
  artifacts plus standard result-table/report access.
- Updated active README and roadmap/status docs so PR-25 is complete, PR-26 is
  the current build-first notebook slice, and VALIDATION-DATA-001 remains
  deferred behind the evidence gate.

No validation data, calibration routine, empirical comparison claim, inferred
activity model, inferred reaction quotient, inferred concentration, redox
potential model, electron-balance model, solver-time thermodynamic
enforcement, biological mechanism, numerical model, solver behavior, registry
record, hidden notebook science, schema change, CSV row-contract change, or
silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting, digitizing, or fabricating validation data.

## THERMO-003 Virtual-Experiment Thermodynamic Diagnostics Bridge

Date: 2026-07-01

Status: `complete` for the scoped PR-25 standard-table/accessor bridge after
PR #40 merged; broader THERMO-003 remains `partial` for dynamic thermodynamic and
entropy constraints, and VALIDATION-DATA-001 remains `deferred;
blocked/partial` for ingestion.

Completed in this pass:

- Added `thermodynamic_diagnostics.csv` as a standard virtual-experiment
  output table with schema/data-dictionary coverage in output schema version
  `1.5.0`.
- Added `DegradationScreenResult.thermodynamic_diagnostics()` for loading the
  standard table without rerunning simulations.
- The table is populated only by reading existing per-sample configured-output
  `thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts from
  sample bundle directories.
- Rows copy artifact-presence flags, configured row names/statuses, residual
  and equation fields, entropy-budget summary fields when present, and explicit
  allowed-use/interpretation guardrails.
- If no configured thermodynamic artifacts exist, the standard table is written
  header-only rather than failing validation or inventing diagnostics.
- Added report/index standard-table link visibility through the existing table
  link pattern.
- Updated focused virtual-experiment tests to prove both the header-only
  no-artifact case and the artifact-derived row case.

No validation data, calibration routine, empirical comparison claim, inferred
activity model, inferred reaction quotient, inferred concentration, redox
potential model, electron-balance model, solver-time thermodynamic
enforcement, biological mechanism, numerical model, solver behavior, registry
record, hidden notebook science, or silent fallback constant was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting, digitizing, or fabricating validation data.

## BIO-003 Non-PET Product-Inhibition Genericity Hardening

Date: 2026-07-01

Status: `complete` for the scoped PR-24 build-first genericity-hardening slice
after PR #39 merged; broad BIO-003 remains `partial/software-tested`, and
VALIDATION-DATA-001 remains `deferred; blocked/partial` for ingestion.

Completed in this pass:

- Added
  `data/model_configs/toy_surface_dummy_non_pet_product_inhibition.yml`, a
  `mode: toy`, `maturity: framework_benchmark` configured model derived from
  the generic non-PET surface benchmark.
- The fixture adds an explicit artificial product-state `K_i` parameter and a
  `product_inhibition` modifier on the existing dummy surface-catalysis
  process, labelled as software benchmark/testing coverage rather than
  biological evidence.
- Updated configured workflow tests so `run_configured_model(...)` executes
  the non-PET product-inhibition fixture and verifies configured modifier
  metadata, the reversible product-inhibition assumption surface, artificial
  `K_i` labelling, mode/maturity labels, and successful validation output.
- Updated active README, BIO-003 notes, roadmap/status docs, validation gate
  docs, and queue-status tests so PR-24 is the selected build-first BIO-003
  slice because the validation evidence gate remains blocked.

No new biology, validation data, calibration routine, empirical comparison
claim, solver law, numerical behavior change, registry biology record,
researcher-facing API change, live API call, silent fallback constant,
scientific `K_i` claim, toxicity, uptake, secretion, biomass, physiology, or
multi-product inhibition support was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting, digitizing, or fabricating validation data.

## PRODUCT-001 Provenance/Limitations Report Example Notebook

Date: 2026-07-01

Status: `complete` for the scoped PR-23 example-notebook slice once merged;
PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added `notebooks/examples/15_provenance_limitations_report_example.ipynb`
  as a public-API example that runs an existing supported exploratory virtual
  experiment, writes the Markdown report plus optional HTML sidecar and
  report-folder index, and inspects the provenance/limitation decision summary.
- The notebook loads existing decision-support rows through public
  `DegradationScreenResult` accessors for assumptions, limitations, missing
  parameters, suggested experiments, and provenance.
- The notebook checks existing report/index links for
  `assumption_summary.csv`, `limitations_table.csv`,
  `missing_parameters.csv`, `suggested_experiments.csv`, and
  `provenance_table.csv` without adding notebook-only scientific logic.
- Updated notebook smoke tests so the new example remains researcher-facing,
  unvalidated, public-API-only, and executable with temporary outputs.
- Updated active README and roadmap/status docs so PR-23 is complete for the
  scoped provenance/limitations report example-notebook slice, while
  VALIDATION-DATA-001 remains deferred and evidence-gated before any ingestion
  or empirical-comparison work.

No biological mechanism, numerical model, solver behavior, registry record,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, schema version change, CSV
row contract change, silent fallback constant, report utility behavior, or
hidden notebook science was added.

Recommended next task: revisit VALIDATION-DATA-001 only if source-backed
numeric time-course observations satisfying the active evidence gate are
available; otherwise choose the next build-first simulator/output ergonomics
slice rather than ingesting or fabricating validation data.

## PRODUCT-001 Provenance/Limitations Report Ergonomics

Date: 2026-07-01

Status: `complete` for the scoped PR-22 report-inspection slice once merged;
PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added a provenance and limitation decision-summary section to the
  deterministic Markdown report, derived only from existing
  `assumption_summary.csv`, `limitations_table.csv`, `missing_parameters.csv`,
  `suggested_experiments.csv`, and `provenance_table.csv` rows.
- Expanded the report renderers for assumptions, limitations, missing
  parameters, suggested follow-up experiments, and provenance so row types,
  categories, severities, sources, missing statuses, suggested resolutions,
  allowed-use labels, and provenance record details are easier to inspect.
- Added optional HTML sidecar and report-folder index links for those existing
  decision-support tables while preserving the Markdown report as the primary
  contract.
- Updated focused report tests so real generated reports and small
  table-derived fixtures prove the new decision summary and richer row
  renderers without changing simulation behavior.
- Updated active README and roadmap/status docs so PR-22 is complete for the
  scoped provenance/limitations report ergonomics slice, PR-23 is the next
  build-first PRODUCT-001 provenance/limitations report example-notebook
  target, and VALIDATION-DATA-001 remains deferred to PR-24 or later.

No biological mechanism, numerical model, solver behavior, registry record,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, schema version change, CSV
row contract change, silent fallback constant, or hidden notebook science was
added.

Recommended next task: implement PR-23 as a small build-first PRODUCT-001
example-notebook slice that uses the public API to write reports and inspect
the provenance/limitation decision summary and decision-support table links,
without validation data, calibration, empirical comparison, inferred
environment responses, hidden notebook science, schema changes, or solver/model
changes.

## THERMO-003 Explicit Thermodynamic-Summary Report Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-21 report-inspection slice once merged;
THERMO-003 remains `partial` for broader dynamic thermodynamic and entropy
constraints.

Completed in this pass:

- Added an explicit thermodynamic-diagnostics section to the deterministic
  Markdown report when the report utility is pointed at a configured-output
  folder containing existing `thermodynamic_summary.json` and
  `thermodynamic_summary.csv` artifacts.
- Added optional HTML sidecar and report-folder index links for those existing
  thermodynamic summary artifacts without adding them to the virtual-experiment
  standard table schema.
- Kept the report section bounded to existing configured-output diagnostics:
  summary counts, explicit-Q/entropy-rate flags, entropy-budget fields,
  supported/unsupported-scope text, and row-level residual/equation fields.
- Updated focused configured-output/report tests so a real
  `run_configured_model(...)` explicit-Q Gibbs run proves Markdown, HTML, and
  index visibility for `thermodynamic_summary.json` and
  `thermodynamic_summary.csv`.
- Updated active README and roadmap/status docs so PR-21 is complete for the
  scoped thermodynamic-summary report ergonomics slice, PR-22 is the next
  build-first PRODUCT-001 provenance/limitations report ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-23 or later.

No inferred activities, inferred reaction quotients, inferred concentrations,
redox-potential model, electron-balance model, biological mechanism, numerical
model, solver behavior, registry record, validation data, calibration routine,
empirical comparison claim, schema version change, CSV row contract change,
silent fallback constant, or hidden notebook science was added.

Recommended next task: implement PR-22 as a small build-first PRODUCT-001
slice that improves provenance, limitation, missing-parameter, or
suggested-experiment inspection in existing report/index paths, without
validation data, calibration, empirical comparison, inferred environment
responses, hidden notebook science, schema changes, or solver/model changes.

## PRODUCT-001 Threshold-Time Inspection And Report Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-20 report-inspection slice once merged;
PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added `summary_metrics.csv` to the report/index standard-table links so
  aggregate threshold quantiles are easier to inspect beside per-sample
  threshold rows.
- Expanded the deterministic Markdown report's threshold-time section to show
  existing `threshold_times.csv` rows and existing `summary_metrics.csv`
  threshold quantiles with explicit guardrails.
- Updated report tests so Markdown, HTML, and index outputs expose the
  threshold-time guardrails and `summary_metrics.csv` links.
- Updated active README and roadmap/status docs so PR-20 is complete for the
  scoped threshold-time inspection slice, PR-21 is the next build-first
  THERMO-003 explicit thermodynamic-summary report ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-22 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant,
CSV row contract change, schema version change, or notebook-only scientific
implementation was added.

Recommended next task: implement PR-21 as a small build-first THERMO-003 slice
that improves explicit thermodynamic-summary report or inspection ergonomics
from existing configured-output diagnostics only, without inferred
thermodynamics, validation data, calibration, empirical comparison, hidden
notebook science, or solver/model changes.

## PRODUCT-001 Degradation-Rate Quicklook And Report Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-19 quicklook/report inspection slice
once merged; PRODUCT-001 remains `partial` for broader researcher-facing
output ergonomics.

Completed in this pass:

- Added a presentation-only `degradation_rate_vs_time.png` quicklook figure
  generated from existing `time_series_long.csv` `degradation_rate` rows.
- Added a bounded degradation-rate inspection section to the deterministic
  Markdown report, with optional HTML/index visibility flowing through the
  existing report paths and standard table links.
- Updated virtual-experiment API and report tests so the quicklook figure,
  manifest entry, report guardrails, and `time_series_long.csv` report links
  are exercised.
- Updated active README and roadmap/status docs so PR-19 is complete for the
  scoped degradation-rate inspection slice, PR-20 is the next build-first
  PRODUCT-001 threshold-time inspection/report ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-21 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant,
CSV row contract change, or notebook-only scientific implementation was added.

Recommended next task: implement PR-20 as a small build-first PRODUCT-001
slice that improves threshold-time inspection/report ergonomics from existing
`threshold_times.csv`, `summary_metrics.csv`, and report/index paths with
explicit guardrails, without validation data, calibration, empirical
comparison, inferred environment responses, hidden notebook science, or
solver/model changes.

## PRODUCT-001 Trajectory-Quantile Example And Quicklook Ergonomics

Date: 2026-06-30

Status: `complete` for the scoped PR-18 example/quicklook inspection slice
once merged; PRODUCT-001 remains `partial` for broader researcher-facing
output ergonomics.

Completed in this pass:

- Added `notebooks/examples/14_trajectory_quantiles_example.ipynb` as a
  public-API example that runs an existing exploratory virtual experiment,
  writes standard outputs and reports, loads `trajectory_quantiles.csv` through
  `DegradationScreenResult.trajectory_quantiles()`, and verifies trajectory
  guardrails.
- Added a presentation-only `trajectory_quantile_bands.png` quicklook figure
  generated from existing `trajectory_quantiles.csv` rows.
- Updated notebook and virtual-experiment API tests so the example, quicklook
  figure, report links, and guardrail columns are exercised.
- Updated active README and roadmap/status docs so PR-18 is complete for the
  scoped trajectory-quantile inspection slice, PR-19 is the next build-first
  PRODUCT-001 degradation-rate quicklook/report ergonomics target, and
  VALIDATION-DATA-001 remained deferred behind build-first simulator work.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant,
CSV row contract change, or notebook-only scientific implementation was added.

Recommended next task: implement PR-19 as a small build-first PRODUCT-001
slice that improves degradation-rate inspection and report/quicklook
ergonomics from existing standard output tables with explicit guardrails,
without validation data, calibration, empirical comparison, inferred
environment responses, hidden notebook science, or solver/model changes.

## PRODUCT-001 Trajectory-Quantile Output Ergonomics

Date: 2026-06-29

Status: `complete` for the scoped PR-17 derived-output/report ergonomics
slice once merged; PRODUCT-001 remains `partial` for broader
researcher-facing output ergonomics.

Completed in this pass:

- Added `trajectory_quantiles.csv` as a standard virtual-experiment output
  table derived from existing `time_series_long.csv` sample rows.
- Added `DegradationScreenResult.trajectory_quantiles()` for loading
  trajectory bands without rerunning simulations.
- Updated the Markdown report, optional HTML sidecar, and report-folder index
  so the new standard table is visible while preserving explicit
  interpretation guardrails.
- Updated the versioned output schema and data dictionary to `1.4.0`,
  including machine-readable allowed-use, trajectory-band status, and
  interpretation-guardrail columns.
- Updated active README and roadmap/status docs so PR-17 is complete for the
  scoped trajectory-quantile output ergonomics slice, PR-18 is the next
  build-first PRODUCT-001 trajectory-quantile example and quicklook ergonomics
  target, and VALIDATION-DATA-001 remains deferred to PR-19 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant, or
notebook-only scientific implementation was added.

Recommended next task: implement PR-18 as a small build-first PRODUCT-001 slice
that improves trajectory-quantile inspection and quicklook ergonomics from
existing standard output tables with explicit guardrails, without validation
data, calibration, empirical comparison, inferred environment responses,
hidden notebook science, or solver/model changes.

## PRODUCT-001 Uncertainty-Band Output Ergonomics

Date: 2026-06-29

Status: `complete` for the scoped PR-16 derived-output/report ergonomics
slice once merged; PRODUCT-001 remains `partial` for broader
researcher-facing output ergonomics.

Completed in this pass:

- Added `uncertainty_summary.csv` as a standard virtual-experiment output
  table derived from existing sampled-parameter rows and per-case
  `summary_metrics.csv` quantiles.
- Added `DegradationScreenResult.uncertainty_summary()` for loading the
  uncertainty/range summary without rerunning simulations.
- Updated the Markdown report, optional HTML sidecar, and report-folder index
  so the new standard table is visible while preserving explicit
  interpretation guardrails.
- Updated the versioned output schema and data dictionary to `1.3.0`, including
  machine-readable allowed-use and uncertainty-band status columns.
- Updated active README and roadmap/status docs so PR-16 is complete for the
  scoped uncertainty-output ergonomics slice, PR-17 is the next build-first
  PRODUCT-001 trajectory-quantile output ergonomics target, and
  VALIDATION-DATA-001 remains deferred to PR-18 or later.

No biological mechanism, numerical model, solver behavior, registry records,
validation data, calibration routine, empirical comparison claim, inferred
environment response, posterior uncertainty claim, silent fallback constant, or
notebook-only scientific implementation was added.

Recommended next task: implement PR-17 as a small build-first PRODUCT-001 slice
that derives trajectory-level quantile or band outputs from existing
`time_series_long.csv` sample rows with explicit guardrails, without validation
data, calibration, empirical comparison, inferred environment responses, or
solver/model changes.

## THERMO-003 Entropy-Budget Notebook Inspection

Date: 2026-06-29

Status: `complete` for the scoped PR-15 notebook-inspection slice once merged;
THERMO-003 remains `partial` for broader dynamic thermodynamic and entropy
constraints.

Completed in this pass:

- Extended `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`
  so it inspects the package-generated entropy-budget fields in
  `thermodynamic_summary.json`.
- The notebook now displays `has_entropy_budget`, `entropy_budget_status`,
  evaluated and negative counts, units, total, and limitations from the JSON
  summary while confirming CSV output remains row-level diagnostics.
- Updated notebook tests so the static notebook contract and execution smoke
  path both prove the entropy-budget fields are visible and remain JSON-only.
- Updated active README and roadmap/status docs so PR-15 is complete for the
  scoped notebook-inspection slice, PR-16 is the next build-first PRODUCT-001
  uncertainty-band output ergonomics target, and VALIDATION-DATA-001 remains
  deferred to PR-17.

No source code, numerical model, solver behavior, biological mechanism,
registry record, validation dataset, calibration routine, empirical comparison
claim, inferred thermodynamics, inferred activity/reaction-quotient model,
solver-time thermodynamic enforcement, or output schema was added.

Recommended next task: implement PR-16 as a small PRODUCT-001 slice that
surfaces existing explicit uncertainty/range metadata more clearly in standard
outputs or reports without validation data, calibration, empirical comparison,
inferred environment responses, or silent fallback constants.

## PR-14 Post-Merge Current-Next Rollover

Date: 2026-06-29

Status: `complete` for the scoped docs/tests-only rollover once merged.

Completed in this pass:

- Marked the merged PR-14 configured entropy-budget summary as complete in the
  active orchestrator queue.
- Advanced the machine-checkable current-next target to PR-15 THERMO-003
  entropy-budget output notebook inspection so the next build-first slice makes
  the new JSON budget fields visible in a researcher-facing diagnostics path.
- Kept VALIDATION-DATA-001 deferred and moved its future queue slot to PR-16;
  validation still requires source-backed numeric time-course observations and
  must not be presented as complete by this rollover.
- Updated the roadmap/status contract tests so active docs and the validation
  gate agree on the current-next line and do not point back to completed PR-14
  in current-next wording.

No source code, numerical behavior, solver behavior, notebook behavior,
biological mechanism, registry record, validation dataset, calibration routine,
empirical comparison claim, inferred thermodynamics, or output schema was
changed.

Recommended next task: implement PR-15 as a small notebook/report-output slice
that inspects the configured entropy-budget JSON fields from explicit metadata
only, with no new equations, inferred thermodynamics, validation data, or
solver-time enforcement.

## THERMO-003 Configured Entropy-Budget Summary

Date: 2026-06-23

Status: `complete` for the scoped PR-14 configured entropy-budget summary
slice; THERMO-003 remains `partial` for broader dynamic thermodynamic and
entropy constraints.

Completed in this pass:

- Extended configured `thermodynamic_summary.json` with a top-level
  explicit-metadata-only entropy-production budget over existing
  `entropy_production_rate_metadata` validation rows.
- The budget includes only numeric `entropy_production_rate` values whose
  units are exactly `joule / second / kelvin`; missing, non-numeric, non-finite,
  or differently unitized rows remain unevaluated and are not treated as zero.
- Added focused configured-output tests for a single positive entropy-rate row
  and a mixed positive/negative/missing entropy-rate run, including aggregate
  total, minimum, evaluated count, negative count, status, and unchanged CSV
  row schema.
- Updated active README and roadmap/status docs so PR-13 is complete for the
  entropy-production-rate notebook coverage, this slice is PR-14 THERMO-003
  configured entropy-budget summary, and VALIDATION-DATA-001 is deferred to
  PR-15.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, inferred
thermodynamics, inferred activities, inferred reaction quotients, inferred
concentrations, redox-potential model, electron-balance model, solver-time
thermodynamic enforcement, notebook-only scientific implementation, or CSV row
schema change was added.

Recommended next task: after this configured entropy-budget summary slice is
reviewed and merged, either continue build-first simulator capability with a
small explicit-metadata-only THERMO/PRODUCT slice, or start PR-15
VALIDATION-DATA-001 only if a source-backed numeric time-course dataset
satisfies the active ingestion gate.

## THERMO-003 Entropy-Production-Rate Notebook Coverage

Date: 2026-06-23

Status: `complete` for the scoped PR-13 notebook-coverage slice;
THERMO-003 remains `partial` for broader dynamic thermodynamic and entropy
constraints.

Completed in this pass:

- Extended `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`
  so the configured-output fixture demonstrates both existing explicit
  reaction-quotient Gibbs metadata and existing entropy-production-rate
  metadata.
- The notebook still uses public configured workflow APIs and package-written
  `thermodynamic_summary.json` / `thermodynamic_summary.csv` outputs; it does
  not implement thermodynamic equations inside notebook cells.
- Added notebook smoke assertions proving the configured summary reports
  `has_entropy_production_rate`, the entropy-rate equation, positive explicit
  entropy-production-rate values, `joule / second / kelvin` units, and
  `solver_time_enforcement == not_evaluated`.
- Updated active README and roadmap/status docs so PR-12 is complete for the
  PRODUCT-001 comparison/report-output notebook, this slice is PR-13
  THERMO-003 entropy-production-rate notebook coverage, and
  the next build-first THERMO-003 slice is PR-14 before
  VALIDATION-DATA-001.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, inferred
thermodynamics, inferred activities, inferred reaction quotients, inferred
concentrations, redox-potential model, electron-balance model, solver-time
thermodynamic enforcement, or notebook-only scientific implementation was
added.

Recommended next task: after this notebook-coverage slice is reviewed and
merged, continue THERMO-003 only with another small generic constraint or
output slice that uses explicit configured metadata and tests, continue
PRODUCT-001 if the slice improves researcher-facing simulator capability from
existing outputs, or start validation-data work only when a source-backed
numeric time-course dataset satisfies the active ingestion gate.

## PRODUCT-001 Screen Comparison Summary Example Notebook

Date: 2026-06-23

Status: `complete` for the scoped PR-12 example-notebook slice;
PRODUCT-001 remains `partial` for broader researcher-facing output ergonomics.

Completed in this pass:

- Added `notebooks/examples/13_screen_comparison_summary_example.ipynb` as a
  public-API example for running an existing virtual experiment, writing
  standard outputs, writing Markdown/HTML/index report artifacts, and
  inspecting `comparison_summary.csv`.
- The notebook demonstrates metadata-only runtime environment-grid guardrails
  through `comparison_allowed`, `ranking_allowed`,
  `ranking_blocking_reason`, and `recommended_next_action` columns rather than
  ranking cases or plotting environmental response.
- Added notebook smoke coverage proving the example writes
  `comparison_summary.csv`, `output_manifest.json`,
  `virtual_experiment_report.md`, `virtual_experiment_report.html`, and
  `report/index.html`, and that metadata-only rows remain blocked from
  comparison/ranking use.
- Updated active README and roadmap/status docs so PR-11 is complete for
  screen-comparison summary ergonomics, this example notebook is PR-12
  PRODUCT-001 comparison/report-output example notebook, and
  VALIDATION-DATA-001 remains deferred behind the next build-first THERMO-003
  entropy-rate slices.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook-only
scientific implementation, inferred science, environment response law, ranking
of metadata-only environment cases, or hidden report logic was added.

Recommended next task: after this example-notebook slice is reviewed and
merged, continue PR-13 THERMO-003 entropy-production-rate notebook coverage
without adding new thermodynamic behavior, continue build-first PRODUCT-001
only if the next slice improves researcher-facing simulator capability from
existing outputs, or start validation-data work only when a source-backed
numeric time-course dataset satisfies the active ingestion gate.

## PRODUCT-001 Report-Folder Index Navigation

Date: 2026-06-22

Status: `complete` for the scoped PR-10 report-folder index/navigation slice;
PRODUCT-001 remains `partial` for broader researcher-facing output ergonomics.

Completed in this pass:

- Extended `DegradationScreenResult.write_report(..., include_index=True)` so it
  still writes and returns the deterministic Markdown report while optionally
  writing `report/index.html` navigation for the output folder.
- Added a deterministic stdlib HTML index that links existing report artifacts,
  standard CSV tables, `output_manifest.json`, and optional quicklook figures
  when present.
- Added focused tests proving default Markdown and HTML-sidecar behavior remain
  unchanged, the index is opt-in, HTML is escaped, relative links work for
  absolute and relative output directories, and no validation or calibration
  claims are introduced.
- Updated active README and roadmap/status docs so the current-next slice moves
  from the merged PR-09 HTML wrapper to PR-10 PRODUCT-001 report-folder
  index/navigation, with validation-data ingestion deferred behind the next
  build-first output ergonomics slice.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, inferred science, or hidden report logic was added.

Recommended next task: after this presentation-only index slice is reviewed and
merged, continue PR-11 PRODUCT-001 screen-comparison ergonomics if it remains
derived from standard outputs, or start PR-12 validation-data work only when a
source-backed numeric time-course dataset satisfies the active ingestion gate.

## PRODUCT-001 Screen Comparison Summary

Date: 2026-06-22

Status: `complete` for the scoped PR-11 screen-comparison summary ergonomics
slice; PRODUCT-001 remains `partial` for broader researcher-facing output
ergonomics.

Completed in this pass:

- Added `comparison_summary.csv` as a standard virtual-experiment output table
  derived from existing `final_metrics.csv`, `threshold_times.csv`, and
  environment guardrail rows.
- Added `DegradationScreenResult.comparison_summary()` for loading the guarded
  comparison summary without rerunning simulations.
- Added machine-readable comparison and ranking guardrail columns including
  `comparison_allowed`, `ranking_allowed`, `ranking_blocking_reason`, and
  `recommended_next_action`.
- Preserved existing standard-output units and metadata-only environment
  guardrails; runtime environment grids that are metadata-only remain blocked
  from ranking or environmental-response plot interpretation.
- Updated the versioned output schema and data dictionary to `1.2.0`, and
  included `comparison_summary.csv` in report-folder table links.
- Updated active README and roadmap/status docs so PR-10 is complete for
  report-folder index/navigation, this slice is PR-11 PRODUCT-001
  screen-comparison summary ergonomics, and VALIDATION-DATA-001 remains
  deferred behind the next build-first slice.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, inferred science, environment response law, ranking of metadata-only
environment cases, or hidden report logic was added.

Recommended next task: after this derived-output ergonomics slice is reviewed
and merged, continue PR-12 PRODUCT-001 comparison/report-output example
notebook work if it remains derived from existing standard outputs, or start
validation-data work only when a source-backed numeric time-course dataset
satisfies the active ingestion gate.

## PRODUCT-001 HTML Virtual-Experiment Report Wrapper

Date: 2026-06-22

Status: `partial` for researcher-facing report/output ergonomics.

Completed in this pass:

- Extended `DegradationScreenResult.write_report(..., include_html=True)` so it
  still writes and returns the deterministic Markdown report while also writing
  `virtual_experiment_report.html` beside it when requested.
- Added a small stdlib HTML renderer derived from the Markdown report and the
  same standard table/quicklook paths, with HTML escaping and relative links to
  existing CSV tables and optional quicklook figures.
- Added focused tests proving Markdown output remains the primary report,
  HTML output is opt-in, table-derived content is escaped deterministically,
  standard table and quicklook links are present, and no validation or
  calibration claims are introduced.
- Updated active README and roadmap/status docs so the current-next slice moves
  from the merged Markdown writer to this PRODUCT-001 HTML wrapper.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, or inferred science was added.

Recommended next task: continue PRODUCT-001 report-folder navigation or
screen-comparison ergonomics only if it remains a presentation layer over
standard output tables; otherwise keep validation-data ingestion deferred until
source-backed observations exist.

## BIO-003 Researcher-Facing Product Inhibition Example

Date: 2026-06-21

Status: `partial/software-tested` for broad BIO-003; complete for the scoped
researcher-facing example gap on the selected reversible-product-inhibition
target once this PR is merged.

Completed in this pass:

- Added `notebooks/examples/12_reversible_product_inhibition_example.ipynb`.
- Added `fungal_model.examples.prepare_reversible_product_inhibition_example_registry(...)`
  to prepare an explicit copied example registry fixture with a
  provenance-labelled exploratory `K_i`.
- The notebook compares inhibited and uninhibited exploratory virtual
  experiments through `virtual_experiment(...)`, then inspects
  `mechanism_summary.csv`, configured metadata, limitations, and final metrics.
- Added focused tests proving the example runs offline through public
  researcher-facing names, exposes the active `product_inhibition` rate
  modifier, records the example as non-validation data, and reduces final
  product concentration relative to the uninhibited deterministic run.
- Extended notebook smoke tests so the new example executes under
  `FUNGMOD_NOTEBOOK_OUTPUT_ROOT`.

No generic/core process behavior, numerical solver behavior, organism-specific
inhibition behavior, substrate-specific shortcut, competitive/uncompetitive/
mixed/multi-product inhibition, toxicity, uptake, secretion, biomass,
physiology, validation data, calibration routine, empirical comparison claim,
or fallback inhibition constant was added.

Recommended next task: after this PR is reviewed and merged, select the next
small BIO-003 mechanism-family candidate only if it can be implemented with
explicit provenance, maturity labels, tests, and honest limitations; otherwise
return to PRODUCT-001 output ergonomics or deferred validation-data gate work.

## PRODUCT-001 Virtual-Experiment Report Writer

Date: 2026-06-22

Status: `partial` for researcher-facing report/output ergonomics.

Completed in this pass:

- Added `DegradationScreenResult.write_report(...)` as a public result method
  that writes a deterministic Markdown report under `report/` by default.
- Added an internal report renderer that reads existing standard output tables:
  preflight/modelability, case summary, final metrics, threshold times,
  sampled parameters, mechanism summary, assumption summary, provenance,
  limitations, missing parameters, suggested experiments, and optional
  quicklook figure paths.
- Added focused Reaction 618 API coverage proving the report is written,
  includes table-derived facts and limitation language, exposes exploratory
  parameter assumptions, and does not make positive validation or calibration
  claims.
- Updated active roadmap/status docs to move the current next PR from the
  merged PR-07 BIO-003 example to this scoped PRODUCT-001 report-writer slice.

No biological mechanism, numerical model, solver behavior, registry records,
calibration routine, validation data, empirical comparison claim, notebook
logic, or inferred science was added.

Recommended next task: continue PRODUCT-001 report/output ergonomics only if it
remains a presentation layer over standard tables; otherwise continue toward
researcher screen comparison reports.

## THERMO-003 Configured Entropy-Production-Rate Diagnostic

Date: 2026-06-21

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `validate_entropy_production_rate(...)`, a generic configured metadata
  diagnostic for
  `entropy_production_rate = -condition_specific_delta_gibbs * reaction_extent_rate / temperature`.
- Required explicit provenance-backed `Parameter` inputs for
  condition-specific delta G, reaction extent rate, and temperature, with unit
  checks for energy per mole, mole per time, and kelvin.
- Added configured-validator registry support through
  `entropy_production_rate_metadata`.
- Extended configured `thermodynamic_summary.json` and
  `thermodynamic_summary.csv` rows with entropy-production-rate fields while
  preserving existing reaction-quotient Gibbs fields.
- Added focused synthetic tests for positive and negative entropy-production
  rate cases, invalid temperature and units, missing quantities, registry
  loading, and configured JSON/CSV outputs.

No new biology, substrate-specific mechanism, fungus-specific branch, inferred
activity model, inferred reaction quotient, concentration model,
redox-potential model, electron-balance model, solver-time thermodynamic
enforcement, validation data, calibration routine, or empirical validation
claim was added.

Recommended next task: continue THERMO-003 only if another small generic
first-principles diagnostic has explicit configured inputs and tests, or move
to BIO-003 registry-backed case assembly for the already software-tested
product inhibition mechanism.

## BIO-003 Registry-Backed Product Inhibition Assembly

Date: 2026-06-21

Status: `partial/software-tested` for registry-backed assembly of the first
BIO-003 generic mechanism family where explicit records exist.

Completed in this pass:

- Extended registry-backed case-template assembly so explicit product
  inhibition modifier metadata maps into configured process `modifiers`.
- Supported chain process-template modifiers with explicit
  `product_state_role` and `inhibition_constant_role`, and one-process
  registry templates through `process_state_metadata.process_modifiers`.
- Added `mechanism_summary.csv` rate-modifier rows for active assembled
  product-inhibition modifiers in virtual-experiment outputs.
- Added focused copied-registry tests proving explicit registry template
  records emit configured modifiers, configured outputs expose modifier
  metadata, standard mechanism summaries show the active rate modifier, missing
  K_i records fail explicitly, non-positive K_i fails without fallback, and an
  unrelated non-specific chain remains unaffected.

No organism-specific inhibition behavior, substrate-specific shortcut,
competitive/uncompetitive/mixed inhibition, toxicity, uptake, secretion,
biomass, physiology, validation data, calibration routine, empirical
comparison claim, or fallback inhibition constant was added.

Recommended next task: add a public BIO-003 example or notebook that compares
explicit inhibited and uninhibited exploratory runs while preserving the
configured-mechanics and no-validation limitations.

## THERMO-003 Thermodynamics And Entropy Diagnostics Notebook

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `notebooks/examples/11_thermodynamics_entropy_diagnostics.ipynb`.
- The notebook builds a tiny configured software-test model from the existing
  toy homogeneous benchmark, adds an explicit
  `reaction_quotient_thermodynamic_metadata` validator, runs
  `run_configured_model(...)`, and inspects `thermodynamic_summary.json` and
  `thermodynamic_summary.csv`.
- Added notebook tests proving the file exists, imports public package code,
  avoids thermodynamics/core implementation internals, executes under
  `FUNGMOD_NOTEBOOK_OUTPUT_ROOT`, and writes both thermodynamic summary files.
- Reconciled active README and roadmap-status docs so THERMO-003 example
  coverage is visible in the current queue.

No scientific or numerical behavior, new biology, inferred activity model,
inferred reaction quotient, redox-potential model, solver-time thermodynamic
enforcement, validation data, calibration routine, or empirical validation
claim was added.

Recommended next task: continue THERMO-003 only with another small generic
constraint that has explicit configured inputs and tests, or return to BIO-003
registry-backed case assembly for the already software-tested product
inhibition mechanism.

## PRODUCT-001 Public Virtual-Experiment Product Tour Notebook

Date: 2026-06-20

Status: `partial` for examples and notebooks.

Completed in this pass:

- Added `notebooks/examples/10_virtual_experiment_product_tour.ipynb`.
- The notebook uses public APIs only: `virtual_experiment(...)`,
  `environment_grid(...)`, `preflight(...)`, `simulate(...)`, and standard
  table accessors.
- The notebook inspects `mechanism_summary`, `assumption_summary`,
  `limitations`, `final_metrics`, and `sampled_parameters`.
- Added smoke tests proving the notebook executes with
  `FUNGMOD_NOTEBOOK_OUTPUT_ROOT` and writes expected standard output tables.

No scientific or numerical behavior, new biology, registry records,
calibration routine, validation data, or empirical validation claim was added.

Recommended next task: add a BIO-003-specific notebook after registry-backed
product-inhibition case assembly exists, or add a thermodynamics/entropy
notebook using configured explicit-Q Gibbs outputs.

## PRODUCT-001 Mechanism Summary Output Table

Date: 2026-06-20

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `mechanism_summary.csv` as a standard virtual-experiment output table.
- Added the table to the versioned output schema and data dictionary, bumping
  the virtual-experiment output schema to `1.1.0`.
- Added `DegradationScreenResult.mechanism_summary()` to load the table through
  the public API.
- Populated one active process-law row per simulated case with mechanism kind,
  family, maturity, configured-by source, equation/law summary, state-variable
  roles, parameter roles/symbols, assumptions, limitations, and provenance.
- Added tests for homogeneous Michaelis-Menten and BIO-002 enzyme-chain virtual
  experiments.

No scientific or numerical behavior, registry records, new biology,
calibration routine, validation data, or empirical validation claim was added.

Recommended next task: add a product-tour notebook or expose BIO-003 product
inhibition through registry-backed case assembly so `mechanism_summary.csv`
can show active rate modifiers as well as process laws.

## BIO-003 Configured Reversible Product Inhibition

Date: 2026-06-20

Status: `partial/software-tested` for the first BIO-003 generic mechanism
family.

Completed in this pass:

- Added a generic `RateModifierProcess` wrapper that scales any configured
  process rate with explicit reusable modifiers.
- Added configured process `modifiers` support for `type: product_inhibition`
  with explicit `product_state` and `inhibition_constant`.
- Required the product state to exist and required `K_i` as a positive,
  unit-compatible parameter through the existing assembly/solver checks.
- Added configured output metadata for active process modifiers, including
  maturity and limitation text.
- Added non-specific tests for homogeneous first-order and generic surface
  configured processes, plus full configured-run tests proving active
  assumptions/output metadata, missing-`K_i`, and non-positive-`K_i` failure
  behavior.
- Updated the BIO-003 proposal from `proposed` to `software_tested`.

No organism-specific inhibition behavior, substrate-specific shortcut,
registry-backed case assembly, validation data, calibration routine, empirical
validation claim, or fallback inhibition constant was added.

Recommended next task: expose configured product inhibition through
registry-backed case assembly or add the first public API/notebook example that
shows outputs with and without the modifier while preserving limitations.

## BIO-003 Reversible Product Inhibition Scope Selection

Date: 2026-06-20

Status: `selected/proposed` for the first BIO-003 generic mechanism-family
target.

Completed in this pass:

- Added `foundation_progress/BIO_003_GENERIC_PROCESS_LAWS.md` to record the
  selected first BIO-003 target.
- Added the machine-checkable
  `foundation_progress/proposals/BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml`
  proposal.
- Selected generic reversible product inhibition as the next implementation
  target because the low-level `ProductInhibitionModifier` already exists, but
  configured/registry-backed virtual-experiment integration is not complete.
- Added the final-goal HTML PR plan as an active planning artifact:
  `foundation_progress/FUNGMOD_FINAL_GOAL_PR_PLAN_2026_06_20.html`.

No scientific or numerical behavior, configured workflow behavior, registry
records, simulation outputs, biology implementation, validation data,
calibration routine, or empirical validation claim was added.

Recommended next task: implement BIO-003 reversible product inhibition
integration as a small code PR with explicit product-state mapping, positive
unit-compatible `K_i`, output limitations, and at least two materially
different non-specific tests.

## THERMO-003 Configured Thermodynamic Summary CSV

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `thermodynamic_summary.csv` beside `thermodynamic_summary.json` for
  configured runs with thermodynamic validation results.
- Populated the CSV from the same summary rows as the JSON output so explicit
  Gibbs and entropy-production diagnostics are spreadsheet-friendly without a
  second source of truth.
- Added tests proving the CSV is written, contains the explicit-Q Gibbs
  equation and entropy diagnostic, and appears in `output_manifest.json`.

No new biology, substrate-specific mechanism, fungus-specific branch, activity
model, inferred reaction quotient, redox-potential model, solver-time
thermodynamic enforcement, validation data, calibration routine, or empirical
validation claim was added.

Recommended next task: move to BIO-003 with a small generic process-law
expansion, or continue THERMO-003 by adding carefully scoped configured
examples that exercise explicit thermodynamic metadata.

## THERMO-003 Configured Thermodynamic Summary Output

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `thermodynamic_summary.json` to configured-model output bundles when
  thermodynamic validation results are present.
- Summarized explicit reaction-quotient Gibbs rows, delta-G diagnostics,
  entropy-production-per-mole diagnostics, provenance refs, and the supported
  versus unsupported thermodynamic scope.
- Added a configured workflow test proving an explicit-Q Gibbs validator writes
  the summary and records it in the output manifest.

No new biology, substrate-specific mechanism, fungus-specific branch, activity
model, inferred reaction quotient, redox-potential model, solver-time
thermodynamic enforcement, validation data, calibration routine, or empirical
validation claim was added.

Recommended next task: continue THERMO-003 by adding first-class CSV/standard
table summaries for configured thermodynamics, or move to BIO-003 for a small
generic process-law expansion.

## THERMO-003 Reaction-Quotient Gibbs Feasibility

Date: 2026-06-20

Status: `partial` for dynamic thermodynamic and entropy constraints.

Completed in this pass:

- Added `validate_reaction_quotient_gibbs_feasibility(...)`, a generic
  equation-backed validator for explicitly supplied reaction quotient metadata:
  `delta_g = delta_g_standard + R*T*ln(Q)`.
- Added entropy-production-per-mole reporting as `-delta_g / T`.
- Added a named, sourced ideal-gas constant parameter rather than a silent
  fallback constant.
- Added configured-validator registry support through
  `reaction_quotient_thermodynamic_metadata`.
- Added tests for favorable, unfavorable, invalid, and config-loaded synthetic
  reaction-quotient Gibbs cases.

No new biology, substrate-specific mechanism, fungus-specific branch, activity
model, inferred reaction quotient, redox-potential model, solver-time
thermodynamic enforcement, validation data, calibration routine, or empirical
validation claim was added.

Recommended next task: continue THERMO-003 by connecting explicit
reaction-quotient checks to configured output bundles, or return to
PRODUCT-001/BIO-003 for broader generic mechanism coverage.

## PRODUCT-001 Preflight Policy Columns

Date: 2026-06-20

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added explicit `mode` storage and serialization to `ModelabilityReport`.
- Added `assessment_mode`, `simulation_allowed_for_mode`,
  `blocking_reason`, and `recommended_next_action` columns to
  `modelability_preflight.csv`.
- Added versioned output-schema/data-dictionary coverage for the new columns.
- Added tests proving exploratory cases advertise simulation eligibility and
  blocked scientific preflight reports point to missing-input curation.

No new biology, validation data, simulation behavior, calibration routine,
thermodynamic equation, entropy calculation, environmental response law, or
empirical validation claim was added.

Recommended next task: continue PRODUCT-001 with richer researcher-facing input
coverage or start THERMO-003 with a small generic feasibility equation and
tests.

## PRODUCT-001 Preflight Report Writer

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `VirtualExperiment.write_preflight_report(...)` so researcher-facing
  inputs can write diagnostic modelability tables without assembling or running
  a model.
- Added `write_preflight_tables(...)` for preflight-only
  `modelability_preflight.csv`, `modelability_items.csv`, and the versioned
  data dictionary/schema.
- Marked preflight-only rows with `environment_effect_status=preflight_only`
  so they are not confused with simulated environment-response outputs.
- Added tests proving a scientific-mode case that would be blocked by
  `simulate(...)` still writes diagnostic preflight CSVs.

No new biology, validation data, simulation fallback, calibration routine,
thermodynamic equation, entropy calculation, environmental response law, or
empirical validation claim was added. Blocked cases still do not simulate.

Recommended next task: continue PRODUCT-001 with richer researcher-facing
input coverage or start a generic THERMO-003 feasibility slice with explicit
equations and tests.

## PRODUCT-001 Modelability Items Output

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `modelability_items.csv` to the standard virtual-experiment output
  bundle.
- Added `DegradationScreenResult.modelability_items()` for loading the table
  without rerunning simulation.
- Added versioned output-schema/data-dictionary coverage for the new table.
- Populated the table with every per-case preflight fact: known, uncertain,
  missing, and incompatible modelability items, including JSON details and
  machine-readable allowed-use policy.
- Added tests proving known process-compatibility facts and uncertain
  exploratory parameter facts are inspectable from standard outputs.

No new biology, validation data, calibration routine, thermodynamic equation,
entropy calculation, environmental response law, unsupported-case simulation
path, or empirical validation claim was added.

Recommended next task: continue PRODUCT-001 with a report-writing path for
blocked/unsupported preflight cases, or proceed to a generic THERMO-003
feasibility slice if a small equation-backed scope is clear.

## PRODUCT-001 Environment Grid Helper

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added the top-level researcher-facing `environment_grid(...)` helper as a
  convenience wrapper around `EnvironmentGrid`.
- Exported the helper from `fungal_model.api` and top-level `fungal_model`.
- Updated the README target workflow so researchers can pass runtime
  temperature, pH, and oxygen grids directly into `virtual_experiment(...)`.
- Added tests proving the helper works through the top-level API, standard
  outputs still write, runtime environment cases remain `metadata_only`, and
  the public API documentation/export guardrail includes the new helper.
- Updated active roadmap/status docs to keep PRODUCT-001 partial and current.

No new biology, validation data, pH response law, temperature response law,
oxygen response law, thermodynamic equation, entropy calculation, numerical
method, dataset, calibration routine, or empirical validation claim was added.
Runtime environment-grid values remain metadata unless an explicit response law
or condition-specific parameter record is active.

Recommended next task: continue PRODUCT-001 with a small code PR that improves
exploratory output usefulness, such as richer assumption/range summaries,
clearer missing-mechanism reporting, or broader generic mechanism selection
without fungus-specific branches.

## PRODUCT-001 Assumption Summary Output

Date: 2026-06-19

Status: `partial` for build-first exploratory virtual-experiment expansion.

Completed in this pass:

- Added `assumption_summary.csv` to the standard virtual-experiment output
  bundle.
- Added `DegradationScreenResult.assumption_summary()` for loading the table
  without rerunning simulation.
- Added versioned output-schema/data-dictionary coverage for the new table.
- Populated the table with per-case modelability assumptions, uncertain inputs,
  missing inputs, incompatibilities, and suggested follow-up experiments.
- Added tests proving exploratory assumptions and uncertain parameter policies
  are inspectable from standard outputs.

No new biology, validation data, calibration routine, thermodynamic equation,
entropy calculation, environmental response law, or empirical validation claim
was added.

Recommended next task: continue PRODUCT-001 by improving missing-mechanism and
unsupported-case reporting for researcher-facing inputs, or proceed to a
generic THERMO-003 feasibility slice if a small equation-backed scope is clear.

## PR-04 Build-First Roadmap Reframe

Date: 2026-06-19

Status: `complete` once merged for documentation and guardrail-test scope.

Completed in this pass:

- Reframed VALIDATION-DATA-001 as deferred validation/calibration work rather
  than the blocker for all further repository progress.
- Kept validation in the roadmap and preserved the ingestion gate: real
  observations remain required before making validation, calibration, or
  empirical comparison claims.
- Set the current next PR to PRODUCT-001: build-first exploratory
  virtual-experiment expansion.
- Queued THERMO-003 for dynamic thermodynamic and entropy constraints and
  BIO-003 for generic mechanism expansion through implemented, tested process
  laws.
- Added guardrail tests so active docs keep validation deferred, keep
  PRODUCT-001 current, and require build-first work to preserve explicit
  assumptions, uncertainty, provenance, limitations, and missing-mechanism
  reporting.

No scientific model, numerical method, runtime behavior, output schema, public
API, dataset, validation observation, calibration routine, thermodynamic
equation, entropy calculation, or biology implementation was added in this
documentation reframe.

Recommended next task: implement PRODUCT-001 as a small code PR that expands
researcher-facing exploratory virtual experiments while keeping all assumptions
and unsupported biology explicit.

## PR-03 VALIDATION-DATA-001 Ingestion Gate

Date: 2026-06-19

Status: `blocked/partial` for real-data ingestion.

Completed in this pass:

- Expanded `foundation_progress/VALIDATION_DATA_001_FIRST_TIMECOURSE.md` from
  a stub into an active ingestion-gate/status document.
- Recorded that the existing Resa/Buckin 2011 candidate review remains blocked
  because no ingestable observation rows, observation CSV, extraction metadata,
  uncertainty policy, or preprocessing/conversion record is present.
- Recorded that the existing Ariaeenejad 2020 PersiBGL1 Frontiers candidate
  remains blocked because no machine-readable time-course table exists locally
  and the time axis has an unresolved source-text conflict between hour-based
  evidence and one sentence saying 380 min.
- Recorded the required evidence for a future ingestion PR: exact
  figure/table/supplement identifier, observation rows, units,
  extraction/transcription method, extractor/date, preprocessing/conversion
  notes, uncertainty policy, and explicit limitations.
- Updated the active orchestration and next-steps docs so PR-03 remains the
  current next PR and PR-04 is not advanced.
- Added focused tests proving the two real candidate reviews remain blocked and
  data-free, `data/experiments/literature/` contains no real data files, and
  active docs do not mark VALIDATION-DATA-001 complete or advance beyond PR-03.

No dataset, `raw_data.csv`, `curated_data.csv`, `model_comparison.csv`,
`residuals.csv`, `validation_report.md`, observation rows, literature CSV,
scientific model, parameter, numerical method, runtime behavior, output schema,
public API, external API call, or biology was added.

Recommended next task: find or obtain source-backed numeric time-course
observations satisfying the gate, then open a separate VALIDATION-DATA-001
ingestion PR with dataset files, model-comparison artifacts, limitations, and
tests.

## PR-02 CASE-001 Researcher-Facing Enzyme-Chain Virtual Experiment

Date: 2026-06-19

Status: `complete` for the scoped CASE-001 researcher-facing API path once
PR-02 is merged.

Completed in this pass:

- Exposed the existing BIO-002 extracellular enzyme-chain template through the
  top-level researcher-facing `virtual_experiment(...)` / `VirtualExperiment`
  API using names and aliases for the generic cellulase source, cellulose film,
  and 30 C pH 5 assay context.
- Added registry compatibility metadata for the existing BIO-002 chain so the
  CASE-001 path selects `extracellular_enzyme_chain` without requiring users to
  call `run_extracellular_enzyme_chain_demo(...)` directly.
- Taught modelability to choose the best supported implemented process path
  when the same source/substrate class has multiple scoped alternatives, so
  BIO-001 surface-catalysis metadata does not block the BIO-002 chain path.
- Taught exploratory ensemble simulation and standard result tables to use the
  BIO-002 template-owned parameter records and template suggested experiments.
- Added CASE-001 coverage proving alias resolution, standard output files,
  limitations, suggested experiments, no live socket use, and no unsupported
  whole-fungus/PET/lignin output states or metrics.
- Updated CASE-001 and orchestration docs to mark PR-02 complete once merged
  and set PR-03 VALIDATION-DATA-001 as the next PR.

No new biological mechanism, validation dataset, live external source call,
invented parameter, whole-fungus growth, secretion, uptake, biomass, PET,
lignin, full lignocellulose, organism-specific physiology, or empirical
validation claim was added.

## PR-01 Roadmap Orchestration And Phase Status Tracker

Date: 2026-06-19

Status: `complete` for the scoped documentation/status guardrail once PR-01 is
merged.

Completed in this pass:

- Added `foundation_progress/ROADMAP_ORCHESTRATION_STATUS.md` as the active
  orchestrated-PR workflow and phase-status tracker.
- Recorded the maker/reviewer/comment-loop/merge/next-PR workflow.
- Recorded the PR queue with PR-02 CASE-001 as the current next slice and
  VALIDATION-DATA-001 queued after it.
- Reconciled scoped completion/partial status for SOURCE-002, RESOLVE-001,
  ASSEMBLY-001 case-template basics, API-003, BIO-READINESS-LITE, BIO-002, and
  Phase 2 static balance checks.
- Added completion rules requiring tests, active-doc updates, `progress.md`
  updates, honest scope/limitations, no live external APIs in tests or
  simulation, no unsupported biology, and no silent fallback constants.
- Updated the active roadmap and next-steps document so future agents do not
  rebuild already completed scoped slices or treat `old_progress/` as binding.

No scientific models, parameters, numerical methods, public APIs, runtime
behavior, output schemas, source adapters, registry records, or biology changed.

## Phase 2 Task 4b Process-Reaction Binding For Static Balance Checks

Date: 2026-06-18

Status: `complete` for the corrective P2.4b binding gate. Static balance
checks can no longer pass merely because an unrelated declared reaction is
balanced; requested checks must now bind explicit reaction metadata to the
actual assembled process contributions through explicit process-state to
chemical-species mappings.

Completed in this pass:

- Added explicit `process_id` and state-to-species binding support for
  `balance_checks`.
- Verified each requested assembly-time balance check against the assembled
  process contribution signs and coefficients before running the chemical
  residual validator.
- Included process/reaction binding evidence, mapped process stoichiometry,
  reaction stoichiometry, role checks, product-map evidence, tolerance, and
  failure reasons in validation details.
- Added static balance check evidence to successful `AssemblyReport` payloads.
- Made required scientific/strict balance checks block on missing, unknown,
  duplicated, contradictory, coefficient-mismatched, or unrelated bindings.
- Kept configs without `balance_checks` unchanged.
- Added adversarial tests proving a process `A -> B` cannot pass with
  unrelated balanced metadata `X2 -> 2X`, plus missing/unknown/duplicated/
  contradictory binding tests and a product-map-backed
  homogeneous-Michaelis-Menten binding test.

No trajectory-level balance validation, dynamic Gibbs calculation, activity
model, redox potential, biological data, literature value, process rate
equation, solver equation, or real registry chemistry was added.

## Phase 2 Tasks 3-4 Static Metadata Schema And Assembly-Time Balance Checks

Date: 2026-06-16

Status: `complete` for the scoped P2.3/P2.4 static metadata and
assembly-time balance enforcement foundation. The full thermodynamic
feasibility blocker remains unresolved because dynamic reaction quotients,
activities, activity coefficients, redox potentials, and solver-time
thermodynamic constraints are still not implemented.

Completed in this pass:

- Added optional model-config schema surfaces for `chemistry_metadata`,
  `reaction_metadata`, and `balance_checks` while preserving existing config
  compatibility and raw passthrough.
- Added assembly-time static balance parsing for explicit configured species,
  reaction participant, and reaction metadata.
- Wired optional assembly-time elemental, charge, and electron/redox balance
  checks into configured model assembly.
- Made scientific and strict modes block required assembly-time static checks
  that fail, are unsupported, or are inconclusive because metadata are absent.
- Kept toy and exploratory runs non-blocking for these optional checks while
  recording `failed` or `inconclusive` validation results in the existing
  result/output validation path.
- Added tests proving schema recognition, passing metadata-backed elemental,
  charge, and electron-equivalent checks, exploratory inconclusive metadata
  output, scientific blocking on failed balance, strict blocking on missing
  reaction metadata, and unchanged existing configured-workflow behavior.

No dynamic thermodynamic validation, reaction-quotient calculation, activity
model, activity coefficient, redox potential, biological data, literature
value, process rate equation, solver equation, or real registry chemistry was
added.

## Phase 2 Task 2 Static Elemental and Thermodynamic Validator Foundation

Date: 2026-06-15

Status: `complete` for the scoped static validator foundation. The full
thermodynamic feasibility blocker remains unresolved because dynamic reaction
quotients, activities, activity coefficients, and solver-time thermodynamic
constraints are still not implemented.

Completed in this pass:

- Extended `ValidationResult` with backward-compatible `status`, `severity`,
  and `required` fields.
- Added explicit metadata residual primitives for elemental, charge, and
  electron-equivalent balance.
- Added static validators for elemental balance, charge balance,
  electron/redox balance, and condition-specific Gibbs feasibility.
- Made missing composition, charge, electron-equivalent metadata, unknown
  condition values, and unknown Gibbs values report `inconclusive` rather than
  passed.
- Made provenance failures report structured failed validation results.
- Registered the new static validators through `ValidatorRegistry` for
  explicit inline model-config use.
- Extended configured-output validation summaries with status and severity
  counts while preserving existing boolean `passed` behavior.
- Preserved strict-mode rejection of confirmed failures and added handling for
  required inconclusive/unsupported validation statuses.
- Added tests for balanced/unbalanced synthetic reactions, missing metadata,
  charge/electron checks, favorable/unfavorable/unknown Gibbs metadata,
  provenance failure, config registry integration, exploratory versus strict
  behavior, serialization, and existing validator compatibility.

No dynamic thermodynamic validation, reaction-quotient calculation, activity
model, activity coefficient, redox potential, biological data, literature
value, process rate equation, solver equation, or real registry chemistry was
added.

## Phase 2 Task 1 Thermodynamic and Balance Enforcement Design

Date: 2026-06-15

Status: `complete` for the scoped implementation plan only. The confirmed
thermodynamic feasibility and complete stoichiometric/redox enforcement
blockers remain unresolved.

Completed in this pass:

- Added `FUNGMOD_PHASE_2_THERMODYNAMIC_AND_BALANCE_ENFORCEMENT.md` as the
  staged design for thermodynamic and balance enforcement.
- Defined standard Gibbs energy, condition-specific Gibbs energy, and dynamic
  reaction Gibbs energy as separate concepts.
- Documented what FungMod can honestly enforce with current metadata and what
  remains unsupported.
- Specified elemental, charge, electron/redox, residual, tolerance, unit,
  provenance, mode, assembly-time, post-simulation, schema, API, output,
  migration, test, and milestone requirements.
- Updated `findings.yaml` only to point `P1-AUDIT-THERMO-001` and
  `P1-AUDIT-BALANCE-001` to the Phase 2 plan.

No production thermodynamic enforcement, redox enforcement, formulas, charges,
activity models, Gibbs values, biological data, solver behavior, public APIs,
output schemas, numerical methods, or scientific claims changed.

## Phase 1 Task 5 Documentation and Quality-Gate Synchronization

Date: 2026-06-15

Status: `complete` for the scoped documentation, audit-status, and Phase 1
quality-gate synchronization.

Completed in this pass:

- Reconciled active README capability claims, public API documentation,
  roadmap status notes, Phase 1 reports, and the machine-readable audit
  catalogue with the post-P1.4 repository state.
- Marked Phase 1 complete in
  `FUNGMOD_PHASE_1_REPOSITORY_TRUTH_AND_EXECUTION_HARDENING.md` only after
  verifying the instruction hierarchy, audit catalogue, native execution
  guardrails, adapter retirement, Ruff, Pyright, full tests, and coverage gate.
- Clarified that BIO-001/BIO-002 cellulose-related paths are implemented and
  technically verified only for scoped exploratory pilots, not scientifically
  validated default cellulose degradation.
- Added a migration note for former `process.as_reaction()` users: use native
  process execution or construct an explicit low-level `Reaction`.
- Removed the unsupported tracked notebook checkpoint artifact.
- Added focused documentation synchronization tests for public API docs,
  capability labels, adapter-retirement wording, audit status, checkpoint
  cleanup, and Phase 1 completion status.

No scientific models, parameters, numerical methods, public APIs, runtime
behavior, output schemas, or biology changed.

## Phase 1 Task 1 Instruction-Hierarchy Cleanup

Date: 2026-06-14

Status: `complete` for the scoped instruction/documentation guardrail cleanup.

Completed in this pass:

- Added root `AGENTS.md` as the binding Codex/contributor instruction
  hierarchy.
- Marked `old_progress/` as historical and non-binding while retaining the
  archived restrictions as context.
- Replaced active blanket biology-gate wording with the current rule: no
  unsupported or invented biology, not no biology.
- Added tests that protect the active instruction hierarchy without scanning
  archived files as active instructions.

No scientific or numerical behavior changed. No biology was added.

## Phase 1 Task 2 Audit Finding Reconciliation

Date: 2026-06-14

Status: `complete` for the scoped current-state finding catalogue.

Completed in this pass:

- Added `findings.yaml` as the machine-readable current finding-status
  catalogue for critical/high audit claims.
- Added `foundation_progress/validation/PHASE_1_CURRENT_FINDING_STATUS.md` as
  the concise human-readable status matrix.
- Classified stale and resolved technical audit claims separately from
  confirmed scientific limitations.
- Added `tests/test_findings_catalogue.py` to ensure the catalogue parses,
  finding IDs remain unique, status/severity values are valid, required
  evidence sections exist, and historical claims remain preserved.

No production, scientific, numerical, or public API behavior changed. No audit
finding resolutions were implemented in this task.

## Phase 1 Task 3 Native Execution Path Verification

Date: 2026-06-14

Status: `complete` for the scoped native execution path verification.

Completed in this pass:

- Added `foundation_progress/validation/PHASE_1_NATIVE_EXECUTION_PATHS.md`
  with the current execution-path matrix for configured workflows,
  VirtualExperiment, plugin helpers, notebooks, calibration/uncertainty
  wrappers, reaction-diffusion, and direct low-level solver APIs.
- Strengthened `tests/test_guardrails_native_execution.py` so supported
  configured well-mixed workflows fail if they instantiate the legacy
  `SimulationEngine`, construct `Reaction` objects, or call concrete
  `as_reaction()` adapters.
- Added a configured validator trace proving validators loaded through
  `ValidatorRegistry` execute after the native process solver returns a result.
- Added a configured unsupported-geometry regression proving `film_1d`
  configured geometry fails explicitly instead of silently changing solver
  paths.
- Recorded active process-to-Reaction compatibility adapters as `FD-006` in
  `ARCHITECTURE_DEBT.md` for the P1.4 retirement/containment decision.

No production, scientific, numerical, public API, or output semantics changed.
The low-level `Reaction`, `SimulationEngine`, and `ReactionDiffusionEngine1D`
APIs remain intentionally supported low-level surfaces.

## Phase 1 Task 4 Legacy Adapter Retirement

Date: 2026-06-14

Status: `complete` for the scoped process-to-`Reaction` adapter retirement.

Completed in this pass:

- Removed concrete `as_reaction()` compatibility adapters from homogeneous and
  surface process classes.
- Removed the shared `_reaction_from_process` helper that existed only to build
  legacy `Reaction` objects from `Process` objects.
- Rewrote adapter-dependent process tests so they verify process execution
  through native `ModelBuilder` / `AssembledModel.run()` instead of the legacy
  `SimulationEngine`.
- Kept direct low-level `Reaction`, `SimulationEngine`, and
  `ReactionDiffusionEngine1D` APIs intact where they are intentionally
  supported and tested.
- Added `foundation_progress/validation/PHASE_1_LEGACY_ADAPTER_RETIREMENT.md`
  and marked `FD-006` resolved in `ARCHITECTURE_DEBT.md`.
- Strengthened native-execution guardrails so process modules cannot silently
  reintroduce `as_reaction()` or `_reaction_from_process`.

No supported configured numerical outputs, scientific assumptions, model
parameters, solver settings, public configured APIs, or output schemas changed.

## CLEANUP-001 / SCHEMA-001 Researcher Output Semantics

Date: 2026-06-07

Status: `complete` for the scoped cleanup/schema hardening pass.

Completed in this pass:

- Made the central virtual-experiment directive the active README/progress
  entry point.
- Relabeled toy/synthetic configured assets and notebooks as software-test or
  example fixtures, not scientific records.
- Added versioned virtual-experiment output schema files:
  `virtual_experiment_output_schema.json` and
  `virtual_experiment_output_data_dictionary.csv`.
- Added standard `missing_parameters.csv` and `suggested_experiments.csv`
  tables to virtual-experiment output bundles.
- Added `range_scope`, `range_interpretation`, and `allowed_use` semantics to
  registry parameter records and sampled/provenance output tables without
  removing exact, range, distribution, unknown, or exploratory-prior support.
- Renamed BIO-001 mass-valued product output from concentration wording to
  amount wording.
- Marked BIO-001 accessible-site fraction as a derived proxy rather than a
  modeled accessibility state.
- Added metadata-only environment-grid guardrails so environment summaries are
  explicitly non-rankable and non-plottable as response models unless an
  active response model or condition-specific parameter status is present.

No new data, new biology, or scientific-value edits were added.

## BIO-001 Cellulose Surface Degradation

Date: 2026-06-07

Status: `complete` for a first exploratory insoluble cellulose-like
surface-degradation virtual experiment.

Completed in this pass:

- Added BIO-001 registry records for a generic cellulase enzyme source,
  cellulase-like enzyme class, insoluble cellulose-film substrate, pilot assay
  environment, and surface-catalysis process compatibility.
- Added explicitly marked `exploratory_prior` parameter records for surface
  catalytic rate, adsorption constant, accessible surface area, initial
  cellulose-film mass, and initial cellulase concentration.
- Reused the existing generic `SurfaceCatalysisProcess` and
  `SurfaceCatalysisFactory`; no duplicate surface process was introduced.
- Added exploratory configured-model mode support so sampled BIO-001 runs do
  not need to masquerade as toy runs.
- Extended virtual-experiment output tables with surface-specific degradation
  metrics: solid substrate remaining/degraded fraction, accessible-site
  fraction proxy, soluble product amount, and final product yield.
- Added BIO-001 limitations stating that this is enzyme-mediated surface
  degradation, not whole-fungus growth, secretion, uptake, biomass, oxygen
  limitation, or full lignocellulose modeling.
- Added the executable notebook
  `notebooks/07_bio001_cellulose_surface_virtual_experiment.ipynb`.

See `foundation_progress/BIO_001_CELLULOSE_SURFACE_DEGRADATION.md` for scope,
parameters, output tables, and limitations.

## DATA-002 SABIO-RK Reaction 618 Parameter Ranges

Date: 2026-06-07

Status: `complete` for local Reaction 618 multi-entry parameter-range curation.

Completed in this pass:

- Hardened the local SABIO-RK Reaction 618 beta-glucosidase/cellobiose curation
  into eligible/excluded CSV tables plus JSON and Markdown parameter-range
  summaries.
- Preserved EntryID, organism, enzyme type, pH, temperature, buffer,
  publication/PubMed metadata, source fields, and explicit exclusion reasons.
- Added scoped Km/kcat ranges for all eligible entries, organism, exact pH,
  exact temperature, organism+pH, wildtype-only, and mutant-only groups.
- Marked sparse groups as `insufficient_n` instead of presenting them as robust
  ranges.
- Clarified registry provenance for the all-eligible `literature_range` Km and
  kcat records without overwriting selected exact EntryID 35622 values, the
  unknown enzyme concentration record, or the exploratory enzyme prior.
- Extended virtual-experiment sampled-parameter tables with
  `parameter_source_class` so outputs can distinguish selected exact values,
  literature ranges, user-supplied exploratory priors, and unknown sources.

See `foundation_progress/DATA_002_REACTION_618_PARAMETER_RANGES.md` for scope,
limitations, curated outputs, and interpretation.

## ENV-001 Environment Grids for Virtual Experiments

Date: 2026-06-07

Status: `complete` for runtime environment-grid virtual-experiment support.

Completed in this pass:

- Added concrete `EnvironmentGrid` case generation for temperature, pH, and
  oxygen labels.
- Added runtime in-memory environment records and parameter-record overlay for
  metadata-only environment grid simulations.
- Extended virtual-experiment output tables with `environment_source` and
  `environment_effect_status`.
- Added `final_states.csv` and `environment_summary.csv`.
- Documented that Reaction 618 grid runs do not apply a temperature or pH
  response law; kinetics are reused as metadata-only context unless a future
  response model or condition-specific parameters are active.

See `foundation_progress/ENV_001_ENVIRONMENT_GRIDS.md` for scope,
limitations, and output-table details.

## BIO-002-GENERICITY Extracellular Enzyme-Chain Hardening

Date: 2026-06-13

Status: `complete` for reusable two-step chain assembly and software
verification.

Completed in this pass:

- Refactored `src/fungal_model/screening/enzyme_chain.py` so the generic
  assembler reads entity definitions, loaders, state roles, state units,
  initial states, catalyst states, process sequence, parameter-record IDs,
  product-map IDs, stoichiometric coefficients, conservation weights, output
  labels, limitations, and suggested experiments from registry/template data.
- Moved the current cellulose-equivalent demonstration entity metadata,
  conserved-equivalent definition, and standard-table output labels into
  `data_registry/case_templates/case_templates.yml`.
- Removed hardcoded product-yield and conserved-weight fallbacks from the
  enzyme-chain table writer.
- Added validation for malformed chain templates, including non-positive or
  non-finite coefficients, empty required maps, unknown roles, missing units,
  legacy product-state conflicts, missing conservation metadata, inconsistent
  conservation weights, and invalid output references.
- Added `tests/test_bio002_generic_chain_assembly.py`, with an unrelated
  `polymer_X -> oligomer_Y -> monomer_Z` fixture using different entities,
  states, catalyst names, parameters, output labels, yields `1.5` and `3.0`,
  and conserved weights `1`, `2/3`, and `2/9`.
- Added the machine-readable real mechanism proposal
  `foundation_progress/proposals/BIO_002_EXTRACELLULAR_ENZYME_CHAIN.yml` and
  a readiness test that validates the actual file.
- Preserved the Reaction 618 behavior where beta-D-glucose formed is
  approximately two times cellobiose consumed.

Verification:

- `.venv/bin/python -m pytest tests/test_pre_bio001_stoichiometry_and_assembly.py`
  - Result: 4 passed.
- `.venv/bin/python -m pytest tests/test_bio_readiness_lite.py`
  - Result: 8 passed.
- `.venv/bin/python -m pytest tests/test_bio002_extracellular_enzyme_chain.py`
  - Result: 3 passed.
- `.venv/bin/python -m pytest tests/test_bio002_generic_chain_assembly.py`
  - Result: 11 passed.
- `.venv/bin/python -m ruff check src tests`
  - Result: all checks passed.
- `.venv/bin/python -m pyright --pythonpath "$(.venv/bin/python -c 'import sys; print(sys.executable)')"`
  - Result: 0 errors, 0 warnings, 0 informations.
- `.venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing`
  - Result: 540 passed; total coverage 84.30%, above the 80% gate.

See `foundation_progress/BIO_002_ENZYME_CHAIN_DEGRADATION.md` for the generic
contract, demonstration-specific data, failure modes, and limitations.

## Foundation-First Reset: Milestone 1 Governance Gate

Date: 2026-05-27

Status: `complete` for the initial governance and architecture guardrail scope.

Completed in this foundation-first pass:

- Added `ARCHITECTURE_DEBT.md` as the required containment register for
  temporary architecture compromises.
- Documented the current narrow transitional debts:
  - `FD-001`: legacy PET workflow still exported from generic workflows;
  - `FD-002`: PET-only substrate branch in YAML loading;
  - `FD-003`: `AssembledModel.run()` is still non-native execution debt.
- Added guardrail tests for:
  - PET/product hardcoding in generic source paths;
  - shortcut/fallback patterns in high-risk modules;
  - current and next-milestone public API expectations.
- Added a GitHub PR template requiring scope, tests, limitations, shortcut
  removal, architecture debt, and progress-doc updates.
- Added a minimal GitHub Actions CI workflow that installs `.[dev]` and runs
  `pytest`.
- Updated the notebook test path to the actual `notebooks/examples/` location
  so notebook smoke checks execute rather than failing on discovery.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 7 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 160 passed.

Next foundation milestone: Milestone 2, generic public API names
(`run_configured_model`, `load_model_config`, and future `ProcessLibrary`)
without faking runnable implementation.

## Foundation-First Reset: Milestone 2 Generic Public API

Date: 2026-05-27

Status: `complete` for generic-first public API introduction.

Completed in this foundation-first pass:

- Added `src/fungal_model/io/model_config.py` with a real `ModelConfig`,
  `load_model_config`, and top-level generic model-config validation.
- Added `src/fungal_model/workflows/configured_model.py` with
  `run_configured_model`.
- Made `run_configured_model` load the generic config and fail with a
  structured `ConfiguredModelRunReport` until registry loading, process
  factories, native `AssembledModel.run()`, and configured output bundles exist.
- Added `ProcessLibrary` as the public foundation process-library name over
  current already-built process objects.
- Exposed `load_model_config`, `run_configured_model`, `ProcessLibrary`,
  `ModelConfig`, `ConfiguredModelExecutionError`, and
  `ConfiguredModelRunReport` from top-level `fungal_model`.
- Removed `run_pet_surface_integration` and `PETSurfaceWorkflowConfig` from
  top-level `fungal_model` exports.
- Kept the legacy PET workflow available from `fungal_model.workflows` and made
  it emit a `DeprecationWarning`.
- Updated README workflow guidance to point at the generic configured-model API.
- Updated `ARCHITECTURE_DEBT.md` with `FD-004` for the structural preflight
  runner boundary.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_full_integration_workflow.py`
- Result: 12 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 162 passed.

Next foundation milestone: Milestone 3, registry-based loading for substrates,
geometries, product maps, and validators.

## Foundation-First Reset: Milestone 3 Registry-Based Loading

Date: 2026-05-27

Status: `complete` for the initial registry-based loader boundary.

Completed in this foundation-first pass:

- Added neutral config parameter parsing in `src/fungal_model/io/parameters.py`.
- Added `src/fungal_model/io/registries.py` with:
  - `SubstrateLoaderRegistry`;
  - `GeometryLoaderRegistry`;
  - `ProductMapRegistry`;
  - `ValidatorRegistry`;
  - `RegistryLookupError`.
- Changed `load_substrate` to delegate through `SubstrateLoaderRegistry`.
- Changed `load_geometry` to delegate through `GeometryLoaderRegistry`.
- Added default non-PET substrate loaders for `generic_solid` and
  `generic_dissolved` foundation benchmark configs.
- Added default geometry loaders for `well_mixed` and `film_1d`.
- Added default product-map loaders for `one_to_one` and `stoichiometric`
  configured state mappings.
- Added default validator loaders for `non_negative` and `mass_balance`.
- Added `src/fungal_model/plugins/pet/` with explicit PET substrate loader
  registration.
- Migrated the legacy PET integration workflow and PET config tests to use the
  explicit PET plugin registry.
- Resolved architecture debt `FD-002`: the generic YAML substrate loader no
  longer imports PET or branches on PET.
- Updated README loader guidance to describe the registry boundary.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_registry_based_loading.py tests/test_config_io.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_full_integration_workflow.py`
- Result: 24 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 168 passed.

Next foundation milestone: Milestone 4, model config object expansion for
homogeneous, PET plugin, and dummy non-PET configs.

## Foundation-First Reset: Milestone 4 Model Config Objects

Date: 2026-05-27

Status: `complete` for generic model-config object loading.

Completed in this foundation-first pass:

- Expanded `src/fungal_model/io/model_config.py` from top-level validation into
  structured config objects:
  - `ConfigReference`;
  - `EntityConfigRefs`;
  - `ParameterSetConfig`;
  - `ProcessConfig`;
  - `InitialStateConfig`;
  - `TimeConfig`;
  - `ValidatorConfig`;
  - `OutputConfig`.
- Kept `load_model_config` generic and made it return structured sections
  without executing loaders, factories, or solvers.
- Added canonical foundation model-config shells:
  - `data/model_configs/toy_homogeneous_ab.yml`;
  - `data/model_configs/toy_surface_pet_plugin.yml`;
  - `data/model_configs/toy_surface_dummy_non_pet.yml`.
- The plugin surface config and dummy non-PET surface config use the same
  `surface_catalysis` process shape and configured state mappings.
- Updated schema validation so `model_config` records are treated as
  config-of-configs rather than raw parameter-set files.
- Added `tests/test_model_config_loading.py`.
- Updated README data/config guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_model_config_loading.py tests/test_config_io.py tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 174 passed.

Next foundation milestone: Milestone 5, product-map configs and loader path
for configured product-state mappings.

## Foundation-First Reset: Milestone 5 Product-Map Configs

Date: 2026-05-27

Status: `complete` for file-backed product-map config loading.

Completed in this foundation-first pass:

- Added `src/fungal_model/io/product_maps.py` with `load_product_map`.
- Extended `ProductReleaseMap` with optional `name`, `maturity`, and `source`
  metadata while preserving existing process compatibility.
- Updated `ProductMapRegistry` loaders to preserve product-map metadata from
  config files.
- Added canonical product-map configs:
  - `data/product_maps/toy_surface_plugin_mass_equivalent.yml`;
  - `data/product_maps/toy_surface_dummy_mass_equivalent.yml`.
- Updated the plugin surface and dummy non-PET surface model configs to
  reference product-map files instead of embedding product maps inline.
- Added tests proving product maps load from files, preserve arbitrary state
  names, fail on unknown map types, and are referenced from surface model
  configs.
- Updated README data/config guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_product_map_configs.py tests/test_model_config_loading.py tests/test_registry_based_loading.py tests/test_config_io.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 31 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 178 passed.

Next foundation milestone: Milestone 6, process factory library foundation.

## Foundation-First Reset: Milestone 6 Process Factory Library

Date: 2026-05-27

Status: `complete` for the foundation process-factory layer.

Completed in this foundation-first pass:

- Added `src/fungal_model/processes/factories.py` with:
  - `BuildDecision`;
  - `ProcessBuildContext`;
  - `ProcessFactory`;
  - `FirstOrderFactory`;
  - `MassActionFactory`;
  - `HomogeneousMichaelisMentenFactory`;
  - `SurfaceCatalysisFactory`;
  - `default_foundation_factories`.
- Extended `ProcessLibrary` so it can register factories, reject duplicate
  factories, return a factory by process type, build decisions, and build
  process objects from structured `ProcessConfig` entries.
- Kept existing `ProcessRegistry` behavior intact for already-built process
  objects.
- Verified that:
  - homogeneous `toy_homogeneous_ab.yml` builds through the first-order factory;
  - plugin surface and dummy non-PET surface configs build through the same
    generic surface factory;
  - mass-action and homogeneous Michaelis-Menten factories build generic process
    objects;
  - missing state units/product maps produce structured `BuildDecision`
    failures;
  - the factory module contains no plugin imports or domain names.
- Updated `run_configured_model` preflight reporting so it now names missing
  process-factory wiring, not a missing process-factory library.
- Updated README process-library guidance.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_process_factory_library.py tests/test_model_config_loading.py tests/test_product_map_configs.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 29 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 188 passed.

Next foundation milestone: Milestone 7, native `AssembledModel.run()`.

## Current Roadmap Slice

Current active milestone: **Milestones 1-10 complete for the first roadmap
implementation slice**.

Status: `complete` for the tested scope documented below. Remaining work is
future expansion beyond the first long-term architecture pass.

Completed milestone: **Milestone 2: Generic result object**.

Milestone 2 status: `complete` for the first standardized result/export scope.

Completed in Milestone 2:

- Added `src/fungal_model/results/result.py`.
- Added `src/fungal_model/results/__init__.py`.
- Exposed roadmap `SimulationResult` from top-level `fungal_model`.
- Added a standard result wrapper that can be built from:
  - existing well-mixed ODE results;
  - existing 1D reaction-diffusion results.
- Added state and rate accessors:
  - `state(name)`
  - `rate(name)`
- Added validation attachment and validation report export.
- Added plot methods:
  - `plot_state`
  - `plot_states`
  - `plot_rates`
  - `plot_mass_balance`
- Added standardized output saving:
  - `record.json`
  - `model_assembly_report.json`
  - `assumptions.json`
  - `parameters.csv`
  - `validation_report.json`
  - `solver_report.json`
  - `state_trajectories.csv`
  - `process_rates.csv`
  - `derived_quantities.csv`
  - `figures/state_trajectories.png`
  - `figures/process_rates.png`
  - optional `figures/mass_balance.png`
  - `logs/warnings.txt`
  - `logs/provenance_report.md`
- Updated examples 01-06 to save standardized result outputs while preserving
  their existing legacy files and plots.
- Added `tests/test_results.py`.

Milestone 2 verification:

- `./.venv/bin/python -m pytest tests/test_results.py tests/test_simulation_record.py`
- Result: 4 passed.
- Re-ran examples 01-06 successfully.

Completed milestone: **Milestone 3: Generic homogeneous kinetics**.

Milestone 3 status: `complete` for the first generic homogeneous process scope.

Completed in Milestone 3:

- Added `src/fungal_model/processes/homogeneous.py`.
- Added generic homogeneous process classes:
  - `FirstOrderDecayProcess`
  - `MassActionProcess`
  - `HomogeneousMichaelisMentenProcess`
- Added `homogeneous_process_assumption`.
- Added `as_reaction()` adapters so the new process classes can run through the
  existing ODE `SimulationEngine` before the future process solver exists.
- Updated process and top-level package exports.
- Migrated examples 01 and 02 to build reactions from generic homogeneous
  process classes.
- Added `tests/test_homogeneous_processes.py`.

Milestone 3 behavior now available:

- First-order homogeneous decay/product formation can be declared as a generic
  process and converted into a runnable `Reaction`.
- Generic mass-action processes check state units and rate units.
- Generic homogeneous Michaelis-Menten processes support:
  - classic `Vmax * S / (Km + S)`;
  - enzyme-explicit `kcat * E * S / (Km + S)`;
  - required parameter declarations for model assembly.
- Homogeneous process assumptions stay generic and do not mention PET.

Milestone 3 verification:

- `./.venv/bin/python -m pytest tests/test_homogeneous_processes.py tests/test_michaelis_menten.py tests/test_reaction_engine.py`
- Result: 16 passed.
- Re-ran examples 01 and 02 successfully after migration.

Completed milestone: **Milestone 4: Generic surface process refactor**.

Milestone 4 status: `complete` for the first generic surface-process scope.

Completed in Milestone 4:

- Added `src/fungal_model/processes/surface.py`.
- Added generic surface process components:
  - `AccessibleSitePool`
  - `AccessibleSurfaceAreaModel`
  - `LangmuirAdsorptionModel`
  - `EquilibriumSurfaceCoverageModel`
  - `SurfaceCatalysisModel`
  - `ProductReleaseMap`
  - `SurfaceCatalysisProcess`
  - `BondCleavageProcess` alias
  - `surface_catalysis_rate`
- Added `PETAccessibleSurfaceAreaModel` to `src/fungal_model/substrates/pet.py`.
- Added `pet_product_release_map` for the current mass-equivalent PET benchmark.
- Refactored `PETSurfaceHydrolysisRateLaw` so no-modifier PET surface
  hydrolysis delegates to a generic `SurfaceCatalysisProcess`.
- Kept environmental PET scaling working by applying temperature/pH modifiers
  around the generic `surface_catalysis_rate`.
- Updated process, substrate, and top-level exports.
- Added `tests/test_generic_surface_processes.py`.
- Updated `README.md` with the new roadmap capabilities and limitations.

Milestone 4 behavior now available:

- A generic surface catalysis process can run a dummy non-PET solid substrate.
- Generic surface modules do not import PET-specific modules.
- PET exposes accessibility and product-release composition pieces instead of
  making the generic surface machinery live inside PET.
- PET can still run through the existing `PETSurfaceHydrolysisRateLaw` API.
- PET can also expose its generic composed process through
  `PETSurfaceHydrolysisRateLaw.as_generic_process()`.
- Missing PET accessible surface area still fails honestly.
- The PET mass-equivalent benchmark product map can be checked for mass
  conservation.

Milestone 4 verification:

- `./.venv/bin/python -m pytest tests/test_generic_surface_processes.py tests/test_surface_pet.py tests/test_environmental_modifiers.py`
- Result: 26 passed.
- Re-ran examples 03-06 successfully after the generic surface refactor.

Completed milestone: **Milestone 5: Environment object and modifiers**.

Milestone 5 status: `complete` for the first environment/modifier scope.

Completed in Milestone 5:

- Added `src/fungal_model/entities/environment.py`.
- Added `src/fungal_model/entities/__init__.py`.
- Added `Environment` with temperature, pH, oxygen, water activity, nutrient,
  ionic-strength, pressure, boundary-condition, validity-label, source, notes,
  and assumptions fields.
- Added environment validation and unit checks.
- Added `src/fungal_model/modifiers/`.
- Added environment-driven modifiers:
  - `TemperatureModifier`
  - `PHModifier`
  - `WaterActivityModifier`
  - `OxygenModifier`
  - `ProductInhibitionModifier`
- Added explicit assumptions for water activity, oxygen limitation, and product
  inhibition modifiers.
- Exposed environment and modifiers from top-level `fungal_model`.
- Added `tests/test_environment_modifiers.py`.

Milestone 5 behavior now available:

- Modifiers read environmental values from an `Environment` object rather than
  loose parameters.
- Temperature and pH modifiers reuse the existing Arrhenius and Gaussian pH
  implementations.
- Water activity can explicitly block rates below a sourced threshold.
- Oxygen can explicitly limit rates through a Monod-style activity.
- Product inhibition can explicitly reduce rates from a named product state.

Milestone 5 verification:

- `./.venv/bin/python -m pytest tests/test_environment_modifiers.py tests/test_environmental_modifiers.py`
- Result: 16 passed.

Completed milestone: **Milestone 6: Geometry abstraction**.

Milestone 6 status: `complete` for the first geometry abstraction scope.

Completed in Milestone 6:

- Added `src/fungal_model/geometry/`.
- Added base `Geometry` metadata object.
- Added functional `WellMixedGeometry`.
- Added functional `Film1DGeometry` wrapping the existing `UniformGrid1D`.
- Added explicit metadata placeholders:
  - `ParticleGeometry`
  - `SlabGeometry`
  - `PorousMediumGeometry`
- Added geometry assumptions and provenance/source checks.
- Exposed geometry classes from top-level `fungal_model`.
- Added `tests/test_geometry_abstractions.py`.

Milestone 6 behavior now available:

- Well-mixed models can carry explicit volume, optional surface area, and
  area/volume ratio metadata.
- 1D film models can carry explicit grid and boundary-condition metadata.
- Particle, slab, and porous-medium objects record metadata honestly without
  pretending solver support exists.

Milestone 6 verification:

- `./.venv/bin/python -m pytest tests/test_geometry_abstractions.py tests/test_reaction_diffusion.py`
- Result: 11 passed.

Completed milestone: **Milestone 7: Fungus/enzyme/process compatibility**.

Milestone 7 status: `complete` for the first compatibility-matching scope.

Completed in Milestone 7:

- Added `src/fungal_model/entities/enzyme.py`.
- Added explicit `Enzyme` entity with:
  - enzyme class;
  - target bond types;
  - target substrate names/classes;
  - catalytic and adsorption parameter sets;
  - pH/temperature profile placeholders;
  - validity labels;
  - assumptions, source, and notes.
- Added `Enzyme.compatible_with_substrate`.
- Extended `EnzymeProfile` with `compatible_capabilities`.
- Extended `Fungus` with explicit `uptake_capabilities` and
  `can_assimilate_product`.
- Extended `ModelBuilder` and `ModelAssemblyContext` with `enzymes`.
- Added `CompatibilityIssue` to assembly reports.
- Added assembly failure for incompatible mechanisms through
  `InvalidMechanismError`.
- Added compatibility checks for generic surface-catalysis processes:
  - missing catalyst entity;
  - incompatible enzyme/substrate/bond pairing;
  - fungus lacking a matching enzyme capability.
- Exposed `Enzyme` and `CompatibilityIssue` from package exports.
- Added `tests/test_enzyme_compatibility.py`.
- Updated `README.md`.

Milestone 7 behavior now available:

- Isolated enzyme surface systems can assemble without a fungus when a
  compatible enzyme entity is supplied.
- Living-fungus surface systems require the fungus to declare a compatible
  enzyme capability.
- Incompatible enzyme, substrate, and target-bond pairings fail with structured
  assembly reports.
- Product uptake/assimilation capability is explicit on the fungus.
- Living-fungus process assembly can block on unknown secretion parameters.

Milestone 7 verification:

- `./.venv/bin/python -m pytest tests/test_enzyme_compatibility.py tests/test_process_assembly.py tests/test_fungal_dynamics.py`
- Result: 24 passed.

Completed in this slice:

- Added structured assembly errors in `src/fungal_model/core/errors.py`:
  - `ModelAssemblyError`
  - `MissingProcessError`
  - `MissingParameterError`
  - `IncompatibleUnitsError`
  - `InvalidMechanismError`
- Added generic process contracts in `src/fungal_model/processes/base.py`:
  - `Process`
  - `StateVariableSpec`
  - `ParameterRequirement`
  - `ValidityDomain`
- Added a generic registry in `src/fungal_model/processes/registry.py`:
  - `ProcessRegistry`
  - `MissingProcessIssue`
  - empty `ProcessRegistry.default()` for the current milestone
- Added model assembly scaffolding in `src/fungal_model/processes/assembly.py`:
  - `ModelAssemblyContext`
  - `ProcessMatch`
  - `ParameterIssue`
  - `AssemblyReport`
  - `AssembledModel`
  - `ModelBuilder`
- Added `src/fungal_model/processes/__init__.py` exports.
- Updated top-level package exports in `src/fungal_model/__init__.py`.
- Updated core exports in `src/fungal_model/core/__init__.py`.
- Added assembly tests in `tests/test_process_assembly.py`.

Milestone 1 behavior now available:

- A model can request named process types.
- A `ProcessRegistry` can match registered generic processes.
- Missing mechanisms fail with `MissingProcessError`.
- Missing parameters fail with `MissingParameterError`.
- Explicitly unknown parameters fail instead of receiving fallback constants.
- Missing provenance fails in scientific mode.
- Unsourced parameters are allowed only with `allow_unsourced_for_testing=True`.
- Incompatible parameter units fail separately with `IncompatibleUnitsError`.
- Assembly reports are both machine-readable (`to_dict`) and human-readable
  (`human_readable`).
- A successful assembly produces an `AssembledModel` containing matched
  processes, state variables, parameters, assumptions, validators, solver
  settings, and the assembly report.

Important deliberate limitation:

- `AssembledModel.run()` is a placeholder. Solver-backed execution through the
  process architecture belongs to later milestones. Current runnable models
  still use the existing `SimulationEngine` and `ReactionDiffusionEngine1D`.

Milestone 1 tests added:

- missing process gives a structured report;
- matched process with absent parameter gives a structured missing-parameter
  report;
- unknown parameter value blocks assembly;
- missing parameter provenance blocks assembly;
- testing escape hatch for unsourced parameters is explicit;
- incompatible units are reported separately;
- successful assembly exports state variables, assumptions, solver settings,
  and report data;
- generic process modules do not import PET-specific modules.

Verification:

- `./.venv/bin/python -m pytest tests/test_process_assembly.py`
- Result: 8 passed.

Full-suite verification for this slice:

- `./.venv/bin/python -m pytest`
- Result: 108 passed.

## Current Codebase Capability Inventory

### Scientific Governance

Status: `complete` for the existing foundation.

FungMod can:

- represent scientific parameters with names, symbols, values, units,
  uncertainties, sources, confidence levels, notes, and measurement methods;
- represent unknown parameters explicitly with `value=None`;
- require provenance before scientific runs;
- allow unsourced values only through explicit testing escape hatches;
- serialize parameter sets to JSON and YAML;
- represent modelling assumptions separately from parameters;
- enforce unit-bearing quantities through a shared `pint` registry.

Core files:

- `src/fungal_model/core/parameters.py`
- `src/fungal_model/core/provenance.py`
- `src/fungal_model/core/assumptions.py`
- `src/fungal_model/core/units.py`
- `src/fungal_model/core/errors.py`

### Existing Well-Mixed Solver

Status: `complete` for deterministic ODE reaction systems.

FungMod can:

- run deterministic well-mixed ODE models through `SimulationEngine`;
- use generic `Reaction` objects with unit-checked rate laws;
- validate reaction provenance before scientific execution;
- require unit-bearing initial states and simulation times;
- record solver settings and solver metadata;
- return unit-bearing `SimulationResult` objects;
- create reproducible `SimulationRecord` JSON outputs.

Current limitation:

- This solver works with `Reaction` objects, not yet with the new
  process-centered `AssembledModel`.

Core files:

- `src/fungal_model/chemistry/reactions.py`
- `src/fungal_model/core/simulation.py`

### Validation

Status: `partial` relative to the long-term roadmap; substantial existing
foundation is implemented.

FungMod can validate:

- non-negativity;
- weighted mass balance;
- carbon conservation;
- oxygen limitation;
- biomass yield bounds;
- limiting-case suites;
- selected spatial checks for 1D diffusion and reaction-diffusion models.

Current limitations:

- Validation results do not yet use the roadmap's richer severity/residual
  schema everywhere.
- Validators are not yet automatically attached by the new `ModelBuilder`.
- Thermodynamic feasibility is metadata-supported but not solver-enforced.

Core files:

- `src/fungal_model/core/validators.py`
- `src/fungal_model/validation/`

### Homogeneous Kinetics

Status: `complete` for the existing dissolved-substrate benchmark layer;
`partial` relative to the future process architecture.

FungMod can:

- compute homogeneous Michaelis-Menten rates;
- compute enzyme-explicit Michaelis-Menten rates;
- wrap homogeneous kinetics as `Reaction` rate laws;
- check low-substrate, high-substrate, zero-substrate, zero-enzyme, and unit
  limiting cases.

Current limitations:

- Homogeneous process classes can adapt to the existing ODE `Reaction` engine,
  but `AssembledModel.run()` is still a future native process solver.
- PET is explicitly not treated as a valid dissolved-substrate default.

Core files:

- `src/fungal_model/kinetics/michaelis_menten.py`

### Surface and PET Kinetics

Status: `partial`.

FungMod can:

- represent PET as a solid polyester substrate with explicit unknown material
  parameters by default;
- derive accessible PET surface area from supplied surface area, roughness, and
  amorphous fraction/crystallinity metadata;
- compute Langmuir equilibrium surface coverage;
- run a PET-specific surface hydrolysis rate law through the existing
  `Reaction` engine;
- apply Arrhenius temperature and Gaussian pH modifiers to the PET surface
  hydrolysis rate law.

Current limitations:

- Generic surface catalysis exists and PET composes it through
  `PETAccessibleSurfaceAreaModel`, but the workflow still executes through the
  current ODE reaction adapter rather than a native process solver.
- PET product release is still represented in examples and the integration
  workflow as a simplified lumped mass-equivalent hydrolysate where noted.
- Dynamic adsorption/desorption states, evolving morphology, and resolved
  MHET/BHET/TPA/EG product stoichiometry remain future work.

Core files:

- `src/fungal_model/substrates/pet.py`
- `src/fungal_model/kinetics/langmuir.py`
- `src/fungal_model/kinetics/surface_kinetics.py`
- `src/fungal_model/kinetics/arrhenius.py`
- `src/fungal_model/kinetics/ph.py`

### Universal Substrate Metadata

Status: `partial`.

FungMod can:

- represent generic substrate metadata through `Substrate`;
- represent degradation products without assuming assimilation;
- create explicit unknown parameter sets for substrate metadata;
- expose placeholder metadata classes for cellulose, lignin, starch, and
  chitin;
- keep PET marked as the only currently partial substrate with an implemented
  process path.

Current limitations:

- Placeholder substrates do not yet assemble into scientific kinetic models.
- Substrate maturity levels from the roadmap are conceptually present through
  `completeness`, but not yet enforced by the new process registry.

Core files:

- `src/fungal_model/substrates/base.py`
- `src/fungal_model/substrates/pet.py`
- `src/fungal_model/substrates/cellulose.py`
- `src/fungal_model/substrates/lignin.py`
- `src/fungal_model/substrates/starch.py`
- `src/fungal_model/substrates/chitin.py`

### Fungal Dynamics

Status: `partial`.

FungMod can:

- represent basic fungus metadata;
- represent enzyme capabilities and enzyme profiles;
- model enzyme secretion from active biomass;
- model enzyme production cost;
- model enzyme decay;
- model active-biomass maintenance loss;
- gate product uptake and growth through explicit product-assimilation
  evidence;
- prevent non-assimilable products from causing biomass growth.

Current limitations:

- Fungi and enzymes now participate in model-builder compatibility matching,
  but the builder does not yet auto-generate full living-fungus ODE systems.
- Living-fungus simulations still use existing `Reaction` rate laws rather than
  native process-registry solver execution.

Core files:

- `src/fungal_model/fungi/base.py`
- `src/fungal_model/fungi/enzyme_profile.py`
- `src/fungal_model/fungi/growth.py`
- `src/fungal_model/fungi/metabolism.py`

### Stoichiometry and Thermodynamics

Status: `partial`.

FungMod can:

- parse elemental formula strings;
- represent stoichiometric reaction metadata;
- detect balanced and unbalanced stoichiometry;
- represent carbon-content metadata for state variables;
- represent oxygen-demand metadata;
- represent Gibbs free energy estimates with provenance.

Current limitations:

- Gibbs free energy is not yet enforced as a thermodynamic feasibility
  constraint during solving.
- Redox balance is not yet implemented as a process or validator beyond the
  current oxygen-demand checks.

Core files:

- `src/fungal_model/chemistry/stoichiometry.py`
- `src/fungal_model/chemistry/thermodynamics.py`

### Spatial Transport

Status: `partial`.

FungMod can:

- represent a uniform 1D finite-volume grid;
- represent no-flux, fixed-value, and periodic boundary conditions;
- compute a 1D finite-volume diffusion operator;
- run a 1D method-of-lines reaction-diffusion model;
- validate no-flux conservation, gradient smoothing, and high-diffusion
  well-mixed behavior.

Current limitations:

- Geometry metadata is now exposed through the roadmap `Geometry` hierarchy,
  but transport is not yet a `DiffusionProcess` assembled by `ModelBuilder`.
- 2D/3D, porous media, advection, and dynamic surface/volume coupling are not
  implemented.

Core files:

- `src/fungal_model/transport/geometry.py`
- `src/fungal_model/transport/diffusion.py`
- `src/fungal_model/transport/reaction_diffusion.py`

### Calibration

Status: `partial`.

FungMod can:

- compute unit-aware residuals;
- split sequential train/validation data;
- fit selected parameters with bounded least squares;
- report failed optimizer/model runs without hiding them;
- serialize fit results, residuals, covariance diagnostics, approximate
  confidence intervals where valid, and warnings.

Current limitations:

- Bayesian calibration is a placeholder.
- Calibration is generic but not yet integrated into the future result/output
  system.

Core files:

- `src/fungal_model/calibration/residuals.py`
- `src/fungal_model/calibration/fitting.py`
- `src/fungal_model/calibration/bayesian.py`

### Uncertainty and Sensitivity

Status: `partial`.

FungMod can:

- run Monte Carlo uncertainty propagation for normal, uniform, and lognormal
  parameter uncertainty specifications;
- preserve sample provenance;
- summarize output quantiles;
- run local finite-difference sensitivity analysis with dimensional and
  normalized sensitivities.

Current limitations:

- Global sensitivity is not implemented.
- Uncertainty bands are not yet integrated with a first-class roadmap
  `SimulationResult` plotting system.

Core files:

- `src/fungal_model/uncertainty/monte_carlo.py`
- `src/fungal_model/uncertainty/sensitivity.py`

### Examples

Status: `complete` for the current runnable example set.

Current examples demonstrate:

- first-order well-mixed reaction;
- homogeneous Michaelis-Menten dissolved-substrate benchmark;
- PET surface hydrolysis;
- PET surface hydrolysis with temperature and pH modifiers;
- fungal enzyme secretion and product-coupled growth;
- 1D PET film enzyme diffusion and local hydrolysis;
- Stage 12 wrapper examples for the current canonical examples.

Current limitations:

- Examples now save standardized result outputs, but most still use the
  existing solver/rate-law architecture rather than native process-centered
  solver execution.

Core files:

- `examples/`

### Notebooks

Status: `complete` for the first required notebook/smoke-test scope.

Implemented notebooks:

- `notebooks/00_quickstart.ipynb`
- `notebooks/01_process_library_demo.ipynb`
- `notebooks/02_surface_hydrolysis_demo.ipynb`
- `notebooks/03_fungus_on_pet_demo.ipynb`
- `notebooks/04_reaction_diffusion_demo.ipynb`
- `notebooks/05_calibration_and_uncertainty_demo.ipynb`

Important rule:

- Notebooks must import package code and demonstrate workflows. They must not
  contain core model implementation.
- `tests/test_notebooks.py` enforces that notebooks import `fungal_model`, do
  not define core classes/rate laws, and the quickstart notebook can execute as
  a smoke test.

### Data and Configuration

Status: `complete` for the first YAML schema/loader scope.

Implemented top-level folders:

- `data/fungi/`
- `data/substrates/`
- `data/enzymes/`
- `data/environments/`
- `data/geometries/`
- `data/parameters/`
- `data/experiments/`

Current behavior:

- YAML configs load into `Environment`, `Enzyme`, `Fungus`, `Substrate`,
  `Geometry`, and `ParameterSet` objects.
- Configs require top-level provenance and parameter-level source,
  measurement-method, confidence, notes, validity-range, units, and value
  fields.
- Unknown values remain explicit `value: null` inputs and become unknown
  `Parameter` objects instead of guessed numbers.

## Long-Term Roadmap Status

### Milestone 1: Process base classes

Status: `complete` for the skeleton scope.

Done:

- Process contracts.
- Process registry.
- Model builder skeleton.
- Structured assembly report.
- Structured assembly errors.
- Missing process and missing parameter tests.

Remaining future expansion:

- Entity-aware compatibility matching.
- Process-to-solver execution.
- Automatic validator selection.

### Milestone 2: Generic result object

Status: `complete` for the first standardized result/export scope.

Implemented:

- `src/fungal_model/results/result.py`
- `src/fungal_model/results/__init__.py`
- standardized `results.SimulationResult`
- ODE and reaction-diffusion wrapper constructors
- report/table/log/figure export
- result-generated plots
- tests in `tests/test_results.py`

Still required:

- make the roadmap result object the native output of all solvers rather than
  a wrapper around current solver results;
- add specialized plots for carbon, oxygen, spatial profiles, uncertainty
  bands, and calibration diagnostics.

### Milestone 3: Generic homogeneous kinetics

Status: `complete` for the first generic homogeneous process scope.

Implemented:

- `HomogeneousMichaelisMentenProcess`
- `MassActionProcess`
- `FirstOrderDecayProcess`
- `as_reaction()` adapters for current ODE engine execution
- examples 01 and 02 migrated to generic process classes
- tests in `tests/test_homogeneous_processes.py`

Still required:

- native process solver execution through `AssembledModel.run()`;
- richer process-rate recording from homogeneous processes.

### Milestone 4: Generic surface process refactor

Status: `complete` for the first generic surface-process scope.

Implemented:

- generic adsorption model in process form;
- generic surface catalysis/bond cleavage process;
- accessible site/surface model;
- product release map;
- PET accessibility adapter;
- PET migration to generic process composition;
- dummy non-PET substrate surface test.

Still required:

- dynamic adsorption/desorption states;
- resolved PET product maps beyond the current mass-equivalent benchmark;
- dynamic morphology/accessibility evolution;
- full entity compatibility matching for enzyme class, target bond, substrate,
  environment, and geometry.

### Milestone 5: Environment object and modifiers

Status: `complete` for the first environment/modifier scope.

Implemented:

- `Environment` entity.
- Temperature, pH, water activity, oxygen, and product inhibition modifiers.
- Tests in `tests/test_environment_modifiers.py`.

Still required:

- richer modifier plots and automatic modifier selection during assembly.

### Milestone 6: Geometry abstraction

Status: `complete` for the first geometry abstraction scope.

Implemented:

- roadmap `Geometry` hierarchy;
- functional well-mixed and 1D film geometry wrappers;
- particle, slab, and porous-medium metadata placeholders;
- tests in `tests/test_geometry_abstractions.py`.

Still required:

- process-native diffusion assembly and richer geometry-specific solvers.

### Milestone 7: Fungus/enzyme/process compatibility

Status: `complete` for the first compatibility-matching scope.

Implemented:

- explicit enzyme entities;
- compatibility matching between fungus, enzyme, substrate bond, and surface
  catalysis processes;
- clear assembly failures for missing biological capability;
- tests in `tests/test_enzyme_compatibility.py`.

Still required:

- broader environment and geometry compatibility rules for every process type.

### Milestone 8: Notebooks

Status: `complete` for the first required notebook/smoke-test scope.

Implemented:

- `/notebooks`;
- required six notebooks;
- notebook structure and smoke tests in `tests/test_notebooks.py`.

Still required:

- richer executed notebook snapshots as workflows mature.

### Milestone 9: Data/config schemas

Status: `complete` for the first YAML schema/loader scope.

Implemented:

- YAML loaders;
- JSON export helper;
- schema validation;
- example configs with provenance;
- unknown-value handling in config files;
- tests in `tests/test_config_io.py`.

Still required:

- full versioned schemas and broader literature-backed config libraries.

### Milestone 10: First full integration workflow

Status: `complete` for the first config-driven PET surface integration scope.

Implemented:

- `src/fungal_model/workflows/pet_surface_integration.py`;
- one fungus/enzyme/PET/environment/geometry workflow assembled through the
  registry and model builder;
- standardized output folder with reports, tables, logs, figures, input
  configs, and entity JSON snapshots;
- validation and process-rate plots;
- honest failure when accessible PET surface area is missing;
- honest failure when enzyme/substrate metadata are incompatible;
- tests in `tests/test_full_integration_workflow.py`.

Still required:

- native execution through `AssembledModel.run()`;
- resolved PET product chemistry;
- broader living-fungus dynamics assembled from configs.

## Anti-Cheating Checklist Status

Implemented in current tests:

- missing process fails with `MissingProcessError`;
- missing parameter fails with `MissingParameterError`;
- missing provenance fails in scientific assembly mode;
- incompatible units fail with `IncompatibleUnitsError`;
- generic process modules do not import PET-specific modules;
- generic surface hydrolysis works with PET and a dummy non-PET substrate;
- PET composes generic surface processes through a PET accessibility adapter;
- incompatible fungus/substrate/enzyme pairings fail in model assembly;
- non-assimilable product cannot cause biomass growth;
- roadmap result object saves standardized files, plots, logs, and reports;
- notebooks import from `fungal_model` and do not define core rate laws/classes;
- zero enzyme, zero accessible surface, zero substrate, and zero PET mass checks
  exist for current PET rate-law tests;
- high diffusion approaches well-mixed behavior in existing spatial tests.

Still required:

- oxygen cannot be consumed if oxygen process is absent or unavailable;
- native process-solver execution through `AssembledModel.run()`;
- resolved product stoichiometry for PET surface hydrolysis.

## How To Verify

Focused Milestone 1 tests:

```bash
.venv/bin/python -m pytest tests/test_process_assembly.py
```

Full test suite:

```bash
.venv/bin/python -m pytest
```

Current focused verification:

- 2026-05-26: `tests/test_process_assembly.py` passed with 8 tests.

Current full-suite verification:

- 2026-05-26: full test suite passed with 141 tests after Milestones 5-7.
- 2026-05-26: full test suite passed with 153 tests after Milestones 8-10.

Completed milestone: **Milestone 8: Notebooks**.

Milestone 8 status: `complete` for the first required notebook/smoke-test scope.

Completed in Milestone 8:

- Added top-level `/notebooks`.
- Added required notebooks:
  - `notebooks/00_quickstart.ipynb`
  - `notebooks/01_process_library_demo.ipynb`
  - `notebooks/02_surface_hydrolysis_demo.ipynb`
  - `notebooks/03_fungus_on_pet_demo.ipynb`
  - `notebooks/04_reaction_diffusion_demo.ipynb`
  - `notebooks/05_calibration_and_uncertainty_demo.ipynb`
- The quickstart notebook creates entities, assembles a generic PET surface
  process, runs through the current ODE engine, validates, plots, and saves
  standardized outputs.
- Added `tests/test_notebooks.py`.

Milestone 8 verification:

- `./.venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.

Completed milestone: **Milestone 9: Data/config schemas**.

Milestone 9 status: `complete` for the first YAML schema/loader scope.

Completed in Milestone 9:

- Added top-level data folders:
  - `data/fungi/`
  - `data/substrates/`
  - `data/enzymes/`
  - `data/environments/`
  - `data/geometries/`
  - `data/parameters/`
  - `data/experiments/`
- Added example configs:
  - `data/substrates/pet_film.yml`
  - `data/substrates/cellulose_powder.yml`
  - `data/fungi/toy_pet_fungus.yml`
  - `data/fungi/pleurotus_ostreatus.yml`
  - `data/enzymes/petase_like.yml`
  - `data/environments/lab_30C_pH7.yml`
  - `data/geometries/well_mixed_100ml.yml`
  - `data/geometries/pet_film_1d.yml`
  - `data/parameters/pet_surface_benchmark.yml`
  - `data/experiments/synthetic_pet_surface.yml`
- Added `src/fungal_model/io/`.
- Added schema validation in `src/fungal_model/io/schema.py`.
- Added YAML loaders in `src/fungal_model/io/yaml_loader.py`.
- Added JSON export helper in `src/fungal_model/io/json_export.py`.
- Exposed loaders from top-level `fungal_model`.
- Added `tests/test_config_io.py`.

Milestone 9 behavior now available:

- YAML configs must include top-level provenance fields.
- Parameter entries must include source, measurement method, confidence level,
  notes, validity range, units, and value.
- Unknown values remain `value: null` and load as explicit unknown parameters.
- Example configs can load into `Environment`, `Enzyme`, `PETSubstrate`,
  `Fungus`, `WellMixedGeometry`, `Film1DGeometry`, and `ParameterSet`.

Milestone 9 verification:

- `./.venv/bin/python -m pytest tests/test_config_io.py`
- Result: 6 passed.

Most recently completed milestone: **Milestone 10: First full integration workflow**.

Milestone 10 status: `complete` for the first config-driven PET surface
integration scope.

Completed in Milestone 10:

- Added `src/fungal_model/workflows/pet_surface_integration.py`.
- Added `src/fungal_model/workflows/__init__.py`.
- Exposed `PETSurfaceWorkflowConfig` and `run_pet_surface_integration` from
  top-level `fungal_model`.
- The workflow loads the example configs for:
  - PET film substrate;
  - PETase-like enzyme;
  - toy PET-capable fungus;
  - lab temperature/pH environment;
  - well-mixed geometry;
  - PET surface benchmark parameters.
- The workflow assembles generic surface catalysis through `ModelBuilder` and
  `ProcessRegistry`.
- The workflow runs the assembled process through the current ODE adapter,
  validates non-negativity and mass balance, records process-rate trajectories,
  and wraps the run in standardized `results.SimulationResult`.
- The workflow saves the full standardized output folder plus:
  - `input_configs.json`
  - `substrate.json`
  - `enzyme.json`
  - `fungus.json`
  - `environment.json`
  - `geometry.json`
- Added `tests/test_full_integration_workflow.py`.

Milestone 10 behavior now available:

- A complete config-driven PET surface run can be launched from
  `run_pet_surface_integration(output_dir)`.
- Missing accessible PET surface area fails before simulation with
  `MissingParameterError` and a structured assembly report.
- Incompatible enzyme/substrate metadata fails before simulation with
  `InvalidMechanismError` and structured compatibility issues.
- The saved output folder contains reports, tables, figures, logs, provenance,
  input config references, and entity snapshots.

Milestone 10 verification:

- `./.venv/bin/python -m pytest tests/test_full_integration_workflow.py`
- Result: 3 passed.

## Foundation-First Reset: Milestone 7 Native AssembledModel.run

Date: 2026-05-27

Milestone 7 status: `complete` for the first native assembled-model execution
scope.

Completed in Milestone 7:

- Added `src/fungal_model/solvers/process_ode.py`.
- Added `RunRequest` and `ProcessODESolver`.
- Implemented `AssembledModel.run()` as a real public execution method.
- `AssembledModel.run()` now delegates to the process ODE solver and returns a
  standardized `SimulationResult`.
- The solver builds derivatives from registered process `rate()` and
  `contributions()` methods.
- Process-rate trajectories are recorded into `SimulationResult.process_rates`.
- Model-level and request-level validators are run against the result.
- Unsupported geometry and mismatched initial states fail before simulation
  with structural `ValueError` messages.
- Resolved architecture debt `FD-003`; the shortcut guardrail no longer
  allowlists public `NotImplementedError` in `AssembledModel.run()`.

Milestone 7 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_native_assembled_model_run.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_public_api.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 192 passed.

Next milestone:

- Milestone 8: wire the generic `run_configured_model` workflow into config
  loading, registries, process factories, `AssembledModel.run()`, result
  validation, and output-bundle saving.

## Foundation-First Reset: Milestone 8 Generic run_configured_model

Date: 2026-05-27

Milestone 8 status: `complete` for the first generic configured-model
execution scope.

Completed in Milestone 8:

- Implemented `run_configured_model` as the generic workflow orchestrator.
- Configured runs now load substrates, geometries, product maps, validators,
  fungi, enzymes, environments, and parameter sets from the config contract.
- Plugin-backed substrate loading remains explicit through caller-supplied
  registries; the generic workflow does not import plugin loaders.
- Added `merge_parameter_sets` with duplicate-identical acceptance and
  duplicate-conflict rejection.
- Configured process entries build through `ProcessLibrary` factories and then
  assemble through `ModelBuilder`.
- Configured execution calls `AssembledModel.run()` and returns
  `SimulationResult`.
- Output saving uses the standard `SimulationResult.save()` bundle and adds
  `input_model_config.json` plus `configured_model_run.json`.
- Added a toy generic surface catalyst config so the dummy non-plugin surface
  benchmark exercises entity compatibility without substrate-specific biology.
- Resolved architecture debt `FD-004`.

Milestone 8 behavior now available:

- `run_configured_model("data/model_configs/toy_homogeneous_ab.yml")` runs the
  homogeneous benchmark through the generic workflow.
- `run_configured_model("data/model_configs/toy_surface_dummy_non_pet.yml")`
  runs the dummy non-plugin surface benchmark through the same workflow.
- `run_configured_model("data/model_configs/toy_surface_pet_plugin.yml",
  substrate_registry=pet_substrate_loader_registry())` runs the explicit plugin
  benchmark through the same workflow.
- Running the plugin config without the explicit registry fails structurally at
  input loading instead of creating a generic substrate-specific branch.

Milestone 8 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_model_config_loading.py tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 198 passed.
- `rg -n "SimulationEngine|ReactionDiffusionEngine|solve_ivp" src/fungal_model/workflows src/fungal_model/plugins/pet`
- Result: no matches.
- Generic PET-hardcoding scan over core/process/results/modifiers/io/workflows
  source paths.
- Result: no matches.

Next milestone:

- Milestone 9: remove or relocate the deprecated direct PET workflow path so
  workflows no longer call lower-level solvers directly.

## Foundation-First Reset: Milestone 9 Workflow Solver Isolation

Date: 2026-05-28

Milestone 9 status: `complete` for workflow-level solver isolation.

Completed in Milestone 9:

- Removed `src/fungal_model/workflows/pet_surface_integration.py`.
- Removed `PETSurfaceWorkflowConfig` and `run_pet_surface_integration` from
  `fungal_model.workflows`.
- Added `src/fungal_model/plugins/pet/workflows.py` as the plugin-local
  compatibility helper.
- The PET plugin helper materializes a generic model config and delegates to
  `run_configured_model` with `pet_substrate_loader_registry()`.
- The plugin helper no longer constructs processes, reactions, or low-level
  solvers directly.
- Tightened `tests/test_guardrails_no_hardcoding.py` by removing the legacy
  PET allowlist for generic workflow paths.
- Resolved architecture debt `FD-001`.

Milestone 9 behavior now available:

- `fungal_model.workflows` exports only generic configured-model workflow
  names.
- PET-specific convenience execution lives under `fungal_model.plugins.pet`.
- Generic workflow source paths no longer contain PET-specific workflow names,
  hardcoded PET states, or direct low-level solver imports.

Milestone 9 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_full_integration_workflow.py tests/test_configured_model_workflow.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_public_api.py tests/test_guardrails_no_shortcuts.py`
- Result: 16 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 198 passed.

Next milestone:

- Milestone 10: harden the result/output foundation for configured runs,
  including complete output metadata and snapshots for generic configs.

## Foundation-First Reset: Milestone 10 Result/Output Foundation

Date: 2026-05-28

Milestone 10 status: `complete` for configured-run output bundles.

Completed in Milestone 10:

- Hardened configured-run output saving around `SimulationResult.save()`.
- Added `configured_metadata.json` with config name, mode, maturity, result
  label, model version, state count, process-rate count, and validation
  summary.
- Expanded `configured_model_run.json` with state names, process-rate names,
  validation summary, and solver metadata.
- Added `process_build_decisions.json` so factory decisions are inspectable.
- Added `initial_state.json`, `time_grid.json`, `validators.json`, and
  `merged_parameters.json`.
- Added `entity_snapshots/` with snapshots for configured fungi, substrates,
  enzymes, environments, geometries, and product maps.
- Added `output_manifest.json` listing the complete saved bundle.
- Updated configured workflow tests so homogeneous, plugin, and non-plugin
  foundation configs all prove the complete output bundle exists.

Milestone 10 behavior now available:

- Every configured foundation benchmark saves a complete output folder.
- Mode and maturity are visible without opening the source config.
- Users can inspect config, entity, parameter, process-build, validation, solver,
  trajectory, plot, and provenance artifacts from the output directory.

Milestone 10 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_full_integration_workflow.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 17 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 199 passed.
- Notebook JSON validation for all four foundation notebooks.
- Result: passed.
- Notebook direct-solver/core-implementation scan.
- Result: no matches.

Next milestone:

- Milestone 11: notebook foundation for generic quickstart, config/entity
  inspection, failure reports, and configured output inspection.

## Foundation-First Reset: Milestone 11 Notebook Foundation

Date: 2026-05-28

Milestone 11 status: `complete` for foundation notebook smoke coverage.

Completed in Milestone 11:

- Replaced the old roadmap notebooks with foundation-first notebooks under
  `notebooks/examples/`.
- Added a generic quickstart notebook that runs
  `data/model_configs/toy_homogeneous_ab.yml` through `run_configured_model`.
- Added a config/entity inspection notebook for the dummy non-plugin surface
  benchmark.
- Added a structured failure-report notebook that captures the expected plugin
  registry failure as a `ConfiguredModelRunReport`.
- Added a configured-output inspection notebook that reads the manifest,
  metadata, build decisions, validators, and result state names.
- Tightened notebook tests so required notebooks import package code, call the
  generic configured workflow, avoid core class/rate-law/solver definitions,
  and execute every foundation notebook smoke path.

Milestone 11 behavior now available:

- Notebooks demonstrate the generic workflow instead of constructing low-level
  solvers.
- Failure handling and output inspection are documented as runnable examples.
- Notebook smoke tests create quickstart, failure-report, and output-inspection
  artifacts under `outputs/`.

Milestone 11 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 199 passed.

Next milestone:

- Milestone 12: package quality and CI discipline, including initial linting,
  type-checking, coverage, and README/CI alignment.

## Foundation-First Reset: Milestone 12 Package Quality And CI

Date: 2026-05-28

Milestone 12 status: `complete` for the first executable package-quality
baseline.

Completed in Milestone 12:

- Added `ruff`, `pyright`, and `pytest-cov` to the `dev` extra.
- Added Ruff configuration for correctness-oriented linting over `src` and
  `tests`.
- Added `pyrightconfig.json` as an explicit initial type-checking baseline.
- Added coverage configuration with branch coverage and a starting
  `fail_under = 60` gate.
- Updated GitHub Actions CI to run lint, type check, and coverage-backed tests.
- Added `.github/BRANCH_PROTECTION.md` documenting the default-branch
  protection expectation for the CI workflow.
- Added `tests/test_quality_config.py` to protect declared dev dependencies,
  quality-tool configuration, and CI commands.
- Updated the PR template to require Ruff, Pyright, coverage, and pytest status.
- Cleaned up unused imports surfaced by Ruff without broad style churn.
- Updated `.gitignore` for local coverage artifacts.

Milestone 12 type-checking note:

- The Pyright gate is intentionally permissive around Pint quantity typing and
  optional-state inference. It is active and passing, but the stricter quantity
  typing cleanup remains a future package-quality milestone and is documented
  as `FD-005` in `ARCHITECTURE_DEBT.md`.

Milestone 12 verification:

- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 203 passed, total coverage 84.92%, required coverage 60% reached.

Next milestone:

- Milestone 13: tighten foundation review/readiness, including explicit
  remaining architecture debt and the next realistic type/coverage ratchet.

## Foundation-First Reset: Milestone 13 Foundation Review

Date: 2026-05-28

Milestone 13 status: `complete` for the foundation review/readiness gate.

Completed in Milestone 13:

- Added `FOUNDATION_READINESS.md` with the current foundation gate result,
  active architecture debt, deferred biology scope, and review commands.
- Added `tests/test_guardrails_config_generality.py` to prove the homogeneous,
  explicit PET plugin, and dummy non-PET surface configs all run through
  `run_configured_model`.
- Added `tests/test_guardrails_config_generality.py` coverage for arbitrary
  state names and explicit plugin registry failure.
- Added `tests/test_guardrails_native_execution.py` to prove the configured
  workflow calls `AssembledModel.run()` and high-level workflows do not import
  low-level solver backends.
- Replaced the stale README example-script section with the current
  configured-model benchmark workflow.
- Raised the coverage gate from 60% to 80%.
- Updated branch-protection and quality-config docs/tests for the new coverage
  floor.
- Clarified that `FD-005` remains active and should be removed in a dedicated
  quantity-typing package-quality ratchet.

Milestone 13 behavior now available:

- The required foundation benchmark trio is protected by explicit guardrail
  tests.
- Output bundles are inspected as part of the generic-config guardrail.
- The package now has a more serious coverage gate while preserving the
  documented Pyright quantity-typing baseline.

Milestone 13 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 6 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py`
- Result: 19 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 209 passed, total coverage 84.92%, required coverage 80% reached.

Next milestone:

- Quantity-typing package-quality ratchet: reduce `FD-005` by tightening
  Pyright diagnostics around Pint quantity aliases and optional-state handling.

## Foundation-First Reset: Milestone 14 Pyright Quantity-Typing Ratchet

Date: 2026-05-28

Milestone 14 status: `complete` for the first Pyright quantity/type diagnostic
ratchet.

Completed in Milestone 14:

- Made `fungal_model.core.units.Quantity` a static `TypeAlias` while preserving
  the runtime Pint class export.
- Marked the runtime `Q_` constructor alias as `Any` so Pyright does not treat
  it as a type alias.
- Re-enabled these Pyright diagnostics:
  - `reportInvalidTypeForm`;
  - `reportReturnType`;
  - `reportAssignmentType`;
  - `reportArgumentType`;
  - `reportAttributeAccessIssue`;
  - `reportCallIssue`;
  - `reportOperatorIssue`;
  - `reportOptionalOperand`;
  - `reportGeneralTypeIssues`.
- Tightened process factory protocol typing and product-map defaults.
- Added explicit casts/guards for quantity arithmetic, mass-balance totals,
  local sensitivity perturbations, spatial grid cell width, registry literal
  loading, and result assembly-report summaries.
- Reworked product inhibition activity calculation to avoid ambiguous
  dimensionless quantity operators.
- Updated `ARCHITECTURE_DEBT.md` so `FD-005` now tracks only the remaining
  optional-member-access cleanup.

Milestone 14 verification:

- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_units.py tests/test_process_factory_library.py tests/test_results.py tests/test_configured_model_workflow.py tests/test_registry_based_loading.py tests/test_uncertainty_sensitivity.py tests/test_reaction_diffusion.py tests/test_environment_modifiers.py tests/test_calibration.py`
- Result: 55 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 209 passed, total coverage 84.83%, required coverage 80% reached.

Next milestone:

- Optional-member-access package-quality ratchet: re-enable
  `reportOptionalMemberAccess` by narrowing optional quantities in calibration,
  transport, uncertainty, pH kinetics, and plugin substrate modules.

## Foundation 10/10 Push: F10.2 Centralized Mode/Maturity Enforcement

Date: 2026-05-28

F10.2 status: `complete` for centralized toy/scientific/strict run-mode
preflight enforcement.

Completed in F10.2:

- Added `fungal_model.validation.maturity` as the central maturity-policy
  module for configured runs.
- Added structured `MaturityIssue` records and `InvalidDataMaturityError`
  failures with object type, object id, field, requested mode, reason, and fix.
- Wired `run_configured_model` to enforce the maturity policy after generic
  config/entity/parameter/product-map loading and before process factories,
  model assembly, or solving.
- Preserved toy benchmark execution while preventing framework benchmark
  parameters, toy-only provenance, unknown required parameter values, missing
  required parameter metadata, and toy/framework product maps from running in
  scientific or strict modes.
- Made strict mode reject missing uncertainty metadata for required
  parameters, which scientific mode still allows.
- Added `validity_range` to parameter parsing/serialization so required
  parameter validity metadata can be enforced centrally.
- Moved example notebook outputs from root-level `outputs/` paths to
  `notebooks/examples/Outputs/<notebook-name>/`, with notebook smoke tests
  updated to protect that layout.

Architecture debt:

- No new architecture debt was added for F10.2.

F10.2 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_maturity_policy.py`
- Result: 10 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py`
- Result: 5 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py`
- Result: 2 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_shortcuts.py`
- Result: 2 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 3 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 219 passed.

Next milestone:

- F10.1: decompose the generic configured workflow into separately testable
  input loading, process assembly, orchestration, and output writing
  responsibilities.

## Foundation 10/10 Push: F10.1 Configured Workflow Decomposition

Date: 2026-05-28

F10.1 status: `complete` for decomposing the generic configured workflow into
separately testable responsibilities.

Completed in F10.1:

- Kept `run_configured_model(config_path, output_dir=None, ...)` as the stable
  public entry point.
- Added `ConfiguredModelRunner` for orchestration of config loading, maturity
  preflight, process assembly, model execution, and output writing.
- Added `ConfiguredInputLoader` and `ConfiguredInputs` for resolving entity
  registries, product maps, merged parameter sets, validators, initial state,
  and time grids.
- Added `ConfiguredProcessAssembler` and `ConfiguredProcessAssembly` for
  process-factory decisions, process construction, and `ModelBuilder`
  assembly.
- Added `ConfiguredOutputWriter` for configured output bundle persistence.
- Moved configured workflow error/report helpers into a shared internal module
  so loader, assembler, and runner can all raise the same structured
  execution error without import cycles.
- Exported the new workflow components from `fungal_model.workflows` and the
  top-level package.

Architecture debt:

- No new architecture debt was added for F10.1.

F10.1 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_workflow_components.py`
- Result: 8 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py`
- Result: 5 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_model_config_loading.py`
- Result: 8 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 15 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_maturity_policy.py tests/test_notebooks.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 227 passed.

Next milestone:

- F10.3: strengthen generic workflow failure-path tests with structured
  exception-stage assertions and no false-success output.

## Foundation 10/10 Push: F10.3 Generic Workflow Failure-Path Tests

Date: 2026-05-28

F10.3 status: `complete` for structured generic workflow failure-path coverage.

Completed in F10.3:

- Added `tests/test_configured_workflow_failures.py` with all required generic
  workflow failure-path cases.
- Wrapped model-config loading failures at the public configured workflow
  boundary with `ConfiguredModelExecutionError` stage `model_config_loading`.
- Wrapped process-factory lookup failures, model-assembly failures, and
  model-execution failures with structured configured-run reports.
- Added strict-mode result-validation enforcement: strict configured runs now
  raise before output writing if any configured validator fails.
- Kept non-strict failed validation behavior record-oriented: failed
  validators are saved in result metadata and output bundles instead of being
  hidden or treated as success.
- Updated PET plugin integration tests to assert the generic configured
  workflow error boundary while preserving plugin delegation to
  `run_configured_model`.

F10.3 failure cases now covered:

- missing config file;
- invalid top-level config kind;
- missing configured processes;
- missing configured initial state;
- unknown substrate loader;
- plugin config without explicit plugin registry;
- unknown product-map loader;
- unknown validator type;
- unknown process type;
- missing product map;
- missing state unit;
- missing required parameter;
- conflicting duplicate parameters;
- incompatible initial-state units;
- unsupported geometry;
- failed validation recorded in non-strict mode;
- failed validation raises in strict mode.

Architecture debt:

- No new architecture debt was added for F10.3.

F10.3 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_workflow_failures.py`
- Result: 17 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_full_integration_workflow.py tests/test_configured_workflow_failures.py`
- Result: 20 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_workflow_components.py tests/test_configured_model_workflow.py tests/test_model_config_loading.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 36 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_maturity_policy.py tests/test_notebooks.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 244 passed.

Next milestone:

- F10.4: make configured output bundles reproducibility-grade by adding run
  environment, package version, source revision, and solver settings metadata.

## Foundation 10/10 Push: F10.4 Reproducibility-Grade Output Bundles

Date: 2026-05-28

F10.4 status: `complete` for configured-run output bundle reproducibility
metadata.

Completed in F10.4:

- Added `run_environment.json` to each configured output bundle with UTC run
  timestamp, Python runtime details, platform details, executable path, and
  working directory.
- Added `package_versions.json` with the FungMod model version and installed
  package versions for core runtime dependencies.
- Added `source_revision.json` with truthful Git metadata when available:
  repository root, commit, branch, dirty state, and an error field when Git
  metadata cannot be resolved.
- Added `solver_settings.json` with both configured solver settings and solver
  backend metadata.
- Ensured the output manifest includes the new files and still includes
  itself.
- Added reproducibility tests that assert every manifest-listed file exists,
  mode/maturity are recorded, solver metadata is present, package version
  metadata is present, and process-build decisions are included.

Architecture debt:

- No new architecture debt was added for F10.4.

F10.4 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_output_bundle_reproducibility.py tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py`
- Result: 31 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py`
- Result: 15 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py tests/test_full_integration_workflow.py`
- Result: 6 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 245 passed.

Next milestone:

- F10.5: make the public API intentionally stable and documented, while
  keeping PET-specific helpers contained in `fungal_model.plugins.pet`.

## Foundation 10/10 Push: F10.5 Stable Foundation Public API

Date: 2026-05-28

F10.5 status: `complete` for a documented, generic-first foundation public API.

Completed in F10.5:

- Added a `Foundation Public API` section to `README.md` documenting the stable
  top-level foundation names for configured execution, loaders, model assembly,
  solvers, results, and parameter containers.
- Strengthened `tests/test_guardrails_public_api.py` so the required
  foundation API names must be exported from `fungal_model.__all__` and must
  resolve to the expected objects.
- Added explicit plugin containment checks proving PET helper names are absent
  from top-level `fungal_model` and `fungal_model.workflows`.
- Added explicit plugin availability checks proving PET helper names remain
  available only from `fungal_model.plugins.pet`.
- Expanded public API cleanliness checks across the documented foundation
  primitives so they contain no `TODO`, `placeholder`, or public
  `NotImplementedError` markers.
- Added README documentation coverage checks for every required foundation API
  name and for the PET plugin containment path.

Architecture debt:

- No new architecture debt was added for F10.5.

F10.5 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_public_api.py`
- Result: 7 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_quality_config.py`
- Result: 14 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py tests/test_configured_output_bundle_reproducibility.py tests/test_full_integration_workflow.py tests/test_notebooks.py`
- Result: 37 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 247 passed.

Next milestone:

- F10.6: harden notebook smoke tests so foundation notebooks demonstrate only
  public APIs and do not hide implementation in notebook cells.

## Foundation 10/10 Push: F10.6 Notebook Public-API Smoke Tests

Date: 2026-05-28

F10.6 status: `complete` for notebook public-API and smoke-test guardrails.

Completed in F10.6:

- Added a `FUNGMOD_NOTEBOOK_OUTPUT_ROOT` output-root override to every
  foundation example notebook while preserving the default
  `notebooks/examples/Outputs/<notebook-name>/` location for normal use.
- Updated notebook smoke tests to redirect outputs to `tmp_path` so test runs
  do not write generated files into the repository.
- Strengthened notebook import checks so every foundation notebook must import
  or use public `fungal_model` APIs and call `run_configured_model`.
- Strengthened hidden-implementation guardrails so notebooks cannot define
  process classes, solver classes, process factories, rate-law functions,
  solver functions, direct SciPy solver calls, core simulation-engine imports,
  solver imports, process-internal imports, or legacy rate-law classes.
- Added an explicit quickstart smoke test that executes
  `00_quickstart.ipynb` with temporary outputs and verifies the expected
  result bundle files.
- Kept the full foundation notebook smoke path so the complete example set
  still executes through package APIs.

Architecture debt:

- No new architecture debt was added for F10.6.

F10.6 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_notebooks.py`
- Result: 4 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_public_api.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_quality_config.py`
- Result: 21 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py tests/test_configured_output_bundle_reproducibility.py tests/test_full_integration_workflow.py`
- Result: 34 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 248 passed.

Next milestone:

- F10.7: harden CI and branch-protection documentation around lint, type,
  coverage, and merge requirements.

## Foundation 10/10 Push: F10.7 CI And Branch Protection Gate

Date: 2026-05-28

F10.7 status: `complete` for documented CI and merge-quality policy.

Completed in F10.7:

- Confirmed `.github/workflows/ci.yml` runs the required package-quality gates:
  Ruff, Pyright, and pytest with coverage XML output.
- Strengthened `.github/BRANCH_PROTECTION.md` so default-branch policy requires
  pull requests, the `CI / tests` status check, up-to-date branches, no force
  pushes, and no unaudited direct bypass.
- Updated `README.md` to state that CI is required before merging and to
  summarize the protected-branch requirements.
- Expanded `tests/test_quality_config.py` so the CI commands, coverage gate,
  branch-protection policy, and README merge policy stay mechanically checked.

Architecture debt:

- No new architecture debt was added for F10.7.
- `FD-005` remains active as a documented package-quality typing ratchet, not
  foundation-blocking architecture debt.

F10.7 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_quality_config.py tests/test_foundation_complete_gate.py`
- Result: 8 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 252 passed; coverage 85.35%, above the 80% gate.

Next milestone:

- F10.8: add and test the formal foundation-complete gate before biology may
  begin.

## Foundation 10/10 Push: F10.8 Foundation Complete Gate

Date: 2026-05-28

F10.8 status: `complete` for the formal foundation-complete gate.

Completed in F10.8:

- Added `FOUNDATION_COMPLETE.md` with `Status: complete` for the software
  foundation only.
- Recorded the completion criteria required before biology may begin:
  guardrails, configured workflows, failure paths, maturity modes,
  reproducibility outputs, CI, coverage, plugin containment, notebook public
  API usage, README limitations, and all three foundation configured runs.
- Explicitly stated that the completion gate does not approve real fungal
  biology, PETase mechanisms, literature parameters, metabolism, growth
  physiology, or substrate-specific scientific mechanisms.
- Documented active non-blocking architecture debt `FD-005` as a typing
  ratchet only, not foundation-blocking architecture debt.
- Added `tests/test_foundation_complete_gate.py` so a complete foundation gate
  requires all evidence and cannot coexist with undocumented active
  architecture debt.

Architecture debt:

- No new architecture debt was added for F10.8.

F10.8 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_guardrails_public_api.py tests/test_guardrails_config_generality.py tests/test_guardrails_native_execution.py tests/test_configured_model_workflow.py tests/test_configured_workflow_components.py tests/test_configured_workflow_failures.py tests/test_maturity_policy.py tests/test_configured_output_bundle_reproducibility.py tests/test_notebooks.py tests/test_quality_config.py tests/test_foundation_complete_gate.py`
- Result: 70 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml`
- Result: 252 passed; coverage 85.35%, above the 80% gate.

Next milestone:

- Foundation F10.1-F10.8 is complete. The next work should start the
  post-foundation biology-readiness path from
  `foundation_progress/FUNG_MOD_FOUNDATION_8_TO_10_MILESTONES.md`: literature
  dataset schema, provenance templates, experiment dataset object, and
  calibration workflow on synthetic data before any real biology is added.

## Data Infrastructure: D1 ExperimentDataset Loader

Date: 2026-05-29

D1 status: `complete` for the first strict experiment-dataset schema and
loader.

Completed in D1:

- Added the `fungal_model.data` package with explicit dataset objects:
  `ExperimentDataset`, `DataSource`, `ExperimentalSystem`,
  `ExperimentalConditions`, `MeasurementSeries`, `MeasurementPoint`, and
  `PreprocessingRecord`.
- Added `load_experiment_dataset` for YAML-backed datasets with CSV
  measurement loading, relative CSV resolution, explicit maturity validation,
  required source metadata, required time/value units, uncertainty-unit checks,
  expected-column validation, and optional missing-uncertainty handling only
  when configured.
- Added a synthetic first-order A to B dataset fixture under
  `data/experiments/synthetic/first_order_ab/` with YAML metadata,
  observation CSV, and a generation record.
- Added experiment dataset documentation for maturity labels, toy versus
  synthetic data, provenance, unit requirements, uncertainty behavior, and the
  current no-literature-data boundary.
- Added loader tests covering valid synthetic loading, maturity preservation,
  measurement units and uncertainty, missing kind, invalid maturity, missing
  source, missing CSV files, missing value columns, missing uncertainty
  columns, explicitly allowed missing uncertainty, JSON-safe `to_dict()`, and
  `validate()` success.

Architecture debt:

- No new architecture debt was added for D1.

D1 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py`
- Result: 11 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_maturity_policy.py`
- Result: 12 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 263 passed.

Next milestone:

- D2 should add the explicit observable mapping and model-dataset comparison
  layer before any calibration or real literature data work begins.

## Data Infrastructure: D2 Observable Mapping And Comparison

Date: 2026-05-29

D2 status: `complete` for explicit model-dataset comparison on synthetic data.

Completed in D2:

- Added `src/fungal_model/data/comparison.py` with `ObservableMapping`,
  `ResidualPoint`, `ResidualSeries`, `ModelDatasetComparison`, and
  `evaluate_model_against_dataset`.
- Required explicit dataset-measurement to model-observable mappings; no fuzzy
  matching or automatic biological interpretation is used.
- Implemented state, process-rate, and derived-observable lookup against
  `SimulationResult`.
- Implemented unit-aware identity and unit-conversion comparisons, plus a
  guarded fractional-conversion path that requires an explicit initial value
  and units.
- Implemented linear interpolation to dataset times and structural rejection
  of extrapolation beyond the model time range.
- Implemented raw residuals, standardized residuals when uncertainty exists,
  RMSE, mean absolute residual, chi-square, and reduced chi-square metrics.
- Implemented comparison output bundles with comparison record, dataset
  snapshot, observable mapping, residuals CSV, metrics, validation report, and
  observed-vs-predicted and residual figures.
- Updated the synthetic first-order fixture so it aligns with the existing
  `toy_homogeneous_ab.yml` benchmark time window and rate constant.
- Exposed comparison names from `fungal_model.data` without adding unstable
  data APIs to top-level `fungal_model`.
- Updated data documentation to describe explicit observable mappings and the
  comparison output bundle.

Architecture debt:

- No new architecture debt was added for D2.

D2 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_model_dataset_comparison.py`
- Result: 23 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py`
- Result: 14 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_model_dataset_comparison.py`
- Result: 12 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 275 passed.

Next milestone:

- D3 should add synthetic dataset generation from `SimulationResult`, including
  Gaussian noise options, generation records, reproducibility tests, and
  reloadability checks. No calibration or real literature data yet.

## Data Infrastructure: D3 Synthetic Dataset Generation

Date: 2026-05-29

D3 status: `complete` for synthetic dataset generation from existing
`SimulationResult` objects.

Completed in D3:

- Added `src/fungal_model/data/synthetic.py` with `GaussianNoise`,
  `SyntheticDatasetGenerationError`, and
  `generate_synthetic_dataset_from_result`.
- Implemented generation from explicit `ObservableMapping` entries or a simple
  measurement-to-state mapping, using existing `SimulationResult` states,
  process rates, or derived quantities.
- Wrote reloadable dataset bundles containing:
  - dataset YAML;
  - observations CSV;
  - `generation_record.json`.
- Recorded seed, noise model, source result metadata, optional source config,
  observable mappings, output file names, and true values in the generation
  record.
- Enforced unit compatibility for Gaussian noise and generated measurement
  units.
- Added fixed-seed reproducibility tests, changed-seed tests, reloadability
  tests, comparison-back-to-source tests, generation-record metadata tests,
  incompatible-noise-unit tests, and missing-model-observable tests.
- Updated synthetic-data documentation to describe generation from
  `SimulationResult` and the required generation record.

Architecture debt:

- No new architecture debt was added for D3.

D3 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_model_dataset_comparison.py tests/test_synthetic_dataset_generation.py`
- Result: 30 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py`
- Result: 14 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_synthetic_dataset_generation.py`
- Result: 7 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 282 passed.

Next milestone:

- D4 should add synthetic-only calibration that can recover a known first-order
  parameter from generated synthetic data. Do not add real literature data or
  biological mechanisms.

## Data Infrastructure: D4-D6 Synthetic Calibration And Literature Contract

Date: 2026-05-29

D4-D6 status: `complete` for synthetic-only calibration, train/validation
splits, literature schema guardrails, and the remaining data-validation rules.

Completed in D4-D6:

- Added `calibrate_configured_model` and `CalibrationResult` in
  `src/fungal_model/calibration/configured.py` for synthetic configured-model
  calibration.
- Kept calibration synthetic-only: non-synthetic datasets are rejected, source
  model configs are copied through temporary configured runs, and source config
  files are not mutated in place.
- Added a synthetic first-order calibration model config and calibration
  contract fixture under `data/model_configs/` and `data/calibration/`.
- Wrote inspectable calibration bundles with calibration records, source model
  snapshots, dataset snapshots, fitted parameter files, optimizer metadata,
  train/validation residual CSVs, metrics, assumptions, warnings, and figures.
- Added deterministic train/validation split support by time, with separate
  train and validation residuals/metrics and a clear warning when no
  validation split is supplied.
- Added dataset validation rules for known units, finite numeric values,
  nonnegative time, strictly increasing time per series, nonnegative
  uncertainty, duplicate measurement IDs, source/provenance, preprocessing
  status, and preprocessing notes.
- Added `data/experiments/literature/README.md` as the literature extraction
  metadata contract while keeping the literature directory free of real paper
  data.
- Added `data/experiments/validation/README.md`, `data/calibration/README.md`,
  and `data/README.md` to document maturity labels, synthetic-only calibration,
  and the current no-real-literature boundary.

Architecture debt:

- No new architecture debt was added for D4-D6.

D4-D6 verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_synthetic_calibration.py tests/test_calibration_config_contract.py tests/test_experiment_dataset_validation_rules.py tests/test_literature_schema_contract.py`
- Result: 18 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_experiment_dataset_validation_rules.py tests/test_model_dataset_comparison.py tests/test_synthetic_dataset_generation.py tests/test_configured_synthetic_calibration.py tests/test_calibration_config_contract.py tests/test_literature_schema_contract.py`
- Result: 48 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py tests/test_config_io.py`
- Result: 20 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 300 passed.

Data infrastructure roadmap status:

- D1-D6 and the roadmap definition-of-done items are complete for the
  synthetic/no-real-biology scope. Real literature extraction and real fungal
  biology remain explicitly out of scope until schema-compliant data curation
  work is requested and reviewed.

## Data Infrastructure Finalization: D4-D6 Hardening Before Real Data

Date: 2026-05-31

Status: `complete` for the final pre-real-data hardening pass.

Completed in this pass:

- Finalized configured synthetic calibration behavior:
  - fitted `k_ab` still recovers the synthetic first-order target near
    `0.1 1 / second`;
  - fitted parameter provenance now records synthetic-only calibration,
    dataset ID, least-squares fitting, and not-empirical-validation status;
  - source model configs are not mutated;
  - missing parameter symbols, missing initial guesses, bad bounds,
    non-synthetic datasets, and parameters absent from the configured model
    fail structurally.
- Hardened calibration path resolution:
  - calibration now resolves model-config references against the source config
    path and its ancestors before writing temporary configured runs;
  - synthetic calibration works when invoked from outside the repository root.
- Fixed D5 split semantics with explicit train/validation/holdout behavior:
  - `train_fraction` selects the first time-ordered block;
  - `validation_fraction` selects the next time-ordered block;
  - remaining points become holdout/unused data for future workflows;
  - train, validation, and holdout indices are disjoint and reported in
    `CalibrationSplit.to_dict()`;
  - validation metrics are reported only when validation indices exist.
- Upgraded D6 from README-only to machine-readable literature metadata schema:
  - added `validate_literature_dataset_metadata`;
  - added fake schema-only metadata under
    `data/experiments/literature_schema_examples/`;
  - preserved the rule that `data/experiments/literature/` contains no real
    paper-derived data files.
- Updated the literature README to state that future literature datasets must
  pass machine-readable schema validation and include provenance, units,
  extraction notes, preprocessing, uncertainty status, and source metadata.

Architecture/data debt:

- No architecture or data debt was added.
- No real literature data or real biological mechanisms were inserted.

Verification:

- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_configured_synthetic_calibration.py`
- Result: 15 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_literature_schema_contract.py`
- Result: 13 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_experiment_dataset_loading.py tests/test_model_dataset_comparison.py tests/test_synthetic_dataset_generation.py`
- Result: 30 passed.
- `/private/tmp/fungmod-venv/bin/python -m pytest tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py tests/test_maturity_policy.py tests/test_calibration_config_contract.py`
- Result: 16 passed.
- `/private/tmp/fungmod-venv/bin/python -m ruff check src tests`
- Result: passed.
- `/private/tmp/fungmod-venv/bin/python -m pyright --pythonpath /private/tmp/fungmod-venv/bin/python`
- Result: 0 errors.
- `/private/tmp/fungmod-venv/bin/python -m pytest`
- Result: 320 passed.

Next allowed step:

- Select one candidate real dataset for schema-first ingestion review. Do not
  implement broad biology or substrate-specific mechanisms as the next step.

## Registry And Ranges: R1 ValueSpec And Registry Loader

Date: 2026-06-01

R1 status: `complete` for the ValueSpec and registry-loader foundation.

Completed in R1:

- Added `ValueSpec` in `src/fungal_model/core/value_spec.py` to represent
  exact values, ranges, distributions, unknowns, and not-applicable values with
  explicit units, source, confidence, notes, validation, sampling, and exact
  quantity conversion.
- Supported initial `uniform` and `loguniform` distribution sampling with fixed
  RNG reproducibility.
- Added `src/fungal_model/registry/` with registry records, YAML loading, and
  an in-memory `FungModRegistry` store.
- Implemented minimal records for fungi, enzyme classes, substrates,
  environments, process compatibility, and parameters.
- Added registry lookup methods for fungi, enzyme classes, substrates,
  environments, process compatibility records, and parameter records.
- Added toy/development-only registry fixtures under `data_registry/`.
- Added registry documentation explaining that the registry is not a complete
  biological database and that all current records are toy/development
  fixtures only.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real literature capability records, real fungal datasets,
  range-based ensemble simulation, or new biological process equations were
  added.

Verification:

- `.venv/bin/python -m pytest tests/test_value_spec.py`
- Result: 10 passed.
- `.venv/bin/python -m pytest tests/test_registry_loading.py`
- Result: 11 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_guardrails_no_hardcoding.py`
- Result: 23 passed.
- `.venv/bin/python -m pytest tests/test_guardrails_no_shortcuts.py`
- Result: 2 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 341 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- R2 should implement a modelability report over the toy registry. Do not start
  range-based ensemble simulation or real registry data insertion yet.

## Registry And Ranges: R2 Modelability Report

Date: 2026-06-01

R2 status: `complete` for toy-registry modelability reporting.

Completed in R2:

- Added `src/fungal_model/screening/modelability.py` with:
  - `ReportItem`;
  - `ModelabilityReport`;
  - `assess_modelability`.
- Added `src/fungal_model/screening/__init__.py` as the public screening
  package boundary.
- Implemented registry-only case assessment for:
  - fungus record loading;
  - substrate record loading;
  - environment record loading;
  - fungus enzyme-class capability matching;
  - enzyme/substrate class and bond compatibility;
  - process compatibility discovery;
  - required parameter lookup;
  - exact, uncertain, unknown, and mode-incompatible parameter classification.
- Implemented the four R2 statuses over toy records:
  - `modelable`;
  - `exploratory`;
  - `underparameterized`;
  - `unsupported`.
- Added JSON-safe `ModelabilityReport.to_dict()` and a concise
  `ModelabilityReport.summary()`.
- Added tests that verify default toy underparameterization, exact-only
  modelability, range-based exploratory status, scientific-mode rejection of
  uncertain parameters, missing-parameter reporting, unsupported compatibility,
  JSON-safe report serialization, and invalid mode errors.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real registry records, case-builder workflow, model
  assembly, range-based ensemble simulation, or new process equations were
  added.

Verification:

- `.venv/bin/python -m pytest tests/test_modelability_report.py`
- Result: 8 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_modelability_report.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 33 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 349 passed.

Next milestone:

- R3 should implement a toy-registry case builder that converts a modelable
  registry case into a generic `ModelConfig` for `run_configured_model`. Do not
  start range-based ensemble simulation or real registry data insertion yet.

## Registry And Ranges: R3 Plug-And-Play Case Builder

Date: 2026-06-01

R3 status: `complete` for deterministic toy-registry case building.

Completed in R3:

- Added `src/fungal_model/screening/case_builder.py` with:
  - `build_model_config_from_registry_case`;
  - `RegistryCaseBuildError`;
  - an explicit toy-only config mode boundary for R3.
- The case builder now gates assembly through `assess_modelability` and refuses
  underparameterized, exploratory, unsupported, or non-toy cases.
- Added process-compatibility `parameter_roles` metadata so registry parameter
  symbols can be mapped into the existing generic process factory roles without
  hardcoding substrate-specific workflow logic.
- Converted modelable toy surface-catalysis registry cases into regular
  `ModelConfig` objects that run through `run_configured_model`.
- Kept the generated config self-contained with inline toy geometry, generic
  substrate metadata, toy product maps, explicit parameters, validators, time
  grid, and output settings.
- Added toy/development-only exact adsorption and accessible-surface parameter
  records for case-builder tests while preserving the default underparameterized
  R2 registry case.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real registry records, range-based ensemble simulation, or
  new process equations were added.

Verification:

- `.venv/bin/python -m pytest tests/test_registry_case_builder.py`
- Result: 6 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_modelability_report.py tests/test_registry_case_builder.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 39 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 355 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- R4 should implement exploratory ensemble simulation over `ValueSpec` ranges
  and distributions. Do not add real biology or real literature capability
  records as part of R4.

## Registry And Ranges: R4 Exploratory Ensemble Simulation

Date: 2026-06-01

R4 status: `complete` for toy-registry exploratory ensemble execution.

Completed in R4:

- Added `src/fungal_model/screening/ensemble.py` with:
  - `simulate_screen`;
  - `RegistryScreenResult`;
  - `RegistryCaseEnsemble`;
  - `EnsembleSample`;
  - `RegistryScreenSimulationError`.
- Implemented sampling over registry `ValueSpec` exact, range, and distribution
  values for exploratory toy screen runs.
- Added seeded reproducibility for sampled registry screens.
- Materialized each sampled run as a standard generic `ModelConfig`, then ran it
  through `run_configured_model`; no separate solver path was introduced.
- Wrote per-sample configs, configured output bundles, and
  `screen_summary.json`.
- Kept R4 limited to toy/exploratory registry cases and explicit
  surface-catalysis configs using existing generic process factories.
- Added clear rejection paths for underparameterized cases, unknown parameters,
  unsupported process types, missing parameter-role mappings, invalid sample
  counts, empty input lists, and non-exploratory screen modes.

Architecture/data debt:

- No architecture or data debt was added.
- No real biology, real literature capability records, real fungal datasets,
  JAX, or new biological process equations were added.

Verification:

- `.venv/bin/python -m pytest tests/test_registry_ensemble_simulation.py`
- Result: 6 passed.
- `.venv/bin/python -m pytest tests/test_value_spec.py tests/test_registry_loading.py tests/test_modelability_report.py tests/test_registry_case_builder.py tests/test_registry_ensemble_simulation.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 45 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 361 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- The registry-and-ranges foundation is now ready for a schema-first review of
  the first candidate real capability/dataset records. Real data should enter
  one selected case at a time, with literature-schema validation and no broad
  biology implementation.

## Data Intake Gate: Dataset Candidate Review

Date: 2026-06-01

Status: `complete` for schema-first candidate-review scaffolding before real
data insertion.

Completed:

- Added `src/fungal_model/data/candidate_review.py` with:
  - `DatasetCandidateReview`;
  - `DatasetCandidateReviewLoadError`;
  - `load_dataset_candidate_review`;
  - `validate_dataset_candidate_review`.
- Added public exports from `fungal_model.data`.
- Added `data/experiments/candidate_reviews/README.md` and a
  fake/schema-test-only candidate review fixture.
- Candidate reviews now require:
  - candidate id, name, status, maturity, source, intended use, schema gates,
    review metadata, and notes;
  - literature candidates to include citation, authors, year, and DOI or URL;
  - explicit schema-gate flags for units, uncertainty, preprocessing, and no
    embedded real data.
- Candidate reviews reject observations, measurement series, CSV paths, data
  rows, and other data-insertion fields.
- Documentation now states that candidate reviews are not datasets and must not
  contain extracted values.

Architecture/data debt:

- No architecture or data debt was added.
- No real literature data, real capability records, biological mechanisms, JAX,
  or broad biology implementation were added.

Verification:

- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py`
- Result: 11 passed.
- `.venv/bin/python -m pytest tests/test_dataset_candidate_review.py tests/test_literature_schema_contract.py tests/test_experiment_dataset_loading.py tests/test_guardrails_no_hardcoding.py tests/test_guardrails_no_shortcuts.py`
- Result: 39 passed.
- `/private/tmp/fungmod-venv/bin/ruff check src tests`
- Result: passed.
- `.venv/bin/python -m pytest`
- Result: 372 passed.

Tooling note:

- The `/private/tmp/fungmod-venv/bin/pyright` entry point was present but its
  Python module was missing in this environment, so pyright could not be run in
  this pass.

Next milestone:

- Select one real dataset candidate as a review record only, then validate its
  source/provenance metadata before adding any observations or registry
  capability records.
