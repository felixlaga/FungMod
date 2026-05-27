from __future__ import annotations

from pathlib import Path

import pytest

from fungal_model import load_model_config, load_product_map
from fungal_model.io import ProductMapRegistry


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_MAPS = ROOT / "data" / "product_maps"
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_product_map_configs_load_from_files() -> None:
    dummy = load_product_map(PRODUCT_MAPS / "toy_surface_dummy_mass_equivalent.yml")
    plugin = load_product_map(PRODUCT_MAPS / "toy_surface_plugin_mass_equivalent.yml")

    assert dummy.name == "toy dummy surface mass-equivalent release map"
    assert dummy.maturity == "framework_benchmark"
    assert dummy.reactants == {"solid_substrate_amount": 1.0}
    assert dummy.products == {"released_product_amount": 1.0}
    assert dummy.validate_weight_conservation(
        {"solid_substrate_amount": 1.0, "released_product_amount": 1.0}
    )

    assert plugin.name == "toy plugin surface mass-equivalent release map"
    assert plugin.reactants == {"solid_polymer_amount": 1.0}
    assert plugin.products == {"released_product_amount": 1.0}


def test_product_map_registry_uses_arbitrary_state_names() -> None:
    product_map = ProductMapRegistry.default().load(
        {
            "kind": "product_map",
            "name": "arbitrary names",
            "product_map_type": "one_to_one",
            "maturity": "framework_benchmark",
            "substrate_state": "custom_solid_pool",
            "product_state": "custom_released_pool",
            "provenance": {
                "source": "test",
            },
        }
    )

    assert product_map.reactants == {"custom_solid_pool": 1.0}
    assert product_map.products == {"custom_released_pool": 1.0}
    assert product_map.source == "test"


def test_surface_model_configs_reference_product_map_files() -> None:
    plugin = load_model_config(MODEL_CONFIGS / "toy_surface_pet_plugin.yml")
    dummy = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")

    assert plugin.entities.product_maps[0].path == "data/product_maps/toy_surface_plugin_mass_equivalent.yml"
    assert dummy.entities.product_maps[0].path == "data/product_maps/toy_surface_dummy_mass_equivalent.yml"
    assert plugin.entities.product_maps[0].data is None
    assert dummy.entities.product_maps[0].data is None


def test_product_map_config_fails_for_unknown_type(tmp_path) -> None:
    path = tmp_path / "bad_product_map.yml"
    path.write_text(
        """
kind: product_map
name: bad product map
product_map_type: unknown_map
maturity: framework_benchmark
provenance:
  source: test
  measurement_method: test
  confidence_level: testing
  notes: bad test map
  validity_range: test
  units: not_applicable
substrate_state: a
product_state: b
parameters: []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported product map"):
        load_product_map(path)
