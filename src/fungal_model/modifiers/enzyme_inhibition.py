"""Provenance-bound enzyme-inhibition rate modifiers for a Michaelis-Menten base.

Every law here separates the fixed ``law_source`` (the textbook or paper that
defines the algebra) from the user-declared ``primary_source`` (the study that
supplies the constants) and carries a declared maturity label. The
general reversible-inhibition taxonomy follows Cornish-Bowden (2012):
``v = V S / (K_m alpha + S beta)`` with ``alpha = 1 + sum_i I_i / K_ic,i``
(competitive terms) and ``beta = 1 + sum_i I_i / K_iu,i`` (uncompetitive
terms). Haldane substrate inhibition follows Andrews (1968).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.kinetics._coupled_inhibition import (
    coupled_inhibition_denominator,
    coupled_inhibition_denominator_gradient,
)
from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.modifiers.base import CONDITION_STATE

MATURITY_LITERATURE_BACKED = "literature_backed_software_tested"
MATURITY_FRAMEWORK_BENCHMARK = "framework_benchmark"
SUPPORTED_INHIBITION_MATURITIES: tuple[str, ...] = (
    MATURITY_LITERATURE_BACKED,
    MATURITY_FRAMEWORK_BENCHMARK,
)

CORNISH_BOWDEN_2012_SOURCE = (
    "Cornish-Bowden A. (2012) Fundamentals of Enzyme Kinetics, 4th ed. Wiley-Blackwell, Weinheim; "
    "chapter 6, reversible inhibition: v = V S / (K_m (1 + I / K_ic) + S (1 + I / K_iu))"
)
ANDREWS_1968_SOURCE = (
    "Andrews J.F. (1968) A mathematical model for the continuous culture of microorganisms utilizing "
    "inhibitory substrates. Biotechnol. Bioeng. 10:707-723, doi:10.1002/bit.260100602"
)
KARI_2020_SOURCE = (
    "Kari J. et al. (2020) Biochem. J. 477:1971, doi:10.1042/BCJ20200083 (mixed inhibition of cellulases "
    "reported in the Cornish-Bowden frame)"
)

MECHANISM_COMPETITIVE = "competitive"
MECHANISM_UNCOMPETITIVE = "uncompetitive"
MECHANISM_NONCOMPETITIVE = "noncompetitive"
MECHANISM_MIXED = "mixed"
INHIBITION_MECHANISMS: tuple[str, ...] = (
    MECHANISM_COMPETITIVE,
    MECHANISM_UNCOMPETITIVE,
    MECHANISM_NONCOMPETITIVE,
    MECHANISM_MIXED,
)


def _law_metadata(*, primary_source: str, maturity: str) -> tuple[str, str]:
    source = primary_source.strip()
    label = maturity.strip()
    if not source:
        raise ValueError("Enzyme-inhibition law requires a nonblank primary_source.")
    if label not in SUPPORTED_INHIBITION_MATURITIES:
        raise ValueError(
            "Enzyme-inhibition law maturity must be one of "
            f"{list(SUPPORTED_INHIBITION_MATURITIES)}; received {label!r}."
        )
    return source, label


def _nonnegative(quantity: Quantity, *, name: str) -> np.ndarray:
    values = np.asarray(quantity.magnitude, dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0.0):
        raise ValueError(f"{name} must be finite and nonnegative.")
    return values


def _positive(quantity: Quantity, *, name: str) -> np.ndarray:
    values = np.asarray(quantity.magnitude, dtype=float)
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        raise ValueError(f"{name} must be finite and positive.")
    return values


def _nonnegative_scalar(value: float, *, name: str) -> float:
    if not np.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative.")
    return value


def _positive_scalar(value: float, *, name: str) -> float:
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
    return value


@dataclass(frozen=True)
class CompetitiveInhibitionModifier:
    """Competitive-inhibition correction for a Michaelis-Menten base rate."""

    substrate_state: str
    inhibitor_state: str
    michaelis_constant_symbol: str
    inhibition_constant_symbol: str
    substrate_units: str
    inhibitor_units: str
    primary_source: str
    maturity: str
    name: str = "competitive_inhibition_modifier"
    law_source: str = CORNISH_BOWDEN_2012_SOURCE

    def __post_init__(self) -> None:
        source, maturity = _law_metadata(
            primary_source=self.primary_source,
            maturity=self.maturity,
        )
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)

    @property
    def condition(self) -> str:
        return CONDITION_STATE

    @property
    def read_states(self) -> tuple[tuple[str, str], ...]:
        return ((self.substrate_state, self.substrate_units), (self.inhibitor_state, self.inhibitor_units))

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            Assumption(
                name="single-inhibitor competitive Michaelis-Menten inhibition",
                description=(
                    "A homogeneous Michaelis-Menten base rate is multiplied by "
                    "(K_m + S) / (K_m * (1 + I / K_i) + S)."
                ),
                justification=(
                    "This is the explicit single-substrate competitive-inhibition "
                    "correction selected by the configured mechanism."
                ),
                known_limitations=(
                    "One inhibitor and one homogeneous Michaelis-Menten substrate "
                    "only; no mixed, uncompetitive, irreversible, time-dependent, "
                    "allosteric, transport, toxicity, or whole-organism inference."
                ),
                source=self.primary_source,
            ),
        )

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del environment
        if state is None:
            raise ValueError("CompetitiveInhibitionModifier requires solver state.")
        if self.substrate_state not in state or self.inhibitor_state not in state:
            raise ValueError(
                "CompetitiveInhibitionModifier requires configured substrate and "
                "inhibitor states."
            )
        substrate = assert_compatible(
            state[self.substrate_state],
            self.substrate_units,
            name=self.substrate_state,
        )
        inhibitor = assert_compatible(
            state[self.inhibitor_state],
            self.inhibitor_units,
            name=self.inhibitor_state,
        )
        km = parameters.require_quantity(
            self.michaelis_constant_symbol,
            self.substrate_units,
        )
        ki = parameters.require_quantity(
            self.inhibition_constant_symbol,
            self.inhibitor_units,
        )
        substrate_values = _nonnegative(substrate, name=self.substrate_state)
        inhibitor_values = _nonnegative(inhibitor, name=self.inhibitor_state)
        km_values = _positive(km, name=self.michaelis_constant_symbol)
        ki_values = _positive(ki, name=self.inhibition_constant_symbol)
        ratio = inhibitor_values / ki_values
        activity = (km_values + substrate_values) / (
            km_values * (1.0 + ratio) + substrate_values
        )
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
            rate
            * self.activity(
                parameters=parameters,
                environment=environment,
                state=state,
            ),
            str(rate.units),
            name="competitive-inhibition-scaled rate",
        )

    def _compiled_constants(self, context: KernelContext) -> tuple[int, float, int, float, float, float]:
        substrate_index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        inhibitor_index, to_inhibitor = context.state_slot(self.inhibitor_state, self.inhibitor_units)
        km = _positive_scalar(context.parameter(self.michaelis_constant_symbol, self.substrate_units),
                              name=self.michaelis_constant_symbol)
        ki = _positive_scalar(context.parameter(self.inhibition_constant_symbol, self.inhibitor_units),
                              name=self.inhibition_constant_symbol)
        return substrate_index, to_substrate, inhibitor_index, to_inhibitor, km, ki

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        substrate_index, to_substrate, inhibitor_index, to_inhibitor, km, ki = self._compiled_constants(context)
        substrate_name, inhibitor_name = self.substrate_state, self.inhibitor_state

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            inhibitor = _nonnegative_scalar(state[inhibitor_index] * to_inhibitor, name=inhibitor_name)
            ratio = inhibitor / ki
            return (km + substrate) / (km * (1.0 + ratio) + substrate)

        return kernel

    def compile_activity_gradient(self, context: KernelContext) -> JacobianKernel | None:
        """``D = K_m (1 + I / K_i) + S``; ``da/dS = K_m (I / K_i) / D^2``; ``da/dI = -(K_m + S) K_m / (K_i D^2)``."""

        substrate_index, to_substrate, inhibitor_index, to_inhibitor, km, ki = self._compiled_constants(context)
        size = len(context.state_index)
        substrate_name, inhibitor_name = self.substrate_state, self.inhibitor_state

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            inhibitor = _nonnegative_scalar(state[inhibitor_index] * to_inhibitor, name=inhibitor_name)
            denominator = km * (1.0 + inhibitor / ki) + substrate
            result = np.zeros(size, dtype=float)
            result[substrate_index] += km * (inhibitor / ki) / denominator**2 * to_substrate
            result[inhibitor_index] += -(km + substrate) * km / (ki * denominator**2) * to_inhibitor
            return result

        return gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "competitive_inhibition",
            "mechanism": MECHANISM_COMPETITIVE,
            "substrate_state": self.substrate_state,
            "inhibitor_state": self.inhibitor_state,
            "michaelis_constant_symbol": self.michaelis_constant_symbol,
            "inhibition_constant_symbol": self.inhibition_constant_symbol,
            "substrate_units": self.substrate_units,
            "inhibitor_units": self.inhibitor_units,
            "primary_source": self.primary_source,
            "law_source": self.law_source,
            "maturity": self.maturity,
            "equation": (
                "(K_m + S) / (K_m * (1 + I / K_i) + S)"
            ),
        }


@dataclass(frozen=True)
class SubstrateInhibitionModifier:
    """Haldane substrate-inhibition correction for a Michaelis-Menten base rate."""

    substrate_state: str
    michaelis_constant_symbol: str
    inhibition_constant_symbol: str
    substrate_units: str
    primary_source: str
    maturity: str
    name: str = "substrate_inhibition_modifier"
    law_source: str = ANDREWS_1968_SOURCE

    def __post_init__(self) -> None:
        source, maturity = _law_metadata(
            primary_source=self.primary_source,
            maturity=self.maturity,
        )
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)

    @property
    def condition(self) -> str:
        return CONDITION_STATE

    @property
    def read_states(self) -> tuple[tuple[str, str], ...]:
        return ((self.substrate_state, self.substrate_units),)

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            Assumption(
                name="single-substrate Haldane inhibition",
                description=(
                    "A homogeneous Michaelis-Menten base rate is multiplied by "
                    "(K_m + S) / (K_m + S + S^2 / K_i)."
                ),
                justification=(
                    "This yields the configured Haldane substrate-inhibition law "
                    "without changing the generic base process."
                ),
                known_limitations=(
                    "One homogeneous substrate only; the law does not identify a "
                    "molecular inhibition mechanism or model transport, toxicity, "
                    "growth, mixed substrates, or whole-organism physiology."
                ),
                source=self.primary_source,
            ),
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
            raise ValueError(
                "SubstrateInhibitionModifier requires its configured substrate state."
            )
        substrate = assert_compatible(
            state[self.substrate_state],
            self.substrate_units,
            name=self.substrate_state,
        )
        km = parameters.require_quantity(
            self.michaelis_constant_symbol,
            self.substrate_units,
        )
        ki = parameters.require_quantity(
            self.inhibition_constant_symbol,
            self.substrate_units,
        )
        substrate_values = _nonnegative(substrate, name=self.substrate_state)
        km_values = _positive(km, name=self.michaelis_constant_symbol)
        ki_values = _positive(ki, name=self.inhibition_constant_symbol)
        activity = (km_values + substrate_values) / (
            km_values + substrate_values + substrate_values**2 / ki_values
        )
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
            rate
            * self.activity(
                parameters=parameters,
                environment=environment,
                state=state,
            ),
            str(rate.units),
            name="substrate-inhibition-scaled rate",
        )

    def _compiled_constants(self, context: KernelContext) -> tuple[int, float, float, float]:
        substrate_index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        km = _positive_scalar(context.parameter(self.michaelis_constant_symbol, self.substrate_units),
                              name=self.michaelis_constant_symbol)
        ki = _positive_scalar(context.parameter(self.inhibition_constant_symbol, self.substrate_units),
                              name=self.inhibition_constant_symbol)
        return substrate_index, to_substrate, km, ki

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        substrate_index, to_substrate, km, ki = self._compiled_constants(context)
        substrate_name = self.substrate_state

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            return (km + substrate) / (km + substrate + substrate**2 / ki)

        return kernel

    def compile_activity_gradient(self, context: KernelContext) -> JacobianKernel | None:
        """``D = K_m + S + S^2 / K_i``; ``da/dS = [D - (K_m + S)(1 + 2 S / K_i)] / D^2``."""

        substrate_index, to_substrate, km, ki = self._compiled_constants(context)
        size = len(context.state_index)
        substrate_name = self.substrate_state

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            denominator = km + substrate + substrate**2 / ki
            result = np.zeros(size, dtype=float)
            result[substrate_index] = (
                (denominator - (km + substrate) * (1.0 + 2.0 * substrate / ki)) / denominator**2 * to_substrate
            )
            return result

        return gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "substrate_inhibition",
            "mechanism": "haldane_substrate_inhibition",
            "substrate_state": self.substrate_state,
            "michaelis_constant_symbol": self.michaelis_constant_symbol,
            "inhibition_constant_symbol": self.inhibition_constant_symbol,
            "substrate_units": self.substrate_units,
            "primary_source": self.primary_source,
            "law_source": self.law_source,
            "maturity": self.maturity,
            "equation": "(K_m + S) / (K_m + S + S^2 / K_i)",
        }


@dataclass(frozen=True)
class CoupledSubstrateProductInhibitionModifier:
    """Published combined substrate and double product-inhibition correction."""

    substrate_state: str
    product_state: str
    michaelis_constant_symbol: str
    substrate_inhibition_constant_symbol: str
    product_inhibition_constant_symbol: str
    substrate_units: str
    product_units: str
    primary_source: str
    maturity: str
    name: str = "coupled_substrate_product_inhibition_modifier"
    law_source: str = CORNISH_BOWDEN_2012_SOURCE

    def __post_init__(self) -> None:
        source, maturity = _law_metadata(
            primary_source=self.primary_source,
            maturity=self.maturity,
        )
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)

    @property
    def condition(self) -> str:
        return CONDITION_STATE

    @property
    def read_states(self) -> tuple[tuple[str, str], ...]:
        return ((self.substrate_state, self.substrate_units), (self.product_state, self.product_units))

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            Assumption(
                name="coupled substrate and double product inhibition",
                description=(
                    "A homogeneous Michaelis-Menten base rate is multiplied by "
                    "(K_m + S) / (K_m * (1 + P / K_p)^2 + S * (1 + S / K_i))."
                ),
                justification=(
                    "This preserves the explicitly selected combined rate law without "
                    "approximating it as independently composable modifiers."
                ),
                known_limitations=(
                    "One substrate and one product state only. The squared product term "
                    "is an empirical kinetic form for the sourced enzyme preparation; "
                    "it does not establish elementary binding steps, transfer to other "
                    "enzymes, transport, growth, or whole-organism physiology."
                ),
                source=self.primary_source,
            ),
        )

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del environment
        if state is None:
            raise ValueError(
                "CoupledSubstrateProductInhibitionModifier requires solver state."
            )
        if self.substrate_state not in state or self.product_state not in state:
            raise ValueError(
                "CoupledSubstrateProductInhibitionModifier requires configured "
                "substrate and product states."
            )
        substrate = assert_compatible(
            state[self.substrate_state],
            self.substrate_units,
            name=self.substrate_state,
        )
        product = assert_compatible(
            state[self.product_state],
            self.product_units,
            name=self.product_state,
        )
        km = parameters.require_quantity(
            self.michaelis_constant_symbol,
            self.substrate_units,
        )
        substrate_ki = parameters.require_quantity(
            self.substrate_inhibition_constant_symbol,
            self.substrate_units,
        )
        product_ki = parameters.require_quantity(
            self.product_inhibition_constant_symbol,
            self.product_units,
        )
        substrate_values = _nonnegative(substrate, name=self.substrate_state)
        product_values = _nonnegative(product, name=self.product_state)
        km_values = _positive(km, name=self.michaelis_constant_symbol)
        substrate_ki_values = _positive(
            substrate_ki,
            name=self.substrate_inhibition_constant_symbol,
        )
        product_ki_values = _positive(
            product_ki,
            name=self.product_inhibition_constant_symbol,
        )
        activity = (km_values + substrate_values) / (
            coupled_inhibition_denominator(
                substrate_values, product_values, km_values, substrate_ki_values, product_ki_values,
            )
        )
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
            rate
            * self.activity(
                parameters=parameters,
                environment=environment,
                state=state,
            ),
            str(rate.units),
            name="coupled-substrate-product-inhibition-scaled rate",
        )

    def _compiled_constants(self, context: KernelContext) -> tuple[int, float, int, float, float, float, float]:
        substrate_index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        product_index, to_product = context.state_slot(self.product_state, self.product_units)
        km = _positive_scalar(context.parameter(self.michaelis_constant_symbol, self.substrate_units),
                              name=self.michaelis_constant_symbol)
        substrate_ki = _positive_scalar(
            context.parameter(self.substrate_inhibition_constant_symbol, self.substrate_units),
            name=self.substrate_inhibition_constant_symbol,
        )
        product_ki = _positive_scalar(
            context.parameter(self.product_inhibition_constant_symbol, self.product_units),
            name=self.product_inhibition_constant_symbol,
        )
        return substrate_index, to_substrate, product_index, to_product, km, substrate_ki, product_ki

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        (substrate_index, to_substrate, product_index, to_product,
         km, substrate_ki, product_ki) = self._compiled_constants(context)
        substrate_name, product_name = self.substrate_state, self.product_state

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            product = _nonnegative_scalar(state[product_index] * to_product, name=product_name)
            return (km + substrate) / coupled_inhibition_denominator(substrate, product, km, substrate_ki, product_ki)

        return kernel

    def compile_activity_gradient(self, context: KernelContext) -> JacobianKernel | None:
        """Quotient rule over the published denominator ``D``.

        ``da/dS = [D - (K_m + S) dD/dS] / D^2`` and ``da/dP = -(K_m + S) dD/dP / D^2``
        with ``dD/dS = 1 + 2 S / K_i`` and ``dD/dP = 2 K_m (1 + P / K_p) / K_p``.
        """

        (substrate_index, to_substrate, product_index, to_product,
         km, substrate_ki, product_ki) = self._compiled_constants(context)
        size = len(context.state_index)
        substrate_name, product_name = self.substrate_state, self.product_state

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            product = _nonnegative_scalar(state[product_index] * to_product, name=product_name)
            denominator = coupled_inhibition_denominator(substrate, product, km, substrate_ki, product_ki)
            d_substrate, d_product = coupled_inhibition_denominator_gradient(
                substrate, product, km, substrate_ki, product_ki
            )
            result = np.zeros(size, dtype=float)
            result[substrate_index] += (denominator - (km + substrate) * d_substrate) / denominator**2 * to_substrate
            result[product_index] += -(km + substrate) * d_product / denominator**2 * to_product
            return result

        return gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "coupled_substrate_product_inhibition",
            "mechanism": "coupled_substrate_and_double_product_inhibition",
            "substrate_state": self.substrate_state,
            "product_state": self.product_state,
            "michaelis_constant_symbol": self.michaelis_constant_symbol,
            "substrate_inhibition_constant_symbol": (
                self.substrate_inhibition_constant_symbol
            ),
            "product_inhibition_constant_symbol": (
                self.product_inhibition_constant_symbol
            ),
            "substrate_units": self.substrate_units,
            "product_units": self.product_units,
            "primary_source": self.primary_source,
            "law_source": self.law_source,
            "maturity": self.maturity,
            "equation": (
                "(K_m + S) / (K_m * (1 + P / K_p)^2 + "
                "S * (1 + S / K_i))"
            ),
        }


@dataclass(frozen=True)
class InhibitorTerm:
    """One inhibitor of the general reversible-inhibition law.

    ``competitive_constant_symbol`` names ``K_ic`` (the term in alpha) and
    ``uncompetitive_constant_symbol`` names ``K_iu`` (the term in beta).
    ``None`` means that term is absent by explicit declaration; the
    ``mechanism`` label fixes which combination is allowed, and a missing
    constant is refused rather than defaulted.
    """

    state: str
    units: str
    mechanism: str
    competitive_constant_symbol: str | None = None
    uncompetitive_constant_symbol: str | None = None

    def __post_init__(self) -> None:
        state = self.state.strip()
        mechanism = self.mechanism.strip()
        competitive = _clean_symbol(self.competitive_constant_symbol)
        uncompetitive = _clean_symbol(self.uncompetitive_constant_symbol)
        if not state:
            raise ValueError("InhibitorTerm requires a nonblank state.")
        if mechanism not in INHIBITION_MECHANISMS:
            raise ValueError(
                f"InhibitorTerm mechanism must be one of {list(INHIBITION_MECHANISMS)}; received {mechanism!r}."
            )
        if mechanism == MECHANISM_COMPETITIVE and (competitive is None or uncompetitive is not None):
            raise ValueError(
                f"Competitive inhibitor {state!r} requires competitive_constant_symbol (K_ic) and no "
                "uncompetitive_constant_symbol."
            )
        if mechanism == MECHANISM_UNCOMPETITIVE and (uncompetitive is None or competitive is not None):
            raise ValueError(
                f"Uncompetitive inhibitor {state!r} requires uncompetitive_constant_symbol (K_iu) and no "
                "competitive_constant_symbol."
            )
        if mechanism == MECHANISM_NONCOMPETITIVE and (
            competitive is None or uncompetitive is None or competitive != uncompetitive
        ):
            raise ValueError(
                f"Noncompetitive inhibitor {state!r} requires one symbol declared for both K_ic and K_iu."
            )
        if mechanism == MECHANISM_MIXED and (competitive is None or uncompetitive is None):
            raise ValueError(
                f"Mixed inhibitor {state!r} requires both competitive_constant_symbol (K_ic) and "
                "uncompetitive_constant_symbol (K_iu)."
            )
        if mechanism == MECHANISM_MIXED and competitive == uncompetitive:
            raise ValueError(
                f"Mixed inhibitor {state!r} declares one symbol for K_ic and K_iu; declare mechanism "
                "'noncompetitive' for that case."
            )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "mechanism", mechanism)
        object.__setattr__(self, "competitive_constant_symbol", competitive)
        object.__setattr__(self, "uncompetitive_constant_symbol", uncompetitive)

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "units": self.units,
            "mechanism": self.mechanism,
            "competitive_constant_symbol": self.competitive_constant_symbol,
            "uncompetitive_constant_symbol": self.uncompetitive_constant_symbol,
        }


def _clean_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    symbol = str(value).strip()
    return symbol or None


@dataclass(frozen=True)
class MixedInhibitionModifier:
    """General reversible inhibition of a Michaelis-Menten base by one or more inhibitors.

    ``a = (K_m + S) / (K_m alpha + S beta)`` with ``alpha = 1 + sum_i I_i / K_ic,i``
    and ``beta = 1 + sum_i I_i / K_iu,i`` (Cornish-Bowden 2012). Each inhibitor
    declares its mechanism: competitive (only ``K_ic``), uncompetitive (only
    ``K_iu``), noncompetitive (one constant for both) or mixed (both).
    """

    substrate_state: str
    michaelis_constant_symbol: str
    substrate_units: str
    inhibitors: tuple[InhibitorTerm, ...]
    primary_source: str
    maturity: str
    name: str = "mixed_inhibition_modifier"
    law_source: str = CORNISH_BOWDEN_2012_SOURCE

    def __post_init__(self) -> None:
        source, maturity = _law_metadata(
            primary_source=self.primary_source,
            maturity=self.maturity,
        )
        inhibitors = tuple(self.inhibitors)
        if not inhibitors:
            raise ValueError("MixedInhibitionModifier requires at least one inhibitor term.")
        states = [term.state for term in inhibitors]
        if len(set(states)) != len(states):
            raise ValueError(
                f"MixedInhibitionModifier declares an inhibitor state more than once: {sorted(states)}."
            )
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)
        object.__setattr__(self, "inhibitors", inhibitors)

    @property
    def condition(self) -> str:
        return CONDITION_STATE

    @property
    def read_states(self) -> tuple[tuple[str, str], ...]:
        return (
            (self.substrate_state, self.substrate_units),
            *((term.state, term.units) for term in self.inhibitors),
        )

    @property
    def mechanism(self) -> str:
        """The declared mechanism, or the ``+``-joined list for several inhibitors."""

        return "+".join(term.mechanism for term in self.inhibitors)

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            Assumption(
                name="general reversible inhibition of a Michaelis-Menten base",
                description=(
                    "A homogeneous Michaelis-Menten base rate is multiplied by "
                    "(K_m + S) / (K_m * (1 + sum_i I_i / K_ic,i) + S * (1 + sum_i I_i / K_iu,i)); "
                    f"declared mechanism per inhibitor: {self.mechanism}."
                ),
                justification=(
                    "This is the Cornish-Bowden general reversible-inhibition form; competitive, "
                    "uncompetitive, noncompetitive and mixed inhibition are its special cases and the "
                    "configured mechanism names which constants exist. Mixed inhibition of cellulases on "
                    "their substrate is reported in this frame (Kari et al. 2020)."
                ),
                known_limitations=(
                    "Reversible, rapid-equilibrium, single-substrate inhibition on a homogeneous "
                    "Michaelis-Menten base only; inhibitors act independently (no cooperative or "
                    "allosteric terms), and no irreversible, time-dependent, transport, toxicity or "
                    "whole-organism inference is made. Surface (adsorption-site) inhibition is not "
                    "represented by this factor."
                ),
                source=f"{self.law_source}; {KARI_2020_SOURCE}; parameters: {self.primary_source}",
            ),
        )

    def _term_constants(
        self, parameters: ParameterSet
    ) -> tuple[list[np.ndarray | None], list[np.ndarray | None]]:
        competitive: list[np.ndarray | None] = []
        uncompetitive: list[np.ndarray | None] = []
        for term in self.inhibitors:
            competitive.append(
                None
                if term.competitive_constant_symbol is None
                else _positive(
                    parameters.require_quantity(term.competitive_constant_symbol, term.units),
                    name=term.competitive_constant_symbol,
                )
            )
            uncompetitive.append(
                None
                if term.uncompetitive_constant_symbol is None
                else _positive(
                    parameters.require_quantity(term.uncompetitive_constant_symbol, term.units),
                    name=term.uncompetitive_constant_symbol,
                )
            )
        return competitive, uncompetitive

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        del environment
        if state is None:
            raise ValueError("MixedInhibitionModifier requires solver state.")
        missing = [name for name, _ in self.read_states if name not in state]
        if missing:
            raise ValueError(f"MixedInhibitionModifier requires configured states {missing}.")
        substrate_values = _nonnegative(
            assert_compatible(state[self.substrate_state], self.substrate_units, name=self.substrate_state),
            name=self.substrate_state,
        )
        km_values = _positive(
            parameters.require_quantity(self.michaelis_constant_symbol, self.substrate_units),
            name=self.michaelis_constant_symbol,
        )
        competitive, uncompetitive = self._term_constants(parameters)
        alpha = 1.0
        beta = 1.0
        for term, kic, kiu in zip(self.inhibitors, competitive, uncompetitive, strict=True):
            inhibitor = _nonnegative(
                assert_compatible(state[term.state], term.units, name=term.state), name=term.state
            )
            if kic is not None:
                alpha = alpha + inhibitor / kic
            if kiu is not None:
                beta = beta + inhibitor / kiu
        activity = (km_values + substrate_values) / (km_values * alpha + substrate_values * beta)
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
            name="mixed-inhibition-scaled rate",
        )

    def _compiled_constants(
        self, context: KernelContext
    ) -> tuple[int, float, float, tuple[tuple[str, int, float, float | None, float | None], ...]]:
        substrate_index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        km = _positive_scalar(
            context.parameter(self.michaelis_constant_symbol, self.substrate_units),
            name=self.michaelis_constant_symbol,
        )
        terms = []
        for term in self.inhibitors:
            index, to_inhibitor = context.state_slot(term.state, term.units)
            kic = (
                None
                if term.competitive_constant_symbol is None
                else _positive_scalar(
                    context.parameter(term.competitive_constant_symbol, term.units),
                    name=term.competitive_constant_symbol,
                )
            )
            kiu = (
                None
                if term.uncompetitive_constant_symbol is None
                else _positive_scalar(
                    context.parameter(term.uncompetitive_constant_symbol, term.units),
                    name=term.uncompetitive_constant_symbol,
                )
            )
            terms.append((term.state, index, to_inhibitor, kic, kiu))
        return substrate_index, to_substrate, km, tuple(terms)

    def compile_activity(self, context: KernelContext) -> RateKernel | None:
        substrate_index, to_substrate, km, terms = self._compiled_constants(context)
        substrate_name = self.substrate_state

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            alpha = 1.0
            beta = 1.0
            for name, index, to_inhibitor, kic, kiu in terms:
                inhibitor = _nonnegative_scalar(state[index] * to_inhibitor, name=name)
                if kic is not None:
                    alpha += inhibitor / kic
                if kiu is not None:
                    beta += inhibitor / kiu
            return (km + substrate) / (km * alpha + substrate * beta)

        return kernel

    def compile_activity_gradient(self, context: KernelContext) -> JacobianKernel | None:
        """``D = K_m alpha + S beta``; ``da/dS = [D - (K_m + S) beta] / D^2``;
        ``da/dI_i = -(K_m + S)(K_m / K_ic,i + S / K_iu,i) / D^2`` (absent terms are zero)."""

        substrate_index, to_substrate, km, terms = self._compiled_constants(context)
        size = len(context.state_index)
        substrate_name = self.substrate_state

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            substrate = _nonnegative_scalar(state[substrate_index] * to_substrate, name=substrate_name)
            alpha = 1.0
            beta = 1.0
            inhibitors: list[float] = []
            for name, index, to_inhibitor, kic, kiu in terms:
                inhibitor = _nonnegative_scalar(state[index] * to_inhibitor, name=name)
                inhibitors.append(inhibitor)
                if kic is not None:
                    alpha += inhibitor / kic
                if kiu is not None:
                    beta += inhibitor / kiu
            denominator = km * alpha + substrate * beta
            result = np.zeros(size, dtype=float)
            result[substrate_index] += (denominator - (km + substrate) * beta) / denominator**2 * to_substrate
            for (_, index, to_inhibitor, kic, kiu), _inhibitor in zip(terms, inhibitors, strict=True):
                partial = 0.0
                if kic is not None:
                    partial += km / kic
                if kiu is not None:
                    partial += substrate / kiu
                result[index] += -(km + substrate) * partial / denominator**2 * to_inhibitor
            return result

        return gradient

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "mixed_inhibition",
            "mechanism": self.mechanism,
            "substrate_state": self.substrate_state,
            "michaelis_constant_symbol": self.michaelis_constant_symbol,
            "substrate_units": self.substrate_units,
            "inhibitors": [term.to_dict() for term in self.inhibitors],
            "primary_source": self.primary_source,
            "law_source": self.law_source,
            "maturity": self.maturity,
            "equation": (
                "(K_m + S) / (K_m * (1 + sum_i I_i / K_ic,i) + S * (1 + sum_i I_i / K_iu,i))"
            ),
        }


__all__ = [
    "ANDREWS_1968_SOURCE",
    "CORNISH_BOWDEN_2012_SOURCE",
    "CompetitiveInhibitionModifier",
    "CoupledSubstrateProductInhibitionModifier",
    "INHIBITION_MECHANISMS",
    "InhibitorTerm",
    "KARI_2020_SOURCE",
    "MATURITY_FRAMEWORK_BENCHMARK",
    "MATURITY_LITERATURE_BACKED",
    "MixedInhibitionModifier",
    "SUPPORTED_INHIBITION_MATURITIES",
    "SubstrateInhibitionModifier",
]
