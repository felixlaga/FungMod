"""Shared registry-template environment modifier and environment-response helpers.

Two kinds of configured element read the static environment: rate modifiers
(declared per process under ``modifiers``) and process laws whose own rate
law needs a condition (``ph_ionization_michaelis_menten`` reads pH,
``thermal_inactivation`` reads temperature). Both are listed here so that
template assembly, environment-entity creation, and the environment-response
summary written into config provenance use one vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from fungal_model.registry.records import EnvironmentRecord
from fungal_model.registry.store import FungModRegistry

ENVIRONMENT_MODIFIER_CONDITIONS: Mapping[str, str] = {
    "temperature_arrhenius_reference": "temperature",
    "temperature_cardinal_rosso": "temperature",
    "ph_gaussian": "ph",
    "ph_cardinal_rosso": "ph",
    "oxygen_monod": "oxygen_concentration",
    "water_activity_threshold": "water_activity",
    "water_activity_cardinal_rosso_robinson": "water_activity",
}
ENVIRONMENT_MODIFIER_TYPES = frozenset(ENVIRONMENT_MODIFIER_CONDITIONS)

PROCESS_ENVIRONMENT_CONDITIONS: Mapping[str, tuple[str, ...]] = {
    "ph_ionization_michaelis_menten": ("ph",),
    "thermal_inactivation": ("temperature",),
}

ENVIRONMENT_EFFECT_STATUS_ACTIVE = "active_response_model"
ENVIRONMENT_EFFECT_STATUS_METADATA = "metadata_only"

_E = TypeVar("_E", bound=Exception)


def build_template_environment_modifier(
    *,
    template_id: str,
    parameter_symbols: Mapping[str, str],
    registry: FungModRegistry,
    environment_id: str,
    modifier: Mapping[str, Any],
    modifier_type: str,
    index: int,
    modifier_label: str,
    unresolved_label: str,
    error_type: type[_E],
) -> dict[str, Any]:
    """Build a configured environment modifier from explicit template roles."""

    del index
    condition_name = ENVIRONMENT_MODIFIER_CONDITIONS.get(modifier_type)
    if condition_name is None:
        raise error_type(f"Template {template_id!r} declares unsupported modifier type {modifier_type!r}.")
    _require_exact_environment_condition(
        registry=registry,
        environment_id=environment_id,
        condition_name=condition_name,
        modifier_type=modifier_type,
        modifier_label=modifier_label,
        error_type=error_type,
    )
    role_arguments = {
        "parameter_symbols": parameter_symbols,
        "modifier": modifier,
        "modifier_label": modifier_label,
        "unresolved_label": unresolved_label,
        "error_type": error_type,
    }
    if modifier_type == "temperature_arrhenius_reference":
        configured = {
            "type": modifier_type,
            "activation_energy_symbol": _required_modifier_role_symbol(
                role_field="activation_energy_role", **role_arguments
            ),
            "reference_temperature_symbol": _required_modifier_role_symbol(
                role_field="reference_temperature_role", **role_arguments
            ),
        }
        _add_optional_modifier_role_symbol(
            configured,
            "minimum_temperature_symbol",
            parameter_symbols=parameter_symbols,
            modifier=modifier,
            role_field="minimum_temperature_role",
            unresolved_label=unresolved_label,
            error_type=error_type,
        )
        _add_optional_modifier_role_symbol(
            configured,
            "maximum_temperature_symbol",
            parameter_symbols=parameter_symbols,
            modifier=modifier,
            role_field="maximum_temperature_role",
            unresolved_label=unresolved_label,
            error_type=error_type,
        )
        return configured
    if modifier_type == "temperature_cardinal_rosso":
        return {
            "type": modifier_type,
            "minimum_temperature_symbol": _required_modifier_role_symbol(
                role_field="minimum_temperature_role", **role_arguments
            ),
            "optimum_temperature_symbol": _required_modifier_role_symbol(
                role_field="optimum_temperature_role", **role_arguments
            ),
            "maximum_temperature_symbol": _required_modifier_role_symbol(
                role_field="maximum_temperature_role", **role_arguments
            ),
        }
    if modifier_type == "ph_gaussian":
        configured = {
            "type": modifier_type,
            "optimum_symbol": _required_modifier_role_symbol(role_field="optimum_role", **role_arguments),
            "width_symbol": _required_modifier_role_symbol(role_field="width_role", **role_arguments),
        }
        _add_optional_modifier_role_symbol(
            configured,
            "minimum_ph_symbol",
            parameter_symbols=parameter_symbols,
            modifier=modifier,
            role_field="minimum_ph_role",
            unresolved_label=unresolved_label,
            error_type=error_type,
        )
        _add_optional_modifier_role_symbol(
            configured,
            "maximum_ph_symbol",
            parameter_symbols=parameter_symbols,
            modifier=modifier,
            role_field="maximum_ph_role",
            unresolved_label=unresolved_label,
            error_type=error_type,
        )
        return configured
    if modifier_type == "ph_cardinal_rosso":
        return {
            "type": modifier_type,
            "minimum_ph_symbol": _required_modifier_role_symbol(role_field="minimum_ph_role", **role_arguments),
            "optimum_ph_symbol": _required_modifier_role_symbol(role_field="optimum_ph_role", **role_arguments),
            "maximum_ph_symbol": _required_modifier_role_symbol(role_field="maximum_ph_role", **role_arguments),
        }
    if modifier_type == "oxygen_monod":
        oxygen_units = str(modifier.get("oxygen_units", "")).strip()
        if not oxygen_units:
            raise error_type(f"{modifier_label} requires oxygen_units.")
        return {
            "type": modifier_type,
            "half_saturation_symbol": _required_modifier_role_symbol(
                role_field="half_saturation_role", **role_arguments
            ),
            "oxygen_units": oxygen_units,
        }
    if modifier_type == "water_activity_cardinal_rosso_robinson":
        return {
            "type": modifier_type,
            "minimum_water_activity_symbol": _required_modifier_role_symbol(
                role_field="minimum_water_activity_role", **role_arguments
            ),
            "optimum_water_activity_symbol": _required_modifier_role_symbol(
                role_field="optimum_water_activity_role", **role_arguments
            ),
        }
    return {
        "type": modifier_type,
        "minimum_water_activity_symbol": _required_modifier_role_symbol(
            role_field="minimum_water_activity_role", **role_arguments
        ),
    }


def build_template_environment_entity(
    *,
    registry: FungModRegistry,
    environment_id: str,
    modifiers: list[dict[str, Any]],
    error_type: type[_E],
    process_types: Sequence[str] = (),
) -> dict[str, Any] | None:
    """Build an inline configured environment entity when modifiers or process laws require one."""

    required_conditions = required_environment_conditions(modifiers, process_types=process_types)
    if not required_conditions:
        return None
    for process_type in process_types:
        for condition_name in PROCESS_ENVIRONMENT_CONDITIONS.get(process_type, ()):
            _require_exact_environment_condition(
                registry=registry,
                environment_id=environment_id,
                condition_name=condition_name,
                modifier_type=process_type,
                modifier_label=f"Process law {process_type!r}",
                error_type=error_type,
            )
    environment = registry.get_environment(environment_id)
    return {
        "id": environment_id,
        "data": {
            "kind": "environment",
            "name": environment.name,
            "provenance": {
                **dict(environment.provenance),
                "source": _environment_source(environment, required_conditions, error_type=error_type),
            },
            "conditions": {
                condition: environment.conditions[condition].to_dict()
                for condition in required_conditions
            },
            "notes": environment.notes,
        },
    }


def required_environment_conditions(
    modifiers: Sequence[Mapping[str, Any]],
    *,
    process_types: Sequence[str] = (),
) -> tuple[str, ...]:
    """Return environment condition names required by configured modifiers and process laws."""

    conditions: list[str] = []
    for process_type in process_types:
        conditions.extend(PROCESS_ENVIRONMENT_CONDITIONS.get(process_type, ()))
    for modifier in modifiers:
        if modifier.get("state_source") is not None:
            continue
        condition = ENVIRONMENT_MODIFIER_CONDITIONS.get(str(modifier.get("type", "")).strip())
        if condition is not None:
            conditions.append(condition)
    return tuple(dict.fromkeys(conditions))


def environment_response_summary(processes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize which environment conditions act on rates through explicit laws.

    The result is written into config provenance as ``environment_response`` and
    read back by the virtual-experiment tables. A condition appears only when a
    configured process law or modifier reads it; every other condition stays
    metadata. ``status`` is ``active_response_model`` when at least one law is
    bound and ``metadata_only`` otherwise.
    """

    conditions: dict[str, dict[str, Any]] = {}
    laws: list[dict[str, str]] = []
    for process in processes:
        process_id = str(process.get("id", ""))
        process_type = str(process.get("process_type", ""))
        for condition in PROCESS_ENVIRONMENT_CONDITIONS.get(process_type, ()):
            law = {"process_id": process_id, "law": process_type, "binding": "process_law"}
            laws.append(law)
            conditions.setdefault(condition, {"status": ENVIRONMENT_EFFECT_STATUS_ACTIVE, "laws": []})["laws"].append(law)
        for modifier in process.get("modifiers", ()) or ():
            if not isinstance(modifier, Mapping):
                continue
            if modifier.get("state_source") is not None:
                continue  # Dynamic states do not make EnvironmentGrid labels control rates.
            modifier_type = str(modifier.get("type", "")).strip()
            condition = ENVIRONMENT_MODIFIER_CONDITIONS.get(modifier_type)
            if condition is None:
                continue
            law = {"process_id": process_id, "law": modifier_type, "binding": "modifier"}
            laws.append(law)
            conditions.setdefault(condition, {"status": ENVIRONMENT_EFFECT_STATUS_ACTIVE, "laws": []})["laws"].append(law)
    return {
        "status": ENVIRONMENT_EFFECT_STATUS_ACTIVE if laws else ENVIRONMENT_EFFECT_STATUS_METADATA,
        "conditions": conditions,
        "laws": laws,
        "notes": (
            "Conditions listed here change rates through the named process laws or modifiers; "
            "conditions absent from this summary are metadata and do not change kinetics."
        ),
    }


def _required_modifier_role_symbol(
    *,
    parameter_symbols: Mapping[str, str],
    modifier: Mapping[str, Any],
    role_field: str,
    modifier_label: str,
    unresolved_label: str,
    error_type: type[_E],
) -> str:
    role = str(modifier.get(role_field, "")).strip()
    if not role:
        raise error_type(f"{modifier_label} requires {role_field}.")
    try:
        return parameter_symbols[role]
    except KeyError as exc:
        raise error_type(f"{unresolved_label} references unresolved {role_field} {role!r}.") from exc


def _add_optional_modifier_role_symbol(
    configured: dict[str, Any],
    symbol_field: str,
    *,
    parameter_symbols: Mapping[str, str],
    modifier: Mapping[str, Any],
    role_field: str,
    unresolved_label: str,
    error_type: type[_E],
) -> None:
    role = str(modifier.get(role_field, "")).strip()
    if not role:
        return
    try:
        configured[symbol_field] = parameter_symbols[role]
    except KeyError as exc:
        raise error_type(f"{unresolved_label} references unresolved {role_field} {role!r}.") from exc


def _require_exact_environment_condition(
    *,
    registry: FungModRegistry,
    environment_id: str,
    condition_name: str,
    modifier_type: str,
    modifier_label: str,
    error_type: type[_E],
) -> None:
    environment = registry.get_environment(environment_id)
    value = environment.conditions.get(condition_name)
    if value is None:
        raise error_type(
            f"{modifier_label} {modifier_type!r} requires environment condition {condition_name!r} "
            f"in environment {environment_id!r}."
        )
    if not value.is_exact:
        raise error_type(
            f"{modifier_label} {modifier_type!r} requires exact environment condition {condition_name!r}; "
            f"environment {environment_id!r} has ValueSpec kind {value.kind!r}."
        )
    validation = value.validate(nonnegative=condition_name in {"oxygen_concentration", "water_activity"})
    if not validation.passed or value.value is None or value.units is None:
        raise error_type(
            f"Environment condition {condition_name!r} for environment {environment_id!r} "
            f"failed exact ValueSpec validation: {validation.to_dict()}."
        )


def _environment_source(
    environment: EnvironmentRecord,
    required_conditions: tuple[str, ...],
    *,
    error_type: type[_E],
) -> str:
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
    raise error_type(
        f"Environment record {environment.record_id!r} cannot provide a source for configured "
        "environment modifier assembly."
    )


__all__ = [
    "ENVIRONMENT_EFFECT_STATUS_ACTIVE",
    "ENVIRONMENT_EFFECT_STATUS_METADATA",
    "ENVIRONMENT_MODIFIER_CONDITIONS",
    "ENVIRONMENT_MODIFIER_TYPES",
    "PROCESS_ENVIRONMENT_CONDITIONS",
    "build_template_environment_entity",
    "build_template_environment_modifier",
    "environment_response_summary",
    "required_environment_conditions",
]
