"""Explicit, review-gated fetch of a UniProtKB proteome export as a frozen snapshot.

A strain's enzyme repertoire can come from a UniProtKB TSV export of its
proteome (see ``fungal_model.capability.uniprot`` and the ``genomes.csv``
route of ``load_user_dataset``). This module fetches such an export from the
UniProt REST API, but only when the caller passes ``refresh=True``; without it
only a frozen local snapshot is read, and nothing here runs during a
simulation. A snapshot stores the response bytes with their SHA-256, the URL,
the query, the retrieval time and the UniProt release headers when present,
and a snapshot is never replaced by a response with a different digest unless
the caller passes ``overwrite=True``. ``write_snapshot_to_user_dataset``
copies the TSV into a user-dataset directory and returns a suggested
``genomes.csv`` row for the user to review; it does not write ``genomes.csv``.

The export query is built from a UniProt proteome identifier (``UP`` followed
by digits) or an NCBI taxonomy id. An organism name reaches a proteome
identifier only through ``resolve_proteome_name`` (FETCH-001): it searches
UniProt's proteomes for reference proteomes under that organism name, freezes
the search response as a snapshot of its own (the same pattern, under the
same ``refresh`` and ``overwrite`` rules), and chooses a proteome only when
exactly one candidate's organism name equals the name (case-insensitive) or
the search has exactly one candidate. No candidate, several candidates
without one exact match, or a truncated search is refused with every
candidate listed (``ProteomeChoiceError``); FungMod never takes the first or
the largest. ``fetch_proteome_by_name`` chains the search, the choice and the
export fetch, and checks that the export's taxonomy id is the chosen
candidate's.

The REST URLs, the query fields (``organism_name``, ``proteome_type``), the
return-field names (``accession``, ``id``, ``protein_name``, ``gene_names``,
``organism_name``, ``organism_id``, ``ec``, ``xref_cazy``, ``reviewed``; for
proteomes ``upid``, ``organism``, ``organism_id``, ``protein_count``) and the
proteome-search column headers follow UniProt's REST documentation as known
when this module was written; they were not checked against a live response
from the environment it was written in, which could not reach
rest.uniprot.org. Every response is parsed before it is stored, so a change in
UniProt's column names is refused rather than stored.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote

from fungal_model.capability.resolution import CapabilityResolutionError
from fungal_model.capability.uniprot import UniprotProteome, decode_uniprot_tsv, parse_uniprot_tsv

UNIPROT_STREAM_URL = "https://rest.uniprot.org/uniprotkb/stream"
#: UniProt REST return fields, in the order of the TSV columns ``parse_uniprot_tsv`` reads.
UNIPROT_TSV_FIELDS = (
    "accession",
    "id",
    "protein_name",
    "gene_names",
    "organism_name",
    "organism_id",
    "ec",
    "xref_cazy",
    "reviewed",
)
#: Response headers recorded in the snapshot when UniProt sends them.
UNIPROT_RELEASE_HEADER = "X-UniProt-Release"
UNIPROT_RELEASE_DATE_HEADER = "X-UniProt-Release-Date"
DEFAULT_SNAPSHOT_DIR = "data/source_snapshots/uniprot"
DEFAULT_TIMEOUT_SECONDS = 300.0
SNAPSHOT_TSV_FILENAME = "uniprotkb.tsv"
SNAPSHOT_METADATA_FILENAME = "snapshot.json"
SNAPSHOT_KIND = "fungmod_uniprot_proteome_snapshot"
SNAPSHOT_SCHEMA_VERSION = "1"
FIELD_NAMES_NOTE = (
    "The stream URL and return-field names follow UniProt's REST documentation; they were not checked against a "
    "live response when FungMod's client was written. The response was parsed with parse_uniprot_tsv before it "
    "was stored."
)

#: The UniProt REST search endpoint of proteomes, used to find reference proteomes by organism name.
UNIPROT_PROTEOMES_SEARCH_URL = "https://rest.uniprot.org/proteomes/search"
#: UniProt REST return fields of a proteome search, in the order of ``PROTEOME_SEARCH_COLUMNS``.
PROTEOME_SEARCH_FIELDS = ("upid", "organism", "organism_id", "protein_count")
#: The TSV column headers UniProt documents for those fields; compared case-insensitively.
PROTEOME_SEARCH_COLUMNS = ("Proteome Id", "Organism", "Organism Id", "Protein count")
#: The proteomes query clause that keeps UniProt's reference proteomes only.
REFERENCE_PROTEOME_CLAUSE = "proteome_type:1"
#: The type stated for every candidate of a search restricted by ``REFERENCE_PROTEOME_CLAUSE``.
REFERENCE_PROTEOME_TYPE = f"reference proteome ({REFERENCE_PROTEOME_CLAUSE})"
#: Results requested in one search response; a search with more candidates is refused as truncated.
PROTEOME_SEARCH_PAGE_SIZE = 500
#: Response header with the number of results UniProt found, recorded when sent.
UNIPROT_TOTAL_RESULTS_HEADER = "X-Total-Results"
SEARCH_TSV_FILENAME = "proteomes.tsv"
SEARCH_SNAPSHOT_KIND = "fungmod_uniprot_proteome_search_snapshot"
SEARCH_SNAPSHOT_SCHEMA_VERSION = "1"
SEARCH_FIELD_NAMES_NOTE = (
    "The proteomes search URL, the query fields organism_name and proteome_type, the return-field names and their "
    "TSV column headers follow UniProt's REST documentation; they were not checked against a live response when "
    "FungMod's client was written. The response was parsed before it was stored."
)
#: How ``choose_proteome`` reached its choice.
MATCH_EXACT_NAME = "exact_organism_name"
MATCH_UNIQUE_CANDIDATE = "unique_candidate"
MATCH_PROTEOME_ID = "proteome_id_among_candidates"
MATCH_RULES = (MATCH_EXACT_NAME, MATCH_UNIQUE_CANDIDATE, MATCH_PROTEOME_ID)
_MATCH_TEXT = {
    MATCH_EXACT_NAME: "its organism name equals the name searched (case-insensitive)",
    MATCH_UNIQUE_CANDIDATE: "it is the only candidate of the search",
    MATCH_PROTEOME_ID: "its proteome identifier was given and it is a candidate of the search",
}
# Candidates quoted in an error message; the rest are counted and stay in the search snapshot.
_MESSAGE_CANDIDATE_LIMIT = 25

_PROTEOME_ID = re.compile(r"^UP\d+$")
_TAXONOMY_ID = re.compile(r"^[1-9]\d*$")
_DIGITS = re.compile(r"^\d+$")
# Characters that would end or escape the quoted phrase of a UniProt query.
_QUERY_SYNTAX = re.compile(r'["\\]')


class UniprotFetchError(RuntimeError):
    """Raised when a UniProt snapshot cannot be fetched, verified, stored or exported."""


class MissingSnapshotError(UniprotFetchError):
    """Raised without ``refresh`` when no frozen snapshot exists; ``directory`` is where it would be."""

    def __init__(self, message: str, *, directory: Path, description: str) -> None:
        super().__init__(message)
        self.directory = directory
        self.description = description


class SnapshotConflictError(UniprotFetchError):
    """Raised with ``refresh`` when a frozen snapshot that the new response may not replace exists; it is kept.

    The stored bytes differ from UniProt's new response, or the stored snapshot
    fails its own checks; ``overwrite=True`` replaces it.
    """

    def __init__(self, message: str, *, directory: Path) -> None:
        super().__init__(message)
        self.directory = directory


class ProteomeChoiceError(UniprotFetchError):
    """Raised when an organism name does not lead to exactly one proteome.

    ``reason`` says why, ``candidates`` lists every candidate of the search and
    ``search`` is its frozen snapshot; the message adds the candidates.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        name: str,
        candidates: Sequence[ProteomeCandidate],
        search: ProteomeSearchSnapshot,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.name = name
        self.candidates = tuple(candidates)
        self.search = search


def proteome_query(proteome_id: str) -> str:
    """Return the UniProtKB query for every entry of one UniProt proteome, e.g. ``(proteome:UP000005640)``."""

    text = str(proteome_id).strip()
    if not _PROTEOME_ID.fullmatch(text):
        raise UniprotFetchError(f"{proteome_id!r} is not a UniProt proteome identifier ('UP' followed by digits).")
    return f"(proteome:{text})"


def organism_query(taxonomy_id: str | int) -> str:
    """Return the UniProtKB query for every entry of one NCBI taxonomy id, e.g. ``(organism_id:51453)``.

    The query matches the organism itself, not its descendant taxa, so the
    export holds one organism. It covers every UniProtKB entry of that
    organism, which may be more than one proteome.
    """

    text = str(taxonomy_id).strip()
    if isinstance(taxonomy_id, bool) or not _TAXONOMY_ID.fullmatch(text):
        raise UniprotFetchError(f"{taxonomy_id!r} is not an NCBI taxonomy id (a positive integer).")
    return f"(organism_id:{text})"


def build_stream_url(
    query: str,
    *,
    fields: Sequence[str] = UNIPROT_TSV_FIELDS,
    base_url: str = UNIPROT_STREAM_URL,
) -> str:
    """Return the UniProtKB REST stream URL that exports ``query`` as uncompressed TSV with ``fields``."""

    if not query.strip():
        raise UniprotFetchError("A UniProt query must not be blank.")
    return (
        f"{base_url.rstrip('/')}?query={quote(query.strip(), safe='():')}"
        f"&fields={','.join(quote(name, safe='_') for name in fields)}&format=tsv"
    )


@dataclass(frozen=True)
class UniprotSnapshot:
    """A frozen UniProt export: the TSV file and its ``snapshot.json`` metadata, digest verified."""

    directory: Path
    tsv_path: Path
    metadata_path: Path
    metadata: Mapping[str, Any]

    @property
    def sha256(self) -> str:
        return str(self.metadata["sha256"])

    @property
    def query(self) -> str:
        return str(self.metadata["query"])

    @property
    def url(self) -> str:
        return str(self.metadata["url"])

    @property
    def retrieved_at(self) -> str:
        return str(self.metadata["retrieved_at"])

    @property
    def uniprot_release(self) -> str | None:
        release = self.metadata.get("uniprot_release")
        return None if release is None else str(release)

    def read_bytes(self) -> bytes:
        return self.tsv_path.read_bytes()

    def genomes_row(self, *, strain_id: str, annotation_file: str) -> dict[str, str]:
        """A ``genomes.csv`` row to review: the UniProt release (or retrieval date) as version, the query as source."""

        version = (
            f"release {self.uniprot_release}"
            if self.uniprot_release
            else f"downloaded {self.retrieved_at[:10]} (no release header in the response)"
        )
        release = f", UniProt release {self.uniprot_release}" if self.uniprot_release else ""
        organism = self.metadata.get("organism")
        organism_id = self.metadata.get("organism_id")
        named = ", ".join(
            part for part in (str(organism or ""), f"taxonomy {organism_id}" if organism_id else "") if part
        )
        return {
            "strain_id": strain_id,
            "annotation_file": annotation_file,
            "annotation_tool": f"UniProt {version}",
            "source": (
                f"{f'{named}: ' if named else ''}UniProtKB REST stream query {self.query} retrieved "
                f"{self.retrieved_at}{release}; SHA-256 {self.sha256}; {self.url}"
            ),
        }


def query_key(query: str) -> str:
    """A filesystem-safe name for a query, e.g. ``proteome_UP000005640``."""

    slug = re.sub(r"[^A-Za-z0-9]+", "_", query).strip("_")
    if not slug:
        raise UniprotFetchError(f"Query {query!r} gives no snapshot name.")
    return slug


def load_proteome_snapshot(directory: str | Path) -> UniprotSnapshot:
    """Read a frozen snapshot directory and verify the TSV bytes against the recorded SHA-256."""

    root = Path(directory)
    metadata_path = root / SNAPSHOT_METADATA_FILENAME
    tsv_path = root / SNAPSHOT_TSV_FILENAME
    if not metadata_path.is_file() or not tsv_path.is_file():
        raise UniprotFetchError(
            f"{root} holds no UniProt snapshot ({SNAPSHOT_TSV_FILENAME} and {SNAPSHOT_METADATA_FILENAME})."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UniprotFetchError(f"{metadata_path} is not readable snapshot metadata: {exc}") from exc
    if not isinstance(metadata, dict) or metadata.get("kind") != SNAPSHOT_KIND:
        raise UniprotFetchError(f"{metadata_path} is not a {SNAPSHOT_KIND} record.")
    for key in ("sha256", "query", "url", "retrieved_at"):
        if not metadata.get(key):
            raise UniprotFetchError(f"{metadata_path} lacks {key!r}.")
    actual = hashlib.sha256(tsv_path.read_bytes()).hexdigest()
    if actual != metadata["sha256"]:
        raise UniprotFetchError(
            f"{tsv_path} has SHA-256 {actual}, but {metadata_path} records {metadata['sha256']}; the snapshot was "
            "changed after it was stored."
        )
    return UniprotSnapshot(directory=root, tsv_path=tsv_path, metadata_path=metadata_path, metadata=metadata)


def fetch_proteome_snapshot(
    *,
    proteome_id: str | None = None,
    taxonomy_id: str | int | None = None,
    snapshot_dir: str | Path = DEFAULT_SNAPSHOT_DIR,
    refresh: bool = False,
    overwrite: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> UniprotSnapshot:
    """Return the frozen snapshot for a proteome or taxonomy id, fetching it from UniProt only on request.

    Exactly one of ``proteome_id`` and ``taxonomy_id`` is given. Without
    ``refresh`` the snapshot under ``snapshot_dir/<query key>`` is read and
    its digest verified; a missing snapshot is refused. With ``refresh=True``
    the stream URL is requested, the response is parsed with
    ``parse_uniprot_tsv`` (an unusable response is refused and nothing is
    written), and it is stored with its metadata. An existing snapshot with the
    same digest is returned unchanged; one with a different digest is replaced
    only with ``overwrite=True``.
    """

    if (proteome_id is None) == (taxonomy_id is None):
        raise UniprotFetchError("Give exactly one of proteome_id and taxonomy_id.")
    if proteome_id is not None:
        query = proteome_query(proteome_id)
    else:
        assert taxonomy_id is not None
        query = organism_query(taxonomy_id)
    directory = Path(snapshot_dir) / query_key(query)
    exists = (directory / SNAPSHOT_METADATA_FILENAME).exists() or (directory / SNAPSHOT_TSV_FILENAME).exists()
    if not refresh:
        if not exists:
            raise MissingSnapshotError(
                f"No frozen UniProt snapshot for {query} in {directory}. FungMod reaches UniProt only on explicit "
                "request: pass refresh=True to fetch it, then review it before use.",
                directory=directory,
                description=f"the UniProtKB export {query}",
            )
        return load_proteome_snapshot(directory)

    url = build_stream_url(query)
    body, status, headers = _http_get(url, timeout_seconds=timeout_seconds)
    if status != 200:
        raise UniprotFetchError(f"UniProt answered HTTP {status} for {url}; nothing was stored.")
    label = f"UniProt response for {query}"
    try:
        proteome = parse_uniprot_tsv(decode_uniprot_tsv(body, source=label), source=label)
    except CapabilityResolutionError as exc:
        raise UniprotFetchError(f"{exc} Nothing was stored.") from exc
    digest = hashlib.sha256(body).hexdigest()
    if exists:
        try:
            current = load_proteome_snapshot(directory)
        except UniprotFetchError as exc:
            if not overwrite:
                raise SnapshotConflictError(
                    f"{exc} Pass overwrite=True to replace it with the new response.", directory=directory
                ) from exc
        else:
            if current.sha256 == digest:
                return current
            if not overwrite:
                raise SnapshotConflictError(
                    f"The frozen snapshot in {directory} has SHA-256 {current.sha256}, but UniProt now returns "
                    f"{digest} for {query}. The snapshot is kept; pass overwrite=True to replace it.",
                    directory=directory,
                )
    metadata = _snapshot_metadata(
        query=query,
        url=url,
        status=status,
        headers=headers,
        body=body,
        digest=digest,
        proteome=proteome,
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SNAPSHOT_TSV_FILENAME).write_bytes(body)
    (directory / SNAPSHOT_METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return load_proteome_snapshot(directory)


def write_snapshot_to_user_dataset(
    snapshot: UniprotSnapshot,
    dataset_dir: str | Path,
    *,
    strain_id: str,
    annotation_file: str | None = None,
    overwrite: bool = False,
) -> dict[str, str]:
    """Copy a snapshot's TSV into a user-dataset directory and return a ``genomes.csv`` row to review.

    ``annotation_file`` is a ``/``-separated path relative to ``dataset_dir``
    (default ``annotations/<query key>.tsv``). An existing file with different
    bytes is replaced only with ``overwrite=True``. ``genomes.csv`` itself is
    not written: the returned row is a suggestion for the user to check and add.
    """

    load_proteome_snapshot(snapshot.directory)
    relative = annotation_file or f"annotations/{query_key(snapshot.query)}.tsv"
    windows = PureWindowsPath(relative)
    parts = PurePosixPath(relative).parts
    if PurePosixPath(relative).is_absolute() or windows.drive or windows.root or "\\" in relative or ".." in parts:
        raise UniprotFetchError(
            f"annotation_file {relative!r} must be a '/'-separated path inside the dataset directory."
        )
    root = Path(dataset_dir)
    target = root / relative
    data = snapshot.read_bytes()
    if target.exists():
        if not target.is_file():
            raise UniprotFetchError(f"{target} exists and is not a file.")
        if target.read_bytes() != data and not overwrite:
            raise UniprotFetchError(
                f"{target} exists with different content; pass overwrite=True to replace it with the snapshot."
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.resolve().is_relative_to(root.resolve()):
        raise UniprotFetchError(f"{target} resolves outside the dataset directory {root}.")
    target.write_bytes(data)
    return snapshot.genomes_row(strain_id=strain_id, annotation_file="/".join(part for part in parts if part != "."))


# ---------------------------------------------------------------------------
# From an organism name to a reference proteome (FETCH-001)


def normalize_organism_name(name: str) -> str:
    """The name with surrounding and repeated whitespace removed; refuses a blank name or query syntax."""

    if not isinstance(name, str):
        raise UniprotFetchError(f"An organism name must be text, not {type(name).__name__}.")
    text = " ".join(name.split())
    if not text:
        raise UniprotFetchError("An organism name must not be blank.")
    if _QUERY_SYNTAX.search(text) or any(not character.isprintable() for character in text):
        raise UniprotFetchError(
            f"Organism name {name!r} holds a double quote, a backslash or a control character, which would change "
            "the UniProt query; give the name as plain text."
        )
    return text


def proteome_name_query(name: str) -> str:
    """Return the UniProt proteomes query for reference proteomes named ``name``.

    For example ``organism_name:"Genus species" AND proteome_type:1``. The
    phrase matches organism names that contain it (UniProt's search is
    case-insensitive), so a species name also finds its strains; the choice
    among candidates is ``choose_proteome``'s.
    """

    return f'organism_name:"{normalize_organism_name(name)}" AND {REFERENCE_PROTEOME_CLAUSE}'


def build_proteome_search_url(
    query: str,
    *,
    fields: Sequence[str] = PROTEOME_SEARCH_FIELDS,
    size: int = PROTEOME_SEARCH_PAGE_SIZE,
    base_url: str = UNIPROT_PROTEOMES_SEARCH_URL,
) -> str:
    """Return the UniProt proteomes search URL for ``query`` as uncompressed TSV with ``fields``."""

    if not query.strip():
        raise UniprotFetchError("A UniProt query must not be blank.")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise UniprotFetchError(f"The search page size must be a positive integer, not {size!r}.")
    return (
        f"{base_url.rstrip('/')}?query={quote(query.strip(), safe='():')}"
        f"&fields={','.join(quote(name, safe='_') for name in fields)}&format=tsv&size={size}"
    )


def search_key(name: str) -> str:
    """A filesystem-safe snapshot name for the search of one organism name, the same for any letter case.

    UniProt's search does not distinguish letter case, and a case-insensitive
    file system would not either; the digest suffix keeps names that differ
    only in punctuation apart.
    """

    folded = normalize_organism_name(name).casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")[:60].strip("_") or "name"
    return f"organism_name_{slug}_{hashlib.sha256(folded.encode('utf-8')).hexdigest()[:12]}"


@dataclass(frozen=True)
class ProteomeCandidate:
    """One proteome of a UniProt proteomes search: identifier, organism, taxonomy id, type and protein count."""

    proteome_id: str
    organism: str
    organism_id: str
    protein_count: int | None
    proteome_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "proteome_id": self.proteome_id,
            "organism": self.organism,
            "organism_id": self.organism_id or None,
            "protein_count": self.protein_count,
            "proteome_type": self.proteome_type,
        }

    def text(self) -> str:
        taxonomy = f"taxonomy {self.organism_id}" if self.organism_id else "no taxonomy id"
        proteins = "protein count not given" if self.protein_count is None else f"{self.protein_count} proteins"
        return f"{self.proteome_id} ({self.organism}; {taxonomy}; {self.proteome_type}; {proteins})"


def parse_proteome_search_tsv(data: bytes, *, source: str) -> tuple[ProteomeCandidate, ...]:
    """Parse the TSV of a proteomes search restricted to reference proteomes.

    An empty response (UniProt sends no header when nothing matches) and a
    header without rows give no candidate. Refused: a compressed or non-UTF-8
    response, a header without the documented columns (compared
    case-insensitively) or with a repeated column, a row wider than the
    header, a malformed or repeated proteome identifier, a blank organism and a
    non-numeric taxonomy id or protein count.
    """

    if data.startswith(b"\x1f\x8b"):
        raise UniprotFetchError(f"{source} is gzip-compressed; FungMod reads the uncompressed TSV.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UniprotFetchError(f"{source} is not UTF-8 text: {exc}") from exc
    if not text.strip():
        return ()
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
    header = tuple(cell.strip() for cell in next(reader, []))
    folded = tuple(cell.casefold() for cell in header)
    repeated = sorted({cell for cell in header if cell and folded.count(cell.casefold()) > 1})
    if repeated:
        raise UniprotFetchError(f"{source} repeats the header column(s) {repeated}.")
    missing = [column for column in PROTEOME_SEARCH_COLUMNS if column.casefold() not in folded]
    if missing:
        raise UniprotFetchError(
            f"{source} does not have the proteome-search columns FungMod requested: missing {missing}, found "
            f"{list(header)}. UniProt's column names may have changed; nothing was stored."
        )
    index = {column: folded.index(column.casefold()) for column in PROTEOME_SEARCH_COLUMNS}
    candidates: list[ProteomeCandidate] = []
    seen: dict[str, int] = {}
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        if len(cells) > len(header):
            raise UniprotFetchError(f"{source} line {line} has more cells than the header.")

        def cell(column: str, cells: Sequence[str] = cells) -> str:
            position = index[column]
            return cells[position].strip() if position < len(cells) else ""

        proteome_id = cell("Proteome Id")
        if not _PROTEOME_ID.fullmatch(proteome_id):
            raise UniprotFetchError(
                f"{source} line {line}: {proteome_id!r} is not a UniProt proteome identifier ('UP' followed by digits)."
            )
        if proteome_id in seen:
            raise UniprotFetchError(
                f"{source} line {line} repeats proteome {proteome_id} from line {seen[proteome_id]}."
            )
        seen[proteome_id] = line
        organism = " ".join(cell("Organism").split())
        if not organism:
            raise UniprotFetchError(f"{source} line {line} names no organism for proteome {proteome_id}.")
        organism_id = cell("Organism Id")
        if organism_id and not _DIGITS.fullmatch(organism_id):
            raise UniprotFetchError(f"{source} line {line}: taxonomy id {organism_id!r} is not a whole number.")
        count = cell("Protein count")
        if count and not _DIGITS.fullmatch(count):
            raise UniprotFetchError(f"{source} line {line}: protein count {count!r} is not a whole number.")
        candidates.append(
            ProteomeCandidate(
                proteome_id=proteome_id,
                organism=organism,
                organism_id=organism_id,
                protein_count=int(count) if count else None,
                proteome_type=REFERENCE_PROTEOME_TYPE,
            )
        )
    return tuple(candidates)


@dataclass(frozen=True)
class ProteomeSearchSnapshot:
    """A frozen UniProt proteomes search for one organism name: the TSV and its ``snapshot.json``, digest verified."""

    directory: Path
    tsv_path: Path
    metadata_path: Path
    metadata: Mapping[str, Any]

    @property
    def sha256(self) -> str:
        return str(self.metadata["sha256"])

    @property
    def name(self) -> str:
        return str(self.metadata["organism_name"])

    @property
    def query(self) -> str:
        return str(self.metadata["query"])

    @property
    def url(self) -> str:
        return str(self.metadata["url"])

    @property
    def retrieved_at(self) -> str:
        return str(self.metadata["retrieved_at"])

    @property
    def uniprot_release(self) -> str | None:
        release = self.metadata.get("uniprot_release")
        return None if release is None else str(release)

    @property
    def truncated(self) -> bool:
        return bool(self.metadata.get("truncated"))

    def candidates(self) -> tuple[ProteomeCandidate, ...]:
        return parse_proteome_search_tsv(self.tsv_path.read_bytes(), source=f"UniProt proteome search {self.tsv_path}")

    def text(self) -> str:
        release = f"UniProt release {self.uniprot_release}" if self.uniprot_release else "no UniProt release header"
        return f"{self.directory} (SHA-256 {self.sha256}; retrieved {self.retrieved_at}; {release})"


def load_proteome_search_snapshot(directory: str | Path) -> ProteomeSearchSnapshot:
    """Read a frozen proteome-search snapshot and verify its TSV bytes against the recorded SHA-256."""

    root = Path(directory)
    metadata_path = root / SNAPSHOT_METADATA_FILENAME
    tsv_path = root / SEARCH_TSV_FILENAME
    if not metadata_path.is_file() or not tsv_path.is_file():
        raise UniprotFetchError(
            f"{root} holds no UniProt proteome-search snapshot ({SEARCH_TSV_FILENAME} and "
            f"{SNAPSHOT_METADATA_FILENAME})."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UniprotFetchError(f"{metadata_path} is not readable snapshot metadata: {exc}") from exc
    if not isinstance(metadata, dict) or metadata.get("kind") != SEARCH_SNAPSHOT_KIND:
        raise UniprotFetchError(f"{metadata_path} is not a {SEARCH_SNAPSHOT_KIND} record.")
    for key in ("sha256", "organism_name", "query", "url", "retrieved_at"):
        if not metadata.get(key):
            raise UniprotFetchError(f"{metadata_path} lacks {key!r}.")
    actual = hashlib.sha256(tsv_path.read_bytes()).hexdigest()
    if actual != metadata["sha256"]:
        raise UniprotFetchError(
            f"{tsv_path} has SHA-256 {actual}, but {metadata_path} records {metadata['sha256']}; the snapshot was "
            "changed after it was stored."
        )
    return ProteomeSearchSnapshot(directory=root, tsv_path=tsv_path, metadata_path=metadata_path, metadata=metadata)


def search_proteomes_by_name(
    name: str,
    *,
    snapshot_dir: str | Path = DEFAULT_SNAPSHOT_DIR,
    refresh: bool = False,
    overwrite: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProteomeSearchSnapshot:
    """Return the frozen search for reference proteomes named ``name``, searching UniProt only on request.

    Without ``refresh`` the snapshot under ``snapshot_dir/<search key>`` is
    read and its digest verified; a missing one is refused
    (``MissingSnapshotError``). With ``refresh=True`` the proteomes search URL
    is requested, the response is parsed (an unusable response or an HTTP error
    stores nothing), and it is stored with its metadata, whatever the number
    of candidates, so that a later run without network reaches the same
    decision. An existing snapshot with the same digest is returned unchanged;
    one with a different digest is replaced only with ``overwrite=True``
    (otherwise ``SnapshotConflictError``). The snapshot does not choose a
    proteome: ``choose_proteome`` does.
    """

    text = normalize_organism_name(name)
    query = proteome_name_query(text)
    directory = Path(snapshot_dir) / search_key(text)
    exists = (directory / SNAPSHOT_METADATA_FILENAME).exists() or (directory / SEARCH_TSV_FILENAME).exists()
    if not refresh:
        if not exists:
            raise MissingSnapshotError(
                f"No frozen UniProt proteome search for the name {text!r} in {directory}. FungMod reaches UniProt "
                "only on explicit request: pass refresh=True to search, then review the candidates.",
                directory=directory,
                description=f"the UniProt proteome search for {text!r}",
            )
        return _verified_search(load_proteome_search_snapshot(directory), text)

    url = build_proteome_search_url(query)
    body, status, headers = _http_get(url, timeout_seconds=timeout_seconds)
    if status != 200:
        raise UniprotFetchError(f"UniProt answered HTTP {status} for {url}; nothing was stored.")
    label = f"UniProt proteome search response for {text!r}"
    candidates = parse_proteome_search_tsv(body, source=label)
    total_text = headers.get(UNIPROT_TOTAL_RESULTS_HEADER.lower())
    total = int(total_text) if total_text is not None and _DIGITS.fullmatch(total_text.strip()) else None
    next_page = 'rel="next"' in headers.get("link", "")
    digest = hashlib.sha256(body).hexdigest()
    if exists:
        try:
            current = _verified_search(load_proteome_search_snapshot(directory), text)
        except UniprotFetchError as exc:
            if not overwrite:
                raise SnapshotConflictError(
                    f"{exc} Pass overwrite=True to replace it with the new response.", directory=directory
                ) from exc
        else:
            if current.sha256 == digest:
                return current
            if not overwrite:
                raise SnapshotConflictError(
                    f"The frozen proteome search in {directory} has SHA-256 {current.sha256}, but UniProt now returns "
                    f"{digest} for {query}. The snapshot is kept; pass overwrite=True to replace it.",
                    directory=directory,
                )
    metadata = {
        "kind": SEARCH_SNAPSHOT_KIND,
        "schema_version": SEARCH_SNAPSHOT_SCHEMA_VERSION,
        "source": "UniProt REST API proteomes search endpoint",
        "organism_name": text,
        "name_key": text.casefold(),
        "query": query,
        "query_key": search_key(text),
        "url": url,
        "fields": list(PROTEOME_SEARCH_FIELDS),
        "format": "tsv",
        "page_size": PROTEOME_SEARCH_PAGE_SIZE,
        "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "http_status": status,
        "uniprot_release": headers.get(UNIPROT_RELEASE_HEADER.lower()),
        "uniprot_release_date": headers.get(UNIPROT_RELEASE_DATE_HEADER.lower()),
        "total_results": total,
        "next_page": next_page,
        "truncated": next_page or (total is not None and total > len(candidates)),
        "file": SEARCH_TSV_FILENAME,
        "sha256": digest,
        "size_bytes": len(body),
        "candidate_rows": len(candidates),
        "proteome_type": REFERENCE_PROTEOME_TYPE,
        "fetched_by": "fungal_model.sources.uniprot.search_proteomes_by_name(refresh=True)",
        "field_names_note": SEARCH_FIELD_NAMES_NOTE,
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SEARCH_TSV_FILENAME).write_bytes(body)
    (directory / SNAPSHOT_METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return _verified_search(load_proteome_search_snapshot(directory), text)


@dataclass(frozen=True)
class ProteomeNameResolution:
    """The proteome chosen for an organism name, the rule that chose it and every candidate of the search."""

    name: str
    search: ProteomeSearchSnapshot
    candidates: tuple[ProteomeCandidate, ...]
    chosen: ProteomeCandidate
    match: str

    @property
    def proteome_id(self) -> str:
        return self.chosen.proteome_id

    @property
    def match_rule(self) -> str:
        """Why the chosen candidate was chosen, in words."""

        return _MATCH_TEXT[self.match]

    @property
    def statement(self) -> str:
        """How the proteome was chosen, in one sentence, for a draft's provenance."""

        return (
            f"UniProt proteome {self.chosen.text()} was chosen for the name {self.name!r} because "
            f"{self.match_rule}; the search {self.search.query} gave {len(self.candidates)} candidate(s) "
            f"(snapshot SHA-256 {self.search.sha256}, retrieved {self.search.retrieved_at}; {self.search.url})."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "match": self.match,
            "match_rule": self.match_rule,
            "chosen": self.chosen.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "search": {
                "directory": str(self.search.directory),
                "query": self.search.query,
                "url": self.search.url,
                "sha256": self.search.sha256,
                "retrieved_at": self.search.retrieved_at,
                "uniprot_release": self.search.uniprot_release,
            },
            "statement": self.statement,
        }


def choose_proteome(search: ProteomeSearchSnapshot, *, proteome_id: str | None = None) -> ProteomeNameResolution:
    """Choose the proteome of a frozen search, or refuse with every candidate listed.

    With ``proteome_id`` the identifier must be a candidate of the search.
    Otherwise exactly one candidate whose organism name equals the searched
    name (case-insensitive, whitespace-normalized) is chosen; without such a
    candidate, a search with exactly one candidate chooses it. No candidate,
    several candidates without one exact match (or several exact matches),
    and a search whose results did not fit in one response are refused with
    ``ProteomeChoiceError``. Nothing is chosen by position or size.
    """

    name = search.name
    candidates = search.candidates()

    def refuse(reason: str) -> ProteomeChoiceError:
        shown = "; ".join(candidate.text() for candidate in candidates[:_MESSAGE_CANDIDATE_LIMIT])
        more = len(candidates) - _MESSAGE_CANDIDATE_LIMIT
        listing = f" Candidates: {shown}" + (f"; and {more} more in {search.tsv_path}." if more > 0 else ".")
        return ProteomeChoiceError(
            f"{reason}{listing if candidates else ''} Name the proteome explicitly with its identifier "
            "(proteome_id='UP...').",
            reason=reason,
            name=name,
            candidates=candidates,
            search=search,
        )

    if search.truncated:
        total = search.metadata.get("total_results")
        found = f"{total} results" if total is not None else "more results than one response holds"
        raise refuse(
            f"The UniProt proteome search for {name!r} found {found}, and the stored response holds "
            f"{len(candidates)}; FungMod does not choose from a partial list. Give a more specific organism name."
        )
    if proteome_id is not None:
        wanted = str(proteome_id).strip()
        if not _PROTEOME_ID.fullmatch(wanted):
            raise UniprotFetchError(f"{proteome_id!r} is not a UniProt proteome identifier ('UP' followed by digits).")
        chosen = [candidate for candidate in candidates if candidate.proteome_id == wanted]
        if not chosen:
            raise refuse(
                f"Proteome {wanted} is not among the {len(candidates)} reference proteome(s) the UniProt search for "
                f"{name!r} found."
            )
        return ProteomeNameResolution(name, search, candidates, chosen[0], MATCH_PROTEOME_ID)
    if not candidates:
        raise refuse(
            f"The UniProt proteome search for {name!r} found no reference proteome ({search.query}). Check the "
            "spelling, search with the species name, or find the proteome on uniprot.org (a non-reference "
            "proteome is used only when you name it)."
        )
    key = name.casefold()
    exact = [candidate for candidate in candidates if candidate.organism.casefold() == key]
    if len(exact) == 1:
        return ProteomeNameResolution(name, search, candidates, exact[0], MATCH_EXACT_NAME)
    if len(exact) > 1:
        raise refuse(
            f"{len(exact)} reference proteomes of the UniProt search are named exactly {name!r}; FungMod does not "
            "choose between them."
        )
    if len(candidates) == 1:
        return ProteomeNameResolution(name, search, candidates, candidates[0], MATCH_UNIQUE_CANDIDATE)
    raise refuse(
        f"The UniProt proteome search for {name!r} found {len(candidates)} reference proteomes and none is named "
        "exactly that; FungMod does not choose between them."
    )


def resolve_proteome_name(
    name: str,
    *,
    proteome_id: str | None = None,
    snapshot_dir: str | Path = DEFAULT_SNAPSHOT_DIR,
    refresh: bool = False,
    overwrite: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProteomeNameResolution:
    """Search (``search_proteomes_by_name``) and choose (``choose_proteome``) the reference proteome of a name."""

    search = search_proteomes_by_name(
        name, snapshot_dir=snapshot_dir, refresh=refresh, overwrite=overwrite, timeout_seconds=timeout_seconds
    )
    return choose_proteome(search, proteome_id=proteome_id)


def fetch_proteome_by_name(
    name: str,
    *,
    proteome_id: str | None = None,
    snapshot_dir: str | Path = DEFAULT_SNAPSHOT_DIR,
    refresh: bool = False,
    overwrite: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[ProteomeNameResolution, UniprotSnapshot]:
    """Resolve an organism name to a reference proteome and return the resolution and the proteome's export.

    Both the search and the export are frozen snapshots under
    ``snapshot_dir``, fetched only with ``refresh=True``. The export's
    taxonomy id must be the chosen candidate's; a different one is refused.
    """

    resolution = resolve_proteome_name(
        name,
        proteome_id=proteome_id,
        snapshot_dir=snapshot_dir,
        refresh=refresh,
        overwrite=overwrite,
        timeout_seconds=timeout_seconds,
    )
    snapshot = fetch_proteome_snapshot(
        proteome_id=resolution.proteome_id,
        snapshot_dir=snapshot_dir,
        refresh=refresh,
        overwrite=overwrite,
        timeout_seconds=timeout_seconds,
    )
    exported = str(snapshot.metadata.get("organism_id") or "")
    expected = resolution.chosen.organism_id
    if exported and expected and exported != expected:
        raise UniprotFetchError(
            f"The UniProtKB export of {resolution.proteome_id} ({snapshot.directory}) is of taxonomy {exported}, but "
            f"the proteome search lists {resolution.proteome_id} under taxonomy {expected}; FungMod does not use "
            "an export whose organism differs from the chosen proteome's."
        )
    return resolution, snapshot


def _verified_search(search: ProteomeSearchSnapshot, name: str) -> ProteomeSearchSnapshot:
    if search.metadata.get("name_key") != name.casefold():
        raise UniprotFetchError(
            f"{search.metadata_path} holds the search for {search.name!r}, not for {name!r}; the snapshot "
            "directory does not belong to this name."
        )
    return search


def _http_get(url: str, *, timeout_seconds: float) -> tuple[bytes, int, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "text/plain", "User-Agent": "FungMod UniProt proteome snapshot fetcher"},
    )
    try:
        # Looked up on the module at call time, so a test can patch urllib.request.urlopen.
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(response.getcode())
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise UniprotFetchError(
            f"UniProt answered HTTP {exc.code} for {url}: {exc.reason}. Nothing was stored."
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise UniprotFetchError(f"UniProt could not be reached at {url}: {exc}. Nothing was stored.") from exc
    return body, status, headers


def _snapshot_metadata(
    *,
    query: str,
    url: str,
    status: int,
    headers: Mapping[str, str],
    body: bytes,
    digest: str,
    proteome: UniprotProteome,
) -> dict[str, Any]:
    return {
        "kind": SNAPSHOT_KIND,
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source": "UniProtKB REST API stream endpoint",
        "query": query,
        "query_key": query_key(query),
        "url": url,
        "fields": list(UNIPROT_TSV_FIELDS),
        "format": "tsv",
        "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "http_status": status,
        "uniprot_release": headers.get(UNIPROT_RELEASE_HEADER.lower()),
        "uniprot_release_date": headers.get(UNIPROT_RELEASE_DATE_HEADER.lower()),
        "file": SNAPSHOT_TSV_FILENAME,
        "sha256": digest,
        "size_bytes": len(body),
        "entry_rows": len(proteome.entries),
        "organism": proteome.organism or None,
        "organism_id": proteome.organism_id or None,
        "read_columns": list(proteome.read_columns),
        "ignored_columns": list(proteome.ignored_columns),
        "fetched_by": "fungal_model.sources.uniprot.fetch_proteome_snapshot(refresh=True)",
        "field_names_note": FIELD_NAMES_NOTE,
    }


__all__ = [
    "DEFAULT_SNAPSHOT_DIR",
    "FIELD_NAMES_NOTE",
    "MATCH_EXACT_NAME",
    "MATCH_PROTEOME_ID",
    "MATCH_RULES",
    "MATCH_UNIQUE_CANDIDATE",
    "PROTEOME_SEARCH_COLUMNS",
    "PROTEOME_SEARCH_FIELDS",
    "PROTEOME_SEARCH_PAGE_SIZE",
    "REFERENCE_PROTEOME_CLAUSE",
    "REFERENCE_PROTEOME_TYPE",
    "SEARCH_FIELD_NAMES_NOTE",
    "SEARCH_SNAPSHOT_KIND",
    "SEARCH_TSV_FILENAME",
    "SNAPSHOT_KIND",
    "SNAPSHOT_METADATA_FILENAME",
    "SNAPSHOT_TSV_FILENAME",
    "UNIPROT_PROTEOMES_SEARCH_URL",
    "UNIPROT_RELEASE_DATE_HEADER",
    "UNIPROT_RELEASE_HEADER",
    "UNIPROT_STREAM_URL",
    "UNIPROT_TOTAL_RESULTS_HEADER",
    "UNIPROT_TSV_FIELDS",
    "MissingSnapshotError",
    "ProteomeCandidate",
    "ProteomeChoiceError",
    "ProteomeNameResolution",
    "ProteomeSearchSnapshot",
    "SnapshotConflictError",
    "UniprotFetchError",
    "UniprotSnapshot",
    "build_proteome_search_url",
    "build_stream_url",
    "choose_proteome",
    "fetch_proteome_by_name",
    "fetch_proteome_snapshot",
    "load_proteome_search_snapshot",
    "load_proteome_snapshot",
    "normalize_organism_name",
    "organism_query",
    "parse_proteome_search_tsv",
    "proteome_name_query",
    "proteome_query",
    "query_key",
    "resolve_proteome_name",
    "search_key",
    "search_proteomes_by_name",
    "write_snapshot_to_user_dataset",
]
