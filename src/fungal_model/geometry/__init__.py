"""Geometry abstractions."""

from .base import Geometry, geometry_assumption
from .film_1d import Film1DGeometry, film_1d_geometry_assumption
from .particle import ParticleGeometry, particle_geometry_assumption
from .porous_medium import PorousMediumGeometry, porous_medium_geometry_assumption
from .slab import SlabGeometry, slab_geometry_assumption
from .well_mixed import WellMixedGeometry, well_mixed_geometry_assumption

__all__ = [
    "Film1DGeometry",
    "Geometry",
    "ParticleGeometry",
    "PorousMediumGeometry",
    "SlabGeometry",
    "WellMixedGeometry",
    "film_1d_geometry_assumption",
    "geometry_assumption",
    "particle_geometry_assumption",
    "porous_medium_geometry_assumption",
    "slab_geometry_assumption",
    "well_mixed_geometry_assumption",
]
