"""Digest-checked SABIO-RK query snapshots for an explicit kinetics lookup by EC number (FETCH-002).

``fetch_kinlaw_query_snapshot`` freezes the answer of SABIO-RK's kinetic-law
export API to one query in the layout ``fetch_and_save_export`` already
writes (``<cache_dir>/<query key>/<snapshot id>/`` with ``raw/page_NNNN.json``,
``derived/combined_export.json`` and ``fetch_metadata.json``: the query, the
URLs, the retrieval time, the HTTP status, ``total_count`` and the SHA-256 and
size of every raw page and of the combined export). SABIO-RK is reached only
with ``refresh=True``; without it only the frozen snapshot is read and
verified, and a missing one is refused (``MissingKinlawSnapshotError``).

A fetch runs into a temporary directory through ``fetch_and_save_export`` and
is verified there before anything is stored: an HTTP error, a body that is not
the export envelope, a page that cannot be fetched, or a combined result whose
entry count differs from SABIO-RK's ``total_count`` (a truncated or
incompletely paginated answer) is refused and nothing is stored
(``KinlawFetchError``). A stored snapshot is never replaced: a new response
whose raw bytes differ from it, a stored snapshot that fails its own digest
checks, and several snapshots of one query are refused with the directory to
remove (``KinlawSnapshotConflictError``).

``ec_number_query`` builds the query of the lookup from a complete EC number
and a substrate name, ``ECNumber:"<EC number>" AND Substrate:"<name>"``, with
the same builder as ``SabioRKSource.discover_for_virtual_experiment``. The
field names, the quoting and the export envelope are those the existing client
uses; how SABIO-RK matches a compound name (letter case, synonyms) and what it
answers for a query without matches were not checked against a live response
when this module was written, because the environment could not reach
sabio.h-its.org. An answer that is not the export envelope is refused, never
read as "no entries".
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
import urllib.error
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fungal_model.data.sabiork import SabioRKParseError, load_sabiork_kinlaw_export
from fungal_model.sources.sabiork import (
    SabioRKSourceError,
    _freeform_source_query_from_filters,
    _load_metadata,
    _validate_frozen_raw_page,
)
from fungal_model.sources.sabiork import fetch as _fetch
from fungal_model.sources.sabiork.fetch import (
    ARTIFACT_LAYOUT_VERSION,
    BASE_URL,
    COMBINED_EXPORT_FILENAME,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    ENDPOINT,
    SabioRKFetchError,
    SabioRKTransport,
    build_kinlaw_url,
    query_bundle_key,
)

#: Where SABIO-RK snapshots are read and stored unless a caller names another directory.
DEFAULT_SNAPSHOT_DIR = "data/source_snapshots/sabiork"
#: The query of an EC-number lookup, as ``ec_number_query`` writes it.
KINLAW_QUERY_FORM = 'ECNumber:"<EC number>" AND Substrate:"<substrate name>"'
#: The kinetic-law export endpoint the lookup queries.
KINLAW_EXPORT_URL = f"{BASE_URL}{ENDPOINT}"
METADATA_FILENAME = "fetch_metadata.json"
DEFAULT_TIMEOUT_SECONDS = 60.0

_EC_NUMBER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+\.[0-9]+$")
_EC_PREFIX = re.compile(r"^EC\s*", re.IGNORECASE)
# Characters that would end or escape a quoted SABIO-RK search term; FungMod refuses them instead of escaping.
_UNQUOTABLE = re.compile(r'["\\\x00-\x1f\x7f]')


class KinlawSnapshotError(SabioRKSourceError):
    """Raised when a SABIO-RK query snapshot cannot be read, fetched or stored; ``directory`` is its location."""

    def __init__(self, message: str, *, directory: Path, query: str) -> None:
        super().__init__(message)
        self.directory = directory
        self.query = query


class MissingKinlawSnapshotError(KinlawSnapshotError):
    """Raised without ``refresh`` when no frozen snapshot of the query exists."""


class KinlawSnapshotConflictError(KinlawSnapshotError):
    """Raised when a stored snapshot may not be used or replaced; it is kept, and ``directory`` is what to remove.

    The stored snapshot fails its digest checks, the query directory holds
    several snapshots, or SABIO-RK's new response differs from the stored one.
    """


class KinlawFetchError(KinlawSnapshotError):
    """Raised when SABIO-RK's answer cannot be used (HTTP error, unusable or incomplete); nothing was stored."""


def complete_ec_number(text: str) -> str | None:
    """The complete four-part EC number ``text`` states (an optional ``EC`` prefix removed), or None."""

    value = _EC_PREFIX.sub("", str(text).strip())
    return value if _EC_NUMBER.fullmatch(value) else None


def ec_number_query(ec_number: str, *, substrate: str) -> str:
    """The SABIO-RK query for kinetic laws of one EC number on one substrate name.

    ``ECNumber:"<EC number>" AND Substrate:"<substrate name>"``, built by the
    same function as ``SabioRKSource.discover_for_virtual_experiment``. The EC
    number must be complete (four numeric parts); a substrate name with a
    double quote, a backslash or a control character is refused rather than
    escaped.
    """

    ec = complete_ec_number(ec_number)
    if ec is None:
        raise SabioRKSourceError(
            f"{ec_number!r} is not a complete EC number (four numeric parts such as 1.2.3.4); SABIO-RK is queried by "
            "complete EC numbers only."
        )
    text = str(substrate).strip()
    if not text:
        raise SabioRKSourceError("A SABIO-RK substrate query needs a nonblank substrate name.")
    if _UNQUOTABLE.search(text):
        raise SabioRKSourceError(
            f"The substrate name {text!r} holds a double quote, a backslash or a control character, which would end "
            "or escape the quoted SABIO-RK search term; FungMod does not guess an escaping."
        )
    name = " ".join(text.split())
    return _freeform_source_query_from_filters({"ec_number": ec, "substrate": name})


def kinlaw_query_directory(query: str, *, cache_dir: str | Path = DEFAULT_SNAPSHOT_DIR) -> Path:
    """The directory that holds the frozen snapshot of ``query`` under ``cache_dir``."""

    return Path(cache_dir) / query_bundle_key(query)


def kinlaw_query_snapshot_exists(query: str, *, cache_dir: str | Path = DEFAULT_SNAPSHOT_DIR) -> bool:
    """Whether ``cache_dir`` holds any snapshot directory for ``query`` (verified only when it is read)."""

    return bool(_bundles(kinlaw_query_directory(query, cache_dir=cache_dir)))


@dataclass(frozen=True)
class KinlawQuerySnapshot:
    """A verified frozen SABIO-RK answer to one query: its raw pages, combined export and metadata."""

    query: str
    cache_dir: Path
    bundle: Path
    export_path: Path
    metadata_path: Path
    metadata: Mapping[str, Any]
    entry_count: int
    export_sha256: str

    @property
    def directory(self) -> Path:
        """The query directory (``<cache_dir>/<query key>``) that holds this snapshot."""

        return self.bundle.parent

    @property
    def relative_bundle(self) -> str:
        """The snapshot's directory relative to ``cache_dir``, ``/``-separated."""

        return self.bundle.relative_to(self.cache_dir).as_posix()

    @property
    def relative_export(self) -> str:
        return self.export_path.relative_to(self.cache_dir).as_posix()

    @property
    def retrieved_at(self) -> str:
        return str(self.metadata.get("fetched_at", ""))

    @property
    def http_status(self) -> int:
        return int(self.metadata["http_status"])

    @property
    def total_count(self) -> int:
        return int(self.metadata["total_count"])

    @property
    def source_urls(self) -> tuple[str, ...]:
        return tuple(str(url) for url in self.metadata["source_urls"])

    @property
    def raw_sha256(self) -> tuple[str, ...]:
        """The SHA-256 of every raw response page, in page order (the identity of SABIO-RK's answer)."""

        return tuple(str(page["sha256"]) for page in self.metadata["raw_pages"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "snapshot": self.relative_bundle,
            "export": self.relative_export,
            "export_sha256": self.export_sha256,
            "raw_sha256": list(self.raw_sha256),
            "source_urls": list(self.source_urls),
            "retrieved_at": self.retrieved_at,
            "http_status": self.http_status,
            "total_count": self.total_count,
            "entries": self.entry_count,
        }


def load_kinlaw_query_snapshot(query: str, *, cache_dir: str | Path = DEFAULT_SNAPSHOT_DIR) -> KinlawQuerySnapshot:
    """Read and verify the one frozen snapshot of ``query`` under ``cache_dir``; nothing is fetched.

    Refused: no snapshot (``MissingKinlawSnapshotError``), several snapshots of
    the query, or a snapshot that fails its checks (``KinlawSnapshotConflictError``,
    whose ``directory`` is the query directory to remove).
    """

    root = Path(cache_dir)
    directory = kinlaw_query_directory(query, cache_dir=root)
    bundles = _bundles(directory)
    if not bundles:
        raise MissingKinlawSnapshotError(
            f"No frozen SABIO-RK snapshot of the query {query} in {directory}. FungMod reaches SABIO-RK only on "
            "explicit request: pass refresh=True to fetch it.",
            directory=directory,
            query=query,
        )
    bundle = _single_bundle(bundles, directory=directory, query=query)
    try:
        return _verified(bundle, query=query, cache_dir=root)
    except _Unusable as exc:
        raise KinlawSnapshotConflictError(
            f"The frozen SABIO-RK snapshot {bundle} of the query {query} cannot be used: {exc} It is kept; remove "
            f"{directory} to fetch the query again.",
            directory=directory,
            query=query,
        ) from exc


def fetch_kinlaw_query_snapshot(
    query: str,
    *,
    cache_dir: str | Path = DEFAULT_SNAPSHOT_DIR,
    refresh: bool = False,
    transport: SabioRKTransport | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> KinlawQuerySnapshot:
    """Return the frozen snapshot of ``query``, querying SABIO-RK only with ``refresh=True``.

    Without ``refresh`` this is ``load_kinlaw_query_snapshot``. With it the
    export API is queried through ``fetch_and_save_export`` (every page of a
    paginated answer) into a temporary directory, the result is verified (an
    HTTP error, an unusable body or an entry count that differs from
    ``total_count`` raises ``KinlawFetchError`` and stores nothing), and it is
    stored under ``cache_dir``. A stored snapshot whose raw pages have the same
    SHA-256 as the new answer is returned unchanged; one that differs, fails
    its own checks, or has a sibling is kept and the call refused
    (``KinlawSnapshotConflictError``).
    """

    if not refresh:
        return load_kinlaw_query_snapshot(query, cache_dir=cache_dir)
    root = Path(cache_dir)
    directory = kinlaw_query_directory(query, cache_dir=root)
    current: KinlawQuerySnapshot | None = None
    bundles = _bundles(directory)
    if bundles:
        current = load_kinlaw_query_snapshot(query, cache_dir=root)
    first_url = build_kinlaw_url(
        base_url=BASE_URL, endpoint=ENDPOINT, query=query, page=DEFAULT_PAGE, page_size=DEFAULT_PAGE_SIZE
    )
    with tempfile.TemporaryDirectory(prefix="fungmod-sabiork-") as staging_text:
        staging = Path(staging_text).resolve()
        try:
            _export_path, metadata_path = _fetch.fetch_and_save_export(
                query=query,
                output_dir=staging,
                expected_total_count=None,
                timeout_seconds=timeout_seconds,
                transport=transport,
            )
        except urllib.error.HTTPError as exc:
            raise KinlawFetchError(
                f"SABIO-RK answered HTTP {exc.code} for {exc.filename or first_url}: {exc.reason}. Nothing was stored.",
                directory=directory,
                query=query,
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise KinlawFetchError(
                f"SABIO-RK could not be reached for the query {query} ({first_url}): {exc}. Nothing was stored.",
                directory=directory,
                query=query,
            ) from exc
        except (SabioRKFetchError, ValueError) as exc:
            raise KinlawFetchError(
                f"SABIO-RK's answer to the query {query} ({first_url}) is not a usable kinetic-law export: {exc} "
                "Nothing was stored.",
                directory=directory,
                query=query,
            ) from exc
        try:
            staged = _verified(metadata_path.parent, query=query, cache_dir=staging)
        except _Unusable as exc:
            raise KinlawFetchError(
                f"SABIO-RK's answer to the query {query} ({first_url}) cannot be used: {exc} Nothing was stored.",
                directory=directory,
                query=query,
            ) from exc
        if current is not None:
            if current.raw_sha256 == staged.raw_sha256:
                return current
            raise KinlawSnapshotConflictError(
                f"The frozen SABIO-RK snapshot {current.bundle} of the query {query} has raw response SHA-256 "
                f"{', '.join(current.raw_sha256)}, but SABIO-RK now returns {', '.join(staged.raw_sha256)}. The "
                f"snapshot is kept; remove {directory} to store the new response.",
                directory=directory,
                query=query,
            )
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged.bundle, directory / staged.bundle.name)
    return load_kinlaw_query_snapshot(query, cache_dir=root)


def fetch_kinlaw_query_snapshots(
    queries: Sequence[str],
    *,
    cache_dir: str | Path = DEFAULT_SNAPSHOT_DIR,
    refresh: bool = False,
    transport: SabioRKTransport | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, KinlawQuerySnapshot]:
    """The frozen snapshot of every query, in order; SABIO-RK is queried only with ``refresh=True``.

    Without ``refresh`` every snapshot must exist before any is read: the
    missing ones are refused together (``MissingKinlawSnapshotError`` names the
    first directory and lists every missing query). With ``refresh`` the
    queries are sent one after another, at least
    ``fetch.MIN_REQUEST_INTERVAL_SECONDS`` apart; a failing query stops the
    lookup, and the snapshots stored before it stay frozen.
    """

    unique = list(dict.fromkeys(queries))
    if not refresh:
        missing = [query for query in unique if not kinlaw_query_snapshot_exists(query, cache_dir=cache_dir)]
        if missing:
            listing = "; ".join(
                f"{query} (in {kinlaw_query_directory(query, cache_dir=cache_dir)})" for query in missing
            )
            raise MissingKinlawSnapshotError(
                f"No frozen SABIO-RK snapshot of {len(missing)} of the {len(unique)} queries: {listing}. FungMod "
                "reaches SABIO-RK only on explicit request: pass refresh=True to fetch them.",
                directory=kinlaw_query_directory(missing[0], cache_dir=cache_dir),
                query=missing[0],
            )
    snapshots: dict[str, KinlawQuerySnapshot] = {}
    last_request = 0.0
    for query in unique:
        if refresh:
            wait = _fetch.MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request)
            if last_request and wait > 0:
                time.sleep(wait)
        snapshots[query] = fetch_kinlaw_query_snapshot(
            query, cache_dir=cache_dir, refresh=refresh, transport=transport, timeout_seconds=timeout_seconds
        )
        last_request = time.monotonic()
    return snapshots


# ---------------------------------------------------------------------------
# Verification


class _Unusable(Exception):
    """A snapshot bundle that fails a check; the message says which."""


def _bundles(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.is_dir() or path.is_symlink())


def _single_bundle(bundles: Sequence[Path], *, directory: Path, query: str) -> Path:
    if len(bundles) > 1:
        raise KinlawSnapshotConflictError(
            f"{directory} holds {len(bundles)} snapshots of the SABIO-RK query {query} "
            f"({', '.join(path.name for path in bundles)}); FungMod does not choose between them. They are kept; "
            f"remove {directory} (or all of its snapshots but one).",
            directory=directory,
            query=query,
        )
    return bundles[0]


def _verified(bundle: Path, *, query: str, cache_dir: Path) -> KinlawQuerySnapshot:
    metadata_path = bundle / METADATA_FILENAME
    export_path = bundle / "derived" / COMBINED_EXPORT_FILENAME
    # Symbolic links inside the snapshot are refused; the cache directory itself may lie behind one.
    for path in (bundle, bundle / "raw", bundle / "derived", metadata_path, export_path):
        if path.is_symlink():
            raise _Unusable(f"{path} is a symbolic link; a frozen snapshot holds regular files only.")
    if not metadata_path.is_file() or not export_path.is_file():
        raise _Unusable(f"it lacks {METADATA_FILENAME} or derived/{COMBINED_EXPORT_FILENAME} (an incomplete snapshot).")
    try:
        metadata = _load_metadata(metadata_path)
    except SabioRKSourceError as exc:
        raise _Unusable(str(exc)) from exc
    if metadata.get("query") != query:
        raise _Unusable(f"{metadata_path} records the query {metadata.get('query')!r}, not {query!r}.")
    if metadata.get("immutable_snapshot_bundle") is not True or metadata.get("artifact_layout_version") != (
        ARTIFACT_LAYOUT_VERSION
    ):
        raise _Unusable(f"{metadata_path} is not an immutable snapshot bundle of layout {ARTIFACT_LAYOUT_VERSION}.")
    raw_pages = metadata.get("raw_pages")
    urls = metadata.get("source_urls")
    if (
        not isinstance(raw_pages, list)
        or not raw_pages
        or not isinstance(urls, list)
        or len(urls) != len(raw_pages)
        or metadata.get("requests_made") != len(raw_pages)
    ):
        raise _Unusable(f"{metadata_path} does not list one raw page per request and URL.")
    combined: list[Any] = []
    for number, (page, url) in enumerate(zip(raw_pages, urls, strict=True), start=1):
        if not isinstance(page, Mapping):
            raise _Unusable(f"{metadata_path} raw page {number} is not a JSON object.")
        try:
            relative = _validate_frozen_raw_page(page, metadata_path=metadata_path.resolve())
        except SabioRKSourceError as exc:
            raise _Unusable(f"raw page {number}: {exc} (the snapshot was changed after it was stored).") from exc
        if relative != f"raw/page_{number:04d}.json" or page.get("page") != number or page.get("source_url") != url:
            raise _Unusable(f"{metadata_path} raw page {number} is out of order or names another URL.")
        if page.get("http_status") != 200:
            raise _Unusable(f"page {number} was answered with HTTP {page.get('http_status')}, not 200.")
        try:
            body = json.loads((bundle / relative).read_bytes().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _Unusable(f"raw page {number} is not JSON: {exc}.") from exc
        data = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(data, list):
            raise _Unusable(f"raw page {number} has no JSON-array 'data' field.")
        combined.extend(data)
    derived = metadata.get("derived_export")
    export_bytes = export_path.read_bytes()
    export_sha256 = hashlib.sha256(export_bytes).hexdigest()
    if not isinstance(derived, Mapping) or derived.get("sha256") != export_sha256:
        raise _Unusable(
            f"derived/{COMBINED_EXPORT_FILENAME} has SHA-256 {export_sha256}, which {metadata_path} does not record "
            "(the snapshot was changed after it was stored)."
        )
    try:
        export = load_sabiork_kinlaw_export(export_path)
    except SabioRKParseError as exc:
        raise _Unusable(str(exc)) from exc
    if [dict(entry) for entry in export.entries] != combined:
        raise _Unusable(f"derived/{COMBINED_EXPORT_FILENAME} disagrees with its raw pages.")
    total = metadata.get("total_count")
    pages = metadata.get("total_pages")
    if type(total) is not int or total < 0 or export.meta.get("total_count") != total:
        raise _Unusable(f"{metadata_path} and the export disagree on total_count, or it is not a count.")
    if len(combined) != total:
        raise _Unusable(
            f"SABIO-RK reports total_count {total} for the query, but the {len(raw_pages)} page(s) hold "
            f"{len(combined)} entries; FungMod does not use a truncated or incompletely paginated answer."
        )
    expected_pages = (0, 1) if total == 0 else (len(raw_pages),)
    if type(pages) is not int or pages not in expected_pages:
        raise _Unusable(f"{metadata_path} records total_pages {pages!r} for {len(raw_pages)} page(s) of {total} entries.")
    status = metadata.get("http_status")
    if status != 200:
        raise _Unusable(f"the query was answered with HTTP {status}, not 200.")
    return KinlawQuerySnapshot(
        query=query,
        cache_dir=cache_dir,
        bundle=bundle,
        export_path=export_path,
        metadata_path=metadata_path,
        metadata=dict(metadata),
        entry_count=len(combined),
        export_sha256=export_sha256,
    )


__all__ = [
    "DEFAULT_SNAPSHOT_DIR",
    "KINLAW_EXPORT_URL",
    "KINLAW_QUERY_FORM",
    "KinlawFetchError",
    "KinlawQuerySnapshot",
    "KinlawSnapshotConflictError",
    "KinlawSnapshotError",
    "MissingKinlawSnapshotError",
    "complete_ec_number",
    "ec_number_query",
    "fetch_kinlaw_query_snapshot",
    "fetch_kinlaw_query_snapshots",
    "kinlaw_query_directory",
    "kinlaw_query_snapshot_exists",
    "load_kinlaw_query_snapshot",
]
