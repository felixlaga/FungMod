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
| `fungmod run` | Preflight, then simulate and write tables, manifest and report. |
| `fungmod preflight` | Preflight only; optionally write the preflight tables. |
| `fungmod check-data DIR` | Validate a [user dataset](user-data.md) and list its gaps. |
| `fungmod list` | List the fungi, substrates and environments that can be named. |

The command line only parses arguments and prints what the API returns.
Name resolution, the preflight, the simulation rule of each mode, sampling,
the tables and the report are the ones described in
[virtual experiments](concepts/virtual-experiments.md) and
[outputs](concepts/outputs.md).

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
every combination. FungMod simulates only when every requested case passes
the preflight in the requested mode; otherwise nothing is simulated and the
command exits with 3, listing the blocked cases and their measurement
requests.

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

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success (`preflight`: every case is runnable). |
| 1 | The simulation failed after a passing preflight. |
| 2 | Usage or input error: missing or invalid arguments, unknown or ambiguous names, an invalid registry or user dataset, a non-empty output directory. |
| 3 | The preflight blocks at least one requested case in the requested mode; nothing is simulated. |
