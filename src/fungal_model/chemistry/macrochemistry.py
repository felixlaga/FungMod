"""Conservation-law macrochemical balances and entropy budgets.

Every living or non-living open chemical system obeys the same bookkeeping:
atoms of each element and net charge are conserved, and at constant
temperature and pressure the entropy it produces is fixed by the Gibbs energy
it dissipates. This module solves that bookkeeping and nothing else.

Given explicit species (elemental composition, charge, optional formation
energies) and a caller-fixed subset of signed stoichiometric coefficients, the
remaining coefficients follow from linear conservation alone. The solved
reaction then yields a reaction Gibbs energy, a reaction enthalpy, and an
entropy budget from sourced formation energies.

This is a constraint layer, not a predictive one. Conservation and the second
law say which overall conversions are possible and what they cost; they do not
say how fast anything happens or which admissible conversion a system selects.
No extremal principle (for example maximum entropy production) is applied, no
formation energy, composition, or yield is supplied or inferred, and formation
energies are used exactly as given for their declared conditions: no activity,
concentration, pH, ionic-strength, or temperature correction is made.

Sign convention: negative coefficients are consumed, positive are produced.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, UnitError, assert_compatible, require_quantity

from .stoichiometry import (
    DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE,
    ElementalComposition,
    StoichiometricReactionMetadata,
    StoichiometricTerm,
)

MACROCHEMICAL_BALANCE_MATURITY = "exploratory_software_tested"
CHARGE_CONSERVATION_ROW = "charge"
SECOND_LAW_ENTROPY_PRODUCTION_SOURCE = (
    "Isothermal isobaric chemical entropy production, T * sigma = -delta_r G * rate; "
    "Kondepudi and Prigogine, Modern Thermodynamics, 2nd ed., Wiley 2015."
)
_MOLAR_ENERGY_UNITS = "joule / mole"
_EXTENT_RATE_UNITS = (
    ("mole / second", "watt / kelvin", "watt"),
    ("mole / second / meter ** 3", "watt / kelvin / meter ** 3", "watt / meter ** 3"),
)


class MacrochemicalBalanceError(ValueError):
    """Raised when a macrochemical balance cannot be formed or solved honestly."""


@dataclass(frozen=True)
class MacrochemicalSpecies:
    """One chemical participant with explicit composition, charge, and energies."""

    name: str
    composition: ElementalComposition
    charge: float
    charge_source: str | None
    formation_gibbs: Parameter | None = None
    formation_enthalpy: Parameter | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not has_text(self.name):
            raise ValueError("MacrochemicalSpecies.name must be provided.")
        if self.name == CHARGE_CONSERVATION_ROW:
            raise ValueError(f"{CHARGE_CONSERVATION_ROW!r} is reserved for the charge balance.")
        if not math.isfinite(self.charge):
            raise ValueError(f"Charge of {self.name!r} must be finite.")

    def validate(self) -> None:
        self.composition.validate()
        if not has_text(self.charge_source):
            raise ProvenanceError(f"Charge of {self.name!r} is missing a source.")
        for parameter in (self.formation_gibbs, self.formation_enthalpy):
            if parameter is not None:
                _molar_energy(parameter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "composition": self.composition.to_dict(),
            "charge": self.charge,
            "charge_source": self.charge_source,
            "formation_gibbs": None if self.formation_gibbs is None else self.formation_gibbs.to_dict(),
            "formation_enthalpy": (
                None if self.formation_enthalpy is None else self.formation_enthalpy.to_dict()
            ),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class MacrochemicalEntropyBudget:
    """Entropy and heat rates of one solved reaction at an explicit extent rate.

    The identity ``entropy_production_rate = heat_entropy_export_rate +
    matter_entropy_change_rate`` holds exactly when the heat terms are present.
    """

    entropy_production_rate: Quantity
    heat_release_rate: Quantity | None
    heat_entropy_export_rate: Quantity | None
    matter_entropy_change_rate: Quantity | None

    @property
    def is_second_law_consistent(self) -> bool:
        """Whether the stated extent rate produces non-negative entropy."""

        return float(self.entropy_production_rate.magnitude) >= 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entropy_production_rate": _quantity_dict(self.entropy_production_rate),
            "heat_release_rate": _quantity_dict(self.heat_release_rate),
            "heat_entropy_export_rate": _quantity_dict(self.heat_entropy_export_rate),
            "matter_entropy_change_rate": _quantity_dict(self.matter_entropy_change_rate),
            "is_second_law_consistent": self.is_second_law_consistent,
            "entropy_equation": "entropy_production_rate = -reaction_gibbs * extent_rate / temperature",
            "source": SECOND_LAW_ENTROPY_PRODUCTION_SOURCE,
        }


@dataclass(frozen=True)
class MacrochemicalSolution:
    """A fully determined conserved reaction with its conservation residuals."""

    balance: "MacrochemicalBalance"
    coefficients: dict[str, float]
    fixed_species: tuple[str, ...]
    residuals: dict[str, float]

    def reaction_gibbs(self) -> Quantity:
        """Return the reaction Gibbs energy per mole of reaction extent."""

        return self._reaction_energy("formation_gibbs")

    def reaction_enthalpy(self) -> Quantity:
        """Return the reaction enthalpy per mole of reaction extent."""

        return self._reaction_energy("formation_enthalpy")

    def _reaction_energy(self, attribute: str) -> Quantity:
        if not has_text(self.balance.thermodynamic_conditions):
            raise MacrochemicalBalanceError(
                f"Balance {self.balance.name!r} must declare thermodynamic_conditions before "
                "formation energies are combined."
            )
        total: Quantity | None = None
        for species in self.balance.species:
            parameter = cast("Parameter | None", getattr(species, attribute))
            if parameter is None:
                raise MacrochemicalBalanceError(
                    f"Species {species.name!r} has no {attribute}; reaction energies are "
                    "never computed from a partial set of formation energies."
                )
            term = _molar_energy(parameter) * self.coefficients[species.name]
            total = term if total is None else total + term
        return cast(Quantity, total)

    def entropy_budget(
        self,
        *,
        extent_rate: Quantity,
        temperature: Quantity,
        include_heat: bool,
    ) -> MacrochemicalEntropyBudget:
        """Return entropy production, and optionally its heat/matter split.

        ``extent_rate`` is the caller's reaction extent rate in the
        normalisation of the fixed coefficients. Thermodynamics does not supply
        it. ``include_heat=True`` requires every formation enthalpy.
        """

        rate = require_quantity(extent_rate, name="extent_rate")
        for rate_units, entropy_units, heat_units in _EXTENT_RATE_UNITS:
            try:
                rate = assert_compatible(rate, rate_units, name="extent_rate")
            except UnitError:
                continue
            break
        else:
            raise UnitError(
                "extent_rate must be an amount rate (mole / second) or a volumetric amount "
                f"rate (mole / second / meter ** 3); got {extent_rate.units!s}."
            )
        if not math.isfinite(float(rate.magnitude)):
            raise MacrochemicalBalanceError("extent_rate must be finite.")
        kelvin = assert_compatible(temperature, "kelvin", name="temperature")
        if not math.isfinite(float(kelvin.magnitude)) or float(kelvin.magnitude) <= 0.0:
            raise MacrochemicalBalanceError("temperature must be finite and positive.")

        gibbs = self.reaction_gibbs()
        production = assert_compatible(-gibbs * rate / kelvin, entropy_units, name="entropy production rate")
        if not include_heat:
            return MacrochemicalEntropyBudget(production, None, None, None)
        enthalpy = self.reaction_enthalpy()
        return MacrochemicalEntropyBudget(
            entropy_production_rate=production,
            heat_release_rate=assert_compatible(-enthalpy * rate, heat_units, name="heat release rate"),
            heat_entropy_export_rate=assert_compatible(
                -enthalpy * rate / kelvin, entropy_units, name="heat entropy export rate"
            ),
            matter_entropy_change_rate=assert_compatible(
                (enthalpy - gibbs) * rate / kelvin, entropy_units, name="matter entropy change rate"
            ),
        )

    def stoichiometric_metadata(self) -> StoichiometricReactionMetadata:
        """Return the solved reaction in the form the static validators consume."""

        def terms(sign: float) -> tuple[StoichiometricTerm, ...]:
            return tuple(
                StoichiometricTerm(
                    species=species.name,
                    coefficient=sign * self.coefficients[species.name],
                    composition=species.composition,
                    charge=species.charge,
                    charge_source=species.charge_source,
                )
                for species in self.balance.species
                if sign * self.coefficients[species.name] > 0.0
            )

        return StoichiometricReactionMetadata(
            name=self.balance.name,
            reactants=terms(-1.0),
            products=terms(1.0),
            source=self.balance.source,
            notes=self.balance.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "balance": self.balance.to_dict(),
            "coefficients": dict(self.coefficients),
            "fixed_species": list(self.fixed_species),
            "residuals": dict(self.residuals),
            "sign_convention": "negative coefficients are consumed; positive are produced",
        }


@dataclass(frozen=True)
class MacrochemicalBalance:
    """A set of species whose overall conversion is fixed by conservation.

    ``thermodynamic_conditions`` states the conditions the formation energies
    refer to. It is required before any reaction energy is formed, because the
    energies are combined as given and never transformed between conditions.
    """

    name: str
    species: tuple[MacrochemicalSpecies, ...]
    source: str | None
    thermodynamic_conditions: str | None = None
    maturity: str = MACROCHEMICAL_BALANCE_MATURITY
    notes: str = ""

    def __post_init__(self) -> None:
        if not has_text(self.name):
            raise ValueError("MacrochemicalBalance.name must be provided.")
        if self.maturity != MACROCHEMICAL_BALANCE_MATURITY:
            raise ValueError(
                f"Macrochemical balance maturity must be {MACROCHEMICAL_BALANCE_MATURITY!r}."
            )
        names = [species.name for species in self.species]
        if len(names) < 2:
            raise ValueError("A macrochemical balance requires at least two species.")
        if len(set(names)) != len(names):
            raise ValueError("Macrochemical species names must be distinct.")

    def validate(self) -> None:
        if not has_text(self.source):
            raise ProvenanceError(f"Macrochemical balance {self.name!r} is missing a source.")
        for species in self.species:
            species.validate()

    def conservation_matrix(self) -> tuple[tuple[str, ...], np.ndarray]:
        """Return conserved-quantity labels and the species conservation matrix."""

        elements = sorted({element for species in self.species for element in species.composition.elements})
        labels = (*elements, CHARGE_CONSERVATION_ROW)
        matrix = np.array(
            [
                [species.composition.elements.get(element, 0.0) for species in self.species]
                for element in elements
            ]
            + [[species.charge for species in self.species]],
            dtype=float,
        )
        return labels, matrix

    def solve(
        self,
        fixed_coefficients: Mapping[str, float],
        *,
        absolute_tolerance: float | None = None,
    ) -> MacrochemicalSolution:
        """Solve every unfixed coefficient from element and charge conservation.

        Fails closed when conservation leaves coefficients undetermined (more
        must be fixed) or cannot be satisfied (the species set or fixed values
        are inconsistent). ``absolute_tolerance`` applies to conservation
        residuals relative to the largest coefficient magnitude, at least one.
        """

        self.validate()
        names = [species.name for species in self.species]
        unknown_fixed = sorted(set(fixed_coefficients).difference(names))
        if unknown_fixed:
            raise MacrochemicalBalanceError(f"Fixed coefficients name unknown species: {unknown_fixed}.")
        fixed = {name: float(value) for name, value in fixed_coefficients.items()}
        if not all(math.isfinite(value) for value in fixed.values()):
            raise MacrochemicalBalanceError("Fixed coefficients must be finite.")
        if not any(value != 0.0 for value in fixed.values()):
            raise MacrochemicalBalanceError(
                "At least one nonzero coefficient must be fixed to set the reaction scale."
            )
        tolerance = (
            float(cast(Quantity, DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE.quantity).magnitude)
            if absolute_tolerance is None
            else float(absolute_tolerance)
        )
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise MacrochemicalBalanceError("absolute_tolerance must be finite and non-negative.")

        labels, matrix = self.conservation_matrix()
        free = [index for index, name in enumerate(names) if name not in fixed]
        coefficients = np.array([fixed.get(name, 0.0) for name in names], dtype=float)
        if free:
            free_matrix = matrix[:, free]
            undetermined = len(free) - int(np.linalg.matrix_rank(free_matrix))
            if undetermined:
                raise MacrochemicalBalanceError(
                    f"Conservation leaves {undetermined} degree(s) of freedom among "
                    f"{[names[index] for index in free]}; fix that many more coefficients. "
                    "No coefficient is chosen on the caller's behalf."
                )
            coefficients[free] = np.linalg.lstsq(free_matrix, -matrix @ coefficients, rcond=None)[0]
        residual = matrix @ coefficients
        scale = max(1.0, float(np.max(np.abs(coefficients))))
        if float(np.max(np.abs(residual))) > tolerance * scale:
            violated = {
                label: float(value)
                for label, value in zip(labels, residual, strict=True)
                if abs(float(value)) > tolerance * scale
            }
            raise MacrochemicalBalanceError(
                "The fixed coefficients cannot satisfy conservation with these species; "
                f"residuals (produced minus consumed): {violated}."
            )
        return MacrochemicalSolution(
            balance=self,
            coefficients={name: float(value) for name, value in zip(names, coefficients, strict=True)},
            fixed_species=tuple(name for name in names if name in fixed),
            residuals={label: float(value) for label, value in zip(labels, residual, strict=True)},
        )

    def solve_for_reaction_gibbs(
        self,
        *,
        fixed_coefficients: Mapping[str, float],
        free_species: str,
        reaction_gibbs: Parameter,
        absolute_tolerance: float | None = None,
    ) -> MacrochemicalSolution:
        """Solve the one extra coefficient that gives a stated reaction Gibbs energy.

        Conservation makes the reaction Gibbs energy affine in the coefficient
        of ``free_species``. A target of zero is the reversible limit; a sourced
        negative target is a stated dissipation. The target is an input and is
        never estimated here.
        """

        if free_species in fixed_coefficients:
            raise MacrochemicalBalanceError(f"{free_species!r} cannot be both fixed and free.")
        target = float(_molar_energy(reaction_gibbs).magnitude)

        def gibbs_at(value: float) -> float:
            solution = self.solve(
                {**fixed_coefficients, free_species: value},
                absolute_tolerance=absolute_tolerance,
            )
            return float(solution.reaction_gibbs().to(_MOLAR_ENERGY_UNITS).magnitude)

        intercept = gibbs_at(0.0)
        slope = gibbs_at(1.0) - intercept
        if abs(slope) <= np.finfo(float).eps * max(abs(intercept), abs(target), 1.0):
            raise MacrochemicalBalanceError(
                f"The reaction Gibbs energy does not depend on {free_species!r}; "
                "no coefficient reaches the stated target."
            )
        return self.solve(
            {**fixed_coefficients, free_species: (target - intercept) / slope},
            absolute_tolerance=absolute_tolerance,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "species": [species.to_dict() for species in self.species],
            "source": self.source,
            "thermodynamic_conditions": self.thermodynamic_conditions,
            "maturity": self.maturity,
            "notes": self.notes,
            "limitations": (
                "Element and charge conservation plus formation-energy bookkeeping only. "
                "No rate, yield, composition, or formation energy is predicted or inferred; "
                "no activity, concentration, pH, ionic-strength, or temperature correction "
                "is applied; no extremal entropy principle is used."
            ),
        }


def _molar_energy(parameter: Parameter) -> Quantity:
    """Return a sourced finite molar energy, or raise."""

    parameter.validate_provenance()
    parameter.validate_value()
    quantity = assert_compatible(
        cast(Quantity, parameter.quantity), _MOLAR_ENERGY_UNITS, name=parameter.symbol
    )
    if not math.isfinite(float(quantity.magnitude)):
        raise MacrochemicalBalanceError(f"Molar energy {parameter.symbol!r} must be finite.")
    return quantity


def _quantity_dict(quantity: Quantity | None) -> dict[str, Any] | None:
    if quantity is None:
        return None
    return {"value": float(quantity.magnitude), "units": str(quantity.units)}


__all__ = [
    "CHARGE_CONSERVATION_ROW",
    "MACROCHEMICAL_BALANCE_MATURITY",
    "SECOND_LAW_ENTROPY_PRODUCTION_SOURCE",
    "MacrochemicalBalance",
    "MacrochemicalBalanceError",
    "MacrochemicalEntropyBudget",
    "MacrochemicalSolution",
    "MacrochemicalSpecies",
]
