"""Sourced finite-chain scission laws (Niu et al. 2016, Eqs 12-20).

Rates are one channel per bond for endo action and one channel per chain for
exo action. The input concentration basis is moles of chains per volume;
monomer-equivalent material is the chain-length-weighted sum of those pools.
No chain-end exhaustion coefficient is fitted or assumed.
"""

from __future__ import annotations

import numpy as np


def chain_scission_rate_and_gradient(
    *,
    enzyme: float,
    chains: np.ndarray,
    weights: np.ndarray,
    parent_index: int,
    kcat: float,
    km: float,
    accessible_fraction: float,
) -> tuple[float, float, np.ndarray]:
    """Rate and derivatives with respect to enzyme and each chain pool.

    All concentrations must have one common unit and kcat one inverse-time
    unit. This float primitive is shared by quantity and compiled paths.
    """
    values = np.concatenate(([enzyme, kcat, km, accessible_fraction], chains, weights))
    if not np.isfinite(values).all():
        raise ValueError("Chain-scission states and constants must be finite.")
    if enzyme < 0 or kcat < 0 or np.any(chains < 0) or np.any(weights <= 0):
        raise ValueError("Enzyme, chain pools and kcat must be non-negative; weights positive.")
    if km <= 0 or not 0 <= accessible_fraction <= 1:
        raise ValueError("km must be positive and accessible_fraction must lie in [0, 1].")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            denominator = km + accessible_fraction * float(weights @ chains)
            coefficient = kcat * accessible_fraction
            parent = chains[parent_index]
            rate = coefficient * enzyme * parent / denominator
            derivative_enzyme = coefficient * parent / denominator
            gradient = -coefficient * enzyme * parent * accessible_fraction * weights / denominator**2
            gradient[parent_index] += coefficient * enzyme / denominator
    except (OverflowError, FloatingPointError, ZeroDivisionError) as exc:
        raise ValueError("Chain-scission inputs exceed the finite numerical range.") from exc
    if not np.isfinite([rate, derivative_enzyme, *gradient]).all():
        raise ValueError("Chain-scission inputs exceed the finite numerical range.")
    return rate, derivative_enzyme, gradient
