from __future__ import annotations

import csv
from pathlib import Path

from fungal_model.api import EnvironmentGrid, VirtualExperiment


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "sabiork_beta_glucosidase_source"
SUBSTRATE_ID = "cellobiose"


def test_virtual_experiment_expands_environment_grid_and_writes_environment_tables(
    tmp_path: Path,
) -> None:
    grid = EnvironmentGrid(
        temperature_C=[20, 30],
        ph=[5.0, 6.0],
        oxygen=["aerobic"],
    )
    study = VirtualExperiment.from_registry(
        fungi=[FUNGUS_ID],
        substrates=[SUBSTRATE_ID],
        environments=grid,
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(
        mode="exploratory",
        n_samples=2,
        seed=5,
        output_dir=tmp_path / "reaction_618_environment_grid",
        quicklook=False,
    )

    output_dir = Path(result.output_directory)
    assert study.case_count == 4
    assert len(result.screen_result.case_results) == 4
    assert all(len(case.samples) == 2 for case in result.screen_result.case_results)
    assert all(case.modelability_report.status == "exploratory" for case in result.screen_result.case_results)

    required_files = (
        "modelability_preflight.csv",
        "case_summary.csv",
        "time_series_long.csv",
        "final_states.csv",
        "final_metrics.csv",
        "threshold_times.csv",
        "sampled_parameters.csv",
        "assumption_summary.csv",
        "summary_metrics.csv",
        "environment_summary.csv",
        "provenance_table.csv",
        "limitations_table.csv",
        "missing_parameters.csv",
        "suggested_experiments.csv",
        "virtual_experiment_output_data_dictionary.csv",
        "virtual_experiment_output_schema.json",
    )
    for filename in required_files:
        assert (output_dir / filename).exists(), filename

    time_rows = _csv_rows(output_dir / "time_series_long.csv")
    summary_rows = _csv_rows(output_dir / "environment_summary.csv")
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")
    provenance_rows = _csv_rows(output_dir / "provenance_table.csv")

    required_environment_columns = {
        "environment_id",
        "temperature_C",
        "ph",
        "oxygen",
        "environment_source",
        "environment_effect_status",
        "environment_ranking_allowed",
        "environment_response_plot_allowed",
    }
    assert required_environment_columns <= set(time_rows[0])
    assert {row["environment_id"] for row in summary_rows} == set(study.environment_ids)
    assert {row["environment_effect_status"] for row in summary_rows} == {"metadata_only"}
    assert {row["environment_response_model"] for row in summary_rows} == {"none"}
    assert {row["environment_comparison_allowed"] for row in summary_rows} == {"false"}
    assert {row["environment_ranking_allowed"] for row in summary_rows} == {"false"}
    assert {row["environment_response_plot_allowed"] for row in summary_rows} == {"false"}
    assert {row["environment_response_metric_status"] for row in summary_rows} == {"not_applicable_metadata_only"}
    assert all(row["median_final_substrate_degraded_fraction"] == "" for row in summary_rows)
    assert all("cannot be ranked" in row["environment_guardrail"] for row in summary_rows)
    assert all(row["environment_source"] == "runtime_environment_grid" for row in summary_rows)
    assert all(row["n_cases"] == "1" for row in summary_rows)
    assert all(row["n_samples"] == "2" for row in summary_rows)
    assert all(row["n_successful_samples"] == "2" for row in summary_rows)
    assert all(row["n_failed_samples"] == "0" for row in summary_rows)
    assert any(
        "Do not rank or plot these cases as environmental response models" in row["limitation"]
        for row in limitation_rows
    )
    assert any(
        row["record_type"] == "environment"
        and row["environment_source"] == "runtime_environment_grid"
        and row["environment_effect_status"] == "metadata_only"
        for row in provenance_rows
    )


def test_environment_grid_does_not_mutate_registry_environment_file(tmp_path: Path) -> None:
    registry_text_before = (ROOT / "data_registry" / "environments" / "environments.yml").read_text(
        encoding="utf-8"
    )
    grid = EnvironmentGrid(temperature_C=[20], ph=[5.0], oxygen=["aerobic"])
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=grid,
        registry=REGISTRY_INDEX,
    )

    study.simulate(n_samples=1, seed=1, output_dir=tmp_path / "no_registry_mutation", quicklook=False)

    registry_text_after = (ROOT / "data_registry" / "environments" / "environments.yml").read_text(
        encoding="utf-8"
    )
    assert registry_text_after == registry_text_before
    assert "temp_20C_ph_5p0_aerobic" not in registry_text_after


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
