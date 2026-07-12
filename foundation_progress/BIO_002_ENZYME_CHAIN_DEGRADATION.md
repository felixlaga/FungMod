# BIO-002: Reusable Extracellular Enzyme-Chain Degradation

## Mechanism Scope

BIO-002 assembly supports reusable arbitrary-length linear extracellular
process chains with a minimum of two steps:

```text
substrate pool -> intermediate 1 -> ... -> intermediate N -> product
```

The ordered process templates and their one-reactant/one-product stoichiometric
maps define the chain topology. Every step must consume the preceding step's
product, every topology state must be unique, and the chain must begin at the
`substrate` role and end at the `product` role. Branching, cycles, reordered
steps, disconnected maps, and graph-style pathways fail before model execution.

The generic Python assembler does not know the biological identities used by a
demonstration case. It reads the following from the registry case template:

```text
entity IDs, loaders, names, and metadata
state names, roles, units, and initial values
surface and homogeneous catalyst states
ordered process sequence, process types, and linear state topology
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

## Backward-Compatible Demonstration Template

The current registry template remains the two-step BIO-002 demonstration:

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

The researcher-facing CASE-001 path, public helper signatures, configured
process IDs, state names, conservation weights, and standard output labels are
unchanged for this template.

## Genericity Evidence

`tests/test_bio002_generic_chain_assembly.py` adds an unrelated artificial
three-step framework benchmark:

```text
polymer_X -> oligomer_Y -> fragment_Q -> monomer_Z
```

That fixture uses different entity IDs, state names, three catalyst states,
parameter IDs, output labels, and stoichiometric yields:

```text
first step yield: 1.5
second step yield: 2.0
third step yield: 3.0
conserved weights: 1, 2/3, 1/3, 1/9
```

It assembles and runs through `run_configured_model` using the same generic
code, maps an existing product-inhibition modifier on the third step, preserves
the declared conserved equivalent, and writes configured standard outputs. It
is software verification only, not scientific biology, validation data, or
calibration evidence. The test also guards against reintroducing demonstration
biological names into the generic assembler.

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
fewer than two process steps
process/product-map count mismatches
process state-role mappings that disagree with stoichiometric maps
disconnected or reordered steps
multi-reactant or multi-product branching maps
cycles or repeated topology states
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
branching process graphs
cyclic pathways
```

The first configured surface step uses exploratory scaffold parameters unless a
case supplies calibrated evidence. The current work establishes reusable
architecture and software verification, not Atmodeller-level scientific
validation.
