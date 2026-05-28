"""Traceable model parameters.

Parameters are the only accepted home for scientific constants and fitted
values. Unknown values are represented explicitly by ``value=None``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .provenance import ConfidenceLevel, ProvenanceError, UnknownParameterError, has_text
from .units import Q_, Quantity, UnitError, assert_compatible, is_quantity


def _serialize_value(value: Any) -> Any:
    if is_quantity(value):
        return {"value": value.magnitude, "units": str(value.units)}
    return value


@dataclass(frozen=True)
class Parameter:
    """A single physical, empirical, or numerical model parameter."""

    name: str
    symbol: str
    value: Any | None
    units: str
    uncertainty: Any | None
    source: str | None
    confidence_level: ConfidenceLevel
    notes: str
    measurement_method: str | None = None
    validity_range: str | None = None

    def __post_init__(self) -> None:
        if not has_text(self.name):
            raise ValueError("Parameter.name must be provided.")
        if not has_text(self.symbol):
            raise ValueError("Parameter.symbol must be provided.")
        if not has_text(self.units):
            raise UnitError(f"Parameter {self.symbol} requires explicit units.")
        Q_(1, self.units)
        if self.value is not None and is_quantity(self.value):
            self.value.to(self.units)
        if self.uncertainty is not None and is_quantity(self.uncertainty):
            self.uncertainty.to(self.units)

    @property
    def is_unknown(self) -> bool:
        return self.value is None

    @property
    def quantity(self) -> Quantity | None:
        if self.value is None:
            return None
        if is_quantity(self.value):
            return self.value.to(self.units)
        return Q_(self.value, self.units)

    @property
    def uncertainty_quantity(self) -> Quantity | None:
        if self.uncertainty is None:
            return None
        if is_quantity(self.uncertainty):
            return self.uncertainty.to(self.units)
        if isinstance(self.uncertainty, (int, float)):
            return Q_(self.uncertainty, self.units)
        return None

    def validate_provenance(self, allow_unsourced_for_testing: bool = False) -> None:
        if allow_unsourced_for_testing:
            return
        if not has_text(self.source):
            raise ProvenanceError(
                f"Parameter {self.symbol} ({self.name}) is missing a source. "
                "Use allow_unsourced_for_testing=True only for explicit tests."
            )

    def validate_value(self) -> None:
        if self.value is None:
            raise UnknownParameterError(
                f"Parameter {self.symbol} ({self.name}) is explicitly unknown."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "value": _serialize_value(self.value),
            "units": self.units,
            "uncertainty": _serialize_value(self.uncertainty),
            "source": self.source,
            "confidence_level": self.confidence_level,
            "notes": self.notes,
            "measurement_method": self.measurement_method,
            "validity_range": self.validity_range,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Parameter":
        value = data.get("value")
        if isinstance(value, dict) and "value" in value and "units" in value:
            value = Q_(value["value"], value["units"])
        uncertainty = data.get("uncertainty")
        if isinstance(uncertainty, dict) and "value" in uncertainty and "units" in uncertainty:
            uncertainty = Q_(uncertainty["value"], uncertainty["units"])
        return cls(
            name=str(data["name"]),
            symbol=str(data["symbol"]),
            value=value,
            units=str(data["units"]),
            uncertainty=uncertainty,
            source=data.get("source"),
            confidence_level=data.get("confidence_level", "unknown"),
            notes=str(data.get("notes", "")),
            measurement_method=data.get("measurement_method"),
            validity_range=data.get("validity_range"),
        )


@dataclass
class ParameterSet:
    """A provenance-preserving collection of named parameters."""

    parameters: dict[str, Parameter] = field(default_factory=dict)

    def __init__(self, parameters: Iterable[Parameter] | Mapping[str, Parameter] | None = None):
        self.parameters = {}
        if parameters is None:
            return
        if isinstance(parameters, Mapping):
            iterable = parameters.values()
        else:
            iterable = parameters
        for parameter in iterable:
            self.add(parameter)

    def add(self, parameter: Parameter) -> None:
        if parameter.symbol in self.parameters:
            raise ValueError(f"Duplicate parameter symbol: {parameter.symbol}")
        self.parameters[parameter.symbol] = parameter

    def __iter__(self) -> Iterator[Parameter]:
        return iter(self.parameters.values())

    def __len__(self) -> int:
        return len(self.parameters)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self.parameters

    def get(self, symbol: str) -> Parameter:
        try:
            return self.parameters[symbol]
        except KeyError as exc:
            raise KeyError(f"Parameter {symbol!r} is not present.") from exc

    def require_quantity(self, symbol: str, expected_units: str | None = None) -> Quantity:
        parameter = self.get(symbol)
        parameter.validate_value()
        quantity = parameter.quantity
        if quantity is None:
            raise UnknownParameterError(f"Parameter {symbol} is explicitly unknown.")
        if expected_units is not None:
            return assert_compatible(quantity, expected_units, name=symbol)
        return quantity

    def missing_values(self) -> list[Parameter]:
        return [parameter for parameter in self if parameter.is_unknown]

    def missing_sources(self) -> list[Parameter]:
        return [parameter for parameter in self if not has_text(parameter.source)]

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_values: bool = True,
    ) -> None:
        for parameter in self:
            parameter.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
            if require_values:
                parameter.validate_value()
            Q_(1, parameter.units)

    def provenance_summary(self) -> dict[str, dict[str, str | None]]:
        return {
            parameter.symbol: {
                "name": parameter.name,
                "source": parameter.source,
                "confidence_level": parameter.confidence_level,
                "measurement_method": parameter.measurement_method,
                "validity_range": parameter.validity_range,
            }
            for parameter in self
        }

    def to_dict(self) -> dict[str, Any]:
        return {"parameters": [parameter.to_dict() for parameter in self]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ParameterSet":
        return cls(Parameter.from_dict(item) for item in data.get("parameters", []))

    def to_json(self, path: str | Path | None = None) -> str:
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True)
        if path is not None:
            Path(path).write_text(text + "\n", encoding="utf-8")
        return text

    @classmethod
    def from_json(cls, data_or_path: str | Path) -> "ParameterSet":
        text = str(data_or_path)
        if text.lstrip().startswith(("{", "[")):
            data = json.loads(text)
            return cls.from_dict(data)
        path = Path(data_or_path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(text)
        return cls.from_dict(data)

    def to_yaml(self, path: str | Path | None = None) -> str:
        import yaml

        text = yaml.safe_dump(self.to_dict(), sort_keys=True)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    @classmethod
    def from_yaml(cls, data_or_path: str | Path) -> "ParameterSet":
        import yaml

        text = str(data_or_path)
        if "\n" in text or text.lstrip().startswith(("parameters:", "{", "[")):
            data = yaml.safe_load(text)
            return cls.from_dict(data)
        path = Path(data_or_path)
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            data = yaml.safe_load(text)
        return cls.from_dict(data)


__all__ = ["Parameter", "ParameterSet"]
