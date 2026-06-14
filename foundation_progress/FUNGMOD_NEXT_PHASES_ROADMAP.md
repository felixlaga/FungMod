# FungMod Roadmap: From Curated Virtual Experiments to General Fungus/Substrate Screening

## Purpose

This document defines the next major phases for FungMod after cleanup, API-001, ENV-001, DATA-002, BIO-001, and VALIDATION-001.

The goal is to make FungMod usable for researchers who want to define a fungus or enzyme source, a substrate, and one or more environments, then receive scientifically honest degradation curves and output tables.

The central goal remains:

```text
FungMod exists to let researchers run mechanistic virtual experiments of fungi or enzyme systems degrading substrates across environments, producing clean time-series and summary tables of substrate loss, product release, degradation rates, threshold times, uncertainty, provenance, and limitations.
```

This roadmap is designed to prevent uncontrolled biology expansion.

FungMod should not become a pile of half-ingested datasets or half-implemented mechanisms.

The next phases should build the missing infrastructure needed for reliable biology.

Status note: this roadmap contains phase gates that predate some current
registry-backed BIO work. Before treating any phase as open or complete, verify
against `progress.md`, code, and tests. Reconciling roadmap status is a Phase 1
Task 2 responsibility; this document should not be used to override the current
biology rule in `AGENTS.md`.

---

# Current project status

As of this roadmap, FungMod has:

```text
- central virtual-experiment project directive;
- registry-backed VirtualExperiment API;
- EnvironmentGrid API;
- standard output tables;
- versioned output schema/data dictionary;
- SABIO-RK Reaction 618 enzyme-only homogeneous Michaelis-Menten pilot;
- DATA-002 multi-entry SABIO-RK Reaction 618 parameter-range curation;
- BIO-001 exploratory cellulose-like surface-degradation pilot;
- provenance/limitations/missing-parameter/suggested-experiment tables;
- tests for Reaction 618, homogeneous MM, environment grids, DATA-002, BIO-001, notebooks, and virtual-experiment outputs.
```

The current API can run registered cases from internal registry IDs.

Example:

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_registry(
    fungi=["sabiork_beta_glucosidase_source"],
    substrates=["cellobiose"],
    environments=["sabiork_reaction_618_selected_conditions"],
)

result = study.simulate(mode="exploratory", n_samples=128)
result.write_tables()
```

This is good, but it is still developer-facing.

The final researcher goal is closer to:

```python
study = FungMod.virtual_experiment(
    fungi=["Pleurotus ostreatus"],
    substrates=["cellulose film"],
    environments=FungMod.environment_grid(
        temperature_C=[20, 25, 30],
        ph=[4.5, 5.0, 5.5],
        oxygen="aerobic",
    ),
)

result = study.simulate(mode="exploratory", n_samples=1000)
result.write_tables("outputs/")
```

The next phases bridge that gap.

---

# What rule governs biology work now?

## Short answer

Biology may be added only when the mechanism is explicitly implemented,
provenance-backed, maturity-labelled, covered by tests, and honest about
assumptions and limitations. Unsupported, invented, silently guessed, or falsely
validated biology is forbidden.

The roadmap phase gate below still needs reconciliation against current BIO-001
and BIO-002 work in Phase 1 Task 2. Until that reconciliation is complete,
verify the actual repository state from `progress.md`, code, and tests before
deciding whether a specific biology task is unblocked.

## Why not immediately?

The current codebase can simulate registered cases, but arbitrary researcher-defined fungus/substrate cases still need:

```text
- human-name and alias resolution;
- SABIO-RK-backed reaction/product discovery;
- local source snapshots;
- curated record generation;
- product-map generation;
- state-role mapping;
- config-driven case assembly;
- public scientific-mode simulation;
- environment-response distinction;
- no-new-biology readiness gates.
```

Adding unsupported biology before this risks creating hardcoded one-off cases.

## When biology can proceed

Biology can proceed only when the specific proposal satisfies the current
biology rule and the applicable readiness gate:

```text
A researcher can choose a known fungus/source ID or alias,
choose a known substrate ID or alias,
choose environments or an EnvironmentGrid,
and FungMod can:

1. resolve the names;
2. discover or use known reaction/product/kinetic records;
3. assemble the correct process model from registry/config schemas;
4. run scientific or exploratory simulation;
5. output degradation curves and tables;
6. state missing mechanisms or parameters honestly.
```

Only then should the proposed biology be added or extended.

---

# Phase 1: SOURCE-001 — SABIO-RK Reaction/Product Discovery Adapter

## Goal

Build a controlled SABIO-RK source adapter that can fetch, freeze, parse, and propose FungMod records from SABIO-RK kinetic-law entries.

This phase does not replace the local FungMod registry.

SABIO-RK is an external source.

FungMod still needs a local curated cache/registry for reproducibility, simulation semantics, provenance, and review.

Correct architecture:

```text
SABIO-RK API
-> raw frozen snapshot
-> parser/normalizer
-> curated kinetic/reaction records
-> proposed FungMod registry/product-map records
-> human/review gate
-> simulation registry
```

Incorrect architecture:

```text
VirtualExperiment.simulate()
-> live SABIO-RK API call
-> build model directly from raw API response
```

Live APIs must not be runtime dependencies for simulation.

## Why SOURCE-001 matters

The user wants SABIO-RK to fetch products, reactions, enzymes, and parameters so FungMod does not need a giant manually maintained database.

That is partly correct.

SABIO-RK can supply:

```text
- reaction equation;
- substrates;
- products;
- enzyme names;
- EC numbers;
- organism/source metadata;
- kinetic-law type;
- Km, kcat, Vmax, concentrations, pH, temperature, buffer;
- publication metadata;
- external reaction/compound identifiers when available.
```

But SABIO-RK does not supply everything FungMod needs:

```text
- whole-fungus growth model;
- enzyme secretion model;
- product uptake;
- biomass yield;
- substrate geometry/accessibility;
- state-role semantics;
- simulation time grids;
- allowed-use policy;
- environment-response model;
- output schema interpretation.
```

Therefore SABIO-RK should feed FungMod, not replace FungMod.

## Required SOURCE-001 API

Add a source adapter API, likely under:

```text
src/fungal_model/sources/sabiork/
```

or:

```text
src/fungal_model/data/sabiork_source.py
```

Suggested developer API:

```python
from fungal_model.sources.sabiork import SabioRKSource

source = SabioRKSource(cache_dir="data/source_snapshots/sabiork")

snapshot = source.fetch_kinlaw_entries(
    query='SabioReactionID:618',
    refresh=False,
)

reaction_records = source.parse_reaction_records(snapshot)
proposal = source.propose_fungmod_records(reaction_records)
proposal.write("data/proposed_records/sabiork/reaction_618/")
```

There should also be a CLI/script:

```bash
python scripts/fetch_sabiork_kinlaw_entries.py \
  --query "SabioReactionID:618" \
  --output-dir data/source_snapshots/sabiork/reaction_618
```

The existing fetch script is a good start. SOURCE-001 should integrate it into the source-adapter story, not bypass it.

## Required SOURCE-001 outputs

For a SABIO-RK reaction or query, write:

```text
raw/
    kinlaw_entries_<query>.json
    fetch_metadata.json

curated/
    reaction_records.json
    compound_roles.csv
    kinetic_law_entries.csv
    parameters.csv
    publications.csv
    proposed_product_maps.yml
    proposed_parameter_records.yml
    proposed_process_compatibility.yml
    source_adapter_report.md
```

These are proposed/curated source files, not automatically trusted scientific registry records.

## Required SOURCE-001 behavior

SOURCE-001 must:

```text
1. Use local snapshots by default.
2. Fetch live SABIO-RK data only when explicitly requested.
3. Never call the live API during simulation.
4. Never call the live API during tests.
5. Preserve raw API responses.
6. Preserve original units and values.
7. Preserve EntryID and source metadata.
8. Extract reaction participants and roles.
9. Extract products and stoichiometry when available.
10. Extract kinetic laws and parameters.
11. Extract pH, temperature, buffer, organism, enzyme, EC number, publication metadata.
12. Create proposed FungMod records, not silently committed records.
13. Produce inclusion/exclusion reports.
14. Fail clearly if API is unavailable.
```

## Required SOURCE-001 tests

Add tests such as:

```text
tests/test_sabiork_source_adapter.py
```

Required tests:

```text
- parses a local fixture without network access;
- extracts substrates and products from Reaction 618;
- extracts EC number and enzyme name;
- extracts Km and kcat where present;
- preserves pH and temperature;
- writes proposed product-map records;
- writes proposed parameter records;
- does not mutate the simulation registry;
- network refresh is not used in tests;
- invalid/missing fields are reported, not guessed.
```

## SOURCE-001 acceptance criteria

SOURCE-001 is complete when:

```text
- SABIO-RK entries can be fetched/frozen or loaded from cache;
- reaction products and substrates can be extracted into proposed product maps;
- kinetic parameters can be extracted into proposed parameter records;
- provenance is preserved;
- tests do not require live API;
- no simulation depends on live SABIO-RK;
- proposed records are reviewable before entering the registry.
```

---

# Phase 2: RESOLVE-001 — Human-Readable Name and Alias Resolver

## Goal

Allow researchers to define virtual experiments using human-readable names instead of internal registry IDs.

Current API requires:

```python
fungi=["sabiork_beta_glucosidase_source"]
substrates=["cellobiose"]
environments=["sabiork_reaction_618_selected_conditions"]
```

Future API should allow:

```python
fungi=["beta-glucosidase source"]
substrates=["cellobiose"]
environments=["30C_pH5_aerobic"]
```

and eventually:

```python
fungi=["Pleurotus ostreatus"]
substrates=["cellulose film"]
```

## Required resolver concepts

Add a resolver layer that can resolve:

```text
fungus/source names
substrate names
enzyme class names
environment names
reaction names/equations
EC numbers
external database IDs
aliases
```

Suggested module:

```text
src/fungal_model/api/resolver.py
```

or:

```text
src/fungal_model/registry/resolver.py
```

Suggested API:

```python
resolver = RegistryResolver(registry)

resolver.resolve_fungus("sabiork_beta_glucosidase_source")
resolver.resolve_fungus("beta-glucosidase source")
resolver.resolve_substrate("cellobiose")
resolver.resolve_environment("30C_pH5_aerobic")
resolver.resolve_enzyme_class("EC 3.2.1.21")
```

## Required registry additions

Registry records should support:

```text
canonical_id
display_name
scientific_name
aliases
external_refs
taxon_id, if applicable
ec_number, if applicable
database_ids
```

Do not implement fuzzy matching first.

Start with exact canonical IDs and aliases.

Then add case-insensitive exact matching.

Only later add fuzzy matching with ambiguity reports.

## Required resolver behavior

If one match exists:

```text
return resolved ID + record + confidence
```

If multiple matches exist:

```text
raise AmbiguousResolutionError with candidate list
```

If no match exists:

```text
raise ResolutionError with suggestions:
- available close aliases if safe;
- source adapter suggestions;
- "not in registry" message.
```

Never silently choose among multiple biological records.

## Required RESOLVE-001 tests

Add tests:

```text
tests/test_registry_resolver.py
```

Required:

```text
- resolve exact ID;
- resolve alias;
- resolve case-insensitive alias;
- fail on unknown name;
- fail on ambiguous alias;
- resolve substrate;
- resolve environment;
- resolve enzyme class or EC number if registry supports it;
- VirtualExperiment.from_registry can optionally use resolver.
```

## RESOLVE-001 acceptance criteria

RESOLVE-001 is complete when:

```text
- researcher-facing code no longer requires memorized internal IDs for common cases;
- ambiguous biological names fail explicitly;
- aliases are registry data, not hardcoded Python dictionaries;
- resolver is tested;
- VirtualExperiment can use resolver without weakening exact ID behavior.
```

---

# Phase 3: ASSEMBLY-001 — Config-Driven Case Assembly

## Goal

Move case-specific model assembly information out of Python branches and into registry/config schemas.

Current risk:

```text
case_builder.py hardcodes Reaction 618 and BIO-001 state names, product-map names, and time-grid defaults.
```

That does not scale.

For arbitrary reactions and substrates, state roles, products, stoichiometry, and time grids must be data-driven.

## Required assembly schemas

Add or formalize a case-assembly schema.

Possible file:

```text
data_registry/case_templates/case_templates.yml
```

or add fields to process compatibility records.

Minimum required fields:

```yaml
case_template_id: homogeneous_mm_cellobiose_to_glucose
process_type: homogeneous_michaelis_menten

state_roles:
  substrate: cellobiose_concentration
  product: beta_D_glucose_concentration
  enzyme: beta_glucosidase_concentration

product_map:
  substrate_state: cellobiose_concentration
  product_state: beta_D_glucose_concentration
  stoichiometric_yield: 2.0

time_grid:
  start: 0
  stop: 48
  points: 200
  units: hour

observables:
  substrate_remaining:
    state: cellobiose_concentration
    units: mM
  product_release:
    state: beta_D_glucose_concentration
    units: mM
```

For surface cases:

```yaml
case_template_id: surface_cellulose_degradation
process_type: surface_catalysis

state_roles:
  substrate: solid_substrate_remaining
  product: soluble_product_amount
  accessibility_proxy: accessible_site_fraction_proxy

time_grid:
  start: 0
  stop: 168
  points: 300
  units: hour
```

## What ASSEMBLY-001 must remove

It should remove or reduce:

```text
hardcoded Reaction 618 state names
hardcoded BIO-001 state names
hardcoded product-state naming
hardcoded time-grid defaults
hardcoded product-map identity in generic builders
```

Some default fallback can exist, but production cases should be template-driven.

## Required ASSEMBLY-001 behavior

Given:

```text
fungus/source record
substrate record
environment record
process compatibility record
case template
parameter records
```

FungMod should assemble:

```text
ModelConfig
state variables
initial conditions
process parameters
product maps
time grid
output state roles
```

without adding a new Python branch for every reaction.

## Required ASSEMBLY-001 tests

Add tests:

```text
tests/test_registry_case_templates.py
tests/test_config_driven_case_assembly.py
```

Required:

```text
- Reaction 618 assembles from a template;
- BIO-001 assembles from a template;
- missing template fails clearly;
- invalid state role fails validation;
- invalid product map fails validation;
- time grid is read from template/config;
- no hardcoded Reaction 618 branch is needed for standard assembly;
- outputs are unchanged for existing cases except expected metadata improvements.
```

## ASSEMBLY-001 acceptance criteria

Complete when:

```text
- adding a new SABIO-RK reaction does not require editing case_builder.py for state names;
- product maps and state roles are registry/config records;
- Reaction 618 and BIO-001 still pass tests;
- output tables still use biological state roles correctly.
```

---

# Phase 4: API-003 — Researcher-Facing Virtual Experiment From Names

## Goal

Create the first real researcher-facing API that combines resolver, environment grids, registry-backed simulation, and output tables.

Target:

```python
from fungal_model import virtual_experiment, EnvironmentGrid

study = virtual_experiment(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose"],
    environments=EnvironmentGrid(
        temperature_C=[20, 25, 30],
        ph=[4.5, 5.0, 5.5],
        oxygen="aerobic",
    ),
)

result = study.simulate(mode="exploratory", n_samples=1000)
result.write_tables("outputs/study")
```

Or:

```python
from fungal_model import VirtualExperiment

study = VirtualExperiment.from_names(
    fungi=["beta-glucosidase source"],
    substrates=["cellobiose"],
    environments=["30C_pH5_aerobic"],
)
```

## Required API-003 features

```text
1. top-level convenience function or classmethod;
2. resolver integration;
3. exact error messages for unknown names;
4. ambiguity errors with candidate IDs;
5. support for EnvironmentGrid;
6. table-first outputs;
7. no live API calls during simulation;
8. optional source-discovery suggestions when records are missing;
9. public scientific and exploratory simulation modes;
10. output folder manifest.
```

## Required API-003 methods

`VirtualExperiment` or result object should expose:

```python
study.preflight(mode="scientific")
study.preflight(mode="exploratory")
study.simulate(mode="scientific")
study.simulate(mode="exploratory", n_samples=1000)

result.time_series()
result.final_metrics()
result.threshold_times()
result.sampled_parameters()
result.provenance()
result.limitations()
result.write_tables()
result.write_quicklook_plots()
```

These may read from CSVs internally.

The point is that researchers should not have to manually inspect the output folder for common queries.

## API-003 scientific mode

Public scientific mode is required.

Behavior:

```text
mode="scientific":
    exact/literature-supported values only;
    reject exploratory priors;
    reject broad ranges unless allowed for scientific use;
    run deterministic or exact-record ensemble if appropriate;
    output same table schema.

mode="exploratory":
    allow explicitly marked exploratory priors and allowed literature ranges;
    output uncertainty summaries and provenance.
```

Scientific mode must not imply validation.

Use wording like:

```text
scientific_exact_but_unvalidated
```

where appropriate.

## API-003 acceptance criteria

Complete when:

```text
- user can define a virtual experiment from aliases/names for existing records;
- user can run scientific mode when exact case is modelable;
- user can run exploratory mode with uncertainty;
- result object exposes biological tables;
- unknown/ambiguous names fail clearly;
- no live source API calls occur during simulation;
- output tables remain schema-versioned.
```

---

# Phase 5: ENV-002 — Condition-Specific Parameter Matching and Environment Response Guardrails

## Goal

Make environment screens scientifically meaningful.

ENV-001 created environment grids but treated them as metadata-only unless response laws exist.

ENV-002 should add condition-specific parameter matching.

This is safer than immediately fitting pH/temperature response curves.

## Required ENV-002 behavior

For each environment case:

```text
temperature_C
ph
oxygen
```

FungMod should attempt to select parameter records that match the environment.

Example:

```text
If a parameter record has pH=5.0 and temperature=30C,
use it for environment temp_30C_ph_5p0_aerobic.

If no matching record exists,
either:
    - use environment-independent parameter only if allowed;
    - mark environment_effect_status=metadata_only;
    - or block simulation as missing condition-specific parameters.
```

## Environment matching policies

Add explicit policies:

```text
exact_condition_match
nearest_condition_match
range_condition_match
environment_independent
metadata_only
active_response_model
```

Do not silently use nearest-condition matching in scientific mode.

Exploratory mode may allow nearest/range matching if explicitly marked.

## Required output additions

Include in tables:

```text
environment_parameter_match_policy
matched_parameter_environment_id
condition_distance
condition_match_status
```

## ENV-002 tests

Required:

```text
- exact condition matching works;
- unmatched environment is blocked or metadata-only depending on policy;
- scientific mode rejects nearest-condition matching unless exact;
- exploratory mode records nearest/range matching as exploratory;
- environment ranking remains blocked if metadata-only;
- environment ranking allowed only when active condition effects exist.
```

## ENV-002 acceptance criteria

Complete when:

```text
- environment grids can become scientifically meaningful without fake response curves;
- output tables tell whether environment changed parameters;
- pH/temperature rankings are impossible unless supported by active condition-specific data or response models.
```

---

# Phase 6: CURATION-001 — Registry Review and Promotion Gate

## Goal

Create a formal promotion path from proposed source records to curated registry records.

SOURCE-001 will produce proposed records.

Those records must not automatically become trusted simulation records.

CURATION-001 defines how records are promoted.

## Record maturity ladder

Use or formalize:

```text
raw_source
proposed
curated_exact
curated_literature_range
exploratory_prior
synthetic_fixture
validated
deprecated
```

## Required curation process

Every promoted record must have:

```text
source_database
source_entry_id
source_url or source_snapshot
curator
curation_date
original_value
original_units
converted_value
converted_units
conversion_method
inclusion_reason
exclusion_reason if rejected
allowed_use
limitations
```

## Required curation reports

For every source import:

```text
curation_report.md
eligible_records.csv
excluded_records.csv
proposed_registry_records.yml
accepted_registry_records.yml
rejected_registry_records.yml
```

## CURATION-001 acceptance criteria

Complete when:

```text
- no proposed API/source record is silently used for simulation;
- all simulation records have maturity and allowed-use policy;
- curation reports are testable and versioned;
- registry promotion is explicit.
```

---

# Phase 7: BIO-READINESS Gate

## Goal

Before adding or extending biology, enforce a readiness gate.

No new biological process should be added unless it has:

```text
required inputs
state variables
process law
parameters
units
validity domain
output states
summary metrics
limitations
tests
provenance plan
```

## Biology readiness checklist

A new biology module must define:

```text
1. What biological process is being modeled?
2. What is the process law?
3. What are the state variables?
4. What are the required parameters?
5. What units are expected?
6. What substrate classes are valid?
7. What enzyme/fungus classes are valid?
8. What environmental variables affect it?
9. What output curves does it produce?
10. What scalar metrics does it produce?
11. What assumptions are made?
12. What data sources support it?
13. What is unknown?
14. What experiments would reduce uncertainty?
15. What failure modes should block simulation?
16. What tests prove correct behavior?
```

## BIO-READINESS acceptance criteria

Complete when:

```text
- a new biology proposal cannot be merged without this checklist;
- tests or CI check for required process metadata;
- foundation_progress has a biology proposal template;
- Codex is instructed to reject unsupported, invented, silently guessed, or
  falsely validated biology.
```

---

# Phase 8: BIO-002 — Biology Work Under The Gate

Status note: this section predates the current BIO-002 records documented in
`progress.md`. Phase 1 Task 2 must reconcile whether the prerequisites below are
still roadmap gates, already satisfied, or superseded by current implementation
evidence.

## When to start BIO-002

Start or extend BIO-002-class work only after:

```text
SOURCE-001 complete
RESOLVE-001 complete
ASSEMBLY-001 complete
API-003 complete
ENV-002 at least partially complete
CURATION-001 complete
BIO-READINESS gate active
```

## Recommended BIO-002 target

Do not jump to whole-fungus growth yet.

Recommended:

```text
BIO-002: cellulase/cellulose product-chain extension
```

Possible scope:

```text
cellulose-like substrate
endoglucanase/cellobiohydrolase/beta-glucosidase chain
solid cellulose -> cellobiose -> glucose
```

Why this is a good next biology target:

```text
- continues from Reaction 618 and BIO-001;
- connects soluble and surface degradation;
- still enzyme-mediated, not full fungus growth;
- product chain is interpretable;
- SABIO-RK/BRENDA/CAZy can support parts of it;
- outputs remain degradation/product curves.
```

Avoid:

```text
whole fungus growth
PET
lignin
full lignocellulose
oxygen regulation
secretion dynamics
intracellular metabolism
```

until the enzyme-chain layer is stable.

## BIO-002 required outputs

```text
solid_cellulose_remaining(t)
cellobiose_release(t)
glucose_release(t)
substrate_degraded_fraction(t)
time_to_10/50/90_percent_degradation
final_glucose_yield
rate-limiting step indicator
uncertainty intervals
```

---

# Phase 9: VALIDATION-DATA-001 — First Real Time-Course Validation Dataset

## Goal

Add the first experimental time-course dataset to validate or compare against a virtual experiment.

This is not required for every virtual experiment, but FungMod needs at least one real validation case.

## Recommended validation target

Choose a narrow enzyme-only or enzyme-chain dataset:

```text
beta-glucosidase + cellobiose -> glucose time course
```

or:

```text
cellulase cocktail + cellulose/Avicel -> soluble sugar release time course
```

Do not start with whole-fungus colony growth.

## Required dataset fields

```text
time
substrate concentration or mass remaining
product concentration or amount
enzyme loading
pH
temperature
buffer
replicates if available
source publication
units
measurement method
```

## Required outputs

```text
experiment_dataset.yml
raw_data.csv
curated_data.csv
model_comparison.csv
residuals.csv
validation_report.md
```

## Acceptance criteria

Complete when:

```text
- dataset is local, curated, and provenance-rich;
- model can simulate corresponding case;
- outputs compare simulation to observation;
- limitations state whether this is validation, calibration, or qualitative comparison.
```

---

# Phase 10: BIO-003 — Whole-Fungus Minimal Growth Coupling

## When to start

Only after enzyme-chain and validation-data phases.

Whole-fungus biology should not be added casually.

## Minimal scope

```text
extracellular substrate degradation
soluble product uptake
biomass proxy growth
maintenance cost
```

Do not add full metabolism.

Do not add gene regulation.

Do not add intracellular flux balance.

Do not add morphology unless required.

## Required outputs

```text
substrate_remaining(t)
soluble_product(t)
uptake_flux(t)
biomass_proxy(t)
growth_rate(t)
time_to_substrate_degradation_threshold
time_to_biomass_threshold
```

---

# Phase 11: Database Strategy

## Important principle

FungMod does not need a giant built-in database.

FungMod needs:

```text
source adapters
local source snapshots
curated registry records
review gates
provenance
allowed-use policies
```

SABIO-RK, BRENDA, CAZy, UniProt, KEGG, and literature can feed FungMod.

They do not replace FungMod’s registry.

## Why local records are still needed

Local records are needed for:

```text
reproducibility
offline tests
reviewed curation
source drift detection
provenance
allowed-use semantics
simulation templates
state roles
product maps
process compatibility
```

Live external APIs should never be required to reproduce a simulation.

---

# Phase 12: Recommended immediate next order

Use this exact order:

```text
1. SOURCE-001
2. RESOLVE-001
3. ASSEMBLY-001
4. API-003
5. ENV-002
6. CURATION-001
7. BIO-READINESS
8. BIO-002
9. VALIDATION-DATA-001
10. BIO-003
```

If time is limited, do the first four before expanding biology further.

---

# Final answer to "Can we start biology after this?"

After SOURCE-001, RESOLVE-001, ASSEMBLY-001, API-003, CURATION-001, and BIO-READINESS:

```text
yes, carefully, if the biology proposal passes the BIO-READINESS gate.
```

Before roadmap reconciliation:

```text
verify the specific task against progress.md, code, tests, and AGENTS.md.
```

The project should not add unsupported biological mechanisms. Any added or
extended mechanism must be explicitly implemented, provenance-backed,
maturity-labelled, covered by tests, and honest about assumptions and
limitations.

The next real biology should probably be:

```text
cellulose enzyme-chain degradation:
solid cellulose -> cellobiose -> glucose
```

not whole-fungus growth and not PET.

---

# One-sentence directive

Before adding or extending biology, make sure FungMod can discover/source
reaction data, resolve researcher names, assemble cases from registry/config
schemas, run scientific and exploratory virtual experiments, and output
degradation curves/tables without hardcoded case branches, or document why the
proposal is scoped narrowly enough to proceed under the current biology rule.
