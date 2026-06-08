from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import RegistryLoadError, RegistryValidationError, load_registry
from fungal_model.screening.case_builder import (
    RegistryCaseBuildError,
    get_registry_process_assembler,
    select_registry_case_template,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_reaction_618_template_loads_and_validates() -> None:
    registry = load_registry(REGISTRY_INDEX)

    template = registry.get_case_template("sabiork_reaction_618_homogeneous_mm_template")

    assert template.validate().passed
    assert template.process_type == "homogeneous_michaelis_menten"
    assert template.state_roles == {
        "substrate": "cellobiose_concentration",
        "product": "beta_D_glucose_concentration",
        "enzyme": "beta_glucosidase_concentration",
    }
    assert template.product_map["product_map_type"] == "stoichiometric"
    assert template.stoichiometric_yields["product"] == pytest.approx(2.0)
    assert template.time_grid == {"start": 0.0, "stop": 1000.0, "points": 101, "units": "second"}
    assert "Template metadata does not resolve" in template.validity_notes[0]


def test_bio001_template_loads_and_validates() -> None:
    registry = load_registry(REGISTRY_INDEX)

    template = registry.get_case_template("bio001_cellulose_surface_catalysis_template")

    assert template.validate().passed
    assert template.process_type == "surface_catalysis"
    assert template.state_roles["substrate"] == "solid_substrate_remaining"
    assert template.state_roles["product"] == "soluble_product_amount"
    assert template.state_roles["catalyst"] == "free_enzyme_concentration"
    assert template.state_roles["accessibility_proxy"] == "accessible_site_fraction_remaining_proxy"
    assert template.product_map["product_map_type"] == "one_to_one"
    assert template.time_grid == {"start": 0.0, "stop": 4000.0, "points": 81, "units": "second"}


def test_missing_template_fails_clearly() -> None:
    registry = load_registry(REGISTRY_INDEX)
    compatibility = registry.get_process_compatibility(
        enzyme_class="beta_glucosidase",
        substrate_class="cellobiose",
        process_type="homogeneous_michaelis_menten",
    )[0]

    with pytest.raises(RegistryCaseBuildError, match="missing case template"):
        select_registry_case_template(
            registry=registry,
            compatibility=replace(compatibility, case_template_id="not_a_template"),
        )


def test_invalid_process_type_mismatch_fails_clearly(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _update_template(
        registry_dir,
        "sabiork_reaction_618_homogeneous_mm_template",
        lambda record: record.update({"process_type": "surface_catalysis"}),
    )
    registry = load_registry(registry_dir / "registry_index.yml")
    compatibility = registry.get_process_compatibility(
        enzyme_class="beta_glucosidase",
        substrate_class="cellobiose",
        process_type="homogeneous_michaelis_menten",
    )[0]

    with pytest.raises(RegistryCaseBuildError, match="process_type mismatch"):
        select_registry_case_template(
            registry=registry,
            compatibility=compatibility,
            assembler=get_registry_process_assembler(compatibility.process_type),
        )


def test_invalid_state_role_fails_clearly(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _update_template(
        registry_dir,
        "bio001_cellulose_surface_catalysis_template",
        lambda record: record["state_roles"].update({"invented_role": "made_up_state"}),
    )

    with pytest.raises(RegistryValidationError, match="state_roles.invented_role"):
        load_registry(registry_dir / "registry_index.yml")


def test_invalid_time_grid_fails_clearly(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _update_template(
        registry_dir,
        "bio001_cellulose_surface_catalysis_template",
        lambda record: record["time_grid"].update({"points": 1}),
    )

    with pytest.raises(RegistryValidationError, match="time_grid.points"):
        load_registry(registry_dir / "registry_index.yml")


def test_invalid_product_map_fails_clearly(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _update_template(
        registry_dir,
        "sabiork_reaction_618_homogeneous_mm_template",
        lambda record: record["product_map"].pop("product_state_role"),
    )

    with pytest.raises(RegistryValidationError, match="product_map.product_state_role"):
        load_registry(registry_dir / "registry_index.yml")


def test_unsupported_case_template_field_fails_clearly(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _update_template(
        registry_dir,
        "sabiork_reaction_618_homogeneous_mm_template",
        lambda record: record.update({"surprise_field": "not allowed"}),
    )

    with pytest.raises(RegistryLoadError, match="Unsupported case_template field"):
        load_registry(registry_dir / "registry_index.yml")


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _update_template(registry_dir: Path, template_id: str, update: Any) -> None:
    path = registry_dir / "case_templates" / "case_templates.yml"
    data = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], data["records"])
    for record in records:
        if record["record_id"] == template_id:
            update(record)
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            return
    raise AssertionError(f"Missing template {template_id!r}")


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
