"""pH modifiers that read from Environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment
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
        del state
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

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "ph_gaussian",
            "optimum_symbol": self.optimum_symbol,
            "width_symbol": self.width_symbol,
            "minimum_ph_symbol": self.minimum_ph_symbol,
            "maximum_ph_symbol": self.maximum_ph_symbol,
            "source": self.source,
        }


__all__ = ["PHModifier"]
