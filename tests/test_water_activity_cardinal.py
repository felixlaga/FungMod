"""Rosso-Robinson cardinal water-activity law (CM_2 on water activity).

Artificial cardinal values on a non-biological first-order benchmark exercise
the shape, the shared CM_2 algebra, the compiled constant folding, the config
builder and the template role builder without any organism claim.
"""

from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.core.value_spec import ValueSpec
from fungal_model.entities import Environment
from fungal_model.io import ProcessConfig
from fungal_model.kinetics import cardinal_cm2_activity, cardinal_temperature_activity
from fungal_model.modifiers.water_activity_cardinal import (
    CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE,
    RossoRobinsonWaterActivityModifier,
    rosso_robinson_water_activity_modifier_from_config,
)
from fungal_model.processes import FirstOrderFactory, ProcessBuildContext, RateModifierProcess
from fungal_model.registry.records import EnvironmentRecord
from fungal_model.registry.store import FungModRegistry
from fungal_model.screening.template_environment_modifiers import (
    ENVIRONMENT_MODIFIER_CONDITIONS,
    build_template_environment_modifier,
    environment_response_summary,
    required_environment_conditions,
)

SOURCE = "Artificial cardinal water-activity test values; no organism claim."
AW_MIN, AW_OPT, AW_MAX = 0.80, 0.97, 1.0


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


def _parameters(**overrides: float) -> ParameterSet:
    values = {"aw_min": AW_MIN, "aw_opt": AW_OPT, "aw_max": AW_MAX}
    values.update(overrides)
    return ParameterSet(
        [
            _parameter("aw_min", values["aw_min"], "dimensionless"),
            _parameter("aw_opt", values["aw_opt"], "dimensionless"),
            _parameter("aw_max", values["aw_max"], "dimensionless"),
            _parameter("k_loss", 0.1, "1 / second"),
        ]
    )


def _cm2(x, minimum, optimum, maximum):
    x = np.asarray(x, dtype=float)
    inside = (x > minimum) & (x < maximum)
    numerator = (x - maximum) * (x - minimum) ** 2
    denominator = (optimum - minimum) * (
        (optimum - minimum) * (x - optimum) - (optimum - maximum) * (optimum + minimum - 2.0 * x)
    )
    return np.where(inside, numerator / np.where(inside, denominator, 1.0), 0.0)


def _environment(water_activity: float) -> Environment:
    return Environment(name="e", water_activity=Q_(water_activity, "dimensionless"), source="test")


def _modifier() -> RossoRobinsonWaterActivityModifier:
    return RossoRobinsonWaterActivityModifier("aw_min", "aw_opt", "aw_max", SOURCE)


def test_generic_cm2_equals_the_ctmi_module_on_one_cardinal_triple() -> None:
    temperatures = np.array([270.0, 280.0, 290.0, 300.0, 305.0, 308.0, 310.0, 320.0])
    ctmi = cardinal_temperature_activity(
        temperature=Q_(temperatures, "kelvin"),
        minimum_temperature=Q_(280.0, "kelvin"),
        optimum_temperature=Q_(305.0, "kelvin"),
        maximum_temperature=Q_(310.0, "kelvin"),
        source=SOURCE,
    )
    generic = cardinal_cm2_activity(temperatures, 280.0, 305.0, 310.0)
    np.testing.assert_allclose(generic, ctmi.magnitude, rtol=1e-14)
    scalar = cardinal_cm2_activity(300.0, 280.0, 305.0, 310.0)
    assert isinstance(scalar, float) and scalar == pytest.approx(float(ctmi.magnitude[3]))


def test_cardinal_water_activity_is_one_at_the_optimum_and_zero_at_and_beyond_the_bounds() -> None:
    parameters = _parameters()
    modifier = _modifier()
    assert modifier.activity(parameters=parameters, environment=_environment(AW_OPT)).magnitude == pytest.approx(1.0)
    for water_activity in (0.0, 0.5, AW_MIN, AW_MAX):
        assert modifier.activity(parameters=parameters, environment=_environment(water_activity)).magnitude == 0.0
    grid = np.array([0.81, 0.85, 0.90, 0.95, 0.97, 0.99])
    activity = cardinal_cm2_activity(grid, AW_MIN, AW_OPT, AW_MAX)
    np.testing.assert_allclose(activity, _cm2(grid, AW_MIN, AW_OPT, AW_MAX), rtol=1e-13)
    assert np.all((activity > 0.0) & (activity <= 1.0))
    assert np.all(np.diff(activity[:5]) > 0.0)
    for water_activity, expected in zip(grid, activity):
        assert modifier.activity(parameters=parameters, environment=_environment(float(water_activity))).magnitude == (
            pytest.approx(float(expected))
        )


def test_cardinal_water_activity_refuses_invalid_domains_and_inputs() -> None:
    modifier = _modifier()
    environment = _environment(0.9)
    with pytest.raises(ValueError, match="minimum < optimum < maximum"):
        modifier.activity(parameters=_parameters(aw_opt=0.70), environment=environment)
    with pytest.raises(ValueError, match="midpoint"):
        modifier.activity(parameters=_parameters(aw_opt=0.85), environment=environment)
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        modifier.activity(parameters=_parameters(aw_max=1.2), environment=environment)
    with pytest.raises(ValueError, match="water_activity"):
        modifier.activity(parameters=_parameters(), environment=_environment(1.05))
    with pytest.raises(ValueError):
        modifier.activity(parameters=_parameters(), environment=Environment(name="e", source="test"))
    with pytest.raises(ValueError, match="midpoint"):
        cardinal_cm2_activity(0.9, 0.8, 0.85, 1.0)
    with pytest.raises(ValueError, match="finite"):
        cardinal_cm2_activity(float("nan"), AW_MIN, AW_OPT, AW_MAX)
    with pytest.raises(ValueError, match="source"):
        RossoRobinsonWaterActivityModifier("aw_min", "aw_opt", "aw_max", "  ")
    with pytest.raises(ValueError, match="distinct"):
        RossoRobinsonWaterActivityModifier("aw_min", "aw_min", "aw_max", SOURCE)


def test_cardinal_water_activity_folds_into_a_constant_kernel_equal_to_activity() -> None:
    parameters = _parameters()
    environment = _environment(0.9)
    modifier = _modifier()
    expected = float(_cm2(0.9, AW_MIN, AW_OPT, AW_MAX))
    assert modifier.activity(parameters=parameters, environment=environment).magnitude == pytest.approx(expected)
    scaled = modifier.scale(rate=Q_(2.0, "mole / second"), parameters=parameters, environment=environment)
    assert scaled.to("mole / second").magnitude == pytest.approx(2.0 * expected)
    context = KernelContext(
        state_index={"A": 0},
        state_units={"A": "millimolar"},
        time_units="second",
        parameters=parameters,
        environment=environment,
    )
    kernel = modifier.compile_activity(context)
    assert kernel is not None
    assert kernel(0.0, np.zeros(1)) == pytest.approx(expected)
    assert kernel(5.0, np.ones(1)) == pytest.approx(expected)


def test_cardinal_water_activity_wraps_a_generic_process_with_unit_aware_and_compiled_parity() -> None:
    parameters = _parameters()
    environment = _environment(0.9)
    base = FirstOrderFactory().build(
        ProcessBuildContext(state_units={"A": "millimolar", "B": "millimolar"}, source=SOURCE),
        ProcessConfig(
            id="loss",
            process_type="first_order",
            states={"source": "A", "product": "B"},
            parameters={"rate_constant": "k_loss"},
        ),
    )
    process = RateModifierProcess(base_process=base, rate_modifiers=(_modifier(),))
    gamma = float(_cm2(0.9, AW_MIN, AW_OPT, AW_MAX))
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
    assert {assumption.name for assumption in process.assumptions} >= {"Rosso-Robinson cardinal water activity model"}


def test_cardinal_water_activity_metadata_config_builder_and_requirements() -> None:
    modifier = _modifier()
    assert modifier.condition == "water_activity"
    assert modifier.read_states == ()
    payload = modifier.to_dict()
    assert payload["type"] == CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE == "water_activity_cardinal_rosso"
    assert payload["maturity"] == "literature_backed_software_tested"
    assert "Rosso L, Robinson TP (2001)" in str(payload["law_source"])
    assert "a_w,max" in str(payload["equation"])
    assert [entry["symbol"] for entry in modifier.parameter_requirements] == ["aw_min", "aw_opt", "aw_max"]
    assert all(entry["units"] == "dimensionless" for entry in modifier.parameter_requirements)
    built = rosso_robinson_water_activity_modifier_from_config(
        {
            "type": "water_activity_cardinal_rosso",
            "minimum_water_activity_symbol": "aw_min",
            "optimum_water_activity_symbol": "aw_opt",
            "maximum_water_activity_symbol": "aw_max",
            "source": SOURCE,
        }
    )
    assert built == modifier
    with pytest.raises(ValueError, match="maximum_water_activity_symbol"):
        rosso_robinson_water_activity_modifier_from_config(
            {
                "type": "water_activity_cardinal_rosso",
                "minimum_water_activity_symbol": "aw_min",
                "optimum_water_activity_symbol": "aw_opt",
            }
        )


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
                    "water_activity": ValueSpec(
                        kind="exact",
                        value=0.9,
                        units="dimensionless",
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


def test_template_builder_emits_the_cardinal_water_activity_dict_and_refuses_a_missing_role() -> None:
    assert ENVIRONMENT_MODIFIER_CONDITIONS["water_activity_cardinal_rosso"] == "water_activity"
    registry = _registry("env_fixture")
    roles = {
        "growth_minimum_water_activity": "aw_min",
        "growth_optimum_water_activity": "aw_opt",
        "growth_maximum_water_activity": "aw_max",
    }
    modifier = {
        "type": "water_activity_cardinal_rosso",
        "minimum_water_activity_role": "growth_minimum_water_activity",
        "optimum_water_activity_role": "growth_optimum_water_activity",
        "maximum_water_activity_role": "growth_maximum_water_activity",
        "source": SOURCE,
    }
    common = {
        "template_id": "tmpl",
        "parameter_symbols": roles,
        "registry": registry,
        "environment_id": "env_fixture",
        "modifier_type": "water_activity_cardinal_rosso",
        "index": 0,
        "modifier_label": "Template modifier",
        "unresolved_label": "Template tmpl",
        "error_type": ValueError,
    }
    configured = build_template_environment_modifier(modifier=modifier, **common)
    assert configured == {
        "type": "water_activity_cardinal_rosso",
        "minimum_water_activity_symbol": "aw_min",
        "optimum_water_activity_symbol": "aw_opt",
        "maximum_water_activity_symbol": "aw_max",
        "source": SOURCE,
    }
    assert rosso_robinson_water_activity_modifier_from_config(configured) == _modifier()
    missing = {key: value for key, value in modifier.items() if key != "maximum_water_activity_role"}
    with pytest.raises(ValueError, match="maximum_water_activity_role"):
        build_template_environment_modifier(modifier=missing, **common)
    unresolved = {**modifier, "optimum_water_activity_role": "no_such_role"}
    with pytest.raises(ValueError, match="unresolved optimum_water_activity_role"):
        build_template_environment_modifier(modifier=unresolved, **common)
    assert required_environment_conditions([configured]) == ("water_activity",)
    summary = environment_response_summary([{"id": "loss", "process_type": "first_order", "modifiers": [configured]}])
    assert summary["status"] == "active_response_model"
    assert summary["conditions"]["water_activity"]["laws"] == [
        {"process_id": "loss", "law": "water_activity_cardinal_rosso", "binding": "modifier"}
    ]
