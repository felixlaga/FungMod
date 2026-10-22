"""Empirical conversion-dependence modifier for substrate degradation rates.

Enzymatic hydrolysis of particulate substrates slows with conversion even when
enzyme activity does not fall. Kadam, Rydholm and McMillan (2004) represented
this with a substrate reactivity factor proportional to the remaining
substrate fraction. Restart experiments attribute most of the decline to the
loss of accessible or hydrolysable material, enzyme clogging and surface
heterogeneity rather than to a change in the reactivity of what remains
(Yang, Willies and Wyman 2006 Biotechnol. Bioeng. 94:1122; Levine, Fox, Blanch
and Clark 2010 Biotechnol. Bioeng. 107:37). This modifier therefore carries
the factor ``(S / S_ref)^n`` as an empirical conversion dependence of
unattributed origin, with the exponent an explicit, estimable parameter, and
it makes no claim about which mechanism produces it.
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

SUBSTRATE_REACTIVITY_MODIFIER_TYPE = "substrate_reactivity"
KADAM_2004_SOURCE = (
    "Kadam K.L., Rydholm E.C., McMillan J.D. (2004) Development and validation of a kinetic model for "
    "enzymatic saccharification of lignocellulosic biomass. Biotechnol. Prog. 20:698-705, doi:10.1021/bp034316x"
)
CONVERSION_DEPENDENCE_EVIDENCE = (
    "Yang B., Willies D.M., Wyman C.E. (2006) Changes in the enzymatic hydrolysis rate of Avicel cellulose "
    "with conversion. Biotechnol. Bioeng. 94:1122-1128, doi:10.1002/bit.20942; "
    "Levine S.E., Fox J.M., Blanch H.W., Clark D.S. (2010) A mechanistic model of the enzymatic hydrolysis "
    "of cellulose. Biotechnol. Bioeng. 107:37-51, doi:10.1002/bit.22789"
)


def substrate_reactivity_assumption() -> Assumption:
    return Assumption(
        name="empirical conversion-dependence modifier",
        description=(
            "Rate is multiplied by (S / S_ref)^n for the substrate state S, a reference concentration S_ref "
            "(the initial loading of the same state) and a non-negative exponent n; the factor is zero when S = 0."
        ),
        justification=(
            "A decline in hydrolysis rate with conversion that enzyme activity alone cannot explain must be "
            "explicit when included. n = 1 is the linear substrate reactivity factor of Kadam et al. (2004); "
            "n -> 0 removes the effect. The factor is empirical: restart experiments attribute the decline to "
            "accessibility, hydrolysable fraction, enzyme clogging and surface heterogeneity rather than to a "
            "reactivity change of the remaining material (Yang et al. 2006 Biotechnol. Bioeng. 94:1122; "
            "Levine et al. 2010 Biotechnol. Bioeng. 107:37), and this modifier does not decide between those "
            "mechanisms."
        ),
        known_limitations=(
            "Phenomenological: crystallinity, surface area, adsorption and particle structure are not resolved "
            "and the attribution of the decline is unknown. The factor exceeds one if the substrate exceeds its "
            "reference concentration. With n = 0 the factor is discontinuous at S = 0 (0 at zero, 1 above it); "
            "with 0 < n < 1 its slope is unbounded at S = 0, so no analytic gradient is offered for n < 1 and the "
            "compiled Jacobian of a wrapped process falls back to recorded finite differences."
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
    def condition(self) -> str:
        return CONDITION_STATE

    @property
    def read_states(self) -> tuple[tuple[str, str], ...]:
        return ((self.substrate_state, self.substrate_units),)

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (substrate_reactivity_assumption(),)

    def _constants(self, parameters: ParameterSet) -> tuple[float, float]:
        reference = parameters.require_quantity(self.reference_concentration_symbol, self.substrate_units)
        exponent = parameters.require_quantity(self.exponent_symbol, "dimensionless")
        return _validated_constants(
            float(np.asarray(reference.magnitude, dtype=float)),
            float(np.asarray(exponent.magnitude, dtype=float)),
        )

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
        values = _finite_nonnegative(np.asarray(substrate.magnitude, dtype=float), name=self.substrate_state)
        return Q_(_reactivity(values / reference, exponent), "dimensionless")

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

    def _compiled_constants(self, context: KernelContext) -> tuple[int, float, float, float]:
        index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        reference, exponent = _validated_constants(
            float(context.parameter(self.reference_concentration_symbol, self.substrate_units)),
            float(context.parameter(self.exponent_symbol, "dimensionless")),
        )
        return index, to_substrate, reference, exponent

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        index, to_substrate, reference, exponent = self._compiled_constants(context)
        substrate_name = self.substrate_state

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate = _finite_nonnegative_scalar(state[index] * to_substrate, name=substrate_name)
            ratio = substrate / reference
            if ratio == 0.0:
                return 0.0
            return float(ratio**exponent)

        return kernel

    def compile_activity_gradient(self, context: KernelContext) -> JacobianKernel | None:
        """``da/dS = n (S / S_ref)^(n - 1) / S_ref`` for S > 0 and, for n >= 1, its limit at S = 0.

        At S = 0 the limit is ``1 / S_ref`` for n = 1 and ``0`` for n > 1 (the
        right-derivative the non-negative orthant admits). For ``0 <= n < 1``
        the slope at S = 0 is unbounded (or the factor is a step), so no
        analytic gradient is offered and the caller records a
        finite-difference Jacobian.
        """

        index, to_substrate, reference, exponent = self._compiled_constants(context)
        if exponent < 1.0:
            return None
        size = len(context.state_index)
        substrate_name = self.substrate_state

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            substrate = _finite_nonnegative_scalar(state[index] * to_substrate, name=substrate_name)
            result = np.zeros(size, dtype=float)
            ratio = substrate / reference
            if ratio > 0.0:
                result[index] = exponent * ratio ** (exponent - 1.0) / reference * to_substrate
            elif exponent == 1.0:
                result[index] = to_substrate / reference
            return result

        return gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": SUBSTRATE_REACTIVITY_MODIFIER_TYPE,
            "substrate_state": self.substrate_state,
            "reference_concentration_symbol": self.reference_concentration_symbol,
            "exponent_symbol": self.exponent_symbol,
            "substrate_units": self.substrate_units,
            "source": KADAM_2004_SOURCE,
            "conversion_dependence_evidence": CONVERSION_DEPENDENCE_EVIDENCE,
            "equation": "(S / S_ref)^n",
        }


def _validated_constants(reference: float, exponent: float) -> tuple[float, float]:
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError("Substrate reactivity reference concentration must be finite and positive.")
    if not np.isfinite(exponent) or exponent < 0:
        raise ValueError("Substrate reactivity exponent must be finite and non-negative.")
    return reference, exponent


def _finite_nonnegative(values: np.ndarray, *, name: str) -> np.ndarray:
    if not np.isfinite(values).all() or np.any(values < 0.0):
        raise ValueError(f"{name} must be finite and nonnegative.")
    return values


def _finite_nonnegative_scalar(value: float, *, name: str) -> float:
    if not np.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative.")
    return value


def _reactivity(ratio: np.ndarray, exponent: float) -> np.ndarray:
    values = np.asarray(ratio, dtype=float)
    result = np.where(values > 0.0, np.power(np.where(values > 0.0, values, 1.0), exponent), 0.0)
    return result


__all__ = [
    "CONVERSION_DEPENDENCE_EVIDENCE",
    "KADAM_2004_SOURCE",
    "SUBSTRATE_REACTIVITY_MODIFIER_TYPE",
    "SubstrateReactivityModifier",
    "substrate_reactivity_assumption",
]
