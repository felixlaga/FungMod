# Scientific integrity

FungMod is designed to fail honestly.

## Non-negotiable rules

- Physical quantities carry units.
- Scientific parameters require provenance.
- Unknown values remain unknown unless an explicit exploratory range is
  supplied.
- Toy and synthetic fixtures are labelled as software benchmarks.
- Unsupported mechanisms fail rather than silently falling back.
- A successful solver run is not called validation.
- Notebook code uses package APIs; it does not hide model laws.
- Report renderers do not add scientific logic.

## Provenance and maturity

Parameter and mechanism records carry source, measurement, confidence,
maturity, validity, and allowed-use metadata. Scientific-mode execution
requires exact eligible records; exploratory mode may propagate explicit
ranges or distributions.

## Uncertainty language

FungMod output quantiles can represent:

- sampling from explicit user-supplied exploratory priors;
- propagation of registry ranges that are allowed for exploratory use;
- distributions over repeated model samples.

They do not automatically represent:

- empirical confidence intervals;
- Bayesian posterior intervals;
- measurement uncertainty;
- calibration uncertainty;
- model discrepancy.

The output tables preserve source and interpretation fields so downstream
plots can keep those distinctions.

Variance-based global sensitivity indices are conditional on the exact input
distributions supplied by the caller and currently assume independent inputs.
Bootstrap intervals describe resampling variability of the estimator, not
experimental uncertainty or biological confidence.

## Validation language

Use these statements precisely:

- **Technically verified:** automated tests establish the software behavior.
- **Exploratory:** the run uses explicit assumptions, priors, or scoped pilot
  records.
- **Scientifically validated:** empirical evidence supports the specific
  prediction claim.

FungMod does not currently claim publication-grade validation for arbitrary
fungus/substrate/environment predictions.

The calibration evidence audit never authorizes a publication claim. Even when
all declared machine checks pass, experimental independence, dataset adequacy,
model applicability, external reproducibility, and peer review remain outside
the software contract.

## Responsible notebook and report use

Before sharing an output:

1. read the preflight, mechanism, and assumption tables;
2. identify every exploratory parameter;
3. include the provenance and limitation tables;
4. distinguish metadata-only environment differences from active response laws;
5. state whether empirical observations were compared;
6. keep quick-look plots labelled as exploratory when appropriate;
7. archive the manifest and output schema version.
