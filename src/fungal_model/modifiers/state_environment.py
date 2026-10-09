"""Explicit state-driven environment reads; no simultaneous static authority."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
import math
import numpy as np
from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible


def state_environment_value(
    *, state: Mapping[str, Quantity] | None, state_source: str, environment: Any, field: str, units: str
) -> Quantity:
    if environment is not None and getattr(environment, field, None) is not None:
        raise ValueError(f"{field} cannot be driven by both a static value and state_source.")
    if state is None or state_source not in state:
        raise ValueError(f"{field} requires state_source {state_source!r}.")
    value = assert_compatible(state[state_source], units, name=field)
    if not math.isfinite(float(value.magnitude)):
        raise ValueError(f"{field} must be finite.")
    return value


def check_state_environment(*, environment: Any, field: str) -> None:
    if environment is not None and getattr(environment, field, None) is not None:
        raise ValueError(f"{field} cannot be driven by both a static value and state_source.")


def state_activity_quantity(
    modifier: Any, *, state_source: str, state: Mapping[str, Quantity] | None,
    parameters: ParameterSet, environment: Any,
) -> Quantity:
    """Use the same scalar law and refusals for native and compiled dynamic pH."""
    ph = state_environment_value(
        state=state, state_source=state_source, environment=environment, field="ph", units="dimensionless"
    )
    # These activity kernels do not depend on time; the time unit is unused.
    context = KernelContext({state_source: 0}, {state_source: "dimensionless"}, "second", parameters, environment)
    kernel = modifier.compile_activity(context)
    return Q_(kernel(0.0, np.array([float(ph.magnitude)])), "dimensionless")
