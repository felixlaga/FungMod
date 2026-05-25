"""Stoichiometric and elemental bookkeeping interfaces."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError, has_text
from fungal_model.core.units import Quantity, assert_compatible, require_quantity

FORMULA_PATTERN = re.compile(r"([A-Z][a-z]?)(\d*)")

DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE = Parameter(
    name="default stoichiometric absolute tolerance",
    symbol="epsilon_stoich",
    value=1e-12,
    units="dimensionless",
    uncertainty=None,
    source="Numerical tolerance convention for elemental stoichiometry checks; not a physical parameter.",
    confidence_level="testing",
    notes="Used only to compare floating-point stoichiometric balances.",
    measurement_method="software configuration",
)


@dataclass(frozen=True)
class ElementalComposition:
    """Chemical formula parsed into elemental atom counts."""

    formula: str
    elements: dict[str, float]
    source: str | None
    notes: str = ""

    @classmethod
    def from_formula(
        cls,
        formula: str,
        *,
        source: str | None,
        notes: str = "",
    ) -> "ElementalComposition":
        if not has_text(formula):
            raise ValueError("formula must be provided.")
        elements: dict[str, float] = {}
        consumed = ""
        for element, count_text in FORMULA_PATTERN.findall(formula):
            consumed += f"{element}{count_text}"
            count = float(count_text) if count_text else 1.0
            elements[element] = elements.get(element, 0.0) + count
        if consumed != formula or not elements:
            raise ValueError(f"Unsupported chemical formula format: {formula!r}")
        return cls(formula=formula, elements=elements, source=source, notes=notes)

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if allow_unsourced_for_testing:
            return
        if not has_text(self.source):
            raise ProvenanceError(f"Elemental composition {self.formula!r} is missing a source.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "formula": self.formula,
            "elements": dict(self.elements),
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class StoichiometricTerm:
    """A species and its stoichiometric coefficient in a reaction side."""

    species: str
    coefficient: float
    composition: ElementalComposition | None = None

    def __post_init__(self) -> None:
        if self.coefficient < 0:
            raise ValueError("Stoichiometric coefficients must be non-negative.")


@dataclass(frozen=True)
class StoichiometricReactionMetadata:
    """Elemental stoichiometry metadata independent of a numerical rate law."""

    name: str
    reactants: tuple[StoichiometricTerm, ...]
    products: tuple[StoichiometricTerm, ...]
    source: str | None
    notes: str = ""

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError(f"Stoichiometric metadata for {self.name!r} is missing a source.")
        for term in [*self.reactants, *self.products]:
            if term.composition is not None:
                term.composition.validate(allow_unsourced_for_testing=allow_unsourced_for_testing)

    def element_balance(self) -> dict[str, float]:
        """Return products minus reactants for each element."""

        balance: dict[str, float] = {}
        for side, sign in ((self.reactants, -1.0), (self.products, 1.0)):
            for term in side:
                if term.composition is None:
                    raise ValueError(f"Missing elemental composition for {term.species}.")
                for element, count in term.composition.elements.items():
                    balance[element] = balance.get(element, 0.0) + sign * term.coefficient * count
        return balance

    def is_element_balanced(self, *, absolute_tolerance: float | None = None) -> bool:
        tolerance = (
            float(DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE.quantity.magnitude)
            if absolute_tolerance is None
            else absolute_tolerance
        )
        balance = self.element_balance()
        return all(abs(value) <= tolerance for value in balance.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reactants": [
                {
                    "species": term.species,
                    "coefficient": term.coefficient,
                    "composition": None if term.composition is None else term.composition.to_dict(),
                }
                for term in self.reactants
            ],
            "products": [
                {
                    "species": term.species,
                    "coefficient": term.coefficient,
                    "composition": None if term.composition is None else term.composition.to_dict(),
                }
                for term in self.products
            ],
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CarbonContent:
    """Carbon mass fraction for a model state species."""

    species: str
    carbon_fraction: Parameter

    def __post_init__(self) -> None:
        fraction = self.carbon_fraction.quantity
        if fraction is None:
            return
        value = assert_compatible(fraction, "dimensionless", name=self.carbon_fraction.symbol)
        values = np.asarray(value.magnitude, dtype=float)
        if np.any(values < 0.0) or np.any(values > 1.0):
            raise ValueError("carbon_fraction must be between 0 and 1.")

    def carbon_mass(self, quantity: Quantity) -> Quantity:
        material = assert_compatible(require_quantity(quantity, name=self.species), "kilogram", name=self.species)
        fraction = self.carbon_fraction.quantity
        if fraction is None:
            raise UnknownParameterError(f"Carbon fraction for {self.species} is unknown.")
        return assert_compatible(
            material * assert_compatible(fraction, "dimensionless", name=self.carbon_fraction.symbol),
            "kilogram",
            name=f"{self.species} carbon mass",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "species": self.species,
            "carbon_fraction": self.carbon_fraction.to_dict(),
        }


@dataclass(frozen=True)
class OxygenDemand:
    """Oxygen demand per consumed substrate mass for an aerobic process."""

    process_name: str
    substrate_species: str
    oxygen_per_substrate: Parameter

    def __post_init__(self) -> None:
        demand = self.oxygen_per_substrate.quantity
        if demand is None:
            return
        value = assert_compatible(
            demand,
            "kilogram / kilogram",
            name=self.oxygen_per_substrate.symbol,
        )
        if np.any(np.asarray(value.magnitude, dtype=float) < 0):
            raise ValueError("oxygen_per_substrate must be non-negative.")

    def required_oxygen(self, substrate_consumed: Quantity) -> Quantity:
        consumed = assert_compatible(
            require_quantity(substrate_consumed, name="substrate_consumed"),
            "kilogram",
            name="substrate_consumed",
        )
        demand = self.oxygen_per_substrate.quantity
        if demand is None:
            raise UnknownParameterError(f"Oxygen demand for {self.process_name} is unknown.")
        return assert_compatible(
            consumed * assert_compatible(demand, "kilogram / kilogram", name=self.oxygen_per_substrate.symbol),
            "kilogram",
            name=f"{self.process_name} oxygen demand",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_name": self.process_name,
            "substrate_species": self.substrate_species,
            "oxygen_per_substrate": self.oxygen_per_substrate.to_dict(),
        }


__all__ = [
    "CarbonContent",
    "DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE",
    "ElementalComposition",
    "OxygenDemand",
    "StoichiometricReactionMetadata",
    "StoichiometricTerm",
]
