"""pH activity modifiers for enzyme-mediated rates.

First profile
-------------

Gaussian activity around an optimum pH:

``activity = exp(-0.5 * ((pH - pH_opt) / sigma_pH) ** 2)``

This is an empirical activity modifier, not a mechanistic acid-base model. It
requires a source string and can warn when evaluated outside a measured pH
range.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import cast

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.arrhenius import EnvironmentalValidityWarning

PH_GAUSSIAN_HALF_FACTOR = Parameter(
    name="Gaussian pH activity half factor",
    symbol="half_gaussian",
    value=0.5,
    units="dimensionless",
    uncertainty=None,
    source="Mathematical definition of a Gaussian exponent.",
    confidence_level="high",
    notes="Used in exp(-0.5*x^2) for empirical pH activity.",
    measurement_method="definition",
)

PH_GAUSSIAN_EXPONENT_POWER = Parameter(
    name="Gaussian pH activity exponent power",
    symbol="gaussian_power",
    value=2.0,
    units="dimensionless",
    uncertainty=None,
    source="Mathematical definition of a Gaussian squared deviation.",
    confidence_level="high",
    notes="Used in ((pH - pH_opt)/sigma_pH)^2.",
    measurement_method="definition",
)


def gaussian_ph_activity_assumption() -> Assumption:
    """Return the Stage 5 empirical pH profile assumption."""

    return Assumption(
        name="Gaussian empirical pH activity profile",
        description="Enzyme activity is scaled by a Gaussian curve around an optimum pH.",
        justification="A minimal empirical pH modifier for testing environmental dependence.",
        known_limitations=(
            "Does not model ionization states, multi-peak profiles, irreversible "
            "deactivation, buffer chemistry, or coupling between pH and enzyme adsorption."
        ),
        source="Empirical modelling assumption for pH-dependent activity.",
    )


def _ensure_positive(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) <= 0):
        raise ValueError(f"{name} must be positive.")


def warn_if_ph_outside_range(
    *,
    ph: Quantity,
    minimum_ph: Quantity | None,
    maximum_ph: Quantity | None,
    source: str,
) -> None:
    """Warn if pH is outside a source-supported range."""

    if not has_text(source):
        raise ValueError("A source is required for pH validity ranges.")
    ph_value = assert_compatible(ph, "dimensionless", name="pH")
    values = np.asarray(ph_value.magnitude, dtype=float)
    details: list[str] = []
    if minimum_ph is not None:
        lower = assert_compatible(minimum_ph, "dimensionless", name="minimum_ph")
        if np.any(values < float(lower.magnitude)):
            details.append(f"below pH {float(lower.magnitude)}")
    if maximum_ph is not None:
        upper = assert_compatible(maximum_ph, "dimensionless", name="maximum_ph")
        if np.any(values > float(upper.magnitude)):
            details.append(f"above pH {float(upper.magnitude)}")
    if details:
        warnings.warn(
            "pH is outside the measured/source-supported range "
            f"({', '.join(details)}); source: {source}",
            EnvironmentalValidityWarning,
            stacklevel=2,
        )


def gaussian_ph_activity(
    *,
    ph: Quantity,
    optimum_ph: Quantity,
    width: Quantity,
    minimum_ph: Quantity | None = None,
    maximum_ph: Quantity | None = None,
    source: str,
) -> Quantity:
    """Compute a dimensionless Gaussian pH activity modifier."""

    if not has_text(source):
        raise ValueError("A source is required for pH activity profiles.")
    ph_value = assert_compatible(require_quantity(ph, name="pH"), "dimensionless", name="pH")
    optimum = assert_compatible(
        require_quantity(optimum_ph, name="optimum_ph"),
        "dimensionless",
        name="optimum_ph",
    )
    sigma = assert_compatible(
        require_quantity(width, name="width"),
        "dimensionless",
        name="width",
    )
    _ensure_positive(sigma, "width")
    warn_if_ph_outside_range(
        ph=ph_value,
        minimum_ph=minimum_ph,
        maximum_ph=maximum_ph,
        source=source,
    )
    scaled_deviation = assert_compatible(
        (ph_value - optimum) / sigma,
        "dimensionless",
        name="scaled pH deviation",
    )
    exponent = (
        -cast(Quantity, PH_GAUSSIAN_HALF_FACTOR.quantity).to("dimensionless")
        * scaled_deviation
        ** cast(Quantity, PH_GAUSSIAN_EXPONENT_POWER.quantity).to("dimensionless").magnitude
    )
    return assert_compatible(
        Q_(np.exp(exponent.magnitude), "dimensionless"),
        "dimensionless",
        name="Gaussian pH activity",
    )


@dataclass(frozen=True)
class GaussianPHActivityProfile:
    """Callable Gaussian pH activity profile driven by ``ParameterSet`` symbols."""

    ph_symbol: str
    optimum_symbol: str
    width_symbol: str
    source: str
    minimum_ph_symbol: str | None = None
    maximum_ph_symbol: str | None = None

    def __post_init__(self) -> None:
        if not has_text(self.source):
            raise ValueError("GaussianPHActivityProfile requires a source.")

    @property
    def assumptions(self) -> list[Assumption]:
        return [gaussian_ph_activity_assumption()]

    def activity(self, parameters) -> Quantity:
        minimum_ph = (
            parameters.require_quantity(self.minimum_ph_symbol, "dimensionless")
            if self.minimum_ph_symbol is not None
            else None
        )
        maximum_ph = (
            parameters.require_quantity(self.maximum_ph_symbol, "dimensionless")
            if self.maximum_ph_symbol is not None
            else None
        )
        return gaussian_ph_activity(
            ph=parameters.require_quantity(self.ph_symbol, "dimensionless"),
            optimum_ph=parameters.require_quantity(self.optimum_symbol, "dimensionless"),
            width=parameters.require_quantity(self.width_symbol, "dimensionless"),
            minimum_ph=minimum_ph,
            maximum_ph=maximum_ph,
            source=self.source,
        )

    def scale(self, *, rate: Quantity, parameters) -> Quantity:
        return assert_compatible(
            rate * self.activity(parameters),
            str(rate.units),
            name="pH-scaled rate",
        )


__all__ = [
    "GaussianPHActivityProfile",
    "PH_GAUSSIAN_EXPONENT_POWER",
    "PH_GAUSSIAN_HALF_FACTOR",
    "gaussian_ph_activity",
    "gaussian_ph_activity_assumption",
    "warn_if_ph_outside_range",
]
