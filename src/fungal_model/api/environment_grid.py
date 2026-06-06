"""Environment selection helpers for virtual experiments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EnvironmentGrid:
    """API placeholder for future environment grids.

    API-001 supports registry-backed environment IDs. Numeric grids are kept as
    explicit metadata for later milestones, but are not converted into new
    environment records here.
    """

    environment_ids: tuple[str, ...] = ()
    temperature_C: tuple[float, ...] = ()
    ph: tuple[float, ...] = ()
    oxygen: tuple[str, ...] = ()

    def __init__(
        self,
        environment_ids: Sequence[str] | str = (),
        *,
        temperature_C: Sequence[float] = (),
        ph: Sequence[float] = (),
        oxygen: Sequence[str] | str = (),
    ) -> None:
        object.__setattr__(self, "environment_ids", _string_tuple(environment_ids))
        object.__setattr__(self, "temperature_C", tuple(float(value) for value in temperature_C))
        object.__setattr__(self, "ph", tuple(float(value) for value in ph))
        object.__setattr__(self, "oxygen", _string_tuple(oxygen))

    @classmethod
    def from_registry_ids(cls, environment_ids: Sequence[str] | str) -> "EnvironmentGrid":
        """Build an API-001 grid from already-curated registry environment IDs."""

        return cls(environment_ids=environment_ids)

    def registry_ids(self) -> tuple[str, ...]:
        """Return registry IDs that can be simulated in API-001."""

        if self.environment_ids:
            return self.environment_ids
        raise NotImplementedError(
            "API-001 simulates environment records from registry IDs only. "
            "Numeric environment grids require a later milestone that creates "
            "honest environment records and rate modifiers."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_ids": list(self.environment_ids),
            "temperature_C": list(self.temperature_C),
            "ph": list(self.ph),
            "oxygen": list(self.oxygen),
        }


def _string_tuple(values: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(values, str):
        return (values,) if values else ()
    return tuple(str(value) for value in values)


__all__ = ["EnvironmentGrid"]
