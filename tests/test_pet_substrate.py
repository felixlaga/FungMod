from __future__ import annotations

import pytest

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.units import Q_, UnitError
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set


def pet_parameter(
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
        source="Artificial Stage 3 PET metadata test value; no physical claim.",
        confidence_level="testing",
        notes="Used only for substrate metadata tests.",
        measurement_method="defined benchmark value",
    )


def test_default_pet_records_required_identity_and_unknown_parameters() -> None:
    pet = PETSubstrate()

    assert pet.name == "polyethylene terephthalate"
    assert pet.polymer_type == "polyester"
    assert pet.repeating_unit == "C10H8O4"
    assert pet.dominant_cleavable_bond_type == "ester"
    assert pet.physical_state == "solid_polymer"
    assert pet.completeness == "partial"
    assert pet.density.is_unknown
    assert pet.accessible_surface_area() is None
    pet.validate(require_parameter_values=False)


def test_pet_is_surface_limited_by_default_not_dissolved() -> None:
    pet = PETSubstrate(geometry_type="film")

    assert pet.default_degradation_model == "heterogeneous_surface"
    assert pet.uses_surface_degradation_by_default
    assert not pet.is_dissolved_by_default


def test_default_pet_requires_values_before_full_scientific_use() -> None:
    pet = PETSubstrate()

    with pytest.raises(UnknownParameterError):
        pet.validate(require_parameter_values=True)


def test_pet_degradation_products_are_recorded_without_assimilation_claims() -> None:
    pet = PETSubstrate()
    products = {product.name: product for product in pet.degradation_products}

    assert {"MHET", "BHET", "terephthalic acid", "ethylene glycol"} <= set(products)
    assert all(product.assimilable is None for product in products.values())


def test_pet_parameter_units_are_enforced() -> None:
    bad_density = pet_parameter(
        name="bad density",
        symbol="rho_pet",
        value=1.0,
        units="second",
    )

    with pytest.raises(UnitError):
        PETSubstrate(parameters=make_pet_parameter_set([bad_density]))


def test_invalid_crystallinity_is_rejected() -> None:
    bad_crystallinity = pet_parameter(
        name="bad crystallinity",
        symbol="chi_c",
        value=1.2,
        units="dimensionless",
    )

    with pytest.raises(ValueError):
        PETSubstrate(parameters=make_pet_parameter_set([bad_crystallinity]))


def test_accessible_surface_area_can_be_explicit() -> None:
    pet = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                pet_parameter(
                    name="explicit accessible surface area",
                    symbol="A_accessible",
                    value=Q_(250.0, "centimeter ** 2"),
                    units="meter ** 2",
                )
            ]
        )
    )

    area = pet.require_accessible_surface_area()

    assert area.to("meter ** 2").magnitude == pytest.approx(0.025)


def test_accessible_surface_area_derives_from_surface_roughness_and_amorphous_fraction() -> None:
    pet = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                pet_parameter(
                    name="geometric surface area",
                    symbol="A_surface",
                    value=2.0,
                    units="meter ** 2",
                ),
                pet_parameter(
                    name="roughness factor",
                    symbol="r_rough",
                    value=1.5,
                    units="dimensionless",
                ),
                pet_parameter(
                    name="amorphous fraction",
                    symbol="phi_amorphous",
                    value=0.4,
                    units="dimensionless",
                ),
            ]
        )
    )

    area = pet.require_accessible_surface_area()

    assert area.to("meter ** 2").magnitude == pytest.approx(1.2)


def test_amorphous_fraction_can_be_derived_from_crystallinity_when_not_overridden() -> None:
    pet = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                pet_parameter(
                    name="geometric surface area",
                    symbol="A_surface",
                    value=2.0,
                    units="meter ** 2",
                ),
                pet_parameter(
                    name="roughness factor",
                    symbol="r_rough",
                    value=1.0,
                    units="dimensionless",
                ),
                pet_parameter(
                    name="crystallinity",
                    symbol="chi_c",
                    value=0.25,
                    units="dimensionless",
                ),
            ]
        )
    )

    amorphous = pet.effective_amorphous_fraction()
    area = pet.require_accessible_surface_area()

    assert amorphous is not None
    assert amorphous.to("dimensionless").magnitude == pytest.approx(0.75)
    assert area.to("meter ** 2").magnitude == pytest.approx(1.5)


def test_roughness_factor_cannot_be_below_definition_limit() -> None:
    roughness = pet_parameter(
        name="invalid roughness",
        symbol="r_rough",
        value=0.5,
        units="dimensionless",
    )

    with pytest.raises(ValueError):
        PETSubstrate(parameters=make_pet_parameter_set([roughness]))

