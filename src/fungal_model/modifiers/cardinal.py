"""Cardinal (Rosso-type) temperature, pH and water-activity modifiers that read from Environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.kinetics.cardinal import (
    cardinal_ph_activity,
    cardinal_ph_assumption,
    cardinal_temperature_activity,
    cardinal_temperature_assumption,
    cardinal_water_activity_activity,
    cardinal_water_activity_assumption,
)
from fungal_model.modifiers.base import constant_activity_kernel

CARDINAL_TEMPERATURE_MODIFIER_TYPE = "temperature_cardinal_rosso"
CARDINAL_PH_MODIFIER_TYPE = "ph_cardinal_rosso"
CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE = "water_activity_cardinal_rosso_robinson"


@dataclass(frozen=True)
class CardinalTemperatureModifier:
    """Rosso CTMI activity modifier driven by ``Environment.temperature``."""

    minimum_temperature_symbol: str
    optimum_temperature_symbol: str
    maximum_temperature_symbol: str
    source: str
    name: str = "cardinal_temperature_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (cardinal_temperature_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        return cardinal_temperature_activity(
            temperature=environment.require_temperature(),
            minimum_temperature=parameters.require_quantity(self.minimum_temperature_symbol, "kelvin"),
            optimum_temperature=parameters.require_quantity(self.optimum_temperature_symbol, "kelvin"),
            maximum_temperature=parameters.require_quantity(self.maximum_temperature_symbol, "kelvin"),
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
            name="cardinal-temperature-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        """Environment-only activity: evaluated once at build time."""

        return constant_activity_kernel(self, context)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": CARDINAL_TEMPERATURE_MODIFIER_TYPE,
            "minimum_temperature_symbol": self.minimum_temperature_symbol,
            "optimum_temperature_symbol": self.optimum_temperature_symbol,
            "maximum_temperature_symbol": self.maximum_temperature_symbol,
            "source": self.source,
        }


@dataclass(frozen=True)
class CardinalPHModifier:
    """Rosso CPM activity modifier driven by ``Environment.ph``."""

    minimum_ph_symbol: str
    optimum_ph_symbol: str
    maximum_ph_symbol: str
    source: str
    name: str = "cardinal_ph_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (cardinal_ph_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        return cardinal_ph_activity(
            ph=environment.require_ph(),
            minimum_ph=parameters.require_quantity(self.minimum_ph_symbol, "dimensionless"),
            optimum_ph=parameters.require_quantity(self.optimum_ph_symbol, "dimensionless"),
            maximum_ph=parameters.require_quantity(self.maximum_ph_symbol, "dimensionless"),
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
            name="cardinal-pH-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        """Environment-only activity: evaluated once at build time."""

        return constant_activity_kernel(self, context)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": CARDINAL_PH_MODIFIER_TYPE,
            "minimum_ph_symbol": self.minimum_ph_symbol,
            "optimum_ph_symbol": self.optimum_ph_symbol,
            "maximum_ph_symbol": self.maximum_ph_symbol,
            "source": self.source,
        }


@dataclass(frozen=True)
class CardinalWaterActivityModifier:
    """Rosso and Robinson cardinal water-activity modifier driven by ``Environment.water_activity``."""

    minimum_water_activity_symbol: str
    optimum_water_activity_symbol: str
    source: str
    name: str = "cardinal_water_activity_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (cardinal_water_activity_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        return cardinal_water_activity_activity(
            water_activity=environment.require_water_activity(),
            minimum_water_activity=parameters.require_quantity(self.minimum_water_activity_symbol, "dimensionless"),
            optimum_water_activity=parameters.require_quantity(self.optimum_water_activity_symbol, "dimensionless"),
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
            name="cardinal-water-activity-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        """Environment-only activity: evaluated once at build time."""

        return constant_activity_kernel(self, context)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE,
            "minimum_water_activity_symbol": self.minimum_water_activity_symbol,
            "optimum_water_activity_symbol": self.optimum_water_activity_symbol,
            "source": self.source,
        }


__all__ = [
    "CARDINAL_PH_MODIFIER_TYPE",
    "CARDINAL_TEMPERATURE_MODIFIER_TYPE",
    "CardinalPHModifier",
    "CardinalTemperatureModifier",
    "CardinalWaterActivityModifier",
    "CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE",
]
