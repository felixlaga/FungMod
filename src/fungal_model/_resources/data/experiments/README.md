# Experiment Datasets

This folder contains dataset metadata and observation files for FungMod data
infrastructure tests and, later, curated scientific datasets.

The first literature-raw dataset is available under
`literature/alvarez_gonzalez_2022_free_beta_glucosidase/`. New empirical paper
values still require the tested literature extraction and provenance contract;
the presence of one reviewed dataset is not blanket authorization to ingest
unreviewed observations.

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

## Model Comparison

Dataset measurements must be compared to model outputs through explicit
observable mappings. FungMod does not infer that a dataset column and a model
state mean the same thing from similar names.

Initial comparison outputs are written as an inspectable bundle:

- `comparison_record.json`;
- `dataset_snapshot.json`;
- `observable_mapping.json`;
- `residuals.csv`;
- `metrics.json`;
- `validation_report.json`;
- `figures/observed_vs_predicted.png`;
- `figures/residuals.png`.

Synthetic comparison results are infrastructure checks only. They are not
empirical validation and must not be used as biological evidence.

## Candidate Reviews

Before any real literature dataset is inserted, add a dataset candidate review
under `data/experiments/candidate_reviews/`. Candidate reviews are not datasets:
they must not include observations, measurement rows, CSV paths, or extracted
values. They exist to document the candidate source, intended use, exclusion
criteria, and required schema gates before ingestion begins.
