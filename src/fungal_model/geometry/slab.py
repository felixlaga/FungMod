"""Slab geometry placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from fungal_model.core.assumptions import Assumption
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.geometry.base import Geometry, geometry_assumption


def slab_geometry_assumption() -> Assumption:
    return Assumption(
        name="slab geometry placeholder",
        description="Slab geometry records thickness and optional area/volume metadata.",
        justification="Slab models need explicit thickness before transport or surface coupling is added.",
        known_limitations="No dedicated slab solver or variable geometry is implemented.",
        source="FungMod slab geometry placeholder.",
    )


@dataclass(frozen=True, init=False)
class SlabGeometry(Geometry):
    thickness: Quantity

    def __init__(
        self,
        *,
        thickness: Quantity,
        volume: Quantity | None = None,
        surface_area: Quantity | None = None,
        name: str = "slab",
        source: str = "Explicit slab geometry metadata.",
        notes: str = "",
    ) -> None:
        Geometry.__init__(
            self,
            name=name,
            geometry_type="slab",
            volume=volume,
            surface_area=surface_area,
            assumptions=(geometry_assumption(), slab_geometry_assumption()),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "thickness", assert_compatible(thickness, "meter", name="slab.thickness"))
        if float(self.thickness.magnitude) <= 0:
            raise ValueError("Slab thickness must be positive.")
        self.validate()


__all__ = ["SlabGeometry", "slab_geometry_assumption"]
