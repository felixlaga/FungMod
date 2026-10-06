"""Conservative finite-volume operators on plain numpy arrays for the mycelium core.

Every operator works on magnitudes only, in any number of supported
dimensions, with ``no_flux`` or ``periodic`` boundaries per axis. Face
quantities are arrays with one more entry than cells along their axis;
``divergence`` turns per-axis face fluxes into a cell tendency, so every
transport process built from these operators conserves the discrete integral
under no-flux boundaries to rounding.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from fungal_model.mycelium.grid import SpatialGrid


def _axis_slices(ndim: int, axis: int, item: slice | int) -> tuple[slice | int, ...]:
    slices: list[slice | int] = [slice(None)] * ndim
    slices[axis] = item
    return tuple(slices)


def face_values(values: np.ndarray, *, axis: int, periodic: bool) -> tuple[np.ndarray, np.ndarray]:
    """Cell values on the lower and upper side of every face along ``axis``.

    Under periodic boundaries the first and last faces see the wrapped
    neighbour; under no-flux boundaries the outer faces see the boundary cell
    on both sides, which makes every gradient there vanish.
    """

    ndim = values.ndim
    if periodic:
        lower = np.concatenate([values[_axis_slices(ndim, axis, slice(-1, None))], values], axis=axis)
        upper = np.concatenate([values, values[_axis_slices(ndim, axis, slice(0, 1))]], axis=axis)
    else:
        lower = np.concatenate([values[_axis_slices(ndim, axis, slice(0, 1))], values], axis=axis)
        upper = np.concatenate([values, values[_axis_slices(ndim, axis, slice(-1, None))]], axis=axis)
    return lower, upper


def face_gradient(values: np.ndarray, *, axis: int, cell_width: float, periodic: bool) -> np.ndarray:
    """``(upper - lower) / dx`` at every face along ``axis`` (zero on no-flux outer faces)."""

    lower, upper = face_values(values, axis=axis, periodic=periodic)
    return (upper - lower) / cell_width


def harmonic_face_mean(values: np.ndarray, *, axis: int, periodic: bool) -> np.ndarray:
    """Harmonic mean of the two cells at every face; zero when either side is zero."""

    lower, upper = face_values(values, axis=axis, periodic=periodic)
    product = lower * upper
    total = lower + upper
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = np.where(total > 0.0, 2.0 * product / np.where(total > 0.0, total, 1.0), 0.0)
    return mean


def upwind_face_flux(values: np.ndarray, velocity_faces: np.ndarray, *, axis: int, periodic: bool) -> np.ndarray:
    """First-order upwind advective flux ``v * value`` at every face along ``axis``.

    The upwind cell is the lower cell for a positive face velocity and the
    upper cell otherwise. Under no-flux boundaries the outer faces carry no
    flux whatever the velocity.
    """

    lower, upper = face_values(values, axis=axis, periodic=periodic)
    flux = np.where(velocity_faces > 0.0, velocity_faces * lower, velocity_faces * upper)
    if not periodic:
        ndim = values.ndim
        flux[_axis_slices(ndim, axis, 0)] = 0.0
        flux[_axis_slices(ndim, axis, -1)] = 0.0
    return flux


def divergence(
    face_fluxes: Sequence[np.ndarray],
    *,
    grid: SpatialGrid | None = None,
    cell_widths: Sequence[float] | None = None,
) -> np.ndarray:
    """Cell tendency of outward face fluxes under the conservation law ``du/dt = -div F``.

    With ``grid`` the geometry's face weights are used (``1 / dx`` per axis on a
    cartesian grid, ``r_face / (r_centre dr)`` on an axisymmetric one); with
    ``cell_widths`` alone the cartesian form ``-sum_axis (F_upper - F_lower) / dx``.
    """

    if (grid is None) == (cell_widths is None):
        raise ValueError("divergence takes exactly one of grid or cell_widths.")
    tendency: np.ndarray | None = None
    for axis, flux in enumerate(face_fluxes):
        ndim = flux.ndim
        lower = flux[_axis_slices(ndim, axis, slice(0, -1))]
        upper = flux[_axis_slices(ndim, axis, slice(1, None))]
        if grid is not None:
            weight_lower, weight_upper = grid.face_weights(axis)
            change = -(weight_upper * upper - weight_lower * lower)
        else:
            assert cell_widths is not None
            change = -(upper - lower) / cell_widths[axis]
        tendency = change if tendency is None else tendency + change
    if tendency is None:
        raise ValueError("divergence needs at least one axis of face fluxes.")
    expected = len(grid.shape) if grid is not None else len(cell_widths or ())
    if len(face_fluxes) != expected:
        raise ValueError(f"divergence received {len(face_fluxes)} face-flux arrays for {expected} axes.")
    return tendency


def diffusive_tendency(values: np.ndarray, *, grid: SpatialGrid, diffusivity: float) -> np.ndarray:
    """``D laplacian(values)`` assembled from face gradients (conservative under no-flux)."""

    fluxes = [
        -diffusivity * face_gradient(values, axis=axis, cell_width=width, periodic=periodic)
        for axis, (width, periodic) in enumerate(zip(grid.cell_widths, grid.periodic_axes, strict=True))
    ]
    return divergence(fluxes, grid=grid)


def drift_face_velocities(potential: np.ndarray, *, grid: SpatialGrid, mobility: float) -> list[np.ndarray]:
    """Face velocities ``mobility * grad(potential)`` per axis (zero on no-flux outer faces)."""

    velocities = []
    for axis, (width, periodic) in enumerate(zip(grid.cell_widths, grid.periodic_axes, strict=True)):
        velocities.append(mobility * face_gradient(potential, axis=axis, cell_width=width, periodic=periodic))
    return velocities


def spatial_integral(values: np.ndarray, *, grid: SpatialGrid) -> float:
    """Finite-volume integral over the whole grid (value units times metre to the measure dimension)."""

    array = np.asarray(values, dtype=float)
    if array.shape[-grid.ndim :] != grid.shape:
        raise ValueError(f"Field shape {array.shape} does not end with the grid shape {grid.shape}.")
    return float(np.sum(array * grid.cell_measures))


__all__ = [
    "diffusive_tendency",
    "divergence",
    "drift_face_velocities",
    "face_gradient",
    "face_values",
    "harmonic_face_mean",
    "spatial_integral",
    "upwind_face_flux",
]
