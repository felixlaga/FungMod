"""Partial runs (RUN-001): simulate the runnable cases of a request and report the blocked ones.

``VirtualExperiment.simulate(blocked="report")`` simulates exactly the cases
whose preflight allows simulation in the requested mode, lists the blocked
cases in the tables, summary, manifest and report as not simulated, and keeps
every case's grid position and seed, so that a case's samples do not depend on
which other cases of the request run. The default, ``blocked="refuse"``, is
unchanged. Cases come from the shipped registry and from a user dataset written
by the test (the esterase fixture at three conditions, with sampled kcat
ranges): two materially different routes through the same code.
"""

from __future__ import annotations

import csv
import json
import shutil
from itertools import product
from pathlib import Path
from typing import Any

import pytest

from fungal_model import VirtualExperiment
from fungal_model.api import VirtualExperimentError, virtual_experiment
from fungal_model.api.output_schema import OUTPUT_SCHEMA_VERSION, OUTPUT_TABLE_SCHEMAS
from fungal_model.api.result_tables import (
    CASE_STATUS_NOT_SIMULATED,
    CASE_STATUS_SIMULATED,
    not_simulated_reason,
    preflight_policy,
    write_standard_tables,
)
from fungal_model.screening import RegistryScreenResult, RegistryScreenSimulationError, simulate_screen

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
ESTERASE = ROOT / "tests" / "fixtures" / "user_data" / "esterase_case"

ENZYME_SOURCE = "sabiork_beta_glucosidase_source"
CELLOBIOSE = "cellobiose"
RUNNABLE_ENVIRONMENT = "sabiork_reaction_618_selected_conditions"  # exploratory: sampled enzyme concentration
BLOCKED_ENVIRONMENT = "toy_lab_environment"  # underparameterized: no assay concentrations

ORGANISM = "trichoderma_harzianum_p49p11"
CELLULOSE = "cellulose_celufloc_200"
CULTURE = "gelain_2020_cellulose_batch_10gl"
BGL1A_SOURCE = "phanerochaete_chrysosporium_k3"

PER_SAMPLE_TABLES = (
    "time_series_long",
    "final_states",
    "final_metrics",
    "threshold_times",
    "sampled_parameters",
    "summary_metrics",
    "trajectory_quantiles",
)

ESTERASE_STRAIN = "Esterase source strain E1"
ESTERASE_SUBSTRATE = "p-nitrophenyl butyrate"
ESTERASE_CONDITIONS = ("c30_ph7_5", "c37_ph7_5", "c45_ph7_5")
ESTERASE_SOURCE = "FungMod user-data import fixture; illustrative values, not measurements"


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry_study(*environments: str, fungi: tuple[str, ...] = (ENZYME_SOURCE,), substrates: tuple[str, ...] = (CELLOBIOSE,)) -> VirtualExperiment:
    return VirtualExperiment.from_registry(
        fungi=list(fungi), substrates=list(substrates), environments=list(environments), registry=REGISTRY_INDEX
    )


def _case_directory(root: Path, case: tuple[str, str, str]) -> Path:
    return root / "__".join(case)


def _trajectory_bytes(root: Path, case: tuple[str, str, str]) -> dict[str, bytes]:
    directory = _case_directory(root, case) / "trajectories"
    files = {path.name: path.read_bytes() for path in sorted(directory.glob("*.csv"))}
    assert files, directory
    return files


def _sampled_values(screen: RegistryScreenResult) -> dict[tuple[str, str, str], list[dict[str, dict[str, Any]]]]:
    return {
        (case.fungus_id, case.substrate_id, case.environment_id): [
            {role: dict(value) for role, value in sample.parameters.items()} for sample in case.samples
        ]
        for case in screen.case_results
    }


def _esterase_dataset(directory: Path, *, without_kinetics_at: str | None = None) -> Path:
    """The esterase fixture at three conditions, kcat a range at each (sampled), optionally one condition without rows."""

    shutil.copytree(ESTERASE, directory)
    (directory / "conditions.csv").write_text(
        "condition_id,temperature,temperature_units,ph,notes\n"
        + "".join(
            f"{condition},{condition[1:3]},degC,7.5,Illustrative condition of the partial-run test\n"
            for condition in ESTERASE_CONDITIONS
        ),
        encoding="utf-8",
    )
    lines = ["strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates"]
    for index, condition in enumerate(ESTERASE_CONDITIONS):
        if condition == without_kinetics_at:
            continue
        case = f"strain_e1,carboxylesterase,p_nitrophenyl_butyrate,{condition}"
        lines.extend(
            [
                f"{case},km,{120 + 30 * index},,,µM,estimate,,\"{ESTERASE_SOURCE}\",,",
                f"{case},kcat,,{10 + 10 * index},{40 + 10 * index},1/min,estimate,,\"{ESTERASE_SOURCE}\",,",
                f"{case},substrate_initial_concentration,200,,,µM,estimate,,\"{ESTERASE_SOURCE}\",,",
                f"{case},enzyme_concentration,0.05,,,µM,estimate,,\"{ESTERASE_SOURCE}\",,",
            ]
        )
    (directory / "kinetics.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory


# ---------------------------------------------------------------------------
# The default refuses, as before


def test_refuse_is_the_default_and_report_refuses_identically_when_nothing_is_runnable(tmp_path: Path) -> None:
    mixed = _registry_study(RUNNABLE_ENVIRONMENT, BLOCKED_ENVIRONMENT)
    messages = []
    with pytest.raises(VirtualExperimentError) as error:
        mixed.simulate(mode="exploratory", n_samples=2, seed=1, output_dir=tmp_path / "default")
    messages.append(str(error.value))
    with pytest.raises(VirtualExperimentError) as error:
        mixed.simulate(mode="exploratory", n_samples=2, seed=1, output_dir=tmp_path / "refuse", blocked="refuse")
    messages.append(str(error.value))
    assert not (tmp_path / "default").exists() and not (tmp_path / "refuse").exists()
    assert messages[0] == messages[1]
    assert messages[0].startswith("Exploratory simulation can simulate only modelable or exploratory cases.")
    assert f"{ENZYME_SOURCE} + {CELLOBIOSE} + {BLOCKED_ENVIRONMENT}: underparameterized" in messages[0]
    assert RUNNABLE_ENVIRONMENT + ":" not in messages[0]

    # No runnable case: "report" refuses exactly as "refuse" does, and writes nothing.
    blocked_only = _registry_study(BLOCKED_ENVIRONMENT, "gelain_2020_cellulose_batch_10gl")
    refusals = []
    for policy in ("refuse", "report"):
        with pytest.raises(VirtualExperimentError) as error:
            blocked_only.simulate(mode="exploratory", n_samples=2, seed=1, output_dir=tmp_path / policy, blocked=policy)
        refusals.append(str(error.value))
        assert not (tmp_path / policy).exists()
    assert refusals[0] == refusals[1]


def test_an_unknown_blocked_policy_is_refused(tmp_path: Path) -> None:
    study = _registry_study(RUNNABLE_ENVIRONMENT)

    with pytest.raises(VirtualExperimentError, match="blocked must be one of: refuse, report"):
        study.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "x", blocked="skip")  # type: ignore[arg-type]
    assert not (tmp_path / "x").exists()


# ---------------------------------------------------------------------------
# A partial run on the shipped registry


def test_report_simulates_only_the_runnable_case_and_lists_the_blocked_one(tmp_path: Path) -> None:
    study = _registry_study(RUNNABLE_ENVIRONMENT, BLOCKED_ENVIRONMENT)
    reports = study.preflight(mode="exploratory")
    allowed = {
        (report.fungus_id, report.substrate_id, report.environment_id)
        for report in reports
        if preflight_policy(report)["simulation_allowed_for_mode"]
    }
    assert allowed == {(ENZYME_SOURCE, CELLOBIOSE, RUNNABLE_ENVIRONMENT)}

    with pytest.raises(VirtualExperimentError):  # the same request without the opt-in is refused
        study.simulate(mode="exploratory", n_samples=3, seed=11, output_dir=tmp_path / "refused", quicklook=False)
    result = study.simulate(
        mode="exploratory", n_samples=3, seed=11, output_dir=tmp_path / "partial", quicklook=False, blocked="report"
    )
    root = Path(result.output_directory)
    (case,) = result.screen_result.case_results
    assert (case.fungus_id, case.substrate_id, case.environment_id) in allowed
    assert case.case_index == 0
    assert len(case.samples) == 3
    assert result.partial_run
    (blocked_report,) = result.blocked_reports.values()
    assert list(result.blocked_reports) == [1]
    assert blocked_report.status == "underparameterized"
    assert blocked_report.suggested_experiments

    # The runnable case's trajectories are byte-identical to a run of that case alone.
    alone = _registry_study(RUNNABLE_ENVIRONMENT).simulate(
        mode="exploratory", n_samples=3, seed=11, output_dir=tmp_path / "alone", quicklook=False
    )
    runnable_case = (ENZYME_SOURCE, CELLOBIOSE, RUNNABLE_ENVIRONMENT)
    assert _trajectory_bytes(root, runnable_case) == _trajectory_bytes(Path(alone.output_directory), runnable_case)
    assert _sampled_values(result.screen_result) == _sampled_values(alone.screen_result)
    assert not alone.partial_run

    # case_summary: one row per requested case, in grid order, the blocked one marked not_simulated with the reason.
    summary = _csv_rows(root / "case_summary.csv")
    assert [(row["case_id"], row["environment_id"], row["case_status"]) for row in summary] == [
        ("case_0000", RUNNABLE_ENVIRONMENT, CASE_STATUS_SIMULATED),
        ("case_0001", BLOCKED_ENVIRONMENT, CASE_STATUS_NOT_SIMULATED),
    ]
    simulated, blocked = summary
    assert (simulated["simulated"], simulated["sample_count"], simulated["not_simulated_reason"]) == ("true", "3", "")
    assert (blocked["simulated"], blocked["sample_count"], blocked["sample_failure_count"]) == ("false", "0", "0")
    assert blocked["modelability_status"] == "underparameterized"
    assert blocked["not_simulated_reason"] == not_simulated_reason(blocked_report)
    assert "blocked_by_preflight" in blocked["not_simulated_reason"]
    assert "missing_inputs" in blocked["not_simulated_reason"]
    assert {row["output_schema_version"] for row in summary} == {OUTPUT_SCHEMA_VERSION}

    # The preflight tables carry the blocked case's status, missing items and measurement requests.
    preflight = {row["case_id"]: row for row in _csv_rows(root / "modelability_preflight.csv")}
    assert preflight["case_0001"]["simulation_allowed_for_mode"] == "false"
    assert preflight["case_0001"]["blocking_reason"] == "missing_inputs"
    assert preflight["case_0001"]["environment_effect_status"] == "preflight_only"
    assert preflight["case_0000"]["simulation_allowed_for_mode"] == "true"
    missing = [row for row in _csv_rows(root / "missing_parameters.csv") if row["case_id"] == "case_0001"]
    assert {row["parameter_symbol"] for row in missing} == {item.item_id for item in blocked_report.missing}
    suggestions = [row for row in _csv_rows(root / "suggested_experiments.csv") if row["case_id"] == "case_0001"]
    assert set(blocked_report.suggested_experiments) <= {row["suggested_experiment"] for row in suggestions}
    items = [row for row in _csv_rows(root / "modelability_items.csv") if row["case_id"] == "case_0001"]
    assert {row["item_id"] for row in items if row["item_status"] == "missing"} == {
        item.item_id for item in blocked_report.missing
    }
    limitations = [row for row in _csv_rows(root / "limitations_table.csv") if row["case_id"] == "case_0001"]
    assert any(
        row["category"] == "not_simulated" and row["severity"] == "blocking" and "blocked_by_preflight" in row["limitation"]
        for row in limitations
    )

    # No sample of the blocked case anywhere; its environment is not summarized as simulated.
    for table in PER_SAMPLE_TABLES:
        assert {row["case_id"] for row in _csv_rows(root / f"{table}.csv")} == {"case_0000"}, table
    assert {row["environment_id"] for row in _csv_rows(root / "environment_summary.csv")} == {RUNNABLE_ENVIRONMENT}
    assert {row["case_id"] for row in _csv_rows(root / "comparison_summary.csv")} == {"case_0000"}

    # Summary and manifest say that the run is partial and list the blocked case.
    for document in (_json(root / "virtual_experiment_summary.json"), _json(root / "output_manifest.json")):
        assert document["partial_run"] is True
        assert document["blocked_policy"] == "report"
        assert (document["requested_case_count"], document["simulated_case_count"]) == (2, 1)
        (entry,) = document["blocked_cases"]  # type: ignore[misc]
        assert entry["case_id"] == "case_0001"
        assert entry["environment_id"] == BLOCKED_ENVIRONMENT
        assert entry["status"] == "underparameterized"
        assert entry["missing"] == [item.item_id for item in blocked_report.missing]
        assert entry["suggested_experiments"] == list(blocked_report.suggested_experiments)
        assert entry["not_simulated_reason"] == blocked["not_simulated_reason"]

    # The report says it too.
    report = result.write_report().read_text(encoding="utf-8")
    assert "**Partial run:** 1 of 2 requested cases were simulated." in report
    assert "Not simulated, because the preflight blocked them: `case_0001`." in report
    assert f"`case_0001`: `{ENZYME_SOURCE}` on `{CELLOBIOSE}` in `{BLOCKED_ENVIRONMENT}`" in report
    assert "**Not simulated:** blocked_by_preflight" in report
    assert "Partial run" not in alone.write_report().read_text(encoding="utf-8")


def test_a_blocked_case_before_a_runnable_one_keeps_both_grid_ids(tmp_path: Path) -> None:
    study = _registry_study(BLOCKED_ENVIRONMENT, RUNNABLE_ENVIRONMENT)
    result = study.simulate(
        mode="exploratory", n_samples=2, seed=5, output_dir=tmp_path / "partial", quicklook=False, blocked="report"
    )

    (case,) = result.screen_result.case_results
    assert (case.environment_id, case.case_index) == (RUNNABLE_ENVIRONMENT, 1)
    summary = _csv_rows(Path(result.output_directory) / "case_summary.csv")
    assert [(row["case_id"], row["environment_id"], row["case_status"]) for row in summary] == [
        ("case_0000", BLOCKED_ENVIRONMENT, CASE_STATUS_NOT_SIMULATED),
        ("case_0001", RUNNABLE_ENVIRONMENT, CASE_STATUS_SIMULATED),
    ]
    rows = _csv_rows(Path(result.output_directory) / "time_series_long.csv")
    assert {(row["case_id"], row["environment_id"]) for row in rows} == {("case_0001", RUNNABLE_ENVIRONMENT)}

    # The case runs with the seed of its grid position: the same samples as selecting it alone from this request.
    runnable = (ENZYME_SOURCE, CELLOBIOSE, RUNNABLE_ENVIRONMENT)
    selected = simulate_screen(
        fungus_ids=study.fungus_ids,
        substrate_ids=study.substrate_ids,
        environment_ids=study.environment_ids,
        registry=study.registry,
        n_samples=2,
        seed=5,
        output_dir=tmp_path / "selected",
        cases=[runnable],
    )
    assert _sampled_values(selected) == _sampled_values(result.screen_result)
    assert _trajectory_bytes(tmp_path / "selected", runnable) == _trajectory_bytes(tmp_path / "partial", runnable)


def test_report_on_a_fully_runnable_request_is_a_full_run(tmp_path: Path) -> None:
    study = _registry_study(RUNNABLE_ENVIRONMENT)
    study.simulate(mode="exploratory", n_samples=2, seed=3, output_dir=tmp_path / "default", quicklook=False)
    report = study.simulate(
        mode="exploratory", n_samples=2, seed=3, output_dir=tmp_path / "report", quicklook=False, blocked="report"
    )

    assert not report.partial_run and report.blocked_cases() == []
    manifest = _json(tmp_path / "report" / "output_manifest.json")
    assert (manifest["partial_run"], manifest["blocked_cases"], manifest["blocked_policy"]) == (False, [], "report")
    assert _json(tmp_path / "default" / "output_manifest.json")["blocked_policy"] == "refuse"
    for table in ("case_summary", "final_metrics", "threshold_times", "summary_metrics", "time_series_long"):
        assert (tmp_path / "default" / f"{table}.csv").read_bytes() == (tmp_path / "report" / f"{table}.csv").read_bytes()
    assert {row["case_status"] for row in _csv_rows(tmp_path / "default" / "case_summary.csv")} == {CASE_STATUS_SIMULATED}


# ---------------------------------------------------------------------------
# Scientific mode


def test_scientific_partial_run_simulates_only_scientifically_modelable_cases(tmp_path: Path) -> None:
    grid = dict(fungi=(ORGANISM, BGL1A_SOURCE), substrates=(CELLULOSE, CELLOBIOSE))
    study = _registry_study(CULTURE, **grid)
    exploratory = {
        (report.fungus_id, report.substrate_id): report.status for report in study.preflight(mode="exploratory")
    }
    scientific = {
        (report.fungus_id, report.substrate_id): report.status for report in study.preflight(mode="scientific")
    }
    # The BGL1A source on cellobiose runs in exploratory mode only (its assay concentrations are exploratory priors).
    assert exploratory[(BGL1A_SOURCE, CELLOBIOSE)] == "modelable"
    assert scientific[(BGL1A_SOURCE, CELLOBIOSE)] == "underparameterized"
    assert scientific[(ORGANISM, CELLULOSE)] == "modelable"

    with pytest.raises(VirtualExperimentError) as error:
        study.simulate(mode="scientific", output_dir=tmp_path / "refused", quicklook=False)
    assert "it does not mean experimentally validated" in str(error.value)

    result = study.simulate(mode="scientific", output_dir=tmp_path / "partial", quicklook=False, blocked="report")
    assert [(case.fungus_id, case.substrate_id, case.case_index) for case in result.screen_result.case_results] == [
        (ORGANISM, CELLULOSE, 0)
    ]
    root = Path(result.output_directory)
    summary = {row["case_id"]: row for row in _csv_rows(root / "case_summary.csv")}
    assert [(case_id, row["case_status"]) for case_id, row in summary.items()] == [
        ("case_0000", CASE_STATUS_SIMULATED),
        ("case_0001", CASE_STATUS_NOT_SIMULATED),
        ("case_0002", CASE_STATUS_NOT_SIMULATED),
        ("case_0003", CASE_STATUS_NOT_SIMULATED),
    ]
    assert summary["case_0003"]["fungus_id"] == BGL1A_SOURCE
    assert "the scientific-mode preflight reports underparameterized" in summary["case_0003"]["not_simulated_reason"]
    manifest = _json(root / "output_manifest.json")
    assert manifest["partial_run"] is True
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    assert "It is not a claim of experimental validation." in str(manifest["scientific_mode_note"])
    assert [entry["case_id"] for entry in manifest["blocked_cases"]] == ["case_0001", "case_0002", "case_0003"]  # type: ignore[index, union-attr]

    alone = _registry_study(CULTURE, fungi=(ORGANISM,), substrates=(CELLULOSE,)).simulate(
        mode="scientific", output_dir=tmp_path / "alone", quicklook=False
    )
    case = (ORGANISM, CELLULOSE, CULTURE)
    assert _trajectory_bytes(root, case) == _trajectory_bytes(Path(alone.output_directory), case)

    # The same request in exploratory mode also runs the BGL1A case.
    explored = study.simulate(
        mode="exploratory", n_samples=1, seed=2, output_dir=tmp_path / "exploratory", quicklook=False, blocked="report"
    )
    assert {(case.fungus_id, case.substrate_id) for case in explored.screen_result.case_results} == {
        (ORGANISM, CELLULOSE),
        (BGL1A_SOURCE, CELLOBIOSE),
    }


# ---------------------------------------------------------------------------
# Seeds: a case's samples do not depend on which cases of its request run


def test_case_samples_are_the_same_in_a_full_a_partial_and_a_one_case_selection(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi=ESTERASE_STRAIN,
        substrates=ESTERASE_SUBSTRATE,
        environments=list(ESTERASE_CONDITIONS),
        user_data=_esterase_dataset(tmp_path / "dataset"),
        registry=REGISTRY_INDEX,
    )
    grid = list(product(study.fungus_ids, study.substrate_ids, study.environment_ids))

    def screen(name: str, cases: list[tuple[str, str, str]] | None) -> RegistryScreenResult:
        return simulate_screen(
            fungus_ids=study.fungus_ids,
            substrate_ids=study.substrate_ids,
            environment_ids=study.environment_ids,
            registry=study.registry,
            n_samples=3,
            seed=2026,
            output_dir=tmp_path / name,
            cases=cases,
        )

    full = screen("full", None)
    every = screen("every", grid)
    partial = screen("partial", [grid[0], grid[2]])
    alone = screen("alone", [grid[2]])
    reordered = screen("reordered", [grid[2], grid[0]])

    assert [case.case_index for case in full.case_results] == [0, 1, 2]
    assert [case.case_index for case in partial.case_results] == [0, 2]
    assert [case.case_index for case in alone.case_results] == [2]
    # cases are simulated in the order given: nothing is reordered.
    assert [case.case_index for case in reordered.case_results] == [2, 0]
    samples = _sampled_values(full)
    assert _sampled_values(every) == samples
    for result in (partial, alone, reordered):
        for case, values in _sampled_values(result).items():
            assert values == samples[case]
    for name, cases in (("partial", (grid[0], grid[2])), ("alone", (grid[2],)), ("reordered", (grid[2], grid[0]))):
        for case in cases:
            assert _trajectory_bytes(tmp_path / name, case) == _trajectory_bytes(tmp_path / "full", case)

    # The check is not vacuous: kcat is sampled, differs between samples and between cases.
    kcat = {case: [sample["kcat"]["value"] for sample in values] for case, values in samples.items()}
    assert all(len(set(values)) == 3 for values in kcat.values())
    assert kcat[grid[0]] != kcat[grid[2]]

    # A partial virtual experiment over the same request, its middle condition without kinetics, gives the same
    # samples to the two conditions that run.
    gapped = virtual_experiment(
        fungi=ESTERASE_STRAIN,
        substrates=ESTERASE_SUBSTRATE,
        environments=list(ESTERASE_CONDITIONS),
        user_data=_esterase_dataset(tmp_path / "gapped_dataset", without_kinetics_at=ESTERASE_CONDITIONS[1]),
        registry=REGISTRY_INDEX,
    )
    assert gapped.fungus_ids == study.fungus_ids and gapped.environment_ids == study.environment_ids
    result = gapped.simulate(
        mode="exploratory", n_samples=3, seed=2026, output_dir=tmp_path / "gapped", quicklook=False, blocked="report"
    )
    assert [case.case_index for case in result.screen_result.case_results] == [0, 2]
    assert list(result.blocked_reports) == [1]
    for case, values in _sampled_values(result.screen_result).items():
        assert values == samples[case]
        assert _trajectory_bytes(tmp_path / "gapped", case) == _trajectory_bytes(tmp_path / "full", case)
    (entry,) = result.blocked_cases()
    assert entry["case_id"] == "case_0001"
    assert entry["environment_id"] == grid[1][2]
    assert len(entry["suggested_experiments"]) == 4
    assert entry["suggested_experiments"][0].startswith(
        "Measure km of carboxylesterase from Esterase source strain E1 on p-nitrophenyl butyrate at 37 degC, pH 7.5"
    )
    summary = _csv_rows(tmp_path / "gapped" / "case_summary.csv")
    assert [(row["case_id"], row["case_status"]) for row in summary] == [
        ("case_0000", CASE_STATUS_SIMULATED),
        ("case_0001", CASE_STATUS_NOT_SIMULATED),
        ("case_0002", CASE_STATUS_SIMULATED),
    ]


def test_simulate_screen_refuses_cases_outside_the_grid_repeated_or_empty(tmp_path: Path) -> None:
    study = _registry_study(RUNNABLE_ENVIRONMENT)
    arguments = dict(
        fungus_ids=study.fungus_ids,
        substrate_ids=study.substrate_ids,
        environment_ids=study.environment_ids,
        registry=study.registry,
        n_samples=1,
        seed=1,
        output_dir=tmp_path / "screen",
    )
    case = (ENZYME_SOURCE, CELLOBIOSE, RUNNABLE_ENVIRONMENT)
    for cases, message in (
        ([(ENZYME_SOURCE, CELLOBIOSE, BLOCKED_ENVIRONMENT)], "is not a \\(fungus_id, substrate_id, environment_id\\)"),
        ([case, case], "more than once"),
        ([], "at least one case"),
    ):
        with pytest.raises(RegistryScreenSimulationError, match=message):
            simulate_screen(**arguments, cases=cases)  # type: ignore[arg-type]
    with pytest.raises(RegistryScreenSimulationError, match="repeat a combination"):
        simulate_screen(**{**arguments, "environment_ids": (RUNNABLE_ENVIRONMENT, RUNNABLE_ENVIRONMENT)}, cases=[case])  # type: ignore[arg-type]
    assert not (tmp_path / "screen").exists()


def test_tables_refuse_to_report_a_runnable_or_simulated_case_as_blocked(tmp_path: Path) -> None:
    study = _registry_study(RUNNABLE_ENVIRONMENT, BLOCKED_ENVIRONMENT)
    result = study.simulate(
        mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "partial", quicklook=False, blocked="report"
    )
    runnable_report, blocked_report = result.preflight_reports

    with pytest.raises(ValueError, match="passes the exploratory-mode preflight"):
        write_standard_tables(
            screen_result=result.screen_result,
            registry=study.registry,
            preflight_reports=result.preflight_reports,
            output_dir=tmp_path / "runnable_as_blocked",
            blocked_reports={1: runnable_report},
        )
    with pytest.raises(ValueError, match="was simulated"):
        write_standard_tables(
            screen_result=result.screen_result,
            registry=study.registry,
            preflight_reports=result.preflight_reports,
            output_dir=tmp_path / "collision",
            blocked_reports={0: blocked_report},
        )


def test_case_summary_schema_documents_the_partial_run_columns() -> None:
    columns = {column["name"]: column for column in OUTPUT_TABLE_SCHEMAS["case_summary"]["columns"]}

    assert OUTPUT_SCHEMA_VERSION == "2.2.1"
    assert columns["case_status"]["allowed_values"] == f"{CASE_STATUS_SIMULATED}; {CASE_STATUS_NOT_SIMULATED}"
    assert columns["case_status"]["required"] is True
    assert columns["not_simulated_reason"]["required"] is False
