"""Spatial mycelium: continuum hyphal growth on a compiled finite-volume core.

Fields on a uniform one-, two- or three-dimensional grid (cartesian, or one
radial axis for a colony with circular symmetry); generic processes
for tip extension, tip motion, branching, anastomosis, first-order losses,
local uptake, translocation along hyphae and local secretion; one compile
step that resolves every unit; integration on plain numpy arrays, with the
analytic sparse Jacobian of every process for the implicit methods. The
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
from .jacobian import FieldJacobianKernel, StencilBlock
from .model import CompiledMyceliumModel, MyceliumModel, MyceliumResult, total_amount
from .observation import (
    circle_length_in_square,
    colony_count_outside_disc,
    colony_hull_area,
    colony_hull_radius,
    disc_area_in_square,
)
from .processes import FieldProcess

__all__ = [
    "Anastomosis",
    "CompiledMyceliumModel",
    "DichotomousBranching",
    "FieldDiffusion",
    "FieldJacobianKernel",
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
    "StencilBlock",
    "TipExtension",
    "TipMotion",
    "Translocation",
    "circle_length_in_square",
    "colony_count_outside_disc",
    "colony_hull_area",
    "colony_hull_radius",
    "continuum_process_types",
    "disc_area_in_square",
    "total_amount",
]
