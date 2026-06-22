# Active Next Steps

Use `ROADMAP_ORCHESTRATION_STATUS.md` for the current PR queue and phase
status.

Scoped status as of PR-07:

```text
SOURCE-002: complete for the offline notebook discovery/proposal workflow.
PRE-BIO-001 / ASSEMBLY-001 basics: complete for current template-backed cases.
BIO-READINESS-LITE: complete for the proposal template, validator, and tests.
BIO-002: complete for scoped reusable two-step enzyme-chain assembly.
CASE-001: complete once PR-02 is merged for the researcher-facing named API path.
VALIDATION-DATA-001: deferred; blocked/partial for ingestion until a
source-backed numeric time-course dataset satisfies the active gate.
PRODUCT-001: partial after top-level environment_grid helper,
assumption_summary.csv, modelability_items.csv, and write_preflight_report.
Virtual-experiment outputs now include mechanism_summary.csv for active process
laws, maturity, assumptions, limitations, and provenance.
Example notebooks now include `10_virtual_experiment_product_tour.ipynb` for a
public-API virtual-experiment tour without validation claims.
THERMO-003: partial after explicit reaction-quotient Gibbs/entropy validator
and configured entropy-production-rate metadata diagnostic; configured runs
now summarize those diagnostics, but there are still no inferred activities,
concentrations, redox potentials, electron balances, or solver-time
thermodynamic enforcement.
Thermodynamic summaries are available as JSON and CSV when such validators run.
Example notebooks now include
`11_thermodynamics_entropy_diagnostics.ipynb` for configured explicit-Q Gibbs
and entropy-output inspection without validation claims or solver-time
enforcement.
BIO-003: partial/software-tested for generic reversible product inhibition as
an explicit configured process modifier and registry-backed case-template
assembly when explicit product-state and K_i records exist.
The scoped reversible-product-inhibition target now has a public example
notebook, `12_reversible_product_inhibition_example.ipynb`, that compares
inhibited and uninhibited exploratory virtual experiments and inspects
mechanism summaries, configured metadata, limitations, and final metrics
without validation claims.
```

Current next PR: **PR-07: BIO-003 researcher-facing product inhibition example**.

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

The current THERMO-003 slices should remain configured-output focused:
explicit caller-supplied dimensionless Q, temperature, standard Gibbs,
condition-specific delta G, and reaction extent-rate metadata in;
`thermodynamic_summary.json` and `.csv` out. They must not infer activities,
reaction quotients, concentrations, redox potentials, electron balances,
validation evidence, or solver-time thermodynamic enforcement.

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
