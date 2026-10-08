"""``docs/walkthrough.md`` cannot drift: every command it shows is rerun and every output line it shows checked.

The walkthrough runs ``fungmod assemble --fetch-proteome --fetch-kinetics
--network`` for a synthetic organism, offline, against the frozen snapshots
of ``tests/fixtures/walkthrough/`` (SYNTHETIC TEST RESPONSES in UniProt's and
SABIO-RK's formats, not their data; see that directory's README), then
reviews the draft, checks it and runs it. This module reads the page's
marked blocks (``<!-- walkthrough-<kind>: <key> -->`` before a fenced block or
a table), reruns each marked command exactly as shown (only the two snapshot
directories become absolute paths, so that the run happens in a temporary
directory), applies the page's edits, and checks that every line of each
marked output occurs in the real output, in order (``...`` stands for omitted
text). It also checks the page's claims about replacing the estimates with
your own values, using test values that are not measurements, and the sample
report of ``scripts/verify_live_sources.py`` (synthetic responses through a
patched ``urlopen``). Nothing reaches the network.
"""

from __future__ import annotations

import contextlib
import csv
import io
import os
import re
import shlex
import shutil
import socket
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from fungal_model.cli import main
from fungal_model.sources.sabiork import fetch as sabiork_fetch
from tests import test_verify_live_sources as live

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "walkthrough.md"
SNAPSHOTS = ROOT / "tests" / "fixtures" / "walkthrough"
SHOWN_SNAPSHOTS = "tests/fixtures/walkthrough"
UNIPROT_FIXTURES = ROOT / "tests" / "fixtures" / "uniprot_proteome_search"
SABIO_FIXTURES = ROOT / "tests" / "fixtures" / "sabiork_kinetics_queries"
# Values for the page's template of your own measurements: TEST VALUES, not measurements of anything.
TEST_VALUES = {
    "<Km>": "3",
    "<kcat>": "20",
    "<how it was measured>": "test value written by tests/test_walkthrough_doc.py",
    "<where it is recorded>": "not a measurement",
    "<sd>": "",
    "<replicates>": "",
    "<why this amount>": "test design",
}


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("the walkthrough runs offline from frozen snapshots; nothing may reach the network.")


@contextlib.contextmanager
def offline() -> Iterator[None]:
    """Fail any attempt to reach the network (also used by ``tests/test_real_example_doc.py``)."""

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(urllib.request, "urlopen", _forbidden)
        patch.setattr(sabiork_fetch, "urlopen", _forbidden)
        patch.setattr(socket.socket, "connect", _forbidden)
        yield


def marked_blocks(doc: Path, prefix: str) -> dict[tuple[str, str], str]:
    """A page's marked blocks: the fenced block or table right after each marker, keyed by (kind, key).

    A marker is ``<!-- <prefix>-<kind>: <key> -->`` on its own line (also used by
    ``tests/test_real_example_doc.py``).
    """

    marker = re.compile(rf"<!-- {re.escape(prefix)}-(?P<kind>[a-z-]+): (?P<key>[a-z0-9-]+) -->")
    lines = doc.read_text(encoding="utf-8").splitlines()
    blocks: dict[tuple[str, str], str] = {}
    index = 0
    while index < len(lines):
        match = marker.fullmatch(lines[index].strip())
        index += 1
        if match is None:
            continue
        key = (match["kind"], match["key"])
        assert key not in blocks, f"{key} is marked twice in {doc.name}"
        if lines[index].startswith("```"):
            end = index + 1
            while not lines[end].startswith("```"):
                end += 1
            blocks[key] = "\n".join(lines[index + 1 : end])
            index = end + 1
        elif lines[index].startswith("|"):
            end = index
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            blocks[key] = "\n".join(lines[index:end])
            index = end
        else:
            raise AssertionError(f"{key} in {doc.name} is not followed by a fenced block or a table")
    return blocks


BLOCKS = marked_blocks(DOC, "walkthrough")


def _argv(key: str) -> list[str]:
    """The marked command as shown, with the snapshot directories as absolute paths of the repository."""

    text = BLOCKS[("command", key)].replace("\\\n", " ")
    words = shlex.split(text)
    assert words[0] == "fungmod", f"command {key} must start with fungmod"
    return [
        str(SNAPSHOTS / word[len(SHOWN_SNAPSHOTS) + 1 :]) if word.startswith(SHOWN_SNAPSHOTS) else word
        for word in words[1:]
    ]


@dataclass(frozen=True)
class _Result:
    code: int
    out: str
    err: str


def _normalized(text: str) -> str:
    for form in (str(SNAPSHOTS), SNAPSHOTS.as_posix()):
        text = text.replace(form, SHOWN_SNAPSHOTS)
    return text


def _slashes(text: str) -> str:
    """Windows prints paths with backslashes and quotes a printed argument with double quotes (``shell_quote``);
    there both sides of a comparison are read with forward slashes and single quotes."""

    return text.replace("\\", "/").replace('"', "'") if os.sep == "\\" else text


def _cli(directory: Path, argv: list[str]) -> _Result:
    out, err = io.StringIO(), io.StringIO()
    with offline(), contextlib.chdir(directory), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return _Result(code, _normalized(out.getvalue()), _normalized(err.getvalue()))


def assert_lines_shown(shown_block: str, actual: str, where: str) -> None:
    """Every nonblank line of ``shown_block`` occurs in ``actual``, in the order shown; ``...`` is any text.

    ``where`` names the block in the failure message (also used by ``tests/test_real_example_doc.py``).
    """

    actual_lines = [line.rstrip() for line in _slashes(actual).splitlines()]
    position = 0
    for line in _slashes(shown_block).splitlines():
        shown = line.rstrip()
        if not shown.strip() or shown.strip() == "...":
            continue
        pattern = re.compile(".*".join(re.escape(part) for part in shown.split("...")))
        for index in range(position, len(actual_lines)):
            if pattern.fullmatch(actual_lines[index]):
                position = index + 1
                break
        else:
            raise AssertionError(
                f"{where} shows a line that the command does not print (or not in this order):\n  {shown}\n"
                f"Actual output:\n{actual}"
            )


def _assert_shown(key: str, actual: str) -> None:
    assert_lines_shown(BLOCKS[("output", key)], actual, f"docs/walkthrough.md output {key!r}")


def _replace_line(path: Path, number: int, text: str) -> None:
    lines = path.read_bytes().decode("utf-8").split("\n")
    lines[number - 1] = text
    path.write_bytes("\n".join(lines).encode("utf-8"))


@dataclass(frozen=True)
class _Walk:
    directory: Path
    results: dict[str, _Result]
    drafted_row_5: str


@pytest.fixture(scope="module")
def walk(tmp_path_factory: pytest.TempPathFactory) -> _Walk:
    directory = tmp_path_factory.mktemp("walkthrough")
    results: dict[str, _Result] = {}
    for key in ("assemble-first", "assemble-entry", "check-unreviewed"):
        results[key] = _cli(directory, _argv(key))
    draft = directory / "mould_b2"
    drafted_row_5 = (draft / "kinetics.csv").read_bytes().decode("utf-8").split("\n")[4]
    # The page's edits, exactly as shown.
    contributor = BLOCKS[("edit", "contributor")]
    manifest = (draft / "user_dataset.yml").read_bytes().decode("utf-8").split("\n")
    (number,) = [index + 1 for index, line in enumerate(manifest) if line.startswith("contributor:")]
    _replace_line(draft / "user_dataset.yml", number, contributor)
    _replace_line(draft / "kinetics.csv", 5, BLOCKS[("edit", "kinetics-row-5")])
    for key in ("check-reviewed", "run", "run-blocked"):
        results[key] = _cli(directory, _argv(key))
    return _Walk(directory=directory, results=results, drafted_row_5=drafted_row_5)


# ---------------------------------------------------------------------------
# The commands and outputs shown


@pytest.mark.parametrize(
    ("key", "code", "stream"),
    [
        ("assemble-first", 0, "out"),
        ("assemble-entry", 0, "out"),
        ("check-unreviewed", 2, "err"),
        ("check-reviewed", 0, "out"),
        ("run", 4, "out"),
        ("run-blocked", 3, "out"),
    ],
)
def test_each_command_shown_prints_the_output_shown(walk: _Walk, key: str, code: int, stream: str) -> None:
    result = walk.results[key]
    assert result.code == code, result.out + result.err
    _assert_shown(key, result.out if stream == "out" else result.err)


def test_the_page_shows_the_draft_row_it_edits_and_the_route_it_describes(walk: _Walk) -> None:
    assert BLOCKS[("file", "kinetics-row-5")] == walk.drafted_row_5
    assert BLOCKS[("edit", "contributor")] == "contributor: Your Name"
    first, entry = _argv("assemble-first"), _argv("assemble-entry")
    for option in ("--fetch-proteome", "--fetch-kinetics", "--network"):
        assert option in first and option in entry
    # The worked example runs offline from the frozen snapshots; the command for a real fungus fetches.
    assert "--fetch" not in first and "--fetch" not in entry
    text = DOC.read_text(encoding="utf-8")
    assert "--fetch-proteome --fetch-kinetics --network --fetch \\" in text
    # The second command is the first with the chosen entry and a new output directory.
    position = first.index("--network") + 1
    expected = [*first[:position], "--entry-id", "9900001", *first[position:]]
    expected[expected.index("mould_b2_first")] = "mould_b2"
    assert entry == expected
    assert "synthetic test fixtures, not biology" in text
    assert "A run for a real fungus needs network\n    access (`--fetch`)" in text
    # The draft records nothing of the machine it was made on.
    for path in (walk.directory / "mould_b2").rglob("*"):
        if path.is_file():
            assert str(walk.directory) not in path.read_text(encoding="utf-8", errors="replace"), path


def test_the_provenance_table_shown_is_the_runs_own(walk: _Walk) -> None:
    rows = [line.strip("|").split("|") for line in BLOCKS[("table", "provenance")].splitlines()[2:]]
    shown = [tuple(cell.strip().strip("`") for cell in row) for row in rows]
    with (walk.directory / "runs" / "mould_b2" / "provenance_table.csv").open(encoding="utf-8", newline="") as handle:
        actual = [
            (row["role"], row["maturity"], row["allowed_use"], row["source"])
            for row in csv.DictReader(handle)
            if row["case_id"] == "case_0000" and row["record_type"] == "parameter"
        ]
    assert shown == actual


def test_the_runs_tables_say_what_the_page_says(walk: _Walk) -> None:
    run = walk.directory / "runs" / "mould_b2"
    with (run / "case_summary.csv").open(encoding="utf-8", newline="") as handle:
        cases = {row["case_id"]: row["case_status"] for row in csv.DictReader(handle)}
    assert cases == {"case_0000": "simulated", "case_0001": "not_simulated"}
    with (run / "time_series_long.csv").open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["sample_id"] == "sample_0000"]
    assert len({row["time_index"] for row in rows}) == 61
    with (run / "suggested_experiments.csv").open(encoding="utf-8", newline="") as handle:
        priorities = [row["priority"] for row in csv.DictReader(handle)]
    assert priorities == ["high", "high", "high"]
    figures = sorted(path.name for path in (run / "figures").iterdir())
    for name in ("substrate_remaining_vs_time.png", "degradation_fraction_vs_time.png", "degradation_rate_vs_time.png"):
        assert name in figures


def test_scientific_mode_runs_no_case_of_the_draft(walk: _Walk) -> None:
    argv = _argv("run")
    argv[argv.index("exploratory")] = "scientific"
    for option in ("--samples", "--seed"):
        position = argv.index(option)
        del argv[position : position + 2]
    argv[argv.index("runs/mould_b2")] = "runs/scientific"

    result = _cli(walk.directory, argv)

    assert result.code == 3, result.out + result.err
    assert "Not runnable: 2 of 2 case(s) cannot be simulated in scientific mode." in result.out


def test_your_own_values_close_the_gap_and_exact_values_run_in_scientific_mode(walk: _Walk) -> None:
    own = walk.directory / "mould_b2_own"
    shutil.copytree(walk.directory / "mould_b2", own)
    rows = BLOCKS[("template", "own-measurements")].splitlines()
    filled = []
    for row in rows:
        for placeholder, value in TEST_VALUES.items():
            row = row.replace(placeholder, value)
        assert "<" not in row and ">" not in row, row
        filled.append(row)
    lines = (own / "kinetics.csv").read_bytes().decode("utf-8").split("\n")
    header = lines[0].split(",")
    assert all(len(next(csv.reader([row]))) == len(header) for row in filled)
    assert lines[1].split(",")[3:5] == ["c30_ph5", "km"] and lines[2].split(",")[3:5] == ["c30_ph5", "kcat"]
    lines[1:3] = filled[:2]
    lines[-1:-1] = filled[2:]
    (own / "kinetics.csv").write_bytes("\n".join(lines).encode("utf-8"))

    checked = _cli(walk.directory, ["check-data", "mould_b2_own"])
    assert checked.code == 0, checked.err
    assert "Kinetic values: 8; gaps: 0" in checked.out

    argv = _argv("run")
    argv[argv.index("mould_b2")] = "mould_b2_own"
    argv.remove("--runnable-only")
    argv[argv.index("runs/mould_b2")] = "runs/own"
    exploratory = _cli(walk.directory, argv)
    assert exploratory.code == 0, exploratory.out + exploratory.err
    assert "Simulated 2 case(s) in exploratory mode" in exploratory.out

    argv[argv.index("exploratory")] = "scientific"
    for option in ("--samples", "--seed"):
        position = argv.index(option)
        del argv[position : position + 2]
    argv[argv.index("runs/own")] = "runs/own_scientific"
    scientific = _cli(walk.directory, argv)
    assert scientific.code == 0, scientific.out + scientific.err
    assert "Simulated 2 case(s) in scientific mode" in scientific.out


# ---------------------------------------------------------------------------
# The frozen snapshots and the verification script's sample report


def test_the_frozen_snapshots_hold_the_synthetic_fixtures_byte_for_byte() -> None:
    search = SNAPSHOTS / "uniprot" / "organism_name_synthetic_fixture_mould_b2_32e605c891b0" / "proteomes.tsv"
    export = SNAPSHOTS / "uniprot" / "proteome_UP999990002" / "uniprotkb.tsv"
    (page,) = (SNAPSHOTS / "sabiork").glob("*/*/raw/page_0001.json")
    assert search.read_bytes() == (UNIPROT_FIXTURES / "search_fixture_mould_b2.tsv").read_bytes()
    assert export.read_bytes() == (UNIPROT_FIXTURES / "proteome_UP999990002_uniprotkb.tsv").read_bytes()
    assert page.read_bytes() == (SABIO_FIXTURES / "ecnumber_3_2_1_21_cellobiose.json").read_bytes()
    assert "Synthetic test responses written by hand" in (SNAPSHOTS / "README.md").read_text(encoding="utf-8")


def test_the_sample_report_of_the_verification_script_is_its_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    services = live._FakeServices()
    monkeypatch.setattr(urllib.request, "urlopen", services)
    monkeypatch.setattr(sabiork_fetch, "urlopen", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    live._serve_all(services)

    code, out, err = live._run(*live.ARGS, "--output-dir", tmp_path / "check")

    assert code == 0, out + err
    _assert_shown("verify-live-sources", out)
    assert "python scripts/verify_live_sources.py" in DOC.read_text(encoding="utf-8")
