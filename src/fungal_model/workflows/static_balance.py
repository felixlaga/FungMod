"""Assembly-time static balance checks for configured model metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fungal_model.chemistry.stoichiometry import (
    ElementalComposition,
    StoichiometricReactionMetadata,
    StoichiometricTerm,
)
from fungal_model.core.provenance import has_text
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


def configured_static_balance_validations(config: ModelConfig) -> tuple[ValidationResult, ...]:
    """Build static assembly-time validation results from optional config sections."""

    raw = config.raw
    check_entries = _sequence(raw.get("balance_checks", ()), field_name="balance_checks")
    if not check_entries:
        return ()
    species = _species_metadata(raw.get("chemistry_metadata"))
    reactions = _reaction_metadata(raw.get("reaction_metadata"), species)
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
                )
                for check_type in check_types
            )
            continue
        for check_type in check_types:
            validations.append(
                _with_check_context(
                    _run_static_check(check_type=check_type, reaction=reaction, required=required),
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
) -> ValidationResult:
    name = {
        "elemental": "elemental_balance",
        "charge": "charge_balance",
        "electron": "electron_balance",
        "redox": "electron_balance",
    }.get(check_type, "static_balance")
    return ValidationResult(
        name=name,
        passed=False,
        status="inconclusive",
        severity="error" if required else "warning",
        required=required,
        message="Static balance check is inconclusive because referenced reaction metadata is missing.",
        details={
            "check_id": check_id,
            "reaction_id": reaction_id,
            "check_type": check_type,
            "assembly_time": True,
            "missing_metadata": [f"reaction_metadata.{reaction_id or '<blank>'}"],
        },
    )


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


def _species_metadata(value: Any) -> dict[str, _SpeciesStaticMetadata]:
    if value is None:
        return {}
    data = _mapping(value, field_name="chemistry_metadata")
    species_value = data.get("species", data)
    if isinstance(species_value, Mapping):
        return {
            str(species_id): _species_record_from_mapping(str(species_id), _mapping(species_data, field_name=str(species_id)))
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
) -> dict[str, StoichiometricReactionMetadata]:
    if value is None:
        return {}
    entries = _sequence(value, field_name="reaction_metadata")
    reactions: dict[str, StoichiometricReactionMetadata] = {}
    for index, reaction_data in enumerate(entries):
        data = _mapping(reaction_data, field_name=f"reaction_metadata[{index}]")
        reaction_id = str(data.get("id") or data.get("reaction_id") or "").strip()
        if not reaction_id:
            raise ValueError("Reaction metadata requires id or reaction_id.")
        reactions[reaction_id] = StoichiometricReactionMetadata(
            name=str(data.get("name") or reaction_id),
            reactants=_participant_terms(data.get("reactants", ()), species, field_name=f"{reaction_id}.reactants"),
            products=_participant_terms(data.get("products", ()), species, field_name=f"{reaction_id}.products"),
            source=_source_from_mapping(data),
            notes=str(data.get("notes", "")),
        )
    return reactions


def _participant_terms(
    value: Any,
    species: Mapping[str, _SpeciesStaticMetadata],
    *,
    field_name: str,
) -> tuple[StoichiometricTerm, ...]:
    entries = _sequence(value, field_name=field_name)
    terms: list[StoichiometricTerm] = []
    for index, participant_data in enumerate(entries):
        data = _mapping(participant_data, field_name=f"{field_name}[{index}]")
        species_id = str(data.get("species") or data.get("species_id") or "").strip()
        if not species_id:
            raise ValueError(f"{field_name}[{index}] requires species or species_id.")
        record = species.get(species_id)
        terms.append(
            StoichiometricTerm(
                species=species_id,
                coefficient=float(data.get("coefficient", 1.0)),
                composition=None if record is None else record.composition,
                charge=None if record is None else record.charge,
                charge_source=None if record is None else record.charge_source,
                electron_equivalents=None if record is None else record.electron_equivalents,
                electron_source=None if record is None else record.electron_source,
                notes="" if record is None else record.notes,
            )
        )
    return tuple(terms)


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
