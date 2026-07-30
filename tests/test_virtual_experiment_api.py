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
        "conservation_diagnostics.csv",
        "thermodynamic_diagnostics.csv",
        "solver_diagnostics.csv",
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
    conservation_diagnostic_rows = _csv_rows(output_dir / "conservation_diagnostics.csv")
    thermodynamic_diagnostic_rows = _csv_rows(output_dir / "thermodynamic_diagnostics.csv")
    solver_diagnostic_rows = _csv_rows(output_dir / "solver_diagnostics.csv")
    provenance_rows = _csv_rows(output_dir / "provenance_table.csv")
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")
    missing_rows = _csv_rows(output_dir / "missing_parameters.csv")
    suggestion_rows = _csv_rows(output_dir / "suggested_experiments.csv")
    dictionary_rows = _csv_rows(output_dir / "virtual_experiment_output_data_dictionary.csv")
    output_manifest = _json_mapping(output_dir / "output_manifest.json")
    output_schema = _json_mapping(output_dir / "virtual_experiment_output_schema.json")

    assert output_manifest["output_schema_version"] == OUTPUT_SCHEMA_VERSION == "1.8.0"
    assert output_schema["schema_version"] == OUTPUT_SCHEMA_VERSION
    assert "conservation_diagnostics.csv" in output_manifest["files"]
    assert "conservation_diagnostics" in output_manifest["tables"]
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

    computed_metrics = {row["metric"] for row in final_metric_rows if row["status"] == "computed"}
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
    assert result.conservation_diagnostics() == conservation_diagnostic_rows
    assert {row["summary_kind"] for row in conservation_diagnostic_rows} == {
        "configured_conservation_diagnostics"
    }
    assert {row["conservation_diagnostics_json_present"] for row in conservation_diagnostic_rows} == {"true"}
    assert {row["conservation_diagnostics_csv_present"] for row in conservation_diagnostic_rows} == {"true"}
    assert result.thermodynamic_diagnostics() == thermodynamic_diagnostic_rows == []
    assert result.solver_diagnostics() == solver_diagnostic_rows
    assert {row["summary_kind"] for row in solver_diagnostic_rows} == {"configured_solver_diagnostics"}
    assert {row["summary_status"] for row in solver_diagnostic_rows} == {"available"}
    assert {row["summary_metadata_available"] for row in solver_diagnostic_rows} == {"true"}
    assert {row["solver_diagnostics_json_present"] for row in solver_diagnostic_rows} == {"true"}
    assert {row["solver_diagnostics_csv_present"] for row in solver_diagnostic_rows} == {"true"}
    assert {row["solver_backend"] for row in solver_diagnostic_rows} == {"scipy.solve_ivp"}
    assert {row["allowed_use"] for row in solver_diagnostic_rows} == {"configured_solver_metadata_inspection_only"}
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

    enzyme_prior_rows = [row for row in sampled_rows if row["symbol"] == "enzyme_concentration_beta_glucosidase"]
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
        row["symbol"] == "Km_cellobiose" and row["parameter_source_class"] == "selected_exact_value"
        for row in sampled_rows
    )
    assert any(row["metric"] == "final_product_concentration" and row["fungus_id"] == FUNGUS_ID for row in summary_rows)

    assert any(row["record_type"] == "parameter" and row["value_kind"] == "exact" for row in provenance_rows)
    assert any(row["record_type"] == "parameter" and row["value_kind"] == "distribution" for row in provenance_rows)
    assert any("must not be cited as literature-curated" in row["limitation"] for row in limitation_rows)
    assert any("not a whole-fungus" in row["limitation"] for row in limitation_rows)
    assert not missing_rows
    assert not suggestion_rows
    assert any(row["table"] == "sampled_parameters" and row["column"] == "allowed_use" for row in dictionary_rows)
    assert any(row["table"] == "assumption_summary" and row["column"] == "allowed_use" for row in dictionary_rows)
    assert any(row["table"] == "mechanism_summary" and row["column"] == "mechanism_kind" for row in dictionary_rows)
    assert any(
        row["table"] == "comparison_summary" and row["column"] == "ranking_blocking_reason" for row in dictionary_rows
    )
    assert any(
        row["table"] == "uncertainty_summary" and row["column"] == "interpretation_guardrail" for row in dictionary_rows
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
    assert any(
        row["table"] == "conservation_diagnostics" and row["column"] == "interpretation_guardrail"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "conservation_diagnostics"
        and row["column"] == "output_schema_version"
        and row["output_schema_version"] == OUTPUT_SCHEMA_VERSION
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "thermodynamic_diagnostics" and row["column"] == "interpretation_guardrail"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "thermodynamic_diagnostics"
        and row["column"] == "output_schema_version"
        and row["output_schema_version"] == OUTPUT_SCHEMA_VERSION
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "thermodynamic_diagnostics" and row["column"] == "summary_has_dynamic_reaction_quotient"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "thermodynamic_diagnostics" and row["column"] == "recorded_blocked_count"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "solver_diagnostics" and row["column"] == "interpretation_guardrail"
        for row in dictionary_rows
    )
    assert any(
        row["table"] == "solver_diagnostics"
        and row["column"] == "output_schema_version"
        and row["output_schema_version"] == OUTPUT_SCHEMA_VERSION
        for row in dictionary_rows
    )
    output_schema_tables = output_schema["tables"]
    assert isinstance(output_schema_tables, dict)
    assert "trajectory_quantiles" in output_schema_tables
    assert "conservation_diagnostics" in output_schema_tables
    assert "thermodynamic_diagnostics" in output_schema_tables
    assert "solver_diagnostics" in output_schema_tables
    assert any(row["table"] == "modelability_items" and row["column"] == "allowed_use" for row in dictionary_rows)
    assert any(row["table"] == "missing_parameters" and row["column"] == "expected_units" for row in dictionary_rows)


def test_virtual_experiment_accepts_environment_grid_registry_ids(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=EnvironmentGrid.from_registry_ids(ENVIRONMENT_ID),
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(n_samples=1, seed=3, output_dir=tmp_path / "grid_ids", quicklook=False)

    assert Path(result.output_directory, "time_series_long.csv").exists()


def test_virtual_experiment_conservation_diagnostics_copy_existing_sample_artifacts_only(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=3,
        output_dir=tmp_path / "conservation_bridge",
        quicklook=False,
    )
    sample_dir = Path(result.screen_result.case_results[0].samples[0].output_directory)
    configured_summary = _json_mapping(sample_dir / "conservation_diagnostics.json")
    configured_rows = _csv_rows(sample_dir / "conservation_diagnostics.csv")

    rows = result.conservation_diagnostics()
    assert len(rows) == len(configured_rows) == 1
    row = rows[0]
    configured_row = configured_rows[0]
    assert row["artifact_source_directory"] == str(sample_dir)
    assert row["conservation_diagnostics_json_present"] == "true"
    assert row["conservation_diagnostics_csv_present"] == "true"
    assert row["summary_kind"] == configured_summary["kind"] == "configured_conservation_diagnostics"
    assert row["summary_validator_count"] == str(configured_summary["validator_count"])
    assert row["summary_evaluated_count"] == str(configured_summary["evaluated_count"])
    assert row["summary_status_counts"] == json.dumps(configured_summary["status_counts"], sort_keys=True)
    assert row["summary_allowed_use"] == configured_summary["allowed_use"]
    assert row["unsupported_scope"] == configured_summary["unsupported_scope"]
    copied_fields = (
        "validator_id",
        "status",
        "reason",
        "closed_system",
        "weighted_states",
        "initial_conserved_total",
        "final_conserved_total",
        "final_drift",
        "max_absolute_drift",
        "relative_max_absolute_drift",
        "units",
        "allowed_use",
    )
    assert {field: row[field] for field in copied_fields} == {
        field: configured_row[field] for field in copied_fields
    }
    assert "Rows are copied from existing configured conservation_diagnostics artifacts only" in row[
        "interpretation_guardrail"
    ]
    assert "pass/fail thresholds" in row["interpretation_guardrail"]
    assert "thermodynamics" in row["interpretation_guardrail"]
    assert "biology" in row["interpretation_guardrail"]

    report_path = result.write_report(include_html=True, include_index=True)
    report = report_path.read_text(encoding="utf-8")
    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")
    assert "Standard virtual-experiment rows from `conservation_diagnostics.csv`" in report
    assert "copied from existing configured conservation-diagnostics artifacts only" in report
    assert "do not infer conserved quantities" in report
    assert "pass/fail thresholds" in report
    assert "validation evidence" in report
    assert "chemistry, thermodynamics, calibration, empirical comparison, or biology" in report
    assert "conservation_diagnostics.csv" in html
    assert "conservation_diagnostics.csv" in index
    assert "conservation_diagnostics.json" not in index


def test_virtual_experiment_conservation_diagnostics_header_only_without_sample_artifacts(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=3,
        output_dir=tmp_path / "conservation_bridge_no_artifacts",
        quicklook=False,
    )
    sample_dir = Path(result.screen_result.case_results[0].samples[0].output_directory)
    (sample_dir / "conservation_diagnostics.json").unlink()
    (sample_dir / "conservation_diagnostics.csv").unlink()

    result.write_tables()

    assert result.conservation_diagnostics() == []
    with (Path(result.output_directory) / "conservation_diagnostics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        reader = csv.DictReader(handle)
        assert list(reader) == []
        fieldnames = set(reader.fieldnames or ())
    assert {
        "output_schema_version",
        "case_id",
        "sample_id",
        "artifact_source_directory",
        "conservation_diagnostics_json_present",
        "conservation_diagnostics_csv_present",
        "summary_evaluated_count",
        "validator_id",
        "max_absolute_drift",
        "interpretation_guardrail",
    }.issubset(fieldnames)


def test_virtual_experiment_thermodynamic_diagnostics_copy_existing_sample_artifacts_only(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=3,
        output_dir=tmp_path / "thermodynamic_bridge",
        quicklook=False,
    )
    sample_dir = Path(result.screen_result.case_results[0].samples[0].output_directory)
    summary = {
        "kind": "configured_thermodynamic_summary",
        "count": 1,
        "status_counts": {"passed": 1},
        "severity_counts": {"info": 1},
        "has_reaction_quotient_gibbs": True,
        "has_dynamic_reaction_quotient": True,
        "has_redox_standard_energy": True,
        "has_electron_balance_binding": True,
        "has_entropy_production_rate": True,
        "has_entropy_budget": True,
        "has_solver_time_enforcement": True,
        "entropy_budget_scope": "Aggregate over explicit configured entropy rows.",
        "entropy_budget_units": "joule / second / kelvin",
        "entropy_budget_total": 0.1,
        "entropy_budget_minimum": 0.1,
        "entropy_budget_negative_count": 0,
        "entropy_budget_evaluated_count": 1,
        "entropy_budget_status": "non_negative",
        "entropy_budget_limitations": "Configured metadata summary only; no inferred thermodynamics.",
        "supported_scope": "Explicit configured metadata only.",
        "unsupported_scope": "No inferred activity model or solver-time thermodynamic enforcement.",
    }
    (sample_dir / "thermodynamic_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        sample_dir / "thermodynamic_summary.csv",
        [
            {
                "name": "reaction_quotient_thermodynamic_feasibility",
                "status": "passed",
                "passed": "true",
                "severity": "info",
                "message": "explicit configured metadata row",
                "residual_value": "-5000.0",
                "residual_units": "joule / mole",
                "delta_gibbs": "-5000.0",
                "delta_gibbs_units": "joule / mole",
                "entropy_production_per_mole": "16.77",
                "entropy_production_rate": "0.1",
                "entropy_production_rate_units": "joule / second / kelvin",
                "gibbs_equation": "delta_g = delta_g_standard + R*T*ln(Q)",
                "entropy_equation": "entropy_production_rate = explicit configured metadata",
                "dynamic_reaction_quotient": "explicit_parameter",
                "activity_model": "caller_supplied_dimensionless_reaction_quotient",
                "solver_time_enforcement": "block_unfavorable_forward_rate",
                "constraint_id": "reaction_618_dynamic",
                "process_id": "reaction_618",
                "reaction_id": "sabiork_reaction_618",
                "electron_balance_check_id": "reaction_618_electron_balance",
                "standard_energy_method": "redox_potential",
                "recorded_evaluation_count": "11",
                "recorded_unfavorable_count": "3",
                "recorded_blocked_count": "3",
                "minimum_delta_gibbs": "-5000.0",
                "maximum_delta_gibbs": "2500.0",
            }
        ],
    )
    _write_csv(
        sample_dir / "derived_quantities.csv",
        [
            {
                "kind": "derived",
                "name": "dynamic_thermodynamics.reaction_618_dynamic.reaction_quotient",
                "index": "0",
                "time": "0.0",
                "time_units": "second",
                "value": "0.25",
                "units": "dimensionless",
            },
            {
                "kind": "derived",
                "name": "dynamic_thermodynamics.reaction_618_dynamic.delta_gibbs",
                "index": "0",
                "time": "0.0",
                "time_units": "second",
                "value": "-5000.0",
                "units": "joule / mole",
            },
            {
                "kind": "derived",
                "name": "dynamic_thermodynamics.reaction_618_dynamic.rate_blocked",
                "index": "0",
                "time": "0.0",
                "time_units": "second",
                "value": "0.0",
                "units": "dimensionless",
            },
            {
                "kind": "derived",
                "name": "dynamic_thermodynamics.reaction_618_dynamic.activity.cellobiose_concentration",
                "index": "0",
                "time": "0.0",
                "time_units": "second",
                "value": "1.0",
                "units": "dimensionless",
            },
        ],
    )

    result.write_tables()

    rows = result.thermodynamic_diagnostics()
    assert len(rows) == 1
    row = rows[0]
    assert row["row_name"] == "reaction_quotient_thermodynamic_feasibility"
    assert row["artifact_source_directory"] == str(sample_dir)
    assert row["thermodynamic_summary_json_present"] == "true"
    assert row["thermodynamic_summary_csv_present"] == "true"
    assert row["summary_status_counts"] == '{"passed": 1}'
    assert row["summary_has_reaction_quotient_gibbs"] == "true"
    assert row["summary_has_dynamic_reaction_quotient"] == "true"
    assert row["summary_has_redox_standard_energy"] == "true"
    assert row["summary_has_electron_balance_binding"] == "true"
    assert row["summary_has_entropy_production_rate"] == "true"
    assert row["summary_has_entropy_budget"] == "true"
    assert row["summary_has_solver_time_enforcement"] == "true"
    assert row["entropy_budget_status"] == "non_negative"
    assert row["entropy_budget_negative_count"] == "0"
    assert row["gibbs_equation"] == "delta_g = delta_g_standard + R*T*ln(Q)"
    assert row["solver_time_enforcement"] == "block_unfavorable_forward_rate"
    assert row["constraint_id"] == "reaction_618_dynamic"
    assert row["process_id"] == "reaction_618"
    assert row["reaction_id"] == "sabiork_reaction_618"
    assert row["electron_balance_check_id"] == "reaction_618_electron_balance"
    assert row["standard_energy_method"] == "redox_potential"
    assert row["recorded_evaluation_count"] == "11"
    assert row["recorded_unfavorable_count"] == "3"
    assert row["recorded_blocked_count"] == "3"
    assert row["minimum_delta_gibbs"] == "-5000.0"
    assert row["maximum_delta_gibbs"] == "2500.0"
    assert row["allowed_use"] == "configured_metadata_inspection_only"
    assert (
        "Rows are copied from existing configured thermodynamic_summary artifacts only"
        in row["interpretation_guardrail"]
    )
    assert "does not independently infer or recompute" in row["interpretation_guardrail"]
    assert "does not revalidate or enforce" in row["interpretation_guardrail"]

    time_rows = result.time_series()
    derived_by_state = {
        candidate["state"]: candidate for candidate in time_rows if candidate["source"] == "simulation_derived_quantity"
    }
    assert (
        derived_by_state["derived_quantity.dynamic_thermodynamics.reaction_618_dynamic.reaction_quotient"]["state_role"]
        == "thermodynamic_reaction_quotient"
    )
    assert (
        derived_by_state["derived_quantity.dynamic_thermodynamics.reaction_618_dynamic.delta_gibbs"]["state_role"]
        == "thermodynamic_gibbs_energy"
    )
    assert (
        derived_by_state["derived_quantity.dynamic_thermodynamics.reaction_618_dynamic.rate_blocked"]["state_role"]
        == "thermodynamic_enforcement_flag"
    )
    assert (
        derived_by_state[
            "derived_quantity.dynamic_thermodynamics.reaction_618_dynamic.activity.cellobiose_concentration"
        ]["state_role"]
        == "thermodynamic_activity"
    )

    report_path = result.write_report()
    report = report_path.read_text(encoding="utf-8")
    assert "Standard virtual-experiment rows from `thermodynamic_diagnostics.csv`" in report
    assert "`reaction_quotient_thermodynamic_feasibility` for case" in report
    assert "configured-summary JSON present `true`" in report
    assert "configured-summary CSV present `true`" in report
    assert "allowed use `configured_metadata_inspection_only`" in report
    assert "Rows are copied from existing configured thermodynamic_summary artifacts only" in report
    assert "do not independently infer, recompute, or revalidate activities" in report
    assert "this report does not apply that enforcement" in report
    assert "constraint `reaction_618_dynamic`" in report
    assert "recorded blocked `3`" in report


def test_virtual_experiment_solver_diagnostics_copy_existing_sample_artifacts_only(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=3,
        output_dir=tmp_path / "solver_bridge",
        quicklook=False,
    )
    sample_dir = Path(result.screen_result.case_results[0].samples[0].output_directory)

    rows = result.solver_diagnostics()
    assert len(rows) == 1
    row = rows[0]
    assert row["artifact_source_directory"] == str(sample_dir)
    assert row["solver_diagnostics_json_present"] == "true"
    assert row["solver_diagnostics_csv_present"] == "true"
    assert row["summary_kind"] == "configured_solver_diagnostics"
    assert row["summary_status"] == "available"
    assert row["summary_metadata_available"] == "true"
    assert row["summary_row_count"] == "1"
    assert row["solver_backend"] == "scipy.solve_ivp"
    assert row["metadata_available"] == "True"
    assert row["configured_time_evaluation_count"] == "101"
    assert row["allowed_use"] == "configured_solver_metadata_inspection_only"
    assert "Rows are copied from existing configured solver_diagnostics artifacts only" in row[
        "interpretation_guardrail"
    ]
    assert "solver quality thresholds" in row["interpretation_guardrail"]
    assert "thermodynamic enforcement" in row["interpretation_guardrail"]
    assert "biology claims" in row["interpretation_guardrail"]

    report_path = result.write_report(include_html=True, include_index=True)
    report = report_path.read_text(encoding="utf-8")
    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")
    assert "Standard virtual-experiment rows from `solver_diagnostics.csv`" in report
    assert "copied from existing configured solver-diagnostics artifacts only" in report
    assert "do not change solver behavior" in report
    assert "define numerical quality thresholds" in report
    assert "validation/calibration evidence" in report
    assert "enforce thermodynamics" in report
    assert "add biology claims" in report
    assert "solver_diagnostics.csv" in html
    assert "solver_diagnostics.csv" in index
    assert "solver_diagnostics.json" not in index
    assert "empirically validated" not in report.lower()
    assert "calibrated against observations" not in report.lower()


def test_virtual_experiment_solver_diagnostics_header_only_without_sample_artifacts(
    tmp_path: Path,
) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=3,
        output_dir=tmp_path / "solver_bridge_no_artifacts",
        quicklook=False,
    )
    sample_dir = Path(result.screen_result.case_results[0].samples[0].output_directory)
    (sample_dir / "solver_diagnostics.json").unlink()
    (sample_dir / "solver_diagnostics.csv").unlink()

    result.write_tables()

    assert result.solver_diagnostics() == []
    with (Path(result.output_directory) / "solver_diagnostics.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert list(reader) == []
        fieldnames = set(reader.fieldnames or ())
    assert {
        "output_schema_version",
        "case_id",
        "sample_id",
        "artifact_source_directory",
        "solver_diagnostics_json_present",
        "solver_diagnostics_csv_present",
        "summary_status",
        "solver_backend",
        "interpretation_guardrail",
    }.issubset(fieldnames)


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


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _json_mapping(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    assert isinstance(data, dict)
    return data
