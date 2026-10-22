"""Enzyme-site binding balance for interfacial (solid-substrate) catalysis.

Equations
---------

With total enzyme ``E_T`` (conserved), accessible attack-site concentration
``S_0`` and dissociation constant ``K_d`` (all in one concentration unit), the
bound enzyme ``E_b`` solves the closed balance ``E_T = E_free + E_b``,
``S_0 = S_free + E_b`` with ``K_d = E_free * S_free / E_b``:

``Sigma = E_T + S_0 + K_d``

``Delta = sqrt(Sigma**2 - 4 E_T S_0)``

``E_b = (Sigma - Delta) / 2``

``E_b`` is evaluated as ``2 E_T S_0 / (Sigma + Delta)``, which is the same root
without the cancellation of ``Sigma - Delta`` when ``E_b`` is small. The two
regimes of interfacial kinetics are its limits: ``E_T << S_0`` gives the
conventional Michaelis-Menten form in sites, ``E_b -> E_T S_0 / (K_d + S_0)``;
``S_0 << E_T`` gives the inverse Michaelis-Menten form,
``E_b -> S_0 E_T / (K_d + E_T)`` (Kari et al. 2017, ACS Catal 7:4904; the
substrate-conserving form of Andersen et al. 2018, Math Biosci).

Derivatives of the root:

``dE_b/dE_T = (1 - (Sigma - 2 S_0) / Delta) / 2``

``dE_b/dS_0 = (1 - (Sigma - 2 E_T) / Delta) / 2``

Both are returned as 0 when ``Delta = 0`` (``E_T = S_0`` with ``K_d = 0``), the
one point where the root is not differentiable; see
:func:`site_binding_bound_enzyme_derivatives`.
"""

from __future__ import annotations

import math

from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity

SITE_BINDING_MATURITY = "literature_backed_software_tested"
SITE_BINDING_PRIMARY_SOURCES = (
    "Andersen M, Kari J, Borch K, Westh P (2018). Michaelis-Menten equation for degradation "
    "of insoluble substrate. Math Biosci 296:93-97.",
    "Kari J, Andersen M, Borch K, Westh P (2017). An inverse Michaelis-Menten approach to "
    "interfacial enzyme kinetics. ACS Catal 7:4904-4914.",
)


def _non_negative_float(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return number


def bound_enzyme_magnitude(total_enzyme: float, site_concentration: float, dissociation_constant: float) -> float:
    """Bound enzyme ``E_b`` from magnitudes that share one concentration unit."""

    total = _non_negative_float(total_enzyme, "total_enzyme")
    sites = _non_negative_float(site_concentration, "site_concentration")
    dissociation = _non_negative_float(dissociation_constant, "dissociation_constant")
    sigma = total + sites + dissociation
    # Sigma**2 - 4 E_T S_0 written as a sum of non-negative terms, so rounding never makes it negative.
    discriminant = (total - sites) ** 2 + dissociation * (dissociation + 2.0 * (total + sites))
    delta = math.sqrt(discriminant)
    denominator = sigma + delta
    if denominator == 0.0:
        return 0.0
    return 2.0 * total * sites / denominator


def bound_enzyme_derivative_magnitudes(
    total_enzyme: float,
    site_concentration: float,
    dissociation_constant: float,
) -> tuple[float, float]:
    """``(dE_b/dE_T, dE_b/dS_0)`` as dimensionless magnitudes; both 0 where ``Delta = 0``."""

    total = _non_negative_float(total_enzyme, "total_enzyme")
    sites = _non_negative_float(site_concentration, "site_concentration")
    dissociation = _non_negative_float(dissociation_constant, "dissociation_constant")
    sigma = total + sites + dissociation
    discriminant = (total - sites) ** 2 + dissociation * (dissociation + 2.0 * (total + sites))
    delta = math.sqrt(discriminant)
    if delta == 0.0:
        return 0.0, 0.0
    return (
        0.5 * (1.0 - (sigma - 2.0 * sites) / delta),
        0.5 * (1.0 - (sigma - 2.0 * total) / delta),
    )


def site_binding_bound_enzyme(
    *,
    total_enzyme: Quantity,
    site_concentration: Quantity,
    dissociation_constant: Quantity,
) -> Quantity:
    """Bound enzyme concentration from the closed enzyme-site balance.

    All three inputs are converted to the units of ``total_enzyme``; the result
    carries those units.
    """

    total = require_quantity(total_enzyme, name="total_enzyme")
    units = str(total.units)
    sites = assert_compatible(require_quantity(site_concentration, name="site_concentration"), units, name="site_concentration")
    dissociation = assert_compatible(
        require_quantity(dissociation_constant, name="dissociation_constant"),
        units,
        name="dissociation_constant",
    )
    bound = bound_enzyme_magnitude(float(total.magnitude), float(sites.magnitude), float(dissociation.magnitude))
    return Q_(bound, total.units)


def site_binding_bound_enzyme_derivatives(
    *,
    total_enzyme: Quantity,
    site_concentration: Quantity,
    dissociation_constant: Quantity,
) -> tuple[Quantity, Quantity]:
    """``(dE_b/dE_T, dE_b/dS_0)`` as dimensionless quantities.

    At ``Delta = 0`` (``E_T = S_0`` and ``K_d = 0``) the root is the kink
    ``E_b = min(E_T, S_0)``; both derivatives are returned as 0 there, the
    documented finite choice.
    """

    total = require_quantity(total_enzyme, name="total_enzyme")
    units = str(total.units)
    sites = assert_compatible(require_quantity(site_concentration, name="site_concentration"), units, name="site_concentration")
    dissociation = assert_compatible(
        require_quantity(dissociation_constant, name="dissociation_constant"),
        units,
        name="dissociation_constant",
    )
    by_total, by_sites = bound_enzyme_derivative_magnitudes(
        float(total.magnitude),
        float(sites.magnitude),
        float(dissociation.magnitude),
    )
    return Q_(by_total, "dimensionless"), Q_(by_sites, "dimensionless")


__all__ = [
    "SITE_BINDING_MATURITY",
    "SITE_BINDING_PRIMARY_SOURCES",
    "bound_enzyme_derivative_magnitudes",
    "bound_enzyme_magnitude",
    "site_binding_bound_enzyme",
    "site_binding_bound_enzyme_derivatives",
]
