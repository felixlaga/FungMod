# CALIBRATION-EVIDENCE-001 Publication-Oriented Evidence Audit

## Status

Complete for a bounded software evidence audit. No FungMod biological case is
claimed to have publication-grade calibration.

## Implemented contract

`audit_calibration_evidence(...)` consumes an existing
`LeastSquaresCalibrationResult`, a declared study-evidence context, and
provenance-bearing audit criteria. It reports required/pass status and exact
evidence for optimizer success, prospective-plan metadata, training/model
provenance, validation relationship, independent validation, training points
per parameter, residual-scale coverage, validation/training scaled RMSE,
lag-1 residual correlation, Jacobian rank, covariance, confidence intervals,
and bound-limited parameters.

Criteria own every numerical threshold and its source. Missing or internally
inconsistent evidence remains a blocker. Results save as deterministic JSON
and Markdown.

## Claim boundary

`meets_declared_software_criteria` means only that the result passed the exact
criteria supplied by the caller. `publication_claim_authorized` is fixed to
`false`: code cannot establish experimental independence, appropriate study
design, biological applicability, external reproducibility, peer review, or
journal fitness.

The bundled Alvarez-Gonzalez 2022 time-course comparison cannot supply the
missing independent-validation evidence. It transcribes the publication's own
Model 3 parameters and digitizes the same publication's Figure S1A, performs no
FungMod refit, and records digitization resolution rather than experimental
uncertainty.

## Evidence still required for a biological calibration claim

- an immutable prospective analysis plan with sourced thresholds;
- raw training observations with exact assay/culture conditions;
- a genuinely independent validation experiment and immutable source;
- replicate structure and analytical uncertainty or a justified residual
  model;
- explicit model/version identity and parameter applicability;
- complete data licensing and transformation provenance;
- residual, identifiability, robustness, and sensitivity assessment suitable
  for the intended claim; and
- external scientific review.

## Verification

`tests/test_calibration_evidence.py` proves passing artificial software
evidence without publication authorization, blocking reused training data and
missing provenance, blocking rank/covariance/interval failures, deterministic
artifacts, and rejection of an unsourced criteria contract. The artificial
line fixture is not scientific data.
