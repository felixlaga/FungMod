# Active Next Steps

Use `ROADMAP_ORCHESTRATION_STATUS.md` for the current PR queue and phase
status.

Scoped status as of PR-28 after PR #43 merged, with PR-29 selected:

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
The completed threshold-time inspection/report ergonomics slice exposes
existing `threshold_times.csv` rows and `summary_metrics.csv` threshold
quantiles in the deterministic report and report/index links without
validation claims.
The completed provenance/limitations report ergonomics slice adds a Markdown
decision summary and richer assumption, limitation, missing-parameter,
suggested-experiment, and provenance row renderers derived only from existing
standard output tables. HTML and index paths add links to those existing
decision-support tables without changing the Markdown-primary contract.
The completed provenance/limitations report example-notebook slice adds
`15_provenance_limitations_report_example.ipynb` as a public-API example that
writes Markdown/HTML/index report artifacts and inspects the table-derived
decision summary plus existing decision-support links and rows without
validation claims.
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
Report utilities now add Markdown, HTML, and report-folder index visibility for
existing configured-output `thermodynamic_summary.json` and
`thermodynamic_summary.csv` artifacts without inferring thermodynamic inputs or
adding solver-time enforcement.
Standard virtual-experiment outputs now include `thermodynamic_diagnostics.csv`
and `DegradationScreenResult.thermodynamic_diagnostics()` as a bridge over
existing per-sample configured-output `thermodynamic_summary.json`/`.csv` artifacts only. The table is header-only when no configured thermodynamic
artifacts exist and must not be read as inferred activities, reaction
quotients, concentrations, redox potentials, electron balances, validation
evidence, or solver-time thermodynamic enforcement.
Example notebooks now include
`11_thermodynamics_entropy_diagnostics.ipynb` for configured explicit-Q Gibbs,
entropy-production-rate, and entropy-budget output inspection without
validation claims or solver-time enforcement, including the
`has_entropy_production_rate`, `has_entropy_budget`, and
`entropy_budget_status` summary fields.
Example notebooks now also include
`16_thermodynamic_diagnostics_example.ipynb` for public-API inspection of the
standard `thermodynamic_diagnostics.csv` table, the header-only no-artifact
case, and a labelled package-generated artifact-copy demonstration without
validation claims or solver-time enforcement.
Configured generic processes can now opt into existing
`temperature_arrhenius_reference` and `ph_gaussian` environmental rate
modifiers when explicit Arrhenius or Gaussian pH parameters and the required
environment values are supplied. This is explicit configured framework
behavior, not inferred environment-response biology, calibration, validation,
or empirical comparison.
Example notebooks now include
`17_configured_environment_modifiers_example.ipynb` for public configured
workflow inspection of those explicit environment modifiers through
package-generated configured metadata, assumptions, merged parameters, entity
snapshots, and process rates without fitted response curves, validation,
empirical comparison, inferred environment responses, or EnvironmentGrid
behavior changes.
Configured generic processes can also opt into existing `oxygen_monod` and
`water_activity_threshold` environmental rate modifiers when explicit oxygen
half-saturation, oxygen units, water-activity threshold parameters, and the
required environment values are supplied. This is explicit configured framework
behavior, not inferred oxygen or moisture biology, calibration, validation,
empirical comparison, oxygen consumption, gas transfer, redox balance,
anaerobic metabolism, substrate water binding, or EnvironmentGrid behavior.
BIO-003: partial/software-tested for generic reversible product inhibition as
an explicit configured process modifier, registry-backed case-template
assembly, and a non-PET configured framework benchmark when explicit
product-state and K_i records exist.
The scoped reversible-product-inhibition target now has a public example
notebook, `12_reversible_product_inhibition_example.ipynb`, that compares
inhibited and uninhibited exploratory virtual experiments and inspects
mechanism summaries, configured metadata, limitations, and final metrics
without validation claims.
```

Current next PR: **PR-29: explicit oxygen and water-activity configured modifiers**.

The PR-03 gate document records that the existing Resa/Buckin and
Ariaeenejad/Frontiers candidate reviews are blocked and that this repo still
has no real observation table under `data/experiments/literature/`. That blocks
validation, calibration, and empirical comparison claims; it does not block
building the simulator.

Because the current validation evidence gate is still blocked, PR-27 completed
a build-first configured environment-modifier slice that wires existing
`TemperatureModifier` and `PHModifier` response laws into generic configured
processes with explicit parameters and environment values, and PR-28 completed
a public configured-workflow example notebook for those modifiers after
PR #43 merged. The selected PR-29 work is now a build-first configured
oxygen/water-activity modifier slice that wires existing `OxygenModifier` and
`WaterActivityModifier` response laws into generic configured processes with
explicit parameters, oxygen units, and environment values, without validation
data, calibration, empirical comparison, solver-law changes, silent fallback
constants, inferred environment responses, oxygen consumption, gas transfer,
redox balance, anaerobic metabolism, substrate water-binding behavior,
EnvironmentGrid behavior changes, hidden notebook science, or new biology
claims.

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
The completed thermodynamic-diagnostics bridge slice adds
`thermodynamic_diagnostics.csv` and
`DegradationScreenResult.thermodynamic_diagnostics()` as a standard table
derived only from existing per-sample configured-output
`thermodynamic_summary.json`/`.csv` artifacts. It preserves artifact-presence,
entropy-budget, allowed-use, and interpretation guardrails and must not be
read as inferred thermodynamics, validation evidence, empirical comparison, or
solver-time enforcement.
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

The completed threshold-time inspection/report ergonomics slice improves
inspection of existing `threshold_times.csv` rows and `summary_metrics.csv`
threshold quantiles in report paths only. It does not add validation data,
calibration, empirical-comparison claims, inferred environment responses,
posterior uncertainty claims, solver/model changes, hidden notebook science,
schema changes, or silent fallback constants.

The completed THERMO-003 thermodynamic-summary report ergonomics slice exposes
existing `thermodynamic_summary.json` and `thermodynamic_summary.csv` artifacts
in Markdown, HTML, and index report paths only. It does not infer activities,
reaction quotients, concentrations, redox potentials, electron balances,
validation evidence, or solver-time thermodynamic enforcement.

The completed provenance/limitations report ergonomics slice improves
inspection of existing assumption, limitation, missing-parameter,
suggested-experiment, and provenance rows in Markdown, HTML, and index report
paths only. It does not add validation data, calibration, empirical comparison,
inferred environment responses, hidden notebook science, schema changes, or
solver/model behavior.

The completed PRODUCT-001 provenance/limitations example-notebook slice adds a
public-API example notebook that writes reports and inspects the
provenance/limitation decision summary and decision-support table links. It
does not add validation data, calibration, empirical comparison, inferred
environment responses, hidden notebook science, schema changes, or
solver/model behavior.

VALIDATION-DATA-001 remains deferred and evidence-gated. A validation
ingestion PR should start only if source-backed numeric time-course
observations satisfy the active gate; otherwise future makers should pick
build-first simulator/output ergonomics slices rather than treating incomplete
candidate reviews as data.

The first BIO-003 target is generic reversible product inhibition. The
mechanism is recorded in `BIO_003_GENERIC_PROCESS_LAWS.md` and the
machine-checkable `proposals/BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml`.
Configured model processes can now opt into it with explicit `product_state`
and positive unit-compatible `K_i`. Registry-backed case templates can now
carry explicit product-inhibition modifiers into configured runs and standard
mechanism summaries when product-state and `K_i` records exist. The scoped
researcher-facing example for this reversible-product-inhibition target is
covered by `notebooks/examples/12_reversible_product_inhibition_example.ipynb`;
the non-PET configured benchmark is
`data/model_configs/toy_surface_dummy_non_pet_product_inhibition.yml`. Broad
BIO-003 remains partial.

`old_progress/` is historical and non-binding.
