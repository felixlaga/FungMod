"""Registry record objects for plug-and-play FungMod metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from fungal_model.core.validators import ValidationResult
from fungal_model.core.value_spec import ValueSpec


def _tuple_of_strings(values: Sequence[Any] | None) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()))


@dataclass(frozen=True)
class RegistryRecord:
    """Common metadata required for all registry records."""

    record_id: str
    name: str
    maturity: str
    provenance: Mapping[str, Any]
    notes: str

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
        return {
            "record_id": self.record_id,
            "name": self.name,
            "maturity": self.maturity,
            "provenance": dict(self.provenance),
            "notes": self.notes,
        }


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
class ProcessCompatibilityRecord(RegistryRecord):
    """Record describing when a process type is categorically compatible."""

    enzyme_class: str = ""
    substrate_class: str = ""
    required_bond_classes: tuple[str, ...] = ()
    process_type: str = ""
    required_parameters: tuple[str, ...] = ()
    parameter_roles: Mapping[str, str] = field(default_factory=dict)
    product_map_required: bool = False

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


def _validation_result(record_id: str, issues: list[dict[str, Any]]) -> ValidationResult:
    return ValidationResult(
        name="registry_record",
        passed=not issues,
        message="Registry record is valid." if not issues else "Registry record failed validation.",
        details={"record_id": record_id, "issues": issues},
    )


__all__ = [
    "EnzymeClassRecord",
    "EnvironmentRecord",
    "FungusRecord",
    "ParameterRecord",
    "ProcessCompatibilityRecord",
    "RegistryRecord",
    "SubstrateRecord",
    "_tuple_of_strings",
]
