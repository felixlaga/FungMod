from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model.calibration import (
    DEFAULT_RELATIVE_DIFFERENCE_STEP,
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
    assert result.optimizer_metadata["finite_difference_step"] == DEFAULT_RELATIVE_DIFFERENCE_STEP.value
    assert result.optimizer_metadata["finite_difference_step_origin"] == DEFAULT_RELATIVE_DIFFERENCE_STEP.symbol


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


def _slope_problem(x_values):
    base = ParameterSet([parameter(name="test slope", symbol="k", value=1.0, units="1 / second")])
    fittable = FittableParameter(
        symbol="k",
        lower_bound=parameter(name="lower slope bound", symbol="k_min", value=0.0, units="1 / second"),
        upper_bound=parameter(name="upper slope bound", symbol="k_max", value=5.0, units="1 / second"),
    )
    observations = {"y": Q_(2.0 * x_values.magnitude, "dimensionless")}
    return dict(
        base_parameters=base,
        fittable_parameters=[fittable],
        predict=line_predictor(x_values),
        observations=observations,
        validation_indices=(),
        calibration_source="Artificial finite-difference step recording test.",
    )


def test_difference_step_defaults_to_named_constant_and_is_recorded(tmp_path: Path) -> None:
    result = fit_least_squares(**_slope_problem(Q_(np.linspace(0.0, 5.0, 6), "second")))

    assert result.success
    metadata = result.optimizer_metadata
    assert DEFAULT_RELATIVE_DIFFERENCE_STEP.value == 1.0e-3
    assert metadata["finite_difference_step"] == DEFAULT_RELATIVE_DIFFERENCE_STEP.value
    assert metadata["finite_difference_step_origin"] == DEFAULT_RELATIVE_DIFFERENCE_STEP.symbol == "delta_fit_rel"
    assert "linear parameter space" in metadata["finite_difference_step_definition"]
    assert metadata["method"] == "trf"
    assert metadata["max_nfev"] == 100  # scipy's trf default of 100 evaluations per fitted parameter
    assert metadata["max_nfev_origin"].startswith("scipy default")
    assert "CRIT-003" in str(DEFAULT_RELATIVE_DIFFERENCE_STEP.source)

    result.save(tmp_path)
    saved = json.loads((tmp_path / "fit_result.json").read_text(encoding="utf-8"))
    assert saved["optimizer_metadata"]["finite_difference_step"] == 1.0e-3
    assert saved["optimizer_metadata"]["finite_difference_step_origin"] == "delta_fit_rel"
    assert saved["optimizer_metadata"]["max_nfev"] == 100


def test_caller_declared_difference_step_and_budget_are_used_and_recorded() -> None:
    result = fit_least_squares(**_slope_problem(Q_(np.linspace(0.0, 5.0, 6), "second")), diff_step=2.5e-4, max_nfev=40)

    assert result.success
    assert result.fitted_parameters.get("k").quantity.to("1 / second").magnitude == pytest.approx(2.0)
    metadata = result.optimizer_metadata
    assert metadata["finite_difference_step"] == 2.5e-4
    assert metadata["finite_difference_step_origin"] == "caller"
    assert metadata["max_nfev"] == 40
    assert metadata["max_nfev_origin"] == "caller"
    assert metadata["nfev"] <= 40


@pytest.mark.parametrize("step", [0.0, 1.0, -1.0e-3, float("nan"), float("inf"), True])
def test_invalid_difference_steps_are_refused(step) -> None:
    with pytest.raises(ValueError, match="diff_step"):
        fit_least_squares(**_slope_problem(Q_(np.arange(3.0), "second")), diff_step=step)


def test_zero_valued_parameter_reports_undefined_relative_step() -> None:
    x_values = Q_(np.linspace(0.0, 5.0, 6), "second")
    problem = _slope_problem(x_values)
    problem["base_parameters"] = ParameterSet(
        [parameter(name="test slope", symbol="k", value=0.0, units="1 / second")]
    )
    problem["fittable_parameters"] = [
        FittableParameter(
            symbol="k",
            lower_bound=parameter(name="lower slope bound", symbol="k_min", value=-5.0, units="1 / second"),
            upper_bound=parameter(name="upper slope bound", symbol="k_max", value=5.0, units="1 / second"),
        )
    ]

    result = fit_least_squares(**problem)

    assert result.success
    assert result.fitted_parameters.get("k").quantity.to("1 / second").magnitude == pytest.approx(2.0)
    zero_warnings = [message for message in result.warnings if "exactly zero" in message]
    assert len(zero_warnings) == 1
    assert "initial value" in zero_warnings[0] and "k" in zero_warnings[0]


def _stiff_pool_chain_predictor(times: np.ndarray, *, method: str, rtol: float, atol: float):
    """Artificial stiff pool chain integrated adaptively; no physical or biological claim.

    A saturating conversion of pool ``a`` feeds pool ``b``, which equilibrates
    quickly with a bound pool ``c`` (rates ``kon`` and ``kon / 2``) and is lost
    at rate ``kd``. The fast equilibration makes the system stiff, and the
    observations (``a`` and ``b + c``) resolve ``kon`` only weakly, which is the
    situation in which an adaptive integrator's step noise dominates
    finite-difference derivatives at scipy's default step (ledger CRIT-003).
    """
    from scipy.integrate import solve_ivp

    def predict(parameters: ParameterSet):
        vmax = float(parameters.require_quantity("vmax", "1 / second").magnitude)
        k_half = float(parameters.require_quantity("K", "dimensionless").magnitude)
        kd = float(parameters.require_quantity("kd", "1 / second").magnitude)
        kon = float(parameters.require_quantity("kon", "1 / second").magnitude)
        koff = kon / 2.0

        def rhs(_, y):
            a, b, c = y
            conversion = vmax * a / (k_half + a)
            return [-conversion, conversion - kd * b - kon * b + koff * c, kon * b - koff * c]

        solution = solve_ivp(
            rhs, (0.0, float(times[-1])), [1.0, 0.0, 0.0], t_eval=times, method=method, rtol=rtol, atol=atol
        )
        if solution.status != 0:
            raise RuntimeError(solution.message)
        return {
            "a": Q_(solution.y[0], "dimensionless"),
            "b_total": Q_(solution.y[1] + solution.y[2], "dimensionless"),
        }

    return predict


def test_declared_difference_step_reaches_lower_cost_than_scipy_default_on_adaptive_ode_residuals() -> None:
    times = np.linspace(0.5, 12.0, 10)
    truth = {"vmax": (1.5, "1 / second"), "K": (2.0, "dimensionless"), "kd": (1.2, "1 / second"), "kon": (400.0, "1 / second")}
    bounds = {"vmax": (1.0, 20.0), "K": (1.0, 20.0), "kd": (1.0, 20.0), "kon": (100.0, 2000.0)}
    truth_set = ParameterSet([parameter(name=s, symbol=s, value=v, units=u) for s, (v, u) in truth.items()])
    # Observations from a tight-tolerance integration of the same artificial system.
    observations = _stiff_pool_chain_predictor(times, method="Radau", rtol=1e-12, atol=1e-14)(truth_set)
    start = ParameterSet(
        [parameter(name=s, symbol=s, value=(lo + hi) / 2.0, units=truth[s][1]) for s, (lo, hi) in bounds.items()]
    )
    fittables = [
        FittableParameter(
            symbol=s,
            lower_bound=parameter(name=f"{s} lower", symbol=f"{s}_min", value=lo, units=truth[s][1]),
            upper_bound=parameter(name=f"{s} upper", symbol=f"{s}_max", value=hi, units=truth[s][1]),
        )
        for s, (lo, hi) in bounds.items()
    ]
    # The fitted model is integrated adaptively at loose tolerances, so its residuals carry step noise.
    predict = _stiff_pool_chain_predictor(times, method="LSODA", rtol=1e-3, atol=1e-6)
    problem = dict(
        base_parameters=start, fittable_parameters=fittables, predict=predict, observations=observations,
        validation_indices=(), calibration_source="Artificial stiff pool chain; finite-difference step benchmark.",
    )
    # scipy's default relative step is the square root of machine epsilon. With every bound at or above one,
    # passing it explicitly reproduces scipy's own step exactly (scipy multiplies by max(1, |x|) only then).
    scipy_default_step = float(np.sqrt(np.finfo(float).eps))
    assert scipy_default_step == pytest.approx(1.49e-8, rel=1e-2)

    with_scipy_default = fit_least_squares(**problem, diff_step=scipy_default_step)
    with_declared_step = fit_least_squares(**problem)

    assert with_scipy_default.optimizer_metadata["finite_difference_step"] == scipy_default_step
    assert with_declared_step.optimizer_metadata["finite_difference_step"] == DEFAULT_RELATIVE_DIFFERENCE_STEP.value
    assert with_scipy_default.cost is not None and with_declared_step.cost is not None
    # Differentiating the integrator's step noise collapses the trust region well above the minimum.
    assert with_scipy_default.cost > 10.0 * with_declared_step.cost
    assert with_declared_step.optimizer_metadata["optimality"] < with_scipy_default.optimizer_metadata["optimality"]
    for symbol in ("vmax", "K", "kd"):
        fitted = float(with_declared_step.fitted_parameters.require_quantity(symbol).magnitude)
        assert fitted == pytest.approx(truth[symbol][0], rel=0.05), symbol
    # kon is only weakly resolved by these observations and is deliberately not asserted.
