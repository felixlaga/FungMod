"""Parameter parsing and merging helpers for human-editable configs."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, assert_compatible, is_quantity


class ParameterMergeError(ValueError):
    """Raised when two parameter sets define incompatible values."""


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


def merge_parameter_sets(parameter_sets: tuple[ParameterSet, ...] | list[ParameterSet]) -> ParameterSet:
    """Merge parameter sets while rejecting conflicting duplicate symbols."""

    merged: dict[str, Parameter] = {}
    for parameter_set in parameter_sets:
        for parameter in parameter_set:
            existing = merged.get(parameter.symbol)
            if existing is None:
                merged[parameter.symbol] = parameter
                continue
            if not _same_parameter(existing, parameter):
                raise ParameterMergeError(
                    f"Conflicting parameter definitions for symbol {parameter.symbol!r}."
                )
    return ParameterSet(merged.values())


def _same_parameter(left: Parameter, right: Parameter) -> bool:
    if left.symbol != right.symbol:
        return False
    if not _compatible_units(left.units, right.units):
        return False
    return (
        left.name == right.name
        and left.source == right.source
        and left.confidence_level == right.confidence_level
        and left.notes == right.notes
        and left.measurement_method == right.measurement_method
        and _same_value(left.value, right.value, left.units)
        and _same_value(left.uncertainty, right.uncertainty, left.units)
    )


def _compatible_units(left: str, right: str) -> bool:
    try:
        Q_(1, right).to(left)
    except Exception:
        return False
    return True


def _same_value(left: Any, right: Any, units: str) -> bool:
    if left is None or right is None:
        return left is None and right is None
    left_quantity = left if is_quantity(left) else Q_(left, units)
    right_quantity = right if is_quantity(right) else Q_(right, units)
    right_in_left_units = assert_compatible(right_quantity, str(left_quantity.units))
    left_values = np.asarray(left_quantity.magnitude, dtype=float)
    right_values = np.asarray(right_in_left_units.magnitude, dtype=float)
    return bool(np.allclose(left_values, right_values, rtol=1e-12, atol=1e-15))


__all__ = [
    "ParameterMergeError",
    "merge_parameter_sets",
    "parameter_from_config",
    "parameter_set_from_config",
]
