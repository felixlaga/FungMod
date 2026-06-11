# BIO-002: Reusable Extracellular Enzyme-Chain Degradation

## Goal

Implement a reusable process:

```text
polymer/substrate pool -> soluble intermediate -> soluble product
```

Demo case:

```text
solid cellulose-like substrate -> cellobiose -> glucose
```

## Do not implement

```text
whole-fungus growth
secretion
uptake
biomass
PET
lignin
full lignocellulose
organism-specific behavior
```

## Required outputs

```text
solid_substrate_remaining(t)
solid_substrate_degraded_fraction(t)
cellobiose(t)
glucose(t)
time_to_10/50/90_percent_degradation
final_glucose_yield
limitations_table.csv
suggested_experiments.csv
```

## Implemented

BIO-002 is implemented as a reusable extracellular enzyme-chain workflow:

```text
solid cellulose-equivalent pool --surface catalysis--> cellobiose
cellobiose --homogeneous Michaelis-Menten--> beta-D-glucose
```

The configured process laws are generic:

```text
surface step: equilibrium Langmuir coverage * accessible surface area * surface rate constant
homogeneous step: enzyme-explicit Michaelis-Menten
```

The demo is assembled from registry case-template metadata:

```text
data_registry/case_templates/case_templates.yml
src/fungal_model/screening/enzyme_chain.py
```

Stoichiometric product maps:

```text
solid_cellulose_equivalent_concentration -> 1 cellobiose_concentration
cellobiose_concentration -> 2 beta_D_glucose_concentration
```

Public workflow helpers:

```python
build_extracellular_enzyme_chain_config(...)
run_extracellular_enzyme_chain_demo(...)
write_enzyme_chain_standard_tables(...)
```

## Status

```text
validation_status: exploratory_software_tested
```

BIO-002 does not implement whole-fungus growth, secretion, uptake, biomass,
PET, lignin, full lignocellulose, organism-specific behavior, or an
environmental response law.

The first step uses explicitly labeled BIO-002 exploratory scaffold
parameters. The second step reuses local Reaction 618 Km/kcat records for
cellobiose hydrolysis. The demo is not calibrated or experimentally validated.
