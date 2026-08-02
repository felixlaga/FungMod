"""The canonical ``fungmod`` namespace must mirror the ``fungal_model`` API.

``fungmod`` is the supported, documented import namespace. It re-exports the
full public API of the implementation package ``fungal_model``. These guardrails
keep the two namespaces in lockstep so documentation and user code that import
``fungmod`` never see a smaller or divergent surface.
"""

from __future__ import annotations

import importlib

import fungal_model
import fungmod


def test_version_matches_implementation() -> None:
    assert fungmod.__version__ == fungal_model.__version__


def test_all_mirrors_implementation() -> None:
    assert sorted(fungmod.__all__) == sorted(fungal_model.__all__)


def test_all_is_a_distinct_object() -> None:
    # Mutating the canonical namespace must not corrupt the implementation.
    assert fungmod.__all__ is not fungal_model.__all__


def test_every_exported_name_is_importable_from_fungmod() -> None:
    missing = [name for name in fungal_model.__all__ if not hasattr(fungmod, name)]
    assert not missing, f"fungmod is missing exported names: {missing}"


def test_exported_objects_are_identical() -> None:
    # Re-exports must be the same objects, not copies or shadows.
    for name in fungal_model.__all__:
        if name == "__version__":
            continue
        assert getattr(fungmod, name) is getattr(fungal_model, name), name


def test_canonical_entrypoints_present() -> None:
    for name in (
        "virtual_experiment",
        "run_configured_model",
        "default_registry_path",
        "example_data_path",
        "source_proposal",
    ):
        assert name in fungmod.__all__
        assert callable(getattr(fungmod, name))


def test_submodules_forward_to_implementation() -> None:
    # `from fungmod import <sub>` and `import fungmod.<sub>` resolve to the
    # same implementation subpackages, so `fungmod` covers the full API.
    for sub in ("uncertainty", "calibration", "transport", "workflows"):
        forwarded = importlib.import_module(f"fungmod.{sub}")
        implementation = importlib.import_module(f"fungal_model.{sub}")
        assert forwarded is implementation, sub


def test_deep_submodule_forwarding() -> None:
    # Nested imports resolve to the same implementation source. Python's
    # path-based finder builds the grandchild from the parent's path, so this is
    # a functional equivalence (same code) rather than object identity.
    forwarded = importlib.import_module("fungmod.sources.sabiork")
    implementation = importlib.import_module("fungal_model.sources.sabiork")
    assert forwarded.__file__ == implementation.__file__


def test_missing_submodule_raises() -> None:
    import pytest

    with pytest.raises(AttributeError):
        _ = fungmod.definitely_not_a_real_submodule  # type: ignore[attr-defined]
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fungmod.definitely_not_a_real_submodule")


def test_packages_are_marked_typed() -> None:
    for package_name in ("fungmod", "fungal_model"):
        module = importlib.import_module(package_name)
        package_dir = module.__path__[0]  # type: ignore[attr-defined]
        marker = f"{package_dir}/py.typed"
        import os

        assert os.path.exists(marker), f"{package_name} is missing a py.typed marker"
