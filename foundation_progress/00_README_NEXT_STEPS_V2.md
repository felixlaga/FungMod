# Active Next Steps

Use `ROADMAP_ORCHESTRATION_STATUS.md` for the current PR queue and phase
status.

Scoped status as of PR-05:

```text
SOURCE-002: complete for the offline notebook discovery/proposal workflow.
PRE-BIO-001 / ASSEMBLY-001 basics: complete for current template-backed cases.
BIO-READINESS-LITE: complete for the proposal template, validator, and tests.
BIO-002: complete for scoped reusable two-step enzyme-chain assembly.
CASE-001: complete once PR-02 is merged for the researcher-facing named API path.
VALIDATION-DATA-001: deferred; blocked/partial for ingestion until a
source-backed numeric time-course dataset satisfies the active gate.
PRODUCT-001: current next for build-first exploratory virtual-experiment
expansion; partial after top-level environment_grid helper,
assumption_summary.csv, and modelability_items.csv.
THERMO-003: queued for dynamic thermodynamic and entropy constraints.
BIO-003: queued for generic mechanism expansion after build-first simulator work.
```

Current next PR: **PR-05: PRODUCT-001 build-first exploratory virtual-experiment expansion**.

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
`modelability_items.csv` outputs. They improve the target researcher workflow
and make exploratory assumptions, uncertain inputs, and preflight facts easier
to inspect, but runtime pH, temperature, and oxygen grid values remain
metadata-only unless an explicit response law or condition-specific parameter
record is active.

`old_progress/` is historical and non-binding.
