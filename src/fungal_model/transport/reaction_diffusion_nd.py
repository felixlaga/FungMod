"""Method-of-lines reaction-diffusion engine for uniform 2D and 3D Cartesian grids."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from fungal_model import __version__
from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.transport.cartesian import (
    BoundaryConditionsND,
    UniformCartesianGrid,
    finite_volume_laplacian_nd,
    spatial_integral_nd,
)


@dataclass
class ReactionDiffusionResultND:
    """Unit-bearing result for a uniform Cartesian 2D or 3D simulation."""

    time: Quantity
    fields: dict[str, Quantity]
    initial_fields: dict[str, Quantity]
    grid: UniformCartesianGrid
    success: bool
    message: str
    solver_settings: SolverSettings
    parameters: ParameterSet
    assumptions: list[Assumption]
    reactions: list[Reaction]
    boundary_conditions: dict[str, BoundaryConditionsND]
    diffusion_symbols: dict[str, str | None]
    model_version: str
    solver_metadata: dict[str, Any] = field(default_factory=dict)

    def field_at_final_time(self, name: str) -> Quantity:
        values = self.fields[name]
        return Q_(np.asarray(values.magnitude)[-1], values.units)

    def spatial_integral(self, name: str) -> Quantity:
        return spatial_integral_nd(self.field_at_final_time(name), grid=self.grid)

    def spatial_average(self, name: str) -> Quantity:
        return self.spatial_integral(name) / self.grid.total_measure

    def results_summary(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "grid": self.grid.to_dict(),
            "time": {
                "units": str(self.time.units),
                "initial": float(np.asarray(self.time.magnitude).flat[0]),
                "final": float(np.asarray(self.time.magnitude).flat[-1]),
            },
            "fields": {
                name: {
                    "units": str(values.units),
                    "initial_minimum": float(np.min(np.asarray(values.magnitude)[0])),
                    "initial_maximum": float(np.max(np.asarray(values.magnitude)[0])),
                    "final_minimum": float(np.min(np.asarray(values.magnitude)[-1])),
                    "final_maximum": float(np.max(np.asarray(values.magnitude)[-1])),
                }
                for name, values in self.fields.items()
            },
            "solver_metadata": dict(self.solver_metadata),
        }


@dataclass
class ReactionDiffusionEngineND:
    """Uniform-grid finite-volume reaction-diffusion engine for 2D or 3D."""

    grid: UniformCartesianGrid
    field_units: Mapping[str, str]
    boundary_conditions: Mapping[str, BoundaryConditionsND]
    parameters: ParameterSet
    diffusion_symbols: Mapping[str, str | None]
    reactions: Sequence[Reaction] = field(default_factory=tuple)
    assumptions: Sequence[Assumption] = field(default_factory=tuple)
    model_version: str = __version__
    allow_unsourced_for_testing: bool = False

    def __post_init__(self) -> None:
        self.field_units = dict(self.field_units)
        self.boundary_conditions = dict(self.boundary_conditions)
        self.diffusion_symbols = dict(self.diffusion_symbols)
        self.reactions = tuple(self.reactions)
        self.assumptions = tuple(self.assumptions)
        if not self.field_units:
            raise ValueError("ReactionDiffusionEngineND requires at least one field.")
        expected = set(self.field_units)
        for label, actual in (
            ("boundary_conditions", set(self.boundary_conditions)),
            ("diffusion_symbols", set(self.diffusion_symbols)),
        ):
            if actual != expected:
                raise ValueError(
                    f"{label} must exactly match field_units; missing "
                    f"{sorted(expected - actual)}, extra {sorted(actual - expected)}."
                )
        for name, boundaries in self.boundary_conditions.items():
            if len(boundaries.axes) != self.grid.ndim:
                raise ValueError(
                    f"Boundary conditions for {name!r} do not match grid dimensionality."
                )
        for reaction in self.reactions:
            missing = reaction.species.difference(expected)
            if missing:
                raise ValueError(
                    f"Reaction {reaction.name!r} references unknown Cartesian fields: {sorted(missing)}."
                )

    def _validate_ready(self) -> None:
        self.parameters.validate(
            allow_unsourced_for_testing=self.allow_unsourced_for_testing,
            require_values=True,
        )
        for length in self.grid.axis_lengths:
            length.validate_provenance(
                allow_unsourced_for_testing=self.allow_unsourced_for_testing
            )
            length.validate_value()
        for reaction in self.reactions:
            reaction.validate_provenance(
                allow_unsourced_for_testing=self.allow_unsourced_for_testing
            )
        for name, symbol in self.diffusion_symbols.items():
            if symbol is None:
                continue
            coefficient = self.parameters.require_quantity(symbol, "meter ** 2 / second")
            value = float(coefficient.magnitude)
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"Diffusion coefficient for {name!r} must be finite and nonnegative.")

    def simulate(
        self,
        *,
        initial_fields: Mapping[str, Quantity],
        t_span: tuple[Quantity, Quantity],
        t_eval: Quantity | None = None,
        solver_settings: SolverSettings | Mapping[str, Any] | None = None,
    ) -> ReactionDiffusionResultND:
        """Run one explicit 2D or 3D Cartesian reaction-diffusion model."""

        self._validate_ready()
        expected = set(self.field_units)
        actual = set(initial_fields)
        if actual != expected:
            raise ValueError(
                f"Initial fields mismatch; missing {sorted(expected - actual)}, "
                f"extra {sorted(actual - expected)}."
            )
        names = tuple(self.field_units)
        initial_arrays: dict[str, np.ndarray] = {}
        for name in names:
            quantity = assert_compatible(initial_fields[name], self.field_units[name], name=name)
            values = np.asarray(quantity.magnitude, dtype=float)
            if values.shape != self.grid.shape:
                raise ValueError(
                    f"Initial field {name!r} shape {values.shape} does not match {self.grid.shape}."
                )
            if not np.isfinite(values).all() or np.any(values < 0.0):
                raise ValueError(f"Initial field {name!r} must be finite and nonnegative.")
            initial_arrays[name] = values

        settings = (
            SolverSettings(**solver_settings)
            if isinstance(solver_settings, Mapping)
            else solver_settings or SolverSettings()
        )
        start = require_quantity(t_span[0], name="t_span[0]")
        finish = require_quantity(t_span[1], name="t_span[1]")
        time_units = str(finish.units)
        span = (
            float(assert_compatible(start, time_units, name="t_span[0]").magnitude),
            float(assert_compatible(finish, time_units, name="t_span[1]").magnitude),
        )
        if span[1] <= span[0]:
            raise ValueError("t_span final time must be greater than start time.")
        evaluation_times = None
        if t_eval is not None:
            evaluation_times = np.asarray(
                assert_compatible(t_eval, time_units, name="t_eval").magnitude,
                dtype=float,
            )
        cells_per_field = int(np.prod(self.grid.shape))
        y0 = np.concatenate([initial_arrays[name].reshape(-1) for name in names])

        def rhs(time_value: float, vector: np.ndarray) -> np.ndarray:
            state = {
                name: Q_(
                    vector[index * cells_per_field : (index + 1) * cells_per_field].reshape(
                        self.grid.shape
                    ),
                    self.field_units[name],
                )
                for index, name in enumerate(names)
            }
            derivatives = {
                name: Q_(np.zeros(self.grid.shape), f"{units} / {time_units}")
                for name, units in self.field_units.items()
            }
            for name, symbol in self.diffusion_symbols.items():
                if symbol is None:
                    continue
                coefficient = self.parameters.require_quantity(symbol, f"meter ** 2 / {time_units}")
                diffusion = coefficient * finite_volume_laplacian_nd(
                    state[name],
                    grid=self.grid,
                    boundary_conditions=self.boundary_conditions[name],
                )
                derivatives[name] += assert_compatible(
                    diffusion,
                    f"{self.field_units[name]} / {time_units}",
                    name=f"{name} diffusion contribution",
                )
            time = Q_(time_value, time_units)
            for reaction in self.reactions:
                rate = reaction.rate(state, time, self.parameters)
                if np.asarray(rate.magnitude).shape != self.grid.shape:
                    raise ValueError(
                        f"Local Cartesian reaction {reaction.name!r} must return shape {self.grid.shape}."
                    )
                for name in reaction.species:
                    coefficient = reaction.stoichiometric_coefficient(name)
                    if coefficient == 0.0:
                        continue
                    derivatives[name] += coefficient * assert_compatible(
                        rate,
                        f"{self.field_units[name]} / {time_units}",
                        name=f"{reaction.name} contribution to {name}",
                    )
            return np.concatenate(
                [np.asarray(derivatives[name].magnitude, dtype=float).reshape(-1) for name in names]
            )

        solve_kwargs: dict[str, Any] = {
            "method": settings.method,
            "rtol": settings.rtol,
            "atol": settings.atol,
        }
        if settings.max_step is not None:
            solve_kwargs["max_step"] = float(
                assert_compatible(settings.max_step, time_units, name="max_step").magnitude
            )
        solution = solve_ivp(rhs, span, y0, t_eval=evaluation_times, **solve_kwargs)
        fields = {
            name: Q_(
                solution.y[index * cells_per_field : (index + 1) * cells_per_field].T.reshape(
                    (solution.t.size, *self.grid.shape)
                ),
                self.field_units[name],
            )
            for index, name in enumerate(names)
        }
        assumptions = list(self.assumptions)
        known = {assumption.name for assumption in assumptions}
        for reaction in self.reactions:
            for assumption in reaction.assumptions:
                if assumption.name not in known:
                    assumptions.append(assumption)
                    known.add(assumption.name)
        return ReactionDiffusionResultND(
            time=Q_(solution.t, time_units),
            fields=fields,
            initial_fields={
                name: Q_(values.copy(), self.field_units[name])
                for name, values in initial_arrays.items()
            },
            grid=self.grid,
            success=bool(solution.success),
            message=str(solution.message),
            solver_settings=settings,
            parameters=self.parameters,
            assumptions=assumptions,
            reactions=list(self.reactions),
            boundary_conditions=dict(self.boundary_conditions),
            diffusion_symbols=dict(self.diffusion_symbols),
            model_version=self.model_version,
            solver_metadata={
                "status": int(solution.status),
                "nfev": int(solution.nfev),
                "njev": None if solution.njev is None else int(solution.njev),
                "nlu": None if solution.nlu is None else int(solution.nlu),
                "ndim": self.grid.ndim,
                "shape": list(self.grid.shape),
            },
        )


__all__ = ["ReactionDiffusionEngineND", "ReactionDiffusionResultND"]
