"""Paths to distribution data staged from FungMod's canonical data roots."""

from __future__ import annotations

from pathlib import Path


_PACKAGE_RESOURCE_ROOT = Path(__file__).resolve().parent / "_resources"
_SOURCE_CHECKOUT_ROOT = Path(__file__).resolve().parents[2]


def _resource_root() -> Path:
    if (
        (_PACKAGE_RESOURCE_ROOT / "data" / "README.md").is_file()
        and (_PACKAGE_RESOURCE_ROOT / "data_registry" / "registry_index.yml").is_file()
    ):
        return _PACKAGE_RESOURCE_ROOT
    if (
        (_SOURCE_CHECKOUT_ROOT / "data" / "README.md").is_file()
        and (_SOURCE_CHECKOUT_ROOT / "data_registry" / "registry_index.yml").is_file()
    ):
        return _SOURCE_CHECKOUT_ROOT
    raise FileNotFoundError(
        "FungMod distribution resources are unavailable: the installed package is missing "
        "its staged _resources tree and this is not a canonical source checkout."
    )


def package_data_path(relative_path: str | Path = ".") -> Path:
    """Return one existing packaged data path.

    Installed wheels resolve inside their staged immutable ``_resources``
    directory. Editable/source checkouts resolve the single canonical
    repository ``data/`` and ``data_registry/`` roots. Callers that need a
    writable registry or example should copy the returned path before editing.
    """

    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Packaged data paths must be relative and cannot contain '..'.")
    resource_root = _resource_root().resolve()
    candidate = (resource_root / relative).resolve()
    try:
        candidate.relative_to(resource_root)
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
