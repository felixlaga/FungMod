"""Field declarations and the build-time context of the spatial mycelium core."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.errors import InvalidMechanismError
from fungal_model.core.kernels import conversion_factor, magnitude_in
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_
from fungal_model.mycelium.grid import SpatialGrid

#: A kernel that returns the tendency of every field (field units per time
#: unit) as an array shaped ``(fields, *grid.shape)`` for the projected
#: field array of the same shape.
TendencyKernel = Callable[[float, np.ndarray], np.ndarray]
#: A kernel that returns one per-cell rate array shaped ``grid.shape`` in the
#: process's declared rate units.
RateFieldKernel = Callable[[float, np.ndarray], np.ndarray]


@dataclass(frozen=True)
class FieldSpec:
    """One spatial field: a density, concentration or count per cell."""

    name: str
    units: str
    description: str = ""
    role: str = "field"

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise InvalidMechanismError("FieldSpec.name must be provided.")
        if not str(self.units).strip():
            raise InvalidMechanismError(f"FieldSpec({self.name}).units must be provided.")
        Q_(1, self.units)

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "units": self.units, "description": self.description, "role": self.role}


@dataclass(frozen=True)
class FieldKernelContext:
    """What a field process needs to compile its kernels once, before integration.

    ``field_index`` maps every model field to its row in the field array and
    ``field_units`` records the units that row carries. Lengths inside kernels
    are metres (the grid's cell widths) and times are ``time_units``.
    """

    field_index: Mapping[str, int]
    field_units: Mapping[str, str]
    time_units: str
    parameters: ParameterSet
    grid: SpatialGrid

    def field_slot(self, name: str, units: str) -> tuple[int, float]:
        """Row of ``name`` and the factor converting its stored units to ``units``."""

        if name not in self.field_index:
            raise KeyError(f"Field {name!r} is not part of the compiled model.")
        return self.field_index[name], conversion_factor(self.field_units[name], units, name=name)

    def stored_units(self, name: str) -> str:
        if name not in self.field_units:
            raise KeyError(f"Field {name!r} is not part of the compiled model.")
        return self.field_units[name]

    def parameter(self, symbol: str, units: str) -> float:
        """Scalar parameter value in ``units`` with the provenance checks of ``require_quantity``."""

        return magnitude_in(self.parameters.require_quantity(symbol, units), units, name=symbol)

    def factor(self, from_units: str, to_units: str, *, name: str) -> float:
        return conversion_factor(from_units, to_units, name=name)

    def to_dict(self) -> dict[str, Any]:
        return {"fields": dict(self.field_units), "time_units": self.time_units, "grid": self.grid.to_dict()}


__all__ = ["FieldKernelContext", "FieldSpec", "RateFieldKernel", "TendencyKernel"]
