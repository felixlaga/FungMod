"""Source-labelled template binding for soluble-resource uptake and dissolved oxygen.

This module composes existing processes; every physical coefficient comes
from the caller's records. The ledger is in substrate equivalents, not a
claim that unmeasured carbon dioxide or secreted protein was quantified.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

UPTAKE_QUANTITIES = ("uptake_capacity", "uptake_half_saturation", "maintenance_demand", "initial_soluble_sugar")
OXYGEN_CULTURE_QUANTITIES = ("oxygen_half_saturation", "oxygen_yield", "oxygen_maintenance")
AERATION_QUANTITIES = ("kla", "oxygen_saturation", "initial_dissolved_oxygen")


def augment_uptake_template(mapping: dict[str, Any], *, sugar_state: str, oxygen: bool = False) -> dict[str, Any]:
    """Bind release, growth and maintenance; all names denote registry roles."""
    result = deepcopy(mapping)
    roles = result["state_roles"]
    roles.pop("ledger_unassimilated_substrate")
    del result["initial_state_mapping"]["ledger_unassimilated_substrate"]
    metadata = result["process_state_metadata"]
    del metadata["state_species"]["ledger_unassimilated_substrate"]
    roles.update(soluble_product=sugar_state, ledger_respired_carbon="maintenance_substrate_equivalents")
    result["initial_state_mapping"].update({
        "soluble_product": {"parameter_role": "initial_soluble_sugar", "units_from_role": "initial_soluble_sugar"},
        "ledger_respired_carbon": {"value": 0.0, "units_from_role": "initial_soluble_sugar"},
    })
    metadata["state_species"].update({
        "soluble_product": {"entity_type": "product", "species": sugar_state},
        "ledger_respired_carbon": {"entity_type": "ledger", "species": "maintenance_substrate_equivalents"},
    })
    release_map = metadata["product_maps"][0]
    release_map["products"] = {"soluble_product": {"parameter_role": "release_yield"}}
    release_map["name"] = "Solid hydrolysis to a stated soluble pool"
    release_map["notes"] = "Unit-bearing, user-stated release yield; no molar mass or hydration correction inferred."
    for process in metadata["process_templates"]:
        if process.get("product_map") == release_map["id"]:
            process["state_roles"]["product"] = "soluble_product"
            process["assumptions"] = [process["assumptions"][0], "Consumed solid releases the soluble pool through its explicit yield; biomass forms only by uptake."]
    shared = {
        "state_roles": {"substrate": "soluble_product", "biomass": "biomass"},
        "parameter_roles": {"true_yield": "biomass_yield", "uptake_capacity": "uptake_capacity", "substrate_half_saturation": "uptake_half_saturation", "maintenance_demand": "maintenance_demand"},
        "fixed_parameters": {"time_units": result["time_grid"]["units"], "separate_state_units": True},
        "assumptions": ["Monod saturation of one soluble pool and a capped Pirt maintenance partition; no catabolite repression, storage or death from unmet maintenance. Nitrogen is assumed nonlimiting."],
    }
    growth = {**deepcopy(shared), "id": "soluble_uptake_growth", "process_type": "resource_limited_growth", "stoichiometry": {"soluble_product": {"inverse_parameter_roles": ["biomass_yield"], "factor": -1.0}, "biomass": 1.0}}
    maintenance = {**deepcopy(shared), "id": "soluble_uptake_maintenance", "process_type": "resource_limited_maintenance", "stoichiometry": {"soluble_product": -1.0, "ledger_respired_carbon": 1.0}}
    metadata["process_templates"].extend([growth, maintenance])
    metadata["conservation"] = {
        "id": "released_resource_closure_ledger", "closed_system": True,
        "state_weights": {
            "substrate": 1.0,
            "soluble_product": {"inverse_parameter_roles": ["release_yield"]},
            "biomass": {"inverse_parameter_roles": ["release_yield", "biomass_yield"]},
            "ledger_biomass_loss": {"inverse_parameter_roles": ["release_yield", "biomass_yield"]},
            "ledger_respired_carbon": {"inverse_parameter_roles": ["release_yield"]},
        },
    }
    result["initial_state_mapping"]["ledger_biomass_loss"] = {"value": 0.0, "units_from_role": "initial_biomass"}
    metadata["mechanism_sources"] = ["monod1949", "pirt1965"]
    result["limitations"] = [
        "Software-tested structure only; no fungal constants or empirical validation supplied by the law sources.",
        "One pooled soluble sugar. Its initial amount is explicitly stated; no carry-over is inferred.",
        "The respired-carbon ledger records maintenance substrate equivalents, not measured carbon dioxide. Biomass yield accounts for growth-associated resource demand.",
        "Nitrogen is assumed nonlimiting. Enzyme synthesis is uncosted and is not repressed by sugar; no preferential uptake, morphology, storage or unmet-maintenance death.",
        "Constants are specific to their stated culture condition. Enzyme pools retain assay or mass units.",
    ]
    if oxygen:
        roles.update(dissolved_oxygen="dissolved_oxygen", ledger_oxygen_transfer="oxygen_transferred", ledger_oxygen_consumption="oxygen_consumed")
        for role in ("dissolved_oxygen", "ledger_oxygen_transfer", "ledger_oxygen_consumption"):
            result["initial_state_mapping"][role] = ({"parameter_role": "initial_dissolved_oxygen", "units_from_role": "initial_dissolved_oxygen"} if role == "dissolved_oxygen" else {"value": 0.0, "units_from_role": "initial_dissolved_oxygen"})
            metadata["state_species"][role] = {"entity_type": "product" if role == "dissolved_oxygen" else "ledger", "species": roles[role]}
        for process, demand in ((growth, "oxygen_yield"), (maintenance, "oxygen_maintenance")):
            process["state_roles"]["oxidant"] = "dissolved_oxygen"
            process["parameter_roles"]["oxidant_half_saturation"] = "oxygen_half_saturation"
            process["stoichiometry"].update({"dissolved_oxygen": {"parameter_role": demand, "factor": -1.0}, "ledger_oxygen_consumption": {"parameter_role": demand}})
        metadata["process_templates"].append({
            "id": "oxygen_gas_transfer", "process_type": "gas_transfer",
            "state_roles": {"pool": "dissolved_oxygen", "ledger": "ledger_oxygen_transfer"},
            "parameter_roles": {"transfer_rate": "kla", "saturation": "oxygen_saturation"},
            "fixed_parameters": {"time_units": result["time_grid"]["units"]},
            "assumptions": ["Well-mixed gas-liquid transfer with explicitly stated saturation and measured kLa; no gas-phase or solubility model."],
        })
        metadata["state_domains"] = {"ledger_oxygen_transfer": "signed"}
        metadata["additional_conservation"] = [{"id": "oxygen_balance_ledger", "closed_system": True, "state_weights": {"dissolved_oxygen": 1.0, "ledger_oxygen_transfer": -1.0, "ledger_oxygen_consumption": 1.0}}]
        metadata["mechanism_sources"].append("garcia_ochoa_gomez2009")
        result["limitations"].append("Dissolved oxygen is dynamic with one transfer coefficient. Saturation is a stated measurement/design value; no temperature-derived solubility or vessel correlation.")
    else:
        result["limitations"].append("Oxygen is assumed nonlimiting because no dissolved-oxygen pool is bound.")
    result["observable_roles"] = [*roles, "degradation_rate"]
    result["output_state_roles"] = dict(roles)
    result["validity_notes"] = ["Uptake and release connect explicitly unit-bearing resource and biomass bases; no biological conversion is silently supplied."]
    return result
