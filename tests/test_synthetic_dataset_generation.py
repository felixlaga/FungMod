from __future__ import annotations

import json
from pathlib import Path

import pytest

from fungal_model import run_configured_model
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, UnitError
from fungal_model.data import (
    GaussianNoise,
    ObservableMapping,
    SyntheticDatasetGenerationError,
    evaluate_model_against_dataset,
    generate_synthetic_dataset_from_result,
    load_experiment_dataset,
)
from fungal_model.results import SimulationResult


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_generate_synthetic_dataset_writes_reloadable_bundle(tmp_path: Path) -> None:
    result = _result(times=[0.0, 1.0, 2.0], values=[0.0, 1.0, 2.0])

    dataset = generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=tmp_path,
        noise_model=GaussianNoise(sigma=Q_(0.0, "kilogram"), seed=11),
        dataset_id="synthetic_generated_first_order",
        name="Synthetic generated first-order benchmark",
        source_config="data/model_configs/toy_homogeneous_ab.yml",
    )

    yaml_path = tmp_path / "synthetic_generated_first_order.yml"
    csv_path = tmp_path / "synthetic_generated_first_order_observations.csv"
    record_path = tmp_path / "generation_record.json"

    assert yaml_path.exists()
    assert csv_path.exists()
    assert record_path.exists()
    assert dataset.maturity == "synthetic"
    assert dataset.source.generated_by == "FungMod synthetic dataset generator"
    assert dataset.measurements[0].time_units == "second"
    assert dataset.measurements[0].value_units == "kilogram"
    assert dataset.measurements[0].uncertainty_units == "kilogram"

    reloaded = load_experiment_dataset(yaml_path)
    assert reloaded.validate().passed
    assert reloaded.measurements[0].points[-1].value == pytest.approx(2.0)


def test_generation_with_same_seed_is_reproducible(tmp_path: Path) -> None:
    result = _result(times=[0.0, 1.0, 2.0], values=[0.0, 1.0, 2.0])
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=first,
        noise_model=GaussianNoise(sigma=Q_(0.1, "kilogram"), seed=42),
        dataset_id="synthetic_reproducible",
    )
    generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=second,
        noise_model=GaussianNoise(sigma=Q_(0.1, "kilogram"), seed=42),
        dataset_id="synthetic_reproducible",
    )

    assert (first / "synthetic_reproducible_observations.csv").read_text(encoding="utf-8") == (
        second / "synthetic_reproducible_observations.csv"
    ).read_text(encoding="utf-8")


def test_generation_with_different_seed_changes_observations(tmp_path: Path) -> None:
    result = _result(times=[0.0, 1.0, 2.0], values=[0.0, 1.0, 2.0])
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=first,
        noise_model=GaussianNoise(sigma=Q_(0.1, "kilogram"), seed=1),
        dataset_id="synthetic_seeded",
    )
    generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=second,
        noise_model=GaussianNoise(sigma=Q_(0.1, "kilogram"), seed=2),
        dataset_id="synthetic_seeded",
    )

    assert (first / "synthetic_seeded_observations.csv").read_text(encoding="utf-8") != (
        second / "synthetic_seeded_observations.csv"
    ).read_text(encoding="utf-8")


def test_generated_dataset_compares_against_original_result(tmp_path: Path) -> None:
    result = run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=tmp_path / "model_run",
    )
    dataset = generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=tmp_path / "dataset",
        noise_model=GaussianNoise(sigma=Q_(0.0, "kilogram"), seed=123),
        dataset_id="synthetic_from_configured_result",
        source_config=MODEL_CONFIGS / "toy_homogeneous_ab.yml",
    )

    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=_mapping(),
    )

    assert comparison.metrics["rmse"] == pytest.approx(0.0)
    assert "chi_square" not in comparison.metrics
    assert any(validation.name == "invalid_uncertainty" for validation in comparison.validation_results)


def test_generation_record_preserves_metadata_and_true_values(tmp_path: Path) -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0])

    generate_synthetic_dataset_from_result(
        result=result,
        observable_mapping=_mapping(),
        output_dir=tmp_path,
        noise_model=GaussianNoise(sigma=Q_(0.05, "kilogram"), seed=77),
        dataset_id="synthetic_recorded",
        source_config="data/model_configs/toy_homogeneous_ab.yml",
    )

    record = json.loads((tmp_path / "generation_record.json").read_text(encoding="utf-8"))

    assert record["kind"] == "synthetic_generation_record"
    assert record["dataset_id"] == "synthetic_recorded"
    assert record["noise_model"]["type"] == "gaussian"
    assert record["noise_model"]["seed"] == 77
    assert record["noise_model"]["sigma"]["units"] == "kilogram"
    assert record["source_config"] == "data/model_configs/toy_homogeneous_ab.yml"
    assert record["observable_mapping"][0]["dataset_measurement_id"] == "product_mass"
    assert record["true_values"]["product_mass"]["values"] == [0.0, 1.0]
    assert "not empirical evidence" in record["notes"]


def test_generation_rejects_incompatible_noise_units(tmp_path: Path) -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0])

    with pytest.raises(UnitError):
        generate_synthetic_dataset_from_result(
            result=result,
            observable_mapping=_mapping(),
            output_dir=tmp_path,
            noise_model=GaussianNoise(sigma=Q_(0.1, "second"), seed=1),
            dataset_id="bad_noise_units",
        )


def test_generation_rejects_missing_model_observable(tmp_path: Path) -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0])

    with pytest.raises(SyntheticDatasetGenerationError, match="not present"):
        generate_synthetic_dataset_from_result(
            result=result,
            observable_mapping=[
                ObservableMapping(
                    dataset_measurement_id="product_mass",
                    model_observable="missing_state",
                    observable_type="state",
                )
            ],
            output_dir=tmp_path,
            noise_model=GaussianNoise(sigma=Q_(0.1, "kilogram"), seed=1),
            dataset_id="missing_model_state",
        )


def _mapping() -> tuple[ObservableMapping, ...]:
    return (
        ObservableMapping(
            dataset_measurement_id="product_mass",
            model_observable="released_product_amount",
            observable_type="state",
        ),
    )


def _result(*, times: list[float], values: list[float]) -> SimulationResult:
    return SimulationResult(
        time=Q_(times, "second"),
        states={"released_product_amount": Q_(values, "kilogram")},
        parameters=ParameterSet(),
        assumptions=(),
        solver_settings=SolverSettings(),
        name="synthetic_generation_test_model",
        label="toy",
    )
