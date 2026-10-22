"""Rosso-Robinson cardinal water-activity modifier that reads from Environment.

The threshold law in ``modifiers/water_activity.py`` stays available; this
module adds the smooth cardinal response of Rosso and Robinson (2001), which
is the order-two cardinal model (CM_2) of ``kinetics/cardinal.py`` applied to
water activity. The authors fix ``a_w,max`` at 1.0 (pure water); here it is a
required parameter record so that the choice is explicit and sourced, never a
code default.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.kinetics.cardinal import cardinal_cm2_activity, cardinal_water_activity_assumption
from fungal_model.modifiers.base import constant_activity_kernel

CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE = "water_activity_cardinal_rosso"
CARDINAL_WATER_ACTIVITY_LAW_SOURCE = (
    "Rosso L, Robinson TP (2001) Int J Food Microbiol 63:265-273; DOI 10.1016/s0168-1605(00)00469-4."
)
CARDINAL_WATER_ACTIVITY_LAW_MATURITY = "literature_backed_software_tested"
CARDINAL_WATER_ACTIVITY_EQUATION = (
    "gamma = (a_w - a_w,max)(a_w - a_w,min)^2 / {(a_w,opt - a_w,min)[(a_w,opt - a_w,min)(a_w - a_w,opt) "
    "- (a_w,opt - a_w,max)(a_w,opt + a_w,min - 2 a_w)]} on (a_w,min, a_w,max), 0 outside"
)
_WATER_ACTIVITY_UPPER_PHYSICAL_LIMIT = 1.0


@dataclass(frozen=True)
class CardinalWaterActivityModifier:
    """Rosso-Robinson CM_2 water-activity modifier driven by ``Environment.water_activity``."""

    minimum_water_activity_symbol: str
    optimum_water_activity_symbol: str
    maximum_water_activity_symbol: str
    source: str
    name: str = "cardinal_water_activity_modifier"

    condition: str = "water_activity"
    read_states: tuple[str, ...] = ()
    law_source: str = CARDINAL_WATER_ACTIVITY_LAW_SOURCE
    maturity: str = CARDINAL_WATER_ACTIVITY_LAW_MATURITY

    def __post_init__(self) -> None:
        if not str(self.source).strip():
            raise ValueError("CardinalWaterActivityModifier requires a source.")
        symbols = (
            self.minimum_water_activity_symbol,
            self.optimum_water_activity_symbol,
            self.maximum_water_activity_symbol,
        )
        if any(not str(symbol).strip() for symbol in symbols):
            raise ValueError("CardinalWaterActivityModifier requires three cardinal parameter symbols.")
        if len(set(symbols)) != len(symbols):
            raise ValueError("CardinalWaterActivityModifier cardinal symbols must be distinct.")

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (cardinal_water_activity_assumption(),)

    @property
    def parameter_requirements(self) -> tuple[dict[str, str], ...]:
        """Parameter requirements for the wrapping process (symbol, units, name, description)."""

        return tuple(
            {
                "symbol": symbol,
                "units": "dimensionless",
                "name": name,
                "description": "Cardinal water activity of the explicit configured Rosso-Robinson CM_2 modifier.",
            }
            for symbol, name in (
                (self.minimum_water_activity_symbol, "cardinal minimum water activity"),
                (self.optimum_water_activity_symbol, "cardinal optimum water activity"),
                (self.maximum_water_activity_symbol, "cardinal maximum water activity"),
            )
        )

    @property
    def limitation(self) -> str:
        return (
            "Water-activity scaling uses the Rosso-Robinson cardinal model: an empirical growth-level "
            "shape with zero activity outside the cardinal range and no solute, hysteresis, or "
            "moisture-gradient effects."
        )

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del state
        water_activity = _water_activity_values(environment.require_water_activity())
        minimum = _cardinal_value(parameters, self.minimum_water_activity_symbol)
        optimum = _cardinal_value(parameters, self.optimum_water_activity_symbol)
        maximum = _cardinal_value(parameters, self.maximum_water_activity_symbol)
        return Q_(cardinal_cm2_activity(water_activity, minimum, optimum, maximum), "dimensionless")

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
            "condition": self.condition,
            "minimum_water_activity_symbol": self.minimum_water_activity_symbol,
            "optimum_water_activity_symbol": self.optimum_water_activity_symbol,
            "maximum_water_activity_symbol": self.maximum_water_activity_symbol,
            "source": self.source,
            "law_source": self.law_source,
            "maturity": self.maturity,
            "equation": CARDINAL_WATER_ACTIVITY_EQUATION,
        }


def cardinal_water_activity_modifier_from_config(
    modifier_config: Mapping[str, Any],
) -> CardinalWaterActivityModifier:
    """Build a Rosso-Robinson cardinal water-activity modifier from explicit config fields."""

    return CardinalWaterActivityModifier(
        minimum_water_activity_symbol=_required_symbol(
            modifier_config,
            "minimum_water_activity_symbol",
            "minimum_water_activity",
            field_name="minimum_water_activity_symbol",
        ),
        optimum_water_activity_symbol=_required_symbol(
            modifier_config,
            "optimum_water_activity_symbol",
            "optimum_water_activity",
            field_name="optimum_water_activity_symbol",
        ),
        maximum_water_activity_symbol=_required_symbol(
            modifier_config,
            "maximum_water_activity_symbol",
            "maximum_water_activity",
            field_name="maximum_water_activity_symbol",
        ),
        source=_modifier_source(
            modifier_config,
            "Explicit configured Rosso-Robinson cardinal water-activity modifier.",
        ),
    )


def _water_activity_values(quantity: Quantity) -> np.ndarray:
    values = np.asarray(
        assert_compatible(quantity, "dimensionless", name="environment.water_activity").magnitude,
        dtype=float,
    )
    if not np.isfinite(values).all() or np.any(values < 0.0) or np.any(values > _WATER_ACTIVITY_UPPER_PHYSICAL_LIMIT):
        raise ValueError("environment.water_activity must be finite and within [0, 1].")
    return values


def _cardinal_value(parameters: ParameterSet, symbol: str) -> float:
    quantity = parameters.require_quantity(symbol, "dimensionless")
    values = np.asarray(quantity.magnitude, dtype=float)
    if values.ndim != 0:
        raise ValueError(f"Cardinal water activity {symbol!r} must be a scalar.")
    value = float(values)
    if not np.isfinite(value) or value < 0.0 or value > _WATER_ACTIVITY_UPPER_PHYSICAL_LIMIT:
        raise ValueError(
            f"Cardinal water activity {symbol!r} must be within [0, 1]; pure water has a_w = 1."
        )
    return value


def _required_symbol(modifier_config: Mapping[str, Any], *keys: str, field_name: str) -> str:
    for key in keys:
        value = modifier_config.get(key)
        if value is None:
            continue
        symbol = str(value).strip()
        if symbol:
            return symbol
    raise ValueError(f"{CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE} modifier requires {field_name}.")


def _modifier_source(modifier_config: Mapping[str, Any], default: str) -> str:
    source = str(modifier_config.get("source") or "").strip()
    return source or default


__all__ = [
    "CARDINAL_WATER_ACTIVITY_EQUATION",
    "CARDINAL_WATER_ACTIVITY_LAW_MATURITY",
    "CARDINAL_WATER_ACTIVITY_LAW_SOURCE",
    "CARDINAL_WATER_ACTIVITY_MODIFIER_TYPE",
    "CardinalWaterActivityModifier",
    "cardinal_water_activity_modifier_from_config",
]
