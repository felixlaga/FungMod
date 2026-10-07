# Outputs and artifacts

FungMod prioritizes tables over notebook-only plots. Every reported number
should be recoverable from an exported artifact.

## Standard virtual-experiment tables

| Artifact | Purpose |
| --- | --- |
| `modelability_preflight.csv` | One preflight outcome per case. |
| `modelability_items.csv` | Known, uncertain, missing, or unsupported inputs. |
| `time_series_long.csv` | Long-form state and derived trajectories. |
| `final_metrics.csv` | Final substrate/product metrics and maximum rates. |
| `threshold_times.csv` | Times to configured degradation fractions. |
| `sampled_parameters.csv` | Every sampled value with source and allowed-use metadata. |
| `uncertainty_summary.csv` | Summaries over sampled inputs and output metrics. |
| `trajectory_quantiles.csv` | Time-indexed exploratory trajectory bands. |
| `mechanism_summary.csv` | Active process laws and modifiers. |
| `assumption_summary.csv` | Explicit assumptions attached to cases and processes. |
| `provenance_table.csv` | Source and provenance rows used by the run. |
| `limitations_table.csv` | Known interpretation boundaries. |
| `missing_parameters.csv` | Inputs that remain unavailable. |
| `suggested_experiments.csv` | Measurements that would reduce missingness or uncertainty. |
| `comparison_summary.csv` | Side-by-side metrics plus comparison/ranking guardrails. |
| `conservation_diagnostics.csv` | Copied configured conservation diagnostics, when present. |
| `thermodynamic_diagnostics.csv` | Copied configured thermodynamic diagnostics, when present. |
| `solver_diagnostics.csv` | Solver metadata without invented quality thresholds. |
| `timecourse_comparison.csv` | Written on request by `result.compare_with_timecourses()`: simulated median and 5-95 % band at the user's observed times, residuals and RMSE; in-sample agreement, not validation (schema `2.1.0`). |

Header-only diagnostic tables mean that the corresponding configured evidence
was unavailable. Missing diagnostics are not converted to zeros.

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
