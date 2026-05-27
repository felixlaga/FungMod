from __future__ import annotations

from pathlib import Path

import pytest

from fungal_model.core.units import UnitError
from fungal_model.io import (
    SchemaValidationError,
    load_enzyme,
    load_environment,
    load_fungus,
    load_geometry,
    load_parameter_set,
    load_substrate,
    load_yaml_config,
    validate_config,
)
from fungal_model.plugins.pet import pet_substrate_loader_registry


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_all_example_yaml_configs_pass_minimal_schema() -> None:
    paths = sorted(DATA.glob("*/*.yml"))
    assert paths
    for path in paths:
        config = load_yaml_config(path)
        result = validate_config(config)
        assert result.passed, path


def test_schema_validation_fails_when_provenance_is_missing() -> None:
    with pytest.raises(SchemaValidationError):
        validate_config({"kind": "environment", "name": "bad config"})


def test_schema_validation_fails_for_bad_units() -> None:
    config = load_yaml_config(DATA / "environments" / "lab_30C_pH7.yml")
    config["parameters"] = [
        {
            "name": "bad units",
            "symbol": "bad",
            "value": 1.0,
            "units": "definitely not a unit",
            "source": "test",
            "confidence_level": "testing",
            "notes": "bad unit test",
            "measurement_method": "test",
            "validity_range": "test",
        }
    ]
    with pytest.raises(UnitError):
        validate_config(config)


def test_parameter_set_loader_preserves_units_and_values() -> None:
    parameters = load_parameter_set(DATA / "parameters" / "pet_surface_benchmark.yml")

    assert parameters.get("K_ads").quantity.to("liter / mole").magnitude == pytest.approx(1.0)
    assert parameters.get("k_surface").quantity.to("kilogram / meter ** 2 / second").magnitude == pytest.approx(1.0e-6)


def test_substrate_loader_keeps_unknown_values_unknown() -> None:
    substrate = load_substrate(
        DATA / "substrates" / "pet_film.yml",
        registry=pet_substrate_loader_registry(),
    )

    assert substrate.require_accessible_surface_area().to("meter ** 2").magnitude == pytest.approx(0.1)
    assert substrate.parameters.get("rho_pet").is_unknown


def test_entity_loaders_create_environment_enzyme_geometry_and_fungus() -> None:
    environment = load_environment(DATA / "environments" / "lab_30C_pH7.yml")
    enzyme = load_enzyme(DATA / "enzymes" / "petase_like.yml")
    well_mixed = load_geometry(DATA / "geometries" / "well_mixed_100ml.yml")
    film = load_geometry(DATA / "geometries" / "pet_film_1d.yml")
    fungus = load_fungus(DATA / "fungi" / "toy_pet_fungus.yml")
    substrate = load_substrate(
        DATA / "substrates" / "pet_film.yml",
        registry=pet_substrate_loader_registry(),
    )

    assert environment.require_temperature().to("kelvin").magnitude == pytest.approx(303.15)
    assert enzyme.compatible_with_substrate(substrate, bond_type="ester")
    assert well_mixed.geometry_type == "well_mixed"
    assert film.is_spatial
    assert fungus.enzyme_profile.compatible_capabilities(
        substrate_name="polyethylene terephthalate",
        bond_type="ester",
        enzyme_class="PETase-like hydrolase",
    )
