# FungMod Data

This folder holds human-editable fixtures and, later, curated scientific data.
The current data-infrastructure layer is intentionally synthetic-first: it
tests provenance, units, residuals, output bundles, and calibration plumbing
without adding real fungal biology or literature-derived values.

## Maturity Labels

Data and dataset records must use explicit maturity labels:

- `toy`: artificial benchmark values for software tests.
- `synthetic`: generated from a known model/config or documented fixture.
- `literature_raw`: minimally processed values transcribed or digitized from a source.
- `literature_processed`: cleaned or converted literature values with tracked preprocessing.
- `calibrated`: outputs or parameter sets produced by fitting.
- `validated`: outputs checked against independent data not used for fitting.

Toy and synthetic data are not empirical evidence.

## Current Layout

The foundation configs still keep some legacy top-level fixture files under
folders such as `substrates/`, `enzymes/`, `geometries/`, and `parameters/`.
New experiment and calibration infrastructure is organized by maturity under:

- `experiments/synthetic/`;
- `experiments/literature/`;
- `experiments/validation/`;
- `calibration/synthetic/`.

Do not add real literature data until the literature extraction contract is
implemented and covered by tests.
