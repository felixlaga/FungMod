"""Generic, bounded counterfactual comparisons on matching experimental runs.

Degree of synergy is full-mixture product increment divided by the sum of
individual-member increments at the SAME member doses. Leave-one-out runs
are reported separately and are never used as the synergy denominator.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.units import Quantity, assert_compatible, require_quantity


@dataclass(frozen=True)
class SynergyResult:
    degree_of_synergy: np.ndarray
    defined: np.ndarray
    full_increment: Quantity
    independent_increment: Quantity
    leave_one_out_increments: Mapping[str, Quantity]
    limitation: str = "Matched time grids, same member doses and identical non-enzyme conditions are required; synthetic runs do not validate biology."


def degree_of_synergy(
    *,
    full_increment: Quantity,
    individual_increments: Sequence[Quantity],
    leave_one_out_increments: Mapping[str, Quantity] | None = None,
) -> SynergyResult:
    """Compare baseline-subtracted product amounts or matched instantaneous rates.

    Undefined ratios (zero independent activity) are NaN with a false mask,
    including 0/0. A positive full result over zero is not evidence of an
    infinite finite degree of synergy. Negative increments are refused.
    """
    full = require_quantity(full_increment, name="full_increment")
    values = np.asarray(full.magnitude, dtype=float)
    if not individual_increments:
        raise ValueError("At least one individual-member result is required.")
    total = np.zeros_like(values)
    for increment in individual_increments:
        value = np.asarray(
            assert_compatible(increment, str(full.units), name="individual_increment").magnitude, dtype=float
        )
        if value.shape != values.shape or not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError("Individual increments must be finite, non-negative and have the full result shape.")
        total += value
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("Full increments must be finite and non-negative.")
    loo = dict(leave_one_out_increments or {})
    for key, increment in loo.items():
        value = np.asarray(assert_compatible(increment, str(full.units), name=key).magnitude, dtype=float)
        if value.shape != values.shape or not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError("Leave-one-out increments must be finite, non-negative and have the full result shape.")
    defined = total > 0
    ratio = np.full(values.shape, np.nan)
    np.divide(values, total, out=ratio, where=defined)
    return SynergyResult(ratio, defined, full, total * full.units, loo)


def run_synergy_counterfactuals(
    *,
    members: Sequence[str],
    run: Callable[[frozenset[str]], Any],
    observable: Callable[[Any], Quantity],
    max_members: int,
    include_leave_one_out: bool = True,
) -> SynergyResult:
    """Run full, singleton and optionally leave-one-out subsets with a hard bound.

    ``run`` receives the active member IDs; the caller owns the configured
    model and MUST preserve each retained member's dose and every other
    condition. ``observable`` must return a baseline-subtracted increment.
    Each unique subset is run once (useful for one and two member networks).
    No empty-subset subtraction is silently introduced.
    """
    names = tuple(members)
    if not isinstance(max_members, int) or max_members < 1 or not names or len(names) > max_members:
        raise ValueError("Counterfactual member count exceeds the explicit positive max_members limit.")
    if any(not n.strip() for n in names) or len(set(names)) != len(names):
        raise ValueError("Member identifiers must be nonempty and unique.")
    cache: dict[frozenset[str], Quantity] = {}

    def result(subset: frozenset[str]) -> Quantity:
        if subset not in cache:
            cache[subset] = observable(run(subset))
        return cache[subset]

    all_members = frozenset(names)
    full = result(all_members)
    singles = [result(frozenset((name,))) for name in names]
    loo = {name: result(all_members - {name}) for name in names} if include_leave_one_out else {}
    return degree_of_synergy(full_increment=full, individual_increments=singles, leave_one_out_increments=loo)
