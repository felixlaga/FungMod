"""Registry-driven assembly of several enzyme classes acting together on shared pools.

An ``enzyme_network`` case template composes existing generic process laws on
shared substrate pools: one process per enzyme class and pool, each consuming
its pool and releasing the next pool of the network through a stoichiometric
product map with an explicit yield. Several processes on one pool add their
rates, because the compiled core sums the stoichiometric columns of every
process; a pool released by one process can be the substrate of another. Every
state, parameter role, coefficient, closure weight and modifier comes from the
template and its resolved parameter records, exactly as for a
``culture_physiology`` template (``build_composed_process_config_data``);
nothing is inferred from an organism, substrate or enzyme name, and no rate law
of its own is introduced.

The template must declare the state roles ``substrate`` (the pool the case
starts from) and ``product`` (the last pool of the network). The composition
adds no interaction between the processes beyond their shared pools and the
modifiers the template binds.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fungal_model.registry.records import (
    CaseTemplateRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
)
from fungal_model.registry.store import FungModRegistry
from fungal_model.screening.culture_physiology import build_composed_process_config_data

ENZYME_NETWORK_PROCESS_TYPE = "enzyme_network"
ENZYME_NETWORK_REQUIRED_STATE_ROLES = ("substrate", "product")
ENZYME_NETWORK_REQUIRED_PROCESS_STATE_METADATA = (
    "config_name",
    "config_mode",
    "config_maturity",
    "parameter_set_id",
)


def build_enzyme_network_config_data(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    substrate: SubstrateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    output_directory: str | None,
) -> dict[str, Any]:
    """Build raw model-config data for one enzyme-network registry case."""

    return build_composed_process_config_data(
        process_type=ENZYME_NETWORK_PROCESS_TYPE,
        non_negative_validator_id="non_negative_network_states",
        fallback_label="enzyme network case",
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        substrate=substrate,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        output_directory=output_directory,
    )


__all__ = [
    "ENZYME_NETWORK_PROCESS_TYPE",
    "ENZYME_NETWORK_REQUIRED_PROCESS_STATE_METADATA",
    "ENZYME_NETWORK_REQUIRED_STATE_ROLES",
    "build_enzyme_network_config_data",
]
