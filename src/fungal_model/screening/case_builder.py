"""Build runnable deterministic model configs from modelable registry cases."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from fungal_model.io.model_config import ModelConfig
from fungal_model.registry.records import (
    CaseTemplateRecord,
    EnvironmentRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
)
from fungal_model.registry.store import FungModRegistry, RegistryLookupError
from fungal_model.screening.modelability import ModelabilityReport, assess_modelability

RegistryCaseConfigMode = Literal["toy", "scientific"]

SURFACE_CATALYSIS_PARAMETER_ROLES = (
    "surface_rate_constant",
    "adsorption_constant",
    "accessible_surface_area",
)
HOMOGENEOUS_MM_PARAMETER_ROLES = (
    "km",
    "kcat",
    "substrate_initial_concentration",
    "enzyme_initial_concentration",
)
EXTRACELLULAR_ENZYME_CHAIN_PARAMETER_ROLES = (
    "solid_substrate_initial_concentration",
    "cellulase_initial_concentration",
    "beta_glucosidase_initial_concentration",
    "surface_rate_constant",
    "adsorption_constant",
    "accessible_surface_area",
    "km",
    "kcat",
)
ENVIRONMENT_MODIFIER_TYPES = frozenset(
    {
        "temperature_arrhenius_reference",
        "ph_gaussian",
        "oxygen_monod",
        "water_activity_threshold",
    }
)


class RegistryCaseBuildError(ValueError):
    """Raised when a registry case cannot be converted into a model config."""


@dataclass(frozen=True)
class RegistryProcessAssembler:
    """Config assembly metadata for one registry process type."""

    process_type: str
    process_label: str
    required_parameter_roles: tuple[str, ...]
    required_state_roles: tuple[str, ...]
    deterministic_mode: RegistryCaseConfigMode
    unsupported_mode_message: str
    config_data_builder: Callable[..., dict[str, Any]]


def build_model_config_from_registry_case(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    mode: RegistryCaseConfigMode = "toy",
    output_directory: str | None = None,
) -> ModelConfig:
    """Convert a modelable registry case into a generic deterministic ``ModelConfig``."""

    _validate_mode(mode)
    report = assess_modelability(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        registry=registry,
        mode=mode,
    )
    if report.status != "modelable":
        raise RegistryCaseBuildError(
            "Registry case cannot be built because modelability status is "
            f"{report.status!r}; deterministic assembly requires exact modelable cases. "
            f"Report: {report.to_dict()}"
        )

    compatibility = select_registry_case_compatibility(
        registry=registry,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        report=report,
    )
    assembler = get_registry_process_assembler(compatibility.process_type)
    if assembler is None:
        raise RegistryCaseBuildError(
            "Registry case builder does not support process_type "
            f"{compatibility.process_type!r}."
        )
    if mode != assembler.deterministic_mode:
        raise RegistryCaseBuildError(assembler.unsupported_mode_message)
    parameter_records = _exact_role_parameters(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        required_roles=assembler.required_parameter_roles,
        process_label=assembler.process_label,
    )
    config_data = build_registry_process_config_data(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        output_directory=output_directory,
    )
    return ModelConfig.from_mapping(config_data)


def get_registry_process_assembler(process_type: str) -> RegistryProcessAssembler | None:
    """Return assembly metadata for a supported registry process type."""

    return _REGISTRY_PROCESS_ASSEMBLERS.get(process_type)


def build_registry_process_config_data(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    output_directory: str | None,
) -> dict[str, Any]:
    """Build raw model-config data for a supported registry process."""

    assembler = get_registry_process_assembler(compatibility.process_type)
    if assembler is None:
        raise RegistryCaseBuildError(
            "Registry case builder does not support process_type "
            f"{compatibility.process_type!r}."
        )
    case_template = select_registry_case_template(
        registry=registry,
        compatibility=compatibility,
        assembler=assembler,
    )
    substrate = registry.get_substrate(substrate_id)
    return assembler.config_data_builder(
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


def select_registry_case_template(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    assembler: RegistryProcessAssembler | None = None,
) -> CaseTemplateRecord:
    """Return the explicit case-template record for one compatibility record."""

    if not compatibility.case_template_id:
        raise RegistryCaseBuildError(
            "Process compatibility record "
            f"{compatibility.record_id!r} does not declare case_template_id."
        )
    try:
        template = registry.get_case_template(compatibility.case_template_id)
    except RegistryLookupError as exc:
        raise RegistryCaseBuildError(
            "Process compatibility record "
            f"{compatibility.record_id!r} references missing case template "
            f"{compatibility.case_template_id!r}."
        ) from exc
    selected_assembler = assembler or get_registry_process_assembler(compatibility.process_type)
    if selected_assembler is None:
        raise RegistryCaseBuildError(
            "Registry case builder does not support process_type "
            f"{compatibility.process_type!r}."
        )
    if template.process_type != compatibility.process_type:
        raise RegistryCaseBuildError(
            "Case template process_type mismatch: "
            f"template {template.case_template_id!r} uses {template.process_type!r}, "
            f"but compatibility {compatibility.record_id!r} uses {compatibility.process_type!r}."
        )
    missing_roles = tuple(role for role in selected_assembler.required_state_roles if role not in template.state_roles)
    if missing_roles:
        raise RegistryCaseBuildError(
            "Case template "
            f"{template.case_template_id!r} is missing state role(s) required for "
            f"{selected_assembler.process_label}: {', '.join(missing_roles)}."
        )
    return template


def select_registry_case_compatibility(
    *,
    registry: FungModRegistry,
    fungus_id: str,
    substrate_id: str,
    report: ModelabilityReport,
) -> ProcessCompatibilityRecord:
    fungus = registry.get_fungus(fungus_id)
    substrate = registry.get_substrate(substrate_id)
    for enzyme_class_id in fungus.enzyme_classes:
        for process_type in report.required_processes:
            for compatibility in registry.get_process_compatibility(
                enzyme_class=enzyme_class_id,
                substrate_class=substrate.substrate_class,
                process_type=process_type,
            ):
                if set(compatibility.required_bond_classes).issubset(substrate.bond_classes):
                    return compatibility
    raise RegistryCaseBuildError(
        "Modelability reported a modelable case, but no compatible process "
        "record could be selected for config assembly."
    )


def _exact_role_parameters(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    required_roles: tuple[str, ...],
    process_label: str,
) -> Mapping[str, ParameterRecord]:
    missing_roles = tuple(
        role for role in required_roles if role not in compatibility.parameter_roles
    )
    if missing_roles:
        raise RegistryCaseBuildError(
            f"{process_label} registry compatibility is missing parameter role "
            f"mappings for: {', '.join(missing_roles)}."
        )

    resolved: dict[str, ParameterRecord] = {}
    roles_to_resolve = _roles_to_resolve(
        compatibility=compatibility,
        required_roles=required_roles,
    )
    for role in roles_to_resolve:
        symbol = compatibility.parameter_roles[role]
        record = _best_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
        )
        if record is None:
            raise RegistryCaseBuildError(
                f"No registry parameter record found for role {role!r} and symbol {symbol!r}."
            )
        if not record.value.is_exact:
            raise RegistryCaseBuildError(
                f"Deterministic registry case builder requires exact parameters; role {role!r} uses "
                f"symbol {symbol!r} with ValueSpec kind {record.value.kind!r}."
            )
        validation = record.value.validate(nonnegative=True)
        if not validation.passed:
            raise RegistryCaseBuildError(
                f"Parameter {symbol!r} for role {role!r} failed ValueSpec validation: "
                f"{validation.to_dict()}"
            )
        resolved[role] = record
    return resolved


def _template_state(case_template: CaseTemplateRecord, role: str) -> str:
    try:
        return case_template.state_roles[role]
    except KeyError as exc:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} is missing state role {role!r}."
        ) from exc


def _template_time_config(case_template: CaseTemplateRecord) -> dict[str, Any]:
    time_grid = case_template.time_grid
    return {
        "start": {"value": float(time_grid["start"]), "units": str(time_grid["units"])},
        "stop": {"value": float(time_grid["stop"]), "units": str(time_grid["units"])},
        "points": int(time_grid["points"]),
    }


def _initial_state_from_template(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    states: dict[str, dict[str, Any]] = {}
    for state_role, spec in case_template.initial_state_mapping.items():
        state_name = _template_state(case_template, state_role)
        states[state_name] = {
            "value": _template_initial_value(spec, parameter_records=parameter_records),
            "units": _template_initial_units(spec, parameter_records=parameter_records),
        }
    return {"states": states}


def _template_initial_value(
    spec: Mapping[str, Any],
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> float:
    parameter_role = spec.get("parameter_role")
    if parameter_role is not None:
        role = str(parameter_role)
        return _record_exact_value(_template_parameter_record(parameter_records, role), role=role)
    return float(spec["value"])


def _template_initial_units(
    spec: Mapping[str, Any],
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> str:
    units_from_role = spec.get("units_from_role")
    if units_from_role is not None:
        role = str(units_from_role)
        return _record_units(_template_parameter_record(parameter_records, role), role=role)
    return str(spec["units"])


def _template_parameter_record(
    parameter_records: Mapping[str, ParameterRecord],
    role: str,
) -> ParameterRecord:
    try:
        return parameter_records[role]
    except KeyError as exc:
        raise RegistryCaseBuildError(
            f"Case template references parameter role {role!r}, but that role was not resolved."
        ) from exc


def _product_map_id(case_template: CaseTemplateRecord) -> str:
    return str(case_template.product_map["id"])


def _product_map_entity(
    *,
    case_template: CaseTemplateRecord,
    provenance: Mapping[str, Any],
    name: str,
    maturity: str,
) -> dict[str, Any]:
    product_map_type = str(case_template.product_map["product_map_type"])
    substrate_state = _template_state(case_template, str(case_template.product_map["substrate_state_role"]))
    product_role = str(case_template.product_map["product_state_role"])
    product_state = _template_state(case_template, product_role)
    data: dict[str, Any] = {
        "kind": "product_map",
        "name": name,
        "product_map_type": product_map_type,
        "maturity": maturity,
        "provenance": {
            "source": provenance.get("source", provenance.get("source_database", "FungMod registry case template")),
            "confidence_level": provenance.get("confidence_level", "registry_metadata"),
            "notes": str(case_template.product_map.get("notes", "")),
        },
        "notes": str(case_template.product_map.get("notes", "")),
    }
    if product_map_type == "one_to_one":
        data.update(
            {
                "substrate_state": substrate_state,
                "product_state": product_state,
            }
        )
    elif product_map_type == "stoichiometric":
        data.update(
            {
                "reactants": {substrate_state: 1.0},
                "products": {product_state: _template_product_yield(case_template, product_role)},
            }
        )
    else:
        raise RegistryCaseBuildError(
            f"Unsupported product_map_type {product_map_type!r} in case template "
            f"{case_template.case_template_id!r}."
        )
    return {
        "id": _product_map_id(case_template),
        "loader": product_map_type,
        "data": data,
    }


def _template_product_yield(case_template: CaseTemplateRecord, product_role: str) -> float:
    if product_role in case_template.stoichiometric_yields:
        return float(case_template.stoichiometric_yields[product_role])
    yield_value = case_template.product_map.get("stoichiometric_yield")
    if yield_value is not None:
        return float(yield_value)
    raise RegistryCaseBuildError(
        f"Case template {case_template.case_template_id!r} does not define a yield for product role {product_role!r}."
    )


def _product_conserved_weight(case_template: CaseTemplateRecord, product_role: str) -> float:
    yield_value = _template_product_yield(case_template, product_role)
    if yield_value <= 0.0:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} defines a non-positive yield "
            f"for product role {product_role!r}."
        )
    return 1.0 / yield_value


def _case_template_config(case_template: CaseTemplateRecord) -> dict[str, Any]:
    return {
        "case_template_id": case_template.case_template_id,
        "schema_version": case_template.schema_version,
        "process_type": case_template.process_type,
        "state_roles": dict(case_template.state_roles),
        "observable_roles": list(case_template.observable_roles),
        "output_state_roles": dict(case_template.output_state_roles),
        "limitations": list(case_template.limitations),
        "validity_notes": list(case_template.validity_notes),
    }


def _process_assumptions(case_template: CaseTemplateRecord, fallback: tuple[str, ...]) -> list[str]:
    return list(case_template.limitations or fallback)


def _template_process_modifiers(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    registry: FungModRegistry,
    environment_id: str,
) -> list[dict[str, Any]]:
    modifiers = case_template.process_state_metadata.get("process_modifiers")
    if modifiers is None:
        return []
    if not isinstance(modifiers, list) or any(not isinstance(item, Mapping) for item in modifiers):
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} process_modifiers must be a sequence of mappings."
        )
    configured: list[dict[str, Any]] = []
    for index, modifier in enumerate(modifiers):
        modifier_type = str(modifier.get("type", "")).strip()
        if modifier_type == "product_inhibition":
            configured.append(
                _template_product_inhibition_modifier(
                    case_template=case_template,
                    parameter_records=parameter_records,
                    modifier=modifier,
                    index=index,
                )
            )
            continue
        if modifier_type in ENVIRONMENT_MODIFIER_TYPES:
            configured.append(
                _template_environment_modifier(
                    case_template=case_template,
                    parameter_records=parameter_records,
                    registry=registry,
                    environment_id=environment_id,
                    modifier=modifier,
                    modifier_type=modifier_type,
                    index=index,
                )
            )
            continue
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} declares unsupported modifier type "
            f"{modifier_type!r}."
        )
    return configured


def _template_product_inhibition_modifier(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    modifier: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    product_role = str(modifier.get("product_state_role", "")).strip()
    if not product_role:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} process_modifiers[{index}] requires "
            "product_state_role."
        )
    inhibition_role = str(modifier.get("inhibition_constant_role", "")).strip()
    if not inhibition_role:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} process_modifiers[{index}] requires "
            "inhibition_constant_role."
        )
    return {
        "type": "product_inhibition",
        "product_state": _template_state(case_template, product_role),
        "inhibition_constant": _template_parameter_symbol(
            case_template=case_template,
            parameter_records=parameter_records,
            role=inhibition_role,
            field_name="inhibition_constant_role",
        ),
    }


def _template_environment_modifier(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    registry: FungModRegistry,
    environment_id: str,
    modifier: Mapping[str, Any],
    modifier_type: str,
    index: int,
) -> dict[str, Any]:
    if modifier_type == "temperature_arrhenius_reference":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="temperature",
            case_template=case_template,
            modifier_type=modifier_type,
            index=index,
        )
        configured = {
            "type": modifier_type,
            "activation_energy_symbol": _required_modifier_role_symbol(
                case_template=case_template,
                parameter_records=parameter_records,
                modifier=modifier,
                role_field="activation_energy_role",
                index=index,
            ),
            "reference_temperature_symbol": _required_modifier_role_symbol(
                case_template=case_template,
                parameter_records=parameter_records,
                modifier=modifier,
                role_field="reference_temperature_role",
                index=index,
            ),
        }
        _add_optional_modifier_role_symbol(
            configured,
            "minimum_temperature_symbol",
            case_template=case_template,
            parameter_records=parameter_records,
            modifier=modifier,
            role_field="minimum_temperature_role",
        )
        _add_optional_modifier_role_symbol(
            configured,
            "maximum_temperature_symbol",
            case_template=case_template,
            parameter_records=parameter_records,
            modifier=modifier,
            role_field="maximum_temperature_role",
        )
        return configured
    if modifier_type == "ph_gaussian":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="ph",
            case_template=case_template,
            modifier_type=modifier_type,
            index=index,
        )
        configured = {
            "type": modifier_type,
            "optimum_symbol": _required_modifier_role_symbol(
                case_template=case_template,
                parameter_records=parameter_records,
                modifier=modifier,
                role_field="optimum_role",
                index=index,
            ),
            "width_symbol": _required_modifier_role_symbol(
                case_template=case_template,
                parameter_records=parameter_records,
                modifier=modifier,
                role_field="width_role",
                index=index,
            ),
        }
        _add_optional_modifier_role_symbol(
            configured,
            "minimum_ph_symbol",
            case_template=case_template,
            parameter_records=parameter_records,
            modifier=modifier,
            role_field="minimum_ph_role",
        )
        _add_optional_modifier_role_symbol(
            configured,
            "maximum_ph_symbol",
            case_template=case_template,
            parameter_records=parameter_records,
            modifier=modifier,
            role_field="maximum_ph_role",
        )
        return configured
    if modifier_type == "oxygen_monod":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="oxygen_concentration",
            case_template=case_template,
            modifier_type=modifier_type,
            index=index,
        )
        oxygen_units = str(modifier.get("oxygen_units", "")).strip()
        if not oxygen_units:
            raise RegistryCaseBuildError(
                f"Case template {case_template.case_template_id!r} process_modifiers[{index}] "
                "requires oxygen_units."
            )
        return {
            "type": modifier_type,
            "half_saturation_symbol": _required_modifier_role_symbol(
                case_template=case_template,
                parameter_records=parameter_records,
                modifier=modifier,
                role_field="half_saturation_role",
                index=index,
            ),
            "oxygen_units": oxygen_units,
        }
    if modifier_type == "water_activity_threshold":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="water_activity",
            case_template=case_template,
            modifier_type=modifier_type,
            index=index,
        )
        return {
            "type": modifier_type,
            "minimum_water_activity_symbol": _required_modifier_role_symbol(
                case_template=case_template,
                parameter_records=parameter_records,
                modifier=modifier,
                role_field="minimum_water_activity_role",
                index=index,
            ),
        }
    raise RegistryCaseBuildError(
        f"Case template {case_template.case_template_id!r} declares unsupported modifier type "
        f"{modifier_type!r}."
    )


def _required_modifier_role_symbol(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    modifier: Mapping[str, Any],
    role_field: str,
    index: int,
) -> str:
    role = str(modifier.get(role_field, "")).strip()
    if not role:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} process_modifiers[{index}] requires "
            f"{role_field}."
        )
    return _template_parameter_symbol(
        case_template=case_template,
        parameter_records=parameter_records,
        role=role,
        field_name=role_field,
    )


def _add_optional_modifier_role_symbol(
    configured: dict[str, Any],
    symbol_field: str,
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    modifier: Mapping[str, Any],
    role_field: str,
) -> None:
    role = str(modifier.get(role_field, "")).strip()
    if not role:
        return
    configured[symbol_field] = _template_parameter_symbol(
        case_template=case_template,
        parameter_records=parameter_records,
        role=role,
        field_name=role_field,
    )


def _template_parameter_symbol(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    role: str,
    field_name: str,
) -> str:
    try:
        return parameter_records[role].parameter_symbol
    except KeyError as exc:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} modifier references unresolved "
            f"{field_name} {role!r}."
        ) from exc


def _require_exact_environment_condition(
    *,
    registry: FungModRegistry,
    environment_id: str,
    condition_name: str,
    case_template: CaseTemplateRecord,
    modifier_type: str,
    index: int,
) -> None:
    environment = registry.get_environment(environment_id)
    value = environment.conditions.get(condition_name)
    if value is None:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} process_modifiers[{index}] "
            f"{modifier_type!r} requires environment condition {condition_name!r} in "
            f"environment {environment_id!r}."
        )
    if not value.is_exact:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} process_modifiers[{index}] "
            f"{modifier_type!r} requires exact environment condition {condition_name!r}; "
            f"environment {environment_id!r} has ValueSpec kind {value.kind!r}."
        )
    validation = value.validate(nonnegative=condition_name in {"oxygen_concentration", "water_activity"})
    if not validation.passed or value.value is None or value.units is None:
        raise RegistryCaseBuildError(
            f"Environment condition {condition_name!r} for environment {environment_id!r} "
            f"failed exact ValueSpec validation: {validation.to_dict()}."
        )


def _template_environment_entity(
    *,
    registry: FungModRegistry,
    environment_id: str,
    modifiers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    required_conditions = _required_environment_conditions(modifiers)
    if not required_conditions:
        return None
    environment = registry.get_environment(environment_id)
    return {
        "id": environment_id,
        "data": {
            "kind": "environment",
            "name": environment.name,
            "provenance": {
                **dict(environment.provenance),
                "source": _environment_source(environment, required_conditions),
            },
            "conditions": {
                condition: environment.conditions[condition].to_dict()
                for condition in required_conditions
            },
            "notes": environment.notes,
        },
    }


def _required_environment_conditions(modifiers: list[dict[str, Any]]) -> tuple[str, ...]:
    conditions: list[str] = []
    for modifier in modifiers:
        modifier_type = str(modifier.get("type", "")).strip()
        if modifier_type == "temperature_arrhenius_reference":
            conditions.append("temperature")
        elif modifier_type == "ph_gaussian":
            conditions.append("ph")
        elif modifier_type == "oxygen_monod":
            conditions.append("oxygen_concentration")
        elif modifier_type == "water_activity_threshold":
            conditions.append("water_activity")
    return tuple(dict.fromkeys(conditions))


def _environment_source(environment: EnvironmentRecord, required_conditions: tuple[str, ...]) -> str:
    provenance_source = str(environment.provenance.get("source", "")).strip()
    if provenance_source:
        return provenance_source
    condition_sources = {
        str(environment.conditions[condition].source or "").strip()
        for condition in required_conditions
    }
    condition_sources.discard("")
    if len(condition_sources) == 1:
        return next(iter(condition_sources))
    source_database = str(environment.provenance.get("source_database", "")).strip()
    source_reaction_id = str(environment.provenance.get("source_reaction_id", "")).strip()
    if source_database and source_reaction_id:
        return f"{source_database} reaction {source_reaction_id}"
    if source_database:
        return source_database
    raise RegistryCaseBuildError(
        f"Environment record {environment.record_id!r} cannot provide a source for configured "
        "environment modifier assembly."
    )


def _template_config_name(
    *,
    case_template: CaseTemplateRecord,
    fungus_id: str,
    substrate_id: str,
    fallback: str,
) -> str:
    template = case_template.process_state_metadata.get("config_name")
    if template is None:
        return fallback
    return str(template).format(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        case_template_id=case_template.case_template_id,
    )


def _template_config_mode(case_template: CaseTemplateRecord, *, fallback: str) -> str:
    return str(case_template.process_state_metadata.get("config_mode", fallback))


def _template_config_maturity(case_template: CaseTemplateRecord, *, fallback: str) -> str:
    return str(case_template.process_state_metadata.get("config_maturity", fallback))


def _template_geometry_data(case_template: CaseTemplateRecord, *, fallback: dict[str, Any]) -> dict[str, Any]:
    geometry = case_template.process_state_metadata.get("geometry")
    if isinstance(geometry, Mapping):
        return deepcopy(dict(geometry))
    return fallback


def _surface_catalysis_config_data(
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
    bio001 = _is_bio001_surface_case(compatibility)
    substrate_state = _template_state(case_template, "substrate")
    product_state = _template_state(case_template, "product")
    catalyst_state = _template_state(case_template, "catalyst")
    product_map_id = _product_map_id(case_template)
    primary_bond = str(case_template.process_state_metadata.get("bond_type") or substrate.bond_classes[0])
    accessible_site_pool = str(
        case_template.process_state_metadata.get("accessible_site_pool")
        or "configured accessible site pool"
    )
    provenance = _surface_catalysis_provenance(
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        bio001=bio001,
    )
    modifiers = _template_process_modifiers(
        case_template=case_template,
        parameter_records=parameter_records,
        registry=registry,
        environment_id=environment_id,
    )
    environment_entity = _template_environment_entity(
        registry=registry,
        environment_id=environment_id,
        modifiers=modifiers,
    )
    entities: dict[str, Any] = {
        "geometry": {
            "id": "geometry",
            "loader": "well_mixed",
            "data": _template_geometry_data(
                case_template,
                fallback=_bio001_geometry_data() if bio001 else _toy_geometry_data(),
            ),
        },
        "substrates": [
            {
                "id": substrate_id,
                "loader": "generic_solid",
                "data": _surface_substrate_data(
                    substrate=substrate,
                    enzyme_class=compatibility.enzyme_class,
                    provenance=provenance,
                    bio001=bio001,
                ),
            }
        ],
        "enzymes": [
            {
                "id": compatibility.enzyme_class,
                "data": _surface_enzyme_data(
                    compatibility=compatibility,
                    substrate=substrate,
                    provenance=provenance,
                    bio001=bio001,
                ),
            }
        ],
        "product_maps": [
            _product_map_entity(
                case_template=case_template,
                provenance=provenance,
                name=(
                    "BIO-001 cellulose soluble product release map"
                    if bio001
                    else "toy registry one-to-one product release map"
                ),
                maturity="exploratory" if bio001 else "framework_benchmark",
            )
        ],
    }
    if environment_entity is not None:
        entities["environment"] = environment_entity
    return {
        "kind": "model_config",
        "name": _template_config_name(
            case_template=case_template,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            fallback=_surface_config_name(fungus_id=fungus_id, substrate_id=substrate_id, bio001=bio001),
        ),
        "mode": _template_config_mode(case_template, fallback="exploratory" if bio001 else "toy"),
        "maturity": _template_config_maturity(case_template, fallback="exploratory" if bio001 else "framework_benchmark"),
        "provenance": provenance,
        "case_template": _case_template_config(case_template),
        "entities": entities,
        "parameters": [
            {
                "id": "registry_case_parameters",
                "parameters": [
                    (
                        _exploratory_surface_parameter_config(record, role=role)
                        if bio001
                        else _parameter_config(record, role=role)
                    )
                    for role, record in parameter_records.items()
                ],
            }
        ],
        "processes": [
            {
                "id": "registry_surface_catalysis",
                "process_type": "surface_catalysis",
                "states": {
                    "substrate": substrate_state,
                    "catalyst": catalyst_state,
                    "product": product_state,
                    "bond_type": primary_bond,
                    "accessible_site_pool": accessible_site_pool,
                },
                "parameters": {
                    role: record.parameter_symbol
                    for role, record in parameter_records.items()
                    if role in SURFACE_CATALYSIS_PARAMETER_ROLES
                },
                "product_map": product_map_id,
                "modifiers": modifiers,
                "output_state_roles": dict(case_template.output_state_roles),
                "assumptions": _process_assumptions(
                    case_template,
                    (
                        "Enzyme-mediated insoluble cellulose surface degradation pilot.",
                        "Accessible surface area is constant within each sample; surface renewal and morphology are not modeled.",
                        "Soluble product release is represented by a mass-equivalent product class.",
                    )
                    if bio001
                    else (
                        "Toy registry case builder only.",
                        "Uses the existing generic surface-catalysis factory without adding biology.",
                    ),
                ),
            }
        ],
        "initial_state": _initial_state_from_template(
            case_template=case_template,
            parameter_records=parameter_records,
        ),
        "time": _template_time_config(case_template),
        "validators": [
            {
                "id": "non_negative_states",
                "validator_type": "non_negative",
                "species": [substrate_state, product_state, catalyst_state],
            },
            {
                "id": "closed_mass_balance",
                "validator_type": "mass_balance",
                "conserved_weights": {
                    substrate_state: 1.0,
                    product_state: _product_conserved_weight(case_template, "product"),
                },
            },
        ],
        "outputs": {
            "directory": output_directory
            or f"outputs/registry_cases/{fungus_id}__{substrate_id}__{environment_id}",
            "save": ["record", "validation_report"],
            "plots": ["state_trajectories"],
        },
    }


def _roles_to_resolve(
    *,
    compatibility: ProcessCompatibilityRecord,
    required_roles: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*required_roles, *compatibility.parameter_roles.keys())))


def _is_bio001_surface_case(compatibility: ProcessCompatibilityRecord) -> bool:
    return compatibility.provenance.get("bio_milestone") == "BIO-001"


def _surface_config_name(*, fungus_id: str, substrate_id: str, bio001: bool) -> str:
    if bio001:
        return f"BIO-001 cellulose surface virtual experiment {fungus_id} on {substrate_id}"
    return f"toy registry case {fungus_id} on {substrate_id}"


def _surface_catalysis_provenance(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    bio001: bool,
) -> dict[str, Any]:
    if not bio001:
        return {
            "source": "FungMod R3 toy registry case builder.",
            "measurement_method": "software registry-to-config assembly test",
            "confidence_level": "testing",
            "notes": (
                "Toy/development plug-and-play assembly fixture only; not "
                "empirical evidence and not a biological model."
            ),
            "validity_range": "R3 framework tests only",
            "units": "not_applicable",
            "registry_id": registry.registry_id,
            "fungus_id": fungus_id,
            "substrate_id": substrate_id,
            "environment_id": environment_id,
            "process_compatibility_id": compatibility.record_id,
            "case_template_id": case_template.case_template_id,
        }
    return {
        "source": "FungMod BIO-001 controlled virtual-experiment scaffold.",
        "measurement_method": "registry assembly from user-supplied exploratory ValueSpec samples",
        "confidence_level": "exploratory_assumption",
        "validity_range": "BIO-001 cellulose surface-degradation pilot only",
        "units": "not_applicable",
        "bio_milestone": "BIO-001",
        "registry_id": registry.registry_id,
        "fungus_id": fungus_id,
        "substrate_id": substrate_id,
        "environment_id": environment_id,
        "process_compatibility_id": compatibility.record_id,
        "case_template_id": case_template.case_template_id,
        "parameter_record_ids": {
            role: record.record_id
            for role, record in parameter_records.items()
        },
        "parameter_value_sources": {
            role: record.value.source
            for role, record in parameter_records.items()
        },
        "notes": (
            "Exploratory enzyme-mediated insoluble cellulose surface-degradation "
            "pilot. It is not a whole-fungus model and does not include secretion, "
            "uptake, biomass growth, oxygen limitation, or full lignocellulose structure."
        ),
    }


def _surface_substrate_data(
    *,
    substrate: SubstrateRecord,
    enzyme_class: str,
    provenance: Mapping[str, Any],
    bio001: bool,
) -> dict[str, Any]:
    if not bio001:
        return _generic_substrate_data(substrate=substrate, enzyme_class=enzyme_class)
    return {
        "kind": "substrate",
        "name": substrate.name,
        "substrate_type": "generic_solid",
        "chemical_class": substrate.substrate_class,
        "physical_state": _configured_physical_state(substrate.physical_state),
        "bond_types": list(substrate.bond_classes),
        "accessible_bonds": list(substrate.bond_classes),
        "required_enzyme_classes": [enzyme_class],
        "degradation_products": [
            {
                "name": product,
                "source": provenance["source"],
                "notes": "BIO-001 soluble cellulose hydrolysis-product class; not a full stoichiometric speciation model.",
            }
            for product in substrate.products
        ],
        "completeness": "partial",
        "default_degradation_model": "heterogeneous_surface",
        "water_activity_dependence": "unknown",
        "provenance": {
            "source": provenance["source"],
            "confidence_level": provenance["confidence_level"],
            "notes": "Generic insoluble cellulose-like film metadata for BIO-001 surface degradation.",
        },
        "parameters": [],
    }


def _surface_enzyme_data(
    *,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
    provenance: Mapping[str, Any],
    bio001: bool,
) -> dict[str, Any]:
    if not bio001:
        return _toy_enzyme_data(compatibility=compatibility, substrate=substrate)
    return {
        "kind": "enzyme",
        "name": "Generic cellulase-like enzyme source",
        "enzyme_class": compatibility.enzyme_class,
        "target_bond_types": list(compatibility.required_bond_classes),
        "target_substrate_classes": [substrate.substrate_class],
        "target_substrate_names": [substrate.name],
        "validity_labels": ["exploratory_metadata", "surface_catalysis", "enzyme_mediated_cellulose_degradation"],
        "provenance": {
            "source": provenance["source"],
            "measurement_method": provenance["measurement_method"],
            "confidence_level": provenance["confidence_level"],
            "notes": (
                "Generic cellulase-like enzyme metadata for BIO-001. This does "
                "not model secretion, uptake, biomass growth, or enzyme inactivation."
            ),
            "validity_range": provenance["validity_range"],
            "units": "not_applicable",
        },
        "catalytic_parameters": [],
        "adsorption_parameters": [],
        "parameters": [],
    }


def _bio001_geometry_data() -> dict[str, Any]:
    return {
        "kind": "geometry",
        "name": "BIO-001 well-mixed enzyme assay context",
        "geometry_type": "well_mixed",
        "provenance": {
            "source": "FungMod BIO-001 controlled virtual-experiment scaffold.",
            "measurement_method": "user-specified virtual-experiment context",
            "confidence_level": "exploratory_assumption",
            "notes": "Geometry context for an enzyme-mediated surface-degradation pilot; no spatial gradients are modeled.",
            "validity_range": "BIO-001 cellulose surface-degradation pilot only",
            "units": "not_applicable",
        },
        "volume": {"value": 100.0, "units": "milliliter"},
        "surface_area": {"value": 0.5, "units": "meter ** 2"},
        "parameters": [],
    }


def _homogeneous_mm_config_data(
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
    substrate_state = _template_state(case_template, "substrate")
    product_state = _template_state(case_template, "product")
    enzyme_state = _template_state(case_template, "enzyme")
    substrate_initial = parameter_records["substrate_initial_concentration"]
    substrate_units = _record_units(substrate_initial, role="substrate_initial_concentration")
    rate_units = f"{substrate_units} / second"
    provenance = _homogeneous_mm_provenance(
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
    )
    modifiers = _template_process_modifiers(
        case_template=case_template,
        parameter_records=parameter_records,
        registry=registry,
        environment_id=environment_id,
    )
    environment_entity = _template_environment_entity(
        registry=registry,
        environment_id=environment_id,
        modifiers=modifiers,
    )
    entities: dict[str, Any] = {
        "substrates": [
            {
                "id": substrate_id,
                "loader": "generic_dissolved",
                "data": _homogeneous_substrate_data(
                    substrate=substrate,
                    enzyme_class=compatibility.enzyme_class,
                    provenance=provenance,
                ),
            }
        ],
        "enzymes": [
            {
                "id": compatibility.enzyme_class,
                "data": _homogeneous_enzyme_data(
                    compatibility=compatibility,
                    substrate=substrate,
                    provenance=provenance,
                ),
            }
        ],
        "product_maps": [
            _product_map_entity(
                case_template=case_template,
                provenance=provenance,
                name="SABIO-RK Reaction 618 cellobiose to beta-D-glucose product map",
                maturity="literature_metadata",
            )
        ],
    }
    if environment_entity is not None:
        entities["environment"] = environment_entity
    return {
        "kind": "model_config",
        "name": _template_config_name(
            case_template=case_template,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            fallback="SABIO-RK Reaction 618 beta-glucosidase cellobiose homogeneous Michaelis-Menten",
        ),
        "mode": _template_config_mode(case_template, fallback="scientific"),
        "maturity": _template_config_maturity(case_template, fallback="scientific"),
        "provenance": provenance,
        "case_template": _case_template_config(case_template),
        "entities": entities,
        "parameters": [
            {
                "id": "sabiork_reaction_618_parameters",
                "parameters": [
                    _scientific_parameter_config(record, role=role)
                    for role, record in parameter_records.items()
                ],
            }
        ],
        "processes": [
            {
                "id": "sabiork_reaction_618_homogeneous_mm",
                "process_type": "homogeneous_michaelis_menten",
                "states": {
                    "substrate": substrate_state,
                    "product": product_state,
                    "enzyme": enzyme_state,
                },
                "product_map": _product_map_id(case_template),
                "parameters": {
                    "km": parameter_records["km"].parameter_symbol,
                    "kcat": parameter_records["kcat"].parameter_symbol,
                    "rate_units": rate_units,
                },
                "modifiers": modifiers,
                "output_state_roles": dict(case_template.output_state_roles),
                "assumptions": _process_assumptions(
                    case_template,
                    (
                        "Dissolved homogeneous Michaelis-Menten kinetics for the selected SABIO-RK entry.",
                        "This is an enzyme-kinetics case, not a whole-fungus growth or uptake model.",
                    ),
                ),
            }
        ],
        "initial_state": _initial_state_from_template(
            case_template=case_template,
            parameter_records=parameter_records,
        ),
        "time": _template_time_config(case_template),
        "validators": [
            {
                "id": "non_negative_concentrations",
                "validator_type": "non_negative",
                "species": [substrate_state, product_state, enzyme_state],
            },
            {
                "id": "substrate_product_balance",
                "validator_type": "mass_balance",
                "conserved_weights": {
                    substrate_state: 1.0,
                    product_state: _product_conserved_weight(case_template, "product"),
                },
            },
        ],
        "outputs": {
            "directory": output_directory
            or f"outputs/registry_cases/{fungus_id}__{substrate_id}__{environment_id}",
            "save": ["record", "validation_report"],
            "plots": ["state_trajectories"],
        },
    }


def _homogeneous_substrate_data(
    *,
    substrate: SubstrateRecord,
    enzyme_class: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "substrate",
        "name": substrate.name,
        "substrate_type": "generic_dissolved",
        "chemical_class": substrate.substrate_class,
        "physical_state": "dissolved",
        "bond_types": list(substrate.bond_classes),
        "accessible_bonds": list(substrate.bond_classes),
        "required_enzyme_classes": [enzyme_class],
        "degradation_products": [
            {
                "name": product,
                "source": provenance["source"],
                "notes": "Product listed by SABIO-RK Reaction 618 stoichiometry.",
            }
            for product in substrate.products
        ],
        "completeness": "partial",
        "default_degradation_model": "homogeneous_dissolved",
        "water_activity_dependence": "unknown",
        "provenance": {
            "source": provenance["source"],
            "confidence_level": "literature_curated",
            "notes": "Cellobiose substrate metadata from the curated Reaction 618 registry case.",
        },
        "parameters": [],
    }


def _homogeneous_enzyme_data(
    *,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "enzyme",
        "name": "beta-glucosidase",
        "enzyme_class": compatibility.enzyme_class,
        "target_bond_types": list(compatibility.required_bond_classes),
        "target_substrate_classes": [substrate.substrate_class],
        "target_substrate_names": [substrate.name],
        "validity_labels": ["literature_metadata", "homogeneous_enzyme_kinetics"],
        "provenance": {
            "source": provenance["source"],
            "measurement_method": "SABIO-RK kinetic-law curation",
            "confidence_level": "literature_curated",
            "notes": (
                "Enzyme metadata for the selected Reaction 618 kinetic-law entry; "
                "does not model secretion, uptake, biomass growth, or organism-level degradation."
            ),
            "validity_range": "Selected SABIO-RK EntryID assay conditions.",
            "units": "not_applicable",
        },
        "catalytic_parameters": [],
        "adsorption_parameters": [],
        "parameters": [],
    }


def _toy_geometry_data() -> dict[str, Any]:
    return {
        "kind": "geometry",
        "name": "toy registry well-mixed 100 mL",
        "geometry_type": "well_mixed",
        "provenance": {
            "source": "FungMod R3 toy registry case builder.",
            "measurement_method": "defined benchmark metadata",
            "confidence_level": "testing",
            "notes": "Inline toy geometry for registry-to-config workflow tests.",
            "validity_range": "R3 framework tests only",
            "units": "not_applicable",
        },
        "volume": {"value": 100.0, "units": "milliliter"},
        "surface_area": {"value": 0.1, "units": "meter ** 2"},
        "parameters": [],
    }


def _generic_substrate_data(*, substrate: SubstrateRecord, enzyme_class: str) -> dict[str, Any]:
    return {
        "kind": "substrate",
        "name": substrate.name,
        "substrate_type": "generic_solid",
        "chemical_class": substrate.substrate_class,
        "physical_state": _configured_physical_state(substrate.physical_state),
        "bond_types": list(substrate.bond_classes),
        "accessible_bonds": list(substrate.bond_classes),
        "required_enzyme_classes": [enzyme_class],
        "degradation_products": [
            {
                "name": product,
                "notes": "Toy registry product placeholder; not empirical.",
            }
            for product in substrate.products
        ],
        "provenance": {
            "source": "FungMod R3 toy registry case builder.",
            "confidence_level": "testing",
            "notes": "Inline generic substrate generated from toy registry metadata.",
        },
        "parameters": [],
    }


def _toy_enzyme_data(
    *,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
) -> dict[str, Any]:
    return {
        "kind": "enzyme",
        "name": f"Toy registry catalyst for {compatibility.enzyme_class}",
        "enzyme_class": compatibility.enzyme_class,
        "target_bond_types": list(compatibility.required_bond_classes),
        "target_substrate_classes": [substrate.substrate_class],
        "target_substrate_names": [],
        "validity_labels": ["toy", "registry_case_builder"],
        "provenance": {
            "source": "FungMod R3 toy registry case builder.",
            "measurement_method": "defined benchmark metadata",
            "confidence_level": "testing",
            "notes": "Inline toy enzyme metadata for process compatibility only.",
            "validity_range": "R3 framework tests only",
            "units": "not_applicable",
        },
        "catalytic_parameters": [],
        "adsorption_parameters": [],
        "parameters": [],
    }


def _configured_physical_state(registry_physical_state: str) -> str:
    if registry_physical_state in {"mixed_solid", "solid_polymer", "solid_biomass", "dissolved", "unknown"}:
        return registry_physical_state
    if registry_physical_state in {"toy_solid", "solid"}:
        return "mixed_solid"
    raise RegistryCaseBuildError(
        "Registry substrate physical_state "
        f"{registry_physical_state!r} cannot be represented by the generic config loader."
    )


def _parameter_config(record: ParameterRecord, *, role: str) -> dict[str, Any]:
    assert record.value.value is not None
    return {
        "name": record.name,
        "symbol": record.parameter_symbol,
        "value": record.value.value,
        "units": record.value.units or "dimensionless",
        "uncertainty": 0.0,
        "source": record.value.source or record.provenance.get("source"),
        "confidence_level": record.value.confidence_level
        or record.provenance.get("confidence_level", "testing"),
        "notes": f"{record.notes} Registry case role: {role}. Toy/development only.",
        "measurement_method": "registry exact ValueSpec",
        "validity_range": "R3 toy registry case only",
    }


def _exploratory_surface_parameter_config(record: ParameterRecord, *, role: str) -> dict[str, Any]:
    value = _record_exact_value(record, role=role)
    return {
        "name": record.name,
        "symbol": record.parameter_symbol,
        "value": value,
        "units": _record_units(record, role=role),
        "uncertainty": 0.0,
        "source": record.value.source or _record_source(record),
        "confidence_level": record.value.confidence_level
        or record.provenance.get("confidence_level", "exploratory_assumption"),
        "notes": f"{record.notes} Registry case role: {role}.",
        "measurement_method": "sampled from user-supplied exploratory registry ValueSpec",
        "validity_range": "BIO-001 cellulose surface-degradation pilot only",
    }


def _scientific_parameter_config(record: ParameterRecord, *, role: str) -> dict[str, Any]:
    value = _record_exact_value(record, role=role)
    return {
        "name": record.name,
        "symbol": record.parameter_symbol,
        "value": value,
        "units": _record_units(record, role=role),
        "uncertainty": 0.0,
        "source": record.value.source or _record_source(record),
        "confidence_level": record.value.confidence_level
        or record.provenance.get("confidence_level", "literature_curated"),
        "notes": f"{record.notes} Registry case role: {role}.",
        "measurement_method": "SABIO-RK selected kinetic-law curation",
        "validity_range": "Selected SABIO-RK EntryID assay conditions only.",
    }


def _record_exact_value(record: ParameterRecord, *, role: str) -> float:
    if record.value.value is None:
        raise RegistryCaseBuildError(
            f"Role {role!r} resolved to parameter {record.parameter_symbol!r} without an exact value."
        )
    return float(record.value.value)


def _record_units(record: ParameterRecord, *, role: str) -> str:
    if record.value.units is None:
        raise RegistryCaseBuildError(
            f"Role {role!r} resolved to parameter {record.parameter_symbol!r} without units."
        )
    return record.value.units


def _record_source(record: ParameterRecord) -> str:
    source = record.provenance.get("source")
    if source is not None:
        return str(source)
    if record.provenance.get("source_database") == "SABIO-RK":
        return "SABIO-RK Reaction 618 selected kinetic law"
    return "FungMod registry record"


def _extracellular_enzyme_chain_config_data(
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
    from fungal_model.screening.enzyme_chain import build_extracellular_enzyme_chain_config

    config = build_extracellular_enzyme_chain_config(
        registry=registry,
        template_id=case_template.case_template_id,
        output_directory=output_directory,
    )
    data = config.to_dict()
    data["provenance"] = {
        **dict(data.get("provenance", {})),
        "registry_id": registry.registry_id,
        "fungus_id": fungus_id,
        "substrate_id": substrate_id,
        "environment_id": environment_id,
        "process_compatibility_id": compatibility.record_id,
        "case_template_id": case_template.case_template_id,
        "substrate_name": substrate.name,
        "parameter_record_ids": {
            role: record.record_id
            for role, record in parameter_records.items()
        },
        "notes": (
            "CASE-001 researcher-facing assembly of the existing BIO-002 extracellular "
            "enzyme-chain template. This is cellulose-equivalent, exploratory, and not "
            "a whole-fungus growth, secretion, uptake, biomass, PET, lignin, full "
            "lignocellulose, organism-specific physiology, or empirical-validation model."
        ),
    }
    data["outputs"]["directory"] = output_directory
    return data


def _homogeneous_mm_provenance(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    environment = registry.get_environment(environment_id)
    source = "SABIO-RK Reaction 618 selected kinetic law"
    return {
        "source": source,
        "source_database": compatibility.provenance.get("source_database", "SABIO-RK"),
        "source_reaction_id": compatibility.provenance.get("source_reaction_id"),
        "selected_kinlaw_entry_id": compatibility.provenance.get("selected_kinlaw_entry_id"),
        "kinetic_record": _first_present(
            record.provenance.get("kinetic_record")
            for record in parameter_records.values()
        ),
        "registry_id": registry.registry_id,
        "fungus_id": fungus_id,
        "substrate_id": substrate_id,
        "environment_id": environment_id,
        "process_compatibility_id": compatibility.record_id,
        "case_template_id": case_template.case_template_id,
        "parameter_record_ids": {
            role: record.record_id
            for role, record in parameter_records.items()
        },
        "parameter_value_sources": {
            role: record.value.source
            for role, record in parameter_records.items()
        },
        "environment_conditions": {
            name: value.to_dict()
            for name, value in environment.conditions.items()
        },
        "notes": (
            "Homogeneous Michaelis-Menten config assembled from local FungMod registry "
            "records derived from the selected SABIO-RK Reaction 618 entry."
        ),
    }


def _first_present(values) -> Any | None:
    for value in values:
        if value is not None:
            return value
    return None


def _best_parameter_record(
    *,
    registry: FungModRegistry,
    parameter_symbol: str,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
) -> ParameterRecord | None:
    candidates = [
        record
        for record in registry.parameters.values()
        if record.parameter_symbol == parameter_symbol
        and record.process_type == compatibility.process_type
        and _matches(record.enzyme_class, compatibility.enzyme_class)
        and _matches(record.substrate_class, compatibility.substrate_class)
        and _matches(record.fungus_id, fungus_id)
        and _matches(record.substrate_id, substrate_id)
        and _matches(record.environment_id, environment_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=_parameter_specificity)


def _matches(record_value: str | None, requested: str) -> bool:
    return record_value is None or record_value == requested


def _parameter_specificity(record: ParameterRecord) -> tuple[int, int, int]:
    selector_score = sum(
        value is not None
        for value in (
            record.enzyme_class,
            record.substrate_class,
            record.fungus_id,
            record.substrate_id,
            record.environment_id,
        )
    )
    value_score = 2 if record.value.is_exact else 1 if record.value.is_uncertain else 0
    maturity_score = 1 if record.maturity == "calibrated" else 0
    return selector_score, value_score, maturity_score


def _validate_mode(mode: str) -> None:
    if mode not in {"toy", "scientific"}:
        raise RegistryCaseBuildError(
            "Deterministic registry case builder supports only mode='toy' "
            "or mode='scientific'."
        )


_REGISTRY_PROCESS_ASSEMBLERS = {
    "surface_catalysis": RegistryProcessAssembler(
        process_type="surface_catalysis",
        process_label="Surface-catalysis",
        required_parameter_roles=SURFACE_CATALYSIS_PARAMETER_ROLES,
        required_state_roles=("substrate", "product", "catalyst"),
        deterministic_mode="toy",
        unsupported_mode_message=(
            "Surface-catalysis registry assembly currently only emits toy model configs."
        ),
        config_data_builder=_surface_catalysis_config_data,
    ),
    "homogeneous_michaelis_menten": RegistryProcessAssembler(
        process_type="homogeneous_michaelis_menten",
        process_label="Homogeneous Michaelis-Menten",
        required_parameter_roles=HOMOGENEOUS_MM_PARAMETER_ROLES,
        required_state_roles=("substrate", "product", "enzyme"),
        deterministic_mode="scientific",
        unsupported_mode_message=(
            "Homogeneous Michaelis-Menten registry assembly requires mode='scientific'."
        ),
        config_data_builder=_homogeneous_mm_config_data,
    ),
    "extracellular_enzyme_chain": RegistryProcessAssembler(
        process_type="extracellular_enzyme_chain",
        process_label="Extracellular enzyme chain",
        required_parameter_roles=EXTRACELLULAR_ENZYME_CHAIN_PARAMETER_ROLES,
        required_state_roles=("substrate", "intermediate", "product", "surface_catalyst", "homogeneous_catalyst"),
        deterministic_mode="toy",
        unsupported_mode_message=(
            "Extracellular enzyme-chain registry assembly currently emits the existing "
            "exploratory CASE-001/BIO-002 template through exploratory screens."
        ),
        config_data_builder=_extracellular_enzyme_chain_config_data,
    ),
}


__all__ = [
    "RegistryCaseBuildError",
    "RegistryCaseConfigMode",
    "RegistryProcessAssembler",
    "build_registry_process_config_data",
    "build_model_config_from_registry_case",
    "get_registry_process_assembler",
    "select_registry_case_compatibility",
    "select_registry_case_template",
]
