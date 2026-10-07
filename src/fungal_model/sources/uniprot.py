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

The query is built from a UniProt proteome identifier (``UP`` followed by
digits) or an NCBI taxonomy id. A free-text organism-name lookup is not
offered: choosing a proteome for a name is a judgement FungMod leaves to the
user (future work, if ever, with the candidates shown, never a silent guess).

The REST stream URL and the return-field names (``accession``, ``id``,
``protein_name``, ``gene_names``, ``organism_name``, ``organism_id``, ``ec``,
``xref_cazy``, ``reviewed``) follow UniProt's REST documentation as known when
this module was written; they were not checked against a live response from
the environment it was written in, which could not reach rest.uniprot.org.
The response is parsed before it is stored, so a change in UniProt's column
names is refused rather than stored.
"""

from __future__ import annotations

import hashlib
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

_PROTEOME_ID = re.compile(r"^UP\d+$")
_TAXONOMY_ID = re.compile(r"^[1-9]\d*$")


class UniprotFetchError(RuntimeError):
    """Raised when a UniProt snapshot cannot be fetched, verified, stored or exported."""


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
        return {
            "strain_id": strain_id,
            "annotation_file": annotation_file,
            "annotation_tool": f"UniProt {version}",
            "source": (
                f"UniProtKB REST stream query {self.query} retrieved {self.retrieved_at}{release}; "
                f"SHA-256 {self.sha256}; {self.url}"
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
            raise UniprotFetchError(
                f"No frozen UniProt snapshot for {query} in {directory}. FungMod reaches UniProt only on explicit "
                "request: pass refresh=True to fetch it, then review it before use."
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
                raise UniprotFetchError(f"{exc} Pass overwrite=True to replace it with the new response.") from exc
        else:
            if current.sha256 == digest:
                return current
            if not overwrite:
                raise UniprotFetchError(
                    f"The frozen snapshot in {directory} has SHA-256 {current.sha256}, but UniProt now returns "
                    f"{digest} for {query}. The snapshot is kept; pass overwrite=True to replace it."
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
    "SNAPSHOT_KIND",
    "SNAPSHOT_METADATA_FILENAME",
    "SNAPSHOT_TSV_FILENAME",
    "UNIPROT_RELEASE_DATE_HEADER",
    "UNIPROT_RELEASE_HEADER",
    "UNIPROT_STREAM_URL",
    "UNIPROT_TSV_FIELDS",
    "UniprotFetchError",
    "UniprotSnapshot",
    "build_stream_url",
    "fetch_proteome_snapshot",
    "load_proteome_snapshot",
    "organism_query",
    "proteome_query",
    "query_key",
    "write_snapshot_to_user_dataset",
]
