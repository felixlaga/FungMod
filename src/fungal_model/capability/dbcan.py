"""Parse dbCAN annotation output into a provenance-bearing CAZyme annotation.

dbCAN3 writes a tab-separated ``overview.txt`` with one row per predicted gene
and one column per prediction tool. Families appear with optional subfamily
suffixes and residue ranges, for example ``GH5_5(123-456)``. Only the family
prefix is retained here, because the FungMod family map is keyed on families.

Provenance is not inferred from the file. The organism, genome accession, tool
version, and annotation date must be supplied by the caller, because the
overview file does not record them and a capability result that cannot be traced
to a specific genome and tool version is not reproducible.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from fungal_model.capability.resolution import CazymeAnnotation, CapabilityResolutionError

#: Tool columns that may carry family calls, in dbCAN3 overview.txt.
TOOL_COLUMNS = ("HMMER", "dbCAN_sub", "DIAMOND", "eCAMI", "Hotpep")

#: The gene identifier column of dbCAN overview.txt.
GENE_ID_COLUMN = "Gene ID"

#: A CAZy family prefix: letters then digits, e.g. GH5, AA9, CE1, PL1, GT2, CBM1.
_FAMILY = re.compile(r"^(GH|GT|PL|CE|AA|CBM)(\d+)")

_ABSENT = {"", "-", "n/a", "na", "null"}


def _families_in_cell(cell: str) -> set[str]:
    found: set[str] = set()
    if cell.strip().lower() in _ABSENT:
        return found
    # Split on the separators dbCAN uses between multiple calls in one cell.
    for token in re.split(r"[+|,;\s]+", cell.strip()):
        if not token:
            continue
        # Drop residue ranges and subfamily suffixes: GH5_5(123-456) -> GH5
        head = token.split("(", 1)[0]
        match = _FAMILY.match(head.strip().upper())
        if match:
            found.add(f"{match.group(1)}{match.group(2)}")
    return found


def families_from_overview(path: str | Path, *, tool_columns: Iterable[str] = TOOL_COLUMNS) -> tuple[str, ...]:
    """Return the distinct CAZy families called anywhere in a dbCAN overview file."""

    overview = Path(path)
    text = overview.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    if reader.fieldnames is None:
        raise CapabilityResolutionError(f"{overview} has no header row.")
    present = [c for c in tool_columns if c in reader.fieldnames]
    if not present:
        raise CapabilityResolutionError(
            f"{overview} contains none of the expected dbCAN tool columns {tuple(tool_columns)}; "
            f"found {tuple(reader.fieldnames)}."
        )
    families: set[str] = set()
    for row in reader:
        for column in present:
            families |= _families_in_cell(row.get(column) or "")
    if not families:
        raise CapabilityResolutionError(f"{overview} yielded no CAZy family calls.")
    return tuple(sorted(families))


@dataclass(frozen=True)
class OverviewGene:
    """The family calls of one gene in a dbCAN overview, per tool column."""

    gene_id: str
    calls: Mapping[str, tuple[str, ...]]

    def tools_calling(self, family: str) -> int:
        """Return how many tool columns call ``family`` for this gene."""

        return sum(1 for families in self.calls.values() if family in families)


@dataclass(frozen=True)
class DbcanOverview:
    """A dbCAN overview parsed per gene, so that families can be counted in genes.

    ``tool_columns`` are the tool columns present in the file, in
    ``TOOL_COLUMNS`` order. ``genes`` hold every gene row with its per-tool
    family calls (genes without any call included).
    """

    tool_columns: tuple[str, ...]
    genes: tuple[OverviewGene, ...]

    def family_genes(self, *, min_tools_agreeing: int | None = None) -> dict[str, tuple[str, ...]]:
        """Return each called family with the genes that support it, families sorted.

        Without ``min_tools_agreeing`` a family counts for a gene when any tool
        column calls it, which is the rule of ``families_from_overview``: the
        set of families returned is the same. With ``min_tools_agreeing = m``
        a family counts for a gene only when at least ``m`` of the tool columns
        present call it for that gene; ``m`` must lie between one and the
        number of tool columns present.
        """

        required = 1 if min_tools_agreeing is None else min_tools_agreeing
        if isinstance(required, bool) or not isinstance(required, int) or required < 1:
            raise CapabilityResolutionError(
                f"min_tools_agreeing must be a positive integer; got {min_tools_agreeing!r}."
            )
        if required > len(self.tool_columns):
            raise CapabilityResolutionError(
                f"min_tools_agreeing {required} exceeds the {len(self.tool_columns)} tool column(s) present "
                f"({', '.join(self.tool_columns)}); no family could be called."
            )
        supported: dict[str, list[str]] = {}
        for gene in self.genes:
            called = sorted({family for families in gene.calls.values() for family in families})
            for family in called:
                if gene.tools_calling(family) >= required:
                    supported.setdefault(family, []).append(gene.gene_id)
        return {family: tuple(supported[family]) for family in sorted(supported)}


def parse_overview(
    text: str,
    *,
    source: str,
    tool_columns: Iterable[str] = TOOL_COLUMNS,
) -> DbcanOverview:
    """Parse the text of a dbCAN ``overview.txt`` per gene.

    The header must hold ``Gene ID`` and at least one tool column. Gene
    identifiers must be nonblank and unique, a row may not have more cells than
    the header, and at least one family must be called. ``source`` names the
    file in error messages. Cells are read with the same family rule as
    ``families_from_overview`` (subfamily suffixes and residue ranges dropped).
    """

    reader = csv.reader(text.splitlines(), delimiter="\t")
    header = next(reader, None)
    if header is None or not any(cell.strip() for cell in header):
        raise CapabilityResolutionError(f"{source} has no header row.")
    names = [cell.strip() for cell in header]
    expected = tuple(tool_columns)
    present = tuple(column for column in expected if column in names)
    if GENE_ID_COLUMN not in names or not present:
        raise CapabilityResolutionError(
            f"{source} does not have a dbCAN overview header: it needs the column {GENE_ID_COLUMN!r} and at least "
            f"one of the tool columns {expected} separated by tabs; found {tuple(names)}."
        )
    duplicates = sorted({name for name in names if name and names.count(name) > 1})
    if duplicates:
        raise CapabilityResolutionError(f"{source} repeats the header column(s) {duplicates}.")
    gene_index = names.index(GENE_ID_COLUMN)
    tool_indices = {column: names.index(column) for column in present}
    genes: list[OverviewGene] = []
    seen: dict[str, int] = {}
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        if len(cells) > len(names):
            raise CapabilityResolutionError(f"{source} line {line} has more cells than the header.")
        gene_id = cells[gene_index].strip() if gene_index < len(cells) else ""
        if not gene_id:
            raise CapabilityResolutionError(f"{source} line {line} has no gene identifier in {GENE_ID_COLUMN!r}.")
        if gene_id in seen:
            raise CapabilityResolutionError(
                f"{source} line {line} repeats gene {gene_id!r} from line {seen[gene_id]}; an overview has one "
                "row per gene."
            )
        seen[gene_id] = line
        calls = {
            column: tuple(sorted(_families_in_cell(cells[index] if index < len(cells) else "")))
            for column, index in tool_indices.items()
        }
        genes.append(OverviewGene(gene_id=gene_id, calls=calls))
    if not any(families for gene in genes for families in gene.calls.values()):
        raise CapabilityResolutionError(f"{source} yielded no CAZy family calls.")
    return DbcanOverview(tool_columns=present, genes=tuple(genes))


def annotation_from_overview(
    path: str | Path,
    *,
    organism: str,
    genome_accession: str,
    annotation_tool: str,
    annotation_tool_version: str,
    annotation_date: str,
    notes: str = "",
    tool_columns: Iterable[str] = TOOL_COLUMNS,
) -> CazymeAnnotation:
    """Build a provenance-complete annotation from a dbCAN overview file."""

    return CazymeAnnotation(
        organism=organism,
        families=families_from_overview(path, tool_columns=tool_columns),
        genome_accession=genome_accession,
        annotation_tool=annotation_tool,
        annotation_tool_version=annotation_tool_version,
        annotation_date=annotation_date,
        notes=notes,
    )


__all__ = [
    "GENE_ID_COLUMN",
    "TOOL_COLUMNS",
    "DbcanOverview",
    "OverviewGene",
    "annotation_from_overview",
    "families_from_overview",
    "parse_overview",
]
