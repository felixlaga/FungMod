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

Header-only diagnostic tables mean that the corresponding configured evidence
was unavailable. Missing diagnostics are not converted to zeros.

## Configured-model artifacts

Configured runs also write:

- the resolved input configuration;
- merged parameters;
- entity snapshots;
- process build decisions;
- state and process-rate trajectories;
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
