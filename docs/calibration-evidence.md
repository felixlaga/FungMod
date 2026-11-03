# Calibration evidence

FungMod can fit explicit parameters with bounded least squares and can audit the
result against a study's declared evidence criteria. It cannot decide that a
calibration is publishable.

Configured calibration accepts synthetic and provenance-complete literature
datasets, with separate maturity and interpretation labels. It preserves each
point's declared uncertainty. Partial, nonpositive, or nonfinite uncertainty
is rejected; an entirely unknown series remains unweighted and is reported as
such. Low-level residual utilities support scalar scales and observation-shaped
arrays, including matching slices for training and validation.

`evaluate_model_against_dataset(..., fitted_parameter_count=p)` reports residual
degrees of freedom as `n - p`. Supply the number of parameters fitted using the
observations being evaluated, or zero for predictions independent of those
observations. An omitted count stays unknown. Reduced chi-square is omitted
when the count is unknown, uncertainties are incomplete, or degrees of freedom
are nonpositive. Configured calibration supplies the training count and zero
for held-out observations. These arithmetic diagnostics do not establish an
experimental noise model: digitization resolution is not replicate variance.

Approximate normal confidence intervals are not clipped to optimizer bounds.
An interval extending outside those bounds produces an explicit warning that
the local approximation may be unsuitable.

The research runners report descriptive residuals and convergence diagnostics.
They do not declare a mechanism required or falsified from a training-error
threshold. Cross-source summary schema `2.0.0` removes the previous
`deactivation_warranted` and `identified_series` claims; its explicit
`mechanism_conclusion` remains `not_established_by_training_fit`. The separate
hypothesis runner uses schema `2.0.0` and reports
`not_established_by_exploratory_comparison`. Earlier output folders are historical
and should be regenerated before use with the corrected code.

## What the audit checks

`audit_calibration_evidence(...)` evaluates:

- optimizer success;
- a recorded prospective analysis-plan identifier and source;
- training-dataset and model provenance;
- agreement between the declared validation relationship and the fitted split;
- independently sourced validation when the criteria require it;
- a declared minimum number of training residuals per fitted parameter;
- complete residual-scale coverage and a source for those scales;
- a declared maximum validation-to-training scaled-RMSE ratio;
- evaluable lag-1 residual correlations below a declared maximum;
- full Jacobian column rank;
- available linearized covariance and approximate confidence intervals; and
- absence of parameters reported on or extremely near optimizer bounds.

Every numerical threshold is a unit-bearing `Parameter` with provenance. The
audit does not supply a hidden universal definition of an adequate fit.

## Minimal use

```python
from fungal_model.calibration import (
    CalibrationAuditCriteria,
    CalibrationEvidenceContext,
    audit_calibration_evidence,
)
from fungal_model.core.parameters import Parameter


def criterion(name, symbol, value, source):
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units="dimensionless",
        uncertainty=None,
        source=source,
        confidence_level="high",
        notes="Predeclared study-specific calibration-audit criterion.",
        measurement_method="analysis plan",
    )


criteria = CalibrationAuditCriteria(
    source="DOI or archived prospective analysis plan",
    minimum_training_points_per_parameter=criterion(
        "minimum training points per fitted parameter",
        "n_train_per_parameter_min",
        10,
        "DOI or archived prospective analysis plan",
    ),
    maximum_validation_to_training_rmse_ratio=criterion(
        "maximum validation to training scaled RMSE ratio",
        "rho_rmse_max",
        1.5,
        "DOI or archived prospective analysis plan",
    ),
    maximum_absolute_lag1_residual_correlation=criterion(
        "maximum absolute lag-1 residual correlation",
        "rho_lag1_abs_max",
        0.3,
        "DOI or archived prospective analysis plan",
    ),
)

context = CalibrationEvidenceContext(
    analysis_plan_id="archived-plan-id",
    analysis_plan_source="persistent plan URL or DOI",
    training_dataset_source="training dataset DOI",
    validation_dataset_source="independent experiment dataset DOI",
    validation_relationship="independent_experiment",
    residual_scale_source="measurement uncertainty method DOI or protocol",
    model_identifier="model name and immutable version",
    model_source="repository release DOI or archived source",
)

audit = audit_calibration_evidence(
    result=least_squares_result,
    context=context,
    criteria=criteria,
)
audit.save("outputs/calibration-audit")
```

The example values above are placeholders that must be replaced by criteria
from the actual analysis plan. They are not FungMod defaults or scientific
recommendations.

## Meaning of a pass

A pass means only that the supplied fit satisfies the supplied machine-readable
software criteria. `publication_claim_authorized` is always `false`. Software
cannot establish experimental independence, adequacy of the biological model,
reproducibility by another group, peer review, or journal fitness.

FungMod's bundled Alvarez-Gonzalez 2022 comparisons cannot satisfy the default
independent-validation requirement: both the published-parameter comparison and
the stage-2 fitted/held-out study use observations from the same source, and
their recorded digitization resolution is not experimental uncertainty.

Before making a scientific calibration claim, obtain at least an archived
analysis plan, raw training and genuinely independent validation observations,
exact culture and assay conditions, replicate structure, analytical uncertainty
or a justified residual model, licenses, immutable model/data versions, and an
external scientific review appropriate to the intended claim.

## Finite-difference step

`fit_least_squares` optimises in the linear space of the fitted parameters'
declared units and estimates the Jacobian by forward differences. The relative
step of those differences is an explicit argument, `relative_difference_step`:
scipy perturbs each parameter by the step times its current magnitude. When the
caller omits it, the named constant
`fungal_model.calibration.DEFAULT_RELATIVE_DIFFERENCE_STEP` (1e-3) applies. The
constant exists because scipy's default of about 1.5e-8 differentiates the step
noise of adaptive ODE integrators: in the Gelain 2020 model-criticism study
(frozen-plan amendment 3, ledger entry CRIT-003) the residual-derivative norms of
weakly entering constants were 15 times their converged values at scipy's step,
the trust region collapsed, and every start stopped 1.3 percent above the
minimum that COPASI found; a relative step of 1e-3 made the optimum stationary.
A smooth analytic predictor tolerates a smaller step and a caller may declare
one; a parameter that starts at exactly zero has no relative step there, scipy
substitutes its machine-precision default, and the result warns about it.

Every `LeastSquaresCalibrationResult` records what was used in
`optimizer_metadata`: `relative_difference_step`,
`relative_difference_step_origin` (`caller` or
`default DEFAULT_RELATIVE_DIFFERENCE_STEP`), `finite_difference_parameter_space`,
`max_nfev` (the budget actually passed to scipy, 100 evaluations per fitted
parameter when the caller passed none) and `max_nfev_origin`. Failed fits record
the same settings next to `exception_type`. `calibrate_configured_model`
accepts the same `relative_difference_step`, so `optimizer_metadata.json` and
`calibration_record.json` of a saved bundle carry it, and hands it to the
profile-likelihood refits. Fits recorded before this argument existed were
produced with scipy's default step; none is stored in this repository.

## Profile likelihood

`profile_likelihood(...)` supplements the local covariance approximation by
fixing each selected parameter on an explicit unit-bearing grid and reoptimizing
the remaining parameters. It records chi-square differences, nuisance estimates,
optimizer failures, and cases where a profile improves the original optimum.
This follows the profile construction in [Raue et al. (2009)](https://doi.org/10.1093/bioinformatics/btp358).

The current implementation assumes independent Gaussian observations with fixed,
explicit standard deviations. All observations need positive scales. Supply an
analysis/noise-model source; digitization scales do not establish this noise
model. The inputs must reproduce the original training objective. Failed points
remain explicit with null costs. Finite grids and local optima do not establish
global identifiability, and no confidence endpoints are inferred from a grid edge.

The nuisance refits use the finite-difference step recorded in the reference
fit's `optimizer_metadata` unless `relative_difference_step` is passed; the
report's `optimizer_settings` records the step, its origin and `max_nfev`.

Configured calibration accepts `profile_grids` and `profile_source` and saves
the report inside `optimizer_metadata.json`. It profiles training observations
only. For a fully artificial software example:

```python
from fungal_model.calibration import calibrate_configured_model
from fungal_model.core.units import Q_
from fungal_model.resources import example_data_path

result = calibrate_configured_model(
    model_config=example_data_path("model_configs/synthetic_first_order_calibration.yml"),
    dataset=example_data_path("experiments/synthetic/first_order_ab/synthetic_first_order_ab.yml"),
    parameter_symbols=["k_ab"],
    observable_mapping={"product_mass": "released_product_amount"},
    initial_guess={"k_ab": 0.03},
    bounds={"k_ab": (0.0, 1.0)},
    split={"method": "by_time", "train_fraction": 0.7, "validation_fraction": 0.3},
    profile_grids={"k_ab": Q_([0.05, 0.1, 0.15], "1/second")},
    profile_source="Artificial fixture with declared independent Gaussian test scales; no biological claim.",
)
print(result.optimizer_metadata["profile_likelihood"])
```

For new experimental evidence, use the separate
[frozen-prediction validation workflow](independent-validation.md).

## Posterior sampling

Profile likelihood answers whether a least-squares optimum is flat along one
parameter. [Bayesian calibration](bayesian-calibration.md) answers the wider
question on the compiled core: given declared priors and an explicit error
model, which parameters does the data set identify, which are bounded on one
side only, and which remain prior-dominated ranges. Both are conditional on
the error model, and neither is validation.
