"""Well-mixed ODE solver for assembled process models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from fungal_model.core.numerics import solve_checked

from fungal_model.chemistry.thermodynamics import (
    DynamicThermodynamicConstraint,
    DynamicThermodynamicEvaluation,
)
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.core.validators import ValidationResult
from fungal_model.results import SimulationResult
from fungal_model.core.numerics import JACOBIAN_COMPILED
from fungal_model.solvers.compiled import (
    JACOBIAN_COMPILED_LABEL,
    CompiledModel,
    compile_assembled_model,
    resolve_state_units,
)

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
    """Integrate a well-mixed assembled process model.

    The model is compiled once per run into a numeric right-hand side (see
    :mod:`fungal_model.solvers.compiled`); the kernel used for every process is
    recorded under ``solver_metadata["kernel"]``.
    """

    backend_name = "scipy.solve_ivp"

    def __init__(self, model: AssembledModel) -> None:
        self.model = model

    def compile(self, request: RunRequest) -> CompiledModel:
        """Compile the model for the request's time units without integrating."""

        self._validate_geometry_supported()
        state_units = resolve_state_units(self.model)
        state_names = tuple(state_units)
        time_units = _time_units(request.t_span)
        y0 = _initial_vector(request.initial_state, state_units, state_names)
        return compile_assembled_model(
            self.model,
            time_units=time_units,
            initial_state=np.asarray(y0, dtype=float),
            initial_time=_numeric_t_span(request.t_span, time_units)[0],
            constraints_by_process=_constraints_by_process(self.model),
        )

    def run(self, request: RunRequest) -> SimulationResult:
        self._validate_geometry_supported()
        state_units = resolve_state_units(self.model)
        state_names = tuple(state_units)
        time_units = _time_units(request.t_span)
        t_span_numeric = _numeric_t_span(request.t_span, time_units)
        t_eval_numeric = _numeric_t_eval(request.t_eval, time_units)
        y0 = _initial_vector(request.initial_state, state_units, state_names)
        settings = self.model.solver_settings
        constraints_by_process = _constraints_by_process(self.model)
        compiled = compile_assembled_model(
            self.model,
            time_units=time_units,
            initial_state=np.asarray(y0, dtype=float),
            initial_time=t_span_numeric[0],
            constraints_by_process=constraints_by_process,
        )

        options = settings.scipy_options(state_units, time_units)
        use_compiled_jacobian = settings.jacobian == JACOBIAN_COMPILED and settings.uses_jacobian
        if use_compiled_jacobian:
            options["jac"] = compiled.jacobian
        solution = solve_checked(compiled.rhs, t_span_numeric, y0, t_eval=t_eval_numeric, **options)
        kernel_summary = compiled.summary()
        if use_compiled_jacobian:
            kernel_summary["jacobian"] = JACOBIAN_COMPILED_LABEL
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
            compiled=compiled,
        )
        state_rates = _record_state_rates(compiled, solution.t, solution.y)
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
            derived_quantities={
                **_thermodynamic_derived_quantities(thermodynamic_evaluations),
                **_process_derived_quantities(self.model, states),
            },
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
                "kernel": kernel_summary,
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
            state_rates=state_rates,
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


_state_units = resolve_state_units


def _process_derived_quantities(model: AssembledModel, states: Mapping[str, Quantity]) -> dict[str, Quantity]:
    values: dict[str, Quantity] = {}
    for process in model.processes:
        method = getattr(process, "derived_quantities", None)
        if method is not None:
            for name, quantity in method(states, model.parameters).items():
                key = f"{process.name}.{name}"
                if key in values:
                    raise ValueError(f"Duplicate derived quantity {key!r}.")
                values[key] = require_quantity(quantity, name=key)
    return values


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


def _record_process_rates(
    model: AssembledModel,
    time: Quantity,
    states: Mapping[str, Quantity],
    *,
    constraints_by_process: Mapping[str, DynamicThermodynamicConstraint],
    compiled: CompiledModel,
) -> tuple[
    dict[str, Quantity],
    dict[str, list[DynamicThermodynamicEvaluation]],
]:
    """Process-rate trajectories at the returned time points.

    Unconstrained processes reuse their compiled kernels. Thermodynamically
    constrained processes are re-evaluated through the unit-aware ``enforce``
    so that activities, reaction quotients and Gibbs energies are recorded.
    """

    times = np.asarray(time.magnitude, dtype=float)
    # Accepted states are recorded unclipped; rates at the returned points use
    # the same non-negative projection as the compiled right-hand side.
    raw_matrix = np.vstack([np.asarray(states[name].magnitude, dtype=float) for name in compiled.state_names])
    matrix = np.column_stack([compiled.evaluation_state(raw_matrix[:, i]) for i in range(times.size)]) if times.size else raw_matrix
    rates: dict[str, Quantity] = {}
    evaluations: dict[str, list[DynamicThermodynamicEvaluation]] = {
        constraint.constraint_id: []
        for constraint in model.thermodynamic_constraints
    }
    if times.size == 0:
        return rates, evaluations
    for process in compiled.processes:
        constraint = constraints_by_process.get(process.name)
        if constraint is None:
            values = np.asarray(
                [process.rate(float(time_value), matrix[:, index]) for index, time_value in enumerate(times)],
                dtype=float,
            )
            rates[process.name] = Q_(values, process.rate_units)
            continue
        rate_values: list[Quantity] = []
        for index, time_value in enumerate(times):
            state = compiled.quantity_state(matrix[:, index])
            rate, evaluation = _enforced_process_rate(
                model=model,
                process=process.process,
                state=state,
                time=Q_(time_value, time.units),
                constraint=constraint,
            )
            rate_values.append(rate)
            if evaluation is not None:
                evaluations[evaluation.constraint_id].append(evaluation)
        rates[process.name] = Q_(
            np.asarray([rate.to(rate_values[0].units).magnitude for rate in rate_values], dtype=float),
            rate_values[0].units,
        )
    return rates, evaluations


def _record_state_rates(
    compiled: CompiledModel,
    times: np.ndarray,
    states: np.ndarray,
) -> dict[str, Quantity]:
    """Net rate of change of every state at the returned time points.

    Each column is ``compiled.rhs`` at the accepted state, i.e. the same
    stoichiometric right-hand side the solver integrated, under the same
    negative-state policy (rates evaluated at ``max(state, 0)``). Values are in
    state units per integration time unit. No finite differences of the
    trajectory are used.
    """

    time_values = np.asarray(times, dtype=float)
    state_matrix = np.asarray(states, dtype=float).reshape(len(compiled.state_names), time_values.size)
    derivatives = np.empty((len(compiled.state_names), time_values.size), dtype=float)
    for index, time_value in enumerate(time_values):
        derivatives[:, index] = compiled.rhs(float(time_value), state_matrix[:, index])
    return {
        name: Q_(derivatives[row], f"{units} / {compiled.time_units}")
        for row, (name, units) in enumerate(zip(compiled.state_names, compiled.state_units, strict=True))
    }


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


__all__ = ["ProcessODESolver", "RunRequest"]
