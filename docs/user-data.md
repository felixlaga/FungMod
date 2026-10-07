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

Four complete examples live in the test fixtures:
`tests/fixtures/user_data/esterase_case/` (a user-defined carboxylesterase on a
user-defined aryl ester, `kcat` form, estimates only),
`tests/fixtures/user_data/literature_reentry/` (the published SABIO-RK Reaction
618 selected entry typed in as literature values against the registry's
`cellobiose` and `beta_glucosidase`),
`tests/fixtures/user_data/oxidase_case/` (a user-defined laccase-like oxidase on
a dissolved phenolic substrate, Vmax from a specific activity and an enzyme
loading, with cardinal temperature and pH laws in `responses.csv`; estimates
only) and `tests/fixtures/user_data/genome_case/` (a strain whose enzyme
classes come only from a hand-written dbCAN overview in `genomes.csv`; a format
fixture with synthetic gene identifiers, not a real genome, and no kinetic
values, so every resolved class is a gap).

To start from public kinetics instead of typing them in, draft the tables from
SABIO-RK entries and review them; see
[starting from SABIO-RK](#starting-from-sabio-rk).

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
| `genomes.csv` | no | A dbCAN genome annotation per strain, from which enzyme classes are resolved. |
| annotation files | with `genomes.csv` | The dbCAN `overview.txt` files that `genomes.csv` names, anywhere inside the directory. |
| `timecourse.csv` | no | Measured substrate remaining and product formed over time (see [time courses](#time-courses-comparison-and-fitting)). |
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
(see [below](#fitting-kinetic-constants-to-time-courses)). Every generated
identifier is prefixed with `<dataset_id>__`.

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

### `genomes.csv` (optional): enzyme classes from a genome annotation

Columns: `strain_id`\*, `annotation_file`\*, `annotation_tool`\*, `source`\*,
`min_tools_agreeing`.

```text
strain_id,annotation_file,annotation_tool,source
strain_g1,annotations/strain_g1_overview.txt,dbCAN 4.1.4,"run_dbcan on the predicted proteome of assembly <accession>, 2026-09-30"
```

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

- dbCAN `overview.txt` only, read from the dataset directory; no other
  annotation format and no download at run time.
- Family-level mapping: the curated map covers 18 CAZy families, a
  polyspecific family gives only a candidate class, and the `EC#` column is not
  used. With the shipped registry only `beta_glucosidase` and
  `cellulase_generic` among the mapped classes have a record, so most resolved
  classes are reported as unmodellable; the resolver's `require_diagnostic`
  filter is not exposed.
- Gene counts are annotated genes, not active enzymes, copy numbers or
  expression.
- The test fixture is a format fixture written by hand; no real genome
  annotation is bundled.

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
dataset without `genomes.csv`, `null` without user data), and
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
  own units in the message.
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

The draft does not load yet. Every field that needs a person's decision begins
with `REVIEW:`: always the manifest's `contributor` and the simulation time grid
(FungMod has no default grid), and also, when the source leaves them open, a
temperature or pH that SABIO-RK gives only as a range, the product or yield of
a reaction that does not name one product, the categorical fields of a
substrate the registry does not know, the bond and substrate classes of a
proposed enzyme class, and the enzyme loading a specific activity needs.
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
| kcat/Km, pKa, pH, Ki and other types | | Listed, not converted. |

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

**pH-dependent laws.** A kinetic law with pKa parameters (SABIO-RK's
"Michaelis-Menten (pH-dependent)") is not turned into a cardinal pH law. FungMod
implements that law for registry cases (`ph_ionization_michaelis_menten`, see
[environment response laws](environment-response.md)), but `responses.csv`
cannot bind it yet, so the entry is listed under "pH-ionization laws" as
"pH-ionization law not importable as user data yet"; only its Km and kcat are
converted, at the entry's pH. SABIO-RK
gives the pH of such an entry as the range of the pH profile, so that pH is a
`REVIEW:` field, and the converted constants belong to a law that also contains
pH terms: they need not equal the Km and kcat observed at any single pH.

**What Reaction 618 gives.** Of the 29 entries of the frozen Reaction 618
snapshot, five are converted (38521, 39245, 44879, 44888, 60725). Listed with a
reason: 15 mutants, two conflicts (35622 with 39780, wild-type rice enzymes from
two studies expressed in the same host and measured at 30 degC and pH 5; 38522
with 38534, the pH-dependent laws of BGL1A and BGL1B), four entries whose EC
numbers the registry does not resolve (3.2.1.74, 3.2.1.25, 3.2.1.58) and one
entry without a Km, kcat or Vmax value.
`entry_ids=["35622"]` converts the selected entry of the registry case.

Limits of the SABIO-RK route:

- SABIO-RK only, and only what an export contains; no other kinetics database.
- Homogeneous Michaelis-Menten constants only; inhibition, cooperativity,
  pH-ionization and multi-substrate laws are listed, not imported.
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
- No enzyme cocktails or multi-step chains, no growth, secretion or uptake.
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
  `overview.txt` files are read, and only classes with a registry record are
  added (see the limits of the genome route above).
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
