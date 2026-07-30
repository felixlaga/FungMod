"""Fail-closed assembly of dynamic thermodynamic solver constraints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from fungal_model.chemistry.thermodynamics import (
    DynamicActivityParticipant,
    DynamicThermodynamicConstraint,
)
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, assert_compatible
from fungal_model.core.validators import ValidationResult
from fungal_model.io.model_config import (
    BalanceCheckConfig,
    ModelConfig,
    ReactionMetadataConfig,
    ThermodynamicConstraintConfig,
)


_ENFORCEMENT_MODE = "block_unfavorable_forward_rate"
_ACTIVITY_MODEL = "ideal_dilute_concentration_ratio_with_explicit_floor"
_CONSTRAINT_FIELDS = {
    "id",
    "process_id",
    "reaction_id",
    "electron_balance_check_id",
    "enforcement_mode",
    "standard_energy",
    "temperature",
    "gas_constant",
    "activity_model",
    "absolute_tolerance",
    "provenance_refs",
}
_PARAMETER_FIELDS = {
    "name",
    "symbol",
    "value",
    "units",
    "uncertainty",
    "source",
    "confidence_level",
    "notes",
    "measurement_method",
    "validity_range",
}


def configured_dynamic_thermodynamic_constraints(
    config: ModelConfig,
    *,
    processes: Sequence[Any],
    state_units: Mapping[str, str],
    static_balance_validations: Sequence[ValidationResult],
) -> tuple[DynamicThermodynamicConstraint, ...]:
    """Assemble explicit dynamic constraints after static binding/balance checks."""

    if not config.thermodynamic_constraints:
        return ()
    process_names = [str(getattr(process, "name", "")) for process in processes]
    if len(set(process_names)) != len(process_names):
        raise ValueError(
            "Dynamic thermodynamic constraints require unique assembled process ids."
        )
    reactions = _unique_by_id(
        config.reaction_metadata,
        attribute="id",
        collection="reaction_metadata",
    )
    balance_checks = _unique_by_id(
        config.balance_checks,
        attribute="id",
        collection="balance_checks",
    )
    constraints: list[DynamicThermodynamicConstraint] = []
    constraint_ids: set[str] = set()
    constrained_processes: set[str] = set()
    for item in config.thermodynamic_constraints:
        if item.id in constraint_ids:
            raise ValueError(
                f"Duplicate dynamic thermodynamic constraint id {item.id!r}."
            )
        if item.process_id in constrained_processes:
            raise ValueError(
                f"Process {item.process_id!r} has more than one dynamic "
                "thermodynamic constraint; at most one is supported."
            )
        if item.process_id not in process_names:
            raise ValueError(
                f"Dynamic thermodynamic constraint {item.id!r} references "
                f"unknown assembled process {item.process_id!r}."
            )
        reaction = reactions.get(item.reaction_id)
        if reaction is None:
            raise ValueError(
                f"Dynamic thermodynamic constraint {item.id!r} references "
                f"unknown reaction metadata {item.reaction_id!r}."
            )
        balance_check = balance_checks.get(item.electron_balance_check_id)
        if balance_check is None:
            raise ValueError(
                f"Dynamic thermodynamic constraint {item.id!r} references "
                f"unknown electron balance check {item.electron_balance_check_id!r}."
            )
        binding = _required_passing_electron_binding(
            item=item,
            balance_check=balance_check,
            validations=static_balance_validations,
        )
        constraint = _constraint_from_config(
            item=item,
            reaction=reaction,
            binding=binding,
            state_units=state_units,
        )
        if (
            constraint.standard_energy_method == "redox_potential"
            and "redox" not in balance_check.checks
        ):
            raise ValueError(
                f"Dynamic redox constraint {item.id!r} requires its bound "
                "balance check to request the explicit 'redox' check type."
            )
        constraint.validate()
        constraints.append(constraint)
        constraint_ids.add(item.id)
        constrained_processes.add(item.process_id)
    return tuple(constraints)


def _constraint_from_config(
    *,
    item: ThermodynamicConstraintConfig,
    reaction: ReactionMetadataConfig,
    binding: Mapping[str, Any],
    state_units: Mapping[str, str],
) -> DynamicThermodynamicConstraint:
    raw = _closed_mapping(
        item.raw,
        allowed=_CONSTRAINT_FIELDS,
        required=_CONSTRAINT_FIELDS,
        field_name=f"thermodynamic_constraints.{item.id}",
    )
    if item.enforcement_mode != _ENFORCEMENT_MODE:
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} has unsupported "
            f"enforcement_mode {item.enforcement_mode!r}; expected {_ENFORCEMENT_MODE!r}."
        )
    participants = _participants(
        item=item,
        reaction=reaction,
        binding=binding,
        state_units=state_units,
        standard_concentration=_parameter(
            raw["activity_model"],
            nested_key="standard_concentration",
            field_name=f"thermodynamic_constraints.{item.id}.activity_model",
        ),
    )
    activity = _closed_mapping(
        raw["activity_model"],
        allowed={"type", "standard_concentration", "minimum_activity"},
        required={"type", "standard_concentration", "minimum_activity"},
        field_name=f"thermodynamic_constraints.{item.id}.activity_model",
    )
    activity_type = str(activity["type"]).strip()
    if activity_type != _ACTIVITY_MODEL:
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} has unsupported "
            f"activity_model.type {activity_type!r}; expected {_ACTIVITY_MODEL!r}."
        )
    standard_concentration = _parameter_mapping(
        activity["standard_concentration"],
        field_name=f"thermodynamic_constraints.{item.id}.activity_model.standard_concentration",
    )
    assert_compatible(
        Q_(1.0, standard_concentration.units),
        "mole / liter",
        name="standard_concentration",
    )
    minimum_activity = _parameter_mapping(
        activity["minimum_activity"],
        field_name=f"thermodynamic_constraints.{item.id}.activity_model.minimum_activity",
    )
    standard_energy = _closed_mapping(
        raw["standard_energy"],
        allowed={
            "method",
            "standard_delta_gibbs",
            "standard_redox_potential",
            "electron_transfer_number",
            "faraday_constant",
        },
        required={"method"},
        field_name=f"thermodynamic_constraints.{item.id}.standard_energy",
    )
    method = str(standard_energy["method"]).strip()
    standard_delta_gibbs: Parameter | None = None
    standard_redox_potential: Parameter | None = None
    electron_transfer_number: Parameter | None = None
    faraday_constant: Parameter | None = None
    if method == "standard_delta_gibbs":
        _require_exact_energy_fields(
            standard_energy,
            method=method,
            expected={"method", "standard_delta_gibbs"},
            constraint_id=item.id,
        )
        standard_delta_gibbs = _parameter_mapping(
            standard_energy["standard_delta_gibbs"],
            field_name=(
                f"thermodynamic_constraints.{item.id}."
                "standard_energy.standard_delta_gibbs"
            ),
        )
    elif method == "redox_potential":
        _require_exact_energy_fields(
            standard_energy,
            method=method,
            expected={
                "method",
                "standard_redox_potential",
                "electron_transfer_number",
                "faraday_constant",
            },
            constraint_id=item.id,
        )
        standard_redox_potential = _parameter_mapping(
            standard_energy["standard_redox_potential"],
            field_name=(
                f"thermodynamic_constraints.{item.id}."
                "standard_energy.standard_redox_potential"
            ),
        )
        electron_transfer_number = _parameter_mapping(
            standard_energy["electron_transfer_number"],
            field_name=(
                f"thermodynamic_constraints.{item.id}."
                "standard_energy.electron_transfer_number"
            ),
        )
        _validate_redox_transfer_binding(
            reaction=reaction,
            electron_transfer_number=electron_transfer_number,
            constraint_id=item.id,
        )
        faraday_constant = _parameter_mapping(
            standard_energy["faraday_constant"],
            field_name=(
                f"thermodynamic_constraints.{item.id}."
                "standard_energy.faraday_constant"
            ),
        )
    else:
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} has unsupported "
            f"standard_energy.method {method!r}."
        )
    provenance_refs = _nonblank_text_sequence(
        raw["provenance_refs"],
        field_name=f"thermodynamic_constraints.{item.id}.provenance_refs",
    )
    return DynamicThermodynamicConstraint(
        constraint_id=item.id,
        process_id=item.process_id,
        reaction_id=item.reaction_id,
        electron_balance_check_id=item.electron_balance_check_id,
        participants=participants,
        standard_energy_method=method,
        standard_delta_gibbs=standard_delta_gibbs,
        standard_redox_potential=standard_redox_potential,
        electron_transfer_number=electron_transfer_number,
        faraday_constant=faraday_constant,
        temperature=_parameter_mapping(
            raw["temperature"],
            field_name=f"thermodynamic_constraints.{item.id}.temperature",
        ),
        gas_constant=_parameter_mapping(
            raw["gas_constant"],
            field_name=f"thermodynamic_constraints.{item.id}.gas_constant",
        ),
        standard_concentration=standard_concentration,
        minimum_activity=minimum_activity,
        absolute_tolerance=_parameter_mapping(
            raw["absolute_tolerance"],
            field_name=f"thermodynamic_constraints.{item.id}.absolute_tolerance",
        ),
        provenance_refs=provenance_refs,
        enforcement_mode=item.enforcement_mode,
    )


def _participants(
    *,
    item: ThermodynamicConstraintConfig,
    reaction: ReactionMetadataConfig,
    binding: Mapping[str, Any],
    state_units: Mapping[str, str],
    standard_concentration: Parameter,
) -> tuple[DynamicActivityParticipant, ...]:
    binding_entries = binding.get("state_species_mapping")
    if not isinstance(binding_entries, Sequence) or isinstance(
        binding_entries,
        str | bytes,
    ):
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} has no verified "
            "state/species binding evidence."
        )
    bound_species_by_state: dict[str, str] = {}
    for entry in binding_entries:
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"Dynamic thermodynamic constraint {item.id!r} has malformed "
                "state/species binding evidence."
            )
        state_name = str(entry.get("state_name") or "").strip()
        species_id = str(entry.get("species_id") or "").strip()
        if not state_name or not species_id:
            raise ValueError(
                f"Dynamic thermodynamic constraint {item.id!r} has incomplete "
                "state/species binding evidence."
            )
        bound_species_by_state[state_name] = species_id
    participants: list[DynamicActivityParticipant] = []
    for side, sign, entries in (
        ("reactants", -1.0, reaction.reactants),
        ("products", 1.0, reaction.products),
    ):
        for index, participant in enumerate(entries):
            state_name = "" if participant.state_name is None else participant.state_name.strip()
            if not state_name:
                raise ValueError(
                    f"Dynamic thermodynamic constraint {item.id!r} requires "
                    f"reaction_metadata.{reaction.id}.{side}[{index}].state_name."
                )
            if state_name not in state_units:
                raise ValueError(
                    f"Dynamic thermodynamic constraint {item.id!r} references "
                    f"unknown state {state_name!r}."
                )
            bound_species = bound_species_by_state.get(state_name)
            if bound_species != participant.species_id:
                raise ValueError(
                    f"Dynamic thermodynamic constraint {item.id!r} participant "
                    f"{state_name!r}/{participant.species_id!r} does not match "
                    "the verified static state/species binding."
                )
            coefficient = float(participant.coefficient)
            if not np.isfinite(coefficient) or coefficient <= 0.0:
                raise ValueError(
                    f"Dynamic thermodynamic reaction participant {state_name!r} "
                    "requires a finite positive coefficient."
                )
            assert_compatible(
                Q_(1.0, state_units[state_name]),
                standard_concentration.units,
                name=state_name,
            )
            participants.append(
                DynamicActivityParticipant(
                    state_name=state_name,
                    species_id=participant.species_id,
                    signed_coefficient=sign * coefficient,
                )
            )
    return tuple(participants)


def _required_passing_electron_binding(
    *,
    item: ThermodynamicConstraintConfig,
    balance_check: BalanceCheckConfig,
    validations: Sequence[ValidationResult],
) -> Mapping[str, Any]:
    if balance_check.process_id != item.process_id:
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} process_id does not "
            "match its electron balance check."
        )
    if balance_check.reaction_id != item.reaction_id:
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} reaction_id does not "
            "match its electron balance check."
        )
    if not balance_check.required:
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} requires a required "
            "electron/redox balance check."
        )
    if not any(check in {"electron", "redox"} for check in balance_check.checks):
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} balance check must "
            "request 'electron' or 'redox'."
        )
    candidates = [
        validation
        for validation in validations
        if validation.details.get("check_id") == balance_check.id
        and validation.details.get("reaction_id") == item.reaction_id
        and validation.details.get("check_type") in {"electron", "redox"}
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} requires exactly one "
            "matching assembly-time electron/redox validation."
        )
    validation = candidates[0]
    binding = validation.details.get("binding")
    if (
        not validation.passed
        or validation.status not in {None, "passed"}
        or not isinstance(binding, Mapping)
        or binding.get("verified") is not True
    ):
        raise ValueError(
            f"Dynamic thermodynamic constraint {item.id!r} requires a passing "
            "electron/redox check with verified process/reaction binding."
        )
    return binding


def _parameter(
    value: Any,
    *,
    nested_key: str,
    field_name: str,
) -> Parameter:
    data = _closed_mapping(
        value,
        allowed={"type", "standard_concentration", "minimum_activity"},
        required={"type", "standard_concentration", "minimum_activity"},
        field_name=field_name,
    )
    return _parameter_mapping(
        data[nested_key],
        field_name=f"{field_name}.{nested_key}",
    )


def _parameter_mapping(value: Any, *, field_name: str) -> Parameter:
    data = _closed_mapping(
        value,
        allowed=_PARAMETER_FIELDS,
        required={
            "name",
            "symbol",
            "value",
            "units",
            "source",
            "confidence_level",
            "measurement_method",
        },
        field_name=field_name,
    )
    raw_value = data["value"]
    if (
        isinstance(raw_value, bool)
        or not isinstance(raw_value, int | float)
        or not np.isfinite(float(raw_value))
    ):
        raise ValueError(f"{field_name}.value must be a finite numeric scalar.")
    for provenance_field in (
        "source",
        "confidence_level",
        "measurement_method",
    ):
        if not str(data[provenance_field]).strip():
            raise ValueError(
                f"{field_name}.{provenance_field} must be nonblank."
            )
    try:
        parameter = Parameter.from_dict(data)
        parameter.validate_provenance()
        parameter.validate_value()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is invalid: {exc}") from exc
    if not str(parameter.source or "").strip():
        raise ValueError(f"{field_name}.source must be nonblank.")
    return parameter


def _require_exact_energy_fields(
    data: Mapping[str, Any],
    *,
    method: str,
    expected: set[str],
    constraint_id: str,
) -> None:
    actual = set(data)
    if actual != expected:
        missing = sorted(expected.difference(actual))
        extra = sorted(actual.difference(expected))
        raise ValueError(
            f"Dynamic thermodynamic constraint {constraint_id!r} "
            f"standard_energy method {method!r} has missing fields {missing} "
            f"and incompatible fields {extra}."
        )


def _validate_redox_transfer_binding(
    *,
    reaction: ReactionMetadataConfig,
    electron_transfer_number: Parameter,
    constraint_id: str,
) -> None:
    reaction_raw = reaction.raw
    if not isinstance(reaction_raw, Mapping):
        raise ValueError(
            f"reaction_metadata.{reaction.id} has no raw metadata mapping."
        )
    binding = _closed_mapping(
        reaction_raw.get("electron_transfer_number"),
        allowed={"value", "source"},
        required={"value", "source"},
        field_name=(
            f"reaction_metadata.{reaction.id}.electron_transfer_number"
        ),
    )
    source = str(binding["source"]).strip()
    if not source:
        raise ValueError(
            f"reaction_metadata.{reaction.id}.electron_transfer_number.source "
            "must be nonblank."
        )
    try:
        declared = float(binding["value"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"reaction_metadata.{reaction.id}.electron_transfer_number.value "
            "must be numeric."
        ) from exc
    parameter_quantity = electron_transfer_number.quantity
    assert parameter_quantity is not None
    configured = float(
        assert_compatible(
            parameter_quantity,
            "dimensionless",
            name=electron_transfer_number.symbol,
        ).magnitude
    )
    if (
        not np.isfinite(declared)
        or declared <= 0.0
        or not np.isclose(declared, configured, rtol=1.0e-12, atol=1.0e-12)
    ):
        raise ValueError(
            f"Dynamic redox constraint {constraint_id!r} electron transfer "
            "number must be finite, positive, and exactly match the explicit "
            "reaction metadata binding."
        )


def _closed_mapping(
    value: Any,
    *,
    allowed: set[str],
    required: set[str],
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    unsupported = sorted(str(key) for key in value if str(key) not in allowed)
    missing = sorted(required.difference(str(key) for key in value))
    if unsupported or missing:
        raise ValueError(
            f"{field_name} has missing fields {missing} and unsupported fields "
            f"{unsupported}."
        )
    return value


def _nonblank_text_sequence(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError(f"{field_name} must be a sequence of nonblank strings.")
    values = tuple(str(item).strip() for item in value)
    if not values or any(not item for item in values):
        raise ValueError(f"{field_name} must contain nonblank strings.")
    return values


def _unique_by_id(
    values: Sequence[Any],
    *,
    attribute: str,
    collection: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        identifier = str(getattr(value, attribute))
        if identifier in result:
            raise ValueError(f"{collection} contains duplicate id {identifier!r}.")
        result[identifier] = value
    return result


__all__ = ["configured_dynamic_thermodynamic_constraints"]
