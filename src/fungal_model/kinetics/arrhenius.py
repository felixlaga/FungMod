"""Arrhenius temperature scaling.

Equations
---------

Absolute prefactor form:

``k(T) = A * exp(-Ea / (R*T))``

Reference-rate form:

``k(T) = k_ref * exp((-Ea/R) * (1/T - 1/T_ref))``

The reference-rate form is algebraically equivalent when ``k_ref`` is known at
``T_ref``. It is often more convenient when a kinetic parameter has been
measured at a specific temperature.

Limitations
-----------

This module models monotonic Arrhenius acceleration only. It does not include
enzyme thermal deactivation, protein unfolding, PET glass-transition effects,
or extrapolation safety beyond warning the caller when the supplied temperature
falls outside a measured range.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity


class EnvironmentalValidityWarning(UserWarning):
    """Warns when an environmental modifier is evaluated outside its source range."""


UNIVERSAL_GAS_CONSTANT = Parameter(
    name="universal gas constant",
    symbol="R",
    value=8.31446261815324,
    units="joule / mole / kelvin",
    uncertainty=0.0,
    source="2019 SI exact constants via CODATA relationship R = N_A * k_B.",
    confidence_level="high",
    notes="Used in Arrhenius temperature scaling.",
    measurement_method="defined physical constant",
)


def arrhenius_temperature_assumption() -> Assumption:
    """Return the Stage 5 Arrhenius temperature-scaling assumption."""

    return Assumption(
        name="Arrhenius temperature scaling without deactivation",
        description="Rate constants scale with temperature according to an Arrhenius exponential factor.",
        justification="A minimal physically grounded temperature dependence for kinetic constants.",
        known_limitations=(
            "Does not include enzyme thermal deactivation, protein unfolding, "
            "PET morphology transitions, water-activity coupling, or validated "
            "extrapolation outside the measured temperature range."
        ),
        source="Canonical Arrhenius kinetic temperature dependence.",
    )


def _ensure_positive(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) <= 0):
        raise ValueError(f"{name} must be positive.")


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def warn_if_temperature_outside_range(
    *,
    temperature: Quantity,
    minimum_temperature: Quantity | None,
    maximum_temperature: Quantity | None,
    source: str,
) -> None:
    """Warn if ``temperature`` is outside a source-supported range."""

    if not has_text(source):
        raise ValueError("A source is required for temperature validity ranges.")
    temperature_k = assert_compatible(temperature, "kelvin", name="temperature")
    values = np.asarray(temperature_k.magnitude, dtype=float)
    details: list[str] = []
    if minimum_temperature is not None:
        lower = assert_compatible(
            minimum_temperature,
            "kelvin",
            name="minimum_temperature",
        )
        if np.any(values < float(lower.magnitude)):
            details.append(f"below {float(lower.magnitude)} K")
    if maximum_temperature is not None:
        upper = assert_compatible(
            maximum_temperature,
            "kelvin",
            name="maximum_temperature",
        )
        if np.any(values > float(upper.magnitude)):
            details.append(f"above {float(upper.magnitude)} K")
    if details:
        warnings.warn(
            "Temperature is outside the measured/source-supported range "
            f"({', '.join(details)}); source: {source}",
            EnvironmentalValidityWarning,
            stacklevel=2,
        )


def arrhenius_rate_constant(
    *,
    pre_exponential_factor: Quantity,
    activation_energy: Quantity,
    temperature: Quantity,
    gas_constant: Quantity | None = None,
    minimum_temperature: Quantity | None = None,
    maximum_temperature: Quantity | None = None,
    source: str,
    output_units: str | None = None,
) -> Quantity:
    """Compute ``k(T) = A * exp(-Ea/(R*T))`` with dimensional checks."""

    if not has_text(source):
        raise ValueError("A source is required for Arrhenius temperature scaling.")
    factor = require_quantity(pre_exponential_factor, name="pre_exponential_factor")
    energy = assert_compatible(activation_energy, "joule / mole", name="activation_energy")
    temp = assert_compatible(temperature, "kelvin", name="temperature")
    gas = assert_compatible(
        gas_constant or UNIVERSAL_GAS_CONSTANT.quantity,
        "joule / mole / kelvin",
        name="gas_constant",
    )
    _ensure_non_negative(energy, "activation_energy")
    _ensure_positive(temp, "temperature")
    warn_if_temperature_outside_range(
        temperature=temp,
        minimum_temperature=minimum_temperature,
        maximum_temperature=maximum_temperature,
        source=source,
    )
    exponent = assert_compatible(
        -energy / (gas * temp),
        "dimensionless",
        name="Arrhenius exponent",
    )
    rate_constant = factor * np.exp(exponent.magnitude)
    if output_units is not None:
        return assert_compatible(rate_constant, output_units, name="Arrhenius rate constant")
    return rate_constant


def arrhenius_reference_scaled_rate(
    *,
    reference_rate: Quantity,
    activation_energy: Quantity,
    temperature: Quantity,
    reference_temperature: Quantity,
    gas_constant: Quantity | None = None,
    minimum_temperature: Quantity | None = None,
    maximum_temperature: Quantity | None = None,
    source: str,
    output_units: str | None = None,
) -> Quantity:
    """Scale a known reference rate to another temperature."""

    if not has_text(source):
        raise ValueError("A source is required for Arrhenius temperature scaling.")
    k_ref = require_quantity(reference_rate, name="reference_rate")
    energy = assert_compatible(activation_energy, "joule / mole", name="activation_energy")
    temp = assert_compatible(temperature, "kelvin", name="temperature")
    temp_ref = assert_compatible(
        reference_temperature,
        "kelvin",
        name="reference_temperature",
    )
    gas = assert_compatible(
        gas_constant or UNIVERSAL_GAS_CONSTANT.quantity,
        "joule / mole / kelvin",
        name="gas_constant",
    )
    _ensure_non_negative(energy, "activation_energy")
    _ensure_positive(temp, "temperature")
    _ensure_positive(temp_ref, "reference_temperature")
    warn_if_temperature_outside_range(
        temperature=temp,
        minimum_temperature=minimum_temperature,
        maximum_temperature=maximum_temperature,
        source=source,
    )
    exponent = assert_compatible(
        (-energy / gas) * ((Q_(1.0, "dimensionless") / temp) - (Q_(1.0, "dimensionless") / temp_ref)),
        "dimensionless",
        name="Arrhenius reference exponent",
    )
    scaled_rate = k_ref * np.exp(exponent.magnitude)
    if output_units is not None:
        return assert_compatible(scaled_rate, output_units, name="Arrhenius-scaled rate")
    return scaled_rate


@dataclass(frozen=True)
class ArrheniusReferenceTemperatureScaler:
    """Callable reference-temperature Arrhenius scaler."""

    activation_energy_symbol: str
    reference_temperature_symbol: str
    temperature_symbol: str
    source: str
    minimum_temperature_symbol: str | None = None
    maximum_temperature_symbol: str | None = None

    def __post_init__(self) -> None:
        if not has_text(self.source):
            raise ValueError("ArrheniusReferenceTemperatureScaler requires a source.")

    @property
    def assumptions(self) -> list[Assumption]:
        return [arrhenius_temperature_assumption()]

    def scale(self, *, reference_rate: Quantity, parameters) -> Quantity:
        minimum_temperature = (
            parameters.require_quantity(self.minimum_temperature_symbol, "kelvin")
            if self.minimum_temperature_symbol is not None
            else None
        )
        maximum_temperature = (
            parameters.require_quantity(self.maximum_temperature_symbol, "kelvin")
            if self.maximum_temperature_symbol is not None
            else None
        )
        return arrhenius_reference_scaled_rate(
            reference_rate=reference_rate,
            activation_energy=parameters.require_quantity(self.activation_energy_symbol, "joule / mole"),
            temperature=parameters.require_quantity(self.temperature_symbol, "kelvin"),
            reference_temperature=parameters.require_quantity(self.reference_temperature_symbol, "kelvin"),
            minimum_temperature=minimum_temperature,
            maximum_temperature=maximum_temperature,
            source=self.source,
            output_units=str(reference_rate.units),
        )


__all__ = [
    "ArrheniusReferenceTemperatureScaler",
    "EnvironmentalValidityWarning",
    "UNIVERSAL_GAS_CONSTANT",
    "arrhenius_rate_constant",
    "arrhenius_reference_scaled_rate",
    "arrhenius_temperature_assumption",
    "warn_if_temperature_outside_range",
]
