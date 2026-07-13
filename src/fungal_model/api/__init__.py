"""Researcher-facing FungMod virtual-experiment API."""

from fungal_model.api.curation import (
    CurationDecision,
    CurationError,
    CurationResult,
    review_source_proposal,
)
from fungal_model.api.environment_grid import EnvironmentCase, EnvironmentGrid, environment_grid
from fungal_model.api.registry_promotion import (
    ProspectiveRegistryFile,
    RegistryPromotionAppliedFile,
    RegistryPromotionApplyError,
    RegistryPromotionApplyResult,
    RegistryPromotionCandidate,
    RegistryPromotionPlan,
    RegistryPromotionPlanError,
    RegistryPromotionPlanWriteResult,
    apply_registry_promotion,
    plan_registry_promotion,
)
from fungal_model.api.source_provider import (
    AVAILABLE_SOURCE_PROVIDERS,
    SourceProviderError,
    source_proposal,
)
from fungal_model.api.virtual_experiment import (
    DegradationScreenResult,
    VirtualExperiment,
    VirtualExperimentError,
    VirtualExperimentMode,
    virtual_experiment,
)

__all__ = [
    "CurationDecision",
    "CurationError",
    "CurationResult",
    "DegradationScreenResult",
    "AVAILABLE_SOURCE_PROVIDERS",
    "EnvironmentCase",
    "EnvironmentGrid",
    "environment_grid",
    "apply_registry_promotion",
    "plan_registry_promotion",
    "ProspectiveRegistryFile",
    "RegistryPromotionAppliedFile",
    "RegistryPromotionApplyError",
    "RegistryPromotionApplyResult",
    "RegistryPromotionCandidate",
    "RegistryPromotionPlan",
    "RegistryPromotionPlanError",
    "RegistryPromotionPlanWriteResult",
    "review_source_proposal",
    "source_proposal",
    "SourceProviderError",
    "VirtualExperiment",
    "VirtualExperimentError",
    "VirtualExperimentMode",
    "virtual_experiment",
]
