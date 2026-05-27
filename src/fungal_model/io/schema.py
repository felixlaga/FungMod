"""Schema validation for human-editable FungMod configuration files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fungal_model.core.units import Q_, UnitError

REQUIRED_PROVENANCE_FIELDS = (
    "source",
    "measurement_method",
    "confidence_level",
    "notes",
    "validity_range",
    "units",
)


class SchemaValidationError(ValueError):
    """Raised when a config file violates the minimal FungMod schema."""


@dataclass(frozen=True)
class SchemaValidationResult:
    """Structured schema validation result."""

    passed: bool
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


def validate_config(data: Mapping[str, Any]) -> SchemaValidationResult:
    """Validate top-level provenance and parameter provenance."""

    missing: list[str] = []
    if "kind" not in data:
        missing.append("kind")
    if "name" not in data:
        missing.append("name")
    provenance = data.get("provenance")
    if not isinstance(provenance, Mapping):
        missing.append("provenance")
    else:
        missing.extend(
            f"provenance.{field}"
            for field in REQUIRED_PROVENANCE_FIELDS
            if _is_missing(provenance.get(field))
        )
        _validate_units(provenance.get("units"), "provenance.units")

    if data.get("kind") != "model_config":
        for index, parameter in enumerate(data.get("parameters", []) or []):
            if not isinstance(parameter, Mapping):
                missing.append(f"parameters[{index}]")
                continue
            for field in (
                "name",
                "symbol",
                "value",
                "units",
                "source",
                "confidence_level",
                "notes",
                "measurement_method",
                "validity_range",
            ):
                if field not in parameter:
                    missing.append(f"parameters[{index}].{field}")
            if "units" in parameter:
                _validate_units(parameter["units"], f"parameters[{index}].units")

    if missing:
        raise SchemaValidationError(
            "Configuration is missing required schema/provenance fields: "
            + ", ".join(missing)
        )
    return SchemaValidationResult(
        passed=True,
        message="Configuration schema and provenance fields are present.",
        details={"kind": data["kind"], "name": data["name"]},
    )


def _is_missing(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _validate_units(units: Any, field_name: str) -> None:
    if _is_missing(units):
        raise SchemaValidationError(f"{field_name} is required.")
    if str(units) == "not_applicable":
        return
    try:
        Q_(1, str(units))
    except Exception as exc:
        raise UnitError(f"{field_name} has invalid units: {units!r}") from exc


__all__ = [
    "REQUIRED_PROVENANCE_FIELDS",
    "SchemaValidationError",
    "SchemaValidationResult",
    "validate_config",
]
