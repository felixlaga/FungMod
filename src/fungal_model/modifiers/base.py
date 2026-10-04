"""Base environmental modifier interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment


class EnvironmentalModifier(Protocol):
    """Protocol for explicit rate modifiers driven by environment/state data."""

    name: str

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        ...

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        ...

    def scale(
        self,
        *,
        rate: Quantity,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        ...


@dataclass(frozen=True)
class ModifierMetadata:
    """Small serializable descriptor for a modifier."""

    name: str
    modifier_type: str
    required_parameters: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "modifier_type": self.modifier_type,
            "required_parameters": list(self.required_parameters),
        }


class _ActivityProvider(Protocol):
    """Read-only view of a modifier used for build-time constant folding."""

    @property
    def name(self) -> str:
        ...

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        ...


def constant_activity_kernel(modifier: _ActivityProvider, context: KernelContext) -> RateKernel:
    """Fold a state-independent activity into a constant kernel.

    The environment is a static entity during a run, so an activity that reads
    only parameters and the environment is evaluated once here with the
    modifier's own ``activity`` method; range warnings therefore fire once at
    build time rather than at every right-hand-side evaluation.
    """

    activity = assert_compatible(
        modifier.activity(parameters=context.parameters, environment=context.environment, state=None),
        "dimensionless",
        name=f"{modifier.name} activity",
    )
    values = np.asarray(activity.magnitude, dtype=float)
    if values.ndim != 0:
        raise ValueError(f"{modifier.name} activity must be a scalar for a numeric kernel.")
    value = float(values)

    def kernel(time: float, state: np.ndarray) -> float:
        del time, state
        return value

    return kernel


__all__ = ["EnvironmentalModifier", "ModifierMetadata", "constant_activity_kernel"]
