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
from fungal_model.entities import Environment
from fungal_model.entities import Enzyme
from fungal_model.fungi.base import Fungus
from fungal_model.geometry import (
    Film1DGeometry,
    Geometry,
    ParticleGeometry,
    PorousMediumGeometry,
    SlabGeometry,
    WellMixedGeometry,
)
from fungal_model.io import (
    load_enzyme,
    load_environment,
    load_fungus,
    load_geometry,
    load_parameter_set,
    load_substrate,
)
from fungal_model.modifiers import (
    OxygenModifier,
    PHModifier,
    ProductInhibitionModifier,
    TemperatureModifier,
    WaterActivityModifier,
)
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
    CompatibilityIssue,
)
from fungal_model.results import SimulationResult
from fungal_model.substrates.base import Substrate
from fungal_model.workflows import PETSurfaceWorkflowConfig, run_pet_surface_integration

__all__ = [
    "AssembledModel",
    "AssemblyReport",
    "Assumption",
    "AccessibleSitePool",
    "AccessibleSurfaceAreaModel",
    "BondCleavageProcess",
    "CompatibilityIssue",
    "Enzyme",
    "EquilibriumSurfaceCoverageModel",
    "Environment",
    "Film1DGeometry",
    "Fungus",
    "Geometry",
    "FirstOrderDecayProcess",
    "HomogeneousMichaelisMentenProcess",
    "IncompatibleUnitsError",
    "InvalidMechanismError",
    "load_enzyme",
    "load_environment",
    "load_fungus",
    "load_geometry",
    "load_parameter_set",
    "load_substrate",
    "MassActionProcess",
    "MissingParameterError",
    "MissingProcessError",
    "ModelAssemblyContext",
    "ModelAssemblyError",
    "ModelBuilder",
    "Parameter",
    "ParameterRequirement",
    "ParameterSet",
    "PETSurfaceWorkflowConfig",
    "ParticleGeometry",
    "PorousMediumGeometry",
    "Process",
    "ProcessRegistry",
    "ProductReleaseMap",
    "OxygenModifier",
    "PHModifier",
    "ProductInhibitionModifier",
    "SimulationResult",
    "SlabGeometry",
    "SolverSettings",
    "StateVariableSpec",
    "Substrate",
    "SurfaceCatalysisModel",
    "SurfaceCatalysisProcess",
    "TemperatureModifier",
    "ValidityDomain",
    "WaterActivityModifier",
    "WellMixedGeometry",
    "run_pet_surface_integration",
    "__version__",
]
