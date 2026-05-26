"""Generic surface adsorption and catalysis processes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.langmuir import langmuir_surface_coverage
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)


def surface_catalysis_assumption() -> Assumption:
    """Return the generic surface-catalysis assumption."""

    return Assumption(
        name="generic equilibrium surface catalysis",
        description=(
            "A surface-active catalyst binds according to an explicit coverage "
            "model, and bond-cleavage rate scales with occupied accessible surface area."
        ),
        justification=(
            "Surface-limited solid-substrate models need a generic mechanism "
            "that is independent of any named substrate such as PET."
        ),
        known_limitations=(
            "Does not model dynamic adsorption/desorption state variables, "
            "surface renewal, product inhibition, pore accessibility, or changing morphology."
        ),
        source="Generic surface adsorption and catalysis modelling assumption.",
    )


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def _is_zero_or_negative(quantity: Quantity) -> bool:
    return bool(np.all(np.asarray(quantity.magnitude, dtype=float) <= 0))


def surface_catalysis_rate(
    *,
    free_enzyme: Quantity,
    adsorption_equilibrium_constant: Quantity,
    accessible_surface_area: Quantity,
    surface_catalysis_rate_constant: Quantity,
    substrate_amount: Quantity | None = None,
    rate_units: str | None = None,
) -> Quantity:
    """Compute generic equilibrium-coverage surface-catalysis rate."""

    enzyme = require_quantity(free_enzyme, name="free_enzyme")
    area = require_quantity(accessible_surface_area, name="accessible_surface_area")
    rate_constant = require_quantity(
        surface_catalysis_rate_constant,
        name="surface_catalysis_rate_constant",
    )
    _ensure_non_negative(enzyme, "free_enzyme")
    _ensure_non_negative(area, "accessible_surface_area")
    _ensure_non_negative(rate_constant, "surface_catalysis_rate_constant")

    coverage = langmuir_surface_coverage(
        free_enzyme=enzyme,
        adsorption_equilibrium_constant=adsorption_equilibrium_constant,
    )
    rate = rate_constant * coverage * area
    if substrate_amount is not None:
        substrate = require_quantity(substrate_amount, name="substrate_amount")
        if _is_zero_or_negative(substrate):
            rate = rate * Q_(0.0, "dimensionless")
    if rate_units is not None:
        return assert_compatible(rate, rate_units, name="surface catalysis rate")
    return rate


@dataclass(frozen=True)
class AccessibleSitePool:
    """Description of the accessible solid-substrate pool used by a surface process."""

    name: str
    bond_type: str
    units: str = "meter ** 2"
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "bond_type": self.bond_type,
            "units": self.units,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AccessibleSurfaceAreaModel:
    """Generic accessible-surface model backed by a quantity or parameter."""

    name: str
    area: Quantity | None = None
    parameter_symbol: str | None = None
    assumptions: tuple[Assumption, ...] = ()
    notes: str = ""

    @classmethod
    def from_quantity(
        cls,
        *,
        name: str,
        area: Quantity,
        assumptions: tuple[Assumption, ...] = (),
        notes: str = "",
    ) -> "AccessibleSurfaceAreaModel":
        return cls(name=name, area=assert_compatible(area, "meter ** 2", name=name), assumptions=assumptions, notes=notes)

    @classmethod
    def from_parameter(
        cls,
        *,
        name: str,
        parameter_symbol: str,
        assumptions: tuple[Assumption, ...] = (),
        notes: str = "",
    ) -> "AccessibleSurfaceAreaModel":
        return cls(name=name, parameter_symbol=parameter_symbol, assumptions=assumptions, notes=notes)

    def required_parameters(self) -> tuple[ParameterRequirement, ...]:
        if self.parameter_symbol is None:
            return ()
        return (
            ParameterRequirement(
                symbol=self.parameter_symbol,
                units="meter ** 2",
                name=f"{self.name} accessible surface area",
            ),
        )

    def accessible_area(self, parameters: ParameterSet) -> Quantity:
        if self.area is not None:
            return assert_compatible(self.area, "meter ** 2", name=self.name)
        if self.parameter_symbol is None:
            raise ValueError("AccessibleSurfaceAreaModel requires area or parameter_symbol.")
        return parameters.require_quantity(self.parameter_symbol, "meter ** 2")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "area": None if self.area is None else {"value": self.area.magnitude, "units": str(self.area.units)},
            "parameter_symbol": self.parameter_symbol,
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LangmuirAdsorptionModel:
    """Equilibrium Langmuir coverage model for a free catalyst/enzyme state."""

    adsorption_symbol: str
    enzyme_units: str
    source: str
    notes: str = ""

    def required_parameters(self) -> tuple[ParameterRequirement, ...]:
        return (
            ParameterRequirement(
                symbol=self.adsorption_symbol,
                units=f"1 / ({self.enzyme_units})",
                name="Langmuir adsorption equilibrium constant",
            ),
        )

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            Assumption(
                name="equilibrium Langmuir adsorption",
                description="Free catalyst/enzyme coverage is theta = K_ads * E / (1 + K_ads * E).",
                justification="A small equilibrium coverage model is useful before dynamic binding states are added.",
                known_limitations="No explicit bound enzyme state, desorption dynamics, or site saturation dynamics.",
                source=self.source,
            ),
        )

    def coverage(self, *, free_enzyme: Quantity, parameters: ParameterSet) -> Quantity:
        enzyme = assert_compatible(free_enzyme, self.enzyme_units, name="free_enzyme")
        return langmuir_surface_coverage(
            free_enzyme=enzyme,
            adsorption_equilibrium_constant=parameters.require_quantity(
                self.adsorption_symbol,
                f"1 / ({self.enzyme_units})",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "adsorption_symbol": self.adsorption_symbol,
            "enzyme_units": self.enzyme_units,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class EquilibriumSurfaceCoverageModel(LangmuirAdsorptionModel):
    """Alias class for roadmap wording around equilibrium surface coverage."""


@dataclass(frozen=True)
class SurfaceCatalysisModel:
    """Surface-proportional catalytic model."""

    surface_rate_symbol: str
    rate_units: str
    source: str
    notes: str = ""

    def required_parameters(self) -> tuple[ParameterRequirement, ...]:
        return (
            ParameterRequirement(
                symbol=self.surface_rate_symbol,
                units=f"{self.rate_units} / meter ** 2",
                name="surface catalysis rate constant",
            ),
        )

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            Assumption(
                name="surface-proportional catalysis",
                description="Catalytic rate is proportional to occupied accessible surface area.",
                justification="A minimal surface-rate model is needed before detailed erosion and surface renewal.",
                known_limitations="Does not represent product inhibition, surface ageing, or changing accessible area.",
                source=self.source,
            ),
        )

    def rate_constant(self, parameters: ParameterSet) -> Quantity:
        return parameters.require_quantity(
            self.surface_rate_symbol,
            f"{self.rate_units} / meter ** 2",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "surface_rate_symbol": self.surface_rate_symbol,
            "rate_units": self.rate_units,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ProductReleaseMap:
    """Stoichiometric state mapping for a surface bond-cleavage process."""

    reactants: Mapping[str, float]
    products: Mapping[str, float]
    notes: str = ""

    @classmethod
    def one_to_one(cls, *, substrate_state: str, product_state: str, notes: str = "") -> "ProductReleaseMap":
        return cls(reactants={substrate_state: 1.0}, products={product_state: 1.0}, notes=notes)

    @property
    def species(self) -> set[str]:
        return set(self.reactants) | set(self.products)

    def signed_coefficient(self, species: str) -> float:
        return float(self.products.get(species, 0.0) - self.reactants.get(species, 0.0))

    def validate_weight_conservation(self, weights: Mapping[str, float]) -> bool:
        reactant_total = sum(float(coef) * float(weights[name]) for name, coef in self.reactants.items())
        product_total = sum(float(coef) * float(weights[name]) for name, coef in self.products.items())
        return np.isclose(reactant_total, product_total)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reactants": dict(self.reactants),
            "products": dict(self.products),
            "notes": self.notes,
        }


@dataclass(frozen=True, init=False)
class SurfaceCatalysisProcess(Process):
    """Generic equilibrium-coverage surface catalysis / bond-cleavage process."""

    substrate_state: str
    enzyme_state: str
    substrate_units: str
    enzyme_units: str
    rate_units: str
    accessible_site_pool: AccessibleSitePool
    accessible_surface_model: Any
    adsorption_model: LangmuirAdsorptionModel
    catalytic_model: SurfaceCatalysisModel
    product_release_map: ProductReleaseMap

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        enzyme_state: str,
        substrate_units: str,
        enzyme_units: str,
        accessible_site_pool: AccessibleSitePool,
        accessible_surface_model: Any,
        adsorption_model: LangmuirAdsorptionModel,
        catalytic_model: SurfaceCatalysisModel,
        product_release_map: ProductReleaseMap,
        state_units: Mapping[str, str] | None = None,
        source: str = "Generic surface catalysis process.",
        notes: str = "",
    ) -> None:
        units_by_state = dict(state_units or {})
        units_by_state.setdefault(substrate_state, substrate_units)
        units_by_state.setdefault(enzyme_state, enzyme_units)
        for species in product_release_map.species:
            units_by_state.setdefault(species, substrate_units)

        required_parameters = [
            *getattr(accessible_surface_model, "required_parameters", lambda: ())(),
            *adsorption_model.required_parameters(),
            *catalytic_model.required_parameters(),
        ]
        assumptions = _unique_assumptions(
            [
                surface_catalysis_assumption(),
                *tuple(getattr(accessible_surface_model, "assumptions", ())),
                *adsorption_model.assumptions,
                *catalytic_model.assumptions,
            ]
        )
        Process.__init__(
            self,
            name=name,
            process_type="surface_catalysis",
            required_state_variables=(
                StateVariableSpec(substrate_state, substrate_units, role="solid_substrate"),
                StateVariableSpec(enzyme_state, enzyme_units, role="free_catalyst"),
            ),
            changed_state_variables=tuple(
                StateVariableSpec(species, units_by_state[species])
                for species in product_release_map.species
            ),
            required_parameters=tuple(required_parameters),
            assumptions=assumptions,
            validity=ValidityDomain(
                description="Generic equilibrium-adsorption surface catalysis process.",
                labels=("surface", "heterogeneous", "bond_cleavage"),
                limitations=("Accessible surface area is supplied by an explicit model and is not evolved dynamically.",),
            ),
            failure_modes=(
                "missing accessible surface area",
                "missing adsorption parameter",
                "missing surface catalytic parameter",
                "incompatible catalyst/substrate state units",
            ),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "substrate_state", substrate_state)
        object.__setattr__(self, "enzyme_state", enzyme_state)
        object.__setattr__(self, "substrate_units", substrate_units)
        object.__setattr__(self, "enzyme_units", enzyme_units)
        object.__setattr__(self, "rate_units", catalytic_model.rate_units)
        object.__setattr__(self, "accessible_site_pool", accessible_site_pool)
        object.__setattr__(self, "accessible_surface_model", accessible_surface_model)
        object.__setattr__(self, "adsorption_model", adsorption_model)
        object.__setattr__(self, "catalytic_model", catalytic_model)
        object.__setattr__(self, "product_release_map", product_release_map)

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: object = None,
        geometry: object = None,
    ) -> Quantity:
        del time, environment, geometry
        enzyme = assert_compatible(state[self.enzyme_state], self.enzyme_units, name=self.enzyme_state)
        substrate = assert_compatible(state[self.substrate_state], self.substrate_units, name=self.substrate_state)
        adsorption_constant = parameters.require_quantity(
            self.adsorption_model.adsorption_symbol,
            f"1 / ({self.enzyme_units})",
        )
        return surface_catalysis_rate(
            free_enzyme=enzyme,
            adsorption_equilibrium_constant=adsorption_constant,
            accessible_surface_area=self.accessible_surface_model.accessible_area(parameters),
            surface_catalysis_rate_constant=self.catalytic_model.rate_constant(parameters),
            substrate_amount=substrate,
            rate_units=self.rate_units,
        )

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        return {
            species: self.product_release_map.signed_coefficient(species) * value
            for species in self.product_release_map.species
        }

    def as_reaction(self) -> Reaction:
        return Reaction(
            name=self.name,
            reactants=self.product_release_map.reactants,
            products=self.product_release_map.products,
            rate_law=self.rate,
            rate_units=self.rate_units,
            assumptions=list(self.assumptions),
            source=self.source or "Generic surface catalysis process.",
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "accessible_site_pool": self.accessible_site_pool.to_dict(),
                "accessible_surface_model": self.accessible_surface_model.to_dict(),
                "adsorption_model": self.adsorption_model.to_dict(),
                "catalytic_model": self.catalytic_model.to_dict(),
                "product_release_map": self.product_release_map.to_dict(),
            }
        )
        return data


BondCleavageProcess = SurfaceCatalysisProcess


def _unique_assumptions(assumptions: list[Assumption]) -> tuple[Assumption, ...]:
    result: list[Assumption] = []
    seen: set[str] = set()
    for assumption in assumptions:
        if assumption.name not in seen:
            result.append(assumption)
            seen.add(assumption.name)
    return tuple(result)


__all__ = [
    "AccessibleSitePool",
    "AccessibleSurfaceAreaModel",
    "BondCleavageProcess",
    "EquilibriumSurfaceCoverageModel",
    "LangmuirAdsorptionModel",
    "ProductReleaseMap",
    "SurfaceCatalysisModel",
    "SurfaceCatalysisProcess",
    "surface_catalysis_assumption",
    "surface_catalysis_rate",
]
