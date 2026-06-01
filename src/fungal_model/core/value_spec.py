"""Structured exact, uncertain, unknown, and not-applicable values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import numpy as np

from fungal_model.core.units import Q_, Quantity
from fungal_model.core.validators import ValidationResult

ValueSpecKind = Literal["exact", "range", "distribution", "unknown", "not_applicable"]
SUPPORTED_DISTRIBUTIONS = frozenset({"uniform", "loguniform"})


class ValueSpecError(ValueError):
    """Raised when a value specification cannot be converted or sampled."""


@dataclass(frozen=True)
class ValueSpec:
    """A value that may be exact, uncertain, unknown, or explicitly irrelevant."""

    kind: ValueSpecKind
    units: str | None
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    distribution: str | None = None
    parameters: Mapping[str, float] = field(default_factory=dict)
    source: str | None = None
    confidence_level: str | None = None
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ValueSpec":
        kind = str(data.get("kind", "")).strip()
        parameters = data.get("parameters", {}) or {}
        if not isinstance(parameters, Mapping):
            parameters = {}
        return cls(
            kind=cast(ValueSpecKind, kind),
            units=None if data.get("units") is None else str(data.get("units")),
            value=_optional_float(data.get("value")),
            lower=_optional_float(data.get("lower")),
            upper=_optional_float(data.get("upper")),
            distribution=None if data.get("distribution") is None else str(data.get("distribution")),
            parameters={str(key): float(value) for key, value in parameters.items()},
            source=None if data.get("source") is None else str(data.get("source")),
            confidence_level=None if data.get("confidence_level") is None else str(data.get("confidence_level")),
            notes=str(data.get("notes", "") or ""),
        )

    @property
    def is_exact(self) -> bool:
        return self.kind == "exact"

    @property
    def is_uncertain(self) -> bool:
        return self.kind in {"range", "distribution"}

    @property
    def is_unknown(self) -> bool:
        return self.kind == "unknown"

    def validate(self, nonnegative: bool = False) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        if self.kind not in {"exact", "range", "distribution", "unknown", "not_applicable"}:
            issues.append({"field": "kind", "message": "Unsupported ValueSpec kind.", "value": self.kind})
        if self.units is not None and not _known_units(self.units):
            issues.append({"field": "units", "message": "ValueSpec units are not recognized.", "value": self.units})

        if self.kind == "exact":
            if self.value is None:
                issues.append({"field": "value", "message": "Exact ValueSpec requires value."})
            elif nonnegative and self.value < 0.0:
                issues.append({"field": "value", "message": "Exact ValueSpec must be nonnegative."})
        elif self.kind == "range":
            if self.units is None:
                issues.append({"field": "units", "message": "Range ValueSpec requires units."})
            if self.lower is None:
                issues.append({"field": "lower", "message": "Range ValueSpec requires lower."})
            if self.upper is None:
                issues.append({"field": "upper", "message": "Range ValueSpec requires upper."})
            if self.lower is not None and self.upper is not None:
                if not self.lower < self.upper:
                    issues.append({"field": "range", "message": "Range ValueSpec requires lower < upper."})
                if nonnegative and self.lower < 0.0:
                    issues.append({"field": "lower", "message": "Range ValueSpec lower must be nonnegative."})
        elif self.kind == "distribution":
            issues.extend(self._distribution_issues(nonnegative=nonnegative))
        elif self.kind == "unknown":
            if self.value is not None or self.lower is not None or self.upper is not None:
                issues.append({"field": "value", "message": "Unknown ValueSpec must not include numeric values."})
            if self.distribution is not None or self.parameters:
                issues.append({"field": "distribution", "message": "Unknown ValueSpec must not include a distribution."})
        elif self.kind == "not_applicable":
            if not self.notes.strip():
                issues.append({"field": "notes", "message": "Not-applicable ValueSpec requires explanatory notes."})
            if self.value is not None or self.lower is not None or self.upper is not None:
                issues.append({"field": "value", "message": "Not-applicable ValueSpec must not include numeric values."})

        return ValidationResult(
            name="value_spec",
            passed=not issues,
            message="ValueSpec is valid." if not issues else "ValueSpec failed validation.",
            details={"kind": self.kind, "issues": issues},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "units": self.units,
            "value": self.value,
            "lower": self.lower,
            "upper": self.upper,
            "distribution": self.distribution,
            "parameters": dict(self.parameters),
            "source": self.source,
            "confidence_level": self.confidence_level,
            "notes": self.notes,
        }

    def to_quantity(self) -> Quantity:
        validation = self.validate()
        if not validation.passed:
            raise ValueSpecError(_validation_message(validation))
        if self.kind != "exact":
            raise ValueSpecError(f"ValueSpec kind {self.kind!r} cannot be converted to a single exact quantity.")
        assert self.value is not None
        return Q_(self.value, self._quantity_units())

    def sample(self, rng: np.random.Generator | None = None) -> Quantity:
        validation = self.validate()
        if not validation.passed:
            raise ValueSpecError(_validation_message(validation))
        generator = rng or np.random.default_rng()
        if self.kind == "exact":
            return self.to_quantity()
        if self.kind == "range":
            assert self.lower is not None
            assert self.upper is not None
            return Q_(float(generator.uniform(self.lower, self.upper)), self._quantity_units())
        if self.kind == "distribution":
            assert self.distribution is not None
            if self.distribution == "uniform":
                lower, upper = self._distribution_bounds()
                return Q_(float(generator.uniform(lower, upper)), self._quantity_units())
            if self.distribution == "loguniform":
                lower, upper = self._distribution_bounds()
                value = float(np.exp(generator.uniform(np.log(lower), np.log(upper))))
                return Q_(value, self._quantity_units())
        raise ValueSpecError(f"ValueSpec kind {self.kind!r} cannot be sampled.")

    def _distribution_issues(self, *, nonnegative: bool) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if self.units is None:
            issues.append({"field": "units", "message": "Distribution ValueSpec requires units."})
        if self.distribution is None:
            issues.append({"field": "distribution", "message": "Distribution ValueSpec requires distribution."})
            return issues
        if self.distribution not in SUPPORTED_DISTRIBUTIONS:
            issues.append(
                {
                    "field": "distribution",
                    "message": "Distribution ValueSpec supports only uniform and loguniform.",
                    "value": self.distribution,
                }
            )
            return issues
        if not self.parameters:
            issues.append({"field": "parameters", "message": "Distribution ValueSpec requires parameters."})
            return issues
        lower = self.parameters.get("lower")
        upper = self.parameters.get("upper")
        if lower is None:
            issues.append({"field": "parameters.lower", "message": "Distribution ValueSpec requires lower."})
        if upper is None:
            issues.append({"field": "parameters.upper", "message": "Distribution ValueSpec requires upper."})
        if lower is None or upper is None:
            return issues
        if not lower < upper:
            issues.append({"field": "parameters", "message": "Distribution ValueSpec requires lower < upper."})
        if self.distribution == "loguniform" and lower <= 0.0:
            issues.append({"field": "parameters.lower", "message": "Loguniform lower bound must be positive."})
        if nonnegative and lower < 0.0:
            issues.append({"field": "parameters.lower", "message": "Distribution lower must be nonnegative."})
        return issues

    def _distribution_bounds(self) -> tuple[float, float]:
        lower = self.parameters.get("lower")
        upper = self.parameters.get("upper")
        if lower is None or upper is None:
            raise ValueSpecError("Distribution ValueSpec requires lower and upper parameters.")
        return float(lower), float(upper)

    def _quantity_units(self) -> str:
        return "dimensionless" if self.units is None else self.units


def _known_units(units: str) -> bool:
    try:
        Q_(1, units)
    except Exception:
        return False
    return True


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _validation_message(validation: ValidationResult) -> str:
    return f"{validation.message}: {validation.details.get('issues', [])}"


__all__ = [
    "SUPPORTED_DISTRIBUTIONS",
    "ValueSpec",
    "ValueSpecError",
    "ValueSpecKind",
]
