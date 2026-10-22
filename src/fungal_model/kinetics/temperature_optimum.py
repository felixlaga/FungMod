"""Enzyme temperature laws with an optimum: Sharpe-Schoolfield and the Equilibrium Model.

Both laws multiply a reference-rate Arrhenius activation by a reversible
inactivation term, and both are normalised to one at the reference temperature
so that a rate constant measured at ``T_ref`` keeps its measured meaning.

Equations
---------

Sharpe-Schoolfield, high-temperature form (Schoolfield, Sharpe, Magnuson
1981), normalised at ``T_ref``::

    a(T) = exp[-(E_a/R)(1/T - 1/T_ref)]
           * [1 + exp((dH_H/R)(1/T_H - 1/T_ref))]
           / [1 + exp((dH_H/R)(1/T_H - 1/T))]

With the optional low-temperature term the inactivation sum of the 1981 paper
is used, with the low exponent sign reversed so that both enthalpies are
entered as positive magnitudes::

    D(T) = 1 + exp((dH_L/R)(1/T - 1/T_L)) + exp((dH_H/R)(1/T_H - 1/T))
    a(T) = exp[-(E_a/R)(1/T - 1/T_ref)] * D(T_ref) / D(T)

``T_H`` (``T_L``) is the temperature at which the high (low) inactivation term
alone halves the activity. The ``T/T_ref`` pre-factor of the original 1981
expression is not carried separately; it is absorbed into the Arrhenius
activation as in current parameterisations of this law.

Equilibrium Model (Peterson, Daniel, Danson, Eisenthal 2007)::

    f(T) = 1 / (1 + K_eq(T)),   K_eq(T) = exp((dH_eq/R)(1/T_eq - 1/T))

``f`` is the active fraction of a rapidly reversible active/inactive
equilibrium; ``f(T_eq) = 0.5``. The reference-scaled activity is::

    a(T) = exp[-(E_a/R)(1/T - 1/T_ref)] * f(T) / f(T_ref)

Algebraically ``a(T)`` of the Equilibrium Model equals the high-temperature
Sharpe-Schoolfield form with ``dH_H = dH_eq`` and ``T_H = T_eq``. The two laws
are kept as separate modifier types because their parameters have different
published meanings and sources.

``R`` is ``UNIVERSAL_GAS_CONSTANT``. No parameter value is shipped with this
module; every value must come from a sourced record.

Sources
-------

Schoolfield RM, Sharpe PJH, Magnuson CE (1981) Non-linear regression of
biological temperature-dependent rate models based on absolute reaction-rate
theory. J Theor Biol 88:719-731. DOI 10.1016/0022-5193(81)90246-0.

Peterson ME, Daniel RM, Danson MJ, Eisenthal R (2007) The dependence of enzyme
activity on temperature: determination and validation of parameters.
Biochem J 402:331-337. Reviewed in Daniel RM, Danson MJ, Eisenthal R, Lee CK,
Peterson ME (2007) Extremophiles 12:51-59, DOI 10.1007/s00792-007-0089-7, and
Biochem Soc Trans 35:1543-1546, DOI 10.1042/BST0351543.

Limitations
-----------

Both laws describe time-zero activity. Neither includes irreversible thermal
inactivation (that is the separate ``thermal_inactivation`` process), protein
unfolding kinetics, substrate or pH coupling, or validated extrapolation
beyond the measured range: a declared measured range only produces an
``EnvironmentalValidityWarning``.
"""

from __future__ import annotations

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.arrhenius import (
    UNIVERSAL_GAS_CONSTANT,
    warn_if_temperature_outside_range,
)

TEMPERATURE_OPTIMUM_LAW_MATURITY = "literature_backed_software_tested"

SHARPE_SCHOOLFIELD_LAW_SOURCE = (
    "Schoolfield RM, Sharpe PJH, Magnuson CE (1981) J Theor Biol 88:719-731; "
    "DOI 10.1016/0022-5193(81)90246-0."
)
EQUILIBRIUM_MODEL_LAW_SOURCE = (
    "Peterson ME, Daniel RM, Danson MJ, Eisenthal R (2007) Biochem J 402:331-337; "
    "reviewed in Daniel RM et al. (2007) Extremophiles 12:51-59, "
    "DOI 10.1007/s00792-007-0089-7."
)


def sharpe_schoolfield_assumption() -> Assumption:
    """Return the Sharpe-Schoolfield reversible-inactivation assumption."""

    return Assumption(
        name="Sharpe-Schoolfield temperature response with reversible inactivation",
        description=(
            "A rate scales with Arrhenius activation divided by a reversible high-temperature "
            "(optionally also low-temperature) inactivation term, normalised to one at the "
            "reference temperature, which produces a temperature optimum."
        ),
        justification=(
            "Schoolfield, Sharpe and Magnuson (1981) derived the form from absolute reaction-rate "
            "theory with a rate-controlling enzyme in reversible equilibrium with inactive "
            "states; it is the standard optimum-type enzyme temperature law."
        ),
        known_limitations=(
            "Time-zero activity only: no irreversible denaturation, unfolding kinetics, thermal "
            "history, or coupling to pH or substrate; the T/T_ref pre-factor of the 1981 "
            "expression is absorbed into the Arrhenius term; parameters are enzyme- and "
            "preparation-specific and must come from sourced records."
        ),
        source=SHARPE_SCHOOLFIELD_LAW_SOURCE,
    )


def equilibrium_model_assumption() -> Assumption:
    """Return the Equilibrium Model active-fraction assumption."""

    return Assumption(
        name="Equilibrium Model reversible active-inactive enzyme transition",
        description=(
            "The active fraction of an enzyme follows a rapidly reversible active/inactive "
            "equilibrium with midpoint T_eq and enthalpy dH_eq; the fraction multiplies the "
            "Arrhenius activation and is normalised to one at the reference temperature."
        ),
        justification=(
            "Peterson, Daniel, Danson and Eisenthal (2007) showed that a reversible inactive "
            "form, distinct from irreversible denaturation, explains the time-zero temperature "
            "optimum of enzyme activity."
        ),
        known_limitations=(
            "Time-zero activity only: irreversible inactivation is a separate process; no "
            "unfolding kinetics, substrate or pH coupling; T_eq and dH_eq are enzyme-specific "
            "fitted parameters and must come from sourced records; algebraically identical to "
            "the high-temperature Sharpe-Schoolfield form."
        ),
        source=EQUILIBRIUM_MODEL_LAW_SOURCE,
    )


def sharpe_schoolfield_activity(
    *,
    temperature: Quantity,
    activation_energy: Quantity,
    reference_temperature: Quantity,
    high_inactivation_enthalpy: Quantity,
    high_half_inactivation_temperature: Quantity,
    low_inactivation_enthalpy: Quantity | None = None,
    low_half_inactivation_temperature: Quantity | None = None,
    gas_constant: Quantity | None = None,
    minimum_temperature: Quantity | None = None,
    maximum_temperature: Quantity | None = None,
    source: str,
) -> Quantity:
    """Dimensionless Sharpe-Schoolfield activity normalised to one at ``T_ref``."""

    if not has_text(source):
        raise ValueError("A source is required for Sharpe-Schoolfield temperature scaling.")
    if (low_inactivation_enthalpy is None) != (low_half_inactivation_temperature is None):
        raise ValueError(
            "Sharpe-Schoolfield low-temperature term requires both low_inactivation_enthalpy "
            "and low_half_inactivation_temperature, or neither."
        )
    gas = _gas_constant(gas_constant)
    inverse_temperature = 1.0 / _kelvin_values(temperature, "temperature")
    inverse_reference = 1.0 / _kelvin_scalar(reference_temperature, "reference_temperature")
    energy_over_r = _nonnegative_energy(activation_energy, "activation_energy") / gas
    high_over_r = _positive_energy(high_inactivation_enthalpy, "high_inactivation_enthalpy") / gas
    inverse_high = 1.0 / _kelvin_scalar(
        high_half_inactivation_temperature, "high_half_inactivation_temperature"
    )
    low_over_r: float | None = None
    inverse_low: float | None = None
    if low_inactivation_enthalpy is not None and low_half_inactivation_temperature is not None:
        low_over_r = _positive_energy(low_inactivation_enthalpy, "low_inactivation_enthalpy") / gas
        inverse_low = 1.0 / _kelvin_scalar(
            low_half_inactivation_temperature, "low_half_inactivation_temperature"
        )
    _warn_bounds(temperature, minimum_temperature, maximum_temperature, source)

    def log_inactivation_sum(inverse: np.ndarray | float) -> np.ndarray | float:
        total = np.logaddexp(0.0, high_over_r * (inverse_high - inverse))
        if low_over_r is not None and inverse_low is not None:
            total = np.logaddexp(total, low_over_r * (inverse - inverse_low))
        return total

    log_activity = (
        -energy_over_r * (inverse_temperature - inverse_reference)
        + log_inactivation_sum(inverse_reference)
        - log_inactivation_sum(inverse_temperature)
    )
    return Q_(_shaped(np.exp(log_activity), inverse_temperature), "dimensionless")


def equilibrium_model_active_fraction(
    *,
    temperature: Quantity,
    equilibrium_enthalpy: Quantity,
    equilibrium_temperature: Quantity,
    gas_constant: Quantity | None = None,
    source: str,
) -> Quantity:
    """Active fraction ``f(T) = 1 / (1 + exp((dH_eq/R)(1/T_eq - 1/T)))``."""

    if not has_text(source):
        raise ValueError("A source is required for the Equilibrium Model active fraction.")
    gas = _gas_constant(gas_constant)
    inverse_temperature = 1.0 / _kelvin_values(temperature, "temperature")
    inverse_equilibrium = 1.0 / _kelvin_scalar(equilibrium_temperature, "equilibrium_temperature")
    enthalpy_over_r = _positive_energy(equilibrium_enthalpy, "equilibrium_enthalpy") / gas
    log_fraction = -np.logaddexp(0.0, enthalpy_over_r * (inverse_equilibrium - inverse_temperature))
    return Q_(_shaped(np.exp(log_fraction), inverse_temperature), "dimensionless")


def equilibrium_model_activity(
    *,
    temperature: Quantity,
    activation_energy: Quantity,
    reference_temperature: Quantity,
    equilibrium_enthalpy: Quantity,
    equilibrium_temperature: Quantity,
    gas_constant: Quantity | None = None,
    minimum_temperature: Quantity | None = None,
    maximum_temperature: Quantity | None = None,
    source: str,
) -> Quantity:
    """Arrhenius activation times the active fraction, normalised to one at ``T_ref``."""

    if not has_text(source):
        raise ValueError("A source is required for Equilibrium Model temperature scaling.")
    gas = _gas_constant(gas_constant)
    inverse_temperature = 1.0 / _kelvin_values(temperature, "temperature")
    inverse_reference = 1.0 / _kelvin_scalar(reference_temperature, "reference_temperature")
    energy_over_r = _nonnegative_energy(activation_energy, "activation_energy") / gas
    inverse_equilibrium = 1.0 / _kelvin_scalar(equilibrium_temperature, "equilibrium_temperature")
    enthalpy_over_r = _positive_energy(equilibrium_enthalpy, "equilibrium_enthalpy") / gas
    _warn_bounds(temperature, minimum_temperature, maximum_temperature, source)
    log_activity = (
        -energy_over_r * (inverse_temperature - inverse_reference)
        + np.logaddexp(0.0, enthalpy_over_r * (inverse_equilibrium - inverse_reference))
        - np.logaddexp(0.0, enthalpy_over_r * (inverse_equilibrium - inverse_temperature))
    )
    return Q_(_shaped(np.exp(log_activity), inverse_temperature), "dimensionless")


def _warn_bounds(
    temperature: Quantity,
    minimum_temperature: Quantity | None,
    maximum_temperature: Quantity | None,
    source: str,
) -> None:
    if minimum_temperature is None and maximum_temperature is None:
        return
    warn_if_temperature_outside_range(
        temperature=assert_compatible(temperature, "kelvin", name="temperature"),
        minimum_temperature=minimum_temperature,
        maximum_temperature=maximum_temperature,
        source=source,
    )


def _gas_constant(gas_constant: Quantity | None) -> float:
    gas = assert_compatible(
        gas_constant if gas_constant is not None else UNIVERSAL_GAS_CONSTANT.quantity,
        "joule / mole / kelvin",
        name="gas_constant",
    )
    value = float(gas.magnitude)
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("gas_constant must be finite and positive.")
    return value


def _shaped(activity: np.ndarray, values: np.ndarray) -> np.ndarray | float:
    if np.ndim(values) == 0:
        return float(activity)
    return np.asarray(activity, dtype=float).reshape(np.shape(values))


def _kelvin_values(quantity: Quantity, name: str) -> np.ndarray:
    kelvin = assert_compatible(require_quantity(quantity, name=name), "kelvin", name=name)
    values = np.asarray(kelvin.magnitude, dtype=float)
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        raise ValueError(f"{name} must be finite and positive in kelvin.")
    return values


def _kelvin_scalar(quantity: Quantity, name: str) -> float:
    values = _kelvin_values(quantity, name)
    if values.ndim != 0:
        raise ValueError(f"{name} must be a scalar temperature.")
    return float(values)


def _energy_scalar(quantity: Quantity, name: str) -> float:
    energy = assert_compatible(require_quantity(quantity, name=name), "joule / mole", name=name)
    values = np.asarray(energy.magnitude, dtype=float)
    if values.ndim != 0:
        raise ValueError(f"{name} must be a scalar molar energy.")
    value = float(values)
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return value


def _nonnegative_energy(quantity: Quantity, name: str) -> float:
    value = _energy_scalar(quantity, name)
    if value < 0.0:
        raise ValueError(f"{name} must be non-negative.")
    return value


def _positive_energy(quantity: Quantity, name: str) -> float:
    value = _energy_scalar(quantity, name)
    if value <= 0.0:
        raise ValueError(
            f"{name} must be positive; the published laws define the inactivation and "
            "equilibrium enthalpies as positive magnitudes."
        )
    return value


__all__ = [
    "EQUILIBRIUM_MODEL_LAW_SOURCE",
    "SHARPE_SCHOOLFIELD_LAW_SOURCE",
    "TEMPERATURE_OPTIMUM_LAW_MATURITY",
    "equilibrium_model_active_fraction",
    "equilibrium_model_activity",
    "equilibrium_model_assumption",
    "sharpe_schoolfield_activity",
    "sharpe_schoolfield_assumption",
]
