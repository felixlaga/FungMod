"""Substrate definitions."""

from .base import (
    DegradationProduct,
    Substrate,
    SubstrateParameterSpec,
    make_substrate_parameter_set,
    make_unknown_substrate_parameter,
    validate_substrate_parameter_units,
)
from .cellulose import CelluloseSubstrate, make_cellulose_parameter_set
from .chitin import ChitinSubstrate, make_chitin_parameter_set
from .lignin import LigninSubstrate, make_lignin_parameter_set
from .pet import (
    PETAccessibleSurfaceAreaModel,
    PETSubstrate,
    make_pet_parameter_set,
    pet_product_release_map,
    pet_surface_assumption,
)
from .starch import StarchSubstrate, make_starch_parameter_set

__all__ = [
    "CelluloseSubstrate",
    "ChitinSubstrate",
    "DegradationProduct",
    "LigninSubstrate",
    "PETAccessibleSurfaceAreaModel",
    "PETSubstrate",
    "StarchSubstrate",
    "Substrate",
    "SubstrateParameterSpec",
    "make_cellulose_parameter_set",
    "make_chitin_parameter_set",
    "make_lignin_parameter_set",
    "make_pet_parameter_set",
    "make_starch_parameter_set",
    "make_substrate_parameter_set",
    "make_unknown_substrate_parameter",
    "pet_product_release_map",
    "pet_surface_assumption",
    "validate_substrate_parameter_units",
]
