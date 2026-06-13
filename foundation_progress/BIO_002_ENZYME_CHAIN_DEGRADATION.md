# BIO-002: Reusable Extracellular Enzyme-Chain Degradation

## Mechanism Scope

BIO-002 is a reusable two-step extracellular process mechanism:

```text
substrate pool -> soluble intermediate -> soluble product
```

The generic Python assembler does not know the biological identities used by a
demonstration case. It reads the following from the registry case template:

```text
entity IDs, loaders, names, and metadata
state names, roles, units, and initial values
surface and homogeneous catalyst states
process sequence and process types
parameter-record IDs
product-map IDs and stoichiometric coefficients
conserved-equivalent weights
output roles, labels, summary metrics, limitations, and suggested experiments
```

The implementation lives in:

```text
src/fungal_model/screening/enzyme_chain.py
data_registry/case_templates/case_templates.yml
```

Public workflow helpers:

```python
build_extracellular_enzyme_chain_config(...)
run_extracellular_enzyme_chain_demo(...)
write_enzyme_chain_standard_tables(...)
```

## Current Demonstration Template

The current production template remains a BIO-002 demonstration fixture:

```text
solid cellulose-equivalent pool -> cellobiose -> beta-D-glucose
```

Those names, entity metadata, output labels, exploratory parameters, and
Reaction 618-linked records are registry/template data, not generic mechanism
logic.

Template stoichiometry:

```text
solid_cellulose_equivalent_concentration -> 1 cellobiose_concentration
cellobiose_concentration -> 2 beta_D_glucose_concentration
```

Template conserved-equivalent weights:

```text
solid_cellulose_equivalent_concentration: 1.0
cellobiose_concentration: 1.0
beta_D_glucose_concentration: 0.5
```

The Reaction 618 homogeneous step still preserves:

```text
glucose formed ~= 2 x cellobiose consumed
```

## Genericity Evidence

`tests/test_bio002_generic_chain_assembly.py` adds an unrelated fixture:

```text
polymer_X -> oligomer_Y -> monomer_Z
```

That fixture uses different entity IDs, state names, catalyst names, parameter
IDs, output labels, and stoichiometric yields:

```text
first step yield: 1.5
second step yield: 3.0
conserved weights: 1, 2/3, 2/9
```

It assembles and runs through `run_configured_model` using the same generic
BIO-002 code. The test also guards against reintroducing demo biological names
into the generic assembler.

## Validation and Failure Modes

The assembler rejects malformed chain templates with structured errors for:

```text
zero, negative, NaN, or infinite stoichiometric coefficients
empty required reactant/product maps
unknown state roles
states without units
legacy product-state declarations that conflict with product maps
missing or inconsistent conservation metadata
output metrics that reference unknown roles or derived series
```

The real mechanism proposal is machine-readable:

```text
foundation_progress/proposals/BIO_002_EXTRACELLULAR_ENZYME_CHAIN.yml
```

It passes the BIO-READINESS-LITE validator and separates:

```text
BIO-002: reusable mechanism
CASE/demo: one explicit substrate-to-product setup
DATA dependencies: parameter and validation evidence
```

## Limitations

BIO-002 does not implement:

```text
whole-fungus growth
secretion
uptake
biomass
PET
lignin
full lignocellulose
organism-specific behavior
experimental validation across biological systems
```

The first configured surface step uses exploratory scaffold parameters unless a
case supplies calibrated evidence. The current work establishes reusable
architecture and software verification, not Atmodeller-level scientific
validation.
