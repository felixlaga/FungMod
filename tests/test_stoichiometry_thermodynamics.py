from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry.stoichiometry import (
    CarbonContent,
    ElementalComposition,
    OxygenDemand,
    StoichiometricReactionMetadata,
    StoichiometricTerm,
)
from fungal_model.chemistry.thermodynamics import GibbsFreeEnergyEstimate
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError
from fungal_model.core.units import Q_
from fungal_model.core.validators import (
    validate_biomass_yield_limit,
    validate_carbon_conservation,
    validate_oxygen_limitation,
)


def parameter(
    *,
    name: str,
    symbol: str,
    value,
    units: str,
) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source="Artificial Stage 7 stoichiometry/thermodynamics benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only for validating Stage 7 bookkeeping.",
        measurement_method="defined benchmark value",
    )


class FakeResult:
    def __init__(self, species):
        self.species = species


def carbon_fraction(species: str, value: float | None) -> CarbonContent:
    return CarbonContent(
        species=species,
        carbon_fraction=parameter(
            name=f"{species} carbon fraction",
            symbol=f"fC_{species}",
            value=value,
            units="dimensionless",
        ),
    )


def test_formula_parser_records_element_counts() -> None:
    composition = ElementalComposition.from_formula(
        "C10H8O4",
        source="Artificial Stage 7 PET repeating-unit formula test.",
    )

    assert composition.elements["C"] == pytest.approx(10.0)
    assert composition.elements["H"] == pytest.approx(8.0)
    assert composition.elements["O"] == pytest.approx(4.0)


def test_stoichiometric_reaction_metadata_detects_balanced_reaction() -> None:
    reaction = StoichiometricReactionMetadata(
        name="carbon oxidation",
        reactants=(
            StoichiometricTerm(
                species="C",
                coefficient=1.0,
                composition=ElementalComposition.from_formula(
                    "C",
                    source="Artificial Stage 7 elemental carbon test.",
                ),
            ),
            StoichiometricTerm(
                species="O2",
                coefficient=1.0,
                composition=ElementalComposition.from_formula(
                    "O2",
                    source="Artificial Stage 7 oxygen test.",
                ),
            ),
        ),
        products=(
            StoichiometricTerm(
                species="CO2",
                coefficient=1.0,
                composition=ElementalComposition.from_formula(
                    "CO2",
                    source="Artificial Stage 7 carbon dioxide test.",
                ),
            ),
        ),
        source="Artificial Stage 7 balanced stoichiometry test.",
    )

    assert reaction.is_element_balanced()
    assert reaction.element_balance()["C"] == pytest.approx(0.0)


def test_stoichiometric_reaction_metadata_detects_unbalanced_reaction() -> None:
    reaction = StoichiometricReactionMetadata(
        name="unbalanced oxygen",
        reactants=(
            StoichiometricTerm(
                species="O2",
                coefficient=1.0,
                composition=ElementalComposition.from_formula(
                    "O2",
                    source="Artificial Stage 7 oxygen test.",
                ),
            ),
        ),
        products=(
            StoichiometricTerm(
                species="O",
                coefficient=1.0,
                composition=ElementalComposition.from_formula(
                    "O",
                    source="Artificial Stage 7 oxygen atom test.",
                ),
            ),
        ),
        source="Artificial Stage 7 unbalanced stoichiometry test.",
    )

    assert not reaction.is_element_balanced()


def test_gibbs_free_energy_requires_provenance() -> None:
    estimate = GibbsFreeEnergyEstimate(
        reaction_name="unknown reaction",
        delta_gibbs=Parameter(
            name="unsourced Gibbs estimate",
            symbol="dG",
            value=-10.0,
            units="kilojoule / mole",
            uncertainty=None,
            source=None,
            confidence_level="unknown",
            notes="Deliberately unsourced.",
            measurement_method=None,
        ),
        source=None,
    )

    with pytest.raises(ProvenanceError):
        estimate.validate()


def test_gibbs_free_energy_reports_exergonic_when_known() -> None:
    estimate = GibbsFreeEnergyEstimate(
        reaction_name="benchmark reaction",
        delta_gibbs=parameter(
            name="benchmark Gibbs estimate",
            symbol="dG",
            value=-10.0,
            units="kilojoule / mole",
        ),
        source="Artificial Stage 7 Gibbs estimate test.",
    )

    estimate.validate(require_value=True)
    assert estimate.value().to("kilojoule / mole").magnitude == pytest.approx(-10.0)
    assert estimate.is_exergonic() is True


def test_unknown_carbon_fraction_is_explicit() -> None:
    content = carbon_fraction("biomass", None)

    with pytest.raises(UnknownParameterError):
        content.carbon_mass(Q_(1.0, "kilogram"))


def test_carbon_conservation_passes_for_carbon_transfer() -> None:
    result = FakeResult(
        {
            "PET": Q_(np.array([1.0, 0.5]), "kilogram"),
            "hydrolysate": Q_(np.array([0.0, 0.5]), "kilogram"),
        }
    )

    validation = validate_carbon_conservation(
        result,
        carbon_contents=[
            carbon_fraction("PET", 0.6),
            carbon_fraction("hydrolysate", 0.6),
        ],
    )

    assert validation.passed


def test_carbon_conservation_fails_for_biomass_from_nowhere() -> None:
    result = FakeResult(
        {
            "hydrolysate": Q_(np.array([0.0, 0.0]), "kilogram"),
            "B_active": Q_(np.array([1.0, 2.0]), "kilogram"),
        }
    )

    validation = validate_carbon_conservation(
        result,
        carbon_contents=[
            carbon_fraction("hydrolysate", 0.6),
            carbon_fraction("B_active", 0.5),
        ],
    )

    assert not validation.passed
    assert validation.details["excess_carbon"] > 0.0


def test_oxygen_limitation_passes_when_available_oxygen_is_sufficient() -> None:
    result = FakeResult({"PET": Q_(np.array([1.0, 0.8]), "kilogram")})
    demand = OxygenDemand(
        process_name="aerobic benchmark",
        substrate_species="PET",
        oxygen_per_substrate=parameter(
            name="oxygen demand",
            symbol="O2_per_PET",
            value=0.5,
            units="kilogram / kilogram",
        ),
    )

    validation = validate_oxygen_limitation(
        result,
        oxygen_demand=demand,
        oxygen_available=Q_(0.2, "kilogram"),
    )

    assert validation.passed


def test_oxygen_limitation_fails_when_available_oxygen_is_insufficient() -> None:
    result = FakeResult({"PET": Q_(np.array([1.0, 0.8]), "kilogram")})
    demand = OxygenDemand(
        process_name="aerobic benchmark",
        substrate_species="PET",
        oxygen_per_substrate=parameter(
            name="oxygen demand",
            symbol="O2_per_PET",
            value=1.0,
            units="kilogram / kilogram",
        ),
    )

    validation = validate_oxygen_limitation(
        result,
        oxygen_demand=demand,
        oxygen_available=Q_(0.1, "kilogram"),
    )

    assert not validation.passed
    assert validation.details["oxygen_deficit"] > 0.0


def test_biomass_yield_limit_passes_within_configured_maximum() -> None:
    validation = validate_biomass_yield_limit(
        yield_parameter=parameter(
            name="configured yield",
            symbol="Y_B",
            value=0.4,
            units="dimensionless",
        ),
        maximum_yield_parameter=parameter(
            name="maximum theoretical yield",
            symbol="Y_max",
            value=0.6,
            units="dimensionless",
        ),
    )

    assert validation.passed


def test_biomass_yield_limit_fails_above_configured_maximum() -> None:
    validation = validate_biomass_yield_limit(
        yield_parameter=parameter(
            name="configured yield",
            symbol="Y_B",
            value=0.8,
            units="dimensionless",
        ),
        maximum_yield_parameter=parameter(
            name="maximum theoretical yield",
            symbol="Y_max",
            value=0.6,
            units="dimensionless",
        ),
    )

    assert not validation.passed

