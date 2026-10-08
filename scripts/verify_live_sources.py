#!/usr/bin/env python3
"""Check FungMod's live lookups against the live UniProt and SABIO-RK services, once, with internet access.

FungMod's route from a fungus name to its enzyme repertoire (FETCH-001: the
UniProt proteome search and the UniProtKB export) and its kinetics lookup by
EC number (FETCH-002: the SABIO-RK kinetic-law export) were written from the
services' documentation in an environment that could not reach them; their
tests serve synthetic responses. This script sends one request to each of the
three endpoints through FungMod's own functions (query builders, parsers and
snapshot verification: ``search_proteomes_by_name``, ``choose_proteome``,
``fetch_proteome_snapshot``, ``fetch_kinlaw_query_snapshot``, then
``SabioRKSource.parse_reaction_records`` and ``user_tables_from_sabiork`` on
the answer) and reports, per endpoint, the URL, the HTTP status, the response
headers FungMod relies on, the columns or fields found against those
expected, the number of entries, whether FungMod's parser read the response
and every mismatch.

Usage (from a repository checkout, on a machine with internet access)::

    python scripts/verify_live_sources.py
    python scripts/verify_live_sources.py --organism "GENUS SPECIES" [--proteome UP...] \
        --ec-number EC_NUMBER --substrate "SUBSTRATE NAME" --output-dir NEW_DIRECTORY

The organism, EC number and substrate are probes of the services' formats,
not a statement about any fungus or enzyme. The snapshots and
``verification_report.json`` are written to a new temporary directory, or to
``--output-dir`` (a new or empty directory outside the repository); nothing is
written inside the repository. While FungMod's UniProt functions run,
``urllib.request.urlopen`` is wrapped so that the report can show the status,
headers and columns of exactly the response FungMod parsed; the SABIO-RK
request goes through the documented ``transport`` argument.

Exit codes: 0 every endpoint was checked and matched; 1 at least one mismatch
(a response FungMod would refuse or misread, or a documented assumption that
does not hold); 2 a usage error; 3 no mismatch, but an endpoint could not be
checked (no network, a server error, a name that does not lead to one
proteome, a query without entries).
"""

from __future__ import annotations

import argparse
import contextlib
import email.message
import json
import os
import platform
import sys
import tempfile
import traceback
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fungal_model import __version__ as FUNGMOD_VERSION  # noqa: E402
from fungal_model.api.user_data_sources import UserTablesSourceError, user_tables_from_sabiork  # noqa: E402
from fungal_model.capability.resolution import CapabilityResolutionError  # noqa: E402
from fungal_model.capability.uniprot import UNIPROT_COLUMNS, decode_uniprot_tsv, parse_uniprot_tsv  # noqa: E402
from fungal_model.data.sabiork import SabioRKParseError, load_sabiork_kinlaw_export  # noqa: E402
from fungal_model.sources.sabiork import SabioRKSource, SabioRKSourceError  # noqa: E402
from fungal_model.sources.sabiork.fetch import (  # noqa: E402
    BASE_URL,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    ENDPOINT,
    HTTPResponseSnapshot,
    build_kinlaw_url,
)
from fungal_model.sources.sabiork.query_snapshots import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS as SABIORK_TIMEOUT_SECONDS,
)
from fungal_model.sources.sabiork.query_snapshots import (  # noqa: E402
    KinlawSnapshotError,
    complete_ec_number,
    ec_number_query,
    fetch_kinlaw_query_snapshot,
)
from fungal_model.sources.uniprot import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS as UNIPROT_TIMEOUT_SECONDS,
)
from fungal_model.sources.uniprot import (  # noqa: E402
    PROTEOME_SEARCH_COLUMNS,
    UNIPROT_RELEASE_DATE_HEADER,
    UNIPROT_RELEASE_HEADER,
    UNIPROT_TOTAL_RESULTS_HEADER,
    ProteomeChoiceError,
    ProteomeNameResolution,
    UniprotFetchError,
    build_proteome_search_url,
    build_stream_url,
    choose_proteome,
    fetch_proteome_snapshot,
    normalize_organism_name,
    parse_proteome_search_tsv,
    proteome_name_query,
    proteome_query,
    search_proteomes_by_name,
)

#: The probes used when none is given: a fungus with a UniProt reference proteome, and an EC number with
#: SABIO-RK entries on the name of the registry's cellobiose record (the name FungMod's lookup sends).
DEFAULT_ORGANISM = "Trichoderma reesei"
DEFAULT_EC_NUMBER = "3.2.1.21"
DEFAULT_SUBSTRATE = "Cellobiose"
REPORT_FILENAME = "verification_report.json"
REPORT_KIND = "fungmod_live_source_verification"
SABIORK_USER_AGENT = "FungMod live-source verification (scripts/verify_live_sources.py)"

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2
EXIT_NOT_CHECKED = 3

OK = "ok"
MISMATCH = "MISMATCH"
NOTE = "note"
INFO = "info"

OUTCOME_OK = "OK"
OUTCOME_MISMATCH = "MISMATCH"
OUTCOME_NOT_CHECKED = "NOT CHECKED"

# The envelope fields FungMod reads from a SABIO-RK kinetic-law export page.
SABIORK_ENVELOPE_FIELDS = ("meta", "data")
SABIORK_META_FIELDS = ("total_count", "total_pages")
# The entry fields FungMod's SABIO-RK parser reads (sources.sabiork._reaction_record and _organism).
SABIORK_ENTRY_FIELDS = (
    "general",
    "reaction",
    "kineticlaw",
    "enzyme_description",
    "experimental_conditions",
    "publication",
)


class UsageError(Exception):
    """A command-line argument that cannot be used; nothing was sent or written."""


# ---------------------------------------------------------------------------
# Recording the HTTP exchanges FungMod's functions make


@dataclass
class Exchange:
    """One HTTP request and what came back: status, headers and body, or the error."""

    url: str
    status: int | None
    headers: list[tuple[str, str]]
    body: bytes | None
    error: str | None = None

    def header(self, name: str) -> str | None:
        wanted = name.casefold()
        return next((value for key, value in self.headers if key.casefold() == wanted), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "http_status": self.status,
            "headers": dict(self.headers),
            "body_bytes": None if self.body is None else len(self.body),
            "error": self.error,
        }


class _Replayed:
    """The recorded response, handed back to FungMod's code exactly as received."""

    def __init__(self, body: bytes, status: int, headers: Sequence[tuple[str, str]]) -> None:
        self._body = body
        self._status = status
        self.headers = email.message.Message()
        for key, value in headers:
            self.headers[key] = value

    def __enter__(self) -> _Replayed:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    @property
    def status(self) -> int:
        return self._status

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


class Recorder:
    """Records every request made through ``urllib.request.urlopen`` while installed."""

    def __init__(self) -> None:
        self.exchanges: list[Exchange] = []

    @contextlib.contextmanager
    def installed(self) -> Iterator[Recorder]:
        opener = urllib.request.urlopen

        def recording(request: Any, *args: Any, **kwargs: Any) -> _Replayed:
            return self._open(opener, request, *args, **kwargs)

        urllib.request.urlopen = recording  # type: ignore[assignment]
        try:
            yield self
        finally:
            urllib.request.urlopen = opener

    def _open(self, opener: Callable[..., Any], request: Any, *args: Any, **kwargs: Any) -> _Replayed:
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        try:
            with opener(request, *args, **kwargs) as response:
                status = int(response.getcode())
                headers = [(str(key), str(value)) for key, value in response.headers.items()]
                body = response.read()
        except urllib.error.HTTPError as exc:
            headers = [(str(key), str(value)) for key, value in exc.headers.items()] if exc.headers else []
            self.exchanges.append(Exchange(url, int(exc.code), headers, None, f"HTTP {exc.code}: {exc.reason}"))
            raise
        except (urllib.error.URLError, OSError) as exc:
            self.exchanges.append(Exchange(url, None, [], None, f"not reached: {exc}"))
            raise
        self.exchanges.append(Exchange(url, status, headers, body))
        return _Replayed(body, status, headers)

    def sabiork_transport(self, url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
        """The SABIO-RK transport: the request FungMod's fetcher sends, through the recorded ``urlopen``."""

        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": SABIORK_USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(response.getcode())
            body = response.read().decode("utf-8")
        return HTTPResponseSnapshot(body=body, http_status=status, url=url)

    def since(self, start: int) -> list[Exchange]:
        return self.exchanges[start:]


# ---------------------------------------------------------------------------
# Results


@dataclass
class Check:
    status: str
    what: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "check": self.what, "detail": self.detail}


@dataclass
class EndpointResult:
    title: str
    fungmod_function: str
    url: str = ""
    query: str = ""
    exchanges: list[Exchange] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    not_checked: str = ""

    def add(self, status: str, what: str, detail: str) -> None:
        self.checks.append(Check(status, what, detail))

    @property
    def outcome(self) -> str:
        if any(check.status == MISMATCH for check in self.checks):
            return OUTCOME_MISMATCH
        if self.not_checked:
            return OUTCOME_NOT_CHECKED
        return OUTCOME_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.title,
            "fungmod_function": self.fungmod_function,
            "url": self.url,
            "query": self.query,
            "outcome": self.outcome,
            "not_checked": self.not_checked or None,
            "exchanges": [exchange.to_dict() for exchange in self.exchanges],
            "checks": [check.to_dict() for check in self.checks],
        }


# ---------------------------------------------------------------------------
# Shared checks


def _http_status(result: EndpointResult, exchange: Exchange) -> bool:
    """Record the HTTP outcome; True when a body came back with HTTP 200."""

    if exchange.status is None:
        result.not_checked = f"the service could not be reached ({exchange.error})"
        result.add(NOTE, "HTTP", f"{exchange.error}; check the internet connection or a proxy, then run again")
        return False
    if exchange.status == 200 and exchange.body is not None:
        result.add(OK, "HTTP status", "200")
        return True
    if exchange.status >= 500 or exchange.status == 429:
        result.not_checked = f"the service answered HTTP {exchange.status}"
        result.add(
            NOTE,
            "HTTP status",
            f"{exchange.status} ({exchange.error or 'no body'}): a server-side error or rate limit; run again later",
        )
        return False
    result.add(
        MISMATCH,
        "HTTP status",
        f"{exchange.status} ({exchange.error or 'no body'}), not 200: FungMod refuses this answer; the URL, the "
        "query fields or the quoting may have changed",
    )
    return False


def _header_line(result: EndpointResult, exchange: Exchange, name: str, *, missing: str, missing_detail: str) -> None:
    value = exchange.header(name)
    if value is None:
        result.add(missing, name, f"not sent; {missing_detail}")
    else:
        result.add(OK, name, value)


def _tsv_header(body: bytes) -> list[str]:
    text = body.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0].rstrip("\r")
    return [cell.strip() for cell in first.split("\t")] if first.strip() else []


def _tsv_rows(body: bytes) -> int:
    text = body.decode("utf-8-sig", errors="replace")
    lines = [line for line in text.split("\n")[1:] if line.strip()]
    return len(lines)


def _columns(result: EndpointResult, found: Sequence[str], expected: Sequence[str], *, case_insensitive: bool) -> None:
    def key(text: str) -> str:
        return text.casefold() if case_insensitive else text

    present = {key(column) for column in found}
    missing = [column for column in expected if key(column) not in present]
    extra = [column for column in found if key(column) not in {key(item) for item in expected}]
    result.add(INFO, "columns expected", ", ".join(expected))
    result.add(INFO, "columns found", ", ".join(found) if found else "(none: empty body)")
    if missing:
        result.add(
            MISMATCH,
            "columns",
            f"missing {missing}: FungMod requests these columns; a renamed or dropped field is refused or lost",
        )
    else:
        result.add(
            OK,
            "columns",
            "every expected column is present" + (" (compared case-insensitively)" if case_insensitive else ""),
        )
    if extra:
        result.add(NOTE, "extra columns", f"{extra} (FungMod ignores them)")


def _failure(result: EndpointResult, what: str, exc: BaseException) -> None:
    if result.not_checked:
        return
    if any(check.status == MISMATCH for check in result.checks):
        result.add(INFO, what, f"refused: {exc}")
        return
    result.add(MISMATCH, what, f"refused: {exc}")


# ---------------------------------------------------------------------------
# 1. UniProt proteome search


def check_proteome_search(
    name: str,
    *,
    proteome_id: str | None,
    snapshot_dir: Path,
    recorder: Recorder,
    timeout_seconds: float,
) -> tuple[EndpointResult, ProteomeNameResolution | None]:
    query = proteome_name_query(name)
    result = EndpointResult(
        title="UniProt proteome search (FETCH-001: a fungus name to its reference proteome)",
        fungmod_function="fungal_model.sources.uniprot.search_proteomes_by_name(refresh=True), choose_proteome",
        url=build_proteome_search_url(query),
        query=query,
    )
    start = len(recorder.exchanges)
    search = None
    error: UniprotFetchError | None = None
    try:
        search = search_proteomes_by_name(
            name, snapshot_dir=snapshot_dir, refresh=True, timeout_seconds=timeout_seconds
        )
    except UniprotFetchError as exc:
        error = exc
    result.exchanges = recorder.since(start)
    if not result.exchanges:
        result.add(MISMATCH, "request", f"FungMod sent no request: {error}")
        return result, None
    exchange = result.exchanges[-1]
    if not _http_status(result, exchange):
        return result, None
    assert exchange.body is not None
    result.add(INFO, "Content-Type", exchange.header("Content-Type") or "not sent")
    _header_line(
        result,
        exchange,
        UNIPROT_RELEASE_HEADER,
        missing=NOTE,
        missing_detail="FungMod then records the download date instead of a release (documented fallback)",
    )
    _header_line(result, exchange, UNIPROT_RELEASE_DATE_HEADER, missing=NOTE, missing_detail="recorded only when sent")
    rows = _tsv_rows(exchange.body)
    total_text = exchange.header(UNIPROT_TOTAL_RESULTS_HEADER)
    link = exchange.header("Link") or ""
    next_page = 'rel="next"' in link
    if total_text is None:
        result.add(
            MISMATCH,
            UNIPROT_TOTAL_RESULTS_HEADER,
            "not sent; FungMod reads it to refuse a search with more results than one response holds, and would "
            "then rely on the Link header alone",
        )
    elif not total_text.strip().isdigit():
        result.add(MISMATCH, UNIPROT_TOTAL_RESULTS_HEADER, f"{total_text!r} is not a count")
    elif int(total_text) == rows:
        result.add(OK, UNIPROT_TOTAL_RESULTS_HEADER, f"{total_text}, equal to the {rows} row(s) of the response")
    elif int(total_text) > rows and next_page:
        result.add(NOTE, UNIPROT_TOTAL_RESULTS_HEADER, f"{total_text} results, {rows} in this response (paginated)")
    else:
        result.add(MISMATCH, UNIPROT_TOTAL_RESULTS_HEADER, f"{total_text}, but the response holds {rows} row(s)")
    result.add(INFO, "Link (pagination)", link or "not sent (no next page)")
    if exchange.body.strip():
        _columns(result, _tsv_header(exchange.body), PROTEOME_SEARCH_COLUMNS, case_insensitive=True)
    else:
        result.add(INFO, "columns found", "(none: an empty body, which FungMod reads as no candidate)")
    try:
        candidates = parse_proteome_search_tsv(exchange.body, source="the live proteome search response")
    except UniprotFetchError as exc:
        result.add(MISMATCH, "parse_proteome_search_tsv", f"refused: {exc}")
        return result, None
    result.add(OK, "parse_proteome_search_tsv", f"read {len(candidates)} candidate(s)")
    if search is None:
        _failure(result, "search_proteomes_by_name", error or UniprotFetchError("no snapshot"))
        return result, None
    result.add(OK, "snapshot", f"stored and verified in {search.directory}")
    for candidate in candidates:
        result.add(INFO, "candidate", candidate.text())
    if not candidates:
        result.not_checked = (
            f"no reference proteome is named like {name!r}; the export cannot be checked with this probe "
            "(choose another --organism)"
        )
        result.add(NOTE, "choice", result.not_checked)
        return result, None
    try:
        resolution = choose_proteome(search, proteome_id=proteome_id)
    except ProteomeChoiceError as exc:
        result.not_checked = (
            f"FungMod does not choose among these candidates ({exc.reason}); run again with --proteome UP... "
            "naming one of them to check the export"
        )
        result.add(NOTE, "choice", result.not_checked)
        return result, None
    result.add(OK, "choose_proteome", f"{resolution.chosen.text()}, because {resolution.match_rule}")
    return result, resolution


# ---------------------------------------------------------------------------
# 2. UniProtKB export


def check_proteome_export(
    resolution: ProteomeNameResolution,
    *,
    snapshot_dir: Path,
    recorder: Recorder,
    timeout_seconds: float,
) -> EndpointResult:
    query = proteome_query(resolution.proteome_id)
    result = EndpointResult(
        title=f"UniProtKB export of proteome {resolution.proteome_id} (FETCH-001: the enzyme repertoire)",
        fungmod_function="fungal_model.sources.uniprot.fetch_proteome_snapshot(refresh=True)",
        url=build_stream_url(query),
        query=query,
    )
    start = len(recorder.exchanges)
    snapshot = None
    error: UniprotFetchError | None = None
    try:
        snapshot = fetch_proteome_snapshot(
            proteome_id=resolution.proteome_id, snapshot_dir=snapshot_dir, refresh=True, timeout_seconds=timeout_seconds
        )
    except UniprotFetchError as exc:
        error = exc
    result.exchanges = recorder.since(start)
    if not result.exchanges:
        result.add(MISMATCH, "request", f"FungMod sent no request: {error}")
        return result
    exchange = result.exchanges[-1]
    if not _http_status(result, exchange):
        return result
    assert exchange.body is not None
    result.add(INFO, "Content-Type", exchange.header("Content-Type") or "not sent")
    _header_line(
        result,
        exchange,
        UNIPROT_RELEASE_HEADER,
        missing=NOTE,
        missing_detail="the draft's genomes.csv then names the download date instead of a release (documented fallback)",
    )
    _header_line(result, exchange, UNIPROT_RELEASE_DATE_HEADER, missing=NOTE, missing_detail="recorded only when sent")
    total = exchange.header(UNIPROT_TOTAL_RESULTS_HEADER)
    result.add(
        INFO, UNIPROT_TOTAL_RESULTS_HEADER, total if total is not None else "not sent (FungMod does not read it here)"
    )
    _columns(result, _tsv_header(exchange.body), UNIPROT_COLUMNS, case_insensitive=False)
    label = "the live UniProtKB export"
    try:
        proteome = parse_uniprot_tsv(decode_uniprot_tsv(exchange.body, source=label), source=label)
    except CapabilityResolutionError as exc:
        result.add(MISMATCH, "parse_uniprot_tsv", f"refused: {exc}")
        return result
    entries = proteome.entries
    with_ec = sum(1 for entry in entries if entry.ec_numbers)
    with_cazy = sum(1 for entry in entries if entry.cazy_families)
    result.add(OK, "parse_uniprot_tsv", f"read {len(entries)} entries")
    result.add(
        INFO if with_ec else NOTE,
        "EC number column",
        f"{with_ec} of {len(entries)} entries carry a complete EC number"
        + ("" if with_ec else "; an empty column may mean the field name changed"),
    )
    result.add(
        INFO if with_cazy else NOTE,
        "CAZy column",
        f"{with_cazy} of {len(entries)} entries carry a CAZy family"
        + ("" if with_cazy else "; an empty column may mean the field name changed"),
    )
    expected_taxon = resolution.chosen.organism_id
    if expected_taxon and proteome.organism_id and proteome.organism_id != expected_taxon:
        result.add(
            MISMATCH,
            "Organism (ID)",
            f"{proteome.organism_id}, but the search lists {resolution.proteome_id} under taxonomy {expected_taxon}",
        )
    else:
        result.add(OK, "Organism (ID)", f"{proteome.organism_id or 'not given'} ({proteome.organism or 'no name'})")
    count = resolution.chosen.protein_count
    if count is not None and count != len(entries):
        result.add(
            NOTE,
            "protein count",
            f"the proteome search states {count} proteins and the export holds {len(entries)} entries (FungMod "
            "reads the export as it comes; a large difference may mean an incomplete stream)",
        )
    elif count is not None:
        result.add(OK, "protein count", f"{count}, equal to the export's entries")
    if snapshot is None:
        _failure(result, "fetch_proteome_snapshot", error or UniprotFetchError("no snapshot"))
        return result
    result.add(OK, "snapshot", f"stored and verified in {snapshot.directory}")
    return result


# ---------------------------------------------------------------------------
# 3. SABIO-RK kinetic-law export, queried by EC number and substrate name


def check_sabiork_query(
    ec_number: str,
    substrate: str,
    *,
    cache_dir: Path,
    recorder: Recorder,
    timeout_seconds: float,
) -> EndpointResult:
    query = ec_number_query(ec_number, substrate=substrate)
    ec = complete_ec_number(ec_number) or ec_number
    result = EndpointResult(
        title="SABIO-RK kinetic-law export, queried by EC number and substrate name (FETCH-002)",
        fungmod_function="fungal_model.sources.sabiork.query_snapshots.fetch_kinlaw_query_snapshot(refresh=True)",
        url=build_kinlaw_url(
            base_url=BASE_URL, endpoint=ENDPOINT, query=query, page=DEFAULT_PAGE, page_size=DEFAULT_PAGE_SIZE
        ),
        query=query,
    )
    start = len(recorder.exchanges)
    snapshot = None
    error: KinlawSnapshotError | None = None
    try:
        snapshot = fetch_kinlaw_query_snapshot(
            query,
            cache_dir=cache_dir,
            refresh=True,
            transport=recorder.sabiork_transport,
            timeout_seconds=timeout_seconds,
        )
    except KinlawSnapshotError as exc:
        error = exc
    result.exchanges = recorder.since(start)
    if not result.exchanges:
        result.add(MISMATCH, "request", f"FungMod sent no request: {error}")
        return result
    first = result.exchanges[0]
    failed = next((exchange for exchange in result.exchanges if exchange.status != 200 or exchange.body is None), None)
    if not _http_status(result, failed or first):
        return result
    assert first.body is not None
    result.add(INFO, "Content-Type", first.header("Content-Type") or "not sent")
    result.add(INFO, "pages fetched", str(len(result.exchanges)))
    try:
        payload = json.loads(first.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.add(MISMATCH, "envelope", f"the answer is not UTF-8 JSON: {exc}")
        return result
    if not isinstance(payload, Mapping):
        result.add(MISMATCH, "envelope", f"the answer is a JSON {type(payload).__name__}, not an object")
        return result
    found = list(payload)
    meta = payload.get("meta")
    meta_found = list(meta) if isinstance(meta, Mapping) else []
    result.add(
        INFO,
        "fields expected",
        ", ".join([*SABIORK_ENVELOPE_FIELDS, *(f"meta.{name}" for name in SABIORK_META_FIELDS)]),
    )
    result.add(INFO, "fields found", ", ".join([*found, *(f"meta.{name}" for name in meta_found)]) or "(none)")
    missing = [name for name in SABIORK_ENVELOPE_FIELDS if name not in payload]
    if not isinstance(meta, Mapping) or "total_count" not in meta:
        missing.append("meta.total_count")
    if missing:
        result.add(MISMATCH, "envelope", f"missing {missing}: FungMod refuses an answer without them")
    else:
        result.add(OK, "envelope", "meta, data and meta.total_count are present")
    if isinstance(meta, Mapping):
        if "total_pages" in meta:
            result.add(OK, "meta.total_pages", str(meta.get("total_pages")))
        else:
            result.add(NOTE, "meta.total_pages", "not sent; FungMod then fetches one page only and checks total_count")
        for name in ("page", "page_size"):
            if name in meta:
                result.add(INFO, f"meta.{name}", str(meta.get(name)))
    data = payload.get("data")
    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        entry_fields = sorted({key for entry in data if isinstance(entry, Mapping) for key in entry})
        absent = [name for name in SABIORK_ENTRY_FIELDS if name not in entry_fields]
        result.add(INFO, "entry fields found", ", ".join(entry_fields))
        if absent:
            result.add(
                MISMATCH,
                "entry fields",
                f"no entry has {absent}, which FungMod's parser reads (organism, reaction, parameters, EC number, "
                "conditions, publication)",
            )
        else:
            result.add(OK, "entry fields", ", ".join(SABIORK_ENTRY_FIELDS))
    if snapshot is None:
        _failure(
            result,
            "fetch_kinlaw_query_snapshot",
            error or KinlawSnapshotError("no snapshot", directory=cache_dir, query=query),
        )
        return result
    result.add(
        OK,
        "snapshot",
        f"stored and verified in {snapshot.bundle} (total_count {snapshot.total_count}, {snapshot.entry_count} entries)",
    )
    if snapshot.entry_count == 0:
        result.not_checked = (
            f"SABIO-RK has no entry for {query}; the entry format cannot be checked with this probe "
            "(choose another --ec-number or --substrate)"
        )
        result.add(NOTE, "entries", result.not_checked)
        return result
    _check_sabiork_entries(result, snapshot.export_path, ec=ec, substrate=substrate, cache_dir=cache_dir)
    return result


def _check_sabiork_entries(
    result: EndpointResult, export_path: Path, *, ec: str, substrate: str, cache_dir: Path
) -> None:
    try:
        export = load_sabiork_kinlaw_export(export_path)
        records = SabioRKSource(cache_dir=cache_dir).parse_reaction_records(export)
    except (SabioRKParseError, SabioRKSourceError) as exc:
        result.add(MISMATCH, "parse_reaction_records", f"refused: {exc}")
        return
    total = len(records)
    result.add(OK, "parse_reaction_records", f"read {total} entries")
    ec_numbers = Counter(record.ec_number.strip() for record in records)
    other = {number: count for number, count in ec_numbers.items() if number != ec}
    if not other:
        result.add(OK, "EC numbers", f"every entry states EC {ec}")
    else:
        listing = ", ".join(f"{number or '(none found)'}: {count}" for number, count in sorted(other.items()))
        result.add(
            MISMATCH,
            "EC numbers",
            f"{sum(other.values())} of {total} entries do not state EC {ec} ({listing}); the ECNumber field of the "
            "query, or the parser's EC field, does not work as FungMod assumes",
        )
    without_organism = sum(1 for record in records if not record.organism.strip())
    if without_organism == total:
        result.add(MISMATCH, "organism", "the parser found no organism in any entry")
    elif without_organism:
        result.add(NOTE, "organism", f"{without_organism} of {total} entries name no organism")
    else:
        result.add(OK, "organism", f"every entry names its organism ({len({r.organism for r in records})} organisms)")
    without_parameters = sum(1 for record in records if not record.parameters)
    if without_parameters == total:
        result.add(MISMATCH, "parameters", "the parser found no kinetic parameter in any entry")
    elif without_parameters:
        result.add(NOTE, "parameters", f"{without_parameters} of {total} entries have no kinetic parameter")
    else:
        result.add(OK, "parameters", "every entry has kinetic parameters")
    wanted = " ".join(substrate.split()).casefold()
    naming = sum(
        1 for record in records if any(item.compound_name.strip().casefold() == wanted for item in record.substrates)
    )
    if naming == total:
        result.add(OK, "substrate name", f"every entry names {substrate!r} as a substrate (case-insensitive)")
    elif naming:
        result.add(
            NOTE,
            "substrate name",
            f"{naming} of {total} entries name {substrate!r} as a substrate (case-insensitive); FungMod's lookup "
            "matches entries to the requested substrate by that name, so the others are listed as not used",
        )
    else:
        result.add(
            MISMATCH,
            "substrate name",
            f"no entry names {substrate!r} as a substrate; FungMod's lookup matches entries to the requested "
            "substrate by name and would use none of them",
        )
    try:
        draft = user_tables_from_sabiork(export_path, dataset_id="live_source_check", cache_dir=cache_dir)
    except UserTablesSourceError as exc:
        result.add(MISMATCH, "user_tables_from_sabiork", f"refused: {exc}")
        return
    reasons = Counter(_reason_class(str(item.get("reason", ""))) for item in draft.not_converted)
    detail = f"{len(draft.converted_entry_ids)} of {total} entries converted to kinetics rows"
    if reasons:
        detail += "; not converted: " + "; ".join(f"{reason} ({count})" for reason, count in reasons.most_common(6))
    result.add(OK if draft.converted_entry_ids else NOTE, "user_tables_from_sabiork", detail)


def _reason_class(reason: str) -> str:
    text = " ".join(reason.split())
    for separator in (":", ";", "("):
        text = text.split(separator, 1)[0]
    return text.strip()[:80] or "no reason given"


# ---------------------------------------------------------------------------
# Output directory, report and command line


def _inside(path: Path, root: Path) -> bool:
    child = os.path.normcase(str(path.resolve()))
    parent = os.path.normcase(str(root.resolve()))
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:  # different drives on Windows
        return False


def prepare_output_directory(text: str | None) -> Path:
    """A new or empty directory outside the repository; a new temporary directory when none is given."""

    if text is None:
        base = Path(tempfile.gettempdir())
        if _inside(base, ROOT):
            raise UsageError(f"The temporary directory {base} is inside the repository {ROOT}; give --output-dir.")
        return Path(tempfile.mkdtemp(prefix="fungmod-live-sources-")).resolve()
    path = Path(text).expanduser().resolve()
    if _inside(path, ROOT):
        raise UsageError(
            f"--output-dir {path} is inside the repository {ROOT}; the snapshots of this check are written only "
            "outside it. Give a directory elsewhere, or none for a new temporary directory."
        )
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise UsageError(f"--output-dir {path} must be a new or empty directory.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send one request to UniProt's proteome search, UniProtKB's export and SABIO-RK's kinetic-law export "
            "through FungMod's own query builders, parsers and snapshot checks, and report per endpoint whether the "
            "live responses are what FungMod expects. Needs internet access; writes only to a new temporary "
            "directory or --output-dir, never inside the repository."
        ),
        epilog=(
            "The organism, EC number and substrate are probes of the services' formats only, not statements about "
            "any fungus or enzyme. Exit codes: 0 every endpoint matched; 1 at least one mismatch; 2 usage error; "
            "3 no mismatch, but an endpoint could not be checked."
        ),
    )
    parser.add_argument(
        "--organism",
        default=DEFAULT_ORGANISM,
        help=f"organism name searched among UniProt's reference proteomes (default: {DEFAULT_ORGANISM!r}, a probe)",
    )
    parser.add_argument(
        "--proteome",
        metavar="PROTEOME_ID",
        help="choose this candidate (UP followed by digits) when the name has several reference proteomes",
    )
    parser.add_argument(
        "--ec-number", default=DEFAULT_EC_NUMBER, help=f"complete EC number (default: {DEFAULT_EC_NUMBER})"
    )
    parser.add_argument(
        "--substrate",
        default=DEFAULT_SUBSTRATE,
        help=(
            f"substrate name of the SABIO-RK query (default: {DEFAULT_SUBSTRATE!r}, the name of the registry's "
            "cellobiose record, which FungMod's lookup sends)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        help="new or empty directory outside the repository for the snapshots and the report (default: a new "
        "temporary directory, kept and printed)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        help=f"seconds per request (default: FungMod's own, {UNIPROT_TIMEOUT_SECONDS:g} for UniProt and "
        f"{SABIORK_TIMEOUT_SECONDS:g} for SABIO-RK)",
    )
    return parser.parse_args(argv)


def _print_endpoint(number: int, total: int, result: EndpointResult, out: Any) -> None:
    print(f"\n[{number}/{total}] {result.title}", file=out)
    print(f"  FungMod: {result.fungmod_function}", file=out)
    if result.query:
        print(f"  query: {result.query}", file=out)
    print(f"  URL: {result.url}", file=out)
    for exchange in result.exchanges[1:]:
        print(f"  URL: {exchange.url}", file=out)
    width = max((len(check.status) for check in result.checks), default=4)
    for check in result.checks:
        print(f"  {check.status:<{width}}  {check.what}: {check.detail}", file=out)
    suffix = f" ({result.not_checked})" if result.outcome == OUTCOME_NOT_CHECKED else ""
    print(f"  result: {result.outcome}{suffix}", file=out)


def main(argv: Sequence[str] | None = None) -> int:
    out = sys.stdout
    args = parse_args(argv)
    try:
        name = normalize_organism_name(args.organism)
        if args.proteome is not None:
            proteome_query(args.proteome)
        if complete_ec_number(args.ec_number) is None:
            raise UsageError(f"--ec-number {args.ec_number!r} is not a complete EC number (four numeric parts).")
        query = ec_number_query(args.ec_number, substrate=args.substrate)
        if args.timeout is not None and args.timeout <= 0:
            raise UsageError("--timeout must be positive.")
        output_dir = prepare_output_directory(args.output_dir)
    except (UsageError, UniprotFetchError, SabioRKSourceError) as exc:
        print(f"verify_live_sources: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    uniprot_timeout = args.timeout or UNIPROT_TIMEOUT_SECONDS
    sabiork_timeout = args.timeout or SABIORK_TIMEOUT_SECONDS
    started = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    print("FungMod live-source verification", file=out)
    print(
        f"  FungMod {FUNGMOD_VERSION} ({SRC if (SRC / 'fungal_model').is_dir() else 'installed package'}), "
        f"Python {platform.python_version()}, started {started}",
        file=out,
    )
    print(f"  output directory: {output_dir} (snapshots and {REPORT_FILENAME}; outside the repository)", file=out)
    print(
        f"  probe organism: {name!r} (a probe of UniProt's formats only, not a recommendation or a statement "
        "about this fungus)",
        file=out,
    )
    print(f"  probe query: {query} (a probe of SABIO-RK's format only)", file=out)

    recorder = Recorder()
    results: list[EndpointResult] = []
    with recorder.installed():
        for step in ("uniprot", "sabiork"):
            try:
                if step == "uniprot":
                    search, resolution = check_proteome_search(
                        name,
                        proteome_id=args.proteome.strip() if args.proteome else None,
                        snapshot_dir=output_dir / "uniprot",
                        recorder=recorder,
                        timeout_seconds=uniprot_timeout,
                    )
                    results.append(search)
                    if resolution is not None:
                        results.append(
                            check_proteome_export(
                                resolution,
                                snapshot_dir=output_dir / "uniprot",
                                recorder=recorder,
                                timeout_seconds=uniprot_timeout,
                            )
                        )
                    else:
                        skipped = EndpointResult(
                            title="UniProtKB export (FETCH-001: the enzyme repertoire)",
                            fungmod_function="fungal_model.sources.uniprot.fetch_proteome_snapshot(refresh=True)",
                            url=build_stream_url("(proteome:UP...)"),
                        )
                        skipped.not_checked = "no proteome was chosen by the search above, so no export was requested"
                        results.append(skipped)
                else:
                    results.append(
                        check_sabiork_query(
                            args.ec_number,
                            args.substrate,
                            cache_dir=output_dir / "sabiork",
                            recorder=recorder,
                            timeout_seconds=sabiork_timeout,
                        )
                    )
            except Exception as exc:  # an unexpected failure is a finding, not a crash of the whole check
                failed = EndpointResult(title=f"{step}: unexpected error", fungmod_function="")
                failed.add(MISMATCH, type(exc).__name__, f"{exc}\n{traceback.format_exc()}")
                results.append(failed)

    for number, result in enumerate(results, start=1):
        _print_endpoint(number, len(results), result, out)

    mismatches = sum(1 for result in results if result.outcome == OUTCOME_MISMATCH)
    not_checked = sum(1 for result in results if result.outcome == OUTCOME_NOT_CHECKED)
    matched = len(results) - mismatches - not_checked
    if mismatches:
        code = EXIT_MISMATCH
    elif not_checked:
        code = EXIT_NOT_CHECKED
    else:
        code = EXIT_OK
    report = {
        "kind": REPORT_KIND,
        "fungmod_version": FUNGMOD_VERSION,
        "python": platform.python_version(),
        "started_at": started,
        "probe_organism": name,
        "probe_proteome": args.proteome,
        "probe_ec_number": args.ec_number,
        "probe_substrate": args.substrate,
        "output_directory": str(output_dir),
        "endpoints": [result.to_dict() for result in results],
        "summary": {"ok": matched, "mismatch": mismatches, "not_checked": not_checked},
        "exit_code": code,
    }
    report_path = output_dir / REPORT_FILENAME
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"\nSummary: {len(results)} endpoint(s): {matched} OK, {mismatches} MISMATCH, {not_checked} NOT CHECKED; "
        f"exit code {code}.",
        file=out,
    )
    print(f"Report: {report_path}", file=out)
    if mismatches:
        print(
            "A mismatch means FungMod would refuse or misread this response (it never stores an unreadable one); "
            "send the report to the maintainers so that the client can be corrected.",
            file=out,
        )
    print(
        "This checks the services' formats against FungMod's parsers; it does not check any value, organism or "
        "enzyme, and a match is not a validation of the kinetics or of the proteome.",
        file=out,
    )
    return code


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    raise SystemExit(main())
