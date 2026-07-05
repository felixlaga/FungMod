"""Shared registry-template environment modifier assembly helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from fungal_model.registry.records import EnvironmentRecord
from fungal_model.registry.store import FungModRegistry


ENVIRONMENT_MODIFIER_TYPES = frozenset(
    {
        "temperature_arrhenius_reference",
        "ph_gaussian",
        "oxygen_monod",
        "water_activity_threshold",
    }
)

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

    if modifier_type == "temperature_arrhenius_reference":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="temperature",
            modifier_type=modifier_type,
            modifier_label=modifier_label,
            error_type=error_type,
        )
        configured = {
            "type": modifier_type,
            "activation_energy_symbol": _required_modifier_role_symbol(
                parameter_symbols=parameter_symbols,
                modifier=modifier,
                role_field="activation_energy_role",
                modifier_label=modifier_label,
                unresolved_label=unresolved_label,
                error_type=error_type,
            ),
            "reference_temperature_symbol": _required_modifier_role_symbol(
                parameter_symbols=parameter_symbols,
                modifier=modifier,
                role_field="reference_temperature_role",
                modifier_label=modifier_label,
                unresolved_label=unresolved_label,
                error_type=error_type,
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
    if modifier_type == "ph_gaussian":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="ph",
            modifier_type=modifier_type,
            modifier_label=modifier_label,
            error_type=error_type,
        )
        configured = {
            "type": modifier_type,
            "optimum_symbol": _required_modifier_role_symbol(
                parameter_symbols=parameter_symbols,
                modifier=modifier,
                role_field="optimum_role",
                modifier_label=modifier_label,
                unresolved_label=unresolved_label,
                error_type=error_type,
            ),
            "width_symbol": _required_modifier_role_symbol(
                parameter_symbols=parameter_symbols,
                modifier=modifier,
                role_field="width_role",
                modifier_label=modifier_label,
                unresolved_label=unresolved_label,
                error_type=error_type,
            ),
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
    if modifier_type == "oxygen_monod":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="oxygen_concentration",
            modifier_type=modifier_type,
            modifier_label=modifier_label,
            error_type=error_type,
        )
        oxygen_units = str(modifier.get("oxygen_units", "")).strip()
        if not oxygen_units:
            raise error_type(f"{modifier_label} requires oxygen_units.")
        return {
            "type": modifier_type,
            "half_saturation_symbol": _required_modifier_role_symbol(
                parameter_symbols=parameter_symbols,
                modifier=modifier,
                role_field="half_saturation_role",
                modifier_label=modifier_label,
                unresolved_label=unresolved_label,
                error_type=error_type,
            ),
            "oxygen_units": oxygen_units,
        }
    if modifier_type == "water_activity_threshold":
        _require_exact_environment_condition(
            registry=registry,
            environment_id=environment_id,
            condition_name="water_activity",
            modifier_type=modifier_type,
            modifier_label=modifier_label,
            error_type=error_type,
        )
        return {
            "type": modifier_type,
            "minimum_water_activity_symbol": _required_modifier_role_symbol(
                parameter_symbols=parameter_symbols,
                modifier=modifier,
                role_field="minimum_water_activity_role",
                modifier_label=modifier_label,
                unresolved_label=unresolved_label,
                error_type=error_type,
            ),
        }
    raise error_type(f"Template {template_id!r} declares unsupported modifier type {modifier_type!r}.")


def build_template_environment_entity(
    *,
    registry: FungModRegistry,
    environment_id: str,
    modifiers: list[dict[str, Any]],
    error_type: type[_E],
) -> dict[str, Any] | None:
    """Build an inline configured environment entity when modifiers require one."""

    required_conditions = required_environment_conditions(modifiers)
    if not required_conditions:
        return None
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


def required_environment_conditions(modifiers: list[dict[str, Any]]) -> tuple[str, ...]:
    """Return environment condition names required by configured modifiers."""

    conditions: list[str] = []
    for modifier in modifiers:
        modifier_type = str(modifier.get("type", "")).strip()
        if modifier_type == "temperature_arrhenius_reference":
            conditions.append("temperature")
        elif modifier_type == "ph_gaussian":
            conditions.append("ph")
        elif modifier_type == "oxygen_monod":
            conditions.append("oxygen_concentration")
        elif modifier_type == "water_activity_threshold":
            conditions.append("water_activity")
    return tuple(dict.fromkeys(conditions))


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
