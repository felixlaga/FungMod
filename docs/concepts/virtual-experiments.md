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

## Requests with blocked cases

By default `simulate` refuses a request in which the preflight blocks any
case in the requested mode, and simulates nothing. To simulate the runnable
cases and report the blocked ones, opt in explicitly:

```python
result = study.simulate(mode="exploratory", n_samples=128, seed=42, blocked="report")
result.partial_run       # True when some requested cases were not simulated
result.blocked_cases()   # their case ids, status, missing items and measurement requests
```

The rule of each mode is unchanged (scientific: `modelable` cases only), a
request without any runnable case is still refused, and the blocked cases
appear in the tables as `not_simulated`; see
[partial runs](outputs.md#partial-runs).

## Environment grids

```python
grid = fm.environment_grid(
    temperature_C=[20, 25, 30],
    ph=[4.5, 5.0, 5.5],
    oxygen="aerobic",
)
```

A grid creates explicit environment cases. Temperature, pH, oxygen, or water
activity only affect rates when the case template binds an implemented
response law or a condition-specific parameter record applies. A bound law
reports `environment_effect_status: active_response_model` and names the law
in `environment_response_model`; ranking across environments is allowed only
when every condition that varies across the screen is covered by a law or by
condition-specific records. Otherwise the values remain metadata and ranking
is guarded. See [environment response laws](../environment-response.md).

## Failure is part of the API

Unsupported mechanisms, missing parameters, incompatible units, maturity
violations, and invalid configurations fail explicitly. Preflight and
structured failure reports are designed to explain what must be measured or
implemented next.
