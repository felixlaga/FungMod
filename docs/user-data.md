# User-supplied data

FungMod can simulate a strain, substrate and condition from your own tables
without anyone editing the registry YAML. You put a small manifest and a few
CSV tables in one directory; `load_user_dataset` checks them, reports every
problem at once, and turns them into ordinary registry records that keep each
value's source, units, condition and maturity. `VirtualExperiment` overlays
those records on the registry in memory, so the shared registry is never
modified and nothing is promoted into it.

```python
import fungmod as fm

study = fm.virtual_experiment(
    fungi="Esterase source strain E1",      # a strain name, alias or strain_id
    substrates="p-nitrophenyl butyrate",    # your substrate, or a registry substrate
    environments="c37_ph7_5",               # a condition_id from conditions.csv
    user_data="path/to/esterase_case",      # the dataset directory
)
reports = study.preflight(mode="exploratory")
result = study.simulate(mode="exploratory", n_samples=8)
```

To check a directory before simulating, load it directly. A
`UserDataError` lists every issue with its file, spreadsheet row, column and
message:

```python
try:
    dataset = fm.load_user_dataset("path/to/esterase_case")
except fm.UserDataError as error:
    for issue in error.issues:
        print(issue["file"], issue["row"], issue["column"], issue["message"])
```

A loaded `UserDataset` can be passed as `user_data=` as well; it carries the
`dataset_id`, a SHA-256 `digest` over the manifest and table bytes, the
generated registry mappings (`records`) and `to_dict()`.

Every step on this page also runs from a shell ([command line](cli.md)):
`fungmod check-data DIR` loads a directory and prints its gaps, genome or
proteome resolution, cultures, time courses and fitted values, or every issue as
`file:row:column: message`; `fungmod run --user-data DIR` simulates it;
`fungmod assemble`, `fungmod draft-kinetics`, `fungmod run
--compare-timecourses` and `fungmod fit` are the command-line forms of
`assemble_user_tables`, `user_tables_from_sabiork`, `compare_with_timecourses`
and `fit_user_dataset` (see [the user-data workflow from a shell](cli.md#fungus-x-on-substrate-y-at-conditions-z-from-your-sources)).

Eleven complete examples live in the test fixtures:
`tests/fixtures/user_data/esterase_case/` (a user-defined carboxylesterase on a
user-defined aryl ester, `kcat` form, estimates only),
`tests/fixtures/user_data/literature_reentry/` (the published SABIO-RK Reaction
618 selected entry typed in as literature values against the registry's
`cellobiose` and `beta_glucosidase`),
`tests/fixtures/user_data/bgl1a_ph_ionization/` (the published pH-dependent
law of SABIO-RK entry 38522, BGL1A from Tsukada et al. 2008, typed in as
literature values in the [pH-ionization form](#three-rate-forms), with design
loadings),
`tests/fixtures/user_data/oxidase_case/` (a user-defined laccase-like oxidase on
a dissolved phenolic substrate, Vmax from a specific activity and an enzyme
loading, with cardinal temperature and pH laws in `responses.csv`; estimates
only) and `tests/fixtures/user_data/genome_case/` (a strain whose enzyme
classes come only from a hand-written dbCAN overview in `genomes.csv`; a format
fixture with synthetic gene identifiers, not a real genome, and no kinetic
values, so every resolved class is a gap). `tests/fixtures/user_data/uniprot_case/`
does the same from a hand-written UniProtKB TSV export (a format fixture with
synthetic accessions, not a real proteome). `tests/fixtures/user_data/solid_case/`
is a [solid substrate](#solid-substrates): the registry's apparent hydrolysis
constants for a filter-paper activity pool re-entered as estimates on a
user-defined particulate substrate in g/L, with enzyme doses in FPU per gram
and a reactivity exponent. `tests/fixtures/user_data/culture_reentry/` and
`tests/fixtures/user_data/culture_estimates/` are
[fungal cultures](#fungal-culture-growth-and-secretion): the registry's
*T. harzianum* culture case re-entered in `culture.csv` (FungMod's
retrospective fit as estimates, the deposited initial conditions as
literature), and a user-defined strain growing on a user-defined xylan-like
solid with one protein-mass enzyme pool (estimates only).
`tests/fixtures/user_data/network_chain/` and
`tests/fixtures/user_data/network_parallel/` are
[enzyme networks](#several-enzymes-acting-together): two user-defined classes
degrading a soluble polymer-like substrate through an oligomer-like pool to a
monomer-like product, and two user-defined classes in parallel on one ester-like
substrate (kcat and Vmax forms) with competitive product inhibition of one of
them (estimates only).

To start from public kinetics instead of typing them in, draft the tables from
SABIO-RK entries and review them; see
[starting from SABIO-RK](#starting-from-sabio-rk). To ask for one fungus on
some substrates at some conditions and have FungMod gather everything it can
from your sources into one draft, see
[assembling fungus, substrate and conditions](#assembling-fungus-substrate-and-conditions).

## Assembling fungus, substrate and conditions

`assemble_user_tables` takes the request "fungus X on substrate(s) Y at
condition(s) Z" together with the sources you have, and drafts one set of the
tables described below for exactly that request. Its `review.md` and its
`assembly` report say, for every enzyme class, substrate and condition, what is
known, where it comes from and what is missing. Like the SABIO-RK route, the
result is a draft: you review it, fill its `REVIEW:` fields and load it.

```python
import fungmod as fm

draft = fm.assemble_user_tables(
    dataset_id="strain_g1_on_cellobiose",
    fungus="Genome-annotated strain G1",          # a new strain, a registry fungus, or a strain of user_data
    substrates=["cellobiose"],                    # registry substrates, user_data substrates, or ones you describe
    conditions=[
        {"temperature": 30, "temperature_units": "degC", "ph": 5},
        {"temperature": 40, "temperature_units": "degC", "ph": 5},
    ],
    annotation="path/to/overview.txt",            # the fungus's dbCAN annotation, copied into the draft
    annotation_tool="dbCAN 4.1.4",
    annotation_source="run_dbcan on the predicted proteome of assembly <accession>",
    kinetics_sources=["618"],                     # SABIO-RK sources, as user_tables_from_sabiork takes them
    entry_ids=["35622"],
    design={                                      # the virtual assay's own amounts, optional
        "substrate_initial_concentration": {"value": 10, "units": "mM"},
        "enzyme_concentration": {"value": 1e-3, "units": "mM"},
    },
    time_grid={"duration": 10, "units": "hour", "points": 61},
)
draft.write("strain_g1_on_cellobiose")  # tables, annotations/, user_dataset.yml and review.md
for case in draft.assembly["cases"]:
    print(case["enzyme_class"], case["condition"], case["kinetics_status"], case["reason"])
```

From a shell, `fungmod assemble --fungus ... --substrate ... --temperature-c
30 --temperature-c 40 --ph 5 --annotation ... --annotation-tool ...
--kinetics-source ... --entry-id 35622 --dataset-id ... --output ...` writes the
same draft and prints the per-case report, the `REVIEW:` fields and the next
commands ([command line](cli.md#fungus-x-on-substrate-y-at-conditions-z-from-your-sources)).
When a case of the draft is a `gap` or a `conflict`, the printed `fungmod
run` command carries `--runnable-only` and a line says why: once loaded, that
case's kinetic constants are explicit gaps, so the preflight blocks it, and
without the flag the whole command would simulate nothing (exit code 3).
With it the runnable cases are simulated and the gaps are listed with their
measurement requests (exit code 4, a
[partial run](concepts/outputs.md#partial-runs)); in Python the same is
`study.simulate(..., blocked="report")`.

With the hand-written annotation of the `genome_case` fixture and the frozen
Reaction 618 snapshot (`tests/test_user_data_assembly.py`), the strain has
`beta_glucosidase` (GH1, GH3), `cellobiohydrolase` (GH7),
`cellulase_generic` (GH5), `endo_xylanase` (GH10) and `glucoamylase` (GH15)
from its annotation; all but `beta_glucosidase` do not act on cellobiose and
are reported as such, and the one annotated class without a registry record
(`laccase`, AA1) is listed. At
30 degC, pH 5 the beta-glucosidase kinetics are `transferred_estimate` from
EntryID 35622, a rice enzyme. At 40 degC, pH 5 the case is a `gap`: the only
kinetics were stated at 30 degC, and once loaded, its measurement requests
read "Measure km of beta-glucosidase from Genome-annotated strain G1 on
Cellobiose at 40 degC, pH 5 (mM); kinetics.csv states kinetic constants of this
strain, enzyme class and substrate only at c30_ph5 (30 degC, pH 5), and FungMod
does not reuse kinetics measured at another condition; ...". The draft loads
once its contributor is filled in. In exploratory mode the request for both
conditions runs as a partial run (`blocked="report"`, or `--runnable-only`):
the 30 degC case is simulated and the 40 degC gap is listed as not simulated
with those requests; without the opt-in the request is refused. In scientific
mode both cases are refused, because the transferred values are estimates.

### Inputs

- `fungus`: with `user_data`, the strain of that dataset (ID, name or alias)
  whose rows are used; otherwise a registry fungus (name, alias or ID), which
  becomes a strain of its own (registry names may not be reused) whose
  record's enzyme classes count as evidence; otherwise a free-text name for a
  new strain. `scientific_name` states the species of a new strain.
- `substrates`: names, aliases or IDs of registry substrates (dissolved ones
  only), substrates of `user_data` (their rows are kept), or new substrates,
  given as a name or as a mapping with `substrate` and optionally
  `substrate_id`, `substrate_class`, `physical_state`, `bond_classes`,
  `product`, `product_yield` and `source`; what you leave out is a `REVIEW:`
  field. A mapping for a registry substrate may add `product`,
  `product_yield` and `source` only.
- `conditions`: one mapping per condition with `temperature`,
  `temperature_units` (`degC` or `kelvin`), `ph` and optionally
  `condition_id` and `notes`. Nothing is invented.
- Sources of the enzyme repertoire: `annotation` with `annotation_tool` and
  `annotation_source` (checked like a `genomes.csv` row, copied into
  `annotations/` and listed in `genomes.csv`), `enzyme_classes` you assert
  (a class name, alias, EC number or ID, or a mapping with `enzyme_class`,
  `evidence` and `source`; missing evidence or source is a `REVIEW:` field),
  the registry record of a registry fungus, and the strain's rows in
  `user_data`.
- Sources of kinetics: `user_data` (a dataset directory or a loaded
  `UserDataset`; it is loaded and checked first) and `kinetics_sources`
  (SABIO-RK, as `user_tables_from_sabiork` accepts them); `entry_ids` selects
  entries across them, and `same_species` lists SABIO-RK organism names you
  declare to be the fungus's own species.
- `responses`: response-law rows for the fungus, with the columns of
  `responses.csv` and `substrate` in place of `strain_id` and `substrate_id`.
- `design` and `time_grid`: the virtual assay's amounts
  (`substrate_initial_concentration`, `enzyme_concentration`,
  `enzyme_loading`) and the simulation time grid. Without them these are
  `REVIEW:` fields; the time grid of `user_data` is used when you give one.

### Kinetics status of a case

A case is one enzyme class of the fungus that acts on a requested substrate,
at one requested condition.

| `kinetics_status` | Source | What the draft holds |
| --- | --- | --- |
| `user_data` | Your dataset's rows for this strain, class, substrate and condition. | The rows, unchanged, with your evidence types. |
| `literature_same_organism` | One SABIO-RK entry whose organism is the fungus's species. | The entry converted exactly as `user_tables_from_sabiork` converts it (`literature`). |
| `transferred_estimate` | One SABIO-RK entry of another organism. | The same conversion, then every row that is not a design row has evidence type `estimate` and a method beginning "transferred from <organism> enzyme, SABIO-RK entry <id>". Exploratory mode only. |
| `conflict` | Several candidates of the same standing. | Nothing; all are listed. Choose one with `entry_ids`. |
| `gap` | No candidate at this condition. | No kinetic constant; `load_user_dataset` records the gaps and their measurement requests. |

Your own data takes precedence over entries of the fungus's species, which
take precedence over transfers; weaker candidates at the same condition are
listed as not used. `condition_route` says how the condition is reached:
`same_condition` (kinetics stated at it), `response_law` (carried from the
measured condition by a law, see below) or `none`. Each case in
`draft.assembly["cases"]` also gives the fungus, the class and its evidence,
the substrate, the condition, the measured condition, the source IDs and the
reason; `review.md` shows the same as tables, followed by the transfers, the
gaps, the SABIO-RK entries and what became of each, and the stored registry
cases of a registry fungus.

### Rules

- **The repertoire is evidence, never a name.** A class belongs to the fungus
  only through its genome annotation, a class you assert, its own rows in your
  dataset or its registry record. A SABIO-RK entry or a name never adds one.
- **Which classes act on a substrate** is the registry's categorical rule (the
  substrate class is one of the class's substrate classes and they share a
  bond class; `enzyme_class_acts_on`). Classes of the fungus that do not act on
  a substrate are reported with the reason. Classes that act on it without
  evidence in the fungus are reported as "no annotated gene and no user
  assertion for class C", with the SABIO-RK entries that are therefore not
  used, and they are not added.
- **A transfer stays an estimate.** Kinetics measured on another organism's
  enzyme are never labelled literature or measured for the fungus. Only you can
  change that, by editing `kinetics.csv` yourself with the evidence that
  justifies it.
- **One value per case.** Several candidates are listed and none is converted
  until `entry_ids` chooses, the rule of the SABIO-RK route.
- **No reuse across conditions.** Kinetics are never copied from the condition
  at which they were stated to another. A requested condition that differs
  from the measured one is either a `conditions.csv` row whose gaps name the
  measured condition, or, when a temperature or pH law of `responses.csv` (or
  `responses`) covers every difference, a condition you run through an
  `EnvironmentGrid`: the loader applies a law only at grid conditions, and a
  grid condition reuses a value only when the dataset states it at exactly one
  condition. A law-carried condition is therefore not a `conditions.csv` row,
  and it stays law-carried only while the draft's only rows for that class and
  substrate are its measured condition; otherwise it becomes a gap with the
  reason. The report gives the grid to run, for example
  `environment_grid(temperature_C=[40.0], ph=[5.0])`.
- **Your decisions stay yours.** The reviewer, the time grid, the enzyme
  concentration of the kcat form, an enzyme loading, a product yield that no
  source settles, a new substrate's categories and the source of an annotation
  are `REVIEW:` fields unless you give them. A case without kinetics receives
  your design substrate concentration (and your enzyme concentration when its
  pair already uses the kcat form), so its gaps are only the kinetic constants.
- **Offline and deterministic.** Nothing is fetched while assembling, and the
  same inputs give byte-identical files.

### Limits

- One fungus per call.
- Offline sources only: a dbCAN `overview.txt` file, a user dataset and
  SABIO-RK entries from a proposal, a frozen snapshot or an export; no other
  kinetics database.
- Transferred kinetics are estimates; scientific mode needs your own, or
  same-species literature, values.
- No rate, concentration, expression or secretion is taken from a genome.
- The stored registry cases of a registry fungus are listed, not copied: they
  run without the draft.
- Dissolved substrates only: a requested substrate of `user_data` that is a
  [solid substrate](#solid-substrates) is refused (the drafted tables carry no
  `amount_basis`, and no `culture.csv`: the message names a culture on that
  substrate); load such a dataset with `load_user_dataset` directly. Cultures
  of a `user_data` dataset on other substrates are not carried, like any
  substrate that was not requested.
  Everything else is as for any user dataset (below).
- From a shell, `fungmod assemble` takes the request as a grid of
  `--temperature-c` and `--ph` values in degC, substrates by name and asserted
  classes by name or with their evidence and source
  ([command line](cli.md#fungus-x-on-substrate-y-at-conditions-z-from-your-sources)); kelvin temperatures, explicit condition ids
  and notes, and the categories of a new substrate are set in the Python API
  or while reviewing the tables.

## Directory layout

| File | Required | Content |
| --- | --- | --- |
| `user_dataset.yml` | yes | Dataset id, contributor, date, source and the simulation time grid. |
| `strains.csv` | yes | One row per strain or enzyme source. |
| `enzymes.csv` | yes | Which enzyme classes each strain has, with evidence and source. |
| `enzyme_classes.csv` | no | Enzyme classes that are not in the registry. |
| `substrates.csv` | yes | One row per substrate the dataset uses, with its product and yield. |
| `conditions.csv` | yes | Assay conditions (temperature and pH). |
| `kinetics.csv` | yes | Kinetic values, one row per quantity and case. |
| `responses.csv` | no | Temperature and pH response laws bound to a strain, enzyme class and substrate. |
| `genomes.csv` | no | A dbCAN genome annotation or a UniProt proteome export per strain, from which enzyme classes are resolved. |
| annotation files | with `genomes.csv` | The dbCAN `overview.txt` files and UniProt TSV exports that `genomes.csv` names, anywhere inside the directory. |
| `timecourse.csv` | no | Measured substrate remaining and product formed over time (see [time courses](#time-courses-comparison-and-fitting)). |
| `culture.csv` | no | A strain growing on a solid substrate and secreting its enzyme pools: the roles of the registry's culture model (see [fungal culture](#fungal-culture-growth-and-secretion)). |
| `fit_report.json` | in a fitted dataset | The report of the fit that produced the dataset's `fitted` rows, named by the manifest `fit` block. |

Any other CSV file in the directory is refused as unsupported in this version
rather than ignored. Columns not listed below are refused too. Required columns are marked with an asterisk. Lists inside a cell
are separated by semicolons. Rows are reported by their spreadsheet line
number (the header is line 1).

A cell or manifest value that begins with `REVIEW:` is a field a drafted
dataset left for you to decide (see
[starting from SABIO-RK](#starting-from-sabio-rk)). Such a directory is refused
before anything else is checked, with one issue per review field naming its
file, row and column, so do not start your own text with `REVIEW:`.

### `user_dataset.yml`

```yaml
dataset_id: esterase_demo            # lowercase snake_case, required
contributor: Your Name
date: 2026-10-06                     # ISO date
source: Lab notebook LN-42, pages 10-14
simulation:                          # required; there is no default time grid
  duration: 60
  units: minute
  points: 61
```

`notes` is also accepted, and `fit` in a dataset written by `fit_user_dataset`
(see [below](#fitting-kinetic-constants-to-time-courses)). An optional
`enzyme_network` block with `entry_substrates` makes every case of the dataset
an enzyme network of all the strain's classes acting together (see
[several enzymes acting together](#several-enzymes-acting-together)). Every
generated identifier is prefixed with `<dataset_id>__`.

### `strains.csv`

Columns: `strain_id`\*, `name`\*, `scientific_name`, `aliases`.

```text
strain_id,name,scientific_name,aliases
strain_e1,Esterase source strain E1,,E1 esterase strain
```

The strain id, name and aliases become resolvable names of the strain, so they
must not already name a registry fungus and must be unique in the dataset. A
species-level `scientific_name` may match a registry record; resolving that
species name then becomes ambiguous and fails explicitly.

### `enzymes.csv`

Columns: `strain_id`\*, `enzyme_class`\*, `evidence`\*, `source`\*.

```text
strain_id,enzyme_class,evidence,source
strain_e1,carboxylesterase,activity assay,Lab notebook LN-42 p. 10
```

`enzyme_class` is either a registry enzyme class (its ID, name, alias or EC
number, resolved on the registry) or a `class_id` from `enzyme_classes.csv`.
`evidence` is free text such as "secretome proteomics" or "activity assay".
Every strain must declare at least one class, here or through its genome
annotation in `genomes.csv` (see [below](#genomescsv-optional-enzyme-classes-from-a-genome-annotation));
with a `genomes.csv` this table may hold only its header.

### `enzyme_classes.csv` (optional)

Columns: `class_id`\*, `name`\*, `ec_number`, `target_bond_classes`\*,
`compatible_substrate_classes`\*, `source`\*.

```text
class_id,name,ec_number,target_bond_classes,compatible_substrate_classes,source
carboxylesterase,carboxylesterase,3.1.1.1,carboxylic_ester,aryl_ester,Lab notebook LN-42 p. 3
```

Use it only for classes the registry does not have; an ID or name that the
registry already uses is refused. Bond and substrate classes are lowercase
snake_case.

### `substrates.csv`

Columns: `substrate_id`\*, `registry_substrate`, `name`, `substrate_class`,
`physical_state`, `bond_classes`, `amount_basis`, `product`\*,
`product_yield`\*, `yield_basis`\*, `source`\*.

```text
substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,product,product_yield,yield_basis,source
p_nitrophenyl_butyrate,,p-nitrophenyl butyrate,aryl_ester,dissolved,carboxylic_ester,p_nitrophenol,1,mol/mol,Lab notebook LN-42 p. 4
cellobiose,cellobiose,,,,,beta_D_glucose,2,mol/mol,Reaction equation of the source entry
```

- With `registry_substrate`, the registry record is referenced, not copied: the
  row supplies only the product, yield, bases and source, and the other
  descriptive columns must stay blank. The registry substrate must be
  `dissolved` or `solid_polymer` and must already list the product (the
  registry's solid polymers and their products are listed under
  [registry polymers](#registry-polymers)).
- Without it, `name`, `substrate_class`, `physical_state` and `bond_classes`
  are required, and `physical_state` must be `dissolved` or `solid_polymer`.
- A `dissolved` substrate is stated in amounts per volume: leave
  `amount_basis` blank, and `yield_basis` must be `mol/mol`.
- A `solid_polymer` substrate is one suspended polymer stated on a dry-mass
  basis: `amount_basis` must be `dry_mass` and `yield_basis` must be `g/g`
  (grams of product per gram of dry substrate consumed). See
  [solid substrates](#solid-substrates).
- The product yield is always explicit; it is never inferred, and no basis is
  converted to another.

### `conditions.csv`

Columns: `condition_id`\*, `temperature`\*, `temperature_units`\* (`degC` or
`kelvin`), `ph`\*, `notes`.

```text
condition_id,temperature,temperature_units,ph,notes
c37_ph7_5,37,degC,7.5,50 mM phosphate buffer
```

A cell may be the word `unknown`, which becomes an explicit unknown value.
Temperatures are stored in kelvin with the original value and units in the
notes; pH must lie between 0 and 14.

### `kinetics.csv`

Columns: `strain_id`\*, `enzyme_class`\*, `substrate_id`\*, `condition_id`\*,
`quantity`\*, `value`, `lower`, `upper`, `units`\*, `evidence_type`\*,
`method`, `source`\*, `sd`, `replicates`, `activity_substrate`,
`activity_saturating`, `inhibitor`.

```text
strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,km,150,,,µM,measured,initial-rate fit,LN-42 p. 12,12,3
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,kcat,,20,40,1/min,measured,initial-rate fit,LN-42 p. 12,,3
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,substrate_initial_concentration,200,,,µM,design,experimental design,LN-42 p. 11,,
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,enzyme_concentration,0.05,,,µM,design,experimental design,LN-42 p. 11,,
```

| `quantity` | Units (dimension) | Meaning |
| --- | --- | --- |
| `km` | concentration, amount per volume | Michaelis constant (positive). |
| `substrate_initial_concentration` | concentration, amount per volume | Initial substrate. |
| `kcat` | 1/time | Turnover number (kcat form). |
| `enzyme_concentration` | concentration, amount per volume | Enzyme in the simulated system (kcat form). |
| `vmax` | amount per volume per time, e.g. µM/min | Maximum rate of the simulated system itself. |
| `specific_activity` | amount per time per enzyme mass, e.g. µmol/min/mg or U/mg | Activity per mass of enzyme preparation. |
| `enzyme_loading` | enzyme mass per volume, e.g. mg/L | Enzyme preparation per volume of the simulated system. |
| `assay_activity` | amount per time per volume, e.g. U/mL | Volumetric activity in the simulated system. |
| `kcat_limiting` | 1/time | Limiting turnover of the pH-ionization form (`k0`). |
| `km_limiting` | concentration, amount per volume | Limiting Michaelis constant of the pH-ionization form (`Km0`, positive). |
| `pk_free_lower`, `pk_free_upper` | `dimensionless` | Lower and upper pK of the free enzyme (`pKe1`, `pKe2`). |
| `pk_complex_lower`, `pk_complex_upper` | `dimensionless` | Lower and upper pK of the enzyme-substrate complex (`pKes1`, `pKes2`). |
| `ph_min`, `ph_max` | `dimensionless` | The pH range the pH-ionization law was fitted over; exact values between 0 and 14. |
| `enzyme_dose` | enzyme per dry substrate mass, e.g. mg/g or FPU/g | Enzyme per substrate mass; times `substrate_initial_concentration` it gives the enzyme concentration. [Solid substrates](#solid-substrates) only. |
| `reactivity_exponent` | `dimensionless`, zero or positive | Exponent `n` of the conversion-dependent factor `(S / S0)^n`. [Solid substrates](#solid-substrates) only. |
| `ki` | concentration, amount per volume | Competitive inhibition constant of the row's process by the pool named in `inhibitor` (positive). [Enzyme networks](#competitive-product-inhibition-ki) on dissolved substrates only. |

`U` is the enzyme unit of the unit registry, one micromole per minute.
`enzyme_activity` is refused as ambiguous: say `specific_activity` or
`assay_activity`.

- Give either `value` (exact) or `lower` and `upper` (a range, sampled
  uniformly in exploratory runs).
- On a dissolved substrate the concentration rows of one case must all be
  amount per volume: a mass concentration next to a molar one would need a
  molar mass, and the mol/mol yield cannot be applied to mass concentrations
  either, so both are refused. For the same reason `vmax` and
  `assay_activity` must be amounts, not masses, per volume per time. A
  [solid substrate](#solid-substrates) has the opposite rule: dry masses only.
- `method` is required for `measured`, `literature` and `design` rows, and for
  every `vmax` row whatever its evidence type: it must say how the maximum rate
  of the simulated system was obtained.
- `sd` and `replicates` are kept in the provenance; the standard deviation is
  not turned into a sampling distribution.
- `activity_substrate` and `activity_saturating` belong to `assay_activity`
  rows only and are refused on any other row.

#### Three rate forms

A case (one strain, enzyme class, substrate and condition) uses one of three
forms of Michaelis-Menten kinetics:

- **kcat form**, `rate = kcat · E · S / (Km + S)`: `km`, `kcat`,
  `substrate_initial_concentration` and `enzyme_concentration`. The enzyme is a
  model state.
- **Vmax form**, `rate = Vmax · S / (Km + S)`: `km`, Vmax and
  `substrate_initial_concentration`. There is no enzyme state, so enzyme loss
  or dilution cannot be simulated.
- **pH-ionization form**, the diprotic law FungMod implements as the process
  law `ph_ionization_michaelis_menten` (the law of the registry's BGL1A case,
  see [environment response laws](environment-response.md)):
  `kcat_limiting`, `km_limiting`, `pk_free_lower`, `pk_free_upper`,
  `pk_complex_lower`, `pk_complex_upper`, `ph_min`, `ph_max`,
  `substrate_initial_concentration` and `enzyme_concentration`. The enzyme is a
  model state and the rate follows the pH of the environment:

  ```text
  f_e(pH)  = (10^(pk_free_lower - pH) + 1) (10^(pH - pk_free_upper) + 1)
  f_es(pH) = (10^(pk_complex_lower - pH) + 1) (10^(pH - pk_complex_upper) + 1)
  kcat(pH) = kcat_limiting / f_es(pH)
  Km(pH)   = km_limiting · f_e(pH) / f_es(pH)
  rate     = kcat(pH) · E · S / (Km(pH) + S)
  ```

  "Limiting" means the plateau constant of the fit: `kcat_limiting` is the
  turnover of the enzyme-substrate complex in its active protonation state,
  so the turnover at any pH is at most `kcat_limiting`, and `km_limiting` is
  the matching plateau Michaelis constant. Neither is the kcat or Km measured
  at one pH, so do not enter single-pH constants here (they belong to the kcat
  form), and do not enter these constants as `kcat` and `km`. The quantities
  map to the assembler's roles exactly as the registry's BGL1A records do:

  | `quantity` | Role | SABIO-RK name |
  | --- | --- | --- |
  | `kcat_limiting` | `turnover` | `k0` |
  | `km_limiting` | `michaelis_constant` | `Km0` |
  | `pk_free_lower` / `pk_free_upper` | `free_enzyme_lower_pk` / `free_enzyme_upper_pk` | `pKe1` / `pKe2` |
  | `pk_complex_lower` / `pk_complex_upper` | `complex_lower_pk` / `complex_upper_pk` | `pKes1` / `pKes2` |
  | `ph_min` / `ph_max` | `minimum_ph` / `maximum_ph` | start and end of the law's pH variable |
  | `substrate_initial_concentration` | `substrate_initial_concentration` | |
  | `enzyme_concentration` | `enzyme_initial_concentration` | |

  The re-entry of SABIO-RK entry 38522 in
  `tests/fixtures/user_data/bgl1a_ph_ionization/` reads:

  ```text
  strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,kcat_limiting,1.81,,,1/s,literature,<law constant of entry 38522>,<source>,0.05,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,km_limiting,6.8,,,mM,literature,<law constant of entry 38522>,<source>,0.29,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,pk_free_lower,4.4,,,dimensionless,literature,<law constant of entry 38522>,<source>,0.2,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,pk_free_upper,7.7,,,dimensionless,literature,<law constant of entry 38522>,<source>,0.2,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,pk_complex_lower,4.1,,,dimensionless,literature,<law constant of entry 38522>,<source>,0.1,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,pk_complex_upper,7.6,,,dimensionless,literature,<law constant of entry 38522>,<source>,0.1,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,ph_min,4,,,dimensionless,literature,<lower end of the pH series>,<source>,,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,ph_max,8,,,dimensionless,literature,<upper end of the pH series>,<source>,,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,substrate_initial_concentration,5,,,mM,design,experimental design,<design note>,,
  bgl1a_source,beta_glucosidase,cellobiose,c30_ph5,enzyme_concentration,0.001,,,mM,design,experimental design,<design note>,,
  ```

  With the registry case's loadings it gives the same substrate trajectory as
  the registry BGL1A case in the Tsukada pH 5 assay, and an `EnvironmentGrid`
  over pH 4 to 8 gives initial rates in the ratios of the law's factors
  (`tests/test_user_data_ph_ionization.py`). The condition's temperature is the
  temperature the law was fitted at; its pH is the pH the case runs at.

  Checks: the pK values are finite numbers in `dimensionless`; each lower pK
  lies below its upper pK (for ranges, the whole lower range below the whole
  upper range, so that every sampled pair is ordered); `ph_min` and `ph_max`
  are exact, between 0 and 14, with `ph_min < ph_max`; and every condition with
  pH-ionization rows has one exact pH inside `[ph_min, ph_max]`. An `unknown`
  pH or a pH outside the fitted range is refused on its `conditions.csv` row
  with the reason, and a pH range is never a condition (`ph` takes one number
  or `unknown`). In an `EnvironmentGrid` a grid pH outside the range is not
  refused: the law runs with an `EnvironmentalValidityWarning`, as the
  registry case does. `kcat_limiting` and `km_limiting` may be ranges for
  exploratory sampling.

A case that gives `kcat` or `enzyme_concentration` together with any Vmax row
is refused; FungMod never derives one form from the other. A case that gives
any pH-ionization quantity together with `kcat` or a Vmax row is refused too
(its `enzyme_concentration` belongs to whichever of the kcat and pH-ionization
forms the case uses). All strains and conditions of one enzyme class and
substrate share one generated process, so they must use the same form; a
dataset where one strain uses `kcat` and another `vmax`, or the pH-ionization
form, on the same pair is refused. A generated enzyme class lists the process
law it runs and preflight looks for that law on every substrate of the class,
so a class uses the pH-ionization form on all of its substrates or on none: a
class with the pH-ionization form on one substrate and the kcat or Vmax form on
another is refused. A pair without any rate row is generated in the kcat form,
and its gap requests name both forms (see below); when its class uses the
pH-ionization form on its other substrates, it is generated in that form
instead.

#### Three routes to Vmax

Vmax for a case comes from exactly one route; rows of two routes in one case
are refused. On a [solid substrate](#solid-substrates) only the first route,
an explicit `vmax` row, is accepted.

1. **An explicit `vmax` row**, a rate for the simulated system itself, with a
   `method` saying how it was obtained. Refused without a method or in mass
   units.
2. **`specific_activity` × `enzyme_loading`.** FungMod multiplies the two with
   pint (for example 12 µmol/min/mg × 0.05 mg/L = 0.6 µmol/(L·min) = 0.6 µM/min)
   and writes one derived parameter record for the Vmax role. Its provenance
   lists both source rows (value or range, units, evidence type, source,
   method), the formula and the unit conversion; the two rows produce no records
   of their own. Its maturity is the weaker of the two inputs (see the ordering
   below). When one input is a range and the other exact, the derived value is
   the range scaled by the exact value, which is again a uniform range; two
   ranges are refused because their product is not uniform. With only one of
   the two rows, the Vmax role is a gap whose request names the missing row.
3. **A saturating `assay_activity` on the case substrate.** Accepted only when
   the row states `activity_substrate` equal to the row's `substrate_id` and
   `activity_saturating` = `yes`; the record keeps the assay units and the
   route in provenance. An activity measured on another substrate (for example
   a chromogenic model substrate instead of the case substrate) is refused, and
   so is an activity with `activity_saturating` = `no` or blank: neither is the
   Vmax on this substrate, and FungMod does not convert activities between
   substrates or extrapolate a sub-saturating rate. The activity is read as the
   activity per volume of the simulated system; dilute a stock-solution
   activity yourself and say so in `method`.

### `responses.csv` (optional)

Columns: `strain_id`\*, `enzyme_class`\*, `substrate_id`\*, `law`\*,
`parameter`\*, `value`\*, `units`\*, `evidence_type`\* (`measured`,
`literature` or `estimate`), `method`, `source`\*, `reference_tolerance`,
`kinetics_at_reference`.

Each row binds one parameter of one existing environment-response law to a
strain, enzyme class and substrate. The law enters the generated case template
as a process modifier, the same mechanism registry templates use, so a
temperature or pH grid changes the rate through the law and the result tables
report `environment_effect_status = active_response_model`.

```text
strain_id,enzyme_class,substrate_id,law,parameter,value,units,evidence_type,method,source,reference_tolerance,kinetics_at_reference
strain_l1,laccase_like_oxidase,syringaldazine_like,temperature_cardinal_rosso,minimum_temperature,10,degC,estimate,,Lab notebook LN-7 p. 3,,
strain_l1,laccase_like_oxidase,syringaldazine_like,temperature_cardinal_rosso,optimum_temperature,50,degC,estimate,,Lab notebook LN-7 p. 3,,
strain_l1,laccase_like_oxidase,syringaldazine_like,temperature_cardinal_rosso,maximum_temperature,70,degC,estimate,,Lab notebook LN-7 p. 3,,
strain_l1,laccase_like_oxidase,syringaldazine_like,ph_cardinal_rosso,minimum_ph,3,dimensionless,estimate,,Lab notebook LN-7 p. 4,,
strain_l1,laccase_like_oxidase,syringaldazine_like,ph_cardinal_rosso,optimum_ph,5,dimensionless,estimate,,Lab notebook LN-7 p. 4,,
strain_l1,laccase_like_oxidase,syringaldazine_like,ph_cardinal_rosso,maximum_ph,8,dimensionless,estimate,,Lab notebook LN-7 p. 4,,
```

| `law` | Parameters | Reference parameter | Rate law |
| --- | --- | --- | --- |
| `temperature_cardinal_rosso` | `minimum_temperature`, `optimum_temperature`, `maximum_temperature` (temperatures) | `optimum_temperature` | rate(T) = rate(T_opt) · γ_T(T), Rosso CTMI |
| `ph_cardinal_rosso` | `minimum_ph`, `optimum_ph`, `maximum_ph` (`dimensionless`) | `optimum_ph` | rate(pH) = rate(pH_opt) · γ_pH(pH), Rosso CPM |
| `temperature_arrhenius_reference` | `activation_energy` (energy per amount, e.g. kJ/mol), `reference_temperature` | `reference_temperature` | rate(T) = rate(T_ref) · exp(−Ea/R · (1/T − 1/T_ref)) |

The laws are the implemented modifiers described in
[environment response laws](environment-response.md); a law name FungMod does
not implement is refused, and so are implemented laws this importer does not
bind yet (Gaussian pH, oxygen, water activity) and the optional validity bounds
of the Arrhenius law. On a pair in the pH-ionization form a pH law is refused
as double-counting, because the ionization law already makes the rate depend on
pH; a temperature law binds as usual. Validation:

- Every parameter the law needs is present exactly once, with the right
  dimension (temperatures in `degC` or `kelvin`, pH as `dimensionless`
  between 0 and 14, activation energy as energy per amount).
- The values lie in the law's own domain, checked by evaluating the
  implemented law: cardinal laws need minimum < optimum < maximum, and the
  cardinal temperature law also needs the optimum at or above the midpoint of
  the minimum and maximum.
- One law per condition for a strain, class and substrate (a cardinal
  temperature law and an Arrhenius law would both rescale the same rate), and
  the same law for a condition across the strains of one enzyme class and
  substrate, which share one template.
- `design` is not an evidence type for a response law.

Temperatures are stored in kelvin with the original value in the notes. The
law's records apply at every environment of the case (their `environment_id`
is empty), including runtime grid environments.

#### Reference condition

The law multiplies the configured rate by an activity that is one at its
reference parameter: the optimum of a cardinal law, the reference temperature
of the Arrhenius law. The law therefore rescales the reference value, and the
kinetic constants of that strain, enzyme class and substrate (`km`, `kcat`,
`vmax`, `specific_activity`, `assay_activity`, `kcat_limiting`, `km_limiting`)
must be stated at the reference condition. For every condition at which such rows exist, the condition's
temperature or pH must equal the reference parameter exactly, or lie within
the `reference_tolerance` stated on the reference parameter's row (a
nonnegative number in that row's units; FungMod has no tolerance of its own).
Alternatively `kinetics_at_reference = yes` on that row declares that the
kinetic values are already reference values (for example rates normalised to
the optimum); the declaration is recorded in provenance and not checked. A
condition with an unknown temperature or pH cannot carry kinetic constants for
a law on that condition. Otherwise the dataset is refused with a message
naming the condition, the reference value and the difference. Concentrations
and `enzyme_loading` are amounts, not rates, and are not checked or rescaled;
nor are the pK values and the fitted pH range of the pH-ionization form.

### `genomes.csv` (optional): enzyme classes from a genome annotation

Columns: `strain_id`\*, `annotation_file`\*, `annotation_tool`\*, `source`\*,
`min_tools_agreeing`.

```text
strain_id,annotation_file,annotation_tool,source
strain_g1,annotations/strain_g1_overview.txt,dbCAN 4.1.4,"run_dbcan on the predicted proteome of assembly <accession>, 2026-09-30"
```

A row may instead point to a UniProtKB TSV export of the strain's proteome;
see [From a UniProt proteome](#from-a-uniprot-proteome). The rest of this
section describes dbCAN rows.

Instead of (or besides) listing a strain's enzyme classes by hand, point it to
the dbCAN annotation of its genome or proteome. FungMod resolves the
annotation to enzyme classes with its existing capability resolver and curated
CAZy family map (`data_registry/cazyme_families/cazyme_family_map.yml`). A
genome states which classes a strain can encode, never a rate: no kinetic
constant, enzyme concentration, expression level or secretion is taken from
it, and every resolved class that can act on a dataset substrate but has no
kinetics becomes the explicit gaps described
[below](#gaps-and-measurement-requests).

- `annotation_file` is a path relative to the dataset directory, separated by
  `/`, to a dbCAN `overview.txt`: tab-separated, with the column `Gene ID` and
  at least one of the tool columns `HMMER`, `dbCAN_sub`, `DIAMOND`, `eCAMI` and
  `Hotpep` (other columns such as `EC#` and `#ofTools` are not read). Absolute
  paths, paths with `..` and paths that leave the directory through a symbolic
  link are refused, and so are a missing file, a header without `Gene ID` or a
  tool column, a repeated gene identifier and a file without any family call.
  The file's bytes enter the dataset `digest` and `file_digests` (under its
  relative path), so changing the annotation changes the digest.
- `annotation_tool` is `dbCAN` (or `dbCAN3`, `run_dbcan`) followed by the
  version you ran, which is recorded as written; the overview file does not
  record the version, so a tool without one is refused. Other annotation
  tools are refused.
- `source` says which genome or proteome was annotated, ideally with its
  accession and the run.
- One row per strain; the strain must be in `strains.csv`.

**Families and the consensus rule.** Each tool cell is read as in
`fungal_model.capability.families_from_overview`: subfamily suffixes and
residue ranges are dropped (`GH5_5(35-320)` counts as `GH5`). With
`min_tools_agreeing` blank, a family counts for a gene when any tool column
calls it, which is the existing rule of that function; FungMod has no
multi-tool threshold of its own and does not choose one for you. With
`min_tools_agreeing` = *m*, a family counts for a gene only when at least *m*
of the tool columns present call it for that gene; *m* must be a positive
integer no larger than the number of tool columns in the file. The gene count
of a family or class is the number of genes that carry it under the rule.

**Three outcomes.** The resolver maps families to classes and labels a class
`family_diagnostic` when any supporting family is diagnostic, otherwise
`family_polyspecific` (a candidate capability). Then:

1. *A resolved class with a record in the base registry* joins the strain's
   declared classes, exactly as if `enzymes.csv` had listed it, with the
   evidence `genome annotation (dbCAN, 3 genes, families GH1, GH3)` and the
   row's source. If `enzymes.csv` already declares that class for the strain,
   the explicit row wins and the genome evidence is recorded beside it; both
   appear in the fungus record under
   `provenance.enzyme_class_evidence.<class>` (the annotation under
   `genome_annotation`, with the file digest, the families, the gene
   identifiers and the consensus rule).
2. *A resolved class without a registry record* is listed in
   `unmodellable_enzyme_classes` (class, families, gene count, specificity and
   the reason). No enzyme-class record, case or gap is generated for it.
3. *A family the map assigns to no class* is listed in `unmapped_families`.

`kinetics.csv` and `responses.csv` rows may name a class the annotation
declared; the case then behaves like any other. A strain whose `enzymes.csv`
rows are absent and whose annotation resolves no class with a registry record
is refused with the classes found and the unmapped families.

The gap requests of a class that only the annotation declares say so:

> Measure km of beta-glucosidase from Genome-annotated strain G1 on Cellobiose
> at 30 degC, pH 5.0 (concentration units); the class was inferred from the
> dbCAN annotation (families GH1, GH3; family membership is polyspecific, so
> the activity itself needs confirming).

Such a class reaches scientific mode only through kinetics you supply: with
the annotation alone its roles are `user_dataset_gap` unknowns, preflight is
`underparameterized` in both modes, and simulation is refused.

`UserDataset.genome_annotations` (file, digest, tool and version, tool columns,
consensus rule, gene rows, family gene counts and the family map's digest and
sources), `genome_resolved_classes`, `unmodellable_enzyme_classes` and
`unmapped_families` appear in `UserDataset.to_dict()` and
`UserDataset.summary()` and are empty without a `genomes.csv`.

Limits of the genome route:

- A dbCAN row reads a dbCAN `overview.txt` from the dataset directory; the
  only other format is a UniProtKB TSV export ([below](#from-a-uniprot-proteome)),
  and nothing is downloaded at run time.
- Family-level mapping: the curated map covers 18 CAZy families, a
  polyspecific family gives only a candidate class, and the `EC#` column is not
  used. With the shipped registry, six of the thirteen mapped classes have a
  record (`beta_glucosidase`, `cellobiohydrolase`, `cellulase_generic`,
  `endo_xylanase`, `glucoamylase` and `chitinase`); LPMO, cellobiose
  dehydrogenase, acetyl xylan esterase, laccase, class II peroxidase,
  alpha-amylase and pectate lyase are reported as unmodellable. The
  resolver's `require_diagnostic` filter is not exposed.
- `cellobiohydrolase` (GH6, GH7) is a categorical record without kinetics
  (EC 3.2.1.91, with the reducing-end EC 3.2.1.176 as an alias) whose
  substrate classes are the registry's insoluble cellulose classes
  (`cellulose_particulate`, `cellulose_film_generic`). It joins the strain, and
  on a [solid substrate](#solid-substrates) of such a class its roles are gaps
  whose requests ask for dry-mass units, for example "Measure km of
  Cellobiohydrolase from Genome-annotated strain G1 on Particulate cellulose
  lot G at 30 degC, pH 5.0 (dry mass per volume, for example g/L); the class
  was inferred from the dbCAN annotation (families GH7)." It acts on no
  dissolved substrate. Endoglucanase and LPMO have no record: GH5, GH12 and
  GH45 still map to `cellulase_generic`, and AA9 to an LPMO class without a
  record (no oxidative rate law exists).
- `endo_xylanase` (GH10, GH11; EC 3.2.1.8), `glucoamylase` (GH15; EC 3.2.1.3)
  and `chitinase` (GH18; EC 3.2.1.14) are categorical records without kinetics
  (REGISTRY-002) acting on the registry polymers `xylan`, `starch` and
  `chitin` ([registry polymers](#registry-polymers)). They join the strain,
  and on a dataset substrate that references such a polymer their roles are
  gaps with dry-mass requests. They act on no dissolved substrate.
- Gene counts are annotated genes, not active enzymes, copy numbers or
  expression.
- The test fixture is a format fixture written by hand; no real genome
  annotation is bundled.

### From a UniProt proteome

Most fungi with a sequenced genome have a UniProt proteome whose entries carry
EC numbers and CAZy cross-references. A `genomes.csv` row can point to a
UniProtKB TSV export of that proteome instead of a dbCAN overview, so no
annotation tool has to be run:

```text
strain_id,annotation_file,annotation_tool,source
strain_u1,annotations/strain_u1_uniprot.tsv,UniProt 2026_03,"UniProt proteome UP000xxxxxx, all UniProtKB entries, downloaded 2026-10-01"
```

**Downloading the export.** On uniprot.org, find the organism's proteome
(Proteomes, search the organism, open the reference proteome and note its
`UP...` identifier), then list its UniProtKB entries (the query
`proteome:UP000xxxxxx`). Choose *Download*, format *TSV*, *Compressed: No*,
and customise the columns so that the export holds at least `Entry` and one of
`EC number` and `CAZy`; FungMod also reads `Entry Name`, `Protein names`,
`Gene Names`, `Organism`, `Organism (ID)` and `Reviewed`, and these are
worth selecting. The column names are UniProt's own; where each sits in the
website's column picker may change (the CAZy column is among the
cross-references to protein family databases). Any other column is allowed and
ignored; its name is listed under `ignored_columns`. Save the file inside the
dataset directory.

**The row.**

- `annotation_tool` is `UniProt` (or `UniProtKB`) followed by the UniProt
  release (for example `2026_03`, shown on the website and in the
  `X-UniProt-Release` header) or the download date, recorded as written. The
  export does not record either, so a row without one is refused.
- `annotation_file` follows the path rules of a dbCAN row: relative to the
  dataset directory, `/`-separated, no absolute path, no `..`, no symbolic link
  out of the directory. The file's bytes enter the dataset `digest` and
  `file_digests`, so changing any byte (even in an ignored column) changes the
  digest.
- `source` says which proteome was exported. When it names one UniProt
  proteome identifier (`UP` followed by digits) that identifier is recorded as
  `proteome_id` and named in the measurement requests; a `source` naming
  several identifiers is refused. Without one, requests name the export file.
- `min_tools_agreeing` counts agreeing dbCAN tool columns; a UniProt export has
  none, so a value on a UniProt row is refused.

**Reading the export.** `Entry` is required and must be unique; the format of
an accession is not checked. `EC number` cells hold EC numbers separated by
`"; "`; a partial number such as `3.2.1.-` is kept as partial and never
completed or resolved. `CAZy` cells hold family identifiers separated by `;`,
usually with a trailing `;`; a subfamily suffix is dropped as in the dbCAN
route (`GH5_5` counts as `GH5`). An export must describe one organism: more
than one `Organism (ID)` (or, without that column, more than one `Organism`)
is refused, because mixed sets are not supported. Also refused: a header
without `Entry` or without both `EC number` and `CAZy`, a repeated header
column, a malformed EC number or CAZy identifier, a `Reviewed` cell other than
`reviewed` or `unreviewed`, a gzip-compressed file and an export in which no
entry has an EC number or a CAZy family.

**Resolution.** Nothing new decides a class. The CAZy families of each
protein go through the same `CapabilityResolver` and curated family map as a
dbCAN annotation; each complete EC number goes through the registry's enzyme
class lookup (`RegistryResolver.resolve_enzyme_class`, which matches the
`ec_number` or an alias of a registry record), so an EC number resolves only
to a class with a registry record. An EC number no record carries is listed under
`unresolved_ec_numbers`; one that two records carry is listed there as
ambiguous, and FungMod picks neither.

**When CAZy and EC disagree.** For a protein that has a mapped CAZy family
and a complete EC number, FungMod compares the classes its families name with
the classes its EC numbers resolve to, on every class the EC side can speak
about: the classes its EC numbers resolve to and every registry class whose
record carries an EC number. The two disagree when such a class is named by
one side and not by the other. A disagreeing protein supports **no** class:
it is listed under `ec_cazy_disagreements` with both sides (families and the
classes they name, EC numbers and the classes they resolve to, and the
contested classes), and FungMod does not choose between them. With the
shipped registry, a GH7 protein annotated EC 3.2.1.21 (GH7 names
cellobiohydrolase, the EC number beta-glucosidase; both classes are contested)
and a GH3 protein annotated EC 3.2.1.37 only (GH3 names beta-glucosidase,
whose record carries EC 3.2.1.21) both disagree, while a GH7 protein annotated
EC 3.2.1.91 agrees on `cellobiohydrolase` and a GH11 protein annotated
EC 3.2.1.8 on `endo_xylanase`. A protein whose EC numbers resolve to nothing
and whose family classes carry no registry EC number cannot be compared: its
family classes count, and its EC numbers are listed as unresolved. Every
other protein supports the classes its families or EC numbers name, and each
class records which accessions support it through both annotations
(`cazy_and_ec`), the families only (`cazy`) or the EC numbers only (`ec`).

**Outcomes.** As for a dbCAN row: a class with a registry record joins the
strain (an explicit `enzymes.csv` row wins and keeps the proteome evidence
beside it), a class without one is listed in `unmodellable_enzyme_classes`
and generates nothing, and a family without a class is listed in
`unmapped_families`. A class that only EC numbers support has no family
specificity (`specificity` is `null`). No rate, kinetic constant, enzyme
concentration or expression level is taken from the proteome: every resolved
class that can act on a dataset substrate but has no kinetics becomes
`user_dataset_gap` unknowns whose requests name the evidence:

> Measure km of beta-glucosidase from Proteome-annotated strain U1 on
> Cellobiose at 30 degC, pH 5.0 (concentration units); the class was inferred
> from UniProt proteome UP000000000 (accessions X0TEST01, X0TEST02, X0TEST03;
> CAZy families GH1, GH3; EC 3.2.1.21; 1 of 3 reviewed in Swiss-Prot; family
> membership is polyspecific, so the activity itself needs confirming).

A request quotes at most ten accessions and says how many more there are; the
provenance lists all. Preflight is `underparameterized` and scientific and
exploratory simulation are refused for such a class until kinetics are
supplied, exactly as for a dbCAN class.

**Outputs.** Every entry a UniProt row adds to `genome_annotations`,
`genome_resolved_classes`, `unmodellable_enzyme_classes` and
`unmapped_families` (and so to `virtual_experiment_summary.json` and
`user_dataset_genome_resolution.json`) carries `source_type`
`uniprot_proteome` and the accessions behind it (`accessions`,
`accession_count`; classes also `accessions_by_basis`, `reviewed_accessions`
and `ec_numbers`). Its `genome_annotations` entry adds the `proteome_id`,
organism and taxonomy id, the columns read and ignored, `review_counts`,
`protein_counts` (agreeing, CAZy only, EC only, disagreement, no class),
`unresolved_ec_numbers`, `partial_ec_numbers`, `ec_cazy_disagreements`,
`ec_comparable_classes` and the comparison rule. Entries of a dbCAN row keep
exactly their earlier keys (no `source_type`); a dataset may mix both kinds of
rows, one per strain.

**Fetching an export on request.** `fungal_model.sources.uniprot` builds the
UniProt REST stream URL for a proteome identifier or an NCBI taxonomy id and
fetches it only when you pass `refresh=True`:

```python
from fungal_model.sources.uniprot import fetch_proteome_snapshot, write_snapshot_to_user_dataset

snapshot = fetch_proteome_snapshot(proteome_id="UP000xxxxxx", refresh=True)
# https://rest.uniprot.org/uniprotkb/stream?query=(proteome:UP000xxxxxx)
#   &fields=accession,id,protein_name,gene_names,organism_name,organism_id,ec,xref_cazy,reviewed&format=tsv
row = write_snapshot_to_user_dataset(snapshot, "path/to/my_dataset", strain_id="strain_u1")
# row: a genomes.csv row to review and add yourself (genomes.csv is not written)
```

The response is parsed before it is stored; it is frozen under
`data/source_snapshots/uniprot/<query>/` (by default) as `uniprotkb.tsv` with
`snapshot.json` (SHA-256, URL, query, retrieval time, HTTP status and the
`X-UniProt-Release` and `X-UniProt-Release-Date` headers when sent). Without
`refresh=True` only that snapshot is read and its digest verified; a missing
or changed snapshot is refused. A new response whose digest differs from the
stored one is refused unless you pass `overwrite=True`. A taxonomy id query
(`organism_id:<id>`) returns every UniProtKB entry of that organism, which may
be more than its reference proteome. There is no lookup from a free-text
organism name to a proteome: choosing the proteome is left to you (possible
future work, which would show candidates rather than guess). The URL and the
return-field names follow UniProt's REST documentation as known when the
client was written; they were not checked against a live response in the
environment it was written in, which could not reach rest.uniprot.org.

Limits of the UniProt route:

- UniProtKB annotation is mostly automatic: unreviewed (TrEMBL) entries carry
  EC numbers and names assigned by prediction rules. `Reviewed` is reported
  per class and in each request, never used to filter.
- A protein in the proteome is not an expressed or secreted enzyme, and the
  number of accessions is not a copy number or an activity.
- CAZy cross-references cover only part of a proteome; a protein without one
  can still be a CAZyme. An export without CAZy cross-references resolves
  through EC numbers alone.
- EC numbers resolve only to registry classes that carry an EC number or list
  it as an alias (with the shipped registry, `beta_glucosidase`, EC 3.2.1.21;
  `cellobiohydrolase`, EC 3.2.1.91 and 3.2.1.176; `endo_xylanase`, EC 3.2.1.8;
  `glucoamylase`, EC 3.2.1.3; and `chitinase`, EC 3.2.1.14; no EC number is
  carried by two classes), so most EC numbers are listed as unresolved, and an
  EC number can contradict a family only through such a class. A GH7 protein
  annotated EC 3.2.1.4 (an endoglucanase I) therefore disagrees with the GH7
  family call.
- One organism per export; no merging of proteomes or strains.

## Solid substrates

A substrate can be one suspended solid polymer, for example a particulate
polysaccharide, stated on a dry-mass basis. The homogeneous Michaelis-Menten
process law then runs as an **apparent** bulk saturation law on the dry mass
per volume:

```text
kcat form:  rate = kcat · E · S / (Km + S)
Vmax form:  rate = Vmax · S / (Km + S)
optional:   rate × (S / S0)^n          (reactivity_exponent n, S0 the case's initial substrate)
```

`S` is the dry mass of the solid per volume, `E` the enzyme as a protein mass
or an assay activity per volume, `Km` an apparent half-saturation constant in
dry mass per volume. This is the law of the registry's culture-physiology case
(cellulose consumption `k_h F S / (K_h + S)` with filter-paper activity `F`),
now reachable from your own tables. It is an effective law: `Km` is not a
binding constant, and `kcat`, `Vmax` and `Km` hold for the substrate
preparation and the enzyme and solids loadings at which they were measured.

### Declaring a solid substrate

In `substrates.csv`, a solid substrate has `physical_state` `solid_polymer`,
`amount_basis` `dry_mass` and `yield_basis` `g/g`; the yield is grams of
product per gram of dry substrate consumed, stated by you. A registry
substrate whose record is `solid_polymer` is referenced the same way (the row
gives `amount_basis`, the product, the yield and the source); see
[registry polymers](#registry-polymers).

### Units

| `quantity` | On a solid substrate | Example |
| --- | --- | --- |
| `km`, `substrate_initial_concentration` | dry mass per volume | `g/L` |
| `enzyme_concentration` | protein mass per volume, or an activity per volume in one of the registry's assay units (`filter_paper_unit`, `FPU`; `beta_glucosidase_assay_unit`, `BGU`) | `mg/L`, `FPU/L` |
| `kcat` | substrate mass per time per enzyme amount | `g/(mg*h)` (which is 1/time), `g/FPU/h` |
| `vmax` | dry mass per volume per time | `g/L/h` |
| `enzyme_dose` | enzyme per dry substrate mass | `mg/g`, `FPU/g` |
| `reactivity_exponent` | `dimensionless`, zero or positive | `1` |

The units of `kcat` are checked per case with pint against the case's own
enzyme and substrate rows: `kcat × E` must be the substrate's mass per volume
per time. `kcat` in `g/(mg*h)` with an enzyme in `FPU/L`, or in `g/FPU/h`
with an enzyme in `mg/L`, is refused on the `kcat` row. An assay unit is never
converted to protein mass or molarity, and no molar mass, hydration factor or
monomer equivalent is applied anywhere.

### Worked example

`tests/fixtures/user_data/solid_case/` re-enters the registry's apparent
hydrolysis constants (`gelain_hydrolysis_k_h_calibrated` and
`gelain_hydrolysis_Kh_calibrated`, a FungMod retrospective fit for
*T. harzianum* P49P11 on Celufloc 200) as estimates on a user-defined
particulate substrate, at two enzyme doses with the same temperature and pH:

```text
substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,amount_basis,product,product_yield,yield_basis,source
particulate_lot_p1,,Particulate cellulose lot P1,cellulose_particulate,solid_polymer,beta_1_4_glycosidic,dry_mass,solubilized_substrate_mass,1,g/g,<source>
```

```text
strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates
strain_p1,cellulase_total_filter_paper_activity,particulate_lot_p1,dose_5,km,16.726013979440346,,,g/L,estimate,re-entered registry value (retrospective fit),<source>,,
strain_p1,cellulase_total_filter_paper_activity,particulate_lot_p1,dose_5,kcat,0.018378579847405995,,,g/FPU/h,estimate,re-entered registry value (retrospective fit),<source>,,
strain_p1,cellulase_total_filter_paper_activity,particulate_lot_p1,dose_5,substrate_initial_concentration,20,,,g/L,design,experimental design,<source>,,
strain_p1,cellulase_total_filter_paper_activity,particulate_lot_p1,dose_5,enzyme_dose,5,,,FPU/g,design,experimental design,<source>,,
strain_p1,cellulase_total_filter_paper_activity,particulate_lot_p1,dose_5,reactivity_exponent,1,,,dimensionless,estimate,assumed linear substrate reactivity factor (Kadam et al. 2004); not measured for this lot,<source>,,
```

(and the same rows at `dose_1_25` with an enzyme dose of 1.25 FPU/g).

```python
import fungmod as fm

dataset = fm.load_user_dataset("tests/fixtures/user_data/solid_case")
study = fm.virtual_experiment(
    fungi="strain_p1",
    substrates="particulate_lot_p1",
    environments=["dose_5", "dose_1_25"],
    user_data=dataset,
)
result = study.simulate(mode="exploratory", n_samples=1)
```

The doses give enzyme concentrations of 100 and 25 FPU/L, each one derived
record. The case runs in exploratory mode only, because the constants are a
fit typed in as estimates (scientific mode refuses it). Without the
reactivity rows, the trajectory at 100 FPU/L equals the registry
culture-physiology case's cellulose trajectory with the same constants when its
enzyme synthesis and loss are switched off (`value_overrides`) and its
filter-paper activity is set to 100 FPU/L, and both equal the integrated law
`Km ln(S0/S) + (S0 - S) = kcat E t`, solved with the Lambert W function. With
`n = 1` the time to reach `S` is `(S0 / (kcat E)) (Km (1/S - 1/S0) + ln(S0/S))`
(`tests/test_user_data_solid_substrates.py`).

### Registry polymers

Instead of describing a solid yourself, you can reference a registry substrate
whose record is `solid_polymer`. Since REGISTRY-002 the registry holds three
generic polysaccharides, each with one registry enzyme class acting on it
(categorical metadata from the IUBMB nomenclature and the CAZy families; no
kinetic value):

| Registry substrate | Bond classes | Declared product | Complete-hydrolysis yield (product map) | Registry class acting on it |
| --- | --- | --- | --- | --- |
| `xylan` | `beta_1_4_xylosidic` | `D_xylose_equivalent` | 1.136358 g/g (`xylan_to_d_xylose_equivalent_mass_yield`) | `endo_xylanase` (EC 3.2.1.8; GH10, GH11) |
| `starch` | `alpha_1_4_glycosidic`, `alpha_1_6_glycosidic` | `beta_D_glucose` | 1.111107 g/g (`starch_to_beta_d_glucose_mass_yield`) | `glucoamylase` (EC 3.2.1.3; GH15) |
| `chitin` | `beta_1_4_n_acetylglucosaminidic` | `N_acetyl_D_glucosamine_equivalent` | 1.088659 g/g (`chitin_to_n_acetyl_d_glucosamine_equivalent_mass_yield`) | `chitinase` (EC 3.2.1.14; GH18) |

The insoluble cellulose `cellulose_film_generic` can be referenced the same
way (product `soluble_cellulose_hydrolysis_product`); `cellulose_celufloc_200`
declares no product, so a row cannot reference it. The names, aliases and EC
numbers of the classes resolve in `enzymes.csv` and `kinetics.csv` (for
example `xylanase`, `EC 3.2.1.8`, `amyloglucosidase`, `endochitinase`).

What the records say, and what they do not:

- **Products.** An endo-xylanase releases mainly xylo-oligosaccharides and a
  chitinase mainly chitobiose and chito-oligosaccharides, so `xylan` and
  `chitin` declare **monomer equivalents**: the mass of D-xylose or
  N-acetyl-D-glucosamine that the solubilized polymer gives on complete
  hydrolysis (for example measured by HPLC after acid post-hydrolysis), not
  free monomer and not a reducing-sugar (DNS) equivalent. Glucoamylase
  releases beta-D-glucose from the non-reducing chain ends, so `starch`
  declares `beta_D_glucose`. A row naming another product (`D_xylose`, say) is
  refused with the declared one.
- **Yields.** Each product map is the theoretical mass yield of the idealized
  homopolymer, `M(monomer) / M(monomer - H2O)` from the conventional atomic
  weights (C 12.011, H 1.008, N 14.007, O 15.999), in the limit of a high
  degree of polymerization; the formula is in its provenance. The yield in
  `substrates.csv` is still yours: FungMod neither fills it from the map nor
  checks it against it. Side chains of a real xylan, the lipid and protein of
  a starch and the deacetylated units of a chitin change the true yield.
- **Composition.** The substrate records are generic definitions
  (`exploratory_metadata`): composition varies by source (xylan
  substitution, the amylose/amylopectin ratio and gelatinization of starch,
  the acetylation and polymorph of chitin) and none of it is recorded. The
  starch bond classes are categorical: a case neither weights the (1->4) and
  (1->6) bonds nor resolves branch points, and starch is one bulk dry mass.
- **Classes.** A chitinase found in a fungal genome may serve cell-wall
  remodelling rather than nutrition; it is a candidate capability on an
  external chitin. The classes list only the solid polymer, not dissolved
  oligosaccharides.

A dataset written by `tests/test_registry_polysaccharide_classes.py` (strain,
condition and illustrative estimates, not measurements) references `xylan`:

```text
substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,amount_basis,product,product_yield,yield_basis,source
xylan,xylan,,,,,dry_mass,D_xylose_equivalent,1.136358,g/g,Complete-hydrolysis mass yield of registry product map xylan_to_d_xylose_equivalent_mass_yield
```

```text
strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates
strain_p2,endo_xylanase,xylan,c40_ph5,km,8.0,,,g/L,estimate,,LN-21 p. 2 (illustrative),,
strain_p2,endo_xylanase,xylan,c40_ph5,kcat,0.6,,,g/(mg*h),estimate,,LN-21 p. 2 (illustrative),,
strain_p2,endo_xylanase,xylan,c40_ph5,substrate_initial_concentration,10.0,,,g/L,design,experimental design,LN-21 p. 3,,
strain_p2,endo_xylanase,xylan,c40_ph5,enzyme_concentration,0.5,,,mg/L,design,experimental design,LN-21 p. 3,,
```

with `enzymes.csv` declaring the class as `EC 3.2.1.8`. The case runs in
exploratory mode only (the constants are estimates), the xylan trajectory
equals the integrated law with `Vmax = kcat E` = 0.3 g/L/h, and the product is
`1.136358 (S0 - S)` g/L at every time point. The same test runs starch with
glucoamylase and chitin with chitinase. From a genome or proteome, GH10, GH11,
GH15 and GH18 (or EC 3.2.1.8, 3.2.1.3 and 3.2.1.14) give these classes, and on
a dataset that references the polymer their roles are gaps with dry-mass
requests, for example "Measure km of Endo-1,4-beta-xylanase from
Genome-annotated strain G1 on Generic insoluble xylan at 30 degC, pH 5.0 (dry
mass per volume, for example g/L); the class was inferred from the dbCAN
annotation (families GH10)."

### The enzyme-dose route

Laboratories usually report an enzyme loading per gram of substrate.
`enzyme_dose` (enzyme per dry substrate mass, for example `mg/g` or `FPU/g`)
times the case's `substrate_initial_concentration` gives the enzyme
concentration, multiplied with pint. Like the specific-activity route to Vmax,
it is **one derived record** for the enzyme-concentration role: its provenance
lists both rows (value or range, units, evidence type, source, method), the
formula and the unit conversion, and its maturity is the weaker of the two
inputs. The dose row produces no record of its own; the initial-substrate row
keeps its own record. A dose range times the exact initial substrate is again
a uniform range. Refused: a dose next to an `enzyme_concentration` in the same
case (both set the enzyme), a dose with a ranged initial substrate (the
derived enzyme would be sampled independently of the substrate it is derived
from), and a dose on a dissolved substrate. A dose without an initial
substrate leaves the enzyme concentration a gap whose request asks for the
initial substrate.

### Conversion-dependent reactivity

An optional `reactivity_exponent` row binds the existing
`substrate_reactivity` modifier: the rate is multiplied by `(S / S0)^n`, with
`S0` the case's **own** initial-substrate record (the same record that sets the
initial state; no separate constant) and `n` zero or positive. `n = 1` is the
linear substrate reactivity factor of Kadam, Rydholm and McMillan (2004,
doi:10.1021/bp034316x), the provenance the modifier carries; `n = 0` removes
it. The factor is phenomenological: it resolves no surface, crystallinity or
particle structure, and nothing else of the Kadam model (adsorption, product
inhibition) is implemented. When one case of a class and substrate gives the
exponent, the pair binds the factor and every other strain and condition of
the pair gets a gap for it. Without it, the template states that no
conversion-dependent slowdown is represented. The exponent is refused on a
dissolved substrate.

### Refused on a solid substrate

Each refusal names its file, row and column:

- `specific_activity`, `enzyme_loading` and `assay_activity`, the activity
  routes to Vmax: an activity in amount per time would need a molar mass of a
  repeat unit, one in substrate mass per enzyme mass per time is the `kcat`
  of the kcat form, and a saturating activity is not defined for an
  interfacial substrate. Give `kcat` with an enzyme concentration or dose, or
  `vmax`.
- The pH-ionization form: its Km(pH) describes the ionization of a dissolved
  enzyme-substrate complex, while the Km of the apparent law is not a binding
  constant. An enzyme class in the pH-ionization form cannot act on a solid
  substrate of the dataset either. Use a cardinal pH law in `responses.csv`.
- Molar units on any substrate-side row, on `vmax` and on the enzyme.
- `physical_state` `mixed_solid` or `solid_biomass` (composite substrates,
  which would need a composition model) and `unknown`; a `yield_basis` other
  than `g/g`; an `amount_basis` other than `dry_mass`.
- Adsorption, binding-capacity and surface inputs: the `kinetics.csv`
  quantities `adsorption_constant`, `adsorption_dissociation_constant`,
  `binding_capacity`, `accessible_surface_area`, `specific_surface_area` and
  `surface_rate_constant`, and the `substrates.csv` columns
  `specific_surface_area`, `accessible_surface_area`, `surface_area`,
  `binding_capacity`, `adsorption_capacity`, `crystallinity_index`,
  `particle_size` and `accessible_fraction`. No law of this route reads them,
  and FungMod does not store a value no law uses.
- `timecourse.csv` rows on a solid substrate (comparison and fitting read
  amounts per volume with a mol/mol yield).

### Scientific mode

Unchanged: a solid case reaches scientific mode only when every bound role,
the reactivity exponent and the dose's inputs included, is an exact
`measured`, `literature` or `design` value; an estimate anywhere keeps it
exploratory. Scientific still means exact inputs and an implemented law, not
validation.

### Limits of the solid route

- One polymer per substrate, as a bulk dry mass per volume; no composite
  substrates (glucan, xylan and lignin fractions), no particle size,
  crystallinity, porosity or accessible-area model.
- No enzyme adsorption or partitioning between free and bound enzyme, and no
  Langmuir surface law; the surface law is a later increment.
- No synergy between enzyme classes acting on one solid, no product
  inhibition, no oxidative (LPMO) kinetics; one enzyme class and one process
  per case, except in an [enzyme network](#several-enzymes-acting-together),
  where several classes on one solid act additively and independently (still
  without synergy, adsorption competition or product inhibition).
- The constants are apparent and preparation- and loading-specific; FungMod
  does not extrapolate them to other loadings and does not warn when you do.
- No conversion between dry mass, monomer equivalents and moles; the product
  is a pool in grams with your stated g/g yield.
- No time courses, comparison or fitting on solid substrates; the assembly
  and SABIO-RK drafting routes draft dissolved substrates only.
- The assembled substrate entity carries the substrate's own physical state
  (`solid_polymer`, loaded with the generic solid loader) and an `unknown`
  default degradation model: the apparent law establishes no degradation
  regime of the material.

## Fungal culture: growth and secretion

The rate forms above simulate an enzyme at a concentration you state: an
enzyme assay. An optional `culture.csv` instead simulates **the fungus growing
on the substrate and secreting its enzymes over time**. It binds the same
culture model as the registry's *T. harzianum* P49P11 case (the
`culture_physiology` template of Gelain 2020; see
[organism physiology](organism-physiology.md)) to your own strain, solid
substrate and constants. The process laws and the assembler are the existing
ones; FungMod adds no numerics for user cultures.

```text
consumption:   dS/dt = - k_h · E · S / (K_h + S)            (one consuming enzyme pool E)
growth:        dX/dt = + Y · k_h · E · S / (K_h + S) - k_d · X
ledgers:       (1 - Y) of the consumed substrate -> consumed substrate not retained as biomass
               k_d · X                            -> biomass dry mass lost
each pool P:   dP/dt = + q_P · X · S / (K_ind + S) - k_P · P
```

`S` is the substrate's dry mass per volume, `X` the biomass dry mass per volume
(in the same unit as `S`), and each pool `P` an enzyme amount per volume in its
own unit: a protein mass (for example `mg/L`) or an activity in one of the
registry's assay units (`FPU/L`, `BGU/L`). Exactly one pool, the one whose
class acts on the substrate, consumes it; every other pool is produced and lost
only. All pools share one induction constant `K_ind`, as in the registry case.
`S + X` and both ledgers form one closed dry-mass balance, which every run
checks.

### `culture.csv` (optional)

| Column | Required | Meaning |
| --- | --- | --- |
| `strain_id`* | yes | A strain of `strains.csv`. |
| `substrate_id`* | yes | A substrate of `substrates.csv`: a `solid_polymer` with `amount_basis` `dry_mass`. |
| `condition_id`* | yes | A condition of `conditions.csv`: the culture's temperature and pH (metadata, as for every case without a response law). |
| `quantity`* | yes | One role of the culture model (table below). |
| `enzyme_class` | for pool quantities | The pool's enzyme class, which the strain declares in `enzymes.csv` or `genomes.csv`; blank for a quantity of the culture as a whole. |
| `value` / `lower`, `upper` | yes | An exact value, or a range sampled in exploratory mode. |
| `units`* | yes | Checked with pint against the role's dimension. |
| `evidence_type`* | yes | `measured`, `literature`, `design` or `estimate` (`fitted` is refused: no culture constant is fitted). |
| `method` | for `measured`, `literature`, `design` | How the value was obtained. |
| `source`* | yes | Where the value comes from. |
| `sd`, `replicates` | no | Kept as provenance, not sampled. |

### Roles and units

| `quantity` | `enzyme_class` | Template role | Units (dimension) | Example |
| --- | --- | --- | --- | --- |
| `substrate_initial_concentration` | blank | `initial_substrate` | dry mass per volume | `g/L` |
| `initial_biomass` | blank | `initial_biomass` | biomass dry mass per volume, written exactly like the initial substrate's units | `g/L` |
| `biomass_yield` | blank | `biomass_yield` | dimensionless, above 0 and at most 1 | `g/g` |
| `biomass_loss_rate` | blank | `biomass_loss_rate` | 1/time | `1/h` |
| `induction_half_saturation` | blank | `induction_half_saturation` | dry mass per volume, above 0 | `g/L` |
| `hydrolysis_capacity` | the consuming pool | `hydrolysis_capacity` | substrate dry mass per time per pool amount | `g/FPU/h`, `g/mg/h` |
| `hydrolysis_half_saturation` | the consuming pool | `hydrolysis_half_saturation` | dry mass per volume, above 0 | `g/L` |
| `initial_enzyme_concentration` | each pool | `initial_enzyme_concentration__<class>` | protein mass or assay activity per volume | `FPU/L`, `mg/L` |
| `specific_production_rate` | each pool | `specific_production_rate__<class>` | pool amount per biomass dry mass per time | `FPU/g/h`, `mg/g/h` |
| `enzyme_loss_rate` | each pool | `enzyme_loss_rate__<class>` | 1/time | `1/h` |

The units of a case are also checked together: `hydrolysis_capacity × E` must be
the substrate's dry mass per volume per time with the consuming pool's own
units, and `specific_production_rate × X` an amount of the pool per volume per
time, so a pool in `FPU/L` with a rate per protein mass (or the reverse) is
refused on the rate's row. A molar amount is refused on every substrate-side,
biomass and pool row, and no pool is ever converted between protein mass,
assay units and molarity.

### Worked example

`tests/fixtures/user_data/culture_estimates/` is a user-defined strain with
one user-defined class (an endo-xylanase-like pool stated as a protein mass)
on a user-defined xylan-like solid; every value is an illustrative estimate:

```text
strain_id,substrate_id,condition_id,quantity,enzyme_class,value,lower,upper,units,evidence_type,method,source
strain_x1,xylan_lot_x1,c25,substrate_initial_concentration,,15,,,g/L,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,initial_biomass,,0.2,,,g/L,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,biomass_yield,,0.35,,,g/g,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,biomass_loss_rate,,0.01,,,1/h,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,induction_half_saturation,,0.5,,,g/L,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,hydrolysis_capacity,endo_xylanase_like,0.005,,,g/mg/h,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,hydrolysis_half_saturation,endo_xylanase_like,5,,,g/L,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,initial_enzyme_concentration,endo_xylanase_like,1,,,mg/L,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,specific_production_rate,endo_xylanase_like,5,,,mg/g/h,estimate,illustrative estimate,<source>
strain_x1,xylan_lot_x1,c25,enzyme_loss_rate,endo_xylanase_like,0.02,,,1/h,estimate,illustrative estimate,<source>
```

`kinetics.csv` holds only its header. `fungmod check-data` lists the culture:

```text
$ fungmod check-data tests/fixtures/user_data/culture_estimates
...
Kinetic values: 10; gaps: 0
Cultures (culture.csv; the strain grows on the substrate and secretes its enzyme pools, culture_physiology): 1
  strain     substrate     consuming pool      enzyme pools        culture.csv rows
  strain_x1  xylan_lot_x1  endo_xylanase_like  endo_xylanase_like  2-11
```

and `fungmod run` (or `virtual_experiment(..., user_data=...)`) simulates it:

```text
$ fungmod run --user-data tests/fixtures/user_data/culture_estimates --fungus strain_x1 \
    --substrate xylan_lot_x1 --environment c25 --mode exploratory --samples 8 --seed 1 --output culture_run
...
  1  culture_estimates__strain_x1  culture_estimates__xylan_lot_x1  culture_estimates__c25  modelable  yes
...
    final_substrate_remaining          4.105e-06 [4.105e-06, 4.105e-06] gram / liter (n=8)
    maximum_substrate_depletion_rate   0.4913 [0.4913, 0.4913] gram / hour / liter (n=8)
  Threshold times (median [5th, 95th percentile] over samples):
    time_to_10_percent_substrate_degradation  26.47 [26.47, 26.47] hour (n=8)
    time_to_50_percent_substrate_degradation  49.02 [49.02, 49.02] hour (n=8)
    time_to_90_percent_substrate_degradation  62.3 [62.3, 62.3] hour (n=8)
```

The time series hold the substrate, the biomass, every pool (in its own units;
here `milligram / liter`) and both ledgers. Every value is exact, so the eight
samples coincide; a range in `culture.csv` would be sampled. Because every row
is an estimate, scientific mode refuses the case; with `measured`,
`literature` or `design` rows throughout, the generated template is scientific
and the run is labelled `scientific_exact_unvalidated` (exact inputs and
implemented laws, not validation).

`tests/fixtures/user_data/culture_reentry/` re-enters the registry's own
*T. harzianum* culture case: the nine constants of FungMod's retrospective fit
as `estimate` (they are a fit, neither a literature value nor a measurement of
the strain) and the deposited initial biomass, initial activities and 10, 20
and 30 g/L loadings as `literature`, with a filter-paper (`FPU`) pool that
consumes the cellulose and a beta-glucosidase (`BGU`) pool that is produced and
lost only. Its biomass, cellulose, both activity and both ledger trajectories
equal the registry case's at every loading (`tests/test_user_data_culture.py`).

### What is generated

One culture model per consuming enzyme class and substrate, shared by every
strain that declares the class (the strain's records are selected by its
fungus id, as for the rate forms): a `culture_physiology` process compatibility
(`<dataset>__<class>__<substrate>__culture_physiology`) and case template
(`..._culture_template`) that composes the existing process laws (homogeneous
Michaelis-Menten consumption with a stoichiometric biomass yield and closure
ledger, first-order biomass loss, proportional induced synthesis and
first-order loss of each pool), and for every such strain, role and condition
one parameter record, or an explicit gap. The template declares no vessel
geometry (the model is concentration-only), and each synthesis and consumption
rate is in the units of the state it changes per unit of the dataset's time
grid, so one template serves cases whose rows use different units. The
template is scientific only when every bound record is exact and
scientific-eligible; one estimate keeps it exploratory (the weakest input
wins). The generated enzyme class of the consuming pool lists
`culture_physiology` as its process; the other pools keep their own.
`UserDataset.cultures` lists each strain's culture (consuming pool, pools,
template and compatibility ids, rows).

### Gaps

A role without a row is an explicit unknown with a measurement request that
names it in plain words, for example:

```text
culture_estimates__strain_x1__xylan_lot_x1__c25__culture__biomass_yield__gap
  Measure the biomass yield of Illustrative culture strain X1 on Xylan-like solid lot X1 at condition c25
  (25 degC, pH 6.0): grams of biomass dry mass formed per gram of dry Xylan-like solid lot X1 consumed
  (g/g, dimensionless).
culture_estimates__strain_x1__xylan_lot_x1__c25__culture__specific_production_rate__endo_xylanase_like__gap
  Measure the specific production rate of Endo-xylanase-like pool X1 by Illustrative culture strain X1
  growing on Xylan-like solid lot X1 at condition c25 (25 degC, pH 6.0): enzyme produced per biomass dry
  mass per time at inducing substrate levels (amount of the pool per biomass dry mass per time; the pool is
  stated in mg/L, culture.csv row 8).
```

Nothing is defaulted. A condition with no rows makes every role a gap whose
request says at which conditions the culture has values; a strain that declares
the consuming class without rows has a culture of gaps; a solid substrate the
consuming class acts on without rows is a culture of gaps with the consuming
pool only. With `--runnable-only` (`blocked="report"`) a culture case runs
beside its gap cases ([partial runs](cli.md)).

### Refused

Each refusal names its file, row and column:

- A culture on a substrate without the required basis: a dissolved substrate
  (the culture closes a dry-mass balance and the yield is g/g), and a dissolved
  substrate that a culture's consuming class acts on (a class runs one process
  law on all of its substrates).
- Mixing the culture with the enzyme-assay forms: a `kinetics.csv` row of a
  strain and substrate that have a culture; a `kinetics.csv` row of another
  strain on the culture's class and substrate (all strains of one class and
  substrate share one generated process); a `kinetics.csv` row of a culture's
  consuming class on any substrate. FungMod builds one model per strain,
  substrate and condition and does not choose between a culture and an assay;
  keep assay kinetics in a separate dataset.
- A strain that declares the consuming class and another class acting on the
  culture substrate (a class from a genome annotation included: run the
  culture in a dataset without `genomes.csv`), and a strain that declares the
  consuming class but not every pool of the culture.
- A culture whose pools include no class acting on the substrate, or more
  than one (synergy between pools is not modelled); `hydrolysis_capacity` or
  `hydrolysis_half_saturation` on a pool that does not consume the substrate.
- Units of the wrong dimension, units of one case that do not fit together
  (above), an initial biomass in other units than the initial substrate, a
  yield above 1 g/g or at zero, a zero half-saturation constant, an
  `enzyme_class` on a culture-level quantity or a missing one on a pool
  quantity, a class the strain does not declare, `fitted` evidence, a
  `kinetics.csv` quantity such as `km`, and duplicate rows.
- `responses.csv` rows of a culture: the culture model applies no temperature
  or pH law, so its constants hold at the condition of their rows.
- `timecourse.csv` rows of a culture case: the comparison and the fit read the
  substrate and the product of an enzyme-assay case; a culture's biomass, pools
  and ledgers are not observables of the comparison, and no culture constant is
  fitted.
- `assemble_user_tables` and `fungmod assemble` do not draft or carry
  `culture.csv`: a culture's substrate is a solid, which assembled drafts
  refuse with a message naming the culture; cultures on other substrates of a
  `user_data` dataset are not carried, like any substrate that was not
  requested. Load a culture dataset with `load_user_dataset` directly.

### What is and is not modelled

Modelled: one strain growing in a well-mixed batch on one suspended solid
substrate (dry-mass basis); substrate consumption by one secreted enzyme pool
with an apparent saturation law; biomass formation with an explicit yield and a
closure ledger for the consumed substrate not retained as biomass; first-order
biomass loss into a ledger; substrate-induced, biomass-proportional synthesis
and first-order loss of every enzyme pool, each in its own units.

Not modelled, and the template and outputs say so:

- One fungus per case: no co-cultures, competition or cross-feeding.
- The growth and induction laws are the existing ones: growth is driven only by
  the consumed substrate (no Monod uptake of a soluble sugar, no maintenance,
  no nutrient or oxygen limitation), induction saturates in the solid substrate
  with one constant shared by all pools, and synthesis has no material cost,
  repression or lag.
- No spatial mycelium (the spatial colony models are separate and are not
  bound by user data), no pellet or morphology, no vessel volume.
- No oxygen or pH dynamics: the template declares none, and no response law is
  bound; the temperature and pH of a condition are metadata.
- No soluble products: the product named in `substrates.csv` is not released
  by the culture (the row is still required by `substrates.csv`); consumed
  substrate is biomass or ledger.
- Pools other than the consuming one act on nothing; no synergy, product
  inhibition, adsorption or surface law.
- Constants are apparent and specific to the strain, substrate preparation and
  conditions at which they were obtained; nothing extrapolates them.
- No time courses, comparison or fitting of cultures; no assembly route.

## Several enzymes acting together

The rate forms above run **one** enzyme class of a strain on one substrate: the
class the preflight selects. A fungus secretes several enzymes at once, and an
optional `enzyme_network` block in `user_dataset.yml` makes every case of the
dataset an enzyme network instead: every declared class of the strain that acts
on a pool of the network runs its own Michaelis-Menten process, classes on one
pool act in parallel, and a pool released by one class is the substrate of the
next. The process law, the modifiers and the solver are the existing ones;
FungMod adds no numerics. The compiled core sums the stoichiometric columns of
every process, so processes on one pool add their rates:

```text
pool i:  dS_i/dt = - sum over classes j acting on i of  r_ij  +  y_(i-1) x sum over classes k acting on pool i-1 of  r_(i-1)k
each r:  Vmax S / (Km + S)  or  kcat E S / (Km + S)          (the pair's own rate form and rows)
with ki: r x (Km + S) / (Km (1 + I / Ki) + S)                 (competitive inhibition by a downstream pool I)
```

```yaml
enzyme_network:
  entry_substrates: [polymer_p1]   # the substrates each network starts from
```

Without the block nothing changes: the records of every dataset without it are
byte-identical to those of the previous version.

### Pools and links

- A network starts from an **entry substrate** listed in `entry_substrates`.
- The pool a substrate releases is its `substrates.csv` `product`, with its
  stated `product_yield`. A **link** to another pool is made only when that
  product equals another row's `substrate_id`; names, aliases and registry ids
  are never matched. The chain of links ends at the first product that is no
  substrate of the dataset, the network's **final product**. Each substrate has
  one product, so the pools of a network form a chain (for example
  polymer -> oligomer -> monomer) and any number of classes may act in parallel
  on each pool.
- The entry starts at its `substrate_initial_concentration`; every
  intermediate pool and the final product start at zero. Every pool is reported
  in the units of the entry's initial concentration, and pint converts each Km,
  Vmax and Ki.
- The members of a network are the declared classes (from `enzymes.csv` or a
  genome annotation) that act on one of its pools by the categorical rule.
  Each runs one process on its pool in its pair's rate form: the kcat form
  (with its own enzyme state) or the Vmax form, with every route to Vmax and
  to the enzyme concentration described above.
- An intermediate pool may also be an entry; it then starts a network of its
  own, from its own initial concentration.

### Competitive product inhibition: `ki`

A `kinetics.csv` row with quantity `ki` and the new column `inhibitor` binds the
existing provenance-bound `competitive_inhibition` modifier to the process of
its class and pool:

```text
rate = Vmax S / (Km (1 + I / Ki) + S)
```

`Km` is the process's own Michaelis constant, `I` the state of the pool named in
`inhibitor`, and `Ki` the row's value. The inhibitor is a pool the network
releases **downstream** of the row's substrate: an intermediate's
`substrate_id`, or the final product as written in `substrates.csv`. `Ki` is an
amount per volume (for example mM or uM), the unit basis of the product pool,
checked with pint, and positive. The law's provenance is the primary source
FungMod records for this modifier
(BIO-003, <https://pubmed.ncbi.nlm.nih.gov/7985803/>, maturity
`literature_backed_software_tested`); it supports the equation, not your Ki,
which keeps its own row's source and evidence type. When one strain or
condition gives `ki` for a process, every other strain and condition of that
process gets a Ki gap with a measurement request. A process without a `ki` row
has **no** inhibition term, and its template says so in its limitations; no
inhibition constant is assumed.

### Worked example: a chain and a parallel pair

`tests/fixtures/user_data/network_chain/` is a user-defined strain with two
user-defined classes: one cuts a soluble polymer-like substrate into four
oligomer-like units, the other cuts each oligomer-like unit into two
monomer-like units (every value an illustrative estimate):

```text
substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,product,product_yield,yield_basis,source
polymer_p1,,Soluble polymer-like substrate P1,soluble_polymer_like,dissolved,inner_glycosidic_like,oligomer_o1,4,mol/mol,<source>
oligomer_o1,,Oligomer-like pool O1,oligomer_like,dissolved,inner_glycosidic_like,monomer_m1,2,mol/mol,<source>
```

```text
strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source
strain_n1,depolymerase_like,polymer_p1,c30_ph5,km,2,,,mM,estimate,illustrative estimate,<source>
strain_n1,depolymerase_like,polymer_p1,c30_ph5,kcat,30,,,1/min,estimate,illustrative estimate,<source>
strain_n1,depolymerase_like,polymer_p1,c30_ph5,substrate_initial_concentration,5,,,mM,estimate,illustrative estimate,<source>
strain_n1,depolymerase_like,polymer_p1,c30_ph5,enzyme_concentration,0.002,,,mM,estimate,illustrative estimate,<source>
strain_n1,oligomer_hydrolase_like,oligomer_o1,c30_ph5,km,1,,,mM,estimate,illustrative estimate,<source>
strain_n1,oligomer_hydrolase_like,oligomer_o1,c30_ph5,kcat,60,,,1/min,estimate,illustrative estimate,<source>
strain_n1,oligomer_hydrolase_like,oligomer_o1,c30_ph5,enzyme_concentration,0.001,,,mM,estimate,illustrative estimate,<source>
```

```text
$ fungmod check-data tests/fixtures/user_data/network_chain
...
Enzyme networks (user_dataset.yml enzyme_network; the classes act together on shared pools, enzyme_network): 1
  from polymer_p1: polymer_p1 -> oligomer_o1 (4 mol/mol), oligomer_o1 -> monomer_m1 (2 mol/mol); strains strain_n1
  enzyme class             pool         rate form  competitive inhibitor
  depolymerase_like        polymer_p1   kcat       none
  oligomer_hydrolase_like  oligomer_o1  kcat       none

$ fungmod run --user-data tests/fixtures/user_data/network_chain --fungus strain_n1 \
    --substrate polymer_p1 --environment c30_ph5 --mode exploratory --samples 8 --seed 1 --output network_run
...
    final_substrate_remaining          3.395e-05 [3.395e-05, 3.395e-05] millimolar (n=8)
    final_product_formed               39.98 [39.98, 39.98] millimolar (n=8)
    maximum_product_release_rate       0.1095 [0.1095, 0.1095] millimolar / minute (n=8)
    maximum_substrate_depletion_rate   0.04286 [0.04286, 0.04286] millimolar / minute (n=8)
  Threshold times (median [5th, 95th percentile] over samples):
    time_to_10_percent_substrate_degradation  11.85 [11.85, 11.85] minute (n=8)
    time_to_50_percent_substrate_degradation  64.77 [64.77, 64.77] minute (n=8)
    time_to_90_percent_substrate_degradation  151.8 [151.8, 151.8] minute (n=8)
```

The threshold times and the substrate depletion rate refer to the entry pool,
`product_formed` and the product release rate to the final product. The time
series hold every pool and enzyme (`state_role` `substrate`, `intermediate_1`,
`product`, `enzyme_<class>`) and one `process_rate.<dataset>__<class>__<pool>__homogeneous_mm`
per process, and `mechanism_summary.csv` has the network row followed by one
process-law row per process naming its class (`configured_by`). Here the
oligomer-like pool accumulates while the first class outpaces the second
(10.45 mM at 145 minutes) and is then cleared; the closure `8 P + 2 O + M`
stays at 40 mM in every run (`conservation_diagnostics.csv`, weights from the
yields). In Python:

```python
dataset = fm.load_user_dataset("tests/fixtures/user_data/network_chain")
print(dataset.enzyme_networks[0]["pools"], dataset.enzyme_networks[0]["product"])
study = fm.virtual_experiment(
    fungi="strain_n1", substrates="polymer_p1", environments="c30_ph5", user_data=dataset
)
result = study.simulate(mode="exploratory", n_samples=8, seed=1)
```

`tests/fixtures/user_data/network_parallel/` is the materially different case:
two classes in parallel on one dissolved ester-like substrate, one in the kcat
form and one in the Vmax form, and a `ki` of the first class for the released
acid-like product:

```text
strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,inhibitor
strain_q2,cleaver_a_like,ester_s2,c25_ph7,ki,200,,,µM,estimate,illustrative estimate,<source>,acid_a2
```

Its tests check that the depletion rate is the sum of the two process rates at
every output time, that the first class's rate equals
`Vmax S / (Km (1 + P / Ki) + S)` on the simulated states, that a smaller Ki
leaves more substrate, and that with an initial substrate far below both Km
the substrate decays as `S0 exp(-(Vmax_A / Km_A + Vmax_B / Km_B) t)`
(`tests/test_user_data_network.py`). A network of one class equals the
single-class case of the same rows.

### What a network generates

| Record | Identifier |
| --- | --- |
| Case template per entry (`process_type` `enzyme_network`) | `<dataset_id>__<entry>__enzyme_network_template` |
| Compatibility per class acting on the entry, all pointing to that template | `<dataset_id>__<class>__<entry>__enzyme_network` |
| Parameter record per strain, condition and role | `<dataset_id>__network__<entry>__<strain>__<condition>__<role>` (`__gap` for a gap) |
| Parameter symbol per role | `<dataset_id>__network__<entry>__<role>` |

The roles are `substrate_initial_concentration` (the entry's), and per process
`km__<class>__<pool>`, `kcat__<class>__<pool>` with
`enzyme_initial_concentration__<class>` or `vmax__<class>__<pool>`, plus
`ki__<class>__<pool>` and `reactivity_exponent__<class>__<pool>` when bound.
Each record keeps the value, evidence, maturity and provenance of its row (or
derivation, or gap) and adds the network, role, class and pool under
`fungmod_user_dataset.enzyme_network`; its enzyme-class selector is empty
because one network serves the compatibility of every class acting on its
entry. The generated classes list `enzyme_network` as their only process, so a
network dataset has no single-class cases: the preflight never chooses between
a network and one of its classes. `UserDataset.enzyme_networks` (also in
`to_dict()` and `summary()`) lists each network's pools, links and yields,
processes (class, pool, rate form, process id, inhibitor), classes, strains and
generated ids. The template is scientific only when every record bound to it is
exact and scientific-eligible, as for every user template.

### Gaps of a network

Every role of every process at every condition for every strain of the network
is a record or an explicit gap with the single-class route's measurement
request, naming the class and the pool it acts on, for example "Measure kcat
and the enzyme concentration of Oligomer hydrolase-like class N1 from
Illustrative network strain N1 on Oligomer-like pool O1 at 30 degC, pH 5.0, or
Vmax (or a specific activity and enzyme loading)." A network with a gap is
underparameterized and not simulated: a class the strain has is never silently
left out. With `--runnable-only` (`blocked="report"`) the complete cases run
and the others are listed with their requests.

### Refused in a network

Each refusal names its file, row and column:

- A product that equals the `registry_substrate` of a row with another
  `substrate_id` (ambiguous: write the `substrate_id` to link, or another name
  to end the network), and a cycle of products.
- A link between pools on different bases, dissolved (amount per volume,
  `mol/mol`) and solid (dry mass per volume, `g/g`): the Michaelis-Menten law
  writes its product in the units of its substrate, and a conversion would need
  a molar mass as a dimensional yield, which FungMod does not apply.
- A class that acts on two pools of one network: one enzyme on two substrates
  competes for its active site, which independent processes do not represent.
- Strains of one dataset that declare different classes of a network (one
  network serves every strain; put other enzyme sets in separate datasets).
- On an intermediate pool: an initial concentration (unless the pool is an
  entry), an `enzyme_dose` and a `reactivity_exponent`. Different initial
  concentrations of one entry on the rows of its classes (they are one pool).
- The pH-ionization form in a network; `culture.csv`, `timecourse.csv` and
  `responses.csv` in a network dataset.
- `ki` outside a network dataset (a network of one class is the single-class
  case with inhibition), on a solid substrate (the apparent Km is not a binding
  constant), naming a pool that is not downstream (the substrate itself or an
  upstream pool), in mass units, two inhibitors of one process, and the
  `inhibitor` column on any other row.
- Unknown or repeated entries, an entry no declared class acts on, and a
  substrate that is part of no network.
- `assemble_user_tables` (and `fungmod assemble`) with a network dataset as
  `user_data`: drafts are single-class tables and would drop the network.

### What a network does and does not model

Modelled: several enzyme classes of one strain acting on a chain of
well-mixed pools, each by its own Michaelis-Menten law at its stated
concentration, classes on one pool in parallel with additive rates, each pool
released into the next with the stated yield, and optional competitive
inhibition of a process by one downstream pool.

Not modelled, and the template and outputs say so:

- **Additive, independent action.** Classes on one pool do not compete for
  substrate binding or adsorption sites, do not cooperate (no endo/exo
  synergy) and do not interact; their rates simply add. Measured mixtures that
  degrade faster or slower than the sum of their parts are outside this model.
- One competitive inhibitor per process, and only competitive: no
  non-competitive, uncompetitive or mixed inhibition, no inhibition by several
  products of one process, no substrate inhibition, no competing substrates of
  one enzyme, no transglycosylation.
- Chains only (each substrate has one product), on one amount basis; no
  branching products, no dry-mass-to-molar conversion.
- No response laws, time courses, comparison, fitting, cultures or assembly
  drafting of networks yet; the values hold at the condition of their rows.
- An enzyme-kinetics model at stated enzyme concentrations, not a fungus
  growing and secreting; the strain's class list decides which classes act.

## Evidence types, maturity and modes

| `evidence_type` | Record maturity | Exact value | Range |
| --- | --- | --- | --- |
| `measured` | `user_measured` | scientific and exploratory | exploratory screening only |
| `literature` | `user_reported_literature` | scientific and exploratory | exploratory screening only |
| `design` | `user_design_value` | scientific and exploratory | exploratory screening only |
| `estimate` | `exploratory_prior` (provenance `exploratory_prior: true`) | exploratory only | exploratory only |
| `fitted` | `user_fitted` | exploratory screening only | (not written) |

`fitted` rows are written only by `fit_user_dataset` and are accepted only
with the manifest `fit` block that describes them (see
[fitting](#fitting-kinetic-constants-to-time-courses)); a hand-typed `fitted`
row is refused. They never reach scientific mode.

The maturities are ordered from weakest to strongest as
`exploratory_prior` < `user_design_value` < `user_reported_literature` <
`user_measured`. A Vmax derived from a specific activity and an enzyme loading
takes the weaker input's maturity and allowed use, and every parameter of one
response law takes the weakest maturity among that law's rows: one estimated
cardinal value makes the whole law an `exploratory_prior`.

The allowed use of each record is set explicitly from this table. Scientific
mode therefore accepts a case only when every role (the rate-form roles and the
parameters of any bound law) is an exact `measured`, `literature` or `design`
value; an `estimate` anywhere blocks it with the
usual "Scientific simulation requires exact, non-exploratory, non-toy modelable
cases" error. Scientific still means exact inputs and implemented mechanisms,
not experimental validation; FungMod does not check user values against an
external source.

The generated case template for an enzyme class and substrate is labelled
`scientific` only when every parameter record bound to it (all strains and
conditions, gaps included) is exact and scientific-eligible; otherwise it is
labelled `exploratory`. The template is shared by every strain and condition
of that pair, so one strain whose own records are all eligible still runs in
scientific mode, but its configured model then carries the conservative
`exploratory` label and the deterministic case builder
(`build_model_config_from_registry_case(mode="scientific")`) refuses it.

Text in sources, methods and notes reaches the configured model's maturity
check. Words reserved for software fixtures (`toy`, `testing`, `benchmark`,
`dummy`, `artificial`, `framework`) make a run fail that check, so keep them
out of data you intend to simulate.

## What gets generated

| Record | Identifier |
| --- | --- |
| Fungus per strain, listing its namespaced classes (from `enzymes.csv` and `genomes.csv`) | `<dataset_id>__<strain_id>` |
| Enzyme class per declared class, limited to the process law of its rate form (`homogeneous_michaelis_menten`, or `ph_ionization_michaelis_menten` for the pH-ionization form, or `culture_physiology` for a culture's consuming class) | `<dataset_id>__<class>` |
| Substrate per user-defined substrate, with its physical state (registry substrates are referenced) | `<dataset_id>__<substrate_id>` |
| Enzyme concentration derived from an `enzyme_dose` ([solid substrates](#solid-substrates)) | `<dataset_id>__<strain>__<class>__<substrate>__<condition>__enzyme_concentration` |
| Environment per condition | `<dataset_id>__<condition_id>` |
| Compatibility and case template per class and compatible substrate | `<dataset_id>__<class>__<substrate_id>__homogeneous_mm[_template]`, or `__ph_ionization_mm[_template]` in the pH-ionization form |
| Parameter record per kinetics row of a role | `<dataset_id>__<strain>__<class>__<substrate>__<condition>__<quantity>` |
| Vmax record (explicit row, derived, or from an assay activity) | `<dataset_id>__<strain>__<class>__<substrate>__<condition>__vmax` |
| Response-law parameter record per `responses.csv` row | `<dataset_id>__<strain>__<class>__<substrate>__<law>__<parameter>` |
| Explicit unknown per missing role or law parameter | the same identifier with `__gap` |
| Culture compatibility and case template per consuming class and culture substrate ([fungal culture](#fungal-culture-growth-and-secretion)) | `<dataset_id>__<class>__<substrate_id>__culture_physiology`, `<dataset_id>__<class>__<substrate_id>__culture_template` |
| Enzyme-network template per entry substrate, compatibility per class acting on it, and records per strain, condition and role ([several enzymes acting together](#what-a-network-generates)) | `<dataset_id>__<entry>__enzyme_network_template`, `<dataset_id>__<class>__<entry>__enzyme_network`, `<dataset_id>__network__<entry>__<strain>__<condition>__<role>` |
| Culture parameter record per strain, condition and role (`<pool>` for a pool quantity only) | `<dataset_id>__<strain>__<substrate>__<condition>__culture__<quantity>[__<pool>]`, symbol `<dataset_id>__culture__<quantity>[__<pool>]__<class>__<substrate_id>` |

The compatibility record binds the roles of the pair's rate form (`km`,
`kcat`, `substrate_initial_concentration`, `enzyme_initial_concentration`;
`km`, `vmax`, `substrate_initial_concentration`; or the ten roles of the
pH-ionization form in the table [above](#three-rate-forms)), then
`reactivity_exponent` when a solid pair binds the reactivity factor, followed
by the parameters of any bound law; the template of a Vmax-form pair has no
enzyme state, and a pair with laws or the reactivity factor lists them under
`process_state_metadata.process_modifiers` (the reactivity factor as
`substrate_reactivity` with `reference_concentration_role`
`substrate_initial_concentration`). The template of a pH-ionization
pair has the process type `ph_ionization_michaelis_menten`, so its assembled
model reads the pH of the environment and reports
`environment_effect_status = active_response_model` for pH.
`specific_activity`, `enzyme_loading` and `assay_activity` rows produce no
records of their own; they appear in the provenance of the Vmax record, as an
`enzyme_dose` row appears in the provenance of the derived enzyme
concentration.

A class and substrate are compatible when the substrate class is among the
class's compatible substrate classes and they share a bond class. A
namespaced copy of a registry class keeps the parent's bond classes,
substrate classes and EC number; the parent ID is recorded in provenance only,
never as an alias. Parameter symbols are namespaced as
`<dataset_id>__<quantity>__<class>__<substrate_id>`, law parameters as
`<dataset_id>__<law>__<parameter>__<class>__<substrate_id>`.

Every parameter record carries the reserved provenance namespace
`fungmod_user_dataset` (dataset id, digest, file, row, contributor, source,
method, evidence type, standard deviation, replicates and condition) together
with `measurement_method` and `validity_range` (the condition's temperature and
pH). Curator authoring refuses records that carry this namespace, so a user
dataset cannot be relabelled as curated evidence.

## Gaps and measurement requests

For every strain, declared class, compatible substrate and condition, each
role of the pair's rate form without a kinetics row becomes an explicit unknown
parameter record with maturity `user_dataset_gap` and the allowed use
`preflight_and_gap_analysis_only_requires_measurement_or_curation`. Its units
come only from the user's own rows of the same case (a missing `km` takes the
case's concentration units; on a [solid substrate](#solid-substrates) only the
dry-mass rows `km` and `substrate_initial_concentration` lend their units);
otherwise the units stay empty and the notes state the dimension needed, in
dry-mass terms on a solid substrate. Its provenance holds a measurement request such
as:

> Measure kcat of carboxylesterase from Esterase source strain E1 on
> p-nitrophenyl butyrate at 37 degC, pH 7.5 (units of 1/time).

The request follows the rate form the user started. When no case of the pair
gives any rate row, the `kcat` and enzyme-concentration gaps both carry one
request that names both forms:

> Measure kcat and the enzyme concentration of laccase-like oxidase from
> Oxidase source strain L1 on syringaldazine-like phenolic azine at 50 degC,
> pH 5.0, or Vmax (or a specific activity and enzyme loading).

A started Vmax route with one of its two rows missing asks for that row (for
example the enzyme loading needed to derive Vmax from the specific activity in
a stated row). A missing constant of the pH-ionization form asks for a fit of
the law over a pH series at the condition's temperature, for example:

> Measure the lower pK of the free enzyme (pk_free_lower) of acid
> phosphatase-like enzyme from Phosphatase source strain P1 on model alkyl
> phosphate monoester (dimensionless) by fitting the diprotic pH-ionization law
> to initial rates over a pH series at the temperature of condition c37_ph5
> (37 degC).

and a missing `ph_min` or `ph_max` asks for the end of the fitted pH series. When a law is bound to an enzyme class and substrate for one
strain, every other strain of that pair gets a gap per law parameter (with
no condition), asking for that parameter of that law.

When the strain, class and substrate have kinetic constants at other
conditions but none at this one, the request names them, since kinetics are
never reused at another condition:

> Measure km of carboxylesterase from Esterase source strain E1 on
> p-nitrophenyl butyrate at 45 degC, pH 7.5 (concentration units); kinetics.csv
> states kinetic constants of this strain, enzyme class and substrate only at
> c37_ph7_5 (37 degC, pH 7.5), and FungMod does not reuse kinetics measured at
> another condition.

When the class of the case comes only from the strain's genome annotation,
every request ends with the families it was inferred from (see
[`genomes.csv`](#genomescsv-optional-enzyme-classes-from-a-genome-annotation)),
and the gap's provenance carries `class_evidence: genome_annotation`.

Preflight reports such a case as `underparameterized`, names the namespaced
symbol among the missing items, and quotes the request in the report's
`suggested_experiments` and in `modelability_preflight.csv`; the standard
`missing_parameters.csv` and `suggested_experiments.csv` writers use the same
text. Registry records without a request keep the existing suggestion text.

## Outputs

`VirtualExperiment` keeps `user_dataset_id` and `user_dataset_digest`, and
both appear in `virtual_experiment_summary.json` (under `experiment`) and in
`output_manifest.json` (`null` without user data). Beside them,
`virtual_experiment_summary.json` lists `genome_resolved_classes`,
`unmodellable_enzyme_classes` and `unmapped_families` (empty lists for a
dataset without `genomes.csv`, `null` without user data; entries from a
UniProt export carry `source_type` and accessions), and
`VirtualExperiment.write_preflight_report` writes
`user_dataset_genome_resolution.json` with these lists and the annotations
read when the dataset has a `genomes.csv`. In the standard tables,
`parameter_source_class` reads `user_measured_exact_value`,
`user_reported_literature_range`, `user_design_value_exact_value` and so on,
estimates read `user_supplied_exploratory_prior`, and the mechanism maturity
of an all-user, non-estimate case is
`software_tested_user_supplied_parameterized`; a case with a `fitted` value
reads `user_fitted_exact_value` and
`software_tested_user_fitted_in_sample_unvalidated`. Output schema `2.1.0`
adds the `timecourse_comparison` table, written only on request (see
[comparing](#comparing-a-virtual-experiment-with-the-time-courses)); the other
tables are unchanged.

## Time courses, comparison and fitting

> **Honesty note.** Comparing a simulation with your own time courses, and
> fitting constants to them, measures **in-sample** agreement with your own
> data. It is not validation. A value fitted to a time course reproduces that
> time course by construction, so the agreement is not independent evidence
> that the model or the value is right; only a prediction checked against data
> that played no part in choosing the values can say that (see
> [independent validation](independent-validation.md)). FungMod labels every
> fitted value `fitted` (maturity `user_fitted`), limits it to exploratory
> screening, refuses it in scientific mode, and marks comparison rows whose
> observations were used in the fit.

### `timecourse.csv` (optional)

Columns: `strain_id`\*, `enzyme_class`\*, `substrate_id`\*, `condition_id`\*,
`observable`\*, `time`\*, `time_units`\*, `value`\*, `units`\*, `sd`,
`replicates`, `source`\*, `method`\*.

```text
strain_id,enzyme_class,substrate_id,condition_id,observable,time,time_units,value,units,sd,replicates,source,method
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,s200,substrate,0,minute,200.4,µM,2.0,3,LN-42 p. 20,HPLC
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,s200,substrate,10,minute,191.2,µM,2.0,3,LN-42 p. 20,HPLC
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,s200,product,10,minute,8.7,µM,0.4,3,LN-42 p. 20,absorbance at 405 nm
```

- `observable` is `substrate` (substrate remaining) or `product` (product
  formed since time zero).
- The strain, enzyme class (declared for the strain), substrate (one the class
  can act on) and condition must be declared in the other tables.
- `time` is a finite number, zero or positive, in `time_units` (a time unit);
  `value` is a finite number. Values are not clipped: a slightly negative
  product after background subtraction is kept as measured.
- `units` must be a concentration in amount per volume, the kind of the case's
  states (the product yield is mol/mol), for example µM or mM. Other
  dimensions, and mass concentrations such as g/L, are refused with the case's
  own units in the message. Time courses of a
  [solid substrate](#solid-substrates), and of a
  [culture](#fungal-culture-growth-and-secretion) case, are refused in this
  version.
- `sd` is a positive standard deviation in `units` when given, and
  `replicates` a positive integer; report replicates as their mean with `sd`.
- One series (strain, class, substrate, condition and observable) uses one
  time unit and one value unit and lists each time once; a repeated time is
  refused.

The time courses are kept on `UserDataset.timecourses`, keyed by the generated
case id `<dataset_id>__<strain>__<class>__<substrate>__<condition>`, one
`UserTimecourse` per observable with its rows, sources and methods, and appear
in `to_dict()` (`timecourses`) and `summary()` (`timecourse_case_ids`). They
are observations, not registry records: no record is generated from them. The
file's bytes enter the dataset digest.

### Comparing a virtual experiment with the time courses

```python
dataset = fm.load_user_dataset("path/to/esterase_case")
study = fm.virtual_experiment(
    fungi="Esterase source strain E1",
    substrates="p-nitrophenyl butyrate",
    environments=["s50", "s200", "s800"],
    user_data=dataset,
)
result = study.simulate(mode="exploratory", n_samples=32)
comparison = result.compare_with_timecourses()   # or fm.compare_with_timecourses(result, dataset)
for series in comparison.series:
    print(series["series_id"], series["rmse"], series["units"], series["fraction_inside_band"])
```

From a shell, `fungmod run --user-data DIR ... --compare-timecourses` does
the same after simulating and prints each series' RMSE, mean residual,
fraction inside the band and observations used in a fit
([command line](cli.md#compare-with-your-time-courses)).

For each simulated case with time courses, the median (`p50`) and the 5-95 %
band (`p05`, `p95`) of `trajectory_quantiles.csv` are brought to each observed
time by **linear interpolation on the simulated output grid** and converted to
the observation's units: the substrate state for `substrate`, and
`product_formed` for `product`. An observation outside the simulated time
range refuses the comparison with its row; nothing is extrapolated (extend
`simulation.duration` instead). The comparison is refused for a result built
from another dataset or without time courses.

`timecourse_comparison.csv` is written into the output directory (and joins
`output_manifest.json`): one row per observation with the observed value and
`sd`, the interpolated `simulated_p05`, `simulated_p50` and `simulated_p95`,
the residual (simulated median minus observed), the standardized residual when
`sd` is given, `inside_band`, and per series the RMSE and mean residual in the
observable's units, the fraction inside the band, the number of observations
and the number with `sd`. Every row carries the interpolation method,
`used_in_fit`, `allowed_use = in_sample_agreement_with_user_timecourses_not_validation`
and the in-sample note. In exploratory mode the band spans the sampled input
ranges; with exact inputs every sample is identical and the band has zero
width, so the fraction inside it says little.

### Fitting kinetic constants to time courses

```python
fit = fm.fit_user_dataset(
    dataset,
    parameters=[
        ("strain_e1", "carboxylesterase", "p_nitrophenyl_butyrate", "km"),
        ("strain_e1", "carboxylesterase", "p_nitrophenyl_butyrate", "kcat"),
    ],
    bounds={"km": (10, 5000, "µM"), "kcat": (1, 300, "1/min")},   # required
    initial={"km": 1000, "kcat": 5},
)
for item in fit.quantities:
    print(item.quantity, item.value, item.units, item.identifiability, item.interval)
fitted = fit.write("path/to/esterase_case_fitted")   # a new user dataset
```

From a shell: `fungmod fit DIR --case strain_e1 carboxylesterase
p_nitrophenyl_butyrate --fit km 10 5000 µM --fit kcat 1 300 1/min --initial km
1000 --initial kcat 5 --output DIR_fitted` prints the fitted values, intervals
and verdicts and writes the fitted dataset; an unidentified quantity exits
with code 2 unless `--allow-unidentified`
([command line](cli.md#fit-kinetic-constants-to-your-time-courses)).

What the fit does:

- **One case, shared constants.** `parameters` names `(strain_id,
  enzyme_class, substrate_id, quantity)` tuples of one case with quantities
  among `km`, `kcat` (kcat form) and `vmax` (Vmax form). The time courses of
  that case at `conditions` (default: every condition with time courses) are
  fitted together, so each fitted constant is shared by those conditions; they
  must have the same known temperature and pH (for example several initial
  substrate concentrations of one assay), otherwise the fit is refused. Every
  role the fit does not vary must be an exact value.
- **The existing machinery.** The predictions come from the same assembled
  model a virtual experiment runs (the case's registry records rebuilt by the
  registry assembler for each candidate), integrated on the compiled core
  (`ConfiguredConditionPredictor`), and the optimizer is
  `fungal_model.calibration.fit_least_squares` (bounded trust-region least
  squares) on the natural logarithm of each value. The finite-difference step
  is `1e-3` in log space, above the ODE solver's step noise; it is recorded.
- **Bounds are required** as `(lower, upper, units)` with `0 < lower < upper`;
  there are no default bounds. The fitted value is reported in those units.
  `initial` gives starting values in the same units; without it, the
  dataset's exact value at every fitted condition is the start, and the fit is
  refused when there is none.
- **Error model.** By default each residual is divided by its observation's
  `sd` (independent Gaussian errors with the reported standard deviations).
  When any fitted observation lacks `sd`, the fit is refused unless you pass
  `error_model="unweighted"`, which fits raw residuals (one value unit across
  the series) and is recorded in the dataset and the report.
- **Identifiability.** With `sd` weighting each quantity is profiled
  (`fungal_model.calibration.profile_likelihood`): it is fixed on a log grid
  across its bounds (`profile_points`, default 21, plus the optimum) while the
  other fitted quantities are refitted, and each crossing of the threshold
  (the chi-square quantile of one degree of freedom at `confidence_level`,
  3.84 at 0.95) is bisected with ten further profile evaluations. A quantity
  is `identified` when the profile crosses the threshold on both sides within
  its bounds, `bounded_above_only` or `bounded_below_only` when on one side
  only, and `not_identified_within_bounds` otherwise; the interval is where the
  profile stays under the threshold. With `unweighted`, the local information
  matrix of the residuals (`local_information_analysis`) must have full rank,
  and a linearized interval (residual variance estimated from the residuals)
  must lie inside both bounds. Verdicts are conditional on the bounds of the
  other fitted quantities and on the error model; a finite grid with local
  refits is not a global identifiability proof.
- **Refusals.** A quantity that is not identified refuses the fit with
  `UserDataFitError` (whose `report` holds the profiles) unless
  `allow_unidentified=True`; then its rows are written and labelled "NOT
  IDENTIFIED". A fit that does not converge is always refused, and so are a
  fit with no more observations than quantities, a `kcat` fit in a Vmax-form
  case (or the reverse), and a dataset that is itself the result of a fit.

What `fit.write(path)` writes (a new or empty directory; nothing is
overwritten):

- a copy of every input file, byte for byte, except `kinetics.csv` and
  `user_dataset.yml`;
- `kinetics.csv` with each fitted quantity at each fitted condition replaced
  by a row of `evidence_type = fitted`, the fitted value in the bound units, a
  `method` naming the fit and the time-course rows and a `source` naming the
  input dataset and its digest (a fitted `vmax` replaces the case's whole Vmax
  route at that condition);
- `user_dataset.yml` with a new `dataset_id` (default `<input id>_fitted`)
  and a `fit` block: method, objective, error model, input dataset id and
  digest, the fit report file and its SHA-256, the case, conditions and
  `timecourse.csv` rows used, and per quantity the value, units, bounds,
  starting value, identifiability verdict, method and interval;
- `fit_report.json`: the full report (convergence, residuals per observation,
  observations against parameters, profiles, local information, settings,
  warnings and the claim boundary).

On loading, a `fitted` row is accepted only when the `fit` block lists its
case, condition, quantity, value and units and the report file matches its
recorded digest; a value edited by hand, a changed report or a hand-typed
`fitted` row is refused. The fitted record has maturity `user_fitted`, allowed
use `exploratory_screening_only_not_calibrated_uncertainty_not_environment_response`,
and carries the fit description (method, objective, data rows, bounds,
identifiability and the scientific-mode boundary) under
`provenance.fungmod_user_dataset.fit`. Preflight in exploratory mode treats it
like any exact value; **scientific mode refuses it**, and no relabelling
route is provided: an in-sample fit is not independent evidence, and the same
time courses cannot both choose a value and vouch for it.

## Starting from SABIO-RK

Public kinetics reach a simulation by the same route as your own tables, with
you in the loop. `user_tables_from_sabiork` drafts the tables above from
SABIO-RK kinetic-law entries; you review and edit them; `load_user_dataset`
then checks them like any other dataset. The entries can come from:

- a `RegistryProposal` from `source_proposal(provider="sabiork", ...)`, which
  reads a frozen snapshot, or queries SABIO-RK live only when you pass
  `refresh=True` and your network allows it;
- the path of a kinetic-law export JSON you downloaded from SABIO-RK yourself
  (the `{"meta": ..., "data": [...]}` document of
  `https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?q=...`);
- a reaction ID string such as `"618"`, read from the local snapshot folders
  through the same adapter.

Drafting never fetches anything.

```python
import fungmod as fm

proposal = fm.source_proposal(provider="sabiork", reaction_id="618", entry_id="35622")
draft = fm.user_tables_from_sabiork(
    proposal,                      # or "path/to/export.json", or "618"
    dataset_id="os3bglu6_sabiork",
    design={                       # the virtual assay's own amounts, optional
        "substrate_initial_concentration": {"value": 10, "units": "mM"},
        "enzyme_concentration": {"value": 1e-3, "units": "mM"},
    },
)
draft.write("os3bglu6_sabiork")  # the tables, user_dataset.yml and review.md
print(draft.review)                # every decision, and everything not converted
```

From a shell: `fungmod draft-kinetics SOURCE --provider sabiork --dataset-id ID
--output DIR`, with `SOURCE` an export file or a reaction ID read from the
local snapshots and `--entry-id`, `--design QUANTITY=VALUE UNITS`,
`--strain-for ORGANISM=STRAIN_ID` and `--propose-enzyme-classes` for the
arguments above ([command line](cli.md#draft-tables-from-sabio-rk)).

The draft does not load yet. Every field that needs a person's decision begins
with `REVIEW:`: always the manifest's `contributor` and the simulation time grid
(FungMod has no default grid), and also, when the source leaves them open, a
temperature or pH that SABIO-RK gives only as a range, the product or yield of
a reaction that does not name one product, the categorical fields of a
substrate the registry does not know, the bond and substrate classes of a
proposed enzyme class, the enzyme loading a specific activity needs, and the
`ph_min` and `ph_max` of a pH-ionization law whose entry states no pH range.
`draft.review_fields` and the "Fields to fill" table of `review.md` list them
with file, row and column, and `load_user_dataset` refuses the directory until
each is filled:

```text
UserDataError: User dataset 'os3bglu6_sabiork' still has unfilled review fields (cells or manifest
values beginning with 'REVIEW:'). 4 issue(s):
- user_dataset.yml column contributor: Unfilled review field contributor: 'REVIEW: name of the person
  who reviewed these tables'. Replace it with a reviewed value before loading.
- user_dataset.yml column simulation.duration: Unfilled review field simulation.duration: ...
```

After editing `user_dataset.yml` (for example `duration: 10`, `units: hour`,
`points: 61`) and reviewing the tables:

```python
dataset = fm.load_user_dataset("os3bglu6_sabiork")
study = fm.virtual_experiment(
    fungi="oryza_sativa_in_escherichia_coli_origami_de3",
    substrates="cellobiose",
    environments="c30_ph5",
    user_data=dataset,
)
study.preflight(mode="scientific")
result = study.simulate(mode="scientific")
```

With this design, the drafted EntryID 35622 gives the same Km, kcat, standard
deviations, design values and trajectory as the hand-written
`literature_reentry` fixture (`tests/test_user_data_sources.py`).

### Mapping rules

Every application of these rules is recorded in `review.md`.

| SABIO-RK | User tables | Rule |
| --- | --- | --- |
| Organism and expression host (`expressed_in`) | `strains.csv` | One strain per organism and host, ID `<organism>_in_<host>` (or the ID given in `strain_id_for_organism`), name `SABIO-RK enzyme source: <organism>, expressed in <host>`. Mutant enzymes are listed, not converted: an engineered variant is not an enzyme of the organism. |
| EC number | `enzymes.csv` | Resolved against the registry's enzyme classes, where EC numbers are aliases. An unresolved EC number is listed and the entry not converted; with `propose_enzyme_classes=True` an `enzyme_classes.csv` row is drafted whose bond and substrate classes are `REVIEW:` fields, never inferred. |
| Substrate named by the Km and concentration parameters (or the reaction's only substrate) | `substrates.csv` | Resolved against the registry by name or alias and referenced; otherwise a row with `REVIEW:` substrate class, physical state and bond classes. The product and its mol/mol yield (product coefficient divided by substrate coefficient) come from the reaction when it names one product; otherwise `REVIEW:`. |
| Temperature, pH, buffer | `conditions.csv` | One condition per distinct temperature and pH (IDs such as `c30_ph5`), the buffer in `notes`. A missing value is `unknown`; a range is a `REVIEW:` field. `°C` becomes `degC` and `K` `kelvin`. |
| Km | `km` | |
| kcat | `kcat` | |
| Vmax | `vmax` or `specific_activity` | `vmax` when the units are an amount per volume per time; `specific_activity` when they are an amount per time per enzyme mass, with an `enzyme_loading` row taken from `design` or left as `REVIEW:`. A mass rate is listed. |
| Concentration of the substrate or the enzyme | `substrate_initial_concentration`, `enzyme_concentration` | The assay's values, usually the tested range; a `design` value replaces them (the replaced value is listed). |
| `k0`, `Km0`, `pKe1`, `pKe2`, `pKes1`, `pKes2` and the pH variable of the diprotic "Michaelis-Menten (pH-dependent)" law | `kcat_limiting`, `km_limiting`, `pk_free_lower`, `pk_free_upper`, `pk_complex_lower`, `pk_complex_upper`, `ph_min`, `ph_max` | The [pH-ionization form](#three-rate-forms); see below. |
| kcat/Km, pKa of any other law, Ki and other types | | Listed, not converted. |

Values are copied, never converted: start and end values give `value` or
`lower` and `upper`, the standard deviation becomes `sd`, and the evidence type
is `literature`. The source reads `SABIO-RK EntryID 35622 (Seshadri S et al.
2009, PMID 19587102)` and the method `SABIO-RK kinetic law 35622,
Michaelis-Menten`, followed by the SABIO-RK parameter name when it differs
from its type (`Km0`, `k0`) and SABIO-RK's comment (`apparent`, `estimated from
plot`). `design` takes only `substrate_initial_concentration`,
`enzyme_concentration` and `enzyme_loading`; kinetic constants come from the
source.

**Units.** A unit string the unit registry parses is kept as written
(`mM`, `s^(-1)` and `µmol*min^(-1)*mg^(-1)` all parse). Otherwise the explicit
table `SABIORK_UNIT_SPELLINGS` maps a known SABIO-RK spelling to the same unit
in ASCII (`s^(-1)` to `1/s`, `µmol*min^(-1)*mg^(-1)` to `umol/min/mg`), and the
mapping is recorded; any other unit is listed and its value not converted.
The dimension is then checked for the quantity, so a spelling the registry
misreads (`units/mg` parses as a luminosity) is listed too.

**Conflicts and rate forms.** FungMod holds one value per quantity and case.
Entries that map to the same strain, enzyme class, substrate and condition
(isoenzymes of one organism measured at the same condition) are all listed as
a conflict and none is converted; choose one with `entry_ids`. All cases of an
enzyme class and substrate share one rate form, so when some entries give kcat
and others Vmax the kcat form is kept and the Vmax values are listed.

**pH-dependent laws.** An entry whose kinetic law carries the four pKa
parameters with the limiting kcat and Km of SABIO-RK's diprotic
"Michaelis-Menten (pH-dependent)" law (kinetic-law type 24, as in entries
38522 to 38534 of Reaction 618) is drafted in the
[pH-ionization form](#three-rate-forms). The converter recognises the law by
its formula, compared with whitespace removed to
`E*((k0)/((10^(pKes1-pH)+1)*(10^(pH-pKes2)+1)))*S/(((k0)/((10^(pKes1-pH)+1)*(10^(pH-pKes2)+1)))/(((k0)/(Km0))/((10^(pKe1-pH)+1)*(10^(pH-pKe2)+1)))+S)`,
and by the parameter names in it: `k0` becomes `kcat_limiting`, `Km0`
`km_limiting`, `pKe1` and `pKe2` `pk_free_lower` and `pk_free_upper`, `pKes1`
and `pKes2` `pk_complex_lower` and `pk_complex_upper`, all as `literature`
values with their standard deviations (SABIO-RK's `-` unit of a pKa is written
`dimensionless`). `k0` and `Km0` are never written as `kcat` and `km`: they are
the law's limiting constants, not the constants at the entry's pH. `ph_min`
and `ph_max` are the pH range the entry states, the start and end of the law's
pH variable or else of the assay pH (entry 38522 gives 4 to 8); when it states
none, or two different ones, they are `REVIEW:` fields. The condition pH is the
pH the case runs at: SABIO-RK gives the assay pH of such an entry as the range
of the pH profile, so it stays a `REVIEW:` field, to be filled with one pH
inside `ph_min` to `ph_max` (`unknown` is refused for this form). A law with
pKa parameters whose formula or parameter names differ is listed, not
converted, and none of its constants is written. Because one enzyme class uses
one process law, pH-ionization entries are listed, not converted, when the
selected entries give the same enzyme class in the kcat or Vmax form; select
them alone with `entry_ids`. `review.md` lists every pH-dependent law under
"pH-ionization laws" with its pKa values and whether it was converted.

```python
draft = fm.user_tables_from_sabiork(
    "618",
    dataset_id="bgl1a_sabiork",
    entry_ids=["38522"],
    design={
        "substrate_initial_concentration": {"value": 5, "units": "mM"},
        "enzyme_concentration": {"value": 0.001, "units": "mM"},
    },
)
draft.write("bgl1a_sabiork")  # fill contributor, the time grid and the condition pH (one value from 4 to 8)
```

Once reviewed (pH 5, 14400 s, 145 points), the drafted entry 38522 simulates
the same trajectory as the hand-written `bgl1a_ph_ionization` fixture.

**What Reaction 618 gives.** Of the 29 entries of the frozen Reaction 618
snapshot, five are converted (38521, 39245, 44879, 44888, 60725). Listed with a
reason: 15 mutants, two conflicts (35622 with 39780, wild-type rice enzymes from
two studies expressed in the same host and measured at 30 degC and pH 5; 38522
with 38534, the pH-dependent laws of BGL1A and BGL1B), four entries whose EC
numbers the registry does not resolve (3.2.1.74, 3.2.1.25, 3.2.1.58) and one
entry without a Km, kcat or Vmax value.
`entry_ids=["35622"]` converts the selected entry of the registry case, and
`entry_ids=["38522"]` the pH-dependent law of the registry's BGL1A case.

Limits of the SABIO-RK route:

- SABIO-RK only, and only what an export contains; no other kinetics database.
- Homogeneous Michaelis-Menten constants and the diprotic pH-dependent law
  only; inhibition, cooperativity, other pH laws and multi-substrate laws are
  listed, not imported.
- No value is converted between units, and SABIO-RK's normalised values are not
  used.
- A SABIO-RK concentration range is the range tested in the assay; it is
  written as a range, which exploratory runs sample uniformly and scientific
  mode refuses, unless a `design` value replaces it.
- Strains are keyed by organism and host as SABIO-RK spells them, so
  `Escherichia coli Origami (DE3)` and `Escherichia coli Origami(DE3) cell` are
  different hosts; merge them by editing the tables.
- Mutant enzymes are not converted.

## Limitations of this increment

- Michaelis-Menten kinetics only, in the kcat form, the Vmax form or the
  diprotic pH-ionization form, one form per enzyme class and substrate, and
  the pH-ionization form on all substrates of an enzyme class or on none;
  dissolved substrates, or one suspended solid polymer on a dry-mass basis
  under the apparent law (see the [limits of the solid route](#limits-of-the-solid-route)).
- The pH-ionization form reads the pH once from the environment: no pH
  dynamics, buffer identity, ionic strength or pH-dependent enzyme stability.
  Its constants are not rescaled with temperature except through a bound
  temperature law, which rescales the rate only. A grid pH outside `ph_min` to
  `ph_max` warns rather than being refused. On this branch preflight does not
  itself check that the environment pH is exact; a pH range cannot come from
  `conditions.csv` or an `EnvironmentGrid`, and should one reach a case through
  another environment, assembly refuses it.
- No unit conversion between molar and mass concentrations or rates; the
  product yield must be mol/mol on a dissolved substrate and g/g on a solid
  one. An assay activity is accepted only on the case substrate at saturation
  (and never on a solid substrate); activities are never converted between
  substrates.
- Response laws are limited to the cardinal temperature, cardinal pH and
  Arrhenius laws, one per condition, and scale the rate only: `Km` and the
  concentrations are not rescaled, and no thermal inactivation is represented.
  Without `responses.csv`, user kinetics apply at their stated condition; in an
  `EnvironmentGrid` they are reused at grid conditions only as labelled
  context, as for registry records. With a law, the reused reference values
  are rescaled by the law. When the dataset has several conditions for a case
  (gap records included) no condition-specific record is copied and the grid
  case reports the roles as missing.
- Several enzyme classes act together only in an enzyme network
  ([several enzymes acting together](#several-enzymes-acting-together)):
  independent Michaelis-Menten processes whose rates add on shared pools, a
  chain of pools linked by explicit products on one amount basis, and
  optionally one competitive inhibitor per process; no synergy, competition for
  sites, competing substrates of one enzyme, other inhibition forms, response
  laws, time courses or cultures in a network. Growth and secretion only through
  `culture.csv`, which binds the registry's culture model (one consuming pool,
  an explicit yield, induced synthesis; see
  [what is and is not modelled](#what-is-and-is-not-modelled)); no uptake of
  soluble products.
- Time courses measure the substrate state or the product formed of a
  simulated case; other observables (intermediates, biomass, rates) are not
  read. Comparison interpolates linearly on the simulated output grid and
  never extrapolates.
- A fit covers one case and shares its constants across conditions of one
  temperature and pH; it fits `km`, `kcat` and `vmax` only (not
  concentrations or response-law parameters), from one starting point (no
  multi-start), assumes independent Gaussian errors with the reported `sd`
  (or equal variances when unweighted) and never chains fits. Fitted values
  stay exploratory; scientific mode refuses them.
- A genome annotation adds enzyme classes, never rates; only dbCAN
  `overview.txt` files and UniProtKB TSV exports are read, and only classes
  with a registry record are added (see the limits of the genome and UniProt
  routes above).
- One substrate per substrate class for each enzyme class, because FungMod
  selects a process by enzyme class and substrate class.
- A namespaced copy of a registry class keeps the parent's EC number, so
  resolving that EC number as an enzyme class on the overlaid registry is
  ambiguous; strains, substrates and conditions are unaffected.
- The overlay lives in memory for one experiment. There is no promotion of
  user records into the shared registry.
- Tables drafted from SABIO-RK are drafts: nothing is imported without a
  person filling the `REVIEW:` fields, and only the conversions listed in
  [starting from SABIO-RK](#starting-from-sabio-rk) are made.
- An assembled draft covers one fungus per call, reads offline sources only,
  writes kinetics of another organism's enzyme as estimates, and reaches a
  condition other than the measured one only through a response law at an
  `EnvironmentGrid` condition (see
  [assembling fungus, substrate and conditions](#assembling-fungus-substrate-and-conditions)).
