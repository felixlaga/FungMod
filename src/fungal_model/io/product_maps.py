"""Product-map config loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from fungal_model.processes import ProductReleaseMap

from .registries import ProductMapRegistry


def load_product_map(
    path: str | Path,
    *,
    registry: ProductMapRegistry | None = None,
) -> ProductReleaseMap:
    """Load a configured product map from YAML."""

    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"Product map config {config_path} did not produce a mapping.")
    return (registry or ProductMapRegistry.default()).load(data)


__all__ = ["load_product_map"]
