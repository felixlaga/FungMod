"""Uniform Cartesian finite-volume geometry and diffusion in two or three dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from operator import mul
from typing import Any, cast

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.transport.diffusion import (
    FINITE_DIFFERENCE_CENTER_STENCIL_FACTOR,
    FINITE_VOLUME_BOUNDARY_FACE_FACTOR,
)
from fungal_model.transport.geometry import BoundaryConditions1D


SUPPORTED_CARTESIAN_DIMENSIONS = (2, 3)


@dataclass(frozen=True)
class UniformCartesianGrid:
    """Cell-centered uniform Cartesian grid in exactly two or three dimensions."""

    axis_lengths: tuple[Parameter, ...]
    shape: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.shape) not in SUPPORTED_CARTESIAN_DIMENSIONS:
            raise ValueError("UniformCartesianGrid supports exactly 2D or 3D grids.")
        if len(self.axis_lengths) != len(self.shape):
            raise ValueError("axis_lengths and shape must have the same dimensionality.")
        if any(cells < 2 for cells in self.shape):
            raise ValueError("Every Cartesian grid axis requires at least two cells.")
        for index, length in enumerate(self.axis_lengths):
            if length.quantity is None:
                raise ValueError(f"Cartesian axis length {index} must be known.")
            value = assert_compatible(length.quantity, "meter", name=length.symbol)
            if not np.isfinite(float(value.magnitude)) or float(value.magnitude) <= 0.0:
                raise ValueError("Cartesian axis lengths must be finite and positive.")

    @property
    def ndim(self) -> int:
        return len(self.shape)

    @property
    def cell_widths(self) -> tuple[Quantity, ...]:
        return tuple(
            assert_compatible(length.quantity / cells, "meter", name=f"axis {axis} cell width")
            for axis, (length, cells) in enumerate(zip(self.axis_lengths, self.shape, strict=True))
            if length.quantity is not None
        )

    @property
    def coordinates(self) -> tuple[Quantity, ...]:
        return tuple(
            Q_((np.arange(cells, dtype=float) + 0.5) * width.magnitude, width.units)
            for cells, width in zip(self.shape, self.cell_widths, strict=True)
        )

    @property
    def cell_measure(self) -> Quantity:
        return reduce(mul, self.cell_widths)

    @property
    def total_measure(self) -> Quantity:
        return self.cell_measure * int(np.prod(self.shape))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ndim": self.ndim,
            "shape": list(self.shape),
            "axis_lengths": [length.to_dict() for length in self.axis_lengths],
            "cell_widths": [
                {"value": float(width.magnitude), "units": str(width.units)}
                for width in self.cell_widths
            ],
        }


@dataclass(frozen=True)
class BoundaryConditionsND:
    """One explicit lower/upper boundary pair per Cartesian axis."""

    axes: tuple[BoundaryConditions1D, ...]

    def __post_init__(self) -> None:
        if len(self.axes) not in SUPPORTED_CARTESIAN_DIMENSIONS:
            raise ValueError("BoundaryConditionsND supports exactly 2D or 3D grids.")

    @classmethod
    def no_flux(cls, ndim: int) -> "BoundaryConditionsND":
        if ndim not in SUPPORTED_CARTESIAN_DIMENSIONS:
            raise ValueError("No-flux Cartesian boundaries require ndim=2 or ndim=3.")
        return cls(tuple(BoundaryConditions1D.no_flux() for _ in range(ndim)))

    @classmethod
    def periodic(cls, ndim: int) -> "BoundaryConditionsND":
        if ndim not in SUPPORTED_CARTESIAN_DIMENSIONS:
            raise ValueError("Periodic Cartesian boundaries require ndim=2 or ndim=3.")
        return cls(tuple(BoundaryConditions1D.periodic() for _ in range(ndim)))

    def to_dict(self) -> dict[str, Any]:
        return {"axes": [axis.to_dict() for axis in self.axes]}


def finite_volume_laplacian_nd(
    values: Quantity,
    *,
    grid: UniformCartesianGrid,
    boundary_conditions: BoundaryConditionsND,
) -> Quantity:
    """Return the Cartesian finite-volume Laplacian of a 2D or 3D field."""

    field = require_quantity(values, name="values")
    magnitudes = np.asarray(field.magnitude, dtype=float)
    if magnitudes.shape != grid.shape:
        raise ValueError(
            f"Cartesian field shape {magnitudes.shape} does not match grid shape {grid.shape}."
        )
    if len(boundary_conditions.axes) != grid.ndim:
        raise ValueError("Boundary-condition dimensionality does not match the Cartesian grid.")
    laplacian = np.zeros(grid.shape, dtype=float)
    for axis, (width, boundaries) in enumerate(
        zip(grid.cell_widths, boundary_conditions.axes, strict=True)
    ):
        laplacian += _axis_laplacian(
            magnitudes,
            axis=axis,
            cell_width=float(width.to("meter").magnitude),
            boundaries=boundaries,
            field_units=str(field.units),
        )
    return Q_(laplacian, f"{field.units} / meter ** 2")


def _axis_laplacian(
    values: np.ndarray,
    *,
    axis: int,
    cell_width: float,
    boundaries: BoundaryConditions1D,
    field_units: str,
) -> np.ndarray:
    dx2 = cell_width**2
    center_factor = float(
        cast(Quantity, FINITE_DIFFERENCE_CENTER_STENCIL_FACTOR.quantity)
        .to("dimensionless")
        .magnitude
    )
    if boundaries.left.kind == "periodic":
        return (
            np.roll(values, -1, axis=axis)
            - center_factor * values
            + np.roll(values, 1, axis=axis)
        ) / dx2

    output = np.zeros_like(values, dtype=float)
    interior: list[slice | int] = [slice(None)] * values.ndim
    lower: list[slice | int] = [slice(None)] * values.ndim
    center: list[slice | int] = [slice(None)] * values.ndim
    upper: list[slice | int] = [slice(None)] * values.ndim
    interior[axis] = slice(1, -1)
    lower[axis] = slice(0, -2)
    center[axis] = slice(1, -1)
    upper[axis] = slice(2, None)
    output[tuple(interior)] = (
        values[tuple(upper)]
        - center_factor * values[tuple(center)]
        + values[tuple(lower)]
    ) / dx2

    first: list[slice | int] = [slice(None)] * values.ndim
    second: list[slice | int] = [slice(None)] * values.ndim
    last: list[slice | int] = [slice(None)] * values.ndim
    penultimate: list[slice | int] = [slice(None)] * values.ndim
    first[axis] = 0
    second[axis] = 1
    last[axis] = -1
    penultimate[axis] = -2
    if boundaries.left.kind == "no_flux":
        output[tuple(first)] = (values[tuple(second)] - values[tuple(first)]) / dx2
    else:
        fixed = float(boundaries.left.value_as(field_units).magnitude)
        face_factor = float(
            cast(Quantity, FINITE_VOLUME_BOUNDARY_FACE_FACTOR.quantity)
            .to("dimensionless")
            .magnitude
        )
        output[tuple(first)] = (
            values[tuple(second)]
            - values[tuple(first)]
            - face_factor * (values[tuple(first)] - fixed)
        ) / dx2
    if boundaries.right.kind == "no_flux":
        output[tuple(last)] = (values[tuple(penultimate)] - values[tuple(last)]) / dx2
    else:
        fixed = float(boundaries.right.value_as(field_units).magnitude)
        face_factor = float(
            cast(Quantity, FINITE_VOLUME_BOUNDARY_FACE_FACTOR.quantity)
            .to("dimensionless")
            .magnitude
        )
        output[tuple(last)] = (
            values[tuple(penultimate)]
            - values[tuple(last)]
            + face_factor * (fixed - values[tuple(last)])
        ) / dx2
    return output


def spatial_integral_nd(values: Quantity, *, grid: UniformCartesianGrid) -> Quantity:
    """Return the finite-volume 2D area or 3D volume integral."""

    field = require_quantity(values, name="values")
    magnitudes = np.asarray(field.magnitude, dtype=float)
    if magnitudes.shape != grid.shape:
        raise ValueError(
            f"Cartesian field shape {magnitudes.shape} does not match grid shape {grid.shape}."
        )
    return Q_(float(np.sum(magnitudes)), field.units) * grid.cell_measure


__all__ = [
    "BoundaryConditionsND",
    "SUPPORTED_CARTESIAN_DIMENSIONS",
    "UniformCartesianGrid",
    "finite_volume_laplacian_nd",
    "spatial_integral_nd",
]
