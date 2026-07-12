"""Researcher-facing FungMod virtual-experiment API."""

from fungal_model.api.environment_grid import EnvironmentCase, EnvironmentGrid, environment_grid
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
    "DegradationScreenResult",
    "AVAILABLE_SOURCE_PROVIDERS",
    "EnvironmentCase",
    "EnvironmentGrid",
    "environment_grid",
    "source_proposal",
    "SourceProviderError",
    "VirtualExperiment",
    "VirtualExperimentError",
    "VirtualExperimentMode",
    "virtual_experiment",
]
