"""Minimal SABIO-RK export parsing for curated source snapshots."""

from __future__ import annotations

import csv
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
class SabioRKParameterRange:
    """Literature-derived range for one kinetic parameter in a saved export."""

    parameter_symbol: str
    parameter_type: str
    units: str
    count: int
    status: str
    entry_ids: tuple[str, ...]
    lower: float | None = None
    upper: float | None = None
    min_entry_id: str | None = None
    max_entry_id: str | None = None
    median: float | None = None
    mean: float | None = None
    p05: float | None = None
    p50: float | None = None
    p95: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_symbol": self.parameter_symbol,
            "parameter_type": self.parameter_type,
            "units": self.units,
            "count": self.count,
            "status": self.status,
            "lower": self.lower,
            "upper": self.upper,
            "min_entry_id": self.min_entry_id,
            "max_entry_id": self.max_entry_id,
            "median": self.median,
            "mean": self.mean,
            "p05": self.p05,
            "p50": self.p50,
            "p95": self.p95,
            "entry_ids": list(self.entry_ids),
        }


@dataclass(frozen=True)
class SabioRKParameterRangeReport:
    """Curated Km/kcat range report derived from a saved SABIO-RK export."""

    source_reaction_id: str
    source_export: str
    criteria: Mapping[str, Any]
    ranges: Mapping[str, Mapping[str, Mapping[str, SabioRKParameterRange]]]
    included_entry_ids: tuple[str, ...]
    excluded_entries: tuple[Mapping[str, Any], ...]
    eligible_entries: tuple[Mapping[str, Any], ...]
    observations: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_reaction_id": self.source_reaction_id,
            "source_export": self.source_export,
            "criteria": deepcopy(dict(self.criteria)),
            "ranges": {
                group_type: {
                    group_key: {
                        symbol: parameter_range.to_dict()
                        for symbol, parameter_range in parameter_ranges.items()
                    }
                    for group_key, parameter_ranges in groups.items()
                }
                for group_type, groups in self.ranges.items()
            },
            "included_entry_ids": list(self.included_entry_ids),
            "excluded_entries": [dict(entry) for entry in self.excluded_entries],
            "eligible_entries": [deepcopy(dict(entry)) for entry in self.eligible_entries],
            "observations": [deepcopy(dict(observation)) for observation in self.observations],
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


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


def curate_reaction_618_parameter_ranges(export: SabioRKExport) -> SabioRKParameterRangeReport:
    """Curate Km/kcat ranges from eligible local Reaction 618 kinetic-law entries."""

    paired_observations: list[dict[str, Any]] = []
    eligible_entries: list[dict[str, Any]] = []
    included_entry_ids: list[str] = []
    excluded_entries: list[Mapping[str, Any]] = []
    for index, entry in enumerate(export.entries):
        candidate = _candidate(entry, index)
        exclusion = _range_entry_exclusion(candidate)
        if exclusion is not None:
            excluded_entries.append(_excluded_entry(entry, candidate.features, reason=exclusion))
            continue
        parameters = _parameters(entry)
        km = _parameter_for_type(parameters, "Km", species_contains="Cellobiose")
        kcat = _parameter_for_type(parameters, "kcat")
        parameter_exclusion = _paired_parameter_exclusion(km=km, kcat=kcat)
        if parameter_exclusion is not None:
            excluded_entries.append(_excluded_entry(entry, candidate.features, reason=parameter_exclusion))
            continue
        assert km is not None
        assert kcat is not None
        included_entry_ids.append(candidate.features.entry_id)
        eligible_entries.append(_eligible_entry(entry=entry, features=candidate.features, km=km, kcat=kcat))
        paired_observations.append(
            _paired_observation(
                entry=entry,
                features=candidate.features,
                km=km,
                kcat=kcat,
            )
        )
    ranges = _range_groups(paired_observations)
    return SabioRKParameterRangeReport(
        source_reaction_id="618",
        source_export=str(export.path),
        criteria={
            "reaction_id": "618",
            "reaction": "Cellobiose to beta-D-Glucose",
            "enzyme_name_contains": "beta-glucosidase",
            "ec_number": "3.2.1.21",
            "kinetic_law_type": "Michaelis-Menten",
            "required_parameters": ["Km_cellobiose", "kcat_cellobiose"],
            "accepted_units": {
                "Km_cellobiose": "mM",
                "kcat_cellobiose": "s^(-1)",
            },
            "unit_conversion": "none; source start_value and unit.name are preserved",
            "minimum_n_for_robust_group": 2,
        },
        ranges=ranges,
        included_entry_ids=tuple(included_entry_ids),
        excluded_entries=tuple(excluded_entries),
        eligible_entries=tuple(eligible_entries),
        observations=tuple(paired_observations),
        warnings=(
            "The Km/kcat ranges pool multiple SABIO-RK Reaction 618 entries across organisms and/or assay conditions.",
            "Ranges are exploratory literature priors, not selected-entry uncertainty or calibrated environmental response laws.",
        ),
        limitations=(
            "No live SABIO-RK API access is required or used by this curation path.",
            "No unit conversion is applied; accepted source units are preserved.",
            "Broad cross-entry ranges are not posterior uncertainty estimates.",
            "Broad cross-entry ranges are not pH or temperature response models.",
            "The selected exact EntryID 35622 values remain separate registry records.",
        ),
    )


def write_sabiork_parameter_range_report(
    report: SabioRKParameterRangeReport,
    output_dir: str | Path,
) -> Path:
    """Write JSON, CSV, and Markdown SABIO-RK parameter range reports."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "parameter_range_summary.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_curated_csv(
        directory / "reaction_618_eligible_entries.csv",
        report.eligible_entries,
        fieldnames=_ELIGIBLE_ENTRY_FIELDNAMES,
    )
    _write_curated_csv(
        directory / "reaction_618_excluded_entries.csv",
        report.excluded_entries,
        fieldnames=_EXCLUDED_ENTRY_FIELDNAMES,
    )
    (directory / "parameter_range_summary.md").write_text(
        _parameter_range_markdown(report),
        encoding="utf-8",
    )
    return report_path


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


def _range_entry_exclusion(candidate: _Candidate) -> str | None:
    features = candidate.features
    if candidate.hard_rejection is not None:
        return candidate.hard_rejection
    if not features.reaction_id_match:
        return "reaction_id_not_618"
    if not features.equation_match:
        return "reaction_equation_not_cellobiose_to_beta_D_glucose"
    if not features.enzyme_name_match:
        return "enzyme_name_not_beta_glucosidase"
    if not features.ec_number_match:
        return "ec_number_not_3_2_1_21"
    if not features.substrate_match:
        return "substrate_not_cellobiose"
    if not features.product_match:
        return "product_not_beta_D_glucose_or_glucose"
    if features.kinetic_law_type != "Michaelis-Menten":
        return "kinetic_law_not_plain_michaelis_menten"
    return None


def _parameter_for_type(
    parameters: Sequence[Mapping[str, Any]],
    parameter_type: str,
    *,
    species_contains: str | None = None,
) -> Mapping[str, Any] | None:
    expected = parameter_type.strip().lower()
    for parameter in parameters:
        if _parameter_type_name(parameter).strip().lower() != expected:
            continue
        if species_contains is not None and not _contains_text(
            _text_values(parameter.get("species")),
            species_contains,
        ):
            continue
        return parameter
    return None


def _paired_parameter_exclusion(
    *,
    km: Mapping[str, Any] | None,
    kcat: Mapping[str, Any] | None,
) -> str | None:
    if km is None:
        return "missing_Km_cellobiose"
    if kcat is None:
        return "missing_kcat"
    if _parameter_numeric_value(km) is None:
        return "missing_Km_cellobiose_value"
    if _parameter_unit_name(km) != "mM":
        return "unsupported_Km_cellobiose_units"
    if _parameter_numeric_value(kcat) is None:
        return "missing_kcat_value"
    if _parameter_unit_name(kcat) != "s^(-1)":
        return "unsupported_kcat_units"
    return None


_ELIGIBLE_ENTRY_FIELDNAMES = (
    "entry_id",
    "organism",
    "enzyme_name",
    "ec_number",
    "enzyme_type",
    "kinetic_law_type",
    "Km_cellobiose_value",
    "Km_cellobiose_units",
    "kcat_cellobiose_value",
    "kcat_cellobiose_units",
    "ph",
    "temperature",
    "temperature_units",
    "buffer",
    "pubmed_id",
    "title",
    "journal",
    "year",
    "source_field_Km",
    "source_field_kcat",
)

_EXCLUDED_ENTRY_FIELDNAMES = (
    "entry_id",
    "reason",
    "organism",
    "enzyme_name",
    "ec_number",
    "kinetic_law_type",
    "available_parameter_types",
    "notes",
)

_MINIMUM_GROUP_N = 2


def _eligible_entry(
    *,
    entry: Mapping[str, Any],
    features: _Features,
    km: Mapping[str, Any],
    kcat: Mapping[str, Any],
) -> dict[str, Any]:
    publication = _publication(entry)
    return {
        "entry_id": features.entry_id,
        "organism": _organism_name(entry) or "",
        "enzyme_name": _enzyme_name(entry) or "",
        "ec_number": _ec_number(entry) or "",
        "enzyme_type": _enzyme_type(entry) or "unknown",
        "kinetic_law_type": features.kinetic_law_type,
        "Km_cellobiose_value": _parameter_numeric_value(km),
        "Km_cellobiose_units": _parameter_unit_name(km),
        "kcat_cellobiose_value": _parameter_numeric_value(kcat),
        "kcat_cellobiose_units": _parameter_unit_name(kcat),
        "ph": features.ph_value,
        "temperature": features.temperature_value,
        "temperature_units": features.temperature_unit,
        "buffer": _buffer(entry) or "",
        "pubmed_id": publication.get("pubmed_id"),
        "title": publication.get("title"),
        "journal": publication.get("journal"),
        "year": publication.get("year"),
        "source_field_Km": "kineticlaw.parameter[].start_value",
        "source_field_kcat": "kineticlaw.parameter[].start_value",
    }


def _excluded_entry(
    entry: Mapping[str, Any],
    features: _Features,
    *,
    reason: str,
) -> dict[str, Any]:
    return {
        "entry_id": features.entry_id,
        "reason": reason,
        "organism": _organism_name(entry) or "",
        "enzyme_name": _enzyme_name(entry) or "",
        "ec_number": _ec_number(entry) or "",
        "kinetic_law_type": features.kinetic_law_type or "",
        "available_parameter_types": ";".join(_available_parameter_types(entry)),
        "notes": _exclusion_notes(reason),
    }


def _paired_observation(
    *,
    entry: Mapping[str, Any],
    features: _Features,
    km: Mapping[str, Any],
    kcat: Mapping[str, Any],
) -> dict[str, Any]:
    observation = _eligible_entry(entry=entry, features=features, km=km, kcat=kcat)
    observation.update(
        {
            "Km_cellobiose_parameter_type": "Km",
            "kcat_cellobiose_parameter_type": "kcat",
        }
    )
    return observation


def _range_groups(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, SabioRKParameterRange]]]:
    observation_tuple = tuple(observations)
    groups: Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]] = {
        "all_eligible": {"all_eligible": observation_tuple},
        "by_organism": _group_by(observation_tuple, "organism"),
        "by_pH_exact": _group_by(observation_tuple, "ph", prefix="pH"),
        "by_temperature_exact": _group_by_temperature(observation_tuple),
        "by_organism_and_pH": _group_by_organism_and_ph(observation_tuple),
        "wildtype_only": {
            "wildtype_only": tuple(
                observation
                for observation in observation_tuple
                if str(observation.get("enzyme_type", "")).strip().lower() in {"wildtype", "wild type"}
            )
        },
        "mutant_only": {
            "mutant_only": tuple(
                observation
                for observation in observation_tuple
                if str(observation.get("enzyme_type", "")).strip().lower()
                not in {"", "unknown", "wildtype", "wild type"}
            )
        },
    }
    return {
        group_type: {
            group_key: _parameter_ranges_for_group(group_observations)
            for group_key, group_observations in group_items.items()
        }
        for group_type, group_items in groups.items()
    }


def _parameter_ranges_for_group(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, SabioRKParameterRange]:
    return {
        "Km_cellobiose": _parameter_range(
            symbol="Km_cellobiose",
            parameter_type="Km",
            observations=observations,
            value_key="Km_cellobiose_value",
            unit_key="Km_cellobiose_units",
            default_units="mM",
        ),
        "kcat_cellobiose": _parameter_range(
            symbol="kcat_cellobiose",
            parameter_type="kcat",
            observations=observations,
            value_key="kcat_cellobiose_value",
            unit_key="kcat_cellobiose_units",
            default_units="s^(-1)",
        ),
    }


def _parameter_range(
    *,
    symbol: str,
    parameter_type: str,
    observations: Sequence[Mapping[str, Any]],
    value_key: str,
    unit_key: str,
    default_units: str,
) -> SabioRKParameterRange:
    numeric_observations = tuple(
        observation
        for observation in observations
        if _as_float(observation.get(value_key)) is not None
    )
    if not numeric_observations:
        return SabioRKParameterRange(
            parameter_symbol=symbol,
            parameter_type=parameter_type,
            units=default_units,
            count=0,
            status="insufficient_n",
            entry_ids=(),
        )
    units = str(numeric_observations[0].get(unit_key) or default_units)
    if any(str(observation.get(unit_key) or default_units) != units for observation in numeric_observations):
        raise SabioRKParseError(f"Mixed units are not allowed for {symbol}.")
    value_entry_pairs: list[tuple[float, str]] = []
    for observation in numeric_observations:
        value = _as_float(observation.get(value_key))
        if value is None:
            continue
        value_entry_pairs.append((value, str(observation["entry_id"])))
    values = tuple(value for value, _entry_id_value in value_entry_pairs)
    min_value, min_entry_id = min(value_entry_pairs, key=lambda item: item[0])
    max_value, max_entry_id = max(value_entry_pairs, key=lambda item: item[0])
    return SabioRKParameterRange(
        parameter_symbol=symbol,
        parameter_type=parameter_type,
        units=units,
        lower=min_value,
        upper=max_value,
        count=len(values),
        status="ok" if len(values) >= _MINIMUM_GROUP_N else "insufficient_n",
        min_entry_id=min_entry_id,
        max_entry_id=max_entry_id,
        median=_quantile(values, 0.5),
        mean=sum(values) / len(values),
        p05=_quantile(values, 0.05),
        p50=_quantile(values, 0.5),
        p95=_quantile(values, 0.95),
        entry_ids=tuple(str(observation["entry_id"]) for observation in numeric_observations),
    )


def _group_by(
    observations: Sequence[Mapping[str, Any]],
    key: str,
    *,
    prefix: str | None = None,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        value = observation.get(key)
        if value in {None, ""}:
            group_key = "unknown"
        else:
            group_key = _group_key(value, prefix=prefix)
        groups.setdefault(group_key, []).append(observation)
    return {group_key: tuple(group) for group_key, group in sorted(groups.items())}


def _group_by_temperature(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        value = observation.get("temperature")
        units = observation.get("temperature_units")
        if value in {None, ""}:
            group_key = "unknown"
        else:
            group_key = _group_key(value)
            if units not in {None, ""}:
                group_key = f"{group_key} {units}"
        groups.setdefault(group_key, []).append(observation)
    return {group_key: tuple(group) for group_key, group in sorted(groups.items())}


def _group_by_organism_and_ph(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        organism = str(observation.get("organism") or "unknown")
        ph = _group_key(observation.get("ph"), prefix="pH") if observation.get("ph") not in {None, ""} else "pH unknown"
        group_key = f"{organism} | {ph}"
        groups.setdefault(group_key, []).append(observation)
    return {group_key: tuple(group) for group_key, group in sorted(groups.items())}


def _group_key(value: Any, *, prefix: str | None = None) -> str:
    number = _as_float(value)
    if number is not None:
        formatted = str(int(number)) if number.is_integer() else str(number)
    else:
        formatted = str(value)
    return f"{prefix} {formatted}" if prefix is not None else formatted


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise SabioRKParseError("Cannot compute a quantile for an empty value set.")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _parameter_numeric_value(parameter: Mapping[str, Any]) -> float | None:
    for key in ("start_value", "value"):
        if key in parameter:
            return _as_float(parameter[key])
    return None


def _parameter_unit_name(parameter: Mapping[str, Any]) -> str | None:
    unit = parameter.get("unit", parameter.get("units"))
    if isinstance(unit, Mapping):
        name = unit.get("name")
        return None if name is None else str(name)
    if unit is None:
        return None
    return str(unit)


def _publication(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    publication = entry.get("publication")
    if isinstance(publication, Mapping):
        return publication
    return {}


def _buffer(entry: Mapping[str, Any]) -> str | None:
    conditions = entry.get("experimental_conditions")
    if isinstance(conditions, Mapping) and conditions.get("buffer") is not None:
        return str(conditions["buffer"])
    return _first_text(_field_values(entry, ("buffer",)))


def _enzyme_type(entry: Mapping[str, Any]) -> str | None:
    enzyme_description = entry.get("enzyme_description")
    if isinstance(enzyme_description, Mapping) and enzyme_description.get("wildtype") is not None:
        return str(enzyme_description["wildtype"])
    return _first_text(_field_values(entry, ("EnzymeType", "wildtype")))


def _available_parameter_types(entry: Mapping[str, Any]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for parameter in _parameters(entry):
        parameter_type = _parameter_type_name(parameter)
        if not parameter_type:
            parameter_type = str(parameter.get("name", "unknown"))
        seen.setdefault(parameter_type, None)
    return tuple(seen)


def _exclusion_notes(reason: str) -> str:
    notes_by_reason = {
        "reaction_id_mismatch": "SABIO-RK reaction identifier does not match Reaction 618.",
        "reaction_id_not_618": "SABIO-RK reaction identifier is absent or not Reaction 618.",
        "reaction_equation_not_cellobiose_to_beta_D_glucose": "Reaction equation does not match Cellobiose to beta-D-Glucose.",
        "enzyme_name_not_beta_glucosidase": "Enzyme name does not identify beta-glucosidase.",
        "ec_number_not_3_2_1_21": "EC number does not include 3.2.1.21.",
        "substrate_not_cellobiose": "Cellobiose substrate was not detected.",
        "product_not_beta_D_glucose_or_glucose": "Glucose product was not detected.",
        "kinetic_law_not_plain_michaelis_menten": "Kinetic law is not plain Michaelis-Menten.",
        "missing_Km_cellobiose": "No Km parameter scoped to Cellobiose was found.",
        "missing_kcat": "No kcat parameter was found.",
        "missing_Km_cellobiose_value": "Km for Cellobiose has no explicit numeric value.",
        "missing_kcat_value": "kcat has no explicit numeric value.",
        "unsupported_Km_cellobiose_units": "Km units are absent or not the accepted source unit mM.",
        "unsupported_kcat_units": "kcat units are absent or not the accepted source unit s^(-1).",
    }
    return notes_by_reason.get(reason, "Entry did not satisfy the DATA-002 inclusion criteria.")


def _write_curated_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _parameter_range_markdown(report: SabioRKParameterRangeReport) -> str:
    lines = [
        "# SABIO-RK Reaction 618 Parameter Range Summary",
        "",
        "## Scope",
        "",
        f"- Source export: `{report.source_export}`",
        f"- Source reaction ID: `{report.source_reaction_id}`",
        f"- Included entries: {len(report.included_entry_ids)}",
        f"- Excluded entries: {len(report.excluded_entries)}",
        "",
        "The Km/kcat ranges pool multiple SABIO-RK Reaction 618 entries across organisms and/or assay conditions. They are useful as exploratory literature priors, not as selected-entry uncertainty or calibrated pH/temperature response laws.",
        "",
        "## All Eligible Range",
        "",
        "| Parameter | Count | Status | Lower | Upper | Median | Mean | p05 | p95 | Units | Entry IDs |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    all_eligible = report.ranges.get("all_eligible", {}).get("all_eligible", {})
    for symbol in ("Km_cellobiose", "kcat_cellobiose"):
        parameter_range = all_eligible.get(symbol)
        if parameter_range is None:
            continue
        lines.append(_markdown_range_row(parameter_range))
    lines.extend(
        [
            "",
            "## Scoped Groups",
            "",
            "| Group type | Group | Parameter | Count | Status | Lower | Upper | Median | Units |",
            "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for group_type, groups in report.ranges.items():
        if group_type == "all_eligible":
            continue
        for group_key, parameter_ranges in groups.items():
            for symbol in ("Km_cellobiose", "kcat_cellobiose"):
                parameter_range = parameter_ranges[symbol]
                lines.append(
                    "| "
                    + " | ".join(
                        (
                            _markdown_cell(group_type),
                            _markdown_cell(str(group_key)),
                            _markdown_cell(symbol),
                            str(parameter_range.count),
                            _markdown_cell(parameter_range.status),
                            _format_optional_number(parameter_range.lower),
                            _format_optional_number(parameter_range.upper),
                            _format_optional_number(parameter_range.median),
                            _markdown_cell(parameter_range.units),
                        )
                    )
                    + " |"
                )
    lines.extend(
        [
            "",
            "## Warnings",
            "",
            *[f"- {warning}" for warning in report.warnings],
            "",
            "## Limitations",
            "",
            *[f"- {limitation}" for limitation in report.limitations],
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_range_row(parameter_range: SabioRKParameterRange) -> str:
    return (
        "| "
        + " | ".join(
            (
                parameter_range.parameter_symbol,
                str(parameter_range.count),
                parameter_range.status,
                _format_optional_number(parameter_range.lower),
                _format_optional_number(parameter_range.upper),
                _format_optional_number(parameter_range.median),
                _format_optional_number(parameter_range.mean),
                _format_optional_number(parameter_range.p05),
                _format_optional_number(parameter_range.p95),
                _markdown_cell(parameter_range.units),
                _markdown_cell(";".join(parameter_range.entry_ids)),
            )
        )
        + " |"
    )


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.12g}"


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value).lower()
    return "" if value is None else value


def _first_text(values: Sequence[str]) -> str | None:
    for value in values:
        if value.strip():
            return value
    return None


def _organism_name(entry: Mapping[str, Any]) -> str | None:
    general = entry.get("general")
    if isinstance(general, Mapping):
        organism = general.get("organism")
        if isinstance(organism, Mapping) and organism.get("name") is not None:
            return str(organism["name"])
    return _first_text(_field_values(entry, ("organism",)))


def _enzyme_name(entry: Mapping[str, Any]) -> str | None:
    enzyme_description = entry.get("enzyme_description")
    if isinstance(enzyme_description, Mapping) and enzyme_description.get("enzyme_name") is not None:
        return str(enzyme_description["enzyme_name"])
    return _first_text(_field_values(entry, ("enzyme_name", "EnzymeName")))


def _ec_number(entry: Mapping[str, Any]) -> str | None:
    enzyme_description = entry.get("enzyme_description")
    if isinstance(enzyme_description, Mapping) and enzyme_description.get("ec_number") is not None:
        return str(enzyme_description["ec_number"])
    return _first_text(_field_values(entry, ("ec_number", "ECNumber")))


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
    "SabioRKParameterRange",
    "SabioRKParameterRangeReport",
    "SabioRKParseError",
    "SabioRKSelection",
    "curate_reaction_618_parameter_ranges",
    "load_sabiork_kinlaw_export",
    "select_reaction_618_candidate",
    "write_sabiork_parameter_range_report",
    "write_sabiork_selection_outputs",
]
