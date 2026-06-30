from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from fungal_model import EnvironmentGrid, VirtualExperiment
from fungal_model.api import DegradationScreenResult, VirtualExperimentError
from fungal_model.api.output_schema import OUTPUT_SCHEMA_VERSION


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
        "modelability_items.csv",
        "case_summary.csv",
        "time_series_long.csv",
        "final_states.csv",
        "final_metrics.csv",
        "threshold_times.csv",
        "sampled_parameters.csv",
        "assumption_summary.csv",
        "mechanism_summary.csv",
        "summary_metrics.csv",
        "environment_summary.csv",
        "comparison_summary.csv",
        "uncertainty_summary.csv",
        "trajectory_quantiles.csv",
        "provenance_table.csv",
        "limitations_table.csv",
        "missing_parameters.csv",
        "suggested_experiments.csv",
        "virtual_experiment_output_data_dictionary.csv",
        "virtual_experiment_output_schema.json",
        "virtual_experiment_summary.json",
        "output_manifest.json",
    )
    for filename in required_files:
        assert (output_dir / filename).exists(), filename

    assert (output_dir / "figures" / "substrate_remaining_vs_time.png").exists()
    assert (output_dir / "figures" / "product_release_vs_time.png").exists()
    assert (output_dir / "figures" / "degradation_fraction_vs_time.png").exists()
    assert (output_dir / "figures" / "degradation_rate_vs_time.png").exists()
    assert (output_dir / "figures" / "trajectory_quantile_bands.png").exists()

    time_rows = _csv_rows(output_dir / "time_series_long.csv")
    preflight_rows = _csv_rows(output_dir / "modelability_preflight.csv")
    final_metric_rows = _csv_rows(output_dir / "final_metrics.csv")
    threshold_rows = _csv_rows(output_dir / "threshold_times.csv")
    sampled_rows = _csv_rows(output_dir / "sampled_parameters.csv")
    modelability_rows = _csv_rows(output_dir / "modelability_items.csv")
    assumption_rows = _csv_rows(output_dir / "assumption_summary.csv")
    mechanism_rows = _csv_rows(output_dir / "mechanism_summary.csv")
    summary_rows = _csv_rows(output_dir / "summary_metrics.csv")
    comparison_rows = _csv_rows(output_dir / "comparison_summary.csv")
    uncertainty_rows = _csv_rows(output_dir / "uncertainty_summary.csv")
    trajectory_quantile_rows = _csv_rows(output_dir / "trajectory_quantiles.csv")
    provenance_rows = _csv_rows(output_dir / "provenance_table.csv")
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")
    missing_rows = _csv_rows(output_dir / "missing_parameters.csv")
    suggestion_rows = _csv_rows(output_dir / "suggested_experiments.csv")
    dictionary_rows = _csv_rows(output_dir / "virtual_experiment_output_data_dictionary.csv")
    output_manifest = _json_mapping(output_dir / "output_manifest.json")
    output_schema = _json_mapping(output_dir / "virtual_experiment_output_schema.json")

    assert output_manifest["output_schema_version"] == OUTPUT_SCHEMA_VERSION == "1.4.0"
    assert output_schema["schema_version"] == OUTPUT_SCHEMA_VERSION
    assert "figures/degradation_rate_vs_time.png" in output_manifest["files"]
    assert "figures/trajectory_quantile_bands.png" in output_manifest["files"]

    assert {"case_id", "sample_id", "fungus_id", "substrate_id", "environment_id", "time", "state", "value"}.issubset(
        time_rows[0]
    )
    assert any(row["state"] == "cellobiose_concentration" and row["state_role"] == "substrate" for row in time_rows)
    assert any(row["state"] == "beta_D_glucose_concentration" and row["state_role"] == "product" for row in time_rows)
    assert any(row["state"] == "substrate_degraded_fraction" for row in time_rows)
    assert any(row["state"] == "product_formed" for row in time_rows)
    assert any(row["state"] == "degradation_rate" for row in time_rows)
    assert preflight_rows[0]["assessment_mode"] == "exploratory"
    assert preflight_rows[0]["simulation_allowed_for_mode"] == "true"
    assert preflight_rows[0]["blocking_reason"] == "not_blocked"
    assert preflight_rows[0]["recommended_next_action"] == "simulate_exploratory"

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
    assert result.comparison_summary() == comparison_rows
    assert result.uncertainty_summary() == uncertainty_rows
    assert result.trajectory_quantiles() == trajectory_quantile_rows
    assert any(
        row["source_table"] == "final_metrics"
        and row["source_metric"] == "final_product_concentration"
        and row["comparable_group_id"] == "final_metrics|final_product_concentration|millimolar"
        for row in comparison_rows
    )
    assert any(
        row["source_table"] == "threshold_times"
        and row["source_metric"] == "time_to_10_percent_substrate_degradation"
        and row["threshold_fraction"] == "0.1"
        for row in comparison_rows
    )
    assert {"comparison_allowed", "ranking_allowed", "ranking_blocking_reason", "recommended_next_action"} <= set(
        comparison_rows[0]
    )
    assert {row["recommended_next_action"] for row in comparison_rows} == {
        "side_by_side_comparison_and_guarded_ranking_allowed"
    }

    enzyme_prior_rows = [
        row
        for row in sampled_rows
        if row["symbol"] == "enzyme_concentration_beta_glucosidase"
    ]
    assert enzyme_prior_rows
    assert all(row["source_value_kind"] == "distribution" for row in enzyme_prior_rows)
    assert all(row["parameter_source_class"] == "user_supplied_exploratory_prior" for row in enzyme_prior_rows)
    assert all(row["exploratory_prior"] == "true" for row in enzyme_prior_rows)
    assert all(row["source"] == "user-supplied exploratory range" for row in enzyme_prior_rows)
    assert all(row["range_scope"] == "user_supplied_case_prior" for row in enzyme_prior_rows)
    assert all(
        row["range_interpretation"] == "user_supplied_exploratory_prior_not_literature_curated"
        for row in enzyme_prior_rows
    )
    assert all(row["allowed_use"] == "exploratory_simulation_only_not_literature_curated" for row in enzyme_prior_rows)
    enzyme_uncertainty_rows = [
        row
        for row in uncertainty_rows
        if row["summary_type"] == "sampled_parameter_distribution"
        and row["target_id"] == "enzyme_concentration_beta_glucosidase"
    ]
    assert enzyme_uncertainty_rows
    assert {row["source_table"] for row in enzyme_uncertainty_rows} == {"sampled_parameters"}
    assert {row["source_value_kind"] for row in enzyme_uncertainty_rows} == {"distribution"}
    assert {row["uncertainty_band_status"] for row in enzyme_uncertainty_rows} == {
        "computed_from_explicit_parameter_range"
    }
    assert all("not calibration" in row["interpretation_guardrail"] for row in enzyme_uncertainty_rows)
    metric_uncertainty_rows = [
        row
        for row in uncertainty_rows
        if row["summary_type"] == "output_metric_sample_distribution"
        and row["target_id"] == "final_product_concentration"
    ]
    assert metric_uncertainty_rows
    assert {row["source_table"] for row in metric_uncertainty_rows} == {"summary_metrics"}
    assert {row["allowed_use"] for row in metric_uncertainty_rows} == {"exploratory_output_summary_not_validation"}
    assert all(float(row["p95"]) >= float(row["p05"]) for row in metric_uncertainty_rows)
    substrate_trajectory_rows = [
        row
        for row in trajectory_quantile_rows
        if row["state"] == "cellobiose_concentration"
        and row["state_role"] == "substrate"
        and row["source_table"] == "time_series_long"
        and row["source_metric"] == "value"
    ]
    assert substrate_trajectory_rows
    assert {row["count"] for row in substrate_trajectory_rows} == {"6"}
    assert {row["allowed_use"] for row in substrate_trajectory_rows} == {
        "exploratory_trajectory_summary_not_validation"
    }
    assert {row["trajectory_band_status"] for row in substrate_trajectory_rows} == {
        "computed_from_existing_time_series_rows"
    }
    assert all("not validation data" in row["interpretation_guardrail"] for row in substrate_trajectory_rows)
    assert all(float(row["p95"]) >= float(row["p05"]) for row in substrate_trajectory_rows)
    assert result.modelability_items() == modelability_rows
    assert any(
        row["item_status"] == "known"
        and row["item_type"] == "process_compatibility"
        and row["allowed_use"] == "supports_case_interpretation"
        for row in modelability_rows
    )
    assert any(
        row["item_status"] == "uncertain"
        and row["item_id"] == "enzyme_concentration_beta_glucosidase"
        and row["allowed_use"] == "exploratory_simulation_only"
        for row in modelability_rows
    )
    assert result.assumption_summary() == assumption_rows
    assert result.mechanism_summary() == mechanism_rows
    assert mechanism_rows[0]["mechanism_kind"] == "process_law"
    assert mechanism_rows[0]["mechanism_id"] == "homogeneous_michaelis_menten"
    assert mechanism_rows[0]["mechanism_family"] == "generic homogeneous Michaelis-Menten process"
    assert mechanism_rows[0]["active"] == "true"
    assert mechanism_rows[0]["maturity"] == "software_tested_exploratory_parameterized"
    assert "Km_cellobiose" in mechanism_rows[0]["parameters"]
    assert "whole-fungus physiology" in mechanism_rows[0]["limitations"]
    assert any(
        row["row_type"] == "assumption"
        and row["allowed_use"] == "exploratory_context_not_validation"
        and "mode='exploratory'" in row["message"]
        for row in assumption_rows
    )
    assert any(
        row["row_type"] == "uncertain"
        and row["item_id"] == "enzyme_concentration_beta_glucosidase"
        and row["allowed_use"] == "exploratory_simulation_only"
        for row in assumption_rows
    )
    assert any(
        row["symbol"] == "Km_cellobiose"
        and row["parameter_source_class"] == "selected_exact_value"
        for row in sampled_rows
    )
    assert any(row["metric"] == "final_product_concentration" and row["fungus_id"] == FUNGUS_ID for row in summary_rows)

    assert any(row["record_type"] == "parameter" and row["value_kind"] == "exact" for row in provenance_rows)
    assert any(row["record_type"] == "parameter" and row["value_kind"] == "distribution" for row in provenance_rows)
    assert any("must not be cited as literature-curated" in row["limitation"] for row in limitation_rows)
    assert any("not a whole-fungus" in row["limitation"] for row in limitation_rows)
    assert not missing_rows
    assert not suggestion_rows
    assert any(
        row["table"] == "sampled_parameters" and row["column"] == "allowed_use"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "assumption_summary" and row["column"] == "allowed_use"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "mechanism_summary" and row["column"] == "mechanism_kind"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "comparison_summary" and row["column"] == "ranking_blocking_reason"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "uncertainty_summary" and row["column"] == "interpretation_guardrail"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "uncertainty_summary"
        and row["column"] == "output_schema_version"
        and row["output_schema_version"] == OUTPUT_SCHEMA_VERSION
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "trajectory_quantiles" and row["column"] == "interpretation_guardrail"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "trajectory_quantiles"
        and row["column"] == "output_schema_version"
        and row["output_schema_version"] == OUTPUT_SCHEMA_VERSION
        for row in dictionary_rows
    )
    output_schema_tables = output_schema["tables"]
    assert isinstance(output_schema_tables, dict)
    assert "trajectory_quantiles" in output_schema_tables
    assert any(
        row["table"] == "modelability_items" and row["column"] == "allowed_use"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "missing_parameters" and row["column"] == "expected_units"
        for row in dictionary_rows
    )


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


def test_virtual_experiment_scientific_simulation_rejects_underparameterized_reaction_618(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked")


def test_virtual_experiment_writes_preflight_report_for_blocked_scientific_case(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    tables = study.write_preflight_report(
        mode="scientific",
        output_dir=tmp_path / "scientific_preflight_report",
    )

    output_dir = tmp_path / "scientific_preflight_report"
    assert set(tables.paths) == {
        "modelability_preflight",
        "modelability_items",
        "output_data_dictionary",
        "output_schema",
    }
    assert (output_dir / "modelability_preflight.csv").exists()
    assert (output_dir / "modelability_items.csv").exists()

    preflight_rows = _csv_rows(output_dir / "modelability_preflight.csv")
    item_rows = _csv_rows(output_dir / "modelability_items.csv")
    assert preflight_rows[0]["status"] == "underparameterized"
    assert preflight_rows[0]["assessment_mode"] == "scientific"
    assert preflight_rows[0]["simulation_allowed_for_mode"] == "false"
    assert preflight_rows[0]["blocking_reason"] == "missing_inputs"
    assert preflight_rows[0]["recommended_next_action"] == "measure_or_curate_missing_inputs"
    assert preflight_rows[0]["environment_effect_status"] == "preflight_only"
    assert any(
        row["item_status"] == "missing"
        and row["item_id"] == "enzyme_concentration_beta_glucosidase"
        and row["allowed_use"] == "blocks_scientific_simulation"
        for row in item_rows
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json_mapping(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    assert isinstance(data, dict)
    return data
