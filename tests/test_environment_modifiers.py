from __future__ import annotations

import pytest

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, UnitError
from fungal_model.entities import Environment
from fungal_model.kinetics.arrhenius import EnvironmentalValidityWarning
from fungal_model.modifiers import (
    OxygenModifier,
    PHModifier,
    ProductInhibitionModifier,
    TemperatureModifier,
    WaterActivityModifier,
)


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
        uncertainty=0.0,
        source="Artificial environment-modifier benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only to test environment-driven modifiers.",
        measurement_method="defined benchmark value",
    )


def parameters() -> ParameterSet:
    return ParameterSet(
        [
            parameter(name="activation energy", symbol="Ea", value=40.0, units="kilojoule / mole"),
            parameter(name="reference temperature", symbol="T_ref", value=300.0, units="kelvin"),
            parameter(name="minimum measured temperature", symbol="T_min", value=290.0, units="kelvin"),
            parameter(name="maximum measured temperature", symbol="T_max", value=310.0, units="kelvin"),
            parameter(name="optimum pH", symbol="pH_opt", value=7.0, units="dimensionless"),
            parameter(name="pH width", symbol="pH_sigma", value=1.0, units="dimensionless"),
            parameter(name="minimum pH", symbol="pH_min", value=5.0, units="dimensionless"),
            parameter(name="maximum pH", symbol="pH_max", value=9.0, units="dimensionless"),
            parameter(name="minimum water activity", symbol="a_w_min", value=0.9, units="dimensionless"),
            parameter(name="oxygen half saturation", symbol="K_O2", value=0.2, units="mole / liter"),
            parameter(name="product inhibition constant", symbol="K_i_product", value=2.0, units="mole / liter"),
        ]
    )


def test_environment_requires_source_and_checks_units() -> None:
    env = Environment(
        name="lab",
        temperature=Q_(300.0, "kelvin"),
        ph=Q_(7.0, "dimensionless"),
        water_activity=Q_(0.95, "dimensionless"),
        oxygen_concentration=Q_(0.2, "mole / liter"),
        source="Artificial lab environment.",
    )

    env.validate()
    with pytest.raises(ProvenanceError):
        Environment(name="unsourced", temperature=Q_(300.0, "kelvin")).validate()
    with pytest.raises(UnitError):
        Environment(name="bad pH", ph=Q_(7.0, "meter"), source="bad").validate()


def test_temperature_modifier_reads_environment_and_warns_outside_range() -> None:
    modifier = TemperatureModifier(
        activation_energy_symbol="Ea",
        reference_temperature_symbol="T_ref",
        minimum_temperature_symbol="T_min",
        maximum_temperature_symbol="T_max",
        source="Artificial temperature range.",
    )
    reference_env = Environment(name="reference", temperature=Q_(300.0, "kelvin"), source="test")
    warm_env = Environment(name="warm", temperature=Q_(305.0, "kelvin"), source="test")
    hot_env = Environment(name="hot", temperature=Q_(330.0, "kelvin"), source="test")

    assert modifier.activity(parameters=parameters(), environment=reference_env).magnitude == pytest.approx(1.0)
    assert modifier.scale(rate=Q_(1.0, "mole / second"), parameters=parameters(), environment=warm_env).magnitude > 1.0
    with pytest.warns(EnvironmentalValidityWarning):
        modifier.activity(parameters=parameters(), environment=hot_env)


def test_ph_modifier_reads_environment() -> None:
    modifier = PHModifier(
        optimum_symbol="pH_opt",
        width_symbol="pH_sigma",
        minimum_ph_symbol="pH_min",
        maximum_ph_symbol="pH_max",
        source="Artificial pH range.",
    )
    optimum = Environment(name="optimum", ph=Q_(7.0, "dimensionless"), source="test")
    acidic = Environment(name="acidic", ph=Q_(5.0, "dimensionless"), source="test")

    assert modifier.activity(parameters=parameters(), environment=optimum).magnitude == pytest.approx(1.0)
    assert modifier.activity(parameters=parameters(), environment=acidic).magnitude < 1.0


def test_water_activity_modifier_blocks_below_threshold() -> None:
    modifier = WaterActivityModifier(minimum_water_activity_symbol="a_w_min")
    wet = Environment(name="wet", water_activity=Q_(0.95, "dimensionless"), source="test")
    dry = Environment(name="dry", water_activity=Q_(0.8, "dimensionless"), source="test")

    assert modifier.scale(rate=Q_(2.0, "kilogram / second"), parameters=parameters(), environment=wet).magnitude == pytest.approx(2.0)
    assert modifier.scale(rate=Q_(2.0, "kilogram / second"), parameters=parameters(), environment=dry).magnitude == pytest.approx(0.0)


def test_oxygen_modifier_decreases_rate_when_oxygen_is_low() -> None:
    modifier = OxygenModifier(half_saturation_symbol="K_O2", oxygen_units="mole / liter")
    low = Environment(name="low oxygen", oxygen_concentration=Q_(0.02, "mole / liter"), source="test")
    high = Environment(name="high oxygen", oxygen_concentration=Q_(2.0, "mole / liter"), source="test")

    low_rate = modifier.scale(rate=Q_(1.0, "kilogram / second"), parameters=parameters(), environment=low)
    high_rate = modifier.scale(rate=Q_(1.0, "kilogram / second"), parameters=parameters(), environment=high)

    assert low_rate.magnitude < high_rate.magnitude < 1.0


def test_product_inhibition_modifier_requires_state_and_reduces_rate() -> None:
    modifier = ProductInhibitionModifier(
        product_state="P",
        inhibition_constant_symbol="K_i_product",
        product_units="mole / liter",
    )
    env = Environment(name="lab", source="test")

    uninhibited = modifier.scale(
        rate=Q_(1.0, "mole / second"),
        parameters=parameters(),
        environment=env,
        state={"P": Q_(0.0, "mole / liter")},
    )
    inhibited = modifier.scale(
        rate=Q_(1.0, "mole / second"),
        parameters=parameters(),
        environment=env,
        state={"P": Q_(2.0, "mole / liter")},
    )

    assert uninhibited.magnitude == pytest.approx(1.0)
    assert inhibited.magnitude == pytest.approx(0.5)
    with pytest.raises(ValueError):
        modifier.activity(parameters=parameters(), environment=env, state={})
