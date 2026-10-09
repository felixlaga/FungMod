"""Generic bounded signed-state unit and numerical derivative contracts."""
import numpy as np
import pytest

from fungal_model.core.units import Q_
from fungal_model.core.parameters import ParameterSet
from fungal_model.processes import ModelBuilder, ProcessRegistry
from fungal_model.processes.assembly import _collect_state_variables
from fungal_model.processes.base import Process, StateVariableSpec
from fungal_model.solvers import compile_assembled_model
from fungal_model.solvers.compiled import _finite_difference_gradient, FINITE_DIFFERENCE_RELATIVE_STEP


def test_shared_state_bounds_intersect_after_unit_conversion():
    specs = _collect_state_variables([], [
        StateVariableSpec("charge", "millimole/liter", domain="signed", lower_bound=-1000, upper_bound=1000),
        StateVariableSpec("charge", "mole/liter", domain="signed", lower_bound=-.5, upper_bound=.8),
    ])
    assert (specs[0].lower_bound, specs[0].upper_bound) == (-500, 800)


@pytest.mark.parametrize("value", [-2., -2. + 1e-10, 3. - 1e-10, 3.])
def test_finite_difference_probes_remain_inside_declared_signed_domain(value):
    probes = []
    def rate(t, y):
        probes.append(y[0])
        assert -2 <= y[0] <= 3
        return y[0]**3
    gradient = _finite_difference_gradient(rate, [0], 1, signed={0}, bounds=((-2, 3),))
    # A one-sided probe has O(h) truncation error at the boundary.
    assert gradient(0, np.array([value]))[0] == pytest.approx(3 * value**2, rel=2e-6)
    assert probes


def test_bounded_narrow_interval_uses_representable_in_domain_probe():
    low, high = 1., 1. + 1e-12
    def rate(t, y):
        assert low <= y[0] <= high
        return 2*y[0]
    gradient = _finite_difference_gradient(rate, [0], 1, signed={0}, bounds=((low, high),))
    assert gradient(0, np.array([low]))[0] == 2
    assert gradient(0, np.array([high]))[0] == 2


@pytest.mark.parametrize("value", [0., 1e-12, .1, 10.])
def test_unbounded_nonnegative_fallback_remains_bitwise_identical(value):
    def rate(t, y):
        return 3*y[0]**2 + 2*y[0]
    step = FINITE_DIFFERENCE_RELATIVE_STEP * max(abs(value), 1.)
    old = ((rate(0, [value+step])-rate(0, [value])) / step if value-step < 0 else
        (rate(0, [value+step])-rate(0, [value-step])) / (2*step))
    current = _finite_difference_gradient(rate, [0], 1, bounds=((None, None),))(0, np.array([value]))[0]
    assert current == old


class _VoltageProcess(Process):
    @property
    def rate_units(self):
        return "volt/hour"

    def rate(self, state, time, parameters, environment=None, geometry=None):
        value = float(state["V"].to("volt").magnitude)
        if not -2 <= value <= 3:
            raise ValueError("Voltage outside declared circuit domain")
        return Q_(value**3, self.rate_units)

    def contributions(self, rate):
        return {"V": rate}


def test_compiled_quantity_fallback_receives_canonical_bounds_for_nonbiological_state():
    spec = StateVariableSpec("V", "volt", domain="signed", lower_bound=-2, upper_bound=3)
    process = _VoltageProcess(name="circuit", process_type="generic_circuit", required_state_variables=(spec,),
        changed_state_variables=(spec,), source="Synthetic circuit math test")
    model = ModelBuilder(process_library=ProcessRegistry([process]), parameters=ParameterSet([]),
        state_variables=[StateVariableSpec("V", "millivolt", domain="signed", lower_bound=-2000, upper_bound=3000)]).assemble()
    compiled = compile_assembled_model(model, time_units="hour")
    assert compiled.state_bounds == ((-2000., 3000.),)
    for value in (-2000., 3000.):
        assert compiled.jacobian(0, np.array([value]))[0, 0] == pytest.approx(3*(value/1000)**2, rel=2e-6)
