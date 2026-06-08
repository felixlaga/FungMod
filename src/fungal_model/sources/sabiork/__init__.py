"""SABIO-RK source adapter for frozen snapshots and review proposals."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fungal_model.data.sabiork import SabioRKExport, load_sabiork_kinlaw_export


class SabioRKSourceError(ValueError):
    """Raised when SABIO-RK source discovery cannot proceed safely."""


LiveKinlawFetcher = Callable[[str, Path], tuple[Path, Path]]


@dataclass(frozen=True)
class SabioRKSourceSnapshot:
    """Frozen SABIO-RK kinetic-law snapshot loaded from local storage."""

    query: str
    export_path: Path
    metadata_path: Path | None
    export: SabioRKExport
    fetch_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "export_path": str(self.export_path),
            "metadata_path": None if self.metadata_path is None else str(self.metadata_path),
            "fetch_metadata": deepcopy(dict(self.fetch_metadata)),
            "meta": deepcopy(dict(self.export.meta)),
            "entry_count": len(self.export.entries),
        }


@dataclass(frozen=True)
class SabioRKParticipant:
    """Reaction participant extracted from a SABIO-RK kinetic-law entry."""

    entry_id: str
    reaction_id: str
    role: str
    compound_name: str
    stoichiometry: str
    compound_id: str
    location: str
    comment: str
    external_identifiers: Mapping[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "reaction_id": self.reaction_id,
            "role": self.role,
            "compound_name": self.compound_name,
            "stoichiometry": self.stoichiometry,
            "compound_id": self.compound_id,
            "location": self.location,
            "comment": self.comment,
            "external_identifiers": {
                key: list(values)
                for key, values in self.external_identifiers.items()
            },
        }


@dataclass(frozen=True)
class SabioRKKineticParameter:
    """Kinetic-law parameter extracted without changing source values."""

    entry_id: str
    reaction_id: str
    name: str
    parameter_type: str
    role: str
    species: str
    start_value: Any
    end_value: Any
    standard_deviation: Any
    units: str
    normalized_start_value: Any
    normalized_units: str
    proposed_symbol: str
    source_field: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "reaction_id": self.reaction_id,
            "name": self.name,
            "parameter_type": self.parameter_type,
            "role": self.role,
            "species": self.species,
            "start_value": self.start_value,
            "end_value": self.end_value,
            "standard_deviation": self.standard_deviation,
            "units": self.units,
            "normalized_start_value": self.normalized_start_value,
            "normalized_units": self.normalized_units,
            "proposed_symbol": self.proposed_symbol,
            "source_field": self.source_field,
        }


@dataclass(frozen=True)
class SabioRKReactionRecord:
    """Review-ready source record extracted from one SABIO-RK kinetic-law entry."""

    entry_id: str
    reaction_id: str
    equation: str
    kinetic_law_type: str
    formula: str
    reversible: str
    organism: str
    enzyme_name: str
    ec_number: str
    enzyme_type: str
    ph: Any
    temperature: Any
    temperature_units: str
    buffer: str
    publication: Mapping[str, Any]
    participants: tuple[SabioRKParticipant, ...]
    parameters: tuple[SabioRKKineticParameter, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "reaction_id": self.reaction_id,
            "equation": self.equation,
            "kinetic_law_type": self.kinetic_law_type,
            "formula": self.formula,
            "reversible": self.reversible,
            "organism": self.organism,
            "enzyme_name": self.enzyme_name,
            "ec_number": self.ec_number,
            "enzyme_type": self.enzyme_type,
            "ph": self.ph,
            "temperature": self.temperature,
            "temperature_units": self.temperature_units,
            "buffer": self.buffer,
            "publication": deepcopy(dict(self.publication)),
            "participants": [participant.to_dict() for participant in self.participants],
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "warnings": list(self.warnings),
        }

    @property
    def substrates(self) -> tuple[SabioRKParticipant, ...]:
        return tuple(participant for participant in self.participants if participant.role == "substrate")

    @property
    def products(self) -> tuple[SabioRKParticipant, ...]:
        return tuple(participant for participant in self.participants if participant.role == "product")


@dataclass(frozen=True)
class SabioRKProposalWriteResult:
    """Paths written by a source-record proposal bundle."""

    output_directory: Path
    paths: Mapping[str, Path]

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in self.paths.items()}


@dataclass(frozen=True)
class SabioRKRecordProposal:
    """Proposed FungMod records that must be reviewed before registry use."""

    source_query: str
    source_snapshot_path: str
    reaction_records: tuple[SabioRKReactionRecord, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_sabiork_source_proposal",
            "proposal_status": "proposed_review_required",
            "source_query": self.source_query,
            "source_snapshot_path": self.source_snapshot_path,
            "reaction_records": [record.to_dict() for record in self.reaction_records],
            "limitations": list(self.limitations),
        }

    def write(self, output_dir: str | Path) -> SabioRKProposalWriteResult:
        """Write SOURCE-001 proposed records under a curated proposal folder."""

        root = Path(output_dir)
        curated = root / "curated"
        curated.mkdir(parents=True, exist_ok=True)
        paths = {
            "reaction_records": curated / "reaction_records.json",
            "compound_roles": curated / "compound_roles.csv",
            "kinetic_law_entries": curated / "kinetic_law_entries.csv",
            "parameters": curated / "parameters.csv",
            "publications": curated / "publications.csv",
            "proposed_product_maps": curated / "proposed_product_maps.yml",
            "proposed_parameter_records": curated / "proposed_parameter_records.yml",
            "proposed_process_compatibility": curated / "proposed_process_compatibility.yml",
            "source_adapter_report": curated / "source_adapter_report.md",
        }
        _write_json(paths["reaction_records"], self.to_dict())
        _write_csv(paths["compound_roles"], _compound_role_rows(self.reaction_records), _COMPOUND_ROLE_FIELDS)
        _write_csv(paths["kinetic_law_entries"], _kinetic_law_rows(self.reaction_records), _KINETIC_LAW_FIELDS)
        _write_csv(paths["parameters"], _parameter_rows(self.reaction_records), _PARAMETER_FIELDS)
        _write_csv(paths["publications"], _publication_rows(self.reaction_records), _PUBLICATION_FIELDS)
        _write_yaml(paths["proposed_product_maps"], _proposed_product_maps(self))
        _write_yaml(paths["proposed_parameter_records"], _proposed_parameter_records(self))
        _write_yaml(paths["proposed_process_compatibility"], _proposed_process_compatibility(self))
        paths["source_adapter_report"].write_text(_proposal_report_markdown(self), encoding="utf-8")
        return SabioRKProposalWriteResult(output_directory=root, paths=paths)


class SabioRKSource:
    """Controlled SABIO-RK source adapter for frozen snapshots and proposals."""

    def __init__(
        self,
        cache_dir: str | Path = "data/source_snapshots/sabiork",
        *,
        live_fetcher: LiveKinlawFetcher | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.live_fetcher = live_fetcher

    def fetch_kinlaw_entries(
        self,
        query: str,
        *,
        refresh: bool = False,
        output_dir: str | Path | None = None,
    ) -> SabioRKSourceSnapshot:
        """Load a frozen SABIO-RK kinetic-law export, or refresh only by explicit hook."""

        target_dir = Path(output_dir) if output_dir is not None else self.cache_dir
        if refresh:
            if self.live_fetcher is None:
                raise SabioRKSourceError(
                    "Live SABIO-RK refresh requires an explicit live_fetcher. "
                    "Simulation and tests must use frozen local snapshots."
                )
            export_path, metadata_path = self.live_fetcher(query, target_dir / "raw")
        else:
            export_path = _find_cached_export(target_dir, query)
            metadata_path = _metadata_path_for_export(export_path)
        export = load_sabiork_kinlaw_export(export_path)
        metadata = _load_metadata(metadata_path)
        return SabioRKSourceSnapshot(
            query=query,
            export_path=export_path,
            metadata_path=metadata_path,
            export=export,
            fetch_metadata=metadata,
        )

    def load_kinlaw_entries(
        self,
        path: str | Path,
        *,
        query: str = "",
    ) -> SabioRKSourceSnapshot:
        """Load one explicit frozen export path without any network behavior."""

        export_path = Path(path)
        export = load_sabiork_kinlaw_export(export_path)
        metadata_path = _metadata_path_for_export(export_path)
        return SabioRKSourceSnapshot(
            query=query,
            export_path=export_path,
            metadata_path=metadata_path,
            export=export,
            fetch_metadata=_load_metadata(metadata_path),
        )

    def parse_reaction_records(
        self,
        snapshot: SabioRKSourceSnapshot | SabioRKExport | str | Path,
    ) -> tuple[SabioRKReactionRecord, ...]:
        """Parse source entries into review-ready reaction records."""

        export = _export_from_input(snapshot)
        records = tuple(_reaction_record(entry, index) for index, entry in enumerate(export.entries))
        if not records:
            raise SabioRKSourceError("SABIO-RK snapshot contained no entries to parse.")
        return records

    def propose_fungmod_records(
        self,
        reaction_records: Sequence[SabioRKReactionRecord],
        *,
        source_query: str = "",
        source_snapshot_path: str = "",
    ) -> SabioRKRecordProposal:
        """Create review-only proposed FungMod records from parsed source records."""

        records = tuple(reaction_records)
        if not records:
            raise SabioRKSourceError("Cannot propose FungMod records from an empty source-record set.")
        return SabioRKRecordProposal(
            source_query=source_query,
            source_snapshot_path=source_snapshot_path,
            reaction_records=records,
            limitations=(
                "Proposed source records are not simulation registry records.",
                "No source proposal is automatically trusted for scientific simulation.",
                "SABIO-RK does not provide whole-fungus growth, secretion, uptake, biomass, or geometry models.",
                "Kinetic-law parameters preserve source values and units; review must decide conversions and allowed use.",
            ),
        )


def _export_from_input(snapshot: SabioRKSourceSnapshot | SabioRKExport | str | Path) -> SabioRKExport:
    if isinstance(snapshot, SabioRKSourceSnapshot):
        return snapshot.export
    if isinstance(snapshot, SabioRKExport):
        return snapshot
    return load_sabiork_kinlaw_export(snapshot)


def _reaction_record(entry: Mapping[str, Any], index: int) -> SabioRKReactionRecord:
    entry_id = _entry_id(entry, index)
    reaction = _mapping(entry.get("reaction"))
    kinetic_law = _mapping(entry.get("kineticlaw"))
    enzyme = _mapping(entry.get("enzyme_description"))
    conditions = _mapping(entry.get("experimental_conditions"))
    reaction_id = _reaction_id(entry, reaction)
    participants = _participants(entry=entry, entry_id=entry_id, reaction_id=reaction_id)
    record = SabioRKReactionRecord(
        entry_id=entry_id,
        reaction_id=reaction_id,
        equation=_first_text(reaction.get("equation"), entry.get("ReactionEquation")),
        kinetic_law_type=_kinetic_law_type(kinetic_law, entry),
        formula=_text(kinetic_law.get("formula")),
        reversible=_text(kinetic_law.get("reversible")),
        organism=_organism(entry),
        enzyme_name=_first_text(enzyme.get("enzyme_name"), entry.get("EnzymeName")),
        ec_number=_first_text(enzyme.get("ec_number"), entry.get("ECNumber")),
        enzyme_type=_text(enzyme.get("wildtype")),
        ph=_condition_value(conditions, "envvar_ph"),
        temperature=_condition_value(conditions, "envvar_temperature"),
        temperature_units=_condition_units(conditions, "envvar_temperature"),
        buffer=_text(conditions.get("buffer")),
        publication=deepcopy(dict(_mapping(entry.get("publication")))),
        participants=participants,
        parameters=_parameters(entry_id=entry_id, reaction_id=reaction_id, kinetic_law=kinetic_law, record_participants=participants),
        warnings=(),
    )
    return _record_with_warnings(record)


def _record_with_warnings(record: SabioRKReactionRecord) -> SabioRKReactionRecord:
    warnings: list[str] = []
    if not record.participants:
        warnings.append("missing_reaction_species; no participants were guessed from the equation.")
    if not record.substrates:
        warnings.append("missing_substrate_roles")
    if not record.products:
        warnings.append("missing_product_roles")
    if not record.parameters:
        warnings.append("missing_kinetic_law_parameters")
    if not record.publication:
        warnings.append("missing_publication_metadata")
    return SabioRKReactionRecord(
        entry_id=record.entry_id,
        reaction_id=record.reaction_id,
        equation=record.equation,
        kinetic_law_type=record.kinetic_law_type,
        formula=record.formula,
        reversible=record.reversible,
        organism=record.organism,
        enzyme_name=record.enzyme_name,
        ec_number=record.ec_number,
        enzyme_type=record.enzyme_type,
        ph=record.ph,
        temperature=record.temperature,
        temperature_units=record.temperature_units,
        buffer=record.buffer,
        publication=record.publication,
        participants=record.participants,
        parameters=record.parameters,
        warnings=tuple(warnings),
    )


def _participants(
    *,
    entry: Mapping[str, Any],
    entry_id: str,
    reaction_id: str,
) -> tuple[SabioRKParticipant, ...]:
    reaction = _mapping(entry.get("reaction"))
    species = reaction.get("species")
    if not isinstance(species, list):
        return ()
    external_by_compound = _external_compound_identifiers(entry)
    participants: list[SabioRKParticipant] = []
    for item in species:
        if not isinstance(item, Mapping):
            continue
        compound = _mapping(item.get("compound"))
        compound_id = _text(compound.get("id"))
        location = _mapping(item.get("location"))
        participants.append(
            SabioRKParticipant(
                entry_id=entry_id,
                reaction_id=reaction_id,
                role=_normalized_role(item.get("role")),
                compound_name=_first_text(compound.get("name"), item.get("compound")),
                stoichiometry=_text(item.get("stoch_value")),
                compound_id=compound_id,
                location=_text(location.get("name")),
                comment=_text(item.get("comment")),
                external_identifiers=external_by_compound.get(compound_id, {}),
            )
        )
    return tuple(participants)


def _parameters(
    *,
    entry_id: str,
    reaction_id: str,
    kinetic_law: Mapping[str, Any],
    record_participants: Sequence[SabioRKParticipant],
) -> tuple[SabioRKKineticParameter, ...]:
    raw_parameters = kinetic_law.get("parameter")
    if isinstance(raw_parameters, Mapping):
        parameter_items = (raw_parameters,)
    elif isinstance(raw_parameters, list):
        parameter_items = tuple(item for item in raw_parameters if isinstance(item, Mapping))
    else:
        parameter_items = ()
    primary_substrate = _primary_substrate_name(record_participants)
    output: list[SabioRKKineticParameter] = []
    for parameter in parameter_items:
        parameter_type = _parameter_type_name(parameter)
        species = _species_label(parameter.get("species"))
        units = _unit_name(parameter.get("unit", parameter.get("units")))
        output.append(
            SabioRKKineticParameter(
                entry_id=entry_id,
                reaction_id=reaction_id,
                name=_text(parameter.get("name")),
                parameter_type=parameter_type,
                role=_text(parameter.get("role")),
                species=species,
                start_value=parameter.get("start_value"),
                end_value=parameter.get("end_value"),
                standard_deviation=parameter.get("standard_deviation"),
                units=units,
                normalized_start_value=parameter.get("n_start_value"),
                normalized_units=_normalized_unit_name(parameter.get("unit", parameter.get("units"))),
                proposed_symbol=_proposed_parameter_symbol(
                    parameter_type=parameter_type,
                    species=species,
                    name=_text(parameter.get("name")),
                    primary_substrate=primary_substrate,
                ),
                source_field="kineticlaw.parameter[]",
            )
        )
    return tuple(output)


def _proposed_parameter_symbol(
    *,
    parameter_type: str,
    species: str,
    name: str,
    primary_substrate: str,
) -> str:
    type_token = _token(parameter_type or name or "parameter")
    species_token = _token(species)
    substrate_token = _token(primary_substrate)
    if type_token == "km" and species_token:
        return f"Km_{species_token}"
    if type_token == "kcat" and substrate_token:
        return f"kcat_{substrate_token}"
    if type_token == "concentration" and "enzyme" in species.lower():
        return "enzyme_concentration"
    if type_token == "concentration" and species_token:
        return f"initial_{species_token}_concentration"
    return type_token or "parameter"


def _find_cached_export(cache_dir: Path, query: str) -> Path:
    filename = _raw_export_filename(query)
    reaction_id = _reaction_id_from_query(query)
    reaction_folder = () if reaction_id is None else (cache_dir / f"reaction_{reaction_id}" / "raw" / filename,)
    candidates = (
        cache_dir / "raw" / filename,
        cache_dir / filename,
        cache_dir / _query_slug(query) / "raw" / filename,
        *reaction_folder,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SabioRKSourceError(
        "No frozen SABIO-RK kinetic-law export was found. Looked for: "
        + ", ".join(str(path) for path in candidates)
        + ". Use refresh=True only with an explicit live_fetcher."
    )


def _metadata_path_for_export(export_path: Path) -> Path | None:
    candidate = export_path.parent / "fetch_metadata.json"
    return candidate if candidate.exists() else None


def _load_metadata(path: Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SabioRKSourceError(f"SABIO-RK fetch metadata is not valid JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise SabioRKSourceError(f"SABIO-RK fetch metadata must be a JSON object: {path}")
    return deepcopy(dict(payload))


def _raw_export_filename(query: str) -> str:
    reaction_id = _reaction_id_from_query(query)
    if reaction_id is not None:
        return f"kinlaw_entries_reaction_{reaction_id}.json"
    return f"kinlaw_entries_{_query_slug(query)}.json"


def _reaction_id_from_query(query: str) -> str | None:
    match = re.search(r"SabioReactionID\s*:\s*([A-Za-z0-9_.-]+)", query)
    return match.group(1) if match else None


def _query_slug(query: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", query.strip()).strip("_").lower()
    return slug or "query"


def _reaction_id(entry: Mapping[str, Any], reaction: Mapping[str, Any]) -> str:
    for value in (entry.get("SabioReactionID"), entry.get("ReactionID"), reaction.get("id")):
        if value not in {None, ""}:
            return str(value)
    return ""


def _entry_id(entry: Mapping[str, Any], index: int) -> str:
    for key in ("EntryID", "entry_id", "id"):
        if key in entry and entry[key] is not None:
            return str(entry[key])
    return f"entry_index_{index}"


def _kinetic_law_type(kinetic_law: Mapping[str, Any], entry: Mapping[str, Any]) -> str:
    kinlaw_type = kinetic_law.get("kinlaw_type")
    if isinstance(kinlaw_type, Mapping):
        return _text(kinlaw_type.get("name"))
    if kinlaw_type not in {None, ""}:
        return str(kinlaw_type)
    return _first_text(entry.get("KineticLawType"), "")


def _organism(entry: Mapping[str, Any]) -> str:
    organism = _mapping(_mapping(entry.get("general")).get("organism"))
    return _first_text(organism.get("name"), entry.get("Organism"))


def _condition_value(conditions: Mapping[str, Any], key: str) -> Any:
    value = conditions.get(key)
    if isinstance(value, Mapping):
        return value.get("start_value")
    return None


def _condition_units(conditions: Mapping[str, Any], key: str) -> str:
    value = conditions.get(key)
    if isinstance(value, Mapping):
        return _text(value.get("unit"))
    return ""


def _parameter_type_name(parameter: Mapping[str, Any]) -> str:
    for key in ("parameter_type", "type", "ParameterType", "name"):
        value = parameter.get(key)
        if isinstance(value, Mapping):
            name = value.get("name")
            if name not in {None, ""}:
                return str(name)
        elif value not in {None, ""}:
            return str(value)
    return ""


def _species_label(species: Any) -> str:
    if isinstance(species, Mapping):
        for key in ("species_key", "name", "Species"):
            value = species.get(key)
            if value not in {None, ""}:
                return str(value)
        return _first_text(*species.values())
    return _text(species)


def _unit_name(unit: Any) -> str:
    if isinstance(unit, Mapping):
        return _text(unit.get("name"))
    return _text(unit)


def _normalized_unit_name(unit: Any) -> str:
    if isinstance(unit, Mapping):
        return _text(unit.get("n_name"))
    return ""


def _external_compound_identifiers(entry: Mapping[str, Any]) -> dict[str, dict[str, tuple[str, ...]]]:
    external_links = _mapping(entry.get("external_links"))
    compound_links = external_links.get("compound")
    if not isinstance(compound_links, list):
        return {}
    values: dict[str, dict[str, list[str]]] = {}
    for link in compound_links:
        if not isinstance(link, Mapping):
            continue
        compound_id = _text(link.get("id"))
        key = _text(link.get("key"))
        value = _text(link.get("value"))
        if not compound_id or not key or not value:
            continue
        values.setdefault(compound_id, {}).setdefault(key, [])
        if value not in values[compound_id][key]:
            values[compound_id][key].append(value)
    return {
        compound_id: {key: tuple(items) for key, items in key_values.items()}
        for compound_id, key_values in values.items()
    }


def _primary_substrate_name(participants: Sequence[SabioRKParticipant]) -> str:
    for participant in participants:
        if participant.role == "substrate" and participant.compound_name.lower() not in {"h2o", "water"}:
            return participant.compound_name
    for participant in participants:
        if participant.role == "substrate":
            return participant.compound_name
    return ""


def _normalized_role(value: Any) -> str:
    role = _text(value).strip().lower()
    if role == "catalyst":
        return "catalyst"
    if role == "product":
        return "product"
    if role == "substrate":
        return "substrate"
    return role or "unknown"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, Mapping):
            nested = _first_text(*value.values())
            if nested:
                return nested
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            nested = _first_text(*value)
            if nested:
                return nested
        elif value not in {None, ""}:
            return str(value)
    return ""


def _token(value: str) -> str:
    text = value
    if "|" in text:
        parts = [part.strip() for part in text.split("|") if part.strip()]
        if len(parts) >= 2:
            text = parts[1]
    text = re.sub(r"[^A-Za-z0-9]+", "_", text.strip()).strip("_").lower()
    if text in {"beta_d_glucose", "cellobiose"}:
        return text
    return text


_COMPOUND_ROLE_FIELDS = (
    "entry_id",
    "reaction_id",
    "role",
    "compound_name",
    "stoichiometry",
    "compound_id",
    "location",
    "comment",
    "external_identifiers",
)

_KINETIC_LAW_FIELDS = (
    "entry_id",
    "reaction_id",
    "equation",
    "kinetic_law_type",
    "formula",
    "reversible",
    "organism",
    "enzyme_name",
    "ec_number",
    "ph",
    "temperature",
    "temperature_units",
    "buffer",
    "warnings",
)

_PARAMETER_FIELDS = (
    "entry_id",
    "reaction_id",
    "name",
    "parameter_type",
    "role",
    "species",
    "start_value",
    "end_value",
    "standard_deviation",
    "units",
    "normalized_start_value",
    "normalized_units",
    "proposed_symbol",
    "source_field",
)

_PUBLICATION_FIELDS = (
    "entry_id",
    "reaction_id",
    "publication_id",
    "pubmed_id",
    "title",
    "journal",
    "year",
    "author",
)


def _compound_role_rows(records: Sequence[SabioRKReactionRecord]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        for participant in record.participants:
            row = participant.to_dict()
            row["external_identifiers"] = json.dumps(row["external_identifiers"], sort_keys=True)
            rows.append(row)
    return rows


def _kinetic_law_rows(records: Sequence[SabioRKReactionRecord]) -> list[dict[str, Any]]:
    return [
        {
            "entry_id": record.entry_id,
            "reaction_id": record.reaction_id,
            "equation": record.equation,
            "kinetic_law_type": record.kinetic_law_type,
            "formula": record.formula,
            "reversible": record.reversible,
            "organism": record.organism,
            "enzyme_name": record.enzyme_name,
            "ec_number": record.ec_number,
            "ph": record.ph,
            "temperature": record.temperature,
            "temperature_units": record.temperature_units,
            "buffer": record.buffer,
            "warnings": "; ".join(record.warnings),
        }
        for record in records
    ]


def _parameter_rows(records: Sequence[SabioRKReactionRecord]) -> list[dict[str, Any]]:
    return [
        parameter.to_dict()
        for record in records
        for parameter in record.parameters
    ]


def _publication_rows(records: Sequence[SabioRKReactionRecord]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        publication = record.publication
        rows.append(
            {
                "entry_id": record.entry_id,
                "reaction_id": record.reaction_id,
                "publication_id": publication.get("publication_id", ""),
                "pubmed_id": publication.get("pubmed_id", ""),
                "title": publication.get("title", ""),
                "journal": publication.get("journal", ""),
                "year": publication.get("year", ""),
                "author": "; ".join(str(author) for author in _author_values(publication.get("author"))),
            }
        )
    return rows


def _author_values(value: Any) -> tuple[Any, ...]:
    if isinstance(value, list):
        return tuple(value)
    if value in {None, ""}:
        return ()
    return (value,)


def _proposed_product_maps(proposal: SabioRKRecordProposal) -> dict[str, Any]:
    return {
        "kind": "fungmod_source_proposals",
        "proposal_type": "product_maps",
        "proposal_status": "proposed_review_required",
        "source_query": proposal.source_query,
        "records": [
            {
                "proposal_id": f"proposed_sabiork_{record.reaction_id}_{record.entry_id}_product_map",
                "source_database": "SABIO-RK",
                "source_entry_id": record.entry_id,
                "source_reaction_id": record.reaction_id,
                "product_map_type": "stoichiometric_roles_proposed",
                "substrates": [participant.to_dict() for participant in record.substrates],
                "products": [participant.to_dict() for participant in record.products],
                "participants": [participant.to_dict() for participant in record.participants],
                "review_required": True,
                "notes": "Proposed from SABIO-RK reaction roles; not accepted into the simulation registry.",
            }
            for record in proposal.reaction_records
        ],
    }


def _proposed_parameter_records(proposal: SabioRKRecordProposal) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for record in proposal.reaction_records:
        for parameter in record.parameters:
            records.append(_proposed_parameter_record(record, parameter))
    return {
        "kind": "fungmod_source_proposals",
        "proposal_type": "parameter_records",
        "proposal_status": "proposed_review_required",
        "source_query": proposal.source_query,
        "records": records,
    }


def _proposed_parameter_record(
    record: SabioRKReactionRecord,
    parameter: SabioRKKineticParameter,
) -> dict[str, Any]:
    numeric_value = _as_float(parameter.start_value)
    units = parameter.units
    exact_value_allowed = numeric_value is not None and units not in {"", "-"}
    return {
        "record_id": f"proposed_sabiork_{record.entry_id}_{parameter.proposed_symbol}",
        "proposal_status": "proposed_review_required",
        "name": f"Proposed SABIO-RK {parameter.proposed_symbol} from EntryID {record.entry_id}",
        "maturity": "source_extracted_proposal",
        "provenance": {
            "source_database": "SABIO-RK",
            "source_entry_id": record.entry_id,
            "source_reaction_id": record.reaction_id,
            "source_field": parameter.source_field,
            "publication": deepcopy(dict(record.publication)),
            "notes": "Review required before promotion to the simulation registry.",
        },
        "parameter_symbol": parameter.proposed_symbol,
        "process_type": _proposed_process_type(record),
        "value": {
            "kind": "exact" if exact_value_allowed else "unknown",
            "value": numeric_value if exact_value_allowed else None,
            "units": units if units else None,
            "source": "SABIO-RK kinetic-law entry",
            "confidence_level": "source_extracted_unreviewed",
            "notes": "Original source value preserved; not curated for simulation use.",
        },
        "source_value": parameter.start_value,
        "source_units": parameter.units,
        "normalized_start_value": parameter.normalized_start_value,
        "normalized_units": parameter.normalized_units,
        "allowed_use": "review_only_not_simulation_registry",
        "notes": "SOURCE-001 proposal only; do not use directly in VirtualExperiment simulation.",
    }


def _proposed_process_compatibility(proposal: SabioRKRecordProposal) -> dict[str, Any]:
    return {
        "kind": "fungmod_source_proposals",
        "proposal_type": "process_compatibility",
        "proposal_status": "proposed_review_required",
        "source_query": proposal.source_query,
        "records": [
            {
                "record_id": f"proposed_sabiork_{record.reaction_id}_{record.entry_id}_process_compatibility",
                "name": f"Proposed SABIO-RK EntryID {record.entry_id} process compatibility",
                "maturity": "source_extracted_proposal",
                "source_database": "SABIO-RK",
                "source_entry_id": record.entry_id,
                "source_reaction_id": record.reaction_id,
                "enzyme_name": record.enzyme_name,
                "ec_number": record.ec_number,
                "substrates": [participant.compound_name for participant in record.substrates],
                "products": [participant.compound_name for participant in record.products],
                "process_type": _proposed_process_type(record),
                "required_parameters": [parameter.proposed_symbol for parameter in record.parameters],
                "product_map_required": bool(record.products),
                "review_required": True,
                "notes": "Proposed compatibility only; state roles and product map must be reviewed before registry promotion.",
            }
            for record in proposal.reaction_records
        ],
    }


def _proposed_process_type(record: SabioRKReactionRecord) -> str:
    if "michaelis" in record.kinetic_law_type.lower():
        return "homogeneous_michaelis_menten"
    return "source_extracted_kinetic_law"


def _proposal_report_markdown(proposal: SabioRKRecordProposal) -> str:
    lines = [
        "# SOURCE-001 SABIO-RK Source Adapter Report",
        "",
        f"- Source query: `{proposal.source_query or 'not_specified'}`",
        f"- Source snapshot: `{proposal.source_snapshot_path or 'not_specified'}`",
        f"- Parsed kinetic-law entries: {len(proposal.reaction_records)}",
        "",
        "## Review Status",
        "",
        "All records in this bundle are proposed source records. They are not simulation registry records.",
        "",
        "## Entries",
        "",
        "| EntryID | Reaction ID | Enzyme | EC number | Kinetic law | Substrates | Products | Parameters | Warnings |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in proposal.reaction_records:
        lines.append(
            "| "
            + " | ".join(
                (
                    _md(record.entry_id),
                    _md(record.reaction_id),
                    _md(record.enzyme_name),
                    _md(record.ec_number),
                    _md(record.kinetic_law_type),
                    _md("; ".join(participant.compound_name for participant in record.substrates)),
                    _md("; ".join(participant.compound_name for participant in record.products)),
                    _md("; ".join(parameter.proposed_symbol for parameter in record.parameters)),
                    _md("; ".join(record.warnings)),
                )
            )
            + " |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in proposal.limitations)
    lines.append("")
    return "\n".join(lines)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value).lower()
    return "" if value is None else value


def _md(value: str) -> str:
    return value.replace("|", "\\|")


__all__ = [
    "SabioRKParticipant",
    "SabioRKReactionRecord",
    "SabioRKRecordProposal",
    "SabioRKKineticParameter",
    "SabioRKProposalWriteResult",
    "SabioRKSource",
    "SabioRKSourceError",
    "SabioRKSourceSnapshot",
]
