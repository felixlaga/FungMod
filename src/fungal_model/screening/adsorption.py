"""Registry assembler for explicit single-site adsorbed-enzyme hydrolysis."""

from __future__ import annotations
from typing import Any

from fungal_model.processes.adsorption import ADSORBED_ENZYME_HYDROLYSIS_PROCESS_TYPE

ADSORPTION_PARAMETER_ROLES = ("binding_capacity", "adsorption_constant", "bound_rate_constant", "substrate_initial_concentration", "enzyme_initial_concentration")
ADSORPTION_DISSOCIATION_PARAMETER_ROLES = ("binding_capacity", "adsorption_dissociation_constant", "bound_rate_constant", "substrate_initial_concentration", "enzyme_initial_concentration")


def adsorption_config_data(**kwargs: Any) -> dict[str, Any]:
    # Reuse the biology-independent enzyme-template record and state plumbing.
    from fungal_model.screening.case_builder import RegistryCaseBuildError, _enzyme_kinetics_config_data
    substrate = kwargs["substrate"]
    if substrate.physical_state != "solid_polymer":
        raise RegistryCaseBuildError("Adsorbed-enzyme hydrolysis requires a solid_polymer substrate.")
    roles = kwargs["compatibility"].parameter_roles
    if ("adsorption_constant" in roles) == ("adsorption_dissociation_constant" in roles):
        raise RegistryCaseBuildError("Adsorption template must bind exactly one of association and dissociation constant.")
    binding_role = "adsorption_constant" if "adsorption_constant" in roles else "adsorption_dissociation_constant"
    data = _enzyme_kinetics_config_data(process_type=ADSORBED_ENZYME_HYDROLYSIS_PROCESS_TYPE, process_parameter_roles={role: role for role in ("binding_capacity", binding_role, "bound_rate_constant")}, state_roles=("substrate", "product", "enzyme"), **kwargs)
    data["processes"][0].update({"substrate_physical_state": "solid_polymer", "amount_basis": "dry_mass"})
    return data


def adsorption_registry_assembler() -> Any:
    from fungal_model.screening.case_builder import RegistryProcessAssembler, RegistryRoleSet
    return RegistryProcessAssembler(
        process_type=ADSORBED_ENZYME_HYDROLYSIS_PROCESS_TYPE, process_label="Adsorbed-enzyme hydrolysis",
        required_parameter_roles=ADSORPTION_PARAMETER_ROLES, required_state_roles=("substrate", "product", "enzyme"),
        deterministic_mode="scientific", additional_supported_modes=("toy",),
        required_process_state_metadata=("config_name", "config_mode", "config_maturity", "process_id", "parameter_set_id", "product_map_name"),
        enforce_template_mode_match=True, unsupported_mode_message="Adsorption supports scientific or toy assembly; estimates run through exploratory sampling.", config_data_builder=adsorption_config_data,
        alternative_role_sets=(RegistryRoleSet(name="dissociation", parameter_roles=ADSORPTION_DISSOCIATION_PARAMETER_ROLES, state_roles=("substrate", "product", "enzyme")),),
    )
