"""Minimal SABIO-RK export parsing for curated source snapshots."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class SabioRKParseError(ValueError):
    """Raised when a saved SABIO-RK export cannot be parsed or selected."""


@dataclass(frozen=True)
class SabioRKExport:
    """Saved SABIO-RK kinetic-law export envelope."""

    path: Path
    meta: Mapping[str, Any]
    entries: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "meta": deepcopy(dict(self.meta)),
            "data": [deepcopy(dict(entry)) for entry in self.entries],
        }


@dataclass(frozen=True)
class SabioRKSelection:
    """Selected SABIO-RK kinetic-law entry and JSON-safe report metadata."""

    selected_entry: Mapping[str, Any]
    selected_entry_id: str
    selection_reason: str
    missing_required_fields: tuple[str, ...]
    warnings: tuple[str, ...]
    rejected_candidates: tuple[Mapping[str, str], ...]

    def to_report(self) -> dict[str, Any]:
        return {
            "selected_entry_id": self.selected_entry_id,
            "selection_reason": self.selection_reason,
            "missing_required_fields": list(self.missing_required_fields),
            "warnings": list(self.warnings),
            "rejected_candidates": [dict(candidate) for candidate in self.rejected_candidates],
        }

    def to_dict(self) -> dict[str, Any]:
        report = self.to_report()
        report["selected_entry"] = deepcopy(dict(self.selected_entry))
        return report


@dataclass(frozen=True)
class _Features:
    entry_id: str
    reaction_id_match: bool
    reaction_id_present: bool
    equation_match: bool
    enzyme_name_match: bool
    ec_number_match: bool
    substrate_match: bool
    product_match: bool
    kinetic_law_priority: int
    kinetic_law_type: str | None
    is_wildtype: bool
    ph_is_5: bool
    temperature_is_30_c: bool
    has_km: bool
    has_kcat: bool
    has_clear_vmax: bool
    reference_score: int
    ph_value: Any
    temperature_value: Any
    temperature_unit: str | None

    @property
    def parameter_priority(self) -> int:
        if self.has_km and self.has_kcat:
            return 2
        if self.has_km and self.has_clear_vmax:
            return 1
        return 0

    def score(self, index: int) -> tuple[int, ...]:
        return (
            int(self.reaction_id_match),
            int(self.equation_match),
            int(self.enzyme_name_match),
            int(self.ec_number_match),
            int(self.substrate_match),
            int(self.product_match),
            self.kinetic_law_priority,
            int(self.is_wildtype),
            int(self.ph_is_5),
            int(self.temperature_is_30_c),
            self.parameter_priority,
            self.reference_score,
            -index,
        )


@dataclass(frozen=True)
class _Candidate:
    index: int
    entry: Mapping[str, Any]
    features: _Features
    hard_rejection: str | None


def load_sabiork_kinlaw_export(path: str | Path) -> SabioRKExport:
    """Load a saved SABIO-RK kinetic-law JSON export without normalizing values."""

    export_path = Path(path)
    try:
        payload = json.loads(export_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SabioRKParseError(f"SABIO-RK export is not valid JSON: {export_path}") from exc
    if not isinstance(payload, Mapping):
        raise SabioRKParseError("SABIO-RK export must be a JSON object.")
    meta = payload.get("meta")
    data = payload.get("data")
    if not isinstance(meta, Mapping):
        raise SabioRKParseError("SABIO-RK export is missing a JSON-object 'meta' field.")
    if not isinstance(data, list):
        raise SabioRKParseError("SABIO-RK export is missing a JSON-array 'data' field.")
    entries: list[Mapping[str, Any]] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, Mapping):
            raise SabioRKParseError(f"SABIO-RK export data entry {index} is not a JSON object.")
        entries.append(deepcopy(dict(entry)))
    return SabioRKExport(path=export_path, meta=deepcopy(dict(meta)), entries=tuple(entries))


def select_reaction_618_candidate(export: SabioRKExport) -> SabioRKSelection:
    """Select one Reaction 618 beta-glucosidase candidate by the REAL-001B rules."""

    candidates = tuple(_candidate(entry, index) for index, entry in enumerate(export.entries))
    if not candidates:
        raise SabioRKParseError("SABIO-RK export contains no kinetic-law entries.")
    eligible = tuple(candidate for candidate in candidates if candidate.hard_rejection is None)
    if not eligible:
        rejected = tuple(
            {"entry_id": candidate.features.entry_id, "reason": candidate.hard_rejection or "not_eligible"}
            for candidate in candidates
        )
        raise SabioRKParseError(f"No Reaction 618 candidate is eligible: {rejected}")

    selected = max(eligible, key=lambda candidate: candidate.features.score(candidate.index))
    missing_required_fields = _missing_required_fields(selected.features)
    warnings = _selection_warnings(selected.features, missing_required_fields)
    rejected_candidates = tuple(
        {
            "entry_id": candidate.features.entry_id,
            "reason": candidate.hard_rejection or _rejection_reason(selected.features, candidate.features),
        }
        for candidate in candidates
        if candidate.index != selected.index
    )
    return SabioRKSelection(
        selected_entry=deepcopy(dict(selected.entry)),
        selected_entry_id=selected.features.entry_id,
        selection_reason=_selection_reason(selected.features),
        missing_required_fields=missing_required_fields,
        warnings=warnings,
        rejected_candidates=rejected_candidates,
    )


def write_sabiork_selection_outputs(selection: SabioRKSelection, output_dir: str | Path) -> tuple[Path, Path]:
    """Write the selected raw entry and JSON-safe selection report."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    selected_path = directory / f"selected_kinlaw_entry_{selection.selected_entry_id}.json"
    report_path = directory / "selection_report.json"
    selected_path.write_text(
        json.dumps(selection.selected_entry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(selection.to_report(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return selected_path, report_path


def _candidate(entry: Mapping[str, Any], index: int) -> _Candidate:
    features = _features(entry, index)
    hard_rejection = None
    if features.reaction_id_present and not features.reaction_id_match:
        hard_rejection = "reaction_id_mismatch"
    return _Candidate(index=index, entry=entry, features=features, hard_rejection=hard_rejection)


def _features(entry: Mapping[str, Any], index: int) -> _Features:
    reaction_ids = _reaction_ids(entry)
    parameters = _parameters(entry)
    temperature_value, temperature_unit = _temperature(entry)
    return _Features(
        entry_id=_entry_id(entry, index),
        reaction_id_match="618" in reaction_ids,
        reaction_id_present=bool(reaction_ids),
        equation_match=_equation_matches(entry),
        enzyme_name_match=_contains_text(_field_values(entry, ("EnzymeName", "enzyme_name")), "beta-glucosidase"),
        ec_number_match=_contains_text(_field_values(entry, ("ECNumber", "ec_number")), "3.2.1.21"),
        substrate_match=_contains_text(_substrate_names(entry), "Cellobiose"),
        product_match=(
            _contains_text(_product_names(entry), "beta-D-Glucose")
            or _contains_text(_product_names(entry), "glucose")
        ),
        kinetic_law_priority=_kinetic_law_priority(_kinetic_law_type(entry)),
        kinetic_law_type=_kinetic_law_type(entry),
        is_wildtype=_is_wildtype(entry),
        ph_is_5=_is_close(_ph_value(entry), 5.0),
        temperature_is_30_c=_temperature_is_30_c(temperature_value, temperature_unit),
        has_km=_has_parameter(parameters, "Km"),
        has_kcat=_has_parameter(parameters, "kcat"),
        has_clear_vmax=_has_clear_vmax(parameters),
        reference_score=_reference_score(entry),
        ph_value=_ph_value(entry),
        temperature_value=temperature_value,
        temperature_unit=temperature_unit,
    )


def _entry_id(entry: Mapping[str, Any], index: int) -> str:
    for key in ("EntryID", "entry_id", "id"):
        if key in entry and entry[key] is not None:
            return str(entry[key])
    return f"entry_index_{index}"


def _reaction_ids(entry: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("SabioReactionID", "ReactionID"):
        if key in entry:
            values.update(_text_values(entry[key]))
    reaction = entry.get("reaction")
    if isinstance(reaction, Mapping):
        for key in ("SabioReactionID", "ReactionID", "id"):
            if key in reaction:
                values.update(_text_values(reaction[key]))
    return values


def _equation_matches(entry: Mapping[str, Any]) -> bool:
    equations = _field_values(entry, ("ReactionEquation", "equation", "equation_normalized"))
    return _contains_text(equations, "Cellobiose") and _contains_text(equations, "beta-D-Glucose")


def _field_values(entry: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        if key in entry:
            values.extend(_text_values(entry[key]))
    for container_name in (
        "reaction",
        "enzyme_description",
        "kineticlaw",
        "experimental_conditions",
        "publication",
        "general",
    ):
        container = entry.get(container_name)
        if not isinstance(container, Mapping):
            continue
        for key in keys:
            if key in container:
                values.extend(_text_values(container[key]))
    return values


def _substrate_names(entry: Mapping[str, Any]) -> list[str]:
    names = _field_values(entry, ("Substrate", "substrate"))
    names.extend(_species_names(entry, roles=("substrate",)))
    return names


def _product_names(entry: Mapping[str, Any]) -> list[str]:
    names = _field_values(entry, ("Product", "product"))
    names.extend(_species_names(entry, roles=("product",)))
    return names


def _species_names(entry: Mapping[str, Any], *, roles: Sequence[str]) -> list[str]:
    reaction = entry.get("reaction")
    if not isinstance(reaction, Mapping):
        return []
    species = reaction.get("species")
    if not isinstance(species, list):
        return []
    role_set = {role.lower() for role in roles}
    names: list[str] = []
    for item in species:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role", "")).lower()
        if role not in role_set:
            continue
        compound = item.get("compound")
        if isinstance(compound, Mapping):
            names.extend(_text_values(compound.get("name")))
        else:
            names.extend(_text_values(compound))
    return names


def _kinetic_law_type(entry: Mapping[str, Any]) -> str | None:
    kinetic_law = entry.get("kineticlaw")
    if isinstance(kinetic_law, Mapping):
        kinlaw_type = kinetic_law.get("kinlaw_type")
        if isinstance(kinlaw_type, Mapping) and kinlaw_type.get("name") is not None:
            return str(kinlaw_type["name"])
        if kinlaw_type is not None and not isinstance(kinlaw_type, Mapping):
            return str(kinlaw_type)
    values = _field_values(entry, ("KineticLawType", "kinlaw_type"))
    return values[0] if values else None


def _kinetic_law_priority(kinetic_law_type: str | None) -> int:
    if kinetic_law_type is None:
        return 0
    normalized = kinetic_law_type.strip().lower()
    if normalized == "michaelis-menten":
        return 2
    if normalized == "michaelis-menten (ph-dependent)":
        return 1
    return 0


def _is_wildtype(entry: Mapping[str, Any]) -> bool:
    values = _field_values(entry, ("EnzymeType", "wildtype"))
    return any(value.strip().lower() in {"wildtype", "wild type"} for value in values)


def _ph_value(entry: Mapping[str, Any]) -> Any:
    for value in _field_values(entry, ("pHMin", "ph", "envvar_ph")):
        number = _as_float(value)
        if number is not None:
            return number
    conditions = entry.get("experimental_conditions")
    if isinstance(conditions, Mapping):
        envvar_ph = conditions.get("envvar_ph")
        if isinstance(envvar_ph, Mapping):
            return envvar_ph.get("start_value")
    return None


def _temperature(entry: Mapping[str, Any]) -> tuple[Any, str | None]:
    for value in _field_values(entry, ("TemperatureMin", "temperature")):
        number = _as_float(value)
        if number is not None:
            return number, None
    conditions = entry.get("experimental_conditions")
    if isinstance(conditions, Mapping):
        envvar_temperature = conditions.get("envvar_temperature")
        if isinstance(envvar_temperature, Mapping):
            unit = envvar_temperature.get("unit")
            return envvar_temperature.get("start_value"), None if unit is None else str(unit)
    return None, None


def _temperature_is_30_c(value: Any, unit: str | None) -> bool:
    number = _as_float(value)
    if number is None:
        return False
    if unit is None:
        return _is_close(number, 30.0)
    normalized = unit.strip().lower()
    if normalized in {"c", "degc", "celsius"} or "c" in normalized:
        return _is_close(number, 30.0)
    if normalized in {"k", "kelvin"}:
        return _is_close(number, 303.15)
    return _is_close(number, 30.0)


def _parameters(entry: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    kinetic_law = entry.get("kineticlaw")
    if not isinstance(kinetic_law, Mapping):
        return ()
    parameters = kinetic_law.get("parameter", ())
    if isinstance(parameters, Mapping):
        return (parameters,)
    if not isinstance(parameters, list):
        return ()
    return tuple(parameter for parameter in parameters if isinstance(parameter, Mapping))


def _has_parameter(parameters: Sequence[Mapping[str, Any]], parameter_type: str) -> bool:
    expected = parameter_type.strip().lower()
    return any(
        _parameter_type_name(parameter).strip().lower() == expected
        and _parameter_has_value_and_unit(parameter)
        for parameter in parameters
    )


def _has_clear_vmax(parameters: Sequence[Mapping[str, Any]]) -> bool:
    has_vmax = any(
        _parameter_type_name(parameter).strip().lower() == "vmax"
        and _parameter_has_value_and_unit(parameter)
        for parameter in parameters
    )
    if not has_vmax:
        return False
    return any(
        _parameter_type_name(parameter).strip().lower() == "concentration"
        and _parameter_has_value_and_unit(parameter)
        and _contains_text(_text_values(parameter.get("species")), "enzyme")
        for parameter in parameters
    )


def _parameter_type_name(parameter: Mapping[str, Any]) -> str:
    for key in ("ParameterType", "parameter_type", "type", "name"):
        if key not in parameter:
            continue
        value = parameter[key]
        if isinstance(value, Mapping) and value.get("name") is not None:
            return str(value["name"])
        if value is not None:
            return str(value)
    return ""


def _parameter_has_value_and_unit(parameter: Mapping[str, Any]) -> bool:
    value_present = any(
        key in parameter and parameter[key] is not None
        for key in ("start_value", "value", "lower_value", "upper_value")
    )
    if not value_present:
        return False
    unit = parameter.get("unit", parameter.get("units"))
    if isinstance(unit, Mapping):
        unit_values = _text_values(unit.get("name")) + _text_values(unit.get("n_name"))
    else:
        unit_values = _text_values(unit)
    return any(value.strip() not in {"", "-"} for value in unit_values)


def _reference_score(entry: Mapping[str, Any]) -> int:
    publication = entry.get("publication")
    if not isinstance(publication, Mapping):
        return 0
    fields = ("pubmed_id", "title", "year", "journal", "author")
    return sum(1 for field in fields if _has_value(publication.get(field)))


def _missing_required_fields(features: _Features) -> tuple[str, ...]:
    missing: list[str] = []
    if features.entry_id.startswith("entry_index_"):
        missing.append("EntryID")
    if not features.reaction_id_present or not features.reaction_id_match:
        missing.append("SabioReactionID:618")
    if not features.equation_match:
        missing.append("reaction_equation_cellobiose_to_beta_D_glucose")
    if not features.enzyme_name_match:
        missing.append("enzyme_name_beta_glucosidase")
    if not features.ec_number_match:
        missing.append("ec_number_3.2.1.21")
    if not features.substrate_match:
        missing.append("substrate_cellobiose")
    if not features.product_match:
        missing.append("product_beta_D_glucose")
    if features.kinetic_law_priority == 0:
        missing.append("kinetic_law_type_michaelis_menten")
    if not features.has_km:
        missing.append("Km")
    if not features.has_kcat and not features.has_clear_vmax:
        missing.append("kcat_or_clear_Vmax")
    return tuple(missing)


def _selection_warnings(features: _Features, missing_required_fields: Sequence[str]) -> tuple[str, ...]:
    warnings: list[str] = []
    if missing_required_fields:
        warnings.append("Selected best available candidate has missing required fields; no values were invented.")
    if features.kinetic_law_priority == 1:
        warnings.append("Selected candidate uses a pH-dependent Michaelis-Menten law because no higher-ranked plain case was selected.")
    if features.has_clear_vmax and not features.has_kcat:
        warnings.append("Selected candidate uses Vmax context instead of kcat; downstream curation must verify units and enzyme context.")
    return tuple(warnings)


def _selection_reason(features: _Features) -> str:
    law = features.kinetic_law_type or "unknown kinetic law"
    parameter_text = "Km and kcat present" if features.has_km and features.has_kcat else "incomplete parameter set"
    if features.has_km and features.has_clear_vmax and not features.has_kcat:
        parameter_text = "Km present with clear Vmax context"
    return (
        f"Selected entry {features.entry_id} by ordered REAL-001B rules: "
        "Reaction 618 match, Cellobiose to beta-D-Glucose reaction, beta-glucosidase enzyme, "
        f"EC 3.2.1.21, Cellobiose substrate, glucose product, {law}, "
        f"{'wildtype' if features.is_wildtype else 'non-wildtype or unknown enzyme type'}, "
        f"pH {features.ph_value}, temperature {features.temperature_value} {features.temperature_unit}, "
        f"{parameter_text}, reference metadata score {features.reference_score}/5."
    )


def _rejection_reason(selected: _Features, candidate: _Features) -> str:
    comparisons = (
        ("reaction_id_not_preferred", selected.reaction_id_match, candidate.reaction_id_match),
        ("reaction_equation_not_preferred", selected.equation_match, candidate.equation_match),
        ("enzyme_name_not_beta_glucosidase", selected.enzyme_name_match, candidate.enzyme_name_match),
        ("ec_number_not_3.2.1.21", selected.ec_number_match, candidate.ec_number_match),
        ("substrate_not_cellobiose", selected.substrate_match, candidate.substrate_match),
        ("product_not_beta_D_glucose_or_glucose", selected.product_match, candidate.product_match),
        ("lower_priority_kinetic_law_type", selected.kinetic_law_priority, candidate.kinetic_law_priority),
        ("lower_priority_enzyme_type", selected.is_wildtype, candidate.is_wildtype),
        ("ph_not_5.0", selected.ph_is_5, candidate.ph_is_5),
        ("temperature_not_30_C", selected.temperature_is_30_c, candidate.temperature_is_30_c),
        ("missing_Km_or_kcat", selected.parameter_priority, candidate.parameter_priority),
        ("less_complete_reference_metadata", selected.reference_score, candidate.reference_score),
    )
    for reason, selected_value, candidate_value in comparisons:
        if selected_value != candidate_value:
            return reason
    return "lower_ordered_selection_score"


def _contains_text(values: Any, target: str) -> bool:
    target_lower = target.lower()
    return any(target_lower in value.lower() for value in _text_values(values))


def _text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, Mapping):
        values: list[str] = []
        for nested in value.values():
            values.extend(_text_values(nested))
        return values
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        values = []
        for nested in value:
            values.extend(_text_values(nested))
        return values
    return [str(value)]


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_close(value: Any, expected: float) -> bool:
    number = _as_float(value)
    if number is None:
        return False
    return abs(number - expected) <= 1e-9


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value)
    return True


__all__ = [
    "SabioRKExport",
    "SabioRKParseError",
    "SabioRKSelection",
    "load_sabiork_kinlaw_export",
    "select_reaction_618_candidate",
    "write_sabiork_selection_outputs",
]
