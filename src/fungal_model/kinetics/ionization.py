"""pH-dependent Michaelis-Menten kinetics through diprotic ionization factors.

Equations
---------

Two ionizations of the free enzyme (``pK_e1 < pK_e2``) and two of the
enzyme-substrate complex (``pK_es1 < pK_es2``) scale the limiting constants::

    f_e(pH)  = (10^(pK_e1 - pH) + 1) (10^(pH - pK_e2) + 1)
    f_es(pH) = (10^(pK_es1 - pH) + 1) (10^(pH - pK_es2) + 1)

    kcat(pH)      = k0 / f_es(pH)
    (kcat/Km)(pH) = (k0 / Km0) / f_e(pH)
    Km(pH)        = kcat(pH) / (kcat/Km)(pH) = Km0 f_e(pH) / f_es(pH)

    v = E kcat(pH) S / (Km(pH) + S)

This is the "Michaelis-Menten (pH-dependent)" law as SABIO-RK records it
(kinetic-law type 24); the product form of the two ionization terms is kept
exactly so that database constants reproduce the deposited law.

Limitations
-----------

The ionization factors are an empirical bell-shaped description of a pH
profile measured over a finite range with several buffers; buffer identity,
ionic strength, and pH-dependent stability are not represented. ``k0`` and
``Km0`` are limiting constants of the fit, not the values at any one pH.
"""

from __future__ import annotations

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.michaelis_menten import enzyme_explicit_michaelis_menten_rate
from fungal_model.kinetics.ph import warn_if_ph_outside_range


def ph_ionization_michaelis_menten_assumption() -> Assumption:
    """Return the diprotic pH-dependent Michaelis-Menten assumption."""

    return Assumption(
        name="diprotic ionization pH dependence of Michaelis-Menten constants",
        description=(
            "kcat and kcat/Km are each scaled by a two-pKa ionization factor so that the "
            "turnover and Michaelis constant vary with pH as fitted by the source."
        ),
        justification=(
            "The classical diprotic model reproduces bell-shaped pH profiles of glycoside "
            "hydrolases and is the law form deposited for the constants in use."
        ),
        known_limitations=(
            "Empirical bell-shaped profile fitted over a finite pH range with several buffers; "
            "no buffer-specific, ionic-strength, or pH-dependent stability effects, and no "
            "extrapolation claim outside the source range."
        ),
        source="Classical diprotic enzyme ionization model; SABIO-RK kinetic-law type 24 form.",
    )


def diprotic_ionization_factor(*, ph: Quantity, lower_pk: Quantity, upper_pk: Quantity) -> Quantity:
    """Compute ``(10^(pK_low - pH) + 1) (10^(pH - pK_high) + 1)``."""

    ph_value = _dimensionless(ph, "pH")
    lower = _dimensionless(lower_pk, "lower_pk")
    upper = _dimensionless(upper_pk, "upper_pk")
    if np.any(lower >= upper):
        raise ValueError("Diprotic ionization requires lower_pk < upper_pk.")
    factor = (10.0 ** (lower - ph_value) + 1.0) * (10.0 ** (ph_value - upper) + 1.0)
    return Q_(factor, "dimensionless")


def ph_dependent_turnover(
    *,
    turnover: Quantity,
    ph: Quantity,
    complex_lower_pk: Quantity,
    complex_upper_pk: Quantity,
) -> Quantity:
    """Compute ``kcat(pH) = k0 / f_es(pH)``."""

    k0 = require_quantity(turnover, name="turnover")
    _ensure_non_negative(k0, "turnover")
    factor = diprotic_ionization_factor(ph=ph, lower_pk=complex_lower_pk, upper_pk=complex_upper_pk)
    return assert_compatible(k0 / factor.magnitude, str(k0.units), name="pH-dependent turnover")


def ph_dependent_michaelis_constant(
    *,
    michaelis_constant: Quantity,
    ph: Quantity,
    free_enzyme_lower_pk: Quantity,
    free_enzyme_upper_pk: Quantity,
    complex_lower_pk: Quantity,
    complex_upper_pk: Quantity,
) -> Quantity:
    """Compute ``Km(pH) = Km0 f_e(pH) / f_es(pH)``."""

    km0 = require_quantity(michaelis_constant, name="michaelis_constant")
    _ensure_positive(km0, "michaelis_constant")
    free_factor = diprotic_ionization_factor(
        ph=ph, lower_pk=free_enzyme_lower_pk, upper_pk=free_enzyme_upper_pk
    )
    complex_factor = diprotic_ionization_factor(
        ph=ph, lower_pk=complex_lower_pk, upper_pk=complex_upper_pk
    )
    return assert_compatible(
        km0 * (free_factor.magnitude / complex_factor.magnitude),
        str(km0.units),
        name="pH-dependent Michaelis constant",
    )


def ph_ionization_michaelis_menten_rate(
    *,
    substrate: Quantity,
    enzyme: Quantity,
    turnover: Quantity,
    michaelis_constant: Quantity,
    ph: Quantity,
    free_enzyme_lower_pk: Quantity,
    free_enzyme_upper_pk: Quantity,
    complex_lower_pk: Quantity,
    complex_upper_pk: Quantity,
    rate_units: str,
    minimum_ph: Quantity | None = None,
    maximum_ph: Quantity | None = None,
    source: str,
) -> Quantity:
    """Compute ``v = E kcat(pH) S / (Km(pH) + S)`` with validity warnings."""

    if not has_text(source):
        raise ValueError("A source is required for pH-dependent Michaelis-Menten kinetics.")
    ph_value = assert_compatible(require_quantity(ph, name="pH"), "dimensionless", name="pH")
    warn_if_ph_outside_range(ph=ph_value, minimum_ph=minimum_ph, maximum_ph=maximum_ph, source=source)
    kcat = ph_dependent_turnover(
        turnover=turnover,
        ph=ph_value,
        complex_lower_pk=complex_lower_pk,
        complex_upper_pk=complex_upper_pk,
    )
    km = ph_dependent_michaelis_constant(
        michaelis_constant=michaelis_constant,
        ph=ph_value,
        free_enzyme_lower_pk=free_enzyme_lower_pk,
        free_enzyme_upper_pk=free_enzyme_upper_pk,
        complex_lower_pk=complex_lower_pk,
        complex_upper_pk=complex_upper_pk,
    )
    return enzyme_explicit_michaelis_menten_rate(
        substrate=substrate,
        enzyme=enzyme,
        kcat=kcat,
        km=km,
        rate_units=rate_units,
    )


def _dimensionless(quantity: Quantity, name: str) -> np.ndarray:
    value = assert_compatible(require_quantity(quantity, name=name), "dimensionless", name=name)
    return np.asarray(value.magnitude, dtype=float)


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def _ensure_positive(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) <= 0):
        raise ValueError(f"{name} must be positive.")


__all__ = [
    "diprotic_ionization_factor",
    "ph_dependent_michaelis_constant",
    "ph_dependent_turnover",
    "ph_ionization_michaelis_menten_assumption",
    "ph_ionization_michaelis_menten_rate",
]
