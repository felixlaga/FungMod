"""Environment selection helpers for virtual experiments."""

from __future__ import annotations

import re
from itertools import product
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from fungal_model.core.value_spec import ValueSpec
from fungal_model.registry.records import EnvironmentRecord


EnvironmentEffectStatus = str


@dataclass(frozen=True)
class EnvironmentCase:
    """One concrete runtime environment generated for a virtual experiment."""

    environment_id: str
    temperature: float | None
    temperature_units: str
    ph: float | None
    oxygen: str
    environment_source: str
    environment_effect_status: EnvironmentEffectStatus
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> EnvironmentRecord:
        """Convert this runtime case to an in-memory registry environment record."""

        conditions: dict[str, ValueSpec] = {}
        if self.temperature is not None:
            conditions["temperature"] = ValueSpec(
                kind="exact",
                value=float(self.temperature),
                units=self.temperature_units,
                source="FungMod runtime EnvironmentGrid",
                confidence_level="runtime_metadata",
                notes="Runtime virtual-experiment environment metadata; no response law is implied.",
            )
        if self.ph is not None:
            conditions["ph"] = ValueSpec(
                kind="exact",
                value=float(self.ph),
                units="dimensionless",
                source="FungMod runtime EnvironmentGrid",
                confidence_level="runtime_metadata",
                notes="Runtime virtual-experiment pH metadata; no response law is implied.",
            )
        if self.oxygen:
            conditions["oxygen"] = ValueSpec(
                kind="not_applicable",
                units=None,
                source="FungMod runtime EnvironmentGrid",
                confidence_level="runtime_metadata",
                notes=f"Runtime oxygen label: {self.oxygen}.",
            )
        provenance = {
            "source": "FungMod runtime EnvironmentGrid",
            "environment_source": self.environment_source,
            "environment_effect_status": self.environment_effect_status,
            "runtime_environment_grid": True,
            "temperature_C": self.temperature,
            "ph": self.ph,
            "oxygen": self.oxygen,
            **self.provenance,
        }
        return EnvironmentRecord(
            record_id=self.environment_id,
            name=f"Runtime environment {self.environment_id}",
            maturity="runtime_virtual_experiment",
            provenance=provenance,
            notes=(
                "Generated in memory for a virtual experiment. This record is not "
                "written to data_registry and does not imply an environmental "
                "response model."
            ),
            conditions=conditions,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "temperature": self.temperature,
            "temperature_units": self.temperature_units,
            "ph": self.ph,
            "oxygen": self.oxygen,
            "environment_source": self.environment_source,
            "environment_effect_status": self.environment_effect_status,
            "provenance": dict(self.provenance),
        }


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
        return tuple(case.environment_id for case in self.environment_cases())

    def environment_cases(self) -> tuple[EnvironmentCase, ...]:
        """Generate all concrete runtime environments in the grid."""

        if self.environment_ids:
            return ()
        if not self.temperature_C:
            raise ValueError("EnvironmentGrid requires at least one temperature_C value.")
        if not self.ph:
            raise ValueError("EnvironmentGrid requires at least one ph value.")
        oxygen_values = self.oxygen or ("not_specified",)
        return tuple(
            EnvironmentCase(
                environment_id=_environment_id(temperature, ph_value, oxygen),
                temperature=temperature,
                temperature_units="degree_Celsius",
                ph=ph_value,
                oxygen=oxygen,
                environment_source="runtime_environment_grid",
                environment_effect_status="metadata_only",
                provenance={
                    "generated_by": "EnvironmentGrid",
                    "notes": (
                        "Runtime environment case for virtual-experiment screening. "
                        "Temperature and pH are metadata unless an explicit response law "
                        "or condition-specific parameter record is active."
                    ),
                },
            )
            for temperature, ph_value, oxygen in product(self.temperature_C, self.ph, oxygen_values)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_ids": list(self.environment_ids),
            "temperature_C": list(self.temperature_C),
            "ph": list(self.ph),
            "oxygen": list(self.oxygen),
            "environment_cases": [case.to_dict() for case in self.environment_cases()],
        }


def environment_grid(
    *,
    temperature_C: Sequence[float] = (),
    ph: Sequence[float] = (),
    oxygen: Sequence[str] | str = (),
    environment_ids: Sequence[str] | str = (),
) -> EnvironmentGrid:
    """Create a researcher-facing environment grid.

    Numeric temperature and pH values are runtime metadata unless an explicit
    response law or condition-specific parameter record is active.
    """

    return EnvironmentGrid(
        environment_ids=environment_ids,
        temperature_C=temperature_C,
        ph=ph,
        oxygen=oxygen,
    )


def _string_tuple(values: Sequence[str] | str) -> tuple[str, ...]:
    if isinstance(values, str):
        return (values,) if values else ()
    return tuple(str(value) for value in values)


def _environment_id(temperature_C: float, ph: float, oxygen: str) -> str:
    return f"temp_{_temperature_token(temperature_C)}_ph_{_ph_token(ph)}_{_safe_token(oxygen)}"


def _temperature_token(value: float) -> str:
    if float(value).is_integer():
        text = str(int(value))
    else:
        text = _decimal_token(value, decimals=1)
    return f"{text}C"


def _ph_token(value: float) -> str:
    return _decimal_token(value, decimals=1)


def _decimal_token(value: float, *, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    if text.startswith("-"):
        text = "m" + text[1:]
    return text.replace(".", "p")


def _safe_token(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return clean or "unspecified"


__all__ = ["EnvironmentCase", "EnvironmentEffectStatus", "EnvironmentGrid", "environment_grid"]
