"""Colony observables on a square scan window.

Image-derived colony measures such as those of De Ligne et al. 2019 are
graph quantities: the number of tips outside the inoculum disc (the disc is
removed from the images before counting), and the mycelial area as the
convex hull of all graph nodes, which for a colony with circular symmetry is
the disc of the outermost detected hyphae, truncated by the scan window and
never smaller than the inoculum disc whose boundary nodes the hull contains.

These functions evaluate such observables on a :class:`MyceliumResult`: in
closed form on an axisymmetric grid, and by direct summation and a convex
hull on a two-dimensional cartesian grid whose extent is the window. Every
constant (inoculum radius, window half side, detection density) is a declared
quantity of the caller; nothing here knows an organism or a dataset.
"""

from __future__ import annotations

import numpy as np

from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.mycelium.model import MyceliumResult

DISC_BOUNDARY_POINTS = 64


def disc_area_in_square(radius: float, half_side: float) -> float:
    """Area of the intersection of a centred disc with a square of the given half side (same length unit)."""

    if radius < 0.0 or half_side <= 0.0:
        raise ValueError("disc_area_in_square needs a non-negative radius and a positive half side.")
    if radius <= half_side:
        return float(np.pi * radius**2)
    if radius >= half_side * np.sqrt(2.0):
        return float(4.0 * half_side**2)
    segment = radius**2 * np.arccos(half_side / radius) - half_side * np.sqrt(radius**2 - half_side**2)
    return float(np.pi * radius**2 - 4.0 * segment)


def circle_length_in_square(radius: float, half_side: float) -> float:
    """Length of a centred circle inside a square of the given half side (the derivative of the disc area)."""

    if radius < 0.0 or half_side <= 0.0:
        raise ValueError("circle_length_in_square needs a non-negative radius and a positive half side.")
    if radius <= half_side:
        return float(2.0 * np.pi * radius)
    if radius >= half_side * np.sqrt(2.0):
        return 0.0
    return float(2.0 * np.pi * radius - 8.0 * radius * np.arccos(half_side / radius))


def _metres(quantity: Quantity, name: str) -> float:
    value = float(assert_compatible(require_quantity(quantity, name=name), "meter", name=name).magnitude)
    if not np.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be a finite non-negative length.")
    return value


def _cartesian_window(result: MyceliumResult, half_side: float) -> tuple[np.ndarray, np.ndarray]:
    grid = result.grid
    if grid.geometry != "cartesian" or grid.ndim != 2:
        raise ValueError("Colony observables need an axisymmetric grid or a two-dimensional cartesian grid.")
    sides = [float(length.quantity.to("meter").magnitude) for length in grid.axis_lengths if length.quantity is not None]
    if any(abs(side - 2.0 * half_side) > 1e-9 * max(side, 1e-12) for side in sides):
        raise ValueError(
            f"The cartesian grid ({sides} m) must be the square window of side {2.0 * half_side} m."
        )
    x, y = np.meshgrid(*grid.coordinates, indexing="ij")
    centre = [0.5 * side for side in sides]
    return np.hypot(x - centre[0], y - centre[1]), np.stack([x - centre[0], y - centre[1]], axis=-1)


def colony_count_outside_disc(
    result: MyceliumResult,
    *,
    field: str,
    disc_radius: Quantity,
    window_half_side: Quantity,
) -> Quantity:
    """Integral of a per-area field over the window outside the inoculum disc, at every output time.

    Cells are counted by their centres. The result carries the field's units
    times square metres; for a density per area it is a pure count.
    """

    values = result.fields[field]
    magnitudes = np.asarray(values.magnitude, dtype=float)
    r_disc = _metres(disc_radius, "disc_radius")
    half = _metres(window_half_side, "window_half_side")
    grid = result.grid
    if grid.geometry == "axisymmetric":
        radii = grid.coordinates[0]
        width = grid.cell_widths[0]
        weights = np.array([circle_length_in_square(r, half) * width if r > r_disc else 0.0 for r in radii])
        totals = (magnitudes.reshape(magnitudes.shape[0], -1) * weights).sum(axis=1)
    else:
        distance, _ = _cartesian_window(result, half)
        weights = np.where(distance > r_disc, grid.cell_measures, 0.0).reshape(-1)
        totals = (magnitudes.reshape(magnitudes.shape[0], -1) * weights).sum(axis=1)
    return Q_(totals, f"({values.units}) * meter ** 2")


def colony_hull_radius(
    result: MyceliumResult,
    *,
    field: str,
    detection_density: Quantity,
    disc_radius: Quantity,
) -> Quantity:
    """Radius of the outermost cell whose field reaches the detection density, floored at the disc radius.

    The radius is the distance of the farthest detected cell centre from the
    colony centre in both geometries, so the two agree to within a cell.
    """

    values = result.fields[field]
    level = float(assert_compatible(require_quantity(detection_density, name="detection_density"), str(values.units), name="detection_density").magnitude)
    magnitudes = np.asarray(values.magnitude, dtype=float)
    r_disc = _metres(disc_radius, "disc_radius")
    grid = result.grid
    if grid.geometry == "axisymmetric":
        reach = np.where(magnitudes >= level, grid.coordinates[0], 0.0)
    else:
        if grid.ndim != 2 or grid.geometry != "cartesian":
            raise ValueError("Colony observables need an axisymmetric grid or a two-dimensional cartesian grid.")
        x, y = np.meshgrid(*grid.coordinates, indexing="ij")
        sides = [float(length.quantity.to("meter").magnitude) for length in grid.axis_lengths if length.quantity is not None]
        distance = np.hypot(x - 0.5 * sides[0], y - 0.5 * sides[1])
        reach = np.where(magnitudes >= level, distance, 0.0)
    radii = np.maximum(reach.reshape(magnitudes.shape[0], -1).max(axis=1), r_disc)
    return Q_(radii, "meter")


def colony_hull_area(
    result: MyceliumResult,
    *,
    field: str,
    detection_density: Quantity,
    disc_radius: Quantity,
    window_half_side: Quantity,
) -> Quantity:
    """Convex-hull area of the detected colony and the inoculum boundary inside the window, at every output time.

    Axisymmetric grids use the window-truncated disc of :func:`colony_hull_radius`;
    two-dimensional cartesian grids take the convex hull of the detected cell
    centres and the disc boundary.
    """

    from scipy.spatial import ConvexHull

    values = result.fields[field]
    level = float(assert_compatible(require_quantity(detection_density, name="detection_density"), str(values.units), name="detection_density").magnitude)
    magnitudes = np.asarray(values.magnitude, dtype=float)
    r_disc = _metres(disc_radius, "disc_radius")
    half = _metres(window_half_side, "window_half_side")
    grid = result.grid
    if grid.geometry == "axisymmetric":
        radii = np.asarray(colony_hull_radius(result, field=field, detection_density=detection_density, disc_radius=disc_radius).magnitude)
        areas = np.array([disc_area_in_square(float(radius), half) for radius in radii])
        return Q_(areas, "meter ** 2")
    _distance, offsets = _cartesian_window(result, half)
    angles = np.linspace(0.0, 2.0 * np.pi, DISC_BOUNDARY_POINTS, endpoint=False)
    boundary = np.stack([r_disc * np.cos(angles), r_disc * np.sin(angles)], axis=-1)
    areas = []
    for step in range(magnitudes.shape[0]):
        detected = offsets[magnitudes[step] >= level]
        points = np.vstack([boundary, detected]) if detected.size else boundary
        areas.append(float(ConvexHull(points).volume))
    return Q_(np.array(areas), "meter ** 2")


__all__ = [
    "DISC_BOUNDARY_POINTS",
    "circle_length_in_square",
    "colony_count_outside_disc",
    "colony_hull_area",
    "colony_hull_radius",
    "disc_area_in_square",
]
