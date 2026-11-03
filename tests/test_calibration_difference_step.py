"""Finite-difference step of the least-squares calibration API.

Every model here is an artificial numerical fixture. The toy ODE (saturating
loss with a fixed periodic rate modulation) exists only so that an adaptive
integrator takes many steps and its output is rough at the tolerance level; it
carries no biological or experimental claim.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

from fungal_model.calibration import (
    DEFAULT_RELATIVE_DIFFERENCE_STEP,
    FittableParameter,
    calibrate_configured_model,
    fit_least_squares,
    profile_likelihood,
)
from fungal_model.calibration import profile as profile_module
from fungal_model.calibration.fitting import FINITE_DIFFERENCE_PARAMETER_SPACE
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_

ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIG = ROOT / "data" / "model_configs" / "synthetic_first_order_calibration.yml"
assert DEFAULT_RELATIVE_DIFFERENCE_STEP.value is not None
DECLARED_STEP = float(DEFAULT_RELATIVE_DIFFERENCE_STEP.value)
SCIPY_DEFAULT_STEP = float(np.sqrt(np.finfo(float).eps))

# Toy problem: dy/dt = -k y / (K + y) (1 + a sin(w t)); the modulation is fixed and
# forces roughly a thousand LSODA steps per solve at rtol 1e-6.
TIMES = np.linspace(0.5, 12.0, 24)
INITIAL = 10.0
MODULATION_AMPLITUDE = 0.3
MODULATION_FREQUENCY = 40.0
TRUE_RATE = 1.0
TRUE_HALF_SATURATION = 0.5
LOWER = np.array([0.1, 1.0e-3])
UPPER = np.array([10.0, 10.0])


def _rhs(rate: float, half_saturation: float):
    def rhs(t: float, y: np.ndarray) -> list[float]:
        s = max(float(y[0]), 0.0)
        modulation = 1.0 + MODULATION_AMPLITUDE * np.sin(MODULATION_FREQUENCY * t)
        return [-rate * s / (half_saturation + s) * modulation]

    return rhs


def _simulate(rate: float, half_saturation: float, *, method: str = "LSODA",
              rtol: float = 1.0e-6, atol: float = 1.0e-9) -> np.ndarray:
    solution = solve_ivp(_rhs(rate, half_saturation), (0.0, float(TIMES[-1])), [INITIAL],
                         t_eval=TIMES, method=method, rtol=rtol, atol=atol)
    if not solution.success or solution.y.shape[1] != TIMES.size:
        raise RuntimeError(solution.message)
    return np.asarray(solution.y[0], dtype=float)


# Deterministic pseudo-noise keeps the optimum away from zero residuals without a RNG.
OBSERVED = (_simulate(TRUE_RATE, TRUE_HALF_SATURATION, method="DOP853", rtol=1.0e-12, atol=1.0e-14)
            + 0.02 * np.sin(7.0 * np.arange(TIMES.size)))


def _loose_residuals(vector: np.ndarray) -> np.ndarray:
    return _simulate(float(vector[0]), float(vector[1])) - OBSERVED


def _tight_residuals(vector: np.ndarray) -> np.ndarray:
    return _simulate(float(vector[0]), float(vector[1]), method="DOP853", rtol=1.0e-12, atol=1.0e-14) - OBSERVED


def _parameter(symbol: str, value: float | None, units: str) -> Parameter:
    return Parameter(
        name=symbol, symbol=symbol, value=value, units=units, uncertainty=None,
        source="Artificial finite-difference-step benchmark; no physical claim.",
        confidence_level="testing", notes="Calibration numerics test only.",
        measurement_method="defined benchmark value",
    )


def _toy_problem(rate0: float, half0: float):
    base = ParameterSet([_parameter("k", rate0, "1/hour"), _parameter("K", half0, "gram/liter")])
    fittables = [
        FittableParameter("k", _parameter("k_min", float(LOWER[0]), "1/hour"),
                          _parameter("k_max", float(UPPER[0]), "1/hour")),
        FittableParameter("K", _parameter("K_min", float(LOWER[1]), "gram/liter"),
                          _parameter("K_max", float(UPPER[1]), "gram/liter")),
    ]

    def predict(parameters: ParameterSet):
        rate = float(parameters.require_quantity("k", "1/hour").magnitude)
        half = float(parameters.require_quantity("K", "gram/liter").magnitude)
        return {"substrate": Q_(_simulate(rate, half), "gram/liter")}

    return base, fittables, predict, {"substrate": Q_(OBSERVED, "gram/liter")}


def _linear_problem(slope0: float = 1.0, lower: float = 0.0):
    x = Q_(np.arange(1.0, 6.0), "second")
    base = ParameterSet([_parameter("k", slope0, "1/second")])
    fittable = FittableParameter("k", _parameter("k_min", lower, "1/second"), _parameter("k_max", 5.0, "1/second"))

    def predict(parameters: ParameterSet):
        return {"y": parameters.require_quantity("k", "1/second") * x}

    return base, [fittable], predict, {"y": Q_(2.0 * x.magnitude, "dimensionless")}


def _forward_jacobian(fun, x: np.ndarray, *, absolute_steps: np.ndarray) -> np.ndarray:
    f0 = fun(x)
    columns = []
    for index, step in enumerate(absolute_steps):
        shifted = x.copy()
        shifted[index] += step
        columns.append((fun(shifted) - f0) / step)
    return np.column_stack(columns)


def _central_reference_jacobian(x: np.ndarray) -> np.ndarray:
    columns = []
    for index in range(x.size):
        step = 1.0e-4 * abs(x[index])
        up, down = x.copy(), x.copy()
        up[index] += step
        down[index] -= step
        columns.append((_tight_residuals(up) - _tight_residuals(down)) / (2.0 * step))
    return np.column_stack(columns)


def test_declared_step_reaches_lower_cost_than_scipy_default_on_integrator_noise() -> None:
    start = np.array([2.0, 1.0])
    base, fittables, predict, observations = _toy_problem(*start)

    scipy_default = least_squares(_loose_residuals, start, bounds=(LOWER, UPPER))
    declared = fit_least_squares(
        base_parameters=base, fittable_parameters=fittables, predict=predict,
        observations=observations, validation_indices=(),
        calibration_source="Artificial adaptive-integrator noise benchmark for the difference step.",
    )

    assert declared.success
    assert declared.cost is not None
    # Same objective, same start, same bounds and budget: scipy's default step stalls
    # near the start (observed ratio of order 1e4), the declared step converges.
    assert scipy_default.cost > 10.0 * declared.cost
    assert declared.fitted_parameters.get("k").value == pytest.approx(TRUE_RATE, rel=0.02)
    assert declared.fitted_parameters.get("K").value == pytest.approx(TRUE_HALF_SATURATION, rel=0.05)
    assert declared.optimizer_metadata["relative_difference_step"] == DECLARED_STEP


def test_scipy_default_step_differentiates_integrator_noise() -> None:
    starts = [(0.5, 0.2), (2.0, 1.0), (3.0, 0.1), (0.3, 2.0), (1.5, 0.8), (0.7, 0.05)]
    default_error = 0.0
    declared_error = 0.0
    for start in starts:
        x = np.array(start, dtype=float)
        reference = _central_reference_jacobian(x)
        norms = np.linalg.norm(reference, axis=0)
        default = _forward_jacobian(_loose_residuals, x, absolute_steps=SCIPY_DEFAULT_STEP * np.maximum(1.0, np.abs(x)))
        declared = _forward_jacobian(_loose_residuals, x, absolute_steps=DECLARED_STEP * np.abs(x))
        default_error += float(np.sum(np.linalg.norm(default - reference, axis=0) / norms))
        declared_error += float(np.sum(np.linalg.norm(declared - reference, axis=0) / norms))
    # Summed over starts and columns the default-step Jacobian error is tens of times
    # the declared-step error (observed ratio about 40).
    assert default_error > 5.0 * declared_error


def test_default_step_and_budget_are_recorded_and_saved(tmp_path: Path) -> None:
    base, fittables, predict, observations = _linear_problem()
    result = fit_least_squares(
        base_parameters=base, fittable_parameters=fittables, predict=predict,
        observations=observations, validation_indices=(), calibration_source="Artificial linear fixture.",
    )
    metadata = result.optimizer_metadata
    assert result.success
    assert metadata["relative_difference_step"] == DECLARED_STEP == 1.0e-3
    assert metadata["relative_difference_step_origin"] == "default DEFAULT_RELATIVE_DIFFERENCE_STEP"
    assert metadata["finite_difference_parameter_space"] == FINITE_DIFFERENCE_PARAMETER_SPACE
    assert metadata["max_nfev"] == 100 * len(fittables)
    assert metadata["max_nfev_origin"].startswith("scipy default")

    result.save(tmp_path)
    saved = json.loads((tmp_path / "fit_result.json").read_text(encoding="utf-8"))["optimizer_metadata"]
    for key in ("relative_difference_step", "relative_difference_step_origin",
                "finite_difference_parameter_space", "max_nfev", "max_nfev_origin"):
        assert saved[key] == metadata[key]


def test_caller_step_and_budget_are_recorded() -> None:
    base, fittables, predict, observations = _linear_problem()
    result = fit_least_squares(
        base_parameters=base, fittable_parameters=fittables, predict=predict,
        observations=observations, validation_indices=(), calibration_source="Artificial linear fixture.",
        max_nfev=50, relative_difference_step=1.0e-4,
    )
    assert result.success
    assert result.optimizer_metadata["relative_difference_step"] == 1.0e-4
    assert result.optimizer_metadata["relative_difference_step_origin"] == "caller"
    assert result.optimizer_metadata["max_nfev"] == 50
    assert result.optimizer_metadata["max_nfev_origin"] == "caller"


def test_failed_fit_still_records_optimizer_settings() -> None:
    base, fittables, _predict, observations = _linear_problem()

    def failing_predict(parameters: ParameterSet):
        raise RuntimeError("intentional model failure")

    result = fit_least_squares(
        base_parameters=base, fittable_parameters=fittables, predict=failing_predict,
        observations=observations, validation_indices=(), calibration_source="Artificial failure fixture.",
        relative_difference_step=2.0e-3,
    )
    assert not result.success
    assert result.optimizer_metadata["exception_type"] == "RuntimeError"
    assert result.optimizer_metadata["relative_difference_step"] == 2.0e-3
    assert result.optimizer_metadata["relative_difference_step_origin"] == "caller"
    assert result.optimizer_metadata["max_nfev"] == 100


@pytest.mark.parametrize("step", [0.0, 1.0, -1.0e-3, float("nan"), float("inf"), True, "1e-3"])
def test_invalid_difference_step_is_rejected(step) -> None:
    base, fittables, predict, observations = _linear_problem()
    with pytest.raises(ValueError, match="relative_difference_step"):
        fit_least_squares(
            base_parameters=base, fittable_parameters=fittables, predict=predict,
            observations=observations, validation_indices=(), calibration_source="Artificial linear fixture.",
            relative_difference_step=step,  # type: ignore[arg-type]
        )


def test_zero_initial_value_degenerate_step_is_warned() -> None:
    # Zero strictly inside the bounds: the relative step is zero there and scipy
    # substitutes its machine-precision default, which the result must say.
    base, fittables, predict, observations = _linear_problem(slope0=0.0, lower=-5.0)
    result = fit_least_squares(
        base_parameters=base, fittable_parameters=fittables, predict=predict,
        observations=observations, validation_indices=(), calibration_source="Artificial linear fixture.",
    )
    assert result.success
    assert any("starts at exactly zero" in warning for warning in result.warnings)
    assert result.fitted_parameters.get("k").value == pytest.approx(2.0, rel=1e-6)


def _two_parameter_fit(relative_difference_step: float | None):
    x = np.arange(5.0)

    def predict(parameters: ParameterSet):
        a = parameters.require_quantity("a").magnitude
        b = parameters.require_quantity("b").magnitude
        return {"y": Q_(a * x + b, "dimensionless")}

    observations = {"y": Q_(2.0 * x + 1.0, "dimensionless")}
    scales = {"y": Q_(np.full(5, 0.5), "dimensionless")}
    fit = fit_least_squares(
        base_parameters=ParameterSet([_parameter("a", 1.0, "dimensionless"), _parameter("b", 1.0, "dimensionless")]),
        fittable_parameters=[
            FittableParameter(symbol, _parameter("lo", -10.0, "dimensionless"), _parameter("hi", 10.0, "dimensionless"))
            for symbol in ("a", "b")
        ],
        predict=predict, observations=observations, residual_scales=scales, validation_indices=(),
        calibration_source="Artificial analytic fixture.", relative_difference_step=relative_difference_step,
    )
    return fit, predict, observations, scales


def test_profile_reuses_reference_fit_step_and_records_it(monkeypatch: pytest.MonkeyPatch) -> None:
    fit, predict, observations, scales = _two_parameter_fit(2.0e-3)
    seen: list[float | None] = []
    real_fit = profile_module.fit_least_squares

    def spy(**kwargs):
        seen.append(kwargs["relative_difference_step"])
        return real_fit(**kwargs)

    monkeypatch.setattr(profile_module, "fit_least_squares", spy)
    grids = {"a": Q_([1.0, 2.0], "dimensionless")}
    reused = profile_likelihood(result=fit, predict=predict, observations=observations,
                                residual_scales=scales, grids=grids, source="Artificial declared scales.")
    assert reused.complete
    assert seen == [2.0e-3, 2.0e-3]
    assert reused.optimizer_settings["relative_difference_step"] == 2.0e-3
    assert reused.optimizer_settings["relative_difference_step_origin"] == "reference fit optimizer_metadata"
    assert reused.to_dict()["optimizer_settings"] == dict(reused.optimizer_settings)

    seen.clear()
    overridden = profile_likelihood(result=fit, predict=predict, observations=observations,
                                    residual_scales=scales, grids=grids, source="Artificial declared scales.",
                                    relative_difference_step=5.0e-4, max_nfev=40)
    assert seen == [5.0e-4, 5.0e-4]
    assert overridden.optimizer_settings == {
        "relative_difference_step": 5.0e-4, "relative_difference_step_origin": "caller", "max_nfev": 40,
    }


def test_configured_calibration_records_step_and_hands_it_to_profile(tmp_path: Path) -> None:
    from fungal_model.resources import example_data_path

    dataset = example_data_path("experiments/synthetic/first_order_ab/synthetic_first_order_ab.yml")
    result = calibrate_configured_model(
        model_config=MODEL_CONFIG, dataset=dataset, parameter_symbols=["k_ab"],
        observable_mapping={"product_mass": "released_product_amount"}, initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)}, relative_difference_step=2.0e-3,
        profile_grids={"k_ab": Q_([0.05, 0.1], "1/second")},
        profile_source="Artificial declared independent Gaussian observation noise.", output_dir=tmp_path,
    )
    metadata = result.optimizer_metadata
    assert metadata["relative_difference_step"] == 2.0e-3
    assert metadata["relative_difference_step_origin"] == "caller"
    assert metadata["max_nfev"] == 100
    assert metadata["profile_likelihood"]["optimizer_settings"]["relative_difference_step"] == 2.0e-3
    for name in ("optimizer_metadata.json", "calibration_record.json"):
        saved = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        saved = saved if name == "optimizer_metadata.json" else saved["optimizer_metadata"]
        assert saved["relative_difference_step"] == 2.0e-3
        assert saved["relative_difference_step_origin"] == "caller"
