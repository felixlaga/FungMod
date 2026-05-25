from __future__ import annotations

import pytest

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.units import UnitError
from fungal_model.substrates import (
    CelluloseSubstrate,
    ChitinSubstrate,
    LigninSubstrate,
    PETSubstrate,
    StarchSubstrate,
    make_cellulose_parameter_set,
    make_starch_parameter_set,
)


def substrate_parameter(
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
        source="Artificial Stage 9 universal-substrate metadata test value; no physical claim.",
        confidence_level="testing",
        notes="Used only to verify unit/provenance handling.",
        measurement_method="defined benchmark value",
    )


def placeholder_substrates():
    return [
        CelluloseSubstrate(),
        LigninSubstrate(),
        StarchSubstrate(),
        ChitinSubstrate(),
    ]


def test_stage9_substrates_are_explicit_placeholders() -> None:
    for substrate in placeholder_substrates():
        assert substrate.completeness == "placeholder"
        assert substrate.default_degradation_model == "unknown"
        assert substrate.water_activity_dependence.startswith("unknown")
        assert substrate.thermodynamic_data == ()
        assert len(substrate.parameters.missing_values()) > 0
        substrate.validate(require_parameter_values=False)

        with pytest.raises(UnknownParameterError):
            substrate.validate(require_parameter_values=True)


def test_stage9_product_assimilation_is_not_assumed() -> None:
    for substrate in placeholder_substrates():
        assert len(substrate.degradation_products) > 0
        assert all(product.assimilable is None for product in substrate.degradation_products)
        assert all(product.source for product in substrate.degradation_products)


def test_stage9_substrates_record_required_bond_and_enzyme_metadata() -> None:
    cellulose = CelluloseSubstrate()
    lignin = LigninSubstrate()
    starch = StarchSubstrate()
    chitin = ChitinSubstrate()

    assert "beta-1,4-glycosidic" in cellulose.bond_types
    assert "endoglucanase" in cellulose.required_enzyme_classes
    assert "beta-O-4 aryl ether" in lignin.bond_types
    assert "laccase" in lignin.required_enzyme_classes
    assert "alpha-1,6-glycosidic" in starch.bond_types
    assert "alpha-amylase" in starch.required_enzyme_classes
    assert "N-acetylglucosaminidase" in chitin.required_enzyme_classes


def test_pet_remains_partial_surface_substrate() -> None:
    pet = PETSubstrate()
    data = pet.to_dict()

    assert pet.completeness == "partial"
    assert pet.default_degradation_model == "heterogeneous_surface"
    assert data["water_activity_dependence"] == "unknown"
    assert data["thermodynamic_data"] == []


def test_universal_substrate_to_dict_exports_completeness_and_parameters() -> None:
    substrate = ChitinSubstrate()
    data = substrate.to_dict()

    assert data["name"] == "chitin"
    assert data["completeness"] == "placeholder"
    assert data["default_degradation_model"] == "unknown"
    assert data["water_activity_dependence"].startswith("unknown")
    assert data["parameters"]["parameters"]
    assert data["degradation_products"]


def test_parameter_override_units_are_enforced() -> None:
    bad_density = substrate_parameter(
        name="bad cellulose density",
        symbol="rho_cellulose",
        value=1.0,
        units="second",
    )

    with pytest.raises(UnitError):
        CelluloseSubstrate(parameters=make_cellulose_parameter_set([bad_density]))


def test_sourced_parameter_override_is_preserved_without_completing_stage() -> None:
    density = substrate_parameter(
        name="benchmark starch density",
        symbol="rho_starch",
        value=1.0,
        units="kilogram / meter ** 3",
    )

    starch = StarchSubstrate(parameters=make_starch_parameter_set([density]))

    assert not starch.density.is_unknown
    assert starch.completeness == "placeholder"
    assert len(starch.parameters.missing_values()) > 0
    with pytest.raises(UnknownParameterError):
        starch.validate(require_parameter_values=True)


def test_lignin_ordered_fraction_is_not_treated_as_simple_crystallinity_claim() -> None:
    lignin = LigninSubstrate()

    assert lignin.ordered_fraction.symbol == "chi_order_lignin"
    assert "not treated as a simple crystalline polymer" in lignin.ordered_fraction.notes
