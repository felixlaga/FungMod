"""Generic whole-culture physiology processes.

The processes in this module describe producer-proportional synthesis laws
without naming an organism, an enzyme, or a substrate. They are the registry-
bindable building blocks for organism records: biomass-proportional enzyme
production, optionally induced by a saturable inducer pool. Their material
cost is deliberately not represented here; a costed synthesis closure must be
assembled from explicit stoichiometric processes, never implied by this law.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)

PROPORTIONAL_SYNTHESIS_PROCESS_TYPE = "proportional_synthesis"


def proportional_synthesis_assumption(*, induced: bool) -> Assumption:
    """Return the explicit assumption carried by a proportional synthesis law."""

    law = (
        "rate = q * producer * inducer / (K_I + inducer)"
        if induced
        else "rate = q * producer"
    )
    return Assumption(
        name="producer-proportional synthesis",
        description=(
            f"A product pool is formed at {law}. The producer and the inducer are not consumed "
            "by this law; the product is formed in its own units."
        ),
        justification=(
            "Growth- or biomass-associated production with optional saturable induction is the "
            "canonical effective law for extracellular enzyme production in well-mixed cultures."
        ),
        known_limitations=(
            "The material cost of synthesis (carbon, nitrogen, energy) is not represented and must be "
            "assembled explicitly when a material ledger is required. No repression, catabolite "
            "control, lag, or capacity limit is represented."
        ),
        source="Canonical growth-associated production law (Luedeking-Piret type); no organism claim.",
    )


@dataclass(frozen=True, init=False)
class ProportionalSynthesisProcess(Process):
    """Producer-proportional formation of one product pool, optionally induced.

    ``rate = q * P`` (constitutive) or ``rate = q * P * I / (K_I + I)`` (induced),
    where ``P`` is the producer state, ``I`` the inducer state, ``q`` the specific
    production rate in ``rate_units / producer_units`` and ``K_I`` the induction
    half-saturation constant in the inducer's units. The only contribution is
    ``+rate`` to the product state; nothing is consumed.
    """

    producer_state: str
    producer_units: str
    product_state: str
    product_units: str
    rate_units: str
    specific_rate_symbol: str
    inducer_state: str | None
    inducer_units: str | None
    induction_half_saturation_symbol: str | None

    def __init__(
        self,
        *,
        name: str,
        producer_state: str,
        producer_units: str,
        product_state: str,
        product_units: str,
        rate_units: str,
        specific_rate_symbol: str,
        inducer_state: str | None = None,
        inducer_units: str | None = None,
        induction_half_saturation_symbol: str | None = None,
        source: str = "Generic producer-proportional synthesis process.",
        notes: str = "",
    ) -> None:
        induced_fields = (inducer_state, inducer_units, induction_half_saturation_symbol)
        if any(value is None for value in induced_fields) and any(value is not None for value in induced_fields):
            raise ValueError(
                "Induced synthesis requires inducer_state, inducer_units and "
                "induction_half_saturation_symbol together; omit all three for constitutive synthesis."
            )
        if producer_state == product_state or inducer_state == product_state:
            raise ValueError("The synthesized product must be a state distinct from the producer and the inducer.")
        induced = inducer_state is not None
        required_states = [StateVariableSpec(producer_state, producer_units, role="producer")]
        changed_states = [StateVariableSpec(product_state, product_units, role="product")]
        requirements = [
            ParameterRequirement(
                symbol=specific_rate_symbol,
                units=f"({rate_units}) / ({producer_units})",
                name="specific production rate",
            )
        ]
        if induced:
            assert inducer_state is not None
            assert inducer_units is not None
            assert induction_half_saturation_symbol is not None
            required_states.append(StateVariableSpec(inducer_state, inducer_units, role="inducer"))
            requirements.append(
                ParameterRequirement(
                    symbol=induction_half_saturation_symbol,
                    units=inducer_units,
                    name="induction half-saturation constant",
                )
            )
        Process.__init__(
            self,
            name=name,
            process_type=PROPORTIONAL_SYNTHESIS_PROCESS_TYPE,
            required_state_variables=tuple(required_states),
            changed_state_variables=tuple(changed_states),
            required_parameters=tuple(requirements),
            assumptions=(proportional_synthesis_assumption(induced=induced),),
            validity=ValidityDomain(
                description="Well-mixed producer-proportional synthesis with optional saturable induction.",
                labels=("homogeneous", "physiology", "induced" if induced else "constitutive"),
                limitations=(
                    "Synthesis cost, repression, lag, and capacity limits are not represented.",
                ),
            ),
            failure_modes=(
                "negative producer state",
                "negative inducer state",
                "non-positive induction half-saturation constant",
                "negative specific production rate",
            ),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "producer_state", producer_state)
        object.__setattr__(self, "producer_units", producer_units)
        object.__setattr__(self, "product_state", product_state)
        object.__setattr__(self, "product_units", product_units)
        object.__setattr__(self, "rate_units", rate_units)
        object.__setattr__(self, "specific_rate_symbol", specific_rate_symbol)
        object.__setattr__(self, "inducer_state", inducer_state)
        object.__setattr__(self, "inducer_units", inducer_units)
        object.__setattr__(self, "induction_half_saturation_symbol", induction_half_saturation_symbol)

    @property
    def induced(self) -> bool:
        return self.inducer_state is not None

    @property
    def specific_rate_units(self) -> str:
        return f"({self.rate_units}) / ({self.producer_units})"

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: object = None,
        geometry: object = None,
    ) -> Quantity:
        del time, environment, geometry
        producer = assert_compatible(
            require_quantity(state[self.producer_state], name=self.producer_state),
            self.producer_units,
            name=self.producer_state,
        )
        if np.any(np.asarray(producer.magnitude, dtype=float) < 0):
            raise ValueError(f"{self.producer_state} must be non-negative for proportional synthesis.")
        specific_rate = parameters.require_quantity(self.specific_rate_symbol, self.specific_rate_units)
        if float(specific_rate.magnitude) < 0:
            raise ValueError("specific production rate must be non-negative for proportional synthesis.")
        rate = specific_rate * producer
        if self.induced:
            assert self.inducer_state is not None
            assert self.inducer_units is not None
            assert self.induction_half_saturation_symbol is not None
            inducer = assert_compatible(
                require_quantity(state[self.inducer_state], name=self.inducer_state),
                self.inducer_units,
                name=self.inducer_state,
            )
            if np.any(np.asarray(inducer.magnitude, dtype=float) < 0):
                raise ValueError(f"{self.inducer_state} must be non-negative for induced synthesis.")
            half_saturation = parameters.require_quantity(self.induction_half_saturation_symbol, self.inducer_units)
            if float(half_saturation.magnitude) <= 0:
                raise ValueError("induction half-saturation constant must be positive for induced synthesis.")
            rate = rate * (inducer / (half_saturation + inducer))
        return assert_compatible(rate, self.rate_units, name=f"{self.name} rate")

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        producer_index, to_producer = context.state_slot(self.producer_state, self.producer_units)
        specific_rate = context.parameter(self.specific_rate_symbol, self.specific_rate_units)
        if specific_rate < 0:
            raise ValueError("specific production rate must be non-negative for proportional synthesis.")
        scale = float(
            assert_compatible(
                Q_(1.0, self.specific_rate_units) * Q_(1.0, self.producer_units),
                self.rate_units,
                name=f"{self.name} rate",
            ).magnitude
        )
        producer_name = self.producer_state
        if not self.induced:

            def constitutive_kernel(time: float, state: np.ndarray) -> float:
                del time
                producer = state[producer_index] * to_producer
                if producer < 0:
                    raise ValueError(f"{producer_name} must be non-negative for proportional synthesis.")
                return (specific_rate * producer) * scale

            return constitutive_kernel
        assert self.inducer_state is not None
        assert self.inducer_units is not None
        assert self.induction_half_saturation_symbol is not None
        inducer_index, to_inducer = context.state_slot(self.inducer_state, self.inducer_units)
        half_saturation = context.parameter(self.induction_half_saturation_symbol, self.inducer_units)
        if half_saturation <= 0:
            raise ValueError("induction half-saturation constant must be positive for induced synthesis.")
        inducer_name = self.inducer_state

        def induced_kernel(time: float, state: np.ndarray) -> float:
            del time
            producer = state[producer_index] * to_producer
            inducer = state[inducer_index] * to_inducer
            if producer < 0:
                raise ValueError(f"{producer_name} must be non-negative for proportional synthesis.")
            if inducer < 0:
                raise ValueError(f"{inducer_name} must be non-negative for induced synthesis.")
            return ((specific_rate * producer) * (inducer / (half_saturation + inducer))) * scale

        return induced_kernel

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel | None:
        producer_index, to_producer = context.state_slot(self.producer_state, self.producer_units)
        specific_rate = context.parameter(self.specific_rate_symbol, self.specific_rate_units)
        if specific_rate < 0:
            raise ValueError("specific production rate must be non-negative for proportional synthesis.")
        scale = float(
            assert_compatible(
                Q_(1.0, self.specific_rate_units) * Q_(1.0, self.producer_units),
                self.rate_units,
                name=f"{self.name} rate",
            ).magnitude
        )
        size = len(context.state_index)
        if not self.induced:
            derivative = specific_rate * scale * to_producer

            def constitutive_gradient(time: float, state: np.ndarray) -> np.ndarray:
                del time, state
                result = np.zeros(size, dtype=float)
                result[producer_index] = derivative
                return result

            return constitutive_gradient
        assert self.inducer_state is not None
        assert self.inducer_units is not None
        assert self.induction_half_saturation_symbol is not None
        inducer_index, to_inducer = context.state_slot(self.inducer_state, self.inducer_units)
        half_saturation = context.parameter(self.induction_half_saturation_symbol, self.inducer_units)
        if half_saturation <= 0:
            raise ValueError("induction half-saturation constant must be positive for induced synthesis.")

        def induced_gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            producer = state[producer_index] * to_producer
            inducer = state[inducer_index] * to_inducer
            if producer < 0 or inducer < 0:
                raise ValueError("producer and inducer must be non-negative for induced synthesis.")
            result = np.zeros(size, dtype=float)
            result[producer_index] = specific_rate * inducer / (half_saturation + inducer) * scale * to_producer
            result[inducer_index] += specific_rate * producer * half_saturation / (half_saturation + inducer) ** 2 * scale * to_inducer
            return result

        return induced_gradient

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        return {self.product_state: value}

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "producer_state": self.producer_state,
                "product_state": self.product_state,
                "inducer_state": self.inducer_state,
                "induction": "saturable" if self.induced else "constitutive",
                "rate_units": self.rate_units,
            }
        )
        return data


__all__ = [
    "PROPORTIONAL_SYNTHESIS_PROCESS_TYPE",
    "ProportionalSynthesisProcess",
    "proportional_synthesis_assumption",
]
