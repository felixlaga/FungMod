from __future__ import annotations

import json
from pathlib import Path
from dataclasses import replace

import pytest

from fungal_model import run_configured_model
from fungal_model.calibration import ConfiguredCalibrationError, calibrate_configured_model
from fungal_model.core.units import Q_
from fungal_model.data import (
    GaussianNoise,
    ObservableMapping,
    generate_synthetic_dataset_from_result,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIG = ROOT / "data" / "model_configs" / "synthetic_first_order_calibration.yml"


def test_configured_synthetic_calibration_recovers_first_order_rate(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)
    original_config = MODEL_CONFIG.read_text(encoding="utf-8")

    result = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
        split={"method": "by_time", "train_fraction": 0.7, "validation_fraction": 0.3},
        output_dir=tmp_path / "calibration",
    )

    assert result.success
    assert result.fitted_parameters.get("k_ab").quantity.to("1 / second").magnitude == pytest.approx(0.1, rel=0.05)
    assert result.metrics["train_rmse"] < 0.003
    assert result.metrics["validation_rmse"] < 0.003
    assert result.split is not None
    train_indices = set(result.split.train_indices["product_mass"])
    validation_indices = set(result.split.validation_indices["product_mass"])
    assert train_indices
    assert validation_indices
    assert not train_indices.intersection(validation_indices)
    assert MODEL_CONFIG.read_text(encoding="utf-8") == original_config


def test_calibration_output_bundle_is_inspectable(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
        split={"method": "by_time", "train_fraction": 0.7, "validation_fraction": 0.3},
        output_dir=tmp_path / "calibration",
    )

    expected_files = (
        "calibration_record.json",
        "source_model_config.json",
        "dataset_snapshot.json",
        "fitted_parameters.yml",
        "fitted_parameters.json",
        "optimizer_metadata.json",
        "train_residuals.csv",
        "validation_residuals.csv",
        "metrics.json",
        "assumptions.json",
        "warnings.json",
        "figures/observed_vs_predicted_train.png",
        "figures/observed_vs_predicted_validation.png",
        "figures/residuals_train.png",
        "figures/residuals_validation.png",
    )
    for relative_path in expected_files:
        assert (tmp_path / "calibration" / relative_path).exists(), relative_path
    record = json.loads((tmp_path / "calibration" / "calibration_record.json").read_text(encoding="utf-8"))
    assert record["dataset_id"] == dataset.dataset_id
    assert record["parameter_symbols"] == ["k_ab"]
    assert record["split"]["has_validation"] is True


def test_calibration_without_split_makes_no_validation_claim(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    result = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
    )

    assert result.success
    assert "validation_rmse" not in result.metrics
    assert any("no validation claim" in warning for warning in result.warnings)
    assert result.split is not None
    assert not result.split.has_validation


def test_configured_calibration_rejects_non_synthetic_dataset(tmp_path: Path) -> None:
    dataset = replace(_generated_dataset(tmp_path), maturity="toy")

    with pytest.raises(ConfiguredCalibrationError, match="synthetic-only"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=["k_ab"],
            observable_mapping=_mapping(),
            initial_guess={"k_ab": 0.03},
            bounds={"k_ab": (0.0, 1.0)},
        )


def test_configured_calibration_rejects_bad_split(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    with pytest.raises(ConfiguredCalibrationError, match="by_time"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=["k_ab"],
            observable_mapping=_mapping(),
            initial_guess={"k_ab": 0.03},
            bounds={"k_ab": (0.0, 1.0)},
            split={"method": "random"},
        )


def test_configured_calibration_rejects_parameter_not_in_config(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    with pytest.raises(ConfiguredCalibrationError, match="Missing parameter symbols"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=["not_in_config"],
            observable_mapping=_mapping(),
            initial_guess={"not_in_config": 0.03},
            bounds={"not_in_config": (0.0, 1.0)},
        )


def _generated_dataset(tmp_path: Path):
    result = run_configured_model(
        MODEL_CONFIG,
        output_dir=tmp_path / "source_model_run",
    )
    return generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=tmp_path / "generated_dataset",
        noise_model=GaussianNoise(sigma=Q_(0.001, "kilogram"), seed=17),
        dataset_id="synthetic_first_order_for_calibration",
        source_config=MODEL_CONFIG,
    )


def _mapping() -> tuple[ObservableMapping, ...]:
    return (
        ObservableMapping(
            dataset_measurement_id="product_mass",
            model_observable="released_product_amount",
            observable_type="state",
        ),
    )
