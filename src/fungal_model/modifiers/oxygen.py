"""Oxygen availability modifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment


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
    """Monod-style oxygen limitation modifier using `Environment.oxygen_concentration`."""

    half_saturation_symbol: str
    oxygen_units: str
    name: str = "oxygen_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (oxygen_monod_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        oxygen = environment.require_oxygen_concentration(self.oxygen_units)
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

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "oxygen_monod",
            "half_saturation_symbol": self.half_saturation_symbol,
            "oxygen_units": self.oxygen_units,
        }


__all__ = ["OxygenModifier", "oxygen_monod_assumption"]
