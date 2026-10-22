"""Base environmental modifier interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment

# The condition a modifier responds to. Environment conditions are the gamma
# factors of the multiplicative composition; ``state`` marks a modifier that
# reads solver states (inhibition, conversion dependence) and is never folded
# to a constant.
CONDITION_TEMPERATURE = "temperature"
CONDITION_PH = "ph"
CONDITION_OXYGEN = "oxygen"
CONDITION_WATER_ACTIVITY = "water_activity"
CONDITION_STATE = "state"
MODIFIER_CONDITIONS: tuple[str, ...] = (
    CONDITION_TEMPERATURE,
    CONDITION_PH,
    CONDITION_OXYGEN,
    CONDITION_WATER_ACTIVITY,
    CONDITION_STATE,
)


class EnvironmentalModifier(Protocol):
    """Protocol for explicit rate modifiers driven by environment/state data.

    ``condition`` names what the factor responds to (one of
    :data:`MODIFIER_CONDITIONS`). ``read_states`` lists every solver state the
    factor reads as ``(name, units)`` pairs; it is empty for environment-only
    laws, whose activity gradient with respect to the state vector is then
    identically zero. ``compile_activity_gradient`` returns the gradient of the
    activity with respect to the numeric state vector, or ``None`` when no
    analytic gradient is offered (the caller then records a finite-difference
    Jacobian).
    """

    name: str

    @property
    def condition(self) -> str:
        ...

    @property
    def read_states(self) -> tuple[tuple[str, str], ...]:
        ...

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

    def compile_activity_gradient(self, context: KernelContext) -> JacobianKernel | None:
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


def zero_activity_gradient(context: KernelContext) -> JacobianKernel:
    """Gradient of an activity that reads no solver state: identically zero."""

    size = len(context.state_index)

    def gradient(time: float, state: np.ndarray) -> np.ndarray:
        del time, state
        return np.zeros(size, dtype=float)

    return gradient


__all__ = [
    "CONDITION_OXYGEN",
    "CONDITION_PH",
    "CONDITION_STATE",
    "CONDITION_TEMPERATURE",
    "CONDITION_WATER_ACTIVITY",
    "EnvironmentalModifier",
    "MODIFIER_CONDITIONS",
    "ModifierMetadata",
    "constant_activity_kernel",
    "zero_activity_gradient",
]
