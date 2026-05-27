"""Parameter parsing helpers for human-editable configs."""

from __future__ import annotations

from typing import Any, Mapping

from fungal_model.core.parameters import Parameter, ParameterSet


def parameter_from_config(data: Mapping[str, Any]) -> Parameter:
    """Create a Parameter from a config parameter mapping."""

    return Parameter(
        name=str(data["name"]),
        symbol=str(data["symbol"]),
        value=data.get("value"),
        units=str(data["units"]),
        uncertainty=data.get("uncertainty"),
        source=data.get("source"),
        confidence_level=data.get("confidence_level", "unknown"),
        notes=str(data.get("notes", "")),
        measurement_method=data.get("measurement_method"),
    )


def parameter_set_from_config(data: Mapping[str, Any]) -> ParameterSet:
    return ParameterSet(parameter_from_config(parameter) for parameter in data.get("parameters", []) or [])


__all__ = ["parameter_from_config", "parameter_set_from_config"]
