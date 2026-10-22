"""Generic surface adsorption and catalysis processes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel, magnitude_in
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.langmuir import langmuir_surface_coverage
from fungal_model.kinetics.site_binding import (
    SITE_BINDING_MATURITY,
    SITE_BINDING_PRIMARY_SOURCES,
    bound_enzyme_derivative_magnitudes,
    bound_enzyme_magnitude,
    site_binding_bound_enzyme,
)
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
            "that is independent of any named substrate."
        ),
        known_limitations=(
            "Does not model dynamic adsorption/desorption state variables, "
            "surface renewal, product inhibition, pore accessibility, or changing morphology."
        ),
        source="Generic surface adsorption and catalysis modelling assumption.",
    )


CONSTANT_UNTIL_DEPLETION = "constant_until_depletion"
MASS_SCALED = "mass_scaled"
AREA_MODELS = (CONSTANT_UNTIL_DEPLETION, MASS_SCALED)
MASS_SCALED_AREA_MATURITY = "literature_backed_software_tested"
MASS_SCALED_AREA_SOURCE = (
    "Kadam KL, Rydholm EC, McMillan JD (2004). Development and validation of a kinetic model "
    "for enzymatic saccharification of lignocellulosic biomass. Biotechnol Prog 20:698-705 "
    "(substrate-reactivity factor, n = 1); n = 2/3 is the geometric exponent of an isotropically "
    "shrinking particle (area proportional to mass**(2/3))."
)
SITE_BINDING_SURFACE_CATALYSIS_PROCESS_TYPE = "site_binding_surface_catalysis"


def mass_scaled_area_assumption() -> Assumption:
    """Return the assumption record of the mass-scaled accessible-area law."""

    return Assumption(
        name="mass-scaled accessible surface area",
        description=(
            "Accessible surface area follows the remaining substrate amount, "
            "A(m) = A_0 * (m / m_0)**n, with m_0 the loading at which A_0 applies and n a "
            "geometry exponent supplied with provenance (n = 1: a film or a reactivity "
            "factor linear in remaining substrate; n = 2/3: isotropically shrinking particles)."
        ),
        justification=(
            "The rate must fall continuously to zero as the substrate is consumed; a constant "
            "area with a step at depletion makes the right-hand side discontinuous."
        ),
        known_limitations=(
            "Does not represent crystallinity or amorphous-fraction evolution, pore "
            "accessibility, surface roughening, or particle-size distributions; n is a single "
            "exponent for the whole run."
        ),
        source=MASS_SCALED_AREA_SOURCE,
    )


def site_binding_surface_catalysis_assumption() -> Assumption:
    """Return the assumption record of the enzyme-site binding surface law."""

    return Assumption(
        name="enzyme-site binding balance on a solid substrate",
        description=(
            "Total enzyme E_T is conserved and partitions between free and bound forms over "
            "accessible attack sites S_0 = a_s * m / V with dissociation constant K_d; the bound "
            "enzyme is the physical root of the quadratic balance and the cleavage rate is "
            "k_cat,s * E_b * V / a_s."
        ),
        justification=(
            "Closing the enzyme balance reproduces both the enzyme-limited (conventional "
            "Michaelis-Menten in sites) and the site-limited (inverse Michaelis-Menten) regimes "
            "of interfacial kinetics."
        ),
        known_limitations=(
            "Equilibrium binding only (no adsorption or desorption dynamics), one site class, "
            "no product inhibition, no non-productive binding, no site renewal or crystallinity "
            "evolution; a_s is treated as constant per unit remaining mass."
        ),
        source="; ".join(SITE_BINDING_PRIMARY_SOURCES),
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
    """Generic accessible-surface model backed by a quantity or parameter.

    ``area_model`` selects how the area follows the remaining substrate:

    * ``constant_until_depletion`` (default): the area is the constant ``A_0``
      for any positive substrate amount and the owning process sets the rate
      to zero at or below zero. The right-hand side is discontinuous there.
    * ``mass_scaled``: ``A(m) = A_0 * (m / m_0)**n`` with ``m_0`` the loading
      (``reference_mass_symbol``) and ``n`` a geometry exponent
      (``exponent_symbol``), both parameters with provenance. The area and the
      rate go to zero continuously with the substrate.
    """

    name: str
    area: Quantity | None = None
    parameter_symbol: str | None = None
    assumptions: tuple[Assumption, ...] = ()
    notes: str = ""
    area_model: str = CONSTANT_UNTIL_DEPLETION
    reference_mass_symbol: str | None = None
    exponent_symbol: str | None = None
    reference_mass_units: str = "kilogram"

    def __post_init__(self) -> None:
        if self.area_model not in AREA_MODELS:
            raise ValueError(f"area_model must be one of {AREA_MODELS}; received {self.area_model!r}.")
        if self.area_model == MASS_SCALED:
            if not self.reference_mass_symbol or not self.exponent_symbol:
                raise ValueError("The mass_scaled area model requires reference_mass_symbol and exponent_symbol.")
            Q_(1, self.reference_mass_units)
            if all(assumption.name != mass_scaled_area_assumption().name for assumption in self.assumptions):
                object.__setattr__(self, "assumptions", (*self.assumptions, mass_scaled_area_assumption()))
        elif self.reference_mass_symbol is not None or self.exponent_symbol is not None:
            raise ValueError("reference_mass_symbol and exponent_symbol apply to the mass_scaled area model only.")

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

    @classmethod
    def mass_scaled(
        cls,
        *,
        name: str,
        reference_mass_symbol: str,
        exponent_symbol: str,
        area: Quantity | None = None,
        parameter_symbol: str | None = None,
        reference_mass_units: str = "kilogram",
        assumptions: tuple[Assumption, ...] = (),
        notes: str = "",
    ) -> "AccessibleSurfaceAreaModel":
        """Area ``A_0 * (m / m_0)**n`` with ``A_0`` from ``area`` or ``parameter_symbol``."""

        if (area is None) == (parameter_symbol is None):
            raise ValueError("mass_scaled requires exactly one of area or parameter_symbol for A_0.")
        return cls(
            name=name,
            area=None if area is None else assert_compatible(area, "meter ** 2", name=name),
            parameter_symbol=parameter_symbol,
            assumptions=assumptions,
            notes=notes,
            area_model=MASS_SCALED,
            reference_mass_symbol=reference_mass_symbol,
            exponent_symbol=exponent_symbol,
            reference_mass_units=reference_mass_units,
        )

    @property
    def maturity(self) -> str | None:
        return MASS_SCALED_AREA_MATURITY if self.area_model == MASS_SCALED else None

    def required_parameters(self) -> tuple[ParameterRequirement, ...]:
        requirements: list[ParameterRequirement] = []
        if self.parameter_symbol is not None:
            requirements.append(
                ParameterRequirement(
                    symbol=self.parameter_symbol,
                    units="meter ** 2",
                    name=f"{self.name} accessible surface area",
                )
            )
        if self.area_model == MASS_SCALED:
            assert self.reference_mass_symbol is not None and self.exponent_symbol is not None
            requirements.append(
                ParameterRequirement(
                    symbol=self.reference_mass_symbol,
                    units=self.reference_mass_units,
                    name=f"{self.name} reference substrate loading m_0",
                )
            )
            requirements.append(
                ParameterRequirement(
                    symbol=self.exponent_symbol,
                    units="dimensionless",
                    name=f"{self.name} area geometry exponent n",
                )
            )
        return tuple(requirements)

    def accessible_area(self, parameters: ParameterSet) -> Quantity:
        """The reference area ``A_0`` (the whole law for ``constant_until_depletion``)."""

        if self.area is not None:
            return assert_compatible(self.area, "meter ** 2", name=self.name)
        if self.parameter_symbol is None:
            raise ValueError("AccessibleSurfaceAreaModel requires area or parameter_symbol.")
        return parameters.require_quantity(self.parameter_symbol, "meter ** 2")

    def scaling_parameters(self, parameters: ParameterSet, substrate_units: str) -> tuple[float, float]:
        """``(m_0 in substrate_units, n)`` of the mass-scaled law."""

        if self.area_model != MASS_SCALED:
            raise ValueError("scaling_parameters applies to the mass_scaled area model only.")
        assert self.reference_mass_symbol is not None and self.exponent_symbol is not None
        reference_mass = magnitude_in(
            parameters.require_quantity(self.reference_mass_symbol, substrate_units),
            substrate_units,
            name=self.reference_mass_symbol,
        )
        exponent = magnitude_in(
            parameters.require_quantity(self.exponent_symbol, "dimensionless"),
            "dimensionless",
            name=self.exponent_symbol,
        )
        if reference_mass <= 0.0:
            raise ValueError(f"{self.reference_mass_symbol} (reference substrate loading) must be positive.")
        if exponent < 0.0:
            raise ValueError(f"{self.exponent_symbol} (area geometry exponent) must be non-negative.")
        return reference_mass, exponent

    def accessible_area_at(self, parameters: ParameterSet, substrate_amount: Quantity) -> Quantity:
        """Area at the given substrate amount under the selected ``area_model``."""

        reference_area = self.accessible_area(parameters)
        if self.area_model == CONSTANT_UNTIL_DEPLETION:
            return reference_area
        substrate = require_quantity(substrate_amount, name="substrate_amount")
        substrate_units = str(substrate.units)
        reference_mass, exponent = self.scaling_parameters(parameters, substrate_units)
        amount = float(np.asarray(substrate.magnitude, dtype=float))
        return reference_area * mass_scaled_area_factor(amount, reference_mass, exponent)

    def accessible_area_derivative_at(self, parameters: ParameterSet, substrate_amount: Quantity) -> Quantity:
        """``dA/dm`` in square metres per substrate unit; zero for the constant law."""

        substrate = require_quantity(substrate_amount, name="substrate_amount")
        substrate_units = str(substrate.units)
        reference_area = self.accessible_area(parameters)
        if self.area_model == CONSTANT_UNTIL_DEPLETION:
            return Q_(0.0, "meter ** 2") / Q_(1.0, substrate_units)
        reference_mass, exponent = self.scaling_parameters(parameters, substrate_units)
        amount = float(np.asarray(substrate.magnitude, dtype=float))
        derivative = mass_scaled_area_factor_derivative(amount, reference_mass, exponent)
        return reference_area * derivative / Q_(1.0, substrate_units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "area": None if self.area is None else {"value": self.area.magnitude, "units": str(self.area.units)},
            "parameter_symbol": self.parameter_symbol,
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "notes": self.notes,
            "area_model": self.area_model,
            "reference_mass_symbol": self.reference_mass_symbol,
            "exponent_symbol": self.exponent_symbol,
            "maturity": self.maturity,
            "equation": (
                "A = A_0 for m > 0; rate = 0 at m <= 0"
                if self.area_model == CONSTANT_UNTIL_DEPLETION
                else "A(m) = A_0 * (m / m_0)**n"
            ),
        }


def mass_scaled_area_factor(amount: float, reference_mass: float, exponent: float) -> float:
    """``(m / m_0)**n`` for ``m > 0``; 0 at and below ``m = 0``."""

    if amount <= 0.0:
        return 0.0
    return (amount / reference_mass) ** exponent


def mass_scaled_area_factor_derivative(amount: float, reference_mass: float, exponent: float) -> float:
    """``d/dm (m / m_0)**n``.

    For ``m > 0`` this is ``n * (m / m_0)**(n - 1) / m_0``. At ``m = 0`` the
    derivative is ``1 / m_0`` for ``n = 1``, 0 for ``n > 1``, and unbounded for
    ``n < 1``, where 0 is returned as the only finite choice (the same rule
    :class:`fungal_model.processes.homogeneous.MassActionProcess` applies).
    """

    if amount <= 0.0:
        return 1.0 / reference_mass if exponent == 1.0 else 0.0
    return exponent * (amount / reference_mass) ** (exponent - 1.0) / reference_mass


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
class CoefficientBinding:
    """A stoichiometric coefficient that equals a parameter, or its complement.

    ``complement`` binds the coefficient to ``1 - parameter`` (a fraction that
    closes a mass balance). The numeric coefficient stays on the product map;
    the binding records where it came from so exporters can keep the
    dependence symbolic.
    """

    parameter_symbol: str
    complement: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.parameter_symbol, str) or not self.parameter_symbol.strip():
            raise ValueError("A coefficient binding requires a parameter symbol.")

    def value(self, parameter_value: float) -> float:
        """The coefficient implied by ``parameter_value``."""

        numeric = float(parameter_value)
        return 1.0 - numeric if self.complement else numeric

    def describe(self) -> str:
        return f"1 - {self.parameter_symbol}" if self.complement else self.parameter_symbol

    def to_dict(self) -> dict[str, Any]:
        return {"parameter_symbol": self.parameter_symbol, "complement": self.complement}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CoefficientBinding":
        return cls(parameter_symbol=str(data["parameter_symbol"]), complement=bool(data.get("complement", False)))


@dataclass(frozen=True)
class ProductReleaseMap:
    """Stoichiometric state mapping for a surface bond-cleavage process.

    ``coefficient_bindings`` names the parameter each product coefficient was
    derived from, when it was derived from one. It is descriptive: the numeric
    ``products`` entries drive every simulation.
    """

    reactants: Mapping[str, float]
    products: Mapping[str, float]
    notes: str = ""
    name: str | None = None
    maturity: str | None = None
    source: str | None = None
    coefficient_bindings: Mapping[str, CoefficientBinding] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = sorted(set(self.coefficient_bindings) - set(self.products))
        if unknown:
            raise ValueError(
                "Coefficient bindings must name product states of the map; unknown: " + ", ".join(unknown) + "."
            )
        object.__setattr__(self, "coefficient_bindings", dict(self.coefficient_bindings))

    @classmethod
    def one_to_one(
        cls,
        *,
        substrate_state: str,
        product_state: str,
        notes: str = "",
        name: str | None = None,
        maturity: str | None = None,
        source: str | None = None,
    ) -> "ProductReleaseMap":
        return cls(
            reactants={substrate_state: 1.0},
            products={product_state: 1.0},
            notes=notes,
            name=name,
            maturity=maturity,
            source=source,
        )

    @property
    def species(self) -> set[str]:
        return set(self.reactants) | set(self.products)

    def signed_coefficient(self, species: str) -> float:
        return float(self.products.get(species, 0.0) - self.reactants.get(species, 0.0))

    def validate_weight_conservation(self, weights: Mapping[str, float]) -> bool:
        reactant_total = sum(float(coef) * float(weights[name]) for name, coef in self.reactants.items())
        product_total = sum(float(coef) * float(weights[name]) for name, coef in self.products.items())
        return bool(np.isclose(reactant_total, product_total))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reactants": dict(self.reactants),
            "products": dict(self.products),
            "notes": self.notes,
            "maturity": self.maturity,
            "source": self.source,
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
    area_model: str

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

        area_model = _area_model_name(accessible_surface_model)
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
                labels=("surface", "heterogeneous", "bond_cleavage", f"area_model={area_model}"),
                limitations=_area_model_limitations(area_model),
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
        object.__setattr__(self, "area_model", area_model)

    def _area_at(self, parameters: ParameterSet, substrate: Quantity) -> Quantity:
        """Accessible area at ``substrate`` under the model's area law."""

        area_at = getattr(self.accessible_surface_model, "accessible_area_at", None)
        if area_at is None:
            return self.accessible_surface_model.accessible_area(parameters)
        return area_at(parameters, substrate)

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
            accessible_surface_area=self._area_at(parameters, substrate),
            surface_catalysis_rate_constant=self.catalytic_model.rate_constant(parameters),
            substrate_amount=substrate,
            rate_units=self.rate_units,
        )

    def _compiled_terms(self, context: KernelContext) -> dict[str, Any]:
        """Build-time scalars shared by the rate and gradient kernels."""

        enzyme_index, to_enzyme = context.state_slot(self.enzyme_state, self.enzyme_units)
        substrate_index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        adsorption_units = f"1 / ({self.enzyme_units})"
        adsorption_constant = context.parameter(self.adsorption_model.adsorption_symbol, adsorption_units)
        reference_area = magnitude_in(
            self.accessible_surface_model.accessible_area(context.parameters),
            "meter ** 2",
            name="accessible_surface_area",
        )
        rate_constant = magnitude_in(
            self.catalytic_model.rate_constant(context.parameters),
            f"{self.rate_units} / meter ** 2",
            name="surface_catalysis_rate_constant",
        )
        if reference_area < 0:
            raise ValueError("accessible_surface_area must be non-negative.")
        if rate_constant < 0:
            raise ValueError("surface_catalysis_rate_constant must be non-negative.")
        if adsorption_constant < 0:
            raise ValueError("adsorption_equilibrium_constant must be non-negative.")
        strength_scale = float(
            assert_compatible(
                Q_(1.0, adsorption_units) * Q_(1.0, self.enzyme_units),
                "dimensionless",
                name="K_ads * free_enzyme",
            ).magnitude
        )
        rate_scale = float(
            assert_compatible(
                Q_(1.0, f"{self.rate_units} / meter ** 2") * Q_(1.0, "meter ** 2"),
                self.rate_units,
                name="surface catalysis rate",
            ).magnitude
        )
        if self.area_model == MASS_SCALED:
            reference_mass, exponent = self.accessible_surface_model.scaling_parameters(
                context.parameters,
                self.substrate_units,
            )
        else:
            reference_mass, exponent = float("nan"), float("nan")
        return {
            "enzyme_index": enzyme_index,
            "to_enzyme": to_enzyme,
            "substrate_index": substrate_index,
            "to_substrate": to_substrate,
            "adsorption_constant": adsorption_constant,
            "reference_area": reference_area,
            "rate_constant": rate_constant,
            "strength_scale": strength_scale,
            "rate_scale": rate_scale,
            "reference_mass": reference_mass,
            "exponent": exponent,
        }

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        terms = self._compiled_terms(context)
        enzyme_index = terms["enzyme_index"]
        to_enzyme = terms["to_enzyme"]
        substrate_index = terms["substrate_index"]
        to_substrate = terms["to_substrate"]
        adsorption_constant = terms["adsorption_constant"]
        reference_area = terms["reference_area"]
        rate_constant = terms["rate_constant"]
        strength_scale = terms["strength_scale"]
        rate_scale = terms["rate_scale"]
        reference_mass = terms["reference_mass"]
        exponent = terms["exponent"]
        mass_scaled = self.area_model == MASS_SCALED

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            enzyme = state[enzyme_index] * to_enzyme
            if enzyme < 0:
                raise ValueError("free_enzyme must be non-negative.")
            substrate = state[substrate_index] * to_substrate
            strength = (adsorption_constant * enzyme) * strength_scale
            coverage = strength / (1.0 + strength)
            area = reference_area
            if mass_scaled:
                area = reference_area * mass_scaled_area_factor(substrate, reference_mass, exponent)
            rate = (rate_constant * coverage) * area
            if substrate <= 0:
                rate = rate * 0.0
            return rate * rate_scale

        return kernel

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel | None:
        """Analytic gradient of :meth:`compile_rate`.

        ``dv/dE = k_s * A(m) * K / (1 + K E)**2`` everywhere. ``dv/dm`` is
        ``k_s * theta * dA/dm`` under the mass-scaled law (``n v / m`` for
        ``m > 0``; at ``m = 0`` it is ``k_s theta A_0 / m_0`` for ``n = 1`` and
        0 otherwise) and 0 under ``constant_until_depletion``, whose step at
        depletion has no derivative; at ``m <= 0`` the constant law's rate is
        identically zero, so its gradient is zero in every state there.
        """

        terms = self._compiled_terms(context)
        enzyme_index = terms["enzyme_index"]
        to_enzyme = terms["to_enzyme"]
        substrate_index = terms["substrate_index"]
        to_substrate = terms["to_substrate"]
        adsorption_constant = terms["adsorption_constant"]
        reference_area = terms["reference_area"]
        rate_constant = terms["rate_constant"]
        strength_scale = terms["strength_scale"]
        rate_scale = terms["rate_scale"]
        reference_mass = terms["reference_mass"]
        exponent = terms["exponent"]
        mass_scaled = self.area_model == MASS_SCALED
        size = len(context.state_index)

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            enzyme = state[enzyme_index] * to_enzyme
            if enzyme < 0:
                raise ValueError("free_enzyme must be non-negative.")
            substrate = state[substrate_index] * to_substrate
            result = np.zeros(size, dtype=float)
            strength = (adsorption_constant * enzyme) * strength_scale
            denominator = 1.0 + strength
            coverage = strength / denominator
            coverage_derivative = adsorption_constant * strength_scale / (denominator * denominator)
            if mass_scaled:
                area = reference_area * mass_scaled_area_factor(substrate, reference_mass, exponent)
                area_derivative = reference_area * mass_scaled_area_factor_derivative(substrate, reference_mass, exponent)
                result[enzyme_index] += rate_constant * area * coverage_derivative * rate_scale * to_enzyme
                result[substrate_index] += rate_constant * coverage * area_derivative * rate_scale * to_substrate
            elif substrate > 0:
                result[enzyme_index] += rate_constant * reference_area * coverage_derivative * rate_scale * to_enzyme
            return result

        return gradient

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        return {
            species: self.product_release_map.signed_coefficient(species) * value
            for species in self.product_release_map.species
        }

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "accessible_site_pool": self.accessible_site_pool.to_dict(),
                "accessible_surface_model": self.accessible_surface_model.to_dict(),
                "adsorption_model": self.adsorption_model.to_dict(),
                "catalytic_model": self.catalytic_model.to_dict(),
                "product_release_map": self.product_release_map.to_dict(),
                "area_model": self.area_model,
            }
        )
        return data


BondCleavageProcess = SurfaceCatalysisProcess


def _area_model_name(accessible_surface_model: Any) -> str:
    """The area law a surface model declares; models without one are constant until depletion."""

    area_model = str(getattr(accessible_surface_model, "area_model", CONSTANT_UNTIL_DEPLETION))
    if area_model not in AREA_MODELS:
        raise ValueError(f"Unsupported accessible-area model {area_model!r}; expected one of {AREA_MODELS}.")
    return area_model


def _area_model_limitations(area_model: str) -> tuple[str, ...]:
    if area_model == CONSTANT_UNTIL_DEPLETION:
        return (
            "area_model=constant_until_depletion: accessible surface area is constant for any positive "
            "substrate amount and the rate steps to zero at depletion, so the rate is zeroth order in "
            "substrate and the right-hand side is discontinuous there; the substrate gradient is reported as 0.",
        )
    return (
        "area_model=mass_scaled: accessible surface area follows A = A_0 (m/m_0)**n with a single geometry "
        "exponent; crystallinity, amorphous-fraction and pore-accessibility evolution are not represented.",
    )


@dataclass(frozen=True, init=False)
class SiteBindingSurfaceCatalysisProcess(Process):
    """Surface catalysis with a closed enzyme-site balance (conserved total enzyme).

    States: total enzyme ``E_T`` (concentration, conserved by this process),
    substrate amount ``m`` and the products of ``product_release_map``.
    Parameters: attack sites per substrate amount ``a_s``, dissociation
    constant ``K_d``, site turnover ``k_cat,s`` and the liquid volume ``V``.

    ``S_0 = a_s m / V``; ``E_b`` from :func:`site_binding_bound_enzyme`;
    ``v = k_cat,s E_b V / a_s`` in substrate amount per time.
    """

    substrate_state: str
    enzyme_state: str
    substrate_units: str
    enzyme_units: str
    rate_units: str
    sites_per_mass_symbol: str
    dissociation_constant_symbol: str
    site_turnover_symbol: str
    volume_symbol: str
    product_release_map: ProductReleaseMap
    primary_source: str
    maturity: str

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        enzyme_state: str,
        substrate_units: str,
        enzyme_units: str,
        rate_units: str,
        sites_per_mass_symbol: str,
        dissociation_constant_symbol: str,
        site_turnover_symbol: str,
        volume_symbol: str,
        product_release_map: ProductReleaseMap,
        primary_source: str,
        maturity: str,
        state_units: Mapping[str, str] | None = None,
        source: str = "Generic enzyme-site binding surface catalysis process.",
        notes: str = "",
    ) -> None:
        source_text = str(primary_source).strip()
        if not source_text:
            raise ValueError("Site-binding surface catalysis requires a nonblank primary_source.")
        if maturity != SITE_BINDING_MATURITY:
            raise ValueError(f"Site-binding surface catalysis maturity must be {SITE_BINDING_MATURITY!r}; received {maturity!r}.")
        if substrate_state not in product_release_map.reactants:
            raise ValueError("The product release map must consume the configured substrate state.")
        if enzyme_state in product_release_map.species:
            raise ValueError("Total enzyme is conserved by site binding; it must not appear in the product release map.")
        Q_(1, substrate_units)
        Q_(1, enzyme_units)
        Q_(1, rate_units)
        sites_units = f"mole / ({substrate_units})"
        assert_compatible(
            Q_(1.0, "1 / second") * Q_(1.0, enzyme_units) * Q_(1.0, "liter") / Q_(1.0, sites_units),
            rate_units,
            name="site-binding surface catalysis rate",
        )
        units_by_state = dict(state_units or {})
        units_by_state.setdefault(substrate_state, substrate_units)
        units_by_state.setdefault(enzyme_state, enzyme_units)
        for species in product_release_map.species:
            units_by_state.setdefault(species, substrate_units)
        Process.__init__(
            self,
            name=name,
            process_type=SITE_BINDING_SURFACE_CATALYSIS_PROCESS_TYPE,
            required_state_variables=(
                StateVariableSpec(substrate_state, substrate_units, role="solid_substrate"),
                StateVariableSpec(enzyme_state, enzyme_units, role="total_catalyst"),
            ),
            changed_state_variables=tuple(
                StateVariableSpec(species, units_by_state[species]) for species in product_release_map.species
            ),
            required_parameters=(
                ParameterRequirement(symbol=sites_per_mass_symbol, units=sites_units, name="accessible attack sites per substrate amount a_s"),
                ParameterRequirement(symbol=dissociation_constant_symbol, units=enzyme_units, name="enzyme-site dissociation constant K_d"),
                ParameterRequirement(symbol=site_turnover_symbol, units="1 / second", name="site turnover number k_cat,s"),
                ParameterRequirement(symbol=volume_symbol, units="liter", name="liquid volume V"),
            ),
            assumptions=(site_binding_surface_catalysis_assumption(),),
            validity=ValidityDomain(
                description="Generic enzyme-site binding surface catalysis with a conserved total enzyme.",
                labels=("surface", "heterogeneous", "bond_cleavage", "enzyme_site_balance", maturity),
                limitations=(
                    "Equilibrium binding to one class of accessible sites; no adsorption/desorption dynamics, "
                    "product inhibition, non-productive binding or site renewal; a_s is constant per unit remaining substrate.",
                ),
            ),
            failure_modes=(
                "missing or unknown sites_per_mass",
                "missing dissociation constant",
                "missing site turnover",
                "missing volume",
                "unsupported maturity or missing primary source",
            ),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "substrate_state", substrate_state)
        object.__setattr__(self, "enzyme_state", enzyme_state)
        object.__setattr__(self, "substrate_units", substrate_units)
        object.__setattr__(self, "enzyme_units", enzyme_units)
        object.__setattr__(self, "rate_units", rate_units)
        object.__setattr__(self, "sites_per_mass_symbol", sites_per_mass_symbol)
        object.__setattr__(self, "dissociation_constant_symbol", dissociation_constant_symbol)
        object.__setattr__(self, "site_turnover_symbol", site_turnover_symbol)
        object.__setattr__(self, "volume_symbol", volume_symbol)
        object.__setattr__(self, "product_release_map", product_release_map)
        object.__setattr__(self, "primary_source", source_text)
        object.__setattr__(self, "maturity", maturity)

    @property
    def sites_units(self) -> str:
        return f"mole / ({self.substrate_units})"

    def _parameters(self, parameters: ParameterSet) -> tuple[Quantity, Quantity, Quantity, Quantity]:
        sites_per_mass = parameters.require_quantity(self.sites_per_mass_symbol, self.sites_units)
        dissociation = parameters.require_quantity(self.dissociation_constant_symbol, self.enzyme_units)
        turnover = parameters.require_quantity(self.site_turnover_symbol, "1 / second")
        volume = parameters.require_quantity(self.volume_symbol, "liter")
        for quantity, label in (
            (dissociation, self.dissociation_constant_symbol),
            (turnover, self.site_turnover_symbol),
        ):
            _ensure_non_negative(quantity, label)
        if float(sites_per_mass.magnitude) <= 0.0:
            raise ValueError(f"{self.sites_per_mass_symbol} (sites per substrate amount) must be positive.")
        if float(volume.magnitude) <= 0.0:
            raise ValueError(f"{self.volume_symbol} (liquid volume) must be positive.")
        return sites_per_mass, dissociation, turnover, volume

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: object = None,
        geometry: object = None,
    ) -> Quantity:
        del time, environment, geometry
        total_enzyme = assert_compatible(state[self.enzyme_state], self.enzyme_units, name=self.enzyme_state)
        substrate = assert_compatible(state[self.substrate_state], self.substrate_units, name=self.substrate_state)
        _ensure_non_negative(total_enzyme, self.enzyme_state)
        _ensure_non_negative(substrate, self.substrate_state)
        sites_per_mass, dissociation, turnover, volume = self._parameters(parameters)
        site_concentration = assert_compatible(sites_per_mass * substrate / volume, self.enzyme_units, name="site concentration")
        bound = site_binding_bound_enzyme(
            total_enzyme=total_enzyme,
            site_concentration=site_concentration,
            dissociation_constant=dissociation,
        )
        return assert_compatible(turnover * bound * volume / sites_per_mass, self.rate_units, name=f"{self.name} rate")

    def _compiled_terms(self, context: KernelContext) -> dict[str, Any]:
        enzyme_index, to_enzyme = context.state_slot(self.enzyme_state, self.enzyme_units)
        substrate_index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        sites_per_mass, dissociation, turnover, volume = self._parameters(context.parameters)
        sites_scale = float(
            assert_compatible(
                Q_(1.0, self.sites_units) * Q_(1.0, self.substrate_units) / Q_(1.0, "liter"),
                self.enzyme_units,
                name="site concentration",
            ).magnitude
        )
        rate_scale = float(
            assert_compatible(
                Q_(1.0, "1 / second") * Q_(1.0, self.enzyme_units) * Q_(1.0, "liter") / Q_(1.0, self.sites_units),
                self.rate_units,
                name="site-binding surface catalysis rate",
            ).magnitude
        )
        return {
            "enzyme_index": enzyme_index,
            "to_enzyme": to_enzyme,
            "substrate_index": substrate_index,
            "to_substrate": to_substrate,
            "sites_per_mass": magnitude_in(sites_per_mass, self.sites_units, name=self.sites_per_mass_symbol),
            "dissociation": magnitude_in(dissociation, self.enzyme_units, name=self.dissociation_constant_symbol),
            "turnover": magnitude_in(turnover, "1 / second", name=self.site_turnover_symbol),
            "volume": magnitude_in(volume, "liter", name=self.volume_symbol),
            "sites_scale": sites_scale,
            "rate_scale": rate_scale,
        }

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        terms = self._compiled_terms(context)
        enzyme_index, to_enzyme = terms["enzyme_index"], terms["to_enzyme"]
        substrate_index, to_substrate = terms["substrate_index"], terms["to_substrate"]
        sites_per_mass, dissociation = terms["sites_per_mass"], terms["dissociation"]
        turnover, volume = terms["turnover"], terms["volume"]
        sites_scale, rate_scale = terms["sites_scale"], terms["rate_scale"]
        site_factor = sites_per_mass / volume * sites_scale
        rate_factor = turnover * volume / sites_per_mass * rate_scale

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            total_enzyme = state[enzyme_index] * to_enzyme
            substrate = state[substrate_index] * to_substrate
            if total_enzyme < 0:
                raise ValueError(f"{self.enzyme_state} must be non-negative.")
            if substrate < 0:
                raise ValueError(f"{self.substrate_state} must be non-negative.")
            bound = bound_enzyme_magnitude(total_enzyme, substrate * site_factor, dissociation)
            return bound * rate_factor

        return kernel

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel | None:
        """``dv/dE_T = k V/a_s * dE_b/dE_T``; ``dv/dm = k * dE_b/dS_0`` (``dS_0/dm = a_s/V``); 0 where ``Delta = 0``."""

        terms = self._compiled_terms(context)
        enzyme_index, to_enzyme = terms["enzyme_index"], terms["to_enzyme"]
        substrate_index, to_substrate = terms["substrate_index"], terms["to_substrate"]
        sites_per_mass, dissociation = terms["sites_per_mass"], terms["dissociation"]
        turnover, volume = terms["turnover"], terms["volume"]
        sites_scale, rate_scale = terms["sites_scale"], terms["rate_scale"]
        site_factor = sites_per_mass / volume * sites_scale
        rate_factor = turnover * volume / sites_per_mass * rate_scale
        size = len(context.state_index)

        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            total_enzyme = state[enzyme_index] * to_enzyme
            substrate = state[substrate_index] * to_substrate
            if total_enzyme < 0:
                raise ValueError(f"{self.enzyme_state} must be non-negative.")
            if substrate < 0:
                raise ValueError(f"{self.substrate_state} must be non-negative.")
            by_total, by_sites = bound_enzyme_derivative_magnitudes(total_enzyme, substrate * site_factor, dissociation)
            result = np.zeros(size, dtype=float)
            result[enzyme_index] += rate_factor * by_total * to_enzyme
            result[substrate_index] += rate_factor * by_sites * site_factor * to_substrate
            return result

        return gradient

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        return {
            species: self.product_release_map.signed_coefficient(species) * value
            for species in self.product_release_map.species
        }

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "substrate_state": self.substrate_state,
                "enzyme_state": self.enzyme_state,
                "sites_per_mass_symbol": self.sites_per_mass_symbol,
                "dissociation_constant_symbol": self.dissociation_constant_symbol,
                "site_turnover_symbol": self.site_turnover_symbol,
                "volume_symbol": self.volume_symbol,
                "product_release_map": self.product_release_map.to_dict(),
                "primary_source": self.primary_source,
                "maturity": self.maturity,
                "equation": (
                    "S_0 = a_s m / V; Sigma = E_T + S_0 + K_d; E_b = (Sigma - sqrt(Sigma^2 - 4 E_T S_0)) / 2; "
                    "v = k_cat,s E_b V / a_s"
                ),
            }
        )
        return data


def _unique_assumptions(assumptions: list[Assumption]) -> tuple[Assumption, ...]:
    result: list[Assumption] = []
    seen: set[str] = set()
    for assumption in assumptions:
        if assumption.name not in seen:
            result.append(assumption)
            seen.add(assumption.name)
    return tuple(result)


__all__ = [
    "AREA_MODELS",
    "CONSTANT_UNTIL_DEPLETION",
    "MASS_SCALED",
    "MASS_SCALED_AREA_MATURITY",
    "SITE_BINDING_MATURITY",
    "SITE_BINDING_SURFACE_CATALYSIS_PROCESS_TYPE",
    "AccessibleSitePool",
    "AccessibleSurfaceAreaModel",
    "BondCleavageProcess",
    "EquilibriumSurfaceCoverageModel",
    "LangmuirAdsorptionModel",
    "ProductReleaseMap",
    "SiteBindingSurfaceCatalysisProcess",
    "SurfaceCatalysisModel",
    "SurfaceCatalysisProcess",
    "mass_scaled_area_assumption",
    "mass_scaled_area_factor",
    "mass_scaled_area_factor_derivative",
    "site_binding_surface_catalysis_assumption",
    "surface_catalysis_assumption",
    "surface_catalysis_rate",
]
