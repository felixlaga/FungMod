"""One-dimensional film geometry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.geometry.base import Geometry, geometry_assumption
from fungal_model.transport.geometry import BoundaryConditions1D, UniformGrid1D


def film_1d_geometry_assumption() -> Assumption:
    return Assumption(
        name="one-dimensional film geometry",
        description="A film is represented by a cell-centered 1D grid across its thickness.",
        justification="Thin-film diffusion benchmarks need explicit length, cells, and boundary conditions.",
        known_limitations="No 2D/3D geometry, curvature, swelling, roughness evolution, or variable cell widths.",
        source="FungMod 1D film geometry abstraction.",
    )


@dataclass(frozen=True, init=False)
class Film1DGeometry(Geometry):
    """1D film geometry wrapping the existing `UniformGrid1D`."""

    grid: UniformGrid1D

    def __init__(
        self,
        *,
        length: Parameter,
        n_cells: int,
        surface_area: Quantity | None = None,
        volume: Quantity | None = None,
        boundary_conditions: Mapping[str, BoundaryConditions1D] | None = None,
        name: str = "film_1d",
        source: str = "Explicit 1D film model geometry.",
        notes: str = "",
    ) -> None:
        grid = UniformGrid1D(length=length, n_cells=n_cells)
        assumptions = (geometry_assumption(), film_1d_geometry_assumption())
        Geometry.__init__(
            self,
            name=name,
            geometry_type="film_1d",
            volume=None if volume is None else assert_compatible(volume, "meter ** 3", name="film_1d.volume"),
            surface_area=None if surface_area is None else assert_compatible(surface_area, "meter ** 2", name="film_1d.surface_area"),
            boundary_conditions=dict(boundary_conditions or {}),
            assumptions=assumptions,
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "grid", grid)
        self.validate()

    @property
    def is_spatial(self) -> bool:
        return True

    @property
    def spatial_grid(self) -> UniformGrid1D:
        return self.grid

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["grid"] = self.grid.to_dict()
        return data


__all__ = ["Film1DGeometry", "film_1d_geometry_assumption"]
