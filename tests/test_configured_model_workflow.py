from __future__ import annotations

import json
from pathlib import Path

import pytest

from fungal_model import Parameter, ParameterMergeError, ParameterSet, merge_parameter_sets, run_configured_model
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.results import SimulationResult


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_generic_configured_runner_executes_all_foundation_benchmarks(tmp_path) -> None:
    cases = (
        (MODEL_CONFIGS / "toy_homogeneous_ab.yml", {}, "a_to_b"),
        (MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml", {}, "dummy_surface_catalysis"),
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
        assert (tmp_path / config_path.stem / "record.json").exists()
        assert (tmp_path / config_path.stem / "input_model_config.json").exists()
        assert (tmp_path / config_path.stem / "configured_model_run.json").exists()


def test_configured_output_records_generic_assembly_metadata(tmp_path) -> None:
    result = run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml",
        output_dir=tmp_path / "dummy_run",
    )

    record = json.loads((tmp_path / "dummy_run" / "record.json").read_text(encoding="utf-8"))
    run = json.loads((tmp_path / "dummy_run" / "configured_model_run.json").read_text(encoding="utf-8"))

    assert record["name"] == result.name
    assert record["assembly_report"]["matched_processes"][0]["process_type"] == "surface_catalysis"
    assert run["assembly_success"] is True
    assert run["mode"] == "toy"
    assert run["maturity"] == "framework_benchmark"


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
