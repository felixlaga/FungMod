"""Build runnable deterministic model configs from modelable registry cases."""

from __future__ import annotations

from fungal_model.screening.adsorption import adsorption_registry_assembler

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Literal

from fungal_model.core.units import Q_
from fungal_model.io.model_config import ModelConfig
from fungal_model.modifiers.reactivity import SUBSTRATE_REACTIVITY_MODIFIER_TYPE
from fungal_model.processes.inactivation import THERMAL_INACTIVATION_PROCESS_TYPE
from fungal_model.registry.records import (
    CaseTemplateRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
    parameter_record_is_mode_eligible,
    parameter_record_mode_eligibility_blocker,
    parameter_record_selection_key,
)
from fungal_model.registry.store import FungModRegistry, RegistryLookupError
from fungal_model.screening.modelability import ModelabilityReport, assess_modelability
from fungal_model.screening.parameter_resolution import (
    ExactTemplateParameterError,
    resolve_exact_template_parameter_records,
)
from fungal_model.screening.template_environment_modifiers import (
    ENVIRONMENT_MODIFIER_TYPES,
    build_template_environment_entity,
    build_template_environment_modifier,
    environment_response_summary,
)

RegistryCaseConfigMode = Literal["toy", "scientific"]

SURFACE_CATALYSIS_PARAMETER_ROLES = (
    "surface_rate_constant",
    "adsorption_constant",
    "accessible_surface_area",
)
SURFACE_CATALYSIS_TEMPLATE_MODES = ("toy", "exploratory", "scientific")
SURFACE_CATALYSIS_REQUIRED_PROCESS_STATE_METADATA = (
    "config_name",
    "config_mode",
    "config_maturity",
    "accessible_site_pool",
    "product_map_name",
)
_SURFACE_CONFIG_PROVENANCE_REQUIRED = ("source", "measurement_method", "confidence_level", "validity_range", "notes")
# Written by the assembler, the registry wrapper and the screens; a template cannot state them.
_SURFACE_CONFIG_PROVENANCE_RESERVED = frozenset(
    {
        "registry_id",
        "fungus_id",
        "substrate_id",
        "environment_id",
        "process_compatibility_id",
        "case_template_id",
        "parameter_record_ids",
        "parameter_value_sources",
        "environment_response",
        "screen_mode",
        "sample_directory",
        "run_label",
        "scientific_mode_note",
    }
)
_SURFACE_SUBSTRATE_ENTITY_REQUIRED = ("notes", "product_notes")
_SURFACE_SUBSTRATE_ENTITY_OPTIONAL = ("completeness", "default_degradation_model", "water_activity_dependence")
_SURFACE_PARAMETER_ENTRIES_REQUIRED = ("measurement_method", "validity_range")
HOMOGENEOUS_MM_PARAMETER_ROLES = (
    "km",
    "kcat",
    "substrate_initial_concentration",
    "enzyme_initial_concentration",
)
HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES = (
    "km",
    "vmax",
    "substrate_initial_concentration",
)
PH_IONIZATION_MM_PROCESS_TYPE = "ph_ionization_michaelis_menten"
PH_IONIZATION_MM_PARAMETER_ROLES = (
    "turnover",
    "michaelis_constant",
    "free_enzyme_lower_pk",
    "free_enzyme_upper_pk",
    "complex_lower_pk",
    "complex_upper_pk",
    "minimum_ph",
    "maximum_ph",
    "substrate_initial_concentration",
    "enzyme_initial_concentration",
)
_HOMOGENEOUS_MM_PROCESS_PARAMETER_ROLES = {"km": "km", "kcat": "kcat"}
_HOMOGENEOUS_MM_VMAX_PROCESS_PARAMETER_ROLES = {"km": "km", "vmax": "vmax"}
_PH_IONIZATION_MM_PROCESS_PARAMETER_ROLES = {
    "turnover": "turnover",
    "michaelis_constant": "michaelis_constant",
    "free_enzyme_lower_pk": "free_enzyme_lower_pk",
    "free_enzyme_upper_pk": "free_enzyme_upper_pk",
    "complex_lower_pk": "complex_lower_pk",
    "complex_upper_pk": "complex_upper_pk",
    "minimum_ph": "minimum_ph",
    "maximum_ph": "maximum_ph",
}
# An enzyme-kinetics template (plain or pH-dependent Michaelis-Menten with an enzyme state) may declare, under this
# process_state_metadata key, a loss process of its enzyme state.
ENZYME_INACTIVATION_TEMPLATE_KEY = "enzyme_inactivation"
#: The existing process laws such a template may bind as the loss of its enzyme state: the law's state field that
#: takes the enzyme state, and the parameter fields the law reads. Bound without a product or inactive state, each
#: changes the enzyme state only, so the substrate-product balance of the case is untouched.
ENZYME_INACTIVATION_PROCESS_LAWS: Mapping[str, tuple[str, tuple[str, ...]]] = MappingProxyType(
    {
        "first_order": ("source", ("rate_constant",)),
        THERMAL_INACTIVATION_PROCESS_TYPE: (
            "active",
            ("reference_rate_constant", "inactivation_energy", "reference_temperature"),
        ),
    }
)
_ENZYME_INACTIVATION_FIELDS = frozenset({"process_id", "process_type", "parameter_roles", "assumptions"})
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


class RegistryCaseBuildError(ValueError):
    """Raised when a registry case cannot be converted into a model config."""


PRIMARY_ROLE_SET_NAME = "primary"


@dataclass(frozen=True)
class RegistryRoleSet:
    """One complete set of parameter and state roles an assembler can build from.

    A process law may accept more than one parameterization (for example a
    maximum rate, or a turnover number with an explicit catalyst state). Each
    alternative names every parameter role and template state role it needs;
    the compatibility record's ``parameter_roles`` select the set.
    """

    name: str
    parameter_roles: tuple[str, ...]
    state_roles: tuple[str, ...]


@dataclass(frozen=True)
class RegistryProcessAssembler:
    """Config assembly metadata for one registry process type."""

    process_type: str
    process_label: str
    required_parameter_roles: tuple[str, ...]
    required_state_roles: tuple[str, ...]
    deterministic_mode: RegistryCaseConfigMode
    additional_supported_modes: tuple[RegistryCaseConfigMode, ...]
    required_process_state_metadata: tuple[str, ...]
    enforce_template_mode_match: bool
    unsupported_mode_message: str
    config_data_builder: Callable[..., dict[str, Any]]
    alternative_role_sets: tuple[RegistryRoleSet, ...] = ()

    @property
    def supported_request_modes(self) -> tuple[RegistryCaseConfigMode, ...]:
        """Return the backward-compatible primary mode plus explicit additions."""

        return (self.deterministic_mode, *self.additional_supported_modes)

    @property
    def primary_role_set(self) -> RegistryRoleSet:
        """The role set given by ``required_parameter_roles`` and ``required_state_roles``."""

        return RegistryRoleSet(
            name=PRIMARY_ROLE_SET_NAME,
            parameter_roles=self.required_parameter_roles,
            state_roles=self.required_state_roles,
        )

    def role_set_for(self, compatibility: ProcessCompatibilityRecord) -> RegistryRoleSet:
        """Return the role set a compatibility record binds.

        The primary set is returned when the record binds every primary
        parameter role, or when it binds no alternative completely (so that
        missing-role errors keep naming the primary roles). An alternative is
        returned when the record binds all of its parameter roles and not all
        primary roles. Binding the primary set and an alternative, or two
        alternatives, completely is ambiguous and refused.
        """

        bound = set(compatibility.parameter_roles)
        complete = [
            role_set
            for role_set in (self.primary_role_set, *self.alternative_role_sets)
            if set(role_set.parameter_roles) <= bound
        ]
        if len(complete) > 1:
            raise RegistryCaseBuildError(
                f"Process compatibility record {compatibility.record_id!r} binds more than one complete "
                f"{self.process_label} role set ({', '.join(item.name for item in complete)}); bind exactly one."
            )
        if complete:
            return complete[0]
        return self.primary_role_set

    def parameter_roles_for(self, compatibility: ProcessCompatibilityRecord) -> tuple[str, ...]:
        """Return the parameter roles required for the role set a compatibility record binds."""

        return self.role_set_for(compatibility).parameter_roles


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

    resolved = resolve_registry_case(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        registry=registry,
        mode=mode,
    )
    return build_resolved_case_config(resolved, registry=registry, output_directory=output_directory)


@dataclass(frozen=True)
class ResolvedRegistryCase:
    """A modelable registry case resolved once to its compatibility, template and exact records."""

    fungus_id: str
    substrate_id: str
    environment_id: str
    mode: RegistryCaseConfigMode
    report: ModelabilityReport
    compatibility: ProcessCompatibilityRecord
    case_template: CaseTemplateRecord
    parameter_records: Mapping[str, ParameterRecord]

    @property
    def roles_by_symbol(self) -> dict[str, tuple[str, ...]]:
        """Template roles bound to each resolved parameter symbol."""

        roles: dict[str, list[str]] = {}
        for role, record in self.parameter_records.items():
            roles.setdefault(record.parameter_symbol, []).append(role)
        return {symbol: tuple(items) for symbol, items in roles.items()}


def resolve_registry_case(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    mode: RegistryCaseConfigMode = "toy",
) -> ResolvedRegistryCase:
    """Resolve the compatibility, template and exact parameter records of a modelable case."""

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
    if mode not in assembler.supported_request_modes:
        raise RegistryCaseBuildError(assembler.unsupported_mode_message)
    case_template = select_registry_case_template(
        registry=registry,
        compatibility=compatibility,
        assembler=assembler,
    )
    if (
        assembler.enforce_template_mode_match
        and case_template.process_state_metadata.get("config_mode") != mode
    ):
        raise RegistryCaseBuildError(
            "Requested registry case mode "
            f"{mode!r} disagrees with case template "
            f"{case_template.case_template_id!r} explicit config_mode "
            f"{case_template.process_state_metadata.get('config_mode')!r}."
        )
    parameter_records = _exact_role_parameters(
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        required_roles=assembler.parameter_roles_for(compatibility),
        process_label=assembler.process_label,
        mode=mode,
    )
    return ResolvedRegistryCase(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        mode=mode,
        report=report,
        compatibility=compatibility,
        case_template=case_template,
        parameter_records=parameter_records,
    )


def build_resolved_case_config(
    resolved: ResolvedRegistryCase,
    *,
    registry: FungModRegistry,
    output_directory: str | None = None,
    value_overrides: Mapping[str, float] | None = None,
) -> ModelConfig:
    """Build the ``ModelConfig`` of a resolved case, optionally overriding exact record values.

    ``value_overrides`` maps parameter symbols to candidate values in the
    record's own units. Every overridden symbol must be one the case resolved
    with an exact value; the override reaches every place the template binds
    the symbol, including product-map coefficients derived from it.
    """

    records: Mapping[str, ParameterRecord] = resolved.parameter_records
    if value_overrides:
        roles_by_symbol = resolved.roles_by_symbol
        unknown = sorted(set(value_overrides).difference(roles_by_symbol))
        if unknown:
            raise RegistryCaseBuildError(
                f"Value overrides name symbols the case does not resolve: {unknown}."
            )
        replaced = dict(records)
        for symbol, value in value_overrides.items():
            numeric = float(value)
            if not _is_finite(numeric):
                raise RegistryCaseBuildError(f"Value override for {symbol!r} must be finite.")
            for role in roles_by_symbol[symbol]:
                record = records[role]
                if not record.value.is_exact:
                    raise RegistryCaseBuildError(
                        f"Value override for {symbol!r} requires an exact record; role {role!r} has kind "
                        f"{record.value.kind!r}."
                    )
                replaced[role] = replace(record, value=replace(record.value, value=numeric))
        records = replaced
    config_data = build_registry_process_config_data(
        registry=registry,
        compatibility=resolved.compatibility,
        fungus_id=resolved.fungus_id,
        substrate_id=resolved.substrate_id,
        environment_id=resolved.environment_id,
        parameter_records=records,
        output_directory=output_directory,
        case_template=resolved.case_template,
    )
    return ModelConfig.from_mapping(config_data)


def registry_case_config_factory(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    mode: RegistryCaseConfigMode = "toy",
) -> Callable[[Mapping[str, float]], ModelConfig]:
    """Resolve a case once and return a factory rebuilding its config for candidate values.

    The factory is the calibration hook for registry cases: calibration code
    varies parameter symbols, the factory materializes the public-path config
    for each candidate, and nothing is patched behind the template's back.
    """

    resolved = resolve_registry_case(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        registry=registry,
        mode=mode,
    )

    def factory(values: Mapping[str, float]) -> ModelConfig:
        return build_resolved_case_config(resolved, registry=registry, output_directory=None, value_overrides=values)

    return factory


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


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
    case_template: CaseTemplateRecord | None = None,
) -> dict[str, Any]:
    """Build raw model-config data for a supported registry process."""

    assembler = get_registry_process_assembler(compatibility.process_type)
    if assembler is None:
        raise RegistryCaseBuildError(
            "Registry case builder does not support process_type "
            f"{compatibility.process_type!r}."
        )
    if case_template is None:
        case_template = select_registry_case_template(
            registry=registry,
            compatibility=compatibility,
            assembler=assembler,
        )
    else:
        case_template = _validate_case_template_for_assembler(
            template=case_template,
            compatibility=compatibility,
            assembler=assembler,
        )
    substrate = registry.get_substrate(substrate_id)
    data = assembler.config_data_builder(
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
    medium_rows = case_template.process_state_metadata.get("medium_rows")
    if medium_rows is not None:
        from fungal_model.api.user_data_medium import augment_config_with_medium
        data = augment_config_with_medium(data, medium_rows)
    provenance = data.get("provenance")
    if not isinstance(provenance, dict):
        raise RegistryCaseBuildError(
            f"{assembler.process_label} assembly must return a provenance mapping."
        )
    provenance["environment_response"] = environment_response_summary(data.get("processes", ()))
    return data


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
    return _validate_case_template_for_assembler(
        template=template,
        compatibility=compatibility,
        assembler=selected_assembler,
    )


def _validate_case_template_for_assembler(
    *,
    template: CaseTemplateRecord,
    compatibility: ProcessCompatibilityRecord,
    assembler: RegistryProcessAssembler,
) -> CaseTemplateRecord:
    if template.case_template_id != compatibility.case_template_id:
        raise RegistryCaseBuildError(
            "Explicit case template identity mismatch: "
            f"template {template.case_template_id!r}, compatibility "
            f"{compatibility.record_id!r} requires "
            f"{compatibility.case_template_id!r}."
        )
    if template.process_type != compatibility.process_type:
        raise RegistryCaseBuildError(
            "Case template process_type mismatch: "
            f"template {template.case_template_id!r} uses {template.process_type!r}, "
            f"but compatibility {compatibility.record_id!r} uses {compatibility.process_type!r}."
        )
    missing_roles = tuple(
        role
        for role in assembler.role_set_for(compatibility).state_roles
        if role not in template.state_roles
    )
    if missing_roles:
        raise RegistryCaseBuildError(
            "Case template "
            f"{template.case_template_id!r} is missing state role(s) required for "
            f"{assembler.process_label}: {', '.join(missing_roles)}."
        )
    missing_process_metadata = tuple(
        field_name
        for field_name in assembler.required_process_state_metadata
        if not _canonical_template_text(
            template.process_state_metadata.get(field_name)
        )
    )
    if missing_process_metadata:
        raise RegistryCaseBuildError(
            "Case template "
            f"{template.case_template_id!r} is missing explicit process-state "
            f"metadata required for {assembler.process_label}: "
            f"{', '.join(missing_process_metadata)}."
        )
    return template


def select_registry_case_compatibility(
    *,
    registry: FungModRegistry,
    fungus_id: str,
    substrate_id: str,
    report: ModelabilityReport,
) -> ProcessCompatibilityRecord:
    """Return the process compatibility record the modelability report selected.

    ``assess_modelability`` evaluates every compatible record of a case and
    records the one it selected in ``report.selected_compatibility_id``. Config
    assembly, the exploratory and scientific screens and the result tables all
    resolve the case through this function, so a case is built from exactly the
    record, and therefore the enzyme class, that the preflight assessed. The
    record is looked up by its identifier and checked against the case; it is
    never re-derived.

    A report without a selected record (built by hand, or by an older caller)
    is resolved only when the case has exactly one candidate record; with
    several candidates it is refused with the candidates named, because any
    choice could differ from the one the preflight assessed.
    """

    if report.fungus_id != fungus_id or report.substrate_id != substrate_id:
        raise RegistryCaseBuildError(
            f"Modelability report for {report.fungus_id!r} + {report.substrate_id!r} cannot select the "
            f"process compatibility record of case {fungus_id!r} + {substrate_id!r}."
        )
    if report.selected_compatibility_id is not None:
        return _reported_compatibility(
            registry=registry,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            report=report,
            compatibility_id=report.selected_compatibility_id,
        )
    candidates = _compatibility_candidates(
        registry=registry,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        process_types=report.required_processes,
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RegistryCaseBuildError(
            "Modelability report selects no process compatibility record, and no compatible process "
            f"record of case {fungus_id!r} + {substrate_id!r} could be selected for config assembly."
        )
    listed = "; ".join(
        f"{record.record_id} (enzyme class {record.enzyme_class}, process type {record.process_type})"
        for record in candidates
    )
    raise RegistryCaseBuildError(
        "Modelability report does not name its selected process compatibility record, and case "
        f"{fungus_id!r} + {substrate_id!r} has {len(candidates)} candidate records: {listed}. "
        "Assess the case with assess_modelability, which records the selected record, instead of "
        "choosing one here."
    )


def _reported_compatibility(
    *,
    registry: FungModRegistry,
    fungus_id: str,
    substrate_id: str,
    report: ModelabilityReport,
    compatibility_id: str,
) -> ProcessCompatibilityRecord:
    compatibility = registry.process_compatibility.get(compatibility_id)
    if compatibility is None:
        raise RegistryCaseBuildError(
            f"Modelability report selected process compatibility record {compatibility_id!r}, "
            "which this registry does not hold; assess the case against the registry used for assembly."
        )
    problems: list[str] = []
    if report.selected_enzyme_class not in (None, compatibility.enzyme_class):
        problems.append(
            f"the report names enzyme class {report.selected_enzyme_class!r}, the record "
            f"{compatibility.enzyme_class!r}"
        )
    if compatibility.process_type not in report.required_processes:
        problems.append(
            f"the record's process type {compatibility.process_type!r} is not among the report's "
            f"required processes {list(report.required_processes)!r}"
        )
    candidate_ids = {
        record.record_id
        for record in _compatibility_candidates(
            registry=registry,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            process_types=(compatibility.process_type,),
        )
    }
    if compatibility.record_id not in candidate_ids:
        problems.append(
            "the record is not a standalone compatibility record of the fungus's enzyme classes for the "
            "substrate's class and bond classes"
        )
    if problems:
        raise RegistryCaseBuildError(
            f"Modelability report selected process compatibility record {compatibility_id!r}, which does "
            f"not fit case {fungus_id!r} + {substrate_id!r}: {'; '.join(problems)}."
        )
    return compatibility


def _compatibility_candidates(
    *,
    registry: FungModRegistry,
    fungus_id: str,
    substrate_id: str,
    process_types: tuple[str, ...],
) -> tuple[ProcessCompatibilityRecord, ...]:
    """Every standalone compatibility record of the case for the given process types."""

    fungus = registry.get_fungus(fungus_id)
    substrate = registry.get_substrate(substrate_id)
    candidates: dict[str, ProcessCompatibilityRecord] = {}
    for enzyme_class_id in fungus.enzyme_classes:
        for process_type in process_types:
            try:
                records = registry.get_process_compatibility(
                    enzyme_class=enzyme_class_id,
                    substrate_class=substrate.substrate_class,
                    process_type=process_type,
                )
            except RegistryLookupError:
                # An organism may carry enzyme classes that do not act on this
                # substrate; only classes with a compatibility record are candidates.
                continue
            for compatibility in records:
                if set(compatibility.required_bond_classes).issubset(substrate.bond_classes):
                    candidates.setdefault(compatibility.record_id, compatibility)
    return tuple(candidates.values())


def _exact_role_parameters(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    required_roles: tuple[str, ...],
    process_label: str,
    mode: RegistryCaseConfigMode,
) -> Mapping[str, ParameterRecord]:
    roles_to_resolve = _roles_to_resolve(
        compatibility=compatibility,
        required_roles=required_roles,
    )
    try:
        explicit = resolve_exact_template_parameter_records(
            registry=registry,
            template=case_template,
            compatibility=compatibility,
            required_roles=tuple(compatibility.parameter_roles),
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            mode=mode,
            value_requirement="exact",
        )
    except ExactTemplateParameterError as exc:
        raise RegistryCaseBuildError(f"{process_label} exact parameter mapping is invalid: {exc}") from exc
    if explicit is not None:
        return explicit

    missing_roles = tuple(
        role for role in required_roles if role not in compatibility.parameter_roles
    )
    if missing_roles:
        raise RegistryCaseBuildError(
            f"{process_label} registry compatibility is missing parameter role "
            f"mappings for: {', '.join(missing_roles)}."
        )

    resolved: dict[str, ParameterRecord] = {}
    for role in roles_to_resolve:
        symbol = compatibility.parameter_roles[role]
        record = _best_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            mode=mode,
        )
        if record is None:
            raise RegistryCaseBuildError(
                f"No registry parameter record found for role {role!r} and symbol {symbol!r}."
            )
        _validate_deterministic_parameter_record(
            record,
            role=role,
            expected_symbol=symbol,
            mode=mode,
        )
        resolved[role] = record
    return resolved


def _validate_deterministic_parameter_record(
    record: ParameterRecord,
    *,
    role: str,
    expected_symbol: str,
    mode: RegistryCaseConfigMode,
) -> None:
    if record.parameter_symbol != expected_symbol:
        raise RegistryCaseBuildError(
            f"Parameter role {role!r} expected symbol {expected_symbol!r}, but record "
            f"{record.record_id!r} uses {record.parameter_symbol!r}."
        )
    eligibility_blocker = parameter_record_mode_eligibility_blocker(record, mode=mode)
    if eligibility_blocker is not None:
        raise RegistryCaseBuildError(
            f"Parameter role {role!r} and symbol {expected_symbol!r} is mode-ineligible: "
            f"{eligibility_blocker}"
        )
    if not record.value.is_exact:
        raise RegistryCaseBuildError(
            f"Deterministic registry case builder requires exact parameters; role {role!r} uses "
            f"symbol {expected_symbol!r} with ValueSpec kind {record.value.kind!r}."
        )
    validation = record.value.validate(nonnegative=True)
    if not validation.passed:
        raise RegistryCaseBuildError(
            f"Parameter {expected_symbol!r} for role {role!r} failed ValueSpec validation: "
            f"{validation.to_dict()}"
        )


def _template_state(case_template: CaseTemplateRecord, role: str) -> str:
    try:
        return case_template.state_roles[role]
    except KeyError as exc:
        raise RegistryCaseBuildError(
            f"Case template {case_template.case_template_id!r} is missing state role {role!r}."
        ) from exc


def _canonical_template_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and all(ord(character) >= 32 for character in value)
    )


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
    if spec.get("units_from_roles") is not None:
        return _template_units_from_roles(spec["units_from_roles"], parameter_records=parameter_records)
    return str(spec["units"])


def _template_units_from_roles(
    roles: Any,
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> str:
    """Units of an initial state from ``units_from_roles``: the product of the records' units, simplified by pint.

    For example a dry mass per volume (``g/L``) times an amount per dry mass
    (``mmol/g``) gives ``millimole / liter``. Only the units are taken; every
    value placed in the state is converted to them by pint, and no constant
    the records do not state enters.
    """

    if isinstance(roles, (str, bytes)) or not isinstance(roles, Sequence) or len(roles) < 2:
        raise RegistryCaseBuildError("units_from_roles must list at least two parameter roles.")
    product = Q_(1.0, "dimensionless")
    for raw_role in roles:
        role = str(raw_role)
        product = product * Q_(1.0, _record_units(_template_parameter_record(parameter_records, role), role=role))
    return str(product.to_reduced_units().units)


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
        if modifier_type == SUBSTRATE_REACTIVITY_MODIFIER_TYPE:
            configured.append(
                _template_substrate_reactivity_modifier(
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


def _template_substrate_reactivity_modifier(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    modifier: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    """Bind the conversion-dependent substrate reactivity factor ``(S / S_ref)^n`` from template roles.

    The template names the substrate state role and the parameter roles of the
    reference concentration and the exponent; nothing is defaulted, so the
    reference is whatever record the template binds (for example the case's own
    initial-substrate record).
    """

    fields = {}
    for field_name in ("substrate_state_role", "reference_concentration_role", "exponent_role"):
        value = str(modifier.get(field_name, "")).strip()
        if not value:
            raise RegistryCaseBuildError(
                f"Case template {case_template.case_template_id!r} process_modifiers[{index}] requires "
                f"{field_name}."
            )
        fields[field_name] = value
    return {
        "type": SUBSTRATE_REACTIVITY_MODIFIER_TYPE,
        "substrate_state": _template_state(case_template, fields["substrate_state_role"]),
        "reference_concentration": _template_parameter_symbol(
            case_template=case_template,
            parameter_records=parameter_records,
            role=fields["reference_concentration_role"],
            field_name="reference_concentration_role",
        ),
        "exponent": _template_parameter_symbol(
            case_template=case_template,
            parameter_records=parameter_records,
            role=fields["exponent_role"],
            field_name="exponent_role",
        ),
    }


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
    return build_template_environment_modifier(
        template_id=case_template.case_template_id,
        parameter_symbols={
            role: record.parameter_symbol
            for role, record in parameter_records.items()
        },
        registry=registry,
        environment_id=environment_id,
        modifier=modifier,
        modifier_type=modifier_type,
        index=index,
        modifier_label=f"Case template {case_template.case_template_id!r} process_modifiers[{index}]",
        unresolved_label=f"Case template {case_template.case_template_id!r} modifier",
        error_type=RegistryCaseBuildError,
    )


def _template_environment_entity(
    *,
    registry: FungModRegistry,
    environment_id: str,
    modifiers: list[dict[str, Any]],
    process_types: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    return build_template_environment_entity(
        registry=registry,
        environment_id=environment_id,
        modifiers=modifiers,
        error_type=RegistryCaseBuildError,
        process_types=process_types,
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


def _roles_to_resolve(
    *,
    compatibility: ProcessCompatibilityRecord,
    required_roles: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*required_roles, *compatibility.parameter_roles.keys())))


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
    """Assemble one surface-catalysis case from its template and registry records.

    The law is ``r = k_s * theta(E) * A`` with ``theta = K_ads E / (1 + K_ads E)``:
    it reads the free-catalyst state, the adsorption constant, the surface rate
    constant and the accessible area *parameter*, and it reads no geometry. The
    template therefore states its geometry explicitly: a well-mixed geometry
    mapping, kept as context metadata, or ``geometry: null`` for a model that
    claims no vessel; a template that states neither is refused.

    Every label and text comes from the template (``config_name``,
    ``config_mode``, ``config_maturity``, ``accessible_site_pool``,
    ``product_map_name``, ``config_provenance``, ``substrate_entity``,
    ``enzyme_entity``, ``parameter_entries`` and its ``limitations``); the
    structural fields come from the substrate, enzyme-class and compatibility
    records. The bond class is the template's ``bond_type`` or, when the
    template names none, the one bond class the substrate carries, the enzyme
    class targets and the compatibility record requires; several are refused,
    never chosen. A ``scientific`` template is assembled only from exact records
    that the scientific selection rules accept. Nothing is defaulted.
    """

    metadata = case_template.process_state_metadata
    mode = _surface_config_mode(case_template)
    if mode == "scientific":
        _surface_require_scientific_records(case_template, parameter_records=parameter_records)
    physical_state = _surface_physical_state(substrate)
    geometry = _surface_geometry(case_template)
    limitations = _surface_limitations(case_template)
    bond_type = _surface_bond_type(
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        substrate=substrate,
    )
    declared_provenance = _surface_config_provenance(case_template)
    substrate_entity = _surface_text_block(
        case_template,
        "substrate_entity",
        required=_SURFACE_SUBSTRATE_ENTITY_REQUIRED,
        optional=_SURFACE_SUBSTRATE_ENTITY_OPTIONAL,
    )
    enzyme_entity = _surface_enzyme_entity(case_template)
    parameter_entries = _surface_text_block(
        case_template,
        "parameter_entries",
        required=_SURFACE_PARAMETER_ENTRIES_REQUIRED,
    )
    substrate_state = _template_state(case_template, "substrate")
    product_state = _template_state(case_template, "product")
    catalyst_state = _template_state(case_template, "catalyst")
    provenance = _surface_catalysis_provenance(
        registry=registry,
        compatibility=compatibility,
        case_template=case_template,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        parameter_records=parameter_records,
        declared=declared_provenance,
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
    entities: dict[str, Any] = {}
    if geometry is not None:
        entities["geometry"] = {"id": "geometry", "loader": "well_mixed", "data": geometry}
    entities["substrates"] = [
        {
            "id": substrate_id,
            "loader": "generic_solid",
            "data": _surface_substrate_data(
                substrate=substrate,
                physical_state=physical_state,
                enzyme_class=compatibility.enzyme_class,
                provenance=provenance,
                declared=substrate_entity,
            ),
        }
    ]
    entities["enzymes"] = [
        {
            "id": compatibility.enzyme_class,
            "data": _surface_enzyme_data(
                compatibility=compatibility,
                substrate=substrate,
                provenance=provenance,
                declared=enzyme_entity,
            ),
        }
    ]
    entities["product_maps"] = [
        _product_map_entity(
            case_template=case_template,
            provenance=provenance,
            name=str(metadata["product_map_name"]),
            maturity=str(metadata["config_maturity"]),
        )
    ]
    if environment_entity is not None:
        entities["environment"] = environment_entity
    return {
        "kind": "model_config",
        "name": _surface_config_name(case_template, fungus_id=fungus_id, substrate_id=substrate_id),
        "mode": mode,
        "maturity": str(metadata["config_maturity"]),
        "provenance": provenance,
        "case_template": _case_template_config(case_template),
        "entities": entities,
        "parameters": [
            {
                "id": "registry_case_parameters",
                "parameters": [
                    _surface_parameter_config(record, role=role, entries=parameter_entries)
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
                    "bond_type": bond_type,
                    "accessible_site_pool": str(metadata["accessible_site_pool"]),
                },
                "parameters": {
                    role: record.parameter_symbol
                    for role, record in parameter_records.items()
                    if role in SURFACE_CATALYSIS_PARAMETER_ROLES
                },
                "product_map": _product_map_id(case_template),
                "modifiers": modifiers,
                "output_state_roles": dict(case_template.output_state_roles),
                "assumptions": limitations,
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


def _surface_template_label(case_template: CaseTemplateRecord) -> str:
    return f"Surface-catalysis case template {case_template.case_template_id!r}"


def _surface_config_mode(case_template: CaseTemplateRecord) -> str:
    mode = case_template.process_state_metadata.get("config_mode")
    if mode not in SURFACE_CATALYSIS_TEMPLATE_MODES:
        raise RegistryCaseBuildError(
            f"{_surface_template_label(case_template)} config_mode {mode!r} must be one of "
            f"{', '.join(SURFACE_CATALYSIS_TEMPLATE_MODES)}."
        )
    return str(mode)


def _surface_require_scientific_records(
    case_template: CaseTemplateRecord,
    *,
    parameter_records: Mapping[str, ParameterRecord],
) -> None:
    """Refuse a scientific template bound to any record the scientific rules would not select."""

    problems: list[str] = []
    for role, record in parameter_records.items():
        blocker = parameter_record_mode_eligibility_blocker(record, mode="scientific")
        if blocker is not None:
            problems.append(f"{role} ({record.record_id}): {blocker}")
        elif not record.value.is_exact:
            problems.append(f"{role} ({record.record_id}): ValueSpec kind {record.value.kind!r} is not exact.")
    if problems:
        raise RegistryCaseBuildError(
            f"{_surface_template_label(case_template)} declares config_mode 'scientific', but not every bound "
            f"record is exact and scientific-grade: {' '.join(problems)}"
        )


def _surface_physical_state(substrate: SubstrateRecord) -> str:
    physical_state = _configured_physical_state(substrate.physical_state)
    if physical_state in {"dissolved", "unknown"}:
        raise RegistryCaseBuildError(
            f"Substrate record {substrate.record_id!r} declares physical_state {substrate.physical_state!r}; "
            "surface catalysis acts on a substrate the record declares solid."
        )
    return physical_state


def _surface_geometry(case_template: CaseTemplateRecord) -> dict[str, Any] | None:
    """The template's declared geometry, or ``None`` for an explicit ``geometry: null``.

    The surface law reads no geometry, so none is assumed for a template that
    states none.
    """

    metadata = case_template.process_state_metadata
    label = _surface_template_label(case_template)
    if "geometry" not in metadata:
        raise RegistryCaseBuildError(
            f"{label} declares no geometry. The surface-catalysis law reads no geometry (its area is the "
            "accessible_surface_area parameter), and FungMod assumes none: declare 'geometry: null' for a model "
            "that claims no vessel, or the well-mixed geometry mapping the case states as context."
        )
    geometry = metadata["geometry"]
    if geometry is None:
        return None
    if not isinstance(geometry, Mapping) or not geometry:
        raise RegistryCaseBuildError(f"{label} geometry must be a well-mixed geometry mapping or null.")
    if geometry.get("geometry_type") != "well_mixed":
        raise RegistryCaseBuildError(
            f"{label} geometry_type {geometry.get('geometry_type')!r} is not 'well_mixed'; the surface-catalysis "
            "law is well mixed."
        )
    return deepcopy(dict(geometry))


def _surface_limitations(case_template: CaseTemplateRecord) -> list[str]:
    if not case_template.limitations:
        raise RegistryCaseBuildError(
            f"{_surface_template_label(case_template)} states no limitations; the surface-catalysis process "
            "assumptions are the template's limitations and are never supplied by the assembler."
        )
    return list(case_template.limitations)


def _surface_bond_type(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    substrate: SubstrateRecord,
) -> str:
    """The template's ``bond_type``, or the single bond class shared by the substrate and the enzyme class.

    A shared bond class is one the substrate record carries, the enzyme class
    targets and the compatibility record requires. A declared ``bond_type``
    must be one of them.
    """

    label = _surface_template_label(case_template)
    try:
        enzyme_class = registry.get_enzyme_class(compatibility.enzyme_class)
    except RegistryLookupError as exc:
        raise RegistryCaseBuildError(
            f"Process compatibility record {compatibility.record_id!r} names enzyme class "
            f"{compatibility.enzyme_class!r}, which the registry does not hold."
        ) from exc
    shared = tuple(
        bond
        for bond in dict.fromkeys(substrate.bond_classes)
        if bond in enzyme_class.target_bond_classes and bond in compatibility.required_bond_classes
    )
    declared = case_template.process_state_metadata.get("bond_type")
    if declared is not None:
        if not _canonical_template_text(declared):
            raise RegistryCaseBuildError(f"{label} bond_type must be canonical nonblank text.")
        if declared not in shared:
            raise RegistryCaseBuildError(
                f"{label} bond_type {declared!r} is not a bond class shared by substrate {substrate.record_id!r} "
                f"and enzyme class {enzyme_class.record_id!r} (shared: {list(shared)})."
            )
        return str(declared)
    if len(shared) == 1:
        return shared[0]
    if not shared:
        raise RegistryCaseBuildError(
            f"{label} names no bond_type, and substrate {substrate.record_id!r} and enzyme class "
            f"{enzyme_class.record_id!r} share no bond class."
        )
    raise RegistryCaseBuildError(
        f"{label} names no bond_type, and substrate {substrate.record_id!r} and enzyme class "
        f"{enzyme_class.record_id!r} share {len(shared)} bond classes ({', '.join(shared)}); the bond class is "
        "never chosen: declare bond_type in the template."
    )


def _surface_text_block(
    case_template: CaseTemplateRecord,
    key: str,
    *,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
) -> dict[str, str]:
    """A template mapping of canonical texts with exactly the required and optional keys, in declared order."""

    label = _surface_template_label(case_template)
    block = case_template.process_state_metadata.get(key)
    if not isinstance(block, Mapping):
        raise RegistryCaseBuildError(
            f"{label} requires a {key!r} mapping with {', '.join(required)}."
        )
    unknown = sorted(str(name) for name in block if name not in (*required, *optional))
    if unknown:
        raise RegistryCaseBuildError(f"{label} {key} has unsupported field(s): {', '.join(unknown)}.")
    missing = [name for name in required if not _canonical_template_text(block.get(name))]
    invalid = [name for name in optional if name in block and not _canonical_template_text(block[name])]
    if missing or invalid:
        raise RegistryCaseBuildError(
            f"{label} {key} requires canonical nonblank text for: {', '.join((*missing, *invalid))}."
        )
    return {str(name): str(value) for name, value in block.items()}


def _surface_config_provenance(case_template: CaseTemplateRecord) -> dict[str, str]:
    """The template's ``config_provenance`` texts, in declared order.

    Beyond the required fields a template may state further provenance texts
    (for example a milestone label); it may not state the case-identity and
    record fields the assembler and the screens write.
    """

    label = _surface_template_label(case_template)
    block = case_template.process_state_metadata.get("config_provenance")
    if not isinstance(block, Mapping):
        raise RegistryCaseBuildError(
            f"{label} requires a 'config_provenance' mapping with "
            f"{', '.join(_SURFACE_CONFIG_PROVENANCE_REQUIRED)}."
        )
    reserved = sorted(str(name) for name in block if name in _SURFACE_CONFIG_PROVENANCE_RESERVED)
    if reserved:
        raise RegistryCaseBuildError(
            f"{label} config_provenance may not state assembler-written field(s): {', '.join(reserved)}."
        )
    missing = [name for name in _SURFACE_CONFIG_PROVENANCE_REQUIRED if name not in block]
    invalid = [str(name) for name, value in block.items() if not _canonical_template_text(value)]
    if missing or invalid:
        raise RegistryCaseBuildError(
            f"{label} config_provenance requires canonical nonblank text for: {', '.join((*missing, *invalid))}."
        )
    return {str(name): str(value) for name, value in block.items()}


def _surface_enzyme_entity(case_template: CaseTemplateRecord) -> dict[str, Any]:
    label = _surface_template_label(case_template)
    block = case_template.process_state_metadata.get("enzyme_entity")
    if not isinstance(block, Mapping):
        raise RegistryCaseBuildError(f"{label} requires an 'enzyme_entity' mapping with name, validity_labels, notes.")
    unknown = sorted(str(name) for name in block if name not in ("name", "validity_labels", "notes"))
    if unknown:
        raise RegistryCaseBuildError(f"{label} enzyme_entity has unsupported field(s): {', '.join(unknown)}.")
    missing = [name for name in ("name", "notes") if not _canonical_template_text(block.get(name))]
    if missing:
        raise RegistryCaseBuildError(
            f"{label} enzyme_entity requires canonical nonblank text for: {', '.join(missing)}."
        )
    labels = block.get("validity_labels")
    if (
        isinstance(labels, (str, bytes))
        or not isinstance(labels, Sequence)
        or not labels
        or not all(_canonical_template_text(item) for item in labels)
    ):
        raise RegistryCaseBuildError(
            f"{label} enzyme_entity validity_labels must be a nonempty list of canonical nonblank texts."
        )
    return {"name": str(block["name"]), "validity_labels": [str(item) for item in labels], "notes": str(block["notes"])}


def _surface_config_name(case_template: CaseTemplateRecord, *, fungus_id: str, substrate_id: str) -> str:
    try:
        return str(case_template.process_state_metadata["config_name"]).format(
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            case_template_id=case_template.case_template_id,
        )
    except (KeyError, IndexError, ValueError) as exc:
        raise RegistryCaseBuildError(
            f"{_surface_template_label(case_template)} config_name may use only the fields {{fungus_id}}, "
            f"{{substrate_id}} and {{case_template_id}}: {exc}"
        ) from exc


def _surface_catalysis_provenance(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    case_template: CaseTemplateRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    parameter_records: Mapping[str, ParameterRecord],
    declared: Mapping[str, str],
) -> dict[str, Any]:
    """The template's declared provenance (notes last), the case identity and the bound records."""

    provenance: dict[str, Any] = {name: value for name, value in declared.items() if name != "notes"}
    provenance.update(
        {
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
            "notes": declared["notes"],
        }
    )
    return provenance


def _surface_substrate_data(
    *,
    substrate: SubstrateRecord,
    physical_state: str,
    enzyme_class: str,
    provenance: Mapping[str, Any],
    declared: Mapping[str, str],
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": "substrate",
        "name": substrate.name,
        "substrate_type": "generic_solid",
        "chemical_class": substrate.substrate_class,
        "physical_state": physical_state,
        "bond_types": list(substrate.bond_classes),
        "accessible_bonds": list(substrate.bond_classes),
        "required_enzyme_classes": [enzyme_class],
        "degradation_products": [
            {
                "name": product,
                "source": provenance["source"],
                "notes": declared["product_notes"],
            }
            for product in substrate.products
        ],
    }
    # Optional substrate descriptors are written only when the template states them.
    data.update({name: declared[name] for name in _SURFACE_SUBSTRATE_ENTITY_OPTIONAL if name in declared})
    data["provenance"] = {
        "source": provenance["source"],
        "confidence_level": provenance["confidence_level"],
        "notes": declared["notes"],
    }
    data["parameters"] = []
    return data


def _surface_enzyme_data(
    *,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
    provenance: Mapping[str, Any],
    declared: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "enzyme",
        "name": declared["name"],
        "enzyme_class": compatibility.enzyme_class,
        "target_bond_types": list(compatibility.required_bond_classes),
        "target_substrate_classes": [substrate.substrate_class],
        "target_substrate_names": [substrate.name],
        "validity_labels": list(declared["validity_labels"]),
        "provenance": {
            "source": provenance["source"],
            "measurement_method": provenance["measurement_method"],
            "confidence_level": provenance["confidence_level"],
            "notes": declared["notes"],
            "validity_range": provenance["validity_range"],
            "units": "not_applicable",
        },
        "catalytic_parameters": [],
        "adsorption_parameters": [],
        "parameters": [],
    }


def _surface_parameter_config(
    record: ParameterRecord,
    *,
    role: str,
    entries: Mapping[str, str],
) -> dict[str, Any]:
    confidence_level = record.value.confidence_level or record.provenance.get("confidence_level")
    if not _canonical_template_text(confidence_level):
        raise RegistryCaseBuildError(
            f"Parameter record {record.record_id!r} (role {role!r}) states no confidence level on its value or "
            "provenance."
        )
    return {
        "name": record.name,
        "symbol": record.parameter_symbol,
        "value": _record_exact_value(record, role=role),
        "units": _record_units(record, role=role),
        "uncertainty": 0.0,
        "source": record.value.source or _record_source(record),
        "confidence_level": str(confidence_level),
        "notes": f"{record.notes} Registry case role: {role}.",
        "measurement_method": entries["measurement_method"],
        "validity_range": entries["validity_range"],
    }


def _homogeneous_mm_config_data(**kwargs: Any) -> dict[str, Any]:
    role_set = _REGISTRY_PROCESS_ASSEMBLERS["homogeneous_michaelis_menten"].role_set_for(kwargs["compatibility"])
    process_parameter_roles = (
        _HOMOGENEOUS_MM_PROCESS_PARAMETER_ROLES
        if role_set.name == PRIMARY_ROLE_SET_NAME
        else _HOMOGENEOUS_MM_VMAX_PROCESS_PARAMETER_ROLES
    )
    return _enzyme_kinetics_config_data(
        process_type="homogeneous_michaelis_menten",
        process_parameter_roles=process_parameter_roles,
        state_roles=role_set.state_roles,
        **kwargs,
    )


def _ph_ionization_mm_config_data(**kwargs: Any) -> dict[str, Any]:
    return _enzyme_kinetics_config_data(
        process_type=PH_IONIZATION_MM_PROCESS_TYPE,
        process_parameter_roles=_PH_IONIZATION_MM_PROCESS_PARAMETER_ROLES,
        state_roles=_REGISTRY_PROCESS_ASSEMBLERS[PH_IONIZATION_MM_PROCESS_TYPE].required_state_roles,
        **kwargs,
    )


def _enzyme_kinetics_config_data(
    *,
    process_type: str,
    process_parameter_roles: Mapping[str, str],
    state_roles: tuple[str, ...],
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
    """Assemble one well-mixed enzyme-kinetics process (plain or pH-dependent Michaelis-Menten).

    ``state_roles`` are the template state roles of the selected role set, in
    the order they appear in the process states and validators: substrate,
    product and, for enzyme-explicit role sets, enzyme. The substrate entity
    carries the registry substrate's own physical state: a dissolved substrate
    uses the dissolved loader, any other substrate (a suspended solid on which
    the same law runs as an apparent bulk law) the solid loader. A template
    with an enzyme state may also declare a loss process of that state
    (``process_state_metadata.enzyme_inactivation``); it becomes a second
    process of the config, after the Michaelis-Menten process.
    """

    states = {role: _template_state(case_template, role) for role in state_roles}
    substrate_state = states["substrate"]
    product_state = states["product"]
    process_id = str(case_template.process_state_metadata["process_id"])
    parameter_set_id = str(
        case_template.process_state_metadata["parameter_set_id"]
    )
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
    inactivation = _template_enzyme_inactivation(
        case_template=case_template,
        parameter_records=parameter_records,
        states=states,
        process_id=process_id,
    )
    environment_entity = _template_environment_entity(
        registry=registry,
        environment_id=environment_id,
        modifiers=modifiers,
        process_types=(process_type, *((str(inactivation["process_type"]),) if inactivation is not None else ())),
    )
    enzyme_class = registry.get_enzyme_class(compatibility.enzyme_class)
    entities: dict[str, Any] = {
        "substrates": [
            {
                "id": substrate_id,
                "loader": _substrate_loader(_configured_physical_state(substrate.physical_state)),
                "data": _homogeneous_substrate_data(
                    substrate=substrate,
                    enzyme_class=compatibility.enzyme_class,
                    case_template=case_template,
                    provenance=provenance,
                ),
            }
        ],
        "enzymes": [
            {
                "id": compatibility.enzyme_class,
                "data": _homogeneous_enzyme_data(
                    enzyme_class_name=enzyme_class.name,
                    enzyme_class_maturity=enzyme_class.maturity,
                    enzyme_class_notes=enzyme_class.notes,
                    compatibility=compatibility,
                    substrate=substrate,
                    case_template=case_template,
                    provenance=provenance,
                ),
            }
        ],
        "product_maps": [
            _product_map_entity(
                case_template=case_template,
                provenance=provenance,
                name=str(
                    case_template.process_state_metadata["product_map_name"]
                ),
                maturity=case_template.maturity,
            )
        ],
    }
    if environment_entity is not None:
        entities["environment"] = environment_entity
    return {
        "kind": "model_config",
        "name": str(case_template.process_state_metadata["config_name"]),
        "mode": str(case_template.process_state_metadata["config_mode"]),
        "maturity": str(
            case_template.process_state_metadata["config_maturity"]
        ),
        "provenance": provenance,
        "case_template": _case_template_config(case_template),
        "entities": entities,
        "parameters": [
            {
                "id": parameter_set_id,
                "parameters": [
                    _scientific_parameter_config(record, role=role)
                    for role, record in parameter_records.items()
                ],
            }
        ],
        "processes": [
            {
                "id": process_id,
                "process_type": process_type,
                "states": dict(states),
                "product_map": _product_map_id(case_template),
                "parameters": {
                    **{
                        field: parameter_records[role].parameter_symbol
                        for field, role in process_parameter_roles.items()
                    },
                    "rate_units": rate_units,
                },
                "modifiers": modifiers,
                "output_state_roles": dict(case_template.output_state_roles),
                "assumptions": _process_assumptions(
                    case_template,
                    (),
                ),
            },
            *([inactivation] if inactivation is not None else []),
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
                "species": list(states.values()),
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


def _template_enzyme_inactivation(
    *,
    case_template: CaseTemplateRecord,
    parameter_records: Mapping[str, ParameterRecord],
    states: Mapping[str, str],
    process_id: str,
) -> dict[str, Any] | None:
    """The configured loss process of an enzyme-kinetics template's enzyme state, or None when it declares none.

    ``process_state_metadata.enzyme_inactivation`` names the process id, one of
    the existing laws in ``ENZYME_INACTIVATION_PROCESS_LAWS``, the parameter
    role of every field that law reads (exactly those fields) and at least one
    explicit assumption. The law acts on the enzyme state alone; nothing is
    defaulted, and a role set without an enzyme state (the Vmax form) is
    refused, since it represents no enzyme to lose.
    """

    raw = case_template.process_state_metadata.get(ENZYME_INACTIVATION_TEMPLATE_KEY)
    if raw is None:
        return None
    label = f"Case template {case_template.case_template_id!r} {ENZYME_INACTIVATION_TEMPLATE_KEY}"
    if not isinstance(raw, Mapping):
        raise RegistryCaseBuildError(f"{label} must be a mapping.")
    unknown = sorted(str(key) for key in raw if str(key) not in _ENZYME_INACTIVATION_FIELDS)
    if unknown:
        raise RegistryCaseBuildError(f"{label} has unsupported field(s): {', '.join(unknown)}.")
    inactivation_id = raw.get("process_id")
    if not _canonical_template_text(inactivation_id) or inactivation_id == process_id:
        raise RegistryCaseBuildError(
            f"{label} requires a nonblank process_id distinct from the template's process_id {process_id!r}."
        )
    process_type = str(raw.get("process_type", ""))
    law = ENZYME_INACTIVATION_PROCESS_LAWS.get(process_type)
    if law is None:
        raise RegistryCaseBuildError(
            f"{label} process_type {process_type!r} is not a law the enzyme state can be lost through; supported: "
            f"{', '.join(ENZYME_INACTIVATION_PROCESS_LAWS)}."
        )
    if "enzyme" not in states:
        raise RegistryCaseBuildError(
            f"{label} binds {process_type!r} to the enzyme state, but the bound role set has no enzyme state "
            f"(states: {', '.join(states)}); a maximum-rate role set represents no enzyme, so its loss cannot be "
            "simulated."
        )
    state_field, fields = law
    roles = raw.get("parameter_roles")
    if not isinstance(roles, Mapping) or {str(key) for key in roles} != set(fields):
        raise RegistryCaseBuildError(f"{label} parameter_roles must bind exactly {', '.join(fields)}.")
    assumptions = raw.get("assumptions")
    if (
        not isinstance(assumptions, Sequence)
        or isinstance(assumptions, (str, bytes))
        or not assumptions
        or not all(_canonical_template_text(item) for item in assumptions)
    ):
        raise RegistryCaseBuildError(f"{label} must declare at least one explicit assumption.")
    parameters: dict[str, str] = {}
    for field_name in fields:
        role = str(roles[field_name])
        record = parameter_records.get(role)
        if record is None:
            raise RegistryCaseBuildError(f"{label} parameter_roles.{field_name} references unresolved role {role!r}.")
        parameters[field_name] = record.parameter_symbol
    return {
        "id": str(inactivation_id),
        "process_type": process_type,
        "states": {state_field: states["enzyme"]},
        "parameters": parameters,
        "modifiers": [],
        "output_state_roles": dict(case_template.output_state_roles),
        "assumptions": [str(item) for item in assumptions],
    }


def _homogeneous_substrate_data(
    *,
    substrate: SubstrateRecord,
    enzyme_class: str,
    case_template: CaseTemplateRecord,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    physical_state = _configured_physical_state(substrate.physical_state)
    return {
        "kind": "substrate",
        "name": substrate.name,
        "substrate_type": _substrate_loader(physical_state),
        "chemical_class": substrate.substrate_class,
        "physical_state": physical_state,
        "bond_types": list(substrate.bond_classes),
        "accessible_bonds": list(substrate.bond_classes),
        "required_enzyme_classes": [enzyme_class],
        "degradation_products": [
            {
                "name": product,
                "source": provenance["source"],
                "notes": (
                    "Product declared by the selected registry substrate and "
                    "case-template product-map contract."
                ),
            }
            for product in substrate.products
        ],
        "completeness": "partial",
        "default_degradation_model": _default_degradation_model(physical_state),
        "water_activity_dependence": "unknown",
        "provenance": {
            "source": provenance["source"],
            "confidence_level": provenance["confidence_level"],
            "notes": substrate.notes,
            "validity_range": "; ".join(case_template.validity_notes),
        },
        "parameters": [],
    }


def _substrate_loader(physical_state: str) -> str:
    """The generic substrate loader of a declared physical state: dissolved, or a solid of any kind."""

    return "generic_dissolved" if physical_state == "dissolved" else "generic_solid"


def _default_degradation_model(physical_state: str) -> str:
    """The degradation regime a substrate entity declares for its physical state.

    A dissolved substrate is homogeneous. For a solid the well-mixed law is an
    apparent bulk law that establishes no degradation regime of the material,
    so the regime stays ``unknown``.
    """

    return "homogeneous_dissolved" if physical_state == "dissolved" else "unknown"


def _homogeneous_enzyme_data(
    *,
    enzyme_class_name: str,
    enzyme_class_maturity: str,
    enzyme_class_notes: str,
    compatibility: ProcessCompatibilityRecord,
    substrate: SubstrateRecord,
    case_template: CaseTemplateRecord,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "enzyme",
        "name": enzyme_class_name,
        "enzyme_class": compatibility.enzyme_class,
        "target_bond_types": list(compatibility.required_bond_classes),
        "target_substrate_classes": [substrate.substrate_class],
        "target_substrate_names": [substrate.name],
        "validity_labels": [
            enzyme_class_maturity,
            "homogeneous_enzyme_kinetics",
        ],
        "provenance": {
            "source": provenance["source"],
            "measurement_method": "registry-backed case-template assembly",
            "confidence_level": provenance["confidence_level"],
            "notes": enzyme_class_notes,
            "validity_range": "; ".join(case_template.validity_notes),
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
        "measurement_method": str(
            record.provenance.get(
                "measurement_method",
                "registry-backed exact ValueSpec",
            )
        ),
        "validity_range": str(
            record.provenance.get(
                "validity_range",
                "Linked registry record and case-template scope only.",
            )
        ),
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
    if _canonical_template_text(source):
        return str(source)
    source_database = record.provenance.get("source_database")
    if _canonical_template_text(source_database):
        return str(source_database)
    raise RegistryCaseBuildError(
        f"Parameter record {record.record_id!r} requires explicit value source, "
        "provenance source, or provenance source_database text."
    )


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
    from fungal_model.screening.enzyme_chain import (
        EnzymeChainAssemblyError,
        build_extracellular_enzyme_chain_config,
    )

    try:
        config = build_extracellular_enzyme_chain_config(
            registry=registry,
            template_id=case_template.case_template_id,
            environment_id=environment_id,
            output_directory=output_directory,
        )
    except EnzymeChainAssemblyError as exc:
        raise RegistryCaseBuildError(str(exc)) from exc
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


def _culture_physiology_config_data(
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
    from fungal_model.screening.culture_physiology import build_culture_physiology_config_data

    return build_culture_physiology_config_data(
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


def _enzyme_network_config_data(
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
    from fungal_model.screening.enzyme_network import build_enzyme_network_config_data

    return build_enzyme_network_config_data(
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
    source = _registry_provenance_source(case_template)
    confidence_level = _required_provenance_text(
        case_template.provenance,
        field_name="confidence_level",
        record_label=f"Case template {case_template.case_template_id!r}",
    )
    return {
        "source": source,
        "confidence_level": confidence_level,
        "source_database": _consistent_optional_provenance_text(
            "source_database",
            compatibility.provenance,
            case_template.provenance,
        ),
        "source_reaction_id": _consistent_optional_provenance_text(
            "source_reaction_id",
            compatibility.provenance,
            case_template.provenance,
        ),
        "selected_kinlaw_entry_id": _consistent_optional_provenance_text(
            "selected_kinlaw_entry_id",
            compatibility.provenance,
            case_template.provenance,
        ),
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
        "notes": case_template.notes,
    }


def _registry_provenance_source(record: CaseTemplateRecord) -> str:
    source = record.provenance.get("source")
    if _canonical_template_text(source):
        return str(source)
    source_database = record.provenance.get("source_database")
    if _canonical_template_text(source_database):
        return str(source_database)
    raise RegistryCaseBuildError(
        f"Case template {record.case_template_id!r} requires explicit provenance "
        "source or source_database text for homogeneous assembly."
    )


def _required_provenance_text(
    provenance: Mapping[str, Any],
    *,
    field_name: str,
    record_label: str,
) -> str:
    value = provenance.get(field_name)
    if not _canonical_template_text(value):
        raise RegistryCaseBuildError(
            f"{record_label} requires explicit provenance {field_name!r} text."
        )
    return str(value)


def _consistent_optional_provenance_text(
    field_name: str,
    *provenance_mappings: Mapping[str, Any],
) -> str | None:
    values = tuple(
        mapping[field_name]
        for mapping in provenance_mappings
        if mapping.get(field_name) is not None
    )
    if not values:
        return None
    if any(
        not _canonical_template_text(value) or value != values[0]
        for value in values
    ):
        raise RegistryCaseBuildError(
            "Registry compatibility and case-template provenance disagree on "
            f"canonical {field_name!r} text."
        )
    return str(values[0])


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
    mode: RegistryCaseConfigMode,
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
        and parameter_record_is_mode_eligible(record, mode=mode)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda record: parameter_record_selection_key(record, mode=mode),
    )


def _matches(record_value: str | None, requested: str) -> bool:
    return record_value is None or record_value == requested


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
        additional_supported_modes=("scientific",),
        required_process_state_metadata=SURFACE_CATALYSIS_REQUIRED_PROCESS_STATE_METADATA,
        enforce_template_mode_match=True,
        unsupported_mode_message=(
            "Surface-catalysis registry assembly supports mode='toy' or mode='scientific', matching the "
            "template's config_mode; exploratory templates are sampled through the exploratory screen."
        ),
        config_data_builder=_surface_catalysis_config_data,
    ),
    "homogeneous_michaelis_menten": RegistryProcessAssembler(
        process_type="homogeneous_michaelis_menten",
        process_label="Homogeneous Michaelis-Menten",
        required_parameter_roles=HOMOGENEOUS_MM_PARAMETER_ROLES,
        required_state_roles=("substrate", "product", "enzyme"),
        deterministic_mode="scientific",
        additional_supported_modes=("toy",),
        required_process_state_metadata=(
            "config_name",
            "config_mode",
            "config_maturity",
            "process_id",
            "parameter_set_id",
            "product_map_name",
        ),
        enforce_template_mode_match=True,
        unsupported_mode_message=(
            "Homogeneous Michaelis-Menten registry assembly supports mode='toy' "
            "or mode='scientific'."
        ),
        config_data_builder=_homogeneous_mm_config_data,
        alternative_role_sets=(
            RegistryRoleSet(
                name="vmax",
                parameter_roles=HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES,
                state_roles=("substrate", "product"),
            ),
        ),
    ),
    PH_IONIZATION_MM_PROCESS_TYPE: RegistryProcessAssembler(
        process_type=PH_IONIZATION_MM_PROCESS_TYPE,
        process_label="pH-ionization Michaelis-Menten",
        required_parameter_roles=PH_IONIZATION_MM_PARAMETER_ROLES,
        required_state_roles=("substrate", "product", "enzyme"),
        deterministic_mode="scientific",
        additional_supported_modes=("toy",),
        required_process_state_metadata=(
            "config_name",
            "config_mode",
            "config_maturity",
            "process_id",
            "parameter_set_id",
            "product_map_name",
        ),
        enforce_template_mode_match=True,
        unsupported_mode_message=(
            "pH-ionization Michaelis-Menten registry assembly supports mode='toy' "
            "or mode='scientific'."
        ),
        config_data_builder=_ph_ionization_mm_config_data,
    ),
    "culture_physiology": RegistryProcessAssembler(
        process_type="culture_physiology",
        process_label="Culture physiology",
        required_parameter_roles=(),
        required_state_roles=("substrate", "biomass"),
        deterministic_mode="scientific",
        additional_supported_modes=("toy",),
        required_process_state_metadata=(
            "config_name",
            "config_mode",
            "config_maturity",
            "parameter_set_id",
        ),
        enforce_template_mode_match=True,
        unsupported_mode_message=(
            "Culture-physiology registry assembly supports mode='scientific' or mode='toy'; "
            "exploratory screens sample the same template through the ensemble path."
        ),
        config_data_builder=_culture_physiology_config_data,
    ),
    "enzyme_network": RegistryProcessAssembler(
        process_type="enzyme_network",
        process_label="Enzyme network",
        required_parameter_roles=(),
        required_state_roles=("substrate", "product"),
        deterministic_mode="scientific",
        additional_supported_modes=("toy",),
        required_process_state_metadata=(
            "config_name",
            "config_mode",
            "config_maturity",
            "parameter_set_id",
        ),
        enforce_template_mode_match=True,
        unsupported_mode_message=(
            "Enzyme-network registry assembly supports mode='scientific' or mode='toy'; "
            "exploratory screens sample the same template through the ensemble path."
        ),
        config_data_builder=_enzyme_network_config_data,
    ),
    "extracellular_enzyme_chain": RegistryProcessAssembler(
        process_type="extracellular_enzyme_chain",
        process_label="Extracellular enzyme chain",
        required_parameter_roles=EXTRACELLULAR_ENZYME_CHAIN_PARAMETER_ROLES,
        required_state_roles=("substrate", "intermediate", "product", "surface_catalyst", "homogeneous_catalyst"),
        deterministic_mode="toy",
        additional_supported_modes=(),
        required_process_state_metadata=(),
        enforce_template_mode_match=False,
        unsupported_mode_message=(
            "Extracellular enzyme-chain registry assembly currently emits the existing "
            "exploratory CASE-001/BIO-002 template through exploratory screens."
        ),
        config_data_builder=_extracellular_enzyme_chain_config_data,
    ),
}


_REGISTRY_PROCESS_ASSEMBLERS["adsorbed_enzyme_hydrolysis"] = adsorption_registry_assembler()


__all__ = [
    "ENZYME_INACTIVATION_PROCESS_LAWS",
    "ENZYME_INACTIVATION_TEMPLATE_KEY",
    "HOMOGENEOUS_MM_PARAMETER_ROLES",
    "HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES",
    "PRIMARY_ROLE_SET_NAME",
    "RegistryCaseBuildError",
    "RegistryCaseConfigMode",
    "RegistryProcessAssembler",
    "RegistryRoleSet",
    "SURFACE_CATALYSIS_PARAMETER_ROLES",
    "SURFACE_CATALYSIS_REQUIRED_PROCESS_STATE_METADATA",
    "SURFACE_CATALYSIS_TEMPLATE_MODES",
    "build_registry_process_config_data",
    "build_model_config_from_registry_case",
    "get_registry_process_assembler",
    "select_registry_case_compatibility",
    "select_registry_case_template",
]
