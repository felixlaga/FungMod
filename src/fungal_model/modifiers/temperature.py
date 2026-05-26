"""Temperature modifiers that read from Environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.kinetics.arrhenius import (
    arrhenius_reference_scaled_rate,
    arrhenius_temperature_assumption,
)


@dataclass(frozen=True)
class TemperatureModifier:
    """Arrhenius reference-rate modifier driven by `Environment.temperature`."""

    activation_energy_symbol: str
    reference_temperature_symbol: str
    source: str
    minimum_temperature_symbol: str | None = None
    maximum_temperature_symbol: str | None = None
    name: str = "temperature_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (arrhenius_temperature_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        scaled = self.scale(
            rate=Q_(1.0, "dimensionless"),
            parameters=parameters,
            environment=environment,
        )
        return assert_compatible(scaled, "dimensionless", name="temperature activity")

    def scale(
        self,
        *,
        rate: Quantity,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        minimum = (
            parameters.require_quantity(self.minimum_temperature_symbol, "kelvin")
            if self.minimum_temperature_symbol is not None
            else None
        )
        maximum = (
            parameters.require_quantity(self.maximum_temperature_symbol, "kelvin")
            if self.maximum_temperature_symbol is not None
            else None
        )
        return arrhenius_reference_scaled_rate(
            reference_rate=rate,
            activation_energy=parameters.require_quantity(self.activation_energy_symbol, "joule / mole"),
            temperature=environment.require_temperature(),
            reference_temperature=parameters.require_quantity(self.reference_temperature_symbol, "kelvin"),
            minimum_temperature=minimum,
            maximum_temperature=maximum,
            source=self.source,
            output_units=str(rate.units),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "temperature_arrhenius_reference",
            "activation_energy_symbol": self.activation_energy_symbol,
            "reference_temperature_symbol": self.reference_temperature_symbol,
            "minimum_temperature_symbol": self.minimum_temperature_symbol,
            "maximum_temperature_symbol": self.maximum_temperature_symbol,
            "source": self.source,
        }


__all__ = ["TemperatureModifier"]
