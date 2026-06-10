# SOURCE-002: Notebook-Driven SABIO-RK Discovery and Registry Proposals

## Goal

Add a notebook-friendly route where researchers can provide human-readable source/substrate/enzyme/reaction inputs and generate proposed FungMod records.

## Required API

```python
from fungal_model.sources.sabiork import SabioRKSource

source = SabioRKSource(cache_dir="data/source_snapshots/sabiork")

discovery = source.discover_for_virtual_experiment(
    fungus="Aspergillus niger",
    substrate="cellobiose",
    enzyme="beta-glucosidase",
    ec_number="3.2.1.21",
    reaction_id="618",
    refresh=False,
)

proposal = discovery.to_registry_proposal(
    process_type="homogeneous_michaelis_menten",
    product_map="auto_from_stoichiometry",
)

proposal.write("data/proposed_records/sabiork/aspergillus_niger_cellobiose")
```

## Required behavior

```text
- use frozen local snapshots by default;
- live refresh only with explicit refresh=True and explicit live_fetcher;
- no live API calls during simulation;
- no live API calls during tests;
- no silent mutation of data_registry/;
- proposed records marked proposed_review_required;
- missing fields shown clearly;
- stable deterministic IDs generated.
```

## Required objects

```text
SourceDiscoveryResult
RegistryProposal
```

`SourceDiscoveryResult` should include:

```text
reaction records
substrates
products
enzyme names
EC numbers
organism/source names
kinetic parameters
pH/temperature/buffer
publication metadata
warnings
missing fields
source snapshot path
```

`RegistryProposal` should include proposed:

```text
substrate records
fungus/source records, if applicable
enzyme-class records
parameter records
product-map records
process-compatibility records
case-template records where safe
```

## Required notebook

```text
notebooks/09_sabiork_discovery_to_registry_proposal.ipynb
```

The notebook must demonstrate discovery, show products/parameters/missing fields, write proposed records, and explicitly state that proposals are not production registry records.

## Required tests

```text
tests/test_sabiork_discovery_workflow.py
```

Test no network, deterministic IDs, extracted products, extracted stoichiometry, proposal writing, no data_registry mutation, and unknown query behavior.
