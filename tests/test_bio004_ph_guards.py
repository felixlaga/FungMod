"""Independent dynamic-pH domain, native parity and numeric range checks."""
from dataclasses import replace

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities.environment import Environment
from fungal_model.modifiers import CardinalPHModifier, PHModifier
from fungal_model.processes.buffer import buffer_value
from tests.test_bio004_buffer import SOURCE, balance, driver, params


def _changed_parameters(**changes):
    return ParameterSet([
        replace(parameter, value=changes.get(parameter.symbol, parameter.value))
        for parameter in params()
    ])


def _context(parameters=None):
    return KernelContext({"ph": 0}, {"ph": "dimensionless"}, "hour", parameters or params())


@pytest.mark.parametrize("pka", [-1000.0, 1000.0])
def test_extreme_finite_pka_has_finite_water_only_limit(pka):
    beta, derivative = buffer_value(7, concentrations=np.array([0.1]), pka=np.array([pka]),
        water_ion_product=1e-14, standard_concentration=1)
    assert beta == pytest.approx(np.log(10) * 2e-7)
    assert derivative == pytest.approx(0, abs=1e-20)


@pytest.mark.parametrize("standard,kw", [(5e-324, 1e-14), (1.0, 1e308)])
def test_buffer_unrepresentable_concentration_basis_fails_closed(standard, kw):
    with pytest.raises(ValueError, match="underflows|finite"):
        buffer_value(14, concentrations=np.array([0.1]), pka=np.array([7]),
            water_ion_product=kw, standard_concentration=standard)


@pytest.mark.parametrize("changes", [{"low": -1}, {"high": 15}, {"opt": -1}, {"opt": 15}, {"width": 0}])
def test_gaussian_native_and_compiled_refuse_invalid_parameter_domain(changes):
    modifier = PHModifier("opt", "width", SOURCE, "low", "high", state_source="ph")
    parameters = _changed_parameters(**changes)
    with pytest.raises(ValueError, match="0 to 14"):
        modifier.compile_activity(_context(parameters))
    with pytest.raises(ValueError, match="0 to 14"):
        modifier.activity(parameters=parameters, environment=None, state={"ph": Q_(7, "dimensionless")})


@pytest.mark.parametrize("modifier", [
    PHModifier("opt", "width", SOURCE, "low", "high", state_source="ph"),
    CardinalPHModifier("low", "opt", "high", SOURCE, state_source="ph"),
])
@pytest.mark.parametrize("ph", [1.5, 12.5, float("nan"), float("inf")])
def test_dynamic_modifiers_native_and_compiled_refuse_same_state_domain(modifier, ph):
    with pytest.raises(ValueError):
        modifier.compile_activity(_context())(0, np.array([ph]))
    with pytest.raises(ValueError):
        modifier.activity(parameters=params(), environment=None, state={"ph": Q_(ph, "dimensionless")})


def test_dynamic_modifier_declares_bounded_state():
    ph = next(spec for spec in driver(modified=True).state_variables if spec.name == "ph")
    assert (ph.domain, ph.lower_bound, ph.upper_bound) == ("signed", 0, 14)


def test_direct_buffer_process_refuses_environment_temperature_mismatch():
    p = balance(driver())
    context = KernelContext({"A": 0, "B": 1, "ph": 2}, {"A": "mol/L", "B": "mol/L", "ph": "dimensionless"},
        "hour", params(), Environment("conflicting", temperature=Q_(310, "kelvin")))
    with pytest.raises(ValueError, match="temperature must match"):
        p.compile_rate(context)
    with pytest.raises(ValueError, match="temperature must match"):
        p.rate({"A": Q_(1, "mol/L"), "B": Q_(0, "mol/L"), "ph": Q_(7, "dimensionless")},
            Q_(0, "hour"), params(), context.environment)


@pytest.mark.parametrize("ph", [1.0, 13.0])
def test_dynamic_ionization_native_and_compiled_refuse_same_source_domain(ph):
    from tests.test_ph_ionization_process import _process, _parameters
    process = _process(state_source="ph")
    parameters = _parameters()
    state = {"S": Q_(3, "millimolar"), "E": Q_(.02, "millimolar"), "ph": Q_(ph, "dimensionless")}
    context = KernelContext({"S": 0, "E": 1, "ph": 2}, {name: str(value.units) for name, value in state.items()},
        "second", parameters)
    with pytest.raises(ValueError, match="domain"):
        process.compile_rate(context)(0, np.array([3, .02, ph]))
    with pytest.raises(ValueError, match="domain"):
        process.rate(state, Q_(0, "second"), parameters)
    with pytest.raises(ValueError, match="domain"):
        process.effective_constants(parameters=parameters, environment=None, state=state)
