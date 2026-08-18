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
from collections.abc import Iterable
from pathlib import Path

from fungal_model.capability.resolution import CazymeAnnotation, CapabilityResolutionError

#: Tool columns that may carry family calls, in dbCAN3 overview.txt.
TOOL_COLUMNS = ("HMMER", "dbCAN_sub", "DIAMOND", "eCAMI", "Hotpep")

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


__all__ = ["TOOL_COLUMNS", "annotation_from_overview", "families_from_overview"]
