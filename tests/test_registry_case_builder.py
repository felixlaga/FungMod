from __future__ import annotations

import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.io.model_config import ModelConfig
from fungal_model.registry import load_registry
from fungal_model.registry.records import PARAMETER_ALLOWED_USE_STORAGE_ONLY
from fungal_model.screening import (
    RegistryCaseBuildError,
    assess_modelability,
    build_model_config_from_registry_case,
)
from fungal_model.screening.case_builder import get_registry_process_assembler
from fungal_model.workflows import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
CHAIN_TEMPLATE_ID = "bio002_extracellular_enzyme_chain_template"


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


def test_scientific_builder_rejects_toy_scientific_inputs(tmp_path: Path) -> None:
    registry = _modelable_registry(tmp_path)

    with pytest.raises(RegistryCaseBuildError, match="toy or synthetic"):
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


def test_real_case001_preflight_and_deterministic_build_use_explicit_template_records() -> None:
    registry = load_registry(REGISTRY_INDEX)
    report = assess_modelability(
        fungus_id="generic_cellulase_source",
        substrate_id="cellulose_film_generic",
        environment_id="sabiork_reaction_618_selected_conditions",
        registry=registry,
        mode="toy",
    )
    assert report.status == "modelable"

    config = build_model_config_from_registry_case(
        fungus_id="generic_cellulase_source",
        substrate_id="cellulose_film_generic",
        environment_id="sabiork_reaction_618_selected_conditions",
        registry=registry,
        mode="toy",
    )

    assert config.raw["provenance"]["parameter_record_ids"] == {
        "solid_substrate_initial_concentration": "bio002_initial_solid_cellulose_equivalent_concentration",
        "cellulase_initial_concentration": "bio002_cellulase_initial_concentration",
        "beta_glucosidase_initial_concentration": "bio002_beta_glucosidase_initial_concentration",
        "surface_rate_constant": "bio002_cellulose_to_cellobiose_surface_rate",
        "adsorption_constant": "bio002_cellulase_adsorption_constant",
        "accessible_surface_area": "bio002_cellulose_accessible_surface_area",
        "km": "sabiork_reaction_618_Km_cellobiose",
        "kcat": "sabiork_reaction_618_kcat_cellobiose",
    }


@pytest.mark.parametrize(
    ("malformation", "message"),
    [
        ("not_a_mapping", "modelability status"),
        ("missing_record", "modelability status"),
        ("symbol_mismatch", "modelability status"),
        ("process_mismatch", "requires process_type"),
        ("missing_role_process", "must define one process_type"),
        ("ambiguous_role_process", "multiple process types"),
        ("fungus_mismatch", "not requested fungus"),
        ("substrate_mismatch", "not requested substrate"),
        ("component_fungus_mismatch", "does not provide enzyme class"),
        ("component_substrate_mismatch", "does not have class"),
        ("environment_mismatch", "modelability status"),
        ("unauthorized", "storage-only"),
        ("mode_ineligible", "exploratory-prior"),
    ],
)
def test_case001_explicit_template_mapping_fails_closed(
    malformation: str,
    message: str,
) -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    record_ids = deepcopy(dict(metadata["parameter_record_ids"]))
    metadata["parameter_record_ids"] = record_ids
    surface_role = "surface_rate_constant"
    surface_id = "bio002_cellulose_to_cellobiose_surface_rate"
    kcat_id = "sabiork_reaction_618_kcat_cellobiose"

    if malformation == "not_a_mapping":
        metadata["parameter_record_ids"] = []
    elif malformation == "missing_record":
        record_ids[surface_role] = "missing_explicit_surface_parameter"
    elif malformation == "symbol_mismatch":
        record_ids[surface_role] = "bio002_cellulase_adsorption_constant"
    elif malformation == "process_mismatch":
        registry.parameters[surface_id] = replace(
            registry.parameters[surface_id],
            process_type="homogeneous_michaelis_menten",
        )
    elif malformation == "missing_role_process":
        role_process_types = deepcopy(dict(metadata["parameter_role_process_types"]))
        role_process_types.pop(surface_role)
        metadata["parameter_role_process_types"] = role_process_types
    elif malformation == "ambiguous_role_process":
        process_templates = deepcopy(list(metadata["process_templates"]))
        process_templates[1]["parameter_roles"]["conflicting_surface_rate"] = surface_role
        metadata["process_templates"] = process_templates
    elif malformation == "fungus_mismatch":
        registry.parameters[surface_id] = replace(
            registry.parameters[surface_id],
            fungus_id="toy_fungus_alpha",
        )
    elif malformation == "substrate_mismatch":
        registry.parameters[surface_id] = replace(
            registry.parameters[surface_id],
            substrate_id="toy_cellulose_like_solid",
        )
    elif malformation == "component_fungus_mismatch":
        registry.parameters[kcat_id] = replace(
            registry.parameters[kcat_id],
            fungus_id="toy_fungus_alpha",
        )
    elif malformation == "component_substrate_mismatch":
        registry.parameters[kcat_id] = replace(
            registry.parameters[kcat_id],
            substrate_id="toy_cellulose_like_solid",
        )
    elif malformation == "environment_mismatch":
        original = registry.parameters[surface_id]
        probe_id = "wrong_environment_explicit_surface_parameter"
        registry.parameters[probe_id] = replace(
            original,
            record_id=probe_id,
            environment_id="toy_lab_environment",
        )
        record_ids[surface_role] = probe_id
    elif malformation == "unauthorized":
        original = registry.parameters[surface_id]
        probe_id = "unauthorized_explicit_surface_parameter"
        registry.parameters[probe_id] = replace(
            original,
            record_id=probe_id,
            allowed_use=PARAMETER_ALLOWED_USE_STORAGE_ONLY,
        )
        record_ids[surface_role] = probe_id
    else:
        metadata["config_mode"] = "scientific"
    registry.case_templates[CHAIN_TEMPLATE_ID] = replace(
        template,
        process_state_metadata=metadata,
    )

    with pytest.raises(RegistryCaseBuildError, match=message):
        build_model_config_from_registry_case(
            fungus_id="generic_cellulase_source",
            substrate_id="cellulose_film_generic",
            environment_id="sabiork_reaction_618_selected_conditions",
            registry=registry,
            mode="toy",
        )


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
