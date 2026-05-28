"""Geometry and boundary-condition definitions for spatial models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity, assert_compatible

BoundaryKind = Literal["no_flux", "fixed_value", "periodic"]

CELL_CENTER_OFFSET = Parameter(
    name="cell-center coordinate offset",
    symbol="cell_center_offset",
    value=0.5,
    units="dimensionless",
    uncertainty=None,
    source="Definition of a finite-volume cell center at half a cell width from the cell face.",
    confidence_level="high",
    notes="Numerical geometry convention for Stage 8 1D grids.",
    measurement_method="definition",
)


@dataclass(frozen=True)
class BoundaryCondition:
    """One side of a 1D boundary condition."""

    kind: BoundaryKind
    value: Quantity | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("no_flux", "fixed_value", "periodic"):
            raise ValueError(f"Unsupported boundary condition kind: {self.kind}")
        if self.kind == "fixed_value" and self.value is None:
            raise ValueError("fixed_value boundary conditions require a value.")
        if self.kind != "fixed_value" and self.value is not None:
            raise ValueError(f"{self.kind} boundary conditions must not carry a value.")

    def value_as(self, units: str) -> Quantity:
        if self.value is None:
            raise ValueError(f"{self.kind} boundary condition has no fixed value.")
        return assert_compatible(self.value, units, name="boundary value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": None
            if self.value is None
            else {"value": self.value.magnitude, "units": str(self.value.units)},
        }


@dataclass(frozen=True)
class BoundaryConditions1D:
    """Left and right boundary conditions for one 1D field."""

    left: BoundaryCondition
    right: BoundaryCondition

    def __post_init__(self) -> None:
        if self.left.kind == "periodic" or self.right.kind == "periodic":
            if self.left.kind != "periodic" or self.right.kind != "periodic":
                raise ValueError("Periodic boundaries must be periodic on both sides.")

    @classmethod
    def no_flux(cls) -> "BoundaryConditions1D":
        return cls(BoundaryCondition("no_flux"), BoundaryCondition("no_flux"))

    @classmethod
    def periodic(cls) -> "BoundaryConditions1D":
        return cls(BoundaryCondition("periodic"), BoundaryCondition("periodic"))

    @classmethod
    def fixed(cls, value: Quantity) -> "BoundaryConditions1D":
        return cls(BoundaryCondition("fixed_value", value), BoundaryCondition("fixed_value", value))

    def to_dict(self) -> dict[str, Any]:
        return {"left": self.left.to_dict(), "right": self.right.to_dict()}


@dataclass(frozen=True)
class UniformGrid1D:
    """Cell-centered uniform 1D finite-volume grid."""

    length: Parameter
    n_cells: int

    def __post_init__(self) -> None:
        if self.n_cells < 2:
            raise ValueError("UniformGrid1D requires at least two cells.")
        if self.length.quantity is None:
            raise ValueError("UniformGrid1D length must be known.")
        length = assert_compatible(self.length.quantity, "meter", name=self.length.symbol)
        if float(length.magnitude) <= 0.0:
            raise ValueError("UniformGrid1D length must be positive.")

    @property
    def cell_width(self) -> Quantity:
        length_quantity = self.length.quantity
        if length_quantity is None:
            raise ValueError("UniformGrid1D length must be known.")
        return assert_compatible(
            length_quantity / self.n_cells,
            "meter",
            name="cell width",
        )

    @property
    def coordinates(self) -> Quantity:
        dx = self.cell_width
        offset = float(CELL_CENTER_OFFSET.quantity.to("dimensionless").magnitude)
        return Q_((np.arange(self.n_cells, dtype=float) + offset) * dx.magnitude, dx.units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "length": self.length.to_dict(),
            "n_cells": self.n_cells,
            "cell_width": {
                "value": self.cell_width.magnitude,
                "units": str(self.cell_width.units),
            },
        }


__all__ = [
    "BoundaryCondition",
    "BoundaryConditions1D",
    "BoundaryKind",
    "CELL_CENTER_OFFSET",
    "UniformGrid1D",
]
