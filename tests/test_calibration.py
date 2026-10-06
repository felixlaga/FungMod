from __future__ import annotations

import numpy as np
import pytest

from fungal_model.calibration import (
    FittableParameter,
    fit_least_squares,
    residuals_between,
    sequential_train_validation_split,
)
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, UnitError


def parameter(
    *,
    name: str,
    symbol: str,
    value,
    units: str,
) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source="Artificial Stage 10 calibration benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only for calibration utility tests.",
        measurement_method="defined benchmark value",
    )


def line_predictor(x_values):
    def predict(parameters: ParameterSet):
        slope = parameters.require_quantity("k", "second ** -1")
        return {"y": slope * x_values}

    return predict


def test_pointwise_uncertainty_recovers_analytical_weighted_fit() -> None:
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 12.0])
    sigma = np.array([0.1, 0.2, 10.0])
    base = ParameterSet([parameter(name="slope", symbol="k", value=2.0, units="1/second")])
    spec = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="low", symbol="low", value=0.0, units="1/second"),
        upper_bound=parameter(name="high", symbol="high", value=10.0, units="1/second"),
    )
    fit = fit_least_squares(
        base_parameters=base, fittable_parameters=[spec], predict=line_predictor(Q_(x, "second")),
        observations={"y": Q_(y, "dimensionless")},
        residual_scales={"y": Q_(sigma, "dimensionless")}, validation_indices=(),
        calibration_source="Artificial heteroscedastic linear regression with known analytic optimum.",
    )
    assert fit.success
    expected = np.sum(x * y / sigma**2) / np.sum(x**2 / sigma**2)
    assert fit.fitted_parameters.get("k").value == pytest.approx(expected, rel=1e-6)
    assert abs(expected - np.sum(x*y) / np.sum(x*x)) > 1.0


def test_pointwise_scales_convert_units_and_follow_noncontiguous_split() -> None:
    residuals = residuals_between(
        predictions={"y": Q_([2.0, 4.0, 7.0], "kilogram")},
        observations={"y": Q_([1.0, 2.0, 3.0], "kilogram")},
        residual_scales={"y": Q_([100.0, 200.0, 400.0], "gram")}, indices=[2, 0],
    )
    np.testing.assert_allclose(residuals.flattened_scaled(), [10.0, 10.0])


def test_normal_interval_outside_bounds_is_visible_and_warned() -> None:
    from fungal_model.calibration.fitting import _covariance_and_intervals

    parameters = ParameterSet([parameter(name="slope", symbol="k", value=0.1, units="1/second")])
    spec = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="low", symbol="low", value=0.0, units="1/second"),
        upper_bound=parameter(name="high", symbol="high", value=1.0, units="1/second"),
    )
    covariance, intervals, warnings = _covariance_and_intervals(
        jacobian=np.ones((3, 1)), residual_vector=np.array([2.0, -2.0, 0.0]),
        fitted_vector=np.array([0.1]), fittable_parameters=[spec], fitted_parameters=parameters,
    )
    assert covariance["k"]["k"] == pytest.approx(4.0 / 3.0)
    assert intervals["k"]["lower_95_approx"] < 0.0
    assert intervals["k"]["upper_95_approx"] > 1.0
    assert any("extends outside its optimizer bounds" in message for message in warnings)


@pytest.mark.parametrize("scale", [[1.0], [[1.0, 2.0]], [1.0, 0.0], [1.0, float('nan')], float('inf')])
def test_residual_scale_shape_and_finiteness_are_enforced(scale) -> None:
    with pytest.raises(ValueError, match="Residual scale"):
        residuals_between(
            predictions={"y": Q_([1.0, 2.0], "second")},
            observations={"y": Q_([0.0, 0.0], "second")},
            residual_scales={"y": Q_(scale, "second")},
        ).flattened_scaled()


def test_least_squares_fit_recovers_slope_and_records_validation_split() -> None:
    x_values = Q_(np.linspace(0.0, 5.0, 6), "second")
    observations = {"y": Q_(2.0 * x_values.magnitude, "dimensionless")}
    base = ParameterSet(
        [
            parameter(name="test slope", symbol="k", value=1.0, units="1 / second"),
        ]
    )
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="lower slope bound", symbol="k_min", value=0.0, units="1 / second"),
        upper_bound=parameter(name="upper slope bound", symbol="k_max", value=5.0, units="1 / second"),
    )
    train, validation = sequential_train_validation_split(len(x_values.magnitude))

    result = fit_least_squares(
        base_parameters=base,
        fittable_parameters=[fittable],
        predict=line_predictor(x_values),
        observations=observations,
        train_indices=train,
        validation_indices=validation,
        calibration_source="Artificial Stage 10 linear calibration test.",
    )

    assert result.success
    assert result.fitted_parameters.get("k").quantity.to("1 / second").magnitude == pytest.approx(2.0)
    assert not result.validation_uses_training_data
    assert result.training_residuals is not None
    assert result.validation_residuals is not None
    assert result.training_residuals.rmse_by_species()["y"]["rmse"] < 1e-10
    assert result.confidence_intervals is not None


def test_declared_optimizer_options_are_passed_and_recorded() -> None:
    x_values = Q_(np.linspace(0.0, 5.0, 6), "second")
    observations = {"y": Q_(2.0 * x_values.magnitude, "dimensionless")}
    base = ParameterSet([parameter(name="test slope", symbol="k", value=1.0, units="1 / second")])
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="lower slope bound", symbol="k_min", value=0.0, units="1 / second"),
        upper_bound=parameter(name="upper slope bound", symbol="k_max", value=5.0, units="1 / second"),
    )
    common = dict(base_parameters=base, fittable_parameters=[fittable], predict=line_predictor(x_values),
                  observations=observations, calibration_source="Artificial optimizer-option test.")

    default = fit_least_squares(**common)
    assert default.optimizer_metadata["finite_difference_step"] is None
    assert default.optimizer_metadata["ftol"] is None and default.optimizer_metadata["undeclared_options"].startswith("scipy")

    declared = fit_least_squares(**common, diff_step=1e-3, ftol=1e-12, xtol=1e-12, gtol=1e-12)
    assert declared.success
    assert declared.fitted_parameters.get("k").quantity.to("1 / second").magnitude == pytest.approx(2.0)
    assert declared.optimizer_metadata["finite_difference_step"] == 1e-3
    assert declared.optimizer_metadata["ftol"] == declared.optimizer_metadata["xtol"] == declared.optimizer_metadata["gtol"] == 1e-12
    assert declared.optimizer_metadata["method"] == "trf"

    for options in ({"diff_step": 0.0}, {"diff_step": 1.5}, {"ftol": -1e-8}, {"xtol": float("nan")}, {"gtol": float("inf")}):
        with pytest.raises(ValueError, match="must be|below one"):
            fit_least_squares(**common, **options)


def test_fit_reports_when_validation_reuses_training_data() -> None:
    x_values = Q_(np.arange(4.0), "second")
    observations = {"y": Q_(3.0 * x_values.magnitude, "dimensionless")}
    base = ParameterSet(
        [parameter(name="test slope", symbol="k", value=1.0, units="1 / second")]
    )
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="lower slope bound", symbol="k_min", value=0.0, units="1 / second"),
        upper_bound=parameter(name="upper slope bound", symbol="k_max", value=10.0, units="1 / second"),
    )

    result = fit_least_squares(
        base_parameters=base,
        fittable_parameters=[fittable],
        predict=line_predictor(x_values),
        observations=observations,
        calibration_source="Artificial Stage 10 reused-data warning test.",
    )

    assert result.validation_uses_training_data
    assert any("reuse training data" in warning for warning in result.warnings)


def test_residuals_reject_incompatible_prediction_units() -> None:
    with pytest.raises(UnitError):
        residuals_between(
            predictions={"y": Q_(np.array([1.0]), "meter")},
            observations={"y": Q_(np.array([1.0]), "second")},
        )


def test_parameter_bound_units_are_enforced() -> None:
    base = ParameterSet(
        [parameter(name="test slope", symbol="k", value=1.0, units="1 / second")]
    )
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="bad lower bound", symbol="k_min", value=0.0, units="meter"),
        upper_bound=parameter(name="upper bound", symbol="k_max", value=2.0, units="1 / second"),
    )

    with pytest.raises(UnitError):
        fittable.validate(base)


def test_failed_fit_is_reported_not_hidden() -> None:
    x_values = Q_(np.arange(3.0), "second")
    observations = {"y": Q_(x_values.magnitude, "dimensionless")}
    base = ParameterSet(
        [parameter(name="test slope", symbol="k", value=1.0, units="1 / second")]
    )
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="lower slope bound", symbol="k_min", value=0.0, units="1 / second"),
        upper_bound=parameter(name="upper slope bound", symbol="k_max", value=2.0, units="1 / second"),
    )

    def failing_predict(parameters: ParameterSet):
        del parameters
        raise RuntimeError("intentional model failure")

    result = fit_least_squares(
        base_parameters=base,
        fittable_parameters=[fittable],
        predict=failing_predict,
        observations=observations,
        calibration_source="Artificial Stage 10 failed-fit reporting test.",
    )

    assert not result.success
    assert "intentional model failure" in result.message


def test_calibration_source_is_required() -> None:
    base = ParameterSet(
        [parameter(name="test slope", symbol="k", value=1.0, units="1 / second")]
    )
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="lower slope bound", symbol="k_min", value=0.0, units="1 / second"),
        upper_bound=parameter(name="upper slope bound", symbol="k_max", value=2.0, units="1 / second"),
    )

    with pytest.raises(ProvenanceError):
        fit_least_squares(
            base_parameters=base,
            fittable_parameters=[fittable],
            predict=line_predictor(Q_(np.arange(3.0), "second")),
            observations={"y": Q_(np.arange(3.0), "dimensionless")},
            calibration_source="",
        )
