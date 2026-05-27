"""PET plugin loaders."""

from __future__ import annotations

from typing import Any, Mapping

from fungal_model.io.parameters import parameter_from_config
from fungal_model.io.registries import SubstrateLoaderRegistry
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set


def register_pet_substrate_loader(registry: SubstrateLoaderRegistry) -> SubstrateLoaderRegistry:
    """Register the PET substrate loader on an explicit registry."""

    registry.register("pet", load_pet_substrate)
    return registry


def pet_substrate_loader_registry() -> SubstrateLoaderRegistry:
    """Return a substrate registry with generic foundation loaders and PET."""

    return register_pet_substrate_loader(SubstrateLoaderRegistry.default())


def load_pet_substrate(data: Mapping[str, Any]) -> PETSubstrate:
    return PETSubstrate(
        geometry_type=data.get("geometry_type", "unknown"),
        parameters=make_pet_parameter_set(parameter_from_config(item) for item in data.get("parameters", []) or []),
        notes=data.get("provenance", {}).get("notes", ""),
    )


__all__ = ["load_pet_substrate", "pet_substrate_loader_registry", "register_pet_substrate_loader"]
