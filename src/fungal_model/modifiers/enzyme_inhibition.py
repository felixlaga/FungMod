"""Provenance-bound enzyme-inhibition rate modifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment


_SUPPORTED_MATURITY = "literature_backed_software_tested"


def _law_metadata(*, primary_source: str, maturity: str) -> tuple[str, str]:
    source = primary_source.strip()
    label = maturity.strip()
    if not source:
        raise ValueError("Enzyme-inhibition law requires a nonblank primary_source.")
    if label != _SUPPORTED_MATURITY:
        raise ValueError(
            "Enzyme-inhibition law maturity must be "
            f"{_SUPPORTED_MATURITY!r}; received {label!r}."
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

    def __post_init__(self) -> None:
        source, maturity = _law_metadata(
            primary_source=self.primary_source,
            maturity=self.maturity,
        )
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)

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

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "competitive_inhibition",
            "substrate_state": self.substrate_state,
            "inhibitor_state": self.inhibitor_state,
            "michaelis_constant_symbol": self.michaelis_constant_symbol,
            "inhibition_constant_symbol": self.inhibition_constant_symbol,
            "substrate_units": self.substrate_units,
            "inhibitor_units": self.inhibitor_units,
            "primary_source": self.primary_source,
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

    def __post_init__(self) -> None:
        source, maturity = _law_metadata(
            primary_source=self.primary_source,
            maturity=self.maturity,
        )
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)

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

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "substrate_inhibition",
            "substrate_state": self.substrate_state,
            "michaelis_constant_symbol": self.michaelis_constant_symbol,
            "inhibition_constant_symbol": self.inhibition_constant_symbol,
            "substrate_units": self.substrate_units,
            "primary_source": self.primary_source,
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

    def __post_init__(self) -> None:
        source, maturity = _law_metadata(
            primary_source=self.primary_source,
            maturity=self.maturity,
        )
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)

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
            km_values * (1.0 + product_values / product_ki_values) ** 2
            + substrate_values * (1.0 + substrate_values / substrate_ki_values)
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

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": "coupled_substrate_product_inhibition",
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
            "maturity": self.maturity,
            "equation": (
                "(K_m + S) / (K_m * (1 + P / K_p)^2 + "
                "S * (1 + S / K_i))"
            ),
        }


__all__ = [
    "CompetitiveInhibitionModifier",
    "CoupledSubstrateProductInhibitionModifier",
    "SubstrateInhibitionModifier",
]
