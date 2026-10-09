"""Unit and reporting contracts for opt-in user-data adsorption (BIO-004 M1).

This module owns no records and supplies no values. The existing user-data
loader retains row provenance, namespacing, unknowns and exploratory gates.
"""

from __future__ import annotations

from collections.abc import Mapping

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import ASSAY_BASE_UNITS, Quantity, units_are_compatible
from fungal_model.processes.adsorption import AdsorbedEnzymeHydrolysisProcess

ADSORPTION_QUANTITIES = ("binding_capacity", "adsorption_constant", "adsorption_dissociation_constant", "bound_rate_constant")
ADSORPTION_RATE_FORM = "adsorbed_enzyme"
ADSORPTION_PARAMETER_ROLES = ("binding_capacity", "adsorption_constant", "bound_rate_constant", "substrate_initial_concentration", "enzyme_initial_concentration")
ADSORPTION_DISSOCIATION_PARAMETER_ROLES = ("binding_capacity", "adsorption_dissociation_constant", "bound_rate_constant", "substrate_initial_concentration", "enzyme_initial_concentration")
_ENZYME_AMOUNTS = ("g", "mol", *ASSAY_BASE_UNITS)


def adsorption_units_error(quantity: str, units: str, *, solid: bool) -> str | None:
    """Single-row validation; pair validation below checks the actual enzyme basis."""
    if not solid:
        return f"{quantity} requires a solid_polymer substrate on a dry_mass basis; adsorption on dissolved substrate is refused."
    expected = {
        "binding_capacity": tuple(f"({enzyme})/g" for enzyme in _ENZYME_AMOUNTS),
        "adsorption_constant": tuple(f"L/({enzyme})" for enzyme in _ENZYME_AMOUNTS),
        "adsorption_dissociation_constant": tuple(f"({enzyme})/L" for enzyme in _ENZYME_AMOUNTS),
        "bound_rate_constant": tuple(f"g/({enzyme})/s" for enzyme in _ENZYME_AMOUNTS),
        "enzyme_concentration": tuple(f"({enzyme})/L" for enzyme in _ENZYME_AMOUNTS),
    }
    if quantity not in expected:
        raise ValueError(f"Not an adsorption quantity: {quantity}")
    try:
        if any(units_are_compatible(units, target) for target in expected[quantity]):
            return None
    except Exception:
        pass
    return f"{quantity} units {units!r} must carry the declared enzyme basis and dry-substrate mass basis (expected one of {expected[quantity]})."


def adsorption_case_unit_errors(units_by_quantity: Mapping[str, str]) -> tuple[str, ...]:
    """Fail closed on K/Kd ambiguity and incompatible mass/molar/assay bases.

    Missing capacity/rate/initial rows remain explicit gaps in the caller; K/Kd
    must be chosen explicitly because neither alternative can be guessed.
    """
    problems = []
    if ("adsorption_constant" in units_by_quantity) == ("adsorption_dissociation_constant" in units_by_quantity):
        problems.append("Give exactly one of adsorption_constant and adsorption_dissociation_constant.")
    enzyme = units_by_quantity.get("enzyme_concentration")
    solid = units_by_quantity.get("substrate_initial_concentration")
    if enzyme is None or solid is None:
        return tuple(problems)
    expected = {"binding_capacity": f"({enzyme})/({solid})", "adsorption_constant": f"1/({enzyme})", "adsorption_dissociation_constant": enzyme, "bound_rate_constant": f"({solid})/({enzyme})/s"}
    for quantity, target in expected.items():
        if quantity in units_by_quantity and not units_are_compatible(units_by_quantity[quantity], target):
            problems.append(f"{quantity} units {units_by_quantity[quantity]!r} are incompatible with the case's enzyme basis {enzyme!r} and dry substrate {solid!r}; expected {target}. No assay-to-mass or molar conversion is inferred.")
    return tuple(problems)


def adsorption_result_columns(process: AdsorbedEnzymeHydrolysisProcess, parameters: ParameterSet, states: Mapping[str, Quantity]) -> dict[str, Quantity]:
    """Derived free/bound curves and a pinned conservation residual, without new ODE states."""
    return process.derived_quantities(states, parameters)
