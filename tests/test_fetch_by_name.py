"""From a fungus name to its enzyme repertoire through a UniProt reference proteome (FETCH-001).

``fungal_model.sources.uniprot`` searches UniProt's reference proteomes for an
organism name, freezes the search response as a snapshot, chooses a proteome
only by an exact (case-insensitive) organism-name match or a unique candidate,
and refuses anything else with every candidate listed; ``fungmod assemble
--fetch-proteome`` (or ``--proteome UP...``) turns the chosen proteome's
UniProtKB export into the draft's ``genomes.csv`` row. These tests pin that
contract with patched ``urllib.request.urlopen`` only.

Every UniProt response here is a SYNTHETIC TEST RESPONSE written by hand in the
format UniProt documents (``tests/fixtures/uniprot_proteome_search/README.md``
and the ``uniprot_case`` format fixture); none is UniProt data, and no organism
stands behind any row. Every test runs with ``urlopen`` and socket connections
patched to fail, so the default test run cannot reach the network; a test that
fetches serves its synthetic responses through ``_FakeUniprot``.
"""

from __future__ import annotations

import contextlib
import csv
import email.message
import hashlib
import io
import json
import shutil
import socket
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import assemble_user_tables, load_user_dataset, virtual_experiment
from fungal_model.api.user_data import GENOME_TABLE, REVIEW_MARKER, UNIPROT_SOURCE_TYPE
from fungal_model.api.user_data_assembly import UserTablesAssemblyError
from fungal_model.cli import EXIT_OK, EXIT_USAGE, FETCH_HELP, NO_FETCH_HELP, main, shell_quote
from fungal_model.sources.uniprot import (
    MATCH_EXACT_NAME,
    MATCH_PROTEOME_ID,
    MATCH_UNIQUE_CANDIDATE,
    PROTEOME_SEARCH_COLUMNS,
    REFERENCE_PROTEOME_TYPE,
    SEARCH_SNAPSHOT_KIND,
    SEARCH_TSV_FILENAME,
    SNAPSHOT_METADATA_FILENAME,
    MissingSnapshotError,
    ProteomeChoiceError,
    SnapshotConflictError,
    UniprotFetchError,
    build_proteome_search_url,
    build_stream_url,
    choose_proteome,
    fetch_proteome_by_name,
    fetch_proteome_snapshot,
    load_proteome_search_snapshot,
    normalize_organism_name,
    parse_proteome_search_tsv,
    proteome_name_query,
    proteome_query,
    resolve_proteome_name,
    search_key,
    search_proteomes_by_name,
)
from tests.test_user_data_assembly import _fill

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
RESPONSES = ROOT / "tests" / "fixtures" / "uniprot_proteome_search"
# The proteome export of UP000000000: the repository's UniProt format fixture (synthetic accessions).
EXPORT_U1 = ROOT / "tests" / "fixtures" / "user_data" / "uniprot_case" / "annotations" / "strain_u1_uniprot.tsv"
EXPORT_B2 = RESPONSES / "proteome_UP999990002_uniprotkb.tsv"

# First organism: the search names one candidate exactly like the query (exact-name rule).
NAME_U1 = "Synthetic format-fixture organism"
SEARCH_U1 = RESPONSES / "search_format_fixture_organism.tsv"
# Second, materially different organism: one candidate whose name adds a strain (unique-candidate rule).
NAME_B2 = "Synthetic fixture mould B2"
SEARCH_B2 = RESPONSES / "search_fixture_mould_b2.tsv"
# A name whose two candidates are both strains of it: refused as ambiguous.
NAME_MOULD = "Synthetic fixture mould"
SEARCH_MOULD = RESPONSES / "search_fixture_mould.tsv"
SEARCH_NONE = RESPONSES / "search_no_candidate.tsv"

RELEASE_HEADERS = {"X-UniProt-Release": "fixture_release", "X-UniProt-Release-Date": "06-October-2026"}


# ---------------------------------------------------------------------------
# No network in the default test run


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("FETCH-001 tests must not reach the network; serve a synthetic response instead.")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    yield


def test_the_default_test_run_cannot_reach_the_network() -> None:
    assert urllib.request.urlopen is _forbidden
    with pytest.raises(AssertionError, match="must not reach the network"):
        search_proteomes_by_name(NAME_U1, snapshot_dir="unused", refresh=True)


class _FakeResponse:
    def __init__(self, body: bytes, *, status: int, headers: Mapping[str, str]) -> None:
        self._body = body
        self._status = status
        self.headers = email.message.Message()
        for key, value in headers.items():
            self.headers[key] = value

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


class _FakeUniprot:
    """Serve synthetic UniProt responses by exact URL and record every URL requested."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[bytes | BaseException, int, Mapping[str, str]]] = {}
        self.requested: list[str] = []

    def search(
        self,
        name: str,
        body: bytes | BaseException,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        url = build_proteome_search_url(proteome_name_query(name))
        self.routes[url] = (body, status, RELEASE_HEADERS if headers is None else headers)
        return url

    def export(self, proteome_id: str, body: bytes, *, headers: Mapping[str, str] | None = None) -> str:
        url = build_stream_url(proteome_query(proteome_id))
        self.routes[url] = (body, 200, RELEASE_HEADERS if headers is None else headers)
        return url

    def __call__(self, request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        assert timeout > 0
        url = request.full_url
        self.requested.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected UniProt request {url}")
        body, status, headers = self.routes[url]
        if isinstance(body, BaseException):
            raise body
        return _FakeResponse(body, status=status, headers=headers)


@pytest.fixture
def uniprot(monkeypatch: pytest.MonkeyPatch) -> _FakeUniprot:
    fake = _FakeUniprot()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)


def _served_u1(uniprot: _FakeUniprot) -> None:
    uniprot.search(NAME_U1, SEARCH_U1.read_bytes())
    uniprot.export("UP000000000", EXPORT_U1.read_bytes())


def _served_b2(uniprot: _FakeUniprot) -> None:
    # No release header on these responses: the version is the retrieval date, recorded as such.
    uniprot.search(NAME_B2, SEARCH_B2.read_bytes(), headers={})
    uniprot.export("UP999990002", EXPORT_B2.read_bytes(), headers={})


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()
    }


# ---------------------------------------------------------------------------
# Query, URL and parser


def test_the_query_and_url_are_built_from_the_name() -> None:
    assert normalize_organism_name("  Synthetic   fixture\tmould B2 ") == NAME_B2
    assert proteome_name_query(NAME_B2) == 'organism_name:"Synthetic fixture mould B2" AND proteome_type:1'
    assert build_proteome_search_url(proteome_name_query(NAME_B2)) == (
        "https://rest.uniprot.org/proteomes/search?query=organism_name:%22Synthetic%20fixture%20mould%20B2%22"
        "%20AND%20proteome_type:1&fields=upid,organism,organism_id,protein_count&format=tsv&size=500"
    )
    # Letter case does not change the snapshot directory (UniProt's search ignores it, and so may a file system);
    # punctuation does, through the digest suffix.
    assert search_key(NAME_B2) == search_key("synthetic FIXTURE mould b2")
    assert search_key("Synthetic fixture mould B2.") != search_key(NAME_B2)
    assert search_key(NAME_B2).startswith("organism_name_synthetic_fixture_mould_b2_")
    for bad in ("", "   ", 'Synthetic "fixture"', "Synthetic\\fixture", "Synthetic\x00fixture"):
        with pytest.raises(UniprotFetchError):
            proteome_name_query(bad)
    for bad_size in (0, -1, True):
        with pytest.raises(UniprotFetchError, match="page size"):
            build_proteome_search_url("x", size=bad_size)


def test_the_parser_reads_the_documented_columns_case_insensitively() -> None:
    candidates = parse_proteome_search_tsv(SEARCH_U1.read_bytes(), source="test")
    assert [candidate.to_dict() for candidate in candidates] == [
        {
            "proteome_id": "UP000000000",
            "organism": NAME_U1,
            "organism_id": "0",
            "protein_count": 13,
            "proteome_type": REFERENCE_PROTEOME_TYPE,
        },
        {
            "proteome_id": "UP999990001",
            "organism": "Synthetic format-fixture organism (strain FIX-1B)",
            "organism_id": "9000000001",
            "protein_count": 4211,
            "proteome_type": REFERENCE_PROTEOME_TYPE,
        },
    ]
    assert PROTEOME_SEARCH_COLUMNS == ("Proteome Id", "Organism", "Organism Id", "Protein count")
    variant = b"PROTEOME ID\tOrganism ID\tOrganism\tProtein count\tBUSCO\r\nUP999990002\t9000000002\tB2\t\t-\r\n"
    (only,) = parse_proteome_search_tsv(variant, source="test")
    assert (only.proteome_id, only.organism_id, only.organism, only.protein_count) == ("UP999990002", "9000000002", "B2", None)
    assert parse_proteome_search_tsv(b"", source="test") == ()
    assert parse_proteome_search_tsv(SEARCH_NONE.read_bytes(), source="test") == ()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"Entry\tOrganism\n", "missing ['Proteome Id', 'Organism Id', 'Protein count']"),
        (b"Proteome Id\tOrganism\tOrganism Id\tProtein count\tOrganism\n", "repeats the header column"),
        (b"Proteome Id\tOrganism\tOrganism Id\tProtein count\nUP12x\tA\t1\t2\n", "not a UniProt proteome identifier"),
        (b"Proteome Id\tOrganism\tOrganism Id\tProtein count\nUP1\tA\t1\t2\nUP1\tB\t2\t3\n", "repeats proteome UP1"),
        (b"Proteome Id\tOrganism\tOrganism Id\tProtein count\nUP1\t \t1\t2\n", "names no organism"),
        (b"Proteome Id\tOrganism\tOrganism Id\tProtein count\nUP1\tA\tx1\t2\n", "taxonomy id 'x1'"),
        (b"Proteome Id\tOrganism\tOrganism Id\tProtein count\nUP1\tA\t1\t2,5\n", "protein count '2,5'"),
        (b"Proteome Id\tOrganism\tOrganism Id\tProtein count\nUP1\tA\t1\t2\t9\n", "more cells than the header"),
        (b"\x1f\x8b\x08\x00", "gzip-compressed"),
        (b"\xff\xfe\x00P", "not UTF-8"),
    ],
)
def test_the_parser_refuses_what_it_cannot_read(body: bytes, message: str) -> None:
    with pytest.raises(UniprotFetchError, match=message.replace("[", r"\[").replace("]", r"\]")):
        parse_proteome_search_tsv(body, source="test")


# ---------------------------------------------------------------------------
# Search snapshots and the choice


def test_a_unique_exact_match_is_stored_and_reused_offline_with_an_identical_digest(
    uniprot: _FakeUniprot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    search_url = uniprot.search(NAME_U1, SEARCH_U1.read_bytes(), headers={**RELEASE_HEADERS, "X-Total-Results": "2"})

    resolution = resolve_proteome_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)

    assert uniprot.requested == [search_url]
    assert resolution.proteome_id == "UP000000000"
    assert resolution.match == MATCH_EXACT_NAME
    assert [candidate.proteome_id for candidate in resolution.candidates] == ["UP000000000", "UP999990001"]
    search = resolution.search
    assert search.directory == tmp_path / search_key(NAME_U1)
    assert search.tsv_path == search.directory / SEARCH_TSV_FILENAME
    assert search.tsv_path.read_bytes() == SEARCH_U1.read_bytes()
    metadata = json.loads((search.directory / SNAPSHOT_METADATA_FILENAME).read_text(encoding="utf-8"))
    assert metadata["kind"] == SEARCH_SNAPSHOT_KIND
    assert metadata["organism_name"] == NAME_U1
    assert metadata["query"] == proteome_name_query(NAME_U1)
    assert metadata["url"] == search_url
    assert metadata["http_status"] == 200
    assert metadata["uniprot_release"] == "fixture_release"
    assert metadata["uniprot_release_date"] == "06-October-2026"
    assert metadata["retrieved_at"].endswith("Z")
    assert metadata["sha256"] == hashlib.sha256(SEARCH_U1.read_bytes()).hexdigest()
    assert (metadata["total_results"], metadata["truncated"], metadata["candidate_rows"]) == (2, False, 2)
    assert "were not checked against a live response" in metadata["field_names_note"]
    assert "because its organism name equals the name searched" in resolution.statement
    assert search.sha256 in resolution.statement and search_url in resolution.statement

    # Offline: the frozen search reproduces the same decision from the same bytes, in any letter case.
    _offline(monkeypatch)
    again = resolve_proteome_name(NAME_U1.upper(), snapshot_dir=tmp_path)
    assert again.search.sha256 == search.sha256
    assert again.proteome_id == "UP000000000" and again.match == MATCH_EXACT_NAME
    # With refresh and the same bytes, the stored snapshot is returned unchanged.
    uniprot_again = _FakeUniprot()
    uniprot_again.search(NAME_U1, SEARCH_U1.read_bytes())
    monkeypatch.setattr(urllib.request, "urlopen", uniprot_again)
    assert search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True).metadata == metadata


def test_a_single_candidate_with_another_name_is_chosen_and_the_rule_says_so(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    _served_b2(uniprot)

    resolution, snapshot = fetch_proteome_by_name(NAME_B2, snapshot_dir=tmp_path, refresh=True)

    assert resolution.match == MATCH_UNIQUE_CANDIDATE
    assert resolution.chosen.organism == "Synthetic fixture mould B2 (strain FIX-2)"
    assert resolution.match_rule == "it is the only candidate of the search"
    assert resolution.search.uniprot_release is None
    assert snapshot.query == "(proteome:UP999990002)"
    assert snapshot.read_bytes() == EXPORT_B2.read_bytes()
    assert len(uniprot.requested) == 2
    as_dict = resolution.to_dict()
    assert as_dict["chosen"]["proteome_id"] == "UP999990002"
    assert as_dict["match"] == MATCH_UNIQUE_CANDIDATE


def test_an_ambiguous_name_is_refused_with_every_candidate_until_one_is_named(
    uniprot: _FakeUniprot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    uniprot.search(NAME_MOULD, SEARCH_MOULD.read_bytes())

    with pytest.raises(ProteomeChoiceError) as refused:
        resolve_proteome_name(NAME_MOULD, snapshot_dir=tmp_path, refresh=True)

    error = refused.value
    assert [candidate.proteome_id for candidate in error.candidates] == ["UP999990002", "UP999990003"]
    assert "none is named exactly that; FungMod does not choose between them" in error.reason
    for candidate in error.candidates:
        assert candidate.text() in str(error)
    assert "proteome_id='UP...'" in str(error)
    # The search is frozen all the same, so that the refusal is reproducible offline.
    assert error.search.sha256 == hashlib.sha256(SEARCH_MOULD.read_bytes()).hexdigest()
    _offline(monkeypatch)
    with pytest.raises(ProteomeChoiceError):
        resolve_proteome_name(NAME_MOULD, snapshot_dir=tmp_path)

    chosen = resolve_proteome_name(NAME_MOULD, proteome_id="UP999990003", snapshot_dir=tmp_path)
    assert (chosen.proteome_id, chosen.match) == ("UP999990003", MATCH_PROTEOME_ID)
    with pytest.raises(ProteomeChoiceError, match="UP000000000 is not among the 2 reference proteome"):
        resolve_proteome_name(NAME_MOULD, proteome_id="UP000000000", snapshot_dir=tmp_path)
    with pytest.raises(UniprotFetchError, match="not a UniProt proteome identifier"):
        resolve_proteome_name(NAME_MOULD, proteome_id="UP-3", snapshot_dir=tmp_path)


@pytest.mark.parametrize("body", [b"", SEARCH_NONE.read_bytes()], ids=["empty body", "header only"])
def test_a_name_without_a_reference_proteome_is_refused(uniprot: _FakeUniprot, tmp_path: Path, body: bytes) -> None:
    uniprot.search("Synthetic fixture organism absent", body)

    with pytest.raises(ProteomeChoiceError, match="found no reference proteome") as refused:
        resolve_proteome_name("Synthetic fixture organism absent", snapshot_dir=tmp_path, refresh=True)

    assert refused.value.candidates == ()
    assert "non-reference proteome is used only when you name it" in refused.value.reason


def test_several_exact_matches_are_refused(uniprot: _FakeUniprot, tmp_path: Path) -> None:
    body = (
        b"Proteome Id\tOrganism\tOrganism Id\tProtein count\n"
        b"UP999990002\tSynthetic fixture mould B2\t9000000002\t5\n"
        b"UP999990003\tsynthetic fixture mould b2\t9000000003\t6\n"
    )
    uniprot.search(NAME_B2, body)

    with pytest.raises(ProteomeChoiceError, match="2 reference proteomes of the UniProt search are named exactly"):
        resolve_proteome_name(NAME_B2, snapshot_dir=tmp_path, refresh=True)


@pytest.mark.parametrize(
    "headers",
    [{"X-Total-Results": "731"}, {"Link": '<https://rest.uniprot.org/proteomes/search?cursor=x>; rel="next"'}],
    ids=["total results", "next page"],
)
def test_a_truncated_search_is_refused_even_with_an_exact_match(
    uniprot: _FakeUniprot, tmp_path: Path, headers: dict[str, str]
) -> None:
    uniprot.search(NAME_U1, SEARCH_U1.read_bytes(), headers=headers)

    with pytest.raises(ProteomeChoiceError, match="does not choose from a partial list"):
        resolve_proteome_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)
    assert load_proteome_search_snapshot(tmp_path / search_key(NAME_U1)).truncated


@pytest.mark.parametrize(
    ("response", "status", "message"),
    [
        (urllib.error.HTTPError("u", 503, "Service Unavailable", email.message.Message(), None), 200, "HTTP 503"),
        (urllib.error.URLError("no route to host"), 200, "could not be reached"),
        (SEARCH_U1.read_bytes(), 204, "HTTP 204"),
        (b"<html>Service unavailable</html>\n", 200, "does not have the proteome-search columns"),
    ],
    ids=["HTTP error", "unreachable", "HTTP 204", "not a TSV"],
)
def test_an_http_error_or_unusable_response_stores_nothing(
    uniprot: _FakeUniprot, tmp_path: Path, response: bytes | BaseException, status: int, message: str
) -> None:
    uniprot.search(NAME_U1, response, status=status)

    with pytest.raises(UniprotFetchError, match=message):
        search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)
    assert not any(tmp_path.iterdir())


def test_without_refresh_a_missing_snapshot_is_refused_and_nothing_is_fetched(tmp_path: Path) -> None:
    with pytest.raises(MissingSnapshotError, match="pass refresh=True to search") as refused:
        resolve_proteome_name(NAME_U1, snapshot_dir=tmp_path)
    assert refused.value.directory == tmp_path / search_key(NAME_U1)
    with pytest.raises(MissingSnapshotError, match="pass refresh=True to fetch it") as missing_export:
        fetch_proteome_snapshot(proteome_id="UP000000000", snapshot_dir=tmp_path)
    assert missing_export.value.description == "the UniProtKB export (proteome:UP000000000)"
    assert not any(tmp_path.iterdir())


def test_a_changed_search_snapshot_is_refused(uniprot: _FakeUniprot, tmp_path: Path) -> None:
    uniprot.search(NAME_U1, SEARCH_U1.read_bytes())
    search = search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)

    search.tsv_path.write_bytes(SEARCH_U1.read_bytes().replace(b"UP999990001", b"UP999990009"))
    with pytest.raises(UniprotFetchError, match="changed after it was stored"):
        resolve_proteome_name(NAME_U1, snapshot_dir=tmp_path)
    # A newer response is not stored over a changed or different snapshot unless asked.
    with pytest.raises(SnapshotConflictError, match="Pass overwrite=True to replace it"):
        search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)
    assert search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True, overwrite=True).candidates()

    # A snapshot moved under another name's directory is not that name's search.
    other = tmp_path / search_key(NAME_B2)
    shutil.copytree(search.directory, other)
    with pytest.raises(UniprotFetchError, match="does not belong to this name"):
        resolve_proteome_name(NAME_B2, snapshot_dir=tmp_path)
    metadata = json.loads((search.directory / SNAPSHOT_METADATA_FILENAME).read_text(encoding="utf-8"))
    (search.directory / SNAPSHOT_METADATA_FILENAME).write_text(
        json.dumps({**metadata, "kind": "other"}), encoding="utf-8"
    )
    with pytest.raises(UniprotFetchError, match=f"is not a {SEARCH_SNAPSHOT_KIND} record"):
        load_proteome_search_snapshot(search.directory)


def test_a_different_response_keeps_the_search_snapshot_unless_overwrite(
    uniprot: _FakeUniprot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    uniprot.search(NAME_U1, SEARCH_U1.read_bytes())
    first = search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)
    newer = SEARCH_U1.read_bytes().replace(b"\t4211\n", b"\t4212\n")
    uniprot.search(NAME_U1, newer)

    with pytest.raises(SnapshotConflictError, match="The snapshot is kept") as refused:
        search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)
    assert refused.value.directory == first.directory
    assert first.tsv_path.read_bytes() == SEARCH_U1.read_bytes()
    replaced = search_proteomes_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True, overwrite=True)
    assert replaced.sha256 == hashlib.sha256(newer).hexdigest() != first.sha256


def test_the_export_must_be_of_the_chosen_proteome_taxonomy(uniprot: _FakeUniprot, tmp_path: Path) -> None:
    uniprot.search(NAME_B2, SEARCH_B2.read_bytes())
    # The format fixture's export (taxonomy 0) served for UP999990002 (taxonomy 9000000002 in the search).
    uniprot.export("UP999990002", EXPORT_U1.read_bytes())

    with pytest.raises(UniprotFetchError, match="is of taxonomy 0, but the proteome search lists UP999990002"):
        fetch_proteome_by_name(NAME_B2, snapshot_dir=tmp_path, refresh=True)


def test_neither_the_first_nor_the_largest_candidate_is_chosen(uniprot: _FakeUniprot, tmp_path: Path) -> None:
    header, *rows = SEARCH_U1.read_bytes().splitlines(keepends=True)
    # The exact match is the last and the smallest candidate; it is chosen for its name, not its place or size.
    uniprot.search(NAME_U1, b"".join((header, *reversed(rows))))
    resolution = resolve_proteome_name(NAME_U1, snapshot_dir=tmp_path / "exact", refresh=True)
    assert resolution.candidates[0].proteome_id == "UP999990001"
    assert resolution.candidates[0].protein_count == max(item.protein_count or 0 for item in resolution.candidates)
    assert (resolution.proteome_id, resolution.match) == ("UP000000000", MATCH_EXACT_NAME)

    # Without an exact match, neither order makes a choice.
    header, *rows = SEARCH_MOULD.read_bytes().splitlines(keepends=True)
    for order, ordered in (("as served", rows), ("reversed", list(reversed(rows)))):
        uniprot.search(NAME_MOULD, b"".join((header, *ordered)))
        with pytest.raises(ProteomeChoiceError, match="does not choose between them"):
            resolve_proteome_name(NAME_MOULD, snapshot_dir=tmp_path / order, refresh=True)
    assert "Nothing is chosen by position or size" in (choose_proteome.__doc__ or "")


# ---------------------------------------------------------------------------
# Assembling from the chosen proteome (API)


def test_assemble_user_tables_takes_a_proteome_snapshot_and_records_how_it_was_chosen(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    _served_u1(uniprot)
    resolution, snapshot = fetch_proteome_by_name(NAME_U1, snapshot_dir=tmp_path / "snapshots", refresh=True)

    draft = assemble_user_tables(
        dataset_id="u1_by_name",
        fungus="Strain U1 from its name",
        substrates=["cellobiose"],
        conditions=[{"temperature": 30, "temperature_units": "degC", "ph": 5}],
        proteome=snapshot,
        proteome_selection=resolution.statement,
        registry=REGISTRY_INDEX,
    )

    (row,) = draft.genomes
    assert row["annotation_file"] == "annotations/proteome_UP000000000.tsv"
    assert row["annotation_tool"] == "UniProt release fixture_release"
    assert row["source"].startswith(f"{NAME_U1}, taxonomy 0: UniProtKB REST stream query (proteome:UP000000000)")
    assert snapshot.sha256 in row["source"] and snapshot.url in row["source"]
    assert draft.annotation_files == {"annotations/proteome_UP000000000.tsv": EXPORT_U1.read_bytes()}
    annotation = draft.assembly["annotation"]
    assert annotation["source_type"] == UNIPROT_SOURCE_TYPE
    assert annotation["proteome_id"] == "UP000000000"
    assert annotation["selection"] == resolution.statement
    assert annotation["snapshot"]["sha256"] == snapshot.sha256
    classes = {item["enzyme_class"]: item for item in draft.assembly["enzyme_classes"]}
    assert set(classes) == {"beta_glucosidase", "cellobiohydrolase", "cellulase_generic", "glucoamylase"}
    assert classes["beta_glucosidase"]["declared_in"] == GENOME_TABLE
    (evidence,) = classes["beta_glucosidase"]["evidence"]
    assert evidence["evidence"] == "UniProt proteome UP000000000 (3 proteins, CAZy families GH1, GH3, EC 3.2.1.21)"
    assert evidence["accessions"] == ["X0TEST01", "X0TEST02", "X0TEST03"]
    assert [item["enzyme_class"] for item in draft.assembly["unmodellable_enzyme_classes"]] == ["laccase"]
    assert {item["accession"] for item in annotation["ec_cazy_disagreements"]} == {"X0TEST04", "X0TEST10"}
    assert [case["kinetics_status"] for case in draft.assembly["cases"]] == ["gap"]
    # Provenance of the choice: the manifest's source and review.md name it.
    assert resolution.statement in draft.manifest["source"]
    assert f"- Proteome choice: {resolution.statement}" in draft.review
    assert "UniProt proteome export `annotations/proteome_UP000000000.tsv`" in draft.review
    assert "- X0TEST04: CAZy CBM1, GH7 names cellobiohydrolase" in draft.review
    assert "- laccase (families AA1, 1 protein(s))" in draft.review
    # No kinetic value comes from a proteome: kinetics.csv holds no row.
    assert draft.kinetics == ()

    # The same snapshot given as its directory gives the same draft, byte for byte.
    by_directory = assemble_user_tables(
        dataset_id="u1_by_name",
        fungus="Strain U1 from its name",
        substrates=["cellobiose"],
        conditions=[{"temperature": 30, "temperature_units": "degC", "ph": 5}],
        proteome=snapshot.directory,
        proteome_selection=resolution.statement,
        registry=REGISTRY_INDEX,
    )
    assert by_directory.file_texts() == draft.file_texts()


def test_the_proteome_route_refuses_a_changed_snapshot_and_a_second_annotation(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    _served_u1(uniprot)
    _resolution, snapshot = fetch_proteome_by_name(NAME_U1, snapshot_dir=tmp_path, refresh=True)
    request: dict[str, Any] = {
        "dataset_id": "u1_by_name",
        "fungus": "Strain U1 from its name",
        "substrates": ["cellobiose"],
        "conditions": [{"temperature": 30, "temperature_units": "degC", "ph": 5}],
        "registry": REGISTRY_INDEX,
    }

    with pytest.raises(UserTablesAssemblyError, match="give annotation \\(with annotation_tool\\) or proteome"):
        assemble_user_tables(**request, proteome=snapshot, annotation=EXPORT_U1, annotation_tool="UniProt 2026_03")
    with pytest.raises(UserTablesAssemblyError, match="give it with proteome"):
        assemble_user_tables(**request, enzyme_classes=["beta_glucosidase"], proteome_selection="chosen by hand")
    with pytest.raises(UserTablesAssemblyError, match="must be nonblank"):
        assemble_user_tables(**request, proteome=snapshot, proteome_selection=" ")
    with pytest.raises(UserTablesAssemblyError, match="holds no UniProt snapshot"):
        assemble_user_tables(**request, proteome=tmp_path / "missing")
    snapshot.tsv_path.write_bytes(snapshot.read_bytes().replace(b"GH3;", b"GH1;"))
    with pytest.raises(UserTablesAssemblyError, match="changed after it was stored"):
        assemble_user_tables(**request, proteome=snapshot)


def test_an_annotation_whose_tool_names_uniprot_is_read_as_a_uniprot_export() -> None:
    """A user-downloaded export works through --annotation as well, checked like a genomes.csv UniProt row."""

    request: dict[str, Any] = {
        "dataset_id": "b2_from_file",
        "fungus": "Strain B2",
        "substrates": ["cellobiose"],
        "conditions": [{"temperature": 30, "temperature_units": "degC", "ph": 5}],
        "registry": REGISTRY_INDEX,
        "annotation": EXPORT_B2,
    }
    draft = assemble_user_tables(**request, annotation_tool="UniProt downloaded 2026-10-07")

    (row,) = draft.genomes
    assert row["annotation_file"] == "annotations/proteome_UP999990002_uniprotkb.tsv"
    assert row["annotation_tool"] == "UniProt downloaded 2026-10-07"
    assert row["source"].startswith(REVIEW_MARKER)
    classes = {item["enzyme_class"] for item in draft.assembly["enzyme_classes"]}
    assert classes == {"beta_glucosidase", "chitinase", "endo_xylanase"}
    assert [item["enzyme_class"] for item in draft.assembly["unmodellable_enzyme_classes"]] == [
        "lytic_polysaccharide_monooxygenase"
    ]
    assert [item["family"] for item in draft.assembly["unmapped_families"]] == ["CBM18"]
    assert [item["ec_number"] for item in draft.assembly["annotation"]["unresolved_ec_numbers"]] == ["3.1.1.1"]
    assert draft.assembly["annotation"]["proteome_id"] is None

    with pytest.raises(UserTablesAssemblyError, match="names UniProt without a version"):
        assemble_user_tables(**request, annotation_tool="UniProt")
    with pytest.raises(UserTablesAssemblyError, match="names several proteome identifiers"):
        assemble_user_tables(
            **request, annotation_tool="UniProt 2026_03", annotation_source="UP999990002 and UP999990003"
        )
    with pytest.raises(UserTablesAssemblyError, match="does not have a UniProt TSV header"):
        assemble_user_tables(**{**request, "annotation": SEARCH_B2}, annotation_tool="UniProt 2026_03")


def test_a_uniprot_row_reused_from_user_data_is_named_and_counted_as_proteins() -> None:
    """Before FETCH-001 review.md raised KeyError 'gene_count' for an unmodellable class of a reused UniProt row."""

    draft = assemble_user_tables(
        dataset_id="u1_reused",
        fungus="strain_u1",
        substrates=["cellobiose"],
        conditions=[{"temperature": 30, "temperature_units": "degC", "ph": 5}],
        user_data=EXPORT_U1.parents[1],
        registry=REGISTRY_INDEX,
    )

    assert "UniProt proteome export `annotations/strain_u1_uniprot.tsv`" in draft.review
    assert "- laccase (families AA1, 1 protein(s))" in draft.review
    assert "UniProt proteome export annotations/strain_u1_uniprot.tsv" in draft.manifest["source"]
    assert "dbCAN" not in draft.manifest["source"]


# ---------------------------------------------------------------------------
# fungmod assemble --fetch-proteome / --proteome


def _cli(*args: str | Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def _assemble(fungus: str, snapshots: Path, *extra: str | Path) -> tuple[str | Path, ...]:
    return (
        "assemble",
        "--fungus",
        fungus,
        "--substrate",
        "cellobiose",
        "--temperature-c",
        "30",
        "--ph",
        "5",
        "--registry",
        REGISTRY_INDEX,
        "--snapshot-dir",
        snapshots,
        "--dataset-id",
        "proteome_draft",
        *extra,
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_fungmod_assemble_fetches_by_name_and_reruns_offline_byte_for_byte(
    uniprot: _FakeUniprot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _served_u1(uniprot)
    snapshots = tmp_path / "snapshots"
    draft_dir = tmp_path / "draft"
    arguments = _assemble(NAME_U1, snapshots, "--fetch-proteome")

    code, out, err = _cli(*arguments, "--fetch", "--output", draft_dir)

    assert code == EXIT_OK, err
    assert uniprot.requested == [
        build_proteome_search_url(proteome_name_query(NAME_U1)),
        build_stream_url(proteome_query("UP000000000")),
    ]
    assert "Proteome of the fungus (UniProt):" in out
    assert f"network: --fetch given; UniProt was queried and the responses are frozen under {snapshots}" in out
    assert f"name searched: {NAME_U1!r} (from --fungus)" in out
    assert f"search: {proteome_name_query(NAME_U1)} -> 2 candidate(s)" in out
    chosen_rows = [line.split() for line in out.splitlines() if line.strip().endswith("chosen")]
    assert len(chosen_rows) == 1 and chosen_rows[0][1] == "UP000000000"
    assert f"chosen: UP000000000 ({NAME_U1}) because its organism name equals the name searched" in out
    assert f"export: (proteome:UP000000000), 13 UniProtKB entries of {NAME_U1}" in out
    assert "UniProt release fixture_release" in out
    assert "beta_glucosidase   genomes.csv  UniProt proteome UP000000000 (3 proteins" in out
    assert "Proteins whose CAZy and EC annotations name different classes (they support no class):" in out
    assert "  - 3.2.1.4 (1 protein(s)): no registry enzyme class carries this EC number" in out
    assert "Draft written to" in out and "annotations/proteome_UP000000000.tsv" in out

    (row,) = _csv_rows(draft_dir / GENOME_TABLE)
    assert row["annotation_tool"] == "UniProt release fixture_release"
    assert "(proteome:UP000000000)" in row["source"] and NAME_U1 in row["source"]
    assert (draft_dir / row["annotation_file"]).read_bytes() == EXPORT_U1.read_bytes()
    first = _files(draft_dir)

    # Offline, without --fetch: the frozen snapshots give the same draft, byte for byte.
    _offline(monkeypatch)
    rerun = tmp_path / "rerun"
    code, out_offline, err = _cli(*arguments, "--output", rerun)
    assert code == EXIT_OK, err
    assert f"network: not used; frozen snapshots under {snapshots} (--fetch queries UniProt)" in out_offline
    assert _files(rerun) == first

    # The draft loads through load_user_dataset once reviewed, and its preflight has the class's case.
    _fill(draft_dir)
    dataset = load_user_dataset(draft_dir, registry=REGISTRY_INDEX)
    (annotation,) = dataset.genome_annotations
    assert annotation["source_type"] == UNIPROT_SOURCE_TYPE
    assert annotation["proteome_id"] == "UP000000000"
    assert annotation["annotation_tool_version"] == "release fixture_release"
    assert {item["enzyme_class"] for item in dataset.genome_resolved_classes} == {
        "beta_glucosidase",
        "cellobiohydrolase",
        "cellulase_generic",
        "glucoamylase",
    }
    code, out_check, err_check = _cli("check-data", draft_dir, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err_check
    assert "proteome UP000000000" in out_check
    study = virtual_experiment(
        fungi=NAME_U1, substrates="cellobiose", environments="c30_ph5", user_data=dataset, registry=REGISTRY_INDEX
    )
    (report,) = study.preflight(mode="exploratory")
    assert report.status == "underparameterized"
    assert any(
        "UniProt proteome UP000000000" in request and "X0TEST01" in request for request in report.suggested_experiments
    )


def test_fungmod_assemble_by_scientific_name_takes_the_only_candidate_of_a_second_organism(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    _served_b2(uniprot)
    draft_dir = tmp_path / "draft"

    code, out, err = _cli(
        *_assemble("Strain B2", tmp_path / "snapshots", "--scientific-name", NAME_B2, "--fetch-proteome", "--fetch"),
        "--output",
        draft_dir,
    )

    assert code == EXIT_OK, err
    assert f"name searched: {NAME_B2!r} (from --scientific-name)" in out
    assert "chosen: UP999990002 (Synthetic fixture mould B2 (strain FIX-2)) because it is the only candidate" in out
    assert "no UniProt release header" in out
    (row,) = _csv_rows(draft_dir / GENOME_TABLE)
    # Without a release header the version is the retrieval date, and the row says so.
    assert row["annotation_tool"].startswith("UniProt downloaded 20")
    assert row["annotation_tool"].endswith("(no release header in the response)")
    assert row["source"].startswith("Synthetic fixture mould B2 (strain FIX-2), taxonomy 9000000002: ")
    assert "lytic_polysaccharide_monooxygenase" in out
    assert "  - 3.1.1.1 (1 protein(s)): no registry enzyme class carries this EC number" in out
    manifest = yaml.safe_load((draft_dir / "user_dataset.yml").read_text(encoding="utf-8"))
    assert "because it is the only candidate of the search" in manifest["source"]


def test_fungmod_assemble_offline_without_a_snapshot_prints_the_command_that_fetches_it(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    output = tmp_path / "draft"
    arguments = [str(argument) for argument in _assemble(NAME_U1, snapshots, "--fetch-proteome", "--output", output)]

    code, out, err = _cli(*arguments)

    assert code == EXIT_USAGE
    assert f"no frozen snapshot of the UniProt proteome search for {NAME_U1!r}" in err
    assert "the command line reaches UniProt only with --fetch" in err
    assert f"fungmod {' '.join(shell_quote(argument) for argument in arguments)} --fetch" in err
    assert not output.exists() and not snapshots.exists()

    code, out, err = _cli(*_assemble(NAME_U1, snapshots, "--proteome", "UP000000000", "--output", output))
    assert code == EXIT_USAGE
    assert "no frozen snapshot of the UniProtKB export (proteome:UP000000000)" in err
    assert not output.exists()


def test_fungmod_assemble_lists_the_candidates_of_an_ambiguous_name_and_takes_the_one_named(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    uniprot.search(NAME_MOULD, SEARCH_MOULD.read_bytes())
    uniprot.export("UP999990002", EXPORT_B2.read_bytes())
    snapshots = tmp_path / "snapshots"
    arguments = [str(argument) for argument in _assemble(NAME_MOULD, snapshots, "--fetch-proteome", "--fetch")]

    code, out, err = _cli(*arguments, "--output", tmp_path / "refused")

    assert code == EXIT_USAGE
    assert "found 2 reference proteomes and none is named exactly that" in err
    assert "candidates (2):" in err
    for proteome_id, organism in (
        ("UP999990002", "Synthetic fixture mould B2 (strain FIX-2)"),
        ("UP999990003", "Synthetic fixture mould B3 (strain FIX-3)"),
    ):
        assert any(proteome_id in line and organism in line for line in err.splitlines())
    assert "run the same command with --proteome PROTEOME_ID" in err
    assert not (tmp_path / "refused").exists()
    # The search was frozen; the export was not requested.
    assert uniprot.requested == [build_proteome_search_url(proteome_name_query(NAME_MOULD))]

    code, out, err = _cli(*arguments, "--proteome", "UP999990002", "--output", tmp_path / "chosen")
    assert code == EXIT_OK, err
    assert "chosen: UP999990002 (Synthetic fixture mould B2 (strain FIX-2)) because its proteome identifier was given" in out

    code, out, err = _cli(*arguments, "--proteome", "UP000000000", "--output", tmp_path / "not_a_candidate")
    assert code == EXIT_USAGE
    assert "Proteome UP000000000 is not among the 2 reference proteome(s)" in err


def test_fungmod_assemble_without_a_candidate_points_to_an_explicit_proteome(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    uniprot.search("Synthetic fixture organism absent", SEARCH_NONE.read_bytes())

    code, out, err = _cli(
        *_assemble("Synthetic fixture organism absent", tmp_path / "s", "--fetch-proteome", "--fetch"),
        "--output",
        tmp_path / "draft",
    )

    assert code == EXIT_USAGE
    assert "found no reference proteome" in err
    assert "run the command without --fetch-proteome, with --proteome PROTEOME_ID" in err


def test_fungmod_assemble_takes_an_explicit_proteome_without_a_search(uniprot: _FakeUniprot, tmp_path: Path) -> None:
    uniprot.export("UP999990002", EXPORT_B2.read_bytes())

    code, out, err = _cli(
        *_assemble("Strain B2", tmp_path / "s", "--proteome", "UP999990002", "--fetch"), "--output", tmp_path / "d"
    )

    assert code == EXIT_OK, err
    assert uniprot.requested == [build_stream_url(proteome_query("UP999990002"))]
    assert "name searched" not in out
    assert "export: (proteome:UP999990002), 5 UniProtKB entries" in out


def test_fungmod_assemble_refuses_a_changed_snapshot_and_a_newer_response(
    uniprot: _FakeUniprot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _served_u1(uniprot)
    snapshots = tmp_path / "snapshots"
    arguments = _assemble(NAME_U1, snapshots, "--fetch-proteome")
    assert _cli(*arguments, "--fetch", "--output", tmp_path / "first")[0] == EXIT_OK

    uniprot.search(NAME_U1, SEARCH_U1.read_bytes().replace(b"\t4211\n", b"\t4212\n"))
    code, out, err = _cli(*arguments, "--fetch", "--output", tmp_path / "newer")
    assert code == EXIT_USAGE
    assert "The snapshot is kept" in err
    assert f"remove {snapshots / search_key(NAME_U1)} (or choose another --snapshot-dir)" in err

    _offline(monkeypatch)
    export = snapshots / "proteome_UP000000000" / "uniprotkb.tsv"
    export.write_bytes(export.read_bytes().replace(b"GH3;", b"GH1;"))
    code, out, err = _cli(*arguments, "--output", tmp_path / "tampered")
    assert code == EXIT_USAGE
    assert "changed after it was stored" in err
    assert not (tmp_path / "tampered").exists()


def test_fungmod_assemble_http_error_stores_nothing(uniprot: _FakeUniprot, tmp_path: Path) -> None:
    uniprot.search(NAME_U1, urllib.error.HTTPError("u", 500, "Internal Server Error", email.message.Message(), None))
    snapshots = tmp_path / "snapshots"

    code, out, err = _cli(*_assemble(NAME_U1, snapshots, "--fetch-proteome", "--fetch"), "--output", tmp_path / "d")

    assert code == EXIT_USAGE
    assert "UniProt answered HTTP 500" in err and "Nothing was stored" in err
    assert not snapshots.exists()


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("--fetch", "--enzyme-class", "beta_glucosidase"), "--fetch applies to the UniProt proteome"),
        (("--snapshot-dir", "s", "--enzyme-class", "beta_glucosidase"), "--snapshot-dir applies to the UniProt"),
        (
            ("--proteome", "UP000000000", "--annotation", str(EXPORT_U1), "--annotation-tool", "UniProt 2026_03"),
            "--annotation, --annotation-tool and --proteome both give the fungus's annotation",
        ),
        (("--fetch-proteome", "--annotation-source", "x"), "--annotation-source and --fetch-proteome both give"),
        (("--proteome", "UP-1", "--fetch"), "is not a UniProt proteome identifier"),
        (("--fetch-proteome", "--scientific-name", 'Genus "species"', "--fetch"), "holds a double quote"),
    ],
)
def test_fungmod_assemble_refuses_inconsistent_proteome_options(
    tmp_path: Path, extra: tuple[str, ...], message: str
) -> None:
    arguments = ("assemble", "--fungus", "Strain X", "--substrate", "cellobiose", "--temperature-c", "30", "--ph", "5")
    code, out, err = _cli(*arguments, *extra, "--dataset-id", "x_draft", "--output", tmp_path / "out")

    assert code == EXIT_USAGE
    assert message in err
    assert not (tmp_path / "out").exists()


def test_assemble_help_states_the_network_opt_in() -> None:
    code, assemble_help, _ = _cli("assemble", "--help")
    assert code == EXIT_OK
    flat = " ".join(assemble_help.split())
    for option in ("--proteome PROTEOME_ID", "--fetch-proteome", "--fetch ", "--snapshot-dir DIR"):
        assert option in assemble_help
    # Option help is wrapped (possibly at a hyphen), so compare without whitespace.
    assert "".join(FETCH_HELP.split()) in "".join(assemble_help.split())
    assert NO_FETCH_HELP in flat
    assert "fungmod assemble --fetch, the one network opt-in" in NO_FETCH_HELP
    assert "data/source_snapshots/uniprot" in flat
