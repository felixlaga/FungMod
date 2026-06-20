from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import load_registry
from fungal_model.screening import ModelabilityReport, assess_modelability


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_default_toy_registry_case_is_underparameterized() -> None:
    registry = load_registry(REGISTRY_INDEX)

    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
    )

    assert isinstance(report, ModelabilityReport)
    assert report.status == "underparameterized"
    assert "surface_catalysis" in report.candidate_processes
    assert "k_ads_unknown" in report.required_parameters
    assert _has_item(report.missing, "parameter", "k_ads_unknown")
    assert _has_item(report.uncertain, "parameter", "k_surface_range")
    assert _has_item(report.uncertain, "parameter", "k_surface_prior")


def test_modelability_report_is_json_safe_and_has_summary() -> None:
    registry = load_registry(REGISTRY_INDEX)

    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
    )

    encoded = json.dumps(report.to_dict())

    assert "toy_fungus_alpha" in encoded
    assert report.to_dict()["mode"] == "exploratory"
    assert "underparameterized" in report.summary()


def test_exact_only_case_is_modelable(tmp_path: Path) -> None:
    registry = _registry_with_required_parameters(tmp_path, ["k_surface_exact"])

    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
    )

    assert report.status == "modelable"
    assert _has_item(report.known, "parameter", "k_surface_exact")
    assert not report.uncertain
    assert not report.missing


def test_range_case_is_exploratory(tmp_path: Path) -> None:
    registry = _registry_with_required_parameters(tmp_path, ["k_surface_range"])

    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
        mode="exploratory",
    )

    assert report.status == "exploratory"
    assert _has_item(report.uncertain, "parameter", "k_surface_range")
    assert not report.missing


def test_scientific_mode_marks_uncertain_parameters_incompatible(tmp_path: Path) -> None:
    registry = _registry_with_required_parameters(tmp_path, ["k_surface_range"])

    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
        mode="scientific",
    )

    assert report.status == "underparameterized"
    assert _has_item(report.incompatible, "parameter", "k_surface_range")
    assert not report.uncertain


def test_missing_parameter_case_is_underparameterized(tmp_path: Path) -> None:
    registry = _registry_with_required_parameters(tmp_path, ["k_missing"])

    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
    )

    assert report.status == "underparameterized"
    assert _has_item(report.missing, "parameter", "k_missing")
    assert "Measure or curate k_missing" in report.suggested_experiments[0]


def test_incompatible_enzyme_substrate_case_is_unsupported(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    enzyme_path = registry_dir / "enzymes" / "enzyme_classes.yml"
    data = _yaml_mapping(enzyme_path)
    records = cast(list[dict[str, Any]], data["records"])
    records[0]["compatible_substrate_classes"] = ["other_toy_substrate_class"]
    enzyme_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    registry = load_registry(registry_dir / "registry_index.yml")

    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
    )

    assert report.status == "unsupported"
    assert _has_item(report.incompatible, "enzyme_substrate_match", "toy_cellulase")
    assert not report.candidate_processes


def test_invalid_modelability_mode_fails_clearly() -> None:
    registry = load_registry(REGISTRY_INDEX)

    with pytest.raises(ValueError, match="mode must be one of"):
        assess_modelability(
            fungus_id="toy_fungus_alpha",
            substrate_id="toy_cellulose_like_solid",
            environment_id="toy_lab_environment",
            registry=registry,
            mode="dream",  # type: ignore[arg-type]
        )


def _registry_with_required_parameters(tmp_path: Path, required_parameters: list[str]):
    registry_dir = _copy_registry(tmp_path)
    process_path = registry_dir / "processes" / "process_compatibility.yml"
    data = _yaml_mapping(process_path)
    records = cast(list[dict[str, Any]], data["records"])
    records[0]["required_parameters"] = required_parameters
    records[0]["parameter_roles"] = {"surface_rate_constant": required_parameters[0]} if required_parameters else {}
    process_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_registry(registry_dir / "registry_index.yml")


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _has_item(items, item_type: str, item_id: str) -> bool:
    return any(item.item_type == item_type and item.item_id == item_id for item in items)
