"""Verification of the continuum mycelium against analytic and conservation results."""

from __future__ import annotations

import time

import numpy as np
import pytest

from fungal_model.core.numerics import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.mycelium import FieldSpec, MyceliumModel, SpatialGrid, TipMotion, Translocation, total_amount
from fungal_model.mycelium.benchmarks import (
    HYPHA_UNITS,
    SUBSTRATE_UNITS,
    TIP_UNITS,
    artificial_colony_model,
    artificial_front_model,
    artificial_parameter,
    central_inoculum,
)
from fungal_model.core.parameters import ParameterSet

HOUR = "hour"


def test_edelstein_front_spreads_at_the_pulled_front_speed() -> None:
    """``n_t = D n_xx + alpha n - a n rho``, ``rho_t = v n``: the leading edge is linear, so the speed tends to ``2 sqrt(D alpha)``."""

    diffusivity, branching = 1.0, 0.25
    compiled = artificial_front_model(diffusivity=diffusivity, branching=branching).compile()
    x = compiled.model.grid.coordinates[0] * 1e3
    result = compiled.simulate(
        initial_fields={"tips": Q_(np.where(x < 5.0, 1.0, 0.0), TIP_UNITS), "hyphae": Q_(np.where(x < 5.0, 1.0, 0.0), HYPHA_UNITS)},
        t_span=(Q_(0, HOUR), Q_(80, HOUR)),
        t_eval=Q_(np.arange(0.0, 81.0, 10.0), HOUR),
        solver_settings=SolverSettings(method="BDF", rtol=1e-8, atol=1e-11),
        record_rates=False,
    )
    position = result.front_position("tips", Q_(1e-3, TIP_UNITS)).to("millimeter").magnitude
    speeds = np.diff(position) / 10.0
    analytic = 2.0 * np.sqrt(diffusivity * branching)
    assert np.all(speeds[2:] < analytic)  # a pulled front from compact data approaches its speed from below
    assert np.all(np.diff(speeds[2:]) > 0.0)  # and keeps approaching it
    assert speeds[-1] == pytest.approx(analytic, rel=0.05)
    assert result.fields["tips"].magnitude.min() >= -1e-9 and result.fields["hyphae"].magnitude.min() >= 0.0
    assert result.solver_metadata["jacobian_structure"] == "cartesian_sparse_nearest_neighbour"


def _colony(cells: int = 24, hours: float = 12.0, method: str = "LSODA", **overrides: float):
    model = artificial_colony_model(cells=cells, overrides=overrides)
    compiled = model.compile()
    return compiled.simulate(
        initial_fields=central_inoculum(model.grid),
        t_span=(Q_(0, HOUR), Q_(hours, HOUR)),
        t_eval=Q_(np.linspace(0.0, hours, 4), HOUR),
        solver_settings=SolverSettings(method=method, rtol=1e-6, atol=1e-9),
        record_rates=False,
    )


def test_colony_conserves_substrate_expands_and_stays_symmetric() -> None:
    result = _colony()
    ledger = total_amount(result, [("internal", Q_(1.0, "dimensionless")), ("external", Q_(1.0, "dimensionless")), ("hyphae", Q_(0.1, "microgram / millimeter"))])
    amounts = ledger.to("microgram").magnitude
    np.testing.assert_allclose(amounts, amounts[0], rtol=1e-7)
    extent = result.occupied_measure("hyphae", Q_(0.05, HYPHA_UNITS)).to("millimeter ** 2").magnitude
    assert np.all(np.diff(extent) >= 0.0) and extent[-1] > 2.0 * extent[0]
    front = result.front_position("hyphae", Q_(0.05, HYPHA_UNITS)).to("millimeter").magnitude
    assert np.all(np.diff(front) > 0.0)
    hyphae = result.spatial_integral("hyphae").to("millimeter").magnitude
    assert hyphae[-1] > 1.5 * hyphae[0]
    final = result.field_at_final_time("hyphae").magnitude
    assert np.abs(final - final.T).max() < 1e-10 and np.abs(final - final[::-1, :]).max() < 1e-10
    for name, values in result.fields.items():
        assert values.magnitude.min() >= -1e-9, name
    assert result.fields["external"].magnitude[-1].min() < 3.0  # uptake happened where the colony is


def test_explicit_implicit_and_sparse_methods_agree_on_the_colony() -> None:
    reference = _colony(cells=16, hours=6.0, method="LSODA")
    sparse = _colony(cells=16, hours=6.0, method="BDF")
    explicit = _colony(cells=16, hours=6.0, method="RK45")
    assert sparse.solver_metadata["jacobian_structure"] == "cartesian_sparse_nearest_neighbour"
    for name in reference.fields:
        np.testing.assert_allclose(sparse.fields[name].magnitude, reference.fields[name].magnitude, rtol=2e-4, atol=1e-7, err_msg=name)
        np.testing.assert_allclose(explicit.fields[name].magnitude, reference.fields[name].magnitude, rtol=2e-4, atol=1e-7, err_msg=name)


def test_right_hand_side_of_a_medium_colony_takes_less_than_a_few_milliseconds() -> None:
    model = artificial_colony_model(cells=50)
    compiled = model.compile()
    state = compiled.initial_state(central_inoculum(model.grid))
    compiled.rhs(0.0, state)
    started = time.perf_counter()
    for _ in range(20):
        compiled.rhs(0.0, state)
    per_call = (time.perf_counter() - started) / 20.0
    assert per_call < 0.05, f"{per_call * 1e3:.1f} ms per right-hand side at 50 x 50 cells and 4 fields"


def _translocation_model(*, active: bool) -> MyceliumModel:
    grid = SpatialGrid.no_flux((artificial_parameter("L", 10.0, "millimeter"),), (20,))
    if active:
        translocation = Translocation(
            name="translocation", internal_field="internal", internal_units=SUBSTRATE_UNITS, diffusivity_symbol="Di",
            tip_field="tips", tip_units=TIP_UNITS, active_diffusivity_symbol="Da",
        )
    else:
        translocation = Translocation(name="translocation", internal_field="internal", internal_units=SUBSTRATE_UNITS, diffusivity_symbol="Di")
    processes = [translocation, TipMotion(name="motion", tip_field="tips", tip_units=TIP_UNITS, diffusivity_symbol="Dn")]
    parameters = ParameterSet([
        artificial_parameter("Di", 0.2, "millimeter ** 2 / hour"),
        artificial_parameter("Da", 2.0, "millimeter ** 4 / hour"),
        artificial_parameter("Dn", 0.0, "millimeter ** 2 / hour"),
    ])
    return MyceliumModel(grid=grid, fields=(FieldSpec("internal", SUBSTRATE_UNITS), FieldSpec("tips", TIP_UNITS)), processes=tuple(processes), parameters=parameters)


def test_translocation_conserves_substrate_and_the_active_term_carries_it_towards_tips() -> None:
    x = np.arange(20) * 0.5 + 0.25  # millimetres
    substrate = np.where(x < 2.5, 1.0, 0.0)
    tips = x / 10.0  # a uniform tip-density gradient, so the active velocity is uniform
    outputs = {}
    for active in (False, True):
        compiled = _translocation_model(active=active).compile()
        result = compiled.simulate(
            initial_fields={"internal": Q_(substrate, SUBSTRATE_UNITS), "tips": Q_(tips, TIP_UNITS)},
            t_span=(Q_(0, HOUR), Q_(20, HOUR)),
            t_eval=Q_([0.0, 20.0], HOUR),
            solver_settings=SolverSettings(rtol=1e-9, atol=1e-12),
            record_rates=False,
        )
        totals = result.spatial_integral("internal").magnitude
        assert totals[-1] == pytest.approx(totals[0], rel=1e-9)
        final = result.field_at_final_time("internal").magnitude
        outputs[active] = float(np.sum(final * x) / np.sum(final))
        assert final.min() >= -1e-12
    assert outputs[False] > float(np.sum(substrate * x) / np.sum(substrate))  # diffusion spreads it to the right
    assert outputs[True] > outputs[False] + 1.0  # the active term carries it up the tip gradient (0.2 mm/h for 20 h)
