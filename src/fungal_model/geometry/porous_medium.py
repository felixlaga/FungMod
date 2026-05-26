"""Porous-medium geometry placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from fungal_model.core.assumptions import Assumption
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.geometry.base import Geometry, geometry_assumption


def porous_medium_geometry_assumption() -> Assumption:
    return Assumption(
        name="porous medium geometry placeholder",
        description="Porous medium metadata records porosity and bulk geometry but does not implement transport.",
        justification="Porous geometry must be explicit before diffusion, advection, or tortuosity models can use it.",
        known_limitations="No pore-network, tortuosity, moisture, or advection solver is implemented.",
        source="FungMod porous-medium geometry placeholder.",
    )


@dataclass(frozen=True, init=False)
class PorousMediumGeometry(Geometry):
    porosity: Quantity

    def __init__(
        self,
        *,
        porosity: Quantity,
        volume: Quantity | None = None,
        surface_area: Quantity | None = None,
        name: str = "porous_medium",
        source: str = "Explicit porous-medium geometry metadata.",
        notes: str = "",
    ) -> None:
        Geometry.__init__(
            self,
            name=name,
            geometry_type="porous_medium",
            volume=volume,
            surface_area=surface_area,
            assumptions=(geometry_assumption(), porous_medium_geometry_assumption()),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "porosity", assert_compatible(porosity, "dimensionless", name="porosity"))
        if not 0 <= float(self.porosity.magnitude) <= 1:
            raise ValueError("Porosity must be between 0 and 1.")
        self.validate()


__all__ = ["PorousMediumGeometry", "porous_medium_geometry_assumption"]
