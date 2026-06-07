from __future__ import annotations

import csv
from pathlib import Path

import pytest

from fungal_model import EnvironmentGrid, VirtualExperiment
from fungal_model.api import DegradationScreenResult, VirtualExperimentError


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "sabiork_beta_glucosidase_source"
SUBSTRATE_ID = "cellobiose"
ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"


def test_virtual_experiment_reaction_618_writes_standard_tables_and_quicklook(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_registry(
        fungi=[FUNGUS_ID],
        substrates=[SUBSTRATE_ID],
        environments=[ENVIRONMENT_ID],
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(
        mode="exploratory",
        n_samples=6,
        seed=11,
        output_dir=tmp_path / "reaction_618_virtual_experiment",
    )

    output_dir = Path(result.output_directory)
    assert isinstance(result, DegradationScreenResult)
    assert result.preflight_reports[0].status == "exploratory"
    assert result.screen_result.case_results[0].modelability_report.status == "exploratory"
    assert len(result.screen_result.case_results[0].samples) == 6

    required_files = (
        "modelability_preflight.csv",
        "case_summary.csv",
        "time_series_long.csv",
        "final_states.csv",
        "final_metrics.csv",
        "threshold_times.csv",
        "sampled_parameters.csv",
        "summary_metrics.csv",
        "environment_summary.csv",
        "provenance_table.csv",
        "limitations_table.csv",
        "virtual_experiment_summary.json",
    )
    for filename in required_files:
        assert (output_dir / filename).exists(), filename

    assert (output_dir / "figures" / "substrate_remaining_vs_time.png").exists()
    assert (output_dir / "figures" / "product_release_vs_time.png").exists()
    assert (output_dir / "figures" / "degradation_fraction_vs_time.png").exists()

    time_rows = _csv_rows(output_dir / "time_series_long.csv")
    final_metric_rows = _csv_rows(output_dir / "final_metrics.csv")
    threshold_rows = _csv_rows(output_dir / "threshold_times.csv")
    sampled_rows = _csv_rows(output_dir / "sampled_parameters.csv")
    summary_rows = _csv_rows(output_dir / "summary_metrics.csv")
    provenance_rows = _csv_rows(output_dir / "provenance_table.csv")
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")

    assert {"case_id", "sample_id", "fungus_id", "substrate_id", "environment_id", "time", "state", "value"}.issubset(
        time_rows[0]
    )
    assert any(row["state"] == "cellobiose_concentration" and row["state_role"] == "substrate" for row in time_rows)
    assert any(row["state"] == "beta_D_glucose_concentration" and row["state_role"] == "product" for row in time_rows)
    assert any(row["state"] == "substrate_degraded_fraction" for row in time_rows)
    assert any(row["state"] == "product_formed" for row in time_rows)
    assert any(row["state"] == "degradation_rate" for row in time_rows)

    computed_metrics = {
        row["metric"]
        for row in final_metric_rows
        if row["status"] == "computed"
    }
    assert {
        "final_substrate_remaining",
        "final_substrate_degraded_fraction",
        "final_product_concentration",
        "maximum_product_release_rate",
        "maximum_substrate_depletion_rate",
    }.issubset(computed_metrics)

    assert {row["threshold_fraction"] for row in threshold_rows} == {"0.1", "0.5", "0.9"}
    assert any(row["metric"] == "time_to_10_percent_substrate_degradation" for row in threshold_rows)
    assert any(row["metric"] == "final_product_concentration" and row["count"] == "6" for row in summary_rows)

    enzyme_prior_rows = [
        row
        for row in sampled_rows
        if row["symbol"] == "enzyme_concentration_beta_glucosidase"
    ]
    assert enzyme_prior_rows
    assert all(row["source_value_kind"] == "distribution" for row in enzyme_prior_rows)
    assert all(row["exploratory_prior"] == "true" for row in enzyme_prior_rows)
    assert all(row["source"] == "user-supplied exploratory range" for row in enzyme_prior_rows)

    assert any(row["record_type"] == "parameter" and row["value_kind"] == "exact" for row in provenance_rows)
    assert any(row["record_type"] == "parameter" and row["value_kind"] == "distribution" for row in provenance_rows)
    assert any("must not be cited as literature-curated" in row["limitation"] for row in limitation_rows)
    assert any("not a whole-fungus" in row["limitation"] for row in limitation_rows)


def test_virtual_experiment_accepts_environment_grid_registry_ids(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=EnvironmentGrid.from_registry_ids(ENVIRONMENT_ID),
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(n_samples=1, seed=3, output_dir=tmp_path / "grid_ids", quicklook=False)

    assert Path(result.output_directory, "time_series_long.csv").exists()


def test_environment_grid_numeric_values_generate_runtime_environment_ids() -> None:
    grid = EnvironmentGrid(temperature_C=[30.0], ph=[5.0], oxygen="aerobic")

    assert grid.registry_ids() == ("temp_30C_ph_5p0_aerobic",)


def test_virtual_experiment_scientific_preflight_remains_underparameterized() -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    report = study.preflight(mode="scientific")[0]

    assert report.status == "underparameterized"


def test_virtual_experiment_simulation_supports_exploratory_mode_only(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    with pytest.raises(VirtualExperimentError, match="mode='exploratory'"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked")  # type: ignore[arg-type]


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
