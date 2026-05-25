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
