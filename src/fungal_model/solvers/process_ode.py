"""Well-mixed ODE solver for assembled process models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.integrate import solve_ivp

from fungal_model.chemistry.thermodynamics import (
    DynamicThermodynamicConstraint,
    DynamicThermodynamicEvaluation,
)
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.core.validators import ValidationResult
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
        constraints_by_process = _constraints_by_process(self.model)

        def rhs(t: float, y: np.ndarray) -> list[float]:
            state = _state_from_vector(y, state_units, state_names)
            time = Q_(t, time_units)
            derivatives = {
                name: Q_(0.0, f"{units} / {time_units}")
                for name, units in state_units.items()
            }
            for process in self.model.processes:
                rate, _ = _enforced_process_rate(
                    model=self.model,
                    process=process,
                    state=state,
                    time=time,
                    constraint=constraints_by_process.get(process.name),
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
        process_rates, thermodynamic_evaluations = _record_process_rates(
            self.model,
            time,
            states,
            constraints_by_process=constraints_by_process,
        )
        thermodynamic_metadata = _thermodynamic_metadata(
            self.model.thermodynamic_constraints,
            thermodynamic_evaluations,
        )
        result = SimulationResult(
            time=time,
            states=states,
            parameters=self.model.parameters,
            assumptions=tuple(self.model.assumptions),
            solver_settings=settings,
            process_rates=process_rates,
            derived_quantities=_thermodynamic_derived_quantities(
                thermodynamic_evaluations
            ),
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
                **(
                    {"dynamic_thermodynamics": thermodynamic_metadata}
                    if self.model.thermodynamic_constraints
                    else {}
                ),
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
        dynamic_validations = _thermodynamic_validations(
            self.model.thermodynamic_constraints,
            thermodynamic_evaluations,
        )
        if dynamic_validations:
            result.validation_results = (
                *result.validation_results,
                *dynamic_validations,
            )
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
    *,
    constraints_by_process: Mapping[str, DynamicThermodynamicConstraint],
) -> tuple[
    dict[str, Quantity],
    dict[str, list[DynamicThermodynamicEvaluation]],
]:
    rates: dict[str, list[Quantity]] = {process.name: [] for process in model.processes}
    evaluations: dict[str, list[DynamicThermodynamicEvaluation]] = {
        constraint.constraint_id: []
        for constraint in model.thermodynamic_constraints
    }
    for index, time_value in enumerate(np.asarray(time.magnitude, dtype=float)):
        state = {
            name: Q_(np.asarray(quantity.magnitude, dtype=float)[index], quantity.units)
            for name, quantity in states.items()
        }
        current_time = Q_(time_value, time.units)
        for process in model.processes:
            rate, evaluation = _enforced_process_rate(
                model=model,
                process=process,
                state=state,
                time=current_time,
                constraint=constraints_by_process.get(process.name),
            )
            rates[process.name].append(rate)
            if evaluation is not None:
                evaluations[evaluation.constraint_id].append(evaluation)
    return {
        name: Q_(
            np.asarray([rate.to(rate_values[0].units).magnitude for rate in rate_values], dtype=float),
            rate_values[0].units,
        )
        for name, rate_values in rates.items()
        if rate_values
    }, evaluations


def _constraints_by_process(
    model: AssembledModel,
) -> dict[str, DynamicThermodynamicConstraint]:
    process_names = {process.name for process in model.processes}
    constraints: dict[str, DynamicThermodynamicConstraint] = {}
    ids: set[str] = set()
    for constraint in model.thermodynamic_constraints:
        constraint.validate()
        if constraint.constraint_id in ids:
            raise ValueError(
                f"Duplicate dynamic thermodynamic constraint id "
                f"{constraint.constraint_id!r}."
            )
        if constraint.process_id not in process_names:
            raise ValueError(
                f"Dynamic thermodynamic constraint {constraint.constraint_id!r} "
                f"references unknown process {constraint.process_id!r}."
            )
        if constraint.process_id in constraints:
            raise ValueError(
                f"Process {constraint.process_id!r} has multiple dynamic "
                "thermodynamic constraints."
            )
        ids.add(constraint.constraint_id)
        constraints[constraint.process_id] = constraint
    return constraints


def _enforced_process_rate(
    *,
    model: AssembledModel,
    process: Any,
    state: Mapping[str, Quantity],
    time: Quantity,
    constraint: DynamicThermodynamicConstraint | None,
) -> tuple[Quantity, DynamicThermodynamicEvaluation | None]:
    rate = process.rate(
        state,
        time,
        model.parameters,
        model.context.environment,
        model.context.geometry,
    )
    if constraint is None:
        return rate, None
    return constraint.enforce(rate, state)


def _thermodynamic_derived_quantities(
    evaluations: Mapping[str, Sequence[DynamicThermodynamicEvaluation]],
) -> dict[str, Quantity]:
    derived: dict[str, Quantity] = {}
    for constraint_id, rows in evaluations.items():
        if not rows:
            continue
        prefix = f"dynamic_thermodynamics.{constraint_id}"
        derived[f"{prefix}.reaction_quotient"] = Q_(
            np.asarray([row.reaction_quotient for row in rows], dtype=float),
            "dimensionless",
        )
        derived[f"{prefix}.log_reaction_quotient"] = Q_(
            np.asarray([row.log_reaction_quotient for row in rows], dtype=float),
            "dimensionless",
        )
        derived[f"{prefix}.delta_gibbs"] = Q_(
            np.asarray([row.delta_gibbs for row in rows], dtype=float),
            "joule / mole",
        )
        derived[f"{prefix}.favorable"] = Q_(
            np.asarray([float(row.favorable) for row in rows], dtype=float),
            "dimensionless",
        )
        derived[f"{prefix}.rate_blocked"] = Q_(
            np.asarray([float(row.rate_blocked) for row in rows], dtype=float),
            "dimensionless",
        )
        for state_name in rows[0].activities:
            derived[f"{prefix}.activity.{state_name}"] = Q_(
                np.asarray(
                    [row.activities[state_name] for row in rows],
                    dtype=float,
                ),
                "dimensionless",
            )
    return derived


def _thermodynamic_metadata(
    constraints: Sequence[DynamicThermodynamicConstraint],
    evaluations: Mapping[str, Sequence[DynamicThermodynamicEvaluation]],
) -> dict[str, Any]:
    summaries = []
    for constraint in constraints:
        rows = tuple(evaluations.get(constraint.constraint_id, ()))
        summaries.append(
            {
                "constraint": constraint.to_dict(),
                "recorded_evaluation_count": len(rows),
                "recorded_unfavorable_count": sum(
                    1 for row in rows if not row.favorable
                ),
                "recorded_blocked_count": sum(
                    1 for row in rows if row.rate_blocked
                ),
                "minimum_delta_gibbs": (
                    None if not rows else min(row.delta_gibbs for row in rows)
                ),
                "maximum_delta_gibbs": (
                    None if not rows else max(row.delta_gibbs for row in rows)
                ),
                "final_delta_gibbs": (
                    None if not rows else rows[-1].delta_gibbs
                ),
                "final_reaction_quotient": (
                    None if not rows else rows[-1].reaction_quotient
                ),
            }
        )
    return {
        "enabled": bool(constraints),
        "constraint_count": len(constraints),
        "rhs_enforcement": (
            "active_for_every_process_rate_evaluation"
            if constraints
            else "not_configured"
        ),
        "recorded_summary_scope": (
            "Counts and extrema are evaluated on returned solver time points; "
            "the same constraint is applied separately at every internal RHS call."
        ),
        "constraints": summaries,
    }


def _thermodynamic_validations(
    constraints: Sequence[DynamicThermodynamicConstraint],
    evaluations: Mapping[str, Sequence[DynamicThermodynamicEvaluation]],
) -> tuple[ValidationResult, ...]:
    validations: list[ValidationResult] = []
    for constraint in constraints:
        rows = tuple(evaluations.get(constraint.constraint_id, ()))
        blocked_count = sum(1 for row in rows if row.rate_blocked)
        unfavorable_count = sum(1 for row in rows if not row.favorable)
        validations.append(
            ValidationResult(
                name="dynamic_thermodynamic_feasibility",
                passed=bool(rows),
                status="passed" if rows else "inconclusive",
                severity="info" if rows else "error",
                required=True,
                message=(
                    "Dynamic activities and reaction quotient were evaluated and "
                    "unfavorable forward rates were blocked at solver time."
                    if rows
                    else "Dynamic thermodynamic feasibility had no returned "
                    "time-point evaluations."
                ),
                details={
                    "constraint_id": constraint.constraint_id,
                    "process_id": constraint.process_id,
                    "reaction_id": constraint.reaction_id,
                    "electron_balance_check_id": (
                        constraint.electron_balance_check_id
                    ),
                    "standard_energy_method": constraint.standard_energy_method,
                    "residual_name": "dynamic_reaction_delta_gibbs",
                    "residual_units": "joule / mole",
                    "residual_value": (
                        None if not rows else rows[-1].delta_gibbs
                    ),
                    "standard_delta_gibbs": (
                        None if not rows else rows[-1].standard_delta_gibbs
                    ),
                    "reaction_quotient": (
                        None if not rows else rows[-1].reaction_quotient
                    ),
                    "temperature_K": (
                        None if not rows else rows[-1].temperature_kelvin
                    ),
                    "dynamic_reaction_quotient": "trajectory_state_derived",
                    "activity_model": (
                        "ideal_dilute_concentration_ratio_with_explicit_floor"
                    ),
                    "solver_time_enforcement": constraint.enforcement_mode,
                    "recorded_evaluation_count": len(rows),
                    "recorded_unfavorable_count": unfavorable_count,
                    "recorded_blocked_count": blocked_count,
                    "minimum_delta_gibbs": (
                        None if not rows else min(row.delta_gibbs for row in rows)
                    ),
                    "maximum_delta_gibbs": (
                        None if not rows else max(row.delta_gibbs for row in rows)
                    ),
                    "provenance_refs": list(constraint.provenance_refs),
                    "supported_scope": (
                        "Forward-rate feasibility for one explicitly bound "
                        "reaction using configured ideal-dilute concentration "
                        "activities, explicit floors, and a passing static "
                        "electron/redox balance check."
                    ),
                    "unsupported_scope": (
                        "No inferred species chemistry, activity coefficients, "
                        "reverse rate, coupled reaction network thermodynamics, "
                        "electrochemical gradients, or empirical validation."
                    ),
                    "missing_metadata": [],
                },
            )
        )
    return tuple(validations)


def _optional_solver_kwargs(settings: SolverSettings, time_units: str) -> dict[str, Any]:
    if settings.max_step is None:
        return {}
    return {
        "max_step": float(
            assert_compatible(settings.max_step, time_units, name="max_step").magnitude
        )
    }


__all__ = ["ProcessODESolver", "RunRequest"]
