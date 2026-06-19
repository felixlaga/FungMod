# FungMod Next Phases Roadmap v2

## Central update

This roadmap adds a practical SOURCE-002 phase before new biology:

```text
human names -> SABIO-RK discovery -> proposed records -> explicit review/apply -> simulation registry
```

Researchers should be able to call a Python route from a notebook, give human-readable names for fungus/source, substrate, enzyme, EC number, or reaction, and generate proposed FungMod records.

The production registry must not be mutated automatically.

## Correct architecture

```text
Notebook user input
-> source discovery
-> frozen SABIO-RK snapshot or explicit refresh
-> parsed reactions/products/parameters
-> proposed registry records
-> explicit review/apply
-> virtual experiment
```

Incorrect:

```text
Notebook input
-> live API
-> automatic data_registry mutation
-> simulation
```

## Recommended implementation order

```text
1. SOURCE-002
   Notebook-driven SABIO-RK discovery and registry proposal workflow.

2. PRE-BIO-001
   Stoichiometry and generic assembly hardening.

3. BIO-READINESS-LITE
   Lightweight gate for reusable biological process mechanisms.

4. BIO-002
   Reusable extracellular enzyme-chain degradation process.

5. CASE-001
   Cellulose-like enzyme-chain virtual experiment.

6. PRODUCT-001
   Build-first exploratory virtual-experiment expansion.

7. THERMO-003
   Dynamic thermodynamic and entropy constraints.

8. BIO-003
   Generic mechanism expansion through reusable process laws.

9. VALIDATION-DATA-001
   Deferred first real time-course dataset and model comparison.
```

Full CURATION-001 can wait.

## SOURCE-002

Goal: add a notebook-friendly SABIO-RK discovery workflow.

Target API:

```python
from fungal_model.sources.sabiork import SabioRKSource

source = SabioRKSource(cache_dir="data/source_snapshots/sabiork")

discovery = source.discover_for_virtual_experiment(
    fungus="Aspergillus niger",
    substrate="cellobiose",
    enzyme="beta-glucosidase",
    ec_number="3.2.1.21",
    refresh=False,
)

discovery.show_reactions()
discovery.show_products()
discovery.show_kinetic_parameters()
discovery.show_missing_fields()

proposal = discovery.to_registry_proposal(
    process_type="homogeneous_michaelis_menten",
    product_map="auto_from_stoichiometry",
)

proposal.write("data/proposed_records/sabiork/aspergillus_niger_cellobiose")
```

Required objects:

```text
SourceDiscoveryResult
RegistryProposal
stable ID generation helpers
proposal writer
proposal preview
notebook example
```

Safety requirements:

```text
- use frozen local snapshots by default;
- allow live refresh only with explicit refresh=True and explicit live_fetcher;
- never call live API during simulation;
- never call live API during tests;
- never automatically write to data_registry/;
- proposed records must be marked proposed_review_required;
- missing fields must be reported explicitly.
```

## PRE-BIO-001

Goal: fix the blockers before new biology.

Required:

```text
1. Make stoichiometric product-map yields affect product dynamics.
2. Prove Reaction 618 glucose formation = 2 × cellobiose consumption.
3. Remove or reduce BIO-001-specific branching.
4. Move case-specific mode/maturity/provenance/geometry metadata into templates or registry records.
5. Add a test proving a new surface-catalysis template can assemble without a new Python branch.
```

## BIO-READINESS-LITE

Goal: require future BIO milestones to be reusable process mechanisms.

Rule:

```text
BIO-* = reusable biological process mechanism
CASE-* = specific organism/substrate/environment virtual experiment
DATA-* = source, parameter, or validation evidence
```

Good:

```text
BIO-002: reusable extracellular enzyme-chain degradation
CASE-001: cellulose-like substrate -> cellobiose -> glucose
```

Bad:

```text
BIO-002: Pleurotus ostreatus cellulose model
```

## BIO-002

Goal: implement a reusable enzyme-chain mechanism.

General mechanism:

```text
polymer/substrate pool -> soluble intermediate -> soluble product
```

Demo case:

```text
solid cellulose-like substrate -> cellobiose -> glucose
```

Do not implement whole-fungus growth, secretion, uptake, biomass, PET, lignin, full lignocellulose, or organism-specific behavior.

## CASE-001

Goal: first concrete virtual experiment using BIO-002.

Target API:

```python
from fungal_model import virtual_experiment, EnvironmentGrid

study = virtual_experiment(
    fungi=["generic cellulase enzyme chain source"],
    substrates=["cellulose-like film"],
    environments=EnvironmentGrid(
        temperature_C=[25, 30, 35],
        ph=[4.5, 5.0, 5.5],
        oxygen="aerobic",
    ),
)

result = study.simulate(mode="exploratory", n_samples=256)
```

## PRODUCT-001

Goal: improve the virtual-experiment product before requiring validation data.

FungMod should generate honest exploratory degradation curves from implemented
mechanisms, explicit assumptions, uncertainty ranges, provenance, limitations,
and missing-mechanism reports.

Prioritize:

```text
broader researcher-facing fungus/source + substrate + environment inputs
explicit exploratory priors
substrate remaining, product release, rates, threshold times
uncertainty bands
provenance and limitations
missing mechanism / missing parameter reports
```

## THERMO-003

Goal: add generic thermodynamic and entropy constraints where equations and
inputs are implemented.

Prefer first-principles checks over case-specific fungus models, but do not
emit unsupported thermodynamic, redox, or entropy state.

## BIO-003

Goal: expand biology through reusable process laws.

Good directions include generic hydrolysis, oxidative components, inhibition
laws, environmental modifiers, and additional enzyme-chain motifs. Every
mechanism must be provenance-backed, maturity-labelled, tested, and honest
about limitations.

## VALIDATION-DATA-001

Goal: add the first real time-course dataset for model comparison after the
simulator outputs are mature enough to compare meaningfully.

Validation data is important, but it should not block PRODUCT-001, THERMO-003,
or generic BIO-003 build-out.

Recommended targets:

```text
beta-glucosidase + cellobiose -> glucose time course
cellulase/cellulose -> soluble sugar release time course
```

Do not start with whole-fungus growth.

## When to start biology

Start BIO-002 after:

```text
SOURCE-002
PRE-BIO-001
BIO-READINESS-LITE
```

You do not need full CURATION-001 before BIO-002.
