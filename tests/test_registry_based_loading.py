from __future__ import annotations

from types import SimpleNamespace

import pytest

from fungal_model.core.units import Q_
from fungal_model.io import (
    ProductMapRegistry,
    RegistryLookupError,
    SubstrateLoaderRegistry,
    ValidatorRegistry,
    load_geometry,
    load_substrate,
)
from fungal_model.plugins.pet import pet_substrate_loader_registry


def test_default_substrate_registry_loads_generic_non_pet_substrate(tmp_path) -> None:
    config_path = tmp_path / "generic_solid.yml"
    config_path.write_text(
        """
kind: substrate
name: inert solid benchmark
substrate_type: generic_solid
chemical_class: framework benchmark
physical_state: mixed_solid
bond_types:
  - generic_linkage
accessible_bonds:
  - generic_linkage
required_enzyme_classes: []
default_degradation_model: heterogeneous_surface
completeness: partial
provenance:
  source: Generic non-PET loader test fixture.
  measurement_method: defined benchmark metadata
  confidence_level: testing
  notes: Proves substrate loading is registry-based without a PET branch.
  validity_range: toy benchmark only
  units: not_applicable
parameters:
  - name: generic accessible area
    symbol: A_generic
    value: 0.2
    units: meter ** 2
    uncertainty: 0.0
    source: Generic non-PET loader test fixture.
    confidence_level: testing
    notes: Artificial framework value.
    measurement_method: defined benchmark value
    validity_range: toy benchmark only
degradation_products:
  - name: released_generic_product
    formula:
    assimilable:
    notes: No biology is implied.
    source: Generic non-PET loader test fixture.
""".lstrip(),
        encoding="utf-8",
    )

    substrate = load_substrate(config_path)

    assert substrate.name == "inert solid benchmark"
    assert substrate.physical_state == "mixed_solid"
    assert substrate.parameter("A_generic").quantity.to("meter ** 2").magnitude == pytest.approx(0.2)
    assert substrate.degradation_products[0].name == "released_generic_product"


def test_default_substrate_registry_does_not_include_pet_plugin() -> None:
    registry = SubstrateLoaderRegistry.default()
    assert "pet" not in registry.registered_names()


def test_pet_substrate_loader_requires_explicit_plugin_registry() -> None:
    with pytest.raises(RegistryLookupError):
        load_substrate("data/substrates/pet_film.yml")

    substrate = load_substrate(
        "data/substrates/pet_film.yml",
        registry=pet_substrate_loader_registry(),
    )
    assert substrate.name == "polyethylene terephthalate"
    assert substrate.require_accessible_surface_area().to("meter ** 2").magnitude == pytest.approx(0.1)


def test_geometry_loading_uses_registered_loaders() -> None:
    well_mixed = load_geometry("data/geometries/well_mixed_100ml.yml")
    film = load_geometry("data/geometries/pet_film_1d.yml")

    assert well_mixed.geometry_type == "well_mixed"
    assert not well_mixed.is_spatial
    assert film.geometry_type == "film_1d"
    assert film.is_spatial


def test_product_map_registry_uses_configured_state_names() -> None:
    product_map = ProductMapRegistry.default().load(
        {
            "product_map_type": "one_to_one",
            "substrate_state": "solid_substrate_amount",
            "product_state": "released_product_amount",
            "notes": "arbitrary state names",
        }
    )

    assert product_map.reactants == {"solid_substrate_amount": 1.0}
    assert product_map.products == {"released_product_amount": 1.0}


def test_validator_registry_builds_configured_validators() -> None:
    result = SimpleNamespace(
        species={
            "solid_substrate_amount": Q_([1.0, 0.8], "kilogram"),
            "released_product_amount": Q_([0.0, 0.2], "kilogram"),
        }
    )
    registry = ValidatorRegistry.default()
    non_negative = registry.load(
        {
            "validator_type": "non_negative",
            "species": ["solid_substrate_amount", "released_product_amount"],
        }
    )
    mass_balance = registry.load(
        {
            "validator_type": "mass_balance",
            "conserved_weights": {
                "solid_substrate_amount": 1.0,
                "released_product_amount": 1.0,
            },
        }
    )

    assert non_negative(result).passed
    assert mass_balance(result).passed
