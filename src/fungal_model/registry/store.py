"""In-memory registry store and lookup helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fungal_model.registry.records import (
    CaseTemplateRecord,
    EnzymeClassRecord,
    EnvironmentRecord,
    FungusRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    PROCESS_COMPATIBILITY_SCOPE_COMPONENT,
    PROCESS_COMPATIBILITY_SCOPE_STANDALONE,
    SubstrateRecord,
)


class RegistryLookupError(KeyError):
    """Raised when a registry lookup cannot be satisfied."""


class RegistryValidationError(ValueError):
    """Raised when registry records are invalid or duplicated."""


@dataclass(frozen=True)
class _ProcessCompatibilityAuthorityGraph:
    component_record_ids: frozenset[str]
    components_by_outer: Mapping[
        str,
        tuple[tuple[str, ProcessCompatibilityRecord], ...],
    ]


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
        registry = cls(
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
        registry.validate_process_compatibility_authority_graph()
        return registry

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
        graph = self._process_compatibility_authority_graph()
        records = tuple(
            record
            for record in self.process_compatibility.values()
            if record.record_id not in graph.component_record_ids
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

    def validate_process_compatibility_authority_graph(self) -> None:
        """Fail unless component compatibilities form one closed ownership graph."""

        self._process_compatibility_authority_graph()

    def get_process_component_authorities(
        self,
        outer_record_id: str,
        *,
        template: CaseTemplateRecord | None = None,
    ) -> Mapping[str, ProcessCompatibilityRecord]:
        """Return validated component authorities for one bound outer record."""

        graph = self._process_compatibility_authority_graph()
        try:
            authorities = graph.components_by_outer[outer_record_id]
            outer = self.process_compatibility[outer_record_id]
        except KeyError as exc:
            raise RegistryLookupError(
                f"Process compatibility {outer_record_id!r} has no component authorities."
            ) from exc
        if template is not None:
            if template.case_template_id != outer.case_template_id:
                raise RegistryValidationError(
                    f"Process compatibility {outer_record_id!r} and case template "
                    f"{template.case_template_id!r} disagree."
                )
            expected = _template_process_signature(template)
            actual = tuple(
                (process_id, component.process_type)
                for process_id, component in authorities
            )
            if expected != actual:
                raise RegistryValidationError(
                    f"Case template {template.case_template_id!r} process structure "
                    "disagrees with its validated component authority graph."
                )
        return dict(authorities)

    def _process_compatibility_authority_graph(
        self,
    ) -> _ProcessCompatibilityAuthorityGraph:
        component_record_ids: set[str] = set()
        owners: dict[str, list[tuple[str, str]]] = {}
        components_by_outer: dict[
            str,
            tuple[tuple[str, ProcessCompatibilityRecord], ...],
        ] = {}
        for record in self.process_compatibility.values():
            validation = record.validate()
            if not validation.passed:
                raise RegistryValidationError(
                    f"Invalid process compatibility record {record.record_id!r}: "
                    f"{validation.details}"
                )
            if record.compatibility_scope == PROCESS_COMPATIBILITY_SCOPE_COMPONENT:
                component_record_ids.add(record.record_id)
                if record.case_template_id or record.component_bindings:
                    raise RegistryValidationError(
                        f"Component-only process compatibility {record.record_id!r} cannot "
                        "declare case_template_id or component_bindings."
                    )
                if not _has_complete_parameter_roles(record):
                    raise RegistryValidationError(
                        f"Component-only process compatibility {record.record_id!r} must "
                        "bind every required parameter through one exact semantic role."
                    )

        for outer in self.process_compatibility.values():
            if not outer.component_bindings:
                continue
            if outer.compatibility_scope != PROCESS_COMPATIBILITY_SCOPE_STANDALONE:
                raise RegistryValidationError(
                    f"Component owner {outer.record_id!r} must have standalone scope."
                )
            if not outer.case_template_id:
                raise RegistryValidationError(
                    f"Component owner {outer.record_id!r} must declare case_template_id."
                )
            template = self.case_templates.get(outer.case_template_id)
            if template is None:
                raise RegistryValidationError(
                    f"Component owner {outer.record_id!r} references missing case template "
                    f"{outer.case_template_id!r}."
                )
            if not _has_complete_parameter_roles(outer):
                raise RegistryValidationError(
                    f"Component owner {outer.record_id!r} must bind every required "
                    "parameter through one exact role."
                )
            expected = _template_process_signature(template)
            actual_ids = tuple(
                binding.process_template_id for binding in outer.component_bindings
            )
            if actual_ids != tuple(process_id for process_id, _ in expected):
                raise RegistryValidationError(
                    f"Component owner {outer.record_id!r} bindings must cover the exact "
                    "ordered case-template process IDs."
                )
            resolved: list[tuple[str, ProcessCompatibilityRecord]] = []
            for binding, (process_id, process_type) in zip(
                outer.component_bindings,
                expected,
                strict=True,
            ):
                component = self.process_compatibility.get(
                    binding.compatibility_record_id
                )
                if component is None:
                    raise RegistryValidationError(
                        f"Component owner {outer.record_id!r} references missing component "
                        f"compatibility {binding.compatibility_record_id!r}."
                    )
                if component.compatibility_scope != PROCESS_COMPATIBILITY_SCOPE_COMPONENT:
                    raise RegistryValidationError(
                        f"Component owner {outer.record_id!r} must reference intrinsic "
                        f"component-only compatibility {component.record_id!r}."
                    )
                if component.process_type != process_type:
                    raise RegistryValidationError(
                        f"Component compatibility {component.record_id!r} process_type "
                        f"does not match process template {process_id!r}."
                    )
                owners.setdefault(component.record_id, []).append(
                    (outer.record_id, process_id)
                )
                resolved.append((process_id, component))
            components_by_outer[outer.record_id] = tuple(resolved)

        for component_id in sorted(component_record_ids):
            component_owners = owners.get(component_id, [])
            if len(component_owners) != 1:
                raise RegistryValidationError(
                    f"Component-only process compatibility {component_id!r} must have "
                    f"exactly one owner binding; found {len(component_owners)}."
                )
        return _ProcessCompatibilityAuthorityGraph(
            component_record_ids=frozenset(component_record_ids),
            components_by_outer=components_by_outer,
        )

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


def _template_process_signature(
    template: CaseTemplateRecord,
) -> tuple[tuple[str, str], ...]:
    raw_processes = template.process_state_metadata.get("process_templates")
    if not isinstance(raw_processes, Sequence) or isinstance(
        raw_processes,
        (str, bytes),
    ):
        raise RegistryValidationError(
            f"Case template {template.case_template_id!r} process_templates must be a sequence."
        )
    signature: list[tuple[str, str]] = []
    process_ids: set[str] = set()
    for index, raw_process in enumerate(raw_processes):
        if not isinstance(raw_process, Mapping):
            raise RegistryValidationError(
                f"Case template {template.case_template_id!r} process_templates[{index}] "
                "must be a mapping."
            )
        process_id = raw_process.get("id")
        process_type = raw_process.get("process_type")
        if (
            not isinstance(process_id, str)
            or not process_id
            or process_id != process_id.strip()
        ):
            raise RegistryValidationError(
                f"Case template {template.case_template_id!r} process_templates[{index}].id "
                "must be nonblank text."
            )
        if process_id in process_ids:
            raise RegistryValidationError(
                f"Case template {template.case_template_id!r} process id {process_id!r} "
                "must be unique."
            )
        if (
            not isinstance(process_type, str)
            or not process_type
            or process_type != process_type.strip()
        ):
            raise RegistryValidationError(
                f"Case template {template.case_template_id!r} process {process_id!r} "
                "must declare nonblank process_type."
            )
        process_ids.add(process_id)
        signature.append((process_id, process_type))
    if not signature:
        raise RegistryValidationError(
            f"Case template {template.case_template_id!r} bound process_templates cannot be empty."
        )
    return tuple(signature)


def _has_complete_parameter_roles(record: ProcessCompatibilityRecord) -> bool:
    return bool(record.required_parameters) and bool(record.parameter_roles) and set(
        record.required_parameters
    ) == set(record.parameter_roles.values())


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
