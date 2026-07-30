# BIO-002: Reusable Extracellular Enzyme-Pathway Degradation

## Mechanism Scope

BIO-002 assembly supports reusable extracellular process graphs with a minimum
of two steps and an explicit `topology_type` of `linear`, `branching`, or
`cyclic`:

```text
linear:    substrate -> intermediate 1 -> ... -> product
branching: substrate -> one or more explicit downstream paths
cyclic:    one or more explicit directed state-role cycles
```

Process templates and their distinct stoichiometric maps define the graph.
Every implemented process has one explicit rate-law input; a map may declare
one or more products so one process can create explicit divergent edges.
Linear topology retains ordered contiguous one-product steps and unique states.
Branching topology must contain an actual divergence or convergence, remain
acyclic, and be reachable from the `substrate` role. Cyclic topology must
contain an actual directed cycle and remain reachable from `substrate`.
All graph forms must include `substrate` and `product`, use distinct runtime
states for topology roles, remain connected, agree exactly with process state
roles, and satisfy the declared conservation weights before execution.

The generic Python assembler does not know the biological identities used by a
demonstration case. It reads the following from the registry case template:

```text
entity IDs, loaders, names, and metadata
state names, roles, units, and initial values
surface and homogeneous catalyst states
process sequence, process types, declared graph type, and directed state edges
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

## Backward-Compatible Linear Demonstration Template

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
the declared conserved equivalent, and writes configured standard outputs.
The same fixture is copied and modified in tests to execute:

```text
branching: polymer_X -> oligomer_Y and fragment_Q -> monomer_Z
cyclic:    polymer_X -> oligomer_Y -> fragment_Q -> polymer_X
                                      \-> monomer_Z
```

Those graph fixtures preserve the same explicit conserved equivalent and run
through the standard configured solver. They are software verification only,
not scientific biology, validation data, or calibration evidence. The test
also guards against reintroducing demonstration biological names into the
generic assembler.

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
missing or unsupported topology types
disconnected graphs or states unreachable from the declared substrate role
linear graphs with reordered, branching, cyclic, or repeated topology states
branching declarations without an actual divergence/convergence
branching declarations that contain a directed cycle
cyclic declarations without an actual directed cycle
multiple roles aliased to one runtime topology state
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
linear/branching/cyclic pathway architecture and software verification, not
Atmodeller-level scientific validation or broader biological pathway coverage.
