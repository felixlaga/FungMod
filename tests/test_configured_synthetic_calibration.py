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


def test_fitted_parameter_records_synthetic_only_provenance(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    result = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
    )

    fitted = result.fitted_parameters.get("k_ab")
    provenance_text = " ".join(
        (
            fitted.source,
            fitted.measurement_method,
            fitted.notes,
        )
    ).lower()
    assert "synthetic-only" in provenance_text
    assert dataset.dataset_id in provenance_text
    assert "least-squares" in provenance_text
    assert "not empirical validation" in provenance_text


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
    assert not result.split.has_holdout


@pytest.mark.parametrize("maturity", ["toy", "framework_benchmark", "calibrated", "validated"])
def test_configured_calibration_rejects_uncalibratable_maturity(tmp_path: Path, maturity: str) -> None:
    """Only synthetic and literature datasets may be fitted; everything else fails closed."""

    dataset = replace(_generated_dataset(tmp_path), maturity=maturity)

    with pytest.raises(ConfiguredCalibrationError, match="rejects dataset maturity"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=["k_ab"],
            observable_mapping=_mapping(),
            initial_guess={"k_ab": 0.03},
            bounds={"k_ab": (0.0, 1.0)},
        )


@pytest.mark.parametrize("maturity", ["literature_raw", "literature_processed"])
def test_literature_calibration_is_labelled_as_estimation_not_validation(
    tmp_path: Path, maturity: str
) -> None:
    """A literature fit must never inherit the synthetic fixture wording."""

    dataset = replace(_generated_dataset(tmp_path), maturity=maturity)

    result = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
    )

    assert result.dataset_maturity == maturity
    assert result.to_dict()["dataset_maturity"] == maturity
    assert any("parameter estimation, not validation" in item for item in result.assumptions)
    assert any("not evidence of predictive validity" in item for item in result.warnings)
    # The synthetic-fixture claims must not appear on a literature calibration.
    assert not any("Synthetic-only calibration" in item for item in result.assumptions)
    assert not any(
        "No real fungal biology or literature data" in item for item in result.assumptions
    )


def test_synthetic_calibration_keeps_its_synthetic_labelling(tmp_path: Path) -> None:
    result = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=_generated_dataset(tmp_path),
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
    )

    assert result.dataset_maturity == "synthetic"
    assert any("Synthetic-only calibration" in item for item in result.assumptions)
    assert not any("parameter estimation, not validation" in item for item in result.assumptions)


def test_configured_calibration_rejects_missing_parameter_symbols(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    with pytest.raises(ConfiguredCalibrationError, match="At least one parameter symbol"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=[],
            observable_mapping=_mapping(),
            initial_guess={},
        )


def test_configured_calibration_rejects_missing_initial_guess(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    with pytest.raises(ConfiguredCalibrationError, match="Missing initial guesses"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=["k_ab"],
            observable_mapping=_mapping(),
            initial_guess={},
        )


def test_configured_calibration_rejects_bad_bounds(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    with pytest.raises(ConfiguredCalibrationError, match="lower < upper"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=["k_ab"],
            observable_mapping=_mapping(),
            initial_guess={"k_ab": 0.03},
            bounds={"k_ab": (1.0, 0.0)},
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


def test_train_validation_split_rejects_fraction_sum_over_one(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    with pytest.raises(ConfiguredCalibrationError, match="<= 1"):
        calibrate_configured_model(
            model_config=MODEL_CONFIG,
            dataset=dataset,
            parameter_symbols=["k_ab"],
            observable_mapping=_mapping(),
            initial_guess={"k_ab": 0.03},
            bounds={"k_ab": (0.0, 1.0)},
            split={"method": "by_time", "train_fraction": 0.8, "validation_fraction": 0.3},
        )


def test_train_validation_split_records_holdout_when_fractions_leave_unused_points(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    result = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
        split={"method": "by_time", "train_fraction": 0.6, "validation_fraction": 0.2},
    )

    assert result.split is not None
    train = set(result.split.train_indices["product_mass"])
    validation = set(result.split.validation_indices["product_mass"])
    holdout = set(result.split.holdout_indices["product_mass"])
    assert train
    assert validation
    assert holdout
    assert not train.intersection(validation)
    assert not train.intersection(holdout)
    assert not validation.intersection(holdout)
    assert result.split.has_holdout


def test_validation_fraction_controls_validation_set_size(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    smaller = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
        split={"method": "by_time", "train_fraction": 0.6, "validation_fraction": 0.2},
    )
    larger = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
        split={"method": "by_time", "train_fraction": 0.6, "validation_fraction": 0.4},
    )

    assert smaller.split is not None
    assert larger.split is not None
    assert len(smaller.split.validation_indices["product_mass"]) == 2
    assert len(larger.split.validation_indices["product_mass"]) == 5


def test_validation_metrics_only_appear_when_validation_split_exists(tmp_path: Path) -> None:
    dataset = _generated_dataset(tmp_path)

    no_split = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
    )
    with_split = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
        split={"method": "by_time", "train_fraction": 0.7, "validation_fraction": 0.3},
    )

    assert "validation_rmse" not in no_split.metrics
    assert "validation_rmse" in with_split.metrics


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


def test_configured_calibration_resolves_config_paths_outside_repository_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _generated_dataset(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = calibrate_configured_model(
        model_config=MODEL_CONFIG,
        dataset=dataset,
        parameter_symbols=["k_ab"],
        observable_mapping=_mapping(),
        initial_guess={"k_ab": 0.03},
        bounds={"k_ab": (0.0, 1.0)},
        split={"method": "by_time", "train_fraction": 0.7, "validation_fraction": 0.3},
        output_dir=tmp_path / "calibration_outside_root",
    )

    assert result.success
    assert result.fitted_parameters.get("k_ab").quantity.to("1 / second").magnitude == pytest.approx(0.1, rel=0.05)


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
