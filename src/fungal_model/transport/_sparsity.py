"""Conservative Jacobian structure for cell-local finite-volume dynamics."""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix


def cartesian_jacobian_sparsity(shape: tuple[int, ...], fields: int, *, local_reactions: bool):
    """Include axis neighbours (including periodic wraps) and local cross-fields.

    Including wrap entries on nonperiodic boundaries only overestimates sparsity.
    Never use this for a callable that can couple arbitrary spatial cells.
    """
    cells = int(np.prod(shape))
    indices = np.arange(cells).reshape(shape)
    rows, columns = [], []
    for field in range(fields):
        flat = indices.ravel() + field * cells
        rows.append(flat)
        columns.append(flat)
        for axis in range(len(shape)):
            for offset in (-1, 1):
                rows.append(flat)
                columns.append(np.roll(indices, offset, axis=axis).ravel() + field * cells)
        if local_reactions:
            for other in range(fields):
                if other != field:
                    rows.append(flat)
                    columns.append(indices.ravel() + other * cells)
    row, column = np.concatenate(rows), np.concatenate(columns)
    return coo_matrix((np.ones(row.size, dtype=bool), (row, column)),
                      shape=(cells * fields, cells * fields)).tocsr()
