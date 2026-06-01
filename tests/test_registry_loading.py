from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import (
    RegistryLoadError,
    RegistryLookupError,
    RegistryValidationError,
    ValueSpec,
    load_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_load_toy_registry_index() -> None:
    registry = load_registry(REGISTRY_INDEX)

    assert registry.registry_id == "toy_registry"
    assert registry.version == "0.1.0"
    assert registry.maturity == "development"


def test_load_toy_fungus_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    fungus = registry.get_fungus("toy_fungus_alpha")

    assert fungus.name == "Toy fungus alpha"
    assert fungus.enzyme_classes == ("toy_cellulase",)
    assert "not a real fungus" in fungus.notes


def test_load_toy_substrate_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    substrate = registry.get_substrate("toy_cellulose_like_solid")

    assert substrate.substrate_class == "toy_cellulose_like"
    assert substrate.bond_classes == ("toy_beta_1_4_glycosidic",)
    assert isinstance(substrate.properties["accessible_surface_area"], ValueSpec)
    assert substrate.properties["accessible_surface_area"].kind == "range"


def test_load_toy_environment_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    environment = registry.get_environment("toy_lab_environment")

    assert environment.conditions["temperature"].to_quantity().to("kelvin").magnitude == pytest.approx(303.15)
    assert environment.conditions["ph"].kind == "range"
    assert environment.conditions["oxygen_concentration"].kind == "not_applicable"


def test_load_toy_enzyme_class_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    enzyme = registry.get_enzyme_class("toy_cellulase")

    assert enzyme.target_bond_classes == ("toy_beta_1_4_glycosidic",)
    assert enzyme.compatible_substrate_classes == ("toy_cellulose_like",)
    assert enzyme.compatible_processes == ("surface_catalysis",)


def test_load_toy_process_compatibility_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    records = registry.get_process_compatibility(
        enzyme_class="toy_cellulase",
        substrate_class="toy_cellulose_like",
        process_type="surface_catalysis",
    )

    assert len(records) == 1
    assert records[0].product_map_required
    assert "k_surface_exact" in records[0].required_parameters


def test_load_exact_range_distribution_and_unknown_parameter_records() -> None:
    registry = load_registry(REGISTRY_INDEX)

    exact = registry.get_parameter_records(parameter_symbol="k_surface_exact")[0]
    range_record = registry.get_parameter_records(parameter_symbol="k_surface_range")[0]
    distribution = registry.get_parameter_records(parameter_symbol="k_surface_prior")[0]
    unknown = registry.get_parameter_records(parameter_symbol="k_ads_unknown")[0]

    assert exact.value.kind == "exact"
    assert range_record.value.kind == "range"
    assert distribution.value.kind == "distribution"
    assert distribution.value.distribution == "loguniform"
    assert unknown.value.kind == "unknown"


def test_duplicate_record_ids_fail(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    fungi_path = registry_dir / "fungi" / "fungi.yml"
    data = _yaml_mapping(fungi_path)
    records = cast(list[dict[str, Any]], data["records"])
    records.append(dict(records[0]))
    fungi_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(RegistryValidationError, match="Duplicate"):
        load_registry(registry_dir / "registry_index.yml")


def test_unknown_record_id_fails_clearly() -> None:
    registry = load_registry(REGISTRY_INDEX)

    with pytest.raises(RegistryLookupError, match="Unknown fungus"):
        registry.get_fungus("not_present")


def test_missing_referenced_registry_file_fails_clearly(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    index_path = registry_dir / "registry_index.yml"
    data = _yaml_mapping(index_path)
    records = cast(dict[str, Any], data["records"])
    records["fungi"] = "fungi/missing.yml"
    index_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(RegistryLoadError, match="does not exist"):
        load_registry(index_path)


def test_registry_records_are_json_safe() -> None:
    registry = load_registry(REGISTRY_INDEX)

    encoded = json.dumps(registry.to_dict())

    assert "toy_registry" in encoded
    assert "toy_param_k_surface_loguniform" in encoded


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
