"""Langmuir adsorption helper for surface-limited kinetics.

Equation
--------

``theta = K_ads * E / (1 + K_ads * E)``

where ``theta`` is fractional surface coverage, ``E`` is free enzyme quantity
in the chosen concentration units, and ``K_ads`` has reciprocal units to make
``K_ads * E`` dimensionless.

This is an equilibrium adsorption approximation. It does not model dynamic
adsorption/desorption states, irreversible binding, crowding beyond Langmuir
coverage, or surface heterogeneity.
"""

from __future__ import annotations

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Quantity, assert_compatible, require_quantity

LANGMUIR_DENOMINATOR_OFFSET = Parameter(
    name="Langmuir empty-site denominator offset",
    symbol="one_langmuir",
    value=1.0,
    units="dimensionless",
    uncertainty=None,
    source="Definition of the Langmuir adsorption isotherm denominator.",
    confidence_level="high",
    notes="Mathematical offset in theta = K_ads*E / (1 + K_ads*E).",
    measurement_method="definition",
)


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def langmuir_surface_coverage(
    *,
    free_enzyme: Quantity,
    adsorption_equilibrium_constant: Quantity,
) -> Quantity:
    """Compute fractional surface coverage from free enzyme and ``K_ads``."""

    enzyme = require_quantity(free_enzyme, name="free_enzyme")
    adsorption_constant = require_quantity(
        adsorption_equilibrium_constant,
        name="adsorption_equilibrium_constant",
    )
    _ensure_non_negative(enzyme, "free_enzyme")
    _ensure_non_negative(adsorption_constant, "adsorption_equilibrium_constant")

    adsorption_strength = assert_compatible(
        adsorption_constant * enzyme,
        "dimensionless",
        name="K_ads * free_enzyme",
    )
    denominator = LANGMUIR_DENOMINATOR_OFFSET.quantity + adsorption_strength
    return assert_compatible(
        adsorption_strength / denominator,
        "dimensionless",
        name="Langmuir surface coverage",
    )


__all__ = [
    "LANGMUIR_DENOMINATOR_OFFSET",
    "langmuir_surface_coverage",
]
