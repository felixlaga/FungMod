"""Shared numerical contracts; no chemical or biological assumptions.

SciPy's error control is local: ``atol_i + rtol * abs(y_i)``. It is not an
empirical uncertainty estimate or a guarantee of global trajectory accuracy.
https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from fungal_model.core.units import Quantity, assert_compatible, require_quantity


class IntegrationError(ValueError):
    """A numerical trajectory failed, was incomplete, or contained nonfinite values."""


def _positive_scalar(value: Any, name: str) -> float:
    array = np.asarray(value, dtype=float)
    if array.ndim or not np.isfinite(array) or array <= 0:
        raise ValueError(f"{name} must be a finite positive scalar.")
    return float(array)


JACOBIAN_FINITE_DIFFERENCE_BY_BACKEND = "finite_difference_by_backend"
JACOBIAN_COMPILED = "compiled"
JACOBIAN_OPTIONS = frozenset({JACOBIAN_FINITE_DIFFERENCE_BY_BACKEND, JACOBIAN_COMPILED})
IMPLICIT_METHODS = frozenset({"LSODA", "BDF", "Radau"})


@dataclass(frozen=True)
class SolverSettings:
    """Recorded integration controls with optional unit-bearing per-state atol.

    A scalar atol retains the historical meaning (each state's numeric units).
    A mapping must cover every state exactly, using explicit compatible units;
    spatial engines repeat each field tolerance over its cells.
    """

    method: str = "LSODA"
    rtol: float = 1e-8
    atol: float | Mapping[str, Quantity] = 1e-10
    max_step: Quantity | None = None
    first_step: Quantity | None = None
    #: How implicit methods obtain the Jacobian: ``finite_difference_by_backend``
    #: (scipy differentiates the right-hand side) or ``compiled`` (the compiled
    #: model assembles it from per-process gradient kernels, analytic where a
    #: process offers one and central finite differences otherwise). Explicit
    #: methods ignore it. Only the compiled process core honours ``compiled``.
    jacobian: str = JACOBIAN_FINITE_DIFFERENCE_BY_BACKEND

    def __post_init__(self) -> None:
        if self.method not in {"LSODA", "BDF", "Radau", "DOP853", "RK45", "RK23"}:
            raise ValueError(f"Unsupported integration method: {self.method!r}.")
        if self.jacobian not in JACOBIAN_OPTIONS:
            raise ValueError(f"Unsupported jacobian option: {self.jacobian!r}; choose one of {sorted(JACOBIAN_OPTIONS)}.")
        if not 100 * np.finfo(float).eps <= _positive_scalar(self.rtol, "rtol") < 1:
            raise ValueError("rtol must be at least 100 machine epsilons and less than one.")
        if isinstance(self.atol, Mapping):
            if not self.atol:
                raise ValueError("Per-state atol must not be empty.")
            for name, value in self.atol.items():
                _positive_scalar(require_quantity(value, name=f"atol[{name}]").magnitude, f"atol[{name}]")
        else:
            _positive_scalar(self.atol, "atol")
        for name in ("max_step", "first_step"):
            value = getattr(self, name)
            if value is not None:
                _positive_scalar(assert_compatible(require_quantity(value, name=name), "second").magnitude, name)

    def absolute_tolerances(self, state_units: Mapping[str, str], *, cells: int = 1) -> float | np.ndarray:
        if not isinstance(self.atol, Mapping):
            return float(self.atol)
        if set(self.atol) != set(state_units):
            raise ValueError("Per-state atol must exactly cover the integrated state names.")
        return np.repeat([
            _positive_scalar(assert_compatible(self.atol[name], units, name=f"atol[{name}]").magnitude,
                             f"atol[{name}]")
            for name, units in state_units.items()
        ], cells)

    def scipy_options(self, state_units: Mapping[str, str], time_units: str, *, cells: int = 1) -> dict[str, Any]:
        options = {"method": self.method, "rtol": self.rtol,
                   "atol": self.absolute_tolerances(state_units, cells=cells)}
        for name in ("max_step", "first_step"):
            value = getattr(self, name)
            if value is not None:
                options[name] = _positive_scalar(assert_compatible(value, time_units, name=name).magnitude, name)
        return options

    def to_dict(self) -> dict[str, Any]:
        def quantity(value: Quantity) -> dict[str, Any]:
            return {"value": float(value.magnitude), "units": str(value.units)}
        result = {"method": self.method, "rtol": self.rtol,
                  "atol": ({name: quantity(value) for name, value in self.atol.items()}
                           if isinstance(self.atol, Mapping) else self.atol),
                  "max_step": None if self.max_step is None else quantity(self.max_step)}
        # Keep old scalar-settings serialization byte-for-byte compatible.
        if self.first_step is not None:
            result["first_step"] = quantity(self.first_step)
        if self.jacobian != JACOBIAN_FINITE_DIFFERENCE_BY_BACKEND:
            result["jacobian"] = self.jacobian
        return result

    @property
    def uses_jacobian(self) -> bool:
        """Whether the chosen method consumes a Jacobian at all."""

        return self.method in IMPLICIT_METHODS


def solve_checked(fun, t_span, y0, *, t_eval=None, **options):
    """Integrate a complete finite trajectory or raise; never return a partial run.

    No clipping, fallback solver, or tolerance relaxation is performed. Signed
    states are allowed: positivity is a model-specific constraint, not a generic
    numerical assumption. Terminal events are intentionally outside this API.
    """
    span = np.asarray(t_span, dtype=float)
    initial = np.asarray(y0, dtype=float)
    if span.shape != (2,) or not np.isfinite(span).all() or span[1] <= span[0]:
        raise IntegrationError("t_span must contain two finite increasing times.")
    if initial.ndim != 1 or not initial.size or not np.isfinite(initial).all():
        raise IntegrationError("Initial states must be a nonempty finite vector.")
    grid = None if t_eval is None else np.asarray(t_eval, dtype=float)
    if grid is not None and (grid.ndim != 1 or not grid.size or not np.isfinite(grid).all()
                             or np.any(np.diff(grid) <= 0) or grid[0] < span[0] or grid[-1] > span[1]):
        raise IntegrationError("t_eval must be nonempty, finite, strictly increasing and inside t_span.")
    if "events" in options:
        raise IntegrationError("Terminal/partial trajectories are not supported by solve_checked.")

    def checked_rhs(t, y):
        values = np.asarray(fun(t, y), dtype=float)
        if values.shape != initial.shape or not np.isfinite(values).all():
            raise IntegrationError(f"RHS returned invalid shape or nonfinite derivatives at time {t}.")
        return values

    result = solve_ivp(checked_rhs, tuple(span), initial, t_eval=grid, **options)
    values, times = np.asarray(result.y), np.asarray(result.t)
    complete = (result.success and result.status == 0 and times.ndim == 1 and times.size > 0
                and values.shape == (initial.size, times.size)
                and np.isfinite(values).all() and np.isfinite(times).all())
    if grid is not None:
        complete = complete and np.array_equal(times, grid)
    else:
        complete = complete and times[-1] == span[1]
    if not complete:
        raise IntegrationError(f"Integration failed or returned incomplete/nonfinite states: {result.message}")
    return result


__all__ = [
    "IMPLICIT_METHODS",
    "JACOBIAN_COMPILED",
    "JACOBIAN_FINITE_DIFFERENCE_BY_BACKEND",
    "JACOBIAN_OPTIONS",
    "IntegrationError",
    "SolverSettings",
    "solve_checked",
]
