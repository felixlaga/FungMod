from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from fungal_model import example_data_path, run_configured_model
from fungal_model.data import ObservableMapping, evaluate_model_against_dataset, load_experiment_dataset


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/model_configs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison.yml"
DATASET = (
    ROOT
    / "data/experiments/literature/alvarez_gonzalez_2022_free_beta_glucosidase"
    / "alvarez_gonzalez_2022_free_beta_glucosidase.yml"
)


def test_source_matched_model_compares_without_fungmod_calibration(tmp_path: Path) -> None:
    result = run_configured_model(CONFIG, output_dir=tmp_path / "model")
    dataset = load_experiment_dataset(DATASET)
    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=(
            ObservableMapping(
                dataset_measurement_id="cellobiose_concentration",
                model_observable="cellobiose_concentration",
                observable_type="state",
            ),
        ),
    )

    assert comparison.dataset_id == (
        "alvarez_gonzalez_2022_free_beta_glucosidase_cellobiose_20gl_v1"
    )
    assert comparison.metrics["n_points"] == 9
    assert comparison.metrics["rmse"] == pytest.approx(1.07876597, abs=1.0e-6)
    assert comparison.residuals[0].points[-1].predicted == pytest.approx(6.2112832, abs=1.0e-6)
    assert result.states["glucose_concentration"][-1].magnitude == pytest.approx(
        2.0 * (62.455 - 6.2112832), abs=1.0e-6
    )
    assert all(validation["passed"] for validation in result.validation_report())


def test_comparison_config_preserves_source_scope_and_exact_model_3_parameters() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parameter_values = {
        parameter["symbol"]: parameter["value"]
        for parameter_set in config["parameters"]
        for parameter in parameter_set["parameters"]
    }
    modifier = config["processes"][0]["modifiers"][0]

    assert config["mode"] == "exploratory"
    assert "no parameters are fitted by FungMod" in config["provenance"]["notes"]
    assert parameter_values == {
        "K_m_cellobiose_2022": 43.0,
        "V_max_cellobiose_2022": 19.72544,
        "K_i_cellobiose_2022": 1088.0,
        "K_p_glucose_2022": 34.0,
    }
    assert modifier["type"] == "coupled_substrate_product_inhibition"
    assert modifier["primary_source"] == "https://doi.org/10.3390/catal12010080"


def test_packaged_comparison_config_runs_outside_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_configured_model(
        example_data_path("model_configs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison.yml"),
        output_dir=tmp_path / "packaged_model",
    )

    assert result.states["cellobiose_concentration"][-1].magnitude == pytest.approx(
        6.2112832, abs=1.0e-6
    )


def test_comparison_runner_persists_reproducible_bundles(tmp_path: Path) -> None:
    script_path = ROOT / "scripts/run_literature_time_course_comparison.py"
    spec = importlib.util.spec_from_file_location("run_literature_time_course_comparison", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    comparison = module.run_comparison(output_dir=tmp_path)

    comparison_dir = tmp_path / "comparison_bundle"
    model_dir = tmp_path / "model_bundle"
    assert comparison.metrics["rmse"] == pytest.approx(1.07876597, abs=1.0e-6)
    for path in (
        model_dir / "record.json",
        model_dir / "validation_report.json",
        comparison_dir / "comparison_record.json",
        comparison_dir / "dataset_snapshot.json",
        comparison_dir / "observable_mapping.json",
        comparison_dir / "metrics.json",
        comparison_dir / "model_comparison.csv",
        comparison_dir / "residuals.csv",
        comparison_dir / "validation_report.json",
        comparison_dir / "validation_report.md",
        comparison_dir / "figures/observed_vs_predicted.png",
        comparison_dir / "figures/residuals.png",
    ):
        assert path.is_file(), path
    assert json.loads((comparison_dir / "metrics.json").read_text(encoding="utf-8"))["n_points"] == 9
    report = (comparison_dir / "validation_report.md").read_text(encoding="utf-8")
    assert "does not by itself establish independent validation" in report
    assert "digitization error, not experimental uncertainty" in report
