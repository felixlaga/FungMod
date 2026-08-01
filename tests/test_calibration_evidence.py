from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from fungal_model.calibration import (
    CalibrationAuditCriteria,
    CalibrationEvidenceContext,
    FittableParameter,
    ValidationRelationship,
    audit_calibration_evidence,
    fit_least_squares,
)
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_


def parameter(*, name: str, symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source="Artificial calibration-evidence benchmark value; no scientific claim.",
        confidence_level="testing",
        notes="Defined only for software verification.",
        measurement_method="artificial benchmark definition",
    )


def audit_criteria(*, source: str = "Artificial predeclared software-audit criteria.") -> CalibrationAuditCriteria:
    return CalibrationAuditCriteria(
        source=source,
        minimum_training_points_per_parameter=parameter(
            name="minimum points per parameter",
            symbol="n_train_per_parameter_min",
            value=5.0,
            units="dimensionless",
        ),
        maximum_validation_to_training_rmse_ratio=parameter(
            name="maximum validation to training RMSE ratio",
            symbol="rho_rmse_max",
            value=3.0,
            units="dimensionless",
        ),
        maximum_absolute_lag1_residual_correlation=parameter(
            name="maximum absolute lag-1 residual correlation",
            symbol="rho_lag1_abs_max",
            value=0.95,
            units="dimensionless",
        ),
    )


def evidence_context(
    *,
    relationship: ValidationRelationship = "independent_experiment",
) -> CalibrationEvidenceContext:
    return CalibrationEvidenceContext(
        analysis_plan_id="artificial-plan-001",
        analysis_plan_source="Artificial prospective plan fixture; no real protocol.",
        training_dataset_source="Artificial training observations generated in the test.",
        validation_dataset_source="Separate artificial validation observations generated in the test.",
        validation_relationship=relationship,
        residual_scale_source="Artificial fixed observation scale in the test.",
        model_identifier="artificial-linear-model-1",
        model_source="Artificial line equation defined in the test.",
    )


def fitted_result(*, reuse_training: bool = False):
    x_values = Q_(np.arange(15.0), "second")
    noise = np.array(
        [0.12, -0.04, 0.08, -0.15, 0.03, 0.11, -0.09, 0.05, -0.02, 0.07,
         -0.08, 0.06, 0.02, -0.05, 0.09]
    )
    observations = {"y": Q_(2.0 * x_values.magnitude + noise, "dimensionless")}
    base = ParameterSet(
        [parameter(name="line slope", symbol="k", value=1.5, units="1 / second")]
    )
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(
            name="line slope lower bound",
            symbol="k_lower",
            value=0.0,
            units="1 / second",
        ),
        upper_bound=parameter(
            name="line slope upper bound",
            symbol="k_upper",
            value=4.0,
            units="1 / second",
        ),
    )

    def predict(parameters: ParameterSet):
        return {"y": parameters.require_quantity("k", "1 / second") * x_values}

    return fit_least_squares(
        base_parameters=base,
        fittable_parameters=[fittable],
        predict=predict,
        observations=observations,
        train_indices=tuple(range(10)),
        validation_indices=None if reuse_training else tuple(range(10, 15)),
        residual_scales={"y": Q_(0.2, "dimensionless")},
        calibration_source="Artificial least-squares evidence-audit benchmark.",
    )


def test_evidence_audit_can_pass_declared_software_criteria_without_authorizing_publication(
    tmp_path: Path,
) -> None:
    audit = audit_calibration_evidence(
        result=fitted_result(),
        context=evidence_context(),
        criteria=audit_criteria(),
    )

    assert audit.meets_declared_software_criteria
    assert not audit.publication_claim_authorized
    assert audit.blockers == ()
    assert audit.diagnostics["training_residual_count"] == 10
    assert audit.diagnostics["validation_residual_count"] == 5
    assert "Software checks cannot establish" in audit.publication_claim_limitation

    audit.save(tmp_path)
    assert (tmp_path / "calibration_evidence_audit.json").is_file()
    markdown = (tmp_path / "calibration_evidence_audit.md").read_text(encoding="utf-8")
    assert "Publication claim authorized: `false`" in markdown


def test_evidence_audit_blocks_reused_training_data_and_missing_external_evidence() -> None:
    context = replace(
        evidence_context(relationship="reused_training_data"),
        analysis_plan_source=None,
        validation_dataset_source=None,
        residual_scale_source=None,
    )

    audit = audit_calibration_evidence(
        result=fitted_result(reuse_training=True),
        context=context,
        criteria=audit_criteria(),
    )

    assert not audit.meets_declared_software_criteria
    assert "prospective_analysis_plan" in audit.blockers
    assert "independent_validation" in audit.blockers
    assert "residual_scale_coverage" in audit.blockers
    assert "validation_relationship_consistency" not in audit.blockers


def test_evidence_audit_blocks_rank_and_interval_evidence_when_unavailable() -> None:
    result = replace(
        fitted_result(),
        jacobian_rank=0,
        covariance=None,
        confidence_intervals=None,
    )

    audit = audit_calibration_evidence(
        result=result,
        context=evidence_context(),
        criteria=audit_criteria(),
    )

    assert {"full_rank_jacobian", "covariance_available", "confidence_intervals_available"}.issubset(
        audit.blockers
    )


def test_evidence_audit_rejects_unsourced_threshold_contract() -> None:
    with pytest.raises(ProvenanceError, match="criteria require a source"):
        audit_calibration_evidence(
            result=fitted_result(),
            context=evidence_context(),
            criteria=audit_criteria(source=""),
        )
