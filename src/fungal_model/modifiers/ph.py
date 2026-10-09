"""pH modifiers that read from Environment."""

from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np
from typing import Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.modifiers.base import constant_activity_kernel
from fungal_model.modifiers.state_environment import check_state_environment, state_activity_quantity
from fungal_model.kinetics.ph import gaussian_ph_activity, gaussian_ph_activity_assumption


@dataclass(frozen=True)
class PHModifier:
    """Gaussian pH activity modifier driven by `Environment.ph`."""

    optimum_symbol: str
    width_symbol: str
    source: str
    minimum_ph_symbol: str | None = None
    maximum_ph_symbol: str | None = None
    name: str = "ph_modifier"
    state_source: str | None = None

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (gaussian_ph_activity_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        if self.state_source is not None:
            return state_activity_quantity(self, state_source=self.state_source, state=state,
                parameters=parameters, environment=environment)
        minimum = (
            parameters.require_quantity(self.minimum_ph_symbol, "dimensionless")
            if self.minimum_ph_symbol is not None
            else None
        )
        maximum = (
            parameters.require_quantity(self.maximum_ph_symbol, "dimensionless")
            if self.maximum_ph_symbol is not None
            else None
        )
        return gaussian_ph_activity(
            ph=environment.require_ph(),
            optimum_ph=parameters.require_quantity(self.optimum_symbol, "dimensionless"),
            width=parameters.require_quantity(self.width_symbol, "dimensionless"),
            minimum_ph=minimum,
            maximum_ph=maximum,
            source=self.source,
        )

    def scale(
        self,
        *,
        rate: Quantity,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        return assert_compatible(
            rate * self.activity(parameters=parameters, environment=environment, state=state),
            str(rate.units),
            name="pH-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        """Environment-only activity: evaluated once at build time."""

        if self.state_source is None:
            return constant_activity_kernel(self, context)
        return self._dynamic(context)[0]

    def compile_activity_jacobian(self, context: KernelContext) -> JacobianKernel:
        if self.state_source is None:
            return lambda t, y: np.zeros(len(y))
        return self._dynamic(context)[1]

    def _dynamic(self, context: KernelContext) -> tuple[RateKernel, JacobianKernel]:
        assert self.state_source is not None
        if not self.source.strip():
            raise ValueError("A source is required for a state-driven pH response.")
        check_state_environment(environment=context.environment, field="ph")
        idx, scale = context.state_slot(self.state_source, "dimensionless")
        optimum = context.parameter(self.optimum_symbol, "dimensionless")
        width = context.parameter(self.width_symbol, "dimensionless")
        lower = 0.0 if self.minimum_ph_symbol is None else context.parameter(self.minimum_ph_symbol, "dimensionless")
        upper = 14.0 if self.maximum_ph_symbol is None else context.parameter(self.maximum_ph_symbol, "dimensionless")
        if width <= 0 or not all(map(math.isfinite, (optimum, width, lower, upper))) or not (0 <= lower < upper <= 14 and 0 <= optimum <= 14):
            raise ValueError("State-driven Gaussian pH requires positive width and finite optimum and ordered bounds within 0 to 14.")
        def activity(t: float, y: np.ndarray) -> float:
            ph = y[idx] * scale
            if not lower <= ph <= upper:
                raise ValueError("pH left the declared response domain.")
            deviation = (ph - optimum) / width
            return math.exp(-0.5 * deviation * deviation)
        def gradient(t: float, y: np.ndarray) -> np.ndarray:
            result = np.zeros(len(y))
            value = activity(t, y)
            if value != 0:
                result[idx] = -value * ((y[idx] * scale - optimum) / width) / width * scale
            if not np.isfinite(result[idx]):
                raise ValueError("State-driven pH derivative is not finite in the declared basis.")
            return result
        return activity, gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "ph_gaussian",
            "optimum_symbol": self.optimum_symbol,
            "width_symbol": self.width_symbol,
            "minimum_ph_symbol": self.minimum_ph_symbol,
            "maximum_ph_symbol": self.maximum_ph_symbol,
            "source": self.source,
            **({"state_source": self.state_source} if self.state_source is not None else {}),
        }


__all__ = ["PHModifier"]
