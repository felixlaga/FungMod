from __future__ import annotations

import pytest

from fungal_model.chemistry import (
    DEGREE_OF_REDUCTION_SOURCE,
    ELEMENT_SYMBOLS,
    ElementalComposition,
    MacrochemicalBalance,
    MacrochemicalSpecies,
    OxygenDemand,
    StoichiometricReactionMetadata,
    StoichiometricTerm,
    assign_electron_equivalents,
    degree_of_reduction,
    electron_balance_residual,
    electron_equivalents_from_composition,
)
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, UnitError
from fungal_model.core.validators import validate_electron_balance

FORMULA_SOURCE = "Molecular formula; exact chemical identity, not a measured parameter."
ARTIFICIAL_SOURCE = "Artificial degree-of-reduction benchmark; no organism claim."
BIOMASS_ELEMENTS = {"C": 1.0, "H": 1.8, "O": 0.5, "N": 0.2}


def _formula(formula: str) -> ElementalComposition:
    return ElementalComposition.from_formula(formula, source=FORMULA_SOURCE)


def _biomass() -> ElementalComposition:
    return ElementalComposition.from_elements(BIOMASS_ELEMENTS, source=ARTIFICIAL_SOURCE, formula="CH1.8O0.5N0.2")


def _species(name: str, composition: ElementalComposition, charge: float = 0.0) -> MacrochemicalSpecies:
    return MacrochemicalSpecies(name=name, composition=composition, charge=charge, charge_source=FORMULA_SOURCE)


def test_degree_of_reduction_hand_values() -> None:
    assert degree_of_reduction(_formula("C6H12O6"), 0.0) == pytest.approx(24.0)
    assert degree_of_reduction(_formula("C6H12O6"), 0.0, per_carbon=True) == pytest.approx(4.0)
    assert degree_of_reduction(_biomass(), 0.0) == pytest.approx(4.2)
    assert degree_of_reduction(_formula("O2"), 0.0) == pytest.approx(-4.0)
    assert degree_of_reduction(_formula("CO2"), 0.0) == pytest.approx(0.0)
    assert degree_of_reduction(_formula("H2O"), 0.0) == pytest.approx(0.0)


def test_reference_compounds_and_ions_have_zero_degree_of_reduction() -> None:
    # NH3, H3PO4, H2SO4 and the proton define the zero of the convention; their
    # pH-7 ionic forms stay at zero once the charge is subtracted.
    assert degree_of_reduction(_formula("NH3"), 0.0) == pytest.approx(0.0)
    assert degree_of_reduction(_formula("NH4"), 1.0) == pytest.approx(0.0)
    assert degree_of_reduction(_formula("H3PO4"), 0.0) == pytest.approx(0.0)
    assert degree_of_reduction(_formula("H2SO4"), 0.0) == pytest.approx(0.0)
    assert degree_of_reduction(_formula("H"), 1.0) == pytest.approx(0.0)
    assert degree_of_reduction(_formula("HCO3"), -1.0) == pytest.approx(0.0)
    assert degree_of_reduction(_formula("CH4"), 0.0) == pytest.approx(8.0)


def test_glucose_oxidation_electron_balance_closes_from_composition() -> None:
    balance = MacrochemicalBalance(
        name="glucose complete oxidation",
        species=(
            _species("glucose", _formula("C6H12O6")),
            _species("oxygen", _formula("O2")),
            _species("carbon_dioxide", _formula("CO2")),
            _species("water", _formula("H2O")),
        ),
        source=FORMULA_SOURCE,
    )
    solution = balance.solve({"glucose": -1.0})

    by_hand = sum(
        coefficient * electron_equivalents_from_composition(species.composition, species.charge)
        for species in balance.species
        for coefficient in [solution.coefficients[species.name]]
    )
    assert abs(by_hand) <= 1e-12

    metadata = assign_electron_equivalents(solution.stoichiometric_metadata())
    assert abs(electron_balance_residual(metadata)) <= 1e-12
    assert all(term.electron_source == DEGREE_OF_REDUCTION_SOURCE for term in [*metadata.reactants, *metadata.products])
    assert {term.species: term.electron_equivalents for term in metadata.reactants} == pytest.approx(
        {"glucose": 24.0, "oxygen": -4.0}
    )
    assert validate_electron_balance(metadata).passed


def test_assigning_electron_equivalents_needs_composition_and_charge() -> None:
    reaction = StoichiometricReactionMetadata(
        name="partial",
        reactants=(StoichiometricTerm(species="x", coefficient=1.0, composition=_formula("CH4")),),
        products=(),
        source=FORMULA_SOURCE,
    )
    with pytest.raises(ValueError, match="composition and charge"):
        assign_electron_equivalents(reaction)


def test_oxygen_demand_from_degree_of_reduction_matches_hand_value() -> None:
    # (gamma_S - Y gamma_X) / 4 = (4 - 0.5 * 4.2) / 4 = 0.475 mol O2 per C-mol substrate.
    demand = OxygenDemand.from_degree_of_reduction(
        process_name="artificial growth",
        substrate_species="glucose",
        substrate_composition=_formula("C6H12O6"),
        substrate_charge=0.0,
        biomass_composition=_biomass(),
        biomass_charge=0.0,
        biomass_yield_per_carbon=Q_(0.5, "dimensionless"),
        yield_source=ARTIFICIAL_SOURCE,
    )

    assert demand.basis == "amount"
    assert float(demand.oxygen_per_substrate.quantity.magnitude) == pytest.approx(0.475)
    assert demand.oxygen_per_substrate.source == DEGREE_OF_REDUCTION_SOURCE
    assert demand.required_oxygen(Q_(2.0, "mole")).to("mole").magnitude == pytest.approx(0.95)
    assert demand.to_dict()["basis"] == "amount"
    with pytest.raises(UnitError):
        demand.required_oxygen(Q_(1.0, "kilogram"))


def test_oxygen_demand_matches_the_macrochemical_balance() -> None:
    """The electron-balance identity and the full conservation solve must agree."""

    balance = MacrochemicalBalance(
        name="aerobic growth",
        species=(
            _species("glucose", _formula("C6H12O6")),
            _species("ammonia", _formula("NH3")),
            _species("oxygen", _formula("O2")),
            _species("carbon_dioxide", _formula("CO2")),
            _species("water", _formula("H2O")),
            _species("biomass", _biomass()),
        ),
        source=FORMULA_SOURCE,
    )
    yield_per_carbon = 0.6
    solution = balance.solve({"biomass": 1.0, "glucose": -1.0 / (6.0 * yield_per_carbon)})
    demand = OxygenDemand.from_degree_of_reduction(
        process_name="aerobic growth",
        substrate_species="glucose",
        substrate_composition=_formula("C6H12O6"),
        substrate_charge=0.0,
        biomass_composition=_biomass(),
        biomass_charge=0.0,
        biomass_yield_per_carbon=Q_(yield_per_carbon, "dimensionless"),
        yield_source=ARTIFICIAL_SOURCE,
    )
    oxygen_per_cmol_biomass = float(demand.oxygen_per_substrate.quantity.magnitude) / yield_per_carbon

    assert -solution.coefficients["oxygen"] == pytest.approx(oxygen_per_cmol_biomass, abs=1e-12)


def test_oxygen_demand_refuses_yields_above_the_electron_ceiling_and_unsourced_yields() -> None:
    common = dict(
        process_name="artificial growth",
        substrate_species="glucose",
        substrate_composition=_formula("C6H12O6"),
        substrate_charge=0.0,
        biomass_composition=_biomass(),
        biomass_charge=0.0,
    )
    with pytest.raises(ValueError, match="exceeds the electron balance"):
        OxygenDemand.from_degree_of_reduction(
            **common, biomass_yield_per_carbon=Q_(1.0, "dimensionless"), yield_source=ARTIFICIAL_SOURCE
        )
    with pytest.raises(ProvenanceError):
        OxygenDemand.from_degree_of_reduction(
            **common, biomass_yield_per_carbon=Q_(0.5, "dimensionless"), yield_source=None
        )


def test_mass_basis_oxygen_demand_is_unchanged_and_bases_are_explicit() -> None:
    from fungal_model.core.parameters import Parameter

    demand = OxygenDemand(
        process_name="mass benchmark",
        substrate_species="polymer",
        oxygen_per_substrate=Parameter(
            name="oxygen demand",
            symbol="O2_per_polymer",
            value=0.5,
            units="kilogram / kilogram",
            uncertainty=None,
            source=ARTIFICIAL_SOURCE,
            confidence_level="testing",
            notes="",
        ),
    )
    assert demand.basis == "mass"
    assert demand.required_oxygen(Q_(2.0, "kilogram")).to("kilogram").magnitude == pytest.approx(1.0)
    with pytest.raises(UnitError):
        demand.required_oxygen(Q_(2.0, "mole"))
    with pytest.raises(ValueError, match="basis"):
        OxygenDemand(
            process_name="bad",
            substrate_species="polymer",
            oxygen_per_substrate=demand.oxygen_per_substrate,
            basis="volume",
        )


def test_unknown_element_symbols_are_refused_and_real_ones_accepted() -> None:
    with pytest.raises(ValueError, match=r"not chemical elements: \['Qq', 'Xx'\]"):
        ElementalComposition.from_formula("Xx2Qq", source=FORMULA_SOURCE)
    assert ElementalComposition.from_formula("FeS2", source=FORMULA_SOURCE).elements == {"Fe": 1.0, "S": 2.0}
    assert {"H", "C", "Og"} <= ELEMENT_SYMBOLS
    assert len(ELEMENT_SYMBOLS) == 118


def test_degree_of_reduction_refuses_undefined_cases() -> None:
    with pytest.raises(ValueError, match=r"elements \['Fe'\] have no reference state"):
        degree_of_reduction(_formula("FeS2"), 0.0)
    with pytest.raises(ValueError, match="carbon-free"):
        degree_of_reduction(_formula("O2"), 0.0, per_carbon=True)
    with pytest.raises(ValueError, match="nitrogen reference"):
        degree_of_reduction(_formula("NH3"), 0.0, nitrogen_reference="nitrate")
    with pytest.raises(ValueError, match="finite"):
        degree_of_reduction(_formula("NH3"), float("nan"))
