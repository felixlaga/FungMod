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

DEFAULT_RELATIVE_DIFFERENCE_STEP = Parameter(
    name="least-squares finite-difference relative step",
    symbol="delta_fit_fd",
    value=1.0e-3,
    units="dimensionless",
    uncertainty=None,
    source=(
        "Gelain 2020 model-criticism study, frozen-plan amendment 3 of 2026-10-05 "
        "(data/benchmarks/gelain_2020_criticism/plan.json on branch "
        "claude/gelain-criticism-plan, commits 085d44f and 70e599a, ledger entry "
        "CRIT-003). With scipy's default step of about 1.5e-8 the forward differences "
        "differentiated the adaptive ODE integrator's step noise: residual-derivative "
        "norms of weakly entering constants were 15 times their converged values, the "
        "trust region collapsed and every start stopped 1.3 percent above the minimum "
        "COPASI found. A relative step of 1e-3 made the optimum stationary and "
        "reproduced the cross-solver optimum. The Gelain v2 plan had declared the same "
        "value as log_parameter_difference_step."
    ),
    confidence_level="testing",
    notes=(
        "Relative step of the forward-difference Jacobian in the linear parameter space "
        "that fit_least_squares optimises: scipy perturbs each parameter by "
        "delta_fit_fd times its current magnitude, so the step is one part in a "
        "thousand of the value whatever its units. Appropriate when residuals come from "
        "an adaptive integrator whose output is rough at the tolerance level; a smooth "
        "analytic predictor would tolerate a smaller step, and a caller may declare one. "
        "The step degenerates for a parameter whose value is exactly zero, where scipy "
        "substitutes its machine-precision default. The value and its origin are "
        "recorded in optimizer_metadata of every result."
    ),
    measurement_method="software configuration",
)

#: Description recorded with every fit of the space in which the difference step acts.
FINITE_DIFFERENCE_PARAMETER_SPACE = (
    "linear: each fitted parameter is perturbed by relative_difference_step times its "
    "current magnitude, in its declared units"
)


def _resolve_relative_difference_step(step: float | None) -> tuple[float, str]:
    """Return the finite-difference step to use and where it came from."""

    if step is None:
        value = float(cast(Quantity, DEFAULT_RELATIVE_DIFFERENCE_STEP.quantity).magnitude)
        return value, "default DEFAULT_RELATIVE_DIFFERENCE_STEP"
    if (
        isinstance(step, bool)
        or not isinstance(step, (int, float, np.integer, np.floating))
        or not np.isfinite(step)
        or not 0.0 < float(step) < 1.0
    ):
        raise ValueError(
            "relative_difference_step must be a finite number strictly between 0 and 1; "
            f"got {step!r}. It is the relative finite-difference step of the Jacobian "
            "in linear parameter space."
        )
    return float(step), "caller"


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
        lower, upper = fittable_parameters[index].bounds_numeric(fitted_parameters)
        if value - z_value * standard_error < lower or value + z_value * standard_error > upper:
            warnings.append(
                f"Approximate confidence interval for {symbol} extends outside its optimizer bounds; "
                "the untruncated local normal approximation may be unsuitable."
            )
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
    relative_difference_step: float | None = None,
) -> LeastSquaresCalibrationResult:
    """Fit selected parameters by bounded least squares.

    The optimiser works in the linear parameter space of the fittable
    parameters' declared units and estimates the Jacobian by forward
    differences. ``relative_difference_step`` is the relative step of those
    differences (each parameter is perturbed by the step times its current
    magnitude). When it is ``None`` the named constant
    ``DEFAULT_RELATIVE_DIFFERENCE_STEP`` (1e-3) applies; it exists because
    scipy's default of about 1.5e-8 differentiates the step noise of adaptive
    ODE integrators. The step actually used, its origin, and the evaluation
    budget actually passed to scipy are recorded in ``optimizer_metadata``
    (``relative_difference_step``, ``relative_difference_step_origin``,
    ``finite_difference_parameter_space``, ``max_nfev``, ``max_nfev_origin``).
    ``max_nfev=None`` keeps scipy's documented budget of 100 evaluations per
    fitted parameter, which is then recorded as the number used.

    Failed optimizer runs are returned as `success=False` reports rather than
    being hidden or converted into apparently valid fits.
    """

    if not has_text(calibration_source):
        raise ProvenanceError("calibration_source is required.")
    if not fittable_parameters:
        raise ValueError("At least one fittable parameter is required.")
    difference_step, difference_step_origin = _resolve_relative_difference_step(
        relative_difference_step
    )
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
    if max_nfev is None:
        # scipy's documented default for the trust-region-reflective method.
        effective_max_nfev: Any = 100 * len(fittables)
        max_nfev_origin = "scipy default (100 evaluations per fitted parameter)"
    else:
        effective_max_nfev = max_nfev
        max_nfev_origin = "caller"
    optimizer_settings: dict[str, Any] = {
        "max_nfev": effective_max_nfev,
        "max_nfev_origin": max_nfev_origin,
        "relative_difference_step": difference_step,
        "relative_difference_step_origin": difference_step_origin,
        "finite_difference_parameter_space": FINITE_DIFFERENCE_PARAMETER_SPACE,
    }
    warnings: list[str] = []
    for spec, value in zip(fittables, x0, strict=True):
        if value == 0.0:
            warnings.append(
                f"Fittable parameter {spec.symbol} starts at exactly zero; the relative "
                "finite-difference step degenerates there and scipy substitutes its "
                "machine-precision default step until the parameter moves away from zero."
            )
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
            max_nfev=effective_max_nfev,
            diff_step=difference_step,
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
            optimizer_metadata={"exception_type": type(exc).__name__, **optimizer_settings},
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
            **optimizer_settings,
        },
    )


__all__ = [
    "APPROXIMATE_NORMAL_95_Z",
    "BOUND_PROXIMITY_RELATIVE_TOLERANCE",
    "DEFAULT_RELATIVE_DIFFERENCE_STEP",
    "FINITE_DIFFERENCE_PARAMETER_SPACE",
    "FittableParameter",
    "LeastSquaresCalibrationResult",
    "PredictionFunction",
    "fit_least_squares",
]
