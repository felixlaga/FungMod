"""Well-mixed geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.geometry.base import Geometry, geometry_assumption


def well_mixed_geometry_assumption() -> Assumption:
    return Assumption(
        name="well-mixed geometry",
        description="All state variables are spatially homogeneous within one control volume.",
        justification="Well-mixed ODE models require a volume but no spatial grid.",
        known_limitations="No concentration gradients, boundary layers, diffusion, advection, or surface profiles.",
        source="Canonical well-mixed reactor assumption.",
    )


@dataclass(frozen=True, init=False)
class WellMixedGeometry(Geometry):
    """Non-spatial control-volume geometry."""

    def __init__(
        self,
        *,
        volume: Quantity,
        surface_area: Quantity | None = None,
        name: str = "well_mixed",
        boundary_conditions: Mapping[str, Any] | None = None,
        source: str = "Explicit well-mixed model geometry.",
        notes: str = "",
    ) -> None:
        assumptions = (geometry_assumption(), well_mixed_geometry_assumption())
        Geometry.__init__(
            self,
            name=name,
            geometry_type="well_mixed",
            volume=assert_compatible(volume, "meter ** 3", name="well_mixed.volume"),
            surface_area=None if surface_area is None else assert_compatible(surface_area, "meter ** 2", name="well_mixed.surface_area"),
            boundary_conditions=dict(boundary_conditions or {}),
            assumptions=assumptions,
            source=source,
            notes=notes,
        )
        self.validate()

    @classmethod
    def from_volume_string(cls, volume: str, **kwargs: Any) -> "WellMixedGeometry":
        from fungal_model.core.units import Q_

        return cls(volume=Q_(volume), **kwargs)


__all__ = ["WellMixedGeometry", "well_mixed_geometry_assumption"]
