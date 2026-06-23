# VALIDATION-DATA-001: First Real Time-Course Dataset

## Goal

Add the first real experimental time-course dataset for model comparison.

Recommended:

```text
beta-glucosidase + cellobiose -> glucose time course
```

or:

```text
cellulase/cellulose -> soluble sugar release time course
```

Do not start with whole-fungus growth. Do not overclaim validation.

## Current Status

Status: `deferred; blocked/partial` for ingestion.

Current next PR: **PR-13: THERMO-003 entropy-production-rate notebook coverage**.

This phase has a machine-checkable ingestion gate, but it does not yet have a
source-backed real time-course dataset in the repository. Validation remains
important, but it is deferred as PR-14 until the simulator can produce mature
enough degradation outputs for comparison. This gate does not complete VALIDATION-DATA-001.

## Candidate Evidence Checked

The current repo contains two real candidate reviews under
`data/experiments/candidate_reviews/`:

- `resa_buckin_2011_cellobiose_hydrolysis_review.yml`
- `ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml`

Both are review-only records. They intentionally contain no observations,
measurement rows, extracted figure data, `data_file`, or `csv_path` fields.

### Resa and Buckin 2011 Candidate

Candidate review:
`data/experiments/candidate_reviews/resa_buckin_2011_cellobiose_hydrolysis_review.yml`

Decision: `blocked_do_not_ingest`.

Why blocked:

- no ingestable observation rows were found in the current repo review;
- no machine-readable observation CSV was found;
- no exact figure/table observation extraction metadata is available;
- no extraction method, extractor/date, uncertainty policy, unit-conversion
  notes, preprocessing notes, or excluded-point decisions are recorded.

The candidate may remain useful if full text, supplementary material, or
author-supplied data provide source-backed numeric observations, but it must
not be ingested from the current review alone.

### Ariaeenejad 2020 PersiBGL1 Candidate

Candidate review:
`data/experiments/candidate_reviews/ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml`

Decision: `blocked_time_axis_conflict_do_not_ingest`.

Why blocked:

- no machine-readable time-course observation table was found;
- Figure 6 has not been digitized into local observation rows;
- uncertainty is not defined;
- the public source has an unresolved time-axis conflict.

Frontiers time-axis conflict blocker:

- hour-based evidence in the review says the method used 24-h intervals until
  380 h;
- the Figure 6 caption says 380 h;
- one result sentence describes glucose from 1 h to 380 h and little change
  after 300 h;
- one nearby result sentence says conversion reaches zero after 380 min.

Choosing hours by majority evidence would be an inference. The repository must
not digitize, ingest, or normalize this candidate until the time axis is
resolved from source-backed evidence such as author-supplied raw data, an
erratum, an unambiguous figure axis, or a machine-readable supplement.

## Required Evidence Before Ingestion

A future real-data ingestion PR must add source-backed numeric observations and
record all of these fields before creating a literature dataset:

- `figure_or_table_or_supplement_identifier`: exact source location for the
  observations.
- `observation_rows`: machine-readable time-course rows with raw time and value
  values.
- `units`: raw time units, measured-value units, and any model-target units.
- `extraction_or_transcription_method`: table transcription, supplement import,
  figure digitization, or another explicit method.
- `extractor_and_date`: who extracted or transcribed the values and when.
- `preprocessing_and_conversion_notes`: unit conversions, excluded points,
  normalization, averaging, baseline handling, and any other transformation.
- `uncertainty_policy`: observed uncertainty values, digitization uncertainty,
  assumed absence of uncertainty, or an explicit reason uncertainty is unknown.
- `explicit_limitations`: source limitations, extraction limitations,
  model-comparison limits, and validation-claim limits.

The ingestion PR should then add the appropriate literature dataset files and
model-comparison artifacts with tests. Until these fields are complete,
VALIDATION-DATA-001 remains blocked/partial.

## Files Not Added In This PR

This gate PR adds no real dataset or model-comparison output. In particular, it
does not add:

- `raw_data.csv`;
- `curated_data.csv`;
- `model_comparison.csv`;
- `residuals.csv`;
- `validation_report.md`;
- any other real observation table under `data/experiments/literature/`.

No scientific model, parameter, numerical method, runtime behavior, output
schema, or biology changes in this gate PR.

## Next Action

First build out PRODUCT-001, THERMO-003, and generic BIO-003 simulator
capability. Later, find or obtain source-backed numeric time-course
observations that satisfy the required evidence fields above. Then open a
separate ingestion PR for VALIDATION-DATA-001 with the dataset, comparison
workflow, limitations, and tests.
