# REAL-001: SABIO-RK Reaction 618 Beta-Glucosidase / Cellobiose Pilot

## Purpose

This milestone introduces the first real external kinetic-record-backed case into FungMod.

The goal is not to build a full fungal degradation model. The goal is to use the SABIO-RK Export API to fetch kinetic-law entries for Reaction 618, freeze a reproducible local source snapshot, select one suitable kinetic-law entry, normalize it into a FungMod `KineticRecord`, derive registry records from it, and run the first real homogeneous Michaelis-Menten registry case if the selected entry contains sufficient parameters.

This milestone is the bridge from toy registry records to one real curated enzyme-kinetics case.

## Scientific scope

Reaction:

```text
SABIO-RK Reaction ID: 618
Reaction equation: Cellobiose + H2O = 2 beta-D-Glucose
```

This is a soluble enzyme-kinetics case. It should map to:

```text
process_type: homogeneous_michaelis_menten
```

It must not be treated as whole-fungus growth, cellulose surface degradation, enzyme secretion, fungal uptake, biomass dynamics, oxygen limitation, or PET degradation.

The biological interpretation is:

```text
A selected beta-glucosidase kinetic-law entry for cellobiose hydrolysis,
not a full fungus/substrate/environment degradation model.
```

## SABIO-RK API facts supplied by the user

Base URL:

```text
https://sabio.h-its.org/export-api/sabio/
```

No authentication required.

Rate limit:

```text
60 requests per 60-second window per IP address
```

Kinetic-law JSON endpoint:

```text
GET /kinlaw-entry/json
GET /kinlaw-entry/json/{id}
```

Paginated endpoint query parameters:

```text
q        Solr query string
page     1-based page number
pageSize default 10, max 1000 for JSON
```

Expected JSON response structure:

```json
{
  "meta": {
    "page": 1,
    "page_size": 10,
    "total_count": 150,
    "total_pages": 15
  },
  "data": []
}
```

Relevant query fields from the API guide:

```text
EntryID
SabioReactionID
ReactionEquation
Substrate
Product
AnyRole
ECNumber
EnzymeName
EnzymeType
UniProtKB_AC
HasRecombinant
Organism
KineticLawType
ParameterType
AssociatedSpecies
pHMin
TemperatureMin
Buffer
PubMedID
Title
Author
Journal
Year
```

The initial query for this milestone must be:

```text
q=SabioReactionID:618
page=1
pageSize=1000
```

Full URL pattern:

```text
https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?q=SabioReactionID:618&page=1&pageSize=1000
```

## User-provided Reaction 618 browser facts

The SABIO-RK browser page for Reaction 618 showed:

```text
Reaction equation:
Cellobiose + H2O = 2 beta-D-Glucose

Compounds:
Cellobiose     substrate
H2O            substrate
beta-D-Glucose product

External reaction links:
KEGG Reaction R00026
MetaNetX MNXR146826

Kinetic-law entries: 29

Organism counts:
Phanerochaete chrysosporium: 6
Oryza sativa: 14
Hordeum vulgare: 9

EC number counts:
3.2.1.21: 25
3.2.1.74: 2
3.2.1.25: 1

Enzyme name counts:
beta-glucosidase: 25
glucan 1,4-beta-glucosidase: 2
beta-mannosidase: 1

Enzyme type:
mutant: 15
wildtype: 14

Kinetic-law type:
Michaelis-Menten: 20
Michaelis-Menten (pH-dependent): 8

Parameter types:
Km
concentration
kcat

pH:
5.0: 10
4.0: 9
6.5: 3

Temperature:
30.0 °C: 24
37.0 °C: 2
35.0 °C: 1

Visible PubMed IDs:
18023045
18308333
19766588

Visible paper title:
Role of subsite +1 residues in pH dependence and catalytic activity of the glycoside hydrolase family 1 beta-glucosidase BGL1A from the basidiomycete Phanerochaete chrysosporium
```

These browser facts are not enough by themselves to create parameter records. They only justify Reaction 618 as a good first target. The actual registry values must come from one selected kinetic-law entry fetched/exported through the API.

## Core architecture rule

Do not make FungMod depend on live SABIO-RK calls during normal model runs, tests, or notebooks.

Use this pipeline:

```text
SABIO-RK live API
    -> raw local source snapshot
    -> selected raw kinetic-law entry
    -> curated FungMod KineticRecord
    -> registry records
    -> modelability report
    -> ModelConfig generation
    -> run_configured_model
```

Live API access is allowed only in fetch scripts. Tests must use local fixtures.

## Non-goals

Do not do any of the following in this milestone:

```text
bulk-import SABIO-RK
scrape HTML unless the API fails and this is explicitly reported
invent missing Km, kcat, Vmax, concentration, pH, temperature, or units
add full fungus growth
add enzyme secretion
add product uptake
add biomass growth
add oxygen limitation
add PET chemistry
add cellulose surface morphology
add cellulose crystallinity/surface area evolution
claim validation against time-course observations
depend on the live SABIO-RK API in tests
```

## Directory layout

Create:

```text
data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/
    README.md
    source_notes.md
    raw/
        kinlaw_entries_reaction_618.json
        fetch_metadata.json
        selected_kinlaw_entry_<EntryID>.json
        selection_report.json
    curated/
        kinetic_record.yml
```

Add scripts:

```text
scripts/fetch_sabiork_kinlaw_entries.py
scripts/select_sabiork_kinlaw_entry.py
```

Add source modules as needed:

```text
src/fungal_model/data/sabiork.py
src/fungal_model/data/kinetic_records.py
src/fungal_model/data/kinetic_record_loaders.py
```

Add tests:

```text
tests/test_sabiork_parser.py
tests/test_kinetic_record_loading.py
tests/test_sabiork_reaction_618_registry_case.py
```

Add notebook:

```text
notebooks/06_sabiork_reaction_618_beta_glucosidase.ipynb
```

Update progress file after every phase:

```text
foundation_progress/REAL_001_SABIO_RK_PROGRESS.md
```


# Phase REAL-001A: Fetch raw SABIO-RK Reaction 618 kinetic-law export

## Goal

Fetch and freeze the raw Reaction 618 kinetic-law export.

## Required script

Create:

```text
scripts/fetch_sabiork_kinlaw_entries.py
```

Required command:

```bash
python scripts/fetch_sabiork_kinlaw_entries.py \
  --query "SabioReactionID:618" \
  --output-dir data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw
```

The script must call:

```text
https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json
```

with:

```text
q=SabioReactionID:618
page=1
pageSize=1000
```

## Required output

```text
raw/kinlaw_entries_reaction_618.json
raw/fetch_metadata.json
```

`fetch_metadata.json` must include:

```json
{
  "base_url": "https://sabio.h-its.org/export-api/sabio",
  "endpoint": "/kinlaw-entry/json",
  "query": "SabioReactionID:618",
  "page": 1,
  "pageSize": 1000,
  "fetched_at": "...",
  "http_status": 200,
  "total_count": 29
}
```

If `total_count` differs from 29, do not fail automatically. Record a warning because the database may have changed.

## Required behavior

- Respect the 60 requests/minute API limit.
- Make only one request for this phase unless pagination says more pages exist.
- Validate the response contains `meta` and `data`.
- Validate that entries correspond to `SabioReactionID:618` if that field is present.
- If schema differs, save the raw response and fail clearly.
- Do not normalize or clean values in this phase.
- Do not call this script in tests.

## Tests

Tests must be offline. They may test helper functions using local fixture JSON, but they must not call the live API.

## Phase done when

- raw export is saved;
- fetch metadata is saved;
- no registry files are modified except progress file;
- progress file is updated.


# Phase REAL-001B: Parse export and select one kinetic-law entry

## Goal

Select one best candidate kinetic-law entry from the saved raw export.

## Required module

Create or extend:

```text
src/fungal_model/data/sabiork.py
```

Implement:

```python
load_sabiork_kinlaw_export(path: str | Path) -> SabioRKExport
select_reaction_618_candidate(export: SabioRKExport) -> SabioRKSelection
```

Use simple dataclasses or typed dictionaries. Do not overbuild.

## Selection rules

Select one entry using these rules, in order:

1. Entry belongs to `SabioReactionID:618` if the field exists.
2. Reaction equation contains `Cellobiose` and `beta-D-Glucose` if available.
3. Enzyme name contains `beta-glucosidase`.
4. EC number includes `3.2.1.21`.
5. Substrate includes `Cellobiose`.
6. Product includes `beta-D-Glucose` or `glucose`.
7. Prefer `KineticLawType == "Michaelis-Menten"`.
8. Avoid `Michaelis-Menten (pH-dependent)` for the first deterministic pilot if plain Michaelis-Menten entries are available.
9. Prefer `EnzymeType == wildtype`.
10. Prefer pH 5.0.
11. Prefer temperature 30 °C.
12. Prefer entries with both `Km` and `kcat`.
13. If `kcat` is absent but `Vmax` is present, accept only if units and enzyme/concentration context are clear.
14. Prefer entries with PubMedID, title, year, journal, and authors.

## Required output

```text
raw/selected_kinlaw_entry_<EntryID>.json
raw/selection_report.json
```

`selection_report.json` must include:

```json
{
  "selected_entry_id": "...",
  "selection_reason": "...",
  "missing_required_fields": [],
  "warnings": [],
  "rejected_candidates": [
    {
      "entry_id": "...",
      "reason": "..."
    }
  ]
}
```

If no complete candidate exists, select the best incomplete candidate and record all missing fields. Do not invent missing values.

## Tests

Create:

```text
tests/test_sabiork_parser.py
```

Required tests:

- valid export loads;
- missing `meta` or `data` fails;
- selector prefers beta-glucosidase over unrelated enzyme;
- selector prefers EC 3.2.1.21;
- selector prefers plain Michaelis-Menten over pH-dependent when available;
- selector prefers wildtype over mutant when otherwise equal;
- selector records missing `kcat` or `Vmax`;
- selection report is JSON-safe.

## Phase done when

- parser tests pass;
- selected raw entry is written;
- selection report is written;
- progress file is updated.


# Phase REAL-001C: KineticRecord schema and curated record

## Goal

Normalize the selected raw kinetic-law entry into a FungMod `KineticRecord`.

## Required modules

Create:

```text
src/fungal_model/data/kinetic_records.py
src/fungal_model/data/kinetic_record_loaders.py
```

Expose from:

```text
src/fungal_model/data/__init__.py
```

At minimum:

```python
KineticRecord
KineticParameter
load_kinetic_record
```

## Required dataclasses

Implement minimal explicit dataclasses:

```python
KineticRecord
KineticReaction
KineticEnzyme
KineticLaw
KineticParameter
KineticConditions
KineticReference
KineticCuration
```

Each must support:

```python
to_dict()
validate()
```

## Curated YAML

Create:

```text
data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/curated/kinetic_record.yml
```

Required shape:

```yaml
kind: kinetic_record
record_id: sabiork_reaction_618_selected_kinetic_law
source_database: SABIO-RK
source_reaction_id: "618"
source_kinetic_law_id: "<selected EntryID>"
source_url: "https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json/<selected EntryID>"

reaction:
  equation: "Cellobiose + H2O = 2 beta-D-Glucose"
  substrates:
    - Cellobiose
    - H2O
  products:
    - beta-D-Glucose
  external_links:
    kegg_reaction: R00026
    metanetx: MNXR146826

enzyme:
  name: beta-glucosidase
  ec_number: "3.2.1.21"
  organism: "<from selected entry>"
  enzyme_type: "<wildtype/mutant/unknown>"
  uniprot_id: "<if available>"
  expressed_in: "<if available>"

kinetic_law:
  type: "Michaelis-Menten"
  formula: "<formula if available>"
  notes: "<notes if available>"

parameters:
  - symbol: Km_cellobiose
    parameter_type: Km
    value: <number or null>
    units: "<converted or original compatible units>"
    original_value: <raw number or null>
    original_units: "<raw units>"
    source_field: SABIO-RK parameter Km
  - symbol: kcat_cellobiose
    parameter_type: kcat
    value: <number or null>
    units: "<converted or expected units>"
    original_value: <raw number or null>
    original_units: "<raw units>"
    source_field: SABIO-RK parameter kcat

conditions:
  temperature:
    value: <kelvin value or null>
    units: kelvin
    original_value: <raw value or null>
    original_units: "<raw units>"
  ph:
    value: <pH value or null>
    units: dimensionless
  buffer:
    value: "<buffer string or null>"
    units: null

reference:
  title: "<paper title>"
  pubmed_id: "<PMID if available>"
  doi: "<DOI if available>"
  year: <year if available>
  authors:
    - "<author names if available>"
  journal: "<journal if available>"

curation:
  curated_by: Felix Laga
  curation_date: "<current date>"
  method: "Fetched via SABIO-RK Export API and normalized into FungMod KineticRecord."
  notes: "First real SABIO-RK-backed kinetic pilot. Not a bulk import."
```

## Validation rules

- `kind == kinetic_record`;
- source database required;
- source reaction ID required;
- source kinetic law ID required;
- reaction equation required;
- at least one substrate and one product required;
- enzyme name and EC number required;
- kinetic law type required;
- every parameter must have symbol, parameter type, units, original units, source field, and either value or explicit null;
- null parameter values are allowed but must become unknown `ValueSpec`s downstream;
- original values/units must be preserved;
- pH and temperature must be preserved if present;
- reference metadata must be preserved if present;
- no silent unit conversion without original value/unit.

## Tests

Create:

```text
tests/test_kinetic_record_loading.py
```

Required tests:

- valid curated kinetic record loads;
- missing source database fails;
- missing source kinetic law ID fails;
- missing reaction equation fails;
- missing parameter units fails;
- null parameter value is allowed;
- original units are preserved;
- `to_dict()` is JSON-safe.

## Phase done when

- kinetic record loader exists;
- curated kinetic record loads;
- tests pass;
- progress file is updated.


# Phase REAL-001D: Registry integration

## Goal

Translate the curated kinetic record into FungMod registry records.

## Required records

Add or extend the registry files. Do not remove toy records.

### Enzyme-source pseudo-fungus/source record

```yaml
record_id: sabiork_beta_glucosidase_source
name: SABIO-RK Reaction 618 beta-glucosidase source
maturity: literature_processed
enzyme_classes:
  - beta_glucosidase
assimilable_products: []
provenance:
  source_database: SABIO-RK
  source_reaction_id: "618"
  selected_kinlaw_entry_id: "<EntryID>"
notes: >
  Enzyme-source pseudo-record for a purified or recombinant enzyme kinetics case.
  This is not a whole-fungus growth model and must not imply secretion, uptake,
  biomass growth, or organism-level degradation.
```

### Enzyme class

```yaml
record_id: beta_glucosidase
name: beta-glucosidase
maturity: literature_metadata
target_bond_classes:
  - beta_1_4_glycosidic
compatible_substrate_classes:
  - cellobiose
compatible_processes:
  - homogeneous_michaelis_menten
provenance:
  source_database: SABIO-RK
  source_reaction_id: "618"
  selected_kinlaw_entry_id: "<EntryID>"
notes: First real enzyme-class registry record for soluble beta-glucoside hydrolysis; not full cellulose degradation.
```

### Substrate

```yaml
record_id: cellobiose
name: Cellobiose
maturity: literature_metadata
substrate_class: cellobiose
physical_state: dissolved
bond_classes:
  - beta_1_4_glycosidic
products:
  - beta_D_glucose
properties: {}
provenance:
  source_database: SABIO-RK
  source_reaction_id: "618"
  kegg_reaction: R00026
  metanetx: MNXR146826
notes: Soluble disaccharide substrate for first SABIO-RK kinetic pilot.
```

### Environment

If pH and temperature exist:

```yaml
record_id: sabiork_reaction_618_selected_conditions
name: SABIO-RK Reaction 618 selected assay conditions
maturity: literature_processed
conditions:
  temperature:
    kind: exact
    value: <kelvin value>
    units: kelvin
    source: SABIO-RK Reaction 618 selected kinetic law
    confidence_level: literature_curated
    notes: "Converted from original SABIO-RK temperature; original stored in KineticRecord."
  ph:
    kind: exact
    value: <pH value>
    units: dimensionless
    source: SABIO-RK Reaction 618 selected kinetic law
    confidence_level: literature_curated
    notes: "SABIO-RK assay pH."
provenance:
  source_database: SABIO-RK
  source_reaction_id: "618"
  selected_kinlaw_entry_id: "<EntryID>"
notes: Assay conditions for first real kinetic pilot.
```

If temperature or pH is missing, use `kind: unknown`. Do not use `kind: exact` with a null value.

### Process compatibility

```yaml
record_id: beta_glucosidase_cellobiose_homogeneous_mm
name: beta-glucosidase on cellobiose homogeneous Michaelis-Menten
maturity: literature_metadata
enzyme_class: beta_glucosidase
substrate_class: cellobiose
required_bond_classes:
  - beta_1_4_glycosidic
process_type: homogeneous_michaelis_menten
required_parameters:
  - Km_cellobiose
  - kcat_cellobiose
parameter_roles:
  <role_expected_by_HomogeneousMichaelisMentenFactory_for_Km>: Km_cellobiose
  <role_expected_by_HomogeneousMichaelisMentenFactory_for_kcat_or_rate>: kcat_cellobiose
product_map_required: true
provenance:
  source_database: SABIO-RK
  source_reaction_id: "618"
  selected_kinlaw_entry_id: "<EntryID>"
notes: First non-toy homogeneous enzyme-kinetics compatibility record.
```

Important: inspect the existing `HomogeneousMichaelisMentenFactory` and use exact role names/config fields it expects. Do not guess.

### Parameter records

If value exists:

```yaml
value:
  kind: exact
  value: <numeric value>
  units: "<FungMod-compatible units>"
  source: SABIO-RK Reaction 618 selected kinetic law
  confidence_level: literature_curated
  notes: "Curated from SABIO-RK. Original value and units preserved in kinetic_record.yml."
```

If value is missing:

```yaml
value:
  kind: unknown
  units: "<expected units>"
  source: SABIO-RK Reaction 618 selected kinetic law
  confidence_level: missing_from_selected_entry
  notes: "Parameter required by FungMod but absent in selected SABIO-RK kinetic law."
```

Do not invent values.

## Tests

Add to:

```text
tests/test_sabiork_reaction_618_registry_case.py
```

Required tests:

- registry loads the Reaction 618 enzyme-source record;
- registry loads beta-glucosidase enzyme class;
- registry loads cellobiose substrate;
- registry loads selected conditions;
- registry loads homogeneous Michaelis-Menten compatibility record;
- parameter records preserve exact or unknown `ValueSpec`s;
- modelability is `modelable` if all required parameters are exact;
- modelability is `underparameterized` if any required value is unknown;
- provenance includes SABIO-RK Reaction 618 and selected EntryID.

## Phase done when

- registry loads all records;
- modelability works;
- tests pass;
- progress file is updated.


# Phase REAL-001E: Homogeneous Michaelis-Menten registry case builder

## Goal

Allow the registry case builder and, optionally, ensemble screen to run the Reaction 618 case.

## Requirements

- Do not break existing surface-catalysis tests.
- Add process-specific builder/assembler logic instead of one large conditional.
- Support `process_type: homogeneous_michaelis_menten`.
- Reuse the existing `HomogeneousMichaelisMentenFactory` config shape.
- Deterministic builder may build only when required parameters are exact.
- Range/distribution parameters require exploratory ensemble.
- Unknown required parameters block building.
- Output metadata must preserve SABIO-RK provenance.

## Tests

Extend:

```text
tests/test_sabiork_reaction_618_registry_case.py
```

Required tests:

- builder emits valid homogeneous Michaelis-Menten `ModelConfig` if all required parameters are exact;
- generated config runs through `run_configured_model`;
- substrate decreases and product increases;
- output bundle contains SABIO-RK source metadata;
- deterministic builder refuses range/distribution parameters;
- deterministic builder refuses unknown parameters.

If selected SABIO-RK entry lacks required exact values, do not force a deterministic run. The expected result is underparameterized.

## Phase done when

- deterministic run works if data are complete;
- or underparameterized status is correctly reported if data are incomplete;
- tests pass;
- progress file is updated.


# Phase REAL-001F: Notebook and final reporting

## Goal

Create a researcher-facing notebook that demonstrates the Reaction 618 pilot.

## Notebook

Create:

```text
notebooks/06_sabiork_reaction_618_beta_glucosidase.ipynb
```

Required sections:

1. Title and warning:

```text
SABIO-RK Reaction 618 beta-glucosidase pilot

This is a first curated kinetic-record pilot, not a validated full fungal degradation model.
```

2. Load registry:

```python
from pathlib import Path
from fungal_model.registry import load_registry

ROOT = Path("..").resolve() if Path.cwd().name == "notebooks" else Path(".").resolve()
registry = load_registry(ROOT / "data_registry" / "registry_index.yml")
```

3. Load kinetic record:

```python
from fungal_model.data import load_kinetic_record

record = load_kinetic_record(
    ROOT / "data" / "kinetic_records" / "sabiork" / "case_001_reaction_618_beta_glucosidase" / "curated" / "kinetic_record.yml"
)
record.to_dict()
```

4. Assess modelability:

```python
from fungal_model.screening import assess_modelability

report = assess_modelability(
    fungus_id="sabiork_beta_glucosidase_source",
    substrate_id="cellobiose",
    environment_id="sabiork_reaction_618_selected_conditions",
    registry=registry,
    mode="scientific",
)

print(report.summary())
```

5. Run deterministic config only if modelable:

```python
from fungal_model.screening import build_model_config_from_registry_case
from fungal_model.workflows import run_configured_model
import yaml

if report.status == "modelable":
    output_dir = ROOT / "outputs" / "sabiork_reaction_618_beta_glucosidase"

    config = build_model_config_from_registry_case(
        fungus_id="sabiork_beta_glucosidase_source",
        substrate_id="cellobiose",
        environment_id="sabiork_reaction_618_selected_conditions",
        registry=registry,
        mode="scientific",
        output_directory=str(output_dir),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = output_dir / "model_config.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")

    result = run_configured_model(config_path, output_dir=output_dir / "bundle")
    result.plot_states(output_dir / "states.png")
else:
    print(report.to_dict())
```

6. Optional exploratory screen if range support is implemented.

7. Limitations section:

```text
- enzyme-only kinetic pilot;
- not whole fungus;
- no secretion;
- no uptake;
- no biomass growth;
- no validation against time-course observations;
- parameters only valid for selected SABIO-RK conditions.
```

## Notebook tests

- notebook imports package code;
- notebook does not define core classes or rate laws;
- at least registry and kinetic-record loading cells are smoke-tested.

## Phase done when

- notebook exists;
- notebook can be opened and run through modelability section;
- deterministic run section works if the selected entry is complete;
- progress file is updated;
- Codex suggests next phase.


# Progress file requirement

Codex must update this file after every phase:

```text
foundation_progress/REAL_001_SABIO_RK_PROGRESS.md
```

The file must include:

```text
Status:
Current phase:
Completed phases:
Incomplete phases:
Files added:
Files changed:
Tests added:
Tests run:
Test results:
Selected SABIO-RK EntryID:
Selected organism:
Selected kinetic law type:
Selected parameters:
Modelability result:
Deterministic run result:
Exploratory ensemble result:
Architecture debt added:
Data debt added:
Known limitations:
Next recommended phase:
```

Do not claim the full milestone is complete until every phase is complete or explicitly marked as intentionally deferred.

# Required final response format for Codex

After every Codex run, respond with:

```text
1. Phase implemented
2. Summary of changes
3. Files added/changed
4. Data fetched or generated
5. Tests added
6. Tests run and exact results
7. Architecture debt added
8. Data debt added
9. What remains incomplete
10. Updated progress-file status
11. Next recommended phase
```

Do not report success unless tests were run or explicitly explain why they could not be run.

# Global tests by phase

Minimum focused tests:

```bash
pytest tests/test_sabiork_parser.py
pytest tests/test_kinetic_record_loading.py
pytest tests/test_sabiork_reaction_618_registry_case.py
```

Regression tests that should continue passing:

```bash
pytest tests/test_registry_loading.py
pytest tests/test_modelability_report.py
pytest tests/test_registry_case_builder.py
pytest tests/test_registry_ensemble_simulation.py
```

Full suite:

```bash
pytest
```

If full pytest fails, report exact failures. Do not hide them.

# Final definition of done for REAL-001

REAL-001 is done only when:

```text
- raw SABIO-RK Reaction 618 kinlaw export is saved locally;
- selection report identifies one selected kinetic-law entry;
- curated kinetic_record.yml exists and loads;
- registry records exist and load;
- modelability reports modelable or underparameterized honestly;
- homogeneous Michaelis-Menten case builder supports the case if required values are exact;
- deterministic run works if data are complete;
- exploratory ensemble works if range variant is implemented;
- notebook exists;
- tests pass or failures are honestly reported;
- progress file clearly states what is complete and incomplete;
- no unsupported whole-fungus claims are made.
```
