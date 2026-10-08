"""Kinetics of the fungus's enzyme classes looked up in SABIO-RK by EC number (FETCH-002).

``assemble_user_tables(fetch_kinetics=True)`` (``fungmod assemble --fetch-kinetics``)
queries SABIO-RK's kinetic-law export once per complete EC number of each
registry class of the repertoire that acts on a requested substrate (with
``network=True``, on a pool), restricted to the substrate's name:
``ECNumber:"<EC number>" AND Substrate:"<substrate name>"``. Each answer is a
frozen, digest-checked snapshot in the layout of
``fungal_model.sources.sabiork.fetch.fetch_and_save_export``; SABIO-RK is
reached only with ``refresh=True`` (``--fetch``). The entries then follow the
existing per-case rules of the assembly.

Every SABIO-RK answer here is a SYNTHETIC TEST RESPONSE written by hand in the
format of SABIO-RK's export API (``tests/fixtures/sabiork_kinetics_queries/``,
see its README); none is SABIO-RK data, and no organism stands behind any
entry. Every test runs with ``urlopen`` (``urllib.request`` and the SABIO-RK
fetch module) and socket connections patched to fail, so the default test run
cannot reach the network; a test that fetches serves its synthetic responses
through ``_FakeSabio``. The one in-memory registry change of the second case
(the shipped glucoamylase class widened to a maltose class, and a class without
an EC number) is test-only, as in ``tests/test_user_data_assembly.py``.
"""

from __future__ import annotations

import contextlib
import csv
import email.message
import hashlib
import io
import json
import os
import shutil
import socket
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import assemble_user_tables, load_user_dataset, virtual_experiment
from fungal_model.api.user_data import REVIEW_MARKER
from fungal_model.api.user_data_assembly import (
    DEFAULT_KINETICS_CACHE_DIR,
    NETWORK_BLOCKED,
    AssembledTablesDraft,
    KineticsLookupError,
    KineticsSnapshotConflictError,
    MissingKineticsSnapshotError,
    UserTablesAssemblyError,
)
from fungal_model.cli import EXIT_OK, EXIT_USAGE, FETCH_HELP, FETCH_KINETICS_HELP, main, shell_quote
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.sources.sabiork import SabioRKSource, SabioRKSourceError, frozen_source_urls
from fungal_model.sources.sabiork import fetch as sabiork_fetch
from fungal_model.sources.sabiork.fetch import BASE_URL, DEFAULT_PAGE_SIZE, ENDPOINT, build_kinlaw_url
from fungal_model.sources.sabiork.query_snapshots import (
    DEFAULT_SNAPSHOT_DIR,
    KINLAW_QUERY_FORM,
    KinlawFetchError,
    KinlawSnapshotConflictError,
    MissingKinlawSnapshotError,
    complete_ec_number,
    ec_number_query,
    fetch_kinlaw_query_snapshot,
    kinlaw_query_directory,
    load_kinlaw_query_snapshot,
)
from tests.test_assemble_network import (
    CHAIN,
    PARALLEL,
    TEST_OLIGOMER,
    TIME_GRID,
    _draft_digest,
    _registry_chain_draft,
    _with_registry_chain,
    _without_network_block,
)
from tests.test_user_data_assembly import _g1, _with_glucoamylase_widened_to_maltose

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
RESPONSES = ROOT / "tests" / "fixtures" / "sabiork_kinetics_queries"
ESTERASE = FIXTURES / "esterase_case"
GENOME = FIXTURES / "genome_case"
ANNOTATION = GENOME / "annotations" / "strain_g1_overview.txt"
ANNOTATION_TOOL = "dbCAN 3 overview format (hand-written fixture; no dbCAN run)"
ANNOTATION_SOURCE = "FungMod genome-route format fixture; synthetic gene identifiers, not a real genome"
EXPORT_618 = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)
G1 = "Genome-annotated strain G1"
C30_PH5 = {"temperature": 30, "temperature_units": "degC", "ph": 5}
C40_PH5 = {"temperature": 40, "temperature_units": "degC", "ph": 5}
C40_PH4_5 = {"temperature": 40, "temperature_units": "degC", "ph": 4.5}

# The registry records' own EC numbers and names make the queries; the tests state them to check that.
QUERY_A = 'ECNumber:"3.2.1.21" AND Substrate:"Cellobiose"'
QUERY_B = 'ECNumber:"3.2.1.3" AND Substrate:"maltose"'
OLIGOMER_NAME = "Test-only cellotetraose-like oligomer"
QUERIES_OLIGOMER = (
    f'ECNumber:"3.2.1.91" AND Substrate:"{OLIGOMER_NAME}"',
    f'ECNumber:"3.2.1.176" AND Substrate:"{OLIGOMER_NAME}"',
)
BODY_A = (RESPONSES / "ecnumber_3_2_1_21_cellobiose.json").read_bytes()
BODY_B = (RESPONSES / "ecnumber_3_2_1_3_maltose.json").read_bytes()
BODY_NONE = (RESPONSES / "no_entries.json").read_bytes()
K1 = "Synthetic kinetics organism K1"
K2 = "Synthetic kinetics organism K2"
K4 = "Synthetic kinetics organism K4"
NO_EC_CLASS = "test_maltose_hydrolase_without_ec"

# SHA-256 over the files, annotation digests and to_dict() of drafts WITHOUT fetch_kinetics, computed at 8a35ae5 (the
# base of FETCH-002, before the lookup existed) with tests/test_assemble_network.py's _draft_digest.
DRAFT_DIGESTS_8A35AE5 = {
    "g1_two_sources_duplicates": "89ef2e6515fc4658b149eed116da909fd131bb8e52f83c772d2322e32f945263",
    "g1_same_species": "2f28b12bb89e135f5e8e17cc2b786442255ef216c2128d6671e390382db1013a",
    "g1_entry_ids_two": "1ea75a5c955fa15f6ca65ab8d68f1226267863637d951341053cb626e7b2497b",
    "network_registry_chain": "9b436a714d4f790409c6b0d777cc963937760e4ac45ef12fb917445ffecb5ccb",
    "network_user_chain": "5ddbb776dc0f6132a441ea6ee64dc5bf7b697363b03e7cc9e1dd4b36f10cc73f",
    "network_parallel_user_data": "8afb53c686c28285d858e034d6d0b1a9d186d4b4c26f19bda21f16e7c821cf67",
}
# SHA-256 of the stdout of a network assemble of the user chain (no --fetch-kinetics), run at 8a35ae5.
CLI_NETWORK_STDOUT_DIGEST_8A35AE5 = "832f02d076447f6e4ddf10eaab162d29fc2299ea2bace4e0f2d8e4602984de4e"


# ---------------------------------------------------------------------------
# No network in the default test run


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("FETCH-002 tests must not reach the network; serve a synthetic response instead.")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(sabiork_fetch, "urlopen", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    # SABIO-RK requests are spaced at least this far apart; the synthetic responses need no pause.
    monkeypatch.setattr(sabiork_fetch, "MIN_REQUEST_INTERVAL_SECONDS", 0.0)
    yield


class _FakeResponse:
    def __init__(self, body: bytes, *, status: int) -> None:
        self._body = body
        self._status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


class _FakeSabio:
    """Serve synthetic SABIO-RK export responses by exact URL and record every URL requested."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[bytes | BaseException, int]] = {}
        self.requested: list[str] = []

    def serve(self, query: str, body: bytes | BaseException, *, page: int = 1, status: int = 200) -> str:
        url = _url(query, page)
        self.routes[url] = (body, status)
        return url

    def __call__(self, request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        assert timeout > 0
        url = request.full_url
        self.requested.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected SABIO-RK request {url}")
        body, status = self.routes[url]
        if isinstance(body, BaseException):
            raise body
        return _FakeResponse(body, status=status)


@pytest.fixture
def sabio(monkeypatch: pytest.MonkeyPatch) -> _FakeSabio:
    fake = _FakeSabio()
    monkeypatch.setattr(sabiork_fetch, "urlopen", fake)
    return fake


def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sabiork_fetch, "urlopen", _forbidden)


def _url(query: str, page: int = 1) -> str:
    return build_kinlaw_url(base_url=BASE_URL, endpoint=ENDPOINT, query=query, page=page, page_size=DEFAULT_PAGE_SIZE)


def _pages(body: bytes, sizes: Sequence[int], *, total_count: int | None = None) -> list[bytes]:
    """The entries of one synthetic response split into pages, as SABIO-RK paginates (meta per page)."""

    payload = json.loads(body)
    data = payload["data"]
    pages, start = [], 0
    for number, size in enumerate(sizes, start=1):
        meta = {
            **payload["meta"],
            "page": number,
            "total_count": len(data) if total_count is None else total_count,
            "total_pages": len(sizes),
        }
        pages.append((json.dumps({"meta": meta, "data": data[start : start + size]}, indent=2) + "\n").encode())
        start += size
    return pages


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()
    }


def _bundles(cache: Path, query: str) -> list[Path]:
    directory = kinlaw_query_directory(query, cache_dir=cache)
    return sorted(path for path in directory.iterdir()) if directory.is_dir() else []


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _k1(cache: Path, **overrides: Any) -> AssembledTablesDraft:
    """Strain K1, whose species is the organism of entry 9900001, with beta-glucosidase asserted."""

    arguments: dict[str, Any] = {
        "dataset_id": "k1_draft",
        "fungus": "Strain K1",
        "scientific_name": K1,
        "substrates": ["cellobiose"],
        "conditions": [C30_PH5, C40_PH5],
        "enzyme_classes": [
            {
                "enzyme_class": "beta_glucosidase",
                "evidence": "test-only assertion, not a measurement",
                "source": "tests/test_fetch_kinetics.py",
            }
        ],
        "registry": REGISTRY_INDEX,
        "cache_dir": cache,
        "fetch_kinetics": True,
    }
    arguments.update(overrides)
    return assemble_user_tables(**arguments)


def _query(draft: AssembledTablesDraft, query: str) -> dict[str, Any]:
    (item,) = [item for item in draft.assembly["kinetics_lookup"]["queries"] if item["query"] == query]
    return item


def _uses(item: dict[str, Any]) -> dict[str, str]:
    return {
        **{entry["entry_id"]: "converted" for entry in item["converted"]},
        **{entry["entry_id"]: entry["use"] for entry in item["not_converted"]},
    }


def test_the_default_test_run_cannot_reach_the_network(tmp_path: Path) -> None:
    assert sabiork_fetch.urlopen is _forbidden
    assert urllib.request.urlopen is _forbidden
    with pytest.raises(AssertionError, match="must not reach the network"):
        fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=tmp_path, refresh=True)
    assert not kinlaw_query_directory(QUERY_A, cache_dir=tmp_path).exists()


# ---------------------------------------------------------------------------
# The query and its snapshot


def test_the_query_names_a_complete_ec_number_and_a_substrate_name_only() -> None:
    assert ec_number_query("3.2.1.21", substrate="Cellobiose") == QUERY_A
    assert ec_number_query("EC 3.2.1.3", substrate="  maltose ") == QUERY_B
    assert KINLAW_QUERY_FORM == 'ECNumber:"<EC number>" AND Substrate:"<substrate name>"'
    assert complete_ec_number("EC 3.2.1.176") == "3.2.1.176"
    for partial in ("3.2.1.-", "3.2.1", "3.2.1.n1", "beta-glucosidase", ""):
        assert complete_ec_number(partial) is None
        with pytest.raises(SabioRKSourceError, match="not a complete EC number"):
            ec_number_query(partial, substrate="Cellobiose")
    with pytest.raises(SabioRKSourceError, match="nonblank substrate name"):
        ec_number_query("3.2.1.21", substrate=" ")
    for unquotable in ('Cello"biose', "Cello\\biose", "Cello\nbiose"):
        with pytest.raises(SabioRKSourceError, match="does not guess an escaping"):
            ec_number_query("3.2.1.21", substrate=unquotable)
    assert DEFAULT_KINETICS_CACHE_DIR == DEFAULT_SNAPSHOT_DIR == "data/source_snapshots/sabiork"


def test_an_answer_is_frozen_in_the_existing_snapshot_layout_and_read_back_offline(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sabio.serve(QUERY_A, BODY_A)
    cache = tmp_path / "kinetics"

    snapshot = fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=cache, refresh=True)

    assert sabio.requested == [_url(QUERY_A)]
    (bundle,) = _bundles(cache, QUERY_A)
    assert snapshot.bundle == bundle
    # The layout of fetch_and_save_export: the raw page byte for byte, the combined export and the metadata.
    assert (bundle / "raw" / "page_0001.json").read_bytes() == BODY_A
    metadata = json.loads((bundle / "fetch_metadata.json").read_text(encoding="utf-8"))
    assert metadata["query"] == QUERY_A
    assert metadata["source_urls"] == [_url(QUERY_A)]
    assert metadata["http_status"] == 200
    assert metadata["total_count"] == 7
    assert metadata["raw_pages"][0]["sha256"] == hashlib.sha256(BODY_A).hexdigest()
    assert metadata["immutable_snapshot_bundle"] is True
    assert metadata["warnings"] == []
    assert snapshot.entry_count == 7 and snapshot.http_status == 200
    assert snapshot.raw_sha256 == (hashlib.sha256(BODY_A).hexdigest(),)
    assert snapshot.relative_bundle == f"{kinlaw_query_directory(QUERY_A, cache_dir='.').name}/{bundle.name}"
    assert snapshot.retrieved_at == metadata["fetched_at"]
    # The existing readers find and validate the same snapshot: no parallel layout.
    assert frozen_source_urls(str(snapshot.export_path)) == (_url(QUERY_A),)
    assert SabioRKSource(cache_dir=cache).fetch_kinlaw_entries(QUERY_A).export_path == snapshot.export_path

    _offline(monkeypatch)
    again = load_kinlaw_query_snapshot(QUERY_A, cache_dir=cache)
    assert again.to_dict() == snapshot.to_dict()
    assert fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=cache).to_dict() == snapshot.to_dict()

    # A new fetch whose bytes equal the stored answer keeps the stored snapshot; no second one is written.
    monkeypatch.setattr(sabiork_fetch, "urlopen", sabio)
    assert fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=cache, refresh=True).bundle == bundle
    assert _bundles(cache, QUERY_A) == [bundle]

    with pytest.raises(MissingKinlawSnapshotError, match="pass refresh=True to fetch it") as missing:
        load_kinlaw_query_snapshot(QUERY_B, cache_dir=cache)
    assert missing.value.directory == kinlaw_query_directory(QUERY_B, cache_dir=cache)


def test_a_paginated_answer_is_combined_and_an_incomplete_one_stores_nothing(sabio: _FakeSabio, tmp_path: Path) -> None:
    first, second = _pages(BODY_A, (4, 3))
    sabio.serve(QUERY_A, first)
    sabio.serve(QUERY_A, second, page=2)

    snapshot = fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=tmp_path / "paged", refresh=True)

    assert sabio.requested == [_url(QUERY_A), _url(QUERY_A, 2)]
    assert snapshot.entry_count == 7 and snapshot.total_count == 7
    assert snapshot.raw_sha256 == (hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())
    entries = json.loads(snapshot.export_path.read_text(encoding="utf-8"))["data"]
    assert [entry["id"] for entry in entries] == [9900001 + index for index in range(7)]

    # The second page fails: refused, nothing stored.
    sabio.serve(QUERY_A, urllib.error.HTTPError("u", 503, "Service Unavailable", email.message.Message(), None), page=2)
    with pytest.raises(KinlawFetchError, match="HTTP 503.*Nothing was stored"):
        fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=tmp_path / "failed_page", refresh=True)
    assert not (tmp_path / "failed_page").exists()

    # A total_count larger than the entries returned (one page, no further page announced): refused as truncated.
    (truncated,) = _pages(BODY_A, (7,), total_count=9)
    sabio.serve(QUERY_A, truncated)
    with pytest.raises(KinlawFetchError, match="total_count 9.*hold 7 entries.*truncated.*Nothing was stored"):
        fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=tmp_path / "truncated", refresh=True)
    assert not (tmp_path / "truncated").exists()


@pytest.mark.parametrize(
    ("body", "status", "message"),
    [
        (urllib.error.HTTPError("u", 500, "Internal Server Error", email.message.Message(), None), 200, "HTTP 500"),
        (urllib.error.URLError("connection refused"), 200, "could not be reached"),
        (b"<html>maintenance</html>", 200, "not a usable kinetic-law export"),
        (b'{"data": []}', 200, "not a usable kinetic-law export"),
        (b"\xff\xfe not text", 200, "not a usable kinetic-law export"),
        (BODY_A, 203, "HTTP 203, not 200"),
    ],
    # Short ids: the default id would embed the whole response body, and pytest exports the test id in an
    # environment variable, which Windows limits to 32767 characters.
    ids=["http_500", "unreachable", "html_body", "empty_envelope", "not_utf8", "http_203"],
)
def test_http_errors_and_unusable_answers_store_nothing(
    sabio: _FakeSabio, tmp_path: Path, body: bytes | BaseException, status: int, message: str
) -> None:
    sabio.serve(QUERY_A, body, status=status)
    cache = tmp_path / "kinetics"

    with pytest.raises(KinlawFetchError, match=message) as refused:
        fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=cache, refresh=True)

    assert "Nothing was stored" in str(refused.value)
    assert not cache.exists()


def test_a_changed_superseded_or_doubled_snapshot_is_kept_and_refused(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sabio.serve(QUERY_A, BODY_A)
    cache = tmp_path / "kinetics"
    snapshot = fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=cache, refresh=True)
    stored = _files(cache)
    directory = kinlaw_query_directory(QUERY_A, cache_dir=cache)

    # SABIO-RK now answers with other bytes: the stored snapshot is kept and the call refused.
    sabio.serve(QUERY_A, BODY_A.replace(b'"start_value": 12,', b'"start_value": 13,'))
    with pytest.raises(KinlawSnapshotConflictError, match=f"The snapshot is kept; remove .*{directory.name}") as newer:
        fetch_kinlaw_query_snapshot(QUERY_A, cache_dir=cache, refresh=True)
    assert newer.value.directory == directory
    assert _files(cache) == stored

    # A raw page changed after it was stored.
    _offline(monkeypatch)
    page = snapshot.bundle / "raw" / "page_0001.json"
    page.write_bytes(BODY_A.replace(b'"start_value": 12,', b'"start_value": 14,'))
    with pytest.raises(KinlawSnapshotConflictError, match="changed after it was stored.*It is kept; remove"):
        load_kinlaw_query_snapshot(QUERY_A, cache_dir=cache)
    page.write_bytes(BODY_A)
    # The combined export changed after it was stored.
    original = snapshot.export_path.read_bytes()
    snapshot.export_path.write_bytes(original.replace(b"9900002", b"9900009"))
    with pytest.raises(KinlawSnapshotConflictError, match="does not record"):
        load_kinlaw_query_snapshot(QUERY_A, cache_dir=cache)
    snapshot.export_path.write_bytes(original)
    assert load_kinlaw_query_snapshot(QUERY_A, cache_dir=cache).to_dict() == snapshot.to_dict()

    # Two snapshots of one query: FungMod does not choose between them.
    shutil.copytree(snapshot.bundle, directory / "20000101T000000000000Z-copy")
    with pytest.raises(KinlawSnapshotConflictError, match="holds 2 snapshots .* does not choose"):
        load_kinlaw_query_snapshot(QUERY_A, cache_dir=cache)


# ---------------------------------------------------------------------------
# The assembly: the existing per-case rules on looked-up entries


def test_own_species_entries_are_literature_and_an_offline_rerun_is_byte_identical(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sabio.serve(QUERY_A, BODY_A)
    cache = tmp_path / "kinetics"

    draft = _k1(cache, refresh=True)

    assert sabio.requested == [_url(QUERY_A)]
    statuses = {case["condition"]: case for case in draft.assembly["cases"]}
    assert statuses["c30_ph5"]["kinetics_status"] == "literature_same_organism"
    assert statuses["c30_ph5"]["source_ids"] == ["SABIO-RK EntryID 9900001"]
    # 40 degC: nothing was measured there, and the 30 degC kinetics are not reused without a response law.
    assert statuses["c40_ph5"]["kinetics_status"] == "gap"
    assert "does not reuse them at 40 degC, pH 5 without a temperature response law" in statuses["c40_ph5"]["reason"]
    rows = {row["quantity"]: row for row in draft.kinetics}
    assert {key: rows["km"][key] for key in ("value", "units", "sd", "evidence_type")} == {
        "value": "2.5",
        "units": "mM",
        "sd": "0.2",
        "evidence_type": "literature",
    }
    assert rows["kcat"]["value"] == "12" and rows["kcat"]["evidence_type"] == "literature"

    lookup = draft.assembly["kinetics_lookup"]
    assert lookup["database"] == "SABIO-RK"
    assert lookup["not_queried"] == []
    item = _query(draft, QUERY_A)
    assert (item["enzyme_class"], item["ec_number"], item["substrate_id"]) == ("beta_glucosidase", "3.2.1.21", "cellobiose")
    assert item["entries"] == 7 and item["http_status"] == 200 and item["source_urls"] == [_url(QUERY_A)]
    assert item["counts"] == {"converted": 1, "listed": 1, "not used": 2, "not convertible": 3}
    (converted,) = item["converted"]
    assert converted["entry_id"] == "9900001"
    assert [(case["condition"], case["kinetics_status"]) for case in converted["cases"]] == [
        ("c30_ph5", "literature_same_organism"),
        ("c40_ph5", "gap"),
    ]
    reasons = {entry["entry_id"]: entry for entry in item["not_converted"]}
    assert reasons["9900002"]["use"] == "listed" and "weaker evidence" in reasons["9900002"]["reason"]
    assert "45 degC, pH 6, which is not a requested condition" in reasons["9900003"]["reason"]
    assert reasons["9900004"]["reason"].startswith("mutant enzyme")
    assert "no Km, kcat or Vmax could be converted" in reasons["9900005"]["reason"]
    assert {parameter["reason"] for parameter in reasons["9900005"]["parameters_not_converted"]} == {
        "units 'arbitrary units' are not parsed by the unit registry and are not in the SABIO-RK unit table"
    }
    assert reasons["9900006"]["reason"] == "its substrate 'Synthetic acceptor A9' is not a requested substrate"
    assert reasons["9900007"]["parameters_not_converted"][0]["reason"].startswith("kcat/Km is not a user-data quantity")
    # The draft records the query, its snapshot and its digest, never whether this run reached the network.
    assert f"SABIO-RK query {QUERY_A} (7 entries, retrieved {item['retrieved_at']}" in draft.manifest["source"]
    assert item["export_sha256"] in draft.manifest["source"]
    assert "## Kinetics looked up by EC number" in draft.review
    assert "fetched only on explicit request (refresh=True)" in draft.review
    assert str(cache) not in json.dumps(draft.to_dict()) and str(tmp_path) not in draft.review

    _offline(monkeypatch)
    offline = _k1(cache)
    assert _draft_digest(offline) == _draft_digest(draft)
    assert offline.file_texts() == draft.file_texts()

    # A snapshot changed after it was stored is refused by the assembly too, and kept.
    (bundle,) = _bundles(cache, QUERY_A)
    page = bundle / "raw" / "page_0001.json"
    page.write_bytes(BODY_A.replace(b'"start_value": 2.5,', b'"start_value": 2.6,'))
    with pytest.raises(KineticsSnapshotConflictError, match="changed after it was stored") as changed:
        _k1(cache)
    assert changed.value.directory == kinlaw_query_directory(QUERY_A, cache_dir=cache)
    page.write_bytes(BODY_A)

    without = _k1(cache, fetch_kinetics=False, enzyme_classes=["beta_glucosidase"])
    assert "kinetics_lookup" not in without.assembly
    assert [case["kinetics_status"] for case in without.assembly["cases"]] == ["gap", "gap"]
    assert "Nothing was fetched while assembling." in without.review


def test_other_organisms_are_transfers_and_several_at_one_condition_are_a_conflict(
    sabio: _FakeSabio, tmp_path: Path
) -> None:
    sabio.serve(QUERY_A, BODY_A)
    cache = tmp_path / "kinetics"
    request: dict[str, Any] = {
        "dataset_id": "g1_lookup",
        "fungus": G1,
        "substrates": ["cellobiose"],
        "conditions": [C30_PH5],
        "annotation": ANNOTATION,
        "annotation_tool": ANNOTATION_TOOL,
        "annotation_source": ANNOTATION_SOURCE,
        "registry": REGISTRY_INDEX,
        "cache_dir": cache,
        "fetch_kinetics": True,
    }

    conflict = assemble_user_tables(**request, refresh=True)

    # Only the one class of the annotation that acts on the substrate is looked up.
    assert sabio.requested == [_url(QUERY_A)]
    (case,) = conflict.assembly["cases"]
    assert case["kinetics_status"] == "conflict"
    assert set(case["source_ids"]) == {"SABIO-RK EntryID 9900001", "SABIO-RK EntryID 9900002"}
    assert conflict.kinetics == ()
    assert _query(conflict, QUERY_A)["counts"]["listed"] == 2

    chosen = assemble_user_tables(**request, entry_ids=["9900002"])
    (case,) = chosen.assembly["cases"]
    assert case["kinetics_status"] == "transferred_estimate"
    assert chosen.assembly["transferred_entry_ids"] == ["9900002"]
    constants = [row for row in chosen.kinetics if row["quantity"] in {"km", "kcat"}]
    assert {row["evidence_type"] for row in constants} == {"estimate"}
    assert all(row["method"].startswith(f"transferred from {K2} enzyme, SABIO-RK entry 9900002") for row in constants)
    assert _uses(_query(chosen, QUERY_A))["9900001"] == "not selected"

    # same_species names an organism of the looked-up entries: its entry becomes the fungus's literature.
    declared = assemble_user_tables(**request, same_species=[K1])
    (case,) = declared.assembly["cases"]
    assert (case["kinetics_status"], case["source_ids"]) == ("literature_same_organism", ["SABIO-RK EntryID 9900001"])

    # A local export and the lookup together: both are kinetics sources under the same rules.
    combined = assemble_user_tables(**request, kinetics_sources=[EXPORT_618], entry_ids=["35622", "9900002"])
    (case,) = combined.assembly["cases"]
    assert case["kinetics_status"] == "conflict"
    assert set(case["source_ids"]) == {"SABIO-RK EntryID 35622", "SABIO-RK EntryID 9900002"}
    sources = {item["kind"] for item in combined.assembly["sources"]}
    assert sources == {"sabiork", "sabiork_query"}


def test_a_network_member_gets_kinetics_while_another_stays_a_gap(
    sabio: _FakeSabio, tmp_path_factory: pytest.TempPathFactory
) -> None:
    registry = _with_registry_chain(load_registry(REGISTRY_INDEX))
    for query in QUERIES_OLIGOMER:
        sabio.serve(query, BODY_NONE)
    sabio.serve(QUERY_A, BODY_A)
    # The oligomer's long name makes a long snapshot directory name; a short root keeps Windows paths short.
    cache = tmp_path_factory.mktemp("k")

    draft = _registry_chain_draft(
        registry,
        kinetics_sources=(),
        entry_ids=None,
        same_species=[K1],
        cache_dir=cache,
        fetch_kinetics=True,
        refresh=True,
    )

    # The cellobiohydrolase record states two EC numbers (3.2.1.91 and, as an alias, 3.2.1.176): both are queried.
    assert sabio.requested == [_url(query) for query in (*QUERIES_OLIGOMER, QUERY_A)]
    (network,) = draft.assembly["network"]["networks"]
    members = {member["enzyme_class"]: member for member in network["members"]}
    assert members["beta_glucosidase"]["pool"] == "cellobiose"
    assert members["beta_glucosidase"]["kinetics_status"] == {"c30_ph5": "literature_same_organism"}
    assert members["cellobiohydrolase"]["kinetics_status"] == {"c30_ph5": "gap"}
    (condition,) = network["conditions"]
    assert condition["status"] == NETWORK_BLOCKED
    assert any("cellobiohydrolase" in reason for reason in condition["blocked_by"])
    for query in QUERIES_OLIGOMER:
        item = _query(draft, query)
        assert (item["entries"], item["converted"], item["not_converted"], item["counts"]) == (0, [], [], {})
        assert item["substrate_id"] == TEST_OLIGOMER
    assert _query(draft, QUERY_A)["converted"][0]["entry_id"] == "9900001"
    # The intermediate pool starts at zero: the entry's assay concentration is not written for it.
    assert all(
        not (row["substrate_id"] == "cellobiose" and row["quantity"] == "substrate_initial_concentration")
        for row in draft.kinetics
    )
    assert "Nothing was fetched while assembling" not in draft.review


def _maltose_registry() -> FungModRegistry:
    """The registry with glucoamylase widened to a maltose class, plus a TEST-ONLY maltose class without an EC number."""

    widened = _with_glucoamylase_widened_to_maltose(load_registry(REGISTRY_INDEX))
    shipped = widened.enzyme_classes["glucoamylase"]
    without_ec = replace(
        shipped,
        record_id=NO_EC_CLASS,
        name="Test-only maltose hydrolase without an EC number",
        display_name=NO_EC_CLASS,
        aliases=(),
        ec_number="",
        compatible_substrate_classes=("maltose",),
        provenance={"test_only": "in-memory class of tests/test_fetch_kinetics.py; not a shipped record"},
        notes="Test-only record without an EC number; not a shipped registry enzyme class.",
    )
    return FungModRegistry.build(
        registry_id=widened.registry_id,
        version=widened.version,
        maturity=widened.maturity,
        provenance=widened.provenance,
        fungi=widened.fungi.values(),
        enzyme_classes=(*widened.enzyme_classes.values(), without_ec),
        substrates=widened.substrates.values(),
        environments=widened.environments.values(),
        process_compatibility=widened.process_compatibility.values(),
        parameters=widened.parameters.values(),
        case_templates=widened.case_templates.values(),
        product_maps=widened.product_maps.values(),
    )


def test_a_second_class_and_substrate_follow_the_same_rules(sabio: _FakeSabio, tmp_path: Path) -> None:
    """Another EC number, another (non-registry) substrate, the Vmax form, and a class without an EC number."""

    registry = _maltose_registry()
    maltose = _csv_rows(GENOME / "substrates.csv")[1]
    described = {key: value for key, value in maltose.items() if key not in {"registry_substrate", "yield_basis"}}
    described["substrate"] = described.pop("name")
    sabio.serve(QUERY_B, BODY_B)
    cache = tmp_path / "kinetics"

    draft = assemble_user_tables(
        dataset_id="maltose_lookup",
        fungus=G1,
        substrates=[described],
        conditions=[C40_PH4_5],
        annotation=ANNOTATION,
        annotation_tool=ANNOTATION_TOOL,
        annotation_source=ANNOTATION_SOURCE,
        enzyme_classes=[
            {
                "enzyme_class": NO_EC_CLASS,
                "evidence": "test-only assertion, not a measurement",
                "source": "tests/test_fetch_kinetics.py",
            }
        ],
        design={"substrate_initial_concentration": {"value": 5, "units": "mM"}},
        time_grid=TIME_GRID,
        registry=registry,
        cache_dir=cache,
        fetch_kinetics=True,
        refresh=True,
    )

    assert sabio.requested == [_url(QUERY_B)]
    cases = {case["enzyme_class"]: case for case in draft.assembly["cases"]}
    assert cases["glucoamylase"]["kinetics_status"] == "transferred_estimate"
    assert cases["glucoamylase"]["source_ids"] == ["SABIO-RK EntryID 9900011"]
    assert cases[NO_EC_CLASS]["kinetics_status"] == "gap"
    rows = {row["quantity"]: row for row in draft.kinetics if row["enzyme_class"] == "glucoamylase"}
    assert {key: rows["vmax"][key] for key in ("value", "units", "evidence_type")} == {
        "value": "0.8",
        "units": "mM*min^(-1)",
        "evidence_type": "estimate",
    }
    assert "kcat" not in rows and rows["km"]["value"] == "3.2"
    assert rows["km"]["method"].startswith(f"transferred from {K4} enzyme, SABIO-RK entry 9900011")
    item = _query(draft, QUERY_B)
    assert item["substrate_id"] == "maltose" and item["ec_number"] == "3.2.1.3"
    assert _uses(item) == {"9900011": "converted", "9900012": "not used"}
    (not_queried,) = draft.assembly["kinetics_lookup"]["not_queried"]
    assert not_queried["enzyme_class"] == NO_EC_CLASS
    assert "states no complete EC number" in not_queried["reason"]
    assert "never by a class or enzyme name" in not_queried["reason"]

    # The reviewed draft loads, and its transferred case is runnable in exploratory mode only.
    directory = tmp_path / "draft"
    draft.write(directory)
    manifest = yaml.safe_load((directory / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    (directory / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    assert REVIEW_MARKER not in "".join(path.read_text(encoding="utf-8") for path in directory.glob("*.csv"))
    dataset = load_user_dataset(directory, registry=registry)
    (condition,) = draft.assembly["requested_conditions"]
    study = virtual_experiment(
        fungi=G1, substrates="maltose", environments=condition["condition_id"], user_data=dataset, registry=registry
    )
    (exploratory,) = study.preflight(mode="exploratory")
    assert exploratory.status == "modelable"
    # Transferred kinetics are estimates: scientific mode refuses them.
    (scientific,) = study.preflight(mode="scientific")
    assert scientific.status == "underparameterized"


def test_classes_that_cannot_be_looked_up_are_listed_and_not_queried(sabio: _FakeSabio, tmp_path: Path) -> None:
    # A user-defined class with an EC number: SABIO-RK entries become kinetics of registry classes only.
    esterase = assemble_user_tables(
        dataset_id="esterase_lookup",
        fungus="strain_e1",
        substrates=["p_nitrophenyl_butyrate"],
        conditions=[{"temperature": 37, "temperature_units": "degC", "ph": 7.5}],
        user_data=ESTERASE,
        cache_dir=tmp_path / "kinetics",
        fetch_kinetics=True,
        refresh=True,
    )
    assert sabio.requested == []
    lookup = esterase.assembly["kinetics_lookup"]
    assert lookup["queries"] == []
    (item,) = lookup["not_queried"]
    assert item["enzyme_class"] == "carboxylesterase"
    assert "an enzyme class of the user dataset (enzyme_classes.csv, EC 3.1.1.1)" in item["reason"]
    assert [case["kinetics_status"] for case in esterase.assembly["cases"]] == ["user_data"]
    assert "No query was made." in esterase.review

    # A user class without an EC number, in a network draft.
    chain = assemble_user_tables(
        dataset_id="chain_lookup",
        fungus="strain_n1",
        substrates=["polymer_p1"],
        conditions=[C30_PH5],
        user_data=_without_network_block(tmp_path, CHAIN),
        network=True,
        cache_dir=tmp_path / "kinetics",
        fetch_kinetics=True,
    )
    reasons = {item["enzyme_class"]: item["reason"] for item in chain.assembly["kinetics_lookup"]["not_queried"]}
    assert set(reasons) == {"depolymerase_like", "oligomer_hydrolase_like"}
    assert all("enzyme_classes.csv, no EC number" in reason for reason in reasons.values())

    # A new substrate whose categories are REVIEW fields: which classes act on it is not known, so nothing is queried.
    undetermined = _k1(tmp_path / "kinetics", substrates=["Synthetic undescribed substrate U1"], refresh=True)
    assert sabio.requested == []
    (item,) = undetermined.assembly["kinetics_lookup"]["not_queried"]
    assert item["enzyme_class"] == "" and "are REVIEW fields" in item["reason"]


def test_fetch_kinetics_arguments_are_checked(tmp_path: Path) -> None:
    with pytest.raises(UserTablesAssemblyError, match="refresh is the network opt-in of fetch_kinetics"):
        _k1(tmp_path, fetch_kinetics=False, refresh=True)
    with pytest.raises(UserTablesAssemblyError, match="fetch_kinetics must be True or False"):
        _k1(tmp_path, fetch_kinetics="yes")
    with pytest.raises(UserTablesAssemblyError, match="refresh must be True or False"):
        _k1(tmp_path, refresh=1)
    with pytest.raises(UserTablesAssemblyError, match="so without a repertoire there is nothing to look up"):
        _k1(tmp_path, enzyme_classes=None)
    with pytest.raises(MissingKineticsSnapshotError, match="no frozen SABIO-RK snapshot for 1 of its 1 queries") as missing:
        _k1(tmp_path)
    (item,) = missing.value.missing
    assert item["query"] == QUERY_A and item["enzyme_class"] == "beta_glucosidase"
    assert item["directory"] == str(kinlaw_query_directory(QUERY_A, cache_dir=tmp_path))
    assert isinstance(missing.value, KineticsLookupError) and isinstance(missing.value, UserTablesAssemblyError)
    assert not any(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# Without fetch_kinetics nothing changes


def _plain_chain(tmp_path: Path) -> Path:
    """The network_chain fixture without its enzyme_network block, written with LF line ends on every platform."""

    target = tmp_path / "my_chain"
    shutil.copytree(CHAIN, target)
    manifest = yaml.safe_load((target / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest.pop("enzyme_network")
    (target / "user_dataset.yml").write_bytes(yaml.safe_dump(manifest, sort_keys=False).encode("utf-8"))
    return target


def _baseline_drafts(tmp_path: Path) -> dict[str, Any]:
    plain = _plain_chain(tmp_path)
    return {
        "g1_two_sources_duplicates": lambda: _g1(kinetics_sources=[EXPORT_618, "618"], entry_ids=None),
        "g1_same_species": lambda: _g1(same_species=["Oryza sativa"]),
        "g1_entry_ids_two": lambda: _g1(entry_ids=["35622", "38521"], conditions=[C30_PH5, C40_PH5]),
        "network_registry_chain": lambda: _registry_chain_draft(_with_registry_chain(load_registry(REGISTRY_INDEX))),
        "network_user_chain": lambda: assemble_user_tables(
            dataset_id="chain_draft",
            fungus="strain_n1",
            substrates=["polymer_p1"],
            conditions=[C30_PH5, C40_PH5],
            user_data=plain,
            network=True,
        ),
        "network_parallel_user_data": lambda: assemble_user_tables(
            dataset_id="parallel_draft",
            fungus="strain_q2",
            substrates=["ester_s2"],
            conditions=[{"temperature": 25, "temperature_units": "degC", "ph": 7}],
            user_data=PARALLEL,
            network=True,
        ),
    }


@pytest.mark.parametrize("name", sorted(DRAFT_DIGESTS_8A35AE5))
def test_drafts_without_fetch_kinetics_are_byte_identical_to_the_base_commit(name: str, tmp_path: Path) -> None:
    draft = _baseline_drafts(tmp_path)[name]()
    assert _draft_digest(draft) == DRAFT_DIGESTS_8A35AE5[name]
    assert "kinetics_lookup" not in draft.assembly
    assert all(item["kind"] == "sabiork" for item in draft.assembly["sources"])


@pytest.mark.skipif(os.name == "nt", reason="printed commands quote arguments for cmd on Windows")
def test_a_network_assemble_without_fetch_kinetics_prints_what_it_printed_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plain_chain(tmp_path)
    monkeypatch.chdir(tmp_path)
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "strain_n1",
        "--user-data",
        "my_chain",
        "--substrate",
        "polymer_p1",
        "--temperature-c",
        "30",
        "--temperature-c",
        "40",
        "--ph",
        "5",
        "--network",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "chain_draft",
        "--output",
        "chain_draft",
    )
    assert code == EXIT_OK, err
    assert hashlib.sha256(out.encode("utf-8")).hexdigest() == CLI_NETWORK_STDOUT_DIGEST_8A35AE5


# ---------------------------------------------------------------------------
# fungmod assemble --fetch-kinetics


def _cli(*args: str | Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def _assemble_k1(cache: Path, *extra: str | Path) -> list[str]:
    return [
        str(argument)
        for argument in (
            "assemble",
            "--fungus",
            "Strain K1",
            "--scientific-name",
            K1,
            "--enzyme-class-evidence",
            "beta_glucosidase",
            "test-only assertion, not a measurement",
            "tests/test_fetch_kinetics.py",
            "--substrate",
            "cellobiose",
            "--temperature-c",
            "30",
            "--temperature-c",
            "40",
            "--ph",
            "5",
            "--design",
            "substrate_initial_concentration=10",
            "mM",
            "--design",
            "enzyme_concentration=0.001",
            "mM",
            "--time-grid",
            "10",
            "hour",
            "61",
            "--registry",
            REGISTRY_INDEX,
            "--cache-dir",
            cache,
            "--dataset-id",
            "k1_draft",
            "--fetch-kinetics",
            *extra,
        )
    ]


def test_fungmod_assemble_fetches_kinetics_runs_and_reruns_offline_byte_for_byte(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sabio.serve(QUERY_A, BODY_A)
    cache = tmp_path / "kinetics"
    draft_dir = tmp_path / "draft"

    code, out, err = _cli(*_assemble_k1(cache, "--fetch", "--output", draft_dir))

    assert code == EXIT_OK, err
    assert sabio.requested == [_url(QUERY_A)]
    assert "Kinetics looked up by EC number (--fetch-kinetics; SABIO-RK https://sabio.h-its.org/" in out
    assert f"network: --fetch given; each query below was sent to the database and its answer is frozen under {cache}" in out
    assert f"beta_glucosidase on cellobiose, EC 3.2.1.21: {QUERY_A}" in out
    assert "7 entries; 1 converted, 1 listed, 2 not used, 3 not convertible" in out
    assert (
        "converted 9900001 (Synthetic kinetics organism K1) -> beta_glucosidase on cellobiose at c30_ph5 "
        "(literature_same_organism), beta_glucosidase on cellobiose at c40_ph5 (gap)"
    ) in out
    assert "not used 9900006 (Synthetic kinetics organism K3): its substrate 'Synthetic acceptor A9'" in out
    assert "parameter kcat (7 arbitrary units): units 'arbitrary units' are not parsed" in out
    assert "--runnable-only" in out
    first = _files(draft_dir)
    assert "## Kinetics looked up by EC number" in first["review.md"].decode("utf-8")

    # Offline, without --fetch: the frozen snapshot gives the same draft, byte for byte.
    _offline(monkeypatch)
    rerun = tmp_path / "rerun"
    code, out_offline, err = _cli(*_assemble_k1(cache, "--output", rerun))
    assert code == EXIT_OK, err
    assert f"network: not used; frozen snapshots under {cache} (--fetch queries the database)" in out_offline
    assert _files(rerun) == first

    # The reviewed draft is checked and run: the 30 degC case from the looked-up literature entry.
    manifest = yaml.safe_load((draft_dir / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    (draft_dir / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    code, out_check, err_check = _cli("check-data", draft_dir, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err_check
    code, out_run, err_run = _cli(
        "run",
        "--user-data",
        draft_dir,
        "--fungus",
        "Strain K1",
        "--substrate",
        "cellobiose",
        "--condition",
        "c30_ph5",
        "--registry",
        REGISTRY_INDEX,
        "--mode",
        "scientific",
        "--output",
        tmp_path / "run",
        "--no-plots",
    )
    assert code == EXIT_OK, err_run
    assert "c30_ph5" in out_run


def test_fungmod_assemble_lists_what_it_cannot_look_up_and_makes_no_request(sabio: _FakeSabio, tmp_path: Path) -> None:
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "strain_e1",
        "--user-data",
        ESTERASE,
        "--substrate",
        "p_nitrophenyl_butyrate",
        "--temperature-c",
        "37",
        "--ph",
        "7.5",
        "--fetch-kinetics",
        "--fetch",
        "--cache-dir",
        tmp_path / "kinetics",
        "--registry",
        REGISTRY_INDEX,
        "--dataset-id",
        "esterase_lookup",
        "--output",
        tmp_path / "draft",
    )

    assert code == EXIT_OK, err
    assert sabio.requested == []
    assert "\n  no query was made\n" in out and "  network: " not in out
    assert (
        "  not queried: carboxylesterase on p_nitrophenyl_butyrate: carboxylesterase is an enzyme class of the user "
        "dataset (enzyme_classes.csv, EC 3.1.1.1)"
    ) in out
    assert not (tmp_path / "kinetics").exists()


def test_fungmod_assemble_without_a_kinetics_snapshot_prints_the_command_that_fetches_it(tmp_path: Path) -> None:
    cache = tmp_path / "kinetics"
    output = tmp_path / "draft"
    arguments = _assemble_k1(cache, "--output", output)

    code, out, err = _cli(*arguments)

    assert code == EXIT_USAGE
    assert f"no frozen snapshot of 1 kinetics query of --fetch-kinetics in {cache}" in err
    assert "the command line reaches the kinetics database only with --fetch" in err
    assert f"beta_glucosidase on cellobiose, EC 3.2.1.21: {QUERY_A}" in err
    assert f"fungmod {' '.join(shell_quote(argument) for argument in arguments)} --fetch" in err
    assert not output.exists() and not cache.exists()


def test_fungmod_assemble_refuses_a_superseded_or_changed_kinetics_snapshot(
    sabio: _FakeSabio, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sabio.serve(QUERY_A, BODY_A)
    cache = tmp_path / "kinetics"
    assert _cli(*_assemble_k1(cache, "--fetch", "--output", tmp_path / "first"))[0] == EXIT_OK
    directory = kinlaw_query_directory(QUERY_A, cache_dir=cache)
    stored = _files(cache)

    sabio.serve(QUERY_A, BODY_A.replace(b'"start_value": 30,', b'"start_value": 31,', 1))
    code, out, err = _cli(*_assemble_k1(cache, "--fetch", "--output", tmp_path / "newer"))
    assert code == EXIT_USAGE
    assert "The snapshot is kept" in err
    assert f"remove {directory} (or choose another --cache-dir)" in err
    assert _files(cache) == stored and not (tmp_path / "newer").exists()

    _offline(monkeypatch)
    (bundle,) = _bundles(cache, QUERY_A)
    page = bundle / "raw" / "page_0001.json"
    page.write_bytes(page.read_bytes().replace(b'"start_value": 12,', b'"start_value": 21,'))
    code, out, err = _cli(*_assemble_k1(cache, "--output", tmp_path / "tampered"))
    assert code == EXIT_USAGE
    assert "changed after it was stored" in err and f"remove {directory}" in err
    assert not (tmp_path / "tampered").exists()


def test_fungmod_assemble_kinetics_http_error_and_truncated_answer_store_nothing(
    sabio: _FakeSabio, tmp_path: Path
) -> None:
    cache = tmp_path / "kinetics"
    sabio.serve(QUERY_A, urllib.error.HTTPError("u", 500, "Internal Server Error", email.message.Message(), None))
    code, out, err = _cli(*_assemble_k1(cache, "--fetch", "--output", tmp_path / "error"))
    assert code == EXIT_USAGE
    assert "SABIO-RK answered HTTP 500" in err and "Nothing was stored" in err
    assert not cache.exists() and not (tmp_path / "error").exists()

    first, _second = _pages(BODY_A, (4, 3))
    sabio.serve(QUERY_A, first.replace(b'"total_pages": 2', b'"total_pages": 1'))
    code, out, err = _cli(*_assemble_k1(cache, "--fetch", "--output", tmp_path / "truncated"))
    assert code == EXIT_USAGE
    assert "truncated or incompletely paginated" in err and "Nothing was stored" in err
    assert not cache.exists()


def test_fungmod_assemble_fetch_kinetics_needs_a_repertoire_and_fetch_options_stay_scoped(tmp_path: Path) -> None:
    base = ("assemble", "--fungus", "Strain X", "--substrate", "cellobiose", "--temperature-c", "30", "--ph", "5")
    tail = ("--registry", str(REGISTRY_INDEX), "--cache-dir", str(tmp_path / "kinetics"), "--dataset-id", "x_draft")

    code, out, err = _cli(*base, "--fetch-kinetics", "--fetch", *tail, "--output", tmp_path / "none")
    assert code == EXIT_USAGE
    assert "No enzyme class has evidence for 'Strain X'" in err
    assert "fetch_kinetics looks kinetics up by the EC numbers" in err

    code, out, err = _cli(*base, "--enzyme-class", "beta_glucosidase", "--fetch", *tail, "--output", tmp_path / "a")
    assert code == EXIT_USAGE
    assert "--fetch applies to the UniProt proteome of --proteome or --fetch-proteome and to the kinetics" in err

    code, out, err = _cli(
        *base,
        "--enzyme-class",
        "beta_glucosidase",
        "--fetch-kinetics",
        "--snapshot-dir",
        tmp_path / "s",
        *tail,
        "--output",
        tmp_path / "b",
    )
    assert code == EXIT_USAGE
    assert "--snapshot-dir applies to the UniProt proteome" in err and "kinetics snapshots are under --cache-dir" in err
    assert not (tmp_path / "kinetics").exists()

    code, assemble_help, _ = _cli("assemble", "--help")
    assert code == EXIT_OK
    flat = "".join(assemble_help.split())
    assert "--fetch-kinetics" in assemble_help
    for text in (FETCH_KINETICS_HELP, FETCH_HELP):
        assert "".join(text.split()) in flat
    assert DEFAULT_KINETICS_CACHE_DIR in flat
    assert "kineticslookedupbyECnumber(--fetch-kinetics):" in flat
