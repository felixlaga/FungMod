"""State variable definitions for well-mixed and future spatial models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeciesDefinition:
    """A named state variable with required units."""

    name: str
    units: str
    description: str = ""


__all__ = ["SpeciesDefinition"]

