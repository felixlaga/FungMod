from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest


NOTEBOOKS = [
    "00_quickstart.ipynb",
    "01_config_entity_inspection.ipynb",
    "02_failure_report.ipynb",
    "03_configured_outputs.ipynb",
]

PRODUCT_NOTEBOOKS = [
    "10_virtual_experiment_product_tour.ipynb",
    "13_screen_comparison_summary_example.ipynb",
    "14_trajectory_quantiles_example.ipynb",
    "15_provenance_limitations_report_example.ipynb",
]

THERMODYNAMIC_NOTEBOOKS = [
    "11_thermodynamics_entropy_diagnostics.ipynb",
    "16_thermodynamic_diagnostics_example.ipynb",
]

BIO003_NOTEBOOKS = [
    "12_reversible_product_inhibition_example.ipynb",
]

ENVIRONMENT_MODIFIER_NOTEBOOKS = [
    "17_configured_environment_modifiers_example.ipynb",
    "18_configured_oxygen_water_modifiers_example.ipynb",
]


NOTEBOOK_DIR = Path(__file__).resolve().parents[1] / "notebooks" / "examples"

PUBLIC_API_PATTERNS = (
    re.compile(r"(^|\n)\s*(from\s+fungal_model\s+import|import\s+fungal_model)\b"),
    re.compile(r"\brun_configured_model\s*\("),
)

HIDDEN_IMPLEMENTATION_PATTERNS = {
    "process class": re.compile(r"(^|\n)\s*class\s+\w*Process\b"),
    "solver class": re.compile(r"(^|\n)\s*class\s+\w*Solver\b"),
    "process factory class": re.compile(r"(^|\n)\s*class\s+\w*Factory\b"),
    "rate-law function": re.compile(r"(^|\n)\s*def\s+\w*rate\w*\s*\("),
    "solver function": re.compile(r"(^|\n)\s*def\s+\w*solver\w*\s*\("),
    "low-level solver import": re.compile(r"(^|\n)\s*(from\s+fungal_model\.solvers|from\s+scipy\.integrate)"),
    "core engine import": re.compile(r"(^|\n)\s*from\s+fungal_model\.core\.simulation\b"),
    "process internals import": re.compile(r"(^|\n)\s*from\s+fungal_model\.processes\b"),
    "direct scipy solver call": re.compile(r"\bsolve_ivp\s*\("),
    "legacy rate-law class": re.compile(r"\bRateLaw\s*="),
    "legacy PET rate law": re.compile(r"\bPETSurfaceHydrolysisRateLaw\b"),
    "reaction-diffusion engine": re.compile(r"\bReactionDiffusionEngine\b"),
    "simulation engine": re.compile(r"\bSimulationEngine\b"),
}


def load_notebook(name: str) -> dict:
    path = NOTEBOOK_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def code_cells(notebook: dict) -> list[str]:
    return [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    ]


def markdown_cells(notebook: dict) -> list[str]:
    return [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "markdown"
    ]


def test_required_notebooks_exist_and_import_package_code() -> None:
    for name in NOTEBOOKS:
        notebook = load_notebook(name)
        assert notebook["nbformat"] == 4
        source = "\n".join(code_cells(notebook))
        for pattern in PUBLIC_API_PATTERNS:
            assert pattern.search(source), f"{name} does not demonstrate required public API pattern {pattern.pattern!r}"
        assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_foundation_notebooks_are_labelled_software_test_only() -> None:
    for name in NOTEBOOKS:
        markdown = "\n".join(markdown_cells(load_notebook(name))).lower()

        assert "software-test fixture only" in markdown
        assert "not a researcher-facing scientific example" in markdown


def test_notebooks_do_not_define_core_classes_or_rate_laws() -> None:
    for name in [
        *NOTEBOOKS,
        *PRODUCT_NOTEBOOKS,
        *THERMODYNAMIC_NOTEBOOKS,
        *BIO003_NOTEBOOKS,
        *ENVIRONMENT_MODIFIER_NOTEBOOKS,
    ]:
        source = "\n".join(code_cells(load_notebook(name)))
        for label, pattern in HIDDEN_IMPLEMENTATION_PATTERNS.items():
            assert not pattern.search(source), f"{name} contains hidden implementation pattern {label!r}"


def test_product_tour_notebook_is_researcher_facing_but_unvalidated() -> None:
    notebook = load_notebook("10_virtual_experiment_product_tour.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert "researcher-facing exploratory tour" in markdown
    assert "not an empirical validation" in markdown
    assert "virtual_experiment(" in source
    assert "mechanism_summary()" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_screen_comparison_notebook_is_researcher_facing_but_unvalidated() -> None:
    notebook = load_notebook("13_screen_comparison_summary_example.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "researcher-facing exploratory example" in markdown
    assert "not an empirical validation" in markdown
    assert "metadata-only environment grid" in markdown
    assert "must not rank" in markdown
    assert "virtual_experiment(" in source
    assert "environment_grid(" in source
    assert "write_report(" in source
    assert "include_html=True" in source
    assert "include_index=True" in source
    assert "comparison_summary()" in source
    assert "comparison_summary.csv" in source
    assert "ranking_blocking_reason" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_trajectory_quantiles_notebook_is_researcher_facing_but_unvalidated() -> None:
    notebook = load_notebook("14_trajectory_quantiles_example.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "researcher-facing exploratory example" in markdown
    assert "not an empirical validation" in markdown
    assert "posterior-uncertainty" in markdown
    assert "trajectory_quantiles()" in source
    assert "trajectory_quantiles.csv" in source
    assert "write_quicklook_plots(" in source
    assert "trajectory_quantile_bands.png" in source
    assert "write_report(" in source
    assert "include_html=True" in source
    assert "include_index=True" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_provenance_limitations_report_notebook_is_researcher_facing_but_unvalidated() -> None:
    notebook = load_notebook("15_provenance_limitations_report_example.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "researcher-facing exploratory example" in markdown
    assert "not an empirical validation" in markdown
    assert "report/output ergonomics" in markdown
    assert "provenance/limitation decision summary" in markdown
    assert "decision-support table links" in markdown
    assert "virtual_experiment(" in source
    assert "write_report(" in source
    assert "include_html=True" in source
    assert "include_index=True" in source
    assert "provenance()" in source
    assert "limitations()" in source
    assert "missing_parameters()" in source
    assert "suggested_experiments()" in source
    assert "assumption_summary()" in source
    assert "provenance_table.csv" in source
    assert "limitations_table.csv" in source
    assert "not validation, calibration, empirical comparison, or inferred biology" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_thermodynamics_entropy_notebook_uses_configured_outputs_only() -> None:
    notebook = load_notebook("11_thermodynamics_entropy_diagnostics.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "software-test fixture only" in markdown
    assert "not a researcher-facing scientific example" in markdown
    assert "does not infer activities" in markdown
    assert "does not infer activities, reaction quotients, concentrations" in markdown
    assert "solver time" in markdown
    assert "run_configured_model(" in source
    assert "reaction_quotient_thermodynamic_metadata" in source
    assert "entropy_production_rate_metadata" in source
    assert "entropy_production_rate" in source
    assert "condition_specific_delta_gibbs" in source
    assert "reaction_extent_rate" in source
    assert "entropy budget" in markdown
    assert "has_entropy_budget" in source
    assert "entropy_budget_status" in source
    assert "entropy_budget_negative_count" in source
    assert "csv_has_budget_columns" in source
    assert "thermodynamic_summary.json" in source
    assert "thermodynamic_summary.csv" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source
    assert "from fungal_model.core" not in source
    assert "from fungal_model.chemistry" not in source
    assert "validate_reaction_quotient_gibbs_feasibility" not in source
    assert "GibbsFreeEnergyEstimate" not in source


def test_thermodynamic_diagnostics_notebook_is_researcher_facing_but_unvalidated() -> None:
    notebook = load_notebook("16_thermodynamic_diagnostics_example.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "researcher-facing exploratory example" in markdown
    assert "not an empirical validation" in markdown
    assert "header-only" in markdown
    assert "package-generated configured thermodynamic summary artifacts" in markdown
    assert "does not infer activities, reaction quotients, concentrations" in markdown
    assert "solver-time thermodynamic enforcement" in markdown
    assert "VirtualExperiment.from_registry(" in source
    assert "run_configured_model(" in source
    assert "thermodynamic_diagnostics()" in source
    assert "thermodynamic_diagnostics.csv" in source
    assert "thermodynamic_summary.json" in source
    assert "thermodynamic_summary.csv" in source
    assert "shutil.copy2(" in source
    assert "write_report(" in source
    assert "include_html=True" in source
    assert "include_index=True" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_product_inhibition_notebook_is_researcher_facing_but_unvalidated() -> None:
    notebook = load_notebook("12_reversible_product_inhibition_example.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "researcher-facing exploratory example" in markdown
    assert "not an empirical validation" in markdown
    assert "1 / (1 + p / k_i)" in markdown
    assert "toxicity" in markdown
    assert "virtual_experiment(" in source
    assert "prepare_reversible_product_inhibition_example_registry" in source
    assert "mechanism_summary()" in source
    assert "configured_metadata.json" in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_configured_environment_modifier_notebook_uses_configured_outputs_only() -> None:
    notebook = load_notebook("17_configured_environment_modifiers_example.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "public configured-workflow example" in markdown
    assert "artificial framework-benchmark config data" in markdown
    assert "not an empirical validation" in markdown
    assert "no fitted response curve" in markdown
    assert "no inferred environment response" in markdown
    assert "no environmentgrid behavior change" in markdown
    assert "run_configured_model(" in source
    assert "temperature_arrhenius_reference" in source
    assert "ph_gaussian" in source
    assert "configured_metadata.json" in source
    assert "assumptions.json" in source
    assert "process_rates.csv" in source
    assert "merged_parameters.json" in source
    assert "entity_snapshots" in source
    assert "index.json" in source
    assert "environment_grid(" not in source
    assert "EnvironmentGrid" not in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_configured_oxygen_water_modifier_notebook_uses_configured_outputs_only() -> None:
    notebook = load_notebook("18_configured_oxygen_water_modifiers_example.ipynb")
    markdown = "\n".join(markdown_cells(notebook)).lower()
    source = "\n".join(code_cells(notebook))

    assert notebook["nbformat"] == 4
    assert "public configured-workflow example" in markdown
    assert "artificial framework-benchmark temp config data" in markdown
    assert "not an empirical validation" in markdown
    assert "no biological claim" in markdown
    assert "fitted oxygen/water-activity response curve" in markdown
    assert "no inferred environment response" in markdown
    assert "no environmentgrid behavior change" in markdown
    assert "no oxygen consumption state" in markdown
    assert "gas transfer" in markdown
    assert "redox balance" in markdown
    assert "anaerobic metabolism" in markdown
    assert "substrate water-binding model" in markdown
    assert "run_configured_model(" in source
    assert "oxygen_monod" in source
    assert "water_activity_threshold" in source
    assert "configured_metadata.json" in source
    assert "assumptions.json" in source
    assert "process_rates.csv" in source
    assert "merged_parameters.json" in source
    assert "entity_snapshots" in source
    assert "input_model_config.json" in source
    assert "environment_grid(" not in source
    assert "EnvironmentGrid" not in source
    assert "FUNGMOD_NOTEBOOK_OUTPUT_ROOT" in source


def test_quickstart_notebook_executes_smoke_path_with_temp_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("00_quickstart.ipynb")

    output = output_root / "00_quickstart"
    assert (output / "record.json").exists()
    assert (output / "figures" / "state_trajectories.png").exists()
    assert (output / "output_manifest.json").exists()


def test_foundation_notebooks_execute_smoke_paths_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))

    for name in NOTEBOOKS:
        _execute_notebook(name)

    output = output_root / "00_quickstart"
    assert (output / "record.json").exists()
    assert (output / "figures" / "state_trajectories.png").exists()
    assert (output / "output_manifest.json").exists()

    failure_output = output_root / "02_failure_report"
    assert (failure_output / "failure_report.json").exists()

    inspection_output = output_root / "03_configured_outputs"
    assert (inspection_output / "configured_metadata.json").exists()


def test_product_tour_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("10_virtual_experiment_product_tour.ipynb")

    output = output_root / "10_virtual_experiment_product_tour"
    assert (output / "mechanism_summary.csv").exists()
    assert (output / "assumption_summary.csv").exists()
    assert (output / "limitations_table.csv").exists()
    assert (output / "output_manifest.json").exists()


def test_screen_comparison_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("13_screen_comparison_summary_example.ipynb")

    output = output_root / "13_screen_comparison_summary_example"
    comparison_rows = _csv_rows(output / "comparison_summary.csv")
    assert (output / "output_manifest.json").exists()
    assert (output / "report" / "virtual_experiment_report.md").exists()
    assert (output / "report" / "virtual_experiment_report.html").exists()
    assert (output / "report" / "index.html").exists()
    index_text = (output / "report" / "index.html").read_text(encoding="utf-8")
    assert "comparison_summary.csv" in index_text
    assert comparison_rows
    required_columns = {
        "comparison_allowed",
        "ranking_allowed",
        "ranking_blocking_reason",
        "recommended_next_action",
    }
    assert required_columns.issubset(comparison_rows[0])
    assert {row["comparison_allowed"] for row in comparison_rows} == {"false"}
    assert {row["ranking_allowed"] for row in comparison_rows} == {"false"}
    assert all("cannot be ranked" in row["ranking_blocking_reason"] for row in comparison_rows)
    assert {
        row["recommended_next_action"]
        for row in comparison_rows
    } == {"inspect_source_rows_only_do_not_rank_or_plot_as_response"}


def test_trajectory_quantiles_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("14_trajectory_quantiles_example.ipynb")

    output = output_root / "14_trajectory_quantiles_example"
    trajectory_rows = _csv_rows(output / "trajectory_quantiles.csv")
    assert (output / "output_manifest.json").exists()
    assert (output / "figures" / "trajectory_quantile_bands.png").exists()
    assert (output / "report" / "virtual_experiment_report.md").exists()
    assert (output / "report" / "virtual_experiment_report.html").exists()
    assert (output / "report" / "index.html").exists()
    index_text = (output / "report" / "index.html").read_text(encoding="utf-8")
    assert "trajectory_quantiles.csv" in index_text
    assert "trajectory_quantile_bands.png" in index_text
    assert trajectory_rows
    assert {row["source_table"] for row in trajectory_rows} == {"time_series_long"}
    assert {row["allowed_use"] for row in trajectory_rows} == {
        "exploratory_trajectory_summary_not_validation"
    }
    assert all("not validation data" in row["interpretation_guardrail"] for row in trajectory_rows)


def test_provenance_limitations_report_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("15_provenance_limitations_report_example.ipynb")

    output = output_root / "15_provenance_limitations_report_example"
    report_dir = output / "report"
    report_text = (report_dir / "virtual_experiment_report.md").read_text(encoding="utf-8")
    html_text = (report_dir / "virtual_experiment_report.html").read_text(encoding="utf-8")
    index_text = (report_dir / "index.html").read_text(encoding="utf-8")

    assert (output / "output_manifest.json").exists()
    assert "## Provenance and limitation decision summary" in report_text
    assert "derived only from existing `assumption_summary.csv`" in report_text
    assert "not validation, calibration, empirical comparison, or inferred biology" in report_text
    assert "Source row counts: assumptions=" in report_text
    assert "Limitation severity counts:" in report_text
    assert "Assumption/provenance allowed-use labels present:" in report_text
    assert "Exploratory-prior provenance rows:" in report_text

    assert _csv_rows(output / "assumption_summary.csv")
    assert _csv_rows(output / "limitations_table.csv")
    assert _csv_rows(output / "provenance_table.csv")
    assert (output / "missing_parameters.csv").exists()
    assert (output / "suggested_experiments.csv").exists()

    for filename in (
        "assumption_summary.csv",
        "limitations_table.csv",
        "missing_parameters.csv",
        "suggested_experiments.csv",
        "provenance_table.csv",
    ):
        assert filename in index_text
        assert f"../{filename}" in html_text


def test_thermodynamics_entropy_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("11_thermodynamics_entropy_diagnostics.ipynb")

    output = output_root / "11_thermodynamics_entropy_diagnostics"
    summary = json.loads((output / "thermodynamic_summary.json").read_text(encoding="utf-8"))
    assert (output / "thermodynamic_summary.csv").exists()
    assert summary["kind"] == "configured_thermodynamic_summary"
    assert summary["count"] == 2
    assert summary["has_reaction_quotient_gibbs"] is True
    assert summary["has_entropy_production_rate"] is True
    assert summary["has_entropy_budget"] is True
    assert summary["entropy_budget_units"] == "joule / second / kelvin"
    assert summary["entropy_budget_status"] == "non_negative"
    assert summary["entropy_budget_evaluated_count"] == 1
    assert summary["entropy_budget_negative_count"] == 0
    assert summary["entropy_budget_total"] > 0
    assert "not treated as zero" in summary["entropy_budget_limitations"]
    assert summary["has_solver_time_enforcement"] is False
    rows_by_name = {row["name"]: row for row in summary["rows"]}
    assert rows_by_name["reaction_quotient_thermodynamic_feasibility"]["gibbs_equation"] == (
        "delta_g = delta_g_standard + R*T*ln(Q)"
    )
    entropy_rate_row = rows_by_name["entropy_production_rate_metadata"]
    assert entropy_rate_row["entropy_equation"] == (
        "entropy_production_rate = -condition_specific_delta_gibbs * "
        "reaction_extent_rate / temperature"
    )
    assert entropy_rate_row["entropy_production_rate"] > 0
    assert entropy_rate_row["entropy_production_rate_units"] == "joule / second / kelvin"
    csv_rows_by_name = {row["name"]: row for row in _csv_rows(output / "thermodynamic_summary.csv")}
    assert csv_rows_by_name["entropy_production_rate_metadata"]["solver_time_enforcement"] == "not_evaluated"
    assert float(csv_rows_by_name["entropy_production_rate_metadata"]["entropy_production_rate"]) > 0
    assert "entropy_budget_status" not in csv_rows_by_name["entropy_production_rate_metadata"]
    assert "No inferred activity model" in summary["unsupported_scope"]
    assert "concentration model" in summary["unsupported_scope"]


def test_thermodynamic_diagnostics_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("16_thermodynamic_diagnostics_example.ipynb")

    output = output_root / "16_thermodynamic_diagnostics_example"
    no_artifact_output = output / "no_artifacts"
    configured_output = output / "configured_thermodynamic_summary"
    copied_output = output / "copied_artifact_bridge"

    assert (no_artifact_output / "thermodynamic_diagnostics.csv").exists()
    assert _csv_rows(no_artifact_output / "thermodynamic_diagnostics.csv") == []
    assert (configured_output / "thermodynamic_summary.json").exists()
    assert (configured_output / "thermodynamic_summary.csv").exists()

    summary = json.loads((configured_output / "thermodynamic_summary.json").read_text(encoding="utf-8"))
    diagnostic_rows = _csv_rows(copied_output / "thermodynamic_diagnostics.csv")
    report_text = (copied_output / "report" / "virtual_experiment_report.md").read_text(encoding="utf-8")
    index_text = (copied_output / "report" / "index.html").read_text(encoding="utf-8")

    assert summary["kind"] == "configured_thermodynamic_summary"
    assert summary["has_reaction_quotient_gibbs"] is True
    assert summary["has_entropy_production_rate"] is True
    assert summary["has_entropy_budget"] is True
    assert diagnostic_rows
    assert {row["row_name"] for row in diagnostic_rows} == {
        "reaction_quotient_thermodynamic_feasibility",
        "entropy_production_rate_metadata",
    }
    assert {row["thermodynamic_summary_json_present"] for row in diagnostic_rows} == {"true"}
    assert {row["thermodynamic_summary_csv_present"] for row in diagnostic_rows} == {"true"}
    assert {row["allowed_use"] for row in diagnostic_rows} == {"configured_metadata_inspection_only"}
    assert {row["entropy_budget_status"] for row in diagnostic_rows} == {"non_negative"}
    assert all(
        "Rows are copied from existing configured thermodynamic_summary artifacts only"
        in row["interpretation_guardrail"]
        for row in diagnostic_rows
    )
    assert "Standard virtual-experiment rows from `thermodynamic_diagnostics.csv`" in report_text
    assert "thermodynamic_diagnostics.csv" in index_text


def test_product_inhibition_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("12_reversible_product_inhibition_example.ipynb")

    output = output_root / "12_reversible_product_inhibition_example" / "inhibited"
    mechanism_rows = _csv_rows(output / "mechanism_summary.csv")
    assert (output / "final_metrics.csv").exists()
    assert (output / "limitations_table.csv").exists()
    assert (output / "output_manifest.json").exists()
    assert any(
        row["mechanism_kind"] == "rate_modifier"
        and row["mechanism_id"] == "product_inhibition"
        and row["parameters"] == "inhibition_constant:K_i_bio003_product_example"
        for row in mechanism_rows
    )


def test_configured_environment_modifier_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("17_configured_environment_modifiers_example.ipynb")

    output = output_root / "17_configured_environment_modifiers_example"
    base_output = output / "base"
    modified_output = output / "modified"

    metadata = json.loads((modified_output / "configured_metadata.json").read_text(encoding="utf-8"))
    assumptions = json.loads((modified_output / "assumptions.json").read_text(encoding="utf-8"))
    input_config = json.loads((modified_output / "input_model_config.json").read_text(encoding="utf-8"))
    merged_parameters = json.loads((modified_output / "merged_parameters.json").read_text(encoding="utf-8"))
    entity_index = json.loads((modified_output / "entity_snapshots" / "index.json").read_text(encoding="utf-8"))
    environment_entry = next(entry for entry in entity_index["entities"] if entry["role"] == "environment")
    environment = json.loads((modified_output / environment_entry["snapshot_path"]).read_text(encoding="utf-8"))

    assert (base_output / "process_rates.csv").exists()
    assert (modified_output / "process_rates.csv").exists()
    assert (modified_output / "output_manifest.json").exists()
    assert [row["type"] for row in metadata["configured_process_modifiers"]] == [
        "temperature_arrhenius_reference",
        "ph_gaussian",
    ]
    assert metadata["configured_process_modifiers"][0]["activation_energy_symbol"] == "E_a_env"
    assert metadata["configured_process_modifiers"][1]["width_symbol"] == "pH_width_env"
    assert {row["environment_value"] for row in metadata["configured_process_modifiers"]} == {"temperature", "ph"}
    assert all(row["maturity"] == "exploratory_configured_mechanism" for row in metadata["configured_process_modifiers"])
    assert input_config["processes"][0]["modifiers"][0]["type"] == "temperature_arrhenius_reference"
    assert input_config["processes"][0]["modifiers"][1]["type"] == "ph_gaussian"
    assert {"E_a_env", "T_ref_env", "pH_opt_env", "pH_width_env"}.issubset(
        {item["symbol"] for item in merged_parameters["parameters"]}
    )
    assert environment["temperature"]["value"] == 303.15
    assert environment["ph"]["value"] == 7.0
    assert any(item["name"] == "Arrhenius temperature scaling without deactivation" for item in assumptions)
    assert any(item["name"] == "Gaussian empirical pH activity profile" for item in assumptions)

    base_first_rate = float(_csv_rows(base_output / "process_rates.csv")[0]["value"])
    modified_first_rate = float(_csv_rows(modified_output / "process_rates.csv")[0]["value"])
    assert modified_first_rate != pytest.approx(base_first_rate)


def test_configured_oxygen_water_modifier_notebook_executes_smoke_path_with_temp_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "notebook_outputs"
    monkeypatch.setenv("FUNGMOD_NOTEBOOK_OUTPUT_ROOT", str(output_root))
    _execute_notebook("18_configured_oxygen_water_modifiers_example.ipynb")

    output = output_root / "18_configured_oxygen_water_modifiers_example"
    base_output = output / "base"
    modified_output = output / "modified"

    metadata = json.loads((modified_output / "configured_metadata.json").read_text(encoding="utf-8"))
    assumptions = json.loads((modified_output / "assumptions.json").read_text(encoding="utf-8"))
    input_config = json.loads((modified_output / "input_model_config.json").read_text(encoding="utf-8"))
    merged_parameters = json.loads((modified_output / "merged_parameters.json").read_text(encoding="utf-8"))
    entity_index = json.loads((modified_output / "entity_snapshots" / "index.json").read_text(encoding="utf-8"))
    environment_entry = next(entry for entry in entity_index["entities"] if entry["role"] == "environment")
    environment = json.loads((modified_output / environment_entry["snapshot_path"]).read_text(encoding="utf-8"))

    assert (base_output / "process_rates.csv").exists()
    assert (modified_output / "process_rates.csv").exists()
    assert (modified_output / "output_manifest.json").exists()
    assert [row["type"] for row in metadata["configured_process_modifiers"]] == [
        "oxygen_monod",
        "water_activity_threshold",
    ]
    oxygen_modifier, water_modifier = metadata["configured_process_modifiers"]
    assert oxygen_modifier["half_saturation_symbol"] == "K_O2_env"
    assert oxygen_modifier["oxygen_units"] == "mole / liter"
    assert water_modifier["minimum_water_activity_symbol"] == "a_w_min_env"
    assert {row["environment_value"] for row in metadata["configured_process_modifiers"]} == {
        "oxygen_concentration",
        "water_activity",
    }
    assert all(row["maturity"] == "exploratory_configured_mechanism" for row in metadata["configured_process_modifiers"])
    assert "No oxygen consumption" in oxygen_modifier["limitation"]
    assert "gas transfer" in oxygen_modifier["limitation"]
    assert "redox balance" in oxygen_modifier["limitation"]
    assert "anaerobic metabolism" in oxygen_modifier["limitation"]
    assert "No smooth response curve" in water_modifier["limitation"]
    assert "substrate water binding" in water_modifier["limitation"]
    assert input_config["processes"][0]["modifiers"][0]["type"] == "oxygen_monod"
    assert input_config["processes"][0]["modifiers"][1]["type"] == "water_activity_threshold"
    assert {"K_O2_env", "a_w_min_env"}.issubset(
        {item["symbol"] for item in merged_parameters["parameters"]}
    )
    assert environment["oxygen_concentration"]["value"] == 0.25
    assert environment["oxygen_concentration"]["units"] == "mole / liter"
    assert environment["water_activity"]["value"] == 0.98
    assert any(item["name"] == "oxygen Monod limitation modifier" for item in assumptions)
    assert any(item["name"] == "minimum water activity threshold" for item in assumptions)

    base_first_rate = float(_csv_rows(base_output / "process_rates.csv")[0]["value"])
    modified_first_rate = float(_csv_rows(modified_output / "process_rates.csv")[0]["value"])
    assert modified_first_rate != pytest.approx(base_first_rate)


def _execute_notebook(name: str) -> None:
    namespace: dict[str, object] = {"__name__": "__notebook_smoke__"}
    for source in code_cells(load_notebook(name)):
        exec(compile(source, f"notebooks/{name}", "exec"), namespace)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
