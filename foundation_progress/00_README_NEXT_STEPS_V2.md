# Active Next Steps

Use `ROADMAP_ORCHESTRATION_STATUS.md` for the current PR queue and phase
status.

Scoped status as of PR-19 after merge:

```text
SOURCE-002: complete for the offline notebook discovery/proposal workflow.
PRE-BIO-001 / ASSEMBLY-001 basics: complete for current template-backed cases.
BIO-READINESS-LITE: complete for the proposal template, validator, and tests.
BIO-002: complete for scoped reusable two-step enzyme-chain assembly.
CASE-001: complete once PR-02 is merged for the researcher-facing named API path.
VALIDATION-DATA-001: deferred; blocked/partial for ingestion until a
source-backed numeric time-course dataset satisfies the active gate.
PRODUCT-001: partial after top-level environment_grid helper,
assumption_summary.csv, modelability_items.csv, write_preflight_report, the
scoped `DegradationScreenResult.write_report(...)` Markdown report writer, the
PR-09 HTML report wrapper, and the PR-10 report-folder index/navigation slice.
The PR-09 `include_html=True` option and PR-10 `include_index=True` option
remain opt-in presentation layers over existing standard outputs.
The completed screen-comparison summary slice adds `comparison_summary.csv` as
a derived index over existing final-metric and threshold rows with explicit
comparison/ranking guardrail columns.
The completed comparison/report-output example-notebook slice demonstrates the
public workflow for writing reports and inspecting those guardrails without
ranking metadata-only environment grids.
Virtual-experiment outputs now include mechanism_summary.csv for active process
laws, maturity, assumptions, limitations, and provenance.
Example notebooks now include `10_virtual_experiment_product_tour.ipynb` for a
public-API virtual-experiment tour without validation claims.
Example notebooks also include
`13_screen_comparison_summary_example.ipynb` for public-API report-output and
guarded `comparison_summary.csv` inspection without validation claims.
Example notebooks now include
`14_trajectory_quantiles_example.ipynb` for public-API trajectory-quantile
inspection and presentation-only quicklook generation without validation
claims.
The completed degradation-rate quicklook/report ergonomics slice adds a
presentation-only `degradation_rate_vs_time.png` quicklook and a bounded degradation-rate inspection section
from existing `time_series_long.csv` `degradation_rate` rows without changing
solver/model behavior.
THERMO-003: partial after explicit reaction-quotient Gibbs/entropy validator,
configured entropy-production-rate metadata diagnostic, configured
thermodynamic JSON/CSV summaries, notebook coverage for both explicit-Q and
entropy-rate output rows, and a configured entropy-budget JSON summary over
numeric explicit entropy-rate rows; there are still no inferred activities,
concentrations, redox potentials, electron balances, or solver-time
thermodynamic enforcement.
Thermodynamic summaries are available as JSON and CSV when such validators run.
The JSON summary includes `has_entropy_budget`,
`entropy_budget_evaluated_count`, `entropy_budget_negative_count`, and
`entropy_budget_status` fields while leaving missing or non-numeric
entropy-rate metadata unevaluated rather than treating it as zero.
Example notebooks now include
`11_thermodynamics_entropy_diagnostics.ipynb` for configured explicit-Q Gibbs,
entropy-production-rate, and entropy-budget output inspection without
validation claims or solver-time enforcement, including the
`has_entropy_production_rate`, `has_entropy_budget`, and
`entropy_budget_status` summary fields.
BIO-003: partial/software-tested for generic reversible product inhibition as
an explicit configured process modifier and registry-backed case-template
assembly when explicit product-state and K_i records exist.
The scoped reversible-product-inhibition target now has a public example
notebook, `12_reversible_product_inhibition_example.ipynb`, that compares
inhibited and uninhibited exploratory virtual experiments and inspects
mechanism summaries, configured metadata, limitations, and final metrics
without validation claims.
```

Current next PR: **PR-20: PRODUCT-001 threshold-time inspection/report ergonomics**.

The PR-03 gate document records that the existing Resa/Buckin and
Ariaeenejad/Frontiers candidate reviews are blocked and that this repo still
has no real observation table under `data/experiments/literature/`. That blocks
validation, calibration, and empirical comparison claims; it does not block
building the simulator.

Build-first work should now improve FungMod as a virtual-experiment engine:
broader researcher-facing inputs, explicit exploratory priors, richer
degradation curves, uncertainty bands, provenance, limitations,
missing-mechanism reports, and generic thermodynamic/entropy constraints. Do
not advance validation again until the simulator outputs are mature enough that
comparison to observations is meaningful.

The first PRODUCT-001 implementation slices add the top-level
`environment_grid(...)` helper plus `assumption_summary.csv` and
`modelability_items.csv` outputs, plus a `write_preflight_report(...)` path for
blocked cases. They improve the target researcher workflow and make exploratory
assumptions, uncertain inputs, and preflight facts easier to inspect, but
runtime pH, temperature, and oxygen grid values remain metadata-only unless an
explicit response law or condition-specific parameter record is active.
The completed screen-comparison summary slice adds `comparison_summary.csv` and
`DegradationScreenResult.comparison_summary()` as a derived view over existing
standard output rows. The completed example-notebook slice preserves
metadata-only environment guardrails and must not add biological mechanisms,
solver behavior, validation data, calibration, empirical-comparison claims,
unsupported ranking, inferred environment response, or hidden scientific logic.
The completed uncertainty-output ergonomics slice adds
`uncertainty_summary.csv` and
`DegradationScreenResult.uncertainty_summary()` as a derived view over existing
sampled-parameter and summary-metric rows. It preserves allowed-use,
uncertainty-band status, and interpretation guardrails and must not be read as
validation, calibration, empirical confidence intervals, posterior
uncertainty, inferred environment response, or solver/model behavior.
The completed trajectory-quantile output ergonomics slice adds
`trajectory_quantiles.csv` and
`DegradationScreenResult.trajectory_quantiles()` as a derived view over
existing `time_series_long.csv` sample rows. It preserves allowed-use,
trajectory-band status, and interpretation guardrails and must not be read as
validation data, calibration evidence, empirical confidence intervals,
posterior uncertainty, inferred environment response, or solver/model
behavior.
The completed trajectory-quantile example and quicklook ergonomics slice adds
`14_trajectory_quantiles_example.ipynb` and a presentation-only
`trajectory_quantile_bands.png` quicklook generated from
`trajectory_quantiles.csv`. The figure is an inspection artifact over existing
standard output tables, not validation, calibration, empirical comparison,
posterior uncertainty, inferred environment response, or solver/model
behavior.
The completed degradation-rate quicklook/report ergonomics slice adds
`degradation_rate_vs_time.png` as a presentation-only quicklook generated from
existing `time_series_long.csv` `degradation_rate` rows. The Markdown report
and optional HTML/index outputs expose those existing rate rows for inspection
with explicit guardrails; they do not add validation, calibration, empirical
comparison, a new rate law, inferred environment response, or solver/model
behavior.

THERMO-003 configured-output diagnostics should remain explicit metadata in and
`thermodynamic_summary.json`/`.csv` out. The completed notebook inspection path
must not infer activities, reaction quotients, concentrations, redox potentials,
electron balances, validation evidence, or solver-time thermodynamic
enforcement.

The current PRODUCT-001 slice should improve threshold-time inspection and
report ergonomics from existing `threshold_times.csv`, `summary_metrics.csv`,
and report/index paths only. It must not add validation data, calibration,
empirical-comparison claims, inferred environment responses, posterior
uncertainty claims, solver/model changes, hidden notebook science, or silent
fallback constants.

The first BIO-003 target is generic reversible product inhibition. The
mechanism is recorded in `BIO_003_GENERIC_PROCESS_LAWS.md` and the
machine-checkable `proposals/BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml`.
Configured model processes can now opt into it with explicit `product_state`
and positive unit-compatible `K_i`. Registry-backed case templates can now
carry explicit product-inhibition modifiers into configured runs and standard
mechanism summaries when product-state and `K_i` records exist. The scoped
researcher-facing example for this reversible-product-inhibition target is
covered by `notebooks/examples/12_reversible_product_inhibition_example.ipynb`;
broad BIO-003 remains partial.

`old_progress/` is historical and non-binding.
