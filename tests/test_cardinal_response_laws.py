"""Rosso cardinal temperature (CTMI) and cardinal pH (CPM) response laws.

The laws are exercised with artificial cardinal values on a non-biological
first-order benchmark so that the shape, the compiled constant folding and the
modifier plumbing are tested without any organism claim.
"""

from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Environment
from fungal_model.io import ProcessConfig
from fungal_model.kinetics import cardinal_ph_activity, cardinal_temperature_activity
from fungal_model.modifiers import CardinalPHModifier, CardinalTemperatureModifier
from fungal_model.processes import (
    FirstOrderFactory,
    ModelBuilder,
    ProcessBuildContext,
    ProcessRegistry,
    RateModifierProcess,
    cardinal_ph_modifier_from_config,
    cardinal_temperature_modifier_from_config,
)
from fungal_model.solvers import ProcessODESolver, RunRequest

SOURCE = "Artificial cardinal test values; no organism claim."


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"artificial {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=None,
        source=SOURCE,
        confidence_level="testing",
        notes=SOURCE,
    )


def _parameters() -> ParameterSet:
    return ParameterSet(
        [
            _parameter("T_min", 280.0, "kelvin"),
            _parameter("T_opt", 305.0, "kelvin"),
            _parameter("T_max", 310.0, "kelvin"),
            _parameter("pH_min", 4.0, "dimensionless"),
            _parameter("pH_opt", 5.5, "dimensionless"),
            _parameter("pH_max", 8.0, "dimensionless"),
            _parameter("k_loss", 0.1, "1 / second"),
        ]
    )


def _ctmi(temperature, minimum, optimum, maximum):
    temperature = np.asarray(temperature, dtype=float)
    inside = (temperature > minimum) & (temperature < maximum)
    numerator = (temperature - maximum) * (temperature - minimum) ** 2
    denominator = (optimum - minimum) * (
        (optimum - minimum) * (temperature - optimum) - (optimum - maximum) * (optimum + minimum - 2.0 * temperature)
    )
    return np.where(inside, numerator / np.where(inside, denominator, 1.0), 0.0)


def test_ctmi_is_one_at_the_optimum_zero_at_the_bounds_and_matches_the_closed_form() -> None:
    temperatures = np.array([270.0, 280.0, 290.0, 300.0, 305.0, 308.0, 310.0, 320.0])
    activity = cardinal_temperature_activity(
        temperature=Q_(temperatures, "kelvin"),
        minimum_temperature=Q_(280.0, "kelvin"),
        optimum_temperature=Q_(305.0, "kelvin"),
        maximum_temperature=Q_(310.0, "kelvin"),
        source=SOURCE,
    )
    np.testing.assert_allclose(activity.magnitude, _ctmi(temperatures, 280.0, 305.0, 310.0), rtol=1e-12)
    assert activity.magnitude[4] == pytest.approx(1.0)
    assert activity.magnitude[[0, 1, 6, 7]].tolist() == [0.0, 0.0, 0.0, 0.0]
    assert np.all((activity.magnitude[2:6] > 0.0) & (activity.magnitude[2:6] <= 1.0))
    celsius = cardinal_temperature_activity(
        temperature=Q_(26.85, "degree_Celsius"),
        minimum_temperature=Q_(280.0, "kelvin"),
        optimum_temperature=Q_(305.0, "kelvin"),
        maximum_temperature=Q_(310.0, "kelvin"),
        source=SOURCE,
    )
    assert celsius.magnitude == pytest.approx(_ctmi(300.0, 280.0, 305.0, 310.0))


def test_ctmi_rejects_unordered_values_sub_midpoint_optima_and_missing_sources() -> None:
    kwargs = {"temperature": Q_(300.0, "kelvin"), "source": SOURCE}
    with pytest.raises(ValueError, match="minimum < optimum < maximum"):
        cardinal_temperature_activity(
            minimum_temperature=Q_(305.0, "kelvin"),
            optimum_temperature=Q_(300.0, "kelvin"),
            maximum_temperature=Q_(310.0, "kelvin"),
            **kwargs,
        )
    with pytest.raises(ValueError, match="midpoint"):
        cardinal_temperature_activity(
            minimum_temperature=Q_(280.0, "kelvin"),
            optimum_temperature=Q_(290.0, "kelvin"),
            maximum_temperature=Q_(310.0, "kelvin"),
            **kwargs,
        )
    with pytest.raises(ValueError, match="source"):
        cardinal_temperature_activity(
            temperature=Q_(300.0, "kelvin"),
            minimum_temperature=Q_(280.0, "kelvin"),
            optimum_temperature=Q_(305.0, "kelvin"),
            maximum_temperature=Q_(310.0, "kelvin"),
            source="  ",
        )


def test_cpm_is_one_at_the_optimum_zero_at_the_bounds_and_symmetric_about_a_central_optimum() -> None:
    ph = np.array([3.0, 4.0, 4.5, 5.5, 6.5, 8.0, 9.0])
    activity = cardinal_ph_activity(
        ph=Q_(ph, "dimensionless"),
        minimum_ph=Q_(4.0, "dimensionless"),
        optimum_ph=Q_(5.5, "dimensionless"),
        maximum_ph=Q_(8.0, "dimensionless"),
        source=SOURCE,
    )
    expected = (ph - 4.0) * (ph - 8.0) / ((ph - 4.0) * (ph - 8.0) - (ph - 5.5) ** 2)
    expected[(ph <= 4.0) | (ph >= 8.0)] = 0.0
    np.testing.assert_allclose(activity.magnitude, expected, rtol=1e-12)
    assert activity.magnitude[3] == pytest.approx(1.0)
    central = cardinal_ph_activity(
        ph=Q_(np.array([5.0, 7.0]), "dimensionless"),
        minimum_ph=Q_(4.0, "dimensionless"),
        optimum_ph=Q_(6.0, "dimensionless"),
        maximum_ph=Q_(8.0, "dimensionless"),
        source=SOURCE,
    )
    assert central.magnitude[0] == pytest.approx(central.magnitude[1])
    with pytest.raises(ValueError, match="minimum < optimum < maximum"):
        cardinal_ph_activity(
            ph=Q_(5.0, "dimensionless"),
            minimum_ph=Q_(6.0, "dimensionless"),
            optimum_ph=Q_(5.5, "dimensionless"),
            maximum_ph=Q_(8.0, "dimensionless"),
            source=SOURCE,
        )


def test_cardinal_modifiers_read_the_environment_and_fold_into_constant_kernels() -> None:
    parameters = _parameters()
    environment = Environment(name="e", temperature=Q_(300.0, "kelvin"), ph=Q_(5.0, "dimensionless"), source="test")
    temperature_modifier = CardinalTemperatureModifier("T_min", "T_opt", "T_max", SOURCE)
    ph_modifier = CardinalPHModifier("pH_min", "pH_opt", "pH_max", SOURCE)
    expected_temperature = float(_ctmi(300.0, 280.0, 305.0, 310.0))
    expected_ph = (5.0 - 4.0) * (5.0 - 8.0) / ((5.0 - 4.0) * (5.0 - 8.0) - (5.0 - 5.5) ** 2)
    assert temperature_modifier.activity(parameters=parameters, environment=environment).magnitude == pytest.approx(
        expected_temperature
    )
    assert ph_modifier.activity(parameters=parameters, environment=environment).magnitude == pytest.approx(expected_ph)
    scaled = ph_modifier.scale(rate=Q_(2.0, "mole / second"), parameters=parameters, environment=environment)
    assert scaled.to("mole / second").magnitude == pytest.approx(2.0 * expected_ph)
    context = KernelContext(
        state_index={"A": 0},
        state_units={"A": "millimolar"},
        time_units="second",
        parameters=parameters,
        environment=environment,
    )
    temperature_kernel = temperature_modifier.compile_activity(context)
    ph_kernel = ph_modifier.compile_activity(context)
    assert temperature_kernel is not None and ph_kernel is not None
    assert temperature_kernel(0.0, np.zeros(1)) == pytest.approx(expected_temperature)
    assert ph_kernel(3.0, np.ones(1)) == pytest.approx(expected_ph)
    assert temperature_modifier.to_dict()["type"] == "temperature_cardinal_rosso"
    assert ph_modifier.to_dict()["type"] == "ph_cardinal_rosso"
    assert {assumption.name for assumption in temperature_modifier.assumptions} == {
        "Rosso cardinal temperature model with inflection"
    }
    assert {assumption.name for assumption in ph_modifier.assumptions} == {"Rosso cardinal pH model"}


def test_cardinal_modifiers_wrap_a_generic_process_and_scale_its_compiled_rate() -> None:
    parameters = _parameters()
    environment = Environment(name="e", temperature=Q_(300.0, "kelvin"), ph=Q_(5.0, "dimensionless"), source="test")
    config = ProcessConfig(
        id="loss",
        process_type="first_order",
        states={"source": "A", "product": "B"},
        parameters={"rate_constant": "k_loss"},
        modifiers=[
            {
                "type": "temperature_cardinal_rosso",
                "minimum_temperature_symbol": "T_min",
                "optimum_temperature_symbol": "T_opt",
                "maximum_temperature_symbol": "T_max",
                "source": SOURCE,
            },
            {
                "type": "ph_cardinal_rosso",
                "minimum_ph_symbol": "pH_min",
                "optimum_ph_symbol": "pH_opt",
                "maximum_ph_symbol": "pH_max",
                "source": SOURCE,
            },
        ],
    )
    process = FirstOrderFactory().build(
        ProcessBuildContext(state_units={"A": "millimolar", "B": "millimolar"}, source=SOURCE), config
    )
    assert isinstance(process, RateModifierProcess)
    required = {requirement.symbol: requirement.units for requirement in process.required_parameters}
    assert {"T_min", "T_opt", "T_max"} <= set(required) and required["T_opt"] == "kelvin"
    assert {"pH_min", "pH_opt", "pH_max"} <= set(required) and required["pH_opt"] == "dimensionless"
    assert any("cardinal temperature" in limitation for limitation in process.validity.limitations)
    gamma = float(_ctmi(300.0, 280.0, 305.0, 310.0)) * (
        (5.0 - 4.0) * (5.0 - 8.0) / ((5.0 - 4.0) * (5.0 - 8.0) - (5.0 - 5.5) ** 2)
    )
    state = {"A": Q_(2.0, "millimolar"), "B": Q_(0.0, "millimolar")}
    rate = process.rate(state, Q_(0.0, "second"), parameters, environment).to("millimolar / second").magnitude
    assert rate == pytest.approx(0.1 * 2.0 * gamma)
    context = KernelContext(
        state_index={"A": 0, "B": 1},
        state_units={"A": "micromolar", "B": "micromolar"},
        time_units="minute",
        parameters=parameters,
        environment=environment,
    )
    kernel = process.compile_rate(context)
    assert kernel is not None
    assert kernel(0.0, np.array([2000.0, 0.0])) == pytest.approx(rate)
    with pytest.raises(ValueError, match="require an environment"):
        process.rate(state, Q_(0.0, "second"), parameters, None)
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("first_order_decay",),
        parameters=parameters,
        environment=environment,
        allow_unsourced_for_testing=True,
    ).assemble()
    times = np.linspace(0.0, 20.0, 11)
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state={"A": Q_(2.0, "millimolar"), "B": Q_(0.0, "millimolar")},
            t_span=(Q_(0.0, "second"), Q_(20.0, "second")),
            t_eval=Q_(times, "second"),
        )
    )
    np.testing.assert_allclose(
        result.states["A"].to("millimolar").magnitude, 2.0 * np.exp(-0.1 * gamma * times), rtol=1e-6, atol=1e-9
    )
    assert result.solver_metadata["kernel"]["process_kernels"] == {"loss": "numeric"}


def test_cardinal_modifier_configs_require_all_three_cardinal_symbols() -> None:
    with pytest.raises(ValueError, match="optimum_temperature_symbol"):
        cardinal_temperature_modifier_from_config(
            {"type": "temperature_cardinal_rosso", "minimum_temperature_symbol": "T_min", "maximum_temperature_symbol": "T_max"}
        )
    with pytest.raises(ValueError, match="maximum_ph_symbol"):
        cardinal_ph_modifier_from_config(
            {"type": "ph_cardinal_rosso", "minimum_ph_symbol": "pH_min", "optimum_ph_symbol": "pH_opt"}
        )
