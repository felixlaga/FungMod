"""Read a UniProtKB TSV export and resolve its proteins to FungMod enzyme classes.

UniProt exports UniProtKB entries as tab-separated text whose first row holds
UniProt's own column names. This module reads the columns that bear on enzyme
classes:

``Entry`` (required)
    The accession. Accessions must be nonblank and unique; their format is not
    checked.
``EC number`` and ``CAZy`` (at least one of them)
    ``EC number`` holds EC numbers separated by ``"; "``. A partial EC number
    such as ``3.2.1.-`` is kept as partial and never completed or resolved.
    ``CAZy`` holds CAZy family identifiers separated by ``";"``, usually with
    a trailing ``";"``; a subfamily suffix (``GH5_5``) is dropped, as in the
    dbCAN route, because the family map is keyed on families.
``Entry Name``, ``Protein names``, ``Gene Names``, ``Organism``, ``Organism (ID)``, ``Reviewed``
    Optional and reported. One file covers one organism: more than one
    ``Organism (ID)`` (or, without that column, more than one ``Organism``) is
    refused, because mixed sets are not supported. ``Reviewed`` must read
    ``reviewed`` or ``unreviewed`` when given.

Any other column is allowed and ignored; ``UniprotProteome.ignored_columns``
names them.

Resolution goes through the existing machinery only. The CAZy families of
each protein are resolved by ``CapabilityResolver`` with the curated family
map, exactly as for a dbCAN annotation, and each complete EC number by
``RegistryResolver.resolve_enzyme_class`` against the registry, the EC lookup
the rest of FungMod uses. An EC number therefore resolves only to a class
that has a registry record; FungMod has no EC-to-class table of its own.

When one protein carries both a mapped CAZy family and a complete EC number,
the two annotations are compared on the classes the EC side can speak about:
every class one of the EC numbers resolves to, and every registry class whose
record carries an EC number. They disagree when such a class is named by one
side and not by the other. A disagreeing protein supports no class: it is
reported with both sides (``EcCazyDisagreement``) and FungMod does not choose
between them. A protein whose families map to classes and whose complete EC
numbers resolve to nothing, while none of those classes carries a registry EC
number, is not a disagreement: the EC numbers cannot be compared and are
listed as unresolved.

The result states which classes the proteome plausibly encodes, never a rate,
kinetic constant, expression level or secretion.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from fungal_model.capability.resolution import (
    DIAGNOSTIC,
    POLYSPECIFIC,
    CapabilityResolutionError,
    CapabilityResolver,
    CazymeAnnotation,
    ResolvedCapability,
)
from fungal_model.registry.resolver import AmbiguousResolutionError, RegistryResolver, ResolutionError
from fungal_model.registry.store import FungModRegistry

#: UniProt's column name for the accession; the only required column.
UNIPROT_ENTRY_COLUMN = "Entry"
UNIPROT_EC_COLUMN = "EC number"
UNIPROT_CAZY_COLUMN = "CAZy"
UNIPROT_ORGANISM_COLUMN = "Organism"
UNIPROT_ORGANISM_ID_COLUMN = "Organism (ID)"
UNIPROT_REVIEWED_COLUMN = "Reviewed"
#: The UniProt columns this module reads, in UniProt's export order. Others are ignored.
UNIPROT_COLUMNS = (
    UNIPROT_ENTRY_COLUMN,
    "Entry Name",
    "Protein names",
    "Gene Names",
    UNIPROT_ORGANISM_COLUMN,
    UNIPROT_ORGANISM_ID_COLUMN,
    UNIPROT_EC_COLUMN,
    UNIPROT_CAZY_COLUMN,
    UNIPROT_REVIEWED_COLUMN,
)
#: The columns that carry evidence for an enzyme class; a file needs at least one.
UNIPROT_EVIDENCE_COLUMNS = (UNIPROT_EC_COLUMN, UNIPROT_CAZY_COLUMN)

REVIEWED = "reviewed"
UNREVIEWED = "unreviewed"
#: Review status of an entry whose export has no ``Reviewed`` column, or a blank cell.
REVIEW_NOT_STATED = "not_stated"

#: How a protein supports a class: both annotations, the CAZy families only, the EC numbers only.
BASIS_CAZY_AND_EC = "cazy_and_ec"
BASIS_CAZY = "cazy"
BASIS_EC = "ec"
SUPPORT_BASES = (BASIS_CAZY_AND_EC, BASIS_CAZY, BASIS_EC)

#: Protein-level outcomes counted in ``ProteomeResolution.protein_counts``.
PROTEIN_OUTCOMES = (BASIS_CAZY_AND_EC, BASIS_CAZY, BASIS_EC, "disagreement", "no_class")

COMPARISON_RULE = (
    "A protein with a mapped CAZy family and a complete EC number is compared on every class one of its EC numbers "
    "resolves to through the registry and every registry class whose record carries an EC number; the annotations "
    "disagree when such a class is named by one side and not the other. A disagreeing protein supports no class and "
    "is listed with both sides; FungMod does not choose between them. EC numbers that resolve to no class and touch "
    "no such class cannot be compared and are listed as unresolved. Partial EC numbers never resolve."
)
CLAIM_BOUNDARY = (
    "Enzyme classes inferred from a UniProt proteome state which proteins the organism's annotated proteome "
    "contains, not what it expresses, secretes or how fast; most UniProtKB annotation is automatic (unreviewed "
    "TrEMBL entries), CAZy cross-references cover only part of the proteome, and no rate, kinetic constant or "
    "expression level is taken from the proteome."
)

_EC_NUMBER = re.compile(r"^\d+\.(?:\d+|-)\.(?:\d+|-)\.(?:n?\d+|-)$")
_CAZY_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*$")
_CAZY_FAMILY = re.compile(r"^(GH|GT|PL|CE|AA|CBM)(\d+)(?:_\d+)?$")
_TAXONOMY_ID = re.compile(r"^\d+$")
_GZIP_MAGIC = b"\x1f\x8b"


@dataclass(frozen=True)
class UniprotEntry:
    """One UniProtKB entry of an export, with its EC numbers and CAZy families split out."""

    accession: str
    line: int
    entry_name: str = ""
    protein_names: str = ""
    gene_names: str = ""
    organism: str = ""
    organism_id: str = ""
    reviewed: str = REVIEW_NOT_STATED
    ec_numbers: tuple[str, ...] = ()
    partial_ec_numbers: tuple[str, ...] = ()
    cazy_families: tuple[str, ...] = ()

    @property
    def has_evidence(self) -> bool:
        return bool(self.ec_numbers or self.partial_ec_numbers or self.cazy_families)


@dataclass(frozen=True)
class UniprotProteome:
    """A UniProtKB TSV export read entry by entry.

    ``columns`` is the header as read, ``read_columns`` the UniProt columns of
    ``UNIPROT_COLUMNS`` it contains and ``ignored_columns`` the others.
    """

    columns: tuple[str, ...]
    read_columns: tuple[str, ...]
    ignored_columns: tuple[str, ...]
    entries: tuple[UniprotEntry, ...]

    @property
    def organism_id(self) -> str:
        """The one NCBI taxonomy id of the export, or an empty string when none is given."""

        return next((entry.organism_id for entry in self.entries if entry.organism_id), "")

    @property
    def organism(self) -> str:
        """The one organism name of the export, or an empty string when none is given."""

        return next((entry.organism for entry in self.entries if entry.organism), "")

    @property
    def has_review_column(self) -> bool:
        return UNIPROT_REVIEWED_COLUMN in self.read_columns

    def review_counts(self) -> dict[str, int]:
        """Entries per review status (``reviewed``, ``unreviewed``, ``not_stated``)."""

        counts = {REVIEWED: 0, UNREVIEWED: 0, REVIEW_NOT_STATED: 0}
        for entry in self.entries:
            counts[entry.reviewed] += 1
        return counts

    def family_accessions(self) -> dict[str, tuple[str, ...]]:
        """Each CAZy family with the accessions carrying it, families sorted, accessions in file order."""

        return _grouped((family, entry.accession) for entry in self.entries for family in entry.cazy_families)

    def ec_accessions(self) -> dict[str, tuple[str, ...]]:
        """Each complete EC number with the accessions carrying it."""

        return _grouped((ec, entry.accession) for entry in self.entries for ec in entry.ec_numbers)

    def partial_ec_accessions(self) -> dict[str, tuple[str, ...]]:
        """Each partial EC number with the accessions carrying it."""

        return _grouped((ec, entry.accession) for entry in self.entries for ec in entry.partial_ec_numbers)


def decode_uniprot_tsv(data: bytes, *, source: str) -> str:
    """Decode the bytes of a UniProt TSV export as UTF-8 text, refusing a compressed or non-UTF-8 file."""

    if data.startswith(_GZIP_MAGIC):
        raise CapabilityResolutionError(
            f"{source} is gzip-compressed; download the UniProt TSV uncompressed or decompress it first."
        )
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CapabilityResolutionError(f"{source} is not UTF-8 text: {exc}") from exc


def parse_uniprot_tsv(text: str, *, source: str) -> UniprotProteome:
    """Parse the text of a UniProtKB TSV export.

    ``source`` names the file in error messages. Refuses a missing header, a
    header without ``Entry`` or without both ``EC number`` and ``CAZy``, a
    repeated header column, a row wider than the header, a blank or repeated
    accession, a malformed EC number or CAZy identifier, a ``Reviewed`` cell
    other than ``reviewed`` or ``unreviewed``, a non-numeric ``Organism (ID)``,
    more than one organism in the file, and a file in which no entry carries an
    EC number or a CAZy family.
    """

    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
    header = next(reader, None)
    if header is None or not any(cell.strip() for cell in header):
        raise CapabilityResolutionError(f"{source} has no header row.")
    names = tuple(cell.strip() for cell in header)
    duplicates = sorted({name for name in names if name and names.count(name) > 1})
    if duplicates:
        raise CapabilityResolutionError(f"{source} repeats the header column(s) {duplicates}.")
    if UNIPROT_ENTRY_COLUMN not in names:
        raise CapabilityResolutionError(
            f"{source} does not have a UniProt TSV header: it needs the column {UNIPROT_ENTRY_COLUMN!r} (the "
            f"accession) separated by tabs; found {names}."
        )
    if not any(column in names for column in UNIPROT_EVIDENCE_COLUMNS):
        raise CapabilityResolutionError(
            f"{source} has neither the {UNIPROT_EC_COLUMN!r} nor the {UNIPROT_CAZY_COLUMN!r} column, so it holds "
            "nothing that resolves to an enzyme class; export at least one of them."
        )
    read_columns = tuple(column for column in UNIPROT_COLUMNS if column in names)
    ignored = tuple(name for name in names if name not in UNIPROT_COLUMNS)
    index = {column: names.index(column) for column in read_columns}
    entries: list[UniprotEntry] = []
    seen: dict[str, int] = {}
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        if len(cells) > len(names):
            raise CapabilityResolutionError(f"{source} line {line} has more cells than the header.")

        def cell(column: str, cells: Sequence[str] = cells) -> str:
            position = index.get(column)
            return cells[position].strip() if position is not None and position < len(cells) else ""

        accession = cell(UNIPROT_ENTRY_COLUMN)
        if not accession:
            raise CapabilityResolutionError(f"{source} line {line} has no accession in {UNIPROT_ENTRY_COLUMN!r}.")
        if any(character.isspace() for character in accession):
            raise CapabilityResolutionError(f"{source} line {line} has an accession with whitespace: {accession!r}.")
        if accession in seen:
            raise CapabilityResolutionError(
                f"{source} line {line} repeats accession {accession!r} from line {seen[accession]}; an export has "
                "one row per entry."
            )
        seen[accession] = line
        complete, partial = _ec_numbers(cell(UNIPROT_EC_COLUMN), source=source, line=line)
        entries.append(
            UniprotEntry(
                accession=accession,
                line=line,
                entry_name=cell("Entry Name"),
                protein_names=cell("Protein names"),
                gene_names=cell("Gene Names"),
                organism=cell(UNIPROT_ORGANISM_COLUMN),
                organism_id=_organism_id(cell(UNIPROT_ORGANISM_ID_COLUMN), source=source, line=line),
                reviewed=_reviewed(cell(UNIPROT_REVIEWED_COLUMN), source=source, line=line),
                ec_numbers=complete,
                partial_ec_numbers=partial,
                cazy_families=_cazy_families(cell(UNIPROT_CAZY_COLUMN), source=source, line=line),
            )
        )
    _refuse_mixed_organisms(entries, read_columns, source=source)
    if not any(entry.has_evidence for entry in entries):
        raise CapabilityResolutionError(
            f"{source} has no entry with an EC number or a CAZy family, so nothing resolves to an enzyme class."
        )
    return UniprotProteome(
        columns=names,
        read_columns=read_columns,
        ignored_columns=ignored,
        entries=tuple(entries),
    )


def _ec_numbers(text: str, *, source: str, line: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    complete: list[str] = []
    partial: list[str] = []
    for token in (part.strip() for part in text.split(";")):
        if not token:
            continue
        if not _EC_NUMBER.fullmatch(token):
            raise CapabilityResolutionError(
                f"{source} line {line} has {token!r} in {UNIPROT_EC_COLUMN!r}, which is not an EC number such as "
                "3.2.1.4 or 3.2.1.-; separate several EC numbers with '; '."
            )
        target = partial if "-" in token else complete
        if token not in target:
            target.append(token)
    return tuple(complete), tuple(partial)


def _cazy_families(text: str, *, source: str, line: int) -> tuple[str, ...]:
    families: set[str] = set()
    for token in (part.strip() for part in text.split(";")):
        if not token:
            continue
        if not _CAZY_IDENTIFIER.fullmatch(token):
            raise CapabilityResolutionError(
                f"{source} line {line} has {token!r} in {UNIPROT_CAZY_COLUMN!r}, which is not a CAZy identifier such "
                "as GH7 or CBM1; separate several identifiers with ';'."
            )
        upper = token.upper()
        match = _CAZY_FAMILY.fullmatch(upper)
        # Subfamily suffixes are dropped, as in the dbCAN route: GH5_5 -> GH5. Other identifiers stay as given
        # (upper case) and are reported as unmapped when the family map has no entry for them.
        families.add(f"{match.group(1)}{match.group(2)}" if match else upper)
    return tuple(sorted(families))


def _organism_id(text: str, *, source: str, line: int) -> str:
    if text and not _TAXONOMY_ID.fullmatch(text):
        raise CapabilityResolutionError(
            f"{source} line {line} has {text!r} in {UNIPROT_ORGANISM_ID_COLUMN!r}, which is not an NCBI taxonomy id."
        )
    return text


def _reviewed(text: str, *, source: str, line: int) -> str:
    if not text:
        return REVIEW_NOT_STATED
    value = text.lower()
    if value not in (REVIEWED, UNREVIEWED):
        raise CapabilityResolutionError(
            f"{source} line {line} has {text!r} in {UNIPROT_REVIEWED_COLUMN!r}; UniProt writes 'reviewed' or "
            "'unreviewed'."
        )
    return value


def _refuse_mixed_organisms(entries: Sequence[UniprotEntry], read_columns: Sequence[str], *, source: str) -> None:
    if UNIPROT_ORGANISM_ID_COLUMN in read_columns:
        column = UNIPROT_ORGANISM_ID_COLUMN
        values = sorted({entry.organism_id for entry in entries if entry.organism_id})
    else:
        column = UNIPROT_ORGANISM_COLUMN
        values = sorted({entry.organism for entry in entries if entry.organism})
    if len(values) > 1:
        shown = ", ".join(values[:5]) + (f" and {len(values) - 5} more" if len(values) > 5 else "")
        raise CapabilityResolutionError(
            f"{source} holds entries of {len(values)} organisms in {column!r} ({shown}). One export describes one "
            "strain's proteome; mixed sets are not supported, so export one organism (for example one UniProt "
            "proteome) per file."
        )


# ---------------------------------------------------------------------------
# Resolution


@dataclass(frozen=True)
class EcNumberResolution:
    """One complete EC number and the registry enzyme class it resolves to, or why it resolves to none."""

    ec_number: str
    enzyme_class: str | None
    matched_field: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ProteomeClassSupport:
    """One enzyme class supported by proteins of a proteome, with the accessions and evidence behind it.

    ``specificity`` is the family-map specificity over the supporting CAZy
    families (``family_diagnostic`` when any is diagnostic), or ``None`` when
    only EC numbers support the class. ``modellable`` is true when the class
    has a record in the registry the resolver was built from.
    """

    enzyme_class: str
    modellable: bool
    specificity: str | None
    families: tuple[str, ...]
    ec_numbers: tuple[str, ...]
    accessions: tuple[str, ...]
    accessions_by_basis: Mapping[str, tuple[str, ...]]
    reviewed_accessions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "enzyme_class": self.enzyme_class,
            "families": list(self.families),
            "ec_numbers": list(self.ec_numbers),
            "accessions": list(self.accessions),
            "accession_count": len(self.accessions),
            "accessions_by_basis": {basis: list(items) for basis, items in self.accessions_by_basis.items()},
            "reviewed_accessions": list(self.reviewed_accessions),
            "specificity": self.specificity,
        }


@dataclass(frozen=True)
class EcCazyDisagreement:
    """A protein whose CAZy families and EC numbers name different classes; it supports neither side."""

    accession: str
    reviewed: str
    cazy_families: tuple[str, ...]
    cazy_classes: tuple[str, ...]
    ec_numbers: tuple[str, ...]
    ec_classes: tuple[str, ...]
    contested_classes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "reviewed": self.reviewed,
            "cazy_families": list(self.cazy_families),
            "cazy_classes": list(self.cazy_classes),
            "ec_numbers": list(self.ec_numbers),
            "ec_classes": list(self.ec_classes),
            "contested_classes": list(self.contested_classes),
            "outcome": "supports no class; both annotations are reported and neither is chosen",
        }


@dataclass(frozen=True)
class ProteomeResolution:
    """The auditable result of resolving one UniProt export.

    ``capabilities`` are the classes supported by at least one protein that
    is not in disagreement, sorted by class. ``unmapped_families``,
    ``unresolved_ec_numbers`` and ``partial_ec_numbers`` map each item to the
    accessions carrying it; ``disagreements`` lists the proteins whose two
    annotations differ.
    """

    proteome: UniprotProteome
    capabilities: tuple[ProteomeClassSupport, ...]
    unmapped_families: Mapping[str, tuple[str, ...]]
    unresolved_ec_numbers: Mapping[str, tuple[str, ...]]
    unresolved_ec_reasons: Mapping[str, str]
    partial_ec_numbers: Mapping[str, tuple[str, ...]]
    disagreements: tuple[EcCazyDisagreement, ...]
    ec_comparable_classes: tuple[str, ...]
    protein_counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def modellable_enzyme_classes(self) -> tuple[str, ...]:
        return tuple(item.enzyme_class for item in self.capabilities if item.modellable)

    @property
    def capabilities_without_model(self) -> tuple[str, ...]:
        return tuple(item.enzyme_class for item in self.capabilities if not item.modellable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": [item.to_dict() for item in self.capabilities],
            "unmapped_families": _accession_lists(self.unmapped_families, "family"),
            "unresolved_ec_numbers": [
                {**entry, "reason": self.unresolved_ec_reasons[entry["ec_number"]]}
                for entry in _accession_lists(self.unresolved_ec_numbers, "ec_number")
            ],
            "partial_ec_numbers": _accession_lists(self.partial_ec_numbers, "ec_number"),
            "ec_cazy_disagreements": [item.to_dict() for item in self.disagreements],
            "ec_comparable_classes": list(self.ec_comparable_classes),
            "protein_counts": dict(self.protein_counts),
            "comparison_rule": COMPARISON_RULE,
            "claim_boundary": CLAIM_BOUNDARY,
        }


def resolve_uniprot_proteome(
    proteome: UniprotProteome,
    *,
    capability_resolver: CapabilityResolver,
    registry: FungModRegistry,
    organism: str,
    proteome_source: str,
    annotation_tool: str,
    annotation_tool_version: str,
    annotation_date: str,
) -> ProteomeResolution:
    """Resolve each protein's CAZy families and complete EC numbers, then gather the supported classes.

    The families of each protein go through ``capability_resolver`` (one
    ``CazymeAnnotation`` per protein, carrying the provenance arguments), and
    each complete EC number through ``RegistryResolver(registry)``. The
    comparison rule of the module docstring decides which classes a protein
    supports. ``capability_resolver`` should be built on the same registry so
    that ``modellable`` and the EC lookup agree.
    """

    ec_resolver = RegistryResolver(registry)
    ec_cache: dict[str, EcNumberResolution] = {}
    comparable = frozenset(record_id for record_id, record in registry.enzyme_classes.items() if record.ec_number)
    support: dict[str, dict[str, Any]] = {}
    unmapped: list[tuple[str, str]] = []
    unresolved: list[tuple[str, str]] = []
    disagreements: list[EcCazyDisagreement] = []
    counts: dict[str, int] = dict.fromkeys(PROTEIN_OUTCOMES, 0)
    for entry in proteome.entries:
        if not entry.has_evidence:
            continue
        cazy: dict[str, ResolvedCapability] = {}
        if entry.cazy_families:
            resolution = capability_resolver.resolve(
                CazymeAnnotation(
                    organism=organism,
                    families=entry.cazy_families,
                    genome_accession=proteome_source,
                    annotation_tool=annotation_tool,
                    annotation_tool_version=annotation_tool_version,
                    annotation_date=annotation_date,
                    notes=f"UniProt accession {entry.accession}",
                )
            )
            cazy = {capability.enzyme_class: capability for capability in resolution.capabilities}
            unmapped.extend((family, entry.accession) for family in resolution.unmapped_families)
        ec_classes: dict[str, list[str]] = {}
        for ec in entry.ec_numbers:
            resolved = ec_cache.get(ec)
            if resolved is None:
                resolved = ec_cache[ec] = _resolve_ec(ec, ec_resolver)
            if resolved.enzyme_class is None:
                unresolved.append((ec, entry.accession))
            else:
                ec_classes.setdefault(resolved.enzyme_class, []).append(ec)
        contested: tuple[str, ...] = ()
        if cazy and entry.ec_numbers:
            contested = tuple(
                sorted(
                    enzyme_class
                    for enzyme_class in comparable | set(ec_classes)
                    if (enzyme_class in cazy) != (enzyme_class in ec_classes)
                )
            )
        if contested:
            counts["disagreement"] += 1
            disagreements.append(
                EcCazyDisagreement(
                    accession=entry.accession,
                    reviewed=entry.reviewed,
                    cazy_families=entry.cazy_families,
                    cazy_classes=tuple(sorted(cazy)),
                    ec_numbers=entry.ec_numbers,
                    ec_classes=tuple(sorted(ec_classes)),
                    contested_classes=contested,
                )
            )
            continue
        classes = sorted(set(cazy) | set(ec_classes))
        if not classes:
            counts["no_class"] += 1
            continue
        bases: set[str] = set()
        for enzyme_class in classes:
            basis = (
                BASIS_CAZY_AND_EC
                if enzyme_class in cazy and enzyme_class in ec_classes
                else BASIS_CAZY
                if enzyme_class in cazy
                else BASIS_EC
            )
            bases.add(basis)
            item = support.setdefault(
                enzyme_class,
                {"families": set(), "ec_numbers": set(), "specificities": set(), "accessions": {}, "reviewed": []},
            )
            if enzyme_class in cazy:
                item["families"].update(cazy[enzyme_class].families)
                item["specificities"].add(cazy[enzyme_class].specificity)
            item["ec_numbers"].update(ec_classes.get(enzyme_class, ()))
            item["accessions"][entry.accession] = basis
            if entry.reviewed == REVIEWED:
                item["reviewed"].append(entry.accession)
        counts[next(basis for basis in SUPPORT_BASES if basis in bases)] += 1

    capabilities = tuple(
        ProteomeClassSupport(
            enzyme_class=enzyme_class,
            modellable=enzyme_class in capability_resolver.registry_enzyme_classes,
            specificity=_specificity(item["specificities"]),
            families=tuple(sorted(item["families"])),
            ec_numbers=tuple(sorted(item["ec_numbers"])),
            accessions=tuple(item["accessions"]),
            accessions_by_basis=MappingProxyType(
                {
                    basis: tuple(accession for accession, given in item["accessions"].items() if given == basis)
                    for basis in SUPPORT_BASES
                }
            ),
            reviewed_accessions=tuple(item["reviewed"]),
        )
        for enzyme_class, item in sorted(support.items())
    )
    unresolved_groups = _grouped(unresolved)
    return ProteomeResolution(
        proteome=proteome,
        capabilities=capabilities,
        unmapped_families=MappingProxyType(_grouped(unmapped)),
        unresolved_ec_numbers=MappingProxyType(unresolved_groups),
        unresolved_ec_reasons=MappingProxyType({ec: ec_cache[ec].reason for ec in unresolved_groups}),
        partial_ec_numbers=MappingProxyType(proteome.partial_ec_accessions()),
        disagreements=tuple(disagreements),
        ec_comparable_classes=tuple(sorted(comparable)),
        protein_counts=MappingProxyType(counts),
    )


def _resolve_ec(ec: str, resolver: RegistryResolver) -> EcNumberResolution:
    try:
        resolved = resolver.resolve_enzyme_class(ec)
    except AmbiguousResolutionError as exc:
        candidates = ", ".join(sorted(candidate.record_id for candidate in exc.candidates))
        return EcNumberResolution(
            ec,
            None,
            reason=f"ambiguous in the registry (classes {candidates}); FungMod does not choose one",
        )
    except ResolutionError:
        return EcNumberResolution(ec, None, reason="no registry enzyme class carries this EC number")
    return EcNumberResolution(ec, resolved.record_id, matched_field=resolved.matched_field)


def _specificity(specificities: set[str]) -> str | None:
    if DIAGNOSTIC in specificities:
        return DIAGNOSTIC
    if POLYSPECIFIC in specificities:
        return POLYSPECIFIC
    return None


def _grouped(pairs: Iterable[tuple[str, str]]) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for key, accession in pairs:
        accessions = groups.setdefault(key, [])
        if accession not in accessions:
            accessions.append(accession)
    return {key: tuple(groups[key]) for key in sorted(groups)}


def _accession_lists(groups: Mapping[str, tuple[str, ...]], key: str) -> list[dict[str, Any]]:
    return [
        {key: name, "accessions": list(accessions), "accession_count": len(accessions)}
        for name, accessions in groups.items()
    ]


__all__ = [
    "BASIS_CAZY",
    "BASIS_CAZY_AND_EC",
    "BASIS_EC",
    "CLAIM_BOUNDARY",
    "COMPARISON_RULE",
    "PROTEIN_OUTCOMES",
    "REVIEWED",
    "REVIEW_NOT_STATED",
    "SUPPORT_BASES",
    "UNIPROT_CAZY_COLUMN",
    "UNIPROT_COLUMNS",
    "UNIPROT_EC_COLUMN",
    "UNIPROT_ENTRY_COLUMN",
    "UNIPROT_EVIDENCE_COLUMNS",
    "UNIPROT_ORGANISM_COLUMN",
    "UNIPROT_ORGANISM_ID_COLUMN",
    "UNIPROT_REVIEWED_COLUMN",
    "UNREVIEWED",
    "EcCazyDisagreement",
    "EcNumberResolution",
    "ProteomeClassSupport",
    "ProteomeResolution",
    "UniprotEntry",
    "UniprotProteome",
    "decode_uniprot_tsv",
    "parse_uniprot_tsv",
    "resolve_uniprot_proteome",
]
