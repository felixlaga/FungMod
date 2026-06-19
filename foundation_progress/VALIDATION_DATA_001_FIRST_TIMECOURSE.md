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

## PR-03 Source Assessment

Date: 2026-06-19

Status: `blocked pending ingestable source`.

PR-03 did not add a real experiment dataset. The source assessment found no
public source that currently satisfies the local ingestion criteria for a
real time-course dataset:

- source-backed observation rows with explicit time and value units;
- publication, DOI or URL, authors, year, and exact figure/table/supplement
  identifier;
- extraction or transcription method, extractor, extraction date, and raw
  source units;
- digitization metadata and axis calibration when values come from a figure;
- uncertainty definition or an explicit missing-uncertainty policy;
- preprocessing, conversion, excluded-point, and limitation notes;
- an honest maturity label such as `literature_raw` or
  `literature_processed`;
- explicit `ObservableMapping` for model comparison, with no fuzzy matching.

Two reviewed beta-glucosidase/cellobiose candidates remain blocked:

- `resa_buckin_2011_cellobiose_hydrolysis_review.yml` remains a candidate
  review only because no ingestable observation rows, machine-readable table,
  supplementary data, digitization metadata, or uncertainty/preprocessing
  record were found in public checks.
- `ariaeenejad_2020_persibgl1_cellobiose_hydrolysis_review.yml` remains a
  candidate review only because Figure 6 has no machine-readable observation
  table and the source text has an unresolved time-axis conflict. Method,
  caption, and one result passage support hours, while another result sentence
  says 380 min. FungMod must not resolve that conflict by inference or majority
  vote.

## Current Completion State

VALIDATION-DATA-001 is not complete. The current honest state is a strengthened
blocker/gate: the repo records why no dataset was ingested, keeps the current
next PR on PR-03, and tests that the known blocked candidates are not converted
into `ExperimentDataset` records or marked as complete.

## Evidence Required To Unblock

A future PR may complete this phase only after it adds a local curated real
time-course dataset bundle with source-backed observations and equivalent
metadata to:

```text
experiment_dataset.yml
raw_data.csv
curated_data.csv
model_comparison.csv
residuals.csv
validation_report.md
```

The repo may map those names into the existing dataset/comparison bundle shape
if all equivalent information is present and documented. Any comparison report
must say whether the result is validation, calibration, or qualitative
comparison, and must avoid empirical-validation claims when parameters,
enzyme/source identity, assay conditions, or preprocessing do not match.

## Out Of Scope

This blocker pass did not add biology, parameter values, observation rows,
digitized figure values, model calibration, scientific-mode validation claims,
whole-fungus growth, secretion, uptake, biomass, PET, lignin, full
lignocellulose, organism-specific physiology, or runtime calls to live
external APIs.
