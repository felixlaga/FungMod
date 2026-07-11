"""Least-squares calibration utilities.

The calibration layer is deliberately generic: callers provide a prediction
function that maps a `ParameterSet` to unit-bearing model outputs. This module
handles provenance-checked fittable parameters, bounds, train/validation
residuals, and diagnostics. It does not tune hidden constants or discard failed
fits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

import numpy as np
from scipy.optimize import least_squares

from fungal_model.calibration.residuals import CalibrationResiduals, residuals_between
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible

PredictionFunction = Callable[[ParameterSet], Mapping[str, Quantity]]

APPROXIMATE_NORMAL_95_Z = Parameter(
    name="normal approximation two-sided 95 percent z score",
    symbol="z_0.975",
    value=1.959963984540054,
    units="dimensionless",
    uncertainty=None,
    source="Standard normal distribution quantile used for approximate confidence intervals.",
    confidence_level="high",
    notes=(
        "Used only when a least-squares fit has sufficient residual degrees of "
        "freedom and full-rank Jacobian diagnostics."
    ),
    measurement_method="statistical definition",
)

BOUND_PROXIMITY_RELATIVE_TOLERANCE = Parameter(
    name="least-squares bound proximity relative tolerance",
    symbol="epsilon_fit_bound",
    value=1.0e-10,
    units="dimensionless",
    uncertainty=None,
    source="Numerical diagnostic convention for identifying fitted parameters near optimizer bounds.",
    confidence_level="testing",
    notes="Used only to report possible bound-limited calibration diagnostics.",
    measurement_method="software configuration",
)


def _parameter_with_value(
    parameter: Parameter,
    value: float,
    *,
    source: str,
    notes: str,
    uncertainty: float | None = None,
) -> Parameter:
    return replace(
        parameter,
        value=float(value),
        uncertainty=uncertainty,
        source=source,
        confidence_level="low",
        notes=notes,
        measurement_method="least-squares calibration",
    )


def _replace_parameters(base: ParameterSet, replacements: Mapping[str, Parameter]) -> ParameterSet:
    return ParameterSet(
        [replacements.get(parameter.symbol, parameter) for parameter in base]
    )


@dataclass(frozen=True)
class FittableParameter:
    """A model parameter that may be estimated by least squares."""

    symbol: str
    lower_bound: Parameter
    upper_bound: Parameter
    notes: str = ""

    def validate(self, base_parameters: ParameterSet) -> None:
        base = base_parameters.get(self.symbol)
        base.validate_provenance()
        base.validate_value()
        self.lower_bound.validate_provenance()
        self.lower_bound.validate_value()
        self.upper_bound.validate_provenance()
        self.upper_bound.validate_value()
        lower = float(
            assert_compatible(
                self.lower_bound.quantity,
                base.units,
                name=f"{self.symbol} lower bound",
            ).magnitude
        )
        upper = float(
            assert_compatible(
                self.upper_bound.quantity,
                base.units,
                name=f"{self.symbol} upper bound",
            ).magnitude
        )
        initial = float(cast(Quantity, base.quantity).to(base.units).magnitude)
        if not lower < upper:
            raise ValueError(f"Bounds for {self.symbol} must satisfy lower < upper.")
        if not lower <= initial <= upper:
            raise ValueError(f"Initial value for {self.symbol} is outside its bounds.")

    def initial_numeric(self, base_parameters: ParameterSet) -> float:
        base = base_parameters.get(self.symbol)
        return float(cast(Quantity, base.quantity).to(base.units).magnitude)

    def bounds_numeric(self, base_parameters: ParameterSet) -> tuple[float, float]:
        base = base_parameters.get(self.symbol)
        return (
            float(cast(Quantity, self.lower_bound.quantity).to(base.units).magnitude),
            float(cast(Quantity, self.upper_bound.quantity).to(base.units).magnitude),
        )

    def to_dict(self, base_parameters: ParameterSet) -> dict[str, Any]:
        lower, upper = self.bounds_numeric(base_parameters)
        base = base_parameters.get(self.symbol)
        return {
            "symbol": self.symbol,
            "initial": base.to_dict(),
            "lower_bound": self.lower_bound.to_dict(),
            "upper_bound": self.upper_bound.to_dict(),
            "lower_numeric_in_parameter_units": lower,
            "upper_numeric_in_parameter_units": upper,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LeastSquaresCalibrationResult:
    """Complete report for a least-squares calibration attempt."""

    success: bool
    message: str
    initial_parameters: ParameterSet
    fitted_parameters: ParameterSet
    fittable_parameters: tuple[FittableParameter, ...]
    training_residuals: CalibrationResiduals | None
    validation_residuals: CalibrationResiduals | None
    validation_uses_training_data: bool
    cost: float | None
    jacobian_rank: int | None
    covariance: Mapping[str, Mapping[str, float]] | None
    confidence_intervals: Mapping[str, Mapping[str, float | str]] | None
    warnings: tuple[str, ...]
    optimizer_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "initial_parameters": self.initial_parameters.to_dict(),
            "fitted_parameters": self.fitted_parameters.to_dict(),
            "fittable_parameters": [
                parameter.to_dict(self.initial_parameters)
                for parameter in self.fittable_parameters
            ],
            "training_residuals": (
                None if self.training_residuals is None else self.training_residuals.to_dict()
            ),
            "validation_residuals": (
                None if self.validation_residuals is None else self.validation_residuals.to_dict()
            ),
            "validation_uses_training_data": self.validation_uses_training_data,
            "cost": self.cost,
            "jacobian_rank": self.jacobian_rank,
            "covariance": self.covariance,
            "confidence_intervals": self.confidence_intervals,
            "warnings": list(self.warnings),
            "optimizer_metadata": dict(self.optimizer_metadata),
        }

    def save(self, output_dir: str | Path, *, independent: Quantity | None = None) -> None:
        """Save fit summary, residuals, and residual plots."""

        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "fit_result.json").write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if self.training_residuals is not None:
            self.training_residuals.to_json(path / "training_residuals.json")
            self.training_residuals.plot(path / "training_residuals.png", independent=independent)
        if self.validation_residuals is not None:
            self.validation_residuals.to_json(path / "validation_residuals.json")
            self.validation_residuals.plot(path / "validation_residuals.png", independent=independent)


def _build_replacements(
    base_parameters: ParameterSet,
    fittable_parameters: Sequence[FittableParameter],
    vector: Sequence[float],
    *,
    calibration_source: str,
) -> dict[str, Parameter]:
    replacements: dict[str, Parameter] = {}
    for spec, value in zip(fittable_parameters, vector, strict=True):
        base = base_parameters.get(spec.symbol)
        replacements[spec.symbol] = _parameter_with_value(
            base,
            float(value),
            source=(
                f"Least-squares calibration result. Calibration source: "
                f"{calibration_source}. Initial parameter source: {base.source}"
            ),
            notes=(
                f"Fitted by least squares within explicit bounds. {spec.notes} "
                f"Original notes: {base.notes}"
            ).strip(),
        )
    return replacements


def _covariance_and_intervals(
    *,
    jacobian: np.ndarray,
    residual_vector: np.ndarray,
    fitted_vector: np.ndarray,
    fittable_parameters: Sequence[FittableParameter],
    fitted_parameters: ParameterSet,
) -> tuple[dict[str, dict[str, float]] | None, dict[str, dict[str, float | str]] | None, list[str]]:
    warnings: list[str] = []
    n_residuals, n_parameters = jacobian.shape
    rank = int(np.linalg.matrix_rank(jacobian))
    if n_residuals <= n_parameters:
        warnings.append(
            "Insufficient residual degrees of freedom for covariance and confidence intervals."
        )
        return None, None, warnings
    if rank < n_parameters:
        warnings.append(
            "Jacobian is rank deficient; fitted parameters may be non-identifiable."
        )
        return None, None, warnings
    jt_j = jacobian.T @ jacobian
    try:
        inverse = np.linalg.inv(jt_j)
    except np.linalg.LinAlgError:
        warnings.append("Could not invert J^T J for covariance estimation.")
        return None, None, warnings
    residual_variance = float(np.sum(residual_vector**2) / (n_residuals - n_parameters))
    covariance_matrix = inverse * residual_variance
    symbols = [parameter.symbol for parameter in fittable_parameters]
    covariance = {
        row_symbol: {
            col_symbol: float(covariance_matrix[row, col])
            for col, col_symbol in enumerate(symbols)
        }
        for row, row_symbol in enumerate(symbols)
    }
    z_value = float(cast(Quantity, APPROXIMATE_NORMAL_95_Z.quantity).magnitude)
    intervals: dict[str, dict[str, float | str]] = {}
    for index, symbol in enumerate(symbols):
        parameter = fitted_parameters.get(symbol)
        standard_error = float(np.sqrt(max(0.0, covariance_matrix[index, index])))
        value = float(fitted_vector[index])
        intervals[symbol] = {
            "estimate": value,
            "lower_95_approx": value - z_value * standard_error,
            "upper_95_approx": value + z_value * standard_error,
            "standard_error": standard_error,
            "units": parameter.units,
            "method": "linearized least-squares normal approximation",
        }
    return covariance, intervals, warnings


def fit_least_squares(
    *,
    base_parameters: ParameterSet,
    fittable_parameters: Sequence[FittableParameter],
    predict: PredictionFunction,
    observations: Mapping[str, Quantity],
    train_indices: Sequence[int] | None = None,
    validation_indices: Sequence[int] | None = None,
    residual_scales: Mapping[str, Quantity] | None = None,
    calibration_source: str,
    max_nfev: int | None = None,
) -> LeastSquaresCalibrationResult:
    """Fit selected parameters by bounded least squares.

    Failed optimizer runs are returned as `success=False` reports rather than
    being hidden or converted into apparently valid fits.
    """

    if not has_text(calibration_source):
        raise ProvenanceError("calibration_source is required.")
    if not fittable_parameters:
        raise ValueError("At least one fittable parameter is required.")
    base_parameters.validate(require_values=True)
    fittables = tuple(fittable_parameters)
    for parameter in fittables:
        parameter.validate(base_parameters)

    x0 = np.asarray(
        [parameter.initial_numeric(base_parameters) for parameter in fittables],
        dtype=float,
    )
    lower_bounds, upper_bounds = zip(
        *(parameter.bounds_numeric(base_parameters) for parameter in fittables),
        strict=True,
    )
    bounds = (np.asarray(lower_bounds, dtype=float), np.asarray(upper_bounds, dtype=float))
    warnings: list[str] = []
    validation_uses_training_data = validation_indices is None
    if validation_uses_training_data:
        warnings.append(
            "No validation_indices were supplied; validation residuals reuse training data."
        )
    if residual_scales is None:
        warnings.append(
            "No residual_scales supplied; residuals are optimized in raw observation units."
        )

    def parameter_set_from_vector(vector: Sequence[float]) -> ParameterSet:
        replacements = _build_replacements(
            base_parameters,
            fittables,
            vector,
            calibration_source=calibration_source,
        )
        return _replace_parameters(base_parameters, replacements)

    def objective(vector: np.ndarray) -> np.ndarray:
        parameter_set = parameter_set_from_vector(vector.tolist())
        predictions = predict(parameter_set)
        residuals = residuals_between(
            predictions,
            observations,
            indices=train_indices,
            residual_scales=residual_scales,
            label="training",
        )
        return residuals.flattened_scaled()

    try:
        optimizer_result = least_squares(
            objective,
            x0,
            bounds=bounds,
            max_nfev=max_nfev,
        )
    except Exception as exc:
        return LeastSquaresCalibrationResult(
            success=False,
            message=f"Least-squares calibration failed before producing a fit: {exc}",
            initial_parameters=base_parameters,
            fitted_parameters=base_parameters,
            fittable_parameters=fittables,
            training_residuals=None,
            validation_residuals=None,
            validation_uses_training_data=validation_uses_training_data,
            cost=None,
            jacobian_rank=None,
            covariance=None,
            confidence_intervals=None,
            warnings=tuple(warnings),
            optimizer_metadata={"exception_type": type(exc).__name__},
        )

    fitted_parameters = parameter_set_from_vector(optimizer_result.x)
    predictions = predict(fitted_parameters)
    training_residuals = residuals_between(
        predictions,
        observations,
        indices=train_indices,
        residual_scales=residual_scales,
        label="training",
    )
    validation_residuals = residuals_between(
        predictions,
        observations,
        indices=train_indices if validation_uses_training_data else validation_indices,
        residual_scales=residual_scales,
        label="validation",
        notes=(
            "Validation reused training data."
            if validation_uses_training_data
            else "Validation used held-out indices supplied by caller."
        ),
    )
    residual_vector = training_residuals.flattened_scaled()
    rank = int(np.linalg.matrix_rank(optimizer_result.jac))
    covariance, intervals, diagnostic_warnings = _covariance_and_intervals(
        jacobian=optimizer_result.jac,
        residual_vector=residual_vector,
        fitted_vector=optimizer_result.x,
        fittable_parameters=fittables,
        fitted_parameters=fitted_parameters,
    )
    warnings.extend(diagnostic_warnings)
    for spec, value in zip(fittables, optimizer_result.x, strict=True):
        lower, upper = spec.bounds_numeric(base_parameters)
        tolerance = max(1.0, abs(value)) * float(
            cast(Quantity, BOUND_PROXIMITY_RELATIVE_TOLERANCE.quantity).magnitude
        )
        if abs(value - lower) <= tolerance or abs(value - upper) <= tolerance:
            warnings.append(
                f"Fitted parameter {spec.symbol} lies on or extremely near a bound."
            )

    return LeastSquaresCalibrationResult(
        success=bool(optimizer_result.success),
        message=str(optimizer_result.message),
        initial_parameters=base_parameters,
        fitted_parameters=fitted_parameters,
        fittable_parameters=fittables,
        training_residuals=training_residuals,
        validation_residuals=validation_residuals,
        validation_uses_training_data=validation_uses_training_data,
        cost=float(optimizer_result.cost),
        jacobian_rank=rank,
        covariance=covariance,
        confidence_intervals=intervals,
        warnings=tuple(warnings),
        optimizer_metadata={
            "nfev": int(optimizer_result.nfev),
            "njev": None if optimizer_result.njev is None else int(optimizer_result.njev),
            "status": int(optimizer_result.status),
            "optimality": float(optimizer_result.optimality),
            "active_mask": np.asarray(optimizer_result.active_mask, dtype=int).tolist(),
        },
    )


__all__ = [
    "APPROXIMATE_NORMAL_95_Z",
    "BOUND_PROXIMITY_RELATIVE_TOLERANCE",
    "FittableParameter",
    "LeastSquaresCalibrationResult",
    "PredictionFunction",
    "fit_least_squares",
]
