"""Shared unit registry and helpers.

All scientific quantities that enter equations should be represented as
``pint.Quantity`` objects. Functions in this module deliberately reject naked
numbers where a unit-bearing physical quantity is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

import pint

ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
Q_: Any = ureg.Quantity
if TYPE_CHECKING:
    Quantity: TypeAlias = pint.Quantity[Any]
else:
    Quantity = pint.Quantity


class UnitError(ValueError):
    """Raised when a value lacks units or has incompatible dimensions."""


def is_quantity(value: Any) -> bool:
    """Return ``True`` when *value* behaves like a pint quantity."""

    return hasattr(value, "units") and hasattr(value, "to") and hasattr(value, "magnitude")


def require_quantity(value: Any, name: str = "value") -> Quantity:
    """Require a unit-bearing quantity.

    This helper is used at scientific API boundaries. Tests may construct
    quantities with arbitrary values, but the value must still carry units.
    """

    if not is_quantity(value):
        raise UnitError(f"{name} must be a pint Quantity with explicit units.")
    return value


def quantity_from_value(value: Any, units: str, name: str = "value") -> Quantity:
    """Create or convert a quantity from a value and unit string."""

    if units is None or str(units).strip() == "":
        raise UnitError(f"{name} requires an explicit unit string.")
    if is_quantity(value):
        return value.to(units)
    return Q_(value, units)


def assert_compatible(quantity: Any, expected_units: str, name: str = "quantity") -> Quantity:
    """Return *quantity* converted to *expected_units*, or raise on mismatch."""

    q = require_quantity(quantity, name=name)
    try:
        return q.to(expected_units)
    except pint.DimensionalityError as exc:
        raise UnitError(
            f"{name} has units {q.units!s}, which are incompatible with {expected_units}."
        ) from exc


def units_are_compatible(units: str, expected_units: str) -> bool:
    """Check whether two unit strings have compatible dimensionality."""

    try:
        Q_(1, units).to(expected_units)
        return True
    except pint.DimensionalityError:
        return False


__all__ = [
    "Q_",
    "Quantity",
    "UnitError",
    "assert_compatible",
    "is_quantity",
    "quantity_from_value",
    "require_quantity",
    "ureg",
    "units_are_compatible",
]
