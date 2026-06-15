"""Stoichiometric and elemental bookkeeping interfaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
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

    @classmethod
    def from_elements(
        cls,
        elements: dict[str, float],
        *,
        source: str | None,
        formula: str = "structured_element_counts",
        notes: str = "",
    ) -> "ElementalComposition":
        """Create an explicit composition from structured element counts."""

        if not elements:
            raise ValueError("At least one element count must be provided.")
        normalized: dict[str, float] = {}
        for element, count in elements.items():
            if not has_text(element):
                raise ValueError("Element symbols must be provided.")
            numeric_count = float(count)
            if numeric_count < 0.0 or not np.isfinite(numeric_count):
                raise ValueError("Element counts must be finite and non-negative.")
            normalized[str(element)] = numeric_count
        return cls(formula=formula, elements=normalized, source=source, notes=notes)

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
    charge: float | None = None
    charge_source: str | None = None
    electron_equivalents: float | None = None
    electron_source: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.coefficient < 0 or not np.isfinite(self.coefficient):
            raise ValueError("Stoichiometric coefficients must be finite and non-negative.")
        if self.charge is not None and not np.isfinite(self.charge):
            raise ValueError("Charge metadata must be finite when provided.")
        if self.electron_equivalents is not None and not np.isfinite(self.electron_equivalents):
            raise ValueError("Electron-equivalent metadata must be finite when provided.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "species": self.species,
            "coefficient": self.coefficient,
            "composition": None if self.composition is None else self.composition.to_dict(),
            "charge": self.charge,
            "charge_source": self.charge_source,
            "electron_equivalents": self.electron_equivalents,
            "electron_source": self.electron_source,
            "notes": self.notes,
        }


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

        return element_balance_residual(self)

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
            "reactants": [term.to_dict() for term in self.reactants],
            "products": [term.to_dict() for term in self.products],
            "source": self.source,
            "notes": self.notes,
        }


def element_balance_residual(reaction: StoichiometricReactionMetadata) -> dict[str, float]:
    """Return products-minus-reactants elemental residuals for explicit metadata."""

    balance: dict[str, float] = {}
    for side, sign in ((reaction.reactants, -1.0), (reaction.products, 1.0)):
        for term in side:
            if term.composition is None:
                raise ValueError(f"Missing elemental composition for {term.species}.")
            for element, count in term.composition.elements.items():
                balance[element] = balance.get(element, 0.0) + sign * term.coefficient * count
    return balance


def charge_balance_residual(reaction: StoichiometricReactionMetadata) -> float:
    """Return products-minus-reactants charge residual for explicit metadata."""

    residual = 0.0
    for side, sign in ((reaction.reactants, -1.0), (reaction.products, 1.0)):
        for term in side:
            if term.charge is None:
                raise ValueError(f"Missing charge metadata for {term.species}.")
            residual += sign * term.coefficient * term.charge
    return residual


def electron_balance_residual(reaction: StoichiometricReactionMetadata) -> float:
    """Return products-minus-reactants electron-equivalent residual."""

    residual = 0.0
    for side, sign in ((reaction.reactants, -1.0), (reaction.products, 1.0)):
        for term in side:
            if term.electron_equivalents is None:
                raise ValueError(f"Missing electron-equivalent metadata for {term.species}.")
            residual += sign * term.coefficient * term.electron_equivalents
    return residual


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
    "charge_balance_residual",
    "electron_balance_residual",
    "element_balance_residual",
]
