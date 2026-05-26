from __future__ import annotations

import pytest

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, UnitError
from fungal_model.geometry import (
    Film1DGeometry,
    Geometry,
    ParticleGeometry,
    PorousMediumGeometry,
    SlabGeometry,
    WellMixedGeometry,
)
from fungal_model.transport.geometry import BoundaryCondition, BoundaryConditions1D


def length_parameter() -> Parameter:
    return Parameter(
        name="film length",
        symbol="L",
        value=1.0e-3,
        units="meter",
        uncertainty=0.0,
        source="Artificial geometry benchmark.",
        confidence_level="testing",
        notes="Used only for geometry abstraction tests.",
        measurement_method="defined benchmark value",
    )


def test_well_mixed_geometry_exposes_volume_surface_and_ratio() -> None:
    geometry = WellMixedGeometry(
        volume=Q_(1.0, "liter"),
        surface_area=Q_(0.1, "meter ** 2"),
        source="Artificial well-mixed geometry.",
    )

    assert not geometry.is_spatial
    assert geometry.spatial_grid is None
    assert geometry.volume.to("meter ** 3").magnitude == pytest.approx(1.0e-3)
    assert geometry.area_volume_ratio.to("1 / meter").magnitude == pytest.approx(100.0)
    assert geometry.to_dict()["geometry_type"] == "well_mixed"


def test_geometry_requires_source_and_checks_units() -> None:
    with pytest.raises(ProvenanceError):
        Geometry(name="unsourced", geometry_type="custom", volume=Q_(1.0, "meter ** 3")).validate()
    with pytest.raises(UnitError):
        WellMixedGeometry(volume=Q_(1.0, "meter"), source="bad units")


def test_film_1d_geometry_wraps_uniform_grid_and_boundaries() -> None:
    boundaries = {
        "E": BoundaryConditions1D(
            left=BoundaryCondition("fixed_value", Q_(1.0, "mole / liter")),
            right=BoundaryCondition("no_flux"),
        )
    }
    geometry = Film1DGeometry(
        length=length_parameter(),
        n_cells=8,
        surface_area=Q_(0.2, "meter ** 2"),
        volume=Q_(2.0e-4, "meter ** 3"),
        boundary_conditions=boundaries,
        source="Artificial film geometry.",
    )

    assert geometry.is_spatial
    assert geometry.spatial_grid.n_cells == 8
    assert geometry.spatial_grid.cell_width.to("meter").magnitude == pytest.approx(1.25e-4)
    assert geometry.boundary_conditions["E"].left.kind == "fixed_value"
    assert geometry.to_dict()["grid"]["n_cells"] == 8


def test_placeholder_geometries_are_metadata_not_spatial_solvers() -> None:
    particle = ParticleGeometry(radius=Q_(1.0, "millimeter"), source="Artificial particle.")
    slab = SlabGeometry(thickness=Q_(0.5, "millimeter"), source="Artificial slab.")
    porous = PorousMediumGeometry(porosity=Q_(0.4, "dimensionless"), source="Artificial porous medium.")

    assert particle.geometry_type == "particle"
    assert slab.geometry_type == "slab"
    assert porous.geometry_type == "porous_medium"
    assert not particle.is_spatial
    assert particle.spatial_grid is None
    assert "placeholder" in particle.assumptions[-1].name


def test_porous_medium_rejects_invalid_porosity() -> None:
    with pytest.raises(ValueError):
        PorousMediumGeometry(porosity=Q_(1.2, "dimensionless"), source="Artificial porous medium.")
