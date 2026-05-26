"""Water-activity modifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment


def water_activity_threshold_assumption() -> Assumption:
    return Assumption(
        name="minimum water activity threshold",
        description="Rates are set to zero below an explicit minimum water activity and unchanged above it.",
        justification="A simple sourced threshold prevents hidden moisture permissiveness.",
        known_limitations="No smooth moisture-response curve, hysteresis, substrate water binding, or spatial moisture gradients.",
        source="FungMod water activity modifier design.",
    )


@dataclass(frozen=True)
class WaterActivityModifier:
    """Binary water-activity threshold modifier."""

    minimum_water_activity_symbol: str
    name: str = "water_activity_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (water_activity_threshold_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        water_activity = environment.require_water_activity()
        minimum = parameters.require_quantity(self.minimum_water_activity_symbol, "dimensionless")
        value = np.where(
            np.asarray(water_activity.magnitude, dtype=float) >= float(minimum.magnitude),
            1.0,
            0.0,
        )
        return Q_(value, "dimensionless")

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
            name="water-activity-scaled rate",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "water_activity_threshold",
            "minimum_water_activity_symbol": self.minimum_water_activity_symbol,
        }


__all__ = ["WaterActivityModifier", "water_activity_threshold_assumption"]
