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

Two complete examples live in the test fixtures:
`tests/fixtures/user_data/esterase_case/` (a user-defined carboxylesterase on a
user-defined aryl ester, estimates only) and
`tests/fixtures/user_data/literature_reentry/` (the published SABIO-RK Reaction
618 selected entry typed in as literature values against the registry's
`cellobiose` and `beta_glucosidase`).

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

Any other CSV file in the directory (for example `responses.csv`) is refused as
unsupported in this version rather than ignored. Columns not listed below are
refused too. Required columns are marked with an asterisk. Lists inside a cell
are separated by semicolons. Rows are reported by their spreadsheet line
number (the header is line 1).

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

`notes` is also accepted. Every generated identifier is prefixed with
`<dataset_id>__`.

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
Every strain must declare at least one class.

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
`physical_state`, `bond_classes`, `product`\*, `product_yield`\*,
`yield_basis`\*, `source`\*.

```text
substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,product,product_yield,yield_basis,source
p_nitrophenyl_butyrate,,p-nitrophenyl butyrate,aryl_ester,dissolved,carboxylic_ester,p_nitrophenol,1,mol/mol,Lab notebook LN-42 p. 4
cellobiose,cellobiose,,,,,beta_D_glucose,2,mol/mol,Reaction equation of the source entry
```

- With `registry_substrate`, the registry record is referenced, not copied: the
  row supplies only the product, yield and source, and the other descriptive
  columns must stay blank. The registry substrate must be dissolved and must
  already list the product.
- Without it, every column is required and `physical_state` must be
  `dissolved`.
- The product yield is always explicit (`yield_basis` must be `mol/mol`); it is
  never inferred.

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
`method`, `source`\*, `sd`, `replicates`.

```text
strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,km,150,,,µM,measured,initial-rate fit,LN-42 p. 12,12,3
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,kcat,,20,40,1/min,measured,initial-rate fit,LN-42 p. 12,,3
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,substrate_initial_concentration,200,,,µM,design,experimental design,LN-42 p. 11,,
strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,enzyme_concentration,0.05,,,µM,design,experimental design,LN-42 p. 11,,
```

- `quantity` is one of `km`, `kcat`, `substrate_initial_concentration` and
  `enzyme_concentration`. Rows giving `vmax` or `enzyme_activity` are refused:
  this increment needs `kcat` and an enzyme concentration, and FungMod does not
  convert a maximum rate or an activity unit into them.
- Give either `value` (exact) or `lower` and `upper` (a range, sampled
  uniformly in exploratory runs).
- `km` and both concentrations must be concentrations; `kcat` must have the
  dimension 1/time. The concentration rows of one case must all be amount per
  volume: a mass concentration next to a molar one would need a molar mass,
  and the mol/mol yield cannot be applied to mass concentrations either, so
  both are refused.
- `method` is required for `measured`, `literature` and `design` rows.
- `sd` and `replicates` are kept in the provenance; the standard deviation is
  not turned into a sampling distribution.

## Evidence types, maturity and modes

| `evidence_type` | Record maturity | Exact value | Range |
| --- | --- | --- | --- |
| `measured` | `user_measured` | scientific and exploratory | exploratory screening only |
| `literature` | `user_reported_literature` | scientific and exploratory | exploratory screening only |
| `design` | `user_design_value` | scientific and exploratory | exploratory screening only |
| `estimate` | `exploratory_prior` (provenance `exploratory_prior: true`) | exploratory only | exploratory only |

The allowed use of each record is set explicitly from this table. Scientific
mode therefore accepts a case only when all four roles are exact `measured`,
`literature` or `design` values; an `estimate` anywhere blocks it with the
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
| Fungus per strain, listing its namespaced classes | `<dataset_id>__<strain_id>` |
| Enzyme class per declared class, limited to homogeneous Michaelis-Menten | `<dataset_id>__<class>` |
| Substrate per user-defined substrate (registry substrates are referenced) | `<dataset_id>__<substrate_id>` |
| Environment per condition | `<dataset_id>__<condition_id>` |
| Compatibility and case template per class and compatible substrate | `<dataset_id>__<class>__<substrate_id>__homogeneous_mm[_template]` |
| Parameter record per kinetics row | `<dataset_id>__<strain>__<class>__<substrate>__<condition>__<quantity>` |
| Explicit unknown per missing role | the same identifier with `__gap` |

A class and substrate are compatible when the substrate class is among the
class's compatible substrate classes and they share a bond class. A
namespaced copy of a registry class keeps the parent's bond classes,
substrate classes and EC number; the parent ID is recorded in provenance only,
never as an alias. Parameter symbols are namespaced as
`<dataset_id>__<quantity>__<class>__<substrate_id>`.

Every parameter record carries the reserved provenance namespace
`fungmod_user_dataset` (dataset id, digest, file, row, contributor, source,
method, evidence type, standard deviation, replicates and condition) together
with `measurement_method` and `validity_range` (the condition's temperature and
pH). Curator authoring refuses records that carry this namespace, so a user
dataset cannot be relabelled as curated evidence.

## Gaps and measurement requests

For every strain, declared class, compatible substrate and condition, each of
the four roles without a kinetics row becomes an explicit unknown parameter
record with maturity `user_dataset_gap` and the allowed use
`preflight_and_gap_analysis_only_requires_measurement_or_curation`. Its units
come only from the user's own rows of the same case (a missing `km` takes the
case's concentration units); otherwise the units stay empty and the notes
state the dimension needed. Its provenance holds a measurement request such
as:

> Measure kcat of carboxylesterase from Esterase source strain E1 on
> p-nitrophenyl butyrate at 37 degC, pH 7.5 (units of 1/time).

Preflight reports such a case as `underparameterized`, names the namespaced
symbol among the missing items, and quotes the request in the report's
`suggested_experiments` and in `modelability_preflight.csv`; the standard
`missing_parameters.csv` and `suggested_experiments.csv` writers use the same
text. Registry records without a request keep the existing suggestion text.

## Outputs

`VirtualExperiment` keeps `user_dataset_id` and `user_dataset_digest`, and
both appear in `virtual_experiment_summary.json` (under `experiment`) and in
`output_manifest.json` (`null` without user data). In the standard tables,
`parameter_source_class` reads `user_measured_exact_value`,
`user_reported_literature_range`, `user_design_value_exact_value` and so on,
estimates read `user_supplied_exploratory_prior`, and the mechanism maturity
of an all-user, non-estimate case is
`software_tested_user_supplied_parameterized`. The output schema version is
unchanged.

## Limitations of this increment

- Homogeneous, enzyme-explicit Michaelis-Menten kinetics only; dissolved
  substrates only.
- No `vmax` or activity units, no unit conversion between molar and mass
  concentrations, and the product yield must be mol/mol.
- No response laws: user kinetics apply at their stated condition. In an
  `EnvironmentGrid` they are reused at grid conditions only as labelled
  context without any temperature or pH response law, as for registry
  records; when the dataset has several conditions for a case (gap records
  included) none is copied and the grid case reports the roles as missing.
- No enzyme cocktails or multi-step chains, no time-course responses or
  fitting, no growth, secretion or uptake.
- One substrate per substrate class for each enzyme class, because FungMod
  selects a process by enzyme class and substrate class.
- A namespaced copy of a registry class keeps the parent's EC number, so
  resolving that EC number as an enzyme class on the overlaid registry is
  ambiguous; strains, substrates and conditions are unaffected.
- The overlay lives in memory for one experiment. There is no promotion of
  user records into the shared registry.
