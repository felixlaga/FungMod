# FungMod Registry and Parameter-Range Architecture

## Purpose

FungMod’s long-term goal is to become a plug-and-play simulation and screening tool for fungal degradation systems:

> Given a fungus, substrate, environment, geometry, and available evidence, FungMod should assemble the best-supported model, accept exact values or parameter ranges, run deterministic or ensemble simulations, and report what is known, uncertain, missing, or unsupported.

This file defines the next architecture layer needed to reach that goal.

The key idea is:

```text
Exact biological structure where categorical facts matter.
Ranges/distributions where numerical values are uncertain.
Structured failure where mechanisms or evidence are missing.
```

This is closer to how researchers actually model complex systems. They often do not know one exact value for temperature, surface area, secretion rate, adsorption constant, or rate constant. They know ranges, priors, distributions, assumptions, or scenarios. FungMod must support that natively.

This file is not about implementing detailed real biology yet. It is about building the registry, parameter-range, compatibility, and plug-and-play assembly layer that will allow real biology to be added safely.

---

## Core principle

FungMod should not require exact numerical values for every uncertain parameter.

Instead, every value should be classified as one of:

```text
known_exact
known_range
known_distribution
estimated
calibrated
unknown
not_applicable
```

The model engine should then decide:

```text
scientific deterministic run:
    requires known_exact or calibrated values for all required parameters

exploratory ensemble run:
    allows ranges/distributions and samples across uncertainty

modelability assessment:
    does not require all parameters; reports what is known, uncertain, or missing

toy mode:
    allows benchmark artificial values

strict scientific mode:
    rejects toy, unsourced, unknown, or inappropriate values
```

This lets FungMod be useful before every parameter is known.

---

## Why categorical biology and numeric uncertainty must be separated

Some things must be exact or explicitly declared:

```text
- substrate bond classes
- substrate physical state
- enzyme target class
- whether a product exists in the product map
- whether a fungus has evidence for producing a relevant enzyme class
- whether a product is known to be assimilable
- whether the environment is aerobic/anaerobic
- whether geometry is well-mixed, film, particle, or unsupported
```

Other things can be uncertain ranges:

```text
- temperature
- pH
- water activity
- oxygen concentration
- accessible surface area
- roughness factor
- amorphous fraction
- enzyme loading
- secretion rate
- k_cat
- K_m
- k_surface
- K_ads
- diffusion coefficient
- biomass yield
- maintenance rate
```

FungMod must not confuse these categories.

A range for `k_surface` is useful.

A range for “does the substrate contain beta-1,4-glycosidic bonds?” is usually not useful. That should be represented as known, unknown, or disputed evidence.

---

## Target user workflow

Eventually, a researcher should be able to write:

```python
from fungal_model.registry import load_registry
from fungal_model.screening import assess_modelability, simulate_screen

registry = load_registry("fungmod_registry/")

report = assess_modelability(
    fungus_id="pleurotus_ostreatus",
    substrate_id="cellulose_avicel",
    environment_id="pH5_30C_aerobic",
    registry=registry,
)

print(report.summary())

ensemble = simulate_screen(
    fungus_ids=["pleurotus_ostreatus", "trametes_versicolor"],
    substrate_ids=["cellulose_avicel", "pet_film", "chitin_powder"],
    environment_ids=["pH5_30C_aerobic", "pH7_25C_aerobic"],
    registry=registry,
    mode="exploratory",
    n_samples=512,
)
```

Possible output:

```text
Pleurotus ostreatus + cellulose_avicel + pH5_30C_aerobic

Modelability: exploratory
Can assemble model: yes
Scientific deterministic run: no

Known:
- fungus has cellulase capability evidence
- substrate contains beta-1,4-glycosidic bonds
- product map to glucose/cellobiose exists
- environment pH and temperature are supplied as ranges

Uncertain but sampleable:
- accessible surface area: 0.1-10 m^2/g
- surface hydrolysis parameter: 1e-9-1e-6 kg/m^2/s
- enzyme secretion rate: literature range
- glucose uptake parameter: broad prior

Missing:
- fungus-specific calibrated secretion rate
- dataset validating this fungus/substrate/environment pair

Recommended experiment:
- glucose release time course at fixed biomass/enzyme loading
```

This is a valuable result even when exact prediction is not possible.

---

# Part 1: Registry folder structure

Create a registry layer separate from raw experiment data.

Suggested structure:

```text
data_registry/
    README.md
    registry_index.yml

    fungi/
        fungi.yml
        pleurotus_ostreatus.yml
        trametes_versicolor.yml

    enzymes/
        enzyme_classes.yml
        enzymes.yml

    substrates/
        substrate_classes.yml
        substrates.yml

    products/
        products.yml

    environments/
        environments.yml

    geometries/
        geometries.yml

    processes/
        process_compatibility.yml
        process_requirements.yml

    parameters/
        parameter_records.yml
        parameter_priors.yml
        calibrated_parameter_sets.yml

    datasets/
        datasets.yml

    cases/
        case_templates.yml
```

The existing `data/` folder should continue storing actual model configs, product maps, synthetic/literature datasets, and benchmark files.

The new `data_registry/` folder should store **indexes, capability records, compatibility records, parameter records, and registry metadata**.

---

# Part 2: Registry index

Create:

```text
data_registry/registry_index.yml
```

Example:

```yaml
kind: fungmod_registry_index
registry_id: default_fungmod_registry
version: 0.1.0
maturity: development
description: Default FungMod registry for toy, synthetic, and curated benchmark records.

records:
  fungi: fungi/fungi.yml
  enzymes: enzymes/enzymes.yml
  enzyme_classes: enzymes/enzyme_classes.yml
  substrates: substrates/substrates.yml
  substrate_classes: substrates/substrate_classes.yml
  products: products/products.yml
  environments: environments/environments.yml
  geometries: geometries/geometries.yml
  process_compatibility: processes/process_compatibility.yml
  process_requirements: processes/process_requirements.yml
  parameters: parameters/parameter_records.yml
  parameter_priors: parameters/parameter_priors.yml
  calibrated_parameter_sets: parameters/calibrated_parameter_sets.yml
  datasets: datasets/datasets.yml

provenance:
  created_by: FungMod
  notes: Registry index for plug-and-play model assembly. Not a complete biological database.
```

A registry index lets users load one folder instead of manually passing many files.

---

# Part 3: Core registry objects

Create modules:

```text
src/fungal_model/registry/
    __init__.py
    records.py
    loaders.py
    store.py
    validation.py
```

## Required classes

```python
RegistryRecord
FungusRecord
EnzymeRecord
EnzymeClassRecord
SubstrateRecord
SubstrateClassRecord
ProductRecord
EnvironmentRecord
GeometryRecord
ProcessCompatibilityRecord
ProcessRequirementRecord
ParameterRecord
ParameterPriorRecord
CalibratedParameterSetRecord
DatasetRecord
FungModRegistry
```

Do not overbuild all fields at once. Start with minimal fields needed for modelability assessment.

All records must have:

```python
record_id: str
name: str
maturity: str
provenance: dict
notes: str
```

Every record must support:

```python
to_dict()
validate()
```

---

# Part 4: Value specifications: exact, range, distribution, unknown

This is the most important new concept.

Create:

```text
src/fungal_model/core/value_spec.py
```

or:

```text
src/fungal_model/registry/value_spec.py
```

## Required object

```python
@dataclass(frozen=True)
class ValueSpec:
    kind: Literal[
        "exact",
        "range",
        "distribution",
        "unknown",
        "not_applicable",
    ]
    units: str | None
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    distribution: str | None = None
    parameters: Mapping[str, float] = field(default_factory=dict)
    source: str | None = None
    confidence_level: str | None = None
    notes: str = ""
```

## Supported YAML examples

Exact:

```yaml
temperature:
  kind: exact
  value: 303.15
  units: kelvin
  source: user supplied
```

Range:

```yaml
accessible_surface_area:
  kind: range
  lower: 0.1
  upper: 10.0
  units: meter^2 / gram
  source: estimated range from material characterization
```

Distribution:

```yaml
k_surface:
  kind: distribution
  distribution: loguniform
  parameters:
    lower: 1.0e-9
    upper: 1.0e-6
  units: kilogram / meter^2 / second
  source: exploratory prior
```

Unknown:

```yaml
secretion_rate:
  kind: unknown
  units: gram / gram / second
  source: not measured for this fungus/substrate pair
```

Not applicable:

```yaml
oxygen_concentration:
  kind: not_applicable
  units: null
  source: anaerobic experiment
  notes: Oxygen is not applicable because the case is explicitly anaerobic.
```

## Validation rules

- `exact` requires value and units unless dimensionless.
- `range` requires lower < upper and units.
- `distribution` requires distribution name, parameters, and units.
- Initially support `uniform` and `loguniform`.
- `unknown` may include expected units but no value.
- `not_applicable` must explain why.
- negative values are rejected for parameters marked nonnegative.
- scientific deterministic mode accepts exact/calibrated only.
- exploratory mode accepts exact/range/distribution.
- unknown required values prevent simulation but appear in modelability reports.

## Tests

Add tests for:

- exact value parsing;
- range value parsing;
- invalid range lower >= upper;
- uniform distribution sampling;
- loguniform distribution sampling;
- unknown value;
- not applicable;
- unit compatibility;
- sampling from range/distribution with fixed seed;
- deterministic mode rejecting range/unknown;
- exploratory mode accepting range/distribution.

---

# Part 5: Parameter records and priors

Create registry records for parameters.

Example:

```yaml
- record_id: param_cellulase_surface_rate_generic_range
  name: Generic cellulase surface hydrolysis rate range
  parameter_symbol: k_surface
  applies_to:
    enzyme_class: cellulase
    substrate_class: cellulose
    process_type: surface_catalysis
  value:
    kind: distribution
    distribution: loguniform
    parameters:
      lower: 1.0e-9
      upper: 1.0e-6
    units: kilogram / meter^2 / second
    source: exploratory prior, not calibrated
  maturity: exploratory_prior
  provenance:
    source: placeholder range for software workflow only
    confidence_level: testing
  notes: Not scientific. Used to test range-based screening.
```

Parameter records must be queryable by:

```text
parameter_symbol
process_type
enzyme_class
substrate_class
fungus_id
substrate_id
environment_id
dataset_id
maturity
```

The query should return:

```text
exact match first
calibrated match second
class-level prior third
unknown if nothing exists
```

Do not silently choose a prior as scientific.

---

# Part 6: Capability records

## Fungus capability record

Example:

```yaml
- fungus_id: pleurotus_ostreatus
  name: Pleurotus ostreatus
  taxonomy:
    genus: Pleurotus
    species: ostreatus
  capabilities:
    enzyme_production:
      - enzyme_class: cellulase
        evidence_level: literature_reported
        source: ...
      - enzyme_class: laccase
        evidence_level: literature_reported
        source: ...
    product_assimilation:
      - product_id: glucose
        status: known
        source: ...
  environmental_tolerance:
    temperature:
      kind: range
      lower: 293.15
      upper: 303.15
      units: kelvin
    ph:
      kind: range
      lower: 5.0
      upper: 7.0
      units: dimensionless
  maturity: literature_metadata
```

For now, use fake/toy records only until real literature records are curated.

## Substrate record

Example:

```yaml
- substrate_id: cellulose_avicel
  name: Avicel cellulose
  substrate_class: cellulose
  physical_state: solid_polymer
  bond_classes:
    - beta_1_4_glycosidic
  products:
    - glucose
    - cellobiose
  morphology:
    accessible_surface_area:
      kind: range
      lower: 0.1
      upper: 10.0
      units: meter^2 / gram
  maturity: literature_metadata
```

## Enzyme class record

Example:

```yaml
- enzyme_class: cellulase
  target_bond_classes:
    - beta_1_4_glycosidic
  compatible_substrate_classes:
    - cellulose
  compatible_processes:
    - surface_catalysis
    - homogeneous_michaelis_menten
```

---

# Part 7: Process compatibility registry

Create:

```text
data_registry/processes/process_compatibility.yml
```

Example:

```yaml
- compatibility_id: cellulase_on_cellulose_surface
  enzyme_class: cellulase
  substrate_class: cellulose
  required_bond_classes:
    - beta_1_4_glycosidic
  process_type: surface_catalysis
  required_parameters:
    - k_surface
    - K_ads
  required_states:
    - substrate_amount
    - product_amount
    - free_enzyme_concentration
  product_map_required: true
  maturity: framework_rule
```

This should allow FungMod to answer:

```text
Given fungus produces cellulase and substrate is cellulose,
surface_catalysis is a possible process,
but k_surface and K_ads may be missing or uncertain.
```

---

# Part 8: Modelability assessment

Create:

```text
src/fungal_model/screening/
    __init__.py
    modelability.py
```

## API

```python
def assess_modelability(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    mode: Literal["scientific", "exploratory", "toy"] = "exploratory",
) -> ModelabilityReport:
    ...
```

## ModelabilityReport

```python
@dataclass(frozen=True)
class ModelabilityReport:
    fungus_id: str
    substrate_id: str
    environment_id: str
    status: Literal["modelable", "exploratory", "underparameterized", "unsupported"]
    known: tuple[ReportItem, ...]
    uncertain: tuple[ReportItem, ...]
    missing: tuple[ReportItem, ...]
    incompatible: tuple[ReportItem, ...]
    required_processes: tuple[str, ...]
    candidate_processes: tuple[str, ...]
    required_parameters: tuple[str, ...]
    suggested_experiments: tuple[str, ...]
    assumptions: tuple[str, ...]
    def to_dict(self) -> dict: ...
    def summary(self) -> str: ...
```

## Status definitions

```text
modelable:
    all required mechanisms and exact/calibrated parameters exist for selected mode

exploratory:
    required mechanisms exist, but at least one required parameter is a range/distribution

underparameterized:
    mechanisms exist, but one or more required parameters are unknown

unsupported:
    no compatible mechanism connects fungus capability to substrate target
```

## Required logic

1. Load fungus record.
2. Load substrate record.
3. Load environment record.
4. Find fungus enzyme capabilities.
5. Match enzyme classes to substrate bond/substrate classes.
6. Find compatible processes.
7. Collect required parameters.
8. Query parameter registry for each required parameter.
9. Classify each parameter as known, uncertain, missing, or invalid for mode.
10. Return `ModelabilityReport`.

Do not assemble a full ODE model yet. First build the report.

---

# Part 9: Range-based ensemble simulation

Do not implement this until modelability reports work.

Future API:

```python
simulate_case(
    fungus_id=...,
    substrate_id=...,
    environment_id=...,
    registry=registry,
    mode="exploratory",
    n_samples=512,
)
```

This should:

1. call `assess_modelability`;
2. fail if unsupported or underparameterized;
3. sample ranges/distributions;
4. generate model configs for each sample;
5. run `run_configured_model`;
6. return ensemble result with quantiles.

This is the Atmodeller-like range workflow.

But first implement registry and modelability reports.

---

# Part 10: First implementation milestone

## R1: ValueSpec and registry loader foundation

Implement:

```text
src/fungal_model/core/value_spec.py
src/fungal_model/registry/records.py
src/fungal_model/registry/loaders.py
src/fungal_model/registry/store.py
```

Add toy registry fixtures:

```text
data_registry/registry_index.yml
data_registry/fungi/fungi.yml
data_registry/enzymes/enzyme_classes.yml
data_registry/substrates/substrates.yml
data_registry/environments/environments.yml
data_registry/processes/process_compatibility.yml
data_registry/parameters/parameter_records.yml
```

Do not add real biological records yet. Use toy/fake records clearly marked as test/development.

## R1 tests

- load registry index;
- load toy fungus record;
- load toy substrate record;
- load toy environment record;
- load toy enzyme class record;
- load toy process compatibility record;
- load exact/range/distribution/unknown `ValueSpec`;
- duplicate record IDs fail;
- unknown record ID fails;
- invalid range fails;
- scientific mode rejects range parameters;
- exploratory mode accepts range parameters.

## R1 definition of done

The registry can load toy records and classify exact/range/distribution/unknown values without building a model.

---

# Part 11: R2 modelability report

After R1, implement `assess_modelability`.

Do not implement range simulation yet.

R2 is complete when FungMod can answer:

```text
This case is modelable / exploratory / underparameterized / unsupported
```

using toy registry records.

---

# Part 12: R3 plug-and-play case builder

After R2, implement a case builder that converts a modelable registry case into a `ModelConfig`.

This should use existing `run_configured_model`.

Do not add real biology yet. Use toy cellulase-cellulose-like records to test the flow.

---

# Part 13: R4 exploratory ensemble simulation

After R3, implement sampling over `ValueSpec` ranges/distributions and batch running configs.

This is the point where FungMod starts becoming genuinely Atmodeller-like in the sense of accepting ranges and producing output distributions.

---

# When real data and biology enter

Only after R1-R2 are complete should you insert the first real capability records.

Only after R3-R4 are complete should you run range-based exploratory simulations.

The first real biology process should still be driven by a selected dataset, not invented in advance.

---

# Summary

The long-term plug-and-play architecture is:

```text
Registry records:
    fungi, enzymes, substrates, environments, processes, parameters, datasets

Value specs:
    exact, range, distribution, unknown, not_applicable

Modelability:
    known, uncertain, missing, incompatible

Assembly:
    registry case -> model config -> run_configured_model

Simulation:
    deterministic for exact/calibrated values
    ensemble for ranges/distributions
    failure report for missing mechanisms/parameters
```

This lets FungMod simulate cases that are sufficiently specified and honestly report uncertainty or missing data when they are not.
