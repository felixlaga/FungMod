"""First-order thermal inactivation with Arrhenius temperature dependence.

Equations
---------

::

    k_d(T) = k_d,ref exp( -(E_d / R) (1/T - 1/T_ref) )
    dA/dt  = -k_d(T) A

``A`` is an active pool (an enzyme activity or concentration), ``k_d,ref`` the
inactivation rate constant measured at ``T_ref`` and ``E_d`` the apparent
activation energy of inactivation.

Limitations
-----------

Irreversible single-exponential loss only. No reversible unfolding
(Lumry-Eyring), no proteolysis, no substrate or stabilizer protection, no
pH-dependent stability, and no temperature dynamics; the temperature is read
once from the static environment.
"""

from __future__ import annotations

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.arrhenius import arrhenius_reference_scaled_rate


def thermal_inactivation_assumption() -> Assumption:
    """Return the first-order Arrhenius thermal-inactivation assumption."""

    return Assumption(
        name="first-order thermal inactivation with Arrhenius rate constant",
        description=(
            "An active pool is lost irreversibly at a first-order rate whose constant follows "
            "the Arrhenius reference form in the environment temperature."
        ),
        justification=(
            "Single-exponential activity decay with an apparent inactivation energy is the "
            "minimal sourced description of enzyme thermal stability."
        ),
        known_limitations=(
            "No reversible unfolding, proteolysis, aggregation, substrate or stabilizer "
            "protection, pH-dependent stability, or temperature dynamics; the constant is "
            "only as transferable as the preparation and buffer it was measured in."
        ),
        source="Canonical first-order enzyme inactivation kinetics with Arrhenius temperature dependence.",
    )


def arrhenius_inactivation_rate_constant(
    *,
    reference_rate_constant: Quantity,
    inactivation_energy: Quantity,
    temperature: Quantity,
    reference_temperature: Quantity,
    minimum_temperature: Quantity | None = None,
    maximum_temperature: Quantity | None = None,
    source: str,
) -> Quantity:
    """Compute ``k_d(T)`` from a reference constant and an inactivation energy."""

    if not has_text(source):
        raise ValueError("A source is required for thermal inactivation constants.")
    reference = require_quantity(reference_rate_constant, name="reference_rate_constant")
    if np.any(np.asarray(reference.magnitude, dtype=float) < 0):
        raise ValueError("reference_rate_constant must be non-negative.")
    return arrhenius_reference_scaled_rate(
        reference_rate=reference,
        activation_energy=inactivation_energy,
        temperature=temperature,
        reference_temperature=reference_temperature,
        minimum_temperature=minimum_temperature,
        maximum_temperature=maximum_temperature,
        source=source,
        output_units=str(reference.units),
    )


def thermal_inactivation_rate(
    *,
    active_pool: Quantity,
    rate_constant: Quantity,
    rate_units: str,
) -> Quantity:
    """Compute ``k_d A`` for a non-negative active pool."""

    active = require_quantity(active_pool, name="active_pool")
    if np.any(np.asarray(active.magnitude, dtype=float) < 0):
        raise ValueError("active_pool must be non-negative.")
    return assert_compatible(rate_constant * active, rate_units, name="thermal inactivation rate")


__all__ = [
    "arrhenius_inactivation_rate_constant",
    "thermal_inactivation_assumption",
    "thermal_inactivation_rate",
]
