"""Primed peroxide-driven oxidative cleavage and free-enzyme inactivation.

Kuusk et al. (2018), doi:10.1074/jbc.M117.817593, Eqs 4-5. Explicit
substrate dependence avoids a hidden saturation assumption or a discontinuous
zero-substrate switch. Feed and peroxide decay compose as separate processes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel, conversion_factor
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.peroxide import peroxide_inactivation_rate_and_gradient, peroxide_rate_and_gradient
from fungal_model.processes.base import ParameterRequirement, Process, StateVariableSpec, ValidityDomain

PEROXIDE_SOURCE = (
    "Kuusk et al. 2018, doi:10.1074/jbc.M117.817593, Eqs 4-5; data/mechanism_sources/kuusk2018_peroxide/source.yml"
)


def _assumption() -> Assumption:
    return Assumption(
        name="primed enzyme, supplied peroxide, ordered ternary complex",
        description="Substrate protects active enzyme; oxidative cleavage consumes one peroxide per cut. Product yield is explicit.",
        justification="Kuusk et al. Eqs 4-5 describe catalysis and free-enzyme damage with substrate protection.",
        known_limitations="No reductant balance, in situ peroxide generation, oxygen route, adsorption transient or chain-length allocation.",
        source=PEROXIDE_SOURCE,
    )


class _PeroxideKernels(ABC):
    """Compile the same scalar mathematics used by the quantity interface."""

    substrate_state: str
    peroxide_state: str
    enzyme_state: str
    state_units: str
    peroxide_units: str
    rate_units: str

    @abstractmethod
    def _constants(self, parameters: ParameterSet) -> dict[str, float]:
        """Resolve the particular process constants in its explicit unit basis."""

    @abstractmethod
    def _evaluate(self, s: float, h: float, e: float, constants: dict[str, float]) -> tuple[float, np.ndarray]:
        """Return the particular scalar rate and gradient with respect to S, H, E."""

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: Any = None,
        geometry: Any = None,
    ) -> Quantity:
        del time, environment, geometry
        s = float(assert_compatible(state[self.substrate_state], self.state_units).magnitude)
        h = float(assert_compatible(state[self.peroxide_state], self.peroxide_units).magnitude)
        # A common molar basis makes one peroxide per cut exact even if E was supplied in nM.
        e = float(assert_compatible(state[self.enzyme_state], self.peroxide_units).magnitude)
        value = self._evaluate(s, h, e, self._constants(parameters))[0]
        return Q_(value, f"{self.peroxide_units}/second").to(self.rate_units)

    def _compiled(self, context: KernelContext) -> tuple[RateKernel, JacobianKernel]:
        slots = [
            context.state_slot(self.substrate_state, self.state_units),
            context.state_slot(self.peroxide_state, self.peroxide_units),
            context.state_slot(self.enzyme_state, self.peroxide_units),
        ]
        constants = self._constants(context.parameters)
        scale = conversion_factor(f"{self.peroxide_units}/second", self.rate_units)

        def evaluate(y: np.ndarray) -> tuple[float, np.ndarray]:
            s, h, e = (y[i] * f for i, f in slots)
            return self._evaluate(s, h, e, constants)

        def kernel(t: float, y: np.ndarray) -> float:
            return evaluate(y)[0] * scale

        def gradient(t: float, y: np.ndarray) -> np.ndarray:
            result = np.zeros(len(context.state_index))
            for (index, factor), value in zip(slots, evaluate(y)[1], strict=True):
                result[index] += value * factor * scale
            return result

        return kernel, gradient

    def compile_rate(self, context: KernelContext) -> RateKernel:
        return self._compiled(context)[0]

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel:
        return self._compiled(context)[1]


def _validate_states(state_names: tuple[str, ...], state_units: str, peroxide_units: str, enzyme_units: str) -> None:
    if any(not n.strip() for n in state_names) or len(set(state_names)) != len(state_names):
        raise ValueError("Peroxide-process state names must be nonempty and distinct.")
    for units in (state_units, peroxide_units, enzyme_units):
        assert_compatible(Q_(1, units), "mole/liter", name="explicit molar state basis")


@dataclass(frozen=True, init=False)
class PeroxideOxidativeCleavageProcess(_PeroxideKernels, Process):
    """A cut-rate process with explicit monomer-equivalent product yield.

    Product yield has units substrate amount / peroxide amount (dimensionless
    when both are molar); supply a quantity with the declared physical basis.
    Its source is stored alongside the value exactly as a product map does.
    A ``cuts_state`` tracks cumulative productive peroxide use for ledgers.
    """

    substrate_state: str
    peroxide_state: str
    enzyme_state: str
    product_state: str
    cuts_state: str
    kcat_symbol: str
    peroxide_km_symbol: str
    substrate_km_symbol: str
    substrate_binding_symbol: str
    product_yield: Quantity
    yield_source: str
    state_units: str
    peroxide_units: str
    enzyme_units: str
    rate_units: str

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        peroxide_state: str,
        enzyme_state: str,
        product_state: str,
        cuts_state: str,
        kcat_symbol: str,
        peroxide_km_symbol: str,
        substrate_km_symbol: str,
        substrate_binding_symbol: str,
        product_yield: Quantity,
        yield_source: str,
        state_units: str,
        peroxide_units: str,
        enzyme_units: str,
        source: str,
        rate_units: str | None = None,
        notes: str = "",
    ) -> None:
        _validate_states(
            (substrate_state, peroxide_state, enzyme_state, product_state, cuts_state),
            state_units,
            peroxide_units,
            enzyme_units,
        )
        if not source.strip() or not yield_source.strip():
            raise ValueError("Oxidative cleavage and its product yield require explicit sources.")
        product_yield = assert_compatible(
            require_quantity(product_yield, name="product_yield"), "dimensionless", name="product_yield"
        )
        if not np.isfinite(product_yield.magnitude) or product_yield.magnitude <= 0:
            raise ValueError("product_yield must be finite and positive.")
        rate_units = rate_units or f"{peroxide_units}/second"
        Process.__init__(
            self,
            name=name,
            process_type="peroxide_oxidative_cleavage",
            required_state_variables=(
                StateVariableSpec(substrate_state, state_units, role="substrate"),
                StateVariableSpec(peroxide_state, peroxide_units, role="peroxide"),
                StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"),
            ),
            changed_state_variables=(
                StateVariableSpec(substrate_state, state_units, role="substrate"),
                StateVariableSpec(peroxide_state, peroxide_units, role="peroxide"),
                StateVariableSpec(product_state, state_units, role="product"),
                StateVariableSpec(cuts_state, peroxide_units, role="ledger"),
            ),
            required_parameters=(
                ParameterRequirement(kcat_symbol, "1/second"),
                ParameterRequirement(peroxide_km_symbol, peroxide_units),
                ParameterRequirement(substrate_km_symbol, state_units),
                ParameterRequirement(substrate_binding_symbol, state_units),
            ),
            assumptions=(_assumption(),),
            validity=ValidityDomain(
                description="Ordered ternary-complex oxidative cleavage, software_tested.",
                labels=("software_tested", "oxidative_cleavage"),
                limitations=("No constants transfer automatically between enzymes or solids.",),
            ),
            source=source,
            notes=notes,
        )
        for key, value in locals().copy().items():
            if key in self.__annotations__:
                object.__setattr__(self, key, value)

    def _constants(self, parameters: ParameterSet) -> dict[str, float]:
        return {
            key: float(parameters.require_quantity(symbol, units).magnitude)
            for key, symbol, units in (
                ("kcat", self.kcat_symbol, "1/second"),
                ("peroxide_km", self.peroxide_km_symbol, self.peroxide_units),
                ("substrate_km", self.substrate_km_symbol, self.state_units),
                ("substrate_binding", self.substrate_binding_symbol, self.state_units),
            )
        }

    def _evaluate(self, s: float, h: float, e: float, constants: dict[str, float]) -> tuple[float, np.ndarray]:
        return peroxide_rate_and_gradient(substrate=s, peroxide=h, enzyme=e, **constants)

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units)
        material = value * self.product_yield
        return {
            self.substrate_state: -material,
            self.product_state: material,
            self.peroxide_state: -value,
            self.cuts_state: value,
        }

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({name: getattr(self, name) for name in self.__annotations__ if name != "product_yield"})
        result["product_yield"] = {"value": self.product_yield.magnitude, "units": str(self.product_yield.units)}
        return result


@dataclass(frozen=True, init=False)
class PeroxideInactivationProcess(_PeroxideKernels, Process):
    """Eq4 substrate-protected inactivation with an explicit inactive pool.

    The damage rate is effective second-order in free enzyme and peroxide.
    The source supplies no peroxide consumption per damage event; the process
    deliberately records only the active/inactive enzyme transfer.
    """

    substrate_state: str
    peroxide_state: str
    enzyme_state: str
    inactive_state: str
    inactivation_constant_symbol: str
    substrate_km_symbol: str
    state_units: str
    peroxide_units: str
    enzyme_units: str
    rate_units: str

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        peroxide_state: str,
        enzyme_state: str,
        inactive_state: str,
        inactivation_constant_symbol: str,
        substrate_km_symbol: str,
        state_units: str,
        peroxide_units: str,
        enzyme_units: str,
        source: str,
        rate_units: str | None = None,
        notes: str = "",
    ) -> None:
        _validate_states(
            (substrate_state, peroxide_state, enzyme_state, inactive_state), state_units, peroxide_units, enzyme_units
        )
        if not source.strip():
            raise ValueError("Peroxide inactivation requires a source.")
        rate_units = rate_units or f"{enzyme_units}/second"
        Process.__init__(
            self,
            name=name,
            process_type="peroxide_inactivation",
            required_state_variables=(
                StateVariableSpec(substrate_state, state_units, role="substrate"),
                StateVariableSpec(peroxide_state, peroxide_units, role="peroxide"),
                StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"),
            ),
            changed_state_variables=(
                StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"),
                StateVariableSpec(inactive_state, enzyme_units, role="inactive_enzyme"),
            ),
            required_parameters=(
                ParameterRequirement(inactivation_constant_symbol, f"1/({peroxide_units}*second)"),
                ParameterRequirement(substrate_km_symbol, state_units),
            ),
            assumptions=(_assumption(),),
            validity=ValidityDomain(
                description="Reduced peroxide-dependent free-enzyme inactivation, software_tested.",
                labels=("software_tested", "peroxide"),
                limitations=(
                    "Peroxide use in unproductive chemistry is not quantified by this effective enzyme damage law.",
                ),
            ),
            source=source,
            notes=notes,
        )
        for key, value in locals().copy().items():
            if key in self.__annotations__:
                object.__setattr__(self, key, value)

    def _constants(self, parameters: ParameterSet) -> dict[str, float]:
        return {
            "inactivation_constant": float(
                parameters.require_quantity(
                    self.inactivation_constant_symbol, f"1/({self.peroxide_units}*second)"
                ).magnitude
            ),
            "substrate_km": float(parameters.require_quantity(self.substrate_km_symbol, self.state_units).magnitude),
        }

    def _evaluate(self, s: float, h: float, e: float, constants: dict[str, float]) -> tuple[float, np.ndarray]:
        return peroxide_inactivation_rate_and_gradient(substrate=s, peroxide=h, enzyme=e, **constants)

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units)
        return {self.enzyme_state: cast(Quantity, -value), self.inactive_state: value}

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({name: getattr(self, name) for name in self.__annotations__})
        return result
