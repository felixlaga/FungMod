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
* ``numeric_thermodynamic``: a numeric kernel multiplied by the configured
  constraint's numeric rate factor: the block-mode feasibility indicator, or
  the driving-force factor ``1 - exp(dG / (R T))``;
* ``quantity_wrapped``: the process's own ``rate`` method evaluated on a
  reconstructed unit-bearing state, used when a process offers no kernel;
* ``quantity_wrapped_thermodynamic``: the wrapped evaluation followed by the
  constraint's unit-aware ``enforce``.

The kernel kind of every process is recorded in the solver metadata, so a slow
path is never silent. The compiler introduces no clipping, no fallback
constants, no tolerance changes, and no rate law of its own.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from fungal_model.chemistry.thermodynamics import ENFORCEMENT_BLOCK, DynamicThermodynamicConstraint
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel
from fungal_model.core.numerics import SolverSettings
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
# A constrained process whose constraint offers neither a rate factor nor a
# feasibility kernel has no gradient the compiler can assemble without
# differentiating the constraint; its gradient kernel raises when evaluated.
JACOBIAN_REFUSED = "refused_constraint_without_numeric_factor"
JACOBIAN_BY_BACKEND = "finite_difference_by_backend"
JACOBIAN_COMPILED_LABEL = "compiled_process_gradients"
JACOBIAN_SUMMARY_LABELS = frozenset({JACOBIAN_BY_BACKEND, JACOBIAN_COMPILED_LABEL})
# Relative step of the central finite differences that stand in for a missing
# analytic gradient: the cube root of machine epsilon, which balances the
# O(h^2) truncation error of a central difference against the O(eps/h)
# roundoff error (Nocedal and Wright, "Numerical Optimization", 2nd ed.,
# Springer 2006, section 8.1). The absolute step of state ``i`` is
# ``FINITE_DIFFERENCE_RELATIVE_STEP * max(|y_i|, sigma_i)`` with a per-state
# scale ``sigma_i = atol_i / rtol`` in state units taken from the solver
# settings, the same threshold scipy's own ``num_jac`` uses, so the step is
# tied to the tolerance a state is integrated with instead of to its unit.
FINITE_DIFFERENCE_RELATIVE_STEP = float(np.finfo(float).eps ** (1.0 / 3.0))
# How the gradient of a thermodynamically constrained rate ``v = v_num * phi``
# is assembled: ``grad v = phi * grad v_num + v_num * grad phi`` where the
# constraint offers a factor gradient, and ``grad v = phi * grad v_num`` where
# it offers none (the block-mode indicator). The indicator itself is never
# differentiated, so the Jacobian has no spike on the switching surface.
CONSTRAINT_GRADIENT_RULE = "factor_times_numeric_gradient_plus_rate_times_factor_gradient; indicator_never_differentiated"
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
    #: Per-state scale ``sigma_i`` (state units) below which the finite-difference
    #: step of a numerically differentiated process stops shrinking with the state.
    finite_difference_scales: tuple[float, ...]
    _columns: tuple[np.ndarray, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        expected = (len(self.state_names), len(self.processes))
        if self.stoichiometry.shape != expected:
            raise ValueError(f"Stoichiometry shape {self.stoichiometry.shape} does not match {expected}.")
        if len(self.finite_difference_scales) != len(self.state_names):
            raise ValueError("One finite-difference scale per state is required.")
        object.__setattr__(
            self,
            "_columns",
            tuple(np.array(self.stoichiometry[:, index], dtype=float) for index in range(len(self.processes))),
        )

    def rates(self, time: float, state: np.ndarray) -> np.ndarray:
        """Process rate vector, each entry in its process's own rate units."""

        evaluation_state = evaluation_state_for_rates(state)
        return np.array([process.rate(time, evaluation_state) for process in self.processes], dtype=float)

    def rhs(self, time: float, state: np.ndarray) -> np.ndarray:
        """Time derivative of the numeric state vector in state units per time unit.

        Contributions accumulate process by process in model order, matching
        the summation order of the unit-aware evaluation. Rates are evaluated
        at ``max(state, 0)`` (see :data:`NEGATIVE_STATE_POLICY`); the returned
        derivative is not otherwise altered and the integrated state is never
        clipped.
        """

        evaluation_state = evaluation_state_for_rates(state)
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

        evaluation_state = evaluation_state_for_rates(state)
        mask = (np.asarray(state, dtype=float) >= 0.0).astype(float)
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
            state = evaluation_state_for_rates(states[:, column_index])
            for row_index, process in enumerate(self.processes):
                values[row_index, column_index] = process.rate(float(time), state)
        return {
            process.name: Q_(values[index], process.rate_units)
            for index, process in enumerate(self.processes)
        }

    def summary(self, *, jacobian: str = JACOBIAN_BY_BACKEND) -> dict[str, Any]:
        """Inspectable record of how every process is evaluated.

        ``jacobian`` names how the integrator obtains the Jacobian for this
        run: :data:`JACOBIAN_BY_BACKEND` (scipy differentiates the right-hand
        side) or :data:`JACOBIAN_COMPILED_LABEL` (this model's
        :meth:`jacobian`). The per-process gradient kinds are recorded either
        way, because they describe what :meth:`jacobian` would assemble.
        """

        if jacobian not in JACOBIAN_SUMMARY_LABELS:
            raise ValueError(f"Unknown jacobian label {jacobian!r}; choose one of {sorted(JACOBIAN_SUMMARY_LABELS)}.")
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
            "jacobian": jacobian,
            "jacobian_kernels": jacobian_kinds,
            "analytic_jacobian_count": sum(kind == JACOBIAN_ANALYTIC for kind in jacobian_kinds.values()),
            "finite_difference_scales": {
                name: scale for name, scale in zip(self.state_names, self.finite_difference_scales, strict=True)
            },
            "finite_difference_relative_step": FINITE_DIFFERENCE_RELATIVE_STEP,
            "constraint_gradient_rule": CONSTRAINT_GRADIENT_RULE,
            "negative_state_policy": NEGATIVE_STATE_POLICY,
        }


def compile_assembled_model(
    model: AssembledModel,
    *,
    time_units: str,
    initial_state: np.ndarray | None = None,
    initial_time: float = 0.0,
    constraints_by_process: Mapping[str, DynamicThermodynamicConstraint] | None = None,
    finite_difference_scales: Mapping[str, float] | Sequence[float] | np.ndarray | None = None,
) -> CompiledModel:
    """Compile an assembled well-mixed model for integration in ``time_units``.

    ``initial_state`` is only needed to discover the rate units of a process
    that declares none; every shipped process declares ``rate_units``.

    ``finite_difference_scales`` gives the per-state scale ``sigma_i`` (in the
    state's own units) of the finite-difference step used for processes
    without an analytic gradient, by name or in state order. It is normally
    :meth:`SolverSettings.finite_difference_scales`, ``atol_i / rtol``; when
    omitted the scales of the default :class:`SolverSettings` are used.
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
    scales = _finite_difference_scales(finite_difference_scales, state_units)
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
        parts = _rate_kernel(process, context, rate_units=rate_units, constraint=constraint)
        gradient, jacobian_kind = _gradient_kernel(process, context, parts=parts, scales=scales)
        compiled.append(
            CompiledProcess(
                name=process.name,
                process_type=process.process_type,
                rate_units=rate_units,
                kernel_kind=parts.kind,
                rate=parts.rate,
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
        finite_difference_scales=tuple(float(value) for value in scales),
    )


def _finite_difference_scales(
    scales: Mapping[str, float] | Sequence[float] | np.ndarray | None,
    state_units: Mapping[str, str],
) -> np.ndarray:
    """Per-state finite-difference scales in state order; positive and finite or refused."""

    if scales is None:
        values = SolverSettings().finite_difference_scales(state_units)
    elif isinstance(scales, Mapping):
        if set(scales) != set(state_units):
            raise ValueError("finite_difference_scales must name every compiled state exactly once.")
        values = np.asarray([scales[name] for name in state_units], dtype=float)
    else:
        values = np.asarray(scales, dtype=float)
    if values.shape != (len(state_units),):
        raise ValueError(f"finite_difference_scales must have one entry per state ({len(state_units)}).")
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError("finite_difference_scales must be finite and positive.")
    return values


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


@dataclass(frozen=True)
class _KernelParts:
    """What the compiler knows about one process's rate before assembling its gradient.

    ``rate`` is the kernel the right-hand side evaluates and ``kind`` its
    recorded label. ``unconstrained`` is the same rate without any constraint
    factor (the numeric kernel when the process offers one, its wrapped
    unit-aware ``rate`` otherwise) and ``numeric`` says which of the two it
    is. ``factor`` and ``factor_gradient`` are the constraint's ``phi`` and
    ``grad phi`` closures over the state vector, or ``None``.
    """

    rate: RateKernel
    kind: str
    unconstrained: RateKernel
    numeric: bool
    factor: Callable[[np.ndarray], Any] | None = None
    factor_gradient: Callable[[np.ndarray], np.ndarray] | None = None


def _rate_kernel(
    process: Any,
    context: KernelContext,
    *,
    rate_units: str,
    constraint: DynamicThermodynamicConstraint | None,
) -> _KernelParts:
    numeric = process.compile_rate(context)
    if constraint is None:
        if numeric is None:
            wrapped = _wrapped_kernel(process, context, rate_units=rate_units, constraint=None)
            return _KernelParts(rate=wrapped, kind=KERNEL_QUANTITY_WRAPPED, unconstrained=wrapped, numeric=False)
        return _KernelParts(rate=numeric, kind=KERNEL_NUMERIC, unconstrained=numeric, numeric=True)
    factor, factor_gradient = _constraint_factor(constraint, context)
    if numeric is None or factor is None:
        enforced = _wrapped_kernel(process, context, rate_units=rate_units, constraint=constraint)
        unconstrained = (
            numeric if numeric is not None
            else _wrapped_kernel(process, context, rate_units=rate_units, constraint=None)
        )
        return _KernelParts(
            rate=enforced,
            kind=KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC,
            unconstrained=unconstrained,
            numeric=numeric is not None,
            factor=factor,
            factor_gradient=factor_gradient,
        )
    return _KernelParts(
        rate=_factored_kernel(numeric, factor),
        kind=KERNEL_NUMERIC_THERMODYNAMIC,
        unconstrained=numeric,
        numeric=True,
        factor=factor,
        factor_gradient=factor_gradient,
    )


def _constraint_factor(
    constraint: DynamicThermodynamicConstraint,
    context: KernelContext,
) -> tuple[Callable[[np.ndarray], Any] | None, Callable[[np.ndarray], np.ndarray] | None]:
    """The constraint's numeric rate factor ``phi`` and its gradient, if it offers them.

    A constraint that compiles a rate factor (``compile_rate_factor``) returns
    one closure ``y -> (phi, grad phi)`` with ``grad phi`` ``None`` where the
    factor is not differentiable (the block-mode indicator); it is split here
    into ``phi`` and ``grad phi`` closures, the gradient closure being
    ``None`` in block mode. One that only compiles a feasibility test returns
    the blocking indicator with no gradient. ``(None, None)`` means the
    constraint offers no numeric form and only its unit-aware ``enforce`` can
    evaluate it.
    """

    compile_rate_factor = getattr(constraint, "compile_rate_factor", None)
    if compile_rate_factor is not None:
        rate_factor = compile_rate_factor(context)
        if rate_factor is not None:

            def factor(state: np.ndarray) -> float:
                return float(rate_factor(state)[0])

            if getattr(constraint, "enforcement_mode", None) == ENFORCEMENT_BLOCK:
                return factor, None

            def factor_gradient(state: np.ndarray) -> np.ndarray:
                gradient = rate_factor(state)[1]
                if gradient is None:
                    return np.zeros(len(context.state_index), dtype=float)
                return np.asarray(gradient, dtype=float)

            return factor, factor_gradient
    feasible = constraint.compile_feasibility(context)
    if feasible is None:
        return None, None
    return feasible, None


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
    parts: _KernelParts,
    scales: np.ndarray,
) -> tuple[JacobianKernel, str]:
    """Gradient of the process rate: analytic where offered, finite differences otherwise.

    The unconstrained rate ``v_num`` is differentiated by the process's own
    ``compile_jacobian`` when it offers one and its kernel is numeric, and by
    central finite differences of the unconstrained kernel otherwise. A
    constraint factor ``phi`` enters by the product rule
    (:data:`CONSTRAINT_GRADIENT_RULE`): the blocking indicator and the
    driving-force factor multiply the gradient of ``v_num``, never the other
    way round, so the switch surface carries no spurious derivative.
    """

    base: JacobianKernel | None = None
    kind = JACOBIAN_FINITE_DIFFERENCE
    if parts.numeric:
        compile_jacobian = getattr(process, "compile_jacobian", None)
        base = None if compile_jacobian is None else compile_jacobian(context)
        if base is not None:
            kind = JACOBIAN_ANALYTIC
    if base is None:
        indices = sorted({context.state_index[spec.name] for spec in process.state_variables if spec.name in context.state_index})
        base = _finite_difference_gradient(parts.unconstrained, indices, len(context.state_index), scales)
    if parts.kind not in (KERNEL_NUMERIC_THERMODYNAMIC, KERNEL_QUANTITY_WRAPPED_THERMODYNAMIC):
        return base, kind
    if parts.factor is None:
        name = process.name

        def refused(time: float, state: np.ndarray) -> np.ndarray:
            del time, state
            raise ValueError(
                f"Process {name!r} is bound to a dynamic thermodynamic constraint that offers no numeric rate "
                "factor; its compiled gradient would have to differentiate the constraint itself and is refused."
            )

        return refused, JACOBIAN_REFUSED
    return _factored_gradient(parts.unconstrained, base, parts.factor, parts.factor_gradient, len(context.state_index)), kind


def _factored_gradient(
    unconstrained: RateKernel,
    base: JacobianKernel,
    factor: Callable[[np.ndarray], Any],
    factor_gradient: Callable[[np.ndarray], np.ndarray] | None,
    size: int,
) -> JacobianKernel:
    """``grad (v_num phi) = phi grad v_num + v_num grad phi`` with ``grad phi = 0`` when not offered."""

    def gradient(time: float, state: np.ndarray) -> np.ndarray:
        phi = float(factor(state))
        if factor_gradient is None:
            if phi == 0.0:
                return np.zeros(size, dtype=float)
            return phi * np.asarray(base(time, state), dtype=float)
        result = phi * np.asarray(base(time, state), dtype=float)
        result += unconstrained(time, state) * np.asarray(factor_gradient(state), dtype=float)
        return result

    return gradient


def _finite_difference_gradient(
    rate_kernel: RateKernel,
    indices: list[int],
    size: int,
    scales: np.ndarray,
) -> JacobianKernel:
    """Central differences of ``rate_kernel`` over ``indices``; one-sided at the non-negative boundary.

    The step of state ``i`` is ``FINITE_DIFFERENCE_RELATIVE_STEP * max(|y_i|, sigma_i)``
    with ``sigma_i = scales[i]`` in state units. Where ``y_i - h_i < 0`` the
    second-order one-sided stencil ``(-3 f(y) + 4 f(y + h) - f(y + 2h)) / 2h``
    keeps every evaluation in the non-negative orthant at the same O(h^2)
    truncation order as the central stencil (Fornberg, Math. Comp. 51 (1988)
    699-706, weights for the three-point forward difference).
    """

    relative_step = FINITE_DIFFERENCE_RELATIVE_STEP
    step_floors = np.asarray(scales, dtype=float)

    def gradient(time: float, state: np.ndarray) -> np.ndarray:
        result = np.zeros(size, dtype=float)
        work = np.array(state, dtype=float)
        for index in indices:
            value = work[index]
            step = relative_step * max(abs(value), step_floors[index])
            lower = value - step
            if lower < 0.0:
                # Keep every evaluation in the non-negative orthant the rate is defined on.
                work[index] = value + step
                upper_rate = rate_kernel(time, work)
                work[index] = value + 2.0 * step
                far_rate = rate_kernel(time, work)
                work[index] = value
                base_rate = rate_kernel(time, work)
                result[index] = (-3.0 * base_rate + 4.0 * upper_rate - far_rate) / (2.0 * step)
            else:
                work[index] = value + step
                upper_rate = rate_kernel(time, work)
                work[index] = lower
                lower_rate = rate_kernel(time, work)
                work[index] = value
                result[index] = (upper_rate - lower_rate) / (2.0 * step)
        return result

    return gradient


def _factored_kernel(numeric: RateKernel, factor: Callable[[np.ndarray], Any]) -> RateKernel:
    """``v = v_num * phi``: the blocking indicator or the constraint's driving-force factor.

    The forward rate ``v_num`` must be finite and non-negative, as
    ``block_unfavorable_forward_rate`` requires; the product may be negative
    only through a factor that represents reverse flux.
    """

    def kernel(time: float, state: np.ndarray) -> float:
        rate = numeric(time, state)
        if not np.isfinite(rate):
            raise ValueError("Dynamic thermodynamic enforcement requires a finite scalar process rate.")
        if rate < 0.0:
            raise ValueError("Dynamic thermodynamic enforcement supports nonnegative forward rates only.")
        return rate * float(factor(state))

    return kernel


__all__ = [
    "CONSTRAINT_GRADIENT_RULE",
    "FINITE_DIFFERENCE_RELATIVE_STEP",
    "JACOBIAN_ANALYTIC",
    "JACOBIAN_BY_BACKEND",
    "JACOBIAN_COMPILED_LABEL",
    "JACOBIAN_FINITE_DIFFERENCE",
    "JACOBIAN_REFUSED",
    "JACOBIAN_SUMMARY_LABELS",
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
