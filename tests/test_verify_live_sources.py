"""``scripts/verify_live_sources.py``: the owner's one-off check of the live UniProt and SABIO-RK lookups.

The script sends one request to each of UniProt's proteome search, UniProtKB's
export and SABIO-RK's kinetic-law export through FungMod's own query builders,
parsers and snapshot checks, and reports per endpoint whether the response is
what FungMod expects. These tests run it fully offline: ``urllib.request.urlopen``
is patched to serve SYNTHETIC TEST RESPONSES (the hand-written fixtures of
``tests/fixtures/uniprot_proteome_search/`` and
``tests/fixtures/sabiork_kinetics_queries/``, not UniProt or SABIO-RK data),
and socket connections are patched to fail. They cover the passing path, the
mismatches the script must report (exit code 1), endpoints it cannot check
(exit code 3), usage errors (exit code 2), and that it writes nothing inside the
repository.
"""

from __future__ import annotations

import contextlib
import email.message
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from fungal_model.sources.sabiork import fetch as sabiork_fetch
from fungal_model.sources.sabiork.fetch import BASE_URL, DEFAULT_PAGE_SIZE, ENDPOINT, build_kinlaw_url
from fungal_model.sources.sabiork.query_snapshots import ec_number_query, kinlaw_query_directory
from fungal_model.sources.uniprot import (
    build_proteome_search_url,
    build_stream_url,
    proteome_name_query,
    proteome_query,
    search_key,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_live_sources.py"
UNIPROT = ROOT / "tests" / "fixtures" / "uniprot_proteome_search"
SABIO = ROOT / "tests" / "fixtures" / "sabiork_kinetics_queries"

NAME = "Synthetic fixture mould B2"
SEARCH_BODY = (UNIPROT / "search_fixture_mould_b2.tsv").read_bytes()
EXPORT_BODY = (UNIPROT / "proteome_UP999990002_uniprotkb.tsv").read_bytes()
AMBIGUOUS_NAME = "Synthetic fixture mould"
AMBIGUOUS_BODY = (UNIPROT / "search_fixture_mould.tsv").read_bytes()
SABIO_BODY = (SABIO / "ecnumber_3_2_1_21_cellobiose.json").read_bytes()
NO_ENTRIES_BODY = (SABIO / "no_entries.json").read_bytes()
QUERY = ec_number_query("3.2.1.21", substrate="Cellobiose")
RELEASE = {"X-UniProt-Release": "fixture_release", "X-UniProt-Release-Date": "06-October-2026"}
ARGS = ("--organism", NAME, "--ec-number", "3.2.1.21", "--substrate", "Cellobiose")
# Files the script or FungMod's snapshot functions write; none may appear inside the repository.
ARTIFACT_NAMES = {
    "verification_report.json",
    "proteomes.tsv",
    "uniprotkb.tsv",
    "snapshot.json",
    "fetch_metadata.json",
    "combined_export.json",
    "page_0001.json",
}
IGNORED_DIRECTORIES = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "site", ".hypothesis"}


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("verify_live_sources tests must not reach the network; serve a synthetic response instead.")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(sabiork_fetch, "urlopen", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    yield


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


class _FakeServices:
    """Serve synthetic UniProt and SABIO-RK responses by exact URL and record every URL requested."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[bytes | BaseException, int, Mapping[str, str]]] = {}
        self.requested: list[str] = []

    def serve(
        self, url: str, body: bytes | BaseException, *, status: int = 200, headers: Mapping[str, str] | None = None
    ) -> str:
        self.routes[url] = (body, status, {} if headers is None else headers)
        return url

    def __call__(self, request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        assert timeout > 0
        url = request.full_url
        self.requested.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected request {url}")
        body, status, headers = self.routes[url]
        if isinstance(body, BaseException):
            raise body
        return _FakeResponse(body, status=status, headers=headers)


def _search_url(name: str = NAME) -> str:
    return build_proteome_search_url(proteome_name_query(name))


def _export_url(proteome_id: str = "UP999990002") -> str:
    return build_stream_url(proteome_query(proteome_id))


def _sabio_url(query: str = QUERY) -> str:
    return build_kinlaw_url(base_url=BASE_URL, endpoint=ENDPOINT, query=query, page=1, page_size=DEFAULT_PAGE_SIZE)


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> _FakeServices:
    fake = _FakeServices()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


def _serve_all(services: _FakeServices) -> None:
    services.serve(_search_url(), SEARCH_BODY, headers={**RELEASE, "X-Total-Results": "1"})
    services.serve(_export_url(), EXPORT_BODY, headers=RELEASE)
    services.serve(_sabio_url(), SABIO_BODY, headers={"Content-Type": "application/json"})


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_live_sources", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(*args: str | Path) -> tuple[int, str, str]:
    script = _load_script()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = script.main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def _report(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "verification_report.json").read_text(encoding="utf-8"))


def _outcomes(directory: Path) -> list[str]:
    return [endpoint["outcome"] for endpoint in _report(directory)["endpoints"]]


def _repository_files() -> set[str]:
    files: set[str] = set()
    for directory, subdirectories, names in os.walk(ROOT):
        subdirectories[:] = [name for name in subdirectories if name not in IGNORED_DIRECTORIES]
        for name in names:
            files.add(Path(directory, name).relative_to(ROOT).as_posix())
    return files


def _new_artifacts(before: set[str]) -> list[str]:
    return sorted(path for path in _repository_files() - before if Path(path).name in ARTIFACT_NAMES)


# ---------------------------------------------------------------------------
# The passing path


def test_matching_responses_pass_every_check_and_nothing_is_written_inside_the_repository(
    services: _FakeServices, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _serve_all(services)
    output = tmp_path / "live_check"
    before = _repository_files()
    monkeypatch.chdir(ROOT)  # relative defaults would land in the repository; there must be none

    code, out, err = _run(*ARGS, "--output-dir", output)

    assert code == 0, out + err
    assert _new_artifacts(before) == []
    # One request per endpoint, built by FungMod's own query builders.
    assert services.requested == [_search_url(), _export_url(), _sabio_url()]
    assert _outcomes(output) == ["OK", "OK", "OK"]
    report = _report(output)
    assert report["exit_code"] == 0 and report["summary"] == {"ok": 3, "mismatch": 0, "not_checked": 0}
    # The snapshots are FungMod's, stored only under the output directory, byte for byte as served.
    assert (output / "uniprot" / search_key(NAME) / "proteomes.tsv").read_bytes() == SEARCH_BODY
    assert (output / "uniprot" / "proteome_UP999990002" / "uniprotkb.tsv").read_bytes() == EXPORT_BODY
    (bundle,) = list(kinlaw_query_directory(QUERY, cache_dir=output / "sabiork").iterdir())
    assert (bundle / "raw" / "page_0001.json").read_bytes() == SABIO_BODY

    assert "[1/3] UniProt proteome search (FETCH-001: a fungus name to its reference proteome)" in out
    assert f"  URL: {_search_url()}" in out
    assert "  ok    HTTP status: 200" in out
    assert "  ok    X-UniProt-Release: fixture_release" in out
    assert "  ok    X-Total-Results: 1, equal to the 1 row(s) of the response" in out
    assert "  info  columns found: Proteome Id, Organism, Organism Id, Protein count" in out
    assert "  ok    parse_proteome_search_tsv: read 1 candidate(s)" in out
    assert (
        "  ok    choose_proteome: UP999990002 (Synthetic fixture mould B2 (strain FIX-2); taxonomy 9000000002; "
        "reference proteome (proteome_type:1); 5 proteins), because it is the only candidate of the search"
    ) in out
    assert "[2/3] UniProtKB export of proteome UP999990002 (FETCH-001: the enzyme repertoire)" in out
    assert (
        "  info  columns found: Entry, Entry Name, Protein names, Gene Names, Organism, Organism (ID), EC number, "
        "CAZy, Reviewed"
    ) in out
    assert "  ok    parse_uniprot_tsv: read 5 entries" in out
    assert "  ok    protein count: 5, equal to the export's entries" in out
    assert "[3/3] SABIO-RK kinetic-law export, queried by EC number and substrate name (FETCH-002)" in out
    assert f"  query: {QUERY}" in out
    assert "  ok    envelope: meta, data and meta.total_count are present" in out
    assert "  ok    EC numbers: every entry states EC 3.2.1.21" in out
    assert "  ok    substrate name: every entry names 'Cellobiose' as a substrate (case-insensitive)" in out
    assert "  ok    user_tables_from_sabiork: 3 of 7 entries converted to kinetics rows" in out
    assert "Summary: 3 endpoint(s): 3 OK, 0 MISMATCH, 0 NOT CHECKED; exit code 0." in out
    assert "probe organism: 'Synthetic fixture mould B2' (a probe of UniProt's formats only" in out


def test_without_an_output_directory_a_new_temporary_directory_outside_the_repository_is_used(
    services: _FakeServices, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _serve_all(services)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.chdir(ROOT)
    before = _repository_files()

    code, out, err = _run(*ARGS)

    assert code == 0, out + err
    assert _new_artifacts(before) == []
    (created,) = list(tmp_path.iterdir())
    assert created.name.startswith("fungmod-live-sources-")
    assert (
        f"  output directory: {created.resolve()} (snapshots and verification_report.json; outside the repository)"
        in out
    )
    assert _outcomes(created) == ["OK", "OK", "OK"]


def test_the_default_probes_are_a_known_fungus_and_beta_glucosidase_on_cellobiose() -> None:
    script = _load_script()
    arguments = script.parse_args([])
    assert (arguments.organism, arguments.ec_number, arguments.substrate) == (
        "Trichoderma reesei",
        "3.2.1.21",
        "Cellobiose",
    )
    assert arguments.output_dir is None and arguments.proteome is None


# ---------------------------------------------------------------------------
# Mismatches: exit code 1


def test_a_renamed_search_column_is_a_mismatch_and_the_export_is_not_requested(
    services: _FakeServices, tmp_path: Path
) -> None:
    _serve_all(services)
    services.serve(
        _search_url(), SEARCH_BODY.replace(b"Organism Id", b"Taxon Id"), headers={**RELEASE, "X-Total-Results": "1"}
    )
    output = tmp_path / "out"

    code, out, _err = _run(*ARGS, "--output-dir", output)

    assert code == 1
    assert _outcomes(output) == ["MISMATCH", "NOT CHECKED", "OK"]
    assert "  MISMATCH  columns: missing ['Organism Id']" in out
    assert "  MISMATCH  parse_proteome_search_tsv: refused:" in out
    assert _export_url() not in services.requested
    # FungMod stores nothing it cannot read.
    assert not (output / "uniprot" / search_key(NAME)).exists()
    assert "Summary: 3 endpoint(s): 1 OK, 1 MISMATCH, 1 NOT CHECKED; exit code 1." in out


def test_a_missing_total_results_header_is_a_mismatch_but_the_export_is_still_checked(
    services: _FakeServices, tmp_path: Path
) -> None:
    _serve_all(services)
    services.serve(_search_url(), SEARCH_BODY, headers=RELEASE)
    output = tmp_path / "out"

    code, out, _err = _run(*ARGS, "--output-dir", output)

    assert code == 1
    assert _outcomes(output) == ["MISMATCH", "OK", "OK"]
    assert "  MISMATCH  X-Total-Results: not sent; FungMod reads it to refuse a search" in out


def test_an_export_without_a_requested_column_is_a_mismatch(services: _FakeServices, tmp_path: Path) -> None:
    _serve_all(services)
    without_reviewed = b"\n".join(line.rsplit(b"\t", 1)[0] for line in EXPORT_BODY.split(b"\n") if line) + b"\n"
    services.serve(_export_url(), without_reviewed, headers=RELEASE)
    output = tmp_path / "out"

    code, out, _err = _run(*ARGS, "--output-dir", output)

    assert code == 1
    assert _outcomes(output) == ["OK", "MISMATCH", "OK"]
    assert "  MISMATCH  columns: missing ['Reviewed']" in out
    # FungMod's parser itself accepts the export; the script reports what FungMod asked for and did not get.
    assert "  ok        parse_uniprot_tsv: read 5 entries" in out


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            SABIO_BODY.replace(b'"total_count": 7,', b"", 1),
            "  MISMATCH  envelope: missing ['meta.total_count']: FungMod refuses an answer without them",
        ),
        (
            SABIO_BODY.replace(b'"ec_number": "3.2.1.21"', b'"ec_number": "3.2.1.4"', 1),
            "  MISMATCH  EC numbers: 1 of 7 entries do not state EC 3.2.1.21 (3.2.1.4: 1)",
        ),
        (
            SABIO_BODY.replace(b'"total_count": 7,', b'"total_count": 9,', 1),
            "  MISMATCH  fetch_kinlaw_query_snapshot: refused:",
        ),
        (b"<html>Service moved</html>", "  MISMATCH  envelope: the answer is not UTF-8 JSON"),
        (
            SABIO_BODY.replace(b'"name": "Cellobiose"', b'"name": "beta-D-Cellobiose"'),
            "  MISMATCH  substrate name: no entry names 'Cellobiose' as a substrate",
        ),
    ],
    ids=["no_total_count", "another_ec_number", "truncated", "not_json", "substrate_named_otherwise"],
)
def test_sabiork_answers_fungmod_would_refuse_or_misread_are_mismatches(
    services: _FakeServices, tmp_path: Path, body: bytes, expected: str
) -> None:
    _serve_all(services)
    services.serve(_sabio_url(), body)
    output = tmp_path / "out"

    code, out, _err = _run(*ARGS, "--output-dir", output)

    assert code == 1
    assert _outcomes(output) == ["OK", "OK", "MISMATCH"]
    assert expected in out


@pytest.mark.parametrize(
    ("status", "code", "outcome"), [(400, 1, "MISMATCH"), (404, 1, "MISMATCH"), (503, 3, "NOT CHECKED")]
)
def test_http_errors_are_mismatches_unless_the_server_failed(
    services: _FakeServices, tmp_path: Path, status: int, code: int, outcome: str
) -> None:
    _serve_all(services)
    services.serve(_sabio_url(), urllib.error.HTTPError(_sabio_url(), status, "Error", email.message.Message(), None))
    output = tmp_path / "out"

    exit_code, out, _err = _run(*ARGS, "--output-dir", output)

    assert exit_code == code
    assert _outcomes(output) == ["OK", "OK", outcome]
    assert f"HTTP status: {status} (HTTP {status}: Error)" in out
    assert not (output / "sabiork").exists() or not any((output / "sabiork").rglob("*.json"))


# ---------------------------------------------------------------------------
# Endpoints that cannot be checked: exit code 3


def test_an_unreachable_service_is_not_checked_and_the_other_still_is(services: _FakeServices, tmp_path: Path) -> None:
    _serve_all(services)
    services.serve(_search_url(), urllib.error.URLError("no route to host"))
    output = tmp_path / "out"

    code, out, _err = _run(*ARGS, "--output-dir", output)

    assert code == 3
    assert _outcomes(output) == ["NOT CHECKED", "NOT CHECKED", "OK"]
    assert (
        "result: NOT CHECKED (the service could not be reached (not reached: <urlopen error no route to host>))" in out
    )


def test_an_ambiguous_probe_name_is_not_checked_until_a_proteome_is_named(
    services: _FakeServices, tmp_path: Path
) -> None:
    _serve_all(services)
    services.serve(_search_url(AMBIGUOUS_NAME), AMBIGUOUS_BODY, headers={**RELEASE, "X-Total-Results": "2"})
    arguments = ("--organism", AMBIGUOUS_NAME, "--ec-number", "3.2.1.21", "--substrate", "Cellobiose")

    code, out, _err = _run(*arguments, "--output-dir", tmp_path / "first")
    assert code == 3
    assert _outcomes(tmp_path / "first") == ["NOT CHECKED", "NOT CHECKED", "OK"]
    assert "  info  candidate: UP999990003 (Synthetic fixture mould B3 (strain FIX-3)" in out
    assert "run again with --proteome UP... naming one of them to check the export" in out

    code, out, _err = _run(*arguments, "--proteome", "UP999990002", "--output-dir", tmp_path / "second")
    assert code == 0, out
    assert "because its proteome identifier was given and it is a candidate of the search" in out


def test_a_query_without_entries_is_not_checked(services: _FakeServices, tmp_path: Path) -> None:
    _serve_all(services)
    services.serve(_sabio_url(), NO_ENTRIES_BODY)
    output = tmp_path / "out"

    code, out, _err = _run(*ARGS, "--output-dir", output)

    assert code == 3
    assert _outcomes(output) == ["OK", "OK", "NOT CHECKED"]
    assert "the entry format cannot be checked with this probe" in out


# ---------------------------------------------------------------------------
# Usage errors: exit code 2, nothing sent or written


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--ec-number", "3.2.1"), "is not a complete EC number"),
        (("--substrate", 'Cello"biose'), "does not guess an escaping"),
        (("--organism", 'Genus "species"'), "double quote"),
        (("--proteome", "P12345"), "is not a UniProt proteome identifier"),
        (("--timeout", "0"), "--timeout must be positive"),
    ],
)
def test_unusable_arguments_are_refused_before_any_request(
    services: _FakeServices, tmp_path: Path, arguments: tuple[str, ...], message: str
) -> None:
    code, out, err = _run(*arguments, "--output-dir", tmp_path / "out")

    assert code == 2
    assert message in err
    assert services.requested == []
    assert not (tmp_path / "out").exists()


def test_an_output_directory_inside_the_repository_or_not_empty_is_refused(
    services: _FakeServices, tmp_path: Path
) -> None:
    inside = ROOT / "tests" / "fixtures" / "verify_live_sources_output"
    code, _out, err = _run(*ARGS, "--output-dir", inside)
    assert code == 2
    assert "is inside the repository" in err
    assert not inside.exists()

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("x", encoding="utf-8")
    code, _out, err = _run(*ARGS, "--output-dir", occupied)
    assert code == 2
    assert "must be a new or empty directory" in err
    assert services.requested == []


def test_a_temporary_directory_inside_the_repository_is_refused(
    services: _FakeServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(ROOT / "tests"))
    before = _repository_files()

    code, _out, err = _run(*ARGS)

    assert code == 2
    assert "give --output-dir" in err
    assert _repository_files() - before == set()
    assert services.requested == []
