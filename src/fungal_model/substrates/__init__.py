"""Substrate definitions."""

from .base import DegradationProduct, Substrate
from .pet import PETSubstrate, make_pet_parameter_set, pet_surface_assumption

__all__ = [
    "DegradationProduct",
    "PETSubstrate",
    "Substrate",
    "make_pet_parameter_set",
    "pet_surface_assumption",
]
