"""Machine-readable ``--json`` summaries of ``fungmod run``, ``assemble``, ``check-data`` and ``fit`` (CLI-003).

Each summary must parse, carry the pinned ``schema_version``, agree with the
printed text and the files the command wrote, leave the text and the exit code
unchanged, hold no NaN or infinity, and state a reason for every ``null``.

Inputs are the repository's own fixtures and synthetic fakes only, as in
``tests/test_cli.py``, ``tests/test_cli_user_data_workflow.py``,
``tests/test_fetch_by_name.py``, ``tests/test_fetch_kinetics.py`` and
``tests/test_assemble_network.py``: the Reaction 618 registry case, the
esterase fixture with its synthetic time courses, the hand-written dbCAN format
fixture, the network chain fixture, and synthetic UniProt and kinetic-law
responses served by fakes. Every test runs with the network refused.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import shutil
import socket
import urllib.request
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

import fungal_model
from fungal_model import assemble_user_tables, load_user_dataset
from fungal_model.api import VirtualExperiment, VirtualExperimentError
from fungal_model.api.user_data_assembly import ASSEMBLY_STATUSES
from fungal_model.cli import (
    EXIT_CODE_MEANINGS,
    EXIT_NOT_RUNNABLE,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_SIMULATION_FAILED,
    EXIT_USAGE,
    main,
    shell_quote,
)
from fungal_model.registry import load_registry
from fungal_model.cli_summary import (
    NOT_REACHED,
    NULL_REASONS,
    RESULT_SECTIONS,
    RUN_CASE_STATUSES,
    SUMMARY_KIND,
    SUMMARY_SCHEMA_VERSION,
    SummaryContractError,
    Unknown,
    finalize,
    render,
)
from fungal_model.sources.sabiork import fetch as sabiork_fetch
from tests.test_assemble_network import CHAIN, _without_network_block
from tests.test_cli_user_data_workflow import ESTERASE_STRAIN, ESTERASE_SUBSTRATE, G1_API, G1_ASSEMBLE
from tests.test_fetch_by_name import NAME_B2, NAME_U1, _assemble, _FakeUniprot, _served_b2, _served_u1
from tests.test_fetch_kinetics import BODY_A, QUERY_A, _assemble_k1, _FakeSabio
from tests.test_user_data_assembly import REGISTRY_INDEX
from tests.test_user_data_timecourse import (
    ESTERASE_CASE,
    STARTING_CONDITIONS,
    TIMECOURSE_TABLE,
    _esterase_dataset,
    _simulated_medians,
    _timecourse_from,
)

ROOT = Path(__file__).resolve().parents[1]
ESTERASE = ROOT / "tests" / "fixtures" / "user_data" / "esterase_case"
REACTION_618 = (
    "--fungus",
    "beta-glucosidase source",
    "--substrate",
    "cellobiose",
    "--environment",
    "SABIO-RK Reaction 618 selected assay conditions",
)
# Reaction 618 runs in exploratory mode; the toy lab environment has no assay concentrations (underparameterized).
MIXED_REQUEST = (*REACTION_618, "--environment", "toy_lab_environment")
SAMPLING = ("--mode", "exploratory", "--samples", "2", "--seed", "618", "--no-plots")
ESTERASE_KCAT_REQUEST = (
    "Measure kcat of carboxylesterase from Esterase source strain E1 on p-nitrophenyl butyrate "
    "at 37 degC, pH 7.5 (units of 1/time)."
)
FIT = (
    "--case",
    *ESTERASE_CASE,
    "--fit",
    "km",
    "10",
    "5000",
    "µM",
    "--fit",
    "kcat",
    "1",
    "300",
    "1/min",
    "--initial",
    "km",
    "1000",
    "--profile-points",
    "5",
)


def _refuse_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("The --json summaries must not touch the network; serve a synthetic response instead.")


@pytest.fixture(autouse=True, scope="module")
def no_network() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(urllib.request, "urlopen", _refuse_network)
        patch.setattr(sabiork_fetch, "urlopen", _refuse_network)
        patch.setattr(socket.socket, "connect", _refuse_network)
        yield


@pytest.fixture
def uniprot(monkeypatch: pytest.MonkeyPatch) -> _FakeUniprot:
    fake = _FakeUniprot()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


@pytest.fixture
def sabio(monkeypatch: pytest.MonkeyPatch) -> _FakeSabio:
    fake = _FakeSabio()
    monkeypatch.setattr(sabiork_fetch, "urlopen", fake)
    monkeypatch.setattr(sabiork_fetch, "MIN_REQUEST_INTERVAL_SECONDS", 0.0)
    return fake


@pytest.fixture(scope="module")
def timecourses(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The synthetic esterase time courses of tests/test_cli_user_data_workflow.py: three starting concentrations."""

    root = tmp_path_factory.mktemp("json_esterase")
    directory = _esterase_dataset(root / "dataset", conditions=STARTING_CONDITIONS)
    medians = _simulated_medians(
        directory, load_registry(REGISTRY_INDEX), root / "truth", strain=ESTERASE_STRAIN, substrate=ESTERASE_SUBSTRATE
    )
    sd = {condition: max(0.01 * initial, 0.5) for condition, initial in STARTING_CONDITIONS.items()}
    (directory / TIMECOURSE_TABLE).write_text(
        _timecourse_from(medians, case=ESTERASE_CASE, sd=sd, noise_seed=20261006), encoding="utf-8"
    )
    return directory


@pytest.fixture(scope="module")
def saturating(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Initial substrate far above Km, product only: the time courses do not identify Km (as in the workflow tests)."""

    root = tmp_path_factory.mktemp("json_saturating")
    conditions = {"s20000": 20000.0}
    directory = _esterase_dataset(root / "dataset", conditions=conditions)
    medians = _simulated_medians(
        directory, load_registry(REGISTRY_INDEX), root / "truth", strain=ESTERASE_STRAIN, substrate=ESTERASE_SUBSTRATE
    )
    (directory / TIMECOURSE_TABLE).write_text(
        _timecourse_from(medians, case=ESTERASE_CASE, sd={"s20000": 0.5}, observables=("product",), noise_seed=11),
        encoding="utf-8",
    )
    return directory


# ---------------------------------------------------------------------------
# Helpers


def _cli(*args: str | Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(arg) for arg in args])
    return code, out.getvalue(), err.getvalue()


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _reject_constant(name: str) -> None:
    raise AssertionError(f"the summary holds {name}, which is not JSON")


def _parse(text: str) -> dict[str, Any]:
    """Parse a summary, refusing NaN and infinity, and check the contract every summary keeps."""

    summary = json.loads(text, parse_constant=_reject_constant)
    json.dumps(summary, allow_nan=False)
    assert summary["kind"] == SUMMARY_KIND
    if summary["command"] == "run" and isinstance(summary["result"]["cases"], list):
        assert {case["status"] for case in summary["result"]["cases"]} <= set(RUN_CASE_STATUSES)
    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["fungmod_version"] == fungal_model.__version__
    assert summary["exit_meaning"] == EXIT_CODE_MEANINGS[summary["exit_code"]]
    assert set(summary["result"]) - {NULL_REASONS} == set(RESULT_SECTIONS[summary["command"]])
    _assert_nulls_have_reasons(summary)
    return summary


def _load(path: Path) -> dict[str, Any]:
    return _parse(path.read_text(encoding="utf-8"))


def _assert_nulls_have_reasons(value: Any, path: str = "$") -> None:
    """Every null is listed in its object's null_reasons with a stated reason, and null_reasons lists only nulls."""

    if isinstance(value, dict):
        nulls = {key for key, item in value.items() if item is None}
        reasons = value.get(NULL_REASONS, {})
        assert set(reasons) == nulls, f"{path}: nulls {sorted(nulls)}, reasons {sorted(reasons)}"
        for key, reason in reasons.items():
            assert isinstance(reason, str) and reason.strip(), f"{path}.{key}: no reason"
        for key, item in value.items():
            if key != NULL_REASONS and item is not None:
                _assert_nulls_have_reasons(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert item is not None, f"{path}[{index}] is a null without a place for its reason"
            _assert_nulls_have_reasons(item, f"{path}[{index}]")


def _reason(container: dict[str, Any], key: str) -> str:
    assert container[key] is None
    return container[NULL_REASONS][key]


def _metric_line(stdout: str, metric: str) -> str:
    (line,) = [line.strip() for line in stdout.splitlines() if line.strip().startswith(f"{metric} ")]
    return line


def _printed_requests(stdout: str) -> list[str]:
    block = stdout.split("Measurement requests:\n", 1)[1]
    requests = []
    for line in block.splitlines():
        if not line.startswith("  - "):
            break
        requests.append(line[4:])
    return requests


# ---------------------------------------------------------------------------
# The format


def test_the_schema_version_and_the_commands_with_json_are_pinned() -> None:
    assert SUMMARY_SCHEMA_VERSION == "1.0.0"
    assert set(RESULT_SECTIONS) == {"run", "assemble", "check-data", "fit"}
    assert list(RUN_CASE_STATUSES) == ["ran", "blocked", "refused", "failed"]
    for command in RESULT_SECTIONS:
        code, out, _ = _cli(command, "--help")
        assert code == EXIT_OK and "--json PATH" in out
    for command in ("preflight", "list", "draft-kinetics"):
        code, out, _ = _cli(command, "--help")
        assert code == EXIT_OK and "--json" not in out


def test_a_null_needs_a_reason_and_a_number_must_be_finite() -> None:
    text = render({"value": 1.5, "units": "mM", "seed": Unknown("scientific mode draws no samples")})
    assert json.loads(text) == {
        "value": 1.5,
        "units": "mM",
        "seed": None,
        NULL_REASONS: {"seed": "scientific mode draws no samples"},
    }
    with pytest.raises(SummaryContractError, match="null without a stated reason"):
        finalize({"seed": None})
    with pytest.raises(SummaryContractError, match="needs a stated reason"):
        Unknown("  ")
    for number in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(SummaryContractError, match="not a finite number"):
            finalize({"rmse": number})
    with pytest.raises(SummaryContractError, match="no place for its reason"):
        finalize([Unknown("a list item has no object to hold its reason")])


# ---------------------------------------------------------------------------
# run


def test_a_partial_run_summary_agrees_with_the_text_the_tables_and_the_exit_code(tmp_path: Path) -> None:
    arguments = ("run", *MIXED_REQUEST, *SAMPLING, "--runnable-only", "--report")
    plain_root, json_root = tmp_path / "plain", tmp_path / "with_json"
    code_plain, out_plain, err_plain = _cli(*arguments, "--output", plain_root / "run")
    output = json_root / "run"
    target = tmp_path / "run.json"
    code, out, err = _cli(*arguments, "--output", output, "--json", target)

    # The text and the exit code are those of the same run without --json.
    assert code == code_plain == EXIT_PARTIAL, err
    assert out.replace(str(json_root), "ROOT") == out_plain.replace(str(plain_root), "ROOT")
    assert err == err_plain == ""
    summary = _load(target)
    assert summary["command"] == "run" and summary["exit_code"] == EXIT_PARTIAL
    assert summary["arguments"] == [*arguments, "--output", str(output), "--json", str(target)]
    assert _reason(summary, "error") == "the command reported no error"
    result = summary["result"]
    assert result["request"] == {
        "mode": "exploratory",
        "samples_per_case": 2,
        "seed": 618,
        "runnable_only": True,
        "html_report": True,
        "quicklook_figures": False,
        "compare_timecourses": False,
        "output_directory": str(output),
    }
    experiment = result["experiment"]
    assert experiment["case_count"] == 2 and experiment["environment_count"] == 2
    assert _reason(experiment, "user_dataset") == "no --user-data was given"
    for item in experiment["resolved_names"]:
        assert f"  {item['record_type']} {item['query']!r} -> {item['record_id']} ({item['name']})" in out

    # Each case with its status and reason; the blocked one as case_summary.csv and the text give it.
    cases = {case["case_id"]: case for case in result["cases"]}
    table = {row["case_id"]: row for row in _csv_rows(output / "case_summary.csv")}
    assert [(case["case_id"], case["status"]) for case in result["cases"]] == [
        ("case_0000", "ran"),
        ("case_0001", "blocked"),
    ]
    blocked = cases["case_0001"]
    assert blocked["reason"] == table["case_0001"]["not_simulated_reason"]
    assert f"  not simulated: {blocked['reason']}" in out
    assert blocked["preflight"]["status"] == "underparameterized" and blocked["preflight"]["runnable"] is False
    assert blocked["preflight"]["missing_inputs"] == [
        "initial_cellobiose_concentration",
        "enzyme_concentration_beta_glucosidase",
    ]
    assert _reason(blocked, "final_metrics").startswith("the case was not simulated (blocked)")
    assert result["measurement_requests"] == _printed_requests(out) == blocked["preflight"]["measurement_requests"]

    # The simulated case's metrics are the summary table's values, printed to four significant figures.
    ran = cases["case_0000"]
    assert _reason(ran, "reason") == "the case ran"
    assert ran["samples"] == {"simulated": 2, "failed": 0}
    assert f"  environment effect: {ran['environment_effect']['status']}" in out
    summaries = {row["metric"]: row for row in _csv_rows(output / "summary_metrics.csv") if row["case_id"] == "case_0000"}
    assert {item["metric"] for item in ran["final_metrics"]} <= set(summaries)
    for item in ran["final_metrics"]:
        row = summaries[item["metric"]]
        assert (item["median"], item["p05"], item["p95"]) == (float(row["p50"]), float(row["p05"]), float(row["p95"]))
        assert item["units"] == row["units"] and item["computed_samples"] == 2 and item["not_computed"] == []
        line = _metric_line(out, item["metric"])
        assert f"{item['median']:.4g} [{item['p05']:.4g}, {item['p95']:.4g}] {item['units']} (n=2)" in line
    # No threshold is reached within the simulated span: the times are nulls with the printed reason.
    assert len(ran["threshold_times"]) == 3
    for item in ran["threshold_times"]:
        assert item["units"] == "second" and item["computed_samples"] == 0
        assert item["not_computed"] == [
            {"status": "not_reached", "samples": 2, "notes": ["Threshold was not reached within the simulated time span."]}
        ]
        text = "not_reached in 2 of 2 samples (Threshold was not reached within the simulated time span.)"
        assert _reason(item, "median") == f"no sample computed this metric: {text}"
        assert text in _metric_line(out, item["metric"])

    # The bundle: paths, counts and scope as written and printed.
    simulation = result["simulation"]
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert simulation["output_directory"] == str(output)
    assert simulation["manifest"] == str(output / "output_manifest.json")
    assert (simulation["partial_run"], simulation["requested_case_count"], simulation["simulated_case_count"]) == (
        True,
        2,
        1,
    )
    assert simulation["file_count"] == len(manifest["files"])
    assert simulation["tables"] == manifest["tables"]
    for path in (simulation["report"], simulation["html_report"], simulation["report_index"], *simulation["tables"].values()):
        assert Path(path).is_file(), path
    limitations = _csv_rows(output / "limitations_table.csv")
    severities = dict(sorted(Counter(row["severity"] for row in limitations).items()))
    assert simulation["limitations"]["count"] == len(limitations)
    assert simulation["limitations"]["by_severity"] == severities
    severity_text = ", ".join(f"{count} {severity}" for severity, count in severities.items())
    assert f"Limitations: {len(limitations)} ({severity_text}) in {simulation['limitations']['table']}" in out
    assert simulation["suggested_experiments"]["rows"] == len(_csv_rows(output / "suggested_experiments.csv"))
    assert f"Provenance: {simulation['provenance']['rows']} row(s)" in out
    assert _reason(simulation, "scientific_mode_note") == "the note is written in scientific mode only"
    assert _reason(result, "timecourse_comparison") == "--compare-timecourses was not given"
    # The summary is not part of the bundle.
    assert target.name not in manifest["files"] and target.parent != output


def test_a_refused_run_reports_its_blocked_and_refused_cases_with_reasons(tmp_path: Path) -> None:
    output = tmp_path / "refused"
    code, out, err = _cli("run", *MIXED_REQUEST, *SAMPLING, "--output", output, "--json", tmp_path / "refused.json")

    assert code == EXIT_NOT_RUNNABLE, err
    assert not output.exists()
    result = _load(tmp_path / "refused.json")["result"]
    refused, blocked = result["cases"]
    assert (refused["status"], blocked["status"]) == ("refused", "blocked")
    assert refused["preflight"]["runnable"] is True
    assert refused["reason"] == (
        "not simulated: the preflight blocks 1 of 2 requested case(s) in exploratory mode and --runnable-only was not "
        "given; FungMod simulates only when every requested case passes the preflight"
    )
    assert blocked["reason"] == (
        "blocked_by_preflight: the exploratory-mode preflight reports underparameterized (blocking reason "
        "missing_inputs; next action measure_or_curate_missing_inputs)"
    )
    assert "    blocked: missing_inputs; next action: measure_or_curate_missing_inputs" in out
    assert result["measurement_requests"] == _printed_requests(out)
    assert _reason(result, "simulation") == (
        "nothing was simulated: the preflight blocks 1 of 2 requested case(s) in exploratory mode"
    )
    assert _reason(refused, "samples").startswith("the case was not simulated (refused)")

    # --runnable-only with no runnable case: still exit 3, and the reason says so.
    code, out, err = _cli(
        "run",
        *REACTION_618[:4],
        "--environment",
        "toy_lab_environment",
        *SAMPLING,
        "--runnable-only",
        "--output",
        tmp_path / "none",
        "--json",
        tmp_path / "none.json",
    )
    assert code == EXIT_NOT_RUNNABLE, err
    result = _load(tmp_path / "none.json")["result"]
    assert [case["status"] for case in result["cases"]] == ["blocked"]
    assert _reason(result, "simulation").endswith("--runnable-only has nothing to simulate: no requested case is runnable")


def test_a_failed_simulation_reports_its_runnable_cases_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise VirtualExperimentError("synthetic failure raised by the test")

    monkeypatch.setattr(VirtualExperiment, "simulate", fail)
    code, out, err = _cli("run", *REACTION_618, *SAMPLING, "--output", tmp_path / "run", "--json", tmp_path / "s.json")

    assert code == EXIT_SIMULATION_FAILED
    assert "fungmod run: simulation failed: synthetic failure raised by the test" in err
    result = _load(tmp_path / "s.json")["result"]
    (case,) = result["cases"]
    assert case["status"] == "failed"
    assert case["reason"] == "the simulation failed after a passing preflight: synthetic failure raised by the test"
    assert _reason(result, "simulation") == case["reason"]


def test_json_dash_writes_pure_json_to_stdout_and_the_text_to_stderr(tmp_path: Path) -> None:
    code_plain, out_plain, err_plain = _cli("check-data", ESTERASE)
    code, out, err = _cli("check-data", ESTERASE, "--json", "-")

    assert code == code_plain == EXIT_OK
    assert err == out_plain + err_plain
    summary = _parse(out)  # the whole of standard output is the one JSON document
    assert summary["command"] == "check-data" and summary["result"]["valid"] is True

    code, out, err = _cli("run", *MIXED_REQUEST, *SAMPLING, "--output", tmp_path / "run", "--json", "-")
    assert code == EXIT_NOT_RUNNABLE
    assert "Not runnable: 1 of 2 case(s) cannot be simulated in exploratory mode." in err
    summary = _parse(out)
    assert summary["exit_code"] == EXIT_NOT_RUNNABLE
    assert [case["status"] for case in summary["result"]["cases"]] == ["refused", "blocked"]


@pytest.mark.parametrize("name", ["check_ok", "check_bad", "run_usage", "run_blocked", "fit_usage", "asm_usage"])
def test_the_text_and_the_exit_code_do_not_change_with_json(tmp_path: Path, name: str) -> None:
    bad = tmp_path / "bad_case"
    shutil.copytree(ESTERASE, bad)
    kinetics = bad / "kinetics.csv"
    kinetics.write_text(kinetics.read_text(encoding="utf-8").replace(",km,150,,,µM,", ",km,150,,,parsec,"), "utf-8")
    commands = {
        "check_ok": ("check-data", ESTERASE),
        "check_bad": ("check-data", bad),
        "run_usage": ("run", *REACTION_618, "--mode", "exploratory", "--output", tmp_path / "out"),
        "run_blocked": ("run", *MIXED_REQUEST, *SAMPLING, "--output", tmp_path / "out"),
        "fit_usage": ("fit", ESTERASE, "--case", *ESTERASE_CASE, "--fit", "km", "1", "2", "mM", "--output", tmp_path / "out"),
        "asm_usage": (*G1_ASSEMBLE, "--fungus", "second", "--output", tmp_path / "out"),
    }
    arguments = commands[name]

    plain = _cli(*arguments)
    with_json = _cli(*arguments, "--json", tmp_path / "summary.json")

    assert with_json == plain
    summary = _load(tmp_path / "summary.json")
    assert summary["exit_code"] == plain[0]
    if plain[0] == EXIT_USAGE:
        message = summary["error"]["message"]
        assert f"error: {message}" in plain[2]
        for line in summary["error"]["details"]:
            assert f"  {line}" in plain[2]


def test_a_usage_error_leaves_the_sections_not_reached(tmp_path: Path) -> None:
    code, out, err = _cli("run", *REACTION_618, "--mode", "exploratory", "--output", tmp_path / "out", "--json", "-")

    assert code == EXIT_USAGE and out.startswith("{")
    summary = _parse(out)
    assert summary["error"] == {
        "message": "--samples N is required in exploratory mode; FungMod does not choose a sample count.",
        "details": [],
    }
    assert f"fungmod run: error: {summary['error']['message']}" in err
    result = summary["result"]
    assert all(result[section] is None for section in RESULT_SECTIONS["run"])
    assert set(result[NULL_REASONS].values()) == {NOT_REACHED}


def test_a_json_path_is_checked_before_the_command_runs(tmp_path: Path) -> None:
    existing = tmp_path / "existing.json"
    existing.write_text("kept\n", encoding="utf-8")
    output = tmp_path / "run"
    refusals = {
        existing: "exists; choose a new file, nothing is overwritten",
        output / "summary.json": "is inside --output",
        tmp_path / "missing" / "summary.json": "does not exist; FungMod creates none for it",
    }
    for target, message in refusals.items():
        code, out, err = _cli("run", *REACTION_618, *SAMPLING, "--output", output, "--json", target)
        assert code == EXIT_USAGE, target
        assert message in err and out == ""
        assert not output.exists()
    assert existing.read_text(encoding="utf-8") == "kept\n"


# ---------------------------------------------------------------------------
# check-data


def test_check_data_summaries_state_pass_or_fail_the_errors_and_the_gaps(tmp_path: Path) -> None:
    gap = tmp_path / "gap_case"
    shutil.copytree(ESTERASE, gap)
    kinetics = gap / "kinetics.csv"
    kinetics.write_text(
        "".join(line for line in kinetics.read_text(encoding="utf-8").splitlines(keepends=True) if ",kcat," not in line),
        encoding="utf-8",
    )
    code, out, err = _cli("check-data", gap, "--registry", REGISTRY_INDEX, "--json", tmp_path / "gap.json")

    assert code == EXIT_OK, err
    result = _load(tmp_path / "gap.json")["result"]
    dataset = load_user_dataset(gap, registry=REGISTRY_INDEX)
    assert result["valid"] is True and result["errors"] == []
    assert result["dataset"]["digest"] == dataset.digest and f"Digest: {dataset.digest}" in out
    assert result["dataset"]["time_grid"] == {"duration": 60, "units": "minute", "points": 61}
    assert "Simulation time grid: 60 minute, 61 points" in out
    assert result["dataset"]["record_counts"]["parameter_records"] == 4
    assert (result["dataset"]["kinetic_values"], result["dataset"]["gap_count"]) == (3, 1)
    assert "Kinetic values: 3; gaps: 1" in out
    assert result["gaps"] == [
        {
            "record_id": "esterase_demo__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__c37_ph7_5__kcat__gap",
            "measurement_request": ESTERASE_KCAT_REQUEST,
        }
    ]
    assert f"    measurement request: {ESTERASE_KCAT_REQUEST}" in out
    assert _reason(result["dataset"], "fitted_values").startswith("the dataset holds no fit block")

    bad = tmp_path / "bad_case"
    shutil.copytree(ESTERASE, bad)
    kinetics = bad / "kinetics.csv"
    text = kinetics.read_text(encoding="utf-8")
    text = text.replace(",km,150,,,µM,", ",km,150,,,parsec,").replace(",kcat,30,,,1/min,", ",kcat,30,,,furlong,")
    kinetics.write_text(text, encoding="utf-8")
    (bad / "extra_table.csv").write_text("a\n1\n", encoding="utf-8")
    code, out, err = _cli("check-data", bad, "--json", tmp_path / "bad.json")

    assert code == EXIT_USAGE
    summary = _load(tmp_path / "bad.json")
    result = summary["result"]
    assert result["valid"] is False
    assert _reason(result, "dataset") == "the dataset did not load: see errors"
    assert _reason(result, "gaps") == "the dataset did not load, so its gaps are not known"
    by_location = {item["location"]: item for item in result["errors"]}
    assert by_location["kinetics.csv:2:units"]["line"] == 2
    assert by_location["kinetics.csv:3:units"]["column"] == "units"
    file_level = by_location["extra_table.csv:-:-"]
    assert _reason(file_level, "line") == "a file-level issue: it names no line"
    assert _reason(file_level, "column") == "the issue names no column"
    for item in result["errors"]:
        assert f"  {item['location']}: {item['message']}" in err
    assert summary["error"]["details"] == [f"{item['location']}: {item['message']}" for item in result["errors"]]


# ---------------------------------------------------------------------------
# assemble


def test_an_assemble_summary_agrees_with_the_draft_and_the_text(tmp_path: Path) -> None:
    draft_dir = tmp_path / "g1_draft"
    code, out, err = _cli(*G1_ASSEMBLE, "--output", draft_dir, "--json", tmp_path / "g1.json")

    assert code == EXIT_OK, err
    summary = _load(tmp_path / "g1.json")
    result = summary["result"]
    assert result["request"]["dataset_id"] == "g1_cli" and result["request"]["network"] is False
    assert _reason(result, "proteome").startswith("neither --proteome nor --fetch-proteome was given")
    draft = result["draft"]
    api = assemble_user_tables(**G1_API).assembly
    assert draft["directory"] == str(draft_dir)
    assert draft["fungus"]["strain_id"] == "genome_annotated_strain_g1"
    assert _reason(draft["fungus"], "registry_fungus_id") == "the fungus is not a registry record (resolved as new_strain)"
    assert [item["enzyme_class"] for item in draft["enzyme_classes"]] == [
        item["enzyme_class"] for item in api["enzyme_classes"]
    ]
    assert f"Enzyme classes of the fungus: {len(draft['enzyme_classes'])}" in out
    (acting,) = draft["acting_classes"]
    assert acting["acting"] == ["beta_glucosidase"]
    assert f"On Cellobiose (cellobiose): acting classes {', '.join(acting['acting'])}" in out
    for entry in acting["not_acting"]:
        assert f"  not acting: {entry['enzyme_class']}: {entry['reason']}" in out

    # The kinetics status of each case (class x substrate x condition), and a count of each of the five statuses.
    assert [(case["condition"], case["kinetics_status"]) for case in draft["cases"]] == [
        (case["condition"], case["kinetics_status"]) for case in api["cases"]
    ] == [("c30_ph5", "transferred_estimate"), ("c40_ph5", "gap")]
    for case in draft["cases"]:
        assert f"  case {case['number']}: {case['reason']}" in out
    assert list(draft["kinetics_status_counts"]) == list(ASSEMBLY_STATUSES)
    assert len(ASSEMBLY_STATUSES) == 5
    assert draft["kinetics_status_counts"]["transferred_estimate"] == draft["kinetics_status_counts"]["gap"] == 1
    assert sum(draft["kinetics_status_counts"].values()) == len(draft["cases"])
    assert draft["transferred_entry_ids"] == ["35622"]

    # The REVIEW: fields as printed, the files as written, the next commands as printed.
    assert len(draft["review_fields"]) == 8
    for field in draft["review_fields"]:
        assert f"  {field['location']}: {field['note']}" in out
    contributor = draft["review_fields"][0]
    assert contributor["location"] == "user_dataset.yml:-:contributor"
    assert _reason(contributor, "line") == "a field of user_dataset.yml: it has no line"
    written = sorted(path.relative_to(draft_dir).as_posix() for path in draft_dir.rglob("*") if path.is_file())
    assert sorted(draft["written_files"]) == written
    for name, path in draft["written_files"].items():
        assert Path(path) == draft_dir / name
    steps = draft["next_steps"]
    assert steps["review_fields_to_fill"] == 8 and steps["review_file"] == str(draft_dir / "review.md")
    check, run = steps["commands"]
    assert f"  2. {check['command']}" in out
    assert _reason(check, "complete_with") == "the command is complete as printed"
    assert f"     {run['command']} \\\n       {run['complete_with']}\n" in out
    assert run["command"].endswith("--condition c30_ph5 --condition c40_ph5 --runnable-only")
    (note,) = run["notes"]
    assert note.startswith("--runnable-only because 1 case(s) of this command have no kinetics") and note in out
    assert draft["snapshots"] == {"proteome": [], "kinetics": []}
    assert _reason(draft, "kinetics_lookup") == "--fetch-kinetics was not given"
    assert _reason(draft, "network") == "--network was not given"
    assert draft["limitations"] == list(api["limitations"])


def test_an_assemble_summary_names_the_proteome_and_its_snapshots(
    uniprot: _FakeUniprot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _served_u1(uniprot)
    snapshots = tmp_path / "snapshots"
    code, out, err = _cli(
        *_assemble(NAME_U1, snapshots, "--fetch-proteome"),
        "--fetch",
        "--output",
        tmp_path / "draft",
        "--json",
        tmp_path / "u1.json",
    )

    assert code == EXIT_OK, err
    result = _load(tmp_path / "u1.json")["result"]
    proteome = result["proteome"]
    assert proteome["proteome_id"] == "UP000000000" and proteome["chosen_by"] == "--fetch-proteome"
    assert (proteome["name_searched"], proteome["name_from"]) == (NAME_U1, "--fungus")
    assert f"chosen: UP000000000 ({NAME_U1}) because {proteome['match_rule']}" in out
    assert [item["proteome_id"] for item in proteome["candidates"] if item["chosen"]] == ["UP000000000"]
    assert len(proteome["candidates"]) == 2
    assert proteome["network_used"] is True and proteome["uniprot_release"] == "fixture_release"
    assert proteome["snapshot_directory"] == str(snapshots)
    assert f"snapshot {proteome['export_snapshot']} (SHA-256 {proteome['sha256']}" in out
    assert result["draft"]["snapshots"]["proteome"] == [proteome["search_snapshot"], proteome["export_snapshot"]]
    for path in result["draft"]["snapshots"]["proteome"]:
        assert Path(path).is_dir()

    # By identifier, offline: no name was searched, and the frozen export is read.
    monkeypatch.setattr(urllib.request, "urlopen", _refuse_network)
    code, out, err = _cli(
        *_assemble(NAME_U1, snapshots, "--proteome", "UP000000000"),
        "--output",
        tmp_path / "by_id",
        "--json",
        tmp_path / "by_id.json",
    )
    assert code == EXIT_OK, err
    proteome = _load(tmp_path / "by_id.json")["result"]["proteome"]
    assert (proteome["proteome_id"], proteome["chosen_by"], proteome["network_used"]) == (
        "UP000000000",
        "--proteome",
        False,
    )
    assert _reason(proteome, "candidates") == "--proteome names the proteome; no name was searched"


def test_a_proteome_without_a_release_header_has_a_null_release_with_the_reason(
    uniprot: _FakeUniprot, tmp_path: Path
) -> None:
    _served_b2(uniprot)
    code, out, err = _cli(
        *_assemble("Strain B2", tmp_path / "snapshots", "--scientific-name", NAME_B2, "--fetch-proteome", "--fetch"),
        "--output",
        tmp_path / "draft",
        "--json",
        tmp_path / "b2.json",
    )

    assert code == EXIT_OK, err
    proteome = _load(tmp_path / "b2.json")["result"]["proteome"]
    assert proteome["name_from"] == "--scientific-name"
    assert _reason(proteome, "uniprot_release") == (
        "UniProt sent no release header; the retrieval date stands for the version"
    )
    assert "no UniProt release header" in out


def test_an_assemble_summary_lists_the_kinetics_lookup_and_its_snapshots(sabio: _FakeSabio, tmp_path: Path) -> None:
    sabio.serve(QUERY_A, BODY_A)
    cache = tmp_path / "kinetics"
    code, out, err = _cli(*_assemble_k1(cache, "--fetch", "--output", tmp_path / "draft", "--json", tmp_path / "k1.json"))

    assert code == EXIT_OK, err
    draft = _load(tmp_path / "k1.json")["result"]["draft"]
    lookup = draft["kinetics_lookup"]
    assert lookup["network_used"] is True and lookup["cache_directory"] == str(cache)
    (query,) = lookup["queries"]
    assert (query["enzyme_class"], query["ec_number"], query["query"]) == ("beta_glucosidase", "3.2.1.21", QUERY_A)
    assert _reason(query, "class_defined_in") == "a registry class"
    assert query["entries"] == 7
    assert query["counts"] == {"converted": 1, "listed": 1, "not used": 2, "not convertible": 3}
    assert f"beta_glucosidase on cellobiose, EC 3.2.1.21: {QUERY_A}" in out
    assert draft["snapshots"]["kinetics"] == [query["snapshot"]] and Path(query["snapshot"]).is_dir()
    assert Path(query["snapshot"]).parent.parent == cache and Path(query["export"]).is_file()
    assert f"    snapshot {Path(query['snapshot']).relative_to(cache).as_posix()} (retrieved {query['retrieved_at']}" in out
    assert [(case["condition"], case["kinetics_status"]) for case in draft["cases"]] == [
        ("c30_ph5", "literature_same_organism"),
        ("c40_ph5", "gap"),
    ]
    assert draft["kinetics_status_counts"]["literature_same_organism"] == 1


def test_an_assemble_summary_of_an_enzyme_network(tmp_path: Path) -> None:
    code, out, err = _cli(
        "assemble",
        "--fungus",
        "strain_n1",
        "--user-data",
        _without_network_block(tmp_path, CHAIN),
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
        tmp_path / "chain_draft",
        "--json",
        tmp_path / "chain.json",
    )

    assert code == EXIT_OK, err
    draft = _load(tmp_path / "chain.json")["result"]["draft"]
    network = draft["network"]
    assert network["entry_substrates"] == ["polymer_p1"]
    (item,) = network["networks"]
    members = {member["enzyme_class"]: member for member in item["members"]}
    assert members["depolymerase_like"]["pool_role"] == "entry"
    assert members["oligomer_hydrolase_like"]["pool_role"] == "intermediate"
    assert members["depolymerase_like"]["kinetics_status"] == {"c30_ph5": "user_data", "c40_ph5": "gap"}
    statuses = {entry["condition"]: entry["status"] for entry in item["conditions"]}
    assert statuses == {"c30_ph5": "all_members_have_kinetics", "c40_ph5": "blocked"}
    assert "  c30_ph5: all_members_have_kinetics (initial concentration of polymer_p1: stated)" in out
    roles = {substrate["substrate_id"]: substrate["network_role"] for substrate in draft["substrates"]}
    assert roles["polymer_p1"] == "entry" and roles["oligomer_o1"] == "intermediate"
    (_, run) = draft["next_steps"]["commands"]
    assert run["command"].endswith("--runnable-only") and run["command"] in out


# ---------------------------------------------------------------------------
# fit and the comparison of run


def test_a_fit_summary_agrees_with_the_fit_report_and_the_text(tmp_path: Path, timecourses: Path) -> None:
    output = tmp_path / "fitted"
    code, out, err = _cli("fit", timecourses, *FIT, "--output", output, "--json", tmp_path / "fit.json")

    assert code == EXIT_OK, err
    result = _load(tmp_path / "fit.json")["result"]
    report = json.loads((output / "fit_report.json").read_text(encoding="utf-8"))
    request = result["request"]
    assert request["case"] == dict(report["case"]) and request["output_directory"] == str(output)
    assert [(item["quantity"], item["lower"], item["upper"], item["units"]) for item in request["quantities"]] == [
        ("km", 10.0, 5000.0, "µM"),
        ("kcat", 1.0, 300.0, "1/min"),
    ]
    assert request["quantities"][0]["initial"] == 1000.0
    assert _reason(request["quantities"][1], "initial") == "no --initial: the dataset's exact value is the start"

    fit = result["fit"]
    assert (fit["n_observations"], fit["residual_degrees_of_freedom"]) == (48, 46)
    assert fit["converged"] is True and fit["identified"] is True and fit["confidence_level"] == 0.95
    for item, entry in zip(fit["quantities"], report["quantities"], strict=True):
        assert (item["quantity"], item["value"], item["units"]) == (entry["quantity"], entry["value"], entry["units"])
        assert item["interval"] == {
            "lower": entry["interval"][0],
            "upper": entry["interval"][1],
            "units": entry["units"],
            "confidence_level": 0.95,
        }
        assert item["bounds"]["units"] == item["initial"]["units"] == entry["units"]
        line = next(text.split() for text in out.splitlines() if text.strip().startswith(f"{item['quantity']} "))
        assert line[1:3] == [f"{item['value']:.4g}", item["units"]]
    assert [(item["series_id"], item["rmse"], item["units"]) for item in fit["residuals"]] == [
        (entry["series_id"], entry["rmse"], entry["units"]) for entry in report["residuals"]
    ]
    assert sum(item["n_observations"] for item in fit["residuals"]) == 48

    fitted = load_user_dataset(output, registry=REGISTRY_INDEX)
    assert result["fitted_dataset"] == {
        "dataset_id": "esterase_demo_fitted",
        "digest": fitted.digest,
        "directory": str(fitted.source_directory),
        "fit_report": str(output / "fit_report.json"),
    }
    assert f"Fitted dataset: esterase_demo_fitted (digest {fitted.digest})" in out
    steps = result["next_steps"]
    check, run = steps["commands"]
    assert check["command"] == f"fungmod check-data {shell_quote(str(output))}" and f"  {check['command']}\n" in out
    assert f"  {run['command']} \\\n    {run['complete_with']}\n" in out
    assert run["complete_with"].endswith("--compare-timecourses")
    assert f"Next ({steps['note']}):" in out

    # check-data of the fitted dataset summarizes its fit block.
    code, out, err = _cli("check-data", output, "--json", tmp_path / "check.json")
    assert code == EXIT_OK, err
    (km, kcat) = _load(tmp_path / "check.json")["result"]["dataset"]["fitted_values"]["quantities"]
    assert km["value"] == fit["quantities"][0]["value"] and kcat["units"] == "1/min"
    assert _reason(km["interval"], "confidence_level").startswith("the fit block states no confidence level")


def test_refused_fits_are_summarized_with_what_the_fit_found(tmp_path: Path, saturating: Path) -> None:
    code, out, err = _cli(
        "fit", ESTERASE, "--case", *ESTERASE_CASE, "--fit", "km", "1", "2", "mM", "--output", tmp_path / "a",
        "--json", tmp_path / "early.json",
    )
    assert code == EXIT_USAGE
    result = _load(tmp_path / "early.json")["result"]
    assert _reason(result, "fit") == "the fit was refused before it ran, so there is no fit report (see error)"
    assert _reason(result, "fitted_dataset") == "the fit was refused; nothing was written"

    output = tmp_path / "refused"
    code, out, err = _cli(
        "fit",
        saturating,
        "--case",
        *ESTERASE_CASE,
        "--fit",
        "km",
        "10",
        "2000",
        "µM",
        "--fit",
        "kcat",
        "1",
        "100",
        "1/min",
        "--initial",
        "km",
        "500",
        "--initial",
        "kcat",
        "10",
        "--profile-points",
        "7",
        "--output",
        output,
        "--json",
        tmp_path / "refused.json",
    )
    assert code == EXIT_USAGE and not output.exists()
    summary = _load(tmp_path / "refused.json")
    fit = summary["result"]["fit"]
    assert fit["identified"] is False
    verdicts = {item["quantity"]: item["identifiability"] for item in fit["quantities"]}
    assert verdicts["kcat"] == "identified" and verdicts["km"] != "identified"
    assert verdicts["km"] in out
    assert summary["error"]["message"].startswith(
        "A fitted quantity is not identified by the time courses; no fitted values are written."
    )
    assert f"fungmod fit: error: {summary['error']['message']}" in err
    assert "On the command line, --allow-unidentified writes it labelled as not identified." in summary["error"]["details"]


def test_the_comparison_of_run_and_its_refusal_are_summarized(tmp_path: Path, timecourses: Path) -> None:
    conditions = [part for condition in STARTING_CONDITIONS for part in ("--condition", condition)]
    selection = ("--fungus", ESTERASE_STRAIN, "--substrate", ESTERASE_SUBSTRATE, *conditions)
    sampling = ("--mode", "exploratory", "--samples", "1", "--seed", "1", "--no-plots", "--compare-timecourses")
    output = tmp_path / "run"
    code, out, err = _cli(
        "run", "--user-data", timecourses, *selection, *sampling, "--output", output,
        "--json", tmp_path / "compare.json",
    )

    assert code == EXIT_OK, err
    result = _load(tmp_path / "compare.json")["result"]
    assert result["experiment"]["user_dataset"]["dataset_id"] == "esterase_demo"
    comparison = result["timecourse_comparison"]
    assert comparison["table"] == str(output / "timecourse_comparison.csv")
    assert f"Comparison table: {comparison['table']}" in out
    rows = {(row["case_id"], row["observable"]): row for row in _csv_rows(output / "timecourse_comparison.csv")}
    assert len(comparison["series"]) == 6
    for series in comparison["series"]:
        row = rows[(series["case_id"], series["observable"])]
        assert series["rmse"] == pytest.approx(float(row["series_rmse"]), rel=1e-12)
        assert series["units"] == row["units"] == "µM" and series["used_in_fit"] == 0
        assert series["n_observations"] == 8
    assert comparison["note"] in out
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert result["simulation"]["file_count"] == len(manifest["files"])

    # Observations beyond the simulated duration: the bundle is complete, the comparison refused (exit 2).
    short = tmp_path / "short"
    shutil.copytree(timecourses, short)
    manifest = yaml.safe_load((short / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["simulation"] = {"duration": 30, "units": "minute", "points": 31}
    (short / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    code, out, err = _cli(
        "run", "--user-data", short, *selection, *sampling, "--output", tmp_path / "short_run",
        "--json", tmp_path / "short.json",
    )
    assert code == EXIT_USAGE
    summary = _load(tmp_path / "short.json")
    result = summary["result"]
    assert [case["status"] for case in result["cases"]] == ["ran", "ran", "ran"]
    assert Path(result["simulation"]["manifest"]).is_file()
    assert _reason(result, "timecourse_comparison") == (
        f"the comparison was refused ({summary['error']['message']}); the simulation bundle is complete"
    )
    assert any(":time: time 40 minute of" in line for line in summary["error"]["details"])


def test_the_summary_module_names_no_kinetics_database_and_opens_no_connection() -> None:
    source = (ROOT / "src" / "fungal_model" / "cli_summary.py").read_text(encoding="utf-8")

    assert "sabio" not in source.lower()
    for forbidden in ("urllib", "urlopen", "socket", "refresh", "http://", "https://"):
        assert forbidden not in source, forbidden
