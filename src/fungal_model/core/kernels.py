"""Numeric kernel contracts shared by processes, modifiers, and compiled solvers.

A kernel is a plain-float closure that reproduces a unit-aware rate law after
every unit conversion has been resolved once at build time. Kernels carry no
chemistry or biology of their own: each process or modifier that offers one is
responsible for matching its own ``rate``/``activity`` arithmetic, including
the validation errors it raises for invalid states, and for returning the rate
in its own declared rate units. A process that offers no kernel is evaluated
through its unit-aware ``rate`` method instead, and that choice is recorded.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity

RateKernel = Callable[[float, np.ndarray], float]
"""Rate in the owner's rate units at time ``t`` for the numeric state vector ``y``."""


def conversion_factor(from_units: str, to_units: str, *, name: str = "quantity") -> float:
    """Multiplicative factor converting a magnitude in ``from_units`` to ``to_units``.

    Only multiplicative units are meaningful here; the compiled state vector
    never holds offset units such as degrees Celsius. Incompatible units raise
    :class:`fungal_model.core.units.UnitError` exactly as the unit-aware path.
    """

    return float(assert_compatible(Q_(1.0, from_units), to_units, name=name).magnitude)


def magnitude_in(quantity: Quantity, units: str, *, name: str) -> float:
    """Scalar magnitude of ``quantity`` expressed in ``units``."""

    value = np.asarray(assert_compatible(require_quantity(quantity, name=name), units, name=name).magnitude, dtype=float)
    if value.ndim != 0:
        raise ValueError(f"{name} must be a scalar quantity for a numeric kernel.")
    return float(value)


@dataclass(frozen=True)
class KernelContext:
    """Build-time information a process or modifier needs to compile a kernel.

    ``state_index`` maps every model state to its position in the numeric
    state vector and ``state_units`` records the units that vector carries.
    ``time_units`` is the integration time unit. The context never changes
    during a run; environment and geometry are static entities.
    """

    state_index: Mapping[str, int]
    state_units: Mapping[str, str]
    time_units: str
    parameters: ParameterSet
    environment: Any = None
    geometry: Any = None

    def state_slot(self, name: str, units: str) -> tuple[int, float]:
        """Return the vector index of ``name`` and the factor converting it to ``units``."""

        if name not in self.state_index:
            raise KeyError(f"State {name!r} is not part of the compiled model.")
        return self.state_index[name], conversion_factor(self.state_units[name], units, name=name)

    def parameter(self, symbol: str, units: str) -> float:
        """Scalar parameter value in ``units`` with the same provenance checks as ``require_quantity``."""

        return magnitude_in(self.parameters.require_quantity(symbol, units), units, name=symbol)


__all__ = ["KernelContext", "RateKernel", "conversion_factor", "magnitude_in"]
