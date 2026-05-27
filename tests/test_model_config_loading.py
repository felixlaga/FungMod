from __future__ import annotations

from pathlib import Path

import pytest

from fungal_model import (
    ConfiguredModelExecutionError,
    EntityConfigRefs,
    InitialStateConfig,
    ModelConfig,
    OutputConfig,
    ParameterSetConfig,
    ProcessConfig,
    TimeConfig,
    ValidatorConfig,
    load_model_config,
    run_configured_model,
)
from fungal_model.io import ModelConfigError


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


FOUNDATION_MODEL_CONFIGS = (
    MODEL_CONFIGS / "toy_homogeneous_ab.yml",
    MODEL_CONFIGS / "toy_surface_pet_plugin.yml",
    MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml",
)


def test_foundation_model_configs_load_through_same_generic_loader() -> None:
    configs = [load_model_config(path) for path in FOUNDATION_MODEL_CONFIGS]

    assert [config.kind for config in configs] == ["model_config"] * 3
    assert {config.mode for config in configs} == {"toy"}
    assert {config.maturity for config in configs} == {"framework_benchmark"}
    assert all(config.validate().passed for config in configs)
    assert all(isinstance(config.entities, EntityConfigRefs) for config in configs)
    assert all(isinstance(config.initial_state, InitialStateConfig) for config in configs)
    assert all(isinstance(config.time, TimeConfig) for config in configs)
    assert all(isinstance(config.outputs, OutputConfig) for config in configs)


def test_model_config_sections_are_structured_objects() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")

    assert isinstance(config, ModelConfig)
    assert isinstance(config.parameters[0], ParameterSetConfig)
    assert isinstance(config.processes[0], ProcessConfig)
    assert isinstance(config.validators[0], ValidatorConfig)
    assert config.entities.substrates[0].loader == "generic_solid"
    assert config.entities.product_maps[0].id == "dummy_release_map"
    assert config.processes[0].product_map == "dummy_release_map"
    assert config.time.points == 41
    assert config.outputs.directory == "outputs/toy_surface_dummy_non_pet"


def test_plugin_and_non_plugin_surface_configs_use_same_process_shape() -> None:
    plugin_config = load_model_config(MODEL_CONFIGS / "toy_surface_pet_plugin.yml")
    dummy_config = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")

    assert plugin_config.processes[0].process_type == "surface_catalysis"
    assert dummy_config.processes[0].process_type == "surface_catalysis"
    assert set(plugin_config.processes[0].states) == set(dummy_config.processes[0].states)
    assert plugin_config.processes[0].states["product"] == "released_product_amount"
    assert dummy_config.processes[0].states["product"] == "released_product_amount"


def test_plugin_config_state_names_are_configured_not_hardcoded() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_surface_pet_plugin.yml")

    assert set(config.initial_state.states) == {
        "solid_polymer_amount",
        "released_product_amount",
        "free_catalyst_concentration",
    }
    assert config.processes[0].states["substrate"] == "solid_polymer_amount"


def test_run_configured_model_loads_each_foundation_config_before_structured_failure() -> None:
    for path in FOUNDATION_MODEL_CONFIGS:
        with pytest.raises(ConfiguredModelExecutionError) as exc_info:
            run_configured_model(path)
        report = exc_info.value.report
        assert report.config_path == str(path)
        assert report.stage == "configured_model_execution"
        assert "configured_process_factory_wiring" in report.missing_capabilities
        assert "native_assembled_model_run" in report.missing_capabilities


def test_model_config_rejects_missing_required_sections(tmp_path) -> None:
    path = tmp_path / "bad_model.yml"
    path.write_text(
        """
kind: model_config
name: missing sections
mode: toy
maturity: framework_benchmark
entities: {}
parameters: []
processes: []
initial_state: {}
validators: []
outputs: {}
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ModelConfigError) as exc_info:
        load_model_config(path)

    assert "time" in str(exc_info.value)
