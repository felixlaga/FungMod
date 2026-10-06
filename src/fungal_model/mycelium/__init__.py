"""Spatial mycelium: continuum hyphal growth on a compiled finite-volume core.

Fields on a uniform one-, two- or three-dimensional grid; generic processes
for tip extension, tip motion, branching, anastomosis, first-order losses,
local uptake, translocation along hyphae and local secretion; one compile
step that resolves every unit; integration on plain numpy arrays. The
processes are exploratory until parameterised from a registry record and
checked against colony-expansion data; see ``docs/spatial-mycelium.md``.
"""

from .fields import FieldKernelContext, FieldSpec
from .grid import SpatialGrid
from .hyphae import (
    Anastomosis,
    DichotomousBranching,
    FieldDiffusion,
    FirstOrderLoss,
    LateralBranching,
    LocalSecretion,
    LocalUptake,
    TipExtension,
    TipMotion,
    Translocation,
    continuum_process_types,
)
from .model import CompiledMyceliumModel, MyceliumModel, MyceliumResult, total_amount
from .processes import FieldProcess

__all__ = [
    "Anastomosis",
    "CompiledMyceliumModel",
    "DichotomousBranching",
    "FieldDiffusion",
    "FieldKernelContext",
    "FieldProcess",
    "FieldSpec",
    "FirstOrderLoss",
    "LateralBranching",
    "LocalSecretion",
    "LocalUptake",
    "MyceliumModel",
    "MyceliumResult",
    "SpatialGrid",
    "TipExtension",
    "TipMotion",
    "Translocation",
    "continuum_process_types",
    "total_amount",
]
