"""Stoichiometric and elemental bookkeeping interfaces."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError, has_text
from fungal_model.core.units import Quantity, assert_compatible, require_quantity

FORMULA_PATTERN = re.compile(r"([A-Z][a-z]?)(\d*)")

ELEMENT_SYMBOLS_SOURCE = (
    "IUPAC Periodic Table of the Elements (1 May 2022), symbols of elements 1 to 118."
)
ELEMENT_SYMBOLS: frozenset[str] = frozenset(
    (
        "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
        "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La "
        "Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po "
        "At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg "
        "Cn Nh Fl Mc Lv Ts Og"
    ).split()
)

DEGREE_OF_REDUCTION_SOURCE = (
    "Degree of reduction per formula unit, gamma = 4 C + H - 2 O - 3 N + 5 P + 6 S - z, "
    "with H2O, CO2, NH3, H3PO4, H2SO4 and the proton as the zero references; "
    "Roels, Energetics and Kinetics in Biotechnology, Elsevier 1983; Heijnen and "
    "Kleerebezem, Bioenergetics of Microbial Growth, in Encyclopedia of Industrial "
    "Biotechnology, Wiley 2010."
)
# Electrons per atom relative to the reference compounds above. Only these
# elements have a reference state in the cited degree-of-reduction convention;
# any other element in a composition makes the degree of reduction undefined.
_DEGREE_OF_REDUCTION_ELECTRONS_PER_ATOM: Mapping[str, float] = {
    "C": 4.0,
    "H": 1.0,
    "O": -2.0,
    "P": 5.0,
    "S": 6.0,
}
# Nitrogen electrons per atom depend on the nitrogen reference compound.
_NITROGEN_REFERENCE_ELECTRONS_PER_ATOM: Mapping[str, float] = {"ammonia": -3.0}

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
        unknown = sorted(symbol for symbol in elements if symbol not in ELEMENT_SYMBOLS)
        if unknown:
            raise ValueError(
                f"Formula {formula!r} names symbols that are not chemical elements: {unknown}. "
                f"Recognised symbols follow {ELEMENT_SYMBOLS_SOURCE}"
            )
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
            float(cast(Quantity, DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE.quantity).magnitude)
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


def degree_of_reduction(
    composition: ElementalComposition,
    charge: float,
    *,
    nitrogen_reference: str = "ammonia",
    per_carbon: bool = False,
) -> float:
    """Return the degree of reduction of one formula unit, or per carbon atom.

    ``gamma = 4C + H - 2O - 3N + 5P + 6S - z`` for the ammonia nitrogen reference
    (``DEGREE_OF_REDUCTION_SOURCE``). ``per_carbon=True`` divides by the carbon
    count and refuses carbon-free species. Elements outside C, H, O, N, P, S
    have no reference state in this convention and are refused, as is any
    nitrogen reference other than the ones tabulated here.
    """

    if nitrogen_reference not in _NITROGEN_REFERENCE_ELECTRONS_PER_ATOM:
        raise ValueError(
            f"Unsupported nitrogen reference {nitrogen_reference!r}; supported: "
            f"{sorted(_NITROGEN_REFERENCE_ELECTRONS_PER_ATOM)}."
        )
    if not math.isfinite(float(charge)):
        raise ValueError("charge must be finite.")
    electrons_per_atom = {
        **_DEGREE_OF_REDUCTION_ELECTRONS_PER_ATOM,
        "N": _NITROGEN_REFERENCE_ELECTRONS_PER_ATOM[nitrogen_reference],
    }
    unsupported = sorted(
        element for element, count in composition.elements.items() if count != 0.0 and element not in electrons_per_atom
    )
    if unsupported:
        raise ValueError(
            f"Degree of reduction is undefined for {composition.formula!r}: elements {unsupported} "
            "have no reference state in the C, H, O, N, P, S convention."
        )
    gamma = sum(
        electrons_per_atom[element] * float(count) for element, count in composition.elements.items()
    ) - float(charge)
    if not per_carbon:
        return float(gamma)
    carbon = float(composition.elements.get("C", 0.0))
    if carbon <= 0.0:
        raise ValueError(
            f"Degree of reduction per carbon is undefined for carbon-free {composition.formula!r}."
        )
    return float(gamma / carbon)


def electron_equivalents_from_composition(
    composition: ElementalComposition,
    charge: float,
    *,
    nitrogen_reference: str = "ammonia",
) -> float:
    """Return electron equivalents per formula unit for the electron balance.

    This is the degree of reduction per formula unit, so a conserved reaction
    satisfies ``sum_j nu_j gamma_j = 0`` (for example O2 carries -4).
    """

    return degree_of_reduction(composition, charge, nitrogen_reference=nitrogen_reference)


def assign_electron_equivalents(
    reaction: StoichiometricReactionMetadata,
    *,
    nitrogen_reference: str = "ammonia",
) -> StoichiometricReactionMetadata:
    """Return a copy whose terms carry composition-derived electron equivalents.

    Every term must declare a composition and a charge; nothing is inferred for
    a term that lacks them.
    """

    def with_electrons(term: StoichiometricTerm) -> StoichiometricTerm:
        if term.composition is None or term.charge is None:
            raise ValueError(
                f"Term {term.species!r} needs both composition and charge before electron "
                "equivalents can be derived from its degree of reduction."
            )
        return replace(
            term,
            electron_equivalents=electron_equivalents_from_composition(
                term.composition, term.charge, nitrogen_reference=nitrogen_reference
            ),
            electron_source=DEGREE_OF_REDUCTION_SOURCE,
        )

    return replace(
        reaction,
        reactants=tuple(with_electrons(term) for term in reaction.reactants),
        products=tuple(with_electrons(term) for term in reaction.products),
    )


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


_OXYGEN_DEMAND_BASES: Mapping[str, tuple[str, str]] = {
    "mass": ("kilogram / kilogram", "kilogram"),
    "amount": ("mole / mole", "mole"),
    "carbon_amount": ("mole / mole", "mole"),
}


@dataclass(frozen=True)
class OxygenDemand:
    """Oxygen demand per consumed substrate for an aerobic process.

    ``basis`` declares what the ratio means: ``"mass"`` is kilogram O2 per
    kilogram substrate; ``"amount"`` is mole O2 per mole of substrate formula
    units; ``"carbon_amount"`` is mole O2 per mole of substrate carbon atoms
    (C-mol). All ratios are dimensionless to the unit registry, so the basis
    is an explicit declaration, and ``required_oxygen`` accepts substrate in
    the matching unit only; no molar mass or carbon count is inferred, so a
    caller must pass C-mol (not molecule moles) to a ``"carbon_amount"`` demand.
    """

    process_name: str
    substrate_species: str
    oxygen_per_substrate: Parameter
    basis: str = "mass"

    def __post_init__(self) -> None:
        if self.basis not in _OXYGEN_DEMAND_BASES:
            raise ValueError(
                f"OxygenDemand basis must be one of {sorted(_OXYGEN_DEMAND_BASES)}; got {self.basis!r}."
            )
        demand = self.oxygen_per_substrate.quantity
        if demand is None:
            return
        ratio_units, _ = _OXYGEN_DEMAND_BASES[self.basis]
        value = assert_compatible(demand, ratio_units, name=self.oxygen_per_substrate.symbol)
        if np.any(np.asarray(value.magnitude, dtype=float) < 0):
            raise ValueError("oxygen_per_substrate must be non-negative.")

    @classmethod
    def from_degree_of_reduction(
        cls,
        *,
        process_name: str,
        substrate_species: str,
        substrate_composition: ElementalComposition,
        substrate_charge: float,
        biomass_composition: ElementalComposition,
        biomass_charge: float,
        biomass_yield_per_carbon: Quantity,
        yield_source: str | None,
        nitrogen_reference: str = "ammonia",
    ) -> "OxygenDemand":
        """Oxygen per C-mol substrate from the electron balance of growth.

        ``O2 per C-mol S = (gamma_S - Y_SX gamma_X) / 4`` with both degrees of
        reduction per C-mol and ``Y_SX`` in C-mol biomass per C-mol substrate
        (``DEGREE_OF_REDUCTION_SOURCE``). The identity holds only when every
        other participant (CO2, H2O, the nitrogen source, protons) has zero
        degree of reduction under the chosen nitrogen reference. A yield that
        would need negative oxygen exceeds the electron balance and is refused.
        """

        if not has_text(yield_source):
            raise ProvenanceError("biomass_yield_per_carbon requires a source.")
        yield_value = float(
            assert_compatible(
                require_quantity(biomass_yield_per_carbon, name="biomass_yield_per_carbon"),
                "dimensionless",
                name="biomass_yield_per_carbon",
            ).magnitude
        )
        if not math.isfinite(yield_value) or yield_value < 0.0:
            raise ValueError("biomass_yield_per_carbon must be finite and non-negative.")
        gamma_substrate = degree_of_reduction(
            substrate_composition, substrate_charge, nitrogen_reference=nitrogen_reference, per_carbon=True
        )
        gamma_biomass = degree_of_reduction(
            biomass_composition, biomass_charge, nitrogen_reference=nitrogen_reference, per_carbon=True
        )
        oxygen_per_carbon = (gamma_substrate - yield_value * gamma_biomass) / 4.0
        if oxygen_per_carbon < 0.0:
            raise ValueError(
                f"Yield {yield_value!r} C-mol/C-mol exceeds the electron balance: substrate "
                f"gamma {gamma_substrate!r} cannot supply biomass gamma {gamma_biomass!r}; "
                f"the ceiling is {gamma_substrate / gamma_biomass!r}."
            )
        return cls(
            process_name=process_name,
            substrate_species=substrate_species,
            oxygen_per_substrate=Parameter(
                name=f"oxygen demand per carbon-mole of {substrate_species}",
                symbol=f"O2_per_Cmol_{substrate_species}",
                value=oxygen_per_carbon,
                units="mole / mole",
                uncertainty=None,
                source=DEGREE_OF_REDUCTION_SOURCE,
                confidence_level="medium",
                notes=(
                    f"(gamma_S - Y_SX gamma_X) / 4 with gamma_S = {gamma_substrate!r}, "
                    f"gamma_X = {gamma_biomass!r} per C-mol, Y_SX = {yield_value!r} C-mol/C-mol "
                    f"(yield source: {yield_source}); nitrogen reference {nitrogen_reference!r}. "
                    "Mole O2 per mole carbon atoms of substrate."
                ),
                measurement_method="electron balance",
            ),
            basis="carbon_amount",
        )

    def required_oxygen(self, substrate_consumed: Quantity) -> Quantity:
        ratio_units, amount_units = _OXYGEN_DEMAND_BASES[self.basis]
        consumed = assert_compatible(
            require_quantity(substrate_consumed, name="substrate_consumed"),
            amount_units,
            name="substrate_consumed",
        )
        demand = self.oxygen_per_substrate.quantity
        if demand is None:
            raise UnknownParameterError(f"Oxygen demand for {self.process_name} is unknown.")
        return assert_compatible(
            consumed * assert_compatible(demand, ratio_units, name=self.oxygen_per_substrate.symbol),
            amount_units,
            name=f"{self.process_name} oxygen demand",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_name": self.process_name,
            "substrate_species": self.substrate_species,
            "oxygen_per_substrate": self.oxygen_per_substrate.to_dict(),
            "basis": self.basis,
        }


__all__ = [
    "CarbonContent",
    "DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE",
    "DEGREE_OF_REDUCTION_SOURCE",
    "ELEMENT_SYMBOLS",
    "ELEMENT_SYMBOLS_SOURCE",
    "ElementalComposition",
    "OxygenDemand",
    "StoichiometricReactionMetadata",
    "StoichiometricTerm",
    "assign_electron_equivalents",
    "charge_balance_residual",
    "degree_of_reduction",
    "electron_balance_residual",
    "electron_equivalents_from_composition",
    "element_balance_residual",
]
