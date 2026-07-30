"""Paths to immutable data assets shipped with the FungMod wheel."""

from __future__ import annotations

from pathlib import Path


_RESOURCE_ROOT = Path(__file__).resolve().parent / "_resources"


def package_data_path(relative_path: str | Path = ".") -> Path:
    """Return one existing packaged data path.

    Paths are resolved strictly within the wheel's immutable ``_resources``
    directory. Callers that need a writable registry or example should copy
    the returned file or directory before editing it.
    """

    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Packaged data paths must be relative and cannot contain '..'.")
    candidate = (_RESOURCE_ROOT / relative).resolve()
    try:
        candidate.relative_to(_RESOURCE_ROOT.resolve())
    except ValueError as exc:  # pragma: no cover - defensive after the part check
        raise ValueError("Packaged data paths must stay inside the FungMod resource root.") from exc
    if not candidate.exists():
        raise FileNotFoundError(f"FungMod packaged data asset does not exist: {relative.as_posix()}")
    return candidate


def default_registry_path() -> Path:
    """Return the immutable registry index included in the installed wheel."""

    return package_data_path("data_registry/registry_index.yml")


def example_data_path(relative_path: str | Path = ".") -> Path:
    """Return one immutable example-data path included in the installed wheel."""

    relative = Path(relative_path)
    return package_data_path(Path("data") / relative)


__all__ = ["default_registry_path", "example_data_path", "package_data_path"]
