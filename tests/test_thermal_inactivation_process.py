"""Generic first-order thermal inactivation with an Arrhenius-scaled rate constant."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Environment
from fungal_model.io import ProcessConfig
from fungal_model.kinetics import UNIVERSAL_GAS_CONSTANT, EnvironmentalValidityWarning
from fungal_model.processes import (
    ModelBuilder,
    ProcessBuildContext,
    ProcessLibrary,
    ProcessRegistry,
    ThermalInactivationFactory,
    ThermalInactivationProcess,
)
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
TOY_CONFIG = ROOT / "data" / "model_configs" / "toy_thermal_inactivation_dissolved.yml"
SOURCE = "Artificial inactivation test values; no enzyme claim."
GAS_CONSTANT = float(UNIVERSAL_GAS_CONSTANT.value)


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


def _parameters(**extra: Parameter) -> ParameterSet:
    base = [
        _parameter("k_d_ref", 0.002, "1 / hour"),
        _parameter("E_d", 150.0, "kilojoule / mole"),
        _parameter("T_ref", 302.15, "kelvin"),
    ]
    return ParameterSet([*base, *extra.values()])


def _process(**overrides) -> ThermalInactivationProcess:
    fields = {
        "name": "inactivation",
        "active_state": "A",
        "inactive_state": "D",
        "state_units": "filter_paper_unit / liter",
        "rate_units": "filter_paper_unit / liter / hour",
        "reference_rate_constant_symbol": "k_d_ref",
        "inactivation_energy_symbol": "E_d",
        "reference_temperature_symbol": "T_ref",
        "source": SOURCE,
    }
    fields.update(overrides)
    return ThermalInactivationProcess(**fields)


def _rate_constant(temperature: float) -> float:
    return 0.002 * np.exp(-150000.0 / GAS_CONSTANT * (1.0 / temperature - 1.0 / 302.15))


def _state(active: float, inactive: float = 0.0):
    return {"A": Q_(active, "filter_paper_unit / liter"), "D": Q_(inactive, "filter_paper_unit / liter")}


def test_rate_constant_follows_the_arrhenius_reference_form() -> None:
    process = _process()
    parameters = _parameters()
    at_reference = Environment(name="ref", temperature=Q_(302.15, "kelvin"), source="test")
    warmer = Environment(name="warm", temperature=Q_(39.0, "degree_Celsius"), source="test")
    assert process.rate_constant(parameters=parameters, environment=at_reference).to("1 / hour").magnitude == pytest.approx(
        0.002
    )
    expected = _rate_constant(312.15)
    assert process.rate_constant(parameters=parameters, environment=warmer).to("1 / hour").magnitude == pytest.approx(expected)
    rate = process.rate(_state(10.0), Q_(0.0, "hour"), parameters, warmer)
    assert rate.to("filter_paper_unit / liter / hour").magnitude == pytest.approx(10.0 * expected)
    contributions = process.contributions(rate)
    assert contributions["A"].magnitude == pytest.approx(-rate.magnitude)
    assert contributions["D"].magnitude == pytest.approx(rate.magnitude)
    assert {assumption.name for assumption in process.assumptions} == {
        "first-order thermal inactivation with Arrhenius rate constant"
    }


def test_environment_temperature_is_required_and_invalid_inputs_fail_closed() -> None:
    process = _process()
    parameters = _parameters()
    environment = Environment(name="e", temperature=Q_(302.15, "kelvin"), source="test")
    with pytest.raises(ValueError, match="environment entity with temperature"):
        process.rate(_state(1.0), Q_(0.0, "hour"), parameters, None)
    with pytest.raises(ValueError, match="does not define temperature"):
        process.rate(_state(1.0), Q_(0.0, "hour"), parameters, Environment(name="no T", ph=Q_(5.0, "dimensionless"), source="t"))
    with pytest.raises(ValueError, match="must be non-negative"):
        process.rate(_state(-1.0), Q_(0.0, "hour"), parameters, environment)
    negative_constant = ParameterSet(
        [_parameter("k_d_ref", -0.002, "1 / hour"), _parameter("E_d", 150.0, "kilojoule / mole"), _parameter("T_ref", 302.15, "kelvin")]
    )
    with pytest.raises(ValueError, match="must be non-negative"):
        process.rate(_state(1.0), Q_(0.0, "hour"), negative_constant, environment)
    with pytest.raises(ValueError, match="distinct"):
        _process(inactive_state="A")
    with pytest.raises(ValueError, match="together"):
        _process(minimum_temperature_symbol="T_lo")


def test_measured_temperature_bounds_warn_outside_the_source_range() -> None:
    process = _process(minimum_temperature_symbol="T_lo", maximum_temperature_symbol="T_hi")
    parameters = _parameters(lo=_parameter("T_lo", 298.15, "kelvin"), hi=_parameter("T_hi", 308.15, "kelvin"))
    assert {"T_lo", "T_hi"} <= {requirement.symbol for requirement in process.required_parameters}
    with pytest.warns(EnvironmentalValidityWarning):
        process.rate(_state(1.0), Q_(0.0, "hour"), parameters, Environment(name="hot", temperature=Q_(320.0, "kelvin"), source="t"))


def test_compiled_kernel_matches_the_unit_aware_law_across_mixed_units() -> None:
    process = _process()
    parameters = _parameters()
    environment = Environment(name="warm", temperature=Q_(310.0, "kelvin"), source="test")
    context = KernelContext(
        state_index={"A": 0, "D": 1},
        state_units={"A": "filter_paper_unit / milliliter", "D": "filter_paper_unit / liter"},
        time_units="minute",
        parameters=parameters,
        environment=environment,
    )
    kernel = process.compile_rate(context)
    assert kernel is not None
    for active in (0.01, 0.25, 3.0):
        expected = process.rate(_state(active * 1000.0), Q_(0.0, "hour"), parameters, environment)
        assert kernel(0.0, np.array([active, 0.0])) == pytest.approx(
            expected.to("filter_paper_unit / liter / hour").magnitude, rel=1e-12
        )
    with pytest.raises(ValueError, match="must be non-negative"):
        kernel(0.0, np.array([-1.0, 0.0]))


def test_compiled_solve_matches_exponential_decay_with_a_closed_ledger() -> None:
    process = _process()
    parameters = _parameters()
    environment = Environment(name="warm", temperature=Q_(312.15, "kelvin"), source="test")
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("thermal_inactivation",),
        parameters=parameters,
        environment=environment,
        allow_unsourced_for_testing=True,
    ).assemble()
    times = np.linspace(0.0, 48.0, 13)
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state=_state(10.0),
            t_span=(Q_(0.0, "hour"), Q_(48.0, "hour")),
            t_eval=Q_(times, "hour"),
        )
    )
    active = result.states["A"].to("filter_paper_unit / liter").magnitude
    inactive = result.states["D"].to("filter_paper_unit / liter").magnitude
    np.testing.assert_allclose(active, 10.0 * np.exp(-_rate_constant(312.15) * times), rtol=1e-6, atol=1e-9)
    np.testing.assert_allclose(active + inactive, 10.0, rtol=1e-9)
    assert result.solver_metadata["kernel"]["process_kernels"] == {"inactivation": "numeric"}


def test_factory_builds_the_process_and_fails_closed_on_partial_inputs() -> None:
    factory = ThermalInactivationFactory()
    context = ProcessBuildContext(state_units={"A": "millimolar", "D": "millimolar"}, source=SOURCE)
    complete = ProcessConfig(
        id="inactivation",
        process_type="thermal_inactivation",
        states={"active": "A", "inactive": "D"},
        parameters={"reference_rate_constant": "k_d_ref", "inactivation_energy": "E_d", "reference_temperature": "T_ref"},
    )
    assert factory.can_build(context, complete).can_build
    built = factory.build(context, complete)
    assert isinstance(built, ThermalInactivationProcess)
    assert built.rate_units == "millimolar / second"
    missing = ProcessConfig(
        id="missing",
        process_type="thermal_inactivation",
        states={"active": "A"},
        parameters={"reference_rate_constant": "k_d_ref"},
    )
    decision = factory.can_build(context, missing)
    assert not decision.can_build
    assert {"parameters.inactivation_energy", "parameters.reference_temperature"} <= set(decision.missing_fields)
    partial = ProcessConfig(
        id="partial",
        process_type="thermal_inactivation",
        states={"active": "A"},
        parameters={
            "reference_rate_constant": "k_d_ref",
            "inactivation_energy": "E_d",
            "reference_temperature": "T_ref",
            "minimum_temperature": "T_lo",
        },
    )
    decision = factory.can_build(context, partial)
    assert not decision.can_build
    assert "parameters.minimum_temperature_and_maximum_temperature_must_be_given_together" in decision.incompatible_entities
    assert "thermal_inactivation" in ProcessLibrary.default_foundation().factory_types()


def test_toy_config_runs_through_the_configured_workflow_with_the_closed_form(tmp_path: Path) -> None:
    result = run_configured_model(TOY_CONFIG, output_dir=tmp_path / "bundle")
    assert all(item["passed"] for item in result.validation_report())
    assert result.solver_metadata["kernel"]["process_kernels"] == {"active_pool_inactivation": "numeric"}
    times = np.asarray(result.time.to("second").magnitude)
    active = np.asarray(result.states["active_concentration"].to("millimolar").magnitude)
    inactive = np.asarray(result.states["inactive_concentration"].to("millimolar").magnitude)
    rate_constant = 0.01 * np.exp(-60000.0 / GAS_CONSTANT * (1.0 / 303.15 - 1.0 / 298.15))
    np.testing.assert_allclose(active, np.exp(-rate_constant * times), rtol=1e-6, atol=1e-9)
    np.testing.assert_allclose(active + inactive, 1.0, rtol=1e-9)
    metadata = json.loads((tmp_path / "bundle" / "configured_metadata.json").read_text(encoding="utf-8"))
    laws = metadata["configured_process_laws"]
    assert laws[0]["type"] == "thermal_inactivation"
    assert laws[0]["environment_value"] == "temperature"
    assert laws[0]["maturity"] == "configured_temperature_response_law"
