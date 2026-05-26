"""FungMod: traceable models for fungal and enzyme-mediated substrate degradation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fungal-model")
except PackageNotFoundError:  # pragma: no cover - editable tree before install
    __version__ = "0.1.0"

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import (
    IncompatibleUnitsError,
    InvalidMechanismError,
    MissingParameterError,
    MissingProcessError,
    ModelAssemblyError,
)
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.fungi.base import Fungus
from fungal_model.processes import (
    AssembledModel,
    AssemblyReport,
    ModelAssemblyContext,
    ModelBuilder,
    ParameterRequirement,
    Process,
    ProcessRegistry,
    StateVariableSpec,
    ValidityDomain,
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
    AccessibleSitePool,
    AccessibleSurfaceAreaModel,
    BondCleavageProcess,
    EquilibriumSurfaceCoverageModel,
    LangmuirAdsorptionModel,
    ProductReleaseMap,
    SurfaceCatalysisModel,
    SurfaceCatalysisProcess,
)
from fungal_model.results import SimulationResult
from fungal_model.substrates.base import Substrate

__all__ = [
    "AssembledModel",
    "AssemblyReport",
    "Assumption",
    "AccessibleSitePool",
    "AccessibleSurfaceAreaModel",
    "BondCleavageProcess",
    "EquilibriumSurfaceCoverageModel",
    "Fungus",
    "FirstOrderDecayProcess",
    "HomogeneousMichaelisMentenProcess",
    "IncompatibleUnitsError",
    "InvalidMechanismError",
    "MassActionProcess",
    "MissingParameterError",
    "MissingProcessError",
    "ModelAssemblyContext",
    "ModelAssemblyError",
    "ModelBuilder",
    "Parameter",
    "ParameterRequirement",
    "ParameterSet",
    "Process",
    "ProcessRegistry",
    "ProductReleaseMap",
    "SimulationResult",
    "SolverSettings",
    "StateVariableSpec",
    "Substrate",
    "SurfaceCatalysisModel",
    "SurfaceCatalysisProcess",
    "ValidityDomain",
    "__version__",
]
