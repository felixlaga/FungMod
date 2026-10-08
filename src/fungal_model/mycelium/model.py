"""Compile a spatial mycelium model to numpy kernels and integrate it.

``MyceliumModel`` names a grid, its fields, the field processes and the
parameters. ``compile()`` resolves every unit once, checks that each process
finds the fields it declares with compatible units, and returns a
``CompiledMyceliumModel`` whose right-hand side is a sum of vectorised
tendency kernels evaluated at ``max(field, 0)`` (the negative-state policy
of the well-mixed compiled core). ``simulate`` integrates with
``solve_checked`` and returns unit-bearing fields on the grid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np

from fungal_model import __version__
from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import InvalidMechanismError
from fungal_model.core.kernels import conversion_factor
from fungal_model.core.numerics import JACOBIAN_COMPILED, SolverSettings, solve_checked
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.mycelium.fields import FieldKernelContext, FieldSpec, RateFieldKernel, TendencyKernel
from fungal_model.mycelium.grid import SpatialGrid
from fungal_model.mycelium.jacobian import FieldJacobianKernel, StencilAssembler, stencil_colours, transport_blocks
from fungal_model.mycelium.operators import spatial_integral
from fungal_model.mycelium.processes import FieldProcess

MODEL_REPRESENTATION = "compiled_mycelium_fields"
NEGATIVE_FIELD_POLICY = "kernels evaluated at max(field, 0); integrated fields never clipped"
#: BDF and Radau: the analytic sparse Jacobian assembled from the processes' stencil coefficients.
ANALYTIC_JACOBIAN_STRUCTURE = "analytic_sparse_on_the_nearest_neighbour_stencil"
#: BDF and Radau: forward differences of the right-hand side, one evaluation per colour of the stencil.
FINITE_DIFFERENCE_JACOBIAN_STRUCTURE = "coloured_finite_difference_on_the_nearest_neighbour_pattern"
#: The sparse Jacobian BDF and Radau take by default: the analytic one since SPATIAL-003 (before, the
#: coloured finite-difference one), whenever every process offers an analytic kernel.
JACOBIAN_STRUCTURE = ANALYTIC_JACOBIAN_STRUCTURE
#: LSODA's own differences on a one-axis grid (the default before SPATIAL-003): a banded Jacobian of the cell-major state.
BANDED_JACOBIAN_STRUCTURE = "one_axis_banded_cell_major"
#: LSODA by default since SPATIAL-003: the analytic Jacobian of the cell-major state in band storage.
ANALYTIC_BANDED_JACOBIAN_STRUCTURE = "analytic_banded_cell_major"
#: LSODA with the analytic Jacobian where the band would hold more than a dense matrix (two cells along the first axis).
ANALYTIC_DENSE_JACOBIAN_STRUCTURE = "analytic_dense"
#: Explicit Jacobian choices of :meth:`CompiledMyceliumModel.simulate` for the implicit methods.
JACOBIAN_CHOICES = ("analytic", "finite_difference")
MATURITY_LABEL = "exploratory"


@dataclass(frozen=True)
class CompiledFieldProcess:
    """One process after compilation: its tendency kernel and optional rate kernel."""

    name: str
    process_type: str
    rate_units: str
    kernel_kind: str
    tendency: TendencyKernel
    rate: RateFieldKernel | None
    jacobian: FieldJacobianKernel | None = None


@dataclass(frozen=True)
class MyceliumModel:
    """A spatial mycelium model: grid, fields, field processes and parameters."""

    grid: SpatialGrid
    fields: tuple[FieldSpec, ...]
    processes: tuple[FieldProcess, ...]
    parameters: ParameterSet
    time_units: str = "hour"
    assumptions: tuple[Assumption, ...] = ()

    def __post_init__(self) -> None:
        names = [spec.name for spec in self.fields]
        if not names:
            raise InvalidMechanismError("A MyceliumModel needs at least one field.")
        if len(names) != len(set(names)):
            raise InvalidMechanismError("Field names must be unique.")
        if not self.processes:
            raise InvalidMechanismError("A MyceliumModel needs at least one process.")
        process_names = [process.name for process in self.processes]
        if len(process_names) != len(set(process_names)):
            raise InvalidMechanismError("Process names must be unique.")
        Q_(1, self.time_units).to("second")

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.fields)

    @property
    def field_units(self) -> dict[str, str]:
        return {spec.name: spec.units for spec in self.fields}

    def context(self) -> FieldKernelContext:
        return FieldKernelContext(
            field_index={name: index for index, name in enumerate(self.field_names)},
            field_units=self.field_units,
            time_units=self.time_units,
            parameters=self.parameters,
            grid=self.grid,
        )

    def compile(self) -> "CompiledMyceliumModel":
        """Resolve units, check field declarations and build every kernel once."""

        units = self.field_units
        for process in self.processes:
            for spec in process.fields:
                if spec.name not in units:
                    raise InvalidMechanismError(f"Process {process.name!r} declares field {spec.name!r}, which the model does not have.")
                conversion_factor(units[spec.name], spec.units, name=f"{process.name}:{spec.name}")
        context = self.context()
        compiled = tuple(
            CompiledFieldProcess(
                name=process.name,
                process_type=process.process_type,
                rate_units=process.rate_units,
                kernel_kind=process.kernel_kind,
                tendency=process.compile_tendency(context),
                rate=process.compile_rate(context),
                jacobian=process.compile_jacobian(context),
            )
            for process in self.processes
        )
        return CompiledMyceliumModel(model=self, context=context, processes=compiled)

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid": self.grid.to_dict(),
            "fields": [spec.to_dict() for spec in self.fields],
            "processes": [process.to_dict() for process in self.processes],
            "time_units": self.time_units,
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
        }


@dataclass(frozen=True)
class CompiledMyceliumModel:
    """``d(fields)/dt = sum of process tendencies`` on plain numpy arrays."""

    model: MyceliumModel
    context: FieldKernelContext
    processes: tuple[CompiledFieldProcess, ...]

    @property
    def shape(self) -> tuple[int, ...]:
        return self.model.grid.shape

    @property
    def field_count(self) -> int:
        return len(self.model.fields)

    def unflatten(self, state: np.ndarray) -> np.ndarray:
        return np.asarray(state, dtype=float).reshape((self.field_count, *self.shape))

    def rhs(self, time: float, state: np.ndarray) -> np.ndarray:
        """Time derivative of the flattened field array in field units per time unit."""

        fields = np.maximum(self.unflatten(state), 0.0)
        derivative = np.zeros_like(fields)
        for process in self.processes:
            derivative += process.tendency(time, fields)
        return derivative.ravel()

    def rates(self, time: float, state: np.ndarray) -> dict[str, np.ndarray]:
        """Per-cell rates of the processes that report one, in their rate units."""

        fields = np.maximum(self.unflatten(state), 0.0)
        return {process.name: process.rate(time, fields) for process in self.processes if process.rate is not None}

    # -- Jacobians on the nearest-neighbour stencil -------------------------

    @property
    def processes_without_analytic_jacobian(self) -> tuple[str, ...]:
        return tuple(process.name for process in self.processes if process.jacobian is None)

    @property
    def has_analytic_jacobian(self) -> bool:
        """Whether every process offers the analytic derivative of its tendency."""

        return not self.processes_without_analytic_jacobian

    @cached_property
    def _stencil(self) -> tuple[StencilAssembler, tuple[tuple[int, ...] | None, ...]]:
        """The declared pattern and, per process, the ids of its analytic blocks (``None`` without a kernel).

        A process with an analytic kernel contributes exactly the blocks it
        declares. A process without one is assumed, as every process of this
        core is, to couple a cell to itself and its nearest neighbours only, and
        contributes every pair of its declared fields in the cell and at each
        neighbour.
        """

        index = self.context.field_index
        ndim = self.model.grid.ndim
        keys: list[tuple[int, int, int, int]] = []
        for compiled, declared in zip(self.processes, self.model.processes, strict=True):
            if compiled.jacobian is not None:
                keys.extend(block.key for block in compiled.jacobian.blocks)
                continue
            rows = [index[spec.name] for spec in declared.fields]
            for row in rows:
                for column in rows:
                    keys.extend(block.key for block in transport_blocks(row, column, ndim))
        assembler = StencilAssembler(self.model.grid, self.field_count, keys)
        ids = tuple(None if process.jacobian is None else assembler.key_ids(process.jacobian.blocks) for process in self.processes)
        return assembler, ids

    def jacobian_sparsity(self):
        """The declared nearest-neighbour pattern of the Jacobian as a boolean CSR matrix (field-major state)."""

        return self._stencil[0].pattern().tocsr()

    def analytic_jacobian_sparsity(self):
        """The declared pattern as a boolean CSC matrix, the structure of :meth:`analytic_jacobian`."""

        return self._stencil[0].pattern()

    def jacobian_colours(self) -> np.ndarray:
        """A colour per state such that no two states of one colour share a row of the Jacobian.

        Every process couples a cell to itself and its nearest neighbours only,
        so ``(cell colour, field)`` with the cell colours of
        :func:`~fungal_model.mycelium.jacobian.stencil_colours` (index modulo
        three per axis, with extra colours on a periodic axis whose length is not
        a multiple of three) separates every pair of states that can share a row.
        """

        field_count = self.field_count
        cell_colour = stencil_colours(self.model.grid)
        return (cell_colour[np.newaxis] * field_count + np.arange(field_count).reshape([-1] + [1] * len(self.shape))).ravel()

    def jacobian(self, time: float, state: np.ndarray):
        """Sparse finite-difference Jacobian on the declared pattern, one right-hand side per colour.

        Forward differences with the step ``sqrt(eps) * max(|y_j|, 1)``; the
        fixed rule has no adaptive factor to overflow where a state is inert,
        which scipy's own estimator does on these clipped fields. Entries are
        kept only on the declared pattern, and no two columns of one colour
        share a row of it, so a perturbation of several states of one colour
        never mixes their columns.
        """

        from scipy import sparse

        state = np.asarray(state, dtype=float)
        assembler, _ = self._stencil
        colours = self.jacobian_colours()
        base = self.rhs(time, state)
        steps = np.sqrt(np.finfo(float).eps) * np.maximum(np.abs(state), 1.0)
        values = np.zeros(assembler.nnz, dtype=float)
        entry_colours = colours[assembler.entry_columns]
        for colour in np.unique(colours):
            members = np.flatnonzero(colours == colour)
            perturbed = state.copy()
            perturbed[members] += steps[members]
            difference = self.rhs(time, perturbed) - base
            entries = np.flatnonzero(entry_colours == colour)
            values[entries] = difference[assembler.entry_rows[entries]] / steps[assembler.entry_columns[entries]]
        return sparse.csc_matrix((values, assembler.indices.copy(), assembler.indptr.copy()), shape=(assembler.size, assembler.size))

    def _analytic_values(self, time: float, state: np.ndarray) -> np.ndarray:
        """Data vector of the analytic Jacobian on the declared pattern, before the projection's column scaling."""

        assembler, key_ids = self._stencil
        missing = self.processes_without_analytic_jacobian
        if missing:
            raise ValueError(f"No analytic Jacobian: the processes {list(missing)} do not offer one (compile_jacobian returned None).")
        fields = np.maximum(self.unflatten(state), 0.0)
        data = np.zeros(assembler.nnz, dtype=float)
        for process, ids in zip(self.processes, key_ids, strict=True):
            if process.jacobian is None or ids is None:  # unreachable after the check above
                raise ValueError(f"Process {process.name!r} has no analytic Jacobian.")
            assembler.scatter(data, ids, process.jacobian.values(time, fields))
        return data

    def analytic_jacobian(self, time: float, state: np.ndarray):
        """``d rhs / d state`` assembled from every process's analytic stencil coefficients, as a CSC matrix.

        Coefficients are evaluated at the projected fields ``max(field, 0)``,
        like the right-hand side, and every column is multiplied by the
        projection's derivative (zero where the state is negative, one where it
        is zero or positive: the right derivative), so the matrix is the exact
        derivative of :meth:`rhs` wherever :meth:`rhs` is differentiable. At an
        upwind face whose velocity is exactly zero the derivative of the side
        the kernel uses applies. No dense matrix is formed.
        """

        state = np.asarray(state, dtype=float)
        return self._stencil[0].matrix(self._analytic_values(time, state), state)

    @cached_property
    def _cell_major(self) -> tuple[np.ndarray, np.ndarray]:
        """``(permutation, inverse)``: ``state[permutation]`` orders the state by cell, then field."""

        permutation = np.arange(self.field_count * self.model.grid.cell_count).reshape(self.field_count, -1).T.ravel()
        return permutation, np.argsort(permutation)

    @cached_property
    def _analytic_band(self) -> tuple[int, int, np.ndarray, np.ndarray]:
        """Half-bandwidths in cell-major order, the entries kept in the band and their packed positions.

        The band holds every coupling between cells at most one slice of the
        first axis apart (``prod(shape[1:])`` cells), which is every declared
        entry except the wrap across a periodic first axis (or across a
        periodic line of more than two cells); those lie outside any band.
        """

        assembler, _ = self._stencil
        _, inverse = self._cell_major
        cells = self.model.grid.cell_count
        slice_cells = cells // self.model.grid.shape[0]
        kept = np.flatnonzero(np.abs(assembler.entry_rows % cells - assembler.entry_columns % cells) <= slice_cells)
        rows, columns = inverse[assembler.entry_rows[kept]], inverse[assembler.entry_columns[kept]]
        offsets = rows - columns
        lower = int(max(offsets.max(initial=0), 0))
        upper = int(max((-offsets).max(initial=0), 0))
        packed = (upper + offsets) * assembler.size + columns
        return lower, upper, kept, packed

    def analytic_band_widths(self) -> tuple[int, int]:
        """Lower and upper half-bandwidths of the analytic band with the state in cell-major order."""

        lower, upper, _, _ = self._analytic_band
        return lower, upper

    def analytic_entries_outside_band(self) -> int:
        """Declared entries the band leaves out: the couplings across the wrap of a periodic first axis."""

        _, _, kept, _ = self._analytic_band
        return int(self._stencil[0].nnz - kept.size)

    def analytic_jacobian_banded(self, time: float, cell_major_state: np.ndarray) -> np.ndarray:
        """The analytic Jacobian of the cell-major state in LSODA's packed band storage.

        Row ``upper + i - j`` and column ``j`` hold ``J[i, j]``, the storage of
        ``scipy.linalg.solve_banded``. Every declared entry lies in the band
        except the couplings across the wrap of a periodic first axis
        (:meth:`analytic_entries_outside_band`), which no band can hold and which
        LSODA's own banded differences cannot represent either; there the matrix
        is exact but for those entries.
        """

        assembler, _ = self._stencil
        _, inverse = self._cell_major
        state = np.asarray(cell_major_state, dtype=float)[inverse]
        data = self._analytic_values(time, state)
        mask = state >= 0.0
        lower, upper, kept, packed = self._analytic_band
        band = np.zeros((lower + upper + 1) * assembler.size, dtype=float)
        band[packed] = np.where(mask[assembler.entry_columns[kept]], data[kept], 0.0)
        return band.reshape(lower + upper + 1, assembler.size)

    def jacobian_structure_for(self, settings: SolverSettings, jacobian: str | None = None) -> str:
        """How ``simulate`` obtains the Jacobian for ``settings`` (recorded as ``jacobian_structure``).

        Explicit methods use none (``backend_default``) and ignore the choice.
        ``jacobian`` is ``"analytic"``, ``"finite_difference"`` or ``None`` (the
        default); ``SolverSettings(jacobian="compiled")`` means ``"analytic"``.

        The analytic Jacobian is the default of every implicit method when
        every process offers an analytic kernel: BDF and Radau take the sparse
        matrix; LSODA, which accepts only dense or banded matrices, takes it in
        band storage of the cell-major state (without the couplings across the
        wrap of a periodic first axis, which no band holds; see
        :meth:`analytic_jacobian_banded`) when the band holds no more than a
        dense matrix, and as a dense matrix otherwise (grids of two cells along
        the first axis). ``"finite_difference"``, or the default when a process
        offers no kernel, gives BDF and Radau the coloured finite-difference
        Jacobian and lets LSODA difference the right-hand side itself (banded in
        cell-major order on a one-axis grid, dense otherwise). ``"analytic"`` is
        refused for a model with a process that offers no kernel.
        """

        if jacobian is not None and jacobian not in JACOBIAN_CHOICES:
            raise ValueError(f"jacobian must be one of {JACOBIAN_CHOICES} or None, not {jacobian!r}.")
        if not settings.uses_jacobian:
            return "backend_default"
        compiled = settings.jacobian == JACOBIAN_COMPILED
        if compiled and jacobian == "finite_difference":
            raise ValueError("SolverSettings(jacobian='compiled') asks for the analytic Jacobian; jacobian='finite_difference' contradicts it.")
        required = compiled or jacobian == "analytic"
        if required and not self.has_analytic_jacobian:
            raise ValueError(
                f"The analytic Jacobian was requested, and the processes {list(self.processes_without_analytic_jacobian)} "
                "do not offer one (compile_jacobian returned None)."
            )
        analytic = required or (jacobian is None and self.has_analytic_jacobian)
        if settings.method == "LSODA":
            if not analytic:
                return BANDED_JACOBIAN_STRUCTURE if self.model.grid.ndim == 1 else "backend_default"
            lower, upper = self.analytic_band_widths()
            size = self.field_count * self.model.grid.cell_count
            return ANALYTIC_BANDED_JACOBIAN_STRUCTURE if 2 * lower + upper + 1 <= size else ANALYTIC_DENSE_JACOBIAN_STRUCTURE
        return ANALYTIC_JACOBIAN_STRUCTURE if analytic else FINITE_DIFFERENCE_JACOBIAN_STRUCTURE

    def summary(self) -> dict[str, Any]:
        return {
            "representation": MODEL_REPRESENTATION,
            "field_count": self.field_count,
            "cell_count": self.model.grid.cell_count,
            "process_count": len(self.processes),
            "process_kernels": {process.name: process.kernel_kind for process in self.processes},
            "rate_reporting_processes": [process.name for process in self.processes if process.rate is not None],
            "unit_resolution": "build_time",
            "negative_field_policy": NEGATIVE_FIELD_POLICY,
            "jacobian_structure": ANALYTIC_JACOBIAN_STRUCTURE if self.has_analytic_jacobian else FINITE_DIFFERENCE_JACOBIAN_STRUCTURE,
            "jacobian_kernels": {process.name: "analytic" if process.jacobian is not None else "none" for process in self.processes},
            "maturity": MATURITY_LABEL,
        }

    def initial_state(self, initial_fields: Mapping[str, Quantity]) -> np.ndarray:
        """Flattened finite non-negative initial array in the stored field units."""

        names = self.model.field_names
        missing = set(names) - set(initial_fields)
        extra = set(initial_fields) - set(names)
        if missing or extra:
            raise ValueError(f"Initial fields must cover exactly the model fields; missing {sorted(missing)}, unexpected {sorted(extra)}.")
        arrays = []
        for name, units in zip(names, self.model.field_units.values(), strict=True):
            quantity = assert_compatible(require_quantity(initial_fields[name], name=name), units, name=name)
            values = np.broadcast_to(np.asarray(quantity.magnitude, dtype=float), self.shape)
            if not np.isfinite(values).all() or (values < 0.0).any():
                raise ValueError(f"Initial field {name!r} must be finite and non-negative.")
            arrays.append(np.array(values, dtype=float))
        return np.stack(arrays).ravel()

    def simulate(
        self,
        *,
        initial_fields: Mapping[str, Quantity],
        t_span: tuple[Quantity, Quantity],
        t_eval: Quantity,
        solver_settings: SolverSettings | None = None,
        record_rates: bool = True,
        jacobian: str | None = None,
    ) -> "MyceliumResult":
        """Integrate the fields over ``t_span`` and return them at ``t_eval``.

        The Jacobian each implicit method receives is chosen by
        :meth:`jacobian_structure_for` from ``solver_settings`` and ``jacobian``
        (``"analytic"``, ``"finite_difference"`` or ``None`` for the default) and
        recorded in ``solver_metadata["jacobian_structure"]``.
        """

        settings = SolverSettings() if solver_settings is None else solver_settings
        time_units = self.model.time_units
        span = tuple(float(assert_compatible(require_quantity(value, name="t_span"), time_units).magnitude) for value in t_span)
        grid_times = np.asarray(assert_compatible(require_quantity(t_eval, name="t_eval"), time_units).magnitude, dtype=float)
        state0 = self.initial_state(initial_fields)
        options = settings.scipy_options(self.model.field_units, time_units, cells=self.model.grid.cell_count)
        structure = self.jacobian_structure_for(settings, jacobian)
        bandwidths: tuple[int, int] | None = None
        cell_major = False
        if structure == FINITE_DIFFERENCE_JACOBIAN_STRUCTURE:
            options["jac"] = self.jacobian
        elif structure == ANALYTIC_JACOBIAN_STRUCTURE:
            options["jac"] = self.analytic_jacobian
        elif structure == ANALYTIC_DENSE_JACOBIAN_STRUCTURE:
            options["jac"] = lambda time, state: self.analytic_jacobian(time, state).toarray()
        elif structure == BANDED_JACOBIAN_STRUCTURE:
            # On a one-axis grid a cell-major ordering (cell, field) keeps every coupling
            # within 2 F - 1 of the diagonal, so LSODA can difference and factor a banded
            # Jacobian instead of a dense one: 2 (2 F - 1) + 1 right-hand sides per
            # Jacobian instead of one per state.
            bandwidths = (2 * self.field_count - 1, 2 * self.field_count - 1)
            cell_major = True
        elif structure == ANALYTIC_BANDED_JACOBIAN_STRUCTURE:
            # The declared stencil in cell-major order: every entry within one slice of the first
            # axis lies in the band; the wrap of a periodic first axis is left out and counted.
            bandwidths = self.analytic_band_widths()
            cell_major = True
            options["jac"] = self.analytic_jacobian_banded
        if cell_major and bandwidths is not None:
            permutation, inverse = self._cell_major
            options["lband"], options["uband"] = bandwidths
            if isinstance(options.get("atol"), np.ndarray):
                options["atol"] = np.asarray(options["atol"], dtype=float)[permutation]

            def cell_major_rhs(time: float, state: np.ndarray) -> np.ndarray:
                return self.rhs(time, state[inverse])[permutation]

            result = solve_checked(cell_major_rhs, (span[0], span[1]), state0[permutation], t_eval=grid_times, **options)
            solution = np.asarray(result.y, dtype=float)[inverse]
        else:
            result = solve_checked(self.rhs, (span[0], span[1]), state0, t_eval=grid_times, **options)
            solution = np.asarray(result.y, dtype=float)
        trajectory = solution.T.reshape((grid_times.size, self.field_count, *self.shape))
        fields = {
            name: Q_(np.array(trajectory[:, index]), units)
            for index, (name, units) in enumerate(self.model.field_units.items())
        }
        rates: dict[str, Quantity] | None = None
        if record_rates:
            per_process: dict[str, list[np.ndarray]] = {process.name: [] for process in self.processes if process.rate is not None}
            for step, time in enumerate(grid_times):
                for name, values in self.rates(float(time), trajectory[step].ravel()).items():
                    per_process[name].append(values)
            rate_units = {process.name: process.rate_units for process in self.processes}
            rates = {name: Q_(np.stack(values), rate_units[name]) for name, values in per_process.items()}
        metadata = {
            "status": int(result.status),
            "nfev": int(result.nfev),
            "njev": int(getattr(result, "njev", 0) or 0),
            "nlu": int(getattr(result, "nlu", 0) or 0),
            "jacobian_structure": structure,
            "jacobian_bandwidth": options.get("lband"),
            "jacobian_bandwidths": None if bandwidths is None else list(bandwidths),
            "jacobian_entries_outside_band": (
                self.analytic_entries_outside_band() if structure == ANALYTIC_BANDED_JACOBIAN_STRUCTURE else None
            ),
            "kernel": self.summary(),
        }
        assumptions = list(self.model.assumptions)
        for process in self.model.processes:
            assumptions.extend(process.assumptions)
        return MyceliumResult(
            time=Q_(grid_times, time_units),
            fields=fields,
            initial_fields={name: Q_(np.array(self.unflatten(state0)[index]), units) for index, (name, units) in enumerate(self.model.field_units.items())},
            grid=self.model.grid,
            process_rates=rates,
            solver_settings=settings,
            solver_metadata=metadata,
            assumptions=assumptions,
            model_version=__version__,
            maturity=MATURITY_LABEL,
        )


@dataclass
class MyceliumResult:
    """Unit-bearing fields on the grid over time, with the record of how they were produced."""

    time: Quantity
    fields: dict[str, Quantity]
    initial_fields: dict[str, Quantity]
    grid: SpatialGrid
    process_rates: dict[str, Quantity] | None
    solver_settings: SolverSettings
    solver_metadata: dict[str, Any]
    assumptions: list[Assumption]
    model_version: str
    maturity: str
    limitations: tuple[str, ...] = field(
        default_factory=lambda: (
            "Continuum densities on a uniform grid: no individual hyphae, no colony boundary, no three-dimensional morphology.",
            "Exploratory until a registry record parameterises the processes and a colony-expansion dataset is checksummed.",
        )
    )

    @property
    def ndim(self) -> int:
        return self.grid.ndim

    @property
    def measure_dimension(self) -> int:
        return self.grid.measure_dimension

    def field_at_final_time(self, name: str) -> Quantity:
        values = self.fields[name]
        return Q_(np.asarray(values.magnitude)[-1], values.units)

    def spatial_integral(self, name: str) -> Quantity:
        """Integral of the field over the grid at every output time (units times metre to the measure dimension)."""

        values = self.fields[name]
        magnitudes = np.asarray(values.magnitude, dtype=float)
        integrals = np.array([spatial_integral(magnitudes[step], grid=self.grid) for step in range(magnitudes.shape[0])])
        return Q_(integrals, f"({values.units}) * meter ** {self.measure_dimension}")

    def occupied_measure(self, name: str, threshold: Quantity) -> Quantity:
        """Length, area or volume where the field is at or above ``threshold``, at every output time."""

        values = self.fields[name]
        level = float(assert_compatible(require_quantity(threshold, name="threshold"), str(values.units), name="threshold").magnitude)
        magnitudes = np.asarray(values.magnitude, dtype=float)
        measures = self.grid.cell_measures.reshape(-1)
        occupied = ((magnitudes >= level).reshape(magnitudes.shape[0], -1) * measures).sum(axis=1)
        return Q_(occupied, f"meter ** {self.measure_dimension}")

    def front_position(self, name: str, threshold: Quantity, *, axis: int = 0) -> Quantity:
        """Largest coordinate along ``axis`` where the field (maximised over the other axes) reaches ``threshold``.

        Linear interpolation between the last cell at or above the threshold
        and the next cell below it; ``nan`` when no cell reaches it.
        """

        values = self.fields[name]
        level = float(assert_compatible(require_quantity(threshold, name="threshold"), str(values.units), name="threshold").magnitude)
        magnitudes = np.asarray(values.magnitude, dtype=float)
        coordinates = self.grid.coordinates[axis]
        positions = np.full(magnitudes.shape[0], np.nan)
        for step in range(magnitudes.shape[0]):
            profile = np.moveaxis(magnitudes[step], axis, 0).reshape(magnitudes.shape[1 + axis], -1).max(axis=1)
            above = np.flatnonzero(profile >= level)
            if above.size == 0:
                continue
            last = int(above[-1])
            if last + 1 >= profile.size:
                positions[step] = coordinates[last]
                continue
            drop = profile[last] - profile[last + 1]
            fraction = 0.0 if drop <= 0.0 else (profile[last] - level) / drop
            positions[step] = coordinates[last] + fraction * (coordinates[last + 1] - coordinates[last])
        return Q_(positions, "meter")

    def results_summary(self) -> dict[str, Any]:
        return {
            "representation": MODEL_REPRESENTATION,
            "maturity": self.maturity,
            "grid": self.grid.to_dict(),
            "time_units": str(self.time.units),
            "steps": int(np.asarray(self.time.magnitude).size),
            "fields": {
                name: {
                    "units": str(values.units),
                    "initial_integral": float(self.spatial_integral(name).magnitude[0]),
                    "final_integral": float(self.spatial_integral(name).magnitude[-1]),
                    "final_min": float(np.min(np.asarray(values.magnitude)[-1])),
                    "final_max": float(np.max(np.asarray(values.magnitude)[-1])),
                }
                for name, values in self.fields.items()
            },
            "solver": self.solver_settings.to_dict(),
            "solver_metadata": self.solver_metadata,
            "assumptions": [assumption.name for assumption in self.assumptions],
            "limitations": list(self.limitations),
            "model_version": self.model_version,
        }


def total_amount(result: MyceliumResult, contributions: Sequence[tuple[str, Quantity]]) -> Quantity:
    """Sum of weighted field integrals over time, for conservation ledgers.

    ``contributions`` pairs a field name with the factor converting one unit
    of that field into the common amount; the result has the units of
    ``factor * field * metre ** ndim``.
    """

    total: Quantity | None = None
    for name, factor in contributions:
        term = result.spatial_integral(name) * require_quantity(factor, name=f"factor[{name}]")
        total = term if total is None else total + term
    if total is None:
        raise ValueError("total_amount needs at least one contribution.")
    return total


__all__ = [
    "ANALYTIC_BANDED_JACOBIAN_STRUCTURE",
    "ANALYTIC_DENSE_JACOBIAN_STRUCTURE",
    "ANALYTIC_JACOBIAN_STRUCTURE",
    "BANDED_JACOBIAN_STRUCTURE",
    "FINITE_DIFFERENCE_JACOBIAN_STRUCTURE",
    "JACOBIAN_STRUCTURE",
    "JACOBIAN_CHOICES",
    "MATURITY_LABEL",
    "MODEL_REPRESENTATION",
    "NEGATIVE_FIELD_POLICY",
    "CompiledFieldProcess",
    "CompiledMyceliumModel",
    "MyceliumModel",
    "MyceliumResult",
    "total_amount",
]
