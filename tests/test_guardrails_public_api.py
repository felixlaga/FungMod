from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import fungal_model
import fungal_model.workflows as workflows
from fungal_model import (
    DegradationScreenResult,
    EnvironmentCase,
    EnvironmentGrid,
    Parameter,
    ParameterSet,
    VirtualExperiment,
    VirtualExperimentError,
    load_geometry,
    load_model_config,
    load_parameter_set,
    load_product_map,
    load_substrate,
    run_configured_model,
    virtual_experiment,
)
from fungal_model.plugins import pet as pet_plugin
from fungal_model.processes import (
    AssembledModel,
    ModelBuilder,
    ProcessLibrary,
    ProcessRegistry,
)
from fungal_model.results import SimulationResult
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows import ConfiguredModelExecutionError


ROOT = Path(__file__).resolve().parents[1]

FOUNDATION_PUBLIC_API = {
    "run_configured_model": run_configured_model,
    "load_model_config": load_model_config,
    "load_substrate": load_substrate,
    "load_geometry": load_geometry,
    "load_product_map": load_product_map,
    "load_parameter_set": load_parameter_set,
    "ModelBuilder": ModelBuilder,
    "AssembledModel": AssembledModel,
    "ProcessLibrary": ProcessLibrary,
    "ProcessRegistry": ProcessRegistry,
    "ProcessODESolver": ProcessODESolver,
    "RunRequest": RunRequest,
    "SimulationResult": SimulationResult,
    "Parameter": Parameter,
    "ParameterSet": ParameterSet,
}

RESEARCHER_PUBLIC_API = {
    "VirtualExperiment": VirtualExperiment,
    "virtual_experiment": virtual_experiment,
    "EnvironmentGrid": EnvironmentGrid,
    "EnvironmentCase": EnvironmentCase,
    "DegradationScreenResult": DegradationScreenResult,
    "VirtualExperimentError": VirtualExperimentError,
}

PET_PLUGIN_ONLY_NAMES = (
    "PETSurfaceWorkflowConfig",
    "pet_substrate_loader_registry",
    "register_pet_substrate_loader",
    "run_pet_surface_integration",
)


def test_current_foundation_public_api_is_exported() -> None:
    class_names = {
        "ModelBuilder",
        "AssembledModel",
        "ProcessLibrary",
        "ProcessRegistry",
        "ProcessODESolver",
        "RunRequest",
        "SimulationResult",
        "Parameter",
        "ParameterSet",
    }
    for name, expected in FOUNDATION_PUBLIC_API.items():
        assert name in fungal_model.__all__
        assert getattr(fungal_model, name) is expected
        if name in class_names:
            assert inspect.isclass(expected)
        else:
            assert callable(expected)


def test_current_researcher_public_api_is_exported() -> None:
    class_names = {
        "VirtualExperiment",
        "EnvironmentGrid",
        "EnvironmentCase",
        "DegradationScreenResult",
        "VirtualExperimentError",
    }
    for name, expected in RESEARCHER_PUBLIC_API.items():
        assert name in fungal_model.__all__
        assert getattr(fungal_model, name) is expected
        if name in class_names:
            assert inspect.isclass(expected)
        else:
            assert callable(expected)


def test_top_level_api_is_generic_first() -> None:
    for name in PET_PLUGIN_ONLY_NAMES:
        assert not hasattr(fungal_model, name)
        assert not hasattr(workflows, name)


def test_pet_plugin_helpers_are_available_only_from_pet_plugin() -> None:
    for name in PET_PLUGIN_ONLY_NAMES:
        assert hasattr(pet_plugin, name)
        assert name in pet_plugin.__all__


def test_public_api_names_are_not_unfinished_placeholders() -> None:
    candidates = (
        *FOUNDATION_PUBLIC_API.values(),
        fungal_model.AssembledModel.run,
    )
    for candidate in candidates:
        source = inspect.getsource(candidate).lower()
        assert "notimplementederror" not in source
        assert "placeholder" not in source
        assert "todo" not in source


def test_public_api_is_documented_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Public API" in readme
    for name in RESEARCHER_PUBLIC_API:
        assert f"`{name}`" in readme
    for name in FOUNDATION_PUBLIC_API:
        assert f"`{name}`" in readme
    assert "`run_pet_surface_integration`" in readme
    assert "fungal_model.plugins.pet" in readme


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
    assert "configured_processes" in report.missing_capabilities
    assert "configured_initial_state" in report.missing_capabilities
    assert report.to_dict()["config_path"] == str(config_path)
