"""Cardinal (Rosso-type) temperature and pH response laws.

Equations
---------

Cardinal temperature model with inflection (CTMI)::

    gamma_T(T) = 0                                      for T <= T_min or T >= T_max
    gamma_T(T) = (T - T_max) (T - T_min)^2
                 / { (T_opt - T_min) [ (T_opt - T_min)(T - T_opt)
                                       - (T_opt - T_max)(T_opt + T_min - 2 T) ] }

Cardinal pH model (CPM)::

    gamma_pH(pH) = 0                                    for pH <= pH_min or pH >= pH_max
    gamma_pH(pH) = (pH - pH_min)(pH - pH_max)
                   / [ (pH - pH_min)(pH - pH_max) - (pH - pH_opt)^2 ]

Both activities are dimensionless, equal to one at the optimum and zero at and
outside the cardinal bounds. A rate following the law is ``mu = mu_opt * gamma``;
when both conditions apply the activities multiply (the gamma concept).

Sources
-------

Rosso L, Lobry JR, Flandrois JP (1993) An unexpected correlation between
cardinal temperatures of microbial growth highlighted by a new model.
J Theor Biol 162:447-463 (CTMI). Rosso L, Lobry JR, Bajard S, Flandrois JP
(1995) Convenient model to describe the combined effects of temperature and pH
on microbial growth. Appl Environ Microbiol 61:610-616 (CPM, gamma concept).

Limitations
-----------

Empirical shapes described by three cardinal values per condition. No
sub-lethal injury, adaptation, thermal history, or temperature-pH interaction
beyond the product of the two activities. The CTMI denominator is non-zero on
the open interval ``(T_min, T_max)`` only when ``T_opt >= (T_min + T_max) / 2``;
parameter sets outside that domain are rejected rather than evaluated.
"""

from __future__ import annotations

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity


def cardinal_temperature_assumption() -> Assumption:
    """Return the Rosso cardinal-temperature response assumption."""

    return Assumption(
        name="Rosso cardinal temperature model with inflection",
        description=(
            "A rate scales with a dimensionless CTMI activity that is one at the optimum "
            "temperature and zero at or beyond the minimum and maximum cardinal temperatures."
        ),
        justification=(
            "Three biologically interpretable cardinal temperatures describe the growth "
            "response of many microorganisms without extra shape parameters."
        ),
        known_limitations=(
            "Empirical shape with no sub-lethal injury, adaptation, thermal history, or "
            "mechanistic protein-stability basis; the cardinal values are organism- and "
            "measurement-specific and the law is undefined when the optimum lies below the "
            "midpoint of the cardinal range."
        ),
        source="Rosso, Lobry, Flandrois (1993) J Theor Biol 162:447-463.",
    )


def cardinal_ph_assumption() -> Assumption:
    """Return the Rosso cardinal-pH response assumption."""

    return Assumption(
        name="Rosso cardinal pH model",
        description=(
            "A rate scales with a dimensionless CPM activity that is one at the optimum pH "
            "and zero at or beyond the minimum and maximum cardinal pH values."
        ),
        justification=(
            "Three cardinal pH values describe the pH response of many microorganisms with "
            "a single symmetric-in-form expression."
        ),
        known_limitations=(
            "Empirical growth-level shape, not an ionization model; no buffer chemistry, "
            "ionic-strength effects, adaptation, or coupling to temperature beyond the "
            "multiplicative gamma concept."
        ),
        source="Rosso, Lobry, Bajard, Flandrois (1995) Appl Environ Microbiol 61:610-616.",
    )


def cardinal_temperature_activity(
    *,
    temperature: Quantity,
    minimum_temperature: Quantity,
    optimum_temperature: Quantity,
    maximum_temperature: Quantity,
    source: str,
) -> Quantity:
    """Compute the dimensionless CTMI activity ``gamma_T``."""

    if not has_text(source):
        raise ValueError("A source is required for cardinal temperature activity.")
    values = _kelvin_values(temperature, "temperature")
    minimum = _kelvin_scalar(minimum_temperature, "minimum_temperature")
    optimum = _kelvin_scalar(optimum_temperature, "optimum_temperature")
    maximum = _kelvin_scalar(maximum_temperature, "maximum_temperature")
    if not minimum < optimum < maximum:
        raise ValueError(
            "Cardinal temperatures must satisfy minimum < optimum < maximum; got "
            f"{minimum} K, {optimum} K, {maximum} K."
        )
    if optimum < 0.5 * (minimum + maximum):
        raise ValueError(
            "CTMI requires optimum_temperature >= (minimum_temperature + maximum_temperature) / 2 "
            "so that the denominator keeps one sign on the cardinal range; got optimum "
            f"{optimum} K against midpoint {0.5 * (minimum + maximum)} K."
        )
    flat = np.atleast_1d(values)
    inside = (flat > minimum) & (flat < maximum)
    activity = np.zeros_like(flat, dtype=float)
    temperature_inside = flat[inside]
    numerator = (temperature_inside - maximum) * (temperature_inside - minimum) ** 2
    bracket = (optimum - minimum) * (temperature_inside - optimum) - (optimum - maximum) * (
        optimum + minimum - 2.0 * temperature_inside
    )
    denominator = (optimum - minimum) * bracket
    activity[inside] = numerator / denominator
    return Q_(_shaped(activity, values), "dimensionless")


def cardinal_ph_activity(
    *,
    ph: Quantity,
    minimum_ph: Quantity,
    optimum_ph: Quantity,
    maximum_ph: Quantity,
    source: str,
) -> Quantity:
    """Compute the dimensionless CPM activity ``gamma_pH``."""

    if not has_text(source):
        raise ValueError("A source is required for cardinal pH activity.")
    values = _dimensionless_values(ph, "pH")
    minimum = _dimensionless_scalar(minimum_ph, "minimum_ph")
    optimum = _dimensionless_scalar(optimum_ph, "optimum_ph")
    maximum = _dimensionless_scalar(maximum_ph, "maximum_ph")
    if not minimum < optimum < maximum:
        raise ValueError(
            "Cardinal pH values must satisfy minimum < optimum < maximum; got "
            f"{minimum}, {optimum}, {maximum}."
        )
    flat = np.atleast_1d(values)
    inside = (flat > minimum) & (flat < maximum)
    activity = np.zeros_like(flat, dtype=float)
    ph_inside = flat[inside]
    numerator = (ph_inside - minimum) * (ph_inside - maximum)
    denominator = numerator - (ph_inside - optimum) ** 2
    activity[inside] = numerator / denominator
    return Q_(_shaped(activity, values), "dimensionless")


def _shaped(activity: np.ndarray, values: np.ndarray) -> np.ndarray | float:
    if values.ndim == 0:
        return float(activity[0])
    return activity.reshape(values.shape)


def _kelvin_values(quantity: Quantity, name: str) -> np.ndarray:
    kelvin = assert_compatible(require_quantity(quantity, name=name), "kelvin", name=name)
    values = np.asarray(kelvin.magnitude, dtype=float)
    if np.any(values <= 0.0):
        raise ValueError(f"{name} must be positive in kelvin.")
    return values


def _kelvin_scalar(quantity: Quantity, name: str) -> float:
    values = _kelvin_values(quantity, name)
    if values.ndim != 0:
        raise ValueError(f"{name} must be a scalar temperature.")
    return float(values)


def _dimensionless_values(quantity: Quantity, name: str) -> np.ndarray:
    value = assert_compatible(require_quantity(quantity, name=name), "dimensionless", name=name)
    return np.asarray(value.magnitude, dtype=float)


def _dimensionless_scalar(quantity: Quantity, name: str) -> float:
    values = _dimensionless_values(quantity, name)
    if values.ndim != 0:
        raise ValueError(f"{name} must be a scalar value.")
    return float(values)


__all__ = [
    "cardinal_ph_activity",
    "cardinal_ph_assumption",
    "cardinal_temperature_activity",
    "cardinal_temperature_assumption",
]
