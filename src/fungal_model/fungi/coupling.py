"""Failure-closed composition of minimal fungal and extracellular reactions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ConfidenceLevel, ProvenanceError, has_text
from fungal_model.core.units import Quantity
from fungal_model.core.validators import ValidationResult
from fungal_model.core.simulation import SimulationEngine
from fungal_model.processes.base import Process
from fungal_model.processes.homogeneous import FirstOrderDecayProcess, MassActionProcess
from fungal_model.processes.physiology import ProportionalSynthesisProcess
from fungal_model.fungi.base import Fungus
from fungal_model.fungi.energetics import GibbsEnergyYieldBound
from fungal_model.fungi.enzyme_profile import (
    EnzymeDecayRateLaw,
    EnzymeProductionCostRateLaw,
    EnzymeSecretionRateLaw,
)
from fungal_model.fungi.growth import BiomassMaintenanceRateLaw
from fungal_model.fungi.metabolism import ProductUptakeRateLaw, biomass_yield_coefficient

if TYPE_CHECKING:
    from fungal_model.results import SimulationResult


FUNGAL_COUPLING_MATURITY = "exploratory_software_tested"
SECRETION_COST_RATE_SYMBOL = "alpha_E_c_E"
ENZYME_UNITS = "mole / liter"
BIOMASS_UNITS = "kilogram"
ENZYME_RATE_UNITS = "mole / liter / second"
BIOMASS_RATE_UNITS = "kilogram / second"
_CONFIDENCE_ORDER: tuple[ConfidenceLevel, ...] = ("unknown", "low", "medium", "high")


def _combined_confidence(*levels: ConfidenceLevel) -> ConfidenceLevel:
    """The weaker of the input confidence levels; ``testing`` only when every input is ``testing``."""

    if all(level == "testing" for level in levels):
        return "testing"
    ranked: list[ConfidenceLevel] = [level for level in levels if level in _CONFIDENCE_ORDER]
    if not ranked:
        return "unknown"
    return min(ranked, key=_CONFIDENCE_ORDER.index)


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
        assimilation = self._assimilation()
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

    def _assimilation(self):
        return next(
            item
            for item in self.fungus.uptake_capabilities
            if item.product.casefold() == self.product_name.casefold()
        )

    def compiled_processes(self, degradation: Sequence[Process]) -> tuple[Process, ...]:
        """The coupling as generic processes for the compiled process core.

        ``degradation`` supplies the extracellular degradation as processes
        (``reactions()`` takes ``Reaction`` objects whose Python rate laws
        cannot be compiled); together they must change the configured
        substrate and product states, as the reactions must. Secretion is
        producer-proportional synthesis, decay first-order, the secretion cost
        and maintenance are first-order conversions of active into inactive
        biomass, and uptake is mass action in the product catalysed by active
        biomass with the declared yield. The secretion cost uses the derived
        rate constant ``alpha_E * c_E`` (see ``compiled_parameters``).
        """

        self.validate()
        if not degradation:
            raise ValueError("Fungal coupling requires at least one extracellular degradation process.")
        changed_species = set().union(
            *(set(spec.name for spec in process.changed_state_variables) for process in degradation)
        )
        missing = {self.substrate_state, self.product_state}.difference(changed_species)
        if missing:
            raise ValueError(
                "Fungal coupling degradation processes must change the configured "
                f"substrate and product states; missing {sorted(missing)}."
            )
        biomass_units = {self.active_biomass_state: BIOMASS_UNITS, self.inactive_biomass_state: BIOMASS_UNITS}
        yield_value = biomass_yield_coefficient(parameters=self.parameters, yield_symbol="Y_B")
        coupled: tuple[Process, ...] = (
            ProportionalSynthesisProcess(
                name="fungal extracellular enzyme secretion",
                producer_state=self.active_biomass_state,
                producer_units=BIOMASS_UNITS,
                product_state=self.enzyme_state,
                product_units=ENZYME_UNITS,
                rate_units=ENZYME_RATE_UNITS,
                specific_rate_symbol="alpha_E",
                source=self.coupling_source,
                notes="Constitutive secretion proportional to active biomass.",
            ),
            FirstOrderDecayProcess(
                name="extracellular enzyme decay",
                substrate_state=self.enzyme_state,
                rate_constant_symbol="delta_E",
                state_units=ENZYME_UNITS,
                rate_units=ENZYME_RATE_UNITS,
                source=self.coupling_source,
                notes="First-order loss of extracellular enzyme; the material is not tracked.",
            ),
            MassActionProcess(
                name="enzyme secretion active biomass cost",
                reactants={self.active_biomass_state: 1.0},
                products={self.inactive_biomass_state: 1.0},
                state_units=biomass_units,
                rate_constant_symbol=SECRETION_COST_RATE_SYMBOL,
                rate_constant_units="1 / second",
                rate_units=BIOMASS_RATE_UNITS,
                source=self.coupling_source,
                notes="Active biomass lost per enzyme secreted: rate constant alpha_E times c_E.",
            ),
            MassActionProcess(
                name="assimilable degradation-product uptake",
                reactants={self.product_state: 1.0},
                products={self.active_biomass_state: yield_value},
                catalysts={self.active_biomass_state: 1.0},
                state_units={self.product_state: BIOMASS_UNITS, self.active_biomass_state: BIOMASS_UNITS},
                rate_constant_symbol="q_product",
                rate_constant_units="1 / kilogram / second",
                rate_units=BIOMASS_RATE_UNITS,
                source=self.coupling_source,
                notes=(
                    "Unassimilated product mass is an explicit open-system loss; "
                    "respiration and intracellular metabolism are unresolved."
                ),
            ),
            MassActionProcess(
                name="active biomass maintenance loss",
                reactants={self.active_biomass_state: 1.0},
                products={self.inactive_biomass_state: 1.0},
                state_units=biomass_units,
                rate_constant_symbol="m_B",
                rate_constant_units="1 / second",
                rate_units=BIOMASS_RATE_UNITS,
                source=self.coupling_source,
                notes="First-order conversion of active into inactive biomass.",
            ),
        )
        return (*degradation, *coupled)

    def compiled_parameters(self) -> ParameterSet:
        """The union of fungal and extracellular parameters plus the derived secretion-cost rate constant."""

        parameters = self.parameters
        if SECRETION_COST_RATE_SYMBOL in parameters:
            raise ValueError(f"Parameter symbol {SECRETION_COST_RATE_SYMBOL!r} is reserved for the derived secretion cost.")
        secretion = parameters.get("alpha_E")
        cost = parameters.get("c_E")
        product = parameters.require_quantity("alpha_E", "mole / liter / kilogram / second") * parameters.require_quantity(
            "c_E", "kilogram / (mole / liter)"
        )
        derived = Parameter(
            "enzyme secretion cost rate constant (alpha_E times c_E)",
            SECRETION_COST_RATE_SYMBOL,
            product.to("1 / second"),
            "1 / second",
            None,
            f"Derived from {secretion.symbol} ({secretion.source}) and {cost.symbol} ({cost.source}).",
            _combined_confidence(secretion.confidence_level, cost.confidence_level),
            "Product of the secretion coefficient and the secretion cost, so that the active-biomass cost of "
            "secretion is one mass-action process on the compiled core. Not an independent parameter.",
        )
        return ParameterSet((*parameters, derived))

    def simulate_compiled(
        self,
        *,
        degradation: Sequence[Process],
        initial_state: Mapping[str, Quantity],
        t_span: tuple[Quantity, Quantity],
        t_eval: Quantity | None = None,
        solver_settings: SolverSettings | None = None,
    ) -> SimulationResult:
        """Integrate ``compiled_processes(degradation)`` on the compiled process core."""

        from fungal_model.processes.assembly import ModelBuilder
        from fungal_model.processes.registry import ProcessRegistry
        from fungal_model.solvers.process_ode import ProcessODESolver, RunRequest

        processes = self.compiled_processes(degradation)
        model = ModelBuilder(
            process_library=ProcessRegistry(processes),
            requested_processes=tuple(process.name for process in processes),
            parameters=self.compiled_parameters(),
            solver_settings=solver_settings or SolverSettings(),
        ).assemble()
        return ProcessODESolver(model).run(
            RunRequest(initial_state=initial_state, t_span=t_span, t_eval=t_eval, name="fungal_coupling", label="exploratory")
        )

    def build_engine(self) -> SimulationEngine:
        """Build a well-mixed engine for the explicit exploratory coupling (legacy ``Reaction`` path)."""

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


__all__ = ["FUNGAL_COUPLING_MATURITY", "SECRETION_COST_RATE_SYMBOL", "FungalCouplingModel"]
