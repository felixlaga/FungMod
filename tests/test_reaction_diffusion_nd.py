from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.transport import (
    BoundaryConditionsND,
    ReactionDiffusionEngineND,
    UniformCartesianGrid,
    finite_volume_laplacian_nd,
    spatial_integral_nd,
)


SOURCE = "Artificial Cartesian reaction-diffusion benchmark; no physical claim."


def test_two_dimensional_no_flux_laplacian_conserves_discrete_integral() -> None:
    grid = _grid((5, 7))
    rng = np.random.default_rng(3)
    laplacian = finite_volume_laplacian_nd(
        Q_(rng.random(grid.shape), "mole / liter"),
        grid=grid,
        boundary_conditions=BoundaryConditionsND.no_flux(2),
    )

    assert spatial_integral_nd(laplacian, grid=grid).magnitude == pytest.approx(0.0, abs=1e-12)


def test_periodic_two_dimensional_fourier_mode_matches_discrete_decay() -> None:
    grid = _grid((12, 8))
    x = grid.coordinates[0].to("meter").magnitude
    initial_x = 1.0 + 0.2 * np.cos(2.0 * np.pi * x)
    initial = np.repeat(initial_x[:, None], grid.shape[1], axis=1)
    diffusion = 0.03
    duration = 1.5
    engine = ReactionDiffusionEngineND(
        grid=grid,
        field_units={"C": "mole / liter"},
        boundary_conditions={"C": BoundaryConditionsND.periodic(2)},
        parameters=ParameterSet([_parameter("diffusion", "D", diffusion, "meter ** 2 / second")]),
        diffusion_symbols={"C": "D"},
    )

    result = engine.simulate(
        initial_fields={"C": Q_(initial, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(duration, "second")),
        t_eval=Q_([0.0, duration], "second"),
        solver_settings=SolverSettings(rtol=1e-9, atol=1e-11),
    )

    dx = float(grid.cell_widths[0].to("meter").magnitude)
    discrete_eigenvalue = 4.0 * np.sin(np.pi / grid.shape[0]) ** 2 / dx**2
    expected = 1.0 + 0.2 * np.exp(-diffusion * discrete_eigenvalue * duration) * np.cos(
        2.0 * np.pi * x
    )
    final = result.field_at_final_time("C").to("mole / liter").magnitude
    assert result.success
    assert np.allclose(final, expected[:, None], rtol=2e-6, atol=2e-8)


def test_three_dimensional_no_flux_diffusion_conserves_total_and_smooths() -> None:
    grid = _grid((4, 5, 6))
    initial = np.zeros(grid.shape)
    initial[1, 2, 3] = 1.0
    engine = ReactionDiffusionEngineND(
        grid=grid,
        field_units={"C": "mole / liter"},
        boundary_conditions={"C": BoundaryConditionsND.no_flux(3)},
        parameters=ParameterSet([_parameter("diffusion", "D", 0.02, "meter ** 2 / second")]),
        diffusion_symbols={"C": "D"},
    )

    result = engine.simulate(
        initial_fields={"C": Q_(initial, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(0.5, "second")),
        t_eval=Q_([0.0, 0.5], "second"),
    )

    initial_integral = spatial_integral_nd(Q_(initial, "mole / liter"), grid=grid)
    assert result.success
    assert result.spatial_integral("C").magnitude == pytest.approx(
        initial_integral.magnitude,
        rel=1e-8,
    )
    assert np.var(result.field_at_final_time("C").magnitude) < np.var(initial)
    assert result.solver_metadata["ndim"] == 3


def test_zero_diffusion_reproduces_local_reaction_in_every_two_dimensional_cell() -> None:
    grid = _grid((3, 4))
    initial = np.arange(1.0, 13.0).reshape(grid.shape)

    def rate(state, time, parameters):
        del time
        return parameters.require_quantity("k", "1 / second") * state["A"]

    reaction = Reaction(
        name="local A to B",
        reactants={"A": 1.0},
        products={"B": 1.0},
        rate_law=rate,
        rate_units="mole / liter / second",
        source=SOURCE,
    )
    engine = ReactionDiffusionEngineND(
        grid=grid,
        field_units={"A": "mole / liter", "B": "mole / liter"},
        boundary_conditions={
            "A": BoundaryConditionsND.no_flux(2),
            "B": BoundaryConditionsND.no_flux(2),
        },
        parameters=ParameterSet([_parameter("rate", "k", 0.2, "1 / second")]),
        diffusion_symbols={"A": None, "B": None},
        reactions=(reaction,),
    )

    result = engine.simulate(
        initial_fields={
            "A": Q_(initial, "mole / liter"),
            "B": Q_(np.zeros(grid.shape), "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(2.0, "second")),
        t_eval=Q_([0.0, 2.0], "second"),
    )

    expected_a = initial * np.exp(-0.4)
    assert np.allclose(result.field_at_final_time("A").magnitude, expected_a, rtol=1e-5)
    assert np.allclose(result.field_at_final_time("B").magnitude, initial - expected_a, rtol=1e-5)


def test_cartesian_engine_rejects_unsupported_dimensions_shapes_and_implicit_boundaries() -> None:
    with pytest.raises(ValueError, match="exactly 2D or 3D"):
        _grid((2, 2, 2, 2))
    grid = _grid((3, 3))
    with pytest.raises(ValueError, match="exactly match field_units"):
        ReactionDiffusionEngineND(
            grid=grid,
            field_units={"C": "mole / liter"},
            boundary_conditions={},
            parameters=ParameterSet(),
            diffusion_symbols={"C": None},
        )


def _grid(shape: tuple[int, ...]) -> UniformCartesianGrid:
    return UniformCartesianGrid(
        axis_lengths=tuple(
            _parameter(f"axis {index} length", f"L_{index}", 1.0, "meter")
            for index in range(len(shape))
        ),
        shape=shape,
    )


def _parameter(name: str, symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source=SOURCE,
        confidence_level="testing",
        notes="Artificial finite-volume benchmark value.",
        measurement_method="definition",
    )
