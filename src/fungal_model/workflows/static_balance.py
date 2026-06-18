"""Assembly-time static balance checks for configured model metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fungal_model.chemistry.stoichiometry import (
    DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE,
    ElementalComposition,
    StoichiometricReactionMetadata,
    StoichiometricTerm,
)
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, assert_compatible
from fungal_model.core.validators import (
    ValidationResult,
    validate_charge_balance,
    validate_electron_balance,
    validate_elemental_balance,
)
from fungal_model.io.model_config import ModelConfig


_CHECK_TYPES = ("elemental", "charge", "electron", "redox")


@dataclass(frozen=True)
class _SpeciesStaticMetadata:
    species_id: str
    name: str
    composition: ElementalComposition | None = None
    charge: float | None = None
    charge_source: str | None = None
    electron_equivalents: float | None = None
    electron_source: str | None = None
    source: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class _ReactionParticipantStaticMetadata:
    species_id: str
    coefficient: float
    side: str
    state_name: str | None = None
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "species_id": self.species_id,
            "coefficient": self.coefficient,
            "side": self.side,
            "state_name": self.state_name,
            "role": self.role,
        }


@dataclass(frozen=True)
class _ReactionStaticMetadata:
    reaction_id: str
    reaction: StoichiometricReactionMetadata
    participants: tuple[_ReactionParticipantStaticMetadata, ...]


@dataclass(frozen=True)
class _StateSpeciesBinding:
    state_name: str
    species_id: str
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_name": self.state_name,
            "species_id": self.species_id,
            "role": self.role,
        }


def configured_static_balance_validations(
    config: ModelConfig,
    *,
    processes: Sequence[Any] = (),
    product_maps: Mapping[str, Any] | None = None,
) -> tuple[ValidationResult, ...]:
    """Build static assembly-time validation results from optional config sections."""

    raw = config.raw
    check_entries = _sequence(raw.get("balance_checks", ()), field_name="balance_checks")
    if not check_entries:
        return ()
    process_by_name = _processes_by_name(processes)
    product_maps_by_id = dict(product_maps or {})
    species = _species_metadata(raw.get("chemistry_metadata"))
    reactions = _reaction_metadata(raw.get("reaction_metadata"), species)
    process_configs = {
        process_config.id: process_config
        for process_config in config.processes
    }
    validations: list[ValidationResult] = []
    for index, check_data in enumerate(check_entries):
        check = _mapping(check_data, field_name=f"balance_checks[{index}]")
        check_id = str(check.get("id") or f"balance_check_{index}")
        reaction_id = str(check.get("reaction_id") or check.get("reaction") or "").strip()
        required = bool(check.get("required", True))
        check_types = _check_types(check.get("checks", check.get("check_types", ("elemental",))))
        reaction = reactions.get(reaction_id)
        if reaction is None:
            validations.extend(
                _missing_reaction_validation(
                    check_id=check_id,
                    reaction_id=reaction_id,
                    check_type=check_type,
                    required=required,
                    mode=config.mode,
                )
                for check_type in check_types
            )
            continue
        binding = _validate_process_reaction_binding(
            check=check,
            check_id=check_id,
            reaction=reaction,
            process_by_name=process_by_name,
            process_configs=process_configs,
            product_maps=product_maps_by_id,
            required=required,
            mode=config.mode,
        )
        for check_type in check_types:
            if not binding.passed:
                validations.append(
                    _with_check_context(
                        _binding_failure_validation(
                            check_type=check_type,
                            binding=binding,
                            required=required,
                        ),
                        check_id=check_id,
                        reaction_id=reaction_id,
                        check_type=check_type,
                    )
                )
                continue
            validations.append(
                _with_check_context(
                    _with_binding_evidence(
                        _apply_required_mode_policy(
                            _run_static_check(
                                check_type=check_type,
                                reaction=reaction.reaction,
                                required=required,
                            ),
                            mode=config.mode,
                        ),
                        binding=binding,
                    ),
                    check_id=check_id,
                    reaction_id=reaction_id,
                    check_type=check_type,
                )
            )
    return tuple(validations)


def blocking_static_balance_validations(
    *,
    mode: str,
    validations: Sequence[ValidationResult],
) -> tuple[ValidationResult, ...]:
    """Return static assembly checks that should block strict/scientific execution."""

    if mode not in {"strict", "scientific"}:
        return ()
    return tuple(validation for validation in validations if _validation_blocks_mode(validation))


def static_validation_callable(validation: ValidationResult) -> Callable[[Any], ValidationResult]:
    """Return a result-validator callable that replays an assembly-time check."""

    def validator(result: Any) -> ValidationResult:
        del result
        return validation

    return validator


def _run_static_check(
    *,
    check_type: str,
    reaction: StoichiometricReactionMetadata,
    required: bool,
) -> ValidationResult:
    if check_type == "elemental":
        return validate_elemental_balance(reaction, required=required)
    if check_type == "charge":
        return validate_charge_balance(reaction, required=required)
    if check_type in {"electron", "redox"}:
        return validate_electron_balance(reaction, required=required)
    return ValidationResult(
        name="static_balance",
        passed=False,
        status="unsupported",
        severity="error" if required else "warning",
        required=required,
        message=f"Unsupported static balance check type {check_type!r}.",
        details={"check_type": check_type, "missing_metadata": []},
    )


def _with_check_context(
    validation: ValidationResult,
    *,
    check_id: str,
    reaction_id: str,
    check_type: str,
) -> ValidationResult:
    details = {
        **validation.details,
        "check_id": check_id,
        "reaction_id": reaction_id,
        "check_type": check_type,
        "assembly_time": True,
    }
    return ValidationResult(
        name=validation.name,
        passed=validation.passed,
        status=validation.status,
        severity=validation.severity,
        required=validation.required,
        message=validation.message,
        details=details,
    )


def _missing_reaction_validation(
    *,
    check_id: str,
    reaction_id: str,
    check_type: str,
    required: bool,
    mode: str,
) -> ValidationResult:
    status = _missing_or_unknown_status(required=required, mode=mode)
    name = _balance_check_name(check_type)
    return ValidationResult(
        name=name,
        passed=False,
        status=status,
        severity="error" if required else "warning",
        required=required,
        message="Static balance check cannot run because referenced reaction metadata is missing.",
        details={
            "check_id": check_id,
            "reaction_id": reaction_id,
            "check_type": check_type,
            "assembly_time": True,
            "missing_metadata": [f"reaction_metadata.{reaction_id or '<blank>'}"],
            "binding": {
                "verified": False,
                "failures": [
                    {
                        "reason": "missing_reaction_metadata",
                        "message": "The balance check did not reference a declared reaction metadata record.",
                    }
                ],
            },
        },
    )


def _validate_process_reaction_binding(
    *,
    check: Mapping[str, Any],
    check_id: str,
    reaction: _ReactionStaticMetadata,
    process_by_name: Mapping[str, Any],
    process_configs: Mapping[str, Any],
    product_maps: Mapping[str, Any],
    required: bool,
    mode: str,
) -> ValidationResult:
    process_id = str(check.get("process_id") or check.get("process") or "").strip()
    bindings, binding_failures = _state_species_bindings(
        check.get("state_species", check.get("state_to_species", check.get("state_mappings"))),
        check_id=check_id,
    )
    failures: list[dict[str, Any]] = list(binding_failures)
    process = None
    if not process_id:
        failures.append(
            {
                "reason": "missing_process_reference",
                "field": "process_id",
                "message": "Balance checks must explicitly name the process they bind to.",
            }
        )
    else:
        process = process_by_name.get(process_id)
        if process is None:
            failures.append(
                {
                    "reason": "unknown_process_reference",
                    "field": "process_id",
                    "process_id": process_id,
                    "message": "The referenced process was not assembled.",
                }
            )
    if bindings:
        failures.extend(_duplicate_binding_failures(bindings))
    process_contributions: dict[str, float] = {}
    if process is not None:
        process_contributions, contribution_failures = _process_signed_contributions(process)
        failures.extend(contribution_failures)
    mapped_process_stoichiometry, mapping_failures = _mapped_process_stoichiometry(
        process_contributions,
        bindings,
    )
    failures.extend(mapping_failures)
    reaction_stoichiometry, reaction_failures = _reaction_signed_stoichiometry(reaction)
    failures.extend(reaction_failures)
    failures.extend(
        _compare_bound_stoichiometry(
            mapped_process_stoichiometry=mapped_process_stoichiometry,
            reaction_stoichiometry=reaction_stoichiometry,
        )
    )
    failures.extend(
        _role_failures(
            process_contributions=process_contributions,
            bindings=bindings,
            reaction_stoichiometry=reaction_stoichiometry,
        )
    )
    evidence = _binding_evidence(
        process=process,
        process_id=process_id,
        process_config=process_configs.get(process_id),
        product_maps=product_maps,
        bindings=bindings,
        process_contributions=process_contributions,
        mapped_process_stoichiometry=mapped_process_stoichiometry,
        reaction=reaction,
        reaction_stoichiometry=reaction_stoichiometry,
        failures=failures,
    )
    if failures:
        return ValidationResult(
            name="process_reaction_binding",
            passed=False,
            status=_missing_or_unknown_status(required=required, mode=mode),
            severity="error" if required else "warning",
            required=required,
            message="Process/reaction binding is not verified for this static balance check.",
            details={"binding": evidence},
        )
    return ValidationResult(
        name="process_reaction_binding",
        passed=True,
        status="passed",
        severity="info",
        required=required,
        message="Process/reaction binding is verified for this static balance check.",
        details={"binding": {**evidence, "verified": True}},
    )


def _state_species_bindings(
    value: Any,
    *,
    check_id: str,
) -> tuple[tuple[_StateSpeciesBinding, ...], tuple[dict[str, Any], ...]]:
    if value is None:
        return (), (
            {
                "reason": "missing_state_species_mapping",
                "field": "state_species",
                "check_id": check_id,
                "message": "Balance checks must explicitly map process states to chemical species.",
            },
        )
    failures: list[dict[str, Any]] = []
    bindings: list[_StateSpeciesBinding] = []
    if isinstance(value, Mapping):
        entries = tuple(value.items())
        for state_name, binding_value in entries:
            binding, failure = _state_species_binding_from_entry(
                state_name=str(state_name),
                value=binding_value,
                index=None,
            )
            if failure is not None:
                failures.append(failure)
            if binding is not None:
                bindings.append(binding)
    else:
        for index, entry_value in enumerate(_sequence(value, field_name="state_species")):
            entry = _mapping(entry_value, field_name=f"state_species[{index}]")
            state_name = str(entry.get("state") or entry.get("state_name") or "").strip()
            binding, failure = _state_species_binding_from_entry(
                state_name=state_name,
                value=entry,
                index=index,
            )
            if failure is not None:
                failures.append(failure)
            if binding is not None:
                bindings.append(binding)
    return tuple(bindings), tuple(failures)


def _state_species_binding_from_entry(
    *,
    state_name: str,
    value: Any,
    index: int | None,
) -> tuple[_StateSpeciesBinding | None, dict[str, Any] | None]:
    field = "state_species" if index is None else f"state_species[{index}]"
    if not state_name:
        return None, {
            "reason": "missing_state_name",
            "field": field,
            "message": "Each state-species mapping must name a process state.",
        }
    role: str | None = None
    if isinstance(value, Mapping):
        species_id = str(value.get("species") or value.get("species_id") or "").strip()
        role = _optional_text(value.get("role"))
    else:
        species_id = str(value).strip()
    if not species_id:
        return None, {
            "reason": "missing_species_reference",
            "field": field,
            "state_name": state_name,
            "message": "Each mapped process state must name a chemical species.",
        }
    return _StateSpeciesBinding(
        state_name=state_name,
        species_id=species_id,
        role=None if role is None else role.strip().lower(),
    ), None


def _duplicate_binding_failures(bindings: Sequence[_StateSpeciesBinding]) -> tuple[dict[str, Any], ...]:
    failures: list[dict[str, Any]] = []
    states: dict[str, str] = {}
    species: dict[str, str] = {}
    for binding in bindings:
        previous_species = states.get(binding.state_name)
        if previous_species is not None:
            failures.append(
                {
                    "reason": "duplicate_state_mapping",
                    "state_name": binding.state_name,
                    "species_id": binding.species_id,
                    "previous_species_id": previous_species,
                    "message": "A process state is mapped more than once.",
                }
            )
        states[binding.state_name] = binding.species_id
        previous_state = species.get(binding.species_id)
        if previous_state is not None:
            failures.append(
                {
                    "reason": "duplicate_species_mapping",
                    "species_id": binding.species_id,
                    "state_name": binding.state_name,
                    "previous_state_name": previous_state,
                    "message": "A chemical species is mapped from more than one process state.",
                }
            )
        species[binding.species_id] = binding.state_name
    return tuple(failures)


def _process_signed_contributions(process: Any) -> tuple[dict[str, float], tuple[dict[str, Any], ...]]:
    rate_units = _optional_text(getattr(process, "rate_units", None))
    if rate_units is None:
        return {}, (
            {
                "reason": "missing_process_rate_units",
                "process_id": getattr(process, "name", None),
                "message": "The assembled process does not expose rate_units for contribution binding.",
            },
        )
    try:
        contributions = process.contributions(Q_(1.0, rate_units))
    except (TypeError, ValueError) as exc:
        return {}, (
            {
                "reason": "process_contribution_error",
                "process_id": getattr(process, "name", None),
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        )
    tolerance = _stoichiometric_tolerance()
    signed: dict[str, float] = {}
    failures: list[dict[str, Any]] = []
    for state_name, contribution in contributions.items():
        try:
            value = float(
                assert_compatible(
                    contribution,
                    rate_units,
                    name=f"{getattr(process, 'name', 'process')}.{state_name}",
                ).magnitude
            )
        except (TypeError, ValueError) as exc:
            failures.append(
                {
                    "reason": "incompatible_process_contribution_units",
                    "state_name": str(state_name),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            continue
        if abs(value) > tolerance:
            signed[str(state_name)] = value
    return signed, tuple(failures)


def _mapped_process_stoichiometry(
    process_contributions: Mapping[str, float],
    bindings: Sequence[_StateSpeciesBinding],
) -> tuple[dict[str, float], tuple[dict[str, Any], ...]]:
    failures: list[dict[str, Any]] = []
    binding_by_state = {binding.state_name: binding for binding in bindings}
    missing_states = sorted(set(process_contributions).difference(binding_by_state))
    extra_states = sorted(set(binding_by_state).difference(process_contributions))
    for state_name in missing_states:
        failures.append(
            {
                "reason": "missing_state_mapping",
                "state_name": state_name,
                "message": "A process contribution state is not mapped to a chemical species.",
            }
        )
    for state_name in extra_states:
        failures.append(
            {
                "reason": "unrelated_state_mapping",
                "state_name": state_name,
                "species_id": binding_by_state[state_name].species_id,
                "message": "A mapped state is not changed by the referenced process.",
            }
        )
    mapped: dict[str, float] = {}
    for state_name, coefficient in process_contributions.items():
        binding = binding_by_state.get(state_name)
        if binding is None:
            continue
        mapped[binding.species_id] = mapped.get(binding.species_id, 0.0) + float(coefficient)
    return mapped, tuple(failures)


def _reaction_signed_stoichiometry(
    reaction: _ReactionStaticMetadata,
) -> tuple[dict[str, float], tuple[dict[str, Any], ...]]:
    signed: dict[str, float] = {}
    failures: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for participant in reaction.participants:
        key = (participant.side, participant.species_id)
        if key in seen:
            failures.append(
                {
                    "reason": "duplicate_reaction_participant",
                    "species_id": participant.species_id,
                    "side": participant.side,
                    "message": "Reaction metadata lists the same species more than once on a side.",
                }
            )
        seen.add(key)
        sign = -1.0 if participant.side == "reactant" else 1.0
        signed[participant.species_id] = signed.get(participant.species_id, 0.0) + sign * participant.coefficient
    return signed, tuple(failures)


def _compare_bound_stoichiometry(
    *,
    mapped_process_stoichiometry: Mapping[str, float],
    reaction_stoichiometry: Mapping[str, float],
) -> tuple[dict[str, Any], ...]:
    failures: list[dict[str, Any]] = []
    tolerance = _stoichiometric_tolerance()
    process_species = set(mapped_process_stoichiometry)
    reaction_species = set(reaction_stoichiometry)
    for species_id in sorted(process_species.difference(reaction_species)):
        failures.append(
            {
                "reason": "species_missing_from_reaction",
                "species_id": species_id,
                "message": "A mapped process species is absent from the reaction metadata.",
            }
        )
    for species_id in sorted(reaction_species.difference(process_species)):
        failures.append(
            {
                "reason": "reaction_species_not_bound_to_process",
                "species_id": species_id,
                "message": "A reaction participant is not bound to any changed process state.",
            }
        )
    for species_id in sorted(process_species & reaction_species):
        process_value = float(mapped_process_stoichiometry[species_id])
        reaction_value = float(reaction_stoichiometry[species_id])
        residual = process_value - reaction_value
        if abs(residual) > tolerance:
            failures.append(
                {
                    "reason": "coefficient_mismatch",
                    "species_id": species_id,
                    "process_signed_coefficient": process_value,
                    "reaction_signed_coefficient": reaction_value,
                    "residual_value": residual,
                    "absolute_tolerance": tolerance,
                    "message": "Mapped process contribution does not match reaction stoichiometry.",
                }
            )
    return tuple(failures)


def _role_failures(
    *,
    process_contributions: Mapping[str, float],
    bindings: Sequence[_StateSpeciesBinding],
    reaction_stoichiometry: Mapping[str, float],
) -> tuple[dict[str, Any], ...]:
    failures: list[dict[str, Any]] = []
    for binding in bindings:
        coefficient = process_contributions.get(binding.state_name)
        if coefficient is None:
            continue
        process_role = _role_from_signed_coefficient(coefficient)
        reaction_role = _role_from_signed_coefficient(reaction_stoichiometry.get(binding.species_id, 0.0))
        if reaction_role != "unchanged" and process_role != reaction_role:
            failures.append(
                {
                    "reason": "role_mismatch",
                    "state_name": binding.state_name,
                    "species_id": binding.species_id,
                    "process_role": process_role,
                    "reaction_role": reaction_role,
                    "message": "Mapped state role does not match the reaction participant side.",
                }
            )
        if binding.role is not None and binding.role != process_role:
            failures.append(
                {
                    "reason": "declared_role_contradiction",
                    "state_name": binding.state_name,
                    "species_id": binding.species_id,
                    "declared_role": binding.role,
                    "process_role": process_role,
                    "message": "Declared state-species role contradicts the process contribution sign.",
                }
            )
    return tuple(failures)


def _binding_evidence(
    *,
    process: Any | None,
    process_id: str,
    process_config: Any | None,
    product_maps: Mapping[str, Any],
    bindings: Sequence[_StateSpeciesBinding],
    process_contributions: Mapping[str, float],
    mapped_process_stoichiometry: Mapping[str, float],
    reaction: _ReactionStaticMetadata,
    reaction_stoichiometry: Mapping[str, float],
    failures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    product_map_id = None if process_config is None else getattr(process_config, "product_map", None)
    product_map = product_maps.get(product_map_id) if isinstance(product_map_id, str) else None
    return {
        "verified": not failures,
        "process_id": process_id,
        "process_type": None if process is None else getattr(process, "process_type", None),
        "reaction_id": reaction.reaction_id,
        "state_species_mapping": [binding.to_dict() for binding in bindings],
        "process_contributions": [
            {
                "state_name": state_name,
                "signed_coefficient": coefficient,
                "role": _role_from_signed_coefficient(coefficient),
            }
            for state_name, coefficient in sorted(process_contributions.items())
        ],
        "mapped_process_stoichiometry": dict(sorted(mapped_process_stoichiometry.items())),
        "reaction_stoichiometry": dict(sorted(reaction_stoichiometry.items())),
        "reaction_participants": [participant.to_dict() for participant in reaction.participants],
        "product_map": {
            "id": product_map_id,
            "data": None if product_map is None or not hasattr(product_map, "to_dict") else product_map.to_dict(),
        },
        "absolute_tolerance": _stoichiometric_tolerance(),
        "absolute_tolerance_units": "stoichiometric coefficient per process event",
        "failures": [dict(failure) for failure in failures],
    }


def _binding_failure_validation(
    *,
    check_type: str,
    binding: ValidationResult,
    required: bool,
) -> ValidationResult:
    return ValidationResult(
        name=_balance_check_name(check_type),
        passed=False,
        status=binding.status,
        severity=binding.severity,
        required=required,
        message=(
            "Static balance check cannot pass because process/reaction binding is not verified."
        ),
        details={
            **binding.details,
            "missing_metadata": _binding_missing_metadata(binding.details.get("binding", {})),
        },
    )


def _binding_missing_metadata(binding: Any) -> list[str]:
    if not isinstance(binding, Mapping):
        return []
    missing: list[str] = []
    for failure in binding.get("failures", ()):
        if not isinstance(failure, Mapping):
            continue
        field = failure.get("field")
        if field is not None:
            missing.append(str(field))
    return missing


def _with_binding_evidence(
    validation: ValidationResult,
    *,
    binding: ValidationResult,
) -> ValidationResult:
    return ValidationResult(
        name=validation.name,
        passed=validation.passed,
        status=validation.status,
        severity=validation.severity,
        required=validation.required,
        message=validation.message,
        details={**validation.details, **binding.details},
    )


def _apply_required_mode_policy(validation: ValidationResult, *, mode: str) -> ValidationResult:
    data = validation.to_dict()
    if mode == "exploratory" and validation.required and data["status"] == "inconclusive":
        return ValidationResult(
            name=validation.name,
            passed=False,
            status="failed",
            severity="error",
            required=validation.required,
            message=validation.message,
            details={
                **validation.details,
                "mode_policy": "required exploratory assembly checks cannot remain inconclusive",
            },
        )
    return validation


def _missing_or_unknown_status(*, required: bool, mode: str) -> str:
    if required:
        return "failed" if mode == "exploratory" else "inconclusive"
    return "inconclusive"


def _validation_blocks_mode(validation: ValidationResult) -> bool:
    data = validation.to_dict()
    passed = bool(data.get("passed"))
    status = str(data.get("status") or ("passed" if passed else "failed"))
    severity = str(data.get("severity") or ("info" if passed else "error"))
    required = bool(data.get("required", True))
    if status == "inconclusive":
        return required
    if status == "unsupported":
        return True
    if status == "failed":
        return required or severity in {"error", "blocker"}
    return not passed and required


def _processes_by_name(processes: Sequence[Any]) -> dict[str, Any]:
    process_by_name: dict[str, Any] = {}
    duplicates: set[str] = set()
    for process in processes:
        name = str(getattr(process, "name", ""))
        if name in process_by_name:
            duplicates.add(name)
        process_by_name[name] = process
    return {
        name: process
        for name, process in process_by_name.items()
        if name not in duplicates
    }


def _species_metadata(value: Any) -> dict[str, _SpeciesStaticMetadata]:
    if value is None:
        return {}
    data = _mapping(value, field_name="chemistry_metadata")
    species_value = data.get("species", data)
    if isinstance(species_value, Mapping):
        return {
            str(species_id): _species_record_from_mapping(
                str(species_id),
                _mapping(species_data, field_name=str(species_id)),
            )
            for species_id, species_data in species_value.items()
        }
    species_entries = _sequence(species_value, field_name="chemistry_metadata.species")
    records: dict[str, _SpeciesStaticMetadata] = {}
    for index, species_data in enumerate(species_entries):
        entry = _mapping(species_data, field_name=f"chemistry_metadata.species[{index}]")
        species_id = str(entry.get("id") or entry.get("species_id") or "").strip()
        if not species_id:
            raise ValueError("Chemistry species metadata requires id or species_id.")
        records[species_id] = _species_record_from_mapping(species_id, entry)
    return records


def _species_record_from_mapping(species_id: str, data: Mapping[str, Any]) -> _SpeciesStaticMetadata:
    source = _source_from_mapping(data)
    return _SpeciesStaticMetadata(
        species_id=species_id,
        name=str(data.get("name") or species_id),
        composition=_composition_from_config(data, default_source=source),
        charge=None if data.get("charge") is None else float(data["charge"]),
        charge_source=_optional_text(data.get("charge_source")) or source,
        electron_equivalents=(
            None
            if data.get("electron_equivalents") is None
            else float(data["electron_equivalents"])
        ),
        electron_source=_optional_text(data.get("electron_source")) or source,
        source=source,
        notes=str(data.get("notes", "")),
    )


def _reaction_metadata(
    value: Any,
    species: Mapping[str, _SpeciesStaticMetadata],
) -> dict[str, _ReactionStaticMetadata]:
    if value is None:
        return {}
    entries = _sequence(value, field_name="reaction_metadata")
    reactions: dict[str, _ReactionStaticMetadata] = {}
    for index, reaction_data in enumerate(entries):
        data = _mapping(reaction_data, field_name=f"reaction_metadata[{index}]")
        reaction_id = str(data.get("id") or data.get("reaction_id") or "").strip()
        if not reaction_id:
            raise ValueError("Reaction metadata requires id or reaction_id.")
        reactants, reactant_participants = _participant_terms(
            data.get("reactants", ()),
            species,
            field_name=f"{reaction_id}.reactants",
            side="reactant",
        )
        products, product_participants = _participant_terms(
            data.get("products", ()),
            species,
            field_name=f"{reaction_id}.products",
            side="product",
        )
        reactions[reaction_id] = _ReactionStaticMetadata(
            reaction_id=reaction_id,
            reaction=StoichiometricReactionMetadata(
                name=str(data.get("name") or reaction_id),
                reactants=reactants,
                products=products,
                source=_source_from_mapping(data),
                notes=str(data.get("notes", "")),
            ),
            participants=(*reactant_participants, *product_participants),
        )
    return reactions


def _participant_terms(
    value: Any,
    species: Mapping[str, _SpeciesStaticMetadata],
    *,
    field_name: str,
    side: str,
) -> tuple[tuple[StoichiometricTerm, ...], tuple[_ReactionParticipantStaticMetadata, ...]]:
    entries = _sequence(value, field_name=field_name)
    terms: list[StoichiometricTerm] = []
    participants: list[_ReactionParticipantStaticMetadata] = []
    for index, participant_data in enumerate(entries):
        data = _mapping(participant_data, field_name=f"{field_name}[{index}]")
        species_id = str(data.get("species") or data.get("species_id") or "").strip()
        if not species_id:
            raise ValueError(f"{field_name}[{index}] requires species or species_id.")
        record = species.get(species_id)
        coefficient = float(data.get("coefficient", 1.0))
        terms.append(
            StoichiometricTerm(
                species=species_id,
                coefficient=coefficient,
                composition=None if record is None else record.composition,
                charge=None if record is None else record.charge,
                charge_source=None if record is None else record.charge_source,
                electron_equivalents=None if record is None else record.electron_equivalents,
                electron_source=None if record is None else record.electron_source,
                notes="" if record is None else record.notes,
            )
        )
        participants.append(
            _ReactionParticipantStaticMetadata(
                species_id=species_id,
                coefficient=coefficient,
                side=side,
                state_name=_optional_text(data.get("state_name") or data.get("state")),
                role=_optional_text(data.get("role")),
            )
        )
    return tuple(terms), tuple(participants)


def _composition_from_config(
    data: Mapping[str, Any],
    *,
    default_source: str | None,
) -> ElementalComposition | None:
    source = _optional_text(data.get("composition_source")) or default_source
    composition_data = data.get("composition")
    if isinstance(composition_data, Mapping):
        source = _optional_text(composition_data.get("source")) or source
        if "elements" in composition_data:
            return ElementalComposition.from_elements(
                _element_counts(composition_data["elements"]),
                source=source,
                formula=str(composition_data.get("formula", "structured_element_counts")),
                notes=str(composition_data.get("notes", "")),
            )
        if "formula" in composition_data:
            return ElementalComposition.from_formula(
                str(composition_data["formula"]),
                source=source,
                notes=str(composition_data.get("notes", "")),
            )
    if "elements" in data:
        return ElementalComposition.from_elements(
            _element_counts(data["elements"]),
            source=source,
            formula=str(data.get("formula", "structured_element_counts")),
            notes=str(data.get("composition_notes", "")),
        )
    if data.get("formula") is not None:
        return ElementalComposition.from_formula(
            str(data["formula"]),
            source=source,
            notes=str(data.get("composition_notes", "")),
        )
    return None


def _element_counts(value: Any) -> dict[str, float]:
    return {
        str(element): float(count)
        for element, count in _mapping(value, field_name="elements").items()
    }


def _balance_check_name(check_type: str) -> str:
    return {
        "elemental": "elemental_balance",
        "charge": "charge_balance",
        "electron": "electron_balance",
        "redox": "electron_balance",
    }.get(check_type, "static_balance")


def _role_from_signed_coefficient(coefficient: float) -> str:
    tolerance = _stoichiometric_tolerance()
    if coefficient < -tolerance:
        return "reactant"
    if coefficient > tolerance:
        return "product"
    return "unchanged"


def _stoichiometric_tolerance() -> float:
    return float(DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE.quantity.magnitude)


def _check_types(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = (value,)
    else:
        values = tuple(str(item) for item in _sequence(value, field_name="checks"))
    normalized = tuple(item.strip().lower() for item in values)
    unknown = tuple(item for item in normalized if item not in _CHECK_TYPES)
    if unknown:
        return normalized
    return normalized or ("elemental",)


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return value


def _sequence(value: Any, *, field_name: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError(f"{field_name} must be a sequence.")
    return tuple(value)


def _source_from_mapping(data: Mapping[str, Any]) -> str | None:
    provenance = data.get("provenance")
    if isinstance(provenance, Mapping) and has_text(provenance.get("source")):
        return str(provenance["source"])
    return _optional_text(data.get("source"))


def _optional_text(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return str(value)


__all__ = [
    "blocking_static_balance_validations",
    "configured_static_balance_validations",
    "static_validation_callable",
]
