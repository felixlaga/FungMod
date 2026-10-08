"""Assemble one reviewable user dataset for a fungus, substrates and conditions (ASSEMBLE-001).

``assemble_user_tables`` answers the request "fungus X on substrate(s) Y at
condition(s) Z" from the sources a user has: a dbCAN genome annotation of X or
a UniProtKB export of its proteome (a file, or a frozen snapshot written by
``fungal_model.sources.uniprot``), enzyme classes the user asserts for X, the
registry record of X, an existing user dataset that holds X, and SABIO-RK
kinetic-law entries (a proposal, a frozen snapshot or a downloaded export). It drafts ONE set of user-dataset
tables for exactly that request, together with a structured report
(``AssembledTablesDraft.assembly``) and a ``review.md`` that state, per enzyme
class, substrate and condition, what is known, from where, and what is missing.
The draft is reviewed and edited by a person and then loaded with
``load_user_dataset`` like any other user dataset.

Rules:

- The enzyme repertoire of X comes only from its genome annotation or
  proteome export, the classes the user asserts, its own rows in the user
  dataset, or the registry record of X; never from its name. Each class keeps
  its evidence. (A name can select a proteome only through
  ``fungal_model.sources.uniprot.resolve_proteome_name``, before assembling;
  the classes then come from that proteome's entries.)
- Whether a class acts on a substrate is decided by the categorical rule of
  the registry and of user datasets (``enzyme_class_acts_on``). Classes of X
  that do not act on a substrate are reported, and so are classes that act on
  it without any evidence in X; the latter are never added to X.
- Kinetics of a case (X, class, substrate, condition) come, in this order of
  precedence, from the user's dataset (rows kept unchanged), from SABIO-RK
  entries of X's own species (converted by ``user_tables_from_sabiork``, as
  literature), or from SABIO-RK entries of another organism (the same
  conversion; every non-design row then becomes an ``estimate`` whose method
  says "transferred from <organism> enzyme, SABIO-RK entry <id>"). Several
  candidates on the same level are listed and none is converted unless
  ``entry_ids`` selects one. A case without kinetics is left out of
  ``kinetics.csv``, so the loader records its gaps and measurement requests.
- Kinetics are never reused at a condition other than the one they were
  stated at. A requested condition is reached from a measured one only
  through a temperature or pH law in ``responses.csv``, as an
  ``EnvironmentGrid`` condition (the only place where the loader applies a
  law); otherwise it is a ``conditions.csv`` row whose gaps name the measured
  condition.
- Values the user must decide (the reviewer, the time grid, the enzyme
  concentration of the kcat form, an enzyme loading, a product yield the
  stoichiometry does not settle, a new substrate's categories, the source of
  an annotation) are ``REVIEW:`` fields unless given.
- Nothing is fetched, and the same inputs give byte-identical files.

With ``network=True`` (ASSEMBLE-002) the draft is one enzyme network per
requested substrate (``enzyme_network`` in ``user_dataset.yml``, the
USERDATA-010 route) instead of single-class cases: each requested substrate is
an entry substrate, and the pools it releases are followed only through
stated products (the request's ``product``, the user dataset's
``substrates.csv`` row, or a registry record's single product) that equal a
``substrate_id`` of the user dataset or a registry substrate ID, never a name.
Every class of the repertoire that acts on a pool is a member, with the same
per-case kinetics status; a member without kinetics is a gap, never dropped.
The loader's network rules are applied while drafting: intermediate pools
take no initial concentration, an entry has one, and what a network cannot run
(response laws, the pH-ionization form, cycles, ambiguous products, solid
pools, a class on two pools of one network, an entry no class acts on) is
refused or reported as a gap with the reason. Without ``network`` nothing
changes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from fungal_model.api.user_data import (
    _UNIPROT_PROTEOME_ID,
    CULTURE_TABLE,
    GENOME_TABLE,
    INHIBITOR_COLUMN,
    NETWORK_ENTRY_FIELD,
    NETWORK_MANIFEST_FIELD,
    PH_IONIZATION_QUANTITIES,
    RESPONSE_LAWS,
    REVIEW_MARKER,
    UNIPROT_SOURCE_TYPE,
    USER_DATASET_MANIFEST,
    UserDataset,
    _Context,
    _genome_tool,
    _names_uniprot,
    _read_overview,
    enzyme_class_acts_on,
    load_user_dataset,
)
from fungal_model.api.user_data_sources import (
    CONDITION_COLUMNS,
    ENZYME_CLASS_COLUMNS,
    ENZYME_COLUMNS,
    KINETICS_COLUMNS,
    STRAIN_COLUMNS,
    SUBSTRATE_COLUMNS,
    UserTablesDraft,
    UserTablesSourceError,
    _csv_text,
    _id_number,
    _load_entries,
    _manifest_text,
    _number_cell,
    _validated_design,
    user_tables_from_sabiork,
)
from fungal_model.capability import CapabilityResolver, CazymeAnnotation, CazymeFamilyMap
from fungal_model.capability.resolution import CapabilityResolutionError
from fungal_model.capability.uniprot import decode_uniprot_tsv, parse_uniprot_tsv, resolve_uniprot_proteome
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, units_are_compatible
from fungal_model.registry.loaders import load_registry
from fungal_model.registry.records import FungusRecord, SubstrateRecord
from fungal_model.registry.resolver import AmbiguousResolutionError, RegistryResolver, ResolutionError
from fungal_model.registry.store import FungModRegistry
from fungal_model.resources import default_registry_path
from fungal_model.sources.sabiork import RegistryProposal, stable_sabiork_token
from fungal_model.sources.uniprot import UniprotFetchError, UniprotSnapshot, load_proteome_snapshot, query_key

# Kinetics statuses of a case, as reported in ``AssembledTablesDraft.assembly["cases"]``.
STATUS_USER_DATA = "user_data"
STATUS_LITERATURE = "literature_same_organism"
STATUS_TRANSFERRED = "transferred_estimate"
STATUS_CONFLICT = "conflict"
STATUS_GAP = "gap"
ASSEMBLY_STATUSES = (STATUS_USER_DATA, STATUS_LITERATURE, STATUS_TRANSFERRED, STATUS_CONFLICT, STATUS_GAP)

# Whether an enzyme network of a network draft can run at a requested condition (all or nothing).
NETWORK_COMPLETE = "all_members_have_kinetics"
NETWORK_BLOCKED = "blocked"
NETWORK_UNDETERMINED = "undetermined"
NETWORK_CONDITION_STATUSES: Mapping[str, str] = MappingProxyType(
    {
        NETWORK_COMPLETE: "every member class has kinetics from a source and the entry's initial concentration is "
        "stated or a REVIEW field; check-data lists any role still missing once the tables are reviewed",
        NETWORK_BLOCKED: "a member class has no kinetics (gap or conflict) or the entry's initial concentration is "
        "missing; load_user_dataset records the gaps and the preflight blocks the network (all or nothing)",
        NETWORK_UNDETERMINED: "a pool's substrate class or bond classes are REVIEW fields, so its member classes are "
        "decided only when the reviewed tables are loaded",
    }
)

# How a case reaches its requested condition.
ROUTE_SAME_CONDITION = "same_condition"
ROUTE_RESPONSE_LAW = "response_law"
ROUTE_NONE = "none"

RESPONSE_COLUMNS = (
    "strain_id",
    "enzyme_class",
    "substrate_id",
    "law",
    "parameter",
    "value",
    "units",
    "evidence_type",
    "method",
    "source",
    "reference_tolerance",
    "kinetics_at_reference",
)
GENOME_COLUMNS = ("strain_id", "annotation_file", "annotation_tool", "source", "min_tools_agreeing")
ASSEMBLED_KINETICS_COLUMNS = (*KINETICS_COLUMNS, "replicates", "activity_substrate", "activity_saturating")
# A network draft's kinetics.csv also has the inhibitor column of ki rows (USERDATA-010).
NETWORK_KINETICS_COLUMNS = (*ASSEMBLED_KINETICS_COLUMNS, INHIBITOR_COLUMN)
_TABLE_COLUMNS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "strains.csv": STRAIN_COLUMNS,
        "enzymes.csv": ENZYME_COLUMNS,
        "enzyme_classes.csv": ENZYME_CLASS_COLUMNS,
        "substrates.csv": SUBSTRATE_COLUMNS,
        "conditions.csv": CONDITION_COLUMNS,
        "kinetics.csv": ASSEMBLED_KINETICS_COLUMNS,
        "responses.csv": RESPONSE_COLUMNS,
        GENOME_TABLE: GENOME_COLUMNS,
    }
)
_OPTIONAL_TABLES = frozenset({"enzyme_classes.csv", "responses.csv", GENOME_TABLE})
_REVIEW_MD = "review.md"
_ANNOTATION_DIRECTORY = "annotations"

_DATASET_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*$")
_CLASS_TOKEN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_DECIMAL_ID = re.compile(r"[1-9][0-9]*")
_TEMPERATURE_UNITS = ("degC", "kelvin")
_YIELD_BASIS = "mol/mol"
_LITERATURE = "literature"
_ESTIMATE = "estimate"
_DESIGN = "design"
_DESIGN_METHOD = "experimental design"
_CONSTANT_QUANTITIES = frozenset({"km", "kcat", "vmax", "specific_activity", "assay_activity"})
_KCAT_FORM = "kcat"
_VMAX_FORM = "vmax"
_KCAT_FORM_QUANTITIES = frozenset({"kcat", "enzyme_concentration"})
_VMAX_FORM_QUANTITIES = frozenset({"vmax", "specific_activity", "enzyme_loading", "assay_activity"})
_QUANTITY_ORDER = (
    "km",
    "kcat",
    "vmax",
    "specific_activity",
    "assay_activity",
    "enzyme_loading",
    "substrate_initial_concentration",
    "enzyme_concentration",
)
_SUBSTRATE_SPEC_KEYS = frozenset(
    {
        "substrate",
        "substrate_id",
        "substrate_class",
        "physical_state",
        "bond_classes",
        "product",
        "product_yield",
        "source",
    }
)
_REGISTRY_SUBSTRATE_SPEC_KEYS = frozenset({"substrate", "product", "product_yield", "source"})
_CONDITION_KEYS = frozenset({"condition_id", "temperature", "temperature_units", "ph", "notes"})
_CLASS_SPEC_KEYS = frozenset({"enzyme_class", "evidence", "source"})
_RESPONSE_KEYS = frozenset(
    {
        "enzyme_class",
        "substrate",
        "law",
        "parameter",
        "value",
        "units",
        "evidence_type",
        "method",
        "source",
        "reference_tolerance",
        "kinetics_at_reference",
    }
)
_RESPONSE_REQUIRED = ("enzyme_class", "substrate", "law", "parameter", "value", "units", "evidence_type", "source")
_TIME_GRID_KEYS = frozenset({"duration", "units", "points"})
# Two conditions are the same when their temperatures (in kelvin) and pH values are equal numbers;
# this relative tolerance only absorbs the floating-point rounding of the degC-to-kelvin conversion.
_FLOAT_EQUALITY = 1e-12

_LIMITATIONS = (
    "One fungus per call; its enzyme repertoire comes only from its genome annotation or proteome export, the "
    "classes you assert, its own rows in a user dataset, or its registry record.",
    "Offline sources only: a dbCAN overview.txt file or a UniProtKB TSV export (a file or a frozen UniProt "
    "proteome snapshot), a user dataset directory, and SABIO-RK entries from a RegistryProposal, a frozen snapshot "
    "or an export JSON. Nothing is fetched while assembling.",
    "Kinetics transferred from another organism's enzyme are estimates (exploratory mode only). FungMod never "
    "labels them literature or measured for this fungus; only you can change that, by editing kinetics.csv with "
    "your own evidence.",
    "A genome annotation or proteome export states which enzyme classes the fungus can encode; no rate, "
    "concentration, expression or secretion is taken from it.",
    "Kinetics are never reused at another condition. A requested condition is reached from a measured one only "
    "through a temperature or pH law in responses.csv, as an EnvironmentGrid condition.",
    "Homogeneous Michaelis-Menten kinetics on dissolved substrates only, as in every user dataset.",
)
_NETWORK_LIMITATIONS = (
    "Enzyme network draft: the member classes act together as independent Michaelis-Menten processes whose rates "
    "add on shared pools; no synergy, no competition for substrate binding or adsorption sites, and no inhibition "
    "unless a ki row states a competitive inhibitor.",
    "Pools are linked only where a stated product (the request, the user dataset's substrates.csv or a registry "
    "record's single product) equals a substrate_id; products are never matched by name, so a pool the data does "
    "not link is not part of the network.",
    "A network runs only when every member class has kinetics at the condition (all or nothing): a member without "
    "kinetics is a gap that blocks the network there, never a class left out.",
    "Response laws, the pH-ionization form, cultures and time courses are not combined with an enzyme network in "
    "this version; the network's kinetics apply at the condition of their rows.",
)


class UserTablesAssemblyError(UserTablesSourceError):
    """Raised when a fungus, substrate and condition request cannot be assembled into user tables."""


@dataclass(frozen=True)
class AssembledTablesDraft(UserTablesDraft):
    """User-dataset tables assembled for one fungus, its substrates and conditions, awaiting review.

    A ``UserTablesDraft`` (the tables, manifest, ``review.md``, review fields,
    converted and not-converted SABIO-RK entries and decisions) plus the
    optional ``responses.csv`` and ``genomes.csv`` rows, the annotation files
    copied into the draft (relative path to bytes) and ``assembly``, the
    structured report: the fungus and how it was resolved, its enzyme classes
    with their evidence, which classes act on each substrate, and per case
    (fungus, enzyme class, substrate, requested condition) the class evidence,
    the kinetics status (``user_data``, ``literature_same_organism``,
    ``transferred_estimate``, ``conflict`` or ``gap``), how the condition is
    reached, the source ids and the reason. A network draft
    (``assemble_user_tables(network=True)``) declares ``enzyme_network`` in its
    manifest, its ``kinetics.csv`` has the ``inhibitor`` column, and
    ``assembly["network"]`` reports its pools, links, member classes and
    per-condition status.
    """

    responses: tuple[Mapping[str, str], ...] = ()
    genomes: tuple[Mapping[str, str], ...] = ()
    annotation_files: Mapping[str, bytes] = field(default_factory=dict)
    assembly: Mapping[str, Any] = field(default_factory=dict)

    def tables(self) -> dict[str, tuple[Mapping[str, str], ...]]:
        """Return the table rows by file name; optional tables only when they have rows."""

        tables = {
            "strains.csv": self.strains,
            "enzymes.csv": self.enzymes,
            "enzyme_classes.csv": self.enzyme_classes,
            "substrates.csv": self.substrates,
            "conditions.csv": self.conditions,
            "kinetics.csv": self.kinetics,
            "responses.csv": self.responses,
            GENOME_TABLE: self.genomes,
        }
        return {name: rows for name, rows in tables.items() if rows or name not in _OPTIONAL_TABLES}

    def file_texts(self) -> dict[str, str]:
        """Return the exact text of the manifest, every table and ``review.md``, by file name."""

        texts = {USER_DATASET_MANIFEST: _manifest_text(self.manifest)}
        for name, rows in self.tables().items():
            texts[name] = _csv_text(_table_columns(name, self.manifest), rows)
        texts[_REVIEW_MD] = self.review
        return texts

    def write(self, directory: str | Path, *, overwrite: bool = False) -> dict[str, Path]:
        """Write the manifest, tables, annotation files and ``review.md`` into ``directory``.

        Existing files of the same name are refused unless ``overwrite`` is
        true, and nothing is written inside ``data_registry/``. The same draft
        gives byte-identical files.
        """

        root = Path(directory)
        if "data_registry" in root.resolve(strict=False).parts:
            raise UserTablesAssemblyError(
                "AssembledTablesDraft.write refuses to write inside data_registry/; user tables are an overlay, "
                "never registry records."
            )
        contents: dict[str, bytes] = {name: text.encode("utf-8") for name, text in self.file_texts().items()}
        contents.update(self.annotation_files)
        existing = sorted(name for name in contents if (root / name).exists())
        if existing and not overwrite:
            raise UserTablesAssemblyError(
                f"{root} already holds {', '.join(existing)}; pass overwrite=True to replace them."
            )
        paths: dict[str, Path] = {}
        for name, data in contents.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            paths[name] = path
        return paths

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_assembled_user_tables_draft",
            "dataset_id": self.dataset_id,
            "manifest": _plain(self.manifest),
            "tables": {name: [dict(row) for row in rows] for name, rows in self.tables().items()},
            "annotation_files": {
                name: hashlib.sha256(data).hexdigest() for name, data in sorted(self.annotation_files.items())
            },
            "converted_entry_ids": list(self.converted_entry_ids),
            "not_converted": [dict(item) for item in self.not_converted],
            "not_converted_parameters": [dict(item) for item in self.not_converted_parameters],
            "review_fields": [dict(item) for item in self.review_fields],
            "decisions": list(self.decisions),
            "assembly": _plain(self.assembly),
        }


def assemble_user_tables(
    *,
    dataset_id: str,
    fungus: str,
    substrates: str | Mapping[str, Any] | Sequence[str | Mapping[str, Any]],
    conditions: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    scientific_name: str | None = None,
    same_species: Sequence[str] = (),
    annotation: str | Path | None = None,
    annotation_tool: str | None = None,
    annotation_source: str | None = None,
    proteome: UniprotSnapshot | str | Path | None = None,
    proteome_selection: str | None = None,
    enzyme_classes: Sequence[str | Mapping[str, str]] | None = None,
    kinetics_sources: RegistryProposal | str | Path | Sequence[RegistryProposal | str | Path] = (),
    user_data: str | Path | UserDataset | None = None,
    responses: Sequence[Mapping[str, Any]] | None = None,
    design: Mapping[str, Mapping[str, Any]] | None = None,
    time_grid: Mapping[str, Any] | None = None,
    entry_ids: Sequence[str] | None = None,
    registry: str | Path | FungModRegistry | None = None,
    cache_dir: str | Path = "data/source_snapshots/sabiork",
    network: bool = False,
) -> AssembledTablesDraft:
    """Assemble one reviewable user dataset for a fungus on substrates at stated conditions.

    ``fungus`` is a strain of ``user_data`` (its ID, name or alias), a registry
    fungus (name, alias or ID; its record's enzyme classes then count as
    evidence and its stored registry cases are reported), or a free-text name
    for a new strain. ``scientific_name`` states the species of a new strain;
    a SABIO-RK entry counts as the fungus's own when its organism equals that
    species (or the registry record's or the dataset row's scientific name) or
    one of ``same_species``, organism names you map to the fungus explicitly.

    ``substrates`` are registry substrates (name, alias or ID), substrates of
    ``user_data``, or new substrates: a name, or a mapping with ``substrate``
    and optionally ``substrate_id``, ``substrate_class``, ``physical_state``,
    ``bond_classes``, ``product``, ``product_yield`` and ``source`` (missing
    fields become ``REVIEW:`` fields). For a registry substrate a mapping may
    add ``product``, ``product_yield`` and ``source`` only.

    ``conditions`` are explicit conditions, each a mapping with
    ``temperature``, ``temperature_units`` (``degC`` or ``kelvin``), ``ph`` and
    optionally ``condition_id`` and ``notes``. None is invented.

    ``annotation`` is a dbCAN ``overview.txt`` of the fungus, with
    ``annotation_tool`` (dbCAN and its version) and ``annotation_source`` (the
    genome or proteome annotated; a ``REVIEW:`` field when omitted); it is
    copied into the draft and listed in ``genomes.csv``. When
    ``annotation_tool`` names UniProt (followed by the release or download
    date), ``annotation`` is read as a UniProtKB TSV export instead, exactly as
    a ``genomes.csv`` UniProt row. ``proteome`` is a frozen UniProt proteome
    snapshot (a ``UniprotSnapshot`` or its directory, digest verified), the
    alternative to ``annotation``: its TSV is copied to
    ``annotations/<query key>.tsv`` and its ``genomes.csv`` row is the
    snapshot's (``UniprotSnapshot.genomes_row``: the release or retrieval date
    as the version, the organism, query, retrieval time, SHA-256 and URL as the
    source). ``proteome_selection`` states how that proteome was chosen (for
    example ``ProteomeNameResolution.statement``) and is recorded beside it.
    Classes resolve through the existing UniProt route (CAZy families through
    the family map, complete EC numbers through the registry). ``enzyme_classes`` are
    classes you assert for the fungus: names, aliases, EC numbers or IDs, or
    mappings with ``enzyme_class``, ``evidence`` and ``source`` (``REVIEW:``
    when omitted).

    ``kinetics_sources`` are SABIO-RK sources exactly as
    ``user_tables_from_sabiork`` accepts them; ``entry_ids`` selects entries
    across them. ``user_data`` is an existing user dataset directory (or a
    loaded ``UserDataset``) that holds the fungus; its rows for the fungus
    and the requested substrates are kept unchanged. ``responses`` are
    response-law rows (the columns of ``responses.csv`` with ``substrate`` in
    place of ``strain_id`` and ``substrate_id``) for the fungus. ``design``
    takes ``substrate_initial_concentration``, ``enzyme_concentration`` and
    ``enzyme_loading`` as in ``user_tables_from_sabiork``; ``time_grid`` takes
    ``duration``, ``units`` and ``points``.

    ``network=True`` drafts an enzyme network (``enzyme_network`` in
    ``user_dataset.yml``) instead of single-class cases: every requested
    substrate is an entry substrate, the pools it releases are followed through
    stated products that equal a ``substrate_id`` of ``user_data`` or a
    registry substrate ID (added to the draft), and every class of the
    repertoire acting on a pool is a member with its own per-case kinetics
    status; ``assembly["network"]`` reports pools, links, members, classes that
    act on no pool, and whether each requested condition can run (all members
    with kinetics and the entry's initial concentration). ``user_data`` may then
    be a network dataset itself (its ``ki`` rows are kept). Refused with the
    reason: ``responses`` (laws are not bound to network processes), a cycle of
    products, a product that equals the registry substrate of a pool with
    another ``substrate_id``, a product that is a solid substrate, a class
    acting on two pools of one network, an entry no class acts on, colliding
    state names, and disagreeing initial concentrations of an entry in the
    user's rows.

    Returns an ``AssembledTablesDraft``; ``draft.write(directory)`` writes the
    tables, the annotation file, ``user_dataset.yml`` and ``review.md``, and
    ``draft.assembly`` is the per-case report. ``load_user_dataset`` refuses
    the directory until every ``REVIEW:`` field is filled. Nothing is fetched:
    a proteome snapshot is fetched beforehand, on explicit request, by
    ``fungal_model.sources.uniprot``.
    """

    if not isinstance(dataset_id, str) or not _DATASET_ID.fullmatch(dataset_id):
        raise UserTablesAssemblyError(
            "dataset_id must be lowercase snake_case (letters, digits, single underscores), as user_dataset.yml "
            "requires."
        )
    if not isinstance(network, bool):
        raise UserTablesAssemblyError("network must be True or False.")
    base = _base_registry(registry)
    try:
        design_values = _validated_design(design)
    except UserTablesSourceError as exc:
        raise UserTablesAssemblyError(str(exc)) from exc
    assembler = _Assembler(dataset_id=dataset_id, base=base, design=design, cache_dir=cache_dir)
    assembler.network = network
    assembler.design_values = dict(design_values)
    assembler.design_quantities = tuple(design_values)
    assembler.simulation = _validated_time_grid(time_grid)
    assembler.requested = _validated_conditions(conditions)
    assembler.user = _user_source(user_data, base, network=network)
    assembler.resolve_fungus(fungus, scientific_name=scientific_name)
    assembler.resolve_substrates(_substrate_specs(substrates))
    if network:
        assembler.discover_network_pools()
    assembler.collect_classes(
        annotation=annotation,
        annotation_tool=annotation_tool,
        annotation_source=annotation_source,
        asserted=enzyme_classes,
        proteome=proteome,
        proteome_selection=proteome_selection,
    )
    assembler.collect_entries(_source_tuple(kinetics_sources), entry_ids=entry_ids, same_species=same_species)
    assembler.collect_user_candidates()
    assembler.collect_laws(responses)
    return assembler.build()


# ---------------------------------------------------------------------------
# Input validation


def _base_registry(registry: str | Path | FungModRegistry | None) -> FungModRegistry:
    if isinstance(registry, FungModRegistry):
        return registry
    return load_registry(default_registry_path() if registry is None else Path(registry))


def _validated_time_grid(time_grid: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if time_grid is None:
        return None
    if not isinstance(time_grid, Mapping):
        raise UserTablesAssemblyError("time_grid must be a mapping with duration, units and points.")
    unknown = sorted(str(key) for key in time_grid if key not in _TIME_GRID_KEYS)
    missing = sorted(key for key in _TIME_GRID_KEYS if key not in time_grid)
    if unknown or missing:
        raise UserTablesAssemblyError(
            f"time_grid needs exactly duration, units and points (unknown: {', '.join(unknown) or 'none'}; "
            f"missing: {', '.join(missing) or 'none'})."
        )
    duration, units, points = time_grid["duration"], time_grid["units"], time_grid["points"]
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise UserTablesAssemblyError("time_grid['duration'] must be a positive number.")
    if not isinstance(units, str) or not _parses(units) or not units_are_compatible(units, "second"):
        raise UserTablesAssemblyError("time_grid['units'] must be a time unit such as second, minute or hour.")
    if isinstance(points, bool) or not isinstance(points, int) or points < 2:
        raise UserTablesAssemblyError("time_grid['points'] must be an integer of at least 2.")
    return {"duration": duration, "units": units, "points": points}


@dataclass(frozen=True)
class _Requested:
    """One requested condition."""

    index: int
    condition_id: str
    explicit_id: bool
    temperature: float
    temperature_units: str
    ph: float
    notes: str
    kelvin: float

    @property
    def cells(self) -> dict[str, str]:
        return {
            "temperature": _number_cell(self.temperature),
            "temperature_units": self.temperature_units,
            "ph": _number_cell(self.ph),
        }

    @property
    def text(self) -> str:
        return f"{_number_cell(self.temperature)} {self.temperature_units}, pH {_number_cell(self.ph)}"

    @property
    def temperature_c(self) -> float:
        return float(Q_(self.kelvin, "kelvin").to("degC").magnitude)


def _validated_conditions(conditions: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[_Requested]:
    items: Sequence[Any] = [conditions] if isinstance(conditions, Mapping) else conditions
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence) or not items:
        raise UserTablesAssemblyError(
            "conditions must be one or more mappings with temperature, temperature_units and ph; FungMod does not "
            "invent conditions."
        )
    output: list[_Requested] = []
    for index, item in enumerate(items):
        label = f"conditions[{index}]"
        if not isinstance(item, Mapping):
            raise UserTablesAssemblyError(f"{label} must be a mapping with temperature, temperature_units and ph.")
        unknown = sorted(str(key) for key in item if key not in _CONDITION_KEYS)
        if unknown:
            raise UserTablesAssemblyError(f"{label} has unsupported key(s): {', '.join(unknown)}.")
        missing = [key for key in ("temperature", "temperature_units", "ph") if key not in item]
        if missing:
            raise UserTablesAssemblyError(
                f"{label} needs {', '.join(missing)}; a requested condition states its temperature with units and "
                "its pH explicitly."
            )
        units = item["temperature_units"]
        if units not in _TEMPERATURE_UNITS:
            raise UserTablesAssemblyError(f"{label}['temperature_units'] must be degC or kelvin; got {units!r}.")
        temperature = _finite(item["temperature"])
        ph = _finite(item["ph"])
        if temperature is None or ph is None:
            raise UserTablesAssemblyError(f"{label} temperature and ph must be finite numbers.")
        kelvin = float(Q_(temperature, units).to("kelvin").magnitude)
        if kelvin <= 0.0:
            raise UserTablesAssemblyError(f"{label} temperature must be above absolute zero.")
        if not 0.0 <= ph <= 14.0:
            raise UserTablesAssemblyError(f"{label} ph must lie between 0 and 14.")
        explicit = item.get("condition_id")
        if explicit is not None and (not isinstance(explicit, str) or not _IDENTIFIER.fullmatch(explicit)):
            raise UserTablesAssemblyError(
                f"{label}['condition_id'] must use letters and digits joined by single underscores."
            )
        notes = item.get("notes", "")
        if not isinstance(notes, str):
            raise UserTablesAssemblyError(f"{label}['notes'] must be text.")
        generated = f"{'c' if units == 'degC' else 'k'}{_id_number(temperature)}_ph{_id_number(ph)}"
        requested = _Requested(
            index=index,
            condition_id=explicit if explicit else generated,
            explicit_id=bool(explicit),
            temperature=temperature,
            temperature_units=units,
            ph=ph,
            notes=notes.strip(),
            kelvin=kelvin,
        )
        for earlier in output:
            if _same_condition(earlier.kelvin, earlier.ph, requested.kelvin, requested.ph):
                raise UserTablesAssemblyError(
                    f"{label} repeats the condition of conditions[{earlier.index}] ({earlier.text})."
                )
            if earlier.explicit_id and requested.explicit_id and earlier.condition_id == requested.condition_id:
                raise UserTablesAssemblyError(f"{label} repeats condition_id {requested.condition_id!r}.")
        output.append(requested)
    return output


def _substrate_specs(
    substrates: str | Mapping[str, Any] | Sequence[str | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items: Sequence[Any] = [substrates] if isinstance(substrates, (str, Mapping)) else substrates
    if not isinstance(items, Sequence) or not items:
        raise UserTablesAssemblyError("substrates must name at least one substrate.")
    specs: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            spec: dict[str, Any] = {"substrate": item}
        elif isinstance(item, Mapping):
            spec = dict(item)
        else:
            raise UserTablesAssemblyError(f"substrates[{index}] must be a name or a mapping.")
        unknown = sorted(str(key) for key in spec if key not in _SUBSTRATE_SPEC_KEYS)
        if unknown:
            raise UserTablesAssemblyError(f"substrates[{index}] has unsupported key(s): {', '.join(unknown)}.")
        text = spec.get("substrate")
        if not isinstance(text, str) or not text.strip():
            raise UserTablesAssemblyError(f"substrates[{index}] needs a nonblank substrate name.")
        spec["substrate"] = text.strip()
        specs.append(spec)
    return specs


def _source_tuple(
    sources: RegistryProposal | str | Path | Sequence[RegistryProposal | str | Path],
) -> tuple[RegistryProposal | str | Path, ...]:
    if isinstance(sources, (RegistryProposal, str, Path)):
        return (sources,)
    return tuple(sources)


# ---------------------------------------------------------------------------
# A user dataset that holds the fungus


@dataclass
class _UserSource:
    dataset: UserDataset
    directory: Path
    manifest: Mapping[str, Any]
    rows: dict[str, list[tuple[int, dict[str, str]]]]

    def table(self, name: str) -> list[tuple[int, dict[str, str]]]:
        return self.rows.get(name, [])


def _user_source(
    user_data: str | Path | UserDataset | None, base: FungModRegistry, *, network: bool = False
) -> _UserSource | None:
    if user_data is None:
        return None
    if isinstance(user_data, UserDataset):
        directory = Path(user_data.source_directory)
        dataset = load_user_dataset(directory, registry=base)
        if dataset.digest != user_data.digest:
            raise UserTablesAssemblyError(
                f"The user dataset in {directory} changed on disk since it was loaded (digest {user_data.digest} "
                f"became {dataset.digest}); pass the directory again."
            )
    else:
        directory = Path(user_data)
        dataset = load_user_dataset(directory, registry=base)
    if dataset.enzyme_networks and not network:
        # A network is a modelling choice of the dataset's manifest; single-class drafts would drop it.
        raise UserTablesAssemblyError(
            f"User dataset {dataset.dataset_id!r} declares enzyme networks (enzyme_network in user_dataset.yml, from "
            f"{', '.join(str(item['entry_substrate']) for item in dataset.enzyme_networks)}); assembled drafts are "
            "single-class tables unless network=True (fungmod assemble --network) drafts a network, so this draft "
            "would drop it. Pass network=True, or load that dataset with load_user_dataset directly."
        )
    rows = {name: _read_rows(directory / name) for name in _TABLE_COLUMNS}
    return _UserSource(dataset=dataset, directory=directory, manifest=dict(dataset.manifest), rows=rows)


def _read_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    if not path.is_file():
        return []
    reader = csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline=""))
    header = [cell.strip() for cell in next(reader, [])]
    rows: list[tuple[int, dict[str, str]]] = []
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        rows.append(
            (reader.line_num, {column: (cells[i].strip() if i < len(cells) else "") for i, column in enumerate(header)})
        )
    return rows


# ---------------------------------------------------------------------------
# Working records


@dataclass(frozen=True)
class _Measured:
    """A condition at which kinetics were stated, with its conditions.csv cells."""

    condition_id: str
    temperature: str
    temperature_units: str
    ph: str
    notes: str
    kelvin: float | None
    ph_value: float | None
    user_row: Mapping[str, str] | None = None

    @property
    def single(self) -> bool:
        return self.kelvin is not None and self.ph_value is not None

    @property
    def text(self) -> str:
        temperature = (
            "unknown temperature"
            if self.temperature == "unknown"
            else (
                "a temperature still under review"
                if self.temperature.startswith(REVIEW_MARKER) or self.temperature_units.startswith(REVIEW_MARKER)
                else f"{self.temperature} {self.temperature_units}"
            )
        )
        ph = (
            "unknown pH"
            if self.ph == "unknown"
            else ("a pH still under review" if self.ph.startswith(REVIEW_MARKER) else f"pH {self.ph}")
        )
        return f"{temperature}, {ph}"

    def matches(self, requested: _Requested) -> bool:
        return (
            self.kelvin is not None
            and self.ph_value is not None
            and _same_condition(self.kelvin, self.ph_value, requested.kelvin, requested.ph)
        )

    def same_as(self, other: _Measured) -> bool:
        return (
            self.kelvin is not None
            and self.ph_value is not None
            and other.kelvin is not None
            and other.ph_value is not None
            and _same_condition(self.kelvin, self.ph_value, other.kelvin, other.ph_value)
        )


def _measured(condition_id: str, row: Mapping[str, str], *, user_row: bool) -> _Measured:
    temperature, units, ph = row.get("temperature", ""), row.get("temperature_units", ""), row.get("ph", "")
    number = _finite_text(temperature)
    kelvin = (
        float(Q_(number, units).to("kelvin").magnitude) if number is not None and units in _TEMPERATURE_UNITS else None
    )
    ph_value = _finite_text(ph)
    if ph_value is not None and not 0.0 <= ph_value <= 14.0:
        ph_value = None
    return _Measured(
        condition_id=condition_id,
        temperature=temperature,
        temperature_units=units,
        ph=ph,
        notes=row.get("notes", ""),
        kelvin=kelvin,
        ph_value=ph_value,
        user_row=dict(row) if user_row else None,
    )


@dataclass
class _Target:
    """One requested substrate."""

    index: int
    input: str
    substrate_id: str
    registry_id: str
    name: str
    substrate_class: str | None
    bond_classes: tuple[str, ...] | None
    resolved_as: str
    spec: Mapping[str, Any]
    user_row: dict[str, str] | None = None
    record: SubstrateRecord | None = None
    # Network drafts only: "entry" for a requested substrate, "intermediate" for a pool a stated product adds.
    network_role: str = ""
    released_by: str = ""

    @property
    def determined(self) -> bool:
        return self.substrate_class is not None and self.bond_classes is not None


@dataclass
class _NetworkDraft:
    """The pools one requested substrate releases through stated products, in chain order."""

    entry: _Target
    pools: list[_Target]
    # (substrate_id, product, where the product is stated) of every pool, in chain order.
    products: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class _Evidence:
    kind: str
    evidence: str
    source: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "evidence": self.evidence, "source": self.source, **self.details}


@dataclass
class _Class:
    """One enzyme class of the fungus, with its evidence."""

    key: str
    origin: str
    name: str
    target_bond_classes: tuple[str, ...]
    compatible_substrate_classes: tuple[str, ...]
    evidence: list[_Evidence] = field(default_factory=list)
    row: dict[str, str] | None = None
    user_class_row: dict[str, str] | None = None

    def acts_on(self, target: _Target) -> tuple[str, ...]:
        assert target.substrate_class is not None and target.bond_classes is not None
        return enzyme_class_acts_on(
            target_bond_classes=self.target_bond_classes,
            compatible_substrate_classes=self.compatible_substrate_classes,
            substrate_class=target.substrate_class,
            bond_classes=target.bond_classes,
        )

    def evidence_texts(self) -> list[str]:
        return [_evidence_text(item.evidence, item.source) for item in self.evidence]


@dataclass
class _EntryInfo:
    """One SABIO-RK entry and what became of it."""

    entry_id: str
    organism: str
    host: str
    enzyme: str
    source_label: str
    draft: UserTablesDraft | None = None
    reason: str = ""
    class_key: str = ""
    substrate_text: str = ""
    measured: _Measured | None = None
    target: _Target | None = None
    use: str = ""


@dataclass
class _Candidate:
    """Kinetics for one enzyme class and substrate at one measured condition, from one source."""

    order: int
    level: int
    status: str
    class_key: str
    target: _Target
    measured: _Measured
    rows: list[dict[str, str]]
    form: str
    source_ids: tuple[str, ...]
    label: str
    entry: _EntryInfo | None = None
    excluded: str = ""

    @property
    def has_constants(self) -> bool:
        return any(row["quantity"] in _CONSTANT_QUANTITIES for row in self.rows)


@dataclass
class _Case:
    target: _Target
    enzyme_class: _Class
    requested: _Requested
    status: str = STATUS_GAP
    route: str = ROUTE_NONE
    chosen: _Candidate | None = None
    measured: _Measured | None = None
    listed: list[_Candidate] = field(default_factory=list)
    reason: str = ""
    pure_gap: bool = False
    design_written: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Assembly


class _Assembler:
    def __init__(
        self,
        *,
        dataset_id: str,
        base: FungModRegistry,
        design: Mapping[str, Mapping[str, Any]] | None,
        cache_dir: str | Path,
    ) -> None:
        self.dataset_id = dataset_id
        self.base = base
        self.resolver = RegistryResolver(base)
        self.design = design
        self.design_quantities: tuple[str, ...] = ()
        self.design_values: dict[str, Any] = {}
        self.cache_dir = cache_dir
        self.simulation: dict[str, Any] | None = None
        self.requested: list[_Requested] = []
        self.user: _UserSource | None = None
        # fungus
        self.fungus_input = ""
        self.strain_id = ""
        self.strain_name = ""
        self.strain_row: dict[str, str] = {}
        self.fungus_resolved_as = ""
        self.fungus_record: FungusRecord | None = None
        self.species: list[str] = []
        self.user_strain_id = ""
        # substrates, classes and sources
        self.targets: list[_Target] = []
        self.classes: dict[str, _Class] = {}
        self.genome_rows: list[dict[str, str]] = []
        self.annotation_files: dict[str, bytes] = {}
        self.annotation_report: dict[str, Any] = {}
        self.unmodellable: list[dict[str, Any]] = []
        self.unmapped: list[dict[str, Any]] = []
        self.entries: list[_EntryInfo] = []
        self.sources: list[dict[str, Any]] = []
        self.candidates: list[_Candidate] = []
        self.unused_user_rows: list[str] = []
        self.laws: dict[tuple[str, str], list[dict[str, str]]] = {}
        self.law_origin: dict[tuple[str, str], str] = {}
        self.decisions: list[str] = []
        self.not_converted_parameters: list[dict[str, str]] = []
        # enzyme networks (network=True only)
        self.network = False
        self.networks: list[_NetworkDraft] = []
        # (substrate_id, condition_id) whose initial concentration a kinetics.csv row states (value or REVIEW field)
        self.network_initials: set[tuple[str, str]] = set()

    # -- the fungus ----------------------------------------------------------

    def resolve_fungus(self, fungus: str, *, scientific_name: str | None) -> None:
        if not isinstance(fungus, str) or not fungus.strip():
            raise UserTablesAssemblyError("fungus must be a nonblank name.")
        if scientific_name is not None and (not isinstance(scientific_name, str) or not scientific_name.strip()):
            raise UserTablesAssemblyError("scientific_name must be nonblank text when given.")
        text = fungus.strip()
        self.fungus_input = text
        if self.user is not None:
            self._user_fungus(text, scientific_name)
            return
        try:
            resolved = self.resolver.resolve_fungus(text)
        except AmbiguousResolutionError as exc:
            raise UserTablesAssemblyError(f"fungus {text!r} is ambiguous in the registry: {exc}") from exc
        except ResolutionError:
            self._new_fungus(text, scientific_name)
            return
        record = self.base.get_fungus(resolved.record_id)
        species = record.scientific_name.strip()
        if scientific_name is not None and species and _norm(scientific_name) != _norm(species):
            raise UserTablesAssemblyError(
                f"scientific_name {scientific_name!r} differs from the registry record {record.record_id!r} of "
                f"{text!r}, whose scientific name is {species!r}."
            )
        self.fungus_record = record
        self.fungus_resolved_as = "registry_fungus"
        self.strain_id = self._free_strain_id(f"{record.record_id}_assembled")
        self.strain_name = f"{record.name} (assembled for {self.dataset_id})"
        chosen = species or (scientific_name.strip() if scientific_name else "")
        self.species = [chosen] if chosen else []
        self.strain_row = {
            "strain_id": self.strain_id,
            "name": self.strain_name,
            "scientific_name": chosen,
            "aliases": "",
        }
        self.decisions.append(
            f"Fungus {text!r} resolves to registry fungus `{record.record_id}` (matched {resolved.matched_field} "
            f"{resolved.matched_value!r}); the draft's strain `{self.strain_id}` stands for it, because user-data "
            "strains may not reuse registry names. Its record's enzyme classes count as evidence, and its stored "
            "registry cases are listed."
        )

    def _user_fungus(self, text: str, scientific_name: str | None) -> None:
        assert self.user is not None
        matches: list[dict[str, str]] = []
        for _line, row in self.user.table("strains.csv"):
            names = {
                row.get("strain_id", ""),
                _norm(row.get("name", "")),
                *(_norm(a) for a in _split(row.get("aliases", ""))),
            }
            if text in names or _norm(text) in names:
                matches.append(row)
        if len(matches) != 1:
            available = ", ".join(
                f"{row.get('strain_id', '')} ({row.get('name', '')})" for _line, row in self.user.table("strains.csv")
            )
            raise UserTablesAssemblyError(
                f"fungus {text!r} names {'no' if not matches else 'more than one'} strain of the user dataset "
                f"{self.user.dataset.dataset_id!r} (strains: {available}). Name the strain the dataset holds for "
                "this fungus; the rows of other strains are not this fungus's data."
            )
        row = matches[0]
        species = row.get("scientific_name", "")
        if scientific_name is not None and _norm(scientific_name) != _norm(species):
            raise UserTablesAssemblyError(
                f"scientific_name {scientific_name!r} differs from strains.csv of the user dataset "
                f"({species or 'blank'!r}); the dataset's rows are kept unchanged, so edit the dataset instead."
            )
        self.fungus_resolved_as = "user_data_strain"
        self.strain_id = row["strain_id"]
        self.user_strain_id = row["strain_id"]
        self.strain_name = row["name"]
        self.strain_row = dict(row)
        self.species = [species] if species else []
        self.decisions.append(
            f"Fungus {text!r} is strain `{self.strain_id}` of user dataset {self.user.dataset.dataset_id!r} "
            f"(digest {self.user.dataset.digest}); its rows are kept unchanged."
        )

    def _new_fungus(self, text: str, scientific_name: str | None) -> None:
        self.fungus_resolved_as = "new_strain"
        self.strain_id = self._free_strain_id(stable_sabiork_token(text))
        self.strain_name = text
        species = scientific_name.strip() if scientific_name else ""
        self.species = [species] if species else []
        self.strain_row = {"strain_id": self.strain_id, "name": text, "scientific_name": species, "aliases": ""}
        self.decisions.append(
            f"Fungus {text!r} is not in the registry; it becomes the new strain `{self.strain_id}`"
            + (
                f" of species {species!r}."
                if species
                else " with no species stated (pass scientific_name to state it)."
            )
        )

    def _free_strain_id(self, candidate: str) -> str:
        strain_id = candidate
        while _resolves(self.resolver.resolve_fungus, strain_id):
            strain_id = f"{strain_id}_strain"
        return strain_id

    # -- substrates ----------------------------------------------------------

    def resolve_substrates(self, specs: Sequence[Mapping[str, Any]]) -> None:
        for index, spec in enumerate(specs):
            target = self._target(index, spec)
            for earlier in self.targets:
                if earlier.substrate_id == target.substrate_id:
                    raise UserTablesAssemblyError(
                        f"substrates[{index}] ({target.input!r}) is the same substrate as substrates[{earlier.index}] "
                        f"({earlier.input!r})."
                    )
            self.targets.append(target)

    def _target(self, index: int, spec: Mapping[str, Any]) -> _Target:
        text = str(spec["substrate"])
        extra = sorted(key for key in spec if key != "substrate")
        if self.user is not None:
            row = self._user_substrate(text)
            if row is not None:
                if extra:
                    raise UserTablesAssemblyError(
                        f"substrates[{index}] ({text!r}) is substrate {row['substrate_id']!r} of the user dataset, whose "
                        f"row is kept unchanged; {', '.join(extra)} cannot be given here. Edit the dataset instead."
                    )
                return self._user_target(index, text, row)
        try:
            resolved = self.resolver.resolve_substrate(text)
        except AmbiguousResolutionError as exc:
            raise UserTablesAssemblyError(f"substrate {text!r} is ambiguous in the registry: {exc}") from exc
        except ResolutionError:
            return self._new_target(index, spec)
        record = self.base.get_substrate(resolved.record_id)
        if record.physical_state != "dissolved":
            raise UserTablesAssemblyError(
                f"substrate {text!r} is registry substrate {record.record_id!r} with physical state "
                f"{record.physical_state!r}; user datasets model dissolved substrates only."
            )
        refused = sorted(key for key in spec if key not in _REGISTRY_SUBSTRATE_SPEC_KEYS)
        if refused:
            raise UserTablesAssemblyError(
                f"substrates[{index}] ({text!r}) is registry substrate {record.record_id!r}, which is referenced, not "
                f"copied; {', '.join(refused)} cannot be given for it."
            )
        return _Target(
            index=index,
            input=text,
            substrate_id=record.record_id,
            registry_id=record.record_id,
            name=record.name,
            substrate_class=record.substrate_class,
            bond_classes=tuple(record.bond_classes),
            resolved_as="registry",
            spec=dict(spec),
            record=record,
        )

    def _user_substrate(self, text: str) -> dict[str, str] | None:
        assert self.user is not None
        registry_id = ""
        try:
            registry_id = self.resolver.resolve_substrate(text).record_id
        except ResolutionError:
            registry_id = ""
        for _line, row in self.user.table("substrates.csv"):
            if row.get("substrate_id") == text or (row.get("name") and _norm(row["name"]) == _norm(text)):
                return row
            reference = row.get("registry_substrate", "")
            if reference and registry_id and self.resolver.resolve_substrate(reference).record_id == registry_id:
                return row
        return None

    def _user_target(self, index: int, text: str, row: dict[str, str]) -> _Target:
        reference = row.get("registry_substrate", "")
        record = (
            self.base.get_substrate(self.resolver.resolve_substrate(reference).record_id) if reference else None
        )
        state = record.physical_state if record is not None else row.get("physical_state", "")
        if state != "dissolved":
            # A solid substrate of a user dataset is stated on a dry-mass basis (amount_basis, a g/g yield);
            # drafted tables carry dissolved substrates only, so the row would lose its basis here. Drafts carry
            # no culture.csv either: a culture of the dataset on this substrate would be lost.
            assert self.user is not None
            cultured = [item for item in self.user.dataset.cultures if item["substrate_id"] == row["substrate_id"]]
            culture_text = (
                f", and the dataset's {CULTURE_TABLE} has a culture on it (strain "
                f"{', '.join(repr(item['strain_id']) for item in cultured)}), which drafts do not carry"
                if cultured
                else ""
            )
            raise UserTablesAssemblyError(
                f"substrates[{index}] ({text!r}) is substrate {row['substrate_id']!r} of the user dataset with "
                f"physical state {state!r}; assembled drafts cover dissolved substrates only{culture_text}. Load "
                "that dataset with load_user_dataset directly."
            )
        if record is not None:
            return _Target(
                index=index,
                input=text,
                substrate_id=row["substrate_id"],
                registry_id=record.record_id,
                name=record.name,
                substrate_class=record.substrate_class,
                bond_classes=tuple(record.bond_classes),
                resolved_as="user_data",
                spec={"substrate": text},
                user_row=dict(row),
                record=record,
            )
        return _Target(
            index=index,
            input=text,
            substrate_id=row["substrate_id"],
            registry_id="",
            name=row.get("name", ""),
            substrate_class=row.get("substrate_class", ""),
            bond_classes=_split(row.get("bond_classes", "")),
            resolved_as="user_data",
            spec={"substrate": text},
            user_row=dict(row),
        )

    def _new_target(self, index: int, spec: Mapping[str, Any]) -> _Target:
        text = str(spec["substrate"])
        substrate_id = spec.get("substrate_id", stable_sabiork_token(text))
        if not isinstance(substrate_id, str) or not _IDENTIFIER.fullmatch(substrate_id):
            raise UserTablesAssemblyError(
                f"substrates[{index}]['substrate_id'] must use letters and digits joined by single underscores."
            )
        if _resolves(self.resolver.resolve_substrate, substrate_id):
            raise UserTablesAssemblyError(
                f"substrates[{index}]['substrate_id'] {substrate_id!r} names a registry substrate; choose another ID "
                "for the new substrate."
            )
        substrate_class = spec.get("substrate_class")
        if substrate_class is not None and (
            not isinstance(substrate_class, str) or not _CLASS_TOKEN.fullmatch(substrate_class)
        ):
            raise UserTablesAssemblyError(f"substrates[{index}]['substrate_class'] must be lowercase snake_case.")
        state = spec.get("physical_state")
        if state is not None and state != "dissolved":
            raise UserTablesAssemblyError(
                f"substrates[{index}]['physical_state'] {state!r} is not supported; user datasets model dissolved "
                "substrates only."
            )
        bonds_value = spec.get("bond_classes")
        bonds: tuple[str, ...] | None = None
        if bonds_value is not None:
            bonds = (
                _split(bonds_value)
                if isinstance(bonds_value, str)
                else tuple(str(item).strip() for item in bonds_value)
            )
            if not bonds or any(not _CLASS_TOKEN.fullmatch(item) for item in bonds):
                raise UserTablesAssemblyError(
                    f"substrates[{index}]['bond_classes'] must be lowercase snake_case bond classes."
                )
        return _Target(
            index=index,
            input=text,
            substrate_id=substrate_id,
            registry_id="",
            name=text,
            substrate_class=substrate_class,
            bond_classes=bonds,
            resolved_as="new",
            spec=dict(spec),
        )

    # -- enzyme network pools (network=True) ---------------------------------

    def discover_network_pools(self) -> None:
        """Follow each requested substrate's stated products to the pools of its enzyme network.

        Each requested substrate is an entry substrate. A product links to a
        pool only when it equals the substrate_id of a requested substrate, of
        a user-dataset ``substrates.csv`` row, or a registry substrate ID (the
        draft's substrate_id of a registry substrate), which is the loader's
        rule; such a pool joins the draft as an intermediate. Names and aliases
        are never matched, and a product that is no pool is the network's final
        product.
        """

        for target in self.targets:
            target.network_role = "entry"
        for entry in list(self.targets):
            pools = [entry]
            products: list[tuple[str, str, str]] = []
            while True:
                current = pools[-1]
                stated = self._stated_product(current)
                if stated is None:
                    break
                product, origin = stated
                products.append((current.substrate_id, product, origin))
                pool = self._pool_for_product(current, product, origin)
                if pool is None:
                    break
                if pool in pools:
                    chain = " -> ".join((*(item.substrate_id for item in pools), pool.substrate_id))
                    raise UserTablesAssemblyError(
                        f"The stated products form a cycle in the enzyme network that starts from "
                        f"{entry.substrate_id!r} ({chain}; the product of {current.substrate_id!r} is stated by "
                        f"{origin}). A network's pools are released one into the next and FungMod does not break a "
                        "cycle; state another product for one of these substrates."
                    )
                pools.append(pool)
            self.networks.append(_NetworkDraft(entry=entry, pools=pools, products=products))

    def _stated_product(self, target: _Target) -> tuple[str, str] | None:
        """The product a substrate's row will state, and where it is stated; None when no source states one."""

        if target.user_row is not None:
            assert self.user is not None
            product = target.user_row.get("product", "")
            origin = f"user dataset {self.user.dataset.dataset_id} substrates.csv (substrate {target.substrate_id})"
        elif "product" in target.spec:
            product = _cell(target.spec["product"])
            origin = f"the request (substrates[{target.index}]['product'])"
        elif target.record is not None and len(target.record.products) == 1:
            product = target.record.products[0]
            origin = f"registry substrate record {target.record.record_id}"
        else:
            return None
        if not product or product.startswith(REVIEW_MARKER):
            return None
        return product, origin

    def _pool_for_product(self, current: _Target, product: str, origin: str) -> _Target | None:
        """The pool a stated product releases (an existing target or a new intermediate); None: a final product."""

        where = f"The product {product!r} of {current.substrate_id!r} (stated by {origin})"
        ambiguous = [
            item.substrate_id for item in self.targets if item.registry_id == product and item.substrate_id != product
        ]
        if self.user is not None:
            for _line, row in self.user.table("substrates.csv"):
                reference = row.get("registry_substrate", "")
                if (
                    reference
                    and row.get("substrate_id") != product
                    and self.resolver.resolve_substrate(reference).record_id == product
                ):
                    ambiguous.append(row["substrate_id"])
        if ambiguous:
            other = sorted(set(ambiguous))[0]
            raise UserTablesAssemblyError(
                f"{where} is the registry substrate of {other!r} but not its substrate_id. An enzyme network links a "
                "product to a pool only when it equals a substrate_id, and FungMod does not guess which was meant: "
                f"state the product as {other!r} to release that pool, or give it another name to keep it the "
                "network's final product."
            )
        existing = next((item for item in self.targets if item.substrate_id == product), None)
        if existing is not None:
            return existing
        if self.user is not None:
            row = next(
                (row for _line, row in self.user.table("substrates.csv") if row.get("substrate_id") == product), None
            )
            if row is not None:
                reference = row.get("registry_substrate", "")
                state = (
                    self.base.get_substrate(self.resolver.resolve_substrate(reference).record_id).physical_state
                    if reference
                    else row.get("physical_state", "")
                )
                self._refuse_solid_pool(where, f"substrate {product!r} of the user dataset", state)
                pool = self._user_target(len(self.targets), product, dict(row))
                return self._add_pool(pool, current, origin)
        if product in self.base.substrates:
            record = self.base.get_substrate(product)
            self._refuse_solid_pool(where, f"registry substrate {product!r}", record.physical_state)
            pool = _Target(
                index=len(self.targets),
                input=product,
                substrate_id=record.record_id,
                registry_id=record.record_id,
                name=record.name,
                substrate_class=record.substrate_class,
                bond_classes=tuple(record.bond_classes),
                resolved_as="registry",
                spec={"substrate": product},
                record=record,
            )
            return self._add_pool(pool, current, origin)
        try:
            named = self.resolver.resolve_substrate(product).record_id
        except ResolutionError:
            named = ""
        if named:
            self.decisions.append(
                f"{where} names registry substrate `{named}` by its name or alias, not by its ID; an enzyme network "
                f"links a product to a pool only when it equals a substrate_id, so {product!r} stays the final product "
                f"of the network. State `{named}` as the product to release that pool."
            )
        return None

    def _refuse_solid_pool(self, where: str, what: str, state: str) -> None:
        if state != "dissolved":
            raise UserTablesAssemblyError(
                f"{where} is {what} with physical state {state!r}. Assembled drafts cover dissolved substrates "
                "only, so the enzyme network cannot hold it as a pool; state another product (in the request, or in "
                "the user dataset's substrates.csv) to keep it the network's final product, or load a dataset that "
                "holds it with load_user_dataset directly."
            )

    def _add_pool(self, pool: _Target, current: _Target, origin: str) -> _Target:
        pool.network_role = "intermediate"
        pool.released_by = current.substrate_id
        self.targets.append(pool)
        self.decisions.append(
            f"Enzyme network: {current.substrate_id} releases `{pool.substrate_id}` ({pool.name}), stated by {origin}; "
            f"`{pool.substrate_id}` is added to the draft as an intermediate pool, which starts at zero."
        )
        return pool

    def _refuse_network_laws(self, responses: Sequence[Mapping[str, Any]] | None) -> None:
        """Response laws are not combined with an enzyme network (USERDATA-010)."""

        if responses is not None:
            raise UserTablesAssemblyError(
                "responses binds temperature or pH laws per enzyme class and substrate of a single-class case; "
                "responses.csv is not combined with enzyme_network in this version, so a network draft cannot carry "
                "them. Assemble without network to use the laws."
            )
        if self.user is None:
            return
        pools = {target.substrate_id for target in self.targets if target.user_row is not None}
        lines = [
            line
            for line, row in self.user.table("responses.csv")
            if row.get("strain_id") == self.user_strain_id and row.get("substrate_id") in pools
        ]
        if lines:
            raise UserTablesAssemblyError(
                f"User dataset {self.user.dataset.dataset_id!r} binds response laws to {self.strain_id!r} on "
                f"substrates of this network (responses.csv {_rows_label(lines)}); responses.csv is not combined with "
                "enzyme_network in this version, so a network draft would drop them. Assemble without network to keep "
                "the laws."
            )

    # -- the enzyme repertoire ----------------------------------------------

    def collect_classes(
        self,
        *,
        annotation: str | Path | None,
        annotation_tool: str | None,
        annotation_source: str | None,
        asserted: Sequence[str | Mapping[str, str]] | None,
        proteome: UniprotSnapshot | str | Path | None = None,
        proteome_selection: str | None = None,
    ) -> None:
        annotated = annotation is not None or annotation_tool is not None or annotation_source is not None
        if proteome is not None and annotated:
            raise UserTablesAssemblyError(
                "annotation and proteome both give the fungus's annotation, and genomes.csv holds one annotation per "
                "strain; give annotation (with annotation_tool) or proteome, not both."
            )
        if proteome is None and proteome_selection is not None:
            raise UserTablesAssemblyError("proteome_selection states how proteome was chosen; give it with proteome.")
        if self.user is not None:
            self._user_classes()
        self._asserted_classes(asserted)
        if self.fungus_record is not None:
            self._registry_record_classes(self.fungus_record)
        if annotated:
            self._annotation_classes(annotation, annotation_tool, annotation_source)
        if proteome is not None:
            self._proteome_snapshot_classes(proteome, proteome_selection)
        if not self.classes:
            raise UserTablesAssemblyError(
                f"No enzyme class has evidence for {self.strain_name!r}: give a genome annotation, enzyme_classes you "
                "assert, a registry fungus, or a user dataset that declares its classes. FungMod never takes a "
                "repertoire from a name."
            )

    def _class_from_registry(self, record_id: str) -> _Class:
        existing = self.classes.get(record_id)
        if existing is not None:
            return existing
        record = self.base.get_enzyme_class(record_id)
        item = _Class(
            key=record.record_id,
            origin="registry",
            name=record.name,
            target_bond_classes=tuple(record.target_bond_classes),
            compatible_substrate_classes=tuple(record.compatible_substrate_classes),
        )
        self.classes[record.record_id] = item
        return item

    def _user_class_rows(self) -> dict[str, dict[str, str]]:
        if self.user is None:
            return {}
        return {row["class_id"]: row for _line, row in self.user.table("enzyme_classes.csv")}

    def _class_key(self, text: str) -> str:
        """Resolve a class reference the way the loader does: a user class_id, else a registry class."""

        if text in self._user_class_rows():
            return text
        try:
            return self.resolver.resolve_enzyme_class(text).record_id
        except AmbiguousResolutionError as exc:
            raise UserTablesAssemblyError(f"enzyme class {text!r} is ambiguous in the registry: {exc}") from exc
        except ResolutionError as exc:
            raise UserTablesAssemblyError(
                f"enzyme class {text!r} is neither a registry enzyme class (ID, name, alias or EC number) nor a "
                "class_id of the user dataset's enzyme_classes.csv."
            ) from exc

    def _class_for_key(self, key: str) -> _Class:
        existing = self.classes.get(key)
        if existing is not None:
            return existing
        user_row = self._user_class_rows().get(key)
        if user_row is None:
            return self._class_from_registry(key)
        item = _Class(
            key=key,
            origin="user",
            name=user_row.get("name", key),
            target_bond_classes=_split(user_row.get("target_bond_classes", "")),
            compatible_substrate_classes=_split(user_row.get("compatible_substrate_classes", "")),
            user_class_row=dict(user_row),
        )
        self.classes[key] = item
        return item

    def _user_classes(self) -> None:
        assert self.user is not None
        dataset_id = self.user.dataset.dataset_id
        for line, row in self.user.table("enzymes.csv"):
            if row.get("strain_id") != self.user_strain_id:
                continue
            item = self._class_for_key(self._class_key(row["enzyme_class"]))
            item.evidence.append(
                _Evidence(
                    kind="user_data",
                    evidence=row.get("evidence", ""),
                    source=row.get("source", ""),
                    details={"file": "enzymes.csv", "row": line, "user_dataset": dataset_id},
                )
            )
            if item.row is None:
                item.row = dict(row)
        for resolved in self.user.dataset.genome_resolved_classes:
            if resolved.get("strain_id") != self.user_strain_id:
                continue
            item = self._class_for_key(str(resolved["enzyme_class"]))
            item.evidence.append(
                _Evidence(
                    kind="genome_annotation",
                    evidence=str(resolved.get("evidence", "")),
                    source=str(resolved.get("source", "")),
                    details={
                        "families": list(resolved.get("families", [])),
                        "gene_count": resolved.get("gene_count"),
                        "specificity": resolved.get("specificity"),
                        "file": GENOME_TABLE,
                        "user_dataset": dataset_id,
                    },
                )
            )
        for row_map in self.user.dataset.unmodellable_enzyme_classes:
            if row_map.get("strain_id") == self.user_strain_id:
                self.unmodellable.append(dict(row_map))
        for row_map in self.user.dataset.unmapped_families:
            if row_map.get("strain_id") == self.user_strain_id:
                self.unmapped.append(dict(row_map))
        for line, row in self.user.table(GENOME_TABLE):
            if row.get("strain_id") != self.user_strain_id:
                continue
            self.genome_rows.append(dict(row))
            relative = row.get("annotation_file", "")
            self.annotation_files[relative] = (self.user.directory / relative).read_bytes()
            self.annotation_report = {
                "annotation_file": relative,
                "sha256": hashlib.sha256(self.annotation_files[relative]).hexdigest(),
                "annotation_tool": row.get("annotation_tool", ""),
                "source": row.get("source", ""),
                "from": f"user dataset {dataset_id} {GENOME_TABLE} row {line}",
            }

    def _asserted_classes(self, asserted: Sequence[str | Mapping[str, str]] | None) -> None:
        if asserted is None:
            return
        if isinstance(asserted, (str, Mapping)):
            asserted = [asserted]
        seen: dict[str, int] = {}
        for index, item in enumerate(asserted):
            if isinstance(item, str):
                spec: dict[str, Any] = {"enzyme_class": item}
            elif isinstance(item, Mapping):
                spec = dict(item)
                unknown = sorted(str(key) for key in spec if key not in _CLASS_SPEC_KEYS)
                if unknown:
                    raise UserTablesAssemblyError(
                        f"enzyme_classes[{index}] has unsupported key(s): {', '.join(unknown)}."
                    )
            else:
                raise UserTablesAssemblyError(f"enzyme_classes[{index}] must be a class name or a mapping.")
            text = spec.get("enzyme_class")
            if not isinstance(text, str) or not text.strip():
                raise UserTablesAssemblyError(f"enzyme_classes[{index}] needs a nonblank enzyme_class.")
            for key in ("evidence", "source"):
                value = spec.get(key)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    raise UserTablesAssemblyError(f"enzyme_classes[{index}]['{key}'] must be nonblank text when given.")
            key = self._class_key(text.strip())
            if key in seen:
                raise UserTablesAssemblyError(
                    f"enzyme_classes[{index}] asserts class {key!r} again (enzyme_classes[{seen[key]}])."
                )
            seen[key] = index
            item_class = self._class_for_key(key)
            evidence = str(
                spec.get("evidence") or f"{REVIEW_MARKER} the evidence that {self.strain_name} has {item_class.name}"
            )
            source = str(spec.get("source") or f"{REVIEW_MARKER} where that evidence is recorded")
            item_class.evidence.append(_Evidence(kind="user_assertion", evidence=evidence, source=source))
            if item_class.row is None:
                item_class.row = {
                    "strain_id": self.strain_id,
                    "enzyme_class": key,
                    "evidence": evidence,
                    "source": source,
                }
            else:
                self.decisions.append(
                    f"enzyme_classes[{index}] asserts {key!r}, which the user dataset already declares for "
                    f"{self.strain_id!r}; the dataset's enzymes.csv row is kept and the assertion is reported beside it."
                )

    def _registry_record_classes(self, record: FungusRecord) -> None:
        source_text = str(record.provenance.get("source", "")).strip()
        source = source_text if source_text else f"FungMod registry fungus record {record.record_id}"
        for class_id in record.enzyme_classes:
            if class_id not in self.base.enzyme_classes:
                continue
            item = self._class_from_registry(class_id)
            text = f"enzyme class listed by the FungMod registry fungus record {record.record_id} ({record.name})"
            item.evidence.append(
                _Evidence(kind="registry_record", evidence=text, source=source, details={"record_id": record.record_id})
            )
            if item.row is None:
                item.row = {"strain_id": self.strain_id, "enzyme_class": class_id, "evidence": text, "source": source}

    def _annotation_classes(
        self,
        annotation: str | Path | None,
        annotation_tool: str | None,
        annotation_source: str | None,
    ) -> None:
        if annotation is None or annotation_tool is None:
            raise UserTablesAssemblyError(
                "annotation and annotation_tool are given together (a dbCAN overview.txt and dbCAN with its version)."
            )
        if self.genome_rows:
            raise UserTablesAssemblyError(
                f"The user dataset already has a genome annotation for {self.strain_id!r} in {GENOME_TABLE}; a strain "
                "has one annotation. Pass annotation=None or edit the dataset."
            )
        if annotation_source is not None and (not isinstance(annotation_source, str) or not annotation_source.strip()):
            raise UserTablesAssemblyError("annotation_source must be nonblank text when given.")
        path = Path(annotation)
        uniprot = _names_uniprot({"annotation_tool": str(annotation_tool)})
        if not path.is_file():
            expected = "a UniProtKB TSV export" if uniprot else "a dbCAN overview.txt"
            raise UserTablesAssemblyError(f"annotation {str(path)!r} is not a file; give {expected}.")
        data = path.read_bytes()
        relative = f"{_ANNOTATION_DIRECTORY}/{path.name}"
        if uniprot:
            source = (
                annotation_source.strip()
                if annotation_source
                else f"{REVIEW_MARKER} the UniProt proteome that was exported, ideally with its UP identifier"
            )
            self._proteome_classes(
                data,
                relative=relative,
                tool_text=str(annotation_tool).strip(),
                source=source,
                origin=f"annotation {path.name}",
            )
            return
        context = _Context(base=self.base, issues=[])
        # The genome route's own checks, with its messages: the tool and version, then the overview format.
        tool = _genome_tool(
            {"annotation_tool": str(annotation_tool).strip()}, file=GENOME_TABLE, line=2, context=context
        )
        overview = _read_overview(data, relative, file=GENOME_TABLE, line=2, context=context)
        if context.issues or tool is None or overview is None:
            raise UserTablesAssemblyError("; ".join(str(issue["message"]) for issue in context.issues))
        family_genes = overview.family_genes()
        source = (
            annotation_source.strip()
            if annotation_source
            else f"{REVIEW_MARKER} the genome or proteome that was annotated, ideally with its accession and the run"
        )
        try:
            resolution = CapabilityResolver(
                family_map=CazymeFamilyMap.load(),
                registry_enzyme_classes=tuple(sorted(self.base.enzyme_classes)),
            ).resolve(
                CazymeAnnotation(
                    organism=self.strain_name,
                    families=tuple(family_genes),
                    genome_accession=source,
                    annotation_tool=tool[0],
                    annotation_tool_version=tool[1],
                    annotation_date="not recorded when assembling",
                )
            )
        except (CapabilityResolutionError, ProvenanceError) as exc:
            raise UserTablesAssemblyError(f"The annotation could not be resolved: {exc}") from exc
        self.annotation_files[relative] = data
        self.genome_rows.append(
            {
                "strain_id": self.strain_id,
                "annotation_file": relative,
                "annotation_tool": str(annotation_tool).strip(),
                "source": source,
                "min_tools_agreeing": "",
            }
        )
        self.annotation_report = {
            "annotation_file": relative,
            "sha256": hashlib.sha256(data).hexdigest(),
            "annotation_tool": str(annotation_tool).strip(),
            "source": source,
            "from": f"annotation {path.name}",
            "consensus_rule": "a family counts for a gene when any tool column calls it (min_tools_agreeing blank)",
        }
        gene_order = [gene.gene_id for gene in overview.genes]
        for capability in resolution.capabilities:
            genes = sorted(
                {gene for family in capability.families for gene in family_genes.get(family, ())}, key=gene_order.index
            )
            entry = {
                "enzyme_class": capability.enzyme_class,
                "families": list(capability.families),
                "gene_count": len(genes),
                "specificity": capability.specificity,
            }
            if not capability.modellable:
                self.unmodellable.append(
                    {
                        **entry,
                        "reason": "no enzyme-class record in the registry; FungMod does not create one from a genome "
                        "annotation, so no case is assembled for it",
                    }
                )
                continue
            item = self._class_from_registry(capability.enzyme_class)
            noun = "gene" if len(genes) == 1 else "genes"
            item.evidence.append(
                _Evidence(
                    kind="genome_annotation",
                    evidence=(
                        f"genome annotation ({tool[0]}, {len(genes)} {noun}, families {', '.join(capability.families)}; "
                        f"{capability.specificity})"
                    ),
                    source=source,
                    details={**entry, "gene_ids": genes, "file": GENOME_TABLE},
                )
            )
        for family in resolution.unmapped_families:
            self.unmapped.append(
                {
                    "family": family,
                    "gene_count": len(family_genes.get(family, ())),
                    "reason": "the curated CAZy family map assigns no enzyme class to this family",
                }
            )

    def _proteome_snapshot_classes(self, proteome: UniprotSnapshot | str | Path, selection: str | None) -> None:
        """Read a frozen UniProt proteome snapshot (digest verified) as the fungus's proteome export."""

        if selection is not None and (not isinstance(selection, str) or not selection.strip()):
            raise UserTablesAssemblyError("proteome_selection must be nonblank text when given.")
        if isinstance(proteome, UniprotSnapshot):
            directory: str | Path = proteome.directory
        elif isinstance(proteome, (str, Path)):
            directory = proteome
        else:
            raise UserTablesAssemblyError(
                "proteome must be a UniprotSnapshot or the directory of a frozen UniProt proteome snapshot."
            )
        try:
            snapshot = load_proteome_snapshot(directory)
        except UniprotFetchError as exc:
            raise UserTablesAssemblyError(f"The UniProt proteome snapshot cannot be used: {exc}") from exc
        relative = f"{_ANNOTATION_DIRECTORY}/{query_key(snapshot.query)}.tsv"
        row = snapshot.genomes_row(strain_id=self.strain_id, annotation_file=relative)
        self._proteome_classes(
            snapshot.read_bytes(),
            relative=relative,
            tool_text=row["annotation_tool"],
            source=row["source"],
            origin=f"UniProt proteome snapshot {snapshot.directory}",
            extra={
                "snapshot": {
                    "directory": str(snapshot.directory),
                    "query": snapshot.query,
                    "url": snapshot.url,
                    "retrieved_at": snapshot.retrieved_at,
                    "uniprot_release": snapshot.uniprot_release,
                    "sha256": snapshot.sha256,
                },
                "selection": selection.strip() if selection else None,
            },
        )

    def _proteome_classes(
        self,
        data: bytes,
        *,
        relative: str,
        tool_text: str,
        source: str,
        origin: str,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Resolve a UniProtKB TSV export with the genomes.csv UniProt route's checks and resolver."""

        if self.genome_rows:
            raise UserTablesAssemblyError(
                f"The user dataset already has a genome annotation for {self.strain_id!r} in {GENOME_TABLE}; a strain "
                "has one annotation. Pass no proteome or annotation, or edit the dataset."
            )
        context = _Context(base=self.base, issues=[])
        tool = _genome_tool({"annotation_tool": tool_text}, file=GENOME_TABLE, line=2, context=context)
        if context.issues or tool is None:
            raise UserTablesAssemblyError("; ".join(str(issue["message"]) for issue in context.issues))
        identifiers = sorted(set(_UNIPROT_PROTEOME_ID.findall(source)))
        if len(identifiers) > 1:
            raise UserTablesAssemblyError(
                f"The source of the UniProt export names several proteome identifiers ({', '.join(identifiers)}); "
                "one genomes.csv row reads one proteome, so name only the one exported."
            )
        proteome_id = identifiers[0] if identifiers else None
        label = f"Annotation file {relative!r}"
        try:
            proteome = parse_uniprot_tsv(decode_uniprot_tsv(data, source=label), source=label)
            resolution = resolve_uniprot_proteome(
                proteome,
                capability_resolver=CapabilityResolver(
                    family_map=CazymeFamilyMap.load(),
                    registry_enzyme_classes=tuple(sorted(self.base.enzyme_classes)),
                ),
                registry=self.base,
                organism=self.strain_name,
                proteome_source=source,
                annotation_tool=tool[0],
                annotation_tool_version=tool[1],
                annotation_date="not recorded when assembling",
            )
        except (CapabilityResolutionError, ProvenanceError) as exc:
            raise UserTablesAssemblyError(f"The UniProt export could not be resolved: {exc}") from exc
        self.annotation_files[relative] = data
        self.genome_rows.append(
            {
                "strain_id": self.strain_id,
                "annotation_file": relative,
                "annotation_tool": tool_text,
                "source": source,
                "min_tools_agreeing": "",
            }
        )
        resolved = resolution.to_dict()
        self.annotation_report = {
            "annotation_file": relative,
            "sha256": hashlib.sha256(data).hexdigest(),
            "annotation_tool": tool_text,
            "source": source,
            "from": origin,
            "source_type": UNIPROT_SOURCE_TYPE,
            "proteome_id": proteome_id,
            "organism": proteome.organism or None,
            "organism_id": proteome.organism_id or None,
            "entry_rows": len(proteome.entries),
            "protein_counts": resolved["protein_counts"],
            "unresolved_ec_numbers": resolved["unresolved_ec_numbers"],
            "partial_ec_numbers": resolved["partial_ec_numbers"],
            "ec_cazy_disagreements": resolved["ec_cazy_disagreements"],
            "comparison_rule": resolved["comparison_rule"],
            **dict(extra or {}),
        }
        named = f"UniProt proteome {proteome_id}" if proteome_id else f"UniProt export {relative}"
        for support in resolution.capabilities:
            count = len(support.accessions)
            entry: dict[str, Any] = {
                "enzyme_class": support.enzyme_class,
                "families": list(support.families),
                "ec_numbers": list(support.ec_numbers),
                "accession_count": count,
                "specificity": support.specificity,
            }
            if not support.modellable:
                self.unmodellable.append(
                    {
                        **entry,
                        "accessions": list(support.accessions),
                        "reason": "no enzyme-class record in the registry; FungMod does not create one from a "
                        "proteome export, so no case is assembled for it",
                    }
                )
                continue
            parts = [f"{count} {'protein' if count == 1 else 'proteins'}"]
            if support.families:
                parts.append(f"CAZy families {', '.join(support.families)}")
            if support.ec_numbers:
                parts.append(f"EC {', '.join(support.ec_numbers)}")
            self._class_from_registry(support.enzyme_class).evidence.append(
                _Evidence(
                    kind="proteome_annotation",
                    evidence=f"{named} ({', '.join(parts)})",
                    source=source,
                    details={
                        **entry,
                        "accessions": list(support.accessions),
                        "accessions_by_basis": {
                            basis: list(items) for basis, items in support.accessions_by_basis.items()
                        },
                        "reviewed_accessions": list(support.reviewed_accessions),
                        "file": GENOME_TABLE,
                    },
                )
            )
        for family, accessions in resolution.unmapped_families.items():
            self.unmapped.append(
                {
                    "family": family,
                    "accession_count": len(accessions),
                    "accessions": list(accessions),
                    "reason": "the curated CAZy family map assigns no enzyme class to this family",
                }
            )

    # -- SABIO-RK entries ----------------------------------------------------

    def collect_entries(
        self,
        sources: Sequence[RegistryProposal | str | Path],
        *,
        entry_ids: Sequence[str] | None,
        same_species: Sequence[str],
    ) -> None:
        if isinstance(same_species, str):
            raise UserTablesAssemblyError("same_species must be a sequence of organism names, not one string.")
        mapped = [str(name).strip() for name in same_species]
        if any(not name for name in mapped):
            raise UserTablesAssemblyError("same_species names must be nonblank.")
        wanted: list[str] | None = None
        if entry_ids is not None:
            if isinstance(entry_ids, str):
                raise UserTablesAssemblyError(
                    "entry_ids must be a sequence of EntryIDs such as ['35622'], not one string."
                )
            wanted = [str(value).strip() for value in entry_ids]
            bad = [value for value in wanted if not _DECIMAL_ID.fullmatch(value)]
            if bad:
                raise UserTablesAssemblyError(f"entry_ids must be positive decimal SABIO-RK EntryIDs; got {bad}.")
            if not sources:
                raise UserTablesAssemblyError("entry_ids select SABIO-RK entries, but no kinetics source is given.")
        if mapped and not sources:
            raise UserTablesAssemblyError("same_species maps SABIO-RK organisms, but no kinetics source is given.")
        seen: dict[str, tuple[int, Mapping[str, Any]]] = {}
        selected: list[tuple[int, RegistryProposal | str | Path, Any]] = []
        for index, source in enumerate(sources):
            try:
                loaded = _load_entries(source, cache_dir=self.cache_dir)
            except UserTablesSourceError as exc:
                raise UserTablesAssemblyError(f"kinetics_sources[{index}]: {exc}") from exc
            self.sources.append(
                {
                    "index": index,
                    "kind": "sabiork",
                    "description": loaded.description,
                    "snapshots": [
                        {"file": snapshot.file_name, "sha256": snapshot.sha256, "query": snapshot.query}
                        for snapshot in loaded.snapshots
                    ],
                    "entries": len(loaded.entries),
                }
            )
            for entry in loaded.entries:
                earlier = seen.get(entry.entry_id)
                if earlier is not None:
                    if dict(earlier[1]) != dict(entry.raw):
                        raise UserTablesAssemblyError(
                            f"EntryID {entry.entry_id} appears in kinetics_sources[{earlier[0]}] and "
                            f"kinetics_sources[{index}] with different content; FungMod does not choose between them."
                        )
                    continue
                seen[entry.entry_id] = (index, entry.raw)
                selected.append((index, source, entry))
        if wanted is not None:
            missing = [value for value in dict.fromkeys(wanted) if value not in seen]
            if missing:
                raise UserTablesAssemblyError(
                    f"EntryID(s) {', '.join(missing)} are not in the kinetics sources; they hold "
                    f"{', '.join(seen) or 'no entries'}."
                )
        organisms = {_norm(entry.record.organism) for _index, _source, entry in selected}
        unused = [name for name in mapped if _norm(name) not in organisms]
        if unused:
            raise UserTablesAssemblyError(
                f"same_species names organism(s) {', '.join(repr(name) for name in unused)} that no SABIO-RK entry has; "
                f"the entries name {', '.join(sorted({entry.record.organism for _i, _s, entry in selected})) or 'no organism'}."
            )
        self.species.extend(mapped)
        species = {_norm(name) for name in self.species}
        for index, source, entry in selected:
            raw_enzyme = entry.raw.get("enzyme_description")
            host = str(raw_enzyme.get("expressed_in") or "").strip() if isinstance(raw_enzyme, Mapping) else ""
            record = entry.record
            info = _EntryInfo(
                entry_id=entry.entry_id,
                organism=record.organism.strip(),
                host=host,
                enzyme=f"{record.enzyme_name} (EC {record.ec_number})" if record.ec_number else record.enzyme_name,
                source_label=f"kinetics_sources[{index}]",
            )
            self.entries.append(info)
            if wanted is not None and entry.entry_id not in wanted:
                info.use = "not selected"
                info.reason = "not selected by entry_ids"
                continue
            try:
                draft = user_tables_from_sabiork(
                    source,
                    dataset_id=self.dataset_id,
                    entry_ids=[entry.entry_id],
                    design=self.design,
                    registry=self.base,
                    cache_dir=self.cache_dir,
                )
            except UserTablesSourceError as exc:
                info.use = "not convertible"
                info.reason = _entry_reason(str(exc), entry.entry_id)
                continue
            info.draft = draft
            self._entry_candidate(info, draft, same=_norm(info.organism) in species)

    def _entry_candidate(self, info: _EntryInfo, draft: UserTablesDraft, *, same: bool) -> None:
        (enzyme_row,) = draft.enzymes
        (substrate_row,) = draft.substrates
        (condition_row,) = draft.conditions
        info.class_key = enzyme_row["enzyme_class"]
        info.substrate_text = (
            substrate_row.get("registry_substrate") or substrate_row.get("name") or substrate_row["substrate_id"]
        )
        measured = _measured(condition_row["condition_id"], condition_row, user_row=False)
        info.measured = measured
        target = self._target_for_entry(substrate_row)
        info.target = target
        if target is None:
            info.use = "not used"
            info.reason = f"its substrate {info.substrate_text!r} is not a requested substrate"
            return
        if info.class_key not in self.classes:
            info.use = "not used"
            info.reason = (
                f"{self.strain_name} has no evidence for enzyme class {info.class_key!r} (no annotated gene, no user "
                "assertion, no registry record); the class is not added"
            )
            return
        form = _rows_form(draft.kinetics)
        status = STATUS_LITERATURE if same else STATUS_TRANSFERRED
        self.candidates.append(
            _Candidate(
                order=len(self.candidates),
                level=1 if same else 2,
                status=status,
                class_key=info.class_key,
                target=target,
                measured=measured,
                rows=[dict(row) for row in draft.kinetics],
                form=form,
                source_ids=(f"SABIO-RK EntryID {info.entry_id}",),
                label=f"SABIO-RK EntryID {info.entry_id} ({info.organism}"
                + (f", expressed in {info.host}" if info.host else "")
                + ")",
                entry=info,
            )
        )
        info.use = "candidate"

    def _target_for_entry(self, substrate_row: Mapping[str, str]) -> _Target | None:
        registry_id = substrate_row.get("registry_substrate", "")
        for target in self.targets:
            if registry_id:
                if target.registry_id == registry_id:
                    return target
            elif not target.registry_id and (
                _norm(target.name) == _norm(substrate_row.get("name", ""))
                or target.substrate_id == substrate_row.get("substrate_id")
            ):
                return target
        return None

    # -- the user's own kinetics --------------------------------------------

    def collect_user_candidates(self) -> None:
        if self.user is None:
            return
        dataset_id = self.user.dataset.dataset_id
        conditions = {row["condition_id"]: row for _line, row in self.user.table("conditions.csv")}
        groups: dict[tuple[str, str, str], list[tuple[int, dict[str, str]]]] = {}
        for line, row in self.user.table("kinetics.csv"):
            if row.get("strain_id") != self.user_strain_id:
                continue
            key = (self._class_key(row["enzyme_class"]), row["substrate_id"], row["condition_id"])
            groups.setdefault(key, []).append((line, row))
        for (class_key, substrate_id, condition_id), items in groups.items():
            lines = [line for line, _row in items]
            label = f"user dataset {dataset_id} kinetics.csv {_rows_label(lines)}"
            target = next(
                (item for item in self.targets if item.user_row is not None and item.substrate_id == substrate_id), None
            )
            if target is None:
                self.unused_user_rows.append(f"{label}: substrate {substrate_id!r} is not a requested substrate")
                continue
            rows = [row for _line, row in items]
            self.candidates.append(
                _Candidate(
                    order=len(self.candidates),
                    level=0,
                    status=STATUS_USER_DATA,
                    class_key=class_key,
                    target=target,
                    measured=_measured(condition_id, conditions[condition_id], user_row=True),
                    rows=[dict(row) for row in rows],
                    form=_rows_form(rows),
                    source_ids=(label,),
                    label=label,
                )
            )

    # -- response laws -------------------------------------------------------

    def collect_laws(self, responses: Sequence[Mapping[str, Any]] | None) -> None:
        if self.network:
            self._refuse_network_laws(responses)
            return
        if self.user is not None:
            for _line, row in self.user.table("responses.csv"):
                if row.get("strain_id") != self.user_strain_id:
                    continue
                target = next(
                    (
                        item
                        for item in self.targets
                        if item.user_row is not None and item.substrate_id == row["substrate_id"]
                    ),
                    None,
                )
                if target is None:
                    continue
                key = (self._class_key(row["enzyme_class"]), target.substrate_id)
                self.laws.setdefault(key, []).append(dict(row))
                self.law_origin[key] = f"user dataset {self.user.dataset.dataset_id} responses.csv"
        if responses is None:
            return
        if isinstance(responses, Mapping):
            responses = [responses]
        given: dict[tuple[str, str], list[dict[str, str]]] = {}
        for index, item in enumerate(responses):
            if not isinstance(item, Mapping):
                raise UserTablesAssemblyError(f"responses[{index}] must be a mapping of responses.csv columns.")
            unknown = sorted(str(key) for key in item if key not in _RESPONSE_KEYS)
            if unknown:
                raise UserTablesAssemblyError(f"responses[{index}] has unsupported key(s): {', '.join(unknown)}.")
            missing = [key for key in _RESPONSE_REQUIRED if item.get(key) in (None, "")]
            if missing:
                raise UserTablesAssemblyError(f"responses[{index}] needs {', '.join(missing)}.")
            law = str(item["law"])
            if law not in RESPONSE_LAWS:
                raise UserTablesAssemblyError(
                    f"responses[{index}]['law'] {law!r} is not a law user data binds; use one of "
                    f"{', '.join(RESPONSE_LAWS)}."
                )
            class_key = self._class_key(str(item["enzyme_class"]))
            if class_key not in self.classes:
                raise UserTablesAssemblyError(
                    f"responses[{index}] binds a law to enzyme class {class_key!r}, which has no evidence in "
                    f"{self.strain_name}."
                )
            target = self._target_named(str(item["substrate"]))
            if target is None:
                raise UserTablesAssemblyError(
                    f"responses[{index}]['substrate'] {item['substrate']!r} is not a requested substrate."
                )
            if target.determined and not self.classes[class_key].acts_on(target):
                raise UserTablesAssemblyError(
                    f"responses[{index}] binds a law to {class_key!r} on {target.substrate_id!r}, but that class does "
                    "not act on that substrate."
                )
            key = (class_key, target.substrate_id)
            if key in self.laws:
                raise UserTablesAssemblyError(
                    f"responses[{index}] binds a law to {class_key!r} on {target.substrate_id!r}, which the user dataset "
                    "already binds; edit the dataset's responses.csv instead."
                )
            given.setdefault(key, []).append(
                {
                    "strain_id": self.strain_id,
                    "enzyme_class": class_key,
                    "substrate_id": target.substrate_id,
                    "law": law,
                    "parameter": str(item["parameter"]),
                    "value": _cell(item["value"]),
                    "units": str(item["units"]),
                    "evidence_type": str(item["evidence_type"]),
                    "method": _cell(item.get("method", "")),
                    "source": str(item["source"]),
                    "reference_tolerance": _cell(item.get("reference_tolerance", "")),
                    "kinetics_at_reference": _cell(item.get("kinetics_at_reference", "")),
                }
            )
        for key, rows in given.items():
            self.laws[key] = rows
            self.law_origin[key] = "the responses argument"

    def _target_named(self, text: str) -> _Target | None:
        for target in self.targets:
            if text in {target.input, target.substrate_id, target.registry_id} or _norm(text) == _norm(target.name):
                return target
        try:
            registry_id = self.resolver.resolve_substrate(text).record_id
        except ResolutionError:
            return None
        return next((target for target in self.targets if target.registry_id == registry_id), None)

    def _law_conditions(self, class_key: str, target: _Target) -> set[str]:
        return {RESPONSE_LAWS[row["law"]].condition for row in self.laws.get((class_key, target.substrate_id), [])}

    # -- cases ---------------------------------------------------------------

    def build(self) -> AssembledTablesDraft:
        compatibility = self._compatibility()
        if self.network:
            self._check_network_members(compatibility)
        cases = self._cases(compatibility)
        if self.network:
            self._exclude_network_forms(cases)
        self._apply_rate_forms(cases)
        self._apply_law_reference(cases)
        grid = self._apply_condition_rows(cases)
        included = self._included(cases)
        slots = self._condition_slots(cases, included, grid)
        tables = self._tables(cases, included, slots)
        if self.network:
            self._check_written_links(tables, included)
        manifest = self._manifest()
        review_fields = _review_fields(manifest, tables)
        report = self._report(cases, compatibility, slots, grid, included)
        if self.network:
            report = self._with_network_report(report, cases, compatibility, slots, tables)
        converted = tuple(
            dict.fromkeys(candidate.entry.entry_id for candidate in included if candidate.entry is not None)
        )
        not_converted = tuple(
            {"entry_id": info.entry_id, "reason": info.reason or info.use}
            for info in self.entries
            if info.entry_id not in converted
        )
        draft = AssembledTablesDraft(
            dataset_id=self.dataset_id,
            manifest=manifest,
            strains=tables["strains.csv"],
            enzymes=tables["enzymes.csv"],
            enzyme_classes=tables["enzyme_classes.csv"],
            substrates=tables["substrates.csv"],
            conditions=tables["conditions.csv"],
            kinetics=tables["kinetics.csv"],
            review="",
            converted_entry_ids=converted,
            not_converted=not_converted,
            not_converted_parameters=tuple(self.not_converted_parameters),
            review_fields=review_fields,
            decisions=tuple(dict.fromkeys(self.decisions)),
            responses=tables["responses.csv"],
            genomes=tables[GENOME_TABLE],
            annotation_files=MappingProxyType(dict(self.annotation_files)),
            assembly=report,
        )
        return _with_review(draft, self._review_markdown(draft, report))

    def _compatibility(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for target in self.targets:
            entry: dict[str, Any] = {
                "substrate": target.name,
                "substrate_id": target.substrate_id,
                "acting": [],
                "not_acting": [],
                "acting_without_evidence": [],
                "undetermined": "",
            }
            if not target.determined:
                entry["undetermined"] = (
                    f"the substrate class and bond classes of {target.name} are REVIEW fields, so which enzyme classes "
                    "act on it is decided only when the reviewed tables are loaded; no case is listed for it"
                )
                output.append(entry)
                continue
            for item in self.classes.values():
                bonds = item.acts_on(target)
                if bonds:
                    entry["acting"].append({"enzyme_class": item.key, "bond_classes": list(bonds)})
                else:
                    entry["not_acting"].append({"enzyme_class": item.key, "reason": _not_acting_reason(item, target)})
            for key, name, targets, compatible in self._all_known_classes():
                if key in self.classes:
                    continue
                bonds = enzyme_class_acts_on(
                    target_bond_classes=targets,
                    compatible_substrate_classes=compatible,
                    substrate_class=target.substrate_class or "",
                    bond_classes=target.bond_classes or (),
                )
                if not bonds:
                    continue
                unused = [
                    info.entry_id
                    for info in self.entries
                    if info.class_key == key and info.use == "not used" and info.target is target
                ]
                entry["acting_without_evidence"].append(
                    {
                        "enzyme_class": key,
                        "name": name,
                        "bond_classes": list(bonds),
                        "reason": f"no annotated gene and no user assertion for class {key}"
                        + (
                            f", and the registry record {self.fungus_record.record_id} does not list it"
                            if self.fungus_record is not None
                            else ""
                        )
                        + f"; it is not added to {self.strain_name}",
                        "unused_entry_ids": unused,
                    }
                )
            output.append(entry)
        return output

    def _all_known_classes(self) -> list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]:
        known = [
            (
                record.record_id,
                record.name,
                tuple(record.target_bond_classes),
                tuple(record.compatible_substrate_classes),
            )
            for record in self.base.enzyme_classes.values()
        ]
        for key, row in self._user_class_rows().items():
            known.append(
                (
                    key,
                    row.get("name", key),
                    _split(row.get("target_bond_classes", "")),
                    _split(row.get("compatible_substrate_classes", "")),
                )
            )
        return known

    def _cases(self, compatibility: Sequence[Mapping[str, Any]]) -> list[_Case]:
        cases: list[_Case] = []
        for target, entry in zip(self.targets, compatibility, strict=True):
            for acting in entry["acting"]:
                enzyme_class = self.classes[acting["enzyme_class"]]
                pool = [c for c in self.candidates if c.class_key == enzyme_class.key and c.target is target]
                for requested in self.requested:
                    cases.append(self._case(target, enzyme_class, requested, pool))
        return cases

    def _case(self, target: _Target, enzyme_class: _Class, requested: _Requested, pool: Sequence[_Candidate]) -> _Case:
        case = _Case(target=target, enzyme_class=enzyme_class, requested=requested)
        where = f"{enzyme_class.name} on {target.name} at {requested.text}"
        at_condition = [c for c in pool if c.measured.matches(requested)]
        if at_condition:
            level = min(c.level for c in at_condition)
            chosen = [c for c in at_condition if c.level == level]
            case.listed = [c for c in at_condition if c.level != level]
            if len(chosen) == 1:
                case.chosen = chosen[0]
                case.status = chosen[0].status
                case.route = ROUTE_SAME_CONDITION
                case.measured = chosen[0].measured
                case.reason = self._source_reason(chosen[0])
                if case.listed:
                    case.reason += "; not used at this condition (weaker evidence): " + ", ".join(
                        c.label for c in case.listed
                    )
                return case
            case.status = STATUS_CONFLICT
            case.listed = chosen + case.listed
            case.reason = (
                f"{', '.join(c.label for c in chosen)} all give kinetics for {where}; FungMod holds one value per "
                "quantity and case and does not choose between them (select one with entry_ids)"
            )
            return case
        measured_elsewhere = [c for c in pool if c.has_constants and c.measured.single]
        not_single = [c for c in pool if c.has_constants and not c.measured.single]
        note = (
            "; not at a single stated condition: " + ", ".join(f"{c.label} ({c.measured.text})" for c in not_single)
            if not_single
            else ""
        )
        if not measured_elsewhere:
            case.pure_gap = not not_single
            case.listed = list(not_single)
            case.reason = f"no source gives kinetics for {where}{note}"
            return case
        level = min(c.level for c in measured_elsewhere)
        chosen = [c for c in measured_elsewhere if c.level == level]
        covered = self._law_conditions(enzyme_class.key, target)
        if len(chosen) > 1:
            case.listed = chosen + [c for c in pool if c not in chosen]
            elsewhere = ", ".join(f"{c.label} at {c.measured.text}" for c in chosen)
            if covered:
                case.status = STATUS_CONFLICT
                case.reason = (
                    f"no kinetics at {requested.text}; several measured kinetics could be carried here by the response "
                    f"law ({elsewhere}), and FungMod does not choose the reference (select one with entry_ids)"
                )
            else:
                case.reason = (
                    f"no kinetics at {requested.text}; kinetics are stated only at other conditions ({elsewhere}), "
                    "which FungMod does not reuse here without a response law"
                )
            return case
        candidate = chosen[0]
        case.measured = candidate.measured
        case.listed = [candidate]
        needed = _differing(candidate.measured, requested)
        if needed and needed <= covered:
            case.chosen = candidate
            case.status = candidate.status
            case.route = ROUTE_RESPONSE_LAW
            laws = sorted(
                {
                    row["law"]
                    for row in self.laws[(enzyme_class.key, target.substrate_id)]
                    if RESPONSE_LAWS[row["law"]].condition in needed
                }
            )
            case.reason = (
                f"{self._source_reason(candidate)}, stated at {candidate.measured.condition_id} "
                f"({candidate.measured.text}); carried to {requested.text} by {', '.join(laws)} from "
                f"{self.law_origin[(enzyme_class.key, target.substrate_id)]}, which rescales the rate from the law's "
                "reference condition; run it as an EnvironmentGrid condition"
            )
            return case
        missing_laws = " and ".join(sorted(needed - covered))
        case.reason = (
            f"kinetics for {enzyme_class.name} on {target.name} are stated only at {candidate.measured.condition_id} "
            f"({candidate.measured.text}; {candidate.label}); FungMod does not reuse them at {requested.text} without a "
            f"{missing_laws} response law, so this condition is a gap whose measurement requests name "
            f"{candidate.measured.condition_id}{note}"
        )
        return case

    def _source_reason(self, candidate: _Candidate) -> str:
        if candidate.level == 0:
            return f"{candidate.label}, kept unchanged with their evidence types"
        assert candidate.entry is not None
        if candidate.level == 1:
            return (
                f"{candidate.label}: the organism is {self.strain_name}'s species, so the entry is converted as "
                "user_tables_from_sabiork converts it (literature)"
            )
        return (
            f"transferred from {candidate.entry.organism} enzyme, SABIO-RK entry {candidate.entry.entry_id}: a "
            f"cross-organism transfer, written as estimates for {self.strain_name} (exploratory mode only)"
        )

    def _apply_rate_forms(self, cases: Sequence[_Case]) -> None:
        """All cases of one enzyme class and substrate share one rate form; the best-evidence source sets it."""

        by_pair: dict[tuple[str, str], list[_Case]] = {}
        for case in cases:
            by_pair.setdefault((case.enzyme_class.key, case.target.substrate_id), []).append(case)
        for (class_key, substrate_id), group in by_pair.items():
            used = sorted(
                {id(c): c for case in group for c in self._case_candidates(case) if c.form}.values(),
                key=lambda c: (c.level, c.order),
            )
            if not used:
                continue
            form = used[0].form
            for candidate in used:
                if candidate.form == form:
                    continue
                candidate.excluded = (
                    f"{candidate.label} uses the {candidate.form} rate form, while {used[0].label} uses the {form} form; "
                    f"all cases of {class_key} on {substrate_id} share one form, and FungMod never derives one from "
                    "the other"
                )
                if candidate.entry is not None:
                    candidate.entry.use = "not used"
                    candidate.entry.reason = candidate.excluded
            for case in group:
                for candidate in self._case_candidates(case):
                    if candidate.excluded:
                        self._downgrade(case, candidate.excluded, keep_measured=False)

    def _case_candidates(self, case: _Case) -> list[_Candidate]:
        if case.chosen is not None:
            return [case.chosen]
        if case.status == STATUS_GAP and case.measured is not None and len(case.listed) == 1:
            return list(case.listed)
        return []

    def _downgrade(self, case: _Case, reason: str, *, keep_measured: bool) -> None:
        """Turn a case into a gap; with ``keep_measured`` its measured kinetics stay in the draft to be named."""

        case.status = STATUS_GAP
        case.route = ROUTE_NONE
        case.chosen = None
        if not keep_measured:
            case.measured = None
        case.reason = f"{reason}; the case is left as a gap"

    def _apply_law_reference(self, cases: Sequence[_Case]) -> None:
        """A law rescales from one reference condition: the pair's kinetics must sit at exactly one condition."""

        by_pair: dict[tuple[str, str], list[_Case]] = {}
        for case in cases:
            by_pair.setdefault((case.enzyme_class.key, case.target.substrate_id), []).append(case)
        for (class_key, substrate_id), group in by_pair.items():
            law_cases = [case for case in group if case.route == ROUTE_RESPONSE_LAW]
            if not law_cases:
                continue
            measured: list[_Measured] = []
            for case in group:
                for candidate in self._case_candidates(case):
                    if candidate.has_constants and not any(candidate.measured.same_as(item) for item in measured):
                        measured.append(candidate.measured)
            if len(measured) <= 1:
                continue
            where = ", ".join(f"{item.condition_id} ({item.text})" for item in measured)
            for case in law_cases:
                self._downgrade(
                    case,
                    f"the response law of {class_key} on {substrate_id} rescales kinetics from one reference condition, "
                    f"but the draft states them at {where}",
                    keep_measured=True,
                )

    def _apply_condition_rows(self, cases: Sequence[_Case]) -> dict[int, bool]:
        """Decide for each requested condition whether it is a conditions.csv row or an EnvironmentGrid condition.

        A response law rescales kinetics only at EnvironmentGrid conditions, and
        a grid condition reuses a value only when it is stated at exactly one
        condition of the dataset. The loader records a pair's gaps at every
        conditions.csv row where the pair has no kinetics, so a law-carried pair
        is kept only while the draft's rows are exactly its measured condition;
        otherwise its law-carried cases become gaps, until nothing changes.
        """

        while True:
            is_row = self._requested_rows(cases)
            changed = False
            rows = self._row_conditions(cases, is_row)
            by_pair: dict[tuple[str, str], list[_Case]] = {}
            for case in cases:
                if case.route == ROUTE_RESPONSE_LAW:
                    by_pair.setdefault((case.enzyme_class.key, case.target.substrate_id), []).append(case)
            for (class_key, substrate_id), law_cases in by_pair.items():
                measured = law_cases[0].measured
                # A law-carried case always has a single measured condition (both values stated).
                assert measured is not None and measured.kelvin is not None and measured.ph_value is not None
                reference = (measured.kelvin, measured.ph_value)
                others = [(label, values) for label, values in rows if not _same_condition(*values, *reference)]
                if not others:
                    continue
                where = ", ".join(label for label, _values in others)
                for case in law_cases:
                    self._downgrade(
                        case,
                        f"the draft also has conditions.csv rows at {where}, where load_user_dataset records the gaps of "
                        f"{class_key} on {substrate_id}; an EnvironmentGrid condition reuses a value only when it is "
                        f"stated at one condition, so the law cannot carry the kinetics of {measured.condition_id} here",
                        keep_measured=True,
                    )
                changed = True
            if not changed:
                break
        for requested in self.requested:
            if is_row[requested.index]:
                continue
            for case in cases:
                if case.requested is requested and case.pure_gap:
                    case.reason += (
                        f"; the draft has no conditions.csv row for {requested.text} (it is an EnvironmentGrid "
                        "condition for the law-carried cases), so load_user_dataset records this pair's gaps at the "
                        "draft's conditions.csv rows"
                    )
        return is_row

    def _requested_rows(self, cases: Sequence[_Case]) -> dict[int, bool]:
        is_row: dict[int, bool] = {}
        for requested in self.requested:
            here = [case for case in cases if case.requested is requested]
            law = [case for case in here if case.route == ROUTE_RESPONSE_LAW]
            needs_row = [case for case in here if case.route != ROUTE_RESPONSE_LAW and not case.pure_gap]
            is_row[requested.index] = not law or bool(needs_row)
            if law and needs_row:
                names = ", ".join(f"{case.enzyme_class.key} on {case.target.substrate_id}" for case in needs_row)
                for case in law:
                    self._downgrade(
                        case,
                        f"a response law applies only at EnvironmentGrid conditions, and {requested.text} must be a "
                        f"conditions.csv row here because {names} needs it",
                        keep_measured=True,
                    )
        return is_row

    def _row_conditions(
        self, cases: Sequence[_Case], is_row: Mapping[int, bool]
    ) -> list[tuple[str, tuple[float, float]]]:
        """The (label, (kelvin, pH)) of every conditions.csv row the draft will have."""

        rows: list[tuple[str, tuple[float, float]]] = [
            (f"{requested.condition_id} ({requested.text})", (requested.kelvin, requested.ph))
            for requested in self.requested
            if is_row[requested.index]
        ]
        for case in cases:
            for candidate in self._case_candidates(case):
                measured = candidate.measured
                if candidate.excluded or measured.kelvin is None or measured.ph_value is None:
                    continue
                values = (measured.kelvin, measured.ph_value)
                if not any(_same_condition(*values, *existing) for _label, existing in rows):
                    rows.append((f"{measured.condition_id} ({measured.text})", values))
        return rows

    def _included(self, cases: Sequence[_Case]) -> list[_Candidate]:
        included: dict[int, _Candidate] = {}
        for case in cases:
            for candidate in self._case_candidates(case):
                if not candidate.excluded:
                    included.setdefault(id(candidate), candidate)
        ordered = sorted(included.values(), key=lambda c: c.order)
        for candidate in ordered:
            if candidate.entry is not None:
                candidate.entry.use = "converted"
        for case in cases:
            for candidate in case.listed:
                if candidate.entry is not None and candidate.entry.use == "candidate":
                    candidate.entry.use = "listed"
                    candidate.entry.reason = case.reason
        for candidate in self.candidates:
            info = candidate.entry
            if info is None or info.use != "candidate":
                continue
            info.use = "not used"
            if not candidate.measured.single:
                info.reason = (
                    f"stated at {candidate.measured.text}, not at a single condition, so it matches no requested "
                    "condition and cannot be carried by a response law"
                )
            elif any(candidate.measured.matches(requested) for requested in self.requested):
                info.reason = "a source with stronger evidence gives kinetics for this case at its condition"
            else:
                info.reason = (
                    f"stated at {candidate.measured.text}, which is not a requested condition, and no case needs it "
                    "as its measured condition"
                )
        for candidate in ordered:
            if candidate.entry is not None and candidate.entry.draft is not None:
                # The conversion's own decisions, except its strain and condition IDs, which the assembly replaces.
                self.decisions.extend(text for text in candidate.entry.draft.decisions if not text.startswith("`"))
        return ordered

    # -- conditions ----------------------------------------------------------

    def _condition_slots(
        self,
        cases: Sequence[_Case],
        included: Sequence[_Candidate],
        is_row: Mapping[int, bool],
    ) -> list[dict[str, Any]]:
        """conditions.csv rows: requested rows first, then the measured conditions the draft's kinetics need."""

        slots: list[dict[str, Any]] = []
        for requested in self.requested:
            if not is_row[requested.index]:
                continue
            user = next(
                (c.measured for c in included if c.measured.user_row is not None and c.measured.matches(requested)),
                None,
            ) or self._user_condition_matching(requested)
            notes = [requested.notes] if requested.notes else ["Requested condition"]
            for candidate in included:
                if candidate.entry is not None and candidate.measured.matches(requested) and candidate.measured.notes:
                    notes.append(candidate.measured.notes)
            slot: dict[str, Any] = {
                "requested": requested,
                "measured": None,
                "kelvin": requested.kelvin,
                "ph": requested.ph,
                "fixed": user is not None or requested.explicit_id,
                "condition_id": user.condition_id if user is not None else requested.condition_id,
                "row": dict(user.user_row)
                if user is not None and user.user_row is not None
                else {**requested.cells, "condition_id": "", "notes": "; ".join(dict.fromkeys(notes))},
            }
            if user is not None and requested.explicit_id and user.condition_id != requested.condition_id:
                self.decisions.append(
                    f"Requested condition {requested.text} is condition {user.condition_id!r} of the user dataset, whose "
                    f"row is kept unchanged; the requested ID {requested.condition_id!r} is not used."
                )
            slots.append(slot)
        # A user dataset's condition row is kept unchanged with its ID, so it claims a measured condition first.
        for candidate in sorted(included, key=lambda c: (c.measured.user_row is None, c.order)):
            if any(slot["requested"] is not None and candidate.measured.matches(slot["requested"]) for slot in slots):
                continue
            measured = candidate.measured
            existing = next(
                (slot for slot in slots if slot["measured"] is not None and slot["measured"].same_as(measured)), None
            )
            if existing is not None:
                if existing["measured"].user_row is None and measured.user_row is None and measured.notes:
                    current = existing["row"]["notes"]
                    if measured.notes not in current:
                        existing["row"]["notes"] = f"{current}; {measured.notes}" if current else measured.notes
                continue
            note = "Measured condition of the source kinetics; not a requested condition"
            slots.append(
                {
                    "requested": None,
                    "measured": measured,
                    "kelvin": measured.kelvin,
                    "ph": measured.ph_value,
                    "fixed": measured.user_row is not None,
                    "condition_id": measured.condition_id,
                    "row": dict(measured.user_row)
                    if measured.user_row is not None
                    else {
                        "condition_id": "",
                        "temperature": measured.temperature,
                        "temperature_units": measured.temperature_units,
                        "ph": measured.ph,
                        "notes": f"{note}; {measured.notes}" if measured.notes else note,
                    },
                }
            )
        taken: set[str] = set()
        for slot in slots:
            if slot["fixed"]:
                if slot["condition_id"] in taken:
                    raise UserTablesAssemblyError(
                        f"condition_id {slot['condition_id']!r} names two different conditions of this assembly; "
                        "give the requested conditions IDs the user dataset does not use."
                    )
                taken.add(slot["condition_id"])
        for slot in slots:
            if not slot["fixed"]:
                base_id = slot["condition_id"]
                condition_id = base_id
                suffix = 2
                while condition_id in taken:
                    condition_id = f"{base_id}_{suffix}"
                    suffix += 1
                taken.add(condition_id)
                slot["condition_id"] = condition_id
            if not slot["row"].get("condition_id"):
                # A row the assembly writes (not a user dataset's row, which is kept unchanged) takes the slot's ID.
                slot["row"]["condition_id"] = slot["condition_id"]
        return slots

    def _user_condition_matching(self, requested: _Requested) -> _Measured | None:
        if self.user is None:
            return None
        for _line, row in self.user.table("conditions.csv"):
            measured = _measured(row["condition_id"], row, user_row=True)
            if measured.matches(requested):
                return measured
        return None

    def _slot_for(self, slots: Sequence[Mapping[str, Any]], measured: _Measured) -> Mapping[str, Any]:
        for slot in slots:
            requested = slot["requested"]
            if requested is not None and measured.matches(requested):
                return slot
            if slot["measured"] is not None and slot["measured"].same_as(measured):
                return slot
        raise AssertionError(f"no condition row for {measured.condition_id}")

    # -- tables ----------------------------------------------------------------

    def _tables(
        self,
        cases: Sequence[_Case],
        included: Sequence[_Candidate],
        slots: Sequence[Mapping[str, Any]],
    ) -> dict[str, tuple[Mapping[str, str], ...]]:
        enzymes = [dict(item.row) for item in self.classes.values() if item.row is not None]
        user_classes = [dict(item.user_class_row) for item in self.classes.values() if item.user_class_row is not None]
        kinetics: list[dict[str, str]] = []
        if self.network:
            kinetics = self._network_kinetics(cases, included, slots)
        else:
            for candidate in included:
                if candidate.level == 0:
                    kinetics.extend(dict(row) for row in candidate.rows)
                    continue
                kinetics.extend(self._entry_rows(candidate, self._slot_for(slots, candidate.measured)["condition_id"]))
            kinetics.extend(self._design_rows_for_gaps(cases, included, slots))
        substrates = [self._substrate_row(target, included) for target in self.targets]
        responses: list[dict[str, str]] = []
        for target in self.targets:
            for item in self.classes.values():
                responses.extend(dict(row) for row in self.laws.get((item.key, target.substrate_id), []))
        return {
            "strains.csv": (dict(self.strain_row),),
            "enzymes.csv": tuple(enzymes),
            "enzyme_classes.csv": tuple(user_classes),
            "substrates.csv": tuple(substrates),
            "conditions.csv": tuple(dict(slot["row"]) for slot in slots),
            "kinetics.csv": tuple(kinetics),
            "responses.csv": tuple(responses),
            GENOME_TABLE: tuple(dict(row) for row in self.genome_rows),
        }

    def _design_rows_for_gaps(
        self,
        cases: Sequence[_Case],
        included: Sequence[_Candidate],
        slots: Sequence[Mapping[str, Any]],
        skip_initial: bool = False,
    ) -> list[dict[str, str]]:
        """The stated design amounts for cases without kinetics, so their gaps are only the kinetic constants.

        The initial substrate concentration is written for every such case; the
        enzyme concentration only when the pair's rate form is already the kcat
        form, since writing it would otherwise choose the form for the user.
        A network draft (``skip_initial``) writes the initial concentration per
        entry and condition instead (``_network_design_initials``), and never for
        an intermediate pool, which starts at zero.
        """

        forms: dict[tuple[str, str], str] = {}
        for candidate in sorted(included, key=lambda c: (c.level, c.order)):
            if candidate.form:
                forms.setdefault((candidate.class_key, candidate.target.substrate_id), candidate.form)
        rows: list[dict[str, str]] = []
        slot_ids = {slot["requested"].index: slot["condition_id"] for slot in slots if slot["requested"] is not None}
        for case in cases:
            if case.status not in {STATUS_GAP, STATUS_CONFLICT} or case.requested.index not in slot_ids:
                continue
            key = (case.enzyme_class.key, case.target.substrate_id)
            condition_id = slot_ids[case.requested.index]
            written = []
            for quantity in ("substrate_initial_concentration", "enzyme_concentration"):
                value = self.design_values.get(quantity)
                if value is None or (quantity == "enzyme_concentration" and forms.get(key) != _KCAT_FORM):
                    continue
                if skip_initial and quantity == "substrate_initial_concentration":
                    continue
                rows.append(value.row((self.strain_id, key[0], key[1], condition_id)))
                written.append(quantity)
            if written:
                case.design_written = tuple(written)
        return rows

    def _entry_rows(self, candidate: _Candidate, condition_id: str) -> list[dict[str, str]]:
        assert candidate.entry is not None
        info = candidate.entry
        rows: dict[str, dict[str, str]] = {}
        for original in candidate.rows:
            row = {
                **original,
                "strain_id": self.strain_id,
                "enzyme_class": candidate.class_key,
                "substrate_id": candidate.target.substrate_id,
                "condition_id": condition_id,
            }
            if candidate.level == 2 and row["evidence_type"] != _DESIGN:
                transfer = (
                    f"transferred from {info.organism} enzyme, SABIO-RK entry {info.entry_id}"
                    + (f" (expressed in {info.host})" if info.host else "")
                    + f"; an estimate for {self.strain_name}, not a value reported for it"
                )
                row["evidence_type"] = _ESTIMATE
                row["method"] = (
                    f"{transfer}; source method: {original['method']}" if original.get("method") else transfer
                )
            rows[row["quantity"]] = row
        if candidate.form == _KCAT_FORM and "enzyme_concentration" not in self.design_quantities:
            replaced = rows.pop("enzyme_concentration", None)
            if replaced is not None:
                amount = replaced["value"] or f"{replaced['lower']} to {replaced['upper']}"
                self.not_converted_parameters.append(
                    {
                        "entry_id": info.entry_id,
                        "parameter": f"enzyme_concentration ({amount} {replaced['units']})",
                        "parameter_type": "concentration",
                        "value": amount,
                        "units": replaced["units"],
                        "reason": "the assay's enzyme concentration, not the virtual experiment's; it is a REVIEW "
                        "field of kinetics.csv unless design={'enzyme_concentration': ...} states it",
                    }
                )
            rows["enzyme_concentration"] = {
                "strain_id": self.strain_id,
                "enzyme_class": candidate.class_key,
                "substrate_id": candidate.target.substrate_id,
                "condition_id": condition_id,
                "quantity": "enzyme_concentration",
                "value": f"{REVIEW_MARKER} enzyme concentration of {self.classes[candidate.class_key].name} in the "
                f"simulated {candidate.target.name} system (amount per volume), the virtual experiment's own "
                "amount; or pass design={'enzyme_concentration': ...}",
                "lower": "",
                "upper": "",
                "units": f"{REVIEW_MARKER} an amount-per-volume unit such as uM",
                "evidence_type": _DESIGN,
                "method": _DESIGN_METHOD,
                "source": f"{REVIEW_MARKER} where the enzyme concentration of the virtual experiment comes from",
                "sd": "",
            }
        if info.draft is not None:
            self.not_converted_parameters.extend(dict(parameter) for parameter in info.draft.not_converted_parameters)
        return [rows[quantity] for quantity in _QUANTITY_ORDER if quantity in rows]

    def _substrate_row(self, target: _Target, included: Sequence[_Candidate]) -> dict[str, str]:
        if target.user_row is not None:
            return dict(target.user_row)
        proposals = []
        for candidate in included:
            if candidate.target is target and candidate.entry is not None and candidate.entry.draft is not None:
                (row,) = candidate.entry.draft.substrates
                proposals.append(row)
        spec = target.spec
        product = _cell(spec["product"]) if "product" in spec else ""
        product_yield = _cell(spec["product_yield"]) if "product_yield" in spec else ""
        source = _cell(spec["source"]) if "source" in spec else ""
        if proposals and not (product and product_yield):
            products = list(dict.fromkeys(row["product"] for row in proposals))
            yields = list(dict.fromkeys(row["product_yield"] for row in proposals))
            settled = (
                len(products) == 1
                and len(yields) == 1
                and not products[0].startswith(REVIEW_MARKER)
                and not yields[0].startswith(REVIEW_MARKER)
            )
            if settled and not product:
                product, product_yield = products[0], yields[0] if not product_yield else product_yield
                if not source:
                    source = "; ".join(dict.fromkeys(row["source"] for row in proposals))
            elif not settled:
                self.decisions.append(
                    f"Product of {target.name}: the converted SABIO-RK entries give products {products} and yields "
                    f"{yields}; the product and yield are left for review."
                )
        if not product and target.record is not None and len(target.record.products) == 1:
            product = target.record.products[0]
        row = {
            "substrate_id": target.substrate_id,
            "registry_substrate": target.registry_id,
            "name": "" if target.registry_id else target.name,
            "substrate_class": "",
            "physical_state": "",
            "bond_classes": "",
            "product": product
            or f"{REVIEW_MARKER} product of {target.name} (a registry product for a registry substrate)",
            "product_yield": product_yield
            or f"{REVIEW_MARKER} mol of product per mol of {target.name}; no source settles the stoichiometry",
            "yield_basis": _YIELD_BASIS,
            "source": source or f"{REVIEW_MARKER} the reaction or source stating the product and its yield",
        }
        if not target.registry_id:
            row["substrate_class"] = (
                target.substrate_class or f"{REVIEW_MARKER} substrate class of {target.name} (lowercase snake_case)"
            )
            row["physical_state"] = (
                "dissolved"
                if target.spec.get("physical_state") == "dissolved"
                else f"{REVIEW_MARKER} physical state of {target.name}; user data supports dissolved substrates only"
            )
            row["bond_classes"] = (
                ";".join(target.bond_classes)
                if target.bond_classes is not None
                else f"{REVIEW_MARKER} bond classes of {target.name} the enzyme cleaves (semicolon-separated lowercase snake_case)"
            )
        return row

    # -- enzyme network rules (network=True) ---------------------------------

    def _check_network_members(self, compatibility: Sequence[Mapping[str, Any]]) -> None:
        """An entry needs a class acting on it, and a class acts on one pool of a network (the loader's rules)."""

        acting = {entry["substrate_id"]: [item["enzyme_class"] for item in entry["acting"]] for entry in compatibility}
        for network in self.networks:
            entry = network.entry
            if entry.determined and not acting[entry.substrate_id]:
                raise UserTablesAssemblyError(
                    f"No enzyme class of {self.strain_name} acts on {entry.name} ({entry.substrate_id}), so the "
                    "enzyme network that starts from it would have no process, which load_user_dataset refuses. "
                    "Remove it from the substrates, or give the class that acts on it with its evidence."
                )
            for item in self.classes.values():
                on = [pool.substrate_id for pool in network.pools if item.key in acting[pool.substrate_id]]
                if len(on) > 1:
                    raise UserTablesAssemblyError(
                        f"Enzyme class {item.key!r} of {self.strain_name} acts on {len(on)} pools of the enzyme "
                        f"network that starts from {entry.substrate_id!r} ({', '.join(on)}). One enzyme acting on two "
                        "substrates of one system competes for its active site, which independent Michaelis-Menten "
                        "processes do not represent, and FungMod binds no competing-substrate law; load_user_dataset "
                        "refuses it. Assemble the pools in separate drafts, or without network."
                    )

    def _exclude_network_forms(self, cases: Sequence[_Case]) -> None:
        """Kinetics in the pH-ionization form cannot run in a network: their cases become gaps with the reason."""

        for case in cases:
            for candidate in self._case_candidates(case):
                if candidate.excluded or not any(row["quantity"] in PH_IONIZATION_QUANTITIES for row in candidate.rows):
                    continue
                candidate.excluded = (
                    f"{candidate.label} states the pH-ionization rate form, which an enzyme network does not bind in "
                    "this version (its processes are homogeneous Michaelis-Menten laws in the kcat or Vmax form)"
                )
                if candidate.entry is not None:
                    candidate.entry.use = "not used"
                    candidate.entry.reason = candidate.excluded
                elif candidate.excluded not in self.unused_user_rows:
                    self.unused_user_rows.append(candidate.excluded)
        for case in cases:
            for candidate in self._case_candidates(case):
                if candidate.excluded:
                    self._downgrade(case, candidate.excluded, keep_measured=False)

    def _network_kinetics(
        self,
        cases: Sequence[_Case],
        included: Sequence[_Candidate],
        slots: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, str]]:
        """kinetics.csv of a network draft: the included rows with the loader's initial-concentration rules applied."""

        entries = {network.entry.substrate_id for network in self.networks}
        names = {target.substrate_id: target.name for target in self.targets}
        items: list[tuple[dict[str, str], _Candidate]] = []
        for candidate in included:
            if candidate.level == 0:
                rows = [dict(row) for row in candidate.rows]
            else:
                rows = self._entry_rows(candidate, self._slot_for(slots, candidate.measured)["condition_id"])
            for row in rows:
                if row["quantity"] == "substrate_initial_concentration" and row["substrate_id"] not in entries:
                    self._network_dropped(
                        candidate,
                        row,
                        f"{names[row['substrate_id']]} is an intermediate pool of the enzyme network: it is released "
                        "by the network and starts at zero, so it takes no initial concentration (request it as a "
                        "substrate to start a network of its own from it)",
                    )
                    continue
                items.append((row, candidate))
        rows = self._consolidated_entry_initials(items, names)
        rows.extend(self._design_rows_for_gaps(cases, included, slots, skip_initial=True))
        rows.extend(self._network_design_initials(cases, slots, rows))
        return rows

    def _network_design_initials(
        self, cases: Sequence[_Case], slots: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, str]]
    ) -> list[dict[str, str]]:
        """The design initial concentration of each entry at each requested condition where no row states one.

        An entry's initial concentration belongs to the network, not to one
        class, so it is written once, on the first class acting on the entry.
        """

        value = self.design_values.get("substrate_initial_concentration")
        if value is None:
            return []
        stated = {
            (row["substrate_id"], row["condition_id"])
            for row in rows
            if row["quantity"] == "substrate_initial_concentration"
        }
        requested = [slot for slot in slots if slot["requested"] is not None]
        output: list[dict[str, str]] = []
        for network in self.networks:
            entry = network.entry
            acting = [item for item in self.classes.values() if entry.determined and item.acts_on(entry)]
            if not acting:
                continue
            for slot in requested:
                key = (entry.substrate_id, str(slot["condition_id"]))
                if key in stated:
                    continue
                stated.add(key)
                output.append(value.row((self.strain_id, acting[0].key, entry.substrate_id, key[1])))
                for case in cases:
                    if case.enzyme_class is acting[0] and case.target is entry and case.requested is slot["requested"]:
                        case.design_written = (*case.design_written, "substrate_initial_concentration")
        return output

    def _network_dropped(self, candidate: _Candidate, row: Mapping[str, str], reason: str) -> None:
        amount = _row_amount_text(row)
        if candidate.level == 0:
            self.unused_user_rows.append(
                f"{candidate.label}: {row['quantity']} of {row['substrate_id']} at {row['condition_id']} ({amount}) "
                f"is not used: {reason}"
            )
            return
        assert candidate.entry is not None
        self.not_converted_parameters.append(
            {
                "entry_id": candidate.entry.entry_id,
                "parameter": f"{row['quantity']} ({amount})",
                "parameter_type": "concentration",
                "value": row["value"] or f"{row['lower']} to {row['upper']}",
                "units": row["units"],
                "reason": reason,
            }
        )

    def _consolidated_entry_initials(
        self, items: Sequence[tuple[dict[str, str], _Candidate]], names: Mapping[str, str]
    ) -> list[dict[str, str]]:
        """One initial concentration per entry and condition: the user's rows win; disagreeing sources are reviewed.

        The classes of a network act on one entry pool, whose initial
        concentration is one value (the loader refuses rows that disagree).
        Rows of the user dataset are kept and must agree among themselves;
        source rows (SABIO-RK assay concentrations) that disagree with them are
        listed as not converted; source rows that disagree with each other are
        replaced by one ``REVIEW:`` row naming every stated value.
        """

        groups: dict[tuple[str, str], list[int]] = {}
        for index, (row, _candidate) in enumerate(items):
            if row["quantity"] == "substrate_initial_concentration":
                groups.setdefault((row["substrate_id"], row["condition_id"]), []).append(index)
        dropped: set[int] = set()
        replaced: dict[int, dict[str, str]] = {}
        for (substrate_id, condition_id), indices in groups.items():
            if len({_amount_key(items[index][0]) for index in indices}) <= 1:
                continue
            stated = "; ".join(
                f"{_row_amount_text(row)} from {candidate.label} for {row['enzyme_class']}"
                for row, candidate in (items[index] for index in indices)
            )
            user = [index for index in indices if items[index][1].level == 0]
            if user:
                if len({_amount_key(items[index][0]) for index in user}) > 1:
                    raise UserTablesAssemblyError(
                        f"The user dataset states different initial concentrations of {substrate_id!r} at condition "
                        f"{condition_id!r} on the rows of its classes ({stated}). The classes of an enzyme network act "
                        "on one entry pool, whose initial concentration is one value, and FungMod does not choose "
                        "between them; state it identically on every class's row of the dataset, or assemble without "
                        "network."
                    )
                kept = _amount_key(items[user[0]][0])
                for index in indices:
                    row, candidate = items[index]
                    if candidate.level != 0 and _amount_key(row) != kept:
                        dropped.add(index)
                        self._network_dropped(
                            candidate,
                            row,
                            f"the entry pool {substrate_id} of the enzyme network has one initial concentration at "
                            f"{condition_id}, which the user dataset states ({_row_amount_text(items[user[0]][0])}); "
                            "this source's value is not used",
                        )
                continue
            first = items[indices[0]][0]
            for index in indices:
                dropped.add(index)
                self._network_dropped(
                    items[index][1],
                    items[index][0],
                    f"the sources state different initial concentrations of the entry pool {substrate_id} at "
                    f"{condition_id}, which has one; replaced by one REVIEW field of kinetics.csv",
                )
            replaced[indices[0]] = {
                "strain_id": first["strain_id"],
                "enzyme_class": first["enzyme_class"],
                "substrate_id": substrate_id,
                "condition_id": condition_id,
                "quantity": "substrate_initial_concentration",
                "value": f"{REVIEW_MARKER} initial concentration of {names[substrate_id]} in the enzyme network at "
                f"{condition_id}, one value for the pool (the sources state {stated}); or pass "
                "design={'substrate_initial_concentration': ...}",
                "lower": "",
                "upper": "",
                "units": f"{REVIEW_MARKER} an amount-per-volume unit such as mM",
                "evidence_type": _DESIGN,
                "method": _DESIGN_METHOD,
                "source": f"{REVIEW_MARKER} where the initial concentration of the virtual experiment comes from",
                "sd": "",
            }
        output: list[dict[str, str]] = []
        for index, (row, _candidate) in enumerate(items):
            if index in replaced:
                output.append(replaced[index])
            elif index not in dropped:
                output.append(row)
        return output

    def _check_written_links(
        self, tables: Mapping[str, Sequence[Mapping[str, str]]], included: Sequence[_Candidate]
    ) -> None:
        """The written substrates.csv must link exactly the discovered pools, with distinct state names."""

        rows = {row["substrate_id"]: row for row in tables["substrates.csv"]}
        registry_of = {
            row["registry_substrate"]: row["substrate_id"] for row in rows.values() if row["registry_substrate"]
        }
        kcat_classes = {
            candidate.class_key for candidate in included if candidate.form == _KCAT_FORM and not candidate.excluded
        }
        for network in self.networks:
            expected = [pool.substrate_id for pool in network.pools]
            chain = [network.entry.substrate_id]
            product = rows[chain[-1]]["product"]
            while product in rows and product not in chain:
                chain.append(product)
                product = rows[chain[-1]]["product"]
            if chain != expected or product in chain:
                common = next(
                    (index for index, (a, b) in enumerate(zip(chain, expected, strict=False)) if a != b),
                    min(len(chain), len(expected)),
                )
                stated = rows[chain[common - 1]]
                raise UserTablesAssemblyError(
                    "The drafted substrates.csv links the enzyme network that starts from "
                    f"{network.entry.substrate_id!r} as {' -> '.join((*chain, product))}, while the stated products "
                    f"link {' -> '.join(expected)}: the "
                    f"product of {stated['substrate_id']!r} comes from {stated['source'] or 'a converted source'}. "
                    "FungMod does not choose between them; state the product of that substrate in the request "
                    "(substrates=[{'substrate': ..., 'product': ...}])."
                )
            for pool in chain:
                released = rows[pool]["product"]
                other = registry_of.get(released)
                if other is not None and other != released:
                    raise UserTablesAssemblyError(
                        f"The product {released!r} of {pool!r} in the enzyme network that starts from "
                        f"{network.entry.substrate_id!r} is the registry substrate of {other!r} but not its "
                        "substrate_id, an ambiguity load_user_dataset refuses. State the product as "
                        f"{other!r} to release that pool, or give it another name."
                    )
            names: dict[str, str] = {}
            states = [
                (f"pool {pool.substrate_id}", f"{pool.registry_id or pool.substrate_id}_concentration")
                for pool in network.pools
            ]
            if not product.startswith(REVIEW_MARKER):
                states.append(("the final product", f"{product}_concentration"))
            for pool in network.pools:
                for item in self.classes.values():
                    if item.key in kcat_classes and pool.determined and item.acts_on(pool):
                        states.append((f"the enzyme of {item.key}", f"{item.key}_concentration"))
            for role, state in states:
                if state in names and names[state] != role:
                    raise UserTablesAssemblyError(
                        f"The enzyme network that starts from {network.entry.substrate_id!r} would give the state "
                        f"{state!r} to both {names[state]} and {role}, which load_user_dataset refuses; rename a "
                        "substrate, product or enzyme class."
                    )
                names[state] = role

    def _with_network_report(
        self,
        report: Mapping[str, Any],
        cases: Sequence[_Case],
        compatibility: Sequence[Mapping[str, Any]],
        slots: Sequence[Mapping[str, Any]],
        tables: Mapping[str, Sequence[Mapping[str, str]]],
    ) -> dict[str, Any]:
        """The report of a network draft: substrates with their network role, the network section, more limitations."""

        output = dict(report)
        roles = {target.substrate_id: target for target in self.targets}
        output["substrates"] = [
            {
                **item,
                "network_role": roles[item["substrate_id"]].network_role,
                "released_by": roles[item["substrate_id"]].released_by or None,
            }
            for item in report["substrates"]
        ]
        output["network"] = self._network_report(cases, compatibility, slots, tables)
        output["limitations"] = [*report["limitations"], *_NETWORK_LIMITATIONS]
        return output

    def _network_report(
        self,
        cases: Sequence[_Case],
        compatibility: Sequence[Mapping[str, Any]],
        slots: Sequence[Mapping[str, Any]],
        tables: Mapping[str, Sequence[Mapping[str, str]]],
    ) -> dict[str, Any]:
        rows = {row["substrate_id"]: row for row in tables["substrates.csv"]}
        by_pool = {entry["substrate_id"]: entry for entry in compatibility}
        slot_ids = {slot["requested"].index: slot["condition_id"] for slot in slots if slot["requested"] is not None}
        conditions = [slot_ids[requested.index] for requested in self.requested]
        initials: dict[tuple[str, str], str] = {}
        for row in tables["kinetics.csv"]:
            if row["quantity"] == "substrate_initial_concentration":
                key = (row["substrate_id"], row["condition_id"])
                if initials.get(key) != "stated":
                    initials[key] = "review field" if row["value"].startswith(REVIEW_MARKER) else "stated"
        self.network_initials = set(initials)
        networks: list[dict[str, Any]] = []
        for network in self.networks:
            pools = [pool.substrate_id for pool in network.pools]
            # Where each product was stated when the pools were followed; a product a converted kinetics source
            # gave instead (or a REVIEW field) has none, and its substrates.csv source cell says where it comes from.
            stated_by = {
                substrate_id: origin
                for substrate_id, product, origin in network.products
                if rows[substrate_id]["product"] == product
            }
            links = []
            for pool in pools:
                row = rows[pool]
                product = row["product"]
                links.append(
                    {
                        "substrate_id": pool,
                        "product": None if product.startswith(REVIEW_MARKER) else product,
                        "product_yield": (
                            None if row["product_yield"].startswith(REVIEW_MARKER) else row["product_yield"]
                        ),
                        "yield_basis": row["yield_basis"],
                        "releases_pool": product in pools,
                        "stated_by": stated_by.get(pool),
                        "source": None if row["source"].startswith(REVIEW_MARKER) else row["source"],
                    }
                )
            final = links[-1]["product"]
            members: list[dict[str, Any]] = []
            for pool in network.pools:
                for acting in by_pool[pool.substrate_id]["acting"]:
                    class_key = acting["enzyme_class"]
                    statuses = {
                        slot_ids[case.requested.index]: case.status
                        for case in cases
                        if case.enzyme_class.key == class_key and case.target is pool
                    }
                    members.append(
                        {
                            "enzyme_class": class_key,
                            "name": self.classes[class_key].name,
                            "pool": pool.substrate_id,
                            "pool_role": "entry" if pool is network.entry else "intermediate",
                            "kinetics_status": statuses,
                        }
                    )
            undetermined = [pool.substrate_id for pool in network.pools if not pool.determined]
            member_keys = {item["enzyme_class"] for item in members}
            not_members = []
            for item in self.classes.values():
                if item.key in member_keys:
                    continue
                reasons = [
                    f"{entry['substrate_id']}: {reason['reason']}"
                    for entry in (by_pool[pool] for pool in pools)
                    for reason in entry["not_acting"]
                    if reason["enzyme_class"] == item.key
                ]
                not_members.append({"enzyme_class": item.key, "name": item.name, "reasons": reasons})
            verdicts = []
            for condition_id in conditions:
                blocked_by = [
                    f"{item['enzyme_class']} on {item['pool']} ({item['kinetics_status'][condition_id]})"
                    for item in members
                    if item["kinetics_status"].get(condition_id) in {STATUS_GAP, STATUS_CONFLICT}
                ]
                initial = initials.get((network.entry.substrate_id, condition_id), "missing")
                if initial == "missing":
                    blocked_by.append(
                        f"the initial concentration of {network.entry.substrate_id} (no source states it; give "
                        "design={'substrate_initial_concentration': ...} or a kinetics.csv row)"
                    )
                if undetermined:
                    status = NETWORK_UNDETERMINED
                elif blocked_by:
                    status = NETWORK_BLOCKED
                else:
                    status = NETWORK_COMPLETE
                verdicts.append(
                    {
                        "condition": condition_id,
                        "status": status,
                        "initial_concentration": initial,
                        "blocked_by": blocked_by,
                    }
                )
            networks.append(
                {
                    "entry_substrate": network.entry.substrate_id,
                    "pools": pools,
                    "links": links,
                    "final_product": final,
                    "members": members,
                    "not_members": not_members,
                    "undetermined_pools": undetermined,
                    "conditions": verdicts,
                }
            )
        return {
            "manifest_field": NETWORK_MANIFEST_FIELD,
            "entry_substrates": [network.entry.substrate_id for network in self.networks],
            "networks": networks,
            "status_meaning": dict(NETWORK_CONDITION_STATUSES),
        }

    def _manifest(self) -> dict[str, Any]:
        parts = []
        if self.user is not None:
            parts.append(f"user dataset {self.user.dataset.dataset_id} (sha256 {self.user.dataset.digest})")
        if self.annotation_report:
            parts.append(
                f"{self._annotation_label()} {self.annotation_report['annotation_file']} "
                f"(sha256 {self.annotation_report['sha256']})"
            )
            if self.annotation_report.get("selection"):
                parts.append(f"proteome choice: {self.annotation_report['selection']}")
        for source in self.sources:
            snapshots = ", ".join(f"{item['file']} (sha256 {item['sha256']})" for item in source["snapshots"])
            parts.append(f"SABIO-RK {source['description']}: {snapshots}")
        if self.fungus_record is not None:
            parts.append(f"FungMod registry fungus record {self.fungus_record.record_id}")
        substrates = ", ".join(target.name for target in self.targets if target.network_role != "intermediate")
        conditions = "; ".join(requested.text for requested in self.requested)
        simulation: dict[str, Any]
        if self.simulation is not None:
            simulation = dict(self.simulation)
        elif self.user is not None and isinstance(self.user.manifest.get("simulation"), Mapping):
            simulation = dict(self.user.manifest["simulation"])
            self.decisions.append(
                f"The simulation time grid is the user dataset's ({simulation}); pass time_grid to state another."
            )
        else:
            simulation = {
                "duration": f"{REVIEW_MARKER} simulated duration, a positive number (FungMod has no default time grid)",
                "units": f"{REVIEW_MARKER} time unit of the duration, such as minute or hour",
                "points": f"{REVIEW_MARKER} number of output time points, an integer of at least 2",
            }
        manifest: dict[str, Any] = {
            "dataset_id": self.dataset_id,
            "contributor": f"{REVIEW_MARKER} name of the person who reviewed these tables",
            "source": (
                f"Assembled for {self.strain_name} on {substrates} at {conditions}; sources: "
                f"{'; '.join(parts) or 'none beyond the stated enzyme classes'}"
            ),
            "notes": (
                "Drafted by fungal_model.api.user_data_assembly.assemble_user_tables. review.md lists the enzyme "
                "repertoire with its evidence, every case with its kinetics status, sources and reason, and what is "
                "missing. Transferred kinetics are estimates."
            ),
            "simulation": simulation,
        }
        if self.network:
            manifest["notes"] += (
                " enzyme_network makes every case an enzyme network: the member classes act together on the pools "
                "that the stated products link (assemble_user_tables(network=True)); review.md lists the pools, links "
                "and members."
            )
            manifest[NETWORK_MANIFEST_FIELD] = {
                NETWORK_ENTRY_FIELD: [network.entry.substrate_id for network in self.networks]
            }
        return manifest

    def _annotation_label(self) -> str:
        """How the manifest and review.md name the annotation: a UniProt export or a dbCAN annotation."""

        tool = str(self.annotation_report.get("annotation_tool", ""))
        return "UniProt proteome export" if _names_uniprot({"annotation_tool": tool}) else "dbCAN annotation"

    # -- report ----------------------------------------------------------------

    def _report(
        self,
        cases: Sequence[_Case],
        compatibility: Sequence[Mapping[str, Any]],
        slots: Sequence[Mapping[str, Any]],
        is_row: Mapping[int, bool],
        included: Sequence[_Candidate],
    ) -> dict[str, Any]:
        slot_ids = {slot["requested"].index: slot["condition_id"] for slot in slots if slot["requested"] is not None}
        requested_report = []
        for requested in self.requested:
            row = is_row[requested.index]
            requested_report.append(
                {
                    "condition_id": slot_ids.get(requested.index, requested.condition_id),
                    "temperature": requested.temperature,
                    "temperature_units": requested.temperature_units,
                    "ph": requested.ph,
                    "in_conditions_csv": row,
                    "environment_grid": None
                    if row
                    else {"temperature_C": [_rounded(requested.temperature_c)], "ph": [requested.ph]},
                }
            )
        measured_report = [
            {
                "condition_id": slot["condition_id"],
                "condition": slot["measured"].text,
                "reason": "measured condition of kinetics in the draft; not a requested condition",
            }
            for slot in slots
            if slot["requested"] is None
        ]
        case_report = []
        for case in cases:
            condition_id = slot_ids.get(case.requested.index, case.requested.condition_id)
            listed = case.listed if case.chosen is None else [case.chosen]
            case_report.append(
                {
                    "fungus": self.strain_name,
                    "strain_id": self.strain_id,
                    "enzyme_class": case.enzyme_class.key,
                    "enzyme_class_name": case.enzyme_class.name,
                    "substrate": case.target.name,
                    "substrate_id": case.target.substrate_id,
                    "condition": condition_id,
                    "condition_text": case.requested.text,
                    "in_conditions_csv": is_row[case.requested.index],
                    "class_evidence": case.enzyme_class.evidence_texts(),
                    "kinetics_status": case.status,
                    "condition_route": case.route,
                    "measured_condition": None
                    if case.measured is None
                    else {"condition_id": self._slot_id(slots, case.measured), "condition": case.measured.text},
                    "source_ids": [source_id for candidate in listed for source_id in candidate.source_ids],
                    "design_rows": list(case.design_written),
                    "reason": case.reason,
                }
            )
        stored = self._stored_registry_cases()
        return {
            "kind": "fungmod_user_tables_assembly",
            "dataset_id": self.dataset_id,
            "fungus": {
                "input": self.fungus_input,
                "strain_id": self.strain_id,
                "name": self.strain_name,
                "resolved_as": self.fungus_resolved_as,
                "registry_fungus_id": None if self.fungus_record is None else self.fungus_record.record_id,
                "species_for_sabiork": list(dict.fromkeys(self.species)),
            },
            "substrates": [
                {
                    "input": target.input,
                    "substrate_id": target.substrate_id,
                    "registry_substrate": target.registry_id or None,
                    "name": target.name,
                    "resolved_as": target.resolved_as,
                }
                for target in self.targets
            ],
            "requested_conditions": requested_report,
            "measured_conditions": measured_report,
            "enzyme_classes": [
                {
                    "enzyme_class": item.key,
                    "name": item.name,
                    "origin": item.origin,
                    "declared_in": "enzymes.csv" if item.row is not None else GENOME_TABLE,
                    "evidence": [evidence.to_dict() for evidence in item.evidence],
                }
                for item in self.classes.values()
            ],
            "annotation": dict(self.annotation_report) or None,
            "unmodellable_enzyme_classes": [dict(item) for item in self.unmodellable],
            "unmapped_families": [dict(item) for item in self.unmapped],
            "substrate_compatibility": [dict(item) for item in compatibility],
            "cases": case_report,
            "entries": [
                {
                    "entry_id": info.entry_id,
                    "organism": info.organism,
                    "expressed_in": info.host or None,
                    "enzyme": info.enzyme,
                    "enzyme_class": info.class_key or None,
                    "substrate": info.substrate_text or None,
                    "measured_condition": None if info.measured is None else info.measured.text,
                    "source": info.source_label,
                    "use": info.use,
                    "reason": info.reason,
                }
                for info in self.entries
            ],
            "unused_user_rows": list(self.unused_user_rows),
            "stored_registry_cases": stored,
            "sources": [dict(source) for source in self.sources],
            "transferred_entry_ids": [
                candidate.entry.entry_id
                for candidate in included
                if candidate.level == 2 and candidate.entry is not None
            ],
            "limitations": list(_LIMITATIONS),
        }

    def _slot_id(self, slots: Sequence[Mapping[str, Any]], measured: _Measured) -> str:
        for slot in slots:
            requested = slot["requested"]
            if (requested is not None and measured.matches(requested)) or (
                slot["measured"] is not None and slot["measured"].same_as(measured)
            ):
                return str(slot["condition_id"])
        return measured.condition_id

    def _stored_registry_cases(self) -> list[dict[str, Any]]:
        record = self.fungus_record
        if record is None:
            return []
        output: list[dict[str, Any]] = []
        for target in self.targets:
            if target.record is None:
                continue
            substrate = target.record
            for compatibility in self.base.process_compatibility.values():
                if compatibility.enzyme_class not in record.enzyme_classes:
                    continue
                if compatibility.substrate_class != substrate.substrate_class:
                    continue
                if not set(compatibility.required_bond_classes) <= set(substrate.bond_classes):
                    continue
                parameters = [
                    parameter
                    for parameter in self.base.parameters.values()
                    if parameter.fungus_id == record.record_id
                    and parameter.parameter_symbol in compatibility.required_parameters
                    and parameter.substrate_id in (None, substrate.record_id)
                ]
                if not parameters:
                    continue
                environments = sorted({p.environment_id for p in parameters if p.environment_id is not None})
                output.append(
                    {
                        "fungus_id": record.record_id,
                        "enzyme_class": compatibility.enzyme_class,
                        "substrate_id": substrate.record_id,
                        "process_compatibility": compatibility.record_id,
                        "process_type": compatibility.process_type,
                        "case_template": compatibility.case_template_id or None,
                        "parameter_records": sorted(parameter.record_id for parameter in parameters),
                        "environments": environments,
                        "note": (
                            "stored registry case of the fungus; it is not copied into the draft (curated records are "
                            f"not relabelled as user rows) and runs without it: virtual_experiment(fungi="
                            f"'{record.record_id}', substrates='{substrate.record_id}', environments=...)"
                        ),
                    }
                )
        return output

    # -- review.md -------------------------------------------------------------

    def _review_markdown(self, draft: AssembledTablesDraft, report: Mapping[str, Any]) -> str:
        fungus = report["fungus"]
        requested = [target for target in self.targets if target.network_role != "intermediate"]
        lines = [
            f"# Review: {self.strain_name} on {', '.join(t.name for t in requested)} ({self.dataset_id})",
            "",
            "Assembled by `assemble_user_tables` for one fungus, the requested substrates and the requested "
            "conditions. This is a draft: `load_user_dataset` refuses the directory until every field that begins "
            f"with `{REVIEW_MARKER}` is replaced by a reviewed value. Nothing was fetched while assembling.",
            "",
            "## Request",
            "",
            f"- Fungus: {_md(self.fungus_input)} -> strain `{self.strain_id}` ({_md(self.strain_name)}; "
            f"{fungus['resolved_as'].replace('_', ' ')})"
            + (
                f"; species for SABIO-RK matching: {', '.join(fungus['species_for_sabiork'])}"
                if fungus["species_for_sabiork"]
                else "; no species stated"
            ),
            "- Substrates: "
            + "; ".join(
                f"{_md(t.input)} -> `{t.substrate_id}` ({t.resolved_as.replace('_', ' ')}"
                + (f"; network pool released by `{t.released_by}`" if t.network_role == "intermediate" else "")
                + ")"
                for t in self.targets
            ),
            "- Conditions: "
            + "; ".join(
                f"{item['condition_id']} ({requested.text})"
                + ("" if item["in_conditions_csv"] else ", reached through an EnvironmentGrid")
                for item, requested in zip(report["requested_conditions"], self.requested, strict=True)
            ),
        ]
        sources = []
        if self.user is not None:
            sources.append(f"user dataset `{self.user.dataset.dataset_id}` (sha256 `{self.user.dataset.digest}`)")
        if self.annotation_report:
            sources.append(
                f"{self._annotation_label()} `{self.annotation_report['annotation_file']}` "
                f"(sha256 `{self.annotation_report['sha256']}`)"
            )
        for source in self.sources:
            for snapshot in source["snapshots"]:
                sources.append(
                    f"SABIO-RK {source['description']}: `{snapshot['file']}` (sha256 `{snapshot['sha256']}`)"
                )
        if self.fungus_record is not None:
            sources.append(f"registry fungus record `{self.fungus_record.record_id}`")
        lines.append("- Sources: " + ("; ".join(sources) if sources else "the enzyme classes you asserted only"))
        if self.annotation_report.get("selection"):
            lines.append(f"- Proteome choice: {_md(str(self.annotation_report['selection']))}")
        lines.extend(["", "## Fields to fill", ""])
        if draft.review_fields:
            lines.extend(["| File | Row | Column | What to decide |", "| --- | --- | --- | --- |"])
            for item in draft.review_fields:
                row = "" if item["row"] is None else str(item["row"])
                lines.append(
                    f"| {item['file']} | {row} | {item['column']} | {_md(str(item['note'])[len(REVIEW_MARKER) :].strip())} |"
                )
        else:
            lines.append("None.")
        lines.extend(["", f"## Enzyme repertoire of {_md(self.strain_name)}", ""])
        lines.append(
            "Only a genome annotation or proteome export, the classes you assert, the fungus's own rows in a user "
            "dataset or its registry record give a class; a name never does."
        )
        lines.extend(["", "| Enzyme class | Declared in | Evidence |", "| --- | --- | --- |"])
        for item in report["enzyme_classes"]:
            evidence = "; ".join(_evidence_text(entry["evidence"], entry["source"]) for entry in item["evidence"])
            lines.append(f"| {item['enzyme_class']} | {item['declared_in']} | {_md(evidence)} |")
        unresolved = list(self.annotation_report.get("unresolved_ec_numbers") or ())
        disagreements = list(self.annotation_report.get("ec_cazy_disagreements") or ())
        if self.unmodellable or self.unmapped or unresolved or disagreements:
            lines.extend(["", "Not added from the annotation:", ""])
            for item in self.unmodellable:
                lines.append(
                    f"- {item['enzyme_class']} (families {', '.join(item['families'])}, {_count_text(item)}): "
                    f"{_md(str(item['reason']))}"
                )
            for item in self.unmapped:
                lines.append(f"- family {item['family']} ({_count_text(item)}): {_md(str(item['reason']))}")
            for item in unresolved:
                lines.append(
                    f"- EC {item['ec_number']} ({item['accession_count']} protein(s)): {_md(str(item['reason']))}"
                )
            for item in disagreements:
                lines.append(
                    f"- {item['accession']}: CAZy {', '.join(item['cazy_families'])} names "
                    f"{', '.join(item['cazy_classes']) or 'no class'}, EC {', '.join(item['ec_numbers'])} names "
                    f"{', '.join(item['ec_classes']) or 'no class'}; {_md(str(item['outcome']))}"
                )
        lines.extend(["", "## Which classes act on each substrate", ""])
        for entry in report["substrate_compatibility"]:
            lines.append(f"### {_md(entry['substrate'])}")
            lines.append("")
            if entry["undetermined"]:
                lines.extend([f"- {_md(entry['undetermined'])}", ""])
                continue
            acting = ", ".join(
                f"{item['enzyme_class']} (bonds {', '.join(item['bond_classes'])})" for item in entry["acting"]
            )
            lines.append(f"- Classes of the fungus acting on it: {acting or 'none'}.")
            for item in entry["not_acting"]:
                lines.append(f"- Does not act on it: {item['enzyme_class']}: {_md(item['reason'])}.")
            for item in entry["acting_without_evidence"]:
                unused = (
                    f" SABIO-RK entries for it are not used: {', '.join(item['unused_entry_ids'])}."
                    if item["unused_entry_ids"]
                    else ""
                )
                lines.append(
                    f"- Acts on it without evidence in the fungus: {item['enzyme_class']}: {_md(item['reason'])}.{unused}"
                )
            lines.append("")
        if self.network:
            lines.extend(self._network_markdown(report["network"]))
        lines.extend(
            [
                "## Cases",
                "",
                "| Enzyme class | Substrate | Condition | Kinetics status | Route | Sources | Reason |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for case in report["cases"]:
            lines.append(
                f"| {case['enzyme_class']} | {case['substrate_id']} | {case['condition']} ({case['condition_text']}) | "
                f"{case['kinetics_status']} | {case['condition_route']} | {_md(', '.join(case['source_ids']) or '-')} | "
                f"{_md(case['reason'])} |"
            )
        if not report["cases"]:
            lines.append("| - | - | - | - | - | - | No class of the fungus acts on a requested substrate. |")
        transfers = [case for case in report["cases"] if case["kinetics_status"] == STATUS_TRANSFERRED]
        lines.extend(["", "## Transferred kinetics", ""])
        if transfers:
            lines.append(
                "These kinetics were measured on another organism's enzyme. They are written with evidence type "
                "`estimate`, so they run in exploratory mode only, and their method states the transfer. FungMod never "
                f"labels a transferred value as literature or measured for {_md(self.strain_name)}; you can upgrade one "
                "only by editing kinetics.csv yourself (evidence type, method and source) with the evidence that "
                "justifies it."
            )
            lines.append("")
            for case in transfers:
                lines.append(
                    f"- {case['enzyme_class']} on {case['substrate_id']} at {case['condition']}: {_md(case['reason'])}."
                )
        else:
            lines.append("None.")
        gaps = [case for case in report["cases"] if case["kinetics_status"] in {STATUS_GAP, STATUS_CONFLICT}]
        lines.extend(["", "## Gaps and measurement requests", ""])
        if gaps:
            lines.append(
                "No kinetics.csv row is written for these cases. Once the tables are reviewed, `load_user_dataset` "
                "records each missing role as an explicit gap with a measurement request, which preflight reports as "
                "the suggested experiment."
            )
            lines.append("")
            for case in gaps:
                lines.append(f"- {self._request_text(case)}")
        else:
            lines.append("None.")
        grid = [item for item in report["requested_conditions"] if not item["in_conditions_csv"]]
        lines.extend(["", "## Conditions reached through a response law", ""])
        if grid:
            lines.append(
                "These requested conditions are not conditions.csv rows: the loader applies a response law only at "
                "EnvironmentGrid conditions, so run them with `environment_grid(...)` after loading the reviewed tables."
            )
            lines.append("")
            for item in grid:
                lines.append(
                    f"- {item['condition_id']}: environment_grid(temperature_C={item['environment_grid']['temperature_C']}, "
                    f"ph={item['environment_grid']['ph']})"
                )
        else:
            lines.append("None.")
        if report["measured_conditions"]:
            lines.extend(["", "Measured conditions in conditions.csv that were not requested:", ""])
            for item in report["measured_conditions"]:
                lines.append(f"- {item['condition_id']} ({_md(item['condition'])}): {item['reason']}.")
        lines.extend(["", "## SABIO-RK entries", ""])
        examined = [item for item in report["entries"] if item["use"] != "not selected"]
        skipped = [item["entry_id"] for item in report["entries"] if item["use"] == "not selected"]
        if examined:
            lines.extend(
                [
                    "| EntryID | Organism | Enzyme | Class | Condition | Use | Reason |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for item in examined:
                organism = item["organism"] + (
                    f" (expressed in {item['expressed_in']})" if item["expressed_in"] else ""
                )
                lines.append(
                    f"| {item['entry_id']} | {_md(organism)} | {_md(item['enzyme'])} | {item['enzyme_class'] or '-'} | "
                    f"{_md(item['measured_condition'] or '-')} | {item['use']} | {_md(item['reason'] or '-')} |"
                )
        elif not skipped:
            lines.append("No SABIO-RK source was given.")
        if skipped:
            lines.extend(["", f"Not selected by `entry_ids` (not examined): {', '.join(skipped)}."])
        if self.unused_user_rows:
            lines.extend(["", "User-dataset rows not used:", ""])
            lines.extend(f"- {_md(item)}" for item in self.unused_user_rows)
        lines.extend(["", "## Stored registry cases", ""])
        if report["stored_registry_cases"]:
            for item in report["stored_registry_cases"]:
                lines.append(
                    f"- `{item['process_compatibility']}` ({item['process_type']}, template {item['case_template']}): "
                    f"{len(item['parameter_records'])} parameter records; {_md(item['note'])}."
                )
        else:
            lines.append("None.")
        if draft.not_converted_parameters:
            lines.extend(["", "## Parameters not converted", ""])
            lines.extend(["| EntryID | Parameter | Reason |", "| --- | --- | --- |"])
            for item in draft.not_converted_parameters:
                lines.append(f"| {item['entry_id']} | {_md(item['parameter'])} | {_md(item['reason'])} |")
        if draft.decisions:
            lines.extend(["", "## Decisions", ""])
            lines.extend(f"- {_md_text(item)}" for item in draft.decisions)
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {_md_text(item)}" for item in report["limitations"])
        lines.append("")
        return "\n".join(lines)

    def _network_markdown(self, network: Mapping[str, Any]) -> list[str]:
        lines = [
            "## Enzyme network",
            "",
            f"`user_dataset.yml` declares `{NETWORK_MANIFEST_FIELD}` with `{NETWORK_ENTRY_FIELD}` "
            f"{', '.join(f'`{entry}`' for entry in network['entry_substrates'])}: every member class runs its own "
            "Michaelis-Menten process on its pool, classes on one pool add their rates, and a pool released by one "
            "class is the substrate of the next where substrates.csv states that product as another substrate_id "
            "(never matched by name). Intermediate pools and the final product start at zero. A network runs at a "
            "condition only when every member has kinetics there (all or nothing); a member without kinetics is a "
            "gap, never left out.",
            "",
        ]
        for item in network["networks"]:
            lines.extend([f"### From `{item['entry_substrate']}`", ""])
            links = []
            for link in item["links"]:
                product = f"`{link['product']}`" if link["product"] else "a product still under review"
                amount = (
                    f"{link['product_yield']} {link['yield_basis']}" if link["product_yield"] else "yield under review"
                )
                final = "" if link["releases_pool"] else ", final product"
                links.append(f"`{link['substrate_id']}` -> {product} ({amount}{final})")
            lines.append(f"- Pools and links: {'; '.join(links)}.")
            if item["undetermined_pools"]:
                lines.append(
                    f"- Members on {', '.join(item['undetermined_pools'])} are decided when the reviewed tables are "
                    "loaded (substrate class or bond classes under review)."
                )
            headers = " | ".join(str(entry["condition"]) for entry in item["conditions"])
            lines.extend(["", f"| Member class | Pool | {headers} |"])
            lines.append("| --- | --- | " + " | ".join("---" for _ in item["conditions"]) + " |")
            for member in item["members"]:
                statuses = " | ".join(
                    member["kinetics_status"].get(entry["condition"], "-") for entry in item["conditions"]
                )
                lines.append(f"| {member['enzyme_class']} | {member['pool']} ({member['pool_role']}) | {statuses} |")
            if not item["members"]:
                lines.append("| - | - | " + " | ".join("-" for _ in item["conditions"]) + " |")
            lines.append("")
            for entry in item["conditions"]:
                blocked = f": {_md_text('; '.join(entry['blocked_by']))}" if entry["blocked_by"] else ""
                lines.append(
                    f"- {entry['condition']}: {entry['status']} (initial concentration of `{item['entry_substrate']}`: "
                    f"{entry['initial_concentration']}){blocked}."
                )
            if item["not_members"]:
                lines.extend(["", "Classes of the fungus that act on no pool of this network (not members):", ""])
                for member in item["not_members"]:
                    reasons = "; ".join(member["reasons"]) or "the pools are under review"
                    lines.append(f"- {member['enzyme_class']}: {_md_text(reasons)}.")
            lines.append("")
        return lines

    def _request_text(self, case: Mapping[str, Any]) -> str:
        design = case["design_rows"]
        roles = (
            "km and kcat"
            if "enzyme_concentration" in design
            else "km and kcat with the enzyme concentration, or Vmax (or a specific activity and enzyme loading)"
        )
        pool_role = self._pool_role(case["substrate_id"])
        if "substrate_initial_concentration" not in design and (
            not self.network
            or (pool_role == "entry" and (case["substrate_id"], case["condition"]) not in self.network_initials)
        ):
            roles += ", and state the initial substrate concentration"
        measured = case["measured_condition"]
        text = (
            f"{case['enzyme_class']} on {case['substrate_id']} at {case['condition']} ({case['condition_text']}), "
            f"{case['kinetics_status']}: measure {roles} of {case['enzyme_class_name']} from {self.strain_name} on "
            f"{case['substrate']} at {case['condition_text']}"
        )
        if self.network:
            pool = "the entry pool" if pool_role == "entry" else "an intermediate pool, starting at zero,"
            text += (
                f" ({case['substrate_id']} is {pool} of an enzyme network, which runs at this condition only when "
                "every member class has kinetics)"
            )
        if measured is not None:
            text += (
                f"; kinetics are stated only at {measured['condition_id']} ({measured['condition']}), which FungMod "
                "does not reuse at another condition (a temperature or pH law in responses.csv would carry them to an "
                "EnvironmentGrid condition)"
            )
        return _md(f"{text}. Why: {case['reason']}.")

    def _pool_role(self, substrate_id: str) -> str:
        return next((target.network_role for target in self.targets if target.substrate_id == substrate_id), "")


# ---------------------------------------------------------------------------
# Helpers


def _with_review(draft: AssembledTablesDraft, review: str) -> AssembledTablesDraft:
    return replace(draft, review=review)


def _count_text(item: Mapping[str, Any]) -> str:
    """The gene count of a dbCAN entry or the protein count of a UniProt entry."""

    if "gene_count" in item:
        return f"{item['gene_count']} gene(s)"
    return f"{item.get('accession_count', 0)} protein(s)"


def _evidence_text(evidence: str, source: str) -> str:
    def shown(text: str) -> str:
        return "a REVIEW field" if text.startswith(REVIEW_MARKER) else text

    return f"{shown(evidence)} (source: {shown(source)})" if source else shown(evidence)


def _entry_reason(message: str, entry_id: str) -> str:
    prefix = f"EntryID {entry_id}: "
    index = message.find(prefix)
    return message[index + len(prefix) :] if index >= 0 else message


def _rows_form(rows: Sequence[Mapping[str, str]]) -> str:
    quantities = {row["quantity"] for row in rows}
    if quantities & _KCAT_FORM_QUANTITIES:
        return _KCAT_FORM
    if quantities & _VMAX_FORM_QUANTITIES:
        return _VMAX_FORM
    return ""


def _table_columns(name: str, manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """The columns of a drafted table; a network draft's kinetics.csv adds the ``inhibitor`` column of ki rows."""

    if name == "kinetics.csv" and NETWORK_MANIFEST_FIELD in manifest:
        return NETWORK_KINETICS_COLUMNS
    return _TABLE_COLUMNS[name]


def _amount_key(row: Mapping[str, str]) -> tuple[float | str, ...]:
    """A kinetics row's amount as the loader compares it: value, lower and upper as numbers, and the units."""

    def number_or_text(text: str) -> float | str:
        number = _finite_text(text)
        return text if number is None else number

    return (number_or_text(row["value"]), number_or_text(row["lower"]), number_or_text(row["upper"]), row["units"])


def _row_amount_text(row: Mapping[str, str]) -> str:
    amount = row["value"] or f"{row['lower']} to {row['upper']}"
    return f"{amount} {row['units']}".strip()


def _rows_label(lines: Sequence[int]) -> str:
    return f"row {lines[0]}" if len(lines) == 1 else f"rows {', '.join(str(line) for line in lines)}"


def _differing(measured: _Measured, requested: _Requested) -> set[str]:
    assert measured.kelvin is not None and measured.ph_value is not None
    needed: set[str] = set()
    if not math.isclose(measured.kelvin, requested.kelvin, rel_tol=_FLOAT_EQUALITY, abs_tol=_FLOAT_EQUALITY):
        needed.add("temperature")
    if not math.isclose(measured.ph_value, requested.ph, rel_tol=_FLOAT_EQUALITY, abs_tol=_FLOAT_EQUALITY):
        needed.add("ph")
    return needed


def _same_condition(kelvin_a: float, ph_a: float, kelvin_b: float, ph_b: float) -> bool:
    return math.isclose(kelvin_a, kelvin_b, rel_tol=_FLOAT_EQUALITY, abs_tol=_FLOAT_EQUALITY) and math.isclose(
        ph_a, ph_b, rel_tol=_FLOAT_EQUALITY, abs_tol=_FLOAT_EQUALITY
    )


def _not_acting_reason(item: _Class, target: _Target) -> str:
    if target.substrate_class not in item.compatible_substrate_classes:
        return (
            f"substrate class {target.substrate_class!r} is not among the class's substrate classes "
            f"{list(item.compatible_substrate_classes)}"
        )
    return f"the class cleaves {list(item.target_bond_classes)}, and {target.name} carries {list(target.bond_classes or ())}"


def _review_fields(
    manifest: Mapping[str, Any],
    tables: Mapping[str, Sequence[Mapping[str, str]]],
) -> tuple[Mapping[str, Any], ...]:
    fields: list[Mapping[str, Any]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                walk(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, str) and value.startswith(REVIEW_MARKER):
            fields.append({"file": USER_DATASET_MANIFEST, "row": None, "column": path, "note": value})

    walk(manifest, "")
    for name, rows in tables.items():
        for index, row in enumerate(rows):
            for column in _table_columns(name, manifest):
                cell = row.get(column, "")
                if cell.startswith(REVIEW_MARKER):
                    fields.append({"file": name, "row": index + 2, "column": column, "note": cell})
    return tuple(fields)


def _resolves(resolve: Any, term: str) -> bool:
    try:
        resolve(term)
    except ResolutionError:
        return False
    return True


def _parses(units: str) -> bool:
    try:
        Q_(1.0, units)
    except Exception:  # the unit registry raises several unrelated exception types for bad strings
        return False
    return True


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite_text(text: str) -> float | None:
    if not text or text.startswith(REVIEW_MARKER):
        return None
    return _finite(text)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return _number_cell(float(value))
    return str(value).strip()


def _rounded(value: float) -> float:
    return round(value, 9)


def _split(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in text.split(";") if item.strip()))


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _md_text(value: str) -> str:
    return value.replace("\n", " ")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "ASSEMBLY_STATUSES",
    "AssembledTablesDraft",
    "UserTablesAssemblyError",
    "assemble_user_tables",
]
