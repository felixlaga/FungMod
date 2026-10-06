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
from typing import Any

import numpy as np

from fungal_model import __version__
from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import InvalidMechanismError
from fungal_model.core.kernels import conversion_factor
from fungal_model.core.numerics import SolverSettings, solve_checked
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.mycelium.fields import FieldKernelContext, FieldSpec, RateFieldKernel, TendencyKernel
from fungal_model.mycelium.grid import SpatialGrid
from fungal_model.mycelium.operators import spatial_integral
from fungal_model.mycelium.processes import FieldProcess
from fungal_model.transport._sparsity import cartesian_jacobian_sparsity

MODEL_REPRESENTATION = "compiled_mycelium_fields"
NEGATIVE_FIELD_POLICY = "kernels evaluated at max(field, 0); integrated fields never clipped"
JACOBIAN_STRUCTURE = "cartesian_sparse_nearest_neighbour"
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

    def jacobian_sparsity(self):
        return cartesian_jacobian_sparsity(self.shape, self.field_count, local_reactions=True)

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
            "jacobian_structure": JACOBIAN_STRUCTURE,
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
    ) -> "MyceliumResult":
        settings = SolverSettings() if solver_settings is None else solver_settings
        time_units = self.model.time_units
        span = tuple(float(assert_compatible(require_quantity(value, name="t_span"), time_units).magnitude) for value in t_span)
        grid_times = np.asarray(assert_compatible(require_quantity(t_eval, name="t_eval"), time_units).magnitude, dtype=float)
        state0 = self.initial_state(initial_fields)
        options = settings.scipy_options(self.model.field_units, time_units, cells=self.model.grid.cell_count)
        if settings.uses_jacobian and settings.method != "LSODA":
            options["jac_sparsity"] = self.jacobian_sparsity()
        result = solve_checked(self.rhs, (span[0], span[1]), state0, t_eval=grid_times, **options)
        trajectory = np.asarray(result.y, dtype=float).T.reshape((grid_times.size, self.field_count, *self.shape))
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
            "jacobian_structure": JACOBIAN_STRUCTURE if "jac_sparsity" in options else "backend_default",
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
    "JACOBIAN_STRUCTURE",
    "MATURITY_LABEL",
    "MODEL_REPRESENTATION",
    "NEGATIVE_FIELD_POLICY",
    "CompiledFieldProcess",
    "CompiledMyceliumModel",
    "MyceliumModel",
    "MyceliumResult",
    "total_amount",
]
