"""Draft user-dataset tables from public SABIO-RK kinetic-law entries (USERDATA-005).

``user_tables_from_sabiork`` turns SABIO-RK kinetic-law entries into the CSV
tables and manifest that ``load_user_dataset`` reads, together with a
``review.md`` that lists every mapping decision and every entry or parameter
that was not converted, with the reason. The entries come from a
``RegistryProposal`` (``source_proposal(provider="sabiork", ...)``, which reads
a frozen snapshot or, with ``refresh=True``, fetches live), from a SABIO-RK
kinetic-law export JSON a user downloaded, or from a reaction ID read from the
local snapshot cache through the existing adapter. Nothing here fetches.

The draft is not a dataset yet. Fields that need a person's decision (the
simulation time grid, the reviewer, a pH given only as a range, bond classes of
an enzyme class that is not in the registry, ...) are written as cells
beginning with ``REVIEW:``, and ``load_user_dataset`` refuses the directory,
naming each such field, until every one is filled. The user reviews and edits
the tables; they then load like any other user data.

Mapping rules (each application is recorded in ``review.md``):

- one strain per SABIO-RK organism and expression host, or the strain ID the
  caller maps the organism to; mutant enzymes are not entered as an organism's
  kinetics;
- the EC number is resolved against the registry's enzyme classes and, when
  the caller gives them (``user_enzyme_classes``), against the ``ec_number``
  of user-defined classes of ``enzyme_classes.csv`` by exact match of complete
  EC numbers (FETCH-003); an EC number that resolves to two classes (two
  registry classes, two user-defined classes, or one of each) is listed, never
  decided by the enzyme name; an unresolved EC number is listed, and an
  ``enzyme_classes.csv`` row with ``REVIEW:`` bond and substrate classes is
  proposed only on request;
- the substrate the law describes (named by its Km or concentration
  parameters) is resolved against the registry by name or alias, otherwise it
  becomes a user substrate row with ``REVIEW:`` categorical fields; the product
  and its mol/mol yield come from the reaction's stoichiometry when it names
  one product;
- one condition per distinct temperature and pH, the buffer in its notes;
- Km becomes ``km``, kcat ``kcat``, Vmax ``vmax`` (amount per volume per time)
  or ``specific_activity`` (amount per time per enzyme mass, with an
  ``enzyme_loading`` from ``design`` or a ``REVIEW:`` row); substrate and enzyme
  concentrations become ``substrate_initial_concentration`` and
  ``enzyme_concentration``; start and end values give an exact value or a
  range, the standard deviation ``sd``; evidence is ``literature``;
- units are kept as written when the unit registry parses them, otherwise
  mapped through ``SABIORK_UNIT_SPELLINGS``; any other unit is listed and its
  value not converted. Values are never converted between units;
- SABIO-RK's diprotic "Michaelis-Menten (pH-dependent)" law, recognised by its
  formula and its parameters ``k0``, ``Km0``, ``pKe1``, ``pKe2``, ``pKes1`` and
  ``pKes2``, becomes the pH-ionization rate form of user data: ``kcat_limiting``,
  ``km_limiting``, the four pK values, and ``ph_min`` and ``ph_max`` from the pH
  range the entry states (``REVIEW:`` fields when it states none). A law with
  pKa parameters in any other form is listed, not converted.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from fungal_model.api.user_data import REVIEW_MARKER, USER_DATASET_MANIFEST
from fungal_model.core.units import Q_, units_are_compatible
from fungal_model.data.sabiork import SabioRKParseError
from fungal_model.registry.loaders import load_registry
from fungal_model.registry.resolver import AmbiguousResolutionError, RegistryResolver, ResolutionError
from fungal_model.registry.store import FungModRegistry
from fungal_model.resources import default_registry_path
from fungal_model.sources.sabiork import (
    RegistryProposal,
    SabioRKKineticParameter,
    SabioRKReactionRecord,
    SabioRKSource,
    SabioRKSourceError,
    SabioRKSourceSnapshot,
    stable_sabiork_token,
)
from fungal_model.sources.sabiork.query_snapshots import complete_ec_number

# SABIO-RK unit spellings and the unit-registry spelling written for each. The
# table is consulted only when the unit registry does not parse the SABIO-RK
# spelling as written (a spelling it parses is kept unchanged). Every target is
# the same unit in an ASCII spelling, so a value is never rescaled.
SABIORK_UNIT_SPELLINGS: Mapping[str, str] = MappingProxyType(
    {
        # amount per volume
        "M": "mol/L",
        "mM": "mmol/L",
        "\u00b5M": "umol/L",
        "\u03bcM": "umol/L",
        "nM": "nmol/L",
        "pM": "pmol/L",
        # 1/time
        "s^(-1)": "1/s",
        "min^(-1)": "1/min",
        "h^(-1)": "1/h",
        # amount per volume per time
        "M*s^(-1)": "mol/L/s",
        "mM*s^(-1)": "mmol/L/s",
        "\u00b5M*s^(-1)": "umol/L/s",
        "nM*s^(-1)": "nmol/L/s",
        "M*min^(-1)": "mol/L/min",
        "mM*min^(-1)": "mmol/L/min",
        "\u00b5M*min^(-1)": "umol/L/min",
        "nM*min^(-1)": "nmol/L/min",
        # amount per time per enzyme mass
        "mol*s^(-1)*g^(-1)": "mol/s/g",
        "\u00b5mol*min^(-1)*mg^(-1)": "umol/min/mg",
        "\u03bcmol*min^(-1)*mg^(-1)": "umol/min/mg",
        "nmol*min^(-1)*mg^(-1)": "nmol/min/mg",
        "\u00b5mol*s^(-1)*mg^(-1)": "umol/s/mg",
        "nmol*s^(-1)*mg^(-1)": "nmol/s/mg",
        "U*mg^(-1)": "U/mg",
        "katal*g^(-1)": "kat/g",
        # mass per volume
        "g*l^(-1)": "g/L",
        "mg*ml^(-1)": "mg/mL",
        "\u00b5g*ml^(-1)": "ug/mL",
    }
)

# SABIO-RK temperature units and the conditions.csv spelling for each.
SABIORK_TEMPERATURE_UNITS: Mapping[str, str] = MappingProxyType(
    {"\u00b0C": "degC", "degC": "degC", "K": "kelvin", "kelvin": "kelvin"}
)

# Quantities ``design`` may supply: the virtual assay's own amounts, never kinetic constants.
DESIGN_QUANTITIES = ("substrate_initial_concentration", "enzyme_concentration", "enzyme_loading")

_DEFAULT_DESIGN_METHOD = "experimental design"
_DEFAULT_DESIGN_SOURCE = "Virtual assay design stated when drafting these tables; not reported by SABIO-RK"
_MOLAR = "mol / liter"
_MASS_CONCENTRATION = "gram / liter"
_RATE_CONSTANT = "1 / second"
_MOLAR_RATE = "mol / liter / second"
_MASS_RATE = "gram / liter / second"
_SPECIFIC_ACTIVITY = "mol / second / gram"
_EVIDENCE = "literature"
_YIELD_BASIS = "mol/mol"
_UNKNOWN = "unknown"
_DECIMAL_ID = re.compile(r"[1-9][0-9]*")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*$")
_DATASET_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_MISSING_TEXT = frozenset({"", "-"})

STRAIN_COLUMNS = ("strain_id", "name", "scientific_name", "aliases")
ENZYME_COLUMNS = ("strain_id", "enzyme_class", "evidence", "source")
ENZYME_CLASS_COLUMNS = (
    "class_id",
    "name",
    "ec_number",
    "target_bond_classes",
    "compatible_substrate_classes",
    "source",
)
SUBSTRATE_COLUMNS = (
    "substrate_id",
    "registry_substrate",
    "name",
    "substrate_class",
    "physical_state",
    "bond_classes",
    "product",
    "product_yield",
    "yield_basis",
    "source",
)
CONDITION_COLUMNS = ("condition_id", "temperature", "temperature_units", "ph", "notes")
KINETICS_COLUMNS = (
    "strain_id",
    "enzyme_class",
    "substrate_id",
    "condition_id",
    "quantity",
    "value",
    "lower",
    "upper",
    "units",
    "evidence_type",
    "method",
    "source",
    "sd",
)
_TABLE_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "strains.csv": STRAIN_COLUMNS,
    "enzymes.csv": ENZYME_COLUMNS,
    "enzyme_classes.csv": ENZYME_CLASS_COLUMNS,
    "substrates.csv": SUBSTRATE_COLUMNS,
    "conditions.csv": CONDITION_COLUMNS,
    "kinetics.csv": KINETICS_COLUMNS,
}
_OPTIONAL_TABLES = frozenset({"enzyme_classes.csv"})
_QUANTITY_ORDER = (
    "km",
    "kcat",
    "vmax",
    "specific_activity",
    "enzyme_loading",
    "kcat_limiting",
    "km_limiting",
    "pk_free_lower",
    "pk_free_upper",
    "pk_complex_lower",
    "pk_complex_upper",
    "ph_min",
    "ph_max",
    "substrate_initial_concentration",
    "enzyme_concentration",
)
_CONSTANTS = frozenset({"km", "kcat", "vmax", "specific_activity", "kcat_limiting", "km_limiting"})
_VMAX_QUANTITIES = frozenset({"vmax", "specific_activity"})
_REVIEW_MD = "review.md"

# SABIO-RK's diprotic pH-dependent Michaelis-Menten law (kinetic-law type 24), whitespace removed. Only an
# entry whose formula is exactly this law, with these parameter names, is mapped onto the roles of the
# pH-ionization form: kcat(pH) = k0 / f_es(pH), (kcat/Km)(pH) = (k0 / Km0) / f_e(pH).
PH_IONIZATION_LAW_FORMULA = (
    "E*((k0)/((10^(pKes1-pH)+1)*(10^(pH-pKes2)+1)))*S/(((k0)/((10^(pKes1-pH)+1)*(10^(pH-pKes2)+1)))"
    "/(((k0)/(Km0))/((10^(pKe1-pH)+1)*(10^(pH-pKe2)+1)))+S)"
)
# Parameter name in that formula -> (SABIO-RK parameter type, user-data quantity).
PH_IONIZATION_LAW_PARAMETERS: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "k0": ("kcat", "kcat_limiting"),
        "Km0": ("km", "km_limiting"),
        "pKe1": ("pka", "pk_free_lower"),
        "pKe2": ("pka", "pk_free_upper"),
        "pKes1": ("pka", "pk_complex_lower"),
        "pKes2": ("pka", "pk_complex_upper"),
    }
)
_DIMENSIONLESS_QUANTITIES = frozenset(
    {"pk_free_lower", "pk_free_upper", "pk_complex_lower", "pk_complex_upper", "ph_min", "ph_max"}
)
_DIMENSIONLESS = "dimensionless"
_PH_RANGE_SCALE = (0.0, 14.0)
_LIMITATIONS = (
    "Homogeneous Michaelis-Menten constants (Km, kcat, Vmax), the constants and fitted pH range of the diprotic "
    "pH-dependent Michaelis-Menten law, and the assay's substrate and enzyme concentrations are converted; "
    "inhibition constants, kcat/Km, Hill coefficients and pH laws of any other form are listed, not converted.",
    "Values are copied as SABIO-RK reports them; no value is converted between units, and SABIO-RK's "
    "normalised values are not used.",
    "A SABIO-RK concentration range is the range tested in the assay. It is written as a range, which "
    "exploratory runs sample uniformly and scientific mode refuses; give a design value to state the "
    "virtual assay instead.",
    "A standard deviation is kept in provenance (sd); it does not become a sampling distribution.",
    "Strains are keyed by organism and expression host. Isoenzymes of one organism measured at the same "
    "condition collide and are listed as conflicts; choose one with entry_ids.",
    "Mutant enzymes are listed, not converted: an engineered variant is not an enzyme of the organism.",
    "Nothing is fetched while drafting; a live SABIO-RK query happens only through "
    "source_proposal(provider='sabiork', refresh=True).",
)


class UserTablesSourceError(ValueError):
    """Raised when SABIO-RK entries cannot be drafted into user-dataset tables."""


@dataclass(frozen=True)
class UserTablesDraft:
    """User-dataset tables drafted from SABIO-RK entries, awaiting review.

    ``strains``, ``enzymes``, ``enzyme_classes`` (empty unless proposed),
    ``substrates``, ``conditions`` and ``kinetics`` hold the rows of the CSV
    tables ``load_user_dataset`` reads, as column-to-cell mappings.
    ``manifest`` is the ``user_dataset.yml`` content. ``review`` is the
    ``review.md`` text: every decision, every field still marked
    ``REVIEW:`` (also listed in ``review_fields`` with file, spreadsheet row
    and column), every entry not converted (``not_converted``) and every
    parameter of a converted entry that was not converted
    (``not_converted_parameters``), each with its reason.
    """

    dataset_id: str
    manifest: Mapping[str, Any]
    strains: tuple[Mapping[str, str], ...]
    enzymes: tuple[Mapping[str, str], ...]
    enzyme_classes: tuple[Mapping[str, str], ...]
    substrates: tuple[Mapping[str, str], ...]
    conditions: tuple[Mapping[str, str], ...]
    kinetics: tuple[Mapping[str, str], ...]
    review: str
    converted_entry_ids: tuple[str, ...]
    not_converted: tuple[Mapping[str, str], ...]
    not_converted_parameters: tuple[Mapping[str, str], ...]
    review_fields: tuple[Mapping[str, Any], ...]
    decisions: tuple[str, ...]

    def tables(self) -> dict[str, tuple[Mapping[str, str], ...]]:
        """Return the table rows by file name; ``enzyme_classes.csv`` only when it has rows."""

        tables = {
            "strains.csv": self.strains,
            "enzymes.csv": self.enzymes,
            "enzyme_classes.csv": self.enzyme_classes,
            "substrates.csv": self.substrates,
            "conditions.csv": self.conditions,
            "kinetics.csv": self.kinetics,
        }
        return {name: rows for name, rows in tables.items() if rows or name not in _OPTIONAL_TABLES}

    def file_texts(self) -> dict[str, str]:
        """Return the exact text of every file ``write`` creates, by file name."""

        texts = {USER_DATASET_MANIFEST: _manifest_text(self.manifest)}
        for name, rows in self.tables().items():
            texts[name] = _csv_text(_TABLE_COLUMNS[name], rows)
        texts[_REVIEW_MD] = self.review
        return texts

    def write(self, directory: str | Path, *, overwrite: bool = False) -> dict[str, Path]:
        """Write the manifest, tables and ``review.md`` into ``directory``.

        The directory is created when needed. Existing files of the same name
        are refused unless ``overwrite`` is true, and nothing is written inside
        ``data_registry/``. The output is deterministic: the same draft gives
        byte-identical files.
        """

        root = Path(directory)
        if "data_registry" in root.resolve(strict=False).parts:
            raise UserTablesSourceError(
                "UserTablesDraft.write refuses to write inside data_registry/; user tables are an overlay, "
                "never registry records."
            )
        texts = self.file_texts()
        existing = sorted(name for name in texts if (root / name).exists())
        if existing and not overwrite:
            raise UserTablesSourceError(
                f"{root} already holds {', '.join(existing)}; pass overwrite=True to replace them."
            )
        root.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        for name, text in texts.items():
            path = root / name
            path.write_bytes(text.encode("utf-8"))
            paths[name] = path
        return paths

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_user_tables_draft",
            "source_database": "SABIO-RK",
            "dataset_id": self.dataset_id,
            "manifest": _plain(self.manifest),
            "tables": {name: [dict(row) for row in rows] for name, rows in self.tables().items()},
            "converted_entry_ids": list(self.converted_entry_ids),
            "not_converted": [dict(item) for item in self.not_converted],
            "not_converted_parameters": [dict(item) for item in self.not_converted_parameters],
            "review_fields": [dict(item) for item in self.review_fields],
            "decisions": list(self.decisions),
        }


def user_tables_from_sabiork(
    source: RegistryProposal | str | Path,
    *,
    dataset_id: str,
    strain_id_for_organism: Mapping[str, str] | None = None,
    entry_ids: Sequence[str] | None = None,
    design: Mapping[str, Mapping[str, Any]] | None = None,
    propose_enzyme_classes: bool = False,
    registry: str | Path | FungModRegistry | None = None,
    cache_dir: str | Path = "data/source_snapshots/sabiork",
    user_enzyme_classes: Sequence[Mapping[str, str]] = (),
) -> UserTablesDraft:
    """Draft user-dataset tables from SABIO-RK kinetic-law entries for review.

    ``source`` is a ``RegistryProposal`` from ``source_proposal(provider=
    "sabiork", ...)``, the path of a SABIO-RK kinetic-law export JSON (the
    ``{"meta": ..., "data": [...]}`` document of the export API), or a SABIO-RK
    reaction ID as a decimal string, read from the frozen snapshots under
    ``cache_dir`` and the repository's snapshot folders. Nothing is fetched.

    ``entry_ids`` limits the conversion to those EntryIDs (every one must be
    in the source). ``strain_id_for_organism`` maps a SABIO-RK organism name to
    the strain ID to use; every key must name an organism of the selected
    entries. ``design`` supplies the virtual assay's own amounts, keyed by
    ``substrate_initial_concentration``, ``enzyme_concentration`` or
    ``enzyme_loading``, each a mapping with ``value`` (or ``lower`` and
    ``upper``), ``units`` and optionally ``source`` and ``method``; a design
    value replaces the concentration range SABIO-RK reports for the assay.
    ``propose_enzyme_classes`` drafts an ``enzyme_classes.csv`` row for an EC
    number the registry does not resolve, with its bond and substrate classes
    left as ``REVIEW:`` fields; without it such entries are listed and not
    converted. ``registry`` resolves enzyme classes and substrates (the
    packaged registry by default).

    ``user_enzyme_classes`` (FETCH-003) are user-defined enzyme classes an
    entry's EC number may also resolve to: rows of a user dataset's
    ``enzyme_classes.csv`` (mappings of its columns to cells; ``class_id`` is
    required and must not name a registry class). An entry's EC number
    resolves to such a class only when both are complete EC numbers and equal,
    and only when no registry class and no other user-defined class has it;
    an EC number shared that way is listed with the reason, and a class is
    never chosen by the enzyme name. A class that entries resolve to has its
    row copied unchanged into the draft's ``enzyme_classes.csv``. Without
    ``user_enzyme_classes`` nothing changes.

    Returns a ``UserTablesDraft``; ``draft.write(directory)`` writes the
    tables, ``user_dataset.yml`` and ``review.md``. ``load_user_dataset``
    refuses the directory until every ``REVIEW:`` field is filled.
    """

    if not isinstance(dataset_id, str) or not _DATASET_ID.fullmatch(dataset_id):
        raise UserTablesSourceError(
            "dataset_id must be lowercase snake_case (letters, digits, single underscores), as user_dataset.yml "
            "requires."
        )
    base = _base_registry(registry)
    resolver = RegistryResolver(base)
    user_classes = _validated_user_classes(user_enzyme_classes, resolver)
    design_rows = _validated_design(design)
    organism_map = _validated_organism_map(strain_id_for_organism)
    loaded = _load_entries(source, cache_dir=cache_dir)
    selected = _select_entries(loaded.entries, entry_ids)
    builder = _DraftBuilder(
        dataset_id=dataset_id,
        resolver=resolver,
        registry=base,
        organism_map=organism_map,
        design=design_rows,
        propose_enzyme_classes=propose_enzyme_classes,
        user_classes=user_classes,
    )
    builder.not_selected = tuple(entry for entry in loaded.entries if entry not in selected)
    builder.duplicates = loaded.duplicates
    return builder.build(selected, loaded)


# The kinetics databases user tables can be drafted from, keyed by the provider name that
# ``source_proposal`` uses, with the drafting function of each. A caller that names no database
# itself (the command line) offers these keys and calls the function of the provider the user names.
USER_TABLE_PROVIDERS: Mapping[str, Callable[..., UserTablesDraft]] = MappingProxyType(
    {"sabiork": user_tables_from_sabiork}
)


# ---------------------------------------------------------------------------
# Input


@dataclass(frozen=True)
class _Snapshot:
    file_name: str
    sha256: str
    query: str
    fetched_at: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class _Entry:
    record: SabioRKReactionRecord
    raw: Mapping[str, Any]

    @property
    def entry_id(self) -> str:
        return self.record.entry_id


@dataclass(frozen=True)
class _Loaded:
    description: str
    snapshots: tuple[_Snapshot, ...]
    entries: tuple[_Entry, ...]
    duplicates: tuple[str, ...]


def _base_registry(registry: str | Path | FungModRegistry | None) -> FungModRegistry:
    if isinstance(registry, FungModRegistry):
        return registry
    return load_registry(default_registry_path() if registry is None else Path(registry))


def _load_entries(source: RegistryProposal | str | Path, *, cache_dir: str | Path) -> _Loaded:
    adapter = SabioRKSource(cache_dir=cache_dir)
    try:
        if isinstance(source, RegistryProposal):
            return _load_proposal(source, adapter)
        if isinstance(source, str) and _DECIMAL_ID.fullmatch(source.strip()):
            reaction_id = source.strip()
            snapshot = adapter.fetch_kinlaw_entries(f"SabioReactionID:{reaction_id}", refresh=False)
            return _load_snapshot(snapshot, adapter, f"the local snapshot of SABIO-RK reaction {reaction_id}")
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                raise UserTablesSourceError(
                    f"SABIO-RK export {str(path)!r} is not a file. Give a RegistryProposal, the path of a "
                    "kinetic-law export JSON, or a reaction ID as a decimal string."
                )
            snapshot = adapter.load_kinlaw_entries(path)
            return _load_snapshot(snapshot, adapter, f"the SABIO-RK export file {path.name}")
    except (SabioRKSourceError, SabioRKParseError, OSError) as exc:
        raise UserTablesSourceError(
            f"Could not read SABIO-RK entries: {exc} Nothing is fetched while drafting tables; fetch first with "
            "source_proposal(provider='sabiork', ..., refresh=True) or download an export from SABIO-RK."
        ) from exc
    raise UserTablesSourceError(
        f"source must be a RegistryProposal, a path to a SABIO-RK export JSON or a reaction ID string, not "
        f"{type(source).__name__}."
    )


def _load_snapshot(snapshot: SabioRKSourceSnapshot, adapter: SabioRKSource, description: str) -> _Loaded:
    records = adapter.parse_reaction_records(snapshot)
    pairs = [_Entry(record=record, raw=raw) for raw, record in zip(snapshot.export.entries, records, strict=True)]
    entries, duplicates = _unique_entries(pairs)
    return _Loaded(
        description=description,
        snapshots=(_snapshot_info(snapshot),),
        entries=entries,
        duplicates=duplicates,
    )


def _load_proposal(proposal: RegistryProposal, adapter: SabioRKSource) -> _Loaded:
    paths = [Path(part) for part in proposal.source_snapshot_path.split("; ") if part.strip()]
    if not paths:
        raise UserTablesSourceError("The RegistryProposal names no source snapshot to read the entries from.")
    raw_by_id: dict[str, Mapping[str, Any]] = {}
    snapshots: list[_Snapshot] = []
    for path in paths:
        snapshot = adapter.load_kinlaw_entries(path, query=proposal.source_query)
        snapshots.append(_snapshot_info(snapshot))
        for raw, record in zip(snapshot.export.entries, adapter.parse_reaction_records(snapshot), strict=True):
            raw_by_id.setdefault(record.entry_id, raw)
    pairs: list[_Entry] = []
    for record in proposal.reaction_records:
        raw = raw_by_id.get(record.entry_id)
        if raw is None:
            raise UserTablesSourceError(
                f"EntryID {record.entry_id} of the proposal is not in its snapshot(s) "
                f"{', '.join(path.name for path in paths)}; the raw entry is needed for the expression host, "
                "condition ranges and parameter comments."
            )
        pairs.append(_Entry(record=record, raw=raw))
    entries, duplicates = _unique_entries(pairs)
    query = f" (query {proposal.source_query})" if proposal.source_query else ""
    return _Loaded(
        description=f"a SABIO-RK source proposal{query}",
        snapshots=tuple(snapshots),
        entries=entries,
        duplicates=duplicates,
    )


def _unique_entries(pairs: Sequence[_Entry]) -> tuple[tuple[_Entry, ...], tuple[str, ...]]:
    """Keep the first of identical repeated entries; refuse repeated EntryIDs with different content."""

    first: dict[str, _Entry] = {}
    duplicates: list[str] = []
    for entry in pairs:
        earlier = first.get(entry.entry_id)
        if earlier is None:
            first[entry.entry_id] = entry
            continue
        if dict(earlier.raw) != dict(entry.raw):
            raise UserTablesSourceError(
                f"EntryID {entry.entry_id} appears twice in the input with different content; FungMod does not "
                "choose between them. Select one snapshot."
            )
        duplicates.append(entry.entry_id)
    return tuple(first.values()), tuple(duplicates)


def _snapshot_info(snapshot: SabioRKSourceSnapshot) -> _Snapshot:
    metadata = snapshot.fetch_metadata
    urls = metadata.get("source_urls")
    return _Snapshot(
        file_name=snapshot.export_path.name,
        sha256=hashlib.sha256(snapshot.export_path.read_bytes()).hexdigest(),
        query=str(metadata.get("query") or snapshot.query or ""),
        fetched_at=str(metadata.get("fetched_at") or ""),
        source_urls=tuple(str(url) for url in urls) if isinstance(urls, list) else (),
    )


def _select_entries(entries: Sequence[_Entry], entry_ids: Sequence[str] | None) -> tuple[_Entry, ...]:
    if entry_ids is None:
        return tuple(entries)
    if isinstance(entry_ids, str):
        raise UserTablesSourceError("entry_ids must be a sequence of EntryIDs such as ['35622'], not one string.")
    wanted = [str(value).strip() for value in entry_ids]
    bad = [value for value in wanted if not _DECIMAL_ID.fullmatch(value)]
    if bad:
        raise UserTablesSourceError(f"entry_ids must be positive decimal SABIO-RK EntryIDs; got {bad}.")
    known = [entry.entry_id for entry in entries]
    missing = [value for value in dict.fromkeys(wanted) if value not in known]
    if missing:
        raise UserTablesSourceError(
            f"EntryID(s) {', '.join(missing)} are not in the source; it holds {', '.join(known)}."
        )
    chosen = set(wanted)
    return tuple(entry for entry in entries if entry.entry_id in chosen)


def _validated_organism_map(mapping: Mapping[str, str] | None) -> dict[str, str]:
    if mapping is None:
        return {}
    output: dict[str, str] = {}
    for organism, strain_id in mapping.items():
        if not isinstance(organism, str) or not organism.strip():
            raise UserTablesSourceError("strain_id_for_organism keys must be SABIO-RK organism names.")
        if not isinstance(strain_id, str) or not _IDENTIFIER.fullmatch(strain_id):
            raise UserTablesSourceError(
                f"strain_id_for_organism[{organism!r}] = {strain_id!r} must use letters and digits joined by "
                "single underscores, as strains.csv requires."
            )
        output[organism.strip()] = strain_id
    return output


def _validated_user_classes(
    rows: Sequence[Mapping[str, str]] | None, resolver: RegistryResolver
) -> dict[str, dict[str, str]]:
    """User-defined enzyme classes by class_id, as enzyme_classes.csv cells (FETCH-003)."""

    if rows is None:
        return {}
    if isinstance(rows, (str, Mapping)):
        raise UserTablesSourceError(
            "user_enzyme_classes must be a sequence of enzyme_classes.csv rows (mappings of column to cell), not one "
            "row or a string."
        )
    output: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise UserTablesSourceError(
                f"user_enzyme_classes[{index}] must be an enzyme_classes.csv row (a mapping of column to cell)."
            )
        unknown = sorted(str(key) for key in row if key not in ENZYME_CLASS_COLUMNS)
        if unknown:
            raise UserTablesSourceError(
                f"user_enzyme_classes[{index}] has key(s) {', '.join(unknown)}, which are not enzyme_classes.csv "
                f"columns ({', '.join(ENZYME_CLASS_COLUMNS)})."
            )
        cells = {column: _text(row.get(column)).strip() for column in ENZYME_CLASS_COLUMNS}
        class_id = cells["class_id"]
        if not _IDENTIFIER.fullmatch(class_id):
            raise UserTablesSourceError(
                f"user_enzyme_classes[{index}] needs a class_id of letters and digits joined by single underscores, "
                f"as enzyme_classes.csv requires; got {class_id!r}."
            )
        if class_id in output:
            raise UserTablesSourceError(f"user_enzyme_classes[{index}] repeats class_id {class_id!r}.")
        if _resolves(resolver.resolve_enzyme_class, class_id):
            raise UserTablesSourceError(
                f"user_enzyme_classes[{index}] class_id {class_id!r} names a registry enzyme class; a user-defined "
                "class needs an identifier the registry does not use, as load_user_dataset requires."
            )
        output[class_id] = cells
    return output


def _classes_with_ec_number(ec_number: str, user_classes: Mapping[str, Mapping[str, str]]) -> list[str]:
    """The class_ids of user-defined classes whose ``ec_number`` is the complete EC number ``ec_number``.

    An exact match of complete EC numbers (four numeric parts, an ``EC`` prefix
    ignored): a partial EC number such as ``3.2.1.-`` matches nothing, on
    either side, and nothing is matched by a name.
    """

    number = complete_ec_number(ec_number)
    if number is None:
        return []
    return [
        class_id
        for class_id, row in user_classes.items()
        if complete_ec_number(_text(row.get("ec_number"))) == number
    ]


@dataclass(frozen=True)
class _DesignValue:
    quantity: str
    value: str
    lower: str
    upper: str
    units: str
    source: str
    method: str

    def row(self, case: tuple[str, str, str, str]) -> dict[str, str]:
        strain_id, class_id, substrate_id, condition_id = case
        return _kinetics_row(
            strain_id=strain_id,
            enzyme_class=class_id,
            substrate_id=substrate_id,
            condition_id=condition_id,
            quantity=self.quantity,
            value=self.value,
            lower=self.lower,
            upper=self.upper,
            units=self.units,
            evidence_type="design",
            method=self.method,
            source=self.source,
            sd="",
        )

    @property
    def text(self) -> str:
        amount = self.value if self.value else f"{self.lower} to {self.upper}"
        return f"{self.quantity} = {amount} {self.units} ({self.source})"


_DESIGN_DIMENSIONS = {
    "substrate_initial_concentration": (_MOLAR, "an amount per volume such as mM"),
    "enzyme_concentration": (_MOLAR, "an amount per volume such as uM"),
    "enzyme_loading": (_MASS_CONCENTRATION, "an enzyme mass per volume such as mg/L"),
}


def _validated_design(design: Mapping[str, Mapping[str, Any]] | None) -> dict[str, _DesignValue]:
    if design is None:
        return {}
    output: dict[str, _DesignValue] = {}
    for quantity, item in design.items():
        if quantity not in DESIGN_QUANTITIES:
            raise UserTablesSourceError(
                f"design key {quantity!r} is not one of {', '.join(DESIGN_QUANTITIES)}; kinetic constants come "
                "from the source, not from the design."
            )
        if not isinstance(item, Mapping):
            raise UserTablesSourceError(f"design[{quantity!r}] must be a mapping with value (or lower and upper) and units.")
        unknown = sorted(str(key) for key in item if key not in {"value", "lower", "upper", "units", "source", "method"})
        if unknown:
            raise UserTablesSourceError(f"design[{quantity!r}] has unsupported key(s): {', '.join(unknown)}.")
        units = item.get("units")
        reference, label = _DESIGN_DIMENSIONS[quantity]
        if not isinstance(units, str) or not units.strip() or not _parses(units) or not units_are_compatible(units, reference):
            raise UserTablesSourceError(f"design[{quantity!r}]['units'] must be {label}; got {units!r}.")
        value = item.get("value")
        lower, upper = item.get("lower"), item.get("upper")
        exact = value is not None and lower is None and upper is None
        ranged = value is None and lower is not None and upper is not None
        if not (exact or ranged):
            raise UserTablesSourceError(f"design[{quantity!r}] needs either value or both lower and upper.")
        numbers = [_finite(number) for number in (value, lower, upper) if number is not None]
        if any(number is None or number < 0.0 for number in numbers):
            raise UserTablesSourceError(f"design[{quantity!r}] values must be finite nonnegative numbers.")
        if ranged and not _finite_or_raise(lower) < _finite_or_raise(upper):
            raise UserTablesSourceError(f"design[{quantity!r}] needs lower < upper.")
        source = item.get("source", _DEFAULT_DESIGN_SOURCE)
        method = item.get("method", _DEFAULT_DESIGN_METHOD)
        if not isinstance(source, str) or not source.strip() or not isinstance(method, str) or not method.strip():
            raise UserTablesSourceError(f"design[{quantity!r}] source and method must be nonblank text when given.")
        output[quantity] = _DesignValue(
            quantity=quantity,
            value="" if value is None else _number_cell(_finite_or_raise(value)),
            lower="" if lower is None else _number_cell(_finite_or_raise(lower)),
            upper="" if upper is None else _number_cell(_finite_or_raise(upper)),
            units=units.strip(),
            source=source.strip(),
            method=method.strip(),
        )
    return output


# ---------------------------------------------------------------------------
# Per-entry analysis


@dataclass
class _Plan:
    """One entry's convertible content, or the reasons it is not converted."""

    entry: _Entry
    reasons: list[str] = field(default_factory=list)
    strain_key: tuple[str, str] = ("", "")
    strain_id: str = ""
    class_id: str = ""
    substrate_name: str = ""
    substrate_id: str = ""
    condition: _ConditionCells | None = None
    rows: dict[str, dict[str, str]] = field(default_factory=dict)
    skipped: list[dict[str, str]] = field(default_factory=list)
    notes: list[tuple[str, str]] = field(default_factory=list)
    ph_law: bool = False
    # True when the entry is not converted only because none of its parameters converted.
    parameters_failed: bool = False

    @property
    def condition_id(self) -> str:
        return "" if self.condition is None else self.condition.condition_id

    @property
    def case(self) -> tuple[str, str, str, str]:
        return (self.strain_id, self.class_id, self.substrate_id, self.condition_id)

    def skip(self, parameter: SabioRKKineticParameter | None, reason: str, *, name: str = "", kind: str = "") -> None:
        self.skipped.append(
            {
                "entry_id": self.entry.entry_id,
                "parameter": parameter.name if parameter is not None else name,
                "parameter_type": parameter.parameter_type if parameter is not None else kind,
                "value": _value_text(parameter) if parameter is not None else "",
                "units": parameter.units if parameter is not None else "",
                "reason": reason,
            }
        )


@dataclass
class _ClassChoice:
    class_id: str
    reason: str
    decision: str
    proposed: dict[str, str] | None = None


@dataclass
class _SubstrateChoice:
    substrate_id: str
    registry_id: str
    reason: str
    decision: str


class _DraftBuilder:
    def __init__(
        self,
        *,
        dataset_id: str,
        resolver: RegistryResolver,
        registry: FungModRegistry,
        organism_map: Mapping[str, str],
        design: Mapping[str, _DesignValue],
        propose_enzyme_classes: bool,
        user_classes: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self.dataset_id = dataset_id
        self.resolver = resolver
        self.registry = registry
        self.organism_map = organism_map
        self.design = design
        self.propose_enzyme_classes = propose_enzyme_classes
        # User-defined classes an EC number may resolve to, by class_id (FETCH-003); empty unless given.
        self.user_classes: Mapping[str, Mapping[str, str]] = dict(user_classes or {})
        self.not_selected: tuple[_Entry, ...] = ()
        self.duplicates: tuple[str, ...] = ()
        self.decisions: dict[str, list[str]] = {
            "Strains": [],
            "Enzyme classes": [],
            "Substrates and products": [],
            "Conditions": [],
            "Units": [],
            "Kinetic values": [],
            "Design values": [],
        }
        self._class_cache: dict[str, _ClassChoice] = {}
        self._substrate_cache: dict[str, _SubstrateChoice] = {}
        self._proposed_classes: dict[str, dict[str, str]] = {}
        self._unit_mappings: dict[str, str] = {}
        self._dimensionless_dash = False
        self._pair_forms: dict[tuple[str, str], str] = {}

    # -- orchestration -----------------------------------------------------

    def build(self, entries: Sequence[_Entry], loaded: _Loaded) -> UserTablesDraft:
        organisms = {entry.record.organism.strip() for entry in entries if entry.record.organism.strip()}
        unused = [name for name in self.organism_map if self._mapped_organism(name, organisms) is None]
        if unused:
            raise UserTablesSourceError(
                f"strain_id_for_organism names organism(s) {', '.join(repr(name) for name in unused)} that no "
                f"selected entry has; the selected entries name {', '.join(sorted(organisms)) or 'no organism'}."
            )
        plans = [self._plan(entry) for entry in entries]
        self._assign_strains([plan for plan in plans if not plan.reasons])
        self._resolve_conflicts([plan for plan in plans if not plan.reasons])
        self._apply_rate_forms([plan for plan in plans if not plan.reasons])
        for plan in plans:
            if not plan.reasons and not any(quantity in _CONSTANTS for quantity in plan.rows):
                constants = "k0 or Km0 of the pH-ionization law" if plan.ph_law else "Km, kcat or Vmax"
                plan.reasons.append(
                    f"no {constants} could be converted (its parameters are listed under Parameters not converted)"
                )
                plan.parameters_failed = True
        converted = [plan for plan in plans if not plan.reasons]
        for plan in converted:
            for section, text in plan.notes:
                self._note(section, text)
        if not converted:
            details = "; ".join(f"EntryID {plan.entry.entry_id}: {'; '.join(plan.reasons)}" for plan in plans)
            raise UserTablesSourceError(f"No SABIO-RK entry could be converted into user tables. {details}")
        return self._assemble(plans, converted, loaded)

    # -- one entry ---------------------------------------------------------

    def _plan(self, entry: _Entry) -> _Plan:
        record, raw = entry.record, entry.raw
        plan = _Plan(entry=entry)
        enzyme = _mapping(raw.get("enzyme_description"))
        general = _mapping(raw.get("general"))
        plan.ph_law = any(parameter.parameter_type.strip().casefold() == "pka" for parameter in record.parameters)
        organism = record.organism.strip()
        if not organism:
            plan.reasons.append("SABIO-RK gives no organism for the entry")
        experiment = _text(general.get("experiment_type")).strip()
        if experiment and experiment.casefold() != "invitro":
            plan.reasons.append(f"experiment type {experiment!r}; user data imports in vitro enzyme kinetics only")
        variant = _text(enzyme.get("wildtype")).strip()
        spec = _text(enzyme.get("mutant_spec")).strip()
        if variant.casefold() == "mutant":
            plan.reasons.append(
                f"mutant enzyme{f' ({spec})' if spec else ''}: an engineered variant, not an enzyme of {organism or 'the organism'}, "
                "so it is not entered as the organism's kinetics"
            )
        elif variant.casefold() != "wildtype":
            plan.reasons.append(f"wildtype/mutant status {variant or 'not given'}; only wildtype enzymes are converted")
        law = record.kinetic_law_type.strip()
        if law and "michaelis-menten" not in law.casefold():
            plan.reasons.append(
                f"kinetic law {law!r} is not a Michaelis-Menten law; its parameters are not homogeneous "
                "Michaelis-Menten constants"
            )
        if plan.ph_law:
            problem = _ph_law_problem(entry)
            if problem:
                plan.reasons.append(problem)
            else:
                mapping = ", ".join(f"{name} -> {quantity}" for name, (_kind, quantity) in PH_IONIZATION_LAW_PARAMETERS.items())
                plan.notes.append(
                    (
                        "Kinetic values",
                        f"EntryID {entry.entry_id}: kinetic law {law} is the diprotic pH-ionization law; it is "
                        f"converted to the pH-ionization rate form ({mapping}; its fitted pH range -> ph_min and "
                        "ph_max). k0 and Km0 are the limiting constants of the law, not the kcat and Km at any one pH.",
                    )
                )
        class_choice = self._enzyme_class(record)
        if class_choice.reason:
            plan.reasons.append(class_choice.reason)
        plan.class_id = class_choice.class_id
        substrate_name, substrate_reason = _case_substrate(record)
        if substrate_reason:
            plan.reasons.append(substrate_reason)
        plan.substrate_name = substrate_name
        if substrate_name:
            substrate = self._substrate(substrate_name)
            if substrate.reason:
                plan.reasons.append(substrate.reason)
            plan.substrate_id = substrate.substrate_id
            if not substrate.reason and not class_choice.reason and not class_choice.proposed:
                incompatible = self._incompatible(class_choice.class_id, substrate.registry_id)
                if incompatible:
                    plan.reasons.append(incompatible)
        plan.condition = _condition(raw, ph_law=plan.ph_law)
        plan.strain_key = (organism, _text(enzyme.get("expressed_in")).strip())
        self._parameters(plan, comments=_raw_parameter_comments(raw, len(record.parameters)))
        return plan

    def _parameters(self, plan: _Plan, *, comments: Sequence[str]) -> None:
        record = plan.entry.record
        candidates: dict[str, list[tuple[SabioRKKineticParameter, dict[str, str]]]] = {}
        for parameter, comment in zip(record.parameters, comments, strict=True):
            quantity = self._quantity(plan, parameter)
            if quantity is None:
                continue
            row = self._value_row(plan, parameter, quantity, comment)
            if row is not None:
                candidates.setdefault(row["quantity"], []).append((parameter, row))
        for quantity, items in candidates.items():
            if len(items) > 1:
                for parameter, _row in items:
                    plan.skip(
                        parameter,
                        f"the entry gives {len(items)} {quantity} values; FungMod holds one per case and does not "
                        "choose between them",
                    )
                continue
            plan.rows[quantity] = items[0][1]
        if plan.ph_law:
            self._ph_range_rows(plan)
            return
        if "kcat" in plan.rows:
            for quantity in sorted(_VMAX_QUANTITIES & plan.rows.keys()):
                dropped = plan.rows.pop(quantity)
                plan.skip(
                    None,
                    "the entry also gives kcat; one case uses one rate form (kcat with an enzyme concentration, or "
                    "Vmax) and FungMod never derives one from the other, so the kcat form is kept",
                    name=f"Vmax ({_row_amount(dropped)} {dropped['units']})",
                    kind=quantity,
                )

    def _quantity(self, plan: _Plan, parameter: SabioRKKineticParameter) -> str | None:
        """The user-data quantity of one parameter, or None after listing why it is not converted."""

        kind = parameter.parameter_type.strip().casefold()
        if plan.ph_law:
            law_parameter = PH_IONIZATION_LAW_PARAMETERS.get(parameter.name.strip())
            if law_parameter is not None:
                quantity = law_parameter[1]
                if quantity == "km_limiting" and not self._km_of_case_substrate(plan, parameter):
                    return None
                return quantity
            if kind == "ph":
                # The law's pH variable: its range becomes ph_min and ph_max (see _ph_range_rows).
                return None
            if kind != "concentration":
                plan.skip(
                    parameter,
                    f"parameter type {parameter.parameter_type or 'not given'!r} is not a quantity of the "
                    "pH-ionization form",
                )
                return None
        if kind == "kcat/km":
            plan.skip(parameter, "kcat/Km is not a user-data quantity; FungMod never derives Km or kcat from it")
            return None
        if kind == "km":
            return "km" if self._km_of_case_substrate(plan, parameter) else None
        if kind == "kcat":
            return "kcat"
        if kind == "vmax":
            return "vmax"
        if kind == "concentration":
            compound, role = _species_parts(parameter.species)
            if role == "catalyst":
                return "enzyme_concentration"
            if role == "substrate" and compound and compound.casefold() == plan.substrate_name.casefold():
                return "substrate_initial_concentration"
            plan.skip(
                parameter,
                f"concentration of {compound or 'an unnamed species'}, which is neither the case substrate nor the "
                "enzyme",
            )
            return None
        plan.skip(parameter, f"parameter type {parameter.parameter_type or 'not given'!r} is not a user-data quantity")
        return None

    def _km_of_case_substrate(self, plan: _Plan, parameter: SabioRKKineticParameter) -> bool:
        compound, _role = _species_parts(parameter.species)
        if compound and compound.casefold() != plan.substrate_name.casefold():
            plan.skip(parameter, f"Km of {compound}, not of the case substrate {plan.substrate_name}")
            return False
        return True

    def _ph_range_rows(self, plan: _Plan) -> None:
        """ph_min and ph_max rows from the pH range the entry states, or REVIEW rows when it states none."""

        record = plan.entry.record
        fitted, origin, problem = _ph_fit_range(plan.entry)
        law = record.kinetic_law_type.strip()
        for index, quantity in enumerate(("ph_min", "ph_max")):
            bound = "lowest" if quantity == "ph_min" else "highest"
            if fitted is not None:
                value = _number_cell(fitted[index])
                method = f"SABIO-RK kinetic law {record.entry_id}, {law}; {bound} pH of the {origin}"
            else:
                value = (
                    f"{REVIEW_MARKER} {bound} pH of the pH series the law was fitted over ({problem}); the condition "
                    "pH must lie inside the range"
                )
                method = (
                    f"SABIO-RK kinetic law {record.entry_id}, {law}; {bound} pH of the fitted pH series, not stated by "
                    "the entry and supplied at review"
                )
            plan.rows[quantity] = _kinetics_row(
                strain_id="",
                enzyme_class=plan.class_id,
                substrate_id=plan.substrate_id,
                condition_id="",
                quantity=quantity,
                value=value,
                lower="",
                upper="",
                units=_DIMENSIONLESS,
                evidence_type=_EVIDENCE,
                method=method,
                source=_source_text(record),
                sd="",
            )
        if fitted is not None:
            plan.notes.append(
                (
                    "Kinetic values",
                    f"EntryID {record.entry_id}: ph_min {_number_cell(fitted[0])} and ph_max {_number_cell(fitted[1])} "
                    f"from the {origin}.",
                )
            )
        else:
            plan.notes.append(("Kinetic values", f"EntryID {record.entry_id}: ph_min and ph_max are REVIEW fields; {problem}."))

    def _value_row(
        self,
        plan: _Plan,
        parameter: SabioRKKineticParameter,
        quantity: str,
        comment: str,
    ) -> dict[str, str] | None:
        start = _finite(parameter.start_value)
        end = None if parameter.end_value is None else _finite(parameter.end_value)
        if parameter.start_value is None:
            plan.skip(parameter, "SABIO-RK gives no value")
            return None
        if start is None or (parameter.end_value is not None and end is None):
            plan.skip(parameter, "the value is not a finite number")
            return None
        units = self._units(plan, parameter, quantity)
        if units is None:
            return None
        quantity, problem = _route_quantity(quantity, units)
        if problem:
            plan.skip(parameter, problem)
            return None
        exact = end is None or end == start
        if not exact and end is not None and end < start:
            plan.skip(parameter, "the end value is below the start value")
            return None
        values = (start,) if exact else (start, end)
        if any(value is not None and value < 0.0 for value in values) or (
            quantity in {"km", "km_limiting"} and start <= 0.0
        ):
            plan.skip(parameter, "km must be positive and other values nonnegative")
            return None
        sd = _finite(parameter.standard_deviation)
        sd_text = ""
        if parameter.standard_deviation is not None:
            if sd is None or sd < 0.0:
                plan.notes.append(
                    (
                        "Kinetic values",
                        f"EntryID {plan.entry.entry_id} {parameter.name}: standard deviation "
                        f"{parameter.standard_deviation!r} is not a nonnegative number and is not copied.",
                    )
                )
            else:
                sd_text = _number_cell(sd)
        return _kinetics_row(
            strain_id="",
            enzyme_class=plan.class_id,
            substrate_id=plan.substrate_id,
            condition_id="",
            quantity=quantity,
            value=_number_cell(start) if exact else "",
            lower="" if exact else _number_cell(start),
            upper="" if exact or end is None else _number_cell(end),
            units=units,
            evidence_type=_EVIDENCE,
            method=_method(plan.entry.record, parameter, quantity, comment, exact=exact),
            source=_source_text(plan.entry.record),
            sd=sd_text,
        )

    def _units(self, plan: _Plan, parameter: SabioRKKineticParameter, quantity: str) -> str | None:
        units = parameter.units.strip()
        if units in _MISSING_TEXT and quantity in _DIMENSIONLESS_QUANTITIES:
            # SABIO-RK writes "-" for the unit of a pKa; a pK has no unit.
            self._dimensionless_dash = True
            return _DIMENSIONLESS
        if units in _MISSING_TEXT:
            plan.skip(parameter, "SABIO-RK gives no units")
            return None
        if _parses(units):
            return units
        mapped = SABIORK_UNIT_SPELLINGS.get(units)
        if mapped is None:
            plan.skip(
                parameter,
                f"units {units!r} are not parsed by the unit registry and are not in the SABIO-RK unit table",
            )
            return None
        self._unit_mappings[units] = mapped
        return mapped

    # -- registry resolution -------------------------------------------------

    def _enzyme_class(self, record: SabioRKReactionRecord) -> _ClassChoice:
        ec = record.ec_number.strip()
        name = record.enzyme_name.strip()
        if not ec:
            return _ClassChoice("", f"no EC number for {name or 'the enzyme'}; enzyme classes are resolved by EC number", "")
        cached = self._class_cache.get(ec)
        if cached is not None:
            return cached
        label = f"EC {ec}{f' ({name})' if name else ''}"
        users = _classes_with_ec_number(ec, self.user_classes)
        try:
            resolved = self.resolver.resolve_enzyme_class(ec)
        except AmbiguousResolutionError as exc:
            reason = f"{label} is ambiguous in the registry: {exc}"
            if users:
                reason += f"; it is also the ec_number of {_user_class_text(users)}"
            choice = _ClassChoice("", reason, "")
        except ResolutionError:
            choice = self._user_class(label, users) if users else self._unresolved_class(ec, name, label)
        else:
            if users:
                choice = _ClassChoice(
                    "",
                    f"{label} resolves both to registry enzyme class {resolved.record_id!r} and to "
                    f"{_user_class_text(users)}; FungMod does not choose between classes that share an EC number, "
                    "and never by the enzyme name",
                    "",
                )
            else:
                choice = _ClassChoice(
                    resolved.record_id,
                    "",
                    f"{label} resolves to registry enzyme class `{resolved.record_id}` (matched "
                    f"{resolved.matched_field} {resolved.matched_value!r}).",
                )
        self._class_cache[ec] = choice
        if choice.decision:
            self._note("Enzyme classes", choice.decision)
        elif choice.reason:
            self._note("Enzyme classes", f"{choice.reason}.")
        return choice

    def _user_class(self, label: str, users: Sequence[str]) -> _ClassChoice:
        """The user-defined class an EC number the registry does not resolve names, or why none is taken."""

        if len(users) > 1:
            return _ClassChoice(
                "",
                f"{label} is the ec_number of {_user_class_text(users)}; FungMod does not choose between classes that "
                "share an EC number, and never by the enzyme name",
                "",
            )
        (class_id,) = users
        row = self.user_classes[class_id]
        return _ClassChoice(
            class_id,
            "",
            f"{label} resolves to user-defined enzyme class `{class_id}` (its enzyme_classes.csv ec_number "
            f"{row['ec_number']}, an exact match; no registry class and no other user-defined class has that EC "
            "number). Its enzyme_classes.csv row is the user's, unchanged.",
        )

    def _unresolved_class(self, ec: str, name: str, label: str) -> _ClassChoice:
        if not self.propose_enzyme_classes:
            target = (
                "a registry enzyme class or to the ec_number of a user-defined class"
                if self.user_classes
                else "a registry enzyme class"
            )
            return _ClassChoice(
                "",
                f"{label} does not resolve to {target}; no class is invented (pass "
                "propose_enzyme_classes=True to draft an enzyme_classes.csv row with REVIEW bond and substrate classes)",
                "",
            )
        if name:
            try:
                clash = self.resolver.resolve_enzyme_class(name)
            except ResolutionError:
                clash = None
            if clash is not None:
                return _ClassChoice(
                    "",
                    f"{label} does not resolve, but the name {name!r} names registry enzyme class "
                    f"{clash.record_id!r}; the EC number and the name disagree, so no class is proposed",
                    "",
                )
            named = [
                class_id
                for class_id, row in self.user_classes.items()
                if _norm_text(name) in {_norm_text(class_id), _norm_text(_text(row.get("name")))}
            ]
            if named:
                return _ClassChoice(
                    "",
                    f"{label} does not resolve, but the name {name!r} names user-defined enzyme class {named[0]!r}, "
                    f"whose ec_number is {_text(self.user_classes[named[0]].get('ec_number')) or 'not given'}; the EC "
                    "number and the name disagree, so no class is proposed",
                    "",
                )
        base = stable_sabiork_token(name) if name else f"ec_{stable_sabiork_token(ec)}"
        class_id = base
        if (
            class_id in self._proposed_classes
            or class_id in self.user_classes
            or _resolves(self.resolver.resolve_enzyme_class, class_id)
        ):
            class_id = f"{base}_ec_{stable_sabiork_token(ec)}"
        row = {
            "class_id": class_id,
            "name": name or f"EC {ec}",
            "ec_number": ec,
            "target_bond_classes": f"{REVIEW_MARKER} bond classes {label} cleaves (semicolon-separated lowercase "
            "snake_case); FungMod does not infer them from the EC number",
            "compatible_substrate_classes": f"{REVIEW_MARKER} substrate classes {label} acts on (semicolon-separated "
            "lowercase snake_case)",
            "source": "",
        }
        self._proposed_classes[class_id] = row
        return _ClassChoice(
            class_id,
            "",
            f"{label} does not resolve to a registry enzyme class; enzyme_classes.csv row `{class_id}` is proposed "
            "(propose_enzyme_classes=True) with its bond and substrate classes left as REVIEW fields.",
            proposed=row,
        )

    def _substrate(self, name: str) -> _SubstrateChoice:
        key = name.casefold()
        cached = self._substrate_cache.get(key)
        if cached is not None:
            return cached
        try:
            resolved = self.resolver.resolve_substrate(name)
        except AmbiguousResolutionError as exc:
            choice = _SubstrateChoice("", "", f"substrate {name!r} is ambiguous in the registry: {exc}", "")
        except ResolutionError:
            substrate_id = stable_sabiork_token(name)
            if _resolves(self.resolver.resolve_substrate, substrate_id):
                substrate_id = f"{substrate_id}_sabiork"
            choice = _SubstrateChoice(
                substrate_id,
                "",
                "",
                f"Substrate {name!r} does not resolve to a registry substrate; substrates.csv row `{substrate_id}` "
                "is drafted with its substrate class, physical state and bond classes left as REVIEW fields.",
            )
        else:
            record = self.registry.get_substrate(resolved.record_id)
            if record.physical_state != "dissolved":
                choice = _SubstrateChoice(
                    "",
                    "",
                    f"substrate {name!r} is registry substrate {resolved.record_id!r} with physical state "
                    f"{record.physical_state!r}; user data supports dissolved substrates only",
                    "",
                )
            else:
                choice = _SubstrateChoice(
                    resolved.record_id,
                    resolved.record_id,
                    "",
                    f"Substrate {name!r} resolves to registry substrate `{resolved.record_id}` (matched "
                    f"{resolved.matched_field} {resolved.matched_value!r}); the registry record is referenced, not "
                    "copied.",
                )
        self._substrate_cache[key] = choice
        return choice

    def _incompatible(self, class_id: str, substrate_id: str) -> str:
        if not class_id or not substrate_id:
            return ""
        user_row = self.user_classes.get(class_id)
        if user_row is not None:
            kind = "user-defined enzyme class"
            targets = _semicolon_cells(_text(user_row.get("target_bond_classes")))
            compatible = _semicolon_cells(_text(user_row.get("compatible_substrate_classes")))
        else:
            enzyme_class = self.registry.get_enzyme_class(class_id)
            kind = "registry enzyme class"
            targets = tuple(enzyme_class.target_bond_classes)
            compatible = tuple(enzyme_class.compatible_substrate_classes)
        substrate = self.registry.get_substrate(substrate_id)
        shared = set(targets) & set(substrate.bond_classes)
        if substrate.substrate_class in compatible and shared:
            return ""
        return (
            f"{kind} {class_id!r} cannot act on registry substrate {substrate_id!r} (substrate class "
            f"{substrate.substrate_class!r}, bond classes {list(substrate.bond_classes)}; the class acts on "
            f"{list(compatible)} and cleaves {list(targets)})"
        )

    # -- strains, conflicts, rate forms ------------------------------------

    def _mapped_organism(self, name: str, organisms: Iterable[str]) -> str | None:
        for organism in organisms:
            if organism == name or " ".join(organism.casefold().split()) == " ".join(name.casefold().split()):
                return organism
        return None

    def _strain_for(self, organism: str) -> str | None:
        for name, strain_id in self.organism_map.items():
            if self._mapped_organism(name, (organism,)) is not None:
                return strain_id
        return None

    def _assign_strains(self, plans: Sequence[_Plan]) -> None:
        ids: dict[tuple[str, str], str] = {}
        used: dict[str, tuple[str, str]] = {}
        # A generated ID never takes an ID the caller gave another organism, so sources merge only on request.
        reserved = set(self.organism_map.values())
        for plan in plans:
            key = plan.strain_key
            if key in ids:
                plan.strain_id = ids[key]
                continue
            organism, host = key
            mapped = self._strain_for(organism)
            if mapped is not None:
                strain_id = mapped
            else:
                strain_id = stable_sabiork_token(organism) + (f"_in_{stable_sabiork_token(host)}" if host else "")
                if strain_id in reserved or (strain_id in used and used[strain_id] != key):
                    suffix = 2
                    while f"{strain_id}_{suffix}" in used or f"{strain_id}_{suffix}" in reserved:
                        suffix += 1
                    strain_id = f"{strain_id}_{suffix}"
            ids[key] = strain_id
            used.setdefault(strain_id, key)
            plan.strain_id = strain_id

    def _resolve_conflicts(self, plans: Sequence[_Plan]) -> None:
        for plan in plans:
            for row in plan.rows.values():
                row["strain_id"] = plan.strain_id
                row["condition_id"] = plan.condition_id
        by_case: dict[tuple[str, str, str, str], list[_Plan]] = {}
        for plan in plans:
            by_case.setdefault(plan.case, []).append(plan)
        for case, group in by_case.items():
            if len(group) < 2:
                continue
            ids = ", ".join(plan.entry.entry_id for plan in group)
            for plan in group:
                plan.reasons.append(
                    f"conflict: EntryIDs {ids} map to the same strain {case[0]!r}, enzyme class {case[1]!r}, "
                    f"substrate {case[2]!r} and condition {case[3]!r}; FungMod holds one value per quantity and case "
                    "and does not choose between them (select one with entry_ids)"
                )

    def _apply_rate_forms(self, plans: Sequence[_Plan]) -> None:
        plans = self._separate_ph_ionization_forms(plans)
        by_pair: dict[tuple[str, str], list[_Plan]] = {}
        for plan in plans:
            by_pair.setdefault((plan.class_id, plan.substrate_id), []).append(plan)
        for pair, group in by_pair.items():
            if all(plan.ph_law for plan in group):
                self._pair_forms[pair] = "ph_ionization"
                continue
            kcat = [plan.entry.entry_id for plan in group if "kcat" in plan.rows]
            vmax = [plan.entry.entry_id for plan in group if _VMAX_QUANTITIES & plan.rows.keys()]
            form = "kcat" if kcat else ("vmax" if vmax else "")
            self._pair_forms[pair] = form
            if kcat and vmax:
                self._note(
                    "Kinetic values",
                    f"Enzyme class {pair[0]!r} on substrate {pair[1]!r}: EntryIDs {', '.join(kcat)} give kcat and "
                    f"{', '.join(vmax)} give Vmax. All strains and conditions of one class and substrate share one "
                    "rate form, so the kcat form is kept and the Vmax values are listed as not converted.",
                )
            for plan in group:
                if form == "kcat":
                    for quantity in sorted(_VMAX_QUANTITIES & plan.rows.keys()):
                        dropped = plan.rows.pop(quantity)
                        plan.skip(
                            None,
                            f"enzyme class {pair[0]!r} on substrate {pair[1]!r} uses the kcat form in EntryIDs "
                            f"{', '.join(kcat)}; one rate form per class and substrate",
                            name=f"Vmax ({_row_amount(dropped)} {dropped['units']})",
                            kind=quantity,
                        )
                if form == "vmax" and "enzyme_concentration" in plan.rows:
                    dropped = plan.rows.pop("enzyme_concentration")
                    plan.skip(
                        None,
                        "the case uses the Vmax form, which has no enzyme concentration",
                        name=f"enzyme concentration ({_row_amount(dropped)} {dropped['units']})",
                        kind="concentration",
                    )

    def _separate_ph_ionization_forms(self, plans: Sequence[_Plan]) -> list[_Plan]:
        """Keep pH-ionization entries only where their class uses no other rate form; return the plans left.

        All cases of one enzyme class and substrate share one rate form, and in
        user data an enzyme class uses the pH-ionization form on all of its
        substrates or on none. An entry with a pH-ionization law converts only to
        that form, so where its class has entries of the kcat or Vmax form those
        are kept and the pH-ionization entries are listed with the reason.
        """

        other_forms: dict[str, list[_Plan]] = {}
        for plan in plans:
            if not plan.ph_law:
                other_forms.setdefault(plan.class_id, []).append(plan)
        kept: list[_Plan] = []
        for plan in plans:
            others = other_forms.get(plan.class_id, [])
            if not plan.ph_law or not others:
                kept.append(plan)
                continue
            same_pair = [other for other in others if other.substrate_id == plan.substrate_id]
            listed = same_pair or others
            where = (
                f"on substrate {plan.substrate_id!r}"
                if same_pair
                else f"on substrate(s) {', '.join(dict.fromkeys(repr(other.substrate_id) for other in others))}"
            )
            plan.reasons.append(
                f"enzyme class {plan.class_id!r} uses the kcat or Vmax form {where} in EntryIDs "
                f"{', '.join(other.entry.entry_id for other in listed)}; a pH-ionization law converts only to the "
                "pH-ionization form, and one enzyme class uses one process law (select the pH-ionization entries "
                "alone with entry_ids)"
            )
        return kept

    # -- assembly ------------------------------------------------------------

    def _assemble(self, plans: Sequence[_Plan], converted: Sequence[_Plan], loaded: _Loaded) -> UserTablesDraft:
        strains = self._strain_rows(converted)
        enzymes = self._enzyme_rows(converted)
        classes = self._class_rows(converted)
        substrates = self._substrate_rows(converted)
        conditions = self._condition_rows(converted)
        kinetics = self._kinetics_rows(converted)
        if self._unit_mappings:
            for original, mapped in sorted(self._unit_mappings.items()):
                self._note("Units", f"{original!r} is written as {mapped!r} (SABIO-RK unit table; the same unit).")
        if self._dimensionless_dash:
            self._note(
                "Units",
                "SABIO-RK writes '-' as the unit of a pKa and of the pH; pK values and the fitted pH range are written "
                f"as {_DIMENSIONLESS!r}.",
            )
        manifest = self._manifest(converted, loaded)
        tables = {
            "strains.csv": strains,
            "enzymes.csv": enzymes,
            "enzyme_classes.csv": classes,
            "substrates.csv": substrates,
            "conditions.csv": conditions,
            "kinetics.csv": kinetics,
        }
        review_fields = _review_fields(manifest, tables)
        not_converted = tuple(
            {"entry_id": plan.entry.entry_id, "reason": "; ".join(plan.reasons)} for plan in plans if plan.reasons
        )
        skipped_parameters = tuple(
            item for plan in plans if not plan.reasons or plan.parameters_failed for item in plan.skipped
        )
        decisions = tuple(text for items in self.decisions.values() for text in items)
        draft = UserTablesDraft(
            dataset_id=self.dataset_id,
            manifest=manifest,
            strains=tuple(strains),
            enzymes=tuple(enzymes),
            enzyme_classes=tuple(classes),
            substrates=tuple(substrates),
            conditions=tuple(conditions),
            kinetics=tuple(kinetics),
            review="",
            converted_entry_ids=tuple(plan.entry.entry_id for plan in converted),
            not_converted=not_converted,
            not_converted_parameters=skipped_parameters,
            review_fields=review_fields,
            decisions=decisions,
        )
        return replace(draft, review=self._review_markdown(draft, plans, converted, loaded))

    def _strain_rows(self, plans: Sequence[_Plan]) -> list[dict[str, str]]:
        keys_by_strain: dict[str, list[tuple[str, str]]] = {}
        entries_by_strain: dict[str, list[str]] = {}
        for plan in plans:
            keys = keys_by_strain.setdefault(plan.strain_id, [])
            if plan.strain_key not in keys:
                keys.append(plan.strain_key)
            entries_by_strain.setdefault(plan.strain_id, []).append(plan.entry.entry_id)
        rows: list[dict[str, str]] = []
        for strain_id, keys in keys_by_strain.items():
            organisms = list(dict.fromkeys(organism for organism, _host in keys))
            if len(keys) == 1:
                organism, host = keys[0]
                name = f"SABIO-RK enzyme source: {organism}" + (f", expressed in {host}" if host else "")
            else:
                name = f"SABIO-RK enzyme source: {' / '.join(organisms)}"
            rows.append(
                {
                    "strain_id": strain_id,
                    "name": name,
                    "scientific_name": organisms[0] if len(organisms) == 1 else "",
                    "aliases": "",
                }
            )
            hosts = [host for _organism, host in keys]
            how = (
                "mapped by strain_id_for_organism"
                if self._strain_for(organisms[0]) == strain_id
                else "one strain per SABIO-RK organism and expression host"
            )
            host_text = "; ".join(
                f"{organism}{f' expressed in {host}' if host else ' (no expression host given)'}" for organism, host in keys
            )
            cultivars = _unique(
                _text(_mapping(_mapping(plan.entry.raw.get("general")).get("strain")).get("name")).strip()
                for plan in plans
                if plan.strain_id == strain_id
            )
            self._note(
                "Strains",
                f"`{strain_id}` ({how}): {host_text}; EntryIDs {', '.join(entries_by_strain[strain_id])}"
                + (f"; SABIO-RK organism strains: {', '.join(cultivars)}" if cultivars else "")
                + ("" if len(hosts) == 1 else "; several sources share this strain")
                + ".",
            )
        return rows

    def _enzyme_rows(self, plans: Sequence[_Plan]) -> list[dict[str, str]]:
        grouped: dict[tuple[str, str], list[_Plan]] = {}
        for plan in plans:
            grouped.setdefault((plan.strain_id, plan.class_id), []).append(plan)
        rows: list[dict[str, str]] = []
        for (strain_id, class_id), group in grouped.items():
            evidence = "; ".join(_evidence_text(plan.entry) for plan in group)
            source = "; ".join(_unique(_source_text(plan.entry.record) for plan in group))
            rows.append(
                {
                    "strain_id": strain_id,
                    "enzyme_class": class_id,
                    "evidence": f"in vitro enzyme kinetics in SABIO-RK ({evidence})",
                    "source": source,
                }
            )
        return rows

    def _class_rows(self, plans: Sequence[_Plan]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for class_id, row in self._proposed_classes.items():
            group = [plan for plan in plans if plan.class_id == class_id]
            if not group:
                continue
            rows.append({**row, "source": "; ".join(_unique(_source_text(plan.entry.record) for plan in group))})
        # A user-defined class that entries resolve to keeps the user's own row, so the draft loads on its own.
        used = {plan.class_id for plan in plans}
        for class_id, row in self.user_classes.items():
            if class_id in used:
                rows.append({column: _text(row.get(column)) for column in ENZYME_CLASS_COLUMNS})
        return rows

    def _substrate_rows(self, plans: Sequence[_Plan]) -> list[dict[str, str]]:
        grouped: dict[str, list[_Plan]] = {}
        for plan in plans:
            grouped.setdefault(plan.substrate_id, []).append(plan)
        rows: list[dict[str, str]] = []
        for substrate_id, group in grouped.items():
            name = group[0].substrate_name
            registry_id = self._substrate_cache[name.casefold()].registry_id
            proposals = _unique_items(_product_proposal(plan.entry.record, name) for plan in group)
            registry_products = (
                tuple(self.registry.get_substrate(registry_id).products) if registry_id else ()
            )
            product, product_yield, note = _product_cells(name, proposals, registry_products)
            self._note("Substrates and products", self._substrate_cache[name.casefold()].decision)
            self._note("Substrates and products", note)
            reactions = _unique(
                f"SABIO-RK Reaction {plan.entry.record.reaction_id} equation: {plan.entry.record.equation}"
                for plan in group
            )
            row = {
                "substrate_id": substrate_id,
                "registry_substrate": registry_id,
                "name": "",
                "substrate_class": "",
                "physical_state": "",
                "bond_classes": "",
                "product": product,
                "product_yield": product_yield,
                "yield_basis": _YIELD_BASIS,
                "source": "; ".join(reactions),
            }
            if not registry_id:
                row.update(
                    {
                        "name": name,
                        "substrate_class": f"{REVIEW_MARKER} substrate class of {name} (lowercase snake_case)",
                        "physical_state": f"{REVIEW_MARKER} physical state of {name}; user data supports dissolved "
                        "substrates only",
                        "bond_classes": f"{REVIEW_MARKER} bond classes of {name} the enzyme cleaves (semicolon-separated "
                        "lowercase snake_case)",
                    }
                )
            rows.append(row)
        return rows

    def _condition_rows(self, plans: Sequence[_Plan]) -> list[dict[str, str]]:
        grouped: dict[str, list[_Plan]] = {}
        for plan in plans:
            grouped.setdefault(plan.condition_id, []).append(plan)
        rows: list[dict[str, str]] = []
        for condition_id, group in grouped.items():
            cells = group[0].condition
            assert cells is not None
            buffers = _unique(
                f"EntryID {plan.entry.entry_id}: {plan.entry.record.buffer.strip()}"
                for plan in group
                if plan.entry.record.buffer.strip()
            )
            note_parts = list(cells.notes)
            if buffers:
                note_parts.append(f"SABIO-RK assay buffer ({'; '.join(buffers)})")
            rows.append(
                {
                    "condition_id": condition_id,
                    "temperature": cells.temperature,
                    "temperature_units": cells.temperature_units,
                    "ph": cells.ph,
                    "notes": "; ".join(note_parts),
                }
            )
            entries = ", ".join(plan.entry.entry_id for plan in group)
            if cells.temperature == _UNKNOWN:
                t_text = "unknown"
            elif cells.temperature.startswith(REVIEW_MARKER) or cells.temperature_units.startswith(REVIEW_MARKER):
                t_text = "a REVIEW field"
            else:
                t_text = f"{cells.temperature} {cells.temperature_units}"
            ph_text = "a REVIEW field" if cells.ph.startswith(REVIEW_MARKER) else cells.ph
            self._note(
                "Conditions",
                f"`{condition_id}`: temperature {t_text}, pH {ph_text} (EntryIDs {entries})"
                + (f"; {'; '.join(cells.notes)}" if cells.notes else "")
                + ".",
            )
        return rows

    def _kinetics_rows(self, plans: Sequence[_Plan]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for plan in plans:
            case = plan.case
            form = self._pair_forms.get((plan.class_id, plan.substrate_id), "")
            case_rows = dict(plan.rows)
            for quantity in ("substrate_initial_concentration", "enzyme_concentration"):
                design = self.design.get(quantity)
                if design is None or (quantity == "enzyme_concentration" and form == "vmax"):
                    continue
                replaced = case_rows.pop(quantity, None)
                if replaced is not None:
                    plan.skip(
                        None,
                        f"replaced by the design value {design.text}; the SABIO-RK value is the assay's, not the "
                        "virtual experiment's",
                        name=f"{quantity} ({_row_amount(replaced)} {replaced['units']})",
                        kind="concentration",
                    )
                case_rows[quantity] = design.row(case)
            if "specific_activity" in case_rows:
                loading = self.design.get("enzyme_loading")
                if loading is not None:
                    case_rows["enzyme_loading"] = loading.row(case)
                else:
                    case_rows["enzyme_loading"] = _kinetics_row(
                        strain_id=case[0],
                        enzyme_class=case[1],
                        substrate_id=case[2],
                        condition_id=case[3],
                        quantity="enzyme_loading",
                        value=f"{REVIEW_MARKER} enzyme loading of the simulated system (enzyme mass per volume), "
                        "needed to turn the specific activity into Vmax; or pass design={'enzyme_loading': ...}",
                        lower="",
                        upper="",
                        units=f"{REVIEW_MARKER} a mass-per-volume unit such as mg/L",
                        evidence_type="design",
                        method=_DEFAULT_DESIGN_METHOD,
                        source=f"{REVIEW_MARKER} where the enzyme loading comes from",
                        sd="",
                    )
            for quantity in _QUANTITY_ORDER:
                if quantity not in case_rows:
                    continue
                row = case_rows[quantity]
                rows.append(row)
                if row["evidence_type"] == _EVIDENCE and row["lower"]:
                    self._note(
                        "Kinetic values",
                        f"EntryID {plan.entry.entry_id} {quantity}: SABIO-RK gives {row['lower']} to {row['upper']} "
                        f"{row['units']}, written as a range (lower, upper).",
                    )
        for quantity, design in self.design.items():
            used = any(row["quantity"] == quantity and row["evidence_type"] == "design" for row in rows)
            self._note(
                "Design values",
                f"{design.text}: "
                + ("written as a design row of every case that takes it." if used else "not used by any case.")
            )
        return rows

    def _manifest(self, plans: Sequence[_Plan], loaded: _Loaded) -> dict[str, Any]:
        ids = ", ".join(plan.entry.entry_id for plan in plans)
        label = "EntryID" if len(plans) == 1 else "EntryIDs"
        snapshots = "; ".join(
            f"{snapshot.file_name} (sha256 {snapshot.sha256}"
            + (f", query {snapshot.query}" if snapshot.query else "")
            + (f", fetched {snapshot.fetched_at}" if snapshot.fetched_at else "")
            + ")"
            for snapshot in loaded.snapshots
        )
        return {
            "dataset_id": self.dataset_id,
            "contributor": f"{REVIEW_MARKER} name of the person who reviewed these tables",
            "source": f"SABIO-RK kinetic-law {label} {ids}, read from {loaded.description}: {snapshots}",
            "notes": (
                "Drafted by fungal_model.api.user_data_sources.user_tables_from_sabiork. Values are copied from "
                "SABIO-RK without unit conversion; review.md lists every mapping decision and everything not converted."
            ),
            "simulation": {
                "duration": f"{REVIEW_MARKER} simulated duration, a positive number (FungMod has no default time grid)",
                "units": f"{REVIEW_MARKER} time unit of the duration, such as minute or hour",
                "points": f"{REVIEW_MARKER} number of output time points, an integer of at least 2",
            },
        }

    def _note(self, section: str, text: str) -> None:
        if text and text not in self.decisions[section]:
            self.decisions[section].append(text)

    # -- review.md -----------------------------------------------------------

    def _review_markdown(
        self,
        draft: UserTablesDraft,
        plans: Sequence[_Plan],
        converted: Sequence[_Plan],
        loaded: _Loaded,
    ) -> str:
        lines = [
            f"# Review: SABIO-RK entries drafted as user tables ({self.dataset_id})",
            "",
            f"Read from {loaded.description}.",
            "",
        ]
        for snapshot in loaded.snapshots:
            lines.append(f"- Export `{snapshot.file_name}`, sha256 `{snapshot.sha256}`")
            if snapshot.query:
                lines.append(f"  - query `{snapshot.query}`")
            if snapshot.fetched_at:
                lines.append(f"  - fetched {snapshot.fetched_at}")
            lines.extend(f"  - {url}" for url in snapshot.source_urls)
        selected = len(plans)
        lines.extend(
            [
                "",
                f"Entries in the input: {selected + len(self.not_selected)}; selected: {selected}; converted: "
                f"{len(converted)}; not converted: {selected - len(converted)}.",
                "",
                "This is a draft. `load_user_dataset` refuses the directory until every field that begins with "
                f"`{REVIEW_MARKER}` is replaced by a reviewed value. Nothing was fetched while drafting, and every value "
                "is copied from the export without unit conversion. Read the decisions below, edit the tables where "
                "you disagree, then load them like any other user data.",
                "",
                "## Fields to fill",
                "",
            ]
        )
        if draft.review_fields:
            lines.extend(["| File | Row | Column | What to decide |", "| --- | --- | --- | --- |"])
            for item in draft.review_fields:
                row = "" if item["row"] is None else str(item["row"])
                lines.append(
                    f"| {item['file']} | {row} | {item['column']} | {_md(str(item['note'])[len(REVIEW_MARKER):].strip())} |"
                )
        else:
            lines.append("None.")
        lines.extend(["", "## Mapping decisions", ""])
        rules = _RULES if not self.user_classes else (_RULES[0], _USER_CLASS_RULE, *_RULES[2:])
        lines.extend(f"- {_md_text(rule)}" for rule in rules)
        for section, items in self.decisions.items():
            if not items:
                continue
            lines.extend(["", f"### {section}", ""])
            lines.extend(f"- {_md_text(item)}" for item in items)
        lines.extend(["", "## Entries converted", ""])
        lines.extend(
            [
                "| EntryID | Strain | Enzyme class | Substrate | Condition | Quantities |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for plan in converted:
            quantities = [
                row["quantity"]
                for row in draft.kinetics
                if (row["strain_id"], row["enzyme_class"], row["substrate_id"], row["condition_id"]) == plan.case
            ]
            lines.append(
                f"| {plan.entry.entry_id} | {plan.strain_id} | {plan.class_id} | {plan.substrate_id} | "
                f"{plan.condition_id} | {', '.join(quantities)} |"
            )
        lines.extend(["", "## Entries not converted", ""])
        if draft.not_converted:
            lines.extend(["| EntryID | Organism | Enzyme | Reason |", "| --- | --- | --- | --- |"])
            for plan in plans:
                if not plan.reasons:
                    continue
                record = plan.entry.record
                enzyme = f"{record.enzyme_name} (EC {record.ec_number})" if record.ec_number else record.enzyme_name
                lines.append(
                    f"| {plan.entry.entry_id} | {_md(record.organism)} | {_md(enzyme)} | {_md('; '.join(plan.reasons))} |"
                )
        else:
            lines.append("None.")
        if self.not_selected:
            lines.extend(
                [
                    "",
                    "Not selected by `entry_ids` (not examined): "
                    + ", ".join(entry.entry_id for entry in self.not_selected)
                    + ".",
                ]
            )
        if self.duplicates:
            lines.extend(
                ["", f"Repeated identical entries read once: EntryIDs {', '.join(self.duplicates)}."]
            )
        ph_laws = [plan for plan in plans if plan.ph_law]
        lines.extend(["", "## pH-ionization laws", ""])
        if ph_laws:
            mapping = ", ".join(f"{name} -> {quantity}" for name, (_kind, quantity) in PH_IONIZATION_LAW_PARAMETERS.items())
            lines.extend(
                [
                    "A kinetic law with pKa parameters is converted to the pH-ionization rate form of user data when "
                    "it is SABIO-RK's diprotic pH-dependent Michaelis-Menten law, recognised by its formula "
                    f"`{PH_IONIZATION_LAW_FORMULA}`: {mapping}. The pH range the entry states (the start and end of "
                    "the law's pH variable, or of the assay pH) becomes ph_min and ph_max; without one they are REVIEW "
                    "fields. k0 and Km0 are the limiting constants of the law, not the kcat and Km at any one pH, so "
                    "they are never written as kcat or km. The condition pH is the pH the case runs at: a pH the entry "
                    "gives as a range is a REVIEW field, to be filled with one pH inside ph_min to ph_max. A law with "
                    "pKa parameters in any other form is listed, not converted.",
                    "",
                    "| EntryID | Kinetic law | pKa parameters | Converted |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for plan in ph_laws:
                record = plan.entry.record
                pkas = ", ".join(
                    f"{p.name} = {_value_text(p) or 'no value'}"
                    for p in record.parameters
                    if p.parameter_type.strip().casefold() == "pka"
                )
                status = "pH-ionization form" if not plan.reasons else "no (see Entries not converted)"
                lines.append(f"| {plan.entry.entry_id} | {_md(record.kinetic_law_type)} | {_md(pkas)} | {status} |")
        else:
            lines.append("None in the selected entries.")
        lines.extend(["", "## Parameters not converted", ""])
        if draft.not_converted_parameters:
            lines.append(
                "Parameters of converted entries that are not in the tables, and of entries none of whose "
                "parameters could be converted:"
            )
            lines.extend(["", "| EntryID | Parameter | Type | Value | Units | Reason |", "| --- | --- | --- | --- | --- | --- |"])
            for item in draft.not_converted_parameters:
                lines.append(
                    "| "
                    + " | ".join(
                        _md(item[key]) for key in ("entry_id", "parameter", "parameter_type", "value", "units", "reason")
                    )
                    + " |"
                )
        else:
            lines.append("None.")
        lines.extend(
            [
                "",
                "The parameters of an entry not converted for an entry-level reason (mutant, conflict, "
                "unresolved EC number, law type, substrate) are covered by that reason and not listed one by one.",
                "",
            ]
        )
        lines.extend(["## Limitations", ""])
        lines.extend(f"- {_md_text(item)}" for item in _LIMITATIONS)
        lines.append("")
        return "\n".join(lines)


_RULES = (
    "Strain: one strain per SABIO-RK organism and expression host (expressed_in), or the strain ID given in "
    "strain_id_for_organism. Mutant enzymes are not converted.",
    "Enzyme class: the EC number is resolved against the registry's enzyme classes (EC numbers are aliases there). "
    "An unresolved EC number is listed; an enzyme_classes.csv row is proposed only with propose_enzyme_classes=True, "
    "and its bond and substrate classes are REVIEW fields.",
    "Substrate: the substrate named by the entry's Km and concentration parameters (or the reaction's only substrate) "
    "is resolved against the registry by name or alias; otherwise a substrates.csv row with REVIEW categorical "
    "fields is drafted. Product and mol/mol yield come from the reaction stoichiometry when it names one product.",
    "Condition: one condition per distinct temperature and pH; the buffer goes into notes. A missing value is "
    "written as unknown, a range as a REVIEW field; the pH of a pH-ionization law, which the case runs at, is a "
    "REVIEW field when SABIO-RK gives a range or none.",
    "Kinetics: Km -> km, kcat -> kcat, Vmax -> vmax (amount per volume per time) or specific_activity (amount per "
    "time per enzyme mass, with an enzyme_loading from design or a REVIEW row); the substrate and enzyme "
    "concentrations -> substrate_initial_concentration and enzyme_concentration; evidence literature. Start and end "
    "values give an exact value or a range; the standard deviation goes to sd. Source: SABIO-RK EntryID with the "
    "first author, year and PubMed ID; method: SABIO-RK kinetic law with its rate-law name.",
    "Units: kept as written when the unit registry parses them, otherwise mapped through the SABIO-RK unit table; "
    "any other unit is listed and its value not converted.",
    "pH-ionization laws: SABIO-RK's diprotic pH-dependent Michaelis-Menten law becomes the pH-ionization rate "
    "form (k0 -> kcat_limiting, Km0 -> km_limiting, pKe1, pKe2, pKes1, pKes2 -> the four pK values, the stated pH "
    "range -> ph_min and ph_max, or REVIEW fields); a law with pKa parameters in any other form is listed. One "
    "enzyme class uses the pH-ionization form on all of its substrates or on none, so where entries of the kcat "
    "or Vmax form share the class, the pH-ionization entries are listed.",
)
# The enzyme-class rule of _RULES when user-defined classes are given (FETCH-003); without them _RULES is unchanged.
_USER_CLASS_RULE = (
    "Enzyme class: the EC number is resolved against the registry's enzyme classes (EC numbers are aliases there) "
    "and against the ec_number of the user-defined classes given (user_enzyme_classes; an exact match of complete EC "
    "numbers). An EC number that resolves to two classes (two registry classes, two user-defined classes, or one of "
    "each) is listed, never decided by the enzyme name. An unresolved EC number is listed; an enzyme_classes.csv row "
    "is proposed only with propose_enzyme_classes=True, and its bond and substrate classes are REVIEW fields."
)


# ---------------------------------------------------------------------------
# Helpers


def _case_substrate(record: SabioRKReactionRecord) -> tuple[str, str]:
    """The substrate the law describes: named by Km or concentration parameters, else the only substrate."""

    named: dict[str, str] = {}
    for parameter in record.parameters:
        kind = parameter.parameter_type.strip().casefold()
        if kind not in {"km", "concentration"}:
            continue
        compound, role = _species_parts(parameter.species)
        if compound and role == "substrate":
            named.setdefault(compound.casefold(), compound)
    if len(named) == 1:
        return next(iter(named.values())), ""
    if len(named) > 1:
        return "", (
            f"Km or concentration parameters name several substrates ({', '.join(named.values())}); a homogeneous "
            "Michaelis-Menten case has one substrate"
        )
    substrates = _unique(participant.compound_name for participant in record.substrates)
    if len(substrates) == 1:
        return substrates[0], ""
    return "", (
        f"cannot tell which substrate the law describes: the reaction lists {', '.join(substrates) or 'none'} and no "
        "Km or concentration parameter names one"
    )


def _species_parts(species: str) -> tuple[str, str]:
    parts = [part.strip() for part in species.split("|")]
    if len(parts) == 3:
        return parts[1], parts[2].casefold()
    return "", ""


def _route_quantity(quantity: str, units: str) -> tuple[str, str]:
    """Check the dimension of ``units`` for ``quantity`` (and route Vmax); return (quantity, problem)."""

    if quantity in {"kcat", "kcat_limiting"}:
        if units_are_compatible(units, _RATE_CONSTANT):
            return quantity, ""
        return quantity, f"{quantity} units {units!r} are not 1/time"
    if quantity in _DIMENSIONLESS_QUANTITIES:
        if units_are_compatible(units, _DIMENSIONLESS):
            return quantity, ""
        return quantity, f"{quantity} units {units!r} are not dimensionless"
    if quantity == "vmax":
        if units_are_compatible(units, _MOLAR_RATE):
            return "vmax", ""
        if units_are_compatible(units, _SPECIFIC_ACTIVITY):
            return "specific_activity", ""
        if units_are_compatible(units, _MASS_RATE):
            return quantity, (
                f"Vmax units {units!r} are a mass concentration per time; the substrate amounts and the mol/mol yield "
                "would need a molar mass, which FungMod does not assume"
            )
        return quantity, (
            f"Vmax units {units!r} are neither an amount per volume per time (vmax) nor an amount per time per "
            "enzyme mass (specific_activity)"
        )
    if units_are_compatible(units, _MOLAR):
        return quantity, ""
    if units_are_compatible(units, _MASS_CONCENTRATION):
        return quantity, (
            f"{quantity} units {units!r} are a mass concentration; user data needs amount per volume because the "
            "product yield is mol/mol, and FungMod does not assume a molar mass"
        )
    return quantity, f"{quantity} units {units!r} are not a concentration (amount per volume)"


@dataclass(frozen=True)
class _ConditionCells:
    condition_id: str
    temperature: str
    temperature_units: str
    ph: str
    notes: tuple[str, ...]


def _condition(raw: Mapping[str, Any], *, ph_law: bool = False) -> _ConditionCells:
    """conditions.csv cells for an entry's temperature and pH, and the condition ID they give.

    For a pH-ionization law the pH is the one the case runs at, so a range or a
    missing pH is a REVIEW field to be filled with one pH inside ph_min to ph_max.
    """

    conditions = _mapping(raw.get("experimental_conditions"))
    temperature = _mapping(conditions.get("envvar_temperature"))
    ph = _mapping(conditions.get("envvar_ph"))
    notes: list[str] = []
    unit_text = _text(temperature.get("unit")).strip()
    units = SABIORK_TEMPERATURE_UNITS.get(unit_text, "")
    t_cell, t_numbers = _condition_value(
        temperature.get("start_value"), temperature.get("end_value"), label="temperature", unit_text=unit_text, notes=notes
    )
    if t_cell == _UNKNOWN:
        units = "degC"
        notes.append("SABIO-RK gives no temperature; the units cell is required by conditions.csv and unused")
    elif not units:
        units = f"{REVIEW_MARKER} SABIO-RK temperature unit {unit_text or 'not given'!r} is not degC or kelvin"
        if not t_cell.startswith(REVIEW_MARKER):
            t_cell = f"{REVIEW_MARKER} SABIO-RK gives {t_cell} {unit_text}; restate it in degC or kelvin"
    ph_cell, ph_numbers = _condition_value(
        ph.get("start_value"),
        ph.get("end_value"),
        label="pH",
        unit_text="",
        notes=notes,
        single=_PH_LAW_CONDITION if ph_law else "",
    )
    if ph_law and ph_cell == _UNKNOWN:
        ph_cell = f"{REVIEW_MARKER} SABIO-RK gives no pH; {_PH_LAW_CONDITION}"
    prefix = {"degC": "c", "kelvin": "k"}.get(units, "t")
    t_part = "tunknown" if t_cell == _UNKNOWN else prefix + ("_to_".join(t_numbers) or "review")
    ph_part = "phunknown" if ph_cell == _UNKNOWN else "ph" + ("_to_".join(ph_numbers) or "review")
    return _ConditionCells(
        condition_id=f"{t_part}_{ph_part}",
        temperature=t_cell,
        temperature_units=units,
        ph=ph_cell,
        notes=tuple(notes),
    )


def _condition_value(
    start: Any,
    end: Any,
    *,
    label: str,
    unit_text: str,
    notes: list[str],
    single: str = "",
) -> tuple[str, list[str]]:
    """The cell for one condition variable and the numbers its condition ID is built from.

    ``single`` replaces the request written into the REVIEW cell of a range.
    """

    first = _finite(start)
    last = None if end is None else _finite(end)
    if start is None:
        notes.append(f"SABIO-RK gives no {label}")
        return _UNKNOWN, []
    if first is None or (end is not None and last is None):
        return f"{REVIEW_MARKER} SABIO-RK {label} {start!r} to {end!r} is not a number", []
    if last is not None and last != first:
        unit = f" {unit_text}" if unit_text else ""
        notes.append(f"SABIO-RK gives {label} {_number_cell(first)} to {_number_cell(last)}{unit} (a range)")
        request = single or f"state the single {label} these values apply at, or unknown"
        cell = f"{REVIEW_MARKER} SABIO-RK gives {label} {_number_cell(first)} to {_number_cell(last)}{unit}, a range; {request}"
        return cell, [_id_number(first), _id_number(last)]
    return _number_cell(first), [_id_number(first)]


_PH_LAW_CONDITION = (
    "state the single pH the pH-ionization case runs at, inside ph_min to ph_max in kinetics.csv (the law reads it)"
)


def _ph_law_problem(entry: _Entry) -> str:
    """Why an entry with pKa parameters cannot be mapped onto the pH-ionization form, or an empty string."""

    record = entry.record
    law = record.kinetic_law_type.strip() or "unnamed"
    pkas = [parameter.name.strip() for parameter in record.parameters if parameter.parameter_type.strip().casefold() == "pka"]
    formula = _text(_mapping(entry.raw.get("kineticlaw")).get("formula"))
    if "".join(formula.split()) != PH_IONIZATION_LAW_FORMULA:
        shown = "".join(formula.split()) or "no formula"
        return (
            f"kinetic law {law!r} has pKa parameters ({', '.join(pkas)}), but its formula ({shown}) is not the diprotic "
            "pH-ionization law FungMod implements, so its constants are not mapped onto that law's roles"
        )
    names: dict[str, list[SabioRKKineticParameter]] = {}
    for parameter in record.parameters:
        names.setdefault(parameter.name.strip(), []).append(parameter)
    problems: list[str] = []
    for name, (kind, _quantity) in PH_IONIZATION_LAW_PARAMETERS.items():
        found = names.get(name, [])
        if len(found) != 1:
            problems.append(f"{len(found)} parameters named {name}")
        elif found[0].parameter_type.strip().casefold() != kind:
            problems.append(f"{name} has type {found[0].parameter_type!r}")
    extra = [name for name in pkas if name not in PH_IONIZATION_LAW_PARAMETERS]
    if extra:
        problems.append(f"pKa parameters outside the law ({', '.join(extra)})")
    if problems:
        return (
            f"kinetic law {law!r} has the diprotic pH-ionization formula but not its parameters as FungMod maps them "
            f"({'; '.join(problems)})"
        )
    return ""


def _ph_fit_range(entry: _Entry) -> tuple[tuple[float, float] | None, str, str]:
    """The pH range an entry states for its pH-ionization law: (range, where it comes from, problem).

    The range is the start and end of the law's pH variable, or else of the
    assay pH. When both are given and differ, or neither is a range inside pH 0
    to 14, the range is None and ``problem`` says why.
    """

    candidates: list[tuple[tuple[float, float], str]] = []
    variables = [parameter for parameter in entry.record.parameters if parameter.parameter_type.strip().casefold() == "ph"]
    if len(variables) == 1:
        span = _span(variables[0].start_value, variables[0].end_value)
        if span is not None:
            candidates.append((span, "pH range of the law's pH variable (start and end values of parameter pH)"))
    assay = _mapping(_mapping(entry.raw.get("experimental_conditions")).get("envvar_ph"))
    span = _span(assay.get("start_value"), assay.get("end_value"))
    if span is not None:
        candidates.append((span, "assay pH range of the entry's experimental conditions"))
    if not candidates:
        return None, "", "SABIO-RK states no pH range for this entry"
    spans = {span for span, _origin in candidates}
    if len(spans) > 1:
        described = "; ".join(f"{_number_cell(lo)} to {_number_cell(hi)} ({origin})" for (lo, hi), origin in candidates)
        return None, "", f"SABIO-RK states two different pH ranges ({described})"
    (lower, upper), origin = candidates[0]
    if lower < _PH_RANGE_SCALE[0] or upper > _PH_RANGE_SCALE[1]:
        return None, "", f"the stated pH range {_number_cell(lower)} to {_number_cell(upper)} is outside pH 0 to 14"
    return (lower, upper), origin, ""


def _span(start: Any, end: Any) -> tuple[float, float] | None:
    first, last = _finite(start), _finite(end)
    if first is None or last is None or not first < last:
        return None
    return first, last


def _id_number(value: float) -> str:
    return _number_cell(value).replace("-", "minus").replace(".", "_")


def _product_proposal(record: SabioRKReactionRecord, substrate: str) -> tuple[str, str, str]:
    """(product name, yield text, problem) from the reaction stoichiometry of ``record``."""

    products = _unique(participant.compound_name for participant in record.products)
    if len(products) != 1:
        problem = (
            f"the reaction lists products {', '.join(products)}" if products else "the reaction lists no product"
        )
        return "", "", problem
    product = next(participant for participant in record.products if participant.compound_name == products[0])
    source = next(
        (participant for participant in record.substrates if participant.compound_name.casefold() == substrate.casefold()),
        None,
    )
    product_count = _finite(product.stoichiometry)
    substrate_count = None if source is None else _finite(source.stoichiometry)
    if product_count is None or substrate_count is None or product_count <= 0.0 or substrate_count <= 0.0:
        return products[0], "", "the reaction gives no numeric stoichiometry for the product and substrate"
    return products[0], _number_cell(product_count / substrate_count), ""


def _product_cells(
    substrate: str,
    proposals: Sequence[tuple[str, str, str]],
    registry_products: Sequence[str],
) -> tuple[str, str, str]:
    """Product and yield cells for one substrate row, and the decision text.

    The product is taken only when every reaction of the substrate names the
    same single product; the yield only when, in addition, every reaction gives
    the same numeric stoichiometric ratio. Otherwise the cell is a review field.
    """

    names = _unique(name for name, _value, _problem in proposals)
    yields = _unique(value for _name, value, _problem in proposals)
    problems = _unique(problem for _name, _value, problem in proposals)
    product_known = len(names) == 1 and all(name for name, _value, _problem in proposals)
    issues = [*problems]
    if len(names) > 1:
        issues.append(f"its reactions name different products ({', '.join(names)})")
    if len(yields) > 1:
        issues.append(f"its reactions give different yields ({', '.join(yields)})")
    product = ""
    if product_known:
        name = names[0]
        if registry_products:
            listed = _registry_product(name, registry_products)
            if listed is None:
                issues.append(
                    f"SABIO-RK names {name!r}, which is not among the registry substrate's products "
                    f"{list(registry_products)}"
                )
            product = listed or ""
        else:
            product = stable_sabiork_token(name)
    detail = "; ".join(issues)
    yield_known = bool(product) and len(yields) == 1 and all(value for _name, value, _problem in proposals)
    product_cell = product or f"{REVIEW_MARKER} product of {substrate}; {detail or 'not given'}"
    yield_cell = yields[0] if yield_known else f"{REVIEW_MARKER} mol of product per mol of {substrate}; {detail or 'not given'}"
    if product and yield_known:
        note = (
            f"Product of {substrate}: `{product}` (SABIO-RK {names[0]!r}) with yield {yields[0]} mol/mol from the "
            "reaction stoichiometry (product coefficient divided by the substrate coefficient)."
        )
    else:
        note = f"Product of {substrate}: {detail or 'not given'}; the product and yield are left for review."
    return product_cell, yield_cell, note


def _registry_product(name: str, listed: Sequence[str]) -> str | None:
    token = stable_sabiork_token(name)
    matches = [item for item in listed if stable_sabiork_token(item) == token]
    return matches[0] if len(matches) == 1 else None


def _method(
    record: SabioRKReactionRecord,
    parameter: SabioRKKineticParameter,
    quantity: str,
    comment: str,
    *,
    exact: bool,
) -> str:
    law = record.kinetic_law_type.strip()
    parts = [f"SABIO-RK kinetic law {record.entry_id}" + (f", {law}" if law else "")]
    name = parameter.name.strip()
    if quantity in {"substrate_initial_concentration", "enzyme_concentration"}:
        what = "substrate" if quantity == "substrate_initial_concentration" else "enzyme"
        parts.append(
            f"parameter {name or 'concentration'}: {'range of the ' if not exact else ''}{what} concentration "
            "reported for the assay"
        )
    elif name and name.casefold() != parameter.parameter_type.strip().casefold():
        parts.append(f"parameter {name}")
    if comment:
        parts.append(f"SABIO-RK comment: {comment}")
    return "; ".join(parts)


def _source_text(record: SabioRKReactionRecord) -> str:
    publication = record.publication
    authors = [part.strip() for part in _text(publication.get("author")).split(",") if part.strip()]
    first = authors[0] + (" et al." if len(authors) > 1 else "") if authors else ""
    year = _text(publication.get("year")).strip()
    pubmed = _text(publication.get("pubmed_id")).strip()
    details = ", ".join(
        part for part in (" ".join(item for item in (first, year) if item), f"PMID {pubmed}" if pubmed else "") if part
    )
    return f"SABIO-RK EntryID {record.entry_id}" + (f" ({details})" if details else " (no publication given)")


def _evidence_text(entry: _Entry) -> str:
    record = entry.record
    enzyme = _mapping(entry.raw.get("enzyme_description"))
    parts = [f"EntryID {record.entry_id}: {record.enzyme_name or 'enzyme'}"]
    if record.ec_number:
        parts[0] += f", EC {record.ec_number}"
    variant = " ".join(
        item for item in (_text(enzyme.get("wildtype")).strip().lower(), _text(enzyme.get("mutant_spec")).strip()) if item
    )
    if variant:
        parts.append(variant)
    if enzyme.get("is_recombinant") is True:
        parts.append("recombinant")
    host = _text(enzyme.get("expressed_in")).strip()
    if host:
        parts.append(f"expressed in {host}")
    return ", ".join(parts)


def _raw_parameter_comments(raw: Mapping[str, Any], count: int) -> list[str]:
    raw_parameters = _mapping(raw.get("kineticlaw")).get("parameter")
    if isinstance(raw_parameters, Mapping):
        items: list[Any] = [raw_parameters]
    elif isinstance(raw_parameters, list):
        items = [item for item in raw_parameters if isinstance(item, Mapping)]
    else:
        items = []
    comments = [_text(item.get("comment")).strip() for item in items]
    comments = ["" if comment in _MISSING_TEXT else comment for comment in comments]
    return comments if len(comments) == count else [""] * count


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
            for column in _TABLE_COLUMNS[name]:
                cell = row.get(column, "")
                if cell.startswith(REVIEW_MARKER):
                    fields.append({"file": name, "row": index + 2, "column": column, "note": cell})
    return tuple(fields)


def _kinetics_row(
    *,
    strain_id: str,
    enzyme_class: str,
    substrate_id: str,
    condition_id: str,
    quantity: str,
    value: str,
    lower: str,
    upper: str,
    units: str,
    evidence_type: str,
    method: str,
    source: str,
    sd: str,
) -> dict[str, str]:
    return {
        "strain_id": strain_id,
        "enzyme_class": enzyme_class,
        "substrate_id": substrate_id,
        "condition_id": condition_id,
        "quantity": quantity,
        "value": value,
        "lower": lower,
        "upper": upper,
        "units": units,
        "evidence_type": evidence_type,
        "method": method,
        "source": source,
        "sd": sd,
    }


def _row_amount(row: Mapping[str, str]) -> str:
    return row["value"] or f"{row['lower']} to {row['upper']}"


def _value_text(parameter: SabioRKKineticParameter) -> str:
    start, end = parameter.start_value, parameter.end_value
    if start is None:
        return ""
    if end is None or end == start:
        return str(start)
    return f"{start} to {end}"


def _parses(units: str) -> bool:
    try:
        Q_(1.0, units)
    except Exception:  # the unit registry raises several unrelated exception types for bad strings
        return False
    return True


def _resolves(resolve: Any, term: str) -> bool:
    try:
        resolve(term)
    except ResolutionError:
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


def _finite_or_raise(value: Any) -> float:
    number = _finite(value)
    if number is None:
        raise UserTablesSourceError(f"{value!r} is not a finite number.")
    return number


def _number_cell(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _user_class_text(class_ids: Sequence[str]) -> str:
    """How a reason names user-defined classes that share an EC number."""

    plural = "es" if len(class_ids) > 1 else ""
    return f"user-defined enzyme class{plural} {', '.join(repr(item) for item in class_ids)} of enzyme_classes.csv"


def _norm_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _semicolon_cells(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in text.split(";") if item.strip()))


def _unique_items(values: Iterable[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    return list(dict.fromkeys(values))


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


def _manifest_text(manifest: Mapping[str, Any]) -> str:
    return yaml.safe_dump(_plain(manifest), sort_keys=False, allow_unicode=True, width=100)


def _csv_text(columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()


__all__ = [
    "DESIGN_QUANTITIES",
    "PH_IONIZATION_LAW_FORMULA",
    "PH_IONIZATION_LAW_PARAMETERS",
    "SABIORK_TEMPERATURE_UNITS",
    "SABIORK_UNIT_SPELLINGS",
    "USER_TABLE_PROVIDERS",
    "UserTablesDraft",
    "UserTablesSourceError",
    "user_tables_from_sabiork",
]
