"""Endogenous maintenance: starvation physiology of the generic resource-limited closure.

Abstract dissolved pools (resource, cells, nutrient, acceptor) in millimolar
and hours with artificial values; the test declares one abstract conserved
"carbon unit" per formula unit of resource and cells and ledgers its export to
a reservoir through the extent states. No organism, chemistry or measurement
is claimed.
"""

from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.io import ProcessConfig
from fungal_model.processes import ModelBuilder, ProcessBuildContext, ProcessLibrary, ProcessRegistry
from fungal_model.processes.culture import (
    ENDOGENOUS_MAINTENANCE_MATURITY,
    ENDOGENOUS_MAINTENANCE_PROCESS_TYPE,
    EndogenousMaintenanceProcess,
    endogenous_maintenance_assumption,
)
from fungal_model.processes.culture_factories import EndogenousMaintenanceFactory
from fungal_model.solvers import ProcessODESolver, RunRequest
from tests.test_culture_processes import CLOSURE_PARAMETERS, CLOSURE_STATES, POOLS, SOURCE, SYMBOLS, UNITS
from tests.test_culture_processes import growth as base_growth
from tests.test_culture_processes import maintenance as base_maintenance
from tests.test_culture_processes import parameters as base_parameters
from tests.test_culture_processes import secretion as base_secretion

STATES = ("resource", "cells", "nutrient", "acceptor", "e_growth", "e_maintenance", "e_endogenous")
# Abstract carbon units per formula unit of each pool; the reservoir export per unit extent follows
# from the stoichiometries below (growth 1.5, maintenance 1, endogenous 1).
CARBON = {"resource": 1.0, "cells": 1.0}
RESERVOIR_CARBON = {"e_growth": 1.5, "e_maintenance": 1.0, "e_endogenous": 1.0}


def parameters(**overrides: float) -> ParameterSet:
    values = base_parameters(**{k: v for k, v in overrides.items() if k != "Y_e"})
    values.add(Parameter("artificial Y_e", "Y_e", overrides.get("Y_e", 2.0), "dimensionless", None, SOURCE, "testing",
                         "Artificial maintenance substrate equivalent per cell formula unit oxidised."))
    return values


def endogenous(**kwargs) -> EndogenousMaintenanceProcess:
    fields = dict(name="endogenous", stoichiometry={"cells": -1.0, "acceptor": -1.0}, endogenous_yield_symbol="Y_e",
                  source=SOURCE, **POOLS, **SYMBOLS, **UNITS)
    fields.update(kwargs)
    return EndogenousMaintenanceProcess(**fields)


def _context(parameter_set: ParameterSet, units: str = "millimolar") -> KernelContext:
    return KernelContext(state_index={name: index for index, name in enumerate(STATES)},
                         state_units=dict.fromkeys(STATES, units), time_units="hour", parameters=parameter_set)


def _richardson(function, point: np.ndarray, index: int, side: str) -> float:
    """Richardson extrapolation of a central, right or left difference with a state-scaled step.

    ``(4 D(h/2) - D(h)) / 3`` cancels the h^2 term of a central difference;
    the one-sided differences used at a boundary or a kink are first order, so
    their extrapolation is ``2 D(h/2) - D(h)``.
    """

    step = 1e-5 * max(abs(float(point[index])), 1e-2)

    def difference(h: float) -> float:
        unit = np.zeros_like(point)
        unit[index] = h
        if side == "central":
            return (function(point + unit) - function(point - unit)) / (2.0 * h)
        if side == "right":
            return (function(point + unit) - function(point)) / h
        return (function(point) - function(point - unit)) / h

    if side == "central":
        return (4.0 * difference(step / 2.0) - difference(step)) / 3.0
    return 2.0 * difference(step / 2.0) - difference(step)


def test_batch_starvation_shrinks_cells_only_after_growth_stops_and_closes_the_ledger() -> None:
    processes = (
        base_growth(allocation_fraction_symbol=None, extent_state="e_growth"),
        base_maintenance(extent_state="e_maintenance"),
        endogenous(extent_state="e_endogenous"),
    )
    model = ModelBuilder(process_library=ProcessRegistry(processes), requested_processes=tuple(p.name for p in processes),
                         parameters=parameters(), solver_settings=SolverSettings(rtol=1e-10, atol=1e-13)).assemble()
    initial = {"resource": 1.0, "cells": 0.1, "nutrient": 0.5, "acceptor": 10.0, "e_growth": 0.0, "e_maintenance": 0.0, "e_endogenous": 0.0}
    times = np.linspace(0.0, 400.0, 81)
    result = ProcessODESolver(model).run(RunRequest(
        initial_state={name: Q_(value, "millimolar") for name, value in initial.items()},
        t_span=(Q_(0.0, "hour"), Q_(400.0, "hour")), t_eval=Q_(times, "hour")))
    assert result.solver_metadata["kernel"]["quantity_wrapped_kernel_count"] == 0
    cells = result.states["cells"].magnitude
    resource = result.states["resource"].magnitude
    growth_rate = result.process_rates["growth"].magnitude
    endogenous_rate = result.process_rates["endogenous"].magnitude
    peak = int(np.argmax(cells))
    assert 0 < peak < len(times) - 1
    assert cells[-1] < 0.8 * cells[peak], "cells must decline after the resource is exhausted"
    assert resource[-1] < 1e-3 * resource[0] and resource.min() > -1e-12
    # The deficit is paid only when uptake cannot pay the demand, and growth is zero whenever it is paid.
    assert endogenous_rate[0] == 0.0 and endogenous_rate[-1] > 0.0
    assert np.all(growth_rate[endogenous_rate > 0.0] == 0.0)
    assert np.all(np.diff(cells[peak:]) <= 0.0)
    # After exhaustion the cell pool decays at m / Y_e: the deficit tends to the full demand.
    tail = slice(-11, None)
    specific = -np.gradient(cells[tail], times[tail]) / cells[tail]
    np.testing.assert_allclose(specific, 0.01 / 2.0, rtol=2e-2)
    # Element ledger: carbon units in the pools plus the reservoir export reconstructed from the extents.
    carbon = sum(CARBON[name] * result.states[name].magnitude for name in CARBON)
    carbon = carbon + sum(RESERVOIR_CARBON[name] * result.states[name].magnitude for name in RESERVOIR_CARBON)
    np.testing.assert_allclose(carbon, carbon[0], rtol=0.0, atol=1e-12)
    # The extent ledger of the endogenous process is exactly the cells it oxidised.
    oxidised = result.states["e_endogenous"].magnitude
    formed = result.states["e_growth"].magnitude
    np.testing.assert_allclose(cells - cells[0], formed - oxidised, rtol=0.0, atol=1e-12)


@pytest.mark.parametrize("units,scale", [("millimolar", 1.0), ("mole / liter", 1e-3)])
def test_endogenous_kernel_matches_the_unit_aware_rate_and_the_closed_form(units, scale) -> None:
    process = endogenous()
    parameter_set = parameters()
    kernel = process.compile_rate(_context(parameter_set, units))
    assert kernel is not None
    rng = np.random.default_rng(11)
    for _ in range(25):
        vector = rng.uniform(0.0, 0.05, len(STATES)) * scale  # resource-poor states so that the deficit is often positive
        state = {name: Q_(value, units) for name, value in zip(STATES, vector, strict=True)}
        expected = process.rate(state, Q_(0.0, "hour"), parameter_set).to(process.rate_units).magnitude
        assert kernel(0.0, vector) == pytest.approx(float(expected), rel=1e-12, abs=1e-18)
        resource, cells, acceptor = (vector[STATES.index(name)] / scale for name in ("resource", "cells", "acceptor"))
        capacity = 0.5 * resource / (0.2 + resource) * acceptor / (0.01 + acceptor)
        closed_form = max(0.01 - capacity, 0.0) * cells / 2.0
        assert float(expected) == pytest.approx(closed_form, rel=1e-12, abs=1e-18)
    contributions = process.contributions(Q_(3.0, process.rate_units))
    assert contributions["cells"].magnitude == pytest.approx(-3.0) and contributions["acceptor"].magnitude == pytest.approx(-3.0)
    assert "e_endogenous" not in contributions and endogenous(extent_state="e_endogenous").contributions(Q_(3.0, process.rate_units))["e_endogenous"].magnitude == 3.0
    # Zero demand: nothing is ever unpaid, so the extent is identically zero.
    zero = endogenous().compile_rate(_context(parameters(m=0.0), units))
    assert zero is not None and zero(0.0, np.zeros(len(STATES))) == 0.0 and zero(0.0, rng.uniform(0.0, 1.0, len(STATES))) == 0.0


def _tie_parameters() -> ParameterSet:
    # resource/(K_r + resource) = 0.2/0.4 and acceptor/(K_a + acceptor) = 0.01/0.02 are exact halves, so
    # capacity = 0.5 * 0.5 * 0.5 = 0.125 = m exactly in floating point.
    return parameters(m=0.125)


@pytest.mark.parametrize("label,point,side,builder", [
    ("interior below demand", np.array([0.002, 0.3, 0.4, 0.2, 0.0, 0.0, 0.0]), "central", endogenous),
    ("interior above demand", np.array([0.8, 0.3, 0.4, 0.2, 0.0, 0.0, 0.0]), "central", endogenous),
    ("resource exhausted", np.array([0.0, 0.3, 0.4, 0.2, 0.0, 0.0, 0.0]), "right", endogenous),
    ("acceptor exhausted", np.array([0.8, 0.3, 0.4, 0.0, 0.0, 0.0, 0.0]), "right", endogenous),
    ("no cells", np.array([0.002, 0.0, 0.4, 0.2, 0.0, 0.0, 0.0]), "right", endogenous),
    ("all zero", np.zeros(7), "right", endogenous),
])
def test_endogenous_gradient_matches_richardson_differences(label, point, side, builder) -> None:
    del label
    parameter_set = parameters()
    context = _context(parameter_set)
    process = builder()
    kernel, gradient = process.compile_rate(context), process.compile_jacobian(context)
    assert kernel is not None and gradient is not None
    analytic = gradient(0.0, point)
    numeric = np.array([_richardson(lambda y: kernel(0.0, y), point, i, side) for i in range(len(STATES))])
    np.testing.assert_allclose(analytic, numeric, rtol=1e-6, atol=1e-9)
    assert np.all(analytic[4:] == 0.0)


def test_gradients_at_the_tie_are_one_sided_as_documented() -> None:
    parameter_set = _tie_parameters()
    context = _context(parameter_set)
    point = np.array([0.2, 0.3, 0.4, 0.01, 0.0, 0.0, 0.0])
    endo = endogenous()
    constants = endo.closure_constants(parameter_set)
    assert constants.capacity(0.2, 0.01) == constants.maintenance_demand == 0.125
    # Endogenous: zero from above (c >= m), so it equals the right-sided difference and not the left one.
    kernel, gradient = endo.compile_rate(context), endo.compile_jacobian(context)
    assert kernel is not None and gradient is not None
    analytic = gradient(0.0, point)
    right = np.array([_richardson(lambda y: kernel(0.0, y), point, i, "right") for i in range(len(STATES))])
    left = np.array([_richardson(lambda y: kernel(0.0, y), point, i, "left") for i in range(len(STATES))])
    np.testing.assert_allclose(analytic, right, rtol=0.0, atol=1e-9)
    assert np.all(analytic == 0.0) and left[0] < -1e-3 and left[3] < -1e-3
    # Growth and secretion: zero from below (budget <= 0), so they equal the left-sided difference.
    for process in (base_growth(), base_secretion()):
        kernel, gradient = process.compile_rate(context), process.compile_jacobian(context)
        assert kernel is not None and gradient is not None
        analytic = gradient(0.0, point)
        left = np.array([_richardson(lambda y: kernel(0.0, y), point, i, "left") for i in range(len(STATES))])
        right = np.array([_richardson(lambda y: kernel(0.0, y), point, i, "right") for i in range(len(STATES))])
        np.testing.assert_allclose(analytic, left, rtol=0.0, atol=1e-9)
        assert np.all(analytic == 0.0) and right[0] > 1e-3
    # Maintenance: capped from above (min(m, c)), so its substrate derivative is the right-sided zero.
    kernel, gradient = base_maintenance().compile_rate(context), base_maintenance().compile_jacobian(context)
    assert kernel is not None and gradient is not None
    analytic = gradient(0.0, point)
    right = np.array([_richardson(lambda y: kernel(0.0, y), point, i, "right") for i in range(len(STATES))])
    np.testing.assert_allclose(analytic, right, rtol=1e-9, atol=1e-9)


def test_factory_round_trip_and_missing_field_report() -> None:
    library = ProcessLibrary(factories=(EndogenousMaintenanceFactory(),))
    assert library.factory_types() == (ENDOGENOUS_MAINTENANCE_PROCESS_TYPE,)
    context = ProcessBuildContext(state_units=dict.fromkeys(STATES, "millimolar"), source=SOURCE)
    config = ProcessConfig(id="starvation", process_type=ENDOGENOUS_MAINTENANCE_PROCESS_TYPE,
                           states={**CLOSURE_STATES, "extent": "e_endogenous"},
                           parameters={**CLOSURE_PARAMETERS, "endogenous_yield": "Y_e"},
                           stoichiometry={"cells": -1.0, "acceptor": -1.0})
    (process,) = library.build_processes(context, [config])
    assert isinstance(process, EndogenousMaintenanceProcess)
    assert process.name == "starvation" and process.endogenous_yield_symbol == "Y_e" and process.extent_state == "e_endogenous"
    assert process.stoichiometry == {"cells": -1.0, "acceptor": -1.0} and process.source == SOURCE
    record = process.to_dict()
    assert record["process_type"] == ENDOGENOUS_MAINTENANCE_PROCESS_TYPE
    assert record["endogenous_yield_symbol"] == "Y_e" and record["maturity"] == ENDOGENOUS_MAINTENANCE_MATURITY
    assert record["stoichiometry"] == dict(config.stoichiometry) and record["extent_state"] == "e_endogenous"
    assert record["pools"] == {"substrate": "resource", "biomass": "cells", "nutrient": "nutrient", "oxidant": "acceptor"}
    assert {assumption.name for assumption in process.assumptions} >= {endogenous_maintenance_assumption().name}
    assert ENDOGENOUS_MAINTENANCE_MATURITY in process.validity.labels
    assert any(requirement.symbol == "Y_e" for requirement in process.required_parameters)
    # The built process is the same object the direct constructor makes, kernel for kernel.
    direct = endogenous(name="starvation", extent_state="e_endogenous", notes=process.notes)
    assert direct.to_dict() == record
    model = ModelBuilder(process_library=ProcessRegistry([process]), requested_processes=("starvation",), parameters=parameters()).assemble()
    compiled = ProcessODESolver(model).compile(RunRequest(
        initial_state={name: Q_(0.01, "millimolar") for name in ("resource", "cells", "nutrient", "acceptor", "e_endogenous")},
        t_span=(Q_(0.0, "hour"), Q_(1.0, "hour"))))
    assert compiled.summary()["quantity_wrapped_kernel_count"] == 0 and compiled.summary()["process_count"] == 1
    # Missing the endogenous yield or a pool unit is reported, never guessed.
    partial = ProcessConfig(id="starvation", process_type=ENDOGENOUS_MAINTENANCE_PROCESS_TYPE, states=CLOSURE_STATES,
                            parameters=CLOSURE_PARAMETERS, stoichiometry={"cells": -1.0})
    decision = library.factory_for(ENDOGENOUS_MAINTENANCE_PROCESS_TYPE).can_build(
        ProcessBuildContext(state_units={"resource": "millimolar", "cells": "millimolar", "nutrient": "millimolar"}), partial)
    assert not decision.can_build
    assert set(decision.missing_fields) == {"parameters.endogenous_yield", "state_units.acceptor"}
    with pytest.raises(ValueError, match="cannot build"):
        library.factory_for(ENDOGENOUS_MAINTENANCE_PROCESS_TYPE).build(context, partial)


def test_inconsistent_closure_stoichiometry_is_refused_with_the_expected_coefficient() -> None:
    parameter_set = parameters()
    cases = [
        (base_growth(stoichiometry={"resource": -1.0, "cells": 1.0}), r"'resource' must be -1/Y = -2\.5 .*got -1"),
        (base_growth(stoichiometry={"resource": -2.5, "cells": 2.0}), r"'cells' must be \+1 .*got \+2"),
        (base_growth(stoichiometry={"resource": -2.5, "nutrient": -0.2}), r"'cells' must be \+1 .*got none"),
        (base_maintenance(stoichiometry={"resource": -2.0, "acceptor": -6.0}), r"'resource' must be -1 .*got -2"),
        (base_maintenance(stoichiometry={"acceptor": -6.0}), r"'resource' must be -1 .*got none"),
        (base_secretion(stoichiometry={"resource": -1.0, "product": 1.0}), r"'resource' must be -1/y_s = -0\.5 .*got -1"),
        (base_secretion(stoichiometry={"resource": -0.5, "product": 2.0}), r"coefficient \+1; got"),
        (endogenous(stoichiometry={"cells": -2.0}), r"'cells' must be -1 .*got -2"),
        (endogenous(stoichiometry={"cells": 1.0}), r"'cells' must be -1 .*got \+1"),
    ]
    for process, message in cases:
        with pytest.raises(ValueError, match=message):
            process.closure_constants(parameter_set)
        with pytest.raises(ValueError, match=message):
            process.compile_rate(_context(parameter_set))
    # A yield that cannot define the substrate coefficient is refused too.
    with pytest.raises(ValueError, match="Y must be positive"):
        base_growth().closure_constants(parameters(Y=0.0))
    with pytest.raises(ValueError, match="Y_e must be a finite positive"):
        endogenous().closure_constants(parameters(Y_e=0.0))
    # A coefficient written as -1/Y is accepted within the declared round-off tolerance.
    base_growth(stoichiometry={"resource": -1.0 / 0.4, "cells": 1.0}).closure_constants(parameter_set)
    base_secretion(stoichiometry={"resource": -1.0 / 2.0, "product": 1.0}).closure_constants(parameter_set)
    with pytest.raises(ValueError, match="must be -1/Y"):
        base_growth(stoichiometry={"resource": -2.5 * (1.0 + 1e-6), "cells": 1.0}).closure_constants(parameter_set)
