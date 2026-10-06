"""Uniform finite-volume grids in one, two or three dimensions for the spatial mycelium core.

The grid holds plain floats: cell widths in metres, boundary kinds per axis.
Every unit conversion happens once when a model is compiled, never inside a
right-hand side. Boundaries are declared per axis for the whole grid; a field
that needs a fixed boundary value is not supported by this core yet and is
refused when declared (see :mod:`fungal_model.mycelium.operators`).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from operator import mul
from typing import Any

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.units import assert_compatible
from fungal_model.transport.geometry import BoundaryConditions1D

SUPPORTED_DIMENSIONS = (1, 2, 3)
LENGTH_UNITS = "meter"
SUPPORTED_BOUNDARY_KINDS = ("no_flux", "periodic")


@dataclass(frozen=True)
class SpatialGrid:
    """Cell-centred uniform grid with one explicit boundary pair per axis."""

    axis_lengths: tuple[Parameter, ...]
    shape: tuple[int, ...]
    boundaries: tuple[BoundaryConditions1D, ...]

    def __post_init__(self) -> None:
        if len(self.shape) not in SUPPORTED_DIMENSIONS:
            raise ValueError(f"SpatialGrid supports {SUPPORTED_DIMENSIONS} dimensions, not {len(self.shape)}.")
        if len(self.axis_lengths) != len(self.shape) or len(self.boundaries) != len(self.shape):
            raise ValueError("axis_lengths, shape and boundaries must have the same dimensionality.")
        if any(int(cells) < 2 for cells in self.shape):
            raise ValueError("Every grid axis requires at least two cells.")
        for index, length in enumerate(self.axis_lengths):
            if length.quantity is None:
                raise ValueError(f"Grid axis length {index} must be known.")
            value = float(assert_compatible(length.quantity, LENGTH_UNITS, name=length.symbol).magnitude)
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError("Grid axis lengths must be finite and positive.")
        for index, boundary in enumerate(self.boundaries):
            for side in (boundary.left, boundary.right):
                if side.kind not in SUPPORTED_BOUNDARY_KINDS:
                    raise ValueError(
                        f"Grid axis {index} declares a {side.kind!r} boundary; the mycelium core supports "
                        f"{SUPPORTED_BOUNDARY_KINDS} only."
                    )

    @classmethod
    def no_flux(cls, axis_lengths: tuple[Parameter, ...], shape: tuple[int, ...]) -> "SpatialGrid":
        return cls(tuple(axis_lengths), tuple(int(cells) for cells in shape), tuple(BoundaryConditions1D.no_flux() for _ in shape))

    @classmethod
    def periodic(cls, axis_lengths: tuple[Parameter, ...], shape: tuple[int, ...]) -> "SpatialGrid":
        return cls(tuple(axis_lengths), tuple(int(cells) for cells in shape), tuple(BoundaryConditions1D.periodic() for _ in shape))

    @property
    def ndim(self) -> int:
        return len(self.shape)

    @property
    def cell_count(self) -> int:
        return int(np.prod(self.shape))

    @property
    def cell_widths(self) -> tuple[float, ...]:
        """Cell width per axis in metres."""

        widths = []
        for length, cells in zip(self.axis_lengths, self.shape, strict=True):
            quantity = length.quantity
            assert quantity is not None
            widths.append(float(assert_compatible(quantity, LENGTH_UNITS, name=length.symbol).magnitude) / int(cells))
        return tuple(widths)

    @property
    def periodic_axes(self) -> tuple[bool, ...]:
        return tuple(boundary.left.kind == "periodic" for boundary in self.boundaries)

    @property
    def cell_measure(self) -> float:
        """Cell length, area or volume in metres to the power of the dimension."""

        return float(reduce(mul, self.cell_widths, 1.0))

    @property
    def total_measure(self) -> float:
        return self.cell_measure * self.cell_count

    @property
    def coordinates(self) -> tuple[np.ndarray, ...]:
        """Cell-centre coordinates per axis in metres."""

        return tuple(
            (np.arange(int(cells), dtype=float) + 0.5) * width
            for cells, width in zip(self.shape, self.cell_widths, strict=True)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ndim": self.ndim,
            "shape": list(self.shape),
            "axis_lengths": [length.to_dict() for length in self.axis_lengths],
            "cell_widths_m": list(self.cell_widths),
            "boundaries": [boundary.to_dict() for boundary in self.boundaries],
        }


__all__ = ["LENGTH_UNITS", "SUPPORTED_BOUNDARY_KINDS", "SUPPORTED_DIMENSIONS", "SpatialGrid"]
