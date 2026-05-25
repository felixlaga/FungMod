"""Deterministic ODE simulation engine and reproducibility records."""

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
from fungal_model.core.units import Q_, Quantity, UnitError, assert_compatible, require_quantity


@dataclass(frozen=True)
class SolverSettings:
    """Numerical solver settings that are recorded with every simulation."""

    method: str = "LSODA"
    rtol: float = 1e-8
    atol: float = 1e-10
    max_step: Quantity | None = None

    def to_dict(self) -> dict[str, Any]:
        max_step = None
        if self.max_step is not None:
            max_step = {
                "value": float(self.max_step.magnitude),
                "units": str(self.max_step.units),
            }
        return {
            "method": self.method,
            "rtol": self.rtol,
            "atol": self.atol,
            "max_step": max_step,
        }


def _quantity_array_summary(quantity: Quantity) -> dict[str, Any]:
    values = np.asarray(quantity.magnitude, dtype=float)
    return {
        "units": str(quantity.units),
        "initial": float(values.flat[0]),
        "final": float(values.flat[-1]),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }


@dataclass
class SimulationResult:
    """Unit-bearing simulation output."""

    time: Quantity
    species: dict[str, Quantity]
    initial_state: dict[str, Quantity]
    success: bool
    message: str
    solver_settings: SolverSettings
    parameters: ParameterSet
    assumptions: list[Assumption]
    reactions: list[Reaction]
    model_version: str
    solver_metadata: dict[str, Any] = field(default_factory=dict)

    def results_summary(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "time": _quantity_array_summary(self.time),
            "species": {
                name: _quantity_array_summary(quantity)
                for name, quantity in self.species.items()
            },
            "solver_metadata": self.solver_metadata,
        }

    def final_state(self) -> dict[str, Quantity]:
        return {
            name: Q_(np.asarray(quantity.magnitude).flat[-1], quantity.units)
            for name, quantity in self.species.items()
        }


@dataclass
class SimulationRecord:
    """Serializable record required for reproducible scientific runs."""

    timestamp: str
    model_version: str
    parameters: dict[str, Any]
    assumptions: list[dict[str, Any]]
    solver_settings: dict[str, Any]
    results_summary: dict[str, Any]
    validation_summary: dict[str, Any]

    @classmethod
    def from_result(
        cls,
        result: SimulationResult,
        validation_summary: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    ) -> "SimulationRecord":
        if isinstance(validation_summary, Mapping):
            validation_data: dict[str, Any] = dict(validation_summary)
        else:
            validation_data = {"validations": list(validation_summary)}
        return cls(
            timestamp=datetime.now(UTC).isoformat(),
            model_version=result.model_version,
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
class SimulationEngine:
    """General deterministic reaction-system ODE engine."""

    reactions: Sequence[Reaction]
    parameters: ParameterSet
    species_units: Mapping[str, str]
    assumptions: Sequence[Assumption] = field(default_factory=list)
    model_version: str = __version__
    allow_unsourced_for_testing: bool = False

    def __post_init__(self) -> None:
        self.reactions = list(self.reactions)
        self.assumptions = list(self.assumptions)
        self.species_units = dict(self.species_units)
        if not self.reactions:
            raise ValueError("SimulationEngine requires at least one reaction.")
        if not self.species_units:
            raise ValueError("SimulationEngine requires species_units.")
        for species, units in self.species_units.items():
            Q_(1, units)
        for reaction in self.reactions:
            missing = reaction.species.difference(self.species_units)
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValueError(
                    f"Reaction {reaction.name} references species without units: {missing_list}"
                )

    def _validate_ready_to_run(self) -> None:
        self.parameters.validate(
            allow_unsourced_for_testing=self.allow_unsourced_for_testing,
            require_values=True,
        )
        for reaction in self.reactions:
            reaction.validate_provenance(
                allow_unsourced_for_testing=self.allow_unsourced_for_testing
            )

    def _coerce_initial_state(self, initial_state: Mapping[str, Quantity]) -> list[float]:
        expected = set(self.species_units)
        received = set(initial_state)
        if expected != received:
            missing = expected.difference(received)
            extra = received.difference(expected)
            raise ValueError(
                "Initial state species mismatch. "
                f"Missing: {sorted(missing)}; extra: {sorted(extra)}."
            )
        y0: list[float] = []
        for species, units in self.species_units.items():
            value = require_quantity(initial_state[species], name=f"initial_state[{species}]")
            y0.append(float(assert_compatible(value, units, name=species).magnitude))
        return y0

    def simulate(
        self,
        *,
        initial_state: Mapping[str, Quantity],
        t_span: tuple[Quantity, Quantity],
        t_eval: Quantity | None = None,
        solver_settings: SolverSettings | Mapping[str, Any] | None = None,
    ) -> SimulationResult:
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
            t_eval_quantity = require_quantity(t_eval, name="t_eval")
            t_eval_numeric = np.asarray(
                assert_compatible(t_eval_quantity, time_units, name="t_eval").magnitude,
                dtype=float,
            )

        y0 = self._coerce_initial_state(initial_state)
        species_names = list(self.species_units)

        def rhs(t: float, y: np.ndarray) -> list[float]:
            state = {
                species: Q_(value, self.species_units[species])
                for species, value in zip(species_names, y, strict=True)
            }
            time = Q_(t, time_units)
            derivatives = {
                species: Q_(0.0, f"{units}/{time_units}")
                for species, units in self.species_units.items()
            }
            for reaction in self.reactions:
                rate = reaction.rate(state, time, self.parameters)
                for species in reaction.species:
                    coefficient = reaction.stoichiometric_coefficient(species)
                    if coefficient == 0:
                        continue
                    target_units = f"{self.species_units[species]}/{time_units}"
                    derivatives[species] += coefficient * assert_compatible(
                        rate,
                        target_units,
                        name=f"{reaction.name} contribution to {species}",
                    )
            return [
                float(assert_compatible(derivatives[species], f"{self.species_units[species]}/{time_units}").magnitude)
                for species in species_names
            ]

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

        species = {
            species_name: Q_(solution.y[index], self.species_units[species_name])
            for index, species_name in enumerate(species_names)
        }
        initial_quantities = {
            species_name: Q_(y0[index], self.species_units[species_name])
            for index, species_name in enumerate(species_names)
        }
        all_assumptions = list(self.assumptions)
        seen_assumption_names = {assumption.name for assumption in all_assumptions}
        for reaction in self.reactions:
            for assumption in reaction.assumptions:
                if assumption.name not in seen_assumption_names:
                    all_assumptions.append(assumption)
                    seen_assumption_names.add(assumption.name)

        return SimulationResult(
            time=Q_(solution.t, time_units),
            species=species,
            initial_state=initial_quantities,
            success=bool(solution.success),
            message=str(solution.message),
            solver_settings=settings,
            parameters=self.parameters,
            assumptions=all_assumptions,
            reactions=list(self.reactions),
            model_version=self.model_version,
            solver_metadata={
                "status": int(solution.status),
                "nfev": int(solution.nfev),
                "njev": None if solution.njev is None else int(solution.njev),
                "nlu": None if solution.nlu is None else int(solution.nlu),
            },
        )


__all__ = [
    "SimulationEngine",
    "SimulationRecord",
    "SimulationResult",
    "SolverSettings",
]
