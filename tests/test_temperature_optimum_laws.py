"""Enzyme temperature laws with an optimum: Sharpe-Schoolfield and the Equilibrium Model.

Artificial thermodynamic values on a non-biological first-order benchmark
exercise the closed forms, the normalisation at the reference temperature,
the monotone decline above the half-inactivation temperature, the compiled
constant folding, the config builders and the template role builders. No
enzyme claim is made.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.core.value_spec import ValueSpec
from fungal_model.entities import Environment
from fungal_model.io import ProcessConfig
from fungal_model.kinetics import (
    UNIVERSAL_GAS_CONSTANT,
    EnvironmentalValidityWarning,
    equilibrium_model_active_fraction,
    equilibrium_model_activity,
    sharpe_schoolfield_activity,
)
from fungal_model.modifiers.temperature_optimum import (
    EquilibriumModelModifier,
    SharpeSchoolfieldModifier,
    equilibrium_model_modifier_from_config,
    sharpe_schoolfield_modifier_from_config,
)
from fungal_model.processes import FirstOrderFactory, ProcessBuildContext, RateModifierProcess
from fungal_model.registry.records import EnvironmentRecord
from fungal_model.registry.store import FungModRegistry
from fungal_model.screening.template_environment_modifiers import (
    ENVIRONMENT_MODIFIER_CONDITIONS,
    build_template_environment_modifier,
)

SOURCE = "Artificial temperature-optimum test values; no enzyme claim."
R = UNIVERSAL_GAS_CONSTANT.value
E_A, T_REF = 50_000.0, 298.15
DH_H, T_H = 300_000.0, 320.0
DH_L, T_L = 200_000.0, 280.0
DH_EQ, T_EQ = 150_000.0, 315.0
T_LOW_BOUND, T_HIGH_BOUND = 290.0, 330.0


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
            _parameter("E_a", E_A, "joule / mole"),
            _parameter("T_ref", T_REF, "kelvin"),
            _parameter("dH_H", DH_H, "joule / mole"),
            _parameter("T_H", T_H, "kelvin"),
            _parameter("dH_L", DH_L, "joule / mole"),
            _parameter("T_L", T_L, "kelvin"),
            _parameter("dH_eq", DH_EQ, "joule / mole"),
            _parameter("T_eq", T_EQ, "kelvin"),
            _parameter("T_lo", T_LOW_BOUND, "kelvin"),
            _parameter("T_hi", T_HIGH_BOUND, "kelvin"),
            _parameter("k_loss", 0.1, "1 / second"),
        ]
    )


def _schoolfield(temperature, *, low: bool):
    temperature = np.asarray(temperature, dtype=float)

    def inactivation(t):
        total = 1.0 + np.exp((DH_H / R) * (1.0 / T_H - 1.0 / t))
        if low:
            total = total + np.exp((DH_L / R) * (1.0 / t - 1.0 / T_L))
        return total

    return np.exp(-(E_A / R) * (1.0 / temperature - 1.0 / T_REF)) * inactivation(T_REF) / inactivation(temperature)


def _fraction(temperature):
    temperature = np.asarray(temperature, dtype=float)
    return 1.0 / (1.0 + np.exp((DH_EQ / R) * (1.0 / T_EQ - 1.0 / temperature)))


def _sharpe(temperature, **extra):
    return sharpe_schoolfield_activity(
        temperature=temperature,
        activation_energy=Q_(E_A, "joule / mole"),
        reference_temperature=Q_(T_REF, "kelvin"),
        high_inactivation_enthalpy=Q_(DH_H, "joule / mole"),
        high_half_inactivation_temperature=Q_(T_H, "kelvin"),
        source=SOURCE,
        **extra,
    )


def _environment(temperature: float, units: str = "kelvin") -> Environment:
    return Environment(name="e", temperature=Q_(temperature, units), source="test")


def test_sharpe_schoolfield_is_one_at_reference_decreases_above_t_h_and_matches_the_closed_form() -> None:
    assert _sharpe(Q_(T_REF, "kelvin")).magnitude == pytest.approx(1.0, abs=1e-14)
    above = np.linspace(T_H, 360.0, 25)
    activity_above = _sharpe(Q_(above, "kelvin")).magnitude
    assert np.all(np.diff(activity_above) < 0.0)
    grid = np.linspace(270.0, 360.0, 46)
    np.testing.assert_allclose(_sharpe(Q_(grid, "kelvin")).magnitude, _schoolfield(grid, low=False), rtol=1e-12)
    with_low = _sharpe(
        Q_(grid, "kelvin"),
        low_inactivation_enthalpy=Q_(DH_L, "joule / mole"),
        low_half_inactivation_temperature=Q_(T_L, "kelvin"),
    ).magnitude
    np.testing.assert_allclose(with_low, _schoolfield(grid, low=True), rtol=1e-12)
    assert np.all(with_low[grid < T_REF] < _schoolfield(grid[grid < T_REF], low=False))
    assert with_low.shape == grid.shape
    optimum_index = int(np.argmax(with_low))
    assert 0 < optimum_index < grid.size - 1
    kelvin = _sharpe(Q_(310.0, "kelvin")).magnitude
    celsius = _sharpe(Q_(36.85, "degree_Celsius")).magnitude
    assert celsius == pytest.approx(kelvin, rel=1e-12)
    kilojoule = sharpe_schoolfield_activity(
        temperature=Q_(310.0, "kelvin"),
        activation_energy=Q_(E_A / 1000.0, "kilojoule / mole"),
        reference_temperature=Q_(T_REF, "kelvin"),
        high_inactivation_enthalpy=Q_(DH_H / 1000.0, "kilojoule / mole"),
        high_half_inactivation_temperature=Q_(T_H, "kelvin"),
        source=SOURCE,
    ).magnitude
    assert kilojoule == pytest.approx(kelvin, rel=1e-12)
    assert _sharpe(Q_(1000.0, "kelvin")).magnitude == pytest.approx(0.0, abs=1e-12)


def test_sharpe_schoolfield_refuses_half_low_pairs_blank_sources_and_bad_energies() -> None:
    with pytest.raises(ValueError, match="or neither"):
        _sharpe(Q_(300.0, "kelvin"), low_inactivation_enthalpy=Q_(DH_L, "joule / mole"))
    with pytest.raises(ValueError, match="source"):
        sharpe_schoolfield_activity(
            temperature=Q_(300.0, "kelvin"),
            activation_energy=Q_(E_A, "joule / mole"),
            reference_temperature=Q_(T_REF, "kelvin"),
            high_inactivation_enthalpy=Q_(DH_H, "joule / mole"),
            high_half_inactivation_temperature=Q_(T_H, "kelvin"),
            source="  ",
        )
    with pytest.raises(ValueError, match="activation_energy must be non-negative"):
        sharpe_schoolfield_activity(
            temperature=Q_(300.0, "kelvin"),
            activation_energy=Q_(-1.0, "joule / mole"),
            reference_temperature=Q_(T_REF, "kelvin"),
            high_inactivation_enthalpy=Q_(DH_H, "joule / mole"),
            high_half_inactivation_temperature=Q_(T_H, "kelvin"),
            source=SOURCE,
        )
    with pytest.raises(ValueError, match="high_inactivation_enthalpy must be positive"):
        sharpe_schoolfield_activity(
            temperature=Q_(300.0, "kelvin"),
            activation_energy=Q_(E_A, "joule / mole"),
            reference_temperature=Q_(T_REF, "kelvin"),
            high_inactivation_enthalpy=Q_(0.0, "joule / mole"),
            high_half_inactivation_temperature=Q_(T_H, "kelvin"),
            source=SOURCE,
        )
    with pytest.raises(ValueError, match="positive in kelvin"):
        _sharpe(Q_(-5.0, "kelvin"))


def test_equilibrium_model_fraction_is_half_at_t_eq_monotone_and_the_activity_is_normalised() -> None:
    fraction = equilibrium_model_active_fraction(
        temperature=Q_(T_EQ, "kelvin"),
        equilibrium_enthalpy=Q_(DH_EQ, "joule / mole"),
        equilibrium_temperature=Q_(T_EQ, "kelvin"),
        source=SOURCE,
    )
    assert fraction.magnitude == pytest.approx(0.5, abs=1e-14)
    grid = np.linspace(270.0, 360.0, 46)
    fractions = equilibrium_model_active_fraction(
        temperature=Q_(grid, "kelvin"),
        equilibrium_enthalpy=Q_(DH_EQ, "joule / mole"),
        equilibrium_temperature=Q_(T_EQ, "kelvin"),
        source=SOURCE,
    ).magnitude
    np.testing.assert_allclose(fractions, _fraction(grid), rtol=1e-12)
    assert np.all(np.diff(fractions) < 0.0) and np.all((fractions > 0.0) & (fractions < 1.0))
    celsius = equilibrium_model_active_fraction(
        temperature=Q_(T_EQ - 273.15, "degree_Celsius"),
        equilibrium_enthalpy=Q_(DH_EQ, "joule / mole"),
        equilibrium_temperature=Q_(T_EQ, "kelvin"),
        source=SOURCE,
    )
    assert celsius.magnitude == pytest.approx(0.5, abs=1e-12)

    def activity(temperature):
        return equilibrium_model_activity(
            temperature=temperature,
            activation_energy=Q_(E_A, "joule / mole"),
            reference_temperature=Q_(T_REF, "kelvin"),
            equilibrium_enthalpy=Q_(DH_EQ, "joule / mole"),
            equilibrium_temperature=Q_(T_EQ, "kelvin"),
            source=SOURCE,
        ).magnitude

    assert activity(Q_(T_REF, "kelvin")) == pytest.approx(1.0, abs=1e-14)
    expected = np.exp(-(E_A / R) * (1.0 / grid - 1.0 / T_REF)) * _fraction(grid) / _fraction(T_REF)
    np.testing.assert_allclose(activity(Q_(grid, "kelvin")), expected, rtol=1e-12)
    same_as_high_only_schoolfield = sharpe_schoolfield_activity(
        temperature=Q_(grid, "kelvin"),
        activation_energy=Q_(E_A, "joule / mole"),
        reference_temperature=Q_(T_REF, "kelvin"),
        high_inactivation_enthalpy=Q_(DH_EQ, "joule / mole"),
        high_half_inactivation_temperature=Q_(T_EQ, "kelvin"),
        source=SOURCE,
    ).magnitude
    np.testing.assert_allclose(activity(Q_(grid, "kelvin")), same_as_high_only_schoolfield, rtol=1e-12)
    with pytest.raises(ValueError, match="equilibrium_enthalpy must be positive"):
        equilibrium_model_active_fraction(
            temperature=Q_(300.0, "kelvin"),
            equilibrium_enthalpy=Q_(-DH_EQ, "joule / mole"),
            equilibrium_temperature=Q_(T_EQ, "kelvin"),
            source=SOURCE,
        )


def _sharpe_modifier(**overrides) -> SharpeSchoolfieldModifier:
    fields = {
        "activation_energy_symbol": "E_a",
        "reference_temperature_symbol": "T_ref",
        "high_inactivation_enthalpy_symbol": "dH_H",
        "high_half_inactivation_temperature_symbol": "T_H",
        "source": SOURCE,
    }
    fields.update(overrides)
    return SharpeSchoolfieldModifier(**fields)


def _equilibrium_modifier(**overrides) -> EquilibriumModelModifier:
    fields = {
        "activation_energy_symbol": "E_a",
        "reference_temperature_symbol": "T_ref",
        "equilibrium_enthalpy_symbol": "dH_eq",
        "equilibrium_temperature_symbol": "T_eq",
        "source": SOURCE,
    }
    fields.update(overrides)
    return EquilibriumModelModifier(**fields)


def test_temperature_optimum_modifiers_fold_into_constants_equal_to_activity() -> None:
    parameters = _parameters()
    environment = _environment(36.85, "degree_Celsius")
    context = KernelContext(
        state_index={"A": 0},
        state_units={"A": "millimolar"},
        time_units="second",
        parameters=parameters,
        environment=environment,
    )
    full = _sharpe_modifier(low_inactivation_enthalpy_symbol="dH_L", low_half_inactivation_temperature_symbol="T_L")
    cases = [
        (_sharpe_modifier(), float(_schoolfield(310.0, low=False))),
        (full, float(_schoolfield(310.0, low=True))),
        (
            _equilibrium_modifier(),
            float(np.exp(-(E_A / R) * (1.0 / 310.0 - 1.0 / T_REF)) * _fraction(310.0) / _fraction(T_REF)),
        ),
    ]
    for modifier, expected in cases:
        activity = modifier.activity(parameters=parameters, environment=environment).magnitude
        assert activity == pytest.approx(expected, rel=1e-12)
        kernel = modifier.compile_activity(context)
        assert kernel is not None
        assert kernel(0.0, np.zeros(1)) == pytest.approx(activity, rel=1e-14)
        assert kernel(7.0, np.ones(1)) == pytest.approx(activity, rel=1e-14)
        scaled = modifier.scale(rate=Q_(3.0, "mole / second"), parameters=parameters, environment=environment)
        assert scaled.to("mole / second").magnitude == pytest.approx(3.0 * expected, rel=1e-12)
        assert modifier.condition == "temperature" and modifier.read_states == ()
        payload = modifier.to_dict()
        assert payload["maturity"] == "literature_backed_software_tested"
        assert payload["condition"] == "temperature"
    assert full.has_low_temperature_term and not _sharpe_modifier().has_low_temperature_term
    assert [entry["symbol"] for entry in full.parameter_requirements] == ["E_a", "T_ref", "dH_H", "T_H", "dH_L", "T_L"]
    assert [entry["symbol"] for entry in _equilibrium_modifier().parameter_requirements] == ["E_a", "T_ref", "dH_eq", "T_eq"]
    assert _sharpe_modifier().to_dict()["type"] == "temperature_sharpe_schoolfield"
    assert _equilibrium_modifier().to_dict()["type"] == "temperature_equilibrium_model"
    assert "Schoolfield RM" in str(_sharpe_modifier().to_dict()["law_source"])
    assert "Peterson ME" in str(_equilibrium_modifier().to_dict()["law_source"])
    assert {assumption.name for assumption in full.assumptions} == {
        "Sharpe-Schoolfield temperature response with reversible inactivation"
    }
    assert {assumption.name for assumption in _equilibrium_modifier().assumptions} == {
        "Equilibrium Model reversible active-inactive enzyme transition"
    }


def test_temperature_optimum_modifiers_warn_outside_declared_measured_bounds_only() -> None:
    parameters = _parameters()
    bounded = [
        _sharpe_modifier(minimum_temperature_symbol="T_lo", maximum_temperature_symbol="T_hi"),
        _equilibrium_modifier(minimum_temperature_symbol="T_lo", maximum_temperature_symbol="T_hi"),
    ]
    for modifier in bounded:
        with pytest.warns(EnvironmentalValidityWarning, match="above 330.0 K"):
            modifier.activity(parameters=parameters, environment=_environment(340.0))
        with pytest.warns(EnvironmentalValidityWarning, match="below 290.0 K"):
            modifier.activity(parameters=parameters, environment=_environment(280.0))
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            modifier.activity(parameters=parameters, environment=_environment(300.0))
    for modifier in (_sharpe_modifier(), _equilibrium_modifier()):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            modifier.activity(parameters=parameters, environment=_environment(340.0))


def test_temperature_optimum_modifier_constructors_and_config_builders_refuse_incomplete_fields() -> None:
    with pytest.raises(ValueError, match="or neither"):
        _sharpe_modifier(low_inactivation_enthalpy_symbol="dH_L")
    with pytest.raises(ValueError, match="distinct"):
        _sharpe_modifier(high_half_inactivation_temperature_symbol="T_ref")
    with pytest.raises(ValueError, match="source"):
        _equilibrium_modifier(source="")
    base = {
        "type": "temperature_sharpe_schoolfield",
        "activation_energy_symbol": "E_a",
        "reference_temperature_symbol": "T_ref",
        "high_inactivation_enthalpy_symbol": "dH_H",
        "high_half_inactivation_temperature_symbol": "T_H",
        "source": SOURCE,
    }
    assert sharpe_schoolfield_modifier_from_config(base) == _sharpe_modifier()
    assert sharpe_schoolfield_modifier_from_config(
        {**base, "low_inactivation_enthalpy_symbol": "dH_L", "low_half_inactivation_temperature_symbol": "T_L"}
    ) == _sharpe_modifier(low_inactivation_enthalpy_symbol="dH_L", low_half_inactivation_temperature_symbol="T_L")
    with pytest.raises(ValueError, match="high_half_inactivation_temperature_symbol"):
        sharpe_schoolfield_modifier_from_config(
            {key: value for key, value in base.items() if key != "high_half_inactivation_temperature_symbol"}
        )
    with pytest.raises(ValueError, match="or neither"):
        sharpe_schoolfield_modifier_from_config({**base, "low_inactivation_enthalpy_symbol": "dH_L"})
    equilibrium = {
        "type": "temperature_equilibrium_model",
        "activation_energy_symbol": "E_a",
        "reference_temperature_symbol": "T_ref",
        "equilibrium_enthalpy_symbol": "dH_eq",
        "equilibrium_temperature_symbol": "T_eq",
        "source": SOURCE,
    }
    assert equilibrium_model_modifier_from_config(equilibrium) == _equilibrium_modifier()
    with pytest.raises(ValueError, match="equilibrium_temperature_symbol"):
        equilibrium_model_modifier_from_config(
            {key: value for key, value in equilibrium.items() if key != "equilibrium_temperature_symbol"}
        )


def test_temperature_optimum_modifiers_wrap_a_generic_process_with_compiled_parity() -> None:
    parameters = _parameters()
    environment = _environment(310.0)
    base = FirstOrderFactory().build(
        ProcessBuildContext(state_units={"A": "millimolar", "B": "millimolar"}, source=SOURCE),
        ProcessConfig(
            id="loss",
            process_type="first_order",
            states={"source": "A", "product": "B"},
            parameters={"rate_constant": "k_loss"},
        ),
    )
    for modifier, gamma in (
        (_sharpe_modifier(), float(_schoolfield(310.0, low=False))),
        (
            _equilibrium_modifier(),
            float(np.exp(-(E_A / R) * (1.0 / 310.0 - 1.0 / T_REF)) * _fraction(310.0) / _fraction(T_REF)),
        ),
    ):
        process = RateModifierProcess(base_process=base, rate_modifiers=(modifier,))
        state = {"A": Q_(2.0, "millimolar"), "B": Q_(0.0, "millimolar")}
        rate = process.rate(state, Q_(0.0, "second"), parameters, environment).to("millimolar / second").magnitude
        assert rate == pytest.approx(0.1 * 2.0 * gamma, rel=1e-12)
        context = KernelContext(
            state_index={"A": 0, "B": 1},
            state_units={"A": "micromolar", "B": "micromolar"},
            time_units="minute",
            parameters=parameters,
            environment=environment,
        )
        kernel = process.compile_rate(context)
        assert kernel is not None
        assert kernel(0.0, np.array([2000.0, 0.0])) == pytest.approx(rate, rel=1e-12)


def _registry(environment_id: str) -> FungModRegistry:
    provenance = {
        "source": "WP5 software test fixture.",
        "confidence_level": "testing",
        "notes": "Artificial metadata for template-builder verification only; not scientific data.",
    }
    return FungModRegistry.build(
        registry_id="wp5_fixture_registry",
        version="1.0.0",
        maturity="software_test_fixture",
        provenance=provenance,
        fungi=(),
        enzyme_classes=(),
        substrates=(),
        environments=(
            EnvironmentRecord(
                record_id=environment_id,
                name="Fixture environment",
                maturity="software_test_fixture",
                provenance=provenance,
                notes="Artificial environment fixture; not empirical data.",
                conditions={
                    "temperature": ValueSpec(
                        kind="exact",
                        value=310.0,
                        units="kelvin",
                        source="WP5 software test fixture.",
                        confidence_level="testing",
                        notes="Artificial condition; not empirical data.",
                    )
                },
            ),
        ),
        process_compatibility=(),
        parameters=(),
    )


def test_template_builder_emits_both_temperature_optimum_dicts_and_refuses_missing_or_half_roles() -> None:
    assert ENVIRONMENT_MODIFIER_CONDITIONS["temperature_sharpe_schoolfield"] == "temperature"
    assert ENVIRONMENT_MODIFIER_CONDITIONS["temperature_equilibrium_model"] == "temperature"
    registry = _registry("env_fixture")
    roles = {
        "activation_energy": "E_a",
        "reference_temperature": "T_ref",
        "high_enthalpy": "dH_H",
        "high_temperature": "T_H",
        "low_enthalpy": "dH_L",
        "low_temperature": "T_L",
        "equilibrium_enthalpy": "dH_eq",
        "equilibrium_temperature": "T_eq",
        "lower_bound": "T_lo",
    }
    common = {
        "template_id": "tmpl",
        "parameter_symbols": roles,
        "registry": registry,
        "environment_id": "env_fixture",
        "index": 0,
        "modifier_label": "Template modifier",
        "unresolved_label": "Template tmpl",
        "error_type": ValueError,
    }
    sharpe = {
        "type": "temperature_sharpe_schoolfield",
        "activation_energy_role": "activation_energy",
        "reference_temperature_role": "reference_temperature",
        "high_inactivation_enthalpy_role": "high_enthalpy",
        "high_half_inactivation_temperature_role": "high_temperature",
        "low_inactivation_enthalpy_role": "low_enthalpy",
        "low_half_inactivation_temperature_role": "low_temperature",
        "minimum_temperature_role": "lower_bound",
    }
    configured = build_template_environment_modifier(
        modifier=sharpe, modifier_type="temperature_sharpe_schoolfield", **common
    )
    assert configured == {
        "type": "temperature_sharpe_schoolfield",
        "activation_energy_symbol": "E_a",
        "reference_temperature_symbol": "T_ref",
        "high_inactivation_enthalpy_symbol": "dH_H",
        "high_half_inactivation_temperature_symbol": "T_H",
        "low_inactivation_enthalpy_symbol": "dH_L",
        "low_half_inactivation_temperature_symbol": "T_L",
        "minimum_temperature_symbol": "T_lo",
    }
    built = sharpe_schoolfield_modifier_from_config(configured)
    assert built.has_low_temperature_term and built.minimum_temperature_symbol == "T_lo"
    with pytest.raises(ValueError, match="or neither"):
        build_template_environment_modifier(
            modifier={key: value for key, value in sharpe.items() if key != "low_half_inactivation_temperature_role"},
            modifier_type="temperature_sharpe_schoolfield",
            **common,
        )
    with pytest.raises(ValueError, match="high_inactivation_enthalpy_role"):
        build_template_environment_modifier(
            modifier={key: value for key, value in sharpe.items() if key != "high_inactivation_enthalpy_role"},
            modifier_type="temperature_sharpe_schoolfield",
            **common,
        )
    equilibrium = {
        "type": "temperature_equilibrium_model",
        "activation_energy_role": "activation_energy",
        "reference_temperature_role": "reference_temperature",
        "equilibrium_enthalpy_role": "equilibrium_enthalpy",
        "equilibrium_temperature_role": "equilibrium_temperature",
        "source": SOURCE,
    }
    configured = build_template_environment_modifier(
        modifier=equilibrium, modifier_type="temperature_equilibrium_model", **common
    )
    assert configured == {
        "type": "temperature_equilibrium_model",
        "activation_energy_symbol": "E_a",
        "reference_temperature_symbol": "T_ref",
        "equilibrium_enthalpy_symbol": "dH_eq",
        "equilibrium_temperature_symbol": "T_eq",
        "source": SOURCE,
    }
    assert equilibrium_model_modifier_from_config(configured) == _equilibrium_modifier()
    with pytest.raises(ValueError, match="unresolved equilibrium_temperature_role"):
        build_template_environment_modifier(
            modifier={**equilibrium, "equilibrium_temperature_role": "no_such_role"},
            modifier_type="temperature_equilibrium_model",
            **common,
        )
