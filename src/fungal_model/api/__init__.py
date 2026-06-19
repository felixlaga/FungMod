"""Researcher-facing FungMod virtual-experiment API."""

from fungal_model.api.environment_grid import EnvironmentCase, EnvironmentGrid, environment_grid
from fungal_model.api.virtual_experiment import (
    DegradationScreenResult,
    VirtualExperiment,
    VirtualExperimentError,
    VirtualExperimentMode,
    virtual_experiment,
)

__all__ = [
    "DegradationScreenResult",
    "EnvironmentCase",
    "EnvironmentGrid",
    "environment_grid",
    "VirtualExperiment",
    "VirtualExperimentError",
    "VirtualExperimentMode",
    "virtual_experiment",
]
