"""Failure-closed composition of minimal fungal and extracellular reactions."""

from __future__ import annotations

from dataclasses import dataclass

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.validators import ValidationResult
from fungal_model.core.simulation import SimulationEngine
from fungal_model.fungi.base import Fungus
from fungal_model.fungi.energetics import GibbsEnergyYieldBound
from fungal_model.fungi.enzyme_profile import (
    EnzymeDecayRateLaw,
    EnzymeProductionCostRateLaw,
    EnzymeSecretionRateLaw,
)
from fungal_model.fungi.growth import BiomassMaintenanceRateLaw
from fungal_model.fungi.metabolism import ProductUptakeRateLaw, biomass_yield_coefficient


FUNGAL_COUPLING_MATURITY = "exploratory_software_tested"


@dataclass(frozen=True)
class FungalCouplingModel:
    """Compose explicit secretion, decay, degradation, uptake, and biomass reactions.

    The model reuses existing rate laws and a caller-supplied extracellular
    degradation reaction. It does not infer organism capabilities, parameter
    values, reaction stoichiometry, or intracellular metabolism.
    """

    fungus: Fungus
    degradation_reactions: tuple[Reaction, ...]
    additional_parameters: ParameterSet
    substrate_state: str
    product_state: str
    enzyme_state: str
    active_biomass_state: str
    inactive_biomass_state: str
    substrate_name: str
    product_name: str
    target_bond_type: str
    enzyme_class: str
    coupling_source: str
    maturity: str = FUNGAL_COUPLING_MATURITY
    #: Optional thermodynamic ceiling on the biomass yield. When supplied, a
    #: configured yield that would create free energy is rejected before the
    #: model can run. Thermodynamics constrains the yield; it never supplies a
    #: rate, which depends on enzyme activation barriers instead.
    yield_bound: GibbsEnergyYieldBound | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "substrate_state",
            "product_state",
            "enzyme_state",
            "active_biomass_state",
            "inactive_biomass_state",
            "substrate_name",
            "product_name",
            "target_bond_type",
            "enzyme_class",
        ):
            if not has_text(getattr(self, field_name)):
                raise ValueError(f"Fungal coupling {field_name} must be nonblank.")
        states = {
            self.substrate_state,
            self.product_state,
            self.enzyme_state,
            self.active_biomass_state,
            self.inactive_biomass_state,
        }
        if len(states) != 5:
            raise ValueError("Fungal coupling state names must be distinct.")
        if not has_text(self.coupling_source):
            raise ProvenanceError("Fungal coupling requires a nonblank coupling_source.")
        if self.maturity != FUNGAL_COUPLING_MATURITY:
            raise ValueError(
                f"Fungal coupling maturity must be {FUNGAL_COUPLING_MATURITY!r}."
            )
        if not self.degradation_reactions:
            raise ValueError("Fungal coupling requires at least one extracellular degradation reaction.")
        changed_species = set().union(*(reaction.species for reaction in self.degradation_reactions))
        missing = {self.substrate_state, self.product_state}.difference(changed_species)
        if missing:
            raise ValueError(
                "Fungal coupling degradation reactions must change the configured "
                f"substrate and product states; missing {sorted(missing)}."
            )

    @property
    def parameters(self) -> ParameterSet:
        """Return the exact union of fungal and extracellular parameters."""

        fungal_symbols = {parameter.symbol for parameter in self.fungus.parameters}
        additional_symbols = {parameter.symbol for parameter in self.additional_parameters}
        overlap = sorted(fungal_symbols.intersection(additional_symbols))
        if overlap:
            raise ValueError(f"Fungal and additional parameters overlap: {overlap}.")
        return ParameterSet((*self.fungus.parameters, *self.additional_parameters))

    def validate(self) -> None:
        """Validate capabilities, assimilation evidence, parameters, and reactions."""

        self.fungus.validate(require_parameter_values=True)
        capabilities = self.fungus.enzyme_profile.compatible_capabilities(
            substrate_name=self.substrate_name,
            bond_type=self.target_bond_type,
            enzyme_class=self.enzyme_class,
        )
        if not capabilities:
            raise ValueError(
                "Fungal coupling requires an explicit matching extracellular enzyme capability."
            )
        assimilations = tuple(
            item
            for item in self.fungus.uptake_capabilities
            if item.product.casefold() == self.product_name.casefold()
        )
        if not assimilations:
            raise ValueError("Fungal coupling requires an explicit product-assimilation record.")
        if len(assimilations) != 1:
            raise ValueError("Fungal coupling requires exactly one matching product-assimilation record.")
        if not assimilations[0].assimilable:
            raise ValueError("The configured degradation product is explicitly non-assimilable.")
        self.parameters.validate(require_values=True)
        self.validate_yield_energetics()
        for reaction in self.degradation_reactions:
            reaction.validate_provenance()

    def validate_yield_energetics(self) -> ValidationResult | None:
        """Reject a biomass yield that exceeds its thermodynamic ceiling.

        Returns None when no bound is configured. Supplying a bound removes a
        degree of freedom: the yield can no longer be fitted to any value the
        data happens to prefer, only to a thermodynamically admissible one.
        """

        if self.yield_bound is None:
            return None
        declared = self.parameters.require_quantity("Y_B", "dimensionless")
        return self.yield_bound.enforce_yield(declared, symbol="Y_B")

    def reactions(self) -> tuple[Reaction, ...]:
        """Return the complete coupled reaction set after validation."""

        self.validate()
        assimilation = next(
            item
            for item in self.fungus.uptake_capabilities
            if item.product.casefold() == self.product_name.casefold()
        )
        secretion = EnzymeSecretionRateLaw(
            active_biomass=self.active_biomass_state,
            secretion_symbol="alpha_E",
            rate_units="mole / liter / second",
        )
        decay = EnzymeDecayRateLaw(
            enzyme=self.enzyme_state,
            decay_symbol="delta_E",
            rate_units="mole / liter / second",
            enzyme_units="mole / liter",
        )
        production_cost = EnzymeProductionCostRateLaw(
            active_biomass=self.active_biomass_state,
            secretion_symbol="alpha_E",
            secretion_cost_symbol="c_E",
            enzyme_rate_units="mole / liter / second",
            biomass_rate_units="kilogram / second",
        )
        maintenance = BiomassMaintenanceRateLaw(
            active_biomass=self.active_biomass_state,
            maintenance_symbol="m_B",
            rate_units="kilogram / second",
        )
        uptake = ProductUptakeRateLaw(
            product=self.product_state,
            active_biomass=self.active_biomass_state,
            uptake_symbol="q_product",
            assimilation=assimilation,
            rate_units="kilogram / second",
        )
        yield_value = biomass_yield_coefficient(
            parameters=self.parameters,
            yield_symbol="Y_B",
        )
        coupled = (
            Reaction(
                name="fungal extracellular enzyme secretion",
                reactants={},
                products={self.enzyme_state: 1.0},
                rate_law=secretion,
                rate_units="mole / liter / second",
                assumptions=secretion.assumptions,
                source=self.coupling_source,
            ),
            Reaction(
                name="extracellular enzyme decay",
                reactants={self.enzyme_state: 1.0},
                products={},
                rate_law=decay,
                rate_units="mole / liter / second",
                assumptions=decay.assumptions,
                source=self.coupling_source,
            ),
            Reaction(
                name="enzyme secretion active biomass cost",
                reactants={self.active_biomass_state: 1.0},
                products={self.inactive_biomass_state: 1.0},
                rate_law=production_cost,
                rate_units="kilogram / second",
                assumptions=production_cost.assumptions,
                source=self.coupling_source,
            ),
            Reaction(
                name="assimilable degradation-product uptake",
                reactants={self.product_state: 1.0},
                products={self.active_biomass_state: yield_value},
                rate_law=uptake,
                rate_units="kilogram / second",
                assumptions=uptake.assumptions,
                source=self.coupling_source,
                notes=(
                    "Unassimilated product mass is an explicit open-system loss; "
                    "respiration and intracellular metabolism are unresolved."
                ),
            ),
            Reaction(
                name="active biomass maintenance loss",
                reactants={self.active_biomass_state: 1.0},
                products={self.inactive_biomass_state: 1.0},
                rate_law=maintenance,
                rate_units="kilogram / second",
                assumptions=maintenance.assumptions,
                source=self.coupling_source,
            ),
        )
        return (*self.degradation_reactions, *coupled)

    def build_engine(self) -> SimulationEngine:
        """Build a well-mixed engine for the explicit exploratory coupling."""

        return SimulationEngine(
            reactions=self.reactions(),
            parameters=self.parameters,
            species_units={
                self.substrate_state: "kilogram",
                self.product_state: "kilogram",
                self.enzyme_state: "mole / liter",
                self.active_biomass_state: "kilogram",
                self.inactive_biomass_state: "kilogram",
            },
            assumptions=self.fungus.assumptions,
        )

    def to_dict(self) -> dict[str, object]:
        """Return inspectable scope and provenance metadata."""

        return {
            "maturity": self.maturity,
            "fungus": self.fungus.species_name,
            "substrate_name": self.substrate_name,
            "product_name": self.product_name,
            "target_bond_type": self.target_bond_type,
            "enzyme_class": self.enzyme_class,
            "coupling_source": self.coupling_source,
            "yield_bound": None if self.yield_bound is None else self.yield_bound.to_dict(),
            "states": {
                "substrate": self.substrate_state,
                "product": self.product_state,
                "enzyme": self.enzyme_state,
                "active_biomass": self.active_biomass_state,
                "inactive_biomass": self.inactive_biomass_state,
            },
            "limitations": (
                "Exploratory well-mixed coupling only; no intracellular metabolism, "
                "oxygen state, regulation, morphology, toxicity, spatial secretion, "
                "empirical calibration, or organism-level validation."
            ),
        }


__all__ = ["FUNGAL_COUPLING_MATURITY", "FungalCouplingModel"]
