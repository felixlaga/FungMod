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
from fungal_model.sources.sabiork.fetch import COMBINED_EXPORT_FILENAME, query_bundle_key


class SabioRKSourceError(ValueError):
    """Raised when SABIO-RK source discovery cannot proceed safely."""


LiveKinlawFetcher = Callable[[str, Path], tuple[Path, Path]]
PROPOSAL_STATUS = "proposed_review_required"
REVIEW_ONLY_ALLOWED_USE = "review_only_not_simulation_registry"


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
class RegistryProposalWriteResult:
    """Paths written by a SOURCE-002 registry proposal bundle."""

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


@dataclass(frozen=True)
class SourceDiscoveryResult:
    """Notebook-friendly SABIO-RK discovery result from frozen source snapshots."""

    source_query: str
    source_snapshot_path: str
    reaction_records: tuple[SabioRKReactionRecord, ...]
    filters: Mapping[str, str]
    missing_fields: tuple[Mapping[str, Any], ...]
    limitations: tuple[str, ...]

    def show_reactions(self) -> list[dict[str, Any]]:
        """Return compact reaction rows for notebook display."""

        return [
            {
                "entry_id": record.entry_id,
                "reaction_id": record.reaction_id,
                "equation": record.equation,
                "organism": record.organism,
                "enzyme_name": record.enzyme_name,
                "ec_number": record.ec_number,
                "kinetic_law_type": record.kinetic_law_type,
                "warnings": "; ".join(record.warnings),
            }
            for record in self.reaction_records
        ]

    def show_products(self) -> list[dict[str, Any]]:
        """Return substrate/product stoichiometry rows for notebook display."""

        return [
            {
                "entry_id": participant.entry_id,
                "reaction_id": participant.reaction_id,
                "role": participant.role,
                "compound_name": participant.compound_name,
                "stoichiometry": participant.stoichiometry,
                "compound_id": participant.compound_id,
                "external_identifiers": {
                    key: list(values)
                    for key, values in participant.external_identifiers.items()
                },
            }
            for record in self.reaction_records
            for participant in record.participants
            if participant.role in {"substrate", "product"}
        ]

    def show_kinetic_parameters(self) -> list[dict[str, Any]]:
        """Return source kinetic-parameter rows without unit conversion."""

        return [
            parameter.to_dict()
            for record in self.reaction_records
            for parameter in record.parameters
        ]

    def show_missing_fields(self) -> list[dict[str, Any]]:
        """Return missing or review-sensitive fields surfaced during discovery."""

        return [dict(item) for item in self.missing_fields]

    @property
    def substrates(self) -> tuple[str, ...]:
        return _unique_text(
            participant.compound_name
            for record in self.reaction_records
            for participant in record.substrates
        )

    @property
    def products(self) -> tuple[str, ...]:
        return _unique_text(
            participant.compound_name
            for record in self.reaction_records
            for participant in record.products
        )

    @property
    def enzyme_names(self) -> tuple[str, ...]:
        return _unique_text(record.enzyme_name for record in self.reaction_records)

    @property
    def ec_numbers(self) -> tuple[str, ...]:
        return _unique_text(record.ec_number for record in self.reaction_records)

    @property
    def organism_names(self) -> tuple[str, ...]:
        return _unique_text(record.organism for record in self.reaction_records)

    @property
    def warnings(self) -> tuple[str, ...]:
        return _unique_text(
            warning
            for record in self.reaction_records
            for warning in record.warnings
        )

    def to_registry_proposal(
        self,
        *,
        process_type: str = "homogeneous_michaelis_menten",
        product_map: str = "auto_from_stoichiometry",
    ) -> "RegistryProposal":
        """Create review-only proposed FungMod registry records from this discovery."""

        if not self.reaction_records:
            raise SabioRKSourceError("Cannot create a registry proposal from an empty discovery result.")
        return RegistryProposal(
            source_query=self.source_query,
            source_snapshot_path=self.source_snapshot_path,
            reaction_records=self.reaction_records,
            filters=dict(self.filters),
            process_type=process_type,
            product_map=product_map,
            limitations=(
                *self.limitations,
                "SOURCE-002 proposals are review-only and are not production registry records.",
                "Promotion to data_registry/ requires a separate explicit curation step.",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_sabiork_source_discovery",
            "source_query": self.source_query,
            "source_snapshot_path": self.source_snapshot_path,
            "filters": dict(self.filters),
            "reaction_records": [record.to_dict() for record in self.reaction_records],
            "substrates": list(self.substrates),
            "products": list(self.products),
            "enzyme_names": list(self.enzyme_names),
            "ec_numbers": list(self.ec_numbers),
            "organism_names": list(self.organism_names),
            "kinetic_parameters": self.show_kinetic_parameters(),
            "missing_fields": self.show_missing_fields(),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class RegistryProposal:
    """Review-only FungMod registry proposal generated from SABIO-RK discovery."""

    source_query: str
    source_snapshot_path: str
    reaction_records: tuple[SabioRKReactionRecord, ...]
    filters: Mapping[str, str]
    process_type: str
    product_map: str
    limitations: tuple[str, ...]
    proposal_status: str = PROPOSAL_STATUS

    def proposed_records(self) -> dict[str, list[dict[str, Any]]]:
        """Return proposed registry record groups without writing files."""

        return {
            "fungi": _proposed_source_records(self),
            "substrates": _source_002_proposed_substrates(self),
            "enzyme_classes": _source_002_proposed_enzyme_classes(self),
            "product_maps": _source_002_proposed_product_maps(self),
            "parameter_records": _source_002_proposed_parameter_records(self),
            "process_compatibility": _source_002_proposed_process_compatibility(self),
            "case_templates": _source_002_proposed_case_templates(self),
        }

    def preview(self) -> dict[str, Any]:
        """Return a compact proposal preview for notebooks."""

        records = self.proposed_records()
        return {
            "proposal_status": self.proposal_status,
            "source_query": self.source_query,
            "source_snapshot_path": self.source_snapshot_path,
            "process_type": self.process_type,
            "product_map": self.product_map,
            "record_counts": {key: len(values) for key, values in records.items()},
            "limitations": list(self.limitations),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_sabiork_registry_proposal",
            "proposal_status": self.proposal_status,
            "source_query": self.source_query,
            "source_snapshot_path": self.source_snapshot_path,
            "filters": dict(self.filters),
            "process_type": self.process_type,
            "product_map": self.product_map,
            "reaction_records": [record.to_dict() for record in self.reaction_records],
            "proposed_records": self.proposed_records(),
            "limitations": list(self.limitations),
        }

    def write(self, output_dir: str | Path) -> RegistryProposalWriteResult:
        """Write review-only proposal files outside the production registry."""

        root = Path(output_dir)
        _ensure_not_data_registry(root)
        root.mkdir(parents=True, exist_ok=True)
        records = self.proposed_records()
        paths = {
            "proposal_manifest": root / "proposal_manifest.json",
            "source_discovery_result": root / "source_discovery_result.json",
            "proposed_fungi": root / "proposed_fungi.yml",
            "proposed_substrates": root / "proposed_substrates.yml",
            "proposed_enzyme_classes": root / "proposed_enzyme_classes.yml",
            "proposed_product_maps": root / "proposed_product_maps.yml",
            "proposed_parameter_records": root / "proposed_parameter_records.yml",
            "proposed_process_compatibility": root / "proposed_process_compatibility.yml",
            "proposed_case_templates": root / "proposed_case_templates.yml",
            "source_adapter_report": root / "source_adapter_report.md",
        }
        _write_json(paths["proposal_manifest"], self.to_dict())
        _write_json(
            paths["source_discovery_result"],
            {
                "kind": "fungmod_sabiork_source_discovery",
                "source_query": self.source_query,
                "source_snapshot_path": self.source_snapshot_path,
                "filters": dict(self.filters),
                "reaction_records": [record.to_dict() for record in self.reaction_records],
            },
        )
        _write_proposal_yaml(paths["proposed_fungi"], "fungi", self, records["fungi"])
        _write_proposal_yaml(paths["proposed_substrates"], "substrates", self, records["substrates"])
        _write_proposal_yaml(paths["proposed_enzyme_classes"], "enzyme_classes", self, records["enzyme_classes"])
        _write_proposal_yaml(paths["proposed_product_maps"], "product_maps", self, records["product_maps"])
        _write_proposal_yaml(paths["proposed_parameter_records"], "parameter_records", self, records["parameter_records"])
        _write_proposal_yaml(
            paths["proposed_process_compatibility"],
            "process_compatibility",
            self,
            records["process_compatibility"],
        )
        _write_proposal_yaml(paths["proposed_case_templates"], "case_templates", self, records["case_templates"])
        paths["source_adapter_report"].write_text(_source_002_report_markdown(self), encoding="utf-8")
        return RegistryProposalWriteResult(output_directory=root, paths=paths)


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

    def discover_for_virtual_experiment(
        self,
        *,
        fungus: str | None = None,
        source: str | None = None,
        substrate: str | None = None,
        enzyme: str | None = None,
        ec_number: str | None = None,
        reaction: str | None = None,
        reaction_id: str | int | None = None,
        entry_id: str | int | None = None,
        query: str | None = None,
        refresh: bool = False,
        output_dir: str | Path | None = None,
    ) -> SourceDiscoveryResult:
        """Discover local SABIO-RK entries and prepare them for review-only proposals."""

        filters = _discovery_filters(
            fungus=fungus,
            source=source,
            substrate=substrate,
            enzyme=enzyme,
            ec_number=ec_number,
            reaction=reaction,
            reaction_id=reaction_id,
            entry_id=entry_id,
        )
        source_query = query or _source_query_from_filters(filters)
        if refresh and not source_query:
            source_query = _freeform_source_query_from_filters(filters)
        snapshots = (
            (self.fetch_kinlaw_entries(source_query, refresh=refresh, output_dir=output_dir),)
            if source_query
            else self._local_snapshots_for_discovery(output_dir=output_dir)
        )
        records = tuple(
            record
            for snapshot in snapshots
            for record in self.parse_reaction_records(snapshot)
            if _record_matches_discovery_filters(record, filters)
        )
        if not records:
            raise SabioRKSourceError(
                "No SABIO-RK entries matched discovery filters. "
                f"Filters: {_format_filters(filters)}. "
                "Use a frozen local snapshot, or refresh=True only with configured live refresh."
            )
        snapshot_paths = _unique_text(str(snapshot.export_path) for snapshot in snapshots)
        return SourceDiscoveryResult(
            source_query=source_query or _format_filters(filters),
            source_snapshot_path="; ".join(snapshot_paths),
            reaction_records=records,
            filters=filters,
            missing_fields=_missing_fields(records),
            limitations=(
                "Discovery uses frozen SABIO-RK kinetic-law snapshots unless refresh=True explicitly uses configured live refresh.",
                "Discovery output is not a simulation registry and is not trusted by VirtualExperiment automatically.",
                "SABIO-RK entries may omit enzyme concentration, units, environmental context, or product curation details.",
            ),
        )

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

    def _local_snapshots_for_discovery(
        self,
        *,
        output_dir: str | Path | None = None,
    ) -> tuple[SabioRKSourceSnapshot, ...]:
        target_dir = Path(output_dir) if output_dir is not None else self.cache_dir
        export_paths = _find_all_cached_exports(target_dir)
        if not export_paths:
            raise SabioRKSourceError(
                "No frozen SABIO-RK kinetic-law exports were found for discovery. "
                f"Searched under {target_dir} and local read-only fallback snapshot roots. "
                "Use refresh=True only with configured live refresh."
            )
        return tuple(
            self.load_kinlaw_entries(path, query=_query_from_export_filename(path))
            for path in export_paths
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


def stable_sabiork_token(value: Any) -> str:
    """Return a stable lowercase token for review-only SABIO-RK proposal IDs."""

    text = _first_text(value).strip().lower()
    text = text.replace("β", "beta").replace("°", "")
    token = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return token or "unknown"


def stable_registry_proposal_id(*parts: Any, prefix: str = "proposed_sabiork") -> str:
    """Return a deterministic proposal ID from stable source terms."""

    tokens = [stable_sabiork_token(part) for part in parts if _first_text(part).strip()]
    return "_".join((prefix, *tokens)) if tokens else prefix


def _discovery_filters(
    *,
    fungus: str | None,
    source: str | None,
    substrate: str | None,
    enzyme: str | None,
    ec_number: str | None,
    reaction: str | None,
    reaction_id: str | int | None,
    entry_id: str | int | None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    source_name = source or fungus
    if source_name:
        filters["fungus/source"] = str(source_name)
    for key, value in (
        ("substrate", substrate),
        ("enzyme", enzyme),
        ("ec_number", ec_number),
        ("reaction", reaction),
    ):
        if value not in {None, ""}:
            filters[key] = str(value)
    for key, value in (("reaction_id", reaction_id), ("entry_id", entry_id)):
        if value is None or value == "":
            continue
        filters[key] = _validated_sabio_identifier(value, field=key)
    return filters


def _source_query_from_filters(filters: Mapping[str, str]) -> str:
    reaction_id = filters.get("reaction_id")
    if reaction_id:
        return f"SabioReactionID:{reaction_id}"
    reaction = filters.get("reaction", "")
    if reaction and stable_sabiork_token(reaction).isdigit():
        return f"SabioReactionID:{reaction}"
    return ""


def _freeform_source_query_from_filters(filters: Mapping[str, str]) -> str:
    parts: list[str] = []
    if filters.get("ec_number"):
        parts.append(f"ECNumber:{_quoted_sabio_text(filters['ec_number'])}")
    if filters.get("enzyme"):
        parts.append(f"Enzymename:{_quoted_sabio_text(filters['enzyme'])}")
    if filters.get("substrate"):
        parts.append(f"Substrate:{_quoted_sabio_text(filters['substrate'])}")
    if filters.get("fungus/source"):
        parts.append(f"Organism:{_quoted_sabio_text(filters['fungus/source'])}")
    if filters.get("reaction"):
        parts.append(f"Reaction:{_quoted_sabio_text(filters['reaction'])}")
    if filters.get("entry_id"):
        parts.append(f"EntryID:{filters['entry_id']}")
    return " AND ".join(parts)


def _quoted_sabio_text(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _validated_sabio_identifier(value: str | int, *, field: str) -> str:
    if isinstance(value, bool):
        raise SabioRKSourceError(f"{field} must be a positive decimal SABIO-RK identifier.")
    text = str(value)
    if re.fullmatch(r"[1-9][0-9]*", text) is None:
        raise SabioRKSourceError(
            f"{field} must be a positive decimal SABIO-RK identifier without signs or whitespace."
        )
    return text


def _record_matches_discovery_filters(
    record: SabioRKReactionRecord,
    filters: Mapping[str, str],
) -> bool:
    source_name = filters.get("fungus/source")
    if source_name and not _text_matches(record.organism, source_name):
        return False
    substrate = filters.get("substrate")
    if substrate and not any(_text_matches(participant.compound_name, substrate) for participant in record.substrates):
        return False
    enzyme = filters.get("enzyme")
    if enzyme and not _text_matches(record.enzyme_name, enzyme):
        return False
    ec_number = filters.get("ec_number")
    if ec_number and stable_sabiork_token(record.ec_number) != stable_sabiork_token(ec_number):
        return False
    reaction = filters.get("reaction")
    if reaction and not (
        _text_matches(record.equation, reaction)
        or stable_sabiork_token(record.reaction_id) == stable_sabiork_token(reaction)
    ):
        return False
    reaction_id = filters.get("reaction_id")
    if reaction_id and stable_sabiork_token(record.reaction_id) != stable_sabiork_token(reaction_id):
        return False
    entry_id = filters.get("entry_id")
    if entry_id and stable_sabiork_token(record.entry_id) != stable_sabiork_token(entry_id):
        return False
    return True


def _text_matches(candidate: str, query: str) -> bool:
    candidate_token = stable_sabiork_token(candidate)
    query_token = stable_sabiork_token(query)
    return candidate_token == query_token or query_token in candidate_token


def _format_filters(filters: Mapping[str, str]) -> str:
    if not filters:
        return "none"
    return ", ".join(f"{key}={value!r}" for key, value in filters.items())


def _missing_fields(records: Sequence[SabioRKReactionRecord]) -> tuple[Mapping[str, Any], ...]:
    missing: list[Mapping[str, Any]] = []
    for record in records:
        for field_name, value in (
            ("organism", record.organism),
            ("enzyme_name", record.enzyme_name),
            ("ec_number", record.ec_number),
            ("equation", record.equation),
            ("kinetic_law_type", record.kinetic_law_type),
            ("formula", record.formula),
            ("ph", record.ph),
            ("temperature", record.temperature),
            ("publication", record.publication),
        ):
            if _is_missing_source_value(value):
                missing.append(
                    {
                        "entry_id": record.entry_id,
                        "reaction_id": record.reaction_id,
                        "field": field_name,
                        "message": "SABIO-RK snapshot did not provide this field.",
                    }
                )
        if not record.substrates:
            missing.append(
                {
                    "entry_id": record.entry_id,
                    "reaction_id": record.reaction_id,
                    "field": "substrates",
                    "message": "No substrate participants were extracted.",
                }
            )
        if not record.products:
            missing.append(
                {
                    "entry_id": record.entry_id,
                    "reaction_id": record.reaction_id,
                    "field": "products",
                    "message": "No product participants were extracted.",
                }
            )
        if not record.parameters:
            missing.append(
                {
                    "entry_id": record.entry_id,
                    "reaction_id": record.reaction_id,
                    "field": "kinetic_parameters",
                    "message": "No kinetic-law parameters were extracted.",
                }
            )
        for parameter in record.parameters:
            if parameter.start_value in {None, ""}:
                missing.append(
                    {
                        "entry_id": record.entry_id,
                        "reaction_id": record.reaction_id,
                        "field": f"parameter.{parameter.proposed_symbol}.start_value",
                        "message": "Parameter start value is missing and must be reviewed before registry promotion.",
                    }
                )
            if parameter.units in {"", "-"}:
                missing.append(
                    {
                        "entry_id": record.entry_id,
                        "reaction_id": record.reaction_id,
                        "field": f"parameter.{parameter.proposed_symbol}.units",
                        "message": "Parameter units are missing or not applicable and must be reviewed.",
                    }
                )
    return tuple(missing)


def _is_missing_source_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    if isinstance(value, Mapping):
        return not value
    if isinstance(value, Sequence):
        return not value
    return False


def _unique_text(values: Sequence[str] | Any) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        token = stable_sabiork_token(text)
        if not text or token in seen:
            continue
        output.append(text)
        seen.add(token)
    return tuple(output)


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
    query_key = query_bundle_key(query)
    reaction_id = _reaction_id_from_query(query)
    reaction_folder = () if reaction_id is None else (cache_dir / f"reaction_{reaction_id}" / "raw" / filename,)
    direct_candidates = (
        cache_dir / "raw" / filename,
        cache_dir / filename,
        cache_dir / _query_slug(query) / "raw" / filename,
        *reaction_folder,
    )
    fallback_candidates = tuple(
        candidate
        for root in _local_snapshot_roots(cache_dir)
        for candidate in (
            root / "raw" / filename,
            root / filename,
            root / _query_slug(query) / "raw" / filename,
            *((root / f"reaction_{reaction_id}" / "raw" / filename,) if reaction_id is not None else ()),
            *tuple(sorted(root.glob(f"**/raw/{filename}"))),
            *tuple(sorted(root.glob(f"**/{filename}"))),
        )
    )
    bundle_candidates = tuple(
        candidate
        for root in _local_snapshot_roots(cache_dir)
        for candidate in sorted(
            root.glob(f"**/{query_key}/*/derived/{COMBINED_EXPORT_FILENAME}"),
            reverse=True,
        )
    )
    candidates = _unique_paths((*bundle_candidates, *direct_candidates, *fallback_candidates))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SabioRKSourceError(
        "No frozen SABIO-RK kinetic-law export was found. Looked for: "
        + ", ".join(str(path) for path in candidates)
        + ". Use refresh=True only with configured live refresh."
    )


def _find_all_cached_exports(cache_dir: Path) -> tuple[Path, ...]:
    candidates = tuple(
        candidate
        for root in _local_snapshot_roots(cache_dir)
        for candidate in (
            *tuple(sorted(root.glob("raw/kinlaw_entries*.json"))),
            *tuple(sorted(root.glob("kinlaw_entries*.json"))),
            *tuple(sorted(root.glob("**/raw/kinlaw_entries*.json"))),
            *tuple(sorted(root.glob("**/kinlaw_entries*.json"))),
            *tuple(sorted(root.glob(f"**/derived/{COMBINED_EXPORT_FILENAME}"))),
        )
    )
    return tuple(path for path in _unique_paths(candidates) if path.exists())


def _local_snapshot_roots(cache_dir: Path) -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[4]
    return _unique_paths(
        (
            cache_dir,
            repo_root / "data" / "source_snapshots" / "sabiork",
            repo_root / "data" / "kinetic_records" / "sabiork",
        )
    )


def _unique_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    output: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        output.append(path)
        seen.add(key)
    return tuple(output)


def _query_from_export_filename(path: Path) -> str:
    metadata_path = _metadata_path_for_export(path)
    if metadata_path is not None:
        metadata = _load_metadata(metadata_path)
        metadata_query = metadata.get("query")
        if isinstance(metadata_query, str) and metadata_query:
            return metadata_query
    match = re.search(r"kinlaw_entries_reaction_([A-Za-z0-9_.-]+)\.json$", path.name)
    if match:
        return f"SabioReactionID:{match.group(1)}"
    return path.stem.removeprefix("kinlaw_entries_")


def _metadata_path_for_export(export_path: Path) -> Path | None:
    candidates = (
        export_path.parent / "fetch_metadata.json",
        export_path.parent.parent / "fetch_metadata.json",
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


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


def _proposed_source_records(proposal: RegistryProposal) -> list[dict[str, Any]]:
    records_by_source: dict[str, list[SabioRKReactionRecord]] = {}
    for record in proposal.reaction_records:
        if record.organism:
            records_by_source.setdefault(stable_sabiork_token(record.organism), []).append(record)
    output: list[dict[str, Any]] = []
    for records in records_by_source.values():
        organism = records[0].organism
        output.append(
            {
                "record_id": stable_registry_proposal_id("source", organism),
                "proposal_status": proposal.proposal_status,
                "name": f"Proposed SABIO-RK source {organism}",
                "display_name": organism,
                "scientific_name": organism,
                "aliases": _unique_text((organism, f"{organism} source")),
                "maturity": "source_extracted_proposal",
                "provenance": _source_002_provenance(records, proposal=proposal),
                "enzyme_classes": _unique_text(_source_002_enzyme_id(record) for record in records),
                "assimilable_products": [],
                "review_required": True,
                "allowed_use": REVIEW_ONLY_ALLOWED_USE,
                "notes": "SOURCE-002 proposed source record; review required before production registry use.",
            }
        )
    return output


def _source_002_proposed_substrates(proposal: RegistryProposal) -> list[dict[str, Any]]:
    records_by_compound: dict[str, list[tuple[SabioRKReactionRecord, SabioRKParticipant]]] = {}
    for record in proposal.reaction_records:
        for participant in record.substrates:
            if participant.compound_name:
                records_by_compound.setdefault(stable_sabiork_token(participant.compound_name), []).append((record, participant))
    output: list[dict[str, Any]] = []
    for pairs in records_by_compound.values():
        participant = pairs[0][1]
        source_records = [record for record, _participant in pairs]
        output.append(
            {
                "record_id": _source_002_substrate_id(participant.compound_name),
                "proposal_status": proposal.proposal_status,
                "name": f"Proposed SABIO-RK substrate {participant.compound_name}",
                "display_name": participant.compound_name,
                "aliases": _unique_text((participant.compound_name, stable_sabiork_token(participant.compound_name))),
                "maturity": "source_extracted_proposal",
                "provenance": _source_002_provenance(source_records, proposal=proposal),
                "substrate_class": stable_sabiork_token(participant.compound_name),
                "physical_state": "unknown_from_source",
                "bond_classes": [],
                "products": _unique_text(
                    product.compound_name
                    for record in source_records
                    for product in record.products
                ),
                "external_refs": _compound_external_refs(participant),
                "review_required": True,
                "review_required_fields": ["physical_state", "bond_classes", "products"],
                "allowed_use": REVIEW_ONLY_ALLOWED_USE,
                "notes": "SOURCE-002 proposed substrate record; categorical substrate fields require review.",
            }
        )
    return output


def _source_002_proposed_enzyme_classes(proposal: RegistryProposal) -> list[dict[str, Any]]:
    records_by_enzyme: dict[str, list[SabioRKReactionRecord]] = {}
    for record in proposal.reaction_records:
        key = stable_sabiork_token(record.ec_number or record.enzyme_name)
        records_by_enzyme.setdefault(key, []).append(record)
    output: list[dict[str, Any]] = []
    for records in records_by_enzyme.values():
        record = records[0]
        output.append(
            {
                "record_id": _source_002_enzyme_id(record),
                "proposal_status": proposal.proposal_status,
                "name": f"Proposed SABIO-RK enzyme class {record.enzyme_name or record.ec_number}",
                "display_name": record.enzyme_name,
                "aliases": _unique_text((record.enzyme_name, record.ec_number)),
                "ec_number": record.ec_number,
                "maturity": "source_extracted_proposal",
                "provenance": _source_002_provenance(records, proposal=proposal),
                "target_bond_classes": [],
                "compatible_substrate_classes": _unique_text(
                    stable_sabiork_token(participant.compound_name)
                    for source_record in records
                    for participant in source_record.substrates
                ),
                "compatible_processes": [proposal.process_type],
                "review_required": True,
                "review_required_fields": ["target_bond_classes", "compatible_substrate_classes"],
                "allowed_use": REVIEW_ONLY_ALLOWED_USE,
                "notes": "SOURCE-002 proposed enzyme-class record; enzyme compatibility must be reviewed.",
            }
        )
    return output


def _source_002_proposed_product_maps(proposal: RegistryProposal) -> list[dict[str, Any]]:
    return [
        {
            "record_id": stable_registry_proposal_id("product_map", record.reaction_id, record.entry_id),
            "proposal_status": proposal.proposal_status,
            "source_database": "SABIO-RK",
            "source_entry_id": record.entry_id,
            "source_reaction_id": record.reaction_id,
            "product_map": proposal.product_map,
            "product_map_type": "stoichiometric_roles_proposed",
            "substrates": [participant.to_dict() for participant in record.substrates],
            "products": [participant.to_dict() for participant in record.products],
            "participants": [participant.to_dict() for participant in record.participants],
            "stoichiometric_yields": _stoichiometric_yields(record),
            "review_required": True,
            "allowed_use": REVIEW_ONLY_ALLOWED_USE,
            "notes": "Proposed from SABIO-RK reaction roles; not accepted into the simulation registry.",
        }
        for record in proposal.reaction_records
    ]


def _source_002_proposed_parameter_records(proposal: RegistryProposal) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in proposal.reaction_records:
        for parameter in record.parameters:
            numeric_value = _as_float(parameter.start_value)
            exact_value_allowed = numeric_value is not None and parameter.units not in {"", "-"}
            records.append(
                {
                    "record_id": stable_registry_proposal_id(
                        "parameter",
                        record.reaction_id,
                        record.entry_id,
                        parameter.proposed_symbol,
                    ),
                    "proposal_status": proposal.proposal_status,
                    "name": f"Proposed SABIO-RK {parameter.proposed_symbol} from EntryID {record.entry_id}",
                    "maturity": "source_extracted_proposal",
                    "provenance": {
                        **_source_002_provenance((record,), proposal=proposal),
                        "source_field": parameter.source_field,
                    },
                    "parameter_symbol": parameter.proposed_symbol,
                    "process_type": proposal.process_type,
                    "enzyme_class": _source_002_enzyme_id(record),
                    "substrate_class": stable_sabiork_token(_primary_substrate_name(record.participants)),
                    "fungus_id": stable_registry_proposal_id("source", record.organism) if record.organism else None,
                    "substrate_id": _source_002_substrate_id(_primary_substrate_name(record.participants)),
                    "environment_id": None,
                    "value": {
                        "kind": "exact" if exact_value_allowed else "unknown",
                        "value": numeric_value if exact_value_allowed else None,
                        "units": parameter.units if parameter.units else None,
                        "source": "SABIO-RK kinetic-law entry",
                        "confidence_level": "source_extracted_unreviewed",
                        "notes": "Original source value preserved; not curated for simulation use.",
                    },
                    "source_value": parameter.start_value,
                    "source_units": parameter.units,
                    "normalized_start_value": parameter.normalized_start_value,
                    "normalized_units": parameter.normalized_units,
                    "range_scope": "single_source_entry",
                    "range_interpretation": "source_extracted_unreviewed",
                    "allowed_use": REVIEW_ONLY_ALLOWED_USE,
                    "review_required": True,
                    "notes": "SOURCE-002 proposal only; do not use directly in VirtualExperiment simulation.",
                }
            )
    return records


def _source_002_proposed_process_compatibility(proposal: RegistryProposal) -> list[dict[str, Any]]:
    return [
        {
            "record_id": stable_registry_proposal_id(
                "process_compatibility",
                record.reaction_id,
                record.entry_id,
                proposal.process_type,
            ),
            "proposal_status": proposal.proposal_status,
            "name": f"Proposed SABIO-RK EntryID {record.entry_id} process compatibility",
            "maturity": "source_extracted_proposal",
            "provenance": _source_002_provenance((record,), proposal=proposal),
            "enzyme_class": _source_002_enzyme_id(record),
            "substrate_class": stable_sabiork_token(_primary_substrate_name(record.participants)),
            "required_bond_classes": [],
            "process_type": proposal.process_type,
            "required_parameters": [parameter.proposed_symbol for parameter in record.parameters],
            "parameter_roles": _parameter_roles(record),
            "product_map_required": bool(record.products),
            "case_template_id": stable_registry_proposal_id(
                "case_template",
                record.reaction_id,
                record.entry_id,
                proposal.process_type,
            )
            if _case_template_safe(record, proposal=proposal)
            else "",
            "products": [participant.compound_name for participant in record.products],
            "review_required": True,
            "review_required_fields": ["required_bond_classes", "parameter_roles", "case_template_id"],
            "allowed_use": REVIEW_ONLY_ALLOWED_USE,
            "notes": "Proposed compatibility only; review before registry promotion.",
        }
        for record in proposal.reaction_records
    ]


def _source_002_proposed_case_templates(proposal: RegistryProposal) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in proposal.reaction_records:
        if not _case_template_safe(record, proposal=proposal):
            continue
        primary_substrate = _primary_substrate_name(record.participants)
        primary_product = record.products[0].compound_name
        record_id = stable_registry_proposal_id(
            "case_template",
            record.reaction_id,
            record.entry_id,
            proposal.process_type,
        )
        records.append(
            {
                "record_id": record_id,
                "case_template_id": record_id,
                "proposal_status": proposal.proposal_status,
                "name": f"Proposed SABIO-RK EntryID {record.entry_id} case template",
                "maturity": "source_extracted_proposal",
                "provenance": _source_002_provenance((record,), proposal=proposal),
                "process_type": proposal.process_type,
                "state_roles": {
                    "substrate": stable_sabiork_token(primary_substrate),
                    "product": stable_sabiork_token(primary_product),
                    "enzyme": "enzyme",
                },
                "product_map": {
                    "id": stable_registry_proposal_id("product_map", record.reaction_id, record.entry_id),
                    "product_map_type": "stoichiometric",
                    "substrate_state_role": "substrate",
                    "product_state_role": "product",
                },
                "stoichiometric_yields": _stoichiometric_yields(record),
                "review_required": True,
                "allowed_use": REVIEW_ONLY_ALLOWED_USE,
                "limitations": [
                    "Proposed case template only; initial states, observables, and runtime policy require review.",
                    "No new process biology is added by SOURCE-002.",
                ],
                "validity_notes": [
                    "Generated from source stoichiometry for review.",
                    "Not accepted by the production registry.",
                ],
            }
        )
    return records


def _write_proposal_yaml(
    path: Path,
    proposal_type: str,
    proposal: RegistryProposal,
    records: Sequence[Mapping[str, Any]],
) -> None:
    _write_yaml(
        path,
        {
            "kind": "fungmod_source_proposals",
            "proposal_type": proposal_type,
            "proposal_status": proposal.proposal_status,
            "source_query": proposal.source_query,
            "source_snapshot_path": proposal.source_snapshot_path,
            "records": list(records),
            "limitations": list(proposal.limitations),
        },
    )


def _source_002_report_markdown(proposal: RegistryProposal) -> str:
    preview = proposal.preview()
    lines = [
        "# SOURCE-002 SABIO-RK Discovery Registry Proposal",
        "",
        f"- Proposal status: `{proposal.proposal_status}`",
        f"- Source query: `{proposal.source_query or 'not_specified'}`",
        f"- Source snapshot: `{proposal.source_snapshot_path or 'not_specified'}`",
        f"- Process type: `{proposal.process_type}`",
        f"- Product map policy: `{proposal.product_map}`",
        "",
        "## Safety",
        "",
        "These files are review-only proposals. They are not production registry records and were not written to `data_registry/`.",
        "",
        "## Proposed Record Counts",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in preview["record_counts"].items())
    lines.extend(["", "## Entries", ""])
    lines.extend(
        [
            "| EntryID | Reaction ID | Organism | Enzyme | EC number | Substrates | Products | Parameters |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in proposal.reaction_records:
        lines.append(
            "| "
            + " | ".join(
                (
                    _md(record.entry_id),
                    _md(record.reaction_id),
                    _md(record.organism),
                    _md(record.enzyme_name),
                    _md(record.ec_number),
                    _md("; ".join(participant.compound_name for participant in record.substrates)),
                    _md("; ".join(participant.compound_name for participant in record.products)),
                    _md("; ".join(parameter.proposed_symbol for parameter in record.parameters)),
                )
            )
            + " |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in proposal.limitations)
    lines.append("")
    return "\n".join(lines)


def _ensure_not_data_registry(path: Path) -> None:
    resolved = path.resolve(strict=False)
    if "data_registry" in resolved.parts:
        raise SabioRKSourceError(
            "RegistryProposal.write refuses to write inside data_registry/. "
            "Write proposals under data/proposed_records/ or another review directory, then promote explicitly."
        )


def _source_002_provenance(
    records: Sequence[SabioRKReactionRecord],
    *,
    proposal: RegistryProposal,
) -> dict[str, Any]:
    source_urls = frozen_source_urls(proposal.source_snapshot_path)
    return {
        "source_database": "SABIO-RK",
        "source_query": proposal.source_query,
        "source_snapshot_path": proposal.source_snapshot_path,
        "source_url": source_urls[0] if len(source_urls) == 1 else None,
        "source_urls": list(source_urls),
        "source_entry_ids": list(_unique_text(record.entry_id for record in records)),
        "source_reaction_ids": list(_unique_text(record.reaction_id for record in records)),
        "proposal_status": proposal.proposal_status,
        "notes": "SOURCE-002 review-only proposal; not automatically promoted to the production registry.",
    }


def frozen_source_urls(source_snapshot_path: str) -> tuple[str, ...]:
    """Read source URLs from local frozen-snapshot metadata without network access."""

    urls: list[str] = []
    for value in source_snapshot_path.split("; "):
        metadata = _load_metadata(_metadata_path_for_export(Path(value)))
        raw_urls = metadata.get("source_urls")
        if raw_urls is None:
            continue
        if not isinstance(raw_urls, Sequence) or isinstance(raw_urls, (str, bytes)):
            raise SabioRKSourceError("SABIO-RK fetch metadata source_urls must be a sequence.")
        for url in raw_urls:
            if not isinstance(url, str) or not url.strip():
                raise SabioRKSourceError("SABIO-RK fetch metadata source_urls must contain nonblank URLs.")
            urls.append(url)
    return _unique_text(urls)


def _source_002_enzyme_id(record: SabioRKReactionRecord) -> str:
    return stable_registry_proposal_id("enzyme", record.ec_number or record.enzyme_name)


def _source_002_substrate_id(compound_name: str) -> str:
    return stable_registry_proposal_id("substrate", compound_name)


def _compound_external_refs(participant: SabioRKParticipant) -> dict[str, list[str]]:
    return {
        key: list(values)
        for key, values in participant.external_identifiers.items()
    }


def _parameter_roles(record: SabioRKReactionRecord) -> dict[str, str]:
    roles: dict[str, str] = {}
    for parameter in record.parameters:
        symbol = parameter.proposed_symbol
        lowered = symbol.lower()
        if lowered.startswith("km_"):
            roles.setdefault("Km", symbol)
        elif lowered.startswith("kcat_"):
            roles.setdefault("kcat", symbol)
        elif lowered == "enzyme_concentration":
            roles.setdefault("enzyme_concentration", symbol)
        else:
            roles.setdefault(symbol, symbol)
    return roles


def _case_template_safe(record: SabioRKReactionRecord, *, proposal: RegistryProposal) -> bool:
    return (
        proposal.product_map == "auto_from_stoichiometry"
        and proposal.process_type == "homogeneous_michaelis_menten"
        and bool(_primary_substrate_name(record.participants))
        and bool(record.products)
    )


def _stoichiometric_yields(record: SabioRKReactionRecord) -> dict[str, float]:
    yields: dict[str, float] = {}
    for participant in record.products:
        key = stable_sabiork_token(participant.compound_name)
        value = _as_float(participant.stoichiometry)
        yields[key] = value if value is not None and value > 0.0 else 1.0
    return yields


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
    "PROPOSAL_STATUS",
    "REVIEW_ONLY_ALLOWED_USE",
    "RegistryProposal",
    "RegistryProposalWriteResult",
    "SabioRKParticipant",
    "SabioRKReactionRecord",
    "SabioRKRecordProposal",
    "SabioRKKineticParameter",
    "SabioRKProposalWriteResult",
    "SabioRKSource",
    "SabioRKSourceError",
    "SabioRKSourceSnapshot",
    "SourceDiscoveryResult",
    "frozen_source_urls",
    "stable_registry_proposal_id",
    "stable_sabiork_token",
]
