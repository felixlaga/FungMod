"""YAML loaders for FungMod registry records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar

import yaml

from fungal_model.core.value_spec import ValueSpec
from fungal_model.registry.records import (
    EnzymeClassRecord,
    EnvironmentRecord,
    FungusRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
    _tuple_of_strings,
)
from fungal_model.registry.store import FungModRegistry, RegistryValidationError

T = TypeVar("T")


class RegistryLoadError(ValueError):
    """Raised when a registry index or record file cannot be loaded."""


def load_registry(path: str | Path) -> FungModRegistry:
    """Load a FungMod registry from a registry index YAML file."""

    index_path = Path(path)
    data = _load_mapping(index_path)
    if data.get("kind") != "fungmod_registry_index":
        raise RegistryLoadError(f"Registry index {index_path} must use kind: fungmod_registry_index.")
    records = data.get("records")
    if not isinstance(records, Mapping):
        raise RegistryLoadError(f"Registry index {index_path} requires a records mapping.")
    try:
        return FungModRegistry.build(
            registry_id=str(data["registry_id"]),
            version=str(data["version"]),
            maturity=str(data.get("maturity", "development")),
            provenance=dict(data.get("provenance", {})),
            fungi=_load_records(index_path, records, "fungi", _fungus_record),
            enzyme_classes=_load_records(index_path, records, "enzyme_classes", _enzyme_class_record),
            substrates=_load_records(index_path, records, "substrates", _substrate_record),
            environments=_load_records(index_path, records, "environments", _environment_record),
            process_compatibility=_load_records(
                index_path,
                records,
                "process_compatibility",
                _process_compatibility_record,
            ),
            parameters=_load_records(index_path, records, "parameters", _parameter_record),
        )
    except KeyError as exc:
        raise RegistryLoadError(f"Registry index {index_path} is missing required field: {exc.args[0]}") from exc
    except RegistryValidationError:
        raise


def _load_records(
    index_path: Path,
    records: Mapping[Any, Any],
    key: str,
    factory: Callable[[Mapping[str, Any]], T],
) -> tuple[T, ...]:
    if key not in records:
        raise RegistryLoadError(f"Registry index {index_path} is missing records.{key}.")
    record_path = _resolve_registry_path(index_path, str(records[key]))
    loaded = _load_yaml(record_path)
    if isinstance(loaded, Mapping):
        raw_records = loaded.get("records")
    else:
        raw_records = loaded
    if not isinstance(raw_records, list):
        raise RegistryLoadError(f"Registry record file {record_path} must contain a records list.")
    output: list[T] = []
    for index, item in enumerate(raw_records):
        if not isinstance(item, Mapping):
            raise RegistryLoadError(f"Registry record {record_path}:{index} must be a mapping.")
        output.append(factory(item))
    return tuple(output)


def _resolve_registry_path(index_path: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = index_path.parent / candidate
    if not candidate.exists():
        raise RegistryLoadError(f"Referenced registry file does not exist: {candidate}")
    return candidate


def _fungus_record(data: Mapping[str, Any]) -> FungusRecord:
    return FungusRecord(
        record_id=_record_id(data),
        name=_name(data),
        maturity=_maturity(data),
        provenance=_provenance(data),
        notes=_notes(data),
        enzyme_classes=_tuple_of_strings(_sequence(data.get("enzyme_classes"))),
        assimilable_products=_tuple_of_strings(_sequence(data.get("assimilable_products"))),
    )


def _enzyme_class_record(data: Mapping[str, Any]) -> EnzymeClassRecord:
    return EnzymeClassRecord(
        record_id=_record_id(data),
        name=_name(data),
        maturity=_maturity(data),
        provenance=_provenance(data),
        notes=_notes(data),
        target_bond_classes=_tuple_of_strings(_sequence(data.get("target_bond_classes"))),
        compatible_substrate_classes=_tuple_of_strings(_sequence(data.get("compatible_substrate_classes"))),
        compatible_processes=_tuple_of_strings(_sequence(data.get("compatible_processes"))),
    )


def _substrate_record(data: Mapping[str, Any]) -> SubstrateRecord:
    properties = data.get("properties", {}) or {}
    if not isinstance(properties, Mapping):
        properties = {}
    return SubstrateRecord(
        record_id=_record_id(data),
        name=_name(data),
        maturity=_maturity(data),
        provenance=_provenance(data),
        notes=_notes(data),
        substrate_class=str(data.get("substrate_class", "")),
        physical_state=str(data.get("physical_state", "")),
        bond_classes=_tuple_of_strings(_sequence(data.get("bond_classes"))),
        products=_tuple_of_strings(_sequence(data.get("products"))),
        properties={
            str(key): ValueSpec.from_mapping(value)
            for key, value in properties.items()
            if isinstance(value, Mapping)
        },
    )


def _environment_record(data: Mapping[str, Any]) -> EnvironmentRecord:
    conditions = data.get("conditions", {}) or {}
    if not isinstance(conditions, Mapping):
        conditions = {}
    return EnvironmentRecord(
        record_id=_record_id(data),
        name=_name(data),
        maturity=_maturity(data),
        provenance=_provenance(data),
        notes=_notes(data),
        conditions={
            str(key): ValueSpec.from_mapping(value)
            for key, value in conditions.items()
            if isinstance(value, Mapping)
        },
    )


def _process_compatibility_record(data: Mapping[str, Any]) -> ProcessCompatibilityRecord:
    parameter_roles = data.get("parameter_roles", {}) or {}
    if not isinstance(parameter_roles, Mapping):
        parameter_roles = {}
    return ProcessCompatibilityRecord(
        record_id=_record_id(data),
        name=_name(data),
        maturity=_maturity(data),
        provenance=_provenance(data),
        notes=_notes(data),
        enzyme_class=str(data.get("enzyme_class", "")),
        substrate_class=str(data.get("substrate_class", "")),
        required_bond_classes=_tuple_of_strings(_sequence(data.get("required_bond_classes"))),
        process_type=str(data.get("process_type", "")),
        required_parameters=_tuple_of_strings(_sequence(data.get("required_parameters"))),
        parameter_roles={str(role): str(symbol) for role, symbol in parameter_roles.items()},
        product_map_required=bool(data.get("product_map_required", False)),
    )


def _parameter_record(data: Mapping[str, Any]) -> ParameterRecord:
    value = data.get("value")
    if not isinstance(value, Mapping):
        value = {"kind": "unknown", "units": None, "notes": "Missing value specification."}
    return ParameterRecord(
        record_id=_record_id(data),
        name=_name(data),
        maturity=_maturity(data),
        provenance=_provenance(data),
        notes=_notes(data),
        parameter_symbol=str(data.get("parameter_symbol", "")),
        process_type=str(data.get("process_type", "")),
        enzyme_class=_optional_str(data.get("enzyme_class")),
        substrate_class=_optional_str(data.get("substrate_class")),
        fungus_id=_optional_str(data.get("fungus_id")),
        substrate_id=_optional_str(data.get("substrate_id")),
        environment_id=_optional_str(data.get("environment_id")),
        value=ValueSpec.from_mapping(value),
    )


def _record_id(data: Mapping[str, Any]) -> str:
    return str(data.get("record_id", ""))


def _name(data: Mapping[str, Any]) -> str:
    return str(data.get("name", ""))


def _maturity(data: Mapping[str, Any]) -> str:
    return str(data.get("maturity", ""))


def _provenance(data: Mapping[str, Any]) -> Mapping[str, Any]:
    provenance = data.get("provenance", {})
    return provenance if isinstance(provenance, Mapping) else {}


def _notes(data: Mapping[str, Any]) -> str:
    return str(data.get("notes", "") or "")


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _load_mapping(path: Path) -> Mapping[str, Any]:
    data = _load_yaml(path)
    if not isinstance(data, Mapping):
        raise RegistryLoadError(f"Registry YAML must be a mapping: {path}")
    return data


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


__all__ = [
    "RegistryLoadError",
    "load_registry",
]
