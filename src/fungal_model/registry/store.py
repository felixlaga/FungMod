"""In-memory registry store and lookup helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fungal_model.registry.records import (
    CaseTemplateRecord,
    EnzymeClassRecord,
    EnvironmentRecord,
    FungusRecord,
    ParameterRecord,
    ProcessComponentBinding,
    ProcessCompatibilityRecord,
    SubstrateRecord,
)


class RegistryLookupError(KeyError):
    """Raised when a registry lookup cannot be satisfied."""


class RegistryValidationError(ValueError):
    """Raised when registry records are invalid or duplicated."""


@dataclass(frozen=True)
class FungModRegistry:
    """Loaded FungMod registry records."""

    registry_id: str
    version: str
    maturity: str
    provenance: dict[str, Any]
    fungi: dict[str, FungusRecord]
    enzyme_classes: dict[str, EnzymeClassRecord]
    substrates: dict[str, SubstrateRecord]
    environments: dict[str, EnvironmentRecord]
    process_compatibility: dict[str, ProcessCompatibilityRecord]
    parameters: dict[str, ParameterRecord]
    case_templates: dict[str, CaseTemplateRecord]

    @classmethod
    def build(
        cls,
        *,
        registry_id: str,
        version: str,
        maturity: str,
        provenance: dict[str, Any],
        fungi: Iterable[FungusRecord],
        enzyme_classes: Iterable[EnzymeClassRecord],
        substrates: Iterable[SubstrateRecord],
        environments: Iterable[EnvironmentRecord],
        process_compatibility: Iterable[ProcessCompatibilityRecord],
        parameters: Iterable[ParameterRecord],
        case_templates: Iterable[CaseTemplateRecord] = (),
    ) -> "FungModRegistry":
        return cls(
            registry_id=registry_id,
            version=version,
            maturity=maturity,
            provenance=dict(provenance),
            fungi=_records_by_id(fungi, "fungi"),
            enzyme_classes=_records_by_id(enzyme_classes, "enzyme_classes"),
            substrates=_records_by_id(substrates, "substrates"),
            environments=_records_by_id(environments, "environments"),
            process_compatibility=_records_by_id(process_compatibility, "process_compatibility"),
            parameters=_records_by_id(parameters, "parameters"),
            case_templates=_records_by_id(case_templates, "case_templates"),
        )

    def get_fungus(self, record_id: str) -> FungusRecord:
        return _lookup(self.fungi, record_id, "fungus")

    def get_enzyme_class(self, record_id: str) -> EnzymeClassRecord:
        return _lookup(self.enzyme_classes, record_id, "enzyme class")

    def get_substrate(self, record_id: str) -> SubstrateRecord:
        return _lookup(self.substrates, record_id, "substrate")

    def get_environment(self, record_id: str) -> EnvironmentRecord:
        return _lookup(self.environments, record_id, "environment")

    def get_case_template(self, record_id: str) -> CaseTemplateRecord:
        return _lookup(self.case_templates, record_id, "case template")

    def get_process_compatibility(
        self,
        *,
        enzyme_class: str | None = None,
        substrate_class: str | None = None,
        process_type: str | None = None,
    ) -> tuple[ProcessCompatibilityRecord, ...]:
        component_record_ids: set[str] = set()
        for outer_record in self.process_compatibility.values():
            if not isinstance(outer_record.component_bindings, tuple) or any(
                not isinstance(binding, ProcessComponentBinding)
                for binding in outer_record.component_bindings
            ):
                raise RegistryValidationError(
                    f"Invalid component bindings on process compatibility "
                    f"{outer_record.record_id!r}."
                )
            component_record_ids.update(
                binding.compatibility_record_id
                for binding in outer_record.component_bindings
            )
        records = tuple(
            record
            for record in self.process_compatibility.values()
            if record.record_id not in component_record_ids
            and (enzyme_class is None or record.enzyme_class == enzyme_class)
            and (substrate_class is None or record.substrate_class == substrate_class)
            and (process_type is None or record.process_type == process_type)
        )
        if not records:
            raise RegistryLookupError(
                "No process compatibility records matched "
                f"enzyme_class={enzyme_class!r}, substrate_class={substrate_class!r}, process_type={process_type!r}."
            )
        return records

    def get_parameter_records(
        self,
        *,
        parameter_symbol: str | None = None,
        process_type: str | None = None,
        enzyme_class: str | None = None,
        substrate_class: str | None = None,
        fungus_id: str | None = None,
        substrate_id: str | None = None,
        environment_id: str | None = None,
        maturity: str | None = None,
    ) -> tuple[ParameterRecord, ...]:
        records = tuple(
            record
            for record in self.parameters.values()
            if (parameter_symbol is None or record.parameter_symbol == parameter_symbol)
            and (process_type is None or record.process_type == process_type)
            and (enzyme_class is None or record.enzyme_class == enzyme_class)
            and (substrate_class is None or record.substrate_class == substrate_class)
            and (fungus_id is None or record.fungus_id == fungus_id)
            and (substrate_id is None or record.substrate_id == substrate_id)
            and (environment_id is None or record.environment_id == environment_id)
            and (maturity is None or record.maturity == maturity)
        )
        if not records:
            raise RegistryLookupError(
                "No parameter records matched "
                f"parameter_symbol={parameter_symbol!r}, process_type={process_type!r}, "
                f"enzyme_class={enzyme_class!r}, substrate_class={substrate_class!r}."
            )
        return records

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_registry",
            "registry_id": self.registry_id,
            "version": self.version,
            "maturity": self.maturity,
            "provenance": dict(self.provenance),
            "records": {
                "fungi": [record.to_dict() for record in self.fungi.values()],
                "enzyme_classes": [record.to_dict() for record in self.enzyme_classes.values()],
                "substrates": [record.to_dict() for record in self.substrates.values()],
                "environments": [record.to_dict() for record in self.environments.values()],
                "process_compatibility": [record.to_dict() for record in self.process_compatibility.values()],
                "parameters": [record.to_dict() for record in self.parameters.values()],
                "case_templates": [record.to_dict() for record in self.case_templates.values()],
            },
        }


def _records_by_id(records: Iterable[Any], label: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for record in records:
        validation = record.validate()
        if not validation.passed:
            raise RegistryValidationError(f"Invalid {label} record {record.record_id!r}: {validation.details}")
        if record.record_id in output:
            raise RegistryValidationError(f"Duplicate registry record id in {label}: {record.record_id}")
        output[record.record_id] = record
    return output


def _lookup(records: dict[str, Any], record_id: str, label: str) -> Any:
    try:
        return records[record_id]
    except KeyError as exc:
        raise RegistryLookupError(f"Unknown {label} registry record id: {record_id}") from exc


__all__ = [
    "FungModRegistry",
    "RegistryLookupError",
    "RegistryValidationError",
]
