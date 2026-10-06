"""Conversion-dependent substrate reactivity: a generic rate modifier tested on a non-cellulose toy process."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fungal_model.calibration.bayesian import parameter_for_testing
from fungal_model.calibration.compiled_predictor import (
    ConfiguredCondition,
    ConfiguredConditionPredictor,
    ObservableMapping,
    inline_parameter_config_factory,
)
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_
from fungal_model.io.model_config import load_model_config
from fungal_model.modifiers import SubstrateReactivityModifier
from fungal_model.modifiers.reactivity import KADAM_2004_SOURCE
from fungal_model.processes.rate_modifiers import substrate_reactivity_modifier_from_config

ROOT = Path(__file__).resolve().parents[1]
TOY_CONFIG = ROOT / "data" / "model_configs" / "toy_homogeneous_ab.yml"


def _modifier() -> SubstrateReactivityModifier:
    return SubstrateReactivityModifier(
        substrate_state="polymer",
        reference_concentration_symbol="polymer_reference",
        exponent_symbol="reactivity_exponent",
        substrate_units="gram / liter",
    )


def _parameters(reference: float, exponent: float) -> ParameterSet:
    return ParameterSet(
        [
            parameter_for_testing("polymer_reference", reference, "gram / liter"),
            parameter_for_testing("reactivity_exponent", exponent),
        ]
    )


def test_activity_is_the_remaining_fraction_to_the_declared_power() -> None:
    modifier = _modifier()
    state = {"polymer": Q_(np.array([0.0, 2.5, 5.0, 10.0, 20.0]), "gram / liter")}
    activity = modifier.activity(parameters=_parameters(10.0, 1.0), environment=None, state=state)  # type: ignore[arg-type]
    np.testing.assert_allclose(activity.magnitude, [0.0, 0.25, 0.5, 1.0, 2.0])
    squared = modifier.activity(parameters=_parameters(10.0, 2.0), environment=None, state=state)  # type: ignore[arg-type]
    np.testing.assert_allclose(squared.magnitude, [0.0, 0.0625, 0.25, 1.0, 4.0])
    flat = modifier.activity(parameters=_parameters(10.0, 0.0), environment=None, state=state)  # type: ignore[arg-type]
    np.testing.assert_allclose(flat.magnitude, [0.0, 1.0, 1.0, 1.0, 1.0])
    rate = modifier.scale(rate=Q_(3.0, "gram / liter / hour"), parameters=_parameters(10.0, 1.0), environment=None, state={"polymer": Q_(5.0, "gram / liter")})  # type: ignore[arg-type]
    assert rate.magnitude == pytest.approx(1.5) and str(rate.units) == "gram / hour / liter"
    assert modifier.assumptions[0].source == KADAM_2004_SOURCE
    assert modifier.to_dict()["type"] == "substrate_reactivity"


def test_invalid_constants_and_missing_states_are_rejected() -> None:
    modifier = _modifier()
    state = {"polymer": Q_(5.0, "gram / liter")}
    with pytest.raises(ValueError, match="positive"):
        modifier.activity(parameters=_parameters(0.0, 1.0), environment=None, state=state)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative"):
        modifier.activity(parameters=_parameters(10.0, -0.5), environment=None, state=state)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="requires state"):
        modifier.activity(parameters=_parameters(10.0, 1.0), environment=None, state={"other": Q_(1.0, "gram / liter")})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="requires substrate_state"):
        substrate_reactivity_modifier_from_config({"type": "substrate_reactivity"}, state_units={"polymer": "gram / liter"})
    with pytest.raises(ValueError, match="unknown state"):
        substrate_reactivity_modifier_from_config(
            {"type": "substrate_reactivity", "substrate_state": "missing", "reference_concentration": "r", "exponent": "n"},
            state_units={"polymer": "gram / liter"},
        )
    with pytest.raises(ValueError, match="requires exponent"):
        substrate_reactivity_modifier_from_config(
            {"type": "substrate_reactivity", "substrate_state": "polymer", "reference_concentration": "r"},
            state_units={"polymer": "gram / liter"},
        )


def _toy_predictor(with_modifier: bool) -> ConfiguredConditionPredictor:
    raw = dict(load_model_config(TOY_CONFIG).raw)
    raw = __import__("json").loads(__import__("json").dumps(raw))
    raw["parameters"][0]["parameters"].extend(
        [
            {
                "name": "reference amount", "symbol": "a_reference", "value": 1.0, "units": "kilogram", "uncertainty": 0.0,
                "source": "framework test", "confidence_level": "testing", "notes": "toy", "measurement_method": "defined", "validity_range": "tests",
            },
            {
                "name": "reactivity exponent", "symbol": "a_exponent", "value": 1.0, "units": "dimensionless", "uncertainty": 0.0,
                "source": "framework test", "confidence_level": "testing", "notes": "toy", "measurement_method": "defined", "validity_range": "tests",
            },
        ]
    )
    if with_modifier:
        raw["processes"][0]["modifiers"] = [
            {
                "type": "substrate_reactivity",
                "substrate_state": "dissolved_substrate_amount",
                "reference_concentration": "a_reference",
                "exponent": "a_exponent",
            }
        ]
    factory = inline_parameter_config_factory(raw)
    condition = ConfiguredCondition("toy", factory, (ObservableMapping("substrate", "dissolved_substrate_amount", "kilogram"),))
    return ConfiguredConditionPredictor([condition], fitted_symbols=["k_ab", "a_exponent"], enforce_maturity=False)


def test_compiled_kernel_matches_the_analytic_solution_on_a_toy_first_order_process() -> None:
    times = np.linspace(0.0, 10.0, 6)
    base = _toy_predictor(with_modifier=False).predict_values({"k_ab": 0.3, "a_exponent": 1.0}, "toy", times)[:, 0]
    modified = _toy_predictor(with_modifier=True)
    unchanged = modified.predict_values({"k_ab": 0.3, "a_exponent": 0.0}, "toy", times)[:, 0]
    np.testing.assert_allclose(unchanged, base, rtol=1e-8)
    np.testing.assert_allclose(base, np.exp(-0.3 * times), rtol=1e-6)
    linear = modified.predict_values({"k_ab": 0.3, "a_exponent": 1.0}, "toy", times)[:, 0]
    # dA/dt = -k A (A / A0) with A0 = 1 kg integrates to A = 1 / (1 + k t).
    np.testing.assert_allclose(linear, 1.0 / (1.0 + 0.3 * times), rtol=1e-5)
    assert np.all(linear[1:] > base[1:])
