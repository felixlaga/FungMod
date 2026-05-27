# Results, Validation, and Outputs Foundation Plan

## Objective

Make outputs scientifically inspectable before adding real biology.

## SimulationResult contract

Required fields:

```python
name
mode
maturity
time
states
process_rates
derived_quantities
parameters
assumptions
validation_results
warnings
solver_metadata
assembly_report
config_snapshot
entity_snapshots
model_version
```

## Required methods

```python
state(name)
rate(name)
to_dict()
save(output_dir)
validation_report()
assumption_report()
parameter_table()
plot_states()
plot_rates()
plot_mass_balance()
```

## Output folder

```text
outputs/run_name/
    record.json
    config_snapshot.yml
    model_assembly_report.json
    assumptions.json
    parameters.csv
    validation_report.json
    solver_report.json
    warnings.json
    entities/
    tables/
    figures/
    logs/
```

## Foundation validators

- non-negativity;
- mass balance;
- state units;
- parameter provenance;
- data maturity;
- assembly completeness.

No fungal-specific validation yet.

## Failure behavior

Assembly failures produce structured exceptions with reports. Post-solve validation failures are attached to results; strict mode may raise.

## Plot requirements

Plots must have units, be generated from `SimulationResult`, save reproducibly, and not imply scientific validation if mode is toy.

## Done when

1. every generic workflow returns `SimulationResult`;
2. every result can save a full output bundle;
3. validation is attached;
4. outputs are reproducible;
5. toy status is visible;
6. notebooks use result methods, not custom hidden logic.
