"""Finite-difference diffusion operators for Stage 8 spatial models."""

from __future__ import annotations

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.transport.geometry import BoundaryConditions1D

FINITE_VOLUME_BOUNDARY_FACE_FACTOR = Parameter(
    name="finite-volume fixed-boundary face-distance factor",
    symbol="fixed_boundary_face_factor",
    value=2.0,
    units="dimensionless",
    uncertainty=None,
    source="Finite-volume geometry: a boundary face is half a cell width from the adjacent cell center.",
    confidence_level="high",
    notes="Used for fixed-value boundary fluxes in Stage 8 1D diffusion.",
    measurement_method="definition",
)

FINITE_DIFFERENCE_CENTER_STENCIL_FACTOR = Parameter(
    name="finite-difference center stencil factor",
    symbol="center_stencil_factor",
    value=2.0,
    units="dimensionless",
    uncertainty=None,
    source="Definition of the second-order centered finite-difference stencil.",
    confidence_level="high",
    notes="Used in u[i+1] - 2*u[i] + u[i-1].",
    measurement_method="definition",
)


def finite_volume_laplacian_1d(
    values: Quantity,
    *,
    cell_width: Quantity,
    boundary_conditions: BoundaryConditions1D,
) -> Quantity:
    """Return the 1D finite-volume Laplacian of a cell-centered field.

    The no-flux form conserves the discrete spatial integral exactly for
    diffusion-only dynamics. Fixed-value boundaries use a half-cell boundary
    distance.
    """

    field = require_quantity(values, name="values")
    dx = assert_compatible(cell_width, "meter", name="cell_width")
    magnitudes = np.asarray(field.magnitude, dtype=float)
    if magnitudes.ndim != 1:
        raise ValueError("finite_volume_laplacian_1d expects a one-dimensional field.")
    if magnitudes.size < 2:
        raise ValueError("finite_volume_laplacian_1d requires at least two cells.")
    dx2 = float(dx.magnitude) ** 2
    laplacian = np.zeros_like(magnitudes, dtype=float)

    if boundary_conditions.left.kind == "periodic":
        factor = float(FINITE_DIFFERENCE_CENTER_STENCIL_FACTOR.quantity.to("dimensionless").magnitude)
        laplacian = (np.roll(magnitudes, -1) - factor * magnitudes + np.roll(magnitudes, 1)) / dx2
        return Q_(laplacian, f"{field.units} / meter ** 2")

    if magnitudes.size > 2:
        factor = float(FINITE_DIFFERENCE_CENTER_STENCIL_FACTOR.quantity.to("dimensionless").magnitude)
        laplacian[1:-1] = (magnitudes[2:] - factor * magnitudes[1:-1] + magnitudes[:-2]) / dx2

    if boundary_conditions.left.kind == "no_flux":
        laplacian[0] = (magnitudes[1] - magnitudes[0]) / dx2
    else:
        fixed = boundary_conditions.left.value_as(str(field.units)).magnitude
        factor = float(FINITE_VOLUME_BOUNDARY_FACE_FACTOR.quantity.to("dimensionless").magnitude)
        laplacian[0] = (magnitudes[1] - magnitudes[0] - factor * (magnitudes[0] - fixed)) / dx2

    if boundary_conditions.right.kind == "no_flux":
        laplacian[-1] = (magnitudes[-2] - magnitudes[-1]) / dx2
    else:
        fixed = boundary_conditions.right.value_as(str(field.units)).magnitude
        factor = float(FINITE_VOLUME_BOUNDARY_FACE_FACTOR.quantity.to("dimensionless").magnitude)
        laplacian[-1] = (magnitudes[-2] - magnitudes[-1] + factor * (fixed - magnitudes[-1])) / dx2

    return Q_(laplacian, f"{field.units} / meter ** 2")


def spatial_integral_1d(values: Quantity, *, cell_width: Quantity) -> Quantity:
    """Return the finite-volume spatial integral ``sum(values) * dx``."""

    field = require_quantity(values, name="values")
    dx = assert_compatible(cell_width, "meter", name="cell_width")
    return Q_(float(np.sum(np.asarray(field.magnitude, dtype=float))), field.units) * dx


def spatial_variance(values: Quantity) -> Quantity:
    """Return variance over cells while preserving squared units."""

    field = require_quantity(values, name="values")
    magnitudes = np.asarray(field.magnitude, dtype=float)
    return Q_(float(np.var(magnitudes)), field.units * field.units)


__all__ = [
    "FINITE_VOLUME_BOUNDARY_FACE_FACTOR",
    "FINITE_DIFFERENCE_CENTER_STENCIL_FACTOR",
    "finite_volume_laplacian_1d",
    "spatial_integral_1d",
    "spatial_variance",
]
