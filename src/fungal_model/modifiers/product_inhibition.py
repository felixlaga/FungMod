"""Noncompetitive product inhibition modifier.

The factor ``1 / (1 + P / K_i)`` applied to a whole rate is the noncompetitive
special case of the general reversible-inhibition taxonomy (competitive and
uncompetitive constants equal, ``K_ic = K_iu = K_i``; Cornish-Bowden 2012). It
is not the competitive, uncompetitive or mixed form; those are
:class:`fungal_model.modifiers.MixedInhibitionModifier`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.modifiers.base import CONDITION_STATE
from fungal_model.modifiers.enzyme_inhibition import CORNISH_BOWDEN_2012_SOURCE

PRODUCT_INHIBITION_MECHANISM = "noncompetitive"


def product_inhibition_assumption() -> Assumption:
    return Assumption(
        name="noncompetitive product inhibition",
        description=(
            "Rate is multiplied by 1 / (1 + P / K_i) for an explicit product state P. Applied to a whole "
            "rate this is the noncompetitive inhibition form (K_ic = K_iu = K_i): it lowers the apparent "
            "maximum rate and leaves the apparent K_m unchanged."
        ),
        justification=(
            "Product inhibition must be explicit when included and cannot be hidden in fitted rates; the "
            "mechanism is named so the output states which inhibition form was assumed."
        ),
        known_limitations=(
            "Single product and the noncompetitive form only. Competitive, uncompetitive and mixed forms "
            "change the substrate dependence and need the mixed_inhibition modifier on a Michaelis-Menten "
            "base; multiple products need one term each."
        ),
        source=CORNISH_BOWDEN_2012_SOURCE,
    )


@dataclass(frozen=True)
class ProductInhibitionModifier:
    """Noncompetitive product inhibition: multiply a rate by ``1 / (1 + P / K_i)``."""

    product_state: str
    inhibition_constant_symbol: str
    product_units: str
    name: str = "product_inhibition_modifier"

    @property
    def condition(self) -> str:
        return CONDITION_STATE

    @property
    def read_states(self) -> tuple[tuple[str, str], ...]:
        return ((self.product_state, self.product_units),)

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
        product_values = _finite_nonnegative_product(np.asarray(product.magnitude, dtype=float))
        inhibition = parameters.require_quantity(self.inhibition_constant_symbol, self.product_units)
        inhibition_values = _finite_positive_constant(np.asarray(inhibition.magnitude, dtype=float))
        activity = 1.0 / (1.0 + product_values / inhibition_values)
        return Q_(activity, "dimensionless")

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

    def _compiled_constants(self, context: KernelContext) -> tuple[int, float, float]:
        index, to_product = context.state_slot(self.product_state, self.product_units)
        raw = context.parameter(self.inhibition_constant_symbol, self.product_units)
        inhibition = float(_finite_positive_constant(np.asarray(raw, dtype=float)))
        return index, to_product, inhibition

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        index, to_product, inhibition = self._compiled_constants(context)

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            product = _finite_nonnegative_product_scalar(state[index] * to_product)
            return 1.0 / (1.0 + product / inhibition)

        return kernel

    def compile_activity_gradient(self, context: KernelContext) -> JacobianKernel | None:
        """``da/dP = -(1 / K_i) / (1 + P / K_i)^2`` in state-vector units."""

        index, to_product, inhibition = self._compiled_constants(context)
        size = len(context.state_index)

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            product = _finite_nonnegative_product_scalar(state[index] * to_product)
            result = np.zeros(size, dtype=float)
            result[index] = -(1.0 / inhibition) / (1.0 + product / inhibition) ** 2 * to_product
            return result

        return gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "product_inhibition",
            "mechanism": PRODUCT_INHIBITION_MECHANISM,
            "product_state": self.product_state,
            "inhibition_constant_symbol": self.inhibition_constant_symbol,
            "product_units": self.product_units,
            "law_source": CORNISH_BOWDEN_2012_SOURCE,
            "equation": "1 / (1 + P / K_i)",
        }


PRODUCT_MESSAGE = "Product concentration/amount must be non-negative and finite."
CONSTANT_MESSAGE = "Product inhibition constant must be positive and finite."


def _finite_nonnegative_product(values: np.ndarray) -> np.ndarray:
    if not np.isfinite(values).all() or np.any(values < 0.0):
        raise ValueError(PRODUCT_MESSAGE)
    return values


def _finite_nonnegative_product_scalar(value: float) -> float:
    if not np.isfinite(value) or value < 0.0:
        raise ValueError(PRODUCT_MESSAGE)
    return value


def _finite_positive_constant(values: np.ndarray) -> np.ndarray:
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        raise ValueError(CONSTANT_MESSAGE)
    return values


__all__ = ["PRODUCT_INHIBITION_MECHANISM", "ProductInhibitionModifier", "product_inhibition_assumption"]
