from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy

import pytest
import yaml

from fungal_model import (
    ConfiguredModelExecutionError,
    Parameter,
    ParameterMergeError,
    ParameterSet,
    merge_parameter_sets,
    run_configured_model,
)
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.results import SimulationResult


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_generic_configured_runner_executes_all_foundation_benchmarks(tmp_path) -> None:
    cases = (
        (MODEL_CONFIGS / "toy_homogeneous_ab.yml", {}, "a_to_b"),
        (MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml", {}, "dummy_surface_catalysis"),
        (
            MODEL_CONFIGS / "toy_surface_dummy_non_pet_product_inhibition.yml",
            {},
            "dummy_surface_catalysis",
        ),
        (
            MODEL_CONFIGS / "toy_surface_pet_plugin.yml",
            {"substrate_registry": pet_substrate_loader_registry()},
            "plugin_surface_catalysis",
        ),
    )

    for config_path, options, expected_rate in cases:
        result = run_configured_model(
            config_path,
            output_dir=tmp_path / config_path.stem,
            **options,
        )

        assert isinstance(result, SimulationResult)
        assert result.assembly_report is not None
        assert result.assembly_report.success
        assert expected_rate in result.process_rates
        assert result.validation_results
        assert all(validation.passed for validation in result.validation_results)
        output = tmp_path / config_path.stem
        for relative_path in _expected_configured_output_files():
            assert (output / relative_path).exists(), relative_path
        manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
        metadata = json.loads((output / "configured_metadata.json").read_text(encoding="utf-8"))
        entity_index = json.loads((output / "entity_snapshots" / "index.json").read_text(encoding="utf-8"))
        assert manifest["mode"] == "toy"
        assert manifest["maturity"] == "framework_benchmark"
        assert "entity_snapshots/index.json" in manifest["files"]
        assert metadata["validation"]["passed"] is True
        assert entity_index["entities"]


def test_configured_output_records_generic_assembly_metadata(tmp_path) -> None:
    result = run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml",
        output_dir=tmp_path / "dummy_run",
    )

    record = json.loads((tmp_path / "dummy_run" / "record.json").read_text(encoding="utf-8"))
    run = json.loads((tmp_path / "dummy_run" / "configured_model_run.json").read_text(encoding="utf-8"))
    decisions = json.loads((tmp_path / "dummy_run" / "process_build_decisions.json").read_text(encoding="utf-8"))
    validators = json.loads((tmp_path / "dummy_run" / "validators.json").read_text(encoding="utf-8"))

    assert record["name"] == result.name
    assert record["assembly_report"]["matched_processes"][0]["process_type"] == "surface_catalysis"
    assert run["assembly_success"] is True
    assert run["mode"] == "toy"
    assert run["maturity"] == "framework_benchmark"
    assert run["validation"]["passed"] is True
    assert decisions["decisions"][0]["can_build"] is True
    assert validators["summary"]["passed"] is True


def test_configured_output_bundle_contains_entity_snapshots(tmp_path) -> None:
    run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml",
        output_dir=tmp_path / "dummy_run",
    )

    output = tmp_path / "dummy_run"
    index = json.loads((output / "entity_snapshots" / "index.json").read_text(encoding="utf-8"))
    roles = {entry["role"] for entry in index["entities"]}

    assert {"substrate", "enzyme", "environment", "geometry", "product_map"}.issubset(roles)
    for entry in index["entities"]:
        assert (output / entry["snapshot_path"]).exists()


def test_configured_model_runs_with_explicit_product_inhibition_modifier(tmp_path) -> None:
    config_path = _product_inhibited_homogeneous_config(tmp_path)

    result = run_configured_model(config_path, output_dir=tmp_path / "product_inhibited")

    assert "a_to_b" in result.process_rates
    assumptions = json.loads((tmp_path / "product_inhibited" / "assumptions.json").read_text(encoding="utf-8"))
    metadata = json.loads((tmp_path / "product_inhibited" / "configured_metadata.json").read_text(encoding="utf-8"))
    process_config = json.loads((tmp_path / "product_inhibited" / "input_model_config.json").read_text(encoding="utf-8"))[
        "processes"
    ][0]
    assert any(item["name"] == "reversible product inhibition modifier" for item in assumptions)
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "a_to_b",
            "modifier_index": 0,
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_product",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Single-product reversible inhibition only; configured only when product_state "
                "and positive unit-compatible K_i are explicit."
            ),
        }
    ]
    assert process_config["modifiers"][0]["type"] == "product_inhibition"


def test_non_pet_surface_benchmark_runs_with_explicit_product_inhibition_modifier(tmp_path) -> None:
    output_dir = tmp_path / "dummy_non_pet_product_inhibited"

    result = run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet_product_inhibition.yml",
        output_dir=output_dir,
    )

    metadata = json.loads((output_dir / "configured_metadata.json").read_text(encoding="utf-8"))
    assumptions = json.loads((output_dir / "assumptions.json").read_text(encoding="utf-8"))
    process_config = json.loads((output_dir / "input_model_config.json").read_text(encoding="utf-8"))[
        "processes"
    ][0]
    merged_parameters = json.loads((output_dir / "merged_parameters.json").read_text(encoding="utf-8"))

    assert result.solver_metadata["success"] is True
    assert "dummy_surface_catalysis" in result.process_rates
    assert metadata["mode"] == "toy"
    assert metadata["maturity"] == "framework_benchmark"
    assert metadata["provenance"]["validity_range"] == "framework tests and exploratory examples only"
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "dummy_surface_catalysis",
            "modifier_index": 0,
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_dummy_product",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Single-product reversible inhibition only; configured only when product_state "
                "and positive unit-compatible K_i are explicit."
            ),
        }
    ]
    assert any(item["name"] == "reversible product inhibition modifier" for item in assumptions)
    assert process_config["modifiers"] == [
        {
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_dummy_product",
        }
    ]
    ki_parameter = next(item for item in merged_parameters["parameters"] if item["symbol"] == "K_i_dummy_product")
    assert ki_parameter["units"] == "kilogram"
    assert "not biological inhibition evidence" in ki_parameter["notes"]


def test_configured_product_inhibition_requires_explicit_inhibition_constant(tmp_path) -> None:
    config_path = _product_inhibited_homogeneous_config(tmp_path, include_ki_parameter=False)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "missing_ki")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_assembly"
    assert "required_parameters" in report["missing_capabilities"]
    assert "K_i_product" in json.dumps(report)


def test_configured_product_inhibition_rejects_non_positive_inhibition_constant(tmp_path) -> None:
    config_path = _product_inhibited_homogeneous_config(tmp_path, ki_value=0.0)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "bad_ki")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "Product inhibition constant must be positive" in report["message"]


def test_parameter_merging_allows_identical_duplicates() -> None:
    first = ParameterSet([_parameter(symbol="k_merge", value=1.0)])
    second = ParameterSet([_parameter(symbol="k_merge", value=1.0)])

    merged = merge_parameter_sets([first, second])

    assert len(merged) == 1
    assert merged.get("k_merge").quantity.magnitude == pytest.approx(1.0)


def test_parameter_merging_rejects_conflicting_duplicates() -> None:
    first = ParameterSet([_parameter(symbol="k_merge", value=1.0)])
    second = ParameterSet([_parameter(symbol="k_merge", value=2.0)])

    with pytest.raises(ParameterMergeError, match="k_merge"):
        merge_parameter_sets([first, second])


def _parameter(*, symbol: str, value: float) -> Parameter:
    return Parameter(
        name="merge benchmark parameter",
        symbol=symbol,
        value=value,
        units="1 / second",
        uncertainty=0.0,
        source="FungMod merge benchmark.",
        confidence_level="testing",
        notes="Artificial value for parameter-merge tests.",
        measurement_method="defined benchmark value",
    )


def _product_inhibited_homogeneous_config(
    tmp_path: Path,
    *,
    include_ki_parameter: bool = True,
    ki_value: float = 0.35,
) -> Path:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    parameters = data["parameters"][0]["parameters"]
    if include_ki_parameter:
        parameters.append(
            {
                "name": "toy product inhibition constant",
                "symbol": "K_i_product",
                "value": ki_value,
                "units": "kilogram",
                "uncertainty": 0.0,
                "source": "FungMod generic product inhibition configured benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial value for configured product-inhibition tests.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            }
        )
    data["processes"][0]["modifiers"] = [
        {
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_product",
        }
    ]
    config_path = tmp_path / "toy_homogeneous_product_inhibition.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _expected_configured_output_files() -> tuple[str, ...]:
    return (
        "record.json",
        "model_assembly_report.json",
        "assumptions.json",
        "parameters.csv",
        "validation_report.json",
        "solver_report.json",
        "state_trajectories.csv",
        "process_rates.csv",
        "derived_quantities.csv",
        "figures/state_trajectories.png",
        "figures/process_rates.png",
        "figures/mass_balance.png",
        "logs/provenance_report.md",
        "input_model_config.json",
        "configured_model_run.json",
        "configured_metadata.json",
        "process_build_decisions.json",
        "initial_state.json",
        "time_grid.json",
        "validators.json",
        "merged_parameters.json",
        "run_environment.json",
        "package_versions.json",
        "source_revision.json",
        "solver_settings.json",
        "entity_snapshots/index.json",
        "output_manifest.json",
    )
