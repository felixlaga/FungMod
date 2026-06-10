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
