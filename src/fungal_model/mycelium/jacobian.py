"""Analytic sparse Jacobians of the spatial mycelium core on the nearest-neighbour stencil.

A field process may offer the derivative of its tendency with respect to the
projected fields as a :class:`FieldJacobianKernel`: a fixed tuple of
:class:`StencilBlock` declarations (which field row depends on which field,
in the same cell or in the neighbouring cell one step along an axis) and a
kernel that returns one coefficient array per block, shaped like the grid.
:class:`StencilAssembler` maps the blocks of every process once onto a
compressed sparse column pattern of the flattened field-major state and then
scatters the coefficients into its data array at every evaluation, so no
dense matrix is ever formed.

The transport helpers differentiate the finite-volume operators of
:mod:`fungal_model.mycelium.operators` exactly: the conservative divergence of
central-gradient diffusive fluxes (constant coefficients) and of first-order
upwind drift fluxes (state-dependent coefficients, with the upwind side held
fixed, the one-sided derivative where a face velocity is exactly zero), with
the geometry's face weights and no flux through no-flux outer faces. Nothing
here knows about a fungus, a substrate or a mechanism: the blocks are
declared by the processes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from fungal_model.mycelium.grid import SpatialGrid
from fungal_model.mycelium.operators import face_gradient, face_values

#: Kernel returning one coefficient array (or a scalar broadcast over the
#: grid) per declared block, for the projected field array.
StencilValuesKernel = Callable[[float, np.ndarray], Sequence[np.ndarray | float]]


@dataclass(frozen=True)
class StencilBlock:
    """``d tendency[row](cell) / d field[column](neighbour)`` for every cell of the grid.

    ``axis`` is ``None`` for the same cell; otherwise the neighbour is one
    ``step`` (+1 or -1) along ``axis``, wrapped on a periodic axis and absent
    beyond a no-flux face (where the assembler ignores the coefficient).
    """

    row: int
    column: int
    axis: int | None = None
    step: int = 0

    def __post_init__(self) -> None:
        if self.row < 0 or self.column < 0:
            raise ValueError("StencilBlock rows and columns are non-negative field indices.")
        if self.axis is None:
            if self.step != 0:
                raise ValueError("A same-cell StencilBlock has step 0.")
        elif self.axis < 0 or self.step not in (1, -1):
            raise ValueError("A neighbour StencilBlock has a non-negative axis and a step of +1 or -1.")

    @property
    def key(self) -> tuple[int, int, int, int]:
        return (self.row, self.column, -1 if self.axis is None else self.axis, self.step)


@dataclass(frozen=True)
class FieldJacobianKernel:
    """The analytic Jacobian of one process: its declared blocks and their coefficient kernel."""

    blocks: tuple[StencilBlock, ...]
    values: StencilValuesKernel


# ---------------------------------------------------------------------------
# Transport coefficients
# ---------------------------------------------------------------------------


def _cell_slices(ndim: int, axis: int, extent: int) -> tuple[tuple[slice, ...], tuple[slice, ...]]:
    """Slices of a face array (``extent + 1`` along ``axis``) giving each cell's lower and upper face."""

    lower: list[slice] = [slice(None)] * ndim
    upper: list[slice] = [slice(None)] * ndim
    lower[axis] = slice(0, extent)
    upper[axis] = slice(1, extent + 1)
    return tuple(lower), tuple(upper)


def _face_activity(grid: SpatialGrid, axis: int) -> np.ndarray:
    """1 on faces that carry flux, 0 on the outer faces of a no-flux axis; face-array shaped along ``axis``."""

    extent = grid.shape[axis]
    activity = np.ones(extent + 1)
    if not grid.periodic_axes[axis]:
        activity[0] = 0.0
        activity[-1] = 0.0
    shape = [1] * grid.ndim
    shape[axis] = extent + 1
    return activity.reshape(shape)


@dataclass(frozen=True)
class TransportStencil:
    """Coefficients of one row field with respect to one column field on the nearest-neighbour stencil.

    ``local`` is the same-cell coefficient summed over the axes and
    ``neighbours`` holds, per axis, the coefficients of the neighbour one step
    down and one step up the axis; every array is shaped like the grid.
    """

    local: np.ndarray
    neighbours: tuple[tuple[np.ndarray, np.ndarray], ...]

    def __add__(self, other: "TransportStencil") -> "TransportStencil":
        return TransportStencil(
            local=self.local + other.local,
            neighbours=tuple(
                (lower + other_lower, upper + other_upper)
                for (lower, upper), (other_lower, other_upper) in zip(self.neighbours, other.neighbours, strict=True)
            ),
        )

    def values(self) -> list[np.ndarray]:
        """Coefficient arrays in the block order of :func:`transport_blocks`."""

        values = [self.local]
        for lower, upper in self.neighbours:
            values.append(lower)
            values.append(upper)
        return values


def diffusion_stencil(grid: SpatialGrid, diffusivity: float) -> TransportStencil:
    """Coefficients of ``D laplacian`` built from face gradients (``diffusive_tendency``).

    The tendency of cell ``c`` along each axis is ``w_up D (u[c+1] - u[c]) / dx
    - w_lo D (u[c] - u[c-1]) / dx`` with the geometry's face weights; a no-flux
    outer face contributes nothing.
    """

    local = np.zeros(grid.shape)
    neighbours = []
    for axis, width in enumerate(grid.cell_widths):
        weight_lower, weight_upper = grid.face_weights(axis)
        activity = _face_activity(grid, axis)
        lower_faces, upper_faces = _cell_slices(grid.ndim, axis, grid.shape[axis])
        upper = np.broadcast_to(diffusivity * weight_upper / width * activity[upper_faces], grid.shape)
        lower = np.broadcast_to(diffusivity * weight_lower / width * activity[lower_faces], grid.shape)
        local = local - (upper + lower)
        neighbours.append((np.array(lower), np.array(upper)))
    return TransportStencil(local=local, neighbours=tuple(neighbours))


def upwind_drift_stencil(grid: SpatialGrid, transported: np.ndarray, potential: np.ndarray, mobility: float) -> tuple[TransportStencil, TransportStencil]:
    """Derivatives of ``-div(v q)`` with ``v = mobility grad(g)`` on faces and first-order upwind ``q``.

    Returns the coefficients with respect to the carried field ``q`` and to
    the field ``g`` whose gradient sets the face velocity. For the face flux
    ``F = v q_up`` (``q_up`` the lower cell where ``v > 0``, the upper cell
    otherwise) ``dF/dq_lower = max(v, 0)``, ``dF/dq_upper = min(v, 0)`` and
    ``dF/dg_upper = -dF/dg_lower = mobility q_up / dx``; the tendency of a cell
    is ``-(w_up F_up - w_lo F_lo)``. No-flux outer faces carry no flux whatever
    the fields, so they contribute nothing.
    """

    carried_local = np.zeros(grid.shape)
    potential_local = np.zeros(grid.shape)
    carried_neighbours = []
    potential_neighbours = []
    for axis, (width, periodic) in enumerate(zip(grid.cell_widths, grid.periodic_axes, strict=True)):
        velocity = mobility * face_gradient(potential, axis=axis, cell_width=width, periodic=periodic)
        lower_values, upper_values = face_values(transported, axis=axis, periodic=periodic)
        activity = _face_activity(grid, axis)
        positive = velocity > 0.0
        d_lower = np.where(positive, velocity, 0.0) * activity
        d_upper = np.where(positive, 0.0, velocity) * activity
        carried = np.where(positive, lower_values, upper_values) * activity * (mobility / width)
        weight_lower, weight_upper = grid.face_weights(axis)
        lower_faces, upper_faces = _cell_slices(grid.ndim, axis, grid.shape[axis])
        carried_local = carried_local + weight_lower * d_upper[lower_faces] - weight_upper * d_lower[upper_faces]
        carried_neighbours.append((weight_lower * d_lower[lower_faces], -weight_upper * d_upper[upper_faces]))
        potential_local = potential_local + weight_upper * carried[upper_faces] + weight_lower * carried[lower_faces]
        potential_neighbours.append((-weight_lower * carried[lower_faces], -weight_upper * carried[upper_faces]))
    return (
        TransportStencil(local=carried_local, neighbours=tuple(carried_neighbours)),
        TransportStencil(local=potential_local, neighbours=tuple(potential_neighbours)),
    )


def transport_blocks(row: int, column: int, ndim: int) -> tuple[StencilBlock, ...]:
    """The same-cell block and the two neighbour blocks per axis, in the order of :meth:`TransportStencil.values`."""

    blocks = [StencilBlock(row, column)]
    for axis in range(ndim):
        blocks.append(StencilBlock(row, column, axis, -1))
        blocks.append(StencilBlock(row, column, axis, 1))
    return tuple(blocks)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _index_dtype(*sizes: int) -> type[np.signedinteger]:
    return np.int32 if max(sizes) < np.iinfo(np.int32).max else np.int64


class StencilAssembler:
    """A fixed compressed-sparse-column pattern for the union of declared stencil blocks.

    The state is the flattened field-major array ``(field, *grid.shape)``.
    Built once per compiled model; at every evaluation :meth:`scatter` adds
    coefficient arrays into the data vector and :meth:`matrix` scales each
    column by the derivative of the projection ``max(field, 0)``. Several
    blocks may land on one entry (two processes, or both neighbours of a cell on
    a periodic axis of two cells); their coefficients add.
    """

    def __init__(self, grid: SpatialGrid, field_count: int, keys: Sequence[tuple[int, int, int, int]]) -> None:
        self.shape = grid.shape
        self.field_count = int(field_count)
        cells = grid.cell_count
        size = cells * self.field_count
        self.size = size
        index = np.arange(cells).reshape(grid.shape)
        periodic = grid.periodic_axes
        self.keys: tuple[tuple[int, int, int, int], ...] = tuple(dict.fromkeys(keys))
        self._key_id = {key: number for number, key in enumerate(self.keys)}
        valid_cells: list[np.ndarray | None] = []
        linear: list[np.ndarray] = []
        for row, column, axis, step in self.keys:
            if row >= self.field_count or column >= self.field_count:
                raise ValueError(f"Stencil block ({row}, {column}) names a field outside the {self.field_count} model fields.")
            if axis < 0:
                cells_valid = None
                rows = index.ravel()
                columns = index.ravel()
            else:
                if axis >= grid.ndim:
                    raise ValueError(f"Stencil block axis {axis} is outside the {grid.ndim}-axis grid.")
                neighbour = np.roll(index, -step, axis=axis)
                if periodic[axis]:
                    cells_valid = None
                    rows = index.ravel()
                    columns = neighbour.ravel()
                else:
                    position = np.arange(grid.shape[axis]).reshape([-1 if k == axis else 1 for k in range(grid.ndim)])
                    keep = np.broadcast_to(position != (grid.shape[axis] - 1 if step > 0 else 0), grid.shape).ravel()
                    cells_valid = np.flatnonzero(keep)
                    rows = index.ravel()[cells_valid]
                    columns = neighbour.ravel()[cells_valid]
            valid_cells.append(cells_valid)
            linear.append((np.asarray(columns, dtype=np.int64) + column * cells) * size + (np.asarray(rows, dtype=np.int64) + row * cells))
        if linear:
            unique, inverse = np.unique(np.concatenate(linear), return_inverse=True)
        else:
            unique, inverse = np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        entry_columns = unique // size
        dtype = _index_dtype(size, unique.size)
        self.indices = (unique % size).astype(dtype)
        self.indptr = np.concatenate([[0], np.cumsum(np.bincount(entry_columns, minlength=size))]).astype(dtype)
        self.entry_columns = entry_columns.astype(np.int64)
        self.entry_rows = (unique % size).astype(np.int64)
        self.nnz = int(unique.size)
        positions: list[np.ndarray] = []
        start = 0
        for block in linear:
            positions.append(np.asarray(inverse[start : start + block.size], dtype=np.int64))
            start += block.size
        self._positions = tuple(positions)
        self._valid_cells = tuple(valid_cells)

    def key_ids(self, blocks: Sequence[StencilBlock]) -> tuple[int, ...]:
        return tuple(self._key_id[block.key] for block in blocks)

    def pattern(self):
        """The declared pattern as a boolean CSC matrix."""

        from scipy import sparse

        return sparse.csc_matrix((np.ones(self.nnz, dtype=bool), self.indices.copy(), self.indptr.copy()), shape=(self.size, self.size))

    def scatter(self, data: np.ndarray, key_ids: Sequence[int], values: Sequence[np.ndarray | float]) -> None:
        """Add one process's coefficient arrays (aligned with ``key_ids``) into ``data``."""

        if len(values) != len(key_ids):
            raise ValueError(f"A Jacobian kernel returned {len(values)} coefficient arrays for {len(key_ids)} declared blocks.")
        for key_id, value in zip(key_ids, values, strict=True):
            flat = np.broadcast_to(np.asarray(value, dtype=float), self.shape).reshape(-1)
            cells = self._valid_cells[key_id]
            # Positions are unique within one block, so a fancy-indexed += is exact.
            data[self._positions[key_id]] += flat if cells is None else flat[cells]

    def matrix(self, data: np.ndarray, state: np.ndarray):
        """CSC matrix of ``data`` with every column scaled by ``d max(y, 0) / dy`` (1 where ``y >= 0``)."""

        from scipy import sparse

        mask = np.asarray(state, dtype=float) >= 0.0
        scaled = np.where(mask[self.entry_columns], data, 0.0)
        return sparse.csc_matrix((scaled, self.indices.copy(), self.indptr.copy()), shape=(self.size, self.size))


def stencil_colours(grid: SpatialGrid) -> np.ndarray:
    """A colour per cell such that no two cells of one colour lie in a common nearest-neighbour stencil.

    Per axis the colour is the index modulo three, which separates any two
    cells within two steps on a no-flux axis and on a periodic axis whose
    length is a multiple of three; on any other periodic axis the one or two
    cells after the last whole triple get colours of their own, so the wrap
    never joins two cells of one colour. Cells are combined in mixed radix.
    """

    colour = np.zeros(grid.shape, dtype=np.int64)
    for axis, (extent, periodic) in enumerate(zip(grid.shape, grid.periodic_axes, strict=True)):
        index = np.arange(extent)
        per_axis = index % 3
        radix = 3
        if periodic and extent % 3:
            whole = 3 * (extent // 3)
            per_axis = np.where(index < whole, index % 3, 3 + index - whole)
            radix = 3 + extent - whole
        colour = colour * radix + per_axis.reshape([-1 if k == axis else 1 for k in range(grid.ndim)])
    return colour


__all__ = [
    "FieldJacobianKernel",
    "StencilAssembler",
    "StencilBlock",
    "StencilValuesKernel",
    "TransportStencil",
    "diffusion_stencil",
    "stencil_colours",
    "transport_blocks",
    "upwind_drift_stencil",
]
