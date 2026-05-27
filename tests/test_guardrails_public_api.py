from __future__ import annotations

import inspect

import fungal_model
from fungal_model.processes import ModelBuilder, ProcessRegistry
from fungal_model.results import SimulationResult


NEXT_MILESTONE_PUBLIC_API = (
    "run_configured_model",
    "load_model_config",
    "ProcessLibrary",
)


def test_current_foundation_public_api_is_exported() -> None:
    assert inspect.isclass(ModelBuilder)
    assert inspect.isclass(ProcessRegistry)
    assert inspect.isclass(SimulationResult)
    assert fungal_model.ModelBuilder is ModelBuilder
    assert fungal_model.ProcessRegistry is ProcessRegistry
    assert fungal_model.SimulationResult is SimulationResult


def test_process_registry_or_future_process_library_is_available() -> None:
    process_library = getattr(fungal_model, "ProcessLibrary", None)
    assert inspect.isclass(process_library) or inspect.isclass(ProcessRegistry)


def test_next_milestone_public_api_is_not_faked_when_introduced() -> None:
    # TODO Milestone 2: require these names once generic configured execution is
    # introduced. For Milestone 1, absence is honest; placeholder exports are not.
    for name in NEXT_MILESTONE_PUBLIC_API:
        candidate = getattr(fungal_model, name, None)
        if candidate is None:
            continue
        source = inspect.getsource(candidate).lower()
        assert "notimplementederror" not in source
        assert "placeholder" not in source
        assert "todo" not in source
