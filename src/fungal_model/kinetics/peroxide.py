"""Primed-enzyme peroxide kinetics from Kuusk et al. 2018, Eqs 4-5.

The compulsory-order ternary law keeps substrate depletion explicit. Constants
are preparation-specific. No numerical biological constants are supplied.
"""

from __future__ import annotations

import numpy as np


def peroxide_rate_and_gradient(
    *,
    substrate: float,
    peroxide: float,
    enzyme: float,
    kcat: float,
    peroxide_km: float,
    substrate_km: float,
    substrate_binding: float,
) -> tuple[float, np.ndarray]:
    """Oxidative cuts per volume/time; gradient order is S, H, E."""
    _validate(substrate, peroxide, enzyme, kcat, peroxide_km, substrate_km, substrate_binding)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            s, h, e = substrate, peroxide, enzyme
            d = substrate_binding * peroxide_km + peroxide_km * s + substrate_km * h + s * h
            numerator = kcat * e * s * h
            rate = numerator / d
            gradient = np.array(
                [
                    kcat * e * h * (substrate_binding * peroxide_km + substrate_km * h) / d**2,
                    kcat * e * s * peroxide_km * (substrate_binding + s) / d**2,
                    kcat * s * h / d,
                ]
            )
    except (OverflowError, FloatingPointError, ZeroDivisionError) as exc:
        raise ValueError("Peroxide kinetics inputs exceed the finite numerical range.") from exc
    return _finite_result(rate, gradient)


def peroxide_inactivation_rate_and_gradient(
    *,
    substrate: float,
    peroxide: float,
    enzyme: float,
    inactivation_constant: float,
    substrate_km: float,
) -> tuple[float, np.ndarray]:
    """Effective free-enzyme damage; gradient order is S, H, E."""
    _validate(substrate, peroxide, enzyme, inactivation_constant, substrate_km)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            d = substrate_km + substrate
            coefficient = inactivation_constant * substrate_km
            rate = coefficient * enzyme * peroxide / d
            gradient = np.array(
                [
                    -coefficient * enzyme * peroxide / d**2,
                    coefficient * enzyme / d,
                    coefficient * peroxide / d,
                ]
            )
    except (OverflowError, FloatingPointError, ZeroDivisionError) as exc:
        raise ValueError("Peroxide kinetics inputs exceed the finite numerical range.") from exc
    return _finite_result(rate, gradient)


def _finite_result(rate: float, gradient: np.ndarray) -> tuple[float, np.ndarray]:
    if not np.isfinite([rate, *gradient]).all():
        raise ValueError("Peroxide kinetics inputs exceed the finite numerical range.")
    return rate, gradient


def _validate(s: float, h: float, e: float, k: float, *positive: float) -> None:
    if not np.isfinite([s, h, e, k, *positive]).all():
        raise ValueError("Peroxide kinetics states and constants must be finite.")
    if min(s, h, e, k) < 0:
        raise ValueError("Peroxide kinetics states and rate constants must be non-negative.")
    if min(positive) <= 0:
        raise ValueError("Peroxide kinetics binding and saturation constants must be positive.")
