"""YAML loaders for FungMod registry records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar

import yaml

from fungal_model.core.value_spec import ValueSpec
from fungal_model.registry.records import (
    CaseTemplateRecord,
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
            case_templates=(
                _load_records(index_path, records, "case_templates", _case_template_record)
                if "case_templates" in records
                else ()
            ),
        )
    except KeyError as exc:
        raise RegistryLoadError(f"Registry index {index_path} is missing required field: {exc.args[0]}") from exc
    except RegistryValidationError:
        raise


def load_parameter_record_mapping(data: Mapping[str, Any]) -> ParameterRecord:
    """Load one parameter mapping through the production registry factory."""

    return _parameter_record(data)


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
        **_common_record_fields(data),
        enzyme_classes=_tuple_of_strings(_sequence(data.get("enzyme_classes"))),
        assimilable_products=_tuple_of_strings(_sequence(data.get("assimilable_products"))),
    )


def _enzyme_class_record(data: Mapping[str, Any]) -> EnzymeClassRecord:
    return EnzymeClassRecord(
        **_common_record_fields(data),
        target_bond_classes=_tuple_of_strings(_sequence(data.get("target_bond_classes"))),
        compatible_substrate_classes=_tuple_of_strings(_sequence(data.get("compatible_substrate_classes"))),
        compatible_processes=_tuple_of_strings(_sequence(data.get("compatible_processes"))),
    )


def _substrate_record(data: Mapping[str, Any]) -> SubstrateRecord:
    properties = data.get("properties", {}) or {}
    if not isinstance(properties, Mapping):
        properties = {}
    return SubstrateRecord(
        **_common_record_fields(data),
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
        **_common_record_fields(data),
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
        **_common_record_fields(data),
        enzyme_class=str(data.get("enzyme_class", "")),
        substrate_class=str(data.get("substrate_class", "")),
        required_bond_classes=_tuple_of_strings(_sequence(data.get("required_bond_classes"))),
        process_type=str(data.get("process_type", "")),
        required_parameters=_tuple_of_strings(_sequence(data.get("required_parameters"))),
        parameter_roles={str(role): str(symbol) for role, symbol in parameter_roles.items()},
        product_map_required=bool(data.get("product_map_required", False)),
        case_template_id=str(data.get("case_template_id", "") or ""),
    )


_COMMON_RECORD_FIELDS = {
    "record_id",
    "name",
    "maturity",
    "provenance",
    "notes",
    "display_name",
    "scientific_name",
    "aliases",
    "external_refs",
    "ec_number",
    "database_ids",
}

_CASE_TEMPLATE_FIELDS = _COMMON_RECORD_FIELDS | {
    "case_template_id",
    "schema_version",
    "process_type",
    "state_roles",
    "initial_state_mapping",
    "product_map",
    "stoichiometric_yields",
    "time_grid",
    "observable_roles",
    "output_state_roles",
    "process_state_metadata",
    "limitations",
    "validity_notes",
}

_INITIAL_STATE_MAPPING_FIELDS = {"parameter_role", "value", "units", "units_from_role", "notes"}
_PRODUCT_MAP_FIELDS = {
    "id",
    "product_map_type",
    "substrate_state_role",
    "product_state_role",
    "stoichiometric_yield",
    "notes",
}
_TIME_GRID_FIELDS = {"start", "stop", "points", "units", "notes"}


def _case_template_record(data: Mapping[str, Any]) -> CaseTemplateRecord:
    _fail_on_unknown_fields(data, allowed=_CASE_TEMPLATE_FIELDS, label="case_template")
    initial_state_mapping = _mapping(data.get("initial_state_mapping"))
    for role, spec in initial_state_mapping.items():
        if not isinstance(spec, Mapping):
            continue
        _fail_on_unknown_fields(
            spec,
            allowed=_INITIAL_STATE_MAPPING_FIELDS,
            label=f"case_template.initial_state_mapping.{role}",
        )
    product_map = _mapping(data.get("product_map"))
    _fail_on_unknown_fields(product_map, allowed=_PRODUCT_MAP_FIELDS, label="case_template.product_map")
    time_grid = _mapping(data.get("time_grid"))
    _fail_on_unknown_fields(time_grid, allowed=_TIME_GRID_FIELDS, label="case_template.time_grid")
    return CaseTemplateRecord(
        **_common_record_fields(data),
        case_template_id=str(data.get("case_template_id", "") or ""),
        schema_version=str(data.get("schema_version", "") or ""),
        process_type=str(data.get("process_type", "") or ""),
        state_roles={str(role): str(state) for role, state in _mapping(data.get("state_roles")).items()},
        initial_state_mapping={
            str(role): dict(spec)
            for role, spec in initial_state_mapping.items()
            if isinstance(spec, Mapping)
        },
        product_map=dict(product_map),
        stoichiometric_yields={
            str(role): float(value)
            for role, value in _mapping(data.get("stoichiometric_yields")).items()
        },
        time_grid=dict(time_grid),
        observable_roles=_tuple_of_strings(_sequence(data.get("observable_roles"))),
        output_state_roles={str(role): str(state) for role, state in _mapping(data.get("output_state_roles")).items()},
        process_state_metadata=dict(_mapping(data.get("process_state_metadata"))),
        limitations=_tuple_of_strings(_sequence(data.get("limitations"))),
        validity_notes=_tuple_of_strings(_sequence(data.get("validity_notes"))),
    )


def _parameter_record(data: Mapping[str, Any]) -> ParameterRecord:
    value = data.get("value")
    if not isinstance(value, Mapping):
        value = {"kind": "unknown", "units": None, "notes": "Missing value specification."}
    provenance = _provenance(data)
    maturity = _maturity(data)
    return ParameterRecord(
        **_common_record_fields(data, maturity=maturity, provenance=provenance),
        parameter_symbol=str(data.get("parameter_symbol", "")),
        process_type=str(data.get("process_type", "")),
        enzyme_class=_optional_str(data.get("enzyme_class")),
        substrate_class=_optional_str(data.get("substrate_class")),
        fungus_id=_optional_str(data.get("fungus_id")),
        substrate_id=_optional_str(data.get("substrate_id")),
        environment_id=_optional_str(data.get("environment_id")),
        value=ValueSpec.from_mapping(value),
        range_scope=_range_scope(data, provenance=provenance, maturity=maturity, value=value),
        range_interpretation=_range_interpretation(data, provenance=provenance, maturity=maturity, value=value),
        allowed_use=_allowed_use(data, provenance=provenance, maturity=maturity, value=value),
    )


def _common_record_fields(
    data: Mapping[str, Any],
    *,
    maturity: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": _record_id(data),
        "name": _name(data),
        "maturity": _maturity(data) if maturity is None else maturity,
        "provenance": _provenance(data) if provenance is None else provenance,
        "notes": _notes(data),
        "display_name": _optional_str(data.get("display_name")) or "",
        "scientific_name": _optional_str(data.get("scientific_name")) or "",
        "aliases": _tuple_of_strings(_sequence(data.get("aliases"))),
        "external_refs": _mapping(data.get("external_refs")),
        "ec_number": _optional_str(data.get("ec_number")) or "",
        "database_ids": _database_ids(data.get("database_ids")),
    }


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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _fail_on_unknown_fields(data: Mapping[str, Any], *, allowed: set[str], label: str) -> None:
    unknown = sorted(str(key) for key in data if str(key) not in allowed)
    if unknown:
        raise RegistryLoadError(
            f"Unsupported {label} field(s): {', '.join(unknown)}."
        )


def _database_ids(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): _tuple_of_strings(_sequence(raw_values))
        for key, raw_values in value.items()
    }


def _range_scope(
    data: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any],
    maturity: str,
    value: Mapping[str, Any],
) -> str:
    explicit = data.get("range_scope") or provenance.get("range_scope")
    if explicit is not None:
        return str(explicit)
    value_kind = str(value.get("kind", ""))
    if value_kind not in {"range", "distribution"}:
        return "not_applicable"
    if maturity == "exploratory_prior" or provenance.get("exploratory_prior"):
        return "user_supplied_case_prior"
    if maturity == "literature_range":
        return "literature_record_set"
    if maturity.startswith("toy"):
        return "software_test_fixture"
    return "unspecified_uncertain_value"


def _range_interpretation(
    data: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any],
    maturity: str,
    value: Mapping[str, Any],
) -> str:
    explicit = data.get("range_interpretation") or provenance.get("range_interpretation")
    if explicit is not None:
        return str(explicit)
    value_kind = str(value.get("kind", ""))
    if value_kind not in {"range", "distribution"}:
        return "not_applicable"
    if maturity == "exploratory_prior" or provenance.get("exploratory_prior"):
        return "user_supplied_exploratory_prior_not_literature_curated"
    if maturity == "literature_range":
        return "cross_entry_literature_spread_not_selected_entry_uncertainty"
    if maturity.startswith("toy"):
        return "software_test_fixture_not_scientific_uncertainty"
    return "uncertain_value_requires_interpretation_before_scientific_use"


def _allowed_use(
    data: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any],
    maturity: str,
    value: Mapping[str, Any],
) -> str:
    explicit = data.get("allowed_use") or provenance.get("allowed_use")
    if explicit is not None:
        return str(explicit)
    value_kind = str(value.get("kind", ""))
    if maturity.startswith("toy"):
        return "software_tests_only_not_scientific"
    if maturity == "exploratory_prior" or provenance.get("exploratory_prior"):
        return "exploratory_simulation_only_not_literature_curated"
    if maturity == "literature_range" or value_kind in {"range", "distribution"}:
        return "exploratory_screening_only_not_calibrated_uncertainty_not_environment_response"
    if value_kind == "unknown":
        return "preflight_and_gap_analysis_only_requires_measurement_or_curation"
    if maturity == "literature_processed" and value_kind == "exact":
        return "scientific_or_exploratory_when_all_other_inputs_are_valid"
    return "requires_record_specific_review"


def _load_mapping(path: Path) -> Mapping[str, Any]:
    data = _load_yaml(path)
    if not isinstance(data, Mapping):
        raise RegistryLoadError(f"Registry YAML must be a mapping: {path}")
    return data


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


__all__ = [
    "RegistryLoadError",
    "load_parameter_record_mapping",
    "load_registry",
]
