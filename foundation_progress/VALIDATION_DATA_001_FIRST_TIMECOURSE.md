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

Status: `complete` for the bounded first same-source, no-calibration comparison;
not independent validation.

Current next task: acquire an independent or held-out time course with defined
experimental uncertainty before making any validation or generalization claim.

This phase has a machine-checkable ingestion gate and now contains one
source-backed, nine-point literature-raw cellobiose time course satisfying the
evidence requirements below. The exact published Model 3 inhibition law and
point estimates now run through the generic configured workflow, and the
comparison runner persists model, residual, metric, provenance, mapping,
validation-report, and figure artifacts without fitting.
The PR-31 work is complete after
PR #46, PR-32 repository hygiene cleanup is complete after PR #47, PR-33
chain-template explicit environment modifier assembly is complete after
PR #48, and PR-34 configured-output conservation/drift diagnostics is complete
after PR #49. PR-35 repository hygiene guardrail extension is complete after
PR #50. PR-36 configured-output solver diagnostics is complete after PR #51.
PR-37 solver diagnostics visibility follow-up is complete after PR #52. PR-38
solver diagnostics example notebook is complete after PR #53. PR-39
virtual-experiment solver diagnostics bridge is complete after PR #54. PR-40
virtual-experiment conservation diagnostics bridge is complete after PR #55.
PR-41 Pyright optional-member-access ratchet is complete after PR #56. PR-42
arbitrary-length linear enzyme-chain assembly is complete after PR #57. PR-43
process-bound entropy-production-rate diagnostics is complete after PR #58.
PR-44 researcher source-provider onboarding is complete after PR #59. The
PR-45 CURATION-001 proposal-review and decision-bundle work is complete after
PR #60 merged as `5ac7864`. PR-46 registry-promotion planning is complete after
PR #61 merged as `2b6c639`. PR-47 transactional apply is complete after PR #62
merged as `b1ebb860`. PR-48 identity-only PARAMETER authoring is complete
after PR #63 merged as `764d1e4`. PR-49 reusable public checksum-validated
curation-bundle loading is complete after PR #64 merged as `bbe2ee6`. It centralizes the
owned manifest/schema, exact artifact inventory, declared checksums,
path/symlink containment, and shared deterministic curation-artifact contract
without registry mutation or scientific transformation. PR-50 checksum-loaded
written-source authoring is complete in the current checkout: the
identity-only PARAMETER bridge accepts a `LoadedCurationBundle`, reloads it at
call time, and preserves every existing source, registry, loader, policy, and
no-mutation guardrail. The selected PR-51 follow-up is a versioned nonidentity
ParameterRecord conversion registry with explicit parseable units,
dimensional compatibility, deterministic recomputation, and a closed rounding
policy. That PR-51 scope is complete after PR #66 merged as `bef938f`. The
PR-52 follow-up is complete after PR #67 merged as `5da611b` for non-parameter
authoring across the five index-backed record
families with closed schemas, owned destinations, loader fidelity, conservative
policies, and no authoring/planning mutation. PR-53 is complete after PR #68
merged as `19baedd` with product-map production ownership, a loader schema, an
index-declared destination, and authoring/promotion support without inferred
participants or coefficients. PR-54 is complete after PR #69 merged as
`35a3ecb` with caller-trusted Ed25519 signatures over exact manifest bytes,
decision-curator identity binding, and authoring/planning boundary
revalidation. It does not ingest validation data, establish scientific
validity, authorize simulation automatically, or claim validation.
PR-55 is complete after PR #70 merged as `6b3d275` with arbitrary reaction onboarding
for already implemented homogeneous Michaelis-Menten semantics. Explicit
registry/template records own per-reaction identity, mode, provenance, states,
parameters, product maps, and time grids; an artificial second reaction proves
the generic path without adding biological evidence or validation data.
PR-56 branching/cyclic pathway assembly is complete after PR #71 merged as
`caa0a17`. PR-57 dynamic thermodynamic feasibility and native solver-time
enforcement are complete after PR #72 merged as `ae8a5a3` for explicit sourced
molar activity/Q inputs, passing bound electron/redox evidence, and direct or
redox-derived standard energy. Neither slice adds validation data or empirical
biological evidence.
The completed PR-47 work is bounded transactional
administrative registry apply with exact digest confirmation, intentional plan
schema `2.0.0`, durable curation audit provenance, strict next-patch versioning,
full-root staging/drift checks, locking, no overwrite, and verified rollback.
It does not ingest validation data, change scientific fields, authorize
simulation automatically, or claim validation. CURATION-001 is complete for
its defined review, authoring, authentication, planning, and transactional
apply workflow; that status does not complete scientific validation.
Future validation-data additions must not ingest, digitize, or fabricate data
unless the same evidence requirements are met. The first ingestion completes
the dataset-acquisition slice, not VALIDATION-DATA-001's comparison scope.

## Ingested Evidence

The repository now includes:

- `data/experiments/literature/alvarez_gonzalez_2022_free_beta_glucosidase/`
- DOI `10.3390/catal12010080`;
- Supplementary Figure S1A, filled-square 20 g/L cellobiose series;
- nine points at the source-listed 0-60 minute sampling times;
- explicit pixel-axis calibration, source-PDF checksum, extraction tool and
  date, unit conversion, exclusions, and a 0.6 mM digitization-resolution
  estimate;
- explicit separation of digitization error from unavailable experimental
  uncertainty.

The source describes a purified commercial beta-glucosidase formulation. The
2022 paper does not directly state its biological source organism, so the
dataset deliberately leaves `system.organism` unknown. It is not a
whole-fungus dataset and cannot validate organism-specific behavior.

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

## Required Evidence For Every Ingestion

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

Every ingestion must add the appropriate literature dataset files and tests.
The first dataset's separately implemented comparison slice is described below.

## Comparison Artifacts

Run:

```bash
python scripts/run_literature_time_course_comparison.py \
  --output-dir outputs/alvarez_gonzalez_2022_comparison
```

The runner writes the configured model bundle and a comparison bundle containing
`model_comparison.csv`, `residuals.csv`, `metrics.json`,
`comparison_record.json`, `dataset_snapshot.json`, `observable_mapping.json`,
`validation_report.json`, `validation_report.md`, and two figures.

The configured model uses Supplementary Table S3 Model 3 exactly:

```text
r = Vmax*S / (Km*(1 + P/Kp)^2 + S*(1 + S/Ki))
```

with `Km=43.0 mM`, `Ki=1088.0 mM`, `Kp=34.0 mM`, and
`Vmax=19.72544 mM/min`, the latter derived from the reported
`kcat=333.2 micromole/min/mg` and `59.2 mg/L` dose. FungMod performs no
parameter fitting. The nine-point RMSE is approximately `1.07877 mM`.

The chi-square fields use the digitization-resolution values because those are
the only uncertainty values available. They must not be interpreted as
experimental goodness-of-fit statistics.

## Next Action

Acquire an independent or held-out experiment with a stated uncertainty
definition, replicate structure, and an organism/preparation identity if
organism-level interpretation is intended. Do not generalize this same-source
comparison beyond the selected commercial preparation and assay.
