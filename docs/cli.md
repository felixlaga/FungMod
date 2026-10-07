# Command line

The `fungmod` command runs the same virtual experiments as the Python API
without writing any Python: name a fungus or enzyme source, a substrate and
the conditions, and FungMod resolves the names, runs the modelability
preflight, simulates and writes the standard output bundle. It is installed
with the package (`python -m pip install fungmod`); `python -m fungal_model`
is the same command.

```bash
fungmod --version
fungmod --help
fungmod run --help
```

| Command | What it does |
| --- | --- |
| `fungmod run` | Preflight, then simulate and write tables, manifest and report; `--runnable-only` simulates the runnable cases when others are blocked (exit code 4); `--compare-timecourses` also compares the simulation with your time courses. |
| `fungmod preflight` | Preflight only; optionally write the preflight tables. |
| `fungmod check-data DIR` | Validate a [user dataset](user-data.md) and list its gaps, genome or proteome resolution, [cultures](user-data.md#fungal-culture-growth-and-secretion), [enzyme networks](user-data.md#several-enzymes-acting-together), time courses, fitted values, or every unfilled `REVIEW:` field. |
| `fungmod list` | List the fungi, substrates and environments that can be named. |
| `fungmod assemble` | Draft one reviewable user dataset for a fungus on substrates at conditions from its annotation, the classes you assert, a user dataset and kinetics sources (`assemble_user_tables`). |
| `fungmod draft-kinetics SOURCE` | Draft user tables from a SABIO-RK export or frozen snapshot (`user_tables_from_sabiork`). |
| `fungmod fit DIR` | Fit Km with kcat or Vmax of one case to the dataset's time courses and write the fitted dataset (`fit_user_dataset`). |

The command line only parses arguments and prints what the API returns.
Name resolution, the preflight, the simulation rule of each mode, sampling,
the tables and the report are the ones described in
[virtual experiments](concepts/virtual-experiments.md) and
[outputs](concepts/outputs.md); assembling, drafting, comparing and fitting
are the ones described in [user-supplied data](user-data.md). No subcommand
fetches anything from the network: every source is a local file, a user
dataset or a frozen snapshot already on disk.

The whole workflow for "fungus X on substrate Y in conditions Z" from a
shell is: [`assemble`](#fungus-x-on-substrate-y-at-conditions-z-from-your-sources)
the sources you have into a draft, fill its `REVIEW:` fields,
`check-data`, `run` (with [`--runnable-only`](#run-the-runnable-cases-of-a-request)
while the draft still has gaps), [compare](#compare-with-your-time-courses)
with your time courses and [fit](#fit-kinetic-constants-to-your-time-courses)
kinetic constants to them.

## Fungus X on substrate Y at 30 °C and pH 5

```bash
fungmod run \
  --fungus "P. chrysosporium" \
  --substrate cellobiose \
  --temperature-c 30 --ph 5 \
  --mode exploratory --samples 32 --seed 1 \
  --output runs/p_chrysosporium_30C_pH5 \
  --report
```

```text
Registry: .../data_registry/registry_index.yml (registry toy_registry, version 0.1.0, maturity development)
  fungus 'P. chrysosporium' -> phanerochaete_chrysosporium_k3 (Phanerochaete chrysosporium K-3 (BGL1A enzyme source))
  substrate 'cellobiose' -> cellobiose (Cellobiose)
  environment grid case temp_30C_ph_5p0_not_specified: temperature 30.0 degree_Celsius, pH 5.0, oxygen not_specified
Cases: 1 fungus x 1 substrate x 1 environment = 1

Preflight in exploratory mode:
  #  fungus                          substrate   environment                    status     runnable
  1  phanerochaete_chrysosporium_k3  cellobiose  temp_30C_ph_5p0_not_specified  modelable  yes

Simulated 1 case(s) in exploratory mode: 32 sample(s) per case, seed 1.
Run label: exploratory_uncertainty_screen

Case case_0000: phanerochaete_chrysosporium_k3 + cellobiose + temp_30C_ph_5p0_not_specified
  samples: 32 simulated, 0 failed
  environment effect: active_response_model (ph:ph_ionization_michaelis_menten)
  environment guardrail: Environment comparisons are allowed: explicit response laws act on ph; every other environment condition is metadata and the laws carry the documented limitations.
  Final metrics (median [5th, 95th percentile] over samples):
    final_substrate_remaining          0.4305 [0.4305, 0.4305] millimolar (n=32)
    final_substrate_degraded_fraction  0.9139 [0.9139, 0.9139] dimensionless (n=32)
    ...
  Threshold times (median [5th, 95th percentile] over samples):
    time_to_10_percent_substrate_degradation  808.1 [808.1, 808.1] second (n=32)
    time_to_50_percent_substrate_degradation  4824 [4824, 4824] second (n=32)
    time_to_90_percent_substrate_degradation  1.365e+04 [1.365e+04, 1.365e+04] second (n=32)

Output directory: runs/p_chrysosporium_30C_pH5
Manifest: runs/p_chrysosporium_30C_pH5/output_manifest.json
Report: runs/p_chrysosporium_30C_pH5/report/virtual_experiment_report.md
HTML report: runs/p_chrysosporium_30C_pH5/report/virtual_experiment_report.html
Report index: runs/p_chrysosporium_30C_pH5/report/index.html
Limitations: 14 (5 important, 9 info) in runs/p_chrysosporium_30C_pH5/limitations_table.csv
Provenance: 15 row(s) in runs/p_chrysosporium_30C_pH5/provenance_table.csv
Suggested experiments: 0 in runs/p_chrysosporium_30C_pH5/suggested_experiments.csv
```

Read the output from the top:

- Every name is shown with the registry record it resolved to. Names,
  aliases and ids are matched strictly; an unknown name stops with exit code
  2 and lists known terms, an ambiguous one lists its candidates.
- `--temperature-c` and `--ph` build a runtime condition grid (every
  combination of the values). A grid value changes rates only where the case
  template binds a response law; here the BGL1A case binds a pH law, so the
  case reports `active_response_model` for pH while 30 °C stays metadata, as
  the environment guardrail says. A case without a law reports
  `metadata_only` and must not be ranked across conditions.
- The final metrics and threshold times come from `summary_metrics.csv`
  (median and 5th to 95th percentile of the samples) and
  `threshold_times.csv`. Every value of this case is exact (its assay
  concentrations are exact exploratory priors), so all 32 samples agree;
  sampling spreads the results only where records carry ranges or
  distributions (the Reaction 618 example below).
- The limitations, provenance and suggested-experiment tables are named with
  their row counts; open them before using the numbers.

## Modes

`--mode` is required: it decides what may be simulated, so there is no
default.

| Mode | Inputs | Samples | Meaning |
| --- | --- | --- | --- |
| `exploratory` | modelable cases and cases with explicit ranges or exploratory priors | `--samples N` and `--seed S` required | Output quantiles propagate the stated input ranges; they are not calibrated confidence intervals. |
| `scientific` | exact, non-exploratory, non-toy values and implemented mechanisms only | one exact run per case; `--samples` and `--seed` are refused | Scientific means exact with current registry records and implemented mechanisms; it does not mean experimentally validated. |

The same request can pass in one mode and stop in the other. The BGL1A
assay concentrations above are exploratory priors, not curated values, so in
scientific mode the preflight treats them as missing and stops:

```bash
fungmod preflight --fungus "P. chrysosporium" --substrate cellobiose \
  --temperature-c 30 --ph 5 --mode scientific
```

```text
Preflight in scientific mode:
  #  fungus                          substrate   environment                    status              runnable
  1  phanerochaete_chrysosporium_k3  cellobiose  temp_30C_ph_5p0_not_specified  underparameterized  no
  case 1:
    missing parameter bgl1a_assay_initial_cellobiose_concentration; suggested experiment: Measure or curate bgl1a_assay_initial_cellobiose_concentration for the selected registry case.
    missing parameter bgl1a_assay_enzyme_concentration; suggested experiment: Measure or curate bgl1a_assay_enzyme_concentration for the selected registry case.
    blocked: missing_inputs; next action: measure_or_curate_missing_inputs

Not runnable: 1 of 1 case(s) cannot be simulated in scientific mode.
Scientific simulation requires exact, non-exploratory, non-toy modelable cases. Scientific means exact with current registry records and implemented mechanisms; it does not mean experimentally validated.
Measurement requests:
  - Measure or curate bgl1a_assay_initial_cellobiose_concentration for the selected registry case.
  - Measure or curate bgl1a_assay_enzyme_concentration for the selected registry case.
```

The exit code is 3. Add `--output DIR` to write the preflight tables
(`modelability_preflight.csv`, `modelability_items.csv`, the data dictionary
and the schema).

## Registry environments

Name a curated environment instead of a grid with `--environment` (repeatable;
`--condition` is the same option):

```bash
fungmod run \
  --fungus "beta-glucosidase source" --substrate cellobiose \
  --environment "SABIO-RK Reaction 618 selected assay conditions" \
  --mode exploratory --samples 32 --seed 618 --output runs/reaction_618
```

```text
Preflight in exploratory mode:
  #  fungus                           substrate   environment                               status       runnable
  1  sabiork_beta_glucosidase_source  cellobiose  sabiork_reaction_618_selected_conditions  exploratory  yes
  case 1:
    uncertain parameter enzyme_concentration_beta_glucosidase: Required parameter has a sampleable uncertain ValueSpec.
...
  Final metrics (median [5th, 95th percentile] over samples):
    final_substrate_remaining          3.059 [3.044, 3.06] millimolar (n=32)
    final_substrate_degraded_fraction  0.0003956 [2.473e-05, 0.005202] dimensionless (n=32)
    ...
  Threshold times (median [5th, 95th percentile] over samples):
    time_to_10_percent_substrate_degradation  not_reached in 32 of 32 samples (Threshold was not reached within the simulated time span.)
```

The enzyme concentration is a sampled range (an exploratory prior), so the
case is `exploratory`, runs only in exploratory mode, and its percentiles
describe that prior range, not a calibrated uncertainty.

The whole-organism culture case runs in scientific mode, one exact run per
condition, with no `--samples` or `--seed`:

```bash
fungmod run \
  --fungus "T. harzianum P49P11" --substrate "Celufloc 200" \
  --environment gelain_2020_cellulose_batch_10gl \
  --environment gelain_2020_cellulose_batch_20gl \
  --mode scientific --output runs/t_harzianum
```

Several `--fungus`, `--substrate` and `--environment` (or grid) values form
every combination. By default FungMod simulates only when every requested
case passes the preflight in the requested mode; otherwise nothing is
simulated and the command exits with 3, listing the blocked cases and their
measurement requests, and suggests `--runnable-only` when some case is
runnable.

## Run the runnable cases of a request

A real request almost always has gaps: most enzyme classes of a genome have
no kinetics, and a condition without measured constants is a gap. With
`--runnable-only`, `run` simulates the cases that pass the preflight in the
requested mode and reports the others instead of refusing the whole request
(the API's `VirtualExperiment.simulate(blocked="report")`):

```bash
fungmod run \
  --fungus "beta-glucosidase source" --substrate cellobiose \
  --environment "SABIO-RK Reaction 618 selected assay conditions" \
  --environment toy_lab_environment \
  --mode exploratory --samples 32 --seed 618 --output runs/partial \
  --runnable-only
```

```text
Preflight in exploratory mode:
  #  fungus                           substrate   environment                               status              runnable
  1  sabiork_beta_glucosidase_source  cellobiose  sabiork_reaction_618_selected_conditions  exploratory         yes
  2  sabiork_beta_glucosidase_source  cellobiose  toy_lab_environment                       underparameterized  no
...
Not runnable: 1 of 2 case(s) cannot be simulated in exploratory mode.
--runnable-only: simulating the 1 runnable case(s); the blocked case(s) are not simulated and are listed in case_summary.csv as not_simulated, with their missing inputs in missing_parameters.csv and their measurement requests in suggested_experiments.csv.
Measurement requests:
  - Measure or curate initial_cellobiose_concentration for the selected registry case.
  - Measure or curate enzyme_concentration_beta_glucosidase for the selected registry case.

Simulated 1 case(s) in exploratory mode: 32 sample(s) per case, seed 618.
Partial run: 1 of 2 requested case(s) simulated; the others were blocked by the preflight.
...
Case case_0000: sabiork_beta_glucosidase_source + cellobiose + sabiork_reaction_618_selected_conditions
  samples: 32 simulated, 0 failed
  ...
  Final metrics (median [5th, 95th percentile] over samples):
    final_substrate_remaining          3.059 [3.044, 3.06] millimolar (n=32)
    ...

Case case_0001: sabiork_beta_glucosidase_source + cellobiose + toy_lab_environment
  not simulated: blocked_by_preflight: the exploratory-mode preflight reports underparameterized (blocking reason missing_inputs; next action measure_or_curate_missing_inputs). ...
...
Partial run: 1 of 2 requested case(s) were blocked by the preflight and not simulated (case_0001); exit code 4.
```

- Which cases run is the preflight's rule for the mode, unchanged:
  scientific mode simulates `modelable` cases only, exploratory mode also
  `exploratory` ones. A scientific partial run keeps the scientific wording:
  scientific means exact with current registry records and implemented
  mechanisms; it does not mean experimentally validated.
- The blocked cases are not simulated. They keep their place in the bundle:
  `case_summary.csv` has a row with `case_status` `not_simulated` and the
  reason, `modelability_preflight.csv`, `modelability_items.csv`,
  `missing_parameters.csv` and `suggested_experiments.csv` give their status,
  missing inputs and measurement requests, and `limitations_table.csv` a
  blocking row. They have no row in the per-sample tables (time series,
  final metrics, threshold times, sampled parameters). See
  [partial runs](concepts/outputs.md#partial-runs).
- `virtual_experiment_summary.json`, `output_manifest.json` and the report
  say that the run is partial (`partial_run`, `requested_case_count`,
  `simulated_case_count`) and list the blocked cases.
- Every case keeps the `case_id` of its place in the requested grid
  (`case_0001` above is the second requested case) and the seed of that
  place, so the samples of a simulated case are the ones a run of the same
  request without gaps gives, and the ones `simulate_screen(...,
  cases=[that case])` gives on the same request. The Reaction 618 case is the
  first case here, so its metrics equal those of the single-case run in
  [registry environments](#registry-environments). A case that is not first
  gets another seed in a request that names it alone.
- The exit code is 4 ("partial: some cases blocked"), never 0, so that a
  script notices the missing cases. When no case is runnable, nothing is
  simulated and the exit code stays 3; when none is blocked, the run is a
  full run (exit code 0).

The flag is called `--runnable-only` rather than `--run-runnable`: it says
which cases run (only the runnable ones) without repeating the subcommand
(`fungmod run --run-runnable`), and a printed command that carries it shows
at a glance that some requested cases may not run. The blocked cases are
reported with or without it; the flag only decides whether the runnable ones
are simulated.

## Your own data

Check a [user dataset](user-data.md) directory first:

```bash
fungmod check-data path/to/esterase_case
```

```text
User dataset: esterase_demo
Digest: de74a07c236345be875cb64551c82041490b516d8d448a7e619cb2b8747fc345
Directory: /abs/path/to/esterase_case
Base registry: .../data_registry/registry_index.yml (registry toy_registry)
Simulation time grid: 60 minute, 61 points
Generated records:
  record type            count
  fungi                  1
  enzyme_classes         1
  substrates             1
  environments           1
  process_compatibility  1
  case_templates         1
  parameter_records      4
Kinetic values: 4; gaps: 0
```

A missing kinetics row becomes a gap with its measurement request:

```text
Kinetic values: 3; gaps: 1
Gaps (explicit unknowns; preflight reports their cases as underparameterized):
  - esterase_demo__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__c37_ph7_5__kcat__gap
    measurement request: Measure kcat of carboxylesterase from Esterase source strain E1 on p-nitrophenyl butyrate at 37 degC, pH 7.5 (units of 1/time).
```

An invalid directory exits with 2 and lists every issue as
`file:row:column: message` (the row is the spreadsheet line, the header is
line 1; `-` marks a file-level issue):

```text
fungmod check-data: error: User dataset 'bad_case' is invalid. 2 issue(s):
  kinetics.csv:2:units: km units 'parsec' must be a substrate concentration (amount or mass per volume, for example mM, uM or g/L).
  kinetics.csv:3:units: kcat units 'furlong' must have the dimension 1/time (for example 1/s or 1/min).
```

Then name your strain, substrate and `condition_id`:

```bash
fungmod run --user-data path/to/esterase_case \
  --fungus "Esterase source strain E1" --substrate "p-nitrophenyl butyrate" \
  --condition c37_ph7_5 \
  --mode exploratory --samples 32 --seed 5 --output runs/esterase
```

The dataset is overlaid on the registry in memory; its id and digest are
printed and recorded in `output_manifest.json`. Estimates
(`evidence_type: estimate`) run only in exploratory mode; exact `measured`,
`literature` or `design` values also run in scientific mode:

```bash
fungmod run --user-data path/to/literature_reentry \
  --fungus "Os3BGlu6 source" --substrate cellobiose --condition c30_ph5 \
  --mode scientific --output runs/reentry
```

## Fungus X on substrate Y at conditions Z, from your sources

`fungmod assemble` is the command-line form of
[`assemble_user_tables`](user-data.md#assembling-fungus-substrate-and-conditions):
name one fungus, its substrates and the conditions, give the sources you have,
and it writes one reviewable user-dataset draft for exactly that request and
prints, per enzyme class, substrate and condition, what is known, from where
and what is missing. The example uses files of a repository checkout: the
hand-written dbCAN format fixture of `tests/fixtures/user_data/genome_case/`
(synthetic gene identifiers, not a real genome) and the frozen SABIO-RK
Reaction 618 export.

```bash
fungmod assemble \
  --fungus "Genome-annotated strain G1" \
  --substrate cellobiose \
  --temperature-c 30 --temperature-c 40 --ph 5 \
  --annotation tests/fixtures/user_data/genome_case/annotations/strain_g1_overview.txt \
  --annotation-tool "dbCAN 3 overview format (hand-written fixture; no dbCAN run)" \
  --kinetics-source data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw/kinlaw_entries_reaction_618.json \
  --entry-id 35622 \
  --dataset-id g1_draft --output g1_draft
```

```text
Assembled draft: g1_draft
  fungus 'Genome-annotated strain G1' -> Genome-annotated strain G1 (strain genome_annotated_strain_g1, new_strain)
  substrate 'cellobiose' -> Cellobiose (cellobiose, registry)
  condition c30_ph5: 30 degC, pH 5 (conditions.csv)
  condition c40_ph5: 40 degC, pH 5 (conditions.csv)

Enzyme classes of the fungus: 5
  class              declared in  evidence
  beta_glucosidase   genomes.csv  genome annotation (dbCAN, 3 genes, families GH1, GH3; family_polyspecific)
  cellobiohydrolase  genomes.csv  genome annotation (dbCAN, 1 gene, families GH7; family_diagnostic)
  cellulase_generic  genomes.csv  genome annotation (dbCAN, 1 gene, families GH5; family_polyspecific)
  endo_xylanase      genomes.csv  genome annotation (dbCAN, 1 gene, families GH10; family_diagnostic)
  glucoamylase       genomes.csv  genome annotation (dbCAN, 1 gene, families GH15; family_diagnostic)
Annotated classes without a registry record (no case is assembled for them):
  - laccase (families AA1): no enzyme-class record in the registry; ...
  ...
On Cellobiose (cellobiose): acting classes beta_glucosidase
  not acting: cellobiohydrolase: substrate class 'cellobiose' is not among the class's substrate classes ['cellulose_particulate', 'cellulose_film_generic']
  not acting: cellulase_generic: substrate class 'cellobiose' is not among the class's substrate classes ['cellulose_film_generic']
  not acting: endo_xylanase: substrate class 'cellobiose' is not among the class's substrate classes ['xylan']
  not acting: glucoamylase: substrate class 'cellobiose' is not among the class's substrate classes ['starch']

Cases: 2 (enzyme class x substrate x condition)
  #  fungus                      class             substrate   condition  kinetics status       route           source ids
  1  Genome-annotated strain G1  beta_glucosidase  cellobiose  c30_ph5    transferred_estimate  same_condition  SABIO-RK EntryID 35622
  2  Genome-annotated strain G1  beta_glucosidase  cellobiose  c40_ph5    gap                   none            SABIO-RK EntryID 35622
  case 1: transferred from Oryza sativa enzyme, SABIO-RK entry 35622: a cross-organism transfer, written as estimates for Genome-annotated strain G1 (exploratory mode only)
  case 2: kinetics for beta-glucosidase on Cellobiose are stated only at c30_ph5 (...); FungMod does not reuse them at 40 degC, pH 5 without a temperature response law, so this condition is a gap whose measurement requests name c30_ph5
Transferred from another organism (estimates, exploratory mode only): entries 35622

Kinetic-law entries considered: 29
  entry  organism                     use           reason
  35622  Oryza sativa                 converted     -
  35633  Oryza sativa                 not selected  not selected by entry_ids
  ...

Limitations of this draft:
  - One fungus per call; ...

Draft written to g1_draft:
  annotations/strain_g1_overview.txt
  conditions.csv
  ...

Fields to fill (8); check-data refuses the directory until each REVIEW: field is filled:
  user_dataset.yml:-:contributor: REVIEW: name of the person who reviewed these tables
  user_dataset.yml:-:simulation.duration: REVIEW: simulated duration, a positive number (FungMod has no default time grid)
  user_dataset.yml:-:simulation.units: REVIEW: time unit of the duration, such as minute or hour
  user_dataset.yml:-:simulation.points: REVIEW: number of output time points, an integer of at least 2
  kinetics.csv:5:value: REVIEW: enzyme concentration of beta-glucosidase in the simulated Cellobiose system (amount per volume), ...
  kinetics.csv:5:units: REVIEW: an amount-per-volume unit such as uM
  kinetics.csv:5:source: REVIEW: where the enzyme concentration of the virtual experiment comes from
  genomes.csv:2:source: REVIEW: the genome or proteome that was annotated, ideally with its accession and the run

Next:
  1. Fill the 8 REVIEW: field(s) above; g1_draft/review.md explains every decision.
  2. fungmod check-data g1_draft
  3. Run it (exploratory mode samples ranges and estimates; scientific mode takes exact measured, literature or design values only):
     fungmod run --user-data g1_draft --fungus 'Genome-annotated strain G1' --substrate cellobiose --condition c30_ph5 --condition c40_ph5 --runnable-only \
       --mode exploratory --samples N --seed S --output RUN_DIR
     --runnable-only because 1 case(s) of this command have no kinetics in the draft (beta_glucosidase on cellobiose at c40_ph5 (gap)): the preflight blocks them, so without the flag nothing is simulated (exit code 3); with it the runnable cases are simulated and the blocked ones are listed with their measurement requests (exit code 4).
```

The options map one to one onto the arguments of `assemble_user_tables`:

| Option | API argument |
| --- | --- |
| `--fungus NAME` (one per call) | `fungus` |
| `--substrate NAME` (repeatable) | `substrates` (names; a new substrate's categories become `REVIEW:` fields) |
| `--temperature-c T --ph PH` (repeatable) | `conditions`: every T x pH pair, in degC, as for the `run` grid |
| `--scientific-name NAME` | `scientific_name` |
| `--annotation FILE`, `--annotation-tool TOOL`, `--annotation-source TEXT` | `annotation`, `annotation_tool`, `annotation_source` |
| `--enzyme-class CLASS`, `--enzyme-class-evidence CLASS EVIDENCE SOURCE` (repeatable) | `enzyme_classes` (a name, or a mapping with evidence and source) |
| `--kinetics-source SOURCE` (repeatable) | `kinetics_sources`: a SABIO-RK export JSON, or a reaction id read from the frozen snapshots |
| `--entry-id ID`, `--same-species ORGANISM` (repeatable) | `entry_ids`, `same_species` |
| `--user-data DIR` | `user_data` |
| `--responses FILE` | `responses`: a CSV with the columns of `responses.csv`, `substrate` in place of `strain_id` and `substrate_id` |
| `--design QUANTITY=VALUE UNITS` or `QUANTITY=LOWER:UPPER UNITS` (repeatable) | `design` (`substrate_initial_concentration`, `enzyme_concentration`, `enzyme_loading`) |
| `--time-grid DURATION UNITS POINTS` | `time_grid` |
| `--cache-dir DIR`, `--registry PATH` | `cache_dir`, `registry` |
| `--dataset-id ID`, `--output DIR` | `dataset_id`; the new or empty directory `draft.write` writes |

Nothing is defaulted that the API leaves to you: an option you do not give
is not passed, so the decision stays a `REVIEW:` field (or the API's own
documented default, such as every entry when `--entry-id` is absent). Given
`--annotation-source`, `--design enzyme_concentration=0.001 mM` and
`--time-grid 10 hour 61`, only the reviewer's name is left to fill. Kelvin
temperatures, explicit condition ids and notes, and a new substrate's
categories are not options; edit `conditions.csv` notes or `substrates.csv`
during the review, or use the Python API.

**Fill the review fields.** Open `g1_draft/review.md`, decide each field and
edit the files: for example `contributor: Your Name` and
`simulation: {duration: 10, units: hour, points: 61}` in `user_dataset.yml`,
the enzyme concentration of your virtual assay in `kinetics.csv` row 5
(`0.001`, `mM` and where the value comes from) and the annotated genome in
`genomes.csv`. Until then `check-data` refuses the directory and lists every
field:

```text
fungmod check-data: error: User dataset 'g1_draft' still has unfilled review fields (cells or manifest values beginning with 'REVIEW:'). 8 issue(s):
  user_dataset.yml:-:contributor: Unfilled review field contributor: 'REVIEW: name of the person who reviewed these tables'. Replace it with a reviewed value before loading.
  ...
  Fill each REVIEW: field (a drafted directory's review.md says what to decide for each), then run fungmod check-data again.
```

After the review:

```bash
fungmod check-data g1_draft
```

```text
User dataset: g1_draft
...
Kinetic values: 4; gaps: 4
Gaps (explicit unknowns; preflight reports their cases as underparameterized):
  - g1_draft__genome_annotated_strain_g1__beta_glucosidase__cellobiose__c40_ph5__km__gap
    measurement request: Measure km of beta-glucosidase from Genome-annotated strain G1 on Cellobiose at 40 degC, pH 5 (concentration units); kinetics.csv states kinetic constants of this strain, enzyme class and substrate only at c30_ph5 (30 degC, pH 5), and FungMod does not reuse kinetics measured at another condition; the class was inferred from the dbCAN annotation (...).
  ...
Genome and proteome annotations (genomes.csv): 1
  strain                      file                                tool                                                          source
  genome_annotated_strain_g1  annotations/strain_g1_overview.txt  dbCAN 3 overview format (hand-written fixture; no dbCAN run)  ...
  note: Enzyme classes inferred from a genome annotation state what the strain can encode, not what it expresses, secretes or how fast; ...
Enzyme classes resolved from them: 5
...
```

`check-data` also prints a dataset's cultures (one row per strain and
culture substrate, with the consuming pool, every enzyme pool and the
`culture.csv` rows; see
[fungal culture](user-data.md#fungal-culture-growth-and-secretion)), its
enzyme networks (each entry's chain of pools with the yields and strains, and
one row per process with its class, pool, rate form and competitive inhibitor;
see [several enzymes acting together](user-data.md#several-enzymes-acting-together)), its time
courses (one row per series, with its points, time range, units and how many
observations carry an `sd`) and, for a fitted dataset, the fitted values with
their identifiability verdicts.

**Run it.** The printed command asks for both conditions and carries
`--runnable-only`, because the 40 degC case is a gap that the preflight
blocks. The 30 degC case, whose transferred kinetics are estimates and
therefore run in exploratory mode only, is simulated; the 40 degC case is
listed with its measurement requests, and the exit code is 4:

```bash
fungmod run --user-data g1_draft --fungus "Genome-annotated strain G1" \
  --substrate cellobiose --condition c30_ph5 --condition c40_ph5 --runnable-only \
  --mode exploratory --samples 32 --seed 1 --output runs/g1
```

```text
Preflight in exploratory mode:
  #  fungus                                substrate   environment        status              runnable
  1  g1_draft__genome_annotated_strain_g1  cellobiose  g1_draft__c30_ph5  exploratory         yes
  2  g1_draft__genome_annotated_strain_g1  cellobiose  g1_draft__c40_ph5  underparameterized  no
...
Not runnable: 1 of 2 case(s) cannot be simulated in exploratory mode.
--runnable-only: simulating the 1 runnable case(s); the blocked case(s) are not simulated and are listed in case_summary.csv as not_simulated, with their missing inputs in missing_parameters.csv and their measurement requests in suggested_experiments.csv.
Measurement requests:
  - Measure km of beta-glucosidase from Genome-annotated strain G1 on Cellobiose at 40 degC, pH 5 (concentration units); kinetics.csv states kinetic constants of this strain, enzyme class and substrate only at c30_ph5 (30 degC, pH 5), and FungMod does not reuse kinetics measured at another condition; ...
  ...

Simulated 1 case(s) in exploratory mode: 32 sample(s) per case, seed 1.
Partial run: 1 of 2 requested case(s) simulated; the others were blocked by the preflight.
...
Case case_0000: g1_draft__genome_annotated_strain_g1 + cellobiose + g1_draft__c30_ph5
  samples: 32 simulated, 0 failed
  ...
  Final metrics (median [5th, 95th percentile] over samples):
    final_substrate_remaining          25.34 [4.461, 67.46] millimolar (n=32)
    final_substrate_degraded_fraction  0.1056 [0.05378, 0.2058] dimensionless (n=32)
    ...

Case case_0001: g1_draft__genome_annotated_strain_g1 + cellobiose + g1_draft__c40_ph5
  not simulated: blocked_by_preflight: the exploratory-mode preflight reports underparameterized (blocking reason missing_inputs; next action measure_or_curate_missing_inputs). ...
...
Partial run: 1 of 2 requested case(s) were blocked by the preflight and not simulated (case_0001); exit code 4.
```

The spread comes from the other organism's assay concentration range, which
the transfer keeps as a range; it describes that input range, not a
calibrated uncertainty of this fungus. The 30 degC case is the first case of
the request, so a run of `--condition c30_ph5` alone with the same seed gives
the same samples, byte for byte. Without `--runnable-only` the command
simulates nothing and exits with 3. In scientific mode no case of this draft
is runnable (the transferred values are estimates), so the command exits with
3 even with the flag.

A condition that a temperature or pH law reaches from the measured one (see
[assembling](user-data.md#assembling-fungus-substrate-and-conditions)) is
not a `conditions.csv` row; `assemble` then prints a second `fungmod run`
command with `--temperature-c` and `--ph` for that grid condition.

## Draft tables from SABIO-RK

`fungmod draft-kinetics` is the command-line form of
[`user_tables_from_sabiork`](user-data.md#starting-from-sabio-rk). `SOURCE`
is a SABIO-RK kinetic-law export JSON you downloaded, or a reaction id read
from the frozen snapshots on disk (`--cache-dir`, then the snapshots shipped
with FungMod). `--provider sabiork` is required: the command line names no
database itself and offers the providers of the API's table
`USER_TABLE_PROVIDERS`. Nothing is fetched; fetch a new export with
`source_proposal(provider="sabiork", ..., refresh=True)` in Python or from the
SABIO-RK website.

```bash
fungmod draft-kinetics \
  data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw/kinlaw_entries_reaction_618.json \
  --provider sabiork --entry-id 35622 \
  --design substrate_initial_concentration=10 mM --design enzyme_concentration=0.001 mM \
  --dataset-id os3bglu6_sabiork --output os3bglu6_sabiork
```

```text
Drafted user tables: os3bglu6_sabiork (provider sabiork, source data/kinetic_records/.../kinlaw_entries_reaction_618.json)
Entries converted: 1 (35622)
Parameters listed, not converted: 3
  entry 35622 kcat_Km (kcat/Km) 0.0085 mM^(-1)*s^(-1): kcat/Km is not a user-data quantity; FungMod never derives Km or kcat from it
  entry 35622 E (concentration): SABIO-RK gives no value
  entry 35622 substrate_initial_concentration (3.06 to 76.5 mM) (concentration): replaced by the design value substrate_initial_concentration = 10 mM (...)

Tables:
  strains.csv: 1 row(s)
  ...
Strains (--fungus):
  strain_id                                     name
  oryza_sativa_in_escherichia_coli_origami_de3  SABIO-RK enzyme source: Oryza sativa, expressed in Escherichia coli Origami (DE3)
...
Fields to fill (4); check-data refuses the directory until each REVIEW: field is filled:
  user_dataset.yml:-:contributor: REVIEW: name of the person who reviewed these tables
  ...
```

Without `--entry-id`, the whole Reaction 618 export converts five entries
(38521, 39245, 44879, 44888, 60725) and lists the other 24 with the reason
(mutants, conflicts, unresolved EC numbers, no Km, kcat or Vmax), exactly as
the API reports them. `--strain-for "ORGANISM=STRAIN_ID"` maps a SABIO-RK
organism to your strain id (`strain_id_for_organism`), and
`--propose-enzyme-classes` drafts an `enzyme_classes.csv` row with `REVIEW:`
bond and substrate classes for an unresolved EC number.

## Compare with your time courses

With a user dataset that has a [`timecourse.csv`](user-data.md#time-courses-comparison-and-fitting),
`fungmod run --compare-timecourses` runs
`DegradationScreenResult.compare_with_timecourses()` after simulating: it
writes `timecourse_comparison.csv` into the output directory (and the
manifest) and prints per series the RMSE and mean residual in the series'
units, the fraction of observations inside the simulated 5-95 % band, and
how many observations were used in a fit. The comparison is a flag of `run`
rather than its own subcommand because the API compares a simulation result
in memory with the dataset that built it; there is no result to reload. The
example dataset is the esterase fixture with three initial substrate
concentrations (`s50`, `s200`, `s800`) and the synthetic time courses that
`tests/test_user_data_timecourse.py` builds from a FungMod simulation with
known constants (not measurements).

```bash
fungmod run --user-data esterase_timecourses \
  --fungus "Esterase source strain E1" --substrate "p-nitrophenyl butyrate" \
  --condition s50 --condition s200 --condition s800 \
  --mode exploratory --samples 1 --seed 1 --output runs/esterase --compare-timecourses
```

```text
...
Time-course comparison with user dataset esterase_demo (in-sample agreement, not validation):
  case       observable  n  with sd  RMSE       mean residual  inside 5-95% band  used in fit
  case_0000  substrate   8  8        0.7792 µM  -0.2052        0                  0
  case_0000  product     8  8        0.5679 µM  -0.3513        0                  0
  case_0001  substrate   8  8        1.27 µM    -0.2958        0                  0
  case_0001  product     8  8        1.869 µM   -0.4214        0                  0
  case_0002  substrate   8  8        8.922 µM   0.3853         0                  0
  case_0002  product     8  8        4.068 µM   0.2618         0                  0
  case_0000: time courses of esterase_demo__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__s50
  ...
  In-sample agreement between this simulation and the user's own time courses from the same dataset; it is not validation. ...
  Interpolation: linear interpolation of the simulated p05, p50 and p95 trajectories between the points of the simulated output grid; observations outside the simulated time range are refused, never extrapolated.
Comparison table: runs/esterase/timecourse_comparison.csv
```

With one sample the inputs are exact and the band has zero width, so the
fraction inside it says little; the RMSE is the informative column here.
`--compare-timecourses` needs `--user-data` with a `timecourse.csv`, and
both are checked before anything is simulated (exit code 2). An observation
outside the simulated time range refuses the comparison after the simulation
(exit code 2, the issue printed as `timecourse.csv:row:time: message`); the
simulation bundle is then complete and only `timecourse_comparison.csv` is
missing. Extend `simulation.duration` and run again.

## Fit kinetic constants to your time courses

`fungmod fit` is the command-line form of
[`fit_user_dataset`](user-data.md#fitting-kinetic-constants-to-time-courses).
`--case STRAIN_ID ENZYME_CLASS SUBSTRATE_ID` names the case as the tables do,
and each `--fit QUANTITY LOWER UPPER UNITS` names a fitted quantity (`km`,
`kcat` or `vmax`) with its required bounds; there are no default bounds.

```bash
fungmod fit esterase_timecourses \
  --case strain_e1 carboxylesterase p_nitrophenyl_butyrate \
  --fit km 10 5000 µM --fit kcat 1 300 1/min \
  --initial km 1000 --initial kcat 5 \
  --output esterase_fitted
```

```text
Fitting km, kcat of strain_e1 / carboxylesterase / p_nitrophenyl_butyrate in esterase_timecourses

Fit of user dataset esterase_demo (digest 43aa9fbc...):
  case: strain_e1 / carboxylesterase / p_nitrophenyl_butyrate
  conditions: s50, s200, s800
  observations: 48 (timecourse.csv rows 2-49); fitted quantities: 2; residual degrees of freedom: 46
  error model: sd_weighted
  objective: sum over the time-course observations of ((simulated - observed) / sd)^2, ...
  optimizer: converged (`ftol` termination condition is satisfied.)
  quantity  value  units  interval (95%)  identifiability  bounds      start
  km        148    µM     [132.5, 165.1]  identified       [10, 5000]  1000 (caller-supplied starting value)
  kcat      30.18  1/min  [28.03, 32.52]  identified       [1, 300]    5 (caller-supplied starting value)
  km: profile likelihood, delta chi-square threshold 3.841 (chi-square, 1 degree of freedom, 0.95); the profile exceeds the threshold on both sides within the bounds.
  kcat: profile likelihood, delta chi-square threshold 3.841 (chi-square, 1 degree of freedom, 0.95); the profile exceeds the threshold on both sides within the bounds.

In-sample: Values fitted to the dataset's own time courses: in-sample parameter estimation, not validation. ...

Fitted dataset: esterase_demo_fitted (digest ...)
Directory: .../esterase_fitted
Fit report: esterase_fitted/fit_report.json

Next (fitted values run in exploratory mode only; scientific mode refuses them):
  fungmod check-data esterase_fitted
  fungmod run --user-data esterase_fitted --fungus strain_e1 --substrate p_nitrophenyl_butyrate --condition s50 --condition s200 --condition s800 \
    --mode exploratory --samples N --seed S --output RUN_DIR --compare-timecourses
```

The time courses were simulated with Km = 150 µM and kcat = 30 1/min plus
noise, and both lie in the printed intervals. A run of the fitted dataset with
`--compare-timecourses` reports every observation as used in the fit: the
agreement is in-sample by construction.

| Option | API argument |
| --- | --- |
| `DIR` | `dataset` |
| `--case STRAIN_ID ENZYME_CLASS SUBSTRATE_ID` and `--fit QUANTITY LOWER UPPER UNITS` (repeatable) | `parameters` and `bounds` |
| `--initial QUANTITY VALUE` (repeatable) | `initial`; without it the dataset's exact value is the start |
| `--condition CONDITION_ID` (repeatable) | `conditions`; without it every condition with time courses |
| `--error-model sd_weighted` or `unweighted` | `error_model` (the API's default `sd_weighted` is refused when an observation has no `sd`; `unweighted` is used only when named) |
| `--allow-unidentified` | `allow_unidentified` |
| `--fitted-dataset-id ID` | `fitted_dataset_id` (default `<input id>_fitted`) |
| `--confidence-level P`, `--profile-points N`, `--diff-step STEP`, `--max-nfev N` | `confidence_level` (0.95), `profile_points` (21), `diff_step` (1e-3), `max_nfev` |
| `--registry PATH` | `base_registry` |
| `--output DIR` | the new or empty directory `UserDatasetFit.write` writes |

A quantity the time courses do not identify refuses the fit with exit code
2: the verdicts found are printed, the issues follow as
`timecourse.csv:-:-: km is not_identified_within_bounds ...`, and nothing is
written. `--allow-unidentified` writes it labelled `NOT IDENTIFIED` instead.
A fit that does not converge, a dataset that is itself a fit, too few
observations and invalid bounds are refused the same way.

## Discover names

```bash
fungmod list --aliases
fungmod list --user-data path/to/esterase_case
```

`list` prints the registry (path, id, version and maturity) and each fungus or
enzyme source, substrate and environment with its id, name, maturity and,
with `--aliases`, the aliases that `--fungus`, `--substrate` and
`--environment` accept. The packaged registry is a development registry
(`toy_registry`): read each record's maturity before relying on it.

## Arguments without defaults

- `--mode` is required.
- In exploratory mode `--samples` and `--seed` are required, so every sampled
  run is reproducible; FungMod never chooses a seed. Scientific mode refuses
  both.
- `--output` is required and must be a new or empty directory, so the
  manifest lists only the files of this run.
- A grid needs at least one `--temperature-c` and at least one `--ph`;
  FungMod does not assume a missing condition. `--oxygen` adds a metadata
  label; without it the grid records `not_specified`. A grid and
  `--environment` cannot be mixed.
- `--registry` defaults to the registry packaged with FungMod; the registry
  used is printed first.
- `--report` adds the HTML report and `index.html`; the Markdown report is
  always written. `--no-plots` skips the quick-look figures.
- `--runnable-only` is an explicit opt-in: without it a request with a
  blocked case simulates nothing (exit code 3), as before.
- `assemble` and `draft-kinetics` require `--dataset-id`; `fit` names the
  fitted dataset `<input id>_fitted` (the API's default) unless
  `--fitted-dataset-id` is given. All three require a new or empty
  `--output`; nothing is overwritten. `assemble` takes one `--fungus` and
  needs both `--temperature-c` and `--ph`, like the `run` grid.
- An option of `assemble`, `draft-kinetics` or `fit` that you do not give is
  not passed to the API: the decision stays a `REVIEW:` field of the draft, or
  the API's own documented default applies (stated in `--help`).
  `draft-kinetics --provider` and every `fit --fit` bound are required.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success (`preflight`: every case is runnable). |
| 1 | The simulation failed after a passing preflight. |
| 2 | Usage or input error: missing or invalid arguments, unknown or ambiguous names, an invalid registry or user dataset (including unfilled `REVIEW:` fields), a draft the API refuses (`UserTablesSourceError`, `UserTablesAssemblyError`), a refused fit (`UserDataFitError`: not identified, not converged, invalid bounds), a refused time-course comparison (printed after the complete simulation bundle), a non-empty output directory. Issues that carry a file, row and column are printed as `file:row:column: message`. |
| 3 | The preflight blocks at least one requested case in the requested mode; nothing is simulated (with `--runnable-only`: no requested case is runnable). |
| 4 | Partial run (`run --runnable-only`): the runnable cases were simulated and the bundle written; the blocked cases are listed with their measurement requests and marked `not_simulated` in the tables. |
