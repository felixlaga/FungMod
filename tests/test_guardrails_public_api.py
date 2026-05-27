from __future__ import annotations

import inspect

import pytest

import fungal_model
from fungal_model.processes import (
    AssembledModel,
    ModelBuilder,
    ProcessLibrary,
    ProcessRegistry,
)
from fungal_model.results import SimulationResult
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows import ConfiguredModelExecutionError


def test_current_foundation_public_api_is_exported() -> None:
    assert inspect.isclass(AssembledModel)
    assert inspect.isclass(ModelBuilder)
    assert inspect.isclass(ProcessRegistry)
    assert inspect.isclass(ProcessLibrary)
    assert inspect.isclass(ProcessODESolver)
    assert inspect.isclass(RunRequest)
    assert inspect.isclass(SimulationResult)
    assert fungal_model.AssembledModel is AssembledModel
    assert fungal_model.ModelBuilder is ModelBuilder
    assert fungal_model.ProcessRegistry is ProcessRegistry
    assert fungal_model.ProcessLibrary is ProcessLibrary
    assert fungal_model.ProcessODESolver is ProcessODESolver
    assert fungal_model.RunRequest is RunRequest
    assert fungal_model.SimulationResult is SimulationResult
    assert callable(fungal_model.load_model_config)
    assert callable(fungal_model.run_configured_model)


def test_top_level_api_is_generic_first() -> None:
    assert not hasattr(fungal_model, "run_pet_surface_integration")
    assert not hasattr(fungal_model, "PETSurfaceWorkflowConfig")


def test_public_api_names_are_not_unfinished_placeholders() -> None:
    for candidate in (
        fungal_model.load_model_config,
        fungal_model.run_configured_model,
        fungal_model.ProcessLibrary,
        fungal_model.AssembledModel.run,
    ):
        source = inspect.getsource(candidate).lower()
        assert "notimplementederror" not in source
        assert "placeholder" not in source
        assert "todo" not in source


def test_load_model_config_validates_generic_top_level_contract(tmp_path) -> None:
    config_path = tmp_path / "toy_model.yml"
    config_path.write_text(
        """
kind: model_config
name: toy generic shell
mode: toy
maturity: framework_benchmark
entities: {}
parameters: []
processes: []
initial_state: {}
time:
  start:
    value: 0.0
    units: second
  stop:
    value: 1.0
    units: second
  points: 2
validators: []
outputs: {}
""".lstrip(),
        encoding="utf-8",
    )

    config = fungal_model.load_model_config(config_path)

    assert config.kind == "model_config"
    assert config.name == "toy generic shell"
    assert config.validate().passed
    assert config.to_dict()["maturity"] == "framework_benchmark"


def test_run_configured_model_fails_with_structured_report(tmp_path) -> None:
    config_path = tmp_path / "toy_model.yml"
    config_path.write_text(
        """
kind: model_config
name: toy generic shell
mode: toy
maturity: framework_benchmark
entities: {}
parameters: []
processes: []
initial_state: {}
time:
  start:
    value: 0.0
    units: second
  stop:
    value: 1.0
    units: second
  points: 2
validators: []
outputs: {}
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        fungal_model.run_configured_model(config_path)

    report = exc_info.value.report
    assert report.config_name == "toy generic shell"
    assert report.stage == "configured_model_execution"
    assert "entity_loader_registries" in report.missing_capabilities
    assert "configured_process_factory_wiring" in report.missing_capabilities
    assert report.to_dict()["config_path"] == str(config_path)
