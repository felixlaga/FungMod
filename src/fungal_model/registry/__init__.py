"""Registry APIs for FungMod plug-and-play metadata."""

from fungal_model.core.value_spec import ValueSpec, ValueSpecError
from fungal_model.registry.loaders import RegistryLoadError, load_registry
from fungal_model.registry.records import (
    EnzymeClassRecord,
    EnvironmentRecord,
    FungusRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    RegistryRecord,
    SubstrateRecord,
)
from fungal_model.registry.resolver import (
    AmbiguousResolutionError,
    RegistryResolver,
    ResolutionError,
    ResolvedRecord,
)
from fungal_model.registry.store import FungModRegistry, RegistryLookupError, RegistryValidationError

__all__ = [
    "AmbiguousResolutionError",
    "EnzymeClassRecord",
    "EnvironmentRecord",
    "FungModRegistry",
    "FungusRecord",
    "ParameterRecord",
    "ProcessCompatibilityRecord",
    "RegistryResolver",
    "RegistryLoadError",
    "RegistryLookupError",
    "RegistryRecord",
    "RegistryValidationError",
    "ResolutionError",
    "ResolvedRecord",
    "SubstrateRecord",
    "ValueSpec",
    "ValueSpecError",
    "load_registry",
]
