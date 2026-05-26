"""Particle/sphere geometry placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from fungal_model.core.assumptions import Assumption
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.geometry.base import Geometry, geometry_assumption


def particle_geometry_assumption() -> Assumption:
    return Assumption(
        name="particle geometry placeholder",
        description="Particle geometry records radius, surface area, and volume metadata.",
        justification="Particle models need explicit geometry before kinetics or transport can use them.",
        known_limitations="No radial grid, shrinking-core model, porosity, or particle-size distribution is implemented.",
        source="FungMod particle geometry placeholder.",
    )


@dataclass(frozen=True, init=False)
class ParticleGeometry(Geometry):
    radius: Quantity

    def __init__(
        self,
        *,
        radius: Quantity,
        volume: Quantity | None = None,
        surface_area: Quantity | None = None,
        name: str = "particle",
        source: str = "Explicit particle geometry metadata.",
        notes: str = "",
    ) -> None:
        Geometry.__init__(
            self,
            name=name,
            geometry_type="particle",
            volume=volume,
            surface_area=surface_area,
            assumptions=(geometry_assumption(), particle_geometry_assumption()),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "radius", assert_compatible(radius, "meter", name="particle.radius"))
        if float(self.radius.magnitude) <= 0:
            raise ValueError("Particle radius must be positive.")
        self.validate()


__all__ = ["ParticleGeometry", "particle_geometry_assumption"]
