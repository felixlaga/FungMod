"""The ``fungmod`` command line (CLI-001): run, preflight, check-data, list and --version; run --runnable-only (RUN-001)."""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import fungal_model
from fungal_model.api.user_data import load_user_dataset
from fungal_model.api import VirtualExperimentError, environment_grid, virtual_experiment
from fungal_model.cli import (
    EXIT_NOT_RUNNABLE,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_SIMULATION_FAILED,
    EXIT_USAGE,
    EXPLORATORY_MODE_HELP,
    RUNNABLE_ONLY_HELP,
    SCIENTIFIC_MODE_HELP,
    main,
)
from fungal_model.registry import load_registry
from fungal_model.resources import default_registry_path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
ESTERASE = FIXTURES / "esterase_case"
LITERATURE = FIXTURES / "literature_reentry"

REACTION_618 = (
    "--fungus",
    "beta-glucosidase source",
    "--substrate",
    "cellobiose",
    "--environment",
    "SABIO-RK Reaction 618 selected assay conditions",
)
ORGANISM_CASE = (
    "--fungus",
    "T. harzianum P49P11",
    "--substrate",
    "Celufloc 200",
    "--environment",
    "gelain_2020_cellulose_batch_10gl",
)
# Reaction 618 runs in exploratory mode; the toy lab environment has no assay concentrations (underparameterized).
MIXED_REQUEST = (*REACTION_618, "--environment", "toy_lab_environment")
ESTERASE_SELECTION = (
    "--fungus",
    "Esterase source strain E1",
    "--substrate",
    "p-nitrophenyl butyrate",
    "--condition",
    "c37_ph7_5",
)
ESTERASE_KCAT_REQUEST = (
    "Measure kcat of carboxylesterase from Esterase source strain E1 on p-nitrophenyl butyrate "
    "at 37 degC, pH 7.5 (units of 1/time)."
)


def _cli(capsys: pytest.CaptureFixture[str], *args: str | Path) -> tuple[int, str, str]:
    code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _metric_line(stdout: str, metric: str) -> str:
    lines = [line.strip() for line in stdout.splitlines() if line.strip().startswith(f"{metric} ")]
    assert len(lines) == 1, (metric, lines)
    return lines[0]


def _copy_fixture(tmp_path: Path, source: Path) -> Path:
    destination = tmp_path / source.name
    shutil.copytree(source, destination)
    return destination


# ---------------------------------------------------------------------------
# run


def test_run_exploratory_registry_case_writes_bundle_and_prints_metrics(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "reaction_618"
    code, out, err = _cli(
        capsys,
        "run",
        *REACTION_618,
        "--mode",
        "exploratory",
        "--samples",
        "3",
        "--seed",
        "618",
        "--output",
        output,
        "--report",
    )

    assert code == EXIT_OK, err
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "exploratory"
    assert manifest["run_label"] == "exploratory_uncertainty_screen"
    assert {"report/virtual_experiment_report.md", "report/virtual_experiment_report.html", "report/index.html"} <= set(
        manifest["files"]
    )
    assert any(name.startswith("figures/") for name in manifest["files"])

    assert "Preflight in exploratory mode:" in out
    assert "sabiork_beta_glucosidase_source" in out
    assert "uncertain parameter enzyme_concentration_beta_glucosidase" in out
    assert "Simulated 1 case(s) in exploratory mode: 3 sample(s) per case, seed 618." in out
    summary = {row["metric"]: row for row in _csv_rows(output / "summary_metrics.csv")}
    remaining = summary["final_substrate_remaining"]
    assert remaining["count"] == "3"
    line = _metric_line(out, "final_substrate_remaining")
    assert f"{float(remaining['p50']):.4g} [{float(remaining['p05']):.4g}, {float(remaining['p95']):.4g}]" in line
    assert "millimolar" in line
    assert _metric_line(out, "time_to_50_percent_substrate_degradation")
    limitations = _csv_rows(output / "limitations_table.csv")
    assert f"Limitations: {len(limitations)} (" in out
    assert str(output / "limitations_table.csv") in out
    assert str(output / "provenance_table.csv") in out
    assert str(output / "report" / "virtual_experiment_report.html") in out


def test_run_scientific_organism_case_reports_exact_run_and_threshold_times(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "organism"
    code, out, err = _cli(
        capsys,
        "run",
        *ORGANISM_CASE,
        "--registry",
        REGISTRY_INDEX,
        "--mode",
        "scientific",
        "--output",
        output,
        "--no-plots",
    )

    assert code == EXIT_OK, err
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    assert not any(name.startswith("figures/") for name in manifest["files"])
    assert "report/virtual_experiment_report.md" in manifest["files"]
    assert "report/virtual_experiment_report.html" not in manifest["files"]
    assert "Simulated 1 case(s) in scientific mode: one exact run per case." in out
    assert "It is not a claim of experimental validation." in out
    thresholds = {row["metric"]: row for row in _csv_rows(output / "threshold_times.csv")}
    half = thresholds["time_to_50_percent_substrate_degradation"]
    assert half["status"] == "computed"
    line = _metric_line(out, "time_to_50_percent_substrate_degradation")
    assert f"{float(half['value']):.4g} {half['units']}" in line
    assert "not_applicable (No product state mapping was available.)" in _metric_line(
        out, "final_product_concentration"
    )


def test_run_environment_grid_and_scientific_preflight_gap(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    grid = ("--fungus", "P. chrysosporium", "--substrate", "cellobiose", "--temperature-c", "30", "--ph", "5", "--ph", "6")
    output = tmp_path / "grid"
    code, out, err = _cli(
        capsys, "run", *grid, "--mode", "exploratory", "--samples", "2", "--seed", "1", "--output", output, "--no-plots"
    )

    assert code == EXIT_OK, err
    assert "environment grid case temp_30C_ph_5p0_not_specified" in out
    assert "Case case_0001: phanerochaete_chrysosporium_k3 + cellobiose + temp_30C_ph_6p0_not_specified" in out
    cases = _csv_rows(output / "case_summary.csv")
    assert [row["environment_id"] for row in cases] == [
        "temp_30C_ph_5p0_not_specified",
        "temp_30C_ph_6p0_not_specified",
    ]
    assert out.count(f"environment effect: {cases[0]['environment_effect_status']}") == 2

    blocked_output = tmp_path / "blocked"
    code, out, err = _cli(capsys, "run", *grid, "--mode", "scientific", "--output", blocked_output)

    assert code == EXIT_NOT_RUNNABLE, err
    assert not blocked_output.exists()
    assert "Not runnable: 2 of 2 case(s) cannot be simulated in scientific mode." in out
    assert "it does not mean experimentally validated" in out
    assert "Measurement requests:" in out
    assert "Measure or curate bgl1a_assay_enzyme_concentration for the selected registry case." in out


def test_run_user_data_exploratory_and_scientific_routes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    esterase = load_user_dataset(ESTERASE, registry=REGISTRY_INDEX)
    output = tmp_path / "esterase"
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        ESTERASE,
        *ESTERASE_SELECTION,
        "--mode",
        "exploratory",
        "--samples",
        "2",
        "--seed",
        "5",
        "--output",
        output,
        "--no-plots",
    )

    assert code == EXIT_OK, err
    assert f"User dataset: esterase_demo (digest {esterase.digest})" in out
    assert "fungus 'Esterase source strain E1' -> esterase_demo__strain_e1" in out
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["user_dataset_id"] == "esterase_demo"
    assert manifest["user_dataset_digest"] == esterase.digest

    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        ESTERASE,
        *ESTERASE_SELECTION,
        "--mode",
        "scientific",
        "--output",
        tmp_path / "esterase_scientific",
    )
    assert code == EXIT_NOT_RUNNABLE, err
    assert "Not runnable: 1 of 1 case(s) cannot be simulated in scientific mode." in out

    output = tmp_path / "reentry"
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        LITERATURE,
        "--fungus",
        "Os3BGlu6 source",
        "--substrate",
        "cellobiose",
        "--condition",
        "c30_ph5",
        "--mode",
        "scientific",
        "--output",
        output,
        "--no-plots",
    )

    assert code == EXIT_OK, err
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "scientific"
    assert manifest["user_dataset_id"] == "reaction_618_reentry"
    assert "Simulated 1 case(s) in scientific mode: one exact run per case." in out
    assert _metric_line(out, "final_substrate_degraded_fraction")


# ---------------------------------------------------------------------------
# run --runnable-only (RUN-001)


def test_run_runnable_only_simulates_the_runnable_cases_lists_the_blocked_ones_and_exits_4(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sampling = ("--mode", "exploratory", "--samples", "2", "--seed", "618", "--no-plots")
    refused = tmp_path / "refused"
    code, out, err = _cli(capsys, "run", *MIXED_REQUEST, *sampling, "--output", refused)

    # Without the flag nothing changes: exit 3, nothing written; the flag is suggested.
    assert code == EXIT_NOT_RUNNABLE, err
    assert not refused.exists()
    assert "Nothing was simulated: FungMod simulates only when every requested case passes the preflight." in out
    assert (
        "Add --runnable-only to simulate the 1 runnable case(s) and list the blocked one(s) as not simulated "
        "(exit code 4)."
    ) in out

    output = tmp_path / "partial"
    code, out, err = _cli(capsys, "run", *MIXED_REQUEST, *sampling, "--output", output, "--runnable-only", "--report")

    assert code == EXIT_PARTIAL == 4, err
    assert "Not runnable: 1 of 2 case(s) cannot be simulated in exploratory mode." in out
    assert "--runnable-only: simulating the 1 runnable case(s); the blocked case(s) are not simulated" in out
    assert (
        "Measurement requests:\n"
        "  - Measure or curate initial_cellobiose_concentration for the selected registry case.\n"
        "  - Measure or curate enzyme_concentration_beta_glucosidase for the selected registry case."
    ) in out
    assert "Nothing was simulated" not in out
    assert "Simulated 1 case(s) in exploratory mode: 2 sample(s) per case, seed 618." in out
    assert "Partial run: 1 of 2 requested case(s) simulated; the others were blocked by the preflight." in out
    assert (
        "Case case_0001: sabiork_beta_glucosidase_source + cellobiose + toy_lab_environment\n"
        "  not simulated: blocked_by_preflight: the exploratory-mode preflight reports underparameterized"
    ) in out
    assert _metric_line(out, "final_substrate_remaining")  # printed once, for the simulated case only
    assert out.rstrip().endswith(
        "Partial run: 1 of 2 requested case(s) were blocked by the preflight and not simulated (case_0001); exit code 4."
    )

    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["partial_run"] is True
    assert [case["case_id"] for case in manifest["blocked_cases"]] == ["case_0001"]
    assert {
        "case_summary.csv",
        "modelability_preflight.csv",
        "missing_parameters.csv",
        "suggested_experiments.csv",
        "report/virtual_experiment_report.md",
        "report/virtual_experiment_report.html",
    } <= set(manifest["files"])
    cases = _csv_rows(output / "case_summary.csv")
    assert [(row["case_id"], row["environment_id"], row["case_status"]) for row in cases] == [
        ("case_0000", "sabiork_reaction_618_selected_conditions", "simulated"),
        ("case_0001", "toy_lab_environment", "not_simulated"),
    ]
    requests = {
        row["suggested_experiment"] for row in _csv_rows(output / "suggested_experiments.csv") if row["case_id"] == "case_0001"
    }
    assert "Measure or curate enzyme_concentration_beta_glucosidase for the selected registry case." in requests
    report = (output / "report" / "virtual_experiment_report.md").read_text(encoding="utf-8")
    assert "**Partial run:** 1 of 2 requested cases were simulated." in report


def test_runnable_only_exits_3_when_nothing_is_runnable_and_0_when_nothing_is_blocked(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sampling = ("--mode", "exploratory", "--samples", "1", "--seed", "1", "--no-plots", "--runnable-only")
    blocked_only = (*REACTION_618[:4], "--environment", "toy_lab_environment")
    output = tmp_path / "nothing_runnable"
    code, out, err = _cli(capsys, "run", *blocked_only, *sampling, "--output", output)

    assert code == EXIT_NOT_RUNNABLE, err
    assert not output.exists()
    assert "--runnable-only has nothing to simulate: no requested case is runnable." in out
    assert "Measure or curate initial_cellobiose_concentration for the selected registry case." in out

    output = tmp_path / "nothing_blocked"
    code, out, err = _cli(capsys, "run", *REACTION_618, *sampling, "--output", output)

    assert code == EXIT_OK, err
    assert "Partial run" not in out and "Not runnable" not in out
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert (manifest["partial_run"], manifest["blocked_cases"]) == (False, [])


def test_scientific_runnable_only_simulates_only_modelable_cases_and_keeps_the_scientific_wording(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "scientific"
    code, out, err = _cli(
        capsys,
        "run",
        *ORGANISM_CASE,
        "--environment",
        "toy_lab_environment",
        "--mode",
        "scientific",
        "--output",
        output,
        "--no-plots",
        "--runnable-only",
    )

    assert code == EXIT_PARTIAL, err
    assert "it does not mean experimentally validated" in out
    assert "Simulated 1 case(s) in scientific mode: one exact run per case." in out
    assert "It is not a claim of experimental validation." in out
    assert "the scientific-mode preflight reports underparameterized" in out
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    assert [(case["case_id"], case["environment_id"]) for case in manifest["blocked_cases"]] == [
        ("case_0001", "toy_lab_environment")
    ]


# ---------------------------------------------------------------------------
# preflight


def test_preflight_gap_exits_3_with_measurement_request(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    dataset = _copy_fixture(tmp_path, ESTERASE)
    kinetics = dataset / "kinetics.csv"
    kinetics.write_text(
        "".join(line for line in kinetics.read_text(encoding="utf-8").splitlines(keepends=True) if ",kcat," not in line),
        encoding="utf-8",
    )
    selection = ("--user-data", dataset, *ESTERASE_SELECTION, "--mode", "exploratory")

    tables = tmp_path / "preflight_tables"
    code, out, err = _cli(capsys, "preflight", *selection, "--output", tables)

    assert code == EXIT_NOT_RUNNABLE, err
    assert "underparameterized" in out
    assert "missing parameter esterase_demo__kcat__carboxylesterase__p_nitrophenyl_butyrate" in out
    assert f"suggested experiment: {ESTERASE_KCAT_REQUEST}" in out
    assert f"Measurement requests:\n  - {ESTERASE_KCAT_REQUEST}" in out
    assert ESTERASE_KCAT_REQUEST in (tables / "modelability_preflight.csv").read_text(encoding="utf-8")

    output = tmp_path / "run"
    code, out, err = _cli(capsys, "run", *selection, "--samples", "2", "--seed", "1", "--output", output)
    assert code == EXIT_NOT_RUNNABLE, err
    assert ESTERASE_KCAT_REQUEST in out
    assert not output.exists()


def test_preflight_runnable_case_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(capsys, "preflight", *ORGANISM_CASE, "--mode", "scientific")

    assert code == EXIT_OK, err
    assert "All 1 case(s) are runnable in scientific mode." in out
    assert "trichoderma_harzianum_p49p11" in out


# ---------------------------------------------------------------------------
# check-data and list


def test_check_data_reports_dataset_digest_records_and_gaps(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    esterase = load_user_dataset(ESTERASE, registry=REGISTRY_INDEX)
    code, out, err = _cli(capsys, "check-data", ESTERASE)

    assert code == EXIT_OK, err
    assert "User dataset: esterase_demo" in out
    assert f"Digest: {esterase.digest}" in out
    assert "parameter_records      4" in out
    assert "Kinetic values: 4; gaps: 0" in out

    dataset = _copy_fixture(tmp_path, ESTERASE)
    kinetics = dataset / "kinetics.csv"
    kinetics.write_text(
        "".join(line for line in kinetics.read_text(encoding="utf-8").splitlines(keepends=True) if ",kcat," not in line),
        encoding="utf-8",
    )
    code, out, err = _cli(capsys, "check-data", dataset, "--registry", REGISTRY_INDEX)

    assert code == EXIT_OK, err
    assert "Kinetic values: 3; gaps: 1" in out
    assert "esterase_demo__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__c37_ph7_5__kcat__gap" in out
    assert f"measurement request: {ESTERASE_KCAT_REQUEST}" in out


def test_check_data_lists_every_issue_and_exits_2(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    dataset = _copy_fixture(tmp_path, ESTERASE)
    kinetics = dataset / "kinetics.csv"
    text = kinetics.read_text(encoding="utf-8")
    text = text.replace(",km,150,,,µM,", ",km,150,,,parsec,").replace(",kcat,30,,,1/min,", ",kcat,30,,,furlong,")
    kinetics.write_text(text, encoding="utf-8")

    code, out, err = _cli(capsys, "check-data", dataset)

    assert code == EXIT_USAGE
    assert out == ""
    assert "is invalid. 2 issue(s):" in err
    assert "kinetics.csv:2:units: km units 'parsec' must be a substrate concentration" in err
    assert "kinetics.csv:3:units: kcat units 'furlong' must have the dimension 1/time" in err

    code, out, err = _cli(
        capsys, "run", "--user-data", dataset, *ESTERASE_SELECTION, "--mode", "scientific", "--output", tmp_path / "o"
    )
    assert code == EXIT_USAGE
    assert "kinetics.csv:2:units:" in err and "kinetics.csv:3:units:" in err
    assert not (tmp_path / "o").exists()


def test_list_shows_registry_and_user_data_records(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(capsys, "list")

    assert code == EXIT_OK, err
    registry = load_registry(default_registry_path())
    assert f"(registry {registry.registry_id}, version {registry.version}, maturity {registry.maturity})" in out
    for records in (registry.fungi, registry.substrates, registry.environments):
        for record in records.values():
            assert any(
                line.split()[:1] == [record.record_id] and record.maturity in line for line in out.splitlines()
            ), record.record_id
    assert "esterase_demo__strain_e1" not in out
    assert "aliases" not in out

    code, out, err = _cli(capsys, "list", "--user-data", ESTERASE, "--aliases")
    assert code == EXIT_OK, err
    assert "User dataset: esterase_demo" in out
    assert "esterase_demo__strain_e1" in out
    assert "esterase_demo__c37_ph7_5" in out
    assert "P. chrysosporium" in out


# ---------------------------------------------------------------------------
# usage errors, help and entry points


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--samples", "2", "--seed", "1", "--output", "{out}"), "the following arguments are required: --mode"),
        (("--mode", "exploratory", "--samples", "2", "--output", "{out}"), "--seed S is required"),
        (("--mode", "exploratory", "--seed", "1", "--output", "{out}"), "--samples N is required"),
        (("--mode", "exploratory", "--samples", "2", "--seed", "1"), "the following arguments are required: --output"),
        (("--mode", "scientific", "--samples", "2", "--output", "{out}"), "--samples applies only to exploratory mode"),
        (("--mode", "scientific", "--seed", "3", "--output", "{out}"), "--seed applies only to exploratory mode"),
        (("--mode", "exploratory", "--samples", "0", "--seed", "1", "--output", "{out}"), "at least 1"),
        (("--mode", "exploratory", "--samples", "2", "--seed", "-1", "--output", "{out}"), "at least 0"),
        (("--mode", "bayesian", "--output", "{out}"), "invalid choice: 'bayesian'"),
    ],
)
def test_run_usage_errors_exit_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, arguments: tuple[str, ...], message: str
) -> None:
    output = tmp_path / "out"
    resolved = [str(output) if argument == "{out}" else argument for argument in arguments]

    code, out, err = _cli(capsys, "run", *REACTION_618, *resolved)

    assert code == EXIT_USAGE
    assert message in err
    assert not output.exists()


@pytest.mark.parametrize(
    ("selection", "message"),
    [
        (("--fungus", "no such fungus", "--substrate", "cellobiose", "--environment", "30C_pH5_assay"),
         "Could not resolve fungus 'no such fungus'"),
        (("--fungus", "P. chrysosporium", "--substrate", "cellobiose", "--temperature-c", "30"),
         "needs at least one --temperature-c and at least one --ph value"),
        (("--fungus", "P. chrysosporium", "--substrate", "cellobiose", "--environment", "30C_pH5_assay", "--ph", "5"),
         "not both"),
        (("--fungus", "P. chrysosporium", "--substrate", "cellobiose"), "name the conditions"),
        (("--fungus", "P. chrysosporium", "--substrate", "cellobiose", "--temperature-c", "inf", "--ph", "5"),
         "is not a finite number"),
        (("--fungus", "P. chrysosporium", "--substrate", "cellobiose", "--environment", "30C_pH5_assay",
          "--registry", "missing_registry.yml"), "is not a file"),
        (("--fungus", "P. chrysosporium", "--substrate", "cellobiose", "--condition", "c1", "--user-data", "no_dir"),
         "is not a directory"),
    ],
)
def test_selection_input_errors_exit_2(
    capsys: pytest.CaptureFixture[str], selection: tuple[str, ...], message: str
) -> None:
    code, out, err = _cli(capsys, "preflight", *selection, "--mode", "exploratory")

    assert code == EXIT_USAGE
    assert message in err


def test_run_refuses_a_non_empty_output_directory(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    output = tmp_path / "used"
    output.mkdir()
    (output / "earlier.csv").write_text("x\n", encoding="utf-8")

    code, out, err = _cli(capsys, "run", *ORGANISM_CASE, "--mode", "scientific", "--output", output)

    assert code == EXIT_USAGE
    assert "is not empty" in err
    assert sorted(path.name for path in output.iterdir()) == ["earlier.csv"]


def test_help_explains_both_modes_with_the_api_wording(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, top, _ = _cli(capsys, "--help")
    assert code == EXIT_OK
    code, run_help, _ = _cli(capsys, "run", "--help")
    assert code == EXIT_OK
    code, preflight_help, _ = _cli(capsys, "preflight", "--help")
    assert code == EXIT_OK

    api_wording = (
        "Scientific means exact with current registry records and implemented mechanisms; "
        "it does not mean experimentally validated."
    )
    study = virtual_experiment(
        fungi="P. chrysosporium", substrates="cellobiose", environments=environment_grid(temperature_C=[30], ph=[5])
    )
    with pytest.raises(VirtualExperimentError) as blocked:
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)
    assert api_wording in str(blocked.value)
    assert api_wording.lower() in SCIENTIFIC_MODE_HELP.lower()
    for text in (top, run_help, preflight_help):
        lines = text.splitlines()
        assert f"  {EXPLORATORY_MODE_HELP}" in lines
        assert f"  {SCIENTIFIC_MODE_HELP}" in lines
        assert "  3  the preflight blocks a requested case in the requested mode; nothing is simulated" in lines
        assert (
            "  4  partial run (run --runnable-only): the runnable cases were simulated, the blocked ones are listed"
            in lines
        )
    assert "--mode" in run_help and "required" in run_help
    assert "--runnable-only" in run_help
    assert " ".join(RUNNABLE_ONLY_HELP.split()) in " ".join(run_help.split())


def test_exit_code_4_is_distinct_and_documented() -> None:
    codes = (EXIT_OK, EXIT_SIMULATION_FAILED, EXIT_USAGE, EXIT_NOT_RUNNABLE, EXIT_PARTIAL)
    assert codes == (0, 1, 2, 3, 4)
    docs = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    assert "| 4 | Partial run" in docs
    assert "--runnable-only" in docs


def test_version_and_missing_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(capsys, "--version")
    assert code == EXIT_OK
    assert out.strip() == f"fungmod {fungal_model.__version__}"

    code, out, err = _cli(capsys)
    assert code == EXIT_USAGE
    assert "required: COMMAND" in err


def test_console_script_is_registered_in_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"] == {"fungmod": "fungal_model.cli:main"}


def test_python_dash_m_fungal_model_prints_the_version() -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT / "src"), environment.get("PYTHONPATH", "")) if part
    )
    completed = subprocess.run(
        [sys.executable, "-m", "fungal_model", "--version"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == f"fungmod {fungal_model.__version__}"
