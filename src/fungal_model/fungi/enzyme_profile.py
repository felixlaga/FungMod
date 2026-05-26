"""Fungal enzyme capability metadata and secretion rate laws."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity


def enzyme_secretion_assumption() -> Assumption:
    """Return the Stage 6 enzyme secretion assumption."""

    return Assumption(
        name="active biomass secretes extracellular enzyme",
        description="Secreted enzyme concentration changes according to dE/dt = alpha_E * B_active.",
        justification="A minimal coupling between active fungal biomass and extracellular enzyme availability.",
        known_limitations=(
            "Does not model gene regulation, induction/repression, secretion "
            "pathway saturation, enzyme-specific protein mass, or spatial secretion."
        ),
        source="Stage 6 modelling assumption for biomass-dependent enzyme secretion.",
    )


def enzyme_decay_assumption() -> Assumption:
    """Return the Stage 6 extracellular enzyme decay assumption."""

    return Assumption(
        name="first-order extracellular enzyme decay",
        description="Secreted active enzyme decays according to dE/dt = -delta_E * E.",
        justification="A minimal loss term is needed so enzyme does not persist indefinitely.",
        known_limitations="Does not distinguish proteolysis, denaturation, adsorption loss, or irreversible inactivation mechanisms.",
        source="Stage 6 modelling assumption for enzyme degradation.",
    )


def enzyme_production_cost_assumption() -> Assumption:
    """Return the Stage 6 enzyme production cost assumption."""

    return Assumption(
        name="enzyme secretion has active biomass cost",
        description="Active biomass is depleted by a cost proportional to the enzyme secretion rate.",
        justification="Extracellular enzyme production must not be free.",
        known_limitations=(
            "The cost coefficient lumps reactor volume, protein composition, "
            "biosynthetic energy, and maintenance burden into one parameter."
        ),
        source="Stage 6 modelling assumption enforcing non-free enzyme production.",
    )


@dataclass(frozen=True)
class EnzymeCapability:
    """A fungus-encoded or observed extracellular enzyme capability."""

    name: str
    enzyme_class: str
    target_substrate: str
    target_bond_type: str
    evidence: str
    source: str | None
    notes: str = ""

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if allow_unsourced_for_testing:
            return
        if not has_text(self.source):
            raise ProvenanceError(f"Enzyme capability {self.name!r} is missing a source.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enzyme_class": self.enzyme_class,
            "target_substrate": self.target_substrate,
            "target_bond_type": self.target_bond_type,
            "evidence": self.evidence,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class EnzymeProfile:
    """A collection of extracellular enzyme capabilities."""

    capabilities: tuple[EnzymeCapability, ...] = field(default_factory=tuple)
    source: str | None = None
    notes: str = ""

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError("EnzymeProfile is missing a source.")
        for capability in self.capabilities:
            capability.validate(allow_unsourced_for_testing=allow_unsourced_for_testing)

    def supports_substrate(self, substrate_name: str) -> bool:
        normalized = substrate_name.casefold()
        return any(
            capability.target_substrate.casefold() == normalized
            for capability in self.capabilities
        )

    def compatible_capabilities(
        self,
        *,
        substrate_name: str,
        bond_type: str,
        enzyme_class: str | None = None,
    ) -> tuple[EnzymeCapability, ...]:
        """Return capabilities matching a substrate, bond, and optional enzyme class."""

        normalized_substrate = substrate_name.casefold()
        normalized_bond = bond_type.casefold()
        normalized_class = None if enzyme_class is None else enzyme_class.casefold()
        return tuple(
            capability
            for capability in self.capabilities
            if capability.target_substrate.casefold() == normalized_substrate
            and capability.target_bond_type.casefold() == normalized_bond
            and (
                normalized_class is None
                or capability.enzyme_class.casefold() == normalized_class
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": [capability.to_dict() for capability in self.capabilities],
            "source": self.source,
            "notes": self.notes,
        }


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def enzyme_secretion_rate(
    *,
    active_biomass: Quantity,
    secretion_coefficient: Quantity,
    rate_units: str | None = None,
) -> Quantity:
    """Compute biomass-dependent enzyme secretion rate."""

    biomass = require_quantity(active_biomass, name="active_biomass")
    coefficient = require_quantity(secretion_coefficient, name="secretion_coefficient")
    _ensure_non_negative(biomass, "active_biomass")
    _ensure_non_negative(coefficient, "secretion_coefficient")
    rate = coefficient * biomass
    if rate_units is not None:
        return assert_compatible(rate, rate_units, name="enzyme secretion rate")
    return rate


def enzyme_decay_rate(
    *,
    enzyme: Quantity,
    decay_constant: Quantity,
    rate_units: str | None = None,
) -> Quantity:
    """Compute first-order extracellular enzyme decay rate."""

    enzyme_quantity = require_quantity(enzyme, name="enzyme")
    decay = require_quantity(decay_constant, name="decay_constant")
    _ensure_non_negative(enzyme_quantity, "enzyme")
    _ensure_non_negative(decay, "decay_constant")
    rate = decay * enzyme_quantity
    if rate_units is not None:
        return assert_compatible(rate, rate_units, name="enzyme decay rate")
    return rate


def enzyme_production_cost_rate(
    *,
    secretion_rate: Quantity,
    secretion_cost: Quantity,
    rate_units: str | None = None,
) -> Quantity:
    """Compute active biomass cost associated with enzyme secretion."""

    rate = require_quantity(secretion_rate, name="secretion_rate")
    cost = require_quantity(secretion_cost, name="secretion_cost")
    _ensure_non_negative(rate, "secretion_rate")
    _ensure_non_negative(cost, "secretion_cost")
    biomass_loss = cost * rate
    if rate_units is not None:
        return assert_compatible(biomass_loss, rate_units, name="enzyme production cost rate")
    return biomass_loss


@dataclass(frozen=True)
class EnzymeSecretionRateLaw:
    """Callable ``dE/dt = alpha_E * B_active`` rate law."""

    active_biomass: str
    secretion_symbol: str
    rate_units: str
    biomass_units: str = "kilogram"

    @property
    def assumptions(self) -> list[Assumption]:
        return [enzyme_secretion_assumption()]

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        return enzyme_secretion_rate(
            active_biomass=assert_compatible(
                state[self.active_biomass],
                self.biomass_units,
                name=self.active_biomass,
            ),
            secretion_coefficient=parameters.require_quantity(
                self.secretion_symbol,
                f"{self.rate_units} / {self.biomass_units}",
            ),
            rate_units=self.rate_units,
        )


@dataclass(frozen=True)
class EnzymeDecayRateLaw:
    """Callable first-order enzyme decay rate law."""

    enzyme: str
    decay_symbol: str
    rate_units: str
    enzyme_units: str

    @property
    def assumptions(self) -> list[Assumption]:
        return [enzyme_decay_assumption()]

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        return enzyme_decay_rate(
            enzyme=assert_compatible(state[self.enzyme], self.enzyme_units, name=self.enzyme),
            decay_constant=parameters.require_quantity(self.decay_symbol, "1 / second"),
            rate_units=self.rate_units,
        )


@dataclass(frozen=True)
class EnzymeProductionCostRateLaw:
    """Callable biomass-cost rate law tied to enzyme secretion."""

    active_biomass: str
    secretion_symbol: str
    secretion_cost_symbol: str
    enzyme_rate_units: str
    biomass_rate_units: str
    biomass_units: str = "kilogram"

    @property
    def assumptions(self) -> list[Assumption]:
        return [enzyme_production_cost_assumption(), enzyme_secretion_assumption()]

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        secretion = enzyme_secretion_rate(
            active_biomass=assert_compatible(
                state[self.active_biomass],
                self.biomass_units,
                name=self.active_biomass,
            ),
            secretion_coefficient=parameters.require_quantity(
                self.secretion_symbol,
                f"{self.enzyme_rate_units} / {self.biomass_units}",
            ),
            rate_units=self.enzyme_rate_units,
        )
        del time
        return enzyme_production_cost_rate(
            secretion_rate=secretion,
            secretion_cost=parameters.require_quantity(
                self.secretion_cost_symbol,
                f"{self.biomass_units} / ({self.enzyme_rate_units} * second)",
            ),
            rate_units=self.biomass_rate_units,
        )


__all__ = [
    "EnzymeCapability",
    "EnzymeDecayRateLaw",
    "EnzymeProductionCostRateLaw",
    "EnzymeProfile",
    "EnzymeSecretionRateLaw",
    "enzyme_decay_assumption",
    "enzyme_decay_rate",
    "enzyme_production_cost_assumption",
    "enzyme_production_cost_rate",
    "enzyme_secretion_assumption",
    "enzyme_secretion_rate",
]
