"""One-dimensional reaction-diffusion engine.

This Stage 8 engine uses method-of-lines finite volumes on a cell-centered 1D
grid. Diffusion is explicit in the model configuration through per-field
diffusion-coefficient parameter symbols and per-field boundary conditions.
Local reactions reuse the existing unit-aware ``Reaction`` class.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.integrate import solve_ivp

from fungal_model import __version__
from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.transport.diffusion import finite_volume_laplacian_1d, spatial_integral_1d
from fungal_model.transport.geometry import BoundaryConditions1D, UniformGrid1D


def _quantity_array_summary(quantity: Quantity) -> dict[str, Any]:
    values = np.asarray(quantity.magnitude, dtype=float)
    return {
        "units": str(quantity.units),
        "initial_minimum": float(np.min(values[0])),
        "initial_maximum": float(np.max(values[0])),
        "final_minimum": float(np.min(values[-1])),
        "final_maximum": float(np.max(values[-1])),
    }


@dataclass
class ReactionDiffusionResult1D:
    """Unit-bearing output from a 1D reaction-diffusion simulation."""

    time: Quantity
    fields: dict[str, Quantity]
    initial_fields: dict[str, Quantity]
    grid: UniformGrid1D
    success: bool
    message: str
    solver_settings: SolverSettings
    parameters: ParameterSet
    assumptions: list[Assumption]
    reactions: list[Reaction]
    boundary_conditions: dict[str, BoundaryConditions1D]
    diffusion_symbols: dict[str, str | None]
    model_version: str
    solver_metadata: dict[str, Any] = field(default_factory=dict)

    def field_at_final_time(self, name: str) -> Quantity:
        field_values = self.fields[name]
        return Q_(np.asarray(field_values.magnitude)[-1], field_values.units)

    def spatial_integral(self, name: str) -> Quantity:
        return spatial_integral_1d(self.field_at_final_time(name), cell_width=self.grid.cell_width)

    def spatial_average(self, name: str) -> Quantity:
        return self.spatial_integral(name) / self.grid.length.quantity

    def results_summary(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "time": {
                "units": str(self.time.units),
                "initial": float(np.asarray(self.time.magnitude).flat[0]),
                "final": float(np.asarray(self.time.magnitude).flat[-1]),
            },
            "fields": {
                name: _quantity_array_summary(quantity)
                for name, quantity in self.fields.items()
            },
            "solver_metadata": self.solver_metadata,
        }


@dataclass
class ReactionDiffusionRecord:
    """Serializable record for spatial simulations."""

    timestamp: str
    model_version: str
    grid: dict[str, Any]
    boundary_conditions: dict[str, Any]
    diffusion_symbols: dict[str, str | None]
    parameters: dict[str, Any]
    assumptions: list[dict[str, Any]]
    solver_settings: dict[str, Any]
    results_summary: dict[str, Any]
    validation_summary: dict[str, Any]

    @classmethod
    def from_result(
        cls,
        result: ReactionDiffusionResult1D,
        validation_summary: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    ) -> "ReactionDiffusionRecord":
        if isinstance(validation_summary, Mapping):
            validation_data = dict(validation_summary)
        else:
            validation_data = {"validations": list(validation_summary)}
        return cls(
            timestamp=datetime.now(UTC).isoformat(),
            model_version=result.model_version,
            grid=result.grid.to_dict(),
            boundary_conditions={
                name: boundaries.to_dict()
                for name, boundaries in result.boundary_conditions.items()
            },
            diffusion_symbols=dict(result.diffusion_symbols),
            parameters=result.parameters.to_dict(),
            assumptions=[assumption.to_dict() for assumption in result.assumptions],
            solver_settings=result.solver_settings.to_dict(),
            results_summary=result.results_summary(),
            validation_summary=validation_data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "model_version": self.model_version,
            "grid": self.grid,
            "boundary_conditions": self.boundary_conditions,
            "diffusion_symbols": self.diffusion_symbols,
            "parameters": self.parameters,
            "assumptions": self.assumptions,
            "solver_settings": self.solver_settings,
            "results_summary": self.results_summary,
            "validation_summary": self.validation_summary,
        }

    def to_json(self, path: str | Path | None = None) -> str:
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True)
        if path is not None:
            Path(path).write_text(text + "\n", encoding="utf-8")
        return text


@dataclass
class ReactionDiffusionEngine1D:
    """Deterministic 1D reaction-diffusion method-of-lines engine."""

    grid: UniformGrid1D
    field_units: Mapping[str, str]
    boundary_conditions: Mapping[str, BoundaryConditions1D]
    parameters: ParameterSet
    reactions: Sequence[Reaction] = field(default_factory=list)
    diffusion_symbols: Mapping[str, str | None] = field(default_factory=dict)
    assumptions: Sequence[Assumption] = field(default_factory=list)
    model_version: str = __version__
    allow_unsourced_for_testing: bool = False

    def __post_init__(self) -> None:
        self.field_units = dict(self.field_units)
        self.boundary_conditions = dict(self.boundary_conditions)
        self.diffusion_symbols = dict(self.diffusion_symbols)
        self.reactions = list(self.reactions)
        self.assumptions = list(self.assumptions)
        if not self.field_units:
            raise ValueError("ReactionDiffusionEngine1D requires field_units.")
        missing_boundaries = set(self.field_units).difference(self.boundary_conditions)
        if missing_boundaries:
            raise ValueError(f"Missing boundary conditions for fields: {sorted(missing_boundaries)}")
        for field_name, units in self.field_units.items():
            Q_(1, units)
            self.diffusion_symbols.setdefault(field_name, None)
        for reaction in self.reactions:
            missing = reaction.species.difference(self.field_units)
            if missing:
                raise ValueError(
                    f"Reaction {reaction.name} references fields without units: {sorted(missing)}"
                )

    def _validate_ready_to_run(self) -> None:
        self.parameters.validate(
            allow_unsourced_for_testing=self.allow_unsourced_for_testing,
            require_values=True,
        )
        self.grid.length.validate_provenance(
            allow_unsourced_for_testing=self.allow_unsourced_for_testing
        )
        self.grid.length.validate_value()
        for reaction in self.reactions:
            reaction.validate_provenance(
                allow_unsourced_for_testing=self.allow_unsourced_for_testing
            )

    def _coerce_initial_fields(self, initial_fields: Mapping[str, Quantity]) -> list[np.ndarray]:
        expected = set(self.field_units)
        received = set(initial_fields)
        if expected != received:
            raise ValueError(
                "Initial field mismatch. "
                f"Missing: {sorted(expected.difference(received))}; "
                f"extra: {sorted(received.difference(expected))}."
            )
        arrays: list[np.ndarray] = []
        for name, units in self.field_units.items():
            quantity = assert_compatible(
                require_quantity(initial_fields[name], name=f"initial_fields[{name}]"),
                units,
                name=name,
            )
            values = np.asarray(quantity.magnitude, dtype=float)
            if values.shape != (self.grid.n_cells,):
                raise ValueError(
                    f"Initial field {name!r} must have shape ({self.grid.n_cells},), "
                    f"got {values.shape}."
                )
            arrays.append(values)
        return arrays

    def simulate(
        self,
        *,
        initial_fields: Mapping[str, Quantity],
        t_span: tuple[Quantity, Quantity],
        t_eval: Quantity | None = None,
        solver_settings: SolverSettings | Mapping[str, Any] | None = None,
    ) -> ReactionDiffusionResult1D:
        self._validate_ready_to_run()
        settings = (
            SolverSettings(**solver_settings)
            if isinstance(solver_settings, Mapping)
            else solver_settings or SolverSettings()
        )
        t0 = require_quantity(t_span[0], name="t_span[0]")
        tf = require_quantity(t_span[1], name="t_span[1]")
        time_units = str(tf.units)
        t_span_numeric = (
            float(assert_compatible(t0, time_units, name="t_span[0]").magnitude),
            float(assert_compatible(tf, time_units, name="t_span[1]").magnitude),
        )
        if t_span_numeric[1] <= t_span_numeric[0]:
            raise ValueError("t_span final time must be greater than start time.")
        t_eval_numeric = None
        if t_eval is not None:
            t_eval_numeric = np.asarray(
                assert_compatible(require_quantity(t_eval, name="t_eval"), time_units, name="t_eval").magnitude,
                dtype=float,
            )

        field_names = list(self.field_units)
        initial_arrays = self._coerce_initial_fields(initial_fields)
        y0 = np.concatenate(initial_arrays)
        n = self.grid.n_cells

        def unpack(y: np.ndarray) -> dict[str, np.ndarray]:
            return {
                name: y[index * n : (index + 1) * n]
                for index, name in enumerate(field_names)
            }

        def rhs(t: float, y: np.ndarray) -> np.ndarray:
            arrays = unpack(y)
            derivative_arrays = {
                name: np.zeros(n, dtype=float)
                for name in field_names
            }
            time = Q_(t, time_units)

            for name in field_names:
                diffusion_symbol = self.diffusion_symbols.get(name)
                if diffusion_symbol is None:
                    continue
                diffusion_coefficient = self.parameters.require_quantity(
                    diffusion_symbol,
                    f"meter ** 2 / {time_units}",
                )
                laplacian = finite_volume_laplacian_1d(
                    Q_(arrays[name], self.field_units[name]),
                    cell_width=self.grid.cell_width,
                    boundary_conditions=self.boundary_conditions[name],
                )
                diffusion_term = assert_compatible(
                    diffusion_coefficient * laplacian,
                    f"{self.field_units[name]} / {time_units}",
                    name=f"{name} diffusion term",
                )
                derivative_arrays[name] += np.asarray(diffusion_term.magnitude, dtype=float)

            for cell_index in range(n):
                local_state = {
                    name: Q_(arrays[name][cell_index], self.field_units[name])
                    for name in field_names
                }
                local_derivatives = {
                    name: Q_(0.0, f"{self.field_units[name]} / {time_units}")
                    for name in field_names
                }
                for reaction in self.reactions:
                    rate = reaction.rate(local_state, time, self.parameters)
                    for species in reaction.species:
                        coefficient = reaction.stoichiometric_coefficient(species)
                        if coefficient == 0:
                            continue
                        local_derivatives[species] += coefficient * assert_compatible(
                            rate,
                            f"{self.field_units[species]} / {time_units}",
                            name=f"{reaction.name} contribution to {species}",
                        )
                for name in field_names:
                    derivative_arrays[name][cell_index] += float(
                        assert_compatible(
                            local_derivatives[name],
                            f"{self.field_units[name]} / {time_units}",
                            name=f"{name} local reaction derivative",
                        ).magnitude
                    )

            return np.concatenate([derivative_arrays[name] for name in field_names])

        solve_kwargs: dict[str, Any] = {
            "method": settings.method,
            "rtol": settings.rtol,
            "atol": settings.atol,
        }
        if settings.max_step is not None:
            solve_kwargs["max_step"] = float(
                assert_compatible(settings.max_step, time_units, name="max_step").magnitude
            )
        solution = solve_ivp(rhs, t_span_numeric, y0, t_eval=t_eval_numeric, **solve_kwargs)

        fields: dict[str, Quantity] = {}
        for index, name in enumerate(field_names):
            values = solution.y[index * n : (index + 1) * n, :].T
            fields[name] = Q_(values, self.field_units[name])
        initial_quantities = {
            name: Q_(initial_arrays[index], self.field_units[name])
            for index, name in enumerate(field_names)
        }
        all_assumptions = list(self.assumptions)
        seen_assumptions = {assumption.name for assumption in all_assumptions}
        for reaction in self.reactions:
            for assumption in reaction.assumptions:
                if assumption.name not in seen_assumptions:
                    all_assumptions.append(assumption)
                    seen_assumptions.add(assumption.name)

        return ReactionDiffusionResult1D(
            time=Q_(solution.t, time_units),
            fields=fields,
            initial_fields=initial_quantities,
            grid=self.grid,
            success=bool(solution.success),
            message=str(solution.message),
            solver_settings=settings,
            parameters=self.parameters,
            assumptions=all_assumptions,
            reactions=list(self.reactions),
            boundary_conditions=dict(self.boundary_conditions),
            diffusion_symbols=dict(self.diffusion_symbols),
            model_version=self.model_version,
            solver_metadata={
                "status": int(solution.status),
                "nfev": int(solution.nfev),
                "njev": None if solution.njev is None else int(solution.njev),
                "nlu": None if solution.nlu is None else int(solution.nlu),
            },
        )


__all__ = [
    "ReactionDiffusionEngine1D",
    "ReactionDiffusionRecord",
    "ReactionDiffusionResult1D",
]
