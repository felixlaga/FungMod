"""Shared integration for exploratory inhibited progress-curve studies.

The base denominator is the same kernel used by the configured inhibition
modifier. Optional exponential loss of activity is a declared mathematical
hypothesis, not a validated thermal mechanism or a default registry process.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics._coupled_inhibition import coupled_inhibition_denominator


class ProgressIntegrationError(ValueError):
    """The declared exploratory study could not be integrated."""


@dataclass(frozen=True)
class ProgressTrajectory:
    time: Quantity
    substrate: Quantity
    product: Quantity
    source: str
    hypothesis_source: str
    maturity: str = 'exploratory_software_tested'


def simulate_inhibited_progress(
    *, times: Quantity, initial_substrate: Quantity, initial_product: Quantity,
    vmax: Quantity, km: Quantity, product_ki: Quantity, substrate_ki: Quantity | None,
    decay_rate: Quantity, product_stoichiometry: float, source: str, hypothesis_source: str,
) -> ProgressTrajectory:
    """Integrate in explicit caller units with complete solver checks.

    Stoichiometry, initial product, all constants, and the hypothesis rationale
    are mandatory. The source describes the kinetic form, not evidence that it
    applies to every supplied preparation. States are floored at zero only when
    evaluating trial solver rates, matching the existing exploratory runners.
    """
    if not has_text(source) or not has_text(hypothesis_source):
        raise ProgressIntegrationError('Kinetic source and hypothesis_source are required.')
    time = require_quantity(times, 'times')
    assert_compatible(time, 'second')
    grid = np.asarray(time.magnitude, dtype=float)
    if (grid.ndim != 1 or not grid.size or not np.all(np.isfinite(grid))
            or grid[0] < 0 or grid[-1] <= 0 or np.any(np.diff(grid) <= 0)):
        raise ProgressIntegrationError('Times must be finite, increasing and nonnegative with a positive endpoint.')
    units = str(require_quantity(initial_substrate).units)
    # This study contract concerns homogeneous concentrations only.
    assert_compatible(initial_substrate, 'mole/liter')
    time_units = str(time.units)

    def scalar(value, target, name, *, positive=True):
        array = np.asarray(assert_compatible(value, target, name=name).magnitude, dtype=float)
        if array.ndim or not np.isfinite(array) or (array <= 0 if positive else array < 0):
            raise ProgressIntegrationError(f'{name} must be a finite {"positive" if positive else "nonnegative"} scalar.')
        return float(array)

    s0 = scalar(initial_substrate, units, 'initial_substrate')
    p0 = scalar(initial_product, units, 'initial_product', positive=False)
    v = scalar(vmax, f'({units})/({time_units})', 'vmax')
    m = scalar(km, units, 'km')
    kp = scalar(product_ki, units, 'product_ki')
    ki = None if substrate_ki is None else scalar(substrate_ki, units, 'substrate_ki')
    kd = scalar(decay_rate, f'1/({time_units})', 'decay_rate', positive=False)
    if not np.isfinite(product_stoichiometry) or product_stoichiometry <= 0:
        raise ProgressIntegrationError('product_stoichiometry must be finite and positive.')

    def rhs(t, state):
        substrate, product = max(float(state[0]), 0.0), max(float(state[1]), 0.0)
        rate = v * np.exp(-kd*t) * substrate / coupled_inhibition_denominator(substrate, product, m, ki, kp)
        return [-rate, product_stoichiometry*rate]

    solution = solve_ivp(rhs, (0.0, float(grid[-1])), [s0, p0], t_eval=grid,
                         rtol=1e-10, atol=1e-12, method='LSODA')
    values = np.asarray(solution.y, dtype=float)
    if not solution.success or values.shape != (2, grid.size) or not np.all(np.isfinite(values)):
        raise ProgressIntegrationError(f'integration failed or returned incomplete/nonfinite states: {solution.message}')
    return ProgressTrajectory(time, Q_(values[0], units), Q_(values[1], units), source, hypothesis_source)
