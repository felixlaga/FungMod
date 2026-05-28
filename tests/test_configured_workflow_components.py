from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fungal_model import ModelConfig, load_model_config, run_configured_model
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.results import SimulationResult
from fungal_model.workflows import (
    ConfiguredInputLoader,
    ConfiguredModelExecutionError,
    ConfiguredOutputWriter,
    ConfiguredProcessAssembler,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_configured_input_loader_loads_homogeneous_config() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_homogeneous_ab.yml")

    inputs = ConfiguredInputLoader().load(config)

    assert inputs.environment is not None
    assert inputs.geometry is not None
    assert len(inputs.substrates) == 1
    assert inputs.parameters.get("k_ab").quantity is not None
    assert set(inputs.initial_state) == {"dissolved_substrate_amount", "released_product_amount"}
    assert inputs.t_eval is not None


def test_configured_input_loader_loads_dummy_surface_config() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")

    inputs = ConfiguredInputLoader().load(config)

    assert len(inputs.substrates) == 1
    assert len(inputs.enzymes) == 1
    assert set(inputs.product_maps) == {"dummy_release_map"}
    assert {"K_ads_dummy", "k_surface_dummy", "A_dummy"}.issubset(inputs.parameters.parameters)
    assert inputs.state_units()["solid_substrate_amount"] == "kilogram"


def test_configured_input_loader_loads_plugin_config_only_with_explicit_registry() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_surface_pet_plugin.yml")

    with pytest.raises(ConfiguredModelExecutionError) as error:
        ConfiguredInputLoader().load(config)

    inputs = ConfiguredInputLoader(
        substrate_registry=pet_substrate_loader_registry(),
    ).load(config)

    assert error.value.report.stage == "configured_input_loading"
    assert error.value.report.details["error_type"] == "RegistryLookupError"
    assert len(inputs.substrates) == 1
    assert set(inputs.product_maps) == {"plugin_release_map"}


def test_configured_process_assembler_builds_first_order_process() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_homogeneous_ab.yml")
    inputs = ConfiguredInputLoader().load(config)

    assembly = ConfiguredProcessAssembler().assemble(config, inputs)

    assert assembly.decisions[0].can_build
    assert [process.name for process in assembly.processes] == ["a_to_b"]
    assert assembly.model.assembly_report.success


def test_configured_process_assembler_builds_dummy_surface_process() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")
    inputs = ConfiguredInputLoader().load(config)

    assembly = ConfiguredProcessAssembler().assemble(config, inputs)

    assert assembly.decisions[0].can_build
    assert [process.name for process in assembly.processes] == ["dummy_surface_catalysis"]
    assert assembly.model.assembly_report.success


def test_configured_process_assembler_reports_missing_product_map() -> None:
    config = _model_config_with_process_patch(
        "toy_surface_dummy_non_pet.yml",
        {"product_map": "missing_release_map"},
    )
    inputs = ConfiguredInputLoader().load(config)

    with pytest.raises(ConfiguredModelExecutionError) as error:
        ConfiguredProcessAssembler().assemble(config, inputs)

    report = error.value.report
    decision = report.details["decisions"][0]
    assert report.stage == "process_factory_build"
    assert report.missing_capabilities == ("process_factory_requirements",)
    assert decision["can_build"] is False
    assert "product_maps.missing_release_map" in decision["missing_fields"]


def test_configured_output_writer_writes_expected_files(tmp_path: Path) -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")
    inputs = ConfiguredInputLoader().load(config)
    assembly = ConfiguredProcessAssembler().assemble(config, inputs)
    result = assembly.model.run(
        initial_state=inputs.initial_state,
        t_span=inputs.t_span,
        t_eval=inputs.t_eval,
        label=config.mode,
        name=config.name,
    )

    destination = ConfiguredOutputWriter().write_result_bundle(
        config=config,
        inputs=inputs,
        decisions=assembly.decisions,
        result=result,
        output_dir=tmp_path / "writer_output",
    )

    assert destination == tmp_path / "writer_output"
    for relative_path in (
        "record.json",
        "configured_model_run.json",
        "process_build_decisions.json",
        "merged_parameters.json",
        "entity_snapshots/index.json",
        "output_manifest.json",
    ):
        assert (destination / relative_path).exists(), relative_path


def test_run_configured_model_still_executes_all_foundation_configs(tmp_path: Path) -> None:
    cases: tuple[tuple[str, dict[str, Any]], ...] = (
        ("toy_homogeneous_ab.yml", {}),
        ("toy_surface_dummy_non_pet.yml", {}),
        ("toy_surface_pet_plugin.yml", {"substrate_registry": pet_substrate_loader_registry()}),
    )

    for filename, options in cases:
        result = run_configured_model(
            MODEL_CONFIGS / filename,
            output_dir=tmp_path / Path(filename).stem,
            **options,
        )

        assert isinstance(result, SimulationResult)
        assert result.assembly_report is not None
        assert result.assembly_report.success


def _model_config_with_process_patch(filename: str, patch: dict[str, Any]) -> ModelConfig:
    source = load_model_config(MODEL_CONFIGS / filename)
    data = source.to_dict()
    data["processes"][0] = {**data["processes"][0], **patch}
    return ModelConfig.from_mapping(data, path=source.path)
