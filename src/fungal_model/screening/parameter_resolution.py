"""Shared parameter admission and exact case-template role resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from fungal_model.registry.records import (
    CaseTemplateRecord,
    ParameterRecord,
    ParameterRecordSelectionMode,
    ProcessCompatibilityRecord,
    parameter_record_mode_eligibility_blocker,
)
from fungal_model.registry.store import FungModRegistry

ParameterValueRequirement = Literal["exact", "sampleable"]

_SELECTOR_FIELDS = (
    "enzyme_class",
    "substrate_class",
    "fungus_id",
    "substrate_id",
    "environment_id",
)
_COMPONENT_SELECTOR_FIELDS = ("enzyme_class", "substrate_class")
_BASE_CONTRACT_FIELDS = frozenset(
    {"kind", "parameter_symbol", *_SELECTOR_FIELDS}
)
_INITIAL_CONTRACT_FIELDS = _BASE_CONTRACT_FIELDS | {"record_process_type"}


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
    if set(contracts) != set(record_ids):
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} parameter_role_contracts must "
            "have exactly the same role keys as parameter_record_ids."
        )
    missing_roles = tuple(role for role in required_roles if role not in record_ids)
    if missing_roles:
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} is missing explicit parameter "
            f"record IDs for: {', '.join(missing_roles)}.",
            role=missing_roles[0],
        )

    initial_roles = _initial_parameter_roles(template)
    process_owners, declared_process_types, process_components = _process_role_owners(
        template,
        record_roles=frozenset(roles),
    )
    _validate_compatibility_contract(
        template=template,
        compatibility=compatibility,
        record_roles=frozenset(roles),
        required_roles=required_roles,
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
    _validate_template_component_contracts(
        template=template,
        compatibility=compatibility,
        contracts=role_contracts,
        process_components=process_components,
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
                else process_owners[role]
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
) -> tuple[Mapping[str, str], frozenset[str], Mapping[str, Mapping[str, Any]]]:
    raw_templates = template.process_state_metadata.get("process_templates")
    if not isinstance(raw_templates, Sequence) or isinstance(raw_templates, (str, bytes)):
        raise ExactTemplateParameterError(
            f"Case template {template.case_template_id!r} process_templates must be a sequence."
        )
    owners: dict[str, str] = {}
    owner_components: dict[str, Mapping[str, Any]] = {}
    declared = {template.process_type}
    for raw_template in raw_templates:
        if not isinstance(raw_template, Mapping):
            raise ExactTemplateParameterError(
                f"Case template {template.case_template_id!r} contains a malformed process template."
            )
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
        referenced_roles = {
            value
            for value in parameter_roles.values()
            if isinstance(value, str) and value in record_roles
        }
        referenced_roles.update(
            _nested_parameter_roles(raw_template.get("modifiers"), record_roles=record_roles)
        )
        for role in referenced_roles:
            if role in owner_components:
                raise ExactTemplateParameterError(
                    f"Case template {template.case_template_id!r} assigns parameter role "
                    f"{role!r} to multiple component process types or components.",
                    role=role,
                )
            owners[role] = process_type
            owner_components[role] = raw_template
    return owners, frozenset(declared), owner_components


def _nested_parameter_roles(value: Any, *, record_roles: frozenset[str]) -> set[str]:
    roles: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if (
                isinstance(key, str)
                and key.endswith("_role")
                and isinstance(nested, str)
                and nested in record_roles
            ):
                roles.add(nested)
            roles.update(_nested_parameter_roles(nested, record_roles=record_roles))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            roles.update(_nested_parameter_roles(nested, record_roles=record_roles))
    return roles


def _validate_template_component_contracts(
    *,
    template: CaseTemplateRecord,
    compatibility: ProcessCompatibilityRecord | None,
    contracts: Mapping[str, Mapping[str, Any]],
    process_components: Mapping[str, Mapping[str, Any]],
) -> None:
    enzyme_targets, declared_substrates = _declared_template_components(template)
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

    for role, component in process_components.items():
        component_selectors = _component_selectors(component, role=role)
        _validate_declared_component_pair(
            role=role,
            selectors=component_selectors,
            enzyme_targets=enzyme_targets,
            declared_substrates=declared_substrates,
        )
        _require_exact_component_selectors(
            role=role,
            actual=contracts[role],
            expected=component_selectors,
            context="owning process",
            selectors=_COMPONENT_SELECTOR_FIELDS,
        )
        state_roles = _required_mapping(
            component.get("state_roles"),
            label=f"Component process for template role {role!r} state_roles",
        )
        _require_initial_slot_selectors(
            template=template,
            contracts=contracts,
            process_role=role,
            state_role=state_roles.get("catalyst") or state_roles.get("enzyme"),
            component_selectors=component_selectors,
            selectors=_COMPONENT_SELECTOR_FIELDS,
        )
        _require_initial_slot_selectors(
            template=template,
            contracts=contracts,
            process_role=role,
            state_role=state_roles.get("substrate"),
            component_selectors=component_selectors,
            selectors=("substrate_class",),
        )
        if compatibility is not None and state_roles.get("substrate") == "substrate":
            expected_outer = {
                "enzyme_class": compatibility.enzyme_class,
                "substrate_class": compatibility.substrate_class,
            }
            for selector, expected in expected_outer.items():
                if component_selectors[selector] != expected:
                    raise ExactTemplateParameterError(
                        f"Template role {role!r} is owned by the outer-substrate component "
                        f"and requires {selector}={expected!r}, not "
                        f"{component_selectors[selector]!r}.",
                        role=role,
                    )


def _declared_template_components(
    template: CaseTemplateRecord,
) -> tuple[Mapping[str, frozenset[str]], frozenset[str]]:
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
    declared_substrates: set[str] = set()
    for raw_enzyme in raw_enzymes:
        enzyme = _required_mapping(raw_enzyme, label="Exact template enzyme component")
        data = _required_mapping(enzyme.get("data"), label="Exact template enzyme component data")
        enzyme_class = data.get("enzyme_class")
        targets = data.get("target_substrate_classes")
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
        enzyme_targets[enzyme_class] = target_classes
        declared_substrates.update(target_classes)
    for raw_substrate in raw_substrates:
        substrate = _required_mapping(raw_substrate, label="Exact template substrate component")
        data = _required_mapping(substrate.get("data"), label="Exact template substrate component data")
        substrate_class = data.get("chemical_class")
        if not isinstance(substrate_class, str) or not substrate_class.strip():
            raise ExactTemplateParameterError(
                "Exact template substrate components require a non-empty chemical_class."
            )
        declared_substrates.add(substrate_class)
    return enzyme_targets, frozenset(declared_substrates)


def _component_selectors(
    component: Mapping[str, Any],
    *,
    role: str,
) -> Mapping[str, str]:
    selectors = _required_mapping(
        component.get("component_selectors"),
        label=f"Component process for template role {role!r} component_selectors",
    )
    if set(selectors) != set(_COMPONENT_SELECTOR_FIELDS):
        raise ExactTemplateParameterError(
            f"Component process for template role {role!r} component_selectors must "
            "declare exact enzyme_class and substrate_class keys.",
            role=role,
        )
    if any(
        not isinstance(selectors[field], str) or not selectors[field].strip()
        for field in _COMPONENT_SELECTOR_FIELDS
    ):
        raise ExactTemplateParameterError(
            f"Component process for template role {role!r} component_selectors values "
            "must be non-empty strings.",
            role=role,
        )
    return cast(Mapping[str, str], selectors)


def _validate_declared_component_pair(
    *,
    role: str,
    selectors: Mapping[str, str],
    enzyme_targets: Mapping[str, frozenset[str]],
    declared_substrates: frozenset[str],
) -> None:
    enzyme_class = selectors["enzyme_class"]
    substrate_class = selectors["substrate_class"]
    if (
        enzyme_class not in enzyme_targets
        or substrate_class not in declared_substrates
        or substrate_class not in enzyme_targets[enzyme_class]
    ):
        raise ExactTemplateParameterError(
            f"Template role {role!r} component selector pair enzyme_class="
            f"{enzyme_class!r}, substrate_class={substrate_class!r} is not an exact "
            "declared template component pair.",
            role=role,
        )


def _require_exact_component_selectors(
    *,
    role: str,
    actual: Mapping[str, Any],
    expected: Mapping[str, str],
    context: str,
    selectors: Sequence[str],
) -> None:
    for selector in selectors:
        if actual[selector] != expected[selector]:
            raise ExactTemplateParameterError(
                f"Template role {role!r} {selector}={actual[selector]!r} disagrees "
                f"with its {context} component selector {expected[selector]!r}.",
                role=role,
            )


def _require_initial_slot_selectors(
    *,
    template: CaseTemplateRecord,
    contracts: Mapping[str, Mapping[str, Any]],
    process_role: str,
    state_role: Any,
    component_selectors: Mapping[str, str],
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
    _require_exact_component_selectors(
        role=initial_role,
        actual=contracts[initial_role],
        expected=component_selectors,
        context=f"process role {process_role!r}",
        selectors=selectors,
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
