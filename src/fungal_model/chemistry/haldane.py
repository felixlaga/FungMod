"""Haldane relations: thermodynamic constraints that couple kinetic parameters.

A reversible enzyme's kinetic parameters are not independent. For a uni-uni
reversible Michaelis-Menten mechanism

    v = (V_f * S / K_mS - V_r * P / K_mP) / (1 + S / K_mS + P / K_mP)

the four parameters are tied to the reaction equilibrium constant by the Haldane
relation

    K_eq = (V_f * K_mP) / (V_r * K_mS)

and K_eq is fixed by the standard Gibbs energy of the reaction,
`K_eq = exp(-dG0 / (R * T))`.

This matters for FungMod because it *removes a degree of freedom*. Given a
sourced dG0 and three measured parameters, the fourth is determined rather than
fitted. When kinetic data is scarce, a constraint that reduces dimensionality is
worth more than a mechanism that adds one.

SCOPE. Thermodynamics fixes direction, equilibrium, and the coupling between
parameters. It does not supply an absolute rate: the rate depends on the
activation barrier of a particular protein, which is not derivable from the
reaction's Gibbs energy. Two enzymes catalysing the same reaction share dG0 and
K_eq exactly while differing in V_max by orders of magnitude. Nothing in this
module predicts a turnover number.

This module is deliberately restricted to the uni-uni case, where K_eq is
dimensionless. Multi-substrate reactions such as
`cellobiose + H2O -> 2 glucose` have a concentration-dimensioned K_eq and a
different Haldane form; they are rejected rather than approximated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.core.validators import ValidationResult

#: Molar gas constant, joule / kelvin / mole.
MOLAR_GAS_CONSTANT = Q_(1.0, "molar_gas_constant").to("joule / kelvin / mole")

#: Default relative tolerance when checking a supplied parameter set against K_eq.
DEFAULT_HALDANE_RELATIVE_TOLERANCE = 0.05


class HaldaneError(ValueError):
    """Raised when a Haldane constraint cannot be applied or is violated."""


def equilibrium_constant_from_gibbs(
    *,
    standard_delta_gibbs: Quantity,
    temperature: Quantity,
) -> float:
    """Return the dimensionless equilibrium constant `exp(-dG0 / (R * T))`.

    Both inputs must be explicit quantities. The Gibbs energy is per mole of
    reaction as written, and the temperature must be absolute.
    """

    delta_gibbs = assert_compatible(standard_delta_gibbs, "joule / mole", name="standard_delta_gibbs")
    absolute_temperature = assert_compatible(temperature, "kelvin", name="temperature")
    kelvin = float(absolute_temperature.to("kelvin").magnitude)
    if kelvin <= 0.0:
        raise HaldaneError("Temperature must be positive and absolute.")
    exponent = -float(delta_gibbs.to("joule / mole").magnitude) / (
        float(MOLAR_GAS_CONSTANT.magnitude) * kelvin
    )
    return math.exp(exponent)


def haldane_equilibrium_constant(
    *,
    forward_vmax: Quantity,
    reverse_vmax: Quantity,
    substrate_km: Quantity,
    product_km: Quantity,
) -> float:
    """Return `K_eq = (V_f * K_mP) / (V_r * K_mS)` for a uni-uni mechanism.

    The two maximal rates must share units, and the two Michaelis constants must
    share units, so that the result is dimensionless.
    """

    forward = _positive(forward_vmax, "forward_vmax")
    reverse = _positive(reverse_vmax, "reverse_vmax")
    substrate = _positive(substrate_km, "substrate_km")
    product = _positive(product_km, "product_km")
    ratio = (forward * product) / (reverse * substrate)
    dimensionless = ratio.to("dimensionless")
    return float(dimensionless.magnitude)


def reverse_vmax_from_haldane(
    *,
    equilibrium_constant: float,
    forward_vmax: Quantity,
    substrate_km: Quantity,
    product_km: Quantity,
) -> Quantity:
    """Return the reverse maximal rate implied by the Haldane relation.

    This is the degree of freedom the constraint removes: with a sourced dG0 and
    three measured parameters, the reverse maximal rate is determined and must
    not also be fitted.
    """

    if not math.isfinite(equilibrium_constant) or equilibrium_constant <= 0.0:
        raise HaldaneError("The equilibrium constant must be finite and positive.")
    forward = _positive(forward_vmax, "forward_vmax")
    substrate = _positive(substrate_km, "substrate_km")
    product = _positive(product_km, "product_km")
    return (forward * product) / (substrate * equilibrium_constant)


def check_haldane_consistency(
    *,
    forward_vmax: Quantity,
    reverse_vmax: Quantity,
    substrate_km: Quantity,
    product_km: Quantity,
    standard_delta_gibbs: Quantity,
    temperature: Quantity,
    relative_tolerance: float = DEFAULT_HALDANE_RELATIVE_TOLERANCE,
) -> ValidationResult:
    """Check a measured parameter set against the equilibrium constant.

    A parameter set that violates the Haldane relation is thermodynamically
    inconsistent: no enzyme can have those four values at that temperature. This
    detects transcription errors and parameter sets assembled from mismatched
    sources.
    """

    if relative_tolerance <= 0.0:
        raise HaldaneError("relative_tolerance must be positive.")
    thermodynamic = equilibrium_constant_from_gibbs(
        standard_delta_gibbs=standard_delta_gibbs,
        temperature=temperature,
    )
    kinetic = haldane_equilibrium_constant(
        forward_vmax=forward_vmax,
        reverse_vmax=reverse_vmax,
        substrate_km=substrate_km,
        product_km=product_km,
    )
    relative_error = abs(kinetic - thermodynamic) / thermodynamic
    passed = relative_error <= relative_tolerance
    return ValidationResult(
        name="haldane_consistency",
        passed=passed,
        message=(
            "Kinetic parameters are consistent with the equilibrium constant."
            if passed
            else (
                "Kinetic parameters are thermodynamically inconsistent: the Haldane "
                "ratio disagrees with the equilibrium constant implied by the "
                "standard Gibbs energy."
            )
        ),
        details={
            "equilibrium_constant_from_gibbs": thermodynamic,
            "equilibrium_constant_from_kinetics": kinetic,
            "relative_error": relative_error,
            "relative_tolerance": relative_tolerance,
            "scope": "uni-uni reversible Michaelis-Menten only",
        },
    )


def _positive(value: Any, name: str) -> Quantity:
    if not hasattr(value, "magnitude"):
        raise HaldaneError(f"{name} must be an explicit quantity with units.")
    magnitude = float(value.magnitude)
    if not math.isfinite(magnitude) or magnitude <= 0.0:
        raise HaldaneError(f"{name} must be finite and positive.")
    return value


__all__ = [
    "DEFAULT_HALDANE_RELATIVE_TOLERANCE",
    "HaldaneError",
    "MOLAR_GAS_CONSTANT",
    "check_haldane_consistency",
    "equilibrium_constant_from_gibbs",
    "haldane_equilibrium_constant",
    "reverse_vmax_from_haldane",
]
