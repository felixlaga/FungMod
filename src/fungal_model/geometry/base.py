"""Geometry abstractions for well-mixed and spatial models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible


def geometry_assumption() -> Assumption:
    return Assumption(
        name="explicit geometry metadata",
        description="Model geometry is supplied as a first-class object rather than hidden in rate constants.",
        justification="Surface/volume coupling, spatial grids, and boundary conditions must be explicit.",
        known_limitations="Base geometry metadata does not itself solve transport or morphology dynamics.",
        source="FungMod geometry abstraction design.",
    )


@dataclass(frozen=True)
class Geometry:
    """Base geometry metadata."""

    name: str
    geometry_type: str
    volume: Quantity | None = None
    surface_area: Quantity | None = None
    boundary_conditions: Mapping[str, Any] = field(default_factory=dict)
    assumptions: tuple[Assumption, ...] = field(default_factory=lambda: (geometry_assumption(),))
    source: str | None = None
    notes: str = ""

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError(f"Geometry {self.name!r} is missing a source.")
        if self.volume is not None:
            volume = assert_compatible(self.volume, "meter ** 3", name="geometry.volume")
            if float(volume.magnitude) <= 0:
                raise ValueError("Geometry volume must be positive.")
        if self.surface_area is not None:
            area = assert_compatible(self.surface_area, "meter ** 2", name="geometry.surface_area")
            if float(area.magnitude) < 0:
                raise ValueError("Geometry surface area must be non-negative.")

    @property
    def is_spatial(self) -> bool:
        return False

    @property
    def spatial_grid(self) -> Any | None:
        return None

    @property
    def area_volume_ratio(self) -> Quantity | None:
        if self.surface_area is None or self.volume is None:
            return None
        return assert_compatible(
            self.surface_area / self.volume,
            "1 / meter",
            name="geometry.area_volume_ratio",
        )

    def to_dict(self) -> dict[str, Any]:
        ratio = self.area_volume_ratio
        return {
            "name": self.name,
            "geometry_type": self.geometry_type,
            "volume": _quantity_dict(self.volume),
            "surface_area": _quantity_dict(self.surface_area),
            "area_volume_ratio": _quantity_dict(ratio),
            "is_spatial": self.is_spatial,
            "boundary_conditions": {
                key: value.to_dict() if hasattr(value, "to_dict") else value
                for key, value in self.boundary_conditions.items()
            },
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "source": self.source,
            "notes": self.notes,
        }


def _quantity_dict(quantity: Quantity | None) -> dict[str, Any] | None:
    if quantity is None:
        return None
    return {"value": quantity.magnitude, "units": str(quantity.units)}


__all__ = ["Geometry", "geometry_assumption"]
