"""Product inhibition modifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.entities.environment import Environment


def product_inhibition_assumption() -> Assumption:
    return Assumption(
        name="reversible product inhibition modifier",
        description="Rate is multiplied by 1 / (1 + P / K_i) for an explicit product state.",
        justification="Product inhibition must be explicit when included and cannot be hidden in fitted rates.",
        known_limitations="Single-product reversible inhibition only; no competitive mechanism or multiple products.",
        source="FungMod product inhibition modifier design.",
    )


@dataclass(frozen=True)
class ProductInhibitionModifier:
    """Simple reversible product inhibition modifier."""

    product_state: str
    inhibition_constant_symbol: str
    product_units: str
    name: str = "product_inhibition_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (product_inhibition_assumption(),)

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del environment
        if state is None or self.product_state not in state:
            raise ValueError(f"ProductInhibitionModifier requires state {self.product_state!r}.")
        product = assert_compatible(state[self.product_state], self.product_units, name=self.product_state)
        if np.any(np.asarray(product.magnitude, dtype=float) < 0):
            raise ValueError("Product concentration/amount must be non-negative.")
        inhibition = parameters.require_quantity(self.inhibition_constant_symbol, self.product_units)
        if np.any(np.asarray(inhibition.magnitude, dtype=float) <= 0):
            raise ValueError("Product inhibition constant must be positive.")
        return assert_compatible(1 / (1 + product / inhibition), "dimensionless", name="product inhibition activity")

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
            name="product-inhibition-scaled rate",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "product_inhibition",
            "product_state": self.product_state,
            "inhibition_constant_symbol": self.inhibition_constant_symbol,
            "product_units": self.product_units,
        }


__all__ = ["ProductInhibitionModifier", "product_inhibition_assumption"]
