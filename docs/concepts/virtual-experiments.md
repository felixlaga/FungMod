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

## Surface-catalysis cases

A registry case whose compatibility record selects `surface_catalysis` runs
the generic equilibrium-coverage law

```text
r = k_s * theta(E) * A,    theta = K_ads * E / (1 + K_ads * E)
```

with the free enzyme `E` as a state, the adsorption constant `K_ads`, the
surface rate constant `k_s` and the accessible area `A` as parameter records,
and the rate set to zero once the substrate is exhausted. The law is zero
order in the substrate until then (the area is a constant parameter, not a
function of conversion), and binding does not deplete the free enzyme.

The assembler is template-driven (SURFACE-001). The case template states:

- `config_name`, `config_mode` (`toy`, `exploratory` or `scientific`),
  `config_maturity`, `accessible_site_pool` and `product_map_name` (required;
  a template without one is refused);
- `config_provenance` (`source`, `measurement_method`, `confidence_level`,
  `validity_range`, `notes`, and optionally further provenance texts),
  `substrate_entity` (`notes`, `product_notes`, optional `completeness`,
  `default_degradation_model`, `water_activity_dependence`), `enzyme_entity`
  (`name`, `validity_labels`, `notes`) and `parameter_entries`
  (`measurement_method`, `validity_range`); the process assumptions are the
  template's `limitations`;
- `geometry`: a well-mixed geometry mapping, or `geometry: null` for a model
  that claims no vessel. The surface law reads no geometry (its area is the
  `accessible_surface_area` parameter), so FungMod assumes none and refuses a
  template that states neither;
- `bond_type`, optional: without it the bond class is the one class the
  substrate record carries, the enzyme class targets and the compatibility
  record requires; several are refused, never chosen.

Structural fields (substrate name, class, physical state, bond and product
classes; enzyme class) come from the registry records; a substrate the record
declares dissolved or of unknown physical state is refused. A `toy` or
`scientific` template is built deterministically only in its own mode; a
`scientific` template only from exact records the scientific selection rules
accept; an `exploratory` template is sampled by `simulate(mode="exploratory")`.
The shipped BIO-001 cellulose pilot is an exploratory template whose
cellulose-specific text lives in its registry record; the well-mixed geometry
it declares (100 mL, 0.5 m^2) is context metadata, and its surface area is not
the accessible area the law uses.

## Failure is part of the API

Unsupported mechanisms, missing parameters, incompatible units, maturity
violations, and invalid configurations fail explicitly. Preflight and
structured failure reports are designed to explain what must be measured or
implemented next.
