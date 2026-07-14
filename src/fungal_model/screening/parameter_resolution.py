"""Shared parameter admission and exact case-template role resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from fungal_model.registry.records import (
    CaseTemplateRecord,
    ParameterRecord,
    ParameterRecordSelectionMode,
    ProcessCompatibilityRecord,
    parameter_record_mode_eligibility_blocker,
)
from fungal_model.registry.store import FungModRegistry, RegistryValidationError

ParameterValueRequirement = Literal["exact", "sampleable"]

_SELECTOR_FIELDS = (
    "enzyme_class",
    "substrate_class",
    "fungus_id",
    "substrate_id",
    "environment_id",
)
_BASE_CONTRACT_FIELDS = frozenset(
    {"kind", "parameter_symbol", *_SELECTOR_FIELDS}
)
_INITIAL_CONTRACT_FIELDS = _BASE_CONTRACT_FIELDS | {"record_process_type"}
_INITIAL_STATE_COMPATIBILITY_ROLE_BY_PROCESS_FIELD = {
    "catalyst": "enzyme_initial_concentration",
    "enzyme": "enzyme_initial_concentration",
    "substrate": "substrate_initial_amount",
}
_MODIFIER_COMPATIBILITY_ROLE_BY_FIELD = {
    "product_inhibition": {
        "inhibition_constant_role": "inhibition_constant",
    },
    "temperature_arrhenius_reference": {
        "activation_energy_role": "activation_energy",
        "reference_temperature_role": "reference_temperature",
        "minimum_temperature_role": "minimum_temperature",
        "maximum_temperature_role": "maximum_temperature",
    },
    "ph_gaussian": {
        "optimum_role": "ph_optimum",
        "width_role": "ph_width",
        "minimum_ph_role": "minimum_ph",
        "maximum_ph_role": "maximum_ph",
    },
    "oxygen_monod": {
        "half_saturation_role": "oxygen_half_saturation",
    },
    "water_activity_threshold": {
        "minimum_water_activity_role": "minimum_water_activity",
    },
}
_DIRECT_PROCESS_PARAMETER_FIELDS = {
    "surface_catalysis": (
        "surface_rate_constant",
        "adsorption_constant",
        "accessible_surface_area",
    ),
    "homogeneous_michaelis_menten": ("km", "kcat"),
}


@dataclass(frozen=True)
class _StateComponent:
    entity_type: str
    entity_id: str
    component_class: str


@dataclass(frozen=True)
class _ResolvedProcessComponent:
    compatibility: ProcessCompatibilityRecord
    enzyme: _StateComponent
    substrate: _StateComponent


class ExactTemplateParameterError(ValueError):
    """Raised when an explicit template parameter mapping is not exact and runnable."""

    def __init__(self, message: str, *, role: str = "") -> None:
        super().__init__(message)
        self.role = role


def exact_template_compatibility(
    registry: FungModRegistry,
    template: CaseTemplateRecord,
) -> ProcessCompatibilityRecord | None:
    """Return the unique compatibility record bound to a template, when present."""

    matches = tuple(
        record
        for record in registry.process_compatibility.values()
        if record.case_template_id == template.case_template_id
    )
    if len(matches) > 1:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} is referenced by multiple "
            "process compatibility records."
        )
    return matches[0] if matches else None


def resolve_exact_template_parameter_records(
    *,
    registry: FungModRegistry,
    template: CaseTemplateRecord,
    mode: ParameterRecordSelectionMode,
    environment_id: str | None,
    value_requirement: ParameterValueRequirement,
    compatibility: ProcessCompatibilityRecord | None = None,
    required_roles: Sequence[str] = (),
    fungus_id: str | None = None,
    substrate_id: str | None = None,
) -> Mapping[str, ParameterRecord] | None:
    """Resolve and fully validate a template's explicit role-to-record mapping.

    ``None`` means the template genuinely omits ``parameter_record_ids`` and may
    use an existing dynamic-resolution contract. Once the key is present, every
    role is validated without fallback or substitution.
    """

    metadata = template.process_state_metadata
    if "parameter_record_ids" not in metadata:
        return None
    if "parameter_role_process_types" in metadata:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} uses deprecated "
            "parameter_role_process_types; explicit mappings require per-role record contracts."
        )
    record_ids = _required_mapping(
        metadata.get("parameter_record_ids"),
        label=f"Case template {template.case_template_id!r} parameter_record_ids",
    )
    contracts = _required_mapping(
        metadata.get("parameter_role_contracts"),
        label=f"Case template {template.case_template_id!r} parameter_role_contracts",
    )
    roles = tuple(record_ids)
    if not roles:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} parameter_record_ids cannot be empty."
        )
    effective_required_roles = tuple(
        dict.fromkeys(
            (
                *required_roles,
                *(compatibility.parameter_roles if compatibility is not None else ()),
            )
        )
    )
    if set(contracts) != set(record_ids):
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} parameter_role_contracts must "
            "have exactly the same role keys as parameter_record_ids."
        )
    missing_roles = tuple(
        role for role in effective_required_roles if role not in record_ids
    )
    if missing_roles:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} is missing explicit parameter "
            f"record IDs for: {', '.join(missing_roles)}.",
            role=missing_roles[0],
        )

    initial_roles = _initial_parameter_roles(template)
    missing_initial_roles = tuple(sorted(initial_roles.difference(record_ids)))
    if missing_initial_roles:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} initial_state_mapping "
            "parameter_role/units_from_role values lack explicit parameter records: "
            f"{', '.join(missing_initial_roles)}.",
            role=missing_initial_roles[0],
        )
    (
        process_owners,
        declared_process_types,
        process_components,
        process_role_keys,
        process_templates,
    ) = _process_role_owners(
        template,
        record_roles=frozenset(roles),
    )
    _validate_compatibility_contract(
        template=template,
        compatibility=compatibility,
        record_roles=frozenset(roles),
        required_roles=effective_required_roles,
        contracts=contracts,
    )

    role_contracts = {
        role: _role_contract(
            template=template,
            role=role,
            raw_contract=contracts[role],
            initial_roles=initial_roles,
            process_owners=process_owners,
            declared_process_types=declared_process_types,
        )
        for role in roles
    }
    role_components = _validate_template_component_contracts(
        registry=registry,
        template=template,
        compatibility=compatibility,
        contracts=role_contracts,
        process_components=process_components,
        process_role_keys=process_role_keys,
        process_templates=process_templates,
    )

    resolved: dict[str, ParameterRecord] = {}
    for role in roles:
        contract = role_contracts[role]
        record_id = record_ids[role]
        if not isinstance(record_id, str) or not record_id.strip():
            raise ExactTemplateParameterError(
                f"Case template role {role!r} requires a non-empty parameter record ID.",
                role=role,
            )
        record = registry.parameters.get(record_id)
        if record is None:
            raise ExactTemplateParameterError(
                f"Case template role {role!r} references missing parameter record {record_id!r}.",
                role=role,
            )
        _validate_record(
            registry=registry,
            compatibility=compatibility,
            role=role,
            record=record,
            contract=contract,
            expected_process_type=(
                str(contract["record_process_type"])
                if contract["kind"] == "initial_state"
                else role_components[role].compatibility.process_type
            ),
            mode=mode,
            environment_id=environment_id,
            value_requirement=value_requirement,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
        )
        resolved[role] = record
    return resolved


def _required_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExactTemplateParameterError(f"{label} must be a mapping.")
    if any(not isinstance(key, str) or not key.strip() for key in value):
        raise ExactTemplateParameterError(f"{label} keys must be non-empty strings.")
    return value


def _initial_parameter_roles(template: CaseTemplateRecord) -> frozenset[str]:
    roles: set[str] = set()
    for spec in template.initial_state_mapping.values():
        for field in ("parameter_role", "units_from_role"):
            value = spec.get(field)
            if isinstance(value, str) and value:
                roles.add(value)
    return frozenset(roles)


def _process_role_owners(
    template: CaseTemplateRecord,
    *,
    record_roles: frozenset[str],
) -> tuple[
    Mapping[str, str],
    frozenset[str],
    Mapping[str, Mapping[str, Any]],
    Mapping[str, str],
    tuple[Mapping[str, Any], ...],
]:
    raw_templates = template.process_state_metadata.get("process_templates")
    if not isinstance(raw_templates, Sequence) or isinstance(raw_templates, (str, bytes)):
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} process_templates must be a sequence."
        )
    owners: dict[str, str] = {}
    owner_components: dict[str, Mapping[str, Any]] = {}
    role_keys: dict[str, str] = {}
    process_templates: list[Mapping[str, Any]] = []
    process_ids: set[str] = set()
    declared = {template.process_type}
    for raw_template in raw_templates:
        if not isinstance(raw_template, Mapping):
            raise ExactTemplateParameterError(
                f"Case template {template.case_template_id!r} contains a malformed process template."
            )
        process_id = raw_template.get("id")
        if not isinstance(process_id, str) or not process_id.strip():
            raise ExactTemplateParameterError(
                f"Case template {template.case_template_id!r} contains a process template "
                "without a non-empty id."
            )
        if process_id in process_ids:
            raise ExactTemplateParameterError(
                f"Case template {template.case_template_id!r} declares process template "
                f"id {process_id!r} more than once."
            )
        if "component_selectors" in raw_template:
            raise ExactTemplateParameterError(
                f"Case template process {process_id!r} must derive component identity from "
                "component compatibility and state_species; component_selectors are unsupported."
            )
        process_ids.add(process_id)
        process_templates.append(raw_template)
        process_type = raw_template.get("process_type")
        if not isinstance(process_type, str) or not process_type.strip():
            raise ExactTemplateParameterError(
                f"Case template {template.case_template_id!r} contains a process template "
                "without a non-empty process_type."
            )
        declared.add(process_type)
        parameter_roles = raw_template.get("parameter_roles")
        if not isinstance(parameter_roles, Mapping):
            raise ExactTemplateParameterError(
                f"Case template {template.case_template_id!r} process {process_type!r} "
                "must define parameter_roles as a mapping."
            )
        referenced_roles = _direct_parameter_role_keys(
            template=template,
            process_id=process_id,
            process_type=process_type,
            parameter_roles=parameter_roles,
            record_roles=record_roles,
        )
        for role, semantic_key in _nested_parameter_role_keys(
            raw_template.get("modifiers"),
            record_roles=record_roles,
        ).items():
            existing_key = referenced_roles.get(role)
            if existing_key is not None and existing_key != semantic_key:
                raise ExactTemplateParameterError(
                    f"Case template {template.case_template_id!r} assigns parameter role "
                    f"{role!r} to conflicting component semantic keys.",
                    role=role,
                )
            referenced_roles[role] = semantic_key
        for role, semantic_key in referenced_roles.items():
            if role in owner_components:
                same_component = owner_components[role] is raw_template
                if same_component and role_keys[role] == semantic_key:
                    continue
                raise ExactTemplateParameterError(
                    f"Case template {template.case_template_id!r} assigns parameter role "
                    f"{role!r} to multiple component process types, components, or semantic keys.",
                    role=role,
                )
            owners[role] = process_type
            owner_components[role] = raw_template
            role_keys[role] = semantic_key
    return (
        owners,
        frozenset(declared),
        owner_components,
        role_keys,
        tuple(process_templates),
    )


def _direct_parameter_role_keys(
    *,
    template: CaseTemplateRecord,
    process_id: str,
    process_type: str,
    parameter_roles: Mapping[Any, Any],
    record_roles: frozenset[str],
) -> dict[str, str]:
    invalid = tuple(
        (field, role)
        for field, role in parameter_roles.items()
        if not isinstance(field, str)
        or not field.strip()
        or not isinstance(role, str)
        or not role.strip()
    )
    if invalid:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} process {process_id!r} "
            "parameter_roles requires nonblank text fields and roles."
        )
    role_values = tuple(parameter_roles.values())
    duplicate_roles = tuple(
        sorted({role for role in role_values if role_values.count(role) > 1})
    )
    if duplicate_roles:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} process {process_id!r} "
            "reuses explicit parameter roles across process fields: "
            f"{', '.join(duplicate_roles)}.",
            role=duplicate_roles[0],
        )
    unknown_roles = tuple(role for role in role_values if role not in record_roles)
    if unknown_roles:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} process {process_id!r} "
            "references parameter roles without explicit records: "
            f"{', '.join(unknown_roles)}.",
            role=unknown_roles[0],
        )
    required_fields = _DIRECT_PROCESS_PARAMETER_FIELDS.get(process_type, ())
    missing_fields = tuple(field for field in required_fields if field not in parameter_roles)
    unexpected_fields = tuple(field for field in parameter_roles if field not in required_fields)
    if required_fields and (missing_fields or unexpected_fields):
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} process {process_id!r} "
            f"must use the exact canonical {process_type!r} parameter fields; "
            f"missing={list(missing_fields)}, unexpected={list(unexpected_fields)}."
        )
    return {str(role): str(field) for field, role in parameter_roles.items()}


def _nested_parameter_role_keys(
    value: Any,
    *,
    record_roles: frozenset[str],
) -> Mapping[str, str]:
    roles: dict[str, str] = {}
    if isinstance(value, Mapping):
        modifier_type = value.get("type")
        for key, nested in value.items():
            if (
                isinstance(key, str)
                and key.endswith("_role")
                and isinstance(nested, str)
                and nested in record_roles
            ):
                semantic_key = _modifier_compatibility_role(
                    modifier_type=modifier_type,
                    field=key,
                    role=nested,
                )
                if not semantic_key:
                    raise ExactTemplateParameterError(
                        f"Nested parameter role {nested!r} has an empty semantic key.",
                        role=nested,
                    )
                existing = roles.get(nested)
                if existing is not None and existing != semantic_key:
                    raise ExactTemplateParameterError(
                        f"Nested parameter role {nested!r} has conflicting semantic keys.",
                        role=nested,
                    )
                roles[nested] = semantic_key
            for role, semantic_key in _nested_parameter_role_keys(
                nested,
                record_roles=record_roles,
            ).items():
                existing = roles.get(role)
                if existing is not None and existing != semantic_key:
                    raise ExactTemplateParameterError(
                        f"Nested parameter role {role!r} has conflicting semantic keys.",
                        role=role,
                    )
                roles[role] = semantic_key
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            for role, semantic_key in _nested_parameter_role_keys(
                nested,
                record_roles=record_roles,
            ).items():
                existing = roles.get(role)
                if existing is not None and existing != semantic_key:
                    raise ExactTemplateParameterError(
                        f"Nested parameter role {role!r} has conflicting semantic keys.",
                        role=role,
                    )
                roles[role] = semantic_key
    return roles


def _modifier_compatibility_role(
    *,
    modifier_type: Any,
    field: str,
    role: str,
) -> str:
    if isinstance(modifier_type, str) and modifier_type:
        fields = _MODIFIER_COMPATIBILITY_ROLE_BY_FIELD.get(modifier_type)
        if fields is None or field not in fields:
            raise ExactTemplateParameterError(
                f"Modifier type {modifier_type!r} has no exact semantic role for "
                f"field {field!r}.",
                role=role,
            )
        return fields[field]
    return field.removesuffix("_role")


def _validate_template_component_contracts(
    *,
    registry: FungModRegistry,
    template: CaseTemplateRecord,
    compatibility: ProcessCompatibilityRecord | None,
    contracts: Mapping[str, Mapping[str, Any]],
    process_components: Mapping[str, Mapping[str, Any]],
    process_role_keys: Mapping[str, str],
    process_templates: Sequence[Mapping[str, Any]],
) -> Mapping[str, _ResolvedProcessComponent]:
    (
        enzyme_targets,
        declared_substrates,
        enzyme_entities,
        substrate_entities,
    ) = _declared_template_components(template)
    for role, contract in contracts.items():
        enzyme_class = contract["enzyme_class"]
        substrate_class = contract["substrate_class"]
        if enzyme_class is not None and enzyme_class not in enzyme_targets:
            raise ExactTemplateParameterError(
                f"Template role {role!r} enzyme_class {enzyme_class!r} is not an exact "
                "declared template enzyme component.",
                role=role,
            )
        if substrate_class is not None and substrate_class not in declared_substrates:
            raise ExactTemplateParameterError(
                f"Template role {role!r} substrate_class {substrate_class!r} is not an exact "
                "declared template substrate component.",
                role=role,
            )
        if (
            enzyme_class is not None
            and substrate_class is not None
            and substrate_class not in enzyme_targets[enzyme_class]
        ):
            raise ExactTemplateParameterError(
                f"Template role {role!r} component enzyme_class {enzyme_class!r} does not "
                f"declare substrate_class {substrate_class!r} as a target.",
                role=role,
            )

    state_components = _state_species_components(
        registry=registry,
        template=template,
        enzyme_entities=enzyme_entities,
        substrate_entities=substrate_entities,
    )
    compatibility_by_process = _bound_component_compatibilities(
        registry=registry,
        template=template,
        compatibility=compatibility,
    )
    resolved_by_process: dict[str, _ResolvedProcessComponent] = {}
    for process in process_templates:
        process_id = str(process["id"])
        resolved_by_process[process_id] = _resolve_process_component(
            registry=registry,
            template=template,
            outer_compatibility=compatibility,
            component=process,
            compatibility=compatibility_by_process[process_id],
            state_components=state_components,
            enzyme_targets=enzyme_targets,
            declared_substrates=declared_substrates,
        )

    role_components: dict[str, _ResolvedProcessComponent] = {}
    for role, component in process_components.items():
        process_id = str(component["id"])
        resolved = resolved_by_process[process_id]
        _require_component_assertions(
            role=role,
            contract=contracts[role],
            resolved=resolved,
            expected_compatibility_role=process_role_keys[role],
        )
        role_components[role] = resolved

    for process in process_templates:
        process_id = str(process["id"])
        resolved = resolved_by_process[process_id]
        state_roles = _required_mapping(
            process.get("state_roles"),
            label=f"Component process {process_id!r} state_roles",
        )
        catalyst_field = next(
            (field for field in ("catalyst", "enzyme") if field in state_roles),
            None,
        )
        _require_initial_state_binding(
            template=template,
            contracts=contracts,
            state_role=state_roles.get(catalyst_field) if catalyst_field else None,
            process_field=catalyst_field,
            resolved=resolved,
            selectors=("enzyme_class", "substrate_class"),
        )
        _require_initial_state_binding(
            template=template,
            contracts=contracts,
            state_role=state_roles.get("substrate"),
            process_field="substrate",
            resolved=resolved,
            selectors=("substrate_class",),
        )
    return role_components


def _declared_template_components(
    template: CaseTemplateRecord,
) -> tuple[
    Mapping[str, frozenset[str]],
    frozenset[str],
    Mapping[str, str],
    Mapping[str, str],
]:
    entities = _required_mapping(
        template.process_state_metadata.get("entities"),
        label=f"Case template {template.case_template_id!r} entities",
    )
    raw_enzymes = entities.get("enzymes")
    raw_substrates = entities.get("substrates")
    if not isinstance(raw_enzymes, Sequence) or isinstance(raw_enzymes, (str, bytes)):
        raise ExactTemplateParameterError("Exact template entities.enzymes must be a sequence.")
    if not isinstance(raw_substrates, Sequence) or isinstance(raw_substrates, (str, bytes)):
        raise ExactTemplateParameterError("Exact template entities.substrates must be a sequence.")

    enzyme_targets: dict[str, frozenset[str]] = {}
    enzyme_entities: dict[str, str] = {}
    substrate_entities: dict[str, str] = {}
    declared_substrates: set[str] = set()
    for raw_enzyme in raw_enzymes:
        enzyme = _required_mapping(raw_enzyme, label="Exact template enzyme component")
        data = _required_mapping(enzyme.get("data"), label="Exact template enzyme component data")
        entity_id = enzyme.get("id")
        enzyme_class = data.get("enzyme_class")
        targets = data.get("target_substrate_classes")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ExactTemplateParameterError(
                "Exact template enzyme components require a non-empty entity id."
            )
        if not isinstance(enzyme_class, str) or not enzyme_class.strip():
            raise ExactTemplateParameterError(
                "Exact template enzyme components require a non-empty enzyme_class."
            )
        if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
            raise ExactTemplateParameterError(
                f"Exact template enzyme component {enzyme_class!r} requires "
                "target_substrate_classes."
            )
        target_values = tuple(targets)
        if any(not isinstance(value, str) or not value.strip() for value in target_values):
            raise ExactTemplateParameterError(
                f"Exact template enzyme component {enzyme_class!r} has invalid target classes."
            )
        target_classes = frozenset(target_values)
        if enzyme_class in enzyme_targets:
            raise ExactTemplateParameterError(
                f"Exact template declares enzyme_class {enzyme_class!r} more than once."
            )
        if entity_id in enzyme_entities:
            raise ExactTemplateParameterError(
                f"Exact template declares enzyme entity id {entity_id!r} more than once."
            )
        enzyme_targets[enzyme_class] = target_classes
        enzyme_entities[entity_id] = enzyme_class
        declared_substrates.update(target_classes)
    for raw_substrate in raw_substrates:
        substrate = _required_mapping(raw_substrate, label="Exact template substrate component")
        data = _required_mapping(substrate.get("data"), label="Exact template substrate component data")
        entity_id = substrate.get("id")
        substrate_class = data.get("chemical_class")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ExactTemplateParameterError(
                "Exact template substrate components require a non-empty entity id."
            )
        if not isinstance(substrate_class, str) or not substrate_class.strip():
            raise ExactTemplateParameterError(
                "Exact template substrate components require a non-empty chemical_class."
            )
        if entity_id in substrate_entities:
            raise ExactTemplateParameterError(
                f"Exact template declares substrate entity id {entity_id!r} more than once."
            )
        substrate_entities[entity_id] = substrate_class
        declared_substrates.add(substrate_class)
    return (
        enzyme_targets,
        frozenset(declared_substrates),
        enzyme_entities,
        substrate_entities,
    )


def _state_species_components(
    *,
    registry: FungModRegistry,
    template: CaseTemplateRecord,
    enzyme_entities: Mapping[str, str],
    substrate_entities: Mapping[str, str],
) -> Mapping[str, _StateComponent]:
    raw_bindings = _required_mapping(
        template.process_state_metadata.get("state_species"),
        label=f"Case template {template.case_template_id!r} state_species",
    )
    declared_states = frozenset(template.state_roles.values())
    resolved: dict[str, _StateComponent] = {}
    identities: set[tuple[str, str]] = set()
    outer_substrate_state = template.state_roles.get("substrate")
    if not isinstance(outer_substrate_state, str) or not outer_substrate_state.strip():
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} requires one exact outer "
            "substrate state role."
        )
    if len(substrate_entities) != 1:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} explicit component resolution "
            "requires exactly one configured outer substrate entity."
        )
    configured_substrate_id = next(iter(substrate_entities))
    for entity_id, substrate_class in substrate_entities.items():
        substrate = registry.substrates.get(entity_id)
        if substrate is None:
            raise ExactTemplateParameterError(
                f"Case template declares missing registry substrate entity {entity_id!r}."
            )
        if substrate.substrate_class != substrate_class:
            raise ExactTemplateParameterError(
                f"Case template substrate entity {entity_id!r} chemical_class "
                f"{substrate_class!r} disagrees with registry class "
                f"{substrate.substrate_class!r}."
            )
    for state_name, raw_binding in raw_bindings.items():
        if state_name not in declared_states:
            raise ExactTemplateParameterError(
                f"Case template state_species references undeclared state {state_name!r}."
            )
        binding = _required_mapping(
            raw_binding,
            label=f"Case template state_species.{state_name}",
        )
        if set(binding) != {"species", "entity_type"}:
            raise ExactTemplateParameterError(
                f"Case template state_species.{state_name} must contain exactly "
                "species and entity_type."
            )
        species = binding["species"]
        entity_type = binding["entity_type"]
        if not isinstance(species, str) or not species.strip():
            raise ExactTemplateParameterError(
                f"Case template state_species.{state_name}.species must be nonblank text."
            )
        if entity_type not in {"enzyme", "substrate"}:
            raise ExactTemplateParameterError(
                f"Case template state_species.{state_name}.entity_type must be "
                "'enzyme' or 'substrate'."
            )
        identity = (entity_type, species)
        if identity in identities:
            raise ExactTemplateParameterError(
                f"Case template state_species reuses {entity_type} identity {species!r} "
                "for multiple state slots."
            )
        identities.add(identity)
        if entity_type == "enzyme":
            enzyme_class = enzyme_entities.get(species)
            if enzyme_class is None:
                raise ExactTemplateParameterError(
                    f"Case template state {state_name!r} references undeclared enzyme "
                    f"entity {species!r}."
                )
            if enzyme_class not in registry.enzyme_classes:
                raise ExactTemplateParameterError(
                    f"Case template enzyme entity {species!r} resolves to missing registry "
                    f"enzyme class {enzyme_class!r}."
                )
            component_class = enzyme_class
        else:
            substrate = registry.substrates.get(species)
            if substrate is None:
                raise ExactTemplateParameterError(
                    f"Case template state {state_name!r} references missing registry "
                    f"substrate {species!r}."
                )
            component_class = substrate.substrate_class
            declared_class = substrate_entities.get(species)
            if declared_class is not None and declared_class != component_class:
                raise ExactTemplateParameterError(
                    f"Case template state {state_name!r} substrate identity {species!r} "
                    "disagrees with its configured entity class."
                )
        resolved[state_name] = _StateComponent(
            entity_type=entity_type,
            entity_id=species,
            component_class=component_class,
        )
    outer_component = resolved.get(outer_substrate_state)
    if (
        outer_component is None
        or outer_component.entity_type != "substrate"
        or outer_component.entity_id != configured_substrate_id
    ):
        raise ExactTemplateParameterError(
            f"Configured substrate identity {configured_substrate_id!r} must be the exact "
            f"substrate consumed by outer state {outer_substrate_state!r}."
        )
    return resolved


def _bound_component_compatibilities(
    *,
    registry: FungModRegistry,
    template: CaseTemplateRecord,
    compatibility: ProcessCompatibilityRecord | None,
) -> Mapping[str, ProcessCompatibilityRecord]:
    if compatibility is None:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} requires one outer process "
            "compatibility with ordered component_bindings."
        )
    registered = registry.process_compatibility.get(compatibility.record_id)
    if registered != compatibility:
        raise ExactTemplateParameterError(
            f"Compatibility {compatibility.record_id!r} disagrees with the active registry."
        )
    try:
        return registry.get_process_component_authorities(
            compatibility.record_id,
            template=template,
        )
    except (RegistryValidationError, KeyError) as exc:
        raise ExactTemplateParameterError(
            f"Compatibility {compatibility.record_id!r} component authority graph is invalid: {exc}"
        ) from exc


def _resolve_process_component(
    *,
    registry: FungModRegistry,
    template: CaseTemplateRecord,
    outer_compatibility: ProcessCompatibilityRecord | None,
    component: Mapping[str, Any],
    compatibility: ProcessCompatibilityRecord,
    state_components: Mapping[str, _StateComponent],
    enzyme_targets: Mapping[str, frozenset[str]],
    declared_substrates: frozenset[str],
) -> _ResolvedProcessComponent:
    process_id = str(component["id"])
    state_roles = _required_mapping(
        component.get("state_roles"),
        label=f"Component process {process_id!r} state_roles",
    )
    catalyst_fields = tuple(field for field in ("catalyst", "enzyme") if field in state_roles)
    if len(catalyst_fields) != 1:
        raise ExactTemplateParameterError(
            f"Component process {process_id!r} must declare exactly one catalyst or enzyme state role."
        )
    enzyme = _state_component_for_process_field(
        template=template,
        state_components=state_components,
        process_id=process_id,
        process_field=catalyst_fields[0],
        state_role=state_roles[catalyst_fields[0]],
        expected_entity_type="enzyme",
    )
    substrate = _state_component_for_process_field(
        template=template,
        state_components=state_components,
        process_id=process_id,
        process_field="substrate",
        state_role=state_roles.get("substrate"),
        expected_entity_type="substrate",
    )
    if (
        compatibility.enzyme_class != enzyme.component_class
        or compatibility.substrate_class != substrate.component_class
    ):
        raise ExactTemplateParameterError(
            f"Process template {process_id!r} state identities require component pair "
            f"{enzyme.component_class!r}/{substrate.component_class!r}, but compatibility "
            f"{compatibility.record_id!r} declares {compatibility.enzyme_class!r}/"
            f"{compatibility.substrate_class!r}."
        )
    if (
        enzyme.component_class not in enzyme_targets
        or substrate.component_class not in declared_substrates
        or substrate.component_class not in enzyme_targets[enzyme.component_class]
    ):
        raise ExactTemplateParameterError(
            f"Process template {process_id!r} state identity pair is not an exact declared "
            "template enzyme/substrate target pair."
        )
    capability = registry.enzyme_classes[enzyme.component_class]
    if substrate.component_class not in capability.compatible_substrate_classes:
        raise ExactTemplateParameterError(
            f"Registry enzyme class {enzyme.component_class!r} does not authorize substrate "
            f"class {substrate.component_class!r}."
        )
    if compatibility.process_type not in capability.compatible_processes:
        raise ExactTemplateParameterError(
            f"Registry enzyme class {enzyme.component_class!r} does not authorize process "
            f"type {compatibility.process_type!r}."
        )
    substrate_record = registry.substrates[substrate.entity_id]
    required_bonds = frozenset(compatibility.required_bond_classes)
    if not required_bonds.issubset(capability.target_bond_classes) or not required_bonds.issubset(
        substrate_record.bond_classes
    ):
        raise ExactTemplateParameterError(
            f"Component compatibility {compatibility.record_id!r} bond requirements do not "
            "resolve through the bound enzyme/substrate registry capabilities."
        )
    if outer_compatibility is not None and state_roles.get("substrate") == "substrate":
        if (
            enzyme.component_class != outer_compatibility.enzyme_class
            or substrate.component_class != outer_compatibility.substrate_class
        ):
            raise ExactTemplateParameterError(
                f"Outer process component {process_id!r} disagrees with compatibility "
                f"{outer_compatibility.record_id!r}."
            )
    return _ResolvedProcessComponent(
        compatibility=compatibility,
        enzyme=enzyme,
        substrate=substrate,
    )


def _state_component_for_process_field(
    *,
    template: CaseTemplateRecord,
    state_components: Mapping[str, _StateComponent],
    process_id: str,
    process_field: str,
    state_role: Any,
    expected_entity_type: str,
) -> _StateComponent:
    if not isinstance(state_role, str) or state_role not in template.state_roles:
        raise ExactTemplateParameterError(
            f"Component process {process_id!r} field {process_field!r} must reference an "
            "exact template state role."
        )
    state_name = template.state_roles[state_role]
    component = state_components.get(state_name)
    if component is None:
        raise ExactTemplateParameterError(
            f"Component process {process_id!r} state {state_name!r} lacks a canonical "
            "state_species identity."
        )
    if component.entity_type != expected_entity_type:
        article = "an" if expected_entity_type == "enzyme" else "a"
        raise ExactTemplateParameterError(
            f"Component process {process_id!r} field {process_field!r} requires {article} "
            f"{expected_entity_type} state identity, not {component.entity_type!r}."
        )
    return component


def _require_component_assertions(
    *,
    role: str,
    contract: Mapping[str, Any],
    resolved: _ResolvedProcessComponent,
    expected_compatibility_role: str,
) -> None:
    expected = {
        "enzyme_class": resolved.enzyme.component_class,
        "substrate_class": resolved.substrate.component_class,
    }
    for selector, value in expected.items():
        if contract[selector] != value:
            raise ExactTemplateParameterError(
                f"Template role {role!r} assertion {selector}={contract[selector]!r} "
                f"disagrees with bound component value {value!r}.",
                role=role,
            )
    _require_substrate_identity_assertion(
        role=role,
        contract=contract,
        resolved=resolved,
        label="Template role",
    )
    symbol = contract["parameter_symbol"]
    compatibility_symbols = tuple(resolved.compatibility.parameter_roles.values())
    if (
        resolved.compatibility.parameter_roles.get(expected_compatibility_role)
        != symbol
        or compatibility_symbols.count(symbol) != 1
    ):
        raise ExactTemplateParameterError(
            f"Template role {role!r} symbol {symbol!r} must be bound by exact component "
            f"compatibility role {expected_compatibility_role!r} on "
            f"{resolved.compatibility.record_id!r}.",
            role=role,
        )


def _require_initial_state_binding(
    *,
    template: CaseTemplateRecord,
    contracts: Mapping[str, Mapping[str, Any]],
    state_role: Any,
    process_field: str | None,
    resolved: _ResolvedProcessComponent,
    selectors: Sequence[str],
) -> None:
    if not isinstance(state_role, str):
        return
    initial_spec = template.initial_state_mapping.get(state_role)
    if not isinstance(initial_spec, Mapping):
        return
    initial_role = initial_spec.get("parameter_role")
    if not isinstance(initial_role, str) or initial_role not in contracts:
        return
    contract = contracts[initial_role]
    expected = {
        "enzyme_class": resolved.enzyme.component_class,
        "substrate_class": resolved.substrate.component_class,
    }
    for selector in selectors:
        if contract[selector] != expected[selector]:
            raise ExactTemplateParameterError(
                f"Initial-state role {initial_role!r} assertion {selector}="
                f"{contract[selector]!r} disagrees with bound component value "
                f"{expected[selector]!r}.",
                role=initial_role,
            )
    _require_substrate_identity_assertion(
        role=initial_role,
        contract=contract,
        resolved=resolved,
        label="Initial-state role",
    )
    symbol = contract["parameter_symbol"]
    expected_compatibility_role = (
        _INITIAL_STATE_COMPATIBILITY_ROLE_BY_PROCESS_FIELD.get(process_field)
        if process_field is not None
        else None
    )
    if expected_compatibility_role is None:
        raise ExactTemplateParameterError(
            f"Initial-state role {initial_role!r} has no semantic component role for "
            f"process field {process_field!r}.",
            role=initial_role,
        )
    if (
        resolved.compatibility.parameter_roles.get(expected_compatibility_role)
        != symbol
        or tuple(resolved.compatibility.parameter_roles.values()).count(symbol) != 1
    ):
        raise ExactTemplateParameterError(
            f"Initial-state role {initial_role!r} symbol {symbol!r} must be bound by exact "
            f"component compatibility role {expected_compatibility_role!r} on "
            f"{resolved.compatibility.record_id!r}.",
            role=initial_role,
        )
    if contract["record_process_type"] not in {
        template.process_type,
        resolved.compatibility.process_type,
    }:
        raise ExactTemplateParameterError(
            f"Initial-state role {initial_role!r} record_process_type must be the outer "
            "template or its bound component process type.",
            role=initial_role,
        )


def _require_substrate_identity_assertion(
    *,
    role: str,
    contract: Mapping[str, Any],
    resolved: _ResolvedProcessComponent,
    label: str,
) -> None:
    substrate_id = contract["substrate_id"]
    if substrate_id is not None and substrate_id != resolved.substrate.entity_id:
        raise ExactTemplateParameterError(
            f"{label} {role!r} substrate_id {substrate_id!r} disagrees with consumed "
            f"component identity {resolved.substrate.entity_id!r}.",
            role=role,
        )


def _role_contract(
    *,
    template: CaseTemplateRecord,
    role: str,
    raw_contract: Any,
    initial_roles: frozenset[str],
    process_owners: Mapping[str, str],
    declared_process_types: frozenset[str],
) -> Mapping[str, Any]:
    contract = _required_mapping(
        raw_contract,
        label=f"Case template {template.case_template_id!r} contract for role {role!r}",
    )
    kind = contract.get("kind")
    expected_fields = _INITIAL_CONTRACT_FIELDS if kind == "initial_state" else _BASE_CONTRACT_FIELDS
    if set(contract) != expected_fields:
        raise ExactTemplateParameterError(
            f"Case template role {role!r} must use the exact {kind!r} parameter contract fields.",
            role=role,
        )
    if kind == "initial_state":
        if role not in initial_roles or role in process_owners:
            raise ExactTemplateParameterError(
                f"Case template role {role!r} is not an unambiguous initial-state parameter role.",
                role=role,
            )
        process_type = contract.get("record_process_type")
        if not isinstance(process_type, str) or process_type not in declared_process_types:
            raise ExactTemplateParameterError(
                f"Initial-state role {role!r} record_process_type must be the outer template "
                "process_type or one declared component process_type.",
                role=role,
            )
    elif kind == "process_parameter":
        if role not in process_owners or role in initial_roles:
            raise ExactTemplateParameterError(
                f"Case template role {role!r} is not owned by exactly one component process.",
                role=role,
            )
    else:
        raise ExactTemplateParameterError(
            f"Case template role {role!r} kind must be 'initial_state' or 'process_parameter'.",
            role=role,
        )
    symbol = contract.get("parameter_symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ExactTemplateParameterError(
            f"Case template role {role!r} requires a non-empty parameter_symbol.",
            role=role,
        )
    for field in _SELECTOR_FIELDS:
        value = contract.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ExactTemplateParameterError(
                f"Case template role {role!r} selector {field!r} must be an explicit string or null.",
                role=role,
            )
    return contract


def _validate_compatibility_contract(
    *,
    template: CaseTemplateRecord,
    compatibility: ProcessCompatibilityRecord | None,
    record_roles: frozenset[str],
    required_roles: Sequence[str],
    contracts: Mapping[str, Any],
) -> None:
    if compatibility is None:
        return
    if compatibility.case_template_id != template.case_template_id:
        raise ExactTemplateParameterError(
            f"Compatibility {compatibility.record_id!r} does not reference template "
            f"{template.case_template_id!r}."
        )
    if compatibility.process_type != template.process_type:
        raise ExactTemplateParameterError(
            f"Compatibility {compatibility.record_id!r} and template "
            f"{template.case_template_id!r} disagree on process_type."
        )
    missing = tuple(role for role in required_roles if role not in compatibility.parameter_roles)
    if missing:
        raise ExactTemplateParameterError(
            f"Compatibility {compatibility.record_id!r} is missing parameter role mappings "
            f"for: {', '.join(missing)}.",
            role=missing[0],
        )
    for role, symbol in compatibility.parameter_roles.items():
        if role not in record_roles:
            raise ExactTemplateParameterError(
                f"Compatibility role {role!r} has no explicit template parameter record.",
                role=role,
            )
        contract = contracts[role]
        if not isinstance(contract, Mapping) or contract.get("parameter_symbol") != symbol:
            raise ExactTemplateParameterError(
                f"Compatibility role {role!r} symbol {symbol!r} disagrees with the exact "
                "template role contract.",
                role=role,
            )
    uncovered = tuple(
        symbol
        for symbol in compatibility.required_parameters
        if symbol not in compatibility.parameter_roles.values()
    )
    if uncovered:
        raise ExactTemplateParameterError(
            f"Compatibility {compatibility.record_id!r} required parameters lack explicit roles: "
            f"{', '.join(uncovered)}."
        )


def _validate_record(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord | None,
    role: str,
    record: ParameterRecord,
    contract: Mapping[str, Any],
    expected_process_type: str,
    mode: ParameterRecordSelectionMode,
    environment_id: str | None,
    value_requirement: ParameterValueRequirement,
    fungus_id: str | None,
    substrate_id: str | None,
) -> None:
    if record.parameter_symbol != contract["parameter_symbol"]:
        raise ExactTemplateParameterError(
            f"Template role {role!r} expected symbol {contract['parameter_symbol']!r}, but "
            f"record {record.record_id!r} uses {record.parameter_symbol!r}.",
            role=role,
        )
    if record.process_type != expected_process_type:
        raise ExactTemplateParameterError(
            f"Template role {role!r} requires record process_type {expected_process_type!r}, "
            f"but record {record.record_id!r} uses {record.process_type!r}.",
            role=role,
        )
    for field in _SELECTOR_FIELDS:
        actual = getattr(record, field)
        expected = contract[field]
        if actual != expected:
            raise ExactTemplateParameterError(
                f"Template role {role!r} requires selector {field}={expected!r}, but "
                f"record {record.record_id!r} uses {actual!r}.",
                role=role,
            )
    _validate_component_identity(
        registry=registry,
        role=role,
        contract=contract,
    )
    if compatibility is not None:
        if contract["enzyme_class"] == compatibility.enzyme_class:
            _require_outer_selector(role, "fungus_id", contract["fungus_id"], fungus_id)
        if contract["substrate_class"] == compatibility.substrate_class:
            _require_outer_selector(role, "substrate_id", contract["substrate_id"], substrate_id)
    if environment_id is not None and contract["environment_id"] not in {None, environment_id}:
        raise ExactTemplateParameterError(
            f"Template role {role!r} is scoped to environment {contract['environment_id']!r}, "
            f"not requested environment {environment_id!r}.",
            role=role,
        )
    blocker = parameter_record_mode_eligibility_blocker(record, mode=mode)
    if blocker is not None:
        raise ExactTemplateParameterError(
            f"Template role {role!r} record {record.record_id!r} is ineligible: {blocker}",
            role=role,
        )
    validation = record.value.validate(nonnegative=True)
    if not validation.passed:
        raise ExactTemplateParameterError(
            f"Template role {role!r} record {record.record_id!r} failed nonnegative "
            f"ValueSpec validation: {validation.to_dict()}.",
            role=role,
        )
    if value_requirement == "exact" and not record.value.is_exact:
        raise ExactTemplateParameterError(
            f"Template role {role!r} requires an exact ValueSpec, but record "
            f"{record.record_id!r} uses {record.value.kind!r}.",
            role=role,
        )
    if value_requirement == "sampleable" and not (
        record.value.is_exact or record.value.is_uncertain
    ):
        raise ExactTemplateParameterError(
            f"Template role {role!r} requires an exact or sampleable uncertain ValueSpec, "
            f"but record {record.record_id!r} uses {record.value.kind!r}.",
            role=role,
        )


def _validate_component_identity(
    *,
    registry: FungModRegistry,
    role: str,
    contract: Mapping[str, Any],
) -> None:
    enzyme_class = contract["enzyme_class"]
    substrate_class = contract["substrate_class"]
    if enzyme_class is None and substrate_class is None:
        raise ExactTemplateParameterError(
            f"Template role {role!r} must declare at least one exact component class selector.",
            role=role,
        )
    fungus_id = contract["fungus_id"]
    if fungus_id is not None:
        fungus = registry.fungi.get(fungus_id)
        if (
            fungus is None
            or enzyme_class is None
            or enzyme_class not in fungus.enzyme_classes
        ):
            raise ExactTemplateParameterError(
                f"Template role {role!r} fungus_id {fungus_id!r} does not resolve "
                f"compatibly with enzyme_class {enzyme_class!r}.",
                role=role,
            )
    substrate_id = contract["substrate_id"]
    if substrate_id is not None:
        substrate = registry.substrates.get(substrate_id)
        if substrate is None or substrate.substrate_class != substrate_class:
            raise ExactTemplateParameterError(
                f"Template role {role!r} substrate_id {substrate_id!r} does not resolve "
                f"compatibly with substrate_class {substrate_class!r}.",
                role=role,
            )
def _require_outer_selector(
    role: str,
    field: str,
    configured: str | None,
    requested: str | None,
) -> None:
    if requested is not None and configured not in {None, requested}:
        raise ExactTemplateParameterError(
            f"Template role {role!r} outer {field} {configured!r} does not match "
            f"requested {field} {requested!r}.",
            role=role,
        )


__all__ = [
    "ExactTemplateParameterError",
    "ParameterValueRequirement",
    "exact_template_compatibility",
    "resolve_exact_template_parameter_records",
]
