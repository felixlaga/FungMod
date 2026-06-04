from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.io.model_config import ModelConfig
from fungal_model.registry import load_registry
from fungal_model.screening import (
    RegistryCaseBuildError,
    build_model_config_from_registry_case,
)
from fungal_model.screening.case_builder import get_registry_process_assembler
from fungal_model.workflows import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_default_underparameterized_registry_case_is_not_built() -> None:
    registry = load_registry(REGISTRY_INDEX)

    with pytest.raises(RegistryCaseBuildError, match="modelability status"):
        build_model_config_from_registry_case(
            fungus_id="toy_fungus_alpha",
            substrate_id="toy_cellulose_like_solid",
            environment_id="toy_lab_environment",
            registry=registry,
        )


def test_build_model_config_from_modelable_toy_registry_case(tmp_path: Path) -> None:
    registry = _modelable_registry(tmp_path)

    config = build_model_config_from_registry_case(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
        output_directory=str(tmp_path / "outputs"),
    )

    assert isinstance(config, ModelConfig)
    assert config.mode == "toy"
    assert config.maturity == "framework_benchmark"
    assert config.validate().passed
    process = config.processes[0]
    assert process.process_type == "surface_catalysis"
    assert process.parameters["surface_rate_constant"] == "k_surface_exact"
    assert process.parameters["adsorption_constant"] == "k_ads_exact"
    assert process.parameters["accessible_surface_area"] == "A_surface_exact"


def test_built_registry_case_runs_through_configured_workflow(tmp_path: Path) -> None:
    registry = _modelable_registry(tmp_path)
    config = build_model_config_from_registry_case(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
        output_directory=str(tmp_path / "outputs"),
    )
    config_path = tmp_path / "registry_case.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")

    result = run_configured_model(config_path, output_dir=tmp_path / "run_bundle")

    substrate = result.state("solid_substrate_amount").to("kilogram").magnitude
    product = result.state("released_product_amount").to("kilogram").magnitude
    assert substrate[-1] < substrate[0]
    assert product[-1] > product[0]
    assert (tmp_path / "run_bundle" / "record.json").exists()


def test_builder_rejects_missing_surface_parameter_role(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _set_process_parameters(
        registry_dir,
        required_parameters=["k_surface_exact", "k_ads_exact", "A_surface_exact"],
        parameter_roles={
            "surface_rate_constant": "k_surface_exact",
            "adsorption_constant": "k_ads_exact",
        },
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="accessible_surface_area"):
        build_model_config_from_registry_case(
            fungus_id="toy_fungus_alpha",
            substrate_id="toy_cellulose_like_solid",
            environment_id="toy_lab_environment",
            registry=registry,
        )


def test_builder_rejects_uncertain_parameter_case(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _set_process_parameters(
        registry_dir,
        required_parameters=["k_surface_range", "k_ads_exact", "A_surface_exact"],
        parameter_roles={
            "surface_rate_constant": "k_surface_range",
            "adsorption_constant": "k_ads_exact",
            "accessible_surface_area": "A_surface_exact",
        },
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="modelability status"):
        build_model_config_from_registry_case(
            fungus_id="toy_fungus_alpha",
            substrate_id="toy_cellulose_like_solid",
            environment_id="toy_lab_environment",
            registry=registry,
        )


def test_builder_currently_emits_toy_configs_only(tmp_path: Path) -> None:
    registry = _modelable_registry(tmp_path)

    with pytest.raises(RegistryCaseBuildError, match="only emits toy"):
        build_model_config_from_registry_case(
            fungus_id="toy_fungus_alpha",
            substrate_id="toy_cellulose_like_solid",
            environment_id="toy_lab_environment",
            registry=registry,
            mode="scientific",  # type: ignore[arg-type]
        )


def test_registry_process_assemblers_advertise_supported_roles() -> None:
    surface = get_registry_process_assembler("surface_catalysis")
    homogeneous = get_registry_process_assembler("homogeneous_michaelis_menten")

    assert surface is not None
    assert surface.required_parameter_roles == (
        "surface_rate_constant",
        "adsorption_constant",
        "accessible_surface_area",
    )
    assert surface.deterministic_mode == "toy"
    assert homogeneous is not None
    assert homogeneous.required_parameter_roles == (
        "km",
        "kcat",
        "substrate_initial_concentration",
        "enzyme_initial_concentration",
    )
    assert homogeneous.deterministic_mode == "scientific"
    assert get_registry_process_assembler("unsupported_process") is None


def test_ensemble_uses_registry_process_assembler_api() -> None:
    source = (ROOT / "src" / "fungal_model" / "screening" / "ensemble.py").read_text(
        encoding="utf-8"
    )

    assert "_surface_catalysis_config_data" not in source
    assert "_homogeneous_mm_config_data" not in source
    assert "_select_compatibility" not in source
    assert "get_registry_process_assembler" in source
    assert "build_registry_process_config_data" in source


def _modelable_registry(tmp_path: Path):
    registry_dir = _copy_registry(tmp_path)
    _set_process_parameters(
        registry_dir,
        required_parameters=["k_surface_exact", "k_ads_exact", "A_surface_exact"],
        parameter_roles={
            "surface_rate_constant": "k_surface_exact",
            "adsorption_constant": "k_ads_exact",
            "accessible_surface_area": "A_surface_exact",
        },
    )
    return load_registry(registry_dir / "registry_index.yml")


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _set_process_parameters(
    registry_dir: Path,
    *,
    required_parameters: list[str],
    parameter_roles: dict[str, str],
) -> None:
    process_path = registry_dir / "processes" / "process_compatibility.yml"
    data = _yaml_mapping(process_path)
    records = cast(list[dict[str, Any]], data["records"])
    records[0]["required_parameters"] = required_parameters
    records[0]["parameter_roles"] = parameter_roles
    process_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
