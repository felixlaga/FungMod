from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import load_registry
from fungal_model.screening import RegistryScreenResult, RegistryScreenSimulationError, simulate_screen


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_simulate_screen_runs_exploratory_range_case(tmp_path: Path) -> None:
    registry = _registry_with_surface_parameter(tmp_path, "k_surface_range")

    result = simulate_screen(
        fungus_ids=["toy_fungus_alpha"],
        substrate_ids=["toy_cellulose_like_solid"],
        environment_ids=["toy_lab_environment"],
        registry=registry,
        n_samples=3,
        seed=42,
        output_dir=tmp_path / "screen",
    )

    assert isinstance(result, RegistryScreenResult)
    case = result.case_results[0]
    assert case.modelability_report.status == "exploratory"
    assert len(case.samples) == 3
    values = [sample.parameters["surface_rate_constant"]["value"] for sample in case.samples]
    assert all(1.0e-9 <= float(value) <= 1.0e-6 for value in values)
    assert len(set(values)) == 3
    assert (tmp_path / "screen" / "screen_summary.json").exists()
    assert (Path(case.samples[0].config_path)).exists()
    assert (Path(case.samples[0].output_directory) / "record.json").exists()


def test_simulate_screen_samples_loguniform_distribution(tmp_path: Path) -> None:
    registry = _registry_with_surface_parameter(tmp_path, "k_surface_prior")

    result = simulate_screen(
        fungus_ids=["toy_fungus_alpha"],
        substrate_ids=["toy_cellulose_like_solid"],
        environment_ids=["toy_lab_environment"],
        registry=registry,
        n_samples=4,
        seed=7,
        output_dir=tmp_path / "screen",
    )

    values = [
        float(sample.parameters["surface_rate_constant"]["value"])
        for sample in result.case_results[0].samples
    ]
    assert all(1.0e-9 <= value <= 1.0e-6 for value in values)
    assert all(value > 0.0 for value in values)


def test_simulate_screen_fixed_seed_is_reproducible(tmp_path: Path) -> None:
    registry_a = _registry_with_surface_parameter(tmp_path / "a", "k_surface_range")
    registry_b = _registry_with_surface_parameter(tmp_path / "b", "k_surface_range")

    first = simulate_screen(
        fungus_ids=["toy_fungus_alpha"],
        substrate_ids=["toy_cellulose_like_solid"],
        environment_ids=["toy_lab_environment"],
        registry=registry_a,
        n_samples=3,
        seed=123,
        output_dir=tmp_path / "screen_a",
    )
    second = simulate_screen(
        fungus_ids=["toy_fungus_alpha"],
        substrate_ids=["toy_cellulose_like_solid"],
        environment_ids=["toy_lab_environment"],
        registry=registry_b,
        n_samples=3,
        seed=123,
        output_dir=tmp_path / "screen_b",
    )

    first_values = [
        sample.parameters["surface_rate_constant"]["value"]
        for sample in first.case_results[0].samples
    ]
    second_values = [
        sample.parameters["surface_rate_constant"]["value"]
        for sample in second.case_results[0].samples
    ]
    assert first_values == second_values


def test_simulate_screen_rejects_unknown_underparameterized_case() -> None:
    registry = load_registry(REGISTRY_INDEX)

    with pytest.raises(RegistryScreenSimulationError, match="modelability status"):
        simulate_screen(
            fungus_ids=["toy_fungus_alpha"],
            substrate_ids=["toy_cellulose_like_solid"],
            environment_ids=["toy_lab_environment"],
            registry=registry,
            n_samples=2,
            seed=1,
        )


def test_simulate_screen_rejects_unsupported_mode(tmp_path: Path) -> None:
    registry = _registry_with_surface_parameter(tmp_path, "k_surface_range")

    with pytest.raises(RegistryScreenSimulationError, match="exploratory.*scientific"):
        simulate_screen(
            fungus_ids=["toy_fungus_alpha"],
            substrate_ids=["toy_cellulose_like_solid"],
            environment_ids=["toy_lab_environment"],
            registry=registry,
            n_samples=2,
            mode="strict",  # type: ignore[arg-type]
        )


def test_screen_result_to_dict_is_json_safe(tmp_path: Path) -> None:
    registry = _registry_with_surface_parameter(tmp_path, "k_surface_range")

    result = simulate_screen(
        fungus_ids=["toy_fungus_alpha"],
        substrate_ids=["toy_cellulose_like_solid"],
        environment_ids=["toy_lab_environment"],
        registry=registry,
        n_samples=1,
        seed=5,
        output_dir=tmp_path / "screen",
    )

    encoded = json.dumps(result.to_dict())

    assert "toy_fungus_alpha" in encoded
    assert "surface_rate_constant" in encoded


def _registry_with_surface_parameter(tmp_path: Path, surface_parameter: str):
    registry_dir = _copy_registry(tmp_path)
    process_path = registry_dir / "processes" / "process_compatibility.yml"
    data = _yaml_mapping(process_path)
    records = cast(list[dict[str, Any]], data["records"])
    records[0]["required_parameters"] = [surface_parameter, "k_ads_exact", "A_surface_exact"]
    records[0]["parameter_roles"] = {
        "surface_rate_constant": surface_parameter,
        "adsorption_constant": "k_ads_exact",
        "accessible_surface_area": "A_surface_exact",
    }
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
