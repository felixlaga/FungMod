"""Conversion-dependent substrate reactivity modifier.

Enzymatic hydrolysis of particulate substrates slows with conversion even when
enzyme activity does not fall, because the remaining material is less
accessible. Kadam, Rydholm and McMillan (2004) represented this with a
substrate reactivity factor proportional to the remaining substrate fraction.
This modifier generalises that factor with an exponent so the strength of the
effect is an explicit, estimable parameter rather than a hidden feature of a
fitted rate constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment

SUBSTRATE_REACTIVITY_MODIFIER_TYPE = "substrate_reactivity"
KADAM_2004_SOURCE = (
    "Kadam K.L., Rydholm E.C., McMillan J.D. (2004) Development and validation of a kinetic model for "
    "enzymatic saccharification of lignocellulosic biomass. Biotechnol. Prog. 20:698-705, doi:10.1021/bp034316x"
)


def substrate_reactivity_assumption() -> Assumption:
    return Assumption(
        name="conversion-dependent substrate reactivity modifier",
        description=(
            "Rate is multiplied by (S / S_ref)^n for the substrate state S, a reference concentration S_ref "
            "(the initial loading of the same state) and a non-negative exponent n; the factor is zero when S <= 0."
        ),
        justification=(
            "A decline in hydrolysis rate with conversion that enzyme activity alone cannot explain must be "
            "explicit when included. n = 1 is the linear substrate reactivity factor of Kadam et al. (2004); "
            "n -> 0 removes the effect."
        ),
        known_limitations=(
            "Phenomenological: crystallinity, surface area, adsorption and particle structure are not resolved. "
            "The factor exceeds one if the substrate exceeds its reference concentration."
        ),
        source=KADAM_2004_SOURCE,
    )


@dataclass(frozen=True)
class SubstrateReactivityModifier:
    """Multiply a rate by ``(S / S_ref)**n`` for an explicit substrate state."""

    substrate_state: str
    reference_concentration_symbol: str
    exponent_symbol: str
    substrate_units: str
    name: str = "substrate_reactivity_modifier"

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (substrate_reactivity_assumption(),)

    def _constants(self, parameters: ParameterSet) -> tuple[float, float]:
        reference = parameters.require_quantity(self.reference_concentration_symbol, self.substrate_units)
        exponent = parameters.require_quantity(self.exponent_symbol, "dimensionless")
        reference_value = float(np.asarray(reference.magnitude, dtype=float))
        exponent_value = float(np.asarray(exponent.magnitude, dtype=float))
        if not np.isfinite(reference_value) or reference_value <= 0:
            raise ValueError("Substrate reactivity reference concentration must be finite and positive.")
        if not np.isfinite(exponent_value) or exponent_value < 0:
            raise ValueError("Substrate reactivity exponent must be finite and non-negative.")
        return reference_value, exponent_value

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del environment
        if state is None or self.substrate_state not in state:
            raise ValueError(f"SubstrateReactivityModifier requires state {self.substrate_state!r}.")
        substrate = assert_compatible(state[self.substrate_state], self.substrate_units, name=self.substrate_state)
        reference, exponent = self._constants(parameters)
        ratio = np.maximum(np.asarray(substrate.magnitude, dtype=float) / reference, 0.0)
        return Q_(_reactivity(ratio, exponent), "dimensionless")

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
            name="substrate-reactivity-scaled rate",
        )

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        reference = float(context.parameter(self.reference_concentration_symbol, self.substrate_units))
        exponent = float(context.parameter(self.exponent_symbol, "dimensionless"))
        if not np.isfinite(reference) or reference <= 0:
            raise ValueError("Substrate reactivity reference concentration must be finite and positive.")
        if not np.isfinite(exponent) or exponent < 0:
            raise ValueError("Substrate reactivity exponent must be finite and non-negative.")

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            ratio = state[index] * to_substrate / reference
            if ratio <= 0.0:
                return 0.0
            return float(ratio**exponent)

        return kernel

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": SUBSTRATE_REACTIVITY_MODIFIER_TYPE,
            "substrate_state": self.substrate_state,
            "reference_concentration_symbol": self.reference_concentration_symbol,
            "exponent_symbol": self.exponent_symbol,
            "substrate_units": self.substrate_units,
            "source": KADAM_2004_SOURCE,
        }


def _reactivity(ratio: np.ndarray, exponent: float) -> np.ndarray:
    values = np.asarray(ratio, dtype=float)
    result = np.where(values > 0.0, np.power(np.where(values > 0.0, values, 1.0), exponent), 0.0)
    return result


__all__ = [
    "KADAM_2004_SOURCE",
    "SUBSTRATE_REACTIVITY_MODIFIER_TYPE",
    "SubstrateReactivityModifier",
    "substrate_reactivity_assumption",
]
