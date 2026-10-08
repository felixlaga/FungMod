# Outputs and artifacts

FungMod prioritizes tables over notebook-only plots. Every reported number
should be recoverable from an exported artifact.

## Standard virtual-experiment tables

| Artifact | Purpose |
| --- | --- |
| `modelability_preflight.csv` | One preflight outcome per case. |
| `case_summary.csv` | One row per requested case: sample counts, and `case_status` (`simulated`, or `not_simulated` with the reason in a [partial run](#partial-runs)). |
| `modelability_items.csv` | Known, uncertain, missing, or unsupported inputs. |
| `time_series_long.csv` | Long-form state and derived trajectories. |
| `final_metrics.csv` | Final substrate/product metrics and maximum rates, each in its own state's units. The final product is `final_product_concentration` when its units are anything per volume (judged by pint's dimensionality since schema `2.2.1`; `2.2.0` and earlier bundles named a micromolar product `final_product_amount`) and `final_product_amount` otherwise (a mass or an amount). `final_product_yield` (product formed per initial substrate) is the plain ratio, `dimensionless`, when product and substrate share units; across a [basis change](../user-data.md#a-solid-releasing-a-dissolved-pool) it is the pint quotient with its units (for example `millimole / gram`), never labelled dimensionless. |
| `threshold_times.csv` | Times to configured degradation fractions. |
| `sampled_parameters.csv` | Every sampled value with source and allowed-use metadata. |
| `uncertainty_summary.csv` | Summaries over sampled inputs and output metrics. |
| `trajectory_quantiles.csv` | Time-indexed exploratory trajectory bands. |
| `mechanism_summary.csv` | Active process laws and modifiers. An [enzyme network](../user-data.md#several-enzymes-acting-together) adds one `process_law` row per process (its enzyme class in `configured_by`) after the network row, and a provenance-bound competitive-inhibition modifier its own `rate_modifier` row; the columns and allowed values are unchanged. |
| `assumption_summary.csv` | Explicit assumptions attached to cases and processes. |
| `provenance_table.csv` | Source and provenance rows used by the run. |
| `limitations_table.csv` | Known interpretation boundaries. |
| `missing_parameters.csv` | Inputs that remain unavailable. |
| `suggested_experiments.csv` | Measurements that would reduce missingness or uncertainty. |
| `comparison_summary.csv` | Side-by-side metrics plus comparison/ranking guardrails. |
| `conservation_diagnostics.csv` | Copied configured conservation diagnostics, when present. A weight may carry units (`{"value": ..., "units": ...}` in `weighted_states`, for example a stated yield in `mmol/g` weighing a solid in g/L), so a ledger across bases is summed in one unit through the stated conversion. |
| `thermodynamic_diagnostics.csv` | Copied configured thermodynamic diagnostics, when present. |
| `solver_diagnostics.csv` | Solver metadata without invented quality thresholds. |
| `timecourse_comparison.csv` | Written on request by `result.compare_with_timecourses()`: simulated median and 5-95 % band at the user's observed times, residuals and RMSE; in-sample agreement, not validation (schema `2.1.0`). |

Header-only diagnostic tables mean that the corresponding configured evidence
was unavailable. Missing diagnostics are not converted to zeros.

## Partial runs

By default `VirtualExperiment.simulate` refuses a request in which the
preflight blocks any case. With `simulate(..., blocked="report")` (from a
shell: `fungmod run --runnable-only`, exit code 4) it simulates the cases
that pass the preflight in the requested mode and reports the others; when
no case is runnable it refuses as before. Output schema `2.2.0` records this:

| Where | What a blocked case gets |
| --- | --- |
| `case_summary.csv` | A row with `case_status` `not_simulated`, `simulated` `false`, `sample_count` 0 and `not_simulated_reason`: the preflight mode, status, blocking reason and next action. Simulated cases have `case_status` `simulated` and an empty reason. |
| `modelability_preflight.csv`, `modelability_items.csv` | Its preflight outcome and items, with `simulation_allowed_for_mode` `false` and the blocking reason. |
| `missing_parameters.csv`, `suggested_experiments.csv` | Its missing inputs and measurement requests. |
| `limitations_table.csv` | A `not_simulated` row of severity `blocking`, beside its missing-input rows. |
| `assumption_summary.csv` | Its preflight assumptions and items. |
| Per-sample tables | Nothing: a blocked case has no samples, trajectories, metrics or threshold times. `environment_summary.csv` and `comparison_summary.csv` cover simulated cases only. |
| `virtual_experiment_summary.json`, `output_manifest.json` | `partial_run`, `blocked_policy`, `requested_case_count`, `simulated_case_count` and `blocked_cases` (case id, ids, status, blocking reason, next action, missing and incompatible items, measurement requests, reason). A full run has `partial_run` `false` and an empty list. |
| Report | A "Partial run" statement in the run summary and a "Not simulated" note on each blocked case. |

`case_id` is `case_<position>` in the requested fungus x substrate x
environment grid, so the ids of a partial run are those of the full request
and the blocked rows sit in grid order between the simulated ones. Each
case's seed is drawn from the run seed by the same position, so the samples
of a simulated case equal those of a run of the same request in which every
case is runnable, and those of `simulate_screen(..., cases=[that case])` on
the same request. A request that names the case alone gives it position 0 and
therefore the same samples only when it is the first case of the larger
request.

## Degradation and product-release rates

The tables follow output schema `2.0.0`.

| Row or metric | Table | Definition |
| --- | --- | --- |
| `degradation_rate` | `time_series_long.csv` | -d[substrate]/dt of the case's mapped substrate state |
| `product_release_rate` | `time_series_long.csv` | +d[product]/dt of the case's mapped product state |
| `maximum_substrate_depletion_rate` | `final_metrics.csv` | maximum of `degradation_rate` over the returned time points |
| `maximum_product_release_rate` | `final_metrics.csv` | maximum of `product_release_rate` over the returned time points |
| `process_rate.<process_id>` | `time_series_long.csv` | rate of one configured process, in its own rate units |

Each rate is in its state's units per time unit, and the rate rows carry the
source `simulation_state_rate`. The values come from the sample bundle's
`state_rates.csv`: at every returned time point the well-mixed solver evaluates
the same compiled right-hand side it integrated, with rates evaluated at
`max(state, 0)` as during integration. They are not finite differences of the
trajectory and not a process rate, so a product yield other than one and models
with several processes report the change of the mapped state itself.

If a case maps no substrate or no product state, or a sample bundle has no
`state_rates.csv` (bundles written before schema `2.0.0`, or producers that
record none), the rows have an empty `value`, `units` and `source` set to
`not_applicable`, and the reason in `notes`; the final metrics have status
`not_applicable` with the reason. Process rates are never used in their place.

Bundles written under schema `1.8.0` report `degradation_rate` and
`product_release_rate` as whichever process rate was listed last at each time
point, and both maximum-rate metrics as the largest rate of any process, in
that process's units. Those values are wrong for models with more than one
process and for product yields other than one; do not compare them with schema
`2.0.0` values.

## Configured-model artifacts

Configured runs also write:

- the resolved input configuration;
- merged parameters;
- entity snapshots;
- process build decisions;
- state, process-rate and net state-rate trajectories (`state_trajectories.csv`,
  `process_rates.csv`, `state_rates.csv`; the last is header-only when the
  producer records no state rates);
- validation and solver reports;
- conservation and thermodynamic summaries when configured;
- entropy-production-rate trajectories when every required conversion and
  provenance input is explicit;
- a package-version and source-revision record;
- `output_manifest.json`.

## Reports

```python
result.write_report(
    "outputs/report",
    include_html=True,
    include_index=True,
)
```

The report renderer reads existing tables. It does not add scientific logic,
infer biology, or reinterpret unavailable values.

## Quick-look figures

Quick-look plots are generated from standard tables for inspection. They are
not publication-grade validation figures and do not add calibration evidence.
`fungmod run --no-plots` (or `simulate(..., quicklook=False)`) skips them, and
`result.write_quicklook_plots()` draws them again from the tables. They add no
table, column or value: the output schema is unchanged by them.

Every run writes five run-level figures to `figures/`, overlaying its cases:

| File | What it draws |
| --- | --- |
| `substrate_remaining_vs_time.png` | every sample's substrate state (`state_role` `substrate`) |
| `product_release_vs_time.png` | every sample's `product_formed` |
| `degradation_fraction_vs_time.png` | every sample's `substrate_degraded_fraction` |
| `degradation_rate_vs_time.png` | every sample's `degradation_rate` (the substrate's state rate) |
| `trajectory_quantile_bands.png` | p05-p95 band and p50 of `trajectory_quantiles.csv` for the first three series in the order substrate states, `product_formed`, `substrate_degraded_fraction` |

When the rows of one of the first four figures come in more than one units
text, value or time (cases of a grid in g/L and in mM, or in hours and in
minutes), each units text gets its own panel with its units on both axes;
before, they shared one axis labelled with the first units. A run in one units
text draws exactly as before.

### Networks, cultures and chains

A case whose time series hold the rates of more than one process (an
[enzyme network](../user-data.md#several-enzymes-acting-together) of two or more
classes, a [fungal culture](../user-data.md#fungal-culture-growth-and-secretion),
the registry's extracellular enzyme chain) also gets two figures of its own,
after the run-level figures in case-id order:

| File | Panels |
| --- | --- |
| `<case_id>_state_trajectories.png` | One panel per simulated state (`source` `simulation_state`): the substrate (for a network, the entry pool), the intermediate pools in their order and the final product, then every other state as the table lists it (the enzymes; for a culture the biomass, each enzyme pool and both closure ledgers). Each panel is in its state's own units, `value (<units>)`. The substrate panel marks the times to 10, 50 and 90 % substrate degradation of `threshold_times.csv` (the same thresholds as for every case: (S0 - S) / S0 of the case's substrate state) at their p50 from `summary_metrics.csv`, shaded p05-p95 when the samples differ, with the number of samples that reached each; a threshold no sample reached is listed as not reached. |
| `<case_id>_process_rates.png` | One panel per `process_rate.<process_id>` series of `time_series_long.csv`: each process law as the solver evaluated it at the returned times, in its own rate units, `rate (<units>)`, never converted (a culture's loss rates are recorded per second and its synthesis rates per hour). For a network, each panel names the process's enzyme class and pool and its rate modifiers (a competitive inhibitor), read from the per-process rows of `mechanism_summary.csv` (the template's `process_enzyme_classes`). |

With more than one sample, each panel shows the p05-p95 band and the p50 of
`trajectory_quantiles.csv` (a summary of the simulated samples, not validation
or a confidence interval); with one sample, the sample itself. No two units
share a value axis, so a solid in g/L and its released pool in mmol/L, or an
assay-unit pool and the biomass, are never drawn against one scale. A case
with one process (every single-class case) gets the run-level figures only.
