"""Compiled well-mixed process models: units resolved once, numeric right-hand side.

The compiler turns an :class:`~fungal_model.processes.assembly.AssembledModel`
into a plain-numpy right-hand side. Every unit conversion between a process's
rate units, the model state units, and the integration time unit is resolved
once at build time. Each process contributes one column of a stoichiometric
matrix ``N`` (states x processes), obtained by probing
:meth:`Process.contributions` and verifying that contributions are linear in
the rate. The rate vector ``v(t, y)`` is evaluated by one kernel per process:

* ``numeric``: a closure returned by :meth:`Process.compile_rate` that
  reproduces the process's unit-aware ``rate`` arithmetic on floats;
* ``numeric_thermodynamic``: a numeric kernel followed by the configured
  dynamic Gibbs feasibility test, blocking an unfavorable forward rate;
* ``quantity_wrapped``: the process's own ``rate`` method evaluated on a
  reconstructed unit-bearing state, used when a process offers no kernel;
* ``quantity_wrapped_thermodynamic``: the wrapped evaluation followed by the
  constraint's unit-aware ``enforce``.

The kernel kind of every process is recorded in the solver metadata, so a slow
path is never silent. The compiler introduces no clipping, no fallback
constants, no tolerance changes, and no rate law of its own.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from fungal_model.chemistry.thermodynamics import DynamicThermodynamicConstraint
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.units import Q_, Quantity, assert_compatible

if TYPE_CHECKING:
    from fungal_model.processes.assembly import AssembledModel

KERNEL_NUMERIC = "numeric"
KERNEL_NUMERIC_THERMODYNAMIC = "numeric_thermodynamic"
KERNEL_QUANTITY_WRAPPED = "quantity_wrapped"
KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC = "quantity_wrapped_thermodynamic"
NUMERIC_KERNEL_KINDS = frozenset({KERNEL_NUMERIC, KERNEL_NUMERIC_THERMODYNAMIC})
WRAPPED_KERNEL_KINDS = frozenset({KERNEL_QUANTITY_WRAPPED, KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC})
STOICHIOMETRY_PROBE_VALUES = (0.0, 1.0, 2.0)
MODEL_REPRESENTATION = "compiled_stoichiometric_rhs"
JACOBIAN_ANALYTIC = "analytic"
JACOBIAN_FINITE_DIFFERENCE = "finite_difference"
JACOBIAN_BY_BACKEND = "finite_difference_by_backend"
JACOBIAN_COMPILED_LABEL = "compiled_process_gradients"
# Relative step of the central finite differences that stand in for a missing
# analytic gradient; the absolute step never drops below the relative step
# itself, so states near zero are perturbed by at least that much.
FINITE_DIFFERENCE_RELATIVE_STEP = 1e-6
# Constitutive rate laws are defined on the non-negative orthant. Solver trial
# iterates can step slightly outside it near depletion, so rates are evaluated
# at the projection ``max(state, 0)`` (Shampine, Thompson, Kierzenka and Byrne,
# "Non-negative solutions of ODEs", Appl. Math. Comput. 170 (2005) 556-569).
# The integrated state itself is never clipped; validators check accepted
# trajectories for negativity beyond tolerance.
NEGATIVE_STATE_POLICY = "rates_evaluated_at_max_state_zero_trajectory_never_clipped"


def evaluation_state_for_rates(state: np.ndarray) -> np.ndarray:
    """Project a solver trial state onto the non-negative orthant for rate evaluation."""

    return np.maximum(np.asarray(state, dtype=float), 0.0)



def resolve_state_units(model: AssembledModel) -> dict[str, str]:
    """Ordered state names and units of an assembled model; conflicts fail."""

    units: dict[str, str] = {}
    for spec in model.state_variables:
        if spec.name in units and units[spec.name] != spec.units:
            raise ValueError(f"Conflicting state units for {spec.name!r}.")
        units[spec.name] = spec.units
    if not units:
        raise ValueError("Assembled model has no state variables.")
    return units


@dataclass(frozen=True)
class CompiledProcess:
    """One process of a compiled model: its kernel, its gradient and its stoichiometric column."""

    name: str
    process_type: str
    rate_units: str
    kernel_kind: str
    rate: RateKernel
    stoichiometry: np.ndarray
    process: Any
    constraint: DynamicThermodynamicConstraint | None = None
    gradient: JacobianKernel | None = None
    jacobian_kind: str = JACOBIAN_FINITE_DIFFERENCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "process_type": self.process_type,
            "rate_units": self.rate_units,
            "kernel_kind": self.kernel_kind,
            "stoichiometry": self.stoichiometry.tolist(),
        }


@dataclass(frozen=True)
class CompiledModel:
    """A well-mixed model compiled to ``dy/dt = N v(t, y)`` on plain floats."""

    state_names: tuple[str, ...]
    state_units: tuple[str, ...]
    time_units: str
    processes: tuple[CompiledProcess, ...]
    stoichiometry: np.ndarray
    context: KernelContext
    state_domains: tuple[str, ...] = ()
    state_bounds: tuple[tuple[float | None, float | None], ...] = ()
    _columns: tuple[np.ndarray, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        expected = (len(self.state_names), len(self.processes))
        if self.stoichiometry.shape != expected:
            raise ValueError(f"Stoichiometry shape {self.stoichiometry.shape} does not match {expected}.")
        object.__setattr__(
            self,
            "_columns",
            tuple(np.array(self.stoichiometry[:, index], dtype=float) for index in range(len(self.processes))),
        )

    def evaluation_state(self, state: np.ndarray) -> np.ndarray:
        values = np.asarray(state, dtype=float)
        projected = evaluation_state_for_rates(values)
        if self.state_domains:
            signed = np.array([domain == "signed" for domain in self.state_domains])
            projected[signed] = values[signed]
        for index, (lower, upper) in enumerate(self.state_bounds):
            if (lower is not None and values[index] < lower) or (upper is not None and values[index] > upper):
                raise ValueError(f"State {self.state_names[index]!r} outside declared bounds [{lower}, {upper}].")
        return projected

    def rates(self, time: float, state: np.ndarray) -> np.ndarray:
        """Process rate vector, each entry in its process's own rate units."""

        evaluation_state = self.evaluation_state(state)
        return np.array([process.rate(time, evaluation_state) for process in self.processes], dtype=float)

    def rhs(self, time: float, state: np.ndarray) -> np.ndarray:
        """Time derivative of the numeric state vector in state units per time unit.

        Contributions accumulate process by process in model order, matching
        the summation order of the unit-aware evaluation. Rates are evaluated
        at ``max(state, 0)`` (see :data:`NEGATIVE_STATE_POLICY`); the returned
        derivative is not otherwise altered and the integrated state is never
        clipped.
        """

        evaluation_state = self.evaluation_state(state)
        derivative = np.zeros(len(self.state_names), dtype=float)
        for process, column in zip(self.processes, self._columns, strict=True):
            derivative += column * process.rate(time, evaluation_state)
        return derivative

    def jacobian(self, time: float, state: np.ndarray) -> np.ndarray:
        """``d(dy/dt)/dy`` as a dense matrix, assembled as ``N diag-free sum of column x gradient``.

        Each process gradient is evaluated at ``max(state, 0)`` like the rate
        and multiplied by the derivative of that projection (zero where the
        state is negative), so the matrix is the exact derivative of
        :meth:`rhs` wherever :meth:`rhs` is differentiable.
        """

        evaluation_state = self.evaluation_state(state)
        mask = (np.asarray(state, dtype=float) >= 0.0).astype(float)
        for index, domain in enumerate(self.state_domains):
            if domain == "signed":
                mask[index] = 1.0
        matrix = np.zeros((len(self.state_names), len(self.state_names)), dtype=float)
        for process, column in zip(self.processes, self._columns, strict=True):
            if process.gradient is None:
                raise ValueError(f"Process {process.name!r} has no gradient kernel.")
            gradient = np.asarray(process.gradient(time, evaluation_state), dtype=float) * mask
            matrix += np.outer(column, gradient)
        return matrix

    def quantity_state(self, state: np.ndarray) -> dict[str, Quantity]:
        """Reconstruct a unit-bearing state mapping from a numeric vector."""

        return {
            name: Q_(state[index], units)
            for index, (name, units) in enumerate(zip(self.state_names, self.state_units, strict=True))
        }

    def rate_trajectories(self, times: np.ndarray, states: np.ndarray) -> dict[str, Quantity]:
        """Process rates along a trajectory (``states`` has shape states x times)."""

        values = np.empty((len(self.processes), times.size), dtype=float)
        for column_index, time in enumerate(times):
            state = self.evaluation_state(states[:, column_index])
            for row_index, process in enumerate(self.processes):
                values[row_index, column_index] = process.rate(float(time), state)
        return {
            process.name: Q_(values[index], process.rate_units)
            for index, process in enumerate(self.processes)
        }

    def summary(self) -> dict[str, Any]:
        """Inspectable record of how every process is evaluated."""

        kinds = {process.name: process.kernel_kind for process in self.processes}
        jacobian_kinds = {process.name: process.jacobian_kind for process in self.processes}
        return {
            "representation": MODEL_REPRESENTATION,
            "state_count": len(self.state_names),
            "process_count": len(self.processes),
            "process_kernels": kinds,
            "numeric_kernel_count": sum(kind in NUMERIC_KERNEL_KINDS for kind in kinds.values()),
            "quantity_wrapped_kernel_count": sum(kind in WRAPPED_KERNEL_KINDS for kind in kinds.values()),
            "unit_resolution": "build_time",
            "stoichiometry_probe": "contributions_linear_in_rate",
            "jacobian": JACOBIAN_BY_BACKEND,
            "jacobian_kernels": jacobian_kinds,
            "analytic_jacobian_count": sum(kind == JACOBIAN_ANALYTIC for kind in jacobian_kinds.values()),
            "negative_state_policy": NEGATIVE_STATE_POLICY if not any(d == "signed" for d in self.state_domains)
            else "non_negative_states_projected_signed_states_preserved_trajectory_never_clipped",
            **({"state_domains": dict(zip(self.state_names, self.state_domains))}
               if any(d == "signed" for d in self.state_domains) else {}),
        }


def compile_assembled_model(
    model: AssembledModel,
    *,
    time_units: str,
    initial_state: np.ndarray | None = None,
    initial_time: float = 0.0,
    constraints_by_process: Mapping[str, DynamicThermodynamicConstraint] | None = None,
) -> CompiledModel:
    """Compile an assembled well-mixed model for integration in ``time_units``.

    ``initial_state`` is only needed to discover the rate units of a process
    that declares none; every shipped process declares ``rate_units``.
    """

    state_units = resolve_state_units(model)
    state_names = tuple(state_units)
    context = KernelContext(
        state_index={name: index for index, name in enumerate(state_names)},
        state_units=dict(state_units),
        time_units=time_units,
        parameters=model.parameters,
        environment=model.context.environment,
        geometry=model.context.geometry,
    )
    state_bounds = tuple((spec.lower_bound, spec.upper_bound) for spec in model.state_variables)
    signed_indices = {index for index, spec in enumerate(model.state_variables) if spec.domain == "signed"}
    constraints = dict(constraints_by_process or {})
    unknown = sorted(set(constraints).difference(process.name for process in model.processes))
    if unknown:
        raise ValueError(f"Dynamic thermodynamic constraints reference unknown processes: {unknown}.")
    compiled: list[CompiledProcess] = []
    columns: list[np.ndarray] = []
    for process in model.processes:
        rate_units = _rate_units(process, context, initial_state=initial_state, initial_time=initial_time)
        column = _stoichiometry_column(process, rate_units=rate_units, context=context)
        constraint = constraints.get(process.name)
        kernel, kind = _rate_kernel(process, context, rate_units=rate_units, constraint=constraint)
        gradient, jacobian_kind = _gradient_kernel(process, context, rate_kernel=kernel, kernel_kind=kind,
            state_bounds=state_bounds, signed_indices=signed_indices)
        compiled.append(
            CompiledProcess(
                name=process.name,
                process_type=process.process_type,
                rate_units=rate_units,
                kernel_kind=kind,
                rate=kernel,
                stoichiometry=column,
                process=process,
                constraint=constraint,
                gradient=gradient,
                jacobian_kind=jacobian_kind,
            )
        )
        columns.append(column)
    stoichiometry = (
        np.column_stack(columns) if columns else np.zeros((len(state_names), 0), dtype=float)
    )
    return CompiledModel(
        state_names=state_names,
        state_units=tuple(state_units[name] for name in state_names),
        time_units=time_units,
        processes=tuple(compiled),
        stoichiometry=stoichiometry,
        context=context,
        state_domains=tuple(spec.domain for spec in model.state_variables),
        state_bounds=state_bounds,
    )


def _rate_units(
    process: Any,
    context: KernelContext,
    *,
    initial_state: np.ndarray | None,
    initial_time: float,
) -> str:
    declared = getattr(process, "rate_units", None)
    if isinstance(declared, str) and declared.strip():
        Q_(1.0, declared)
        return declared
    if initial_state is None:
        raise ValueError(
            f"Process {process.name!r} declares no rate_units; an initial state is required to compile it."
        )
    state = _quantity_state(initial_state, context)
    rate = process.rate(
        state,
        Q_(initial_time, context.time_units),
        context.parameters,
        context.environment,
        context.geometry,
    )
    return str(rate.units)


def _quantity_state(vector: np.ndarray, context: KernelContext) -> dict[str, Quantity]:
    return {name: Q_(vector[index], context.state_units[name]) for name, index in context.state_index.items()}


def _stoichiometry_column(process: Any, *, rate_units: str, context: KernelContext) -> np.ndarray:
    """Probe ``contributions`` at three rates and require linearity in the rate."""

    size = len(context.state_index)
    probes: dict[float, np.ndarray] = {}
    for probe_value in STOICHIOMETRY_PROBE_VALUES:
        column = np.zeros(size, dtype=float)
        for species, contribution in process.contributions(Q_(probe_value, rate_units)).items():
            if species not in context.state_index:
                raise ValueError(f"Process {process.name!r} contributed to unknown state {species!r}.")
            target_units = f"{context.state_units[species]} / {context.time_units}"
            column[context.state_index[species]] = float(
                assert_compatible(contribution, target_units, name=f"{process.name} contribution to {species}").magnitude
            )
        probes[probe_value] = column
    unit_column = probes[1.0]
    linear = bool(
        np.all(probes[0.0] == 0.0)
        and np.allclose(probes[2.0], 2.0 * unit_column, rtol=1e-12, atol=0.0)
        and np.isfinite(unit_column).all()
    )
    if not linear:
        raise ValueError(
            f"Process {process.name!r} contributions are not linear in its rate; "
            "the compiled stoichiometric form cannot represent it."
        )
    return unit_column


def _rate_kernel(
    process: Any,
    context: KernelContext,
    *,
    rate_units: str,
    constraint: DynamicThermodynamicConstraint | None,
) -> tuple[RateKernel, str]:
    numeric = process.compile_rate(context)
    if numeric is None:
        kind = KERNEL_QUANTITY_WRAPPED if constraint is None else KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC
        return _wrapped_kernel(process, context, rate_units=rate_units, constraint=constraint), kind
    if constraint is None:
        return numeric, KERNEL_NUMERIC
    feasible = constraint.compile_feasibility(context)
    if feasible is None:
        return (
            _wrapped_kernel(process, context, rate_units=rate_units, constraint=constraint),
            KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC,
        )
    return _blocking_kernel(numeric, feasible), KERNEL_NUMERIC_THERMODYNAMIC


def _wrapped_kernel(
    process: Any,
    context: KernelContext,
    *,
    rate_units: str,
    constraint: DynamicThermodynamicConstraint | None,
) -> RateKernel:
    """Evaluate the unit-aware ``rate`` (and ``enforce``) on a reconstructed state."""

    parameters, environment, geometry = context.parameters, context.environment, context.geometry
    time_units = context.time_units
    name = f"{process.name} rate"

    def kernel(time: float, state: np.ndarray) -> float:
        quantity_state = _quantity_state(state, context)
        rate = process.rate(quantity_state, Q_(time, time_units), parameters, environment, geometry)
        if constraint is not None:
            rate, _ = constraint.enforce(rate, quantity_state)
        return float(assert_compatible(rate, rate_units, name=name).magnitude)

    return kernel


def _gradient_kernel(
    process: Any,
    context: KernelContext,
    *,
    rate_kernel: RateKernel,
    kernel_kind: str,
    state_bounds: tuple[tuple[float | None, float | None], ...] = (),
    signed_indices: set[int] | None = None,
) -> tuple[JacobianKernel, str]:
    """The process's analytic gradient when it offers one and nothing blocks it; central differences otherwise.

    A thermodynamically constrained or quantity-wrapped rate is differentiated
    numerically, because the blocking test is not differentiable and a wrapped
    rate has no kernel to differentiate analytically.
    """

    if kernel_kind == KERNEL_NUMERIC:
        compile_jacobian = getattr(process, "compile_jacobian", None)
        analytic = None if compile_jacobian is None else compile_jacobian(context)
        if analytic is not None:
            return analytic, JACOBIAN_ANALYTIC
    indices = sorted({context.state_index[spec.name] for spec in process.state_variables if spec.name in context.state_index})
    signed = signed_indices if signed_indices is not None else {
        context.state_index[spec.name] for spec in process.state_variables if spec.domain == "signed"}
    return _finite_difference_gradient(rate_kernel, indices, len(context.state_index),
        signed=signed, bounds=state_bounds), JACOBIAN_FINITE_DIFFERENCE


def _finite_difference_gradient(
    rate_kernel: RateKernel, indices: list[int], size: int, *, signed: set[int] | None = None,
    bounds: tuple[tuple[float | None, float | None], ...] = (),
) -> JacobianKernel:
    """Central differences; use in-domain one-sided probes at declared boundaries."""

    relative_step = FINITE_DIFFERENCE_RELATIVE_STEP

    def gradient(time: float, state: np.ndarray) -> np.ndarray:
        result = np.zeros(size, dtype=float)
        work = np.array(state, dtype=float)
        for index in indices:
            value = work[index]
            step = relative_step * max(abs(value), 1.0)
            lower = value - step
            if bounds and any(bound is not None for bound in bounds[index]):
                minimum, maximum = bounds[index]
                if index not in (signed or set()):
                    minimum = max(0.0, minimum) if minimum is not None else 0.0
                if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                    raise ValueError("Finite-difference state lies outside its declared bounds.")
                lower_room = float("inf") if minimum is None else value - minimum
                upper_room = float("inf") if maximum is None else maximum - value
                if step > min(lower_room, upper_room):
                    offset = min(step, upper_room) if upper_room >= lower_room else -min(step, lower_room)
                    probe = value + offset
                    if probe == value:
                        raise ValueError("Declared state domain is too narrow for a finite-difference probe.")
                    work[index] = probe
                    probe_rate = rate_kernel(time, work)
                    work[index] = value
                    result[index] = (probe_rate - rate_kernel(time, work)) / (probe - value)
                    continue
            if lower < 0.0 and index not in (signed or set()):
                # Keep the historical unbounded non-negative policy exactly.
                work[index] = value + step
                upper_rate = rate_kernel(time, work)
                work[index] = value
                base_rate = rate_kernel(time, work)
                result[index] = (upper_rate - base_rate) / step
            else:
                work[index] = value + step
                upper_rate = rate_kernel(time, work)
                work[index] = lower
                lower_rate = rate_kernel(time, work)
                work[index] = value
                result[index] = (upper_rate - lower_rate) / (2.0 * step)
        return result

    return gradient


def _blocking_kernel(numeric: RateKernel, feasible: Callable[[np.ndarray], bool]) -> RateKernel:
    """Apply ``block_unfavorable_forward_rate`` semantics to a numeric kernel."""

    def kernel(time: float, state: np.ndarray) -> float:
        rate = numeric(time, state)
        if not np.isfinite(rate):
            raise ValueError("Dynamic thermodynamic enforcement requires a finite scalar process rate.")
        if rate < 0.0:
            raise ValueError("Dynamic thermodynamic enforcement supports nonnegative forward rates only.")
        return rate if feasible(state) else 0.0

    return kernel


__all__ = [
    "FINITE_DIFFERENCE_RELATIVE_STEP",
    "JACOBIAN_ANALYTIC",
    "JACOBIAN_BY_BACKEND",
    "JACOBIAN_COMPILED_LABEL",
    "JACOBIAN_FINITE_DIFFERENCE",
    "NEGATIVE_STATE_POLICY",
    "evaluation_state_for_rates",
    "KERNEL_NUMERIC",
    "KERNEL_NUMERIC_THERMODYNAMIC",
    "KERNEL_QUANTITY_WRAPPED",
    "KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC",
    "MODEL_REPRESENTATION",
    "NUMERIC_KERNEL_KINDS",
    "WRAPPED_KERNEL_KINDS",
    "CompiledModel",
    "CompiledProcess",
    "compile_assembled_model",
    "resolve_state_units",
]
