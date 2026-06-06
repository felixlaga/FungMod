"""Researcher-facing FungMod virtual-experiment API."""

from fungal_model.api.environment_grid import EnvironmentGrid
from fungal_model.api.virtual_experiment import (
    DegradationScreenResult,
    VirtualExperiment,
    VirtualExperimentError,
    VirtualExperimentMode,
)

__all__ = [
    "DegradationScreenResult",
    "EnvironmentGrid",
    "VirtualExperiment",
    "VirtualExperimentError",
    "VirtualExperimentMode",
]
