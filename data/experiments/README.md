# Experiment Datasets

This folder contains dataset metadata and observation files for FungMod data
infrastructure tests and, later, curated scientific datasets.

No real literature data are included yet. Do not add empirical paper values
until the literature extraction and provenance schemas are implemented and
tested.

## Maturity Labels

Every experiment dataset must declare one maturity label:

- `toy`: artificial demo values, not generated from a documented model.
- `synthetic`: generated from a known model or fixture with documented inputs.
- `literature_raw`: manually digitized or transcribed values from a source.
- `literature_processed`: cleaned or converted literature data with tracked
  preprocessing.
- `calibrated`: data or parameter outputs produced by fitting.
- `validated`: data or model outputs checked against independent validation
  data.

## Toy Versus Synthetic

Toy data are arbitrary benchmark values for exercising software paths.
Synthetic data are generated from a known equation, model result, or fixture
record and must include enough metadata to reproduce the intent of the
generated observations.

Neither toy nor synthetic data are empirical biological evidence.

## Required Metadata

Experiment dataset YAML files must include:

- `kind: experiment_dataset`;
- `dataset_id`, `name`, and `maturity`;
- source/provenance metadata;
- system metadata;
- experimental conditions;
- measurement-series metadata;
- preprocessing records;
- validation rules for expected CSV columns and uncertainty behavior.

Measurement series must declare explicit time and value units. If an
uncertainty column is configured, uncertainty units are required. Missing
uncertainty is allowed only when `validation.allow_missing_uncertainty: true`
is explicitly set.
