"""Oxygen availability modifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.modifiers.base import constant_activity_kernel


def oxygen_monod_assumption() -> Assumption:
    return Assumption(
        name="oxygen Monod limitation modifier",
        description="Aerobic rate is multiplied by O2 / (K_O2 + O2).",
        justification="Aerobic processes should not ignore explicitly low oxygen availability.",
        known_limitations="No oxygen consumption state, gas transfer, redox balance, or anaerobic metabolism is represented.",
        source="FungMod oxygen modifier design.",
    )


@dataclass(frozen=True)
class OxygenModifier:
    """Monod oxygen limitation from a declared state or the static environment."""

    half_saturation_symbol: str
    oxygen_units: str
    name: str = "oxygen_modifier"
    state_source: str | None = None

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        if self.state_source is None:
            return (oxygen_monod_assumption(),)
        return (Assumption(name="state-driven oxygen Monod limitation", description="Rate is multiplied by the declared dissolved-oxygen state divided by its sum with K_O2.", justification="Explicit oxygen limitation of an existing rate law.", known_limitations="The modifier supplies no transfer or uptake balance itself; companion processes must account for oxygen consumption.", source="Monod saturation form; data/mechanism_sources/monod1949/source.yml"),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        if self.state_source is None:
            oxygen = environment.require_oxygen_concentration(self.oxygen_units)
        else:
            if state is None or self.state_source not in state:
                raise ValueError(f"OxygenModifier requires state {self.state_source!r}.")
            oxygen = assert_compatible(state[self.state_source], self.oxygen_units, name=self.state_source)
        half = parameters.require_quantity(self.half_saturation_symbol, self.oxygen_units)
        if float(half.magnitude) <= 0:
            raise ValueError("Oxygen half-saturation must be positive.")
        if np.any(np.asarray(oxygen.magnitude, dtype=float) < 0):
            raise ValueError("Oxygen concentration must be non-negative.")
        return assert_compatible(oxygen / (half + oxygen), "dimensionless", name="oxygen activity")

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
            name="oxygen-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        """Fold static oxygen once, or read the declared state slot each step."""

        if self.state_source is None:
            return constant_activity_kernel(self, context)
        index, scale = context.state_slot(self.state_source, self.oxygen_units)
        half = context.parameter(self.half_saturation_symbol, self.oxygen_units)
        if not np.isfinite(half) or half <= 0:
            raise ValueError("Oxygen half-saturation must be finite and positive.")

        def activity(time: float, state: np.ndarray) -> float:
            del time
            oxygen = state[index] * scale
            if oxygen < 0:
                raise ValueError("Oxygen concentration must be non-negative.")
            return oxygen / (half + oxygen)

        return activity

    def compile_activity_jacobian(self, context: KernelContext) -> JacobianKernel:
        """Analytic derivative of the oxygen factor; the static factor has none."""
        size = len(context.state_index)
        if self.state_source is None:
            def constant_gradient(time: float, state: np.ndarray) -> np.ndarray:
                return np.zeros(size, dtype=float)
            return constant_gradient
        index, scale = context.state_slot(self.state_source, self.oxygen_units)
        half = context.parameter(self.half_saturation_symbol, self.oxygen_units)
        if not np.isfinite(half) or half <= 0:
            raise ValueError("Oxygen half-saturation must be finite and positive.")

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            result = np.zeros(size, dtype=float)
            oxygen = state[index] * scale
            if oxygen < 0:
                raise ValueError("Oxygen concentration must be non-negative.")
            result[index] = half * scale / (half + oxygen) ** 2
            return result

        return gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "oxygen_monod",
            "half_saturation_symbol": self.half_saturation_symbol,
            "oxygen_units": self.oxygen_units,
            **({"state_source": self.state_source} if self.state_source is not None else {}),
        }


__all__ = ["OxygenModifier", "oxygen_monod_assumption"]
