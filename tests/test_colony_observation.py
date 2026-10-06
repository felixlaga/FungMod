"""Colony observables on a square window: closed forms, counts outside a disc, hull radius and area."""

from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.numerics import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.mycelium import (
    MyceliumResult,
    SpatialGrid,
    circle_length_in_square,
    colony_count_outside_disc,
    colony_hull_area,
    colony_hull_radius,
    disc_area_in_square,
)
from fungal_model.mycelium.benchmarks import TIP_UNITS, artificial_parameter

HALF = 20.0


def _result(grid: SpatialGrid, field: np.ndarray, units: str = TIP_UNITS) -> MyceliumResult:
    return MyceliumResult(
        time=Q_(np.array([0.0]), "hour"),
        fields={"tips": Q_(field[np.newaxis], units)},
        initial_fields={"tips": Q_(field, units)},
        grid=grid,
        process_rates=None,
        solver_settings=SolverSettings(),
        solver_metadata={},
        assumptions=[],
        model_version="test",
        maturity="exploratory",
    )


def test_disc_area_and_circle_length_in_a_square_are_consistent_closed_forms() -> None:
    assert disc_area_in_square(10.0, HALF) == pytest.approx(np.pi * 100.0)
    assert disc_area_in_square(HALF * np.sqrt(2.0), HALF) == pytest.approx(4.0 * HALF**2)
    assert disc_area_in_square(50.0, HALF) == pytest.approx(4.0 * HALF**2)
    assert circle_length_in_square(10.0, HALF) == pytest.approx(2.0 * np.pi * 10.0)
    assert circle_length_in_square(HALF * np.sqrt(2.0), HALF) == pytest.approx(0.0, abs=1e-9)
    assert circle_length_in_square(HALF, HALF) == pytest.approx(2.0 * np.pi * HALF)
    for radius in (21.0, 24.0, 27.0):
        step = 1e-5
        derivative = (disc_area_in_square(radius + step, HALF) - disc_area_in_square(radius - step, HALF)) / (2.0 * step)
        assert derivative == pytest.approx(circle_length_in_square(radius, HALF), rel=1e-5)
        assert np.pi * HALF**2 < disc_area_in_square(radius, HALF) < 4.0 * HALF**2
    with pytest.raises(ValueError):
        disc_area_in_square(-1.0, HALF)


def test_counts_outside_the_disc_agree_between_geometries_for_a_uniform_density() -> None:
    density, disc = 3.0, 5.0
    radial = SpatialGrid.axisymmetric(artificial_parameter("R", HALF * np.sqrt(2.0), "millimeter"), 2000)
    count = colony_count_outside_disc(
        _result(radial, np.full(radial.shape, density)),
        field="tips", disc_radius=Q_(disc, "millimeter"), window_half_side=Q_(HALF, "millimeter"),
    ).to("dimensionless").magnitude[0]
    expected = density * (4.0 * HALF**2 - np.pi * disc**2)
    assert count == pytest.approx(expected, rel=2e-3)
    square = SpatialGrid.no_flux((artificial_parameter("L", 2 * HALF, "millimeter"),) * 2, (200, 200))
    count_2d = colony_count_outside_disc(
        _result(square, np.full(square.shape, density)),
        field="tips", disc_radius=Q_(disc, "millimeter"), window_half_side=Q_(HALF, "millimeter"),
    ).to("dimensionless").magnitude[0]
    assert count_2d == pytest.approx(expected, rel=5e-3)
    with pytest.raises(ValueError, match="square window"):
        colony_count_outside_disc(
            _result(square, np.full(square.shape, density)),
            field="tips", disc_radius=Q_(disc, "millimeter"), window_half_side=Q_(HALF / 2, "millimeter"),
        )


def test_hull_radius_and_area_follow_the_outermost_detected_cell_and_never_shrink_below_the_disc() -> None:
    radial = SpatialGrid.axisymmetric(artificial_parameter("R", HALF * np.sqrt(2.0), "millimeter"), 283)
    radii_mm = radial.coordinates[0] * 1e3
    width_mm = radial.cell_widths[0] * 1e3
    for extent, inside_window in ((12.0, True), (24.0, False)):
        field = np.where(radii_mm < extent, 2.0, 0.0)
        hull = colony_hull_radius(_result(radial, field), field="tips", detection_density=Q_(1.0, TIP_UNITS), disc_radius=Q_(5.0, "millimeter"))
        radius_mm = hull.to("millimeter").magnitude[0]
        assert abs(radius_mm - extent) <= width_mm
        area = colony_hull_area(
            _result(radial, field), field="tips", detection_density=Q_(1.0, TIP_UNITS),
            disc_radius=Q_(5.0, "millimeter"), window_half_side=Q_(HALF, "millimeter"),
        ).to("millimeter ** 2").magnitude[0]
        assert area == pytest.approx(disc_area_in_square(radius_mm, HALF))
        assert bool(area < np.pi * HALF**2) is inside_window
    empty = colony_hull_area(
        _result(radial, np.zeros(radial.shape)), field="tips", detection_density=Q_(1.0, TIP_UNITS),
        disc_radius=Q_(5.0, "millimeter"), window_half_side=Q_(HALF, "millimeter"),
    ).to("millimeter ** 2").magnitude[0]
    assert empty == pytest.approx(np.pi * 25.0)
    square = SpatialGrid.no_flux((artificial_parameter("L", 2 * HALF, "millimeter"),) * 2, (160, 160))
    x, y = np.meshgrid(*[axis * 1e3 - HALF for axis in square.coordinates], indexing="ij")
    field_2d = np.where(np.hypot(x, y) < 12.0, 2.0, 0.0)
    area_2d = colony_hull_area(
        _result(square, field_2d), field="tips", detection_density=Q_(1.0, TIP_UNITS),
        disc_radius=Q_(5.0, "millimeter"), window_half_side=Q_(HALF, "millimeter"),
    ).to("millimeter ** 2").magnitude[0]
    assert area_2d == pytest.approx(np.pi * 144.0, rel=0.02)
    radius_2d = colony_hull_radius(_result(square, field_2d), field="tips", detection_density=Q_(1.0, TIP_UNITS), disc_radius=Q_(5.0, "millimeter"))
    assert radius_2d.to("millimeter").magnitude[0] == pytest.approx(12.0, abs=0.3)
