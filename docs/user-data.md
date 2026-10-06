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

Three complete examples live in the test fixtures:
`tests/fixtures/user_data/esterase_case/` (a user-defined carboxylesterase on a
user-defined aryl ester, `kcat` form, estimates only),
`tests/fixtures/user_data/literature_reentry/` (the published SABIO-RK Reaction
618 selected entry typed in as literature values against the registry's
`cellobiose` and `beta_glucosidase`) and
`tests/fixtures/user_data/oxidase_case/` (a user-defined laccase-like oxidase on
a dissolved phenolic substrate, Vmax from a specific activity and an enzyme
loading, with cardinal temperature and pH laws in `responses.csv`; estimates
only).

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

Any other CSV file in the directory (for example a time-course table) is
refused as unsupported in this version rather than ignored. Columns not listed
below are refused too. Required columns are marked with an asterisk. Lists inside a cell
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
`method`, `source`\*, `sd`, `replicates`, `activity_substrate`,
`activity_saturating`.

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

`U` is the enzyme unit of the unit registry, one micromole per minute.
`enzyme_activity` is refused as ambiguous: say `specific_activity` or
`assay_activity`.

- Give either `value` (exact) or `lower` and `upper` (a range, sampled
  uniformly in exploratory runs).
- The concentration rows of one case must all be amount per volume: a mass
  concentration next to a molar one would need a molar mass, and the mol/mol
  yield cannot be applied to mass concentrations either, so both are refused.
  For the same reason `vmax` and `assay_activity` must be amounts, not masses,
  per volume per time.
- `method` is required for `measured`, `literature` and `design` rows, and for
  every `vmax` row whatever its evidence type: it must say how the maximum rate
  of the simulated system was obtained.
- `sd` and `replicates` are kept in the provenance; the standard deviation is
  not turned into a sampling distribution.
- `activity_substrate` and `activity_saturating` belong to `assay_activity`
  rows only and are refused on any other row.

#### Two rate forms

A case (one strain, enzyme class, substrate and condition) uses one of two
forms of homogeneous Michaelis-Menten kinetics:

- **kcat form**, `rate = kcat · E · S / (Km + S)`: `km`, `kcat`,
  `substrate_initial_concentration` and `enzyme_concentration`. The enzyme is a
  model state.
- **Vmax form**, `rate = Vmax · S / (Km + S)`: `km`, Vmax and
  `substrate_initial_concentration`. There is no enzyme state, so enzyme loss
  or dilution cannot be simulated.

A case that gives `kcat` or `enzyme_concentration` together with any Vmax row
is refused; FungMod never derives one form from the other. All strains and
conditions of one enzyme class and substrate share one generated process, so
they must use the same form; a dataset where one strain uses `kcat` and another
`vmax` on the same pair is refused. A pair without any rate row is generated in
the kcat form, and its gap requests name both forms (see below).

#### Three routes to Vmax

Vmax for a case comes from exactly one route; rows of two routes in one case
are refused.

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
of the Arrhenius law. Validation:

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
`vmax`, `specific_activity`, `assay_activity`) must be stated at the reference
condition. For every condition at which such rows exist, the condition's
temperature or pH must equal the reference parameter exactly, or lie within
the `reference_tolerance` stated on the reference parameter's row (a
nonnegative number in that row's units; FungMod has no tolerance of its own).
Alternatively `kinetics_at_reference = yes` on that row declares that the
kinetic values are already reference values (for example rates normalised to
the optimum); the declaration is recorded in provenance and not checked. A
condition with an unknown temperature or pH cannot carry kinetic constants for
a law on that condition. Otherwise the dataset is refused with a message
naming the condition, the reference value and the difference. Concentrations
and `enzyme_loading` are amounts, not rates, and are not checked or rescaled.

## Evidence types, maturity and modes

| `evidence_type` | Record maturity | Exact value | Range |
| --- | --- | --- | --- |
| `measured` | `user_measured` | scientific and exploratory | exploratory screening only |
| `literature` | `user_reported_literature` | scientific and exploratory | exploratory screening only |
| `design` | `user_design_value` | scientific and exploratory | exploratory screening only |
| `estimate` | `exploratory_prior` (provenance `exploratory_prior: true`) | exploratory only | exploratory only |

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
| Fungus per strain, listing its namespaced classes | `<dataset_id>__<strain_id>` |
| Enzyme class per declared class, limited to homogeneous Michaelis-Menten | `<dataset_id>__<class>` |
| Substrate per user-defined substrate (registry substrates are referenced) | `<dataset_id>__<substrate_id>` |
| Environment per condition | `<dataset_id>__<condition_id>` |
| Compatibility and case template per class and compatible substrate | `<dataset_id>__<class>__<substrate_id>__homogeneous_mm[_template]` |
| Parameter record per kinetics row of a role | `<dataset_id>__<strain>__<class>__<substrate>__<condition>__<quantity>` |
| Vmax record (explicit row, derived, or from an assay activity) | `<dataset_id>__<strain>__<class>__<substrate>__<condition>__vmax` |
| Response-law parameter record per `responses.csv` row | `<dataset_id>__<strain>__<class>__<substrate>__<law>__<parameter>` |
| Explicit unknown per missing role or law parameter | the same identifier with `__gap` |

The compatibility record binds the roles of the pair's rate form (`km`,
`kcat`, `substrate_initial_concentration`, `enzyme_initial_concentration`, or
`km`, `vmax`, `substrate_initial_concentration`) followed by the parameters of
any bound law; the template of a Vmax-form pair has no enzyme state, and a
pair with laws lists them under `process_state_metadata.process_modifiers`.
`specific_activity`, `enzyme_loading` and `assay_activity` rows produce no
records of their own; they appear in the provenance of the Vmax record.

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
case's concentration units); otherwise the units stay empty and the notes
state the dimension needed. Its provenance holds a measurement request such
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
a stated row). When a law is bound to an enzyme class and substrate for one
strain, every other strain of that pair gets a gap per law parameter (with
no condition), asking for that parameter of that law.

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

- Homogeneous Michaelis-Menten kinetics only, in the kcat form or the Vmax
  form, one form per enzyme class and substrate; dissolved substrates only.
- No unit conversion between molar and mass concentrations or rates, and the
  product yield must be mol/mol. An assay activity is accepted only on the case
  substrate at saturation; activities are never converted between substrates.
- Response laws are limited to the cardinal temperature, cardinal pH and
  Arrhenius laws, one per condition, and scale the rate only: `Km` and the
  concentrations are not rescaled, and no thermal inactivation is represented.
  Without `responses.csv`, user kinetics apply at their stated condition; in an
  `EnvironmentGrid` they are reused at grid conditions only as labelled
  context, as for registry records. With a law, the reused reference values
  are rescaled by the law. When the dataset has several conditions for a case
  (gap records included) no condition-specific record is copied and the grid
  case reports the roles as missing.
- No enzyme cocktails or multi-step chains, no time-course responses or
  fitting, no growth, secretion or uptake.
- One substrate per substrate class for each enzyme class, because FungMod
  selects a process by enzyme class and substrate class.
- A namespaced copy of a registry class keeps the parent's EC number, so
  resolving that EC number as an enzyme class on the overlaid registry is
  ambiguous; strains, substrates and conditions are unaffected.
- The overlay lives in memory for one experiment. There is no promotion of
  user records into the shared registry.
