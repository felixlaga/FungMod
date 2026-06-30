from __future__ import annotations

import csv
import shutil
import socket
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model import VirtualExperiment, environment_grid, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.report import write_virtual_experiment_report
from fungal_model.registry import AmbiguousResolutionError, ResolutionError


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "sabiork_beta_glucosidase_source"
SUBSTRATE_ID = "cellobiose"
ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"
ENZYME_CONCENTRATION_SYMBOL = "enzyme_concentration_beta_glucosidase"


def test_virtual_experiment_top_level_works_with_exact_registry_ids() -> None:
    study = virtual_experiment(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    assert isinstance(study, VirtualExperiment)
    assert study.fungus_ids == (FUNGUS_ID,)
    assert study.substrate_ids == (SUBSTRATE_ID,)
    assert study.environment_ids == (ENVIRONMENT_ID,)


def test_virtual_experiment_top_level_works_with_aliases_and_names() -> None:
    study = virtual_experiment(
        fungi=["beta-glucosidase source"],
        substrates=["cellobiose substrate"],
        environments=["30 C pH 5 assay"],
        registry=REGISTRY_INDEX,
    )

    assert study.fungus_ids == (FUNGUS_ID,)
    assert study.substrate_ids == (SUBSTRATE_ID,)
    assert study.environment_ids == (ENVIRONMENT_ID,)
    assert {record.record_type for record in study.resolved_records} == {"fungus", "substrate", "environment"}


def test_unknown_fungus_name_fails_clearly() -> None:
    with pytest.raises(ResolutionError, match="Could not resolve fungus 'unknown source'") as exc_info:
        virtual_experiment(
            fungi="unknown source",
            substrates="cellobiose",
            environments=ENVIRONMENT_ID,
            registry=REGISTRY_INDEX,
        )

    assert exc_info.value.record_type == "fungus"


def test_unknown_substrate_name_fails_clearly() -> None:
    with pytest.raises(ResolutionError, match="Could not resolve substrate 'unknown substrate'") as exc_info:
        virtual_experiment(
            fungi="beta-glucosidase source",
            substrates="unknown substrate",
            environments=ENVIRONMENT_ID,
            registry=REGISTRY_INDEX,
        )

    assert exc_info.value.record_type == "substrate"


def test_ambiguous_name_fails_clearly_and_lists_candidate_ids(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    fungi_path = registry_dir / "fungi" / "fungi.yml"
    data = _yaml_mapping(fungi_path)
    records = cast(list[dict[str, Any]], data["records"])
    for record in records[:2]:
        aliases = list(record.get("aliases") or [])
        aliases.append("shared source alias")
        record["aliases"] = aliases
    fungi_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(AmbiguousResolutionError, match="toy_fungus_alpha") as exc_info:
        virtual_experiment(
            fungi="shared source alias",
            substrates="cellobiose",
            environments=ENVIRONMENT_ID,
            registry=registry_dir / "registry_index.yml",
        )

    assert {candidate.record_id for candidate in exc_info.value.candidates} == {
        "toy_fungus_alpha",
        "generic_cellulase_source",
    }


def test_environment_grid_works_through_top_level_api(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose substrate",
        environments=environment_grid(temperature_C=[20.0, 25.0], ph=[4.5], oxygen="aerobic"),
        registry=REGISTRY_INDEX,
    )

    assert study.environment_ids == ("temp_20C_ph_4p5_aerobic", "temp_25C_ph_4p5_aerobic")
    assert len(study.environment_cases) == 2
    assert {case.environment_effect_status for case in study.environment_cases} == {"metadata_only"}
    reports = study.preflight(mode="exploratory")
    assert {report.status for report in reports} == {"exploratory"}
    result = study.simulate(mode="exploratory", n_samples=1, seed=2, output_dir=tmp_path / "grid", quicklook=False)
    assert len(result.screen_result.case_results) == 2
    assert {row["environment_effect_status"] for row in result.provenance()} >= {"metadata_only"}
    assert any(
        "Temperature and pH do not modify kinetics" in row["limitation"]
        or "Do not rank or plot these cases as environmental response models" in row["limitation"]
        for row in result.limitations()
    )


def test_public_preflight_scientific_and_exploratory_modes() -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    scientific = study.preflight(mode="scientific")[0]
    exploratory = study.preflight(mode="exploratory")[0]

    assert scientific.status == "underparameterized"
    assert any(item.item_id == ENZYME_CONCENTRATION_SYMBOL for item in scientific.missing)
    assert exploratory.status == "exploratory"
    assert any(item.item_id == ENZYME_CONCENTRATION_SYMBOL for item in exploratory.uncertain)


def test_simulate_exploratory_works_for_reaction_618(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(mode="exploratory", n_samples=2, seed=4, output_dir=tmp_path / "exploratory", quicklook=False)

    assert result.mode == "exploratory"
    assert len(result.screen_result.case_results[0].samples) == 2
    assert result.time_series()
    assert result.final_metrics()
    assert result.limitations()
    assert Path(result.output_directory, "output_manifest.json").exists()
    assert result.time_series()[0]["output_schema_version"]


def test_simulate_scientific_rejects_reaction_618_when_enzyme_concentration_unknown(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    with pytest.raises(VirtualExperimentError, match=ENZYME_CONCENTRATION_SYMBOL):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific_blocked", quicklook=False)


def test_simulate_scientific_succeeds_for_exact_local_fixture(tmp_path: Path) -> None:
    registry = _registry_with_exact_enzyme_concentration(tmp_path)
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=registry / "registry_index.yml",
    )

    result = study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)

    assert result.mode == "scientific"
    assert result.n_samples == 1
    assert result.to_dict()["run_label"] == "scientific_exact_unvalidated"
    assert len(result.screen_result.case_results[0].samples) == 1
    assert any(row["state"] == "cellobiose_concentration" for row in result.time_series())
    assert all(row["source_value_kind"] == "exact" for row in result.sampled_parameters())
    assert not any(row["exploratory_prior"] == "true" for row in result.sampled_parameters())
    manifest = _yaml_mapping(Path(result.output_directory) / "output_manifest.json")
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    assert manifest["output_schema_version"]


def test_scientific_mode_rejects_exploratory_priors(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    scientific = study.preflight(mode="scientific")[0]
    exploratory = study.preflight(mode="exploratory")[0]

    assert any(item.item_id == ENZYME_CONCENTRATION_SYMBOL for item in scientific.missing)
    assert not scientific.uncertain
    assert any(item.item_id == ENZYME_CONCENTRATION_SYMBOL for item in exploratory.uncertain)
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)


def test_scientific_mode_rejects_toy_scientific_inputs(tmp_path: Path) -> None:
    registry = _modelable_toy_registry(tmp_path)
    study = virtual_experiment(
        fungi="toy_fungus_alpha",
        substrates="toy_cellulose_like_solid",
        environments="toy_lab_environment",
        registry=registry / "registry_index.yml",
    )

    report = study.preflight(mode="scientific")[0]

    assert report.status == "underparameterized"
    assert any("toy or synthetic" in item.message for item in report.incompatible)
    with pytest.raises(VirtualExperimentError, match="toy or synthetic"):
        study.simulate(mode="scientific", output_dir=tmp_path / "toy_blocked", quicklook=False)


def test_result_table_accessors_return_standard_tables(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(mode="exploratory", n_samples=1, seed=6, output_dir=tmp_path / "accessors", quicklook=False)

    assert result.time_series()[0]["state"]
    assert result.final_metrics()[0]["metric"]
    assert result.threshold_times()[0]["threshold_fraction"]
    assert result.sampled_parameters()[0]["symbol"]
    assert result.trajectory_quantiles()[0]["state"]
    assert result.provenance()[0]["record_type"]
    assert result.limitations()[0]["limitation"]
    assert result.missing_parameters() == []
    assert result.suggested_experiments() == []


def test_result_write_report_renders_standard_table_facts_without_validation_claims(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=7,
        output_dir=tmp_path / "report",
        quicklook=False,
    )

    report_path = result.write_report()
    report = report_path.read_text(encoding="utf-8")

    assert report_path == Path(result.output_directory) / "report" / "virtual_experiment_report.md"
    assert "# FungMod Virtual-Experiment Report" in report
    assert "generated from existing FungMod standard output tables" in report
    assert "not an additional validation, calibration, or empirical comparison" in report
    assert "sabiork_beta_glucosidase_source" in report
    assert "cellobiose" in report
    assert "final_product_concentration" in report
    assert "time_to_10_percent_substrate_degradation" in report
    assert "existing `threshold_times.csv` and `summary_metrics.csv` values only" in report
    assert "not validation data, calibration results, empirical comparisons" in report
    assert "summary_metrics.csv" in report
    assert "time_to_50_percent_substrate_degradation" in report
    assert "## Degradation-rate inspection" in report
    assert "existing `time_series_long.csv` `degradation_rate` rows only" in report
    assert "maximum observed rate" in report
    assert "or a new rate law" in report
    assert "## Uncertainty and range summary" in report
    assert "not empirical confidence intervals, calibration results, or validation evidence" in report
    assert "sampled_parameter_distribution" in report
    assert "## Trajectory quantile bands" in report
    assert "time_series_long.csv" in report
    assert "exploratory_trajectory_summary_not_validation" in report
    assert "homogeneous_michaelis_menten" in report
    assert "whole-fungus physiology" in report
    assert "user_supplied_exploratory_prior" in report
    sampled_rows = _csv_rows(Path(result.output_directory) / "sampled_parameters.csv")
    sampled_numeric = next(row for row in sampled_rows if row["sampled_value"])
    assert f"`{sampled_numeric['symbol']}` = {sampled_numeric['sampled_value']} {sampled_numeric['units']}" in report
    threshold_rows = _csv_rows(Path(result.output_directory) / "threshold_times.csv")
    not_reached_threshold = next(row for row in threshold_rows if row["status"] == "not_reached" and row["notes"])
    assert f"`{not_reached_threshold['status']}`. {not_reached_threshold['notes']}" in report
    assert f"`{not_reached_threshold['status']}` at  {not_reached_threshold['units']}" not in report
    assert "empirically validated" not in report.lower()
    assert "calibrated against observations" not in report.lower()
    assert (Path(result.output_directory) / "output_manifest.json").exists()
    assert not (Path(result.output_directory) / "report" / "index.html").exists()


def test_result_write_report_can_write_html_sidecar_without_changing_markdown_contract(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=9,
        output_dir=tmp_path / "html_report",
        quicklook=False,
    )

    report_path = result.write_report(include_html=True)
    html_path = report_path.with_suffix(".html")
    html = html_path.read_text(encoding="utf-8")

    assert report_path == Path(result.output_directory) / "report" / "virtual_experiment_report.md"
    assert html_path == Path(result.output_directory) / "report" / "virtual_experiment_report.html"
    assert "# FungMod Virtual-Experiment Report" in report_path.read_text(encoding="utf-8")
    assert "<h1>FungMod Virtual-Experiment Report</h1>" in html
    assert 'href="../case_summary.csv"' in html
    assert 'href="../time_series_long.csv"' in html
    assert 'href="../final_metrics.csv"' in html
    assert 'href="../uncertainty_summary.csv"' in html
    assert 'href="../summary_metrics.csv"' in html
    assert 'href="../trajectory_quantiles.csv"' in html
    assert "not an additional validation, calibration, or empirical comparison" in html
    assert "empirically validated" not in html.lower()
    assert "calibrated against observations" not in html.lower()
    assert "report/virtual_experiment_report.html" in (
        Path(result.output_directory) / "output_manifest.json"
    ).read_text(encoding="utf-8")
    assert not (Path(result.output_directory) / "report" / "index.html").exists()


def test_result_write_report_can_write_report_folder_index_over_existing_artifacts(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=10,
        output_dir=tmp_path / "indexed_report",
        quicklook=False,
    )
    quicklook_path = Path(result.output_directory) / "figures" / "quicklook<summary>.png"
    quicklook_path.parent.mkdir()
    quicklook_path.write_bytes(b"placeholder")
    result.quicklook_paths = (str(quicklook_path),)

    report_path = result.write_report(include_html=True, include_index=True)
    index_path = report_path.with_name("index.html")
    index = index_path.read_text(encoding="utf-8")

    assert report_path == Path(result.output_directory) / "report" / "virtual_experiment_report.md"
    assert index_path == Path(result.output_directory) / "report" / "index.html"
    assert "<h1>FungMod Virtual-Experiment Output Index</h1>" in index
    assert 'href="virtual_experiment_report.md"' in index
    assert 'href="virtual_experiment_report.html"' in index
    assert 'href="../output_manifest.json"' in index
    assert 'href="../case_summary.csv"' in index
    assert 'href="../time_series_long.csv"' in index
    assert 'href="../final_metrics.csv"' in index
    assert 'href="../uncertainty_summary.csv"' in index
    assert 'href="../summary_metrics.csv"' in index
    assert 'href="../trajectory_quantiles.csv"' in index
    assert 'href="../figures/quicklook&lt;summary&gt;.png"' in index
    assert "links existing output artifacts only" in index
    assert "validation, calibration, empirical comparison, or scientific interpretation" in index
    assert "empirically validated" not in index.lower()
    assert "calibrated against observations" not in index.lower()
    assert "report/index.html" in (Path(result.output_directory) / "output_manifest.json").read_text(encoding="utf-8")


def test_html_report_escapes_table_content_and_links_figures_deterministically(tmp_path: Path) -> None:
    table_dir = tmp_path / "tables"
    table_dir.mkdir()
    _write_csv(
        table_dir / "case_summary.csv",
        [
            {
                "case_id": "case_<script>alert(1)</script>",
                "fungus_id": "source & enzyme",
                "substrate_id": "cellobiose",
                "environment_id": "30C_pH5",
                "modelability_status": "exploratory",
            }
        ],
    )
    _write_csv(
        table_dir / "final_metrics.csv",
        [
            {
                "case_id": "case_1",
                "sample_id": "sample_0",
                "metric": "final_product_concentration",
                "value": "1.0",
                "units": "mM",
                "status": "computed",
            }
        ],
    )
    (table_dir / "output_manifest.json").write_text('{"kind": "test_manifest"}\n', encoding="utf-8")
    figure_path = tmp_path / "figures" / "quicklook<1>.png"
    figure_path.parent.mkdir()
    figure_path.write_bytes(b"placeholder")

    report_path = write_virtual_experiment_report(
        table_dir=table_dir,
        output_dir=tmp_path / "report",
        quicklook_paths=(str(figure_path),),
        include_html=True,
        include_index=True,
    )
    html_path = report_path.with_suffix(".html")
    index_path = report_path.with_name("index.html")
    first_html = html_path.read_text(encoding="utf-8")
    first_index = index_path.read_text(encoding="utf-8")

    write_virtual_experiment_report(
        table_dir=table_dir,
        output_dir=tmp_path / "report",
        quicklook_paths=(str(figure_path),),
        include_html=True,
        include_index=True,
    )

    assert report_path.exists()
    assert html_path.exists()
    assert index_path.exists()
    assert html_path.read_text(encoding="utf-8") == first_html
    assert index_path.read_text(encoding="utf-8") == first_index
    assert "<script>alert(1)</script>" not in first_html
    assert "case_&lt;script&gt;alert(1)&lt;/script&gt;" in first_html
    assert "source &amp; enzyme" in first_html
    assert 'href="../tables/case_summary.csv"' in first_html
    assert "quicklook&lt;1&gt;.png" in first_html
    assert "validation, calibration, or empirical comparison" in first_html
    assert 'href="virtual_experiment_report.md"' in first_index
    assert 'href="virtual_experiment_report.html"' in first_index
    assert 'href="../tables/output_manifest.json"' in first_index
    assert 'href="../tables/case_summary.csv"' in first_index
    assert 'href="../figures/quicklook&lt;1&gt;.png"' in first_index
    assert "validation, calibration, empirical comparison, or scientific interpretation" in first_index


def test_html_report_uses_report_relative_links_for_relative_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    table_dir = Path("outputs")
    table_dir.mkdir()
    _write_csv(
        table_dir / "case_summary.csv",
        [
            {
                "case_id": "case_1",
                "fungus_id": "source",
                "substrate_id": "cellobiose",
                "environment_id": "30C_pH5",
                "modelability_status": "exploratory",
            }
        ],
    )
    (table_dir / "output_manifest.json").write_text('{"kind": "test_manifest"}\n', encoding="utf-8")
    figure_path = Path("outputs") / "figures" / "quicklook.png"
    figure_path.parent.mkdir()
    figure_path.write_bytes(b"placeholder")

    report_path = write_virtual_experiment_report(
        table_dir=table_dir,
        output_dir=Path("outputs") / "report",
        quicklook_paths=(str(figure_path),),
        include_html=True,
        include_index=True,
    )

    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")
    assert 'href="../case_summary.csv"' in html
    assert 'href="../figures/quicklook.png"' in html
    assert 'href="outputs/case_summary.csv"' not in html
    assert 'href="outputs/figures/quicklook.png"' not in html
    assert 'href="virtual_experiment_report.md"' in index
    assert 'href="virtual_experiment_report.html"' in index
    assert 'href="../output_manifest.json"' in index
    assert 'href="../case_summary.csv"' in index
    assert 'href="../figures/quicklook.png"' in index
    assert 'href="outputs/output_manifest.json"' not in index
    assert 'href="outputs/case_summary.csv"' not in index


def test_no_live_external_api_call_occurs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def blocked_connect(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("VirtualExperiment simulation must not call live external APIs.")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    study = virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(mode="exploratory", n_samples=1, seed=8, output_dir=tmp_path / "offline", quicklook=False)

    assert result.time_series()


def _registry_with_exact_enzyme_concentration(tmp_path: Path) -> Path:
    registry_dir = _copy_registry(tmp_path)
    parameters_path = registry_dir / "parameters" / "parameter_records.yml"
    data = _yaml_mapping(parameters_path)
    records = cast(list[dict[str, Any]], data["records"])
    for record in records:
        if (
            record.get("parameter_symbol") == ENZYME_CONCENTRATION_SYMBOL
            and record.get("process_type") == "homogeneous_michaelis_menten"
            and record.get("maturity") == "literature_processed"
        ):
            record["value"] = {
                "kind": "exact",
                "value": 0.01,
                "units": "mM",
                "source": "Local deterministic enzyme concentration fixture",
                "confidence_level": "synthetic_control",
                "notes": "Used only to exercise scientific-mode mechanics; not a SABIO-RK value.",
            }
            parameters_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            return registry_dir
    raise AssertionError("Missing enzyme concentration record")


def _modelable_toy_registry(tmp_path: Path) -> Path:
    registry_dir = _copy_registry(tmp_path)
    process_path = registry_dir / "processes" / "process_compatibility.yml"
    data = _yaml_mapping(process_path)
    records = cast(list[dict[str, Any]], data["records"])
    records[0]["required_parameters"] = ["k_surface_exact", "k_ads_exact", "A_surface_exact"]
    records[0]["parameter_roles"] = {
        "surface_rate_constant": "k_surface_exact",
        "adsorption_constant": "k_ads_exact",
        "accessible_surface_area": "A_surface_exact",
    }
    process_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return registry_dir


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    assert rows
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
