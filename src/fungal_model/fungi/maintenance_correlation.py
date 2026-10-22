"""Maintenance Gibbs energy correlation of Tijhuis, van Loosdrecht and Heijnen (1993).

Tijhuis, van Loosdrecht and Heijnen compiled maintenance data from aerobic and
anaerobic chemostat cultures of heterotrophic and autotrophic microorganisms
and found that the maintenance Gibbs energy requirement per carbon-mole of
biomass follows one Arrhenius-type temperature law independent of the
electron donor and acceptor:

    m_G(T) = m_G,ref exp[-(E_a,m / R) (1/T - 1/T_ref)]

with m_G,ref = 4.5 kJ per C-mol biomass per hour at T_ref = 298.15 K and
E_a,m = 69 kJ/mol. ``substrate_maintenance_from_gibbs`` converts m_G into the
Pirt substrate maintenance coefficient m_S = m_G / |dG_cat| with dG_cat the
catabolic Gibbs energy per substrate formula unit of the caller's balance.

Maturity ``literature_backed_software_tested``: the constants are the
published correlation, the implementation is tested against the published
functional form, and no organism-specific or fungus-specific validation is
claimed. The correlation is a cross-species chemostat compilation; applying it
to one organism is the caller's assumption and must be recorded as such.
Carbon-moles are expressed with the SI ``mole`` because pint has no C-mol
unit; every name states the per-C-mol-biomass basis.

Reference: Tijhuis L, van Loosdrecht MCM, Heijnen JJ (1993) A thermodynamically
based correlation for maintenance Gibbs energy requirements in aerobic and
anaerobic chemostat cultures. Biotechnol Bioeng 42:509-519.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.arrhenius import UNIVERSAL_GAS_CONSTANT

MAINTENANCE_CORRELATION_MATURITY = "literature_backed_software_tested"
MAINTENANCE_GIBBS_UNITS = "kilojoule / mole / hour"
SUBSTRATE_MAINTENANCE_UNITS = "1 / hour"
CATABOLIC_GIBBS_UNITS = "kilojoule / mole"

TIJHUIS_SOURCE = (
    "Tijhuis L, van Loosdrecht MCM, Heijnen JJ (1993) A thermodynamically based correlation for maintenance "
    "Gibbs energy requirements in aerobic and anaerobic chemostat cultures. Biotechnol Bioeng 42:509-519."
)
TIJHUIS_VALIDITY = (
    "Cross-species compilation of chemostat maintenance data (heterotrophic and autotrophic, aerobic and "
    "anaerobic microorganisms); no fungus-specific or organism-specific claim; the caller records the "
    "assumption that the correlation applies to the modelled culture."
)

TIJHUIS_REFERENCE_MAINTENANCE_GIBBS = Parameter(
    name="Tijhuis reference maintenance Gibbs energy per C-mol biomass",
    symbol="m_G_ref",
    value=4.5,
    units=MAINTENANCE_GIBBS_UNITS,
    uncertainty=None,
    source=TIJHUIS_SOURCE,
    confidence_level="high",
    notes="m_G at the reference temperature 298.15 K; kilojoule per carbon-mole of biomass per hour.",
    measurement_method="published correlation constant",
    validity_range=TIJHUIS_VALIDITY,
)
TIJHUIS_MAINTENANCE_ACTIVATION_ENERGY = Parameter(
    name="Tijhuis maintenance activation energy",
    symbol="E_a_m",
    value=69.0,
    units="kilojoule / mole",
    uncertainty=None,
    source=TIJHUIS_SOURCE,
    confidence_level="high",
    notes="Arrhenius activation energy of the maintenance Gibbs energy requirement.",
    measurement_method="published correlation constant",
    validity_range=TIJHUIS_VALIDITY,
)
TIJHUIS_REFERENCE_TEMPERATURE = Parameter(
    name="Tijhuis reference temperature",
    symbol="T_ref_m",
    value=298.15,
    units="kelvin",
    uncertainty=0.0,
    source=TIJHUIS_SOURCE,
    confidence_level="high",
    notes="Reference temperature of the maintenance correlation (25 degC).",
    measurement_method="published correlation constant",
    validity_range=TIJHUIS_VALIDITY,
)


def tijhuis_maintenance_assumption() -> Assumption:
    """The assumption a caller records when applying the correlation to one culture."""

    return Assumption(
        name="Tijhuis maintenance Gibbs energy correlation",
        description=(
            "The maintenance Gibbs energy requirement per C-mol biomass follows "
            "m_G(T) = 4.5 kJ/(Cmol h) exp[-(69 kJ/mol / R)(1/T - 1/298.15 K)], independent of electron donor "
            "and acceptor; the Pirt substrate maintenance coefficient is m_S = m_G / |dG_cat per substrate unit|."
        ),
        justification="Published cross-species regression of chemostat maintenance data.",
        known_limitations=(
            "A compilation across organisms, not a measurement on the modelled culture; the scatter of the "
            "underlying data around the correlation is reported in the source and is not propagated here; "
            "applies to balanced chemostat growth, not to starvation, stationary phase or solid-state "
            "cultivation; no fungus-specific claim."
        ),
        source=TIJHUIS_SOURCE,
    )


def _scalar(value: Quantity, units: str, name: str) -> float:
    array = np.asarray(assert_compatible(require_quantity(value, name=name), units, name=name).magnitude, dtype=float)
    if array.ndim or not np.isfinite(array):
        raise ValueError(f"{name} must be a finite scalar.")
    return float(array)


def _constant(parameter: Parameter, units: str) -> float:
    parameter.validate_provenance()
    parameter.validate_value()
    assert parameter.quantity is not None
    return float(parameter.quantity.to(units).magnitude)


def tijhuis_maintenance_gibbs(temperature: Quantity) -> Quantity:
    """``m_G(T)`` in kilojoule per C-mol biomass per hour for one absolute temperature.

    Refuses non-finite or non-positive absolute temperatures; a temperature
    given in degC is converted by pint. The validity of the compilation at the
    requested temperature is the caller's responsibility (see ``TIJHUIS_VALIDITY``).
    """

    kelvin = _scalar(temperature, "kelvin", "temperature")
    if kelvin <= 0.0:
        raise ValueError("temperature must be a positive absolute temperature.")
    reference = _constant(TIJHUIS_REFERENCE_MAINTENANCE_GIBBS, MAINTENANCE_GIBBS_UNITS)
    activation = _constant(TIJHUIS_MAINTENANCE_ACTIVATION_ENERGY, "joule / mole")
    reference_temperature = _constant(TIJHUIS_REFERENCE_TEMPERATURE, "kelvin")
    gas_constant = _constant(UNIVERSAL_GAS_CONSTANT, "joule / mole / kelvin")
    return Q_(reference * float(np.exp(-(activation / gas_constant) * (1.0 / kelvin - 1.0 / reference_temperature))), MAINTENANCE_GIBBS_UNITS)


def substrate_maintenance_from_gibbs(maintenance_gibbs: Quantity, catabolic_gibbs_per_substrate: Quantity) -> Quantity:
    """``m_S = m_G / |dG_cat|``: substrate formula units per C-mol biomass per hour.

    ``catabolic_gibbs_per_substrate`` is the Gibbs energy of the catabolic
    reaction per substrate formula unit under the caller's conditions; it must
    be negative (exergonic), because an endergonic catabolism cannot supply
    maintenance energy and dividing by its magnitude would hide that.
    """

    gibbs = _scalar(maintenance_gibbs, MAINTENANCE_GIBBS_UNITS, "maintenance_gibbs")
    catabolic = _scalar(catabolic_gibbs_per_substrate, CATABOLIC_GIBBS_UNITS, "catabolic_gibbs_per_substrate")
    if gibbs < 0.0:
        raise ValueError("maintenance_gibbs must be non-negative.")
    if catabolic >= 0.0:
        raise ValueError("catabolic_gibbs_per_substrate must be negative (exergonic catabolism) to supply maintenance energy.")
    return Q_(gibbs / abs(catabolic), SUBSTRATE_MAINTENANCE_UNITS)


def maintenance_correlation_record() -> dict[str, Any]:
    """Provenance record of the correlation for result metadata."""

    return {
        "maturity": MAINTENANCE_CORRELATION_MATURITY,
        "source": TIJHUIS_SOURCE,
        "validity": TIJHUIS_VALIDITY,
        "constants": {
            parameter.symbol: parameter.to_dict()
            for parameter in (TIJHUIS_REFERENCE_MAINTENANCE_GIBBS, TIJHUIS_MAINTENANCE_ACTIVATION_ENERGY,
                              TIJHUIS_REFERENCE_TEMPERATURE, UNIVERSAL_GAS_CONSTANT)
        },
        "assumption": tijhuis_maintenance_assumption().to_dict(),
    }


__all__ = [
    "CATABOLIC_GIBBS_UNITS",
    "MAINTENANCE_CORRELATION_MATURITY",
    "MAINTENANCE_GIBBS_UNITS",
    "SUBSTRATE_MAINTENANCE_UNITS",
    "TIJHUIS_MAINTENANCE_ACTIVATION_ENERGY",
    "TIJHUIS_REFERENCE_MAINTENANCE_GIBBS",
    "TIJHUIS_REFERENCE_TEMPERATURE",
    "TIJHUIS_SOURCE",
    "TIJHUIS_VALIDITY",
    "maintenance_correlation_record",
    "substrate_maintenance_from_gibbs",
    "tijhuis_maintenance_assumption",
    "tijhuis_maintenance_gibbs",
]
