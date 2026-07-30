"""Closed, versioned unit-conversion methods for curator-authored parameters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

from pint.errors import PintError

from fungal_model.core.units import Q_


PARAMETER_CONVERSION_REGISTRY_SCHEMA_VERSION = "1.0.0"
PINT_DECIMAL_PLACES_HALF_EVEN_12_V1 = (
    "pint_unit_conversion_decimal_places_half_even_12_v1"
)


class ParameterConversionError(ValueError):
    """Raised when a requested parameter conversion is absent or not exact."""


@dataclass(frozen=True)
class ParameterConversionMethod:
    """One named and versioned deterministic unit-conversion policy."""

    method_id: str
    version: str
    algorithm: str
    rounding_mode: str
    decimal_places: int

    def __post_init__(self) -> None:
        if not self.method_id.strip() or not self.version.strip():
            raise ParameterConversionError("Conversion method identity and version are required.")
        if self.algorithm != "pint_unit_conversion":
            raise ParameterConversionError(
                f"Unsupported conversion algorithm {self.algorithm!r}."
            )
        if self.rounding_mode != "decimal_places_half_even":
            raise ParameterConversionError(
                f"Unsupported conversion rounding mode {self.rounding_mode!r}."
            )
        if type(self.decimal_places) is not int or not 0 <= self.decimal_places <= 15:
            raise ParameterConversionError(
                "Conversion decimal_places must be an integer from 0 through 15."
            )

    def convert(
        self,
        value: float,
        *,
        source_units: str,
        target_units: str,
    ) -> float:
        """Convert and deterministically round one finite float."""

        if type(value) is not float or not math.isfinite(value):
            raise ParameterConversionError("Conversion source value must be a finite float.")
        if not source_units.strip() or not target_units.strip():
            raise ParameterConversionError("Conversion source and target units are required.")
        if source_units == target_units:
            raise ParameterConversionError(
                "Nonidentity conversion requires distinct source and target unit text."
            )
        try:
            magnitude = float(Q_(value, source_units).to(target_units).magnitude)
        except (PintError, TypeError, ValueError) as exc:
            raise ParameterConversionError(
                f"Conversion units {source_units!r} and {target_units!r} "
                "must parse and have compatible dimensionality."
            ) from exc
        if not math.isfinite(magnitude):
            raise ParameterConversionError("Converted parameter value must remain finite.")
        try:
            quantum = Decimal(1).scaleb(-self.decimal_places)
            rounded = Decimal(str(magnitude)).quantize(
                quantum,
                rounding=ROUND_HALF_EVEN,
            )
        except (InvalidOperation, ValueError) as exc:
            raise ParameterConversionError(
                "Converted parameter value cannot satisfy the registered rounding policy."
            ) from exc
        result = float(rounded)
        if not math.isfinite(result):
            raise ParameterConversionError("Rounded parameter value must remain finite.")
        return result


@dataclass(frozen=True)
class ParameterConversionRegistry:
    """Immutable collection of closed conversion methods."""

    schema_version: str
    methods: tuple[ParameterConversionMethod, ...]

    def __post_init__(self) -> None:
        if self.schema_version != PARAMETER_CONVERSION_REGISTRY_SCHEMA_VERSION:
            raise ParameterConversionError(
                "Unsupported parameter conversion registry schema version."
            )
        ids = [method.method_id for method in self.methods]
        if not ids or len(ids) != len(set(ids)):
            raise ParameterConversionError(
                "Parameter conversion registry requires unique method identifiers."
            )

    def resolve(self, method_id: str) -> ParameterConversionMethod:
        matches = [method for method in self.methods if method.method_id == method_id]
        if len(matches) != 1:
            raise ParameterConversionError(
                f"Conversion method {method_id!r} is not registered exactly once."
            )
        return matches[0]


def default_parameter_conversion_registry() -> ParameterConversionRegistry:
    """Return the closed built-in nonidentity conversion registry."""

    return ParameterConversionRegistry(
        schema_version=PARAMETER_CONVERSION_REGISTRY_SCHEMA_VERSION,
        methods=(
            ParameterConversionMethod(
                method_id=PINT_DECIMAL_PLACES_HALF_EVEN_12_V1,
                version="1.0.0",
                algorithm="pint_unit_conversion",
                rounding_mode="decimal_places_half_even",
                decimal_places=12,
            ),
        ),
    )


__all__ = [
    "PARAMETER_CONVERSION_REGISTRY_SCHEMA_VERSION",
    "PINT_DECIMAL_PLACES_HALF_EVEN_12_V1",
    "ParameterConversionError",
    "ParameterConversionMethod",
    "ParameterConversionRegistry",
    "default_parameter_conversion_registry",
]
