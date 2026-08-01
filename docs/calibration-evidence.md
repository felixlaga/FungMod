# Calibration evidence

FungMod can fit explicit parameters with bounded least squares and can audit the
result against a study's declared evidence criteria. It cannot decide that a
calibration is publishable.

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

FungMod's bundled Alvarez-Gonzalez 2022 comparison cannot satisfy the default
independent-validation requirement: it compares parameters and digitized
observations from the same source without refitting, and its recorded
digitization resolution is not experimental uncertainty.

Before making a scientific calibration claim, obtain at least an archived
analysis plan, raw training and genuinely independent validation observations,
exact culture and assay conditions, replicate structure, analytical uncertainty
or a justified residual model, licenses, immutable model/data versions, and an
external scientific review appropriate to the intended claim.
