# Virtual experiments

A FungMod virtual experiment is the Cartesian product of:

- one or more fungus or enzyme-source records;
- one or more substrate records;
- one or more registry or runtime environment cases;
- an explicit simulation mode and sampling policy.

## Lifecycle

```text
resolve records
→ modelability preflight
→ assemble implemented processes
→ sample explicit ranges when allowed
→ solve each allowed case
→ validate configured numerical/physical contracts
→ write standard tables, diagnostics, figures, reports, and manifest
```

Modelability prevents unsupported execution, but simulation outputs are the
product.

## Exploratory mode

Exploratory mode may use records explicitly labelled for exploratory
simulation, including bounded ranges or distributions. It does not silently
fill missing values.

```python
result = study.simulate(
    mode="exploratory",
    n_samples=128,
    seed=42,
)
```

Interpretation:

- sampled-input summaries are conditional on the supplied ranges;
- output quantiles are propagated exploratory uncertainty;
- neither is automatically calibration, a posterior, or validation evidence.

## Scientific mode

Scientific mode requires exact, non-toy, non-exploratory parameter values and
implemented mechanisms:

```python
result = study.simulate(mode="scientific")
```

The label means the run satisfies FungMod's exact-input software gate. It does
not by itself mean the model has been empirically validated for the requested
system.

## Environment grids

```python
grid = fm.environment_grid(
    temperature_C=[20, 25, 30],
    ph=[4.5, 5.0, 5.5],
    oxygen="aerobic",
)
```

A grid creates explicit environment cases. Temperature, pH, oxygen, or water
activity only affect rates when an implemented response law or
condition-specific parameter record is bound. Otherwise the values remain
metadata and ranking is guarded.

## Failure is part of the API

Unsupported mechanisms, missing parameters, incompatible units, maturity
violations, and invalid configurations fail explicitly. Preflight and
structured failure reports are designed to explain what must be measured or
implemented next.
