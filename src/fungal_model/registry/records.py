"""Registry record objects for plug-and-play FungMod metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from fungal_model.core.validators import ValidationResult
from fungal_model.core.value_spec import ValueSpec
from fungal_model.provenance import classify_parameter_provenance


def _tuple_of_strings(values: Sequence[Any] | None) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()))


CASE_TEMPLATE_SCHEMA_VERSION = "1"
PARAMETER_ALLOWED_USE_STORAGE_ONLY = "registry_storage_only_no_simulation_authorization"
PARAMETER_ALLOWED_USE_SCIENTIFIC = (
    "scientific_or_exploratory_when_all_other_inputs_are_valid"
)
PARAMETER_ALLOWED_USE_EXPLORATORY = (
    "exploratory_simulation_only_not_literature_curated"
)
PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING = (
    "exploratory_screening_only_not_calibrated_uncertainty_not_environment_response"
)
PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY = "software_tests_only_not_scientific"
PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY = (
    "preflight_and_gap_analysis_only_requires_measurement_or_curation"
)
ParameterRecordSelectionMode = Literal["exploratory", "scientific", "toy"]
_PARAMETER_ALLOWED_USE_BY_MODE: Mapping[ParameterRecordSelectionMode, frozenset[str]] = {
    "scientific": frozenset({PARAMETER_ALLOWED_USE_SCIENTIFIC}),
    "exploratory": frozenset(
        {
            PARAMETER_ALLOWED_USE_SCIENTIFIC,
            PARAMETER_ALLOWED_USE_EXPLORATORY,
            PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING,
            PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY,
        }
    ),
    "toy": frozenset(
        {
            PARAMETER_ALLOWED_USE_SCIENTIFIC,
            PARAMETER_ALLOWED_USE_EXPLORATORY,
            PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING,
            PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY,
        }
    ),
}
CASE_TEMPLATE_ALLOWED_STATE_ROLES = frozenset(
    {
        "substrate",
        "intermediate",
        "product",
        "enzyme",
        "catalyst",
        "surface_catalyst",
        "homogeneous_catalyst",
        "accessibility_proxy",
    }
)
CASE_TEMPLATE_INDEXED_STATE_ROLE_PATTERN = re.compile(
    r"^(?:intermediate|catalyst|enzyme)_[a-z0-9][a-z0-9_]*$"
)


@dataclass(frozen=True)
class RegistryRecord:
    """Common metadata required for all registry records."""

    record_id: str
    name: str
    maturity: str
    provenance: Mapping[str, Any]
    notes: str
    display_name: str = ""
    scientific_name: str = ""
    aliases: tuple[str, ...] = ()
    external_refs: Mapping[str, Any] = field(default_factory=dict)
    ec_number: str = ""
    database_ids: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def _common_issues(self) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if not self.record_id:
            issues.append({"field": "record_id", "message": "Registry record id is required."})
        if not self.name:
            issues.append({"field": "name", "message": "Registry record name is required."})
        if not self.maturity:
            issues.append({"field": "maturity", "message": "Registry record maturity is required."})
        if not isinstance(self.provenance, Mapping) or not self.provenance:
            issues.append({"field": "provenance", "message": "Registry record provenance is required."})
        if not self.notes:
            issues.append({"field": "notes", "message": "Registry record notes are required."})
        return issues

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "record_id": self.record_id,
            "name": self.name,
            "maturity": self.maturity,
            "provenance": dict(self.provenance),
            "notes": self.notes,
        }
        if self.display_name:
            data["display_name"] = self.display_name
        if self.scientific_name:
            data["scientific_name"] = self.scientific_name
        if self.aliases:
            data["aliases"] = list(self.aliases)
        if self.external_refs:
            data["external_refs"] = dict(self.external_refs)
        if self.ec_number:
            data["ec_number"] = self.ec_number
        if self.database_ids:
            data["database_ids"] = {
                key: list(values)
                for key, values in self.database_ids.items()
            }
        return data


@dataclass(frozen=True)
class FungusRecord(RegistryRecord):
    """Minimal fungus capability record."""

    enzyme_classes: tuple[str, ...] = ()
    assimilable_products: tuple[str, ...] = ()

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        if not self.enzyme_classes:
            issues.append({"field": "enzyme_classes", "message": "Fungus record requires enzyme classes."})
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "enzyme_classes": list(self.enzyme_classes),
                "assimilable_products": list(self.assimilable_products),
            }
        )
        return data


@dataclass(frozen=True)
class EnzymeClassRecord(RegistryRecord):
    """Minimal enzyme-class compatibility record."""

    target_bond_classes: tuple[str, ...] = ()
    compatible_substrate_classes: tuple[str, ...] = ()
    compatible_processes: tuple[str, ...] = ()

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        if not self.target_bond_classes:
            issues.append({"field": "target_bond_classes", "message": "Enzyme class requires target bonds."})
        if not self.compatible_substrate_classes:
            issues.append(
                {"field": "compatible_substrate_classes", "message": "Enzyme class requires substrate classes."}
            )
        if not self.compatible_processes:
            issues.append({"field": "compatible_processes", "message": "Enzyme class requires processes."})
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "target_bond_classes": list(self.target_bond_classes),
                "compatible_substrate_classes": list(self.compatible_substrate_classes),
                "compatible_processes": list(self.compatible_processes),
            }
        )
        return data


@dataclass(frozen=True)
class SubstrateRecord(RegistryRecord):
    """Minimal substrate record with categorical structure and value specs."""

    substrate_class: str = ""
    physical_state: str = ""
    bond_classes: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    properties: Mapping[str, ValueSpec] = field(default_factory=dict)

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        if not self.substrate_class:
            issues.append({"field": "substrate_class", "message": "Substrate class is required."})
        if not self.physical_state:
            issues.append({"field": "physical_state", "message": "Substrate physical state is required."})
        if not self.bond_classes:
            issues.append({"field": "bond_classes", "message": "Substrate bond classes are required."})
        for key, value in self.properties.items():
            validation = value.validate()
            if not validation.passed:
                issues.append({"field": f"properties.{key}", "message": validation.message, "details": validation.details})
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "substrate_class": self.substrate_class,
                "physical_state": self.physical_state,
                "bond_classes": list(self.bond_classes),
                "products": list(self.products),
                "properties": {key: value.to_dict() for key, value in self.properties.items()},
            }
        )
        return data


@dataclass(frozen=True)
class EnvironmentRecord(RegistryRecord):
    """Minimal environment record with condition value specs."""

    conditions: Mapping[str, ValueSpec] = field(default_factory=dict)

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        if not self.conditions:
            issues.append({"field": "conditions", "message": "Environment record requires conditions."})
        for key, value in self.conditions.items():
            validation = value.validate()
            if not validation.passed:
                issues.append({"field": f"conditions.{key}", "message": validation.message, "details": validation.details})
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["conditions"] = {key: value.to_dict() for key, value in self.conditions.items()}
        return data


@dataclass(frozen=True)
class ProcessComponentBinding:
    """Ordered binding from one template process to one component compatibility."""

    process_template_id: str
    compatibility_record_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "process_template_id": self.process_template_id,
            "compatibility_record_id": self.compatibility_record_id,
        }


@dataclass(frozen=True)
class ProcessCompatibilityRecord(RegistryRecord):
    """Record describing when a process type is categorically compatible."""

    enzyme_class: str = ""
    substrate_class: str = ""
    required_bond_classes: tuple[str, ...] = ()
    process_type: str = ""
    required_parameters: tuple[str, ...] = ()
    parameter_roles: Mapping[str, str] = field(default_factory=dict)
    product_map_required: bool = False
    case_template_id: str = ""
    component_bindings: tuple[ProcessComponentBinding, ...] = ()

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        for field_name in ("enzyme_class", "substrate_class", "process_type"):
            if not getattr(self, field_name):
                issues.append({"field": field_name, "message": f"{field_name} is required."})
        if not self.required_bond_classes:
            issues.append({"field": "required_bond_classes", "message": "Required bond classes are required."})
        unknown_role_parameters = tuple(
            symbol
            for symbol in self.parameter_roles.values()
            if symbol not in self.required_parameters
        )
        if unknown_role_parameters:
            issues.append(
                {
                    "field": "parameter_roles",
                    "message": "Parameter role mappings must reference required parameters.",
                    "details": {"unknown_symbols": unknown_role_parameters},
                }
            )
        bindings = self.component_bindings
        if not isinstance(bindings, tuple):
            issues.append(
                {
                    "field": "component_bindings",
                    "message": "Component bindings must be an immutable sequence.",
                }
            )
            bindings = ()
        process_ids: list[str] = []
        compatibility_ids: list[str] = []
        for index, binding in enumerate(bindings):
            if not isinstance(binding, ProcessComponentBinding):
                issues.append(
                    {
                        "field": f"component_bindings.{index}",
                        "message": "Component bindings must use ProcessComponentBinding values.",
                    }
                )
                continue
            process_ids.append(binding.process_template_id)
            compatibility_ids.append(binding.compatibility_record_id)
            if (
                not isinstance(binding.process_template_id, str)
                or not binding.process_template_id.strip()
            ):
                issues.append(
                    {
                        "field": f"component_bindings.{index}.process_template_id",
                        "message": "Component binding process_template_id is required.",
                    }
                )
            if (
                not isinstance(binding.compatibility_record_id, str)
                or not binding.compatibility_record_id.strip()
            ):
                issues.append(
                    {
                        "field": f"component_bindings.{index}.compatibility_record_id",
                        "message": "Component binding compatibility_record_id is required.",
                    }
                )
        if len(set(process_ids)) != len(process_ids):
            issues.append(
                {
                    "field": "component_bindings",
                    "message": "Component binding process_template_id values must be unique.",
                }
            )
        if len(set(compatibility_ids)) != len(compatibility_ids):
            issues.append(
                {
                    "field": "component_bindings",
                    "message": "Component binding compatibility_record_id values must be unique.",
                }
            )
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "enzyme_class": self.enzyme_class,
                "substrate_class": self.substrate_class,
                "required_bond_classes": list(self.required_bond_classes),
                "process_type": self.process_type,
                "required_parameters": list(self.required_parameters),
                "parameter_roles": dict(self.parameter_roles),
                "product_map_required": self.product_map_required,
                "case_template_id": self.case_template_id,
            }
        )
        if self.component_bindings:
            data["component_bindings"] = [
                binding.to_dict() for binding in self.component_bindings
            ]
        return data


@dataclass(frozen=True)
class CaseTemplateRecord(RegistryRecord):
    """Assembly-only template for turning a compatible registry case into states and outputs."""

    case_template_id: str = ""
    schema_version: str = CASE_TEMPLATE_SCHEMA_VERSION
    process_type: str = ""
    state_roles: Mapping[str, str] = field(default_factory=dict)
    initial_state_mapping: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    product_map: Mapping[str, Any] = field(default_factory=dict)
    stoichiometric_yields: Mapping[str, float] = field(default_factory=dict)
    time_grid: Mapping[str, Any] = field(default_factory=dict)
    observable_roles: tuple[str, ...] = ()
    output_state_roles: Mapping[str, str] = field(default_factory=dict)
    process_state_metadata: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    validity_notes: tuple[str, ...] = ()

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        if not self.case_template_id:
            issues.append({"field": "case_template_id", "message": "Case template id is required."})
        elif self.case_template_id != self.record_id:
            issues.append(
                {
                    "field": "case_template_id",
                    "message": "case_template_id must match record_id.",
                    "details": {"case_template_id": self.case_template_id, "record_id": self.record_id},
                }
            )
        if self.schema_version != CASE_TEMPLATE_SCHEMA_VERSION:
            issues.append(
                {
                    "field": "schema_version",
                    "message": f"Unsupported case-template schema version {self.schema_version!r}.",
                }
            )
        if not self.process_type:
            issues.append({"field": "process_type", "message": "Case template process_type is required."})
        issues.extend(_case_template_state_role_issues(self.state_roles))
        issues.extend(_case_template_initial_state_issues(self.initial_state_mapping, self.state_roles))
        issues.extend(_case_template_product_map_issues(self.product_map, self.state_roles, self.stoichiometric_yields))
        issues.extend(_case_template_time_grid_issues(self.time_grid))
        issues.extend(_case_template_output_role_issues("observable_roles", self.observable_roles))
        issues.extend(_case_template_state_role_issues(self.output_state_roles, field_name="output_state_roles"))
        if not self.limitations:
            issues.append({"field": "limitations", "message": "Case template limitations are required."})
        if not self.validity_notes:
            issues.append({"field": "validity_notes", "message": "Case template validity notes are required."})
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "case_template_id": self.case_template_id,
                "schema_version": self.schema_version,
                "process_type": self.process_type,
                "state_roles": dict(self.state_roles),
                "initial_state_mapping": {
                    role: dict(spec)
                    for role, spec in self.initial_state_mapping.items()
                },
                "product_map": dict(self.product_map),
                "stoichiometric_yields": dict(self.stoichiometric_yields),
                "time_grid": dict(self.time_grid),
                "observable_roles": list(self.observable_roles),
                "output_state_roles": dict(self.output_state_roles),
                "process_state_metadata": dict(self.process_state_metadata),
                "limitations": list(self.limitations),
                "validity_notes": list(self.validity_notes),
            }
        )
        return data


@dataclass(frozen=True)
class ParameterRecord(RegistryRecord):
    """Registry parameter value tied to process/entity selectors."""

    parameter_symbol: str = ""
    process_type: str = ""
    enzyme_class: str | None = None
    substrate_class: str | None = None
    fungus_id: str | None = None
    substrate_id: str | None = None
    environment_id: str | None = None
    value: ValueSpec = field(default_factory=lambda: ValueSpec(kind="unknown", units=None))
    range_scope: str = ""
    range_interpretation: str = ""
    allowed_use: str = ""

    def validate(self) -> ValidationResult:
        issues = self._common_issues()
        if not self.parameter_symbol:
            issues.append({"field": "parameter_symbol", "message": "Parameter symbol is required."})
        if not self.process_type:
            issues.append({"field": "process_type", "message": "Parameter process type is required."})
        validation = self.value.validate()
        if not validation.passed:
            issues.append({"field": "value", "message": validation.message, "details": validation.details})
        return _validation_result(self.record_id, issues)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "parameter_symbol": self.parameter_symbol,
                "process_type": self.process_type,
                "enzyme_class": self.enzyme_class,
                "substrate_class": self.substrate_class,
                "fungus_id": self.fungus_id,
                "substrate_id": self.substrate_id,
                "environment_id": self.environment_id,
                "value": self.value.to_dict(),
                "range_scope": self.range_scope,
                "range_interpretation": self.range_interpretation,
                "allowed_use": self.allowed_use,
            }
        )
        return data


def parameter_simulation_authorization_blocker(record: ParameterRecord) -> str | None:
    """Return the mode-independent simulation blocker for a parameter record."""

    if record.allowed_use == PARAMETER_ALLOWED_USE_STORAGE_ONLY:
        return "Parameter allowed_use is storage-only and does not authorize simulation in any mode."
    if classify_parameter_provenance(record.provenance) != "generic":
        return (
            "Parameter provenance carries curator-authoring source evidence, which does not "
            "authorize simulation even if its outer allowed_use is changed."
        )
    return None


def parameter_is_simulation_authorized(record: ParameterRecord) -> bool:
    """Return whether the record passes the mode-independent authorization policy."""

    return parameter_simulation_authorization_blocker(record) is None


def parameter_record_is_exploratory(record: ParameterRecord) -> bool:
    """Return whether a parameter is explicitly limited to exploratory use."""

    return record.maturity == "exploratory_prior" or bool(
        record.provenance.get("exploratory_prior")
    )


def parameter_record_mode_eligibility_blocker(
    record: ParameterRecord,
    *,
    mode: ParameterRecordSelectionMode,
) -> str | None:
    """Return the shared authorization and mode-eligibility blocker."""

    if mode not in _PARAMETER_ALLOWED_USE_BY_MODE:
        raise ValueError(f"Unsupported parameter selection mode: {mode!r}")
    authorization_blocker = parameter_simulation_authorization_blocker(record)
    if authorization_blocker is not None:
        return authorization_blocker
    if record.allowed_use not in _PARAMETER_ALLOWED_USE_BY_MODE[mode]:
        return (
            f"Parameter allowed_use {record.allowed_use!r} does not exactly authorize "
            f"{mode} simulation."
        )
    if mode in {"exploratory", "toy"}:
        return None
    if parameter_record_is_exploratory(record):
        return "Scientific mode rejects exploratory-prior parameter records."
    maturity = record.maturity.casefold()
    if maturity.startswith("toy") or maturity.startswith("synthetic"):
        return "Scientific mode rejects toy or synthetic parameter records."
    return None


def parameter_record_is_mode_eligible(
    record: ParameterRecord,
    *,
    mode: ParameterRecordSelectionMode,
) -> bool:
    """Return whether a parameter may enter candidate ranking for the mode."""

    return parameter_record_mode_eligibility_blocker(record, mode=mode) is None


def parameter_record_selection_key(
    record: ParameterRecord,
    *,
    mode: ParameterRecordSelectionMode,
) -> tuple[int, ...]:
    """Return the shared mode-aware ranking key for parameter candidates."""

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
    maturity_score = 1 if record.maturity == "calibrated" else 0
    if mode == "exploratory":
        value_score = 2 if record.value.is_uncertain else 1 if record.value.is_exact else 0
        exploratory_score = int(
            parameter_record_is_exploratory(record)
        )
        return (
            selector_score,
            value_score,
            exploratory_score,
            maturity_score,
        )
    if mode in {"scientific", "toy"}:
        value_score = 2 if record.value.is_exact else 1 if record.value.is_uncertain else 0
        return selector_score, value_score, maturity_score
    raise ValueError(f"Unsupported parameter selection mode: {mode!r}")


def _validation_result(record_id: str, issues: list[dict[str, Any]]) -> ValidationResult:
    return ValidationResult(
        name="registry_record",
        passed=not issues,
        message="Registry record is valid." if not issues else "Registry record failed validation.",
        details={"record_id": record_id, "issues": issues},
    )


def _case_template_state_role_issues(
    state_roles: Mapping[str, str],
    *,
    field_name: str = "state_roles",
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(state_roles, Mapping) or not state_roles:
        return [{"field": field_name, "message": "Case template state roles are required."}]
    for role, state_name in state_roles.items():
        role_text = str(role).strip()
        state_text = str(state_name).strip()
        if not role_text:
            issues.append({"field": field_name, "message": "State role names must be nonempty."})
        if (
            role_text
            and role_text not in CASE_TEMPLATE_ALLOWED_STATE_ROLES
            and CASE_TEMPLATE_INDEXED_STATE_ROLE_PATTERN.fullmatch(role_text) is None
        ):
            issues.append(
                {
                    "field": f"{field_name}.{role_text}",
                    "message": "Unsupported case-template state role.",
                    "details": {
                        "allowed_roles": sorted(CASE_TEMPLATE_ALLOWED_STATE_ROLES),
                        "allowed_indexed_role_pattern": CASE_TEMPLATE_INDEXED_STATE_ROLE_PATTERN.pattern,
                    },
                }
            )
        if not state_text:
            issues.append({"field": f"{field_name}.{role_text}", "message": "State role values must be nonempty."})
    return issues


def _case_template_initial_state_issues(
    initial_state_mapping: Mapping[str, Mapping[str, Any]],
    state_roles: Mapping[str, str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(initial_state_mapping, Mapping) or not initial_state_mapping:
        return [{"field": "initial_state_mapping", "message": "Case template initial_state_mapping is required."}]
    for role, spec in initial_state_mapping.items():
        role_text = str(role).strip()
        if role_text not in state_roles:
            issues.append(
                {
                    "field": f"initial_state_mapping.{role_text}",
                    "message": "Initial-state role must reference a state_roles key.",
                }
            )
        if not isinstance(spec, Mapping):
            issues.append(
                {
                    "field": f"initial_state_mapping.{role_text}",
                    "message": "Initial-state mapping entries must be mappings.",
                }
            )
            continue
        has_parameter = bool(str(spec.get("parameter_role", "")).strip())
        has_value = spec.get("value") is not None
        if has_parameter == has_value:
            issues.append(
                {
                    "field": f"initial_state_mapping.{role_text}",
                    "message": "Initial-state mapping must define exactly one of parameter_role or value.",
                }
            )
        has_units = bool(str(spec.get("units", "")).strip())
        has_units_from_role = bool(str(spec.get("units_from_role", "")).strip())
        if has_units == has_units_from_role:
            issues.append(
                {
                    "field": f"initial_state_mapping.{role_text}",
                    "message": "Initial-state mapping must define exactly one of units or units_from_role.",
                }
            )
    return issues


def _case_template_product_map_issues(
    product_map: Mapping[str, Any],
    state_roles: Mapping[str, str],
    stoichiometric_yields: Mapping[str, float],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if "product" not in state_roles:
        return issues
    if not isinstance(product_map, Mapping) or not product_map:
        return [{"field": "product_map", "message": "Case templates with product states require product_map."}]
    for field_name in ("id", "product_map_type", "substrate_state_role", "product_state_role"):
        if not str(product_map.get(field_name, "")).strip():
            issues.append({"field": f"product_map.{field_name}", "message": "Product map field is required."})
    for field_name in ("substrate_state_role", "product_state_role"):
        role = str(product_map.get(field_name, "")).strip()
        if role and role not in state_roles:
            issues.append(
                {
                    "field": f"product_map.{field_name}",
                    "message": "Product map state role must reference state_roles.",
                }
            )
    product_map_type = str(product_map.get("product_map_type", "")).strip()
    if product_map_type not in {"one_to_one", "stoichiometric"}:
        issues.append(
            {
                "field": "product_map.product_map_type",
                "message": "Product map type must be one_to_one or stoichiometric.",
            }
        )
    if not isinstance(stoichiometric_yields, Mapping) or not stoichiometric_yields:
        issues.append(
            {
                "field": "stoichiometric_yields",
                "message": "Case templates with product states require stoichiometric_yields.",
            }
        )
    for role, value in stoichiometric_yields.items():
        role_text = str(role).strip()
        if role_text not in state_roles:
            issues.append(
                {
                    "field": f"stoichiometric_yields.{role_text}",
                    "message": "Stoichiometric-yield role must reference state_roles.",
                }
            )
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            issues.append(
                {
                    "field": f"stoichiometric_yields.{role_text}",
                    "message": "Stoichiometric yield must be numeric.",
                }
            )
            continue
        if numeric <= 0.0:
            issues.append(
                {
                    "field": f"stoichiometric_yields.{role_text}",
                    "message": "Stoichiometric yield must be positive.",
                }
            )
    return issues


def _case_template_time_grid_issues(time_grid: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(time_grid, Mapping) or not time_grid:
        return [{"field": "time_grid", "message": "Case template time_grid is required."}]
    for field_name in ("start", "stop", "points", "units"):
        if time_grid.get(field_name) is None or str(time_grid.get(field_name)).strip() == "":
            issues.append({"field": f"time_grid.{field_name}", "message": "Time-grid field is required."})
    try:
        start = float(str(time_grid.get("start", "")))
        stop = float(str(time_grid.get("stop", "")))
    except (TypeError, ValueError):
        issues.append({"field": "time_grid", "message": "Time-grid start and stop must be numeric."})
    else:
        if stop <= start:
            issues.append({"field": "time_grid.stop", "message": "Time-grid stop must be greater than start."})
    try:
        points = int(str(time_grid.get("points", "")))
    except (TypeError, ValueError):
        issues.append({"field": "time_grid.points", "message": "Time-grid points must be an integer."})
    else:
        if points < 2:
            issues.append({"field": "time_grid.points", "message": "Time-grid points must be at least 2."})
    return issues


def _case_template_output_role_issues(field_name: str, roles: Sequence[str]) -> list[dict[str, Any]]:
    if not roles:
        return [{"field": field_name, "message": "Case template observable roles are required."}]
    if any(not str(role).strip() for role in roles):
        return [{"field": field_name, "message": "Case template observable roles must be nonempty."}]
    return []


__all__ = [
    "CASE_TEMPLATE_ALLOWED_STATE_ROLES",
    "CASE_TEMPLATE_SCHEMA_VERSION",
    "CaseTemplateRecord",
    "EnzymeClassRecord",
    "EnvironmentRecord",
    "FungusRecord",
    "ParameterRecord",
    "ParameterRecordSelectionMode",
    "PARAMETER_ALLOWED_USE_EXPLORATORY",
    "PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING",
    "PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY",
    "PARAMETER_ALLOWED_USE_SCIENTIFIC",
    "PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY",
    "PARAMETER_ALLOWED_USE_STORAGE_ONLY",
    "parameter_is_simulation_authorized",
    "parameter_record_is_exploratory",
    "parameter_record_is_mode_eligible",
    "parameter_record_mode_eligibility_blocker",
    "parameter_record_selection_key",
    "parameter_simulation_authorization_blocker",
    "ProcessCompatibilityRecord",
    "RegistryRecord",
    "SubstrateRecord",
    "_tuple_of_strings",
]
