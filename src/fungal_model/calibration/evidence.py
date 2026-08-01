"""Evidence audit for publication-oriented calibration workflows.

This module audits a completed least-squares result against explicit,
provenance-bearing criteria. It cannot authorize a publication claim: dataset
independence, experimental adequacy, model applicability, and peer review are
external scientific judgements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence, cast

import numpy as np

from fungal_model.calibration.fitting import LeastSquaresCalibrationResult
from fungal_model.calibration.residuals import CalibrationResiduals
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible

ValidationRelationship = Literal[
    "independent_experiment",
    "held_out_same_experiment",
    "reused_training_data",
]


def _dimensionless_value(parameter: Parameter, *, name: str) -> float:
    parameter.validate_provenance()
    parameter.validate_value()
    return float(
        assert_compatible(
            cast(Quantity, parameter.quantity),
            "dimensionless",
            name=name,
        ).magnitude
    )


@dataclass(frozen=True)
class CalibrationEvidenceContext:
    """Study evidence declared by the calibration author."""

    analysis_plan_id: str | None
    analysis_plan_source: str | None
    training_dataset_source: str | None
    validation_dataset_source: str | None
    validation_relationship: ValidationRelationship
    residual_scale_source: str | None
    model_identifier: str | None
    model_source: str | None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_plan_id": self.analysis_plan_id,
            "analysis_plan_source": self.analysis_plan_source,
            "training_dataset_source": self.training_dataset_source,
            "validation_dataset_source": self.validation_dataset_source,
            "validation_relationship": self.validation_relationship,
            "residual_scale_source": self.residual_scale_source,
            "model_identifier": self.model_identifier,
            "model_source": self.model_source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CalibrationAuditCriteria:
    """Explicit thresholds and evidence requirements for one audit."""

    source: str
    minimum_training_points_per_parameter: Parameter
    maximum_validation_to_training_rmse_ratio: Parameter
    maximum_absolute_lag1_residual_correlation: Parameter
    require_independent_validation: bool = True
    require_residual_scales: bool = True
    require_full_rank: bool = True
    require_covariance: bool = True
    require_confidence_intervals: bool = True
    require_no_bound_limited_parameters: bool = True

    def validated_values(self) -> tuple[float, float, float]:
        if not has_text(self.source):
            raise ProvenanceError("Calibration audit criteria require a source.")
        minimum_points = _dimensionless_value(
            self.minimum_training_points_per_parameter,
            name="minimum training points per parameter",
        )
        maximum_ratio = _dimensionless_value(
            self.maximum_validation_to_training_rmse_ratio,
            name="maximum validation-to-training RMSE ratio",
        )
        maximum_correlation = _dimensionless_value(
            self.maximum_absolute_lag1_residual_correlation,
            name="maximum absolute lag-1 residual correlation",
        )
        if minimum_points <= 0.0:
            raise ValueError("minimum_training_points_per_parameter must be positive.")
        if maximum_ratio <= 0.0:
            raise ValueError("maximum_validation_to_training_rmse_ratio must be positive.")
        if not 0.0 <= maximum_correlation <= 1.0:
            raise ValueError(
                "maximum_absolute_lag1_residual_correlation must lie between 0 and 1."
            )
        return minimum_points, maximum_ratio, maximum_correlation

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "minimum_training_points_per_parameter": (
                self.minimum_training_points_per_parameter.to_dict()
            ),
            "maximum_validation_to_training_rmse_ratio": (
                self.maximum_validation_to_training_rmse_ratio.to_dict()
            ),
            "maximum_absolute_lag1_residual_correlation": (
                self.maximum_absolute_lag1_residual_correlation.to_dict()
            ),
            "require_independent_validation": self.require_independent_validation,
            "require_residual_scales": self.require_residual_scales,
            "require_full_rank": self.require_full_rank,
            "require_covariance": self.require_covariance,
            "require_confidence_intervals": self.require_confidence_intervals,
            "require_no_bound_limited_parameters": self.require_no_bound_limited_parameters,
        }


@dataclass(frozen=True)
class CalibrationEvidenceCheck:
    """One machine-readable audit result."""

    check_id: str
    passed: bool
    required: bool
    summary: str
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "required": self.required,
            "summary": self.summary,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class CalibrationEvidenceAudit:
    """Complete evidence report for a least-squares result."""

    context: CalibrationEvidenceContext
    criteria: CalibrationAuditCriteria
    checks: tuple[CalibrationEvidenceCheck, ...]
    diagnostics: Mapping[str, Any]
    meets_declared_software_criteria: bool
    publication_claim_authorized: bool
    publication_claim_limitation: str

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(
            check.check_id
            for check in self.checks
            if check.required and not check.passed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "criteria": self.criteria.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "diagnostics": dict(self.diagnostics),
            "blockers": list(self.blockers),
            "meets_declared_software_criteria": self.meets_declared_software_criteria,
            "publication_claim_authorized": self.publication_claim_authorized,
            "publication_claim_limitation": self.publication_claim_limitation,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Calibration evidence audit",
            "",
            f"- Meets declared software criteria: `{str(self.meets_declared_software_criteria).lower()}`",
            "- Publication claim authorized: `false`",
            f"- Publication limitation: {self.publication_claim_limitation}",
            "",
            "## Checks",
            "",
            "| Check | Required | Result | Summary |",
            "| --- | --- | --- | --- |",
        ]
        for check in self.checks:
            lines.append(
                f"| `{check.check_id}` | `{str(check.required).lower()}` | "
                f"`{'pass' if check.passed else 'fail'}` | {check.summary} |"
            )
        if self.blockers:
            lines.extend(("", "## Blocking checks", ""))
            lines.extend(f"- `{blocker}`" for blocker in self.blockers)
        lines.append("")
        return "\n".join(lines)

    def save(self, output_dir: str | Path) -> None:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "calibration_evidence_audit.json").write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (path / "calibration_evidence_audit.md").write_text(
            self.to_markdown(),
            encoding="utf-8",
        )


def _residual_count(residuals: CalibrationResiduals | None) -> int:
    if residuals is None:
        return 0
    return sum(np.asarray(value.magnitude).size for value in residuals.residuals.values())


def _scaled_rmse(residuals: CalibrationResiduals | None) -> float | None:
    if residuals is None:
        return None
    vector = residuals.flattened_scaled()
    if vector.size == 0 or not np.all(np.isfinite(vector)):
        return None
    return float(np.sqrt(np.mean(vector**2)))


def _residual_scale_coverage(residuals: CalibrationResiduals | None) -> tuple[bool, list[str]]:
    if residuals is None:
        return False, []
    species = sorted(residuals.residuals)
    missing = [name for name in species if name not in residuals.residual_scales]
    return not missing and bool(species), missing


def _lag1_correlations(
    residual_sets: Sequence[CalibrationResiduals | None],
) -> tuple[dict[str, float], list[str]]:
    correlations: dict[str, float] = {}
    unavailable: list[str] = []
    for residual_set in residual_sets:
        if residual_set is None:
            continue
        for species, quantity in residual_set.residuals.items():
            key = f"{residual_set.label}:{species}"
            values = np.asarray(quantity.magnitude, dtype=float).reshape(-1)
            if values.size < 3 or np.std(values[:-1]) == 0.0 or np.std(values[1:]) == 0.0:
                unavailable.append(key)
                continue
            correlation = float(np.corrcoef(values[:-1], values[1:])[0, 1])
            if not np.isfinite(correlation):
                unavailable.append(key)
                continue
            correlations[key] = correlation
    return correlations, unavailable


def _check(
    check_id: str,
    passed: bool,
    *,
    required: bool = True,
    summary: str,
    **evidence: Any,
) -> CalibrationEvidenceCheck:
    return CalibrationEvidenceCheck(
        check_id=check_id,
        passed=bool(passed),
        required=required,
        summary=summary,
        evidence=evidence,
    )


def audit_calibration_evidence(
    *,
    result: LeastSquaresCalibrationResult,
    context: CalibrationEvidenceContext,
    criteria: CalibrationAuditCriteria,
) -> CalibrationEvidenceAudit:
    """Audit one fit without authorizing a publication claim."""

    minimum_points, maximum_ratio, maximum_correlation = criteria.validated_values()
    checks: list[CalibrationEvidenceCheck] = []
    checks.append(
        _check(
            "optimizer_success",
            result.success,
            summary="Least-squares optimizer reported success." if result.success else result.message,
            optimizer_message=result.message,
        )
    )

    plan_complete = has_text(context.analysis_plan_id) and has_text(context.analysis_plan_source)
    checks.append(
        _check(
            "prospective_analysis_plan",
            plan_complete,
            summary=(
                "Analysis-plan identifier and source are recorded."
                if plan_complete
                else "Analysis-plan identifier or source is missing."
            ),
            analysis_plan_id=context.analysis_plan_id,
            analysis_plan_source=context.analysis_plan_source,
        )
    )
    training_source_present = has_text(context.training_dataset_source)
    checks.append(
        _check(
            "training_dataset_provenance",
            training_source_present,
            summary=(
                "Training-dataset provenance is recorded."
                if training_source_present
                else "Training-dataset provenance is missing."
            ),
            training_dataset_source=context.training_dataset_source,
        )
    )
    model_identity_present = has_text(context.model_identifier) and has_text(context.model_source)
    checks.append(
        _check(
            "model_identity_and_source",
            model_identity_present,
            summary=(
                "Model identifier and source are recorded."
                if model_identity_present
                else "Model identifier or source is missing."
            ),
            model_identifier=context.model_identifier,
            model_source=context.model_source,
        )
    )

    expected_reuse = context.validation_relationship == "reused_training_data"
    relationship_consistent = result.validation_uses_training_data == expected_reuse
    checks.append(
        _check(
            "validation_relationship_consistency",
            relationship_consistent,
            summary=(
                "Declared validation relationship matches fitted-result indices."
                if relationship_consistent
                else "Declared validation relationship conflicts with fitted-result indices."
            ),
            declared_relationship=context.validation_relationship,
            result_validation_uses_training_data=result.validation_uses_training_data,
        )
    )
    independent = (
        context.validation_relationship == "independent_experiment"
        and not result.validation_uses_training_data
        and has_text(context.validation_dataset_source)
    )
    checks.append(
        _check(
            "independent_validation",
            independent,
            required=criteria.require_independent_validation,
            summary=(
                "An independently sourced validation experiment is declared and not reused for training."
                if independent
                else "Independent validation evidence is absent or reuses training data."
            ),
            validation_dataset_source=context.validation_dataset_source,
            declared_relationship=context.validation_relationship,
        )
    )

    n_parameters = len(result.fittable_parameters)
    n_training = _residual_count(result.training_residuals)
    points_per_parameter = float(n_training / n_parameters) if n_parameters else 0.0
    point_adequacy = n_parameters > 0 and points_per_parameter >= minimum_points
    checks.append(
        _check(
            "training_points_per_parameter",
            point_adequacy,
            summary=(
                f"Observed {points_per_parameter:.3g} training residuals per fitted parameter; "
                f"declared minimum is {minimum_points:.3g}."
            ),
            n_training_residuals=n_training,
            n_fitted_parameters=n_parameters,
            observed_points_per_parameter=points_per_parameter,
            required_minimum=minimum_points,
        )
    )

    training_scales, training_missing = _residual_scale_coverage(result.training_residuals)
    validation_scales, validation_missing = _residual_scale_coverage(result.validation_residuals)
    scale_source = has_text(context.residual_scale_source)
    scale_coverage = training_scales and validation_scales and scale_source
    checks.append(
        _check(
            "residual_scale_coverage",
            scale_coverage,
            required=criteria.require_residual_scales,
            summary=(
                "Every fitted species has an explicit residual scale and its source is recorded."
                if scale_coverage
                else "Residual scales or their source are incomplete."
            ),
            training_missing_species=training_missing,
            validation_missing_species=validation_missing,
            residual_scale_source=context.residual_scale_source,
        )
    )

    training_rmse = _scaled_rmse(result.training_residuals)
    validation_rmse = _scaled_rmse(result.validation_residuals)
    rmse_ratio = (
        None
        if training_rmse is None or validation_rmse is None or training_rmse <= 0.0
        else validation_rmse / training_rmse
    )
    ratio_passed = rmse_ratio is not None and np.isfinite(rmse_ratio) and rmse_ratio <= maximum_ratio
    checks.append(
        _check(
            "validation_to_training_scaled_rmse_ratio",
            ratio_passed,
            summary=(
                f"Validation/training scaled RMSE ratio is {rmse_ratio:.3g}; "
                f"declared maximum is {maximum_ratio:.3g}."
                if rmse_ratio is not None
                else "Validation/training scaled RMSE ratio is undefined."
            ),
            training_scaled_rmse=training_rmse,
            validation_scaled_rmse=validation_rmse,
            ratio=rmse_ratio,
            required_maximum=maximum_ratio,
        )
    )

    correlations, unavailable_correlations = _lag1_correlations(
        (result.training_residuals, result.validation_residuals)
    )
    correlation_passed = (
        bool(correlations)
        and not unavailable_correlations
        and all(abs(value) <= maximum_correlation for value in correlations.values())
    )
    checks.append(
        _check(
            "lag1_residual_correlation",
            correlation_passed,
            summary=(
                "All residual series have evaluable lag-1 correlations within the declared limit."
                if correlation_passed
                else "A residual series is unevaluable or exceeds the declared lag-1 correlation limit."
            ),
            correlations=correlations,
            unavailable=unavailable_correlations,
            required_maximum_absolute=maximum_correlation,
        )
    )

    full_rank = result.jacobian_rank == n_parameters and n_parameters > 0
    checks.append(
        _check(
            "full_rank_jacobian",
            full_rank,
            required=criteria.require_full_rank,
            summary=(
                "Fitted Jacobian has full column rank."
                if full_rank
                else "Fitted Jacobian is missing or rank deficient."
            ),
            jacobian_rank=result.jacobian_rank,
            n_fitted_parameters=n_parameters,
        )
    )
    checks.append(
        _check(
            "covariance_available",
            result.covariance is not None,
            required=criteria.require_covariance,
            summary=(
                "Linearized covariance is available."
                if result.covariance is not None
                else "Linearized covariance is unavailable."
            ),
        )
    )
    checks.append(
        _check(
            "confidence_intervals_available",
            result.confidence_intervals is not None,
            required=criteria.require_confidence_intervals,
            summary=(
                "Approximate fitted-parameter confidence intervals are available."
                if result.confidence_intervals is not None
                else "Approximate fitted-parameter confidence intervals are unavailable."
            ),
        )
    )
    bound_warnings = [warning for warning in result.warnings if "near a bound" in warning]
    checks.append(
        _check(
            "no_bound_limited_parameters",
            not bound_warnings,
            required=criteria.require_no_bound_limited_parameters,
            summary=(
                "No fitted parameter is reported on or extremely near a bound."
                if not bound_warnings
                else "At least one fitted parameter is reported on or extremely near a bound."
            ),
            bound_warnings=bound_warnings,
        )
    )

    required_checks_pass = all(check.passed for check in checks if check.required)
    diagnostics = {
        "training_residual_count": n_training,
        "validation_residual_count": _residual_count(result.validation_residuals),
        "training_scaled_rmse": training_rmse,
        "validation_scaled_rmse": validation_rmse,
        "validation_to_training_scaled_rmse_ratio": rmse_ratio,
        "lag1_residual_correlations": correlations,
        "unevaluable_lag1_residual_series": unavailable_correlations,
        "optimizer_warnings": list(result.warnings),
    }
    return CalibrationEvidenceAudit(
        context=context,
        criteria=criteria,
        checks=tuple(checks),
        diagnostics=diagnostics,
        meets_declared_software_criteria=required_checks_pass,
        publication_claim_authorized=False,
        publication_claim_limitation=(
            "Software checks cannot establish experimental independence, dataset adequacy, "
            "model applicability, reproducibility by another group, peer review, or publication fitness."
        ),
    )


__all__ = [
    "CalibrationAuditCriteria",
    "CalibrationEvidenceAudit",
    "CalibrationEvidenceCheck",
    "CalibrationEvidenceContext",
    "ValidationRelationship",
    "audit_calibration_evidence",
]
