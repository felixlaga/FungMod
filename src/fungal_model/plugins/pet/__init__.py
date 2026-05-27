"""PET plugin integration helpers."""

from .loaders import pet_substrate_loader_registry, register_pet_substrate_loader

__all__ = ["pet_substrate_loader_registry", "register_pet_substrate_loader"]
