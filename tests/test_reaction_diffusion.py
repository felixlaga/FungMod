from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_non_negative
from fungal_model.transport.diffusion import finite_volume_laplacian_1d, spatial_integral_1d
from fungal_model.transport.geometry import BoundaryCondition, BoundaryConditions1D, UniformGrid1D
from fungal_model.transport.reaction_diffusion import ReactionDiffusionEngine1D
from fungal_model.validation.spatial import (
    validate_diffusion_smooths_gradient,
    validate_no_flux_spatial_integral_conserved,
    validate_spatial_average_close_to_expected,
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
        uncertainty=0.0 if value is not None else None,
        source="Artificial Stage 8 reaction-diffusion benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only for validating Stage 8 spatial numerics.",
        measurement_method="defined benchmark value",
    )


def grid(n_cells: int = 20) -> UniformGrid1D:
    return UniformGrid1D(
        length=parameter(
            name="benchmark one-dimensional domain length",
            symbol="L",
            value=1.0,
            units="meter",
        ),
        n_cells=n_cells,
    )


def diffusion_parameters() -> ParameterSet:
    return ParameterSet(
        [
            parameter(
                name="benchmark diffusion coefficient",
                symbol="D",
                value=1.0e-3,
                units="meter ** 2 / second",
            ),
        ]
    )


def reaction_parameters() -> ParameterSet:
    return ParameterSet(
        [
            parameter(
                name="benchmark first-order rate constant",
                symbol="k",
                value=0.2,
                units="1 / second",
            ),
            parameter(
                name="benchmark diffusion coefficient",
                symbol="D",
                value=1.0e-1,
                units="meter ** 2 / second",
            ),
        ]
    )


def first_order_reaction() -> Reaction:
    def rate_law(state, time, parameters):
        del time
        return parameters.require_quantity("k", "1 / second") * state["A"]

    return Reaction(
        name="local first-order A to B",
        reactants={"A": 1.0},
        products={"B": 1.0},
        rate_law=rate_law,
        rate_units="mole / liter / second",
        source="Artificial Stage 8 local reaction benchmark.",
    )


def test_no_flux_laplacian_has_zero_spatial_integral() -> None:
    values = Q_(np.array([0.0, 1.0, 0.0, 2.0]), "mole / liter")
    cell_width = Q_(0.25, "meter")
    laplacian = finite_volume_laplacian_1d(
        values,
        cell_width=cell_width,
        boundary_conditions=BoundaryConditions1D.no_flux(),
    )
    integral = spatial_integral_1d(laplacian, cell_width=cell_width)

    assert integral.magnitude == pytest.approx(0.0)


def test_missing_boundary_conditions_are_rejected() -> None:
    with pytest.raises(ValueError):
        ReactionDiffusionEngine1D(
            grid=grid(),
            field_units={"C": "mole / liter"},
            boundary_conditions={},
            parameters=diffusion_parameters(),
        )


def test_diffusion_smooths_gradient_and_no_flux_conserves_integral() -> None:
    initial = np.zeros(20)
    initial[10] = 1.0
    engine = ReactionDiffusionEngine1D(
        grid=grid(),
        field_units={"C": "mole / liter"},
        boundary_conditions={"C": BoundaryConditions1D.no_flux()},
        parameters=diffusion_parameters(),
        diffusion_symbols={"C": "D"},
    )

    result = engine.simulate(
        initial_fields={"C": Q_(initial, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(20.0, "second")),
        t_eval=Q_(np.linspace(0.0, 20.0, 41), "second"),
    )

    assert result.success
    assert validate_non_negative(type("SpatialAdapter", (), {"species": result.fields})()).passed
    assert validate_diffusion_smooths_gradient(result, field="C").passed
    assert validate_no_flux_spatial_integral_conserved(
        result,
        field="C",
        relative_tolerance=Q_(1e-6, "dimensionless"),
    ).passed


def test_zero_diffusion_reproduces_local_ode_behavior() -> None:
    initial_a = np.array([1.0, 2.0, 3.0])
    engine = ReactionDiffusionEngine1D(
        grid=grid(n_cells=3),
        field_units={"A": "mole / liter", "B": "mole / liter"},
        boundary_conditions={
            "A": BoundaryConditions1D.no_flux(),
            "B": BoundaryConditions1D.no_flux(),
        },
        parameters=reaction_parameters(),
        reactions=[first_order_reaction()],
        diffusion_symbols={"A": None, "B": None},
    )

    result = engine.simulate(
        initial_fields={
            "A": Q_(initial_a, "mole / liter"),
            "B": Q_(np.zeros_like(initial_a), "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(2.0, "second")),
        t_eval=Q_(np.array([0.0, 2.0]), "second"),
    )

    expected_a = initial_a * np.exp(-0.2 * 2.0)
    final_a = result.field_at_final_time("A").to("mole / liter").magnitude
    final_b = result.field_at_final_time("B").to("mole / liter").magnitude

    assert np.allclose(final_a, expected_a, rtol=1e-5, atol=1e-8)
    assert np.allclose(final_b, initial_a - expected_a, rtol=1e-5, atol=1e-8)


def test_high_diffusion_average_matches_well_mixed_linear_reaction() -> None:
    initial_a = np.array([0.0, 0.0, 3.0, 3.0])
    engine = ReactionDiffusionEngine1D(
        grid=grid(n_cells=4),
        field_units={"A": "mole / liter", "B": "mole / liter"},
        boundary_conditions={
            "A": BoundaryConditions1D.no_flux(),
            "B": BoundaryConditions1D.no_flux(),
        },
        parameters=reaction_parameters(),
        reactions=[first_order_reaction()],
        diffusion_symbols={"A": "D", "B": "D"},
    )

    result = engine.simulate(
        initial_fields={
            "A": Q_(initial_a, "mole / liter"),
            "B": Q_(np.zeros_like(initial_a), "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(1.0, "second")),
        t_eval=Q_(np.linspace(0.0, 1.0, 11), "second"),
        solver_settings=SolverSettings(max_step=Q_(0.01, "second")),
    )
    expected_average = Q_(float(np.mean(initial_a) * np.exp(-0.2)), "mole / liter")

    assert result.success
    assert validate_diffusion_smooths_gradient(result, field="A").passed
    assert validate_spatial_average_close_to_expected(
        result,
        field="A",
        expected_average=expected_average,
        relative_tolerance=Q_(1e-5, "dimensionless"),
    ).passed


def test_fixed_value_boundary_conditions_are_explicit() -> None:
    boundaries = BoundaryConditions1D(
        left=BoundaryCondition("fixed_value", Q_(1.0, "mole / liter")),
        right=BoundaryCondition("no_flux"),
    )
    engine = ReactionDiffusionEngine1D(
        grid=grid(),
        field_units={"C": "mole / liter"},
        boundary_conditions={"C": boundaries},
        parameters=diffusion_parameters(),
        diffusion_symbols={"C": "D"},
    )

    result = engine.simulate(
        initial_fields={"C": Q_(np.zeros(20), "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(5.0, "second")),
        t_eval=Q_(np.linspace(0.0, 5.0, 11), "second"),
    )

    assert result.success
    assert result.field_at_final_time("C").magnitude[0] > result.field_at_final_time("C").magnitude[-1]

