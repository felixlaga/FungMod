"""Base environmental modifier interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity
from fungal_model.entities.environment import Environment


class EnvironmentalModifier(Protocol):
    """Protocol for explicit rate modifiers driven by environment/state data."""

    name: str

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        ...

    def activity(
        self,
        *,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        ...

    def scale(
        self,
        *,
        rate: Quantity,
        parameters: ParameterSet,
        environment: Environment,
        state: Mapping[str, Quantity] | None = None,
    ) -> Quantity:
        ...


@dataclass(frozen=True)
class ModifierMetadata:
    """Small serializable descriptor for a modifier."""

    name: str
    modifier_type: str
    required_parameters: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "modifier_type": self.modifier_type,
            "required_parameters": list(self.required_parameters),
        }


__all__ = ["EnvironmentalModifier", "ModifierMetadata"]
