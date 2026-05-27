"""Well-mixed ODE solver for assembled process models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.integrate import solve_ivp

from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.results import SimulationResult

if TYPE_CHECKING:
    from fungal_model.processes.assembly import AssembledModel


@dataclass(frozen=True)
class RunRequest:
    """Inputs required to run an assembled process model."""

    initial_state: Mapping[str, Quantity]
    t_span: tuple[Quantity, Quantity]
    t_eval: Quantity | None = None
    validators: tuple[Any, ...] = ()
    label: str = "toy"
    name: str = "assembled_model"


class ProcessODESolver:
    """Integrate a well-mixed assembled process model."""

    backend_name = "scipy.solve_ivp"

    def __init__(self, model: AssembledModel) -> None:
        self.model = model

    def run(self, request: RunRequest) -> SimulationResult:
        self._validate_geometry_supported()
        state_units = _state_units(self.model)
        state_names = tuple(state_units)
        time_units = _time_units(request.t_span)
        t_span_numeric = _numeric_t_span(request.t_span, time_units)
        t_eval_numeric = _numeric_t_eval(request.t_eval, time_units)
        y0 = _initial_vector(request.initial_state, state_units, state_names)
        settings = self.model.solver_settings

        def rhs(t: float, y: np.ndarray) -> list[float]:
            state = _state_from_vector(y, state_units, state_names)
            time = Q_(t, time_units)
            derivatives = {
                name: Q_(0.0, f"{units} / {time_units}")
                for name, units in state_units.items()
            }
            for process in self.model.processes:
                rate = process.rate(
                    state,
                    time,
                    self.model.parameters,
                    self.model.context.environment,
                    self.model.context.geometry,
                )
                for species, contribution in process.contributions(rate).items():
                    if species not in derivatives:
                        raise ValueError(
                            f"Process {process.name!r} contributed to unknown state {species!r}."
                        )
                    target_units = f"{state_units[species]} / {time_units}"
                    derivatives[species] += assert_compatible(
                        contribution,
                        target_units,
                        name=f"{process.name} contribution to {species}",
                    )
            return [
                float(assert_compatible(derivatives[name], f"{state_units[name]} / {time_units}").magnitude)
                for name in state_names
            ]

        solution = solve_ivp(
            rhs,
            t_span_numeric,
            y0,
            t_eval=t_eval_numeric,
            method=settings.method,
            rtol=settings.rtol,
            atol=settings.atol,
            **_optional_solver_kwargs(settings, time_units),
        )
        states = {
            name: Q_(solution.y[index], state_units[name])
            for index, name in enumerate(state_names)
        }
        time = Q_(solution.t, time_units)
        process_rates = _record_process_rates(
            self.model,
            time,
            states,
        )
        result = SimulationResult(
            time=time,
            states=states,
            parameters=self.model.parameters,
            assumptions=tuple(self.model.assumptions),
            solver_settings=settings,
            process_rates=process_rates,
            validation_results=(),
            warnings=(),
            solver_metadata={
                "backend": self.backend_name,
                "method": settings.method,
                "success": bool(solution.success),
                "message": str(solution.message),
                "status": int(solution.status),
                "nfev": int(solution.nfev),
                "njev": None if solution.njev is None else int(solution.njev),
                "nlu": None if solution.nlu is None else int(solution.nlu),
            },
            assembly_report=self.model.assembly_report,
            name=request.name,
            label=request.label,
            source_result_summary={
                "success": bool(solution.success),
                "message": str(solution.message),
            },
        )
        validators = tuple(self.model.validators) + tuple(request.validators)
        if validators:
            result.validate(validators)
        return result

    def _validate_geometry_supported(self) -> None:
        geometry = self.model.context.geometry
        if geometry is None:
            return
        geometry_type = getattr(geometry, "geometry_type", None)
        if geometry_type != "well_mixed":
            raise ValueError(
                f"ProcessODESolver supports only well_mixed geometry; received {geometry_type!r}."
            )


def _state_units(model: AssembledModel) -> dict[str, str]:
    units: dict[str, str] = {}
    for spec in model.state_variables:
        if spec.name in units and units[spec.name] != spec.units:
            raise ValueError(f"Conflicting state units for {spec.name!r}.")
        units[spec.name] = spec.units
    if not units:
        raise ValueError("Assembled model has no state variables.")
    return units


def _time_units(t_span: tuple[Quantity, Quantity]) -> str:
    return str(require_quantity(t_span[1], name="t_span[1]").units)


def _numeric_t_span(t_span: tuple[Quantity, Quantity], time_units: str) -> tuple[float, float]:
    start = require_quantity(t_span[0], name="t_span[0]")
    stop = require_quantity(t_span[1], name="t_span[1]")
    numeric = (
        float(assert_compatible(start, time_units, name="t_span[0]").magnitude),
        float(assert_compatible(stop, time_units, name="t_span[1]").magnitude),
    )
    if numeric[1] <= numeric[0]:
        raise ValueError("t_span final time must be greater than start time.")
    return numeric


def _numeric_t_eval(t_eval: Quantity | None, time_units: str) -> np.ndarray | None:
    if t_eval is None:
        return None
    values = np.asarray(
        assert_compatible(require_quantity(t_eval, name="t_eval"), time_units, name="t_eval").magnitude,
        dtype=float,
    )
    if values.ndim != 1:
        raise ValueError("t_eval must be one-dimensional.")
    return values


def _initial_vector(
    initial_state: Mapping[str, Quantity],
    state_units: Mapping[str, str],
    state_names: Sequence[str],
) -> list[float]:
    expected = set(state_names)
    received = set(initial_state)
    if expected != received:
        missing = sorted(expected.difference(received))
        extra = sorted(received.difference(expected))
        raise ValueError(f"Initial state mismatch. Missing: {missing}; extra: {extra}.")
    return [
        float(
            assert_compatible(
                require_quantity(initial_state[name], name=f"initial_state[{name}]"),
                state_units[name],
                name=name,
            ).magnitude
        )
        for name in state_names
    ]


def _state_from_vector(
    y: np.ndarray,
    state_units: Mapping[str, str],
    state_names: Sequence[str],
) -> dict[str, Quantity]:
    return {
        name: Q_(value, state_units[name])
        for name, value in zip(state_names, y, strict=True)
    }


def _record_process_rates(
    model: AssembledModel,
    time: Quantity,
    states: Mapping[str, Quantity],
) -> dict[str, Quantity]:
    rates: dict[str, list[Quantity]] = {process.name: [] for process in model.processes}
    for index, time_value in enumerate(np.asarray(time.magnitude, dtype=float)):
        state = {
            name: Q_(np.asarray(quantity.magnitude, dtype=float)[index], quantity.units)
            for name, quantity in states.items()
        }
        current_time = Q_(time_value, time.units)
        for process in model.processes:
            rates[process.name].append(
                process.rate(
                    state,
                    current_time,
                    model.parameters,
                    model.context.environment,
                    model.context.geometry,
                )
            )
    return {
        name: Q_(
            np.asarray([rate.to(rate_values[0].units).magnitude for rate in rate_values], dtype=float),
            rate_values[0].units,
        )
        for name, rate_values in rates.items()
        if rate_values
    }


def _optional_solver_kwargs(settings: SolverSettings, time_units: str) -> dict[str, Any]:
    if settings.max_step is None:
        return {}
    return {
        "max_step": float(
            assert_compatible(settings.max_step, time_units, name="max_step").magnitude
        )
    }


__all__ = ["ProcessODESolver", "RunRequest"]
