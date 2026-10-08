"""``docs/real-example.md`` cannot drift: every command it shows is rerun and every output line and table checked.

The page runs the two registry cases whose numbers come from published sources
(*T. harzianum* P49P11 on cellulose, Gelain 2020; *P. chrysosporium* BGL1A on
cellobiose, SABIO-RK entry 38522) from the stored records alone. This module
reads the page's marked blocks (``<!-- real-example-<kind>: <key> -->`` before a
fenced block or a table, parsed by the walkthrough test's helpers), reruns each
marked command exactly as shown in a temporary directory, runs the page's
Python snippet there (only the path of the stored observations becomes
absolute), and checks that every line of each marked output occurs in the real
output, in order (``...`` stands for omitted text). Each table on the page is
checked against the run's own tables, the registry records and the archived
SABIO-RK export, and the survey of stored cases against the registry and the
preflight of every fungus in both modes. Nothing reaches the network.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import re
import shlex
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from fungal_model.cli import main
from fungal_model.registry import load_registry
from tests.test_walkthrough_doc import assert_lines_shown, marked_blocks, offline

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "real-example.md"
BLOCKS = marked_blocks(DOC, "real-example")
REGISTRY = load_registry(ROOT / "data_registry" / "registry_index.yml")
OBSERVATIONS = "data/benchmarks/gelain_2020_v2/observations.json"
RAW_EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)
TH_RUN = Path("outputs") / "t_harzianum"
BGL_RUN = Path("outputs") / "bgl1a"
# One stored case per registry fungus, to check what the survey says about the modes it runs in.
SURVEY_CASES = {
    "trichoderma_harzianum_p49p11": ("cellulose_celufloc_200", "gelain_2020_cellulose_batch_10gl"),
    "phanerochaete_chrysosporium_k3": ("cellobiose", "tsukada_2008_bgl1a_assay_30c_ph5"),
    "sabiork_beta_glucosidase_source": ("cellobiose", "sabiork_reaction_618_selected_conditions"),
    "toy_fungus_alpha": ("toy_cellulose_like_solid", "toy_lab_environment"),
    "generic_cellulase_source": ("cellulose_film_generic", "bio001_cellulose_surface_pilot_environment"),
}
# What the survey's "Runs in" column says, as preflight exit codes (exploratory, scientific): 0 runnable, 3 blocked.
RUNS_IN = {"scientific mode": (0, 0), "exploratory mode only": (0, 3), "neither mode": (3, 3)}


@dataclass(frozen=True)
class _Result:
    code: int
    out: str
    err: str


def _argv(key: str) -> list[str]:
    words = shlex.split(BLOCKS[("command", key)].replace("\\\n", " "))
    assert words[0] == "fungmod", f"command {key} must start with fungmod"
    return words[1:]


def _cli(directory: Path, argv: list[str]) -> _Result:
    out, err = io.StringIO(), io.StringIO()
    with offline(), contextlib.chdir(directory), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return _Result(code, out.getvalue(), err.getvalue())


def _snippet(directory: Path) -> _Result:
    """The page's Python snippet as shown, run where the commands ran; the observations path becomes absolute."""

    code = BLOCKS[("code", "th-compare")]
    assert code.count(OBSERVATIONS) == 1
    code = code.replace(OBSERVATIONS, (ROOT / OBSERVATIONS).as_posix())
    out = io.StringIO()
    with offline(), contextlib.chdir(directory), contextlib.redirect_stdout(out):
        exec(compile(code, "docs/real-example.md th-compare", "exec"), {"__name__": "__main__"})
    return _Result(0, out.getvalue(), "")


def _table(key: str) -> list[dict[str, str]]:
    lines = BLOCKS[("table", key)].splitlines()
    header = [cell.strip() for cell in lines[0].strip().strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == len(header), line
        rows.append(dict(zip(header, cells, strict=True)))
    return rows


def _code(cell: str) -> str:
    return cell.strip("`")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _number(value: float) -> str:
    """How the page prints a record's value: four significant digits, as the command line prints metrics."""

    return format(value, ".4g")


@dataclass(frozen=True)
class _Page:
    directory: Path
    results: dict[str, _Result]


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> _Page:
    directory = tmp_path_factory.mktemp("rx")
    results = {key: _cli(directory, _argv(key)) for key in ("list", "th-run", "bgl-run", "bgl-preflight")}
    results["th-compare"] = _snippet(directory)
    return _Page(directory=directory, results=results)


# ---------------------------------------------------------------------------
# The commands and outputs shown


@pytest.mark.parametrize(
    ("key", "code"),
    [("list", 0), ("th-run", 0), ("th-compare", 0), ("bgl-run", 0), ("bgl-preflight", 3)],
)
def test_each_command_shown_prints_the_output_shown(page: _Page, key: str, code: int) -> None:
    result = page.results[key]
    assert result.code == code, result.out + result.err
    assert_lines_shown(BLOCKS[("output", key)], result.out, f"docs/real-example.md output {key!r}")


def test_the_commands_use_stored_records_only_and_the_modes_the_page_names() -> None:
    th, bgl = _argv("th-run"), _argv("bgl-run")
    assert th[th.index("--mode") + 1] == "scientific" and "--samples" not in th
    assert bgl[bgl.index("--mode") + 1] == "exploratory"
    assert [word for word in th if word.startswith("gelain_2020_cellulose_batch_")] == [
        f"gelain_2020_cellulose_batch_{loading}gl" for loading in (10, 20, 30)
    ]
    assert [word for word in bgl if word.startswith("tsukada_")] == [
        f"tsukada_2008_bgl1a_assay_30c_ph{ph}" for ph in (4, 5, 6, 7, 8)
    ]
    # Registry cases only: no user dataset, no assembly, no network opt-in anywhere on the page.
    for key in ("list", "th-run", "bgl-run", "bgl-preflight"):
        assert not {"--user-data", "--fetch", "--fetch-kinetics", "--fetch-proteome"} & set(_argv(key))
    text = DOC.read_text(encoding="utf-8")
    assert "Stored literature data, not validated predictions" in text
    assert "`tests/test_real_example_doc.py` reruns the commands" in text


# ---------------------------------------------------------------------------
# The survey of stored cases


def test_the_survey_lists_every_registry_fungus() -> None:
    shown = [_code(row["Registry fungus"]) for row in _table("survey")]
    assert sorted(shown) == sorted(REGISTRY.fungi) == sorted(SURVEY_CASES)


@pytest.mark.parametrize("fungus", list(SURVEY_CASES), ids=["th", "pc", "rice", "toy", "generic"])
def test_the_survey_says_which_modes_each_fungus_runs_in(page: _Page, fungus: str) -> None:
    (row,) = [row for row in _table("survey") if _code(row["Registry fungus"]) == fungus]
    (phrase,) = [phrase for phrase in RUNS_IN if row["Runs in"].startswith(phrase)]
    substrate, environment = SURVEY_CASES[fungus]
    codes = tuple(
        _cli(
            page.directory,
            ["preflight", "--fungus", fungus, "--substrate", substrate, "--environment", environment, "--mode", mode],
        ).code
        for mode in ("exploratory", "scientific")
    )
    assert codes == RUNS_IN[phrase], (fungus, row["Runs in"])


# ---------------------------------------------------------------------------
# Case 1: T. harzianum P49P11 on cellulose


def test_the_stored_observations_are_what_the_page_says(page: _Page) -> None:
    entries = {entry["condition_id"]: entry for entry in json.loads((ROOT / OBSERVATIONS).read_text(encoding="utf-8"))}
    cellulose = [entries[f"gelain_2020_cellulose_{loading}gl"] for loading in (10, 20, 30)]
    observed = 0
    for entry in cellulose:
        assert entry["times_h"] == [8, 12, 24, 32, 48, 54, 72, 96]
        assert entry["raw_replicates_available"] is False
        assert entry["maturity"] == "literature_processed"
        assert set(entry["observations"]) == {"biomass", "substrate", "cellulase_activity", "beta_glucosidase_activity"}
        for series in entry["observations"].values():
            assert series["uncertainty"] is None
            assert len(series["source_cells"]) == len(series["values"]) == len(entry["times_h"])
            assert series["source_file"] and series["source_sheet"]
            observed += len(series["values"])
    assert observed == 96
    # The simulated grid the snippet reads: hourly from 0 to 96 h.
    rows = _rows(page.directory / TH_RUN / "time_series_long.csv")
    times = {float(row["time"]) for row in rows if row["case_id"] == "case_0000"}
    assert times == {float(hour) for hour in range(97)}


def test_the_three_cultures_differ_only_in_their_loading(page: _Page) -> None:
    records: dict[str, dict[str, str]] = defaultdict(dict)
    for row in _rows(page.directory / TH_RUN / "provenance_table.csv"):
        if row["record_type"] == "parameter":
            records[row["case_id"]][row["role"]] = row["record_id"]
    assert sorted(records) == ["case_0000", "case_0001", "case_0002"]
    assert all(len(roles) == 13 for roles in records.values())
    for case, loading in (("case_0001", "20gl"), ("case_0002", "30gl")):
        differing = {role for role, record in records[case].items() if records["case_0000"][role] != record}
        assert differing == {"initial_substrate"}
        assert records[case]["initial_substrate"] == f"gelain_2020_cellulose_initial_loading_{loading}"


def test_the_constants_table_is_the_registry_records_the_run_used(page: _Page) -> None:
    used = {
        (row["role"], row["record_id"], row["maturity"])
        for row in _rows(page.directory / TH_RUN / "provenance_table.csv")
        if row["case_id"] == "case_0000" and row["record_type"] == "parameter"
    }
    rows = _table("th-constants")
    assert len(rows) == 9
    for row in rows:
        record = REGISTRY.parameters[_code(row["Record"])]
        provenance = record.provenance
        posterior = provenance["bayesian_identifiability"]
        assert (_code(row["Role"]), record.record_id, "calibrated") in used
        assert record.value.kind == "exact"
        assert row["Value"] == _number(record.value.value)
        assert row["Units"] == record.value.units == posterior["units"]
        assert _code(row["Posterior class"]) == posterior["class"]
        lower, upper = posterior["credible_interval"]
        assert posterior["credible_mass"] == 0.95
        assert row["95 % credible interval"] == f"{lower:.3g} to {upper:.3g}"
        assert row["Inside"] == ("yes" if posterior["point_value_inside_credible_interval"] else "no")
        assert provenance["confidence_level"] == "calibrated_retrospective_unvalidated"
        assert provenance["fit_model"] == "hydrolysis" and provenance["fit_scenario"] == "primary"
        assert (
            provenance["fit_artifact"]
            == "data/benchmarks/gelain_2020_v2/results/full_fits/cellulose_hydrolysis_primary.json"
        )
        assert (
            provenance["fit_artifact_sha256"]
            == hashlib.sha256((ROOT / provenance["fit_artifact"]).read_bytes()).hexdigest()
        )
        assert provenance["fit_diagnostics"]["practical_rank"] == provenance["fit_diagnostics"]["parameter_count"] == 9
        assert provenance["fit_diagnostics"]["near_bounds"] == ["K_ind", "kF", "kB"]
        assert posterior["artifact"] == "data/benchmarks/gelain_2020_bayesian/results/bayesian_calibration.json"
        assert len(provenance["training_conditions"]) == 3
        assert "gelain_2020_joint_culture_v2" in provenance["source"]
    classes = [_code(row["Posterior class"]) for row in rows]
    assert classes.count("identified") == 5 and classes.count("bounded_below_only") == 1
    assert classes.count("bounded_above_only") == 3


def test_the_initial_state_table_is_the_workbook_records(page: _Page) -> None:
    used = {
        (row["role"], row["record_id"], row["maturity"])
        for row in _rows(page.directory / TH_RUN / "provenance_table.csv")
        if row["record_type"] == "parameter"
    }
    rows = _table("th-initial")
    assert len(rows) == 6
    for row in rows:
        record = REGISTRY.parameters[_code(row["Record"])]
        assert (_code(row["Role"]), record.record_id, "literature_processed") in used
        assert record.value.kind == "exact" and record.provenance["confidence_level"] == "literature_curated"
        assert row["Value"] == _number(record.value.value)
        assert row["Units"] == record.value.units
        assert "doi:10.17632/shd3wcczsr.2" in record.value.source
        assert f"t = 0 row (cell {row['Workbook cell']})" in record.value.source


def test_the_maturity_labels_shown_are_the_runs(page: _Page) -> None:
    # The table's rows say which records carry each label; the run's provenance table is checked for exactly that.
    assert [_code(row["Label"]) for row in _table("th-maturity")] == [
        "calibrated",
        "literature_processed",
        "literature_metadata",
        "scientific_exact_unvalidated",
    ]
    labels = defaultdict(set)
    for row in _rows(page.directory / TH_RUN / "provenance_table.csv"):
        labels[row["maturity"]].add((row["record_type"], row["record_id"]))
    kinds = {maturity: sorted({kind for kind, _ in records}) for maturity, records in labels.items()}
    assert kinds == {
        "calibrated": ["case_template", "parameter", "process_compatibility"],
        "literature_processed": ["environment", "parameter"],
        "literature_metadata": ["fungus", "substrate"],
    }
    assert sum(kind == "parameter" for kind, _ in labels["calibrated"]) == 9
    assert sum(kind == "parameter" for kind, _ in labels["literature_processed"]) == 6
    assert sum(kind == "environment" for kind, _ in labels["literature_processed"]) == 3
    assert "Run label: scientific_exact_unvalidated" in page.results["th-run"].out


def test_the_holdout_errors_quoted_are_the_recorded_ones() -> None:
    # The page quotes the hydrolysis candidate's row of the joint comparison's recorded result.
    benchmark = " ".join((ROOT / "docs" / "gelain-joint-benchmark.md").read_text(encoding="utf-8").split())
    assert "| Cellulose / hydrolysis | 2.493 | 2.465 | 346.9 | 726.7 |" in benchmark
    assert "Both hydrolysis candidates fail the primary observable-worsening screen." in benchmark
    text = " ".join(DOC.read_text(encoding="utf-8").split())
    assert "2.493 g/L (biomass), 2.465 g/L (cellulose), 346.9 FPU/L and 726.7 pNPG U/L" in text


def test_the_culture_limitations_shown_are_the_runs(page: _Page) -> None:
    rows = _rows(page.directory / TH_RUN / "limitations_table.csv")
    for case in ("case_0000", "case_0001", "case_0002"):
        severities = [row["severity"] for row in rows if row["case_id"] == case]
        assert (len(severities), severities.count("important"), severities.count("info")) == (13, 3, 10)
    important = [
        (row["category"], row["limitation"])
        for row in rows
        if row["case_id"] == "case_0000" and row["severity"] == "important"
    ]
    assert [(_code(row["Category"]), row["Limitation"]) for row in _table("th-limits")] == important


def test_the_culture_suggestions_shown_are_the_runs(page: _Page) -> None:
    rows = _rows(page.directory / TH_RUN / "suggested_experiments.csv")
    by_case = defaultdict(list)
    for row in rows:
        by_case[row["case_id"]].append(
            (row["suggestion_id"], row["priority"], row["suggested_experiment"], row["rationale"])
        )
    assert sorted(by_case) == ["case_0000", "case_0001", "case_0002"]
    assert by_case["case_0000"] == by_case["case_0001"] == by_case["case_0002"]
    shown = [
        (_code(row["Suggestion"]), row["Priority"], row["Experiment"], row["Why"]) for row in _table("th-suggestions")
    ]
    assert shown == by_case["case_0000"]


# ---------------------------------------------------------------------------
# Case 2: P. chrysosporium BGL1A on cellobiose, pH 4 to 8


def test_the_ph_table_is_the_runs_summary(page: _Page) -> None:
    run = page.directory / BGL_RUN
    metrics = {(row["environment_id"], row["metric"]): row for row in _rows(run / "summary_metrics.csv")}
    thresholds = defaultdict(set)
    for row in _rows(run / "threshold_times.csv"):
        thresholds[(row["environment_id"], row["threshold_fraction"])].add(row["status"])
    rows = _table("bgl-ph")
    assert [row["pH (buffer)"].split(" ")[0] for row in rows] == ["4", "5", "6", "7", "8"]
    for row in rows:
        ph, buffer = row["pH (buffer)"].split(" ", 1)
        environment = f"tsukada_2008_bgl1a_assay_30c_ph{ph}"
        assert REGISTRY.get_environment(environment).name.endswith(f"(50 mM {buffer.strip('()')})")
        for column, metric in (
            ("Cellobiose degraded after 4 h", "final_substrate_degraded_fraction"),
            ("Glucose formed (mM)", "final_product_formed"),
            ("Maximum depletion rate (mM/s)", "maximum_substrate_depletion_rate"),
        ):
            summary = metrics[(environment, metric)]
            assert summary["p05"] == summary["p50"] == summary["p95"], "the page says all samples agree"
            assert row[column] == _number(float(summary["p50"])), (environment, metric)
        assert metrics[(environment, "final_product_formed")]["units"] == "millimolar"
        assert metrics[(environment, "maximum_substrate_depletion_rate")]["units"] == "millimolar / second"
        for column, fraction in (
            ("10 % degraded (s)", "0.1"),
            ("50 % degraded (s)", "0.5"),
            ("90 % degraded (s)", "0.9"),
        ):
            key = (environment, f"time_to_{int(float(fraction) * 100)}_percent_substrate_degradation")
            if row[column] == "not reached":
                assert thresholds[(environment, fraction)] == {"not_reached"} and key not in metrics
            else:
                assert thresholds[(environment, fraction)] == {"computed"}
                assert metrics[key]["units"] == "second"
                assert row[column] == _number(float(metrics[key]["p50"]))
    # The 4 h grid the page names.
    times = {float(row["time"]) for row in _rows(run / "time_series_long.csv") if row["case_id"] == "case_0000"}
    assert len(times) == 145 and min(times) == 0.0 and max(times) == 14400.0


def test_the_bgl1a_records_table_is_the_registry_and_the_archived_export(page: _Page) -> None:
    raw_bytes = RAW_EXPORT.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    assert f"`{digest}`" in DOC.read_text(encoding="utf-8")
    entry = next(item for item in json.loads(raw_bytes)["data"] if item["id"] == 38522)
    raw = {item["name"]: item for item in entry["kineticlaw"]["parameter"]}
    assert raw["S"]["start_value"] is None and raw["E"]["start_value"] is None, "the entry records no loadings"
    used = {
        (row["role"], row["record_id"], row["maturity"], row["allowed_use"])
        for row in _rows(page.directory / BGL_RUN / "provenance_table.csv")
        if row["case_id"] == "case_0001" and row["record_type"] == "parameter"
    }
    rows = _table("bgl-records")
    assert len(rows) == len(used) == 10
    for row in rows:
        record = REGISTRY.parameters[_code(row["Record"])]
        maturity = _code(row["Maturity"])
        allowed = (
            "exploratory_simulation_only_not_literature_curated"
            if maturity == "exploratory_prior"
            else "scientific_or_exploratory_when_all_other_inputs_are_valid"
        )
        assert (_code(row["Role"]), record.record_id, maturity, allowed) in used
        assert record.maturity == maturity and record.value.kind == "exact"
        assert row["Value"] == _number(record.value.value)
        assert row["Units"] == record.value.units
        parameter = row["SABIO-RK parameter"]
        if parameter == "none":
            assert maturity == "exploratory_prior" and row["Deposited SD"] == "none"
            assert record.value.source == "user-supplied exploratory assumption"
            continue
        assert record.provenance["raw_export_sha256"] == digest
        assert record.provenance["selected_kinlaw_entry_id"] == "38522"
        match = re.fullmatch(r"`(\w+)`(?: \((start|end)\))?", parameter)
        assert match is not None, parameter
        deposited = raw[match[1]]
        assert record.value.value == deposited["end_value" if match[2] == "end" else "start_value"]
        deviation = deposited["standard_deviation"]
        assert row["Deposited SD"] == ("none" if deviation is None else str(deviation))


def test_the_bgl1a_limitations_shown_are_the_runs(page: _Page) -> None:
    rows = _rows(page.directory / BGL_RUN / "limitations_table.csv")
    for case in (f"case_000{index}" for index in range(5)):
        severities = [row["severity"] for row in rows if row["case_id"] == case]
        assert (len(severities), severities.count("important"), severities.count("info")) == (14, 5, 9)
    important = [
        (row["category"], row["limitation"])
        for row in rows
        if row["environment_id"] == "tsukada_2008_bgl1a_assay_30c_ph5" and row["severity"] == "important"
    ]
    assert [(_code(row["Category"]), row["Limitation"]) for row in _table("bgl-limits")] == important
    assert _rows(page.directory / BGL_RUN / "suggested_experiments.csv") == []


# ---------------------------------------------------------------------------
# The page is wired in


def test_the_page_is_in_the_nav_after_the_walkthrough_and_linked() -> None:
    nav = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]
    pages = [next(iter(item.values())) for item in nav]
    assert pages[pages.index("walkthrough.md") + 1] == "real-example.md"
    assert "(docs/real-example.md)" in (ROOT / "README.md").read_text(encoding="utf-8")
    for name in ("index.md", "walkthrough.md"):
        assert "(real-example.md)" in (ROOT / "docs" / name).read_text(encoding="utf-8"), name
