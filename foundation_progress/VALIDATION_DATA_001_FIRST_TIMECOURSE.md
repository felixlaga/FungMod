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

Current next PR: **PR-53: product-map registry destination and ownership contract**.

This phase has a machine-checkable ingestion gate, but it does not yet have a
source-backed real time-course dataset in the repository. Validation remains
important, but it remains deferred until source-backed numeric observations
satisfy the evidence requirements below and the simulator can produce mature
enough degradation outputs for comparison. The PR-31 work is complete after
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
PR-52 follow-up is complete in the current checkout for non-parameter
authoring across the five index-backed record
families with closed schemas, owned destinations, loader fidelity, conservative
policies, and no authoring/planning mutation. The selected PR-53 follow-up
defines product-map production ownership, a loader schema, and an
index-declared destination. It does not ingest
validation data, authorize simulation automatically, or claim validation.
The completed PR-47 work is bounded transactional
administrative registry apply with exact digest confirmation, intentional plan
schema `2.0.0`, durable curation audit provenance, strict next-patch versioning,
full-root staging/drift checks, locking, no overwrite, and verified rollback.
It does not ingest validation data, change scientific fields, authorize
simulation automatically, or claim validation. CURATION-001 remains partial
for product-map destination ownership and curator authentication/signatures.
A future validation ingestion PR must not ingest, digitize, or
fabricate data unless those evidence requirements are met.
This gate does not complete VALIDATION-DATA-001.

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

After PR-52, take the bounded PR-53 product-map registry destination and
ownership contract. Define one production schema, loader, owner, and
index-declared destination before enabling curator-authored promotion; do not
infer stoichiometry or authorize simulation automatically. Continue building PRODUCT-001,
THERMO-003, and generic BIO-003 simulator capability.
Later, find or obtain source-backed numeric time-course
observations that satisfy the required evidence fields above. Then open a
separate ingestion PR for VALIDATION-DATA-001 with the dataset, comparison
workflow, limitations, and tests.
