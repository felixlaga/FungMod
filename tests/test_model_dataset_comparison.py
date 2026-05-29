from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from fungal_model import run_configured_model
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, UnitError
from fungal_model.data import (
    DataSource,
    ExperimentDataset,
    ExperimentalConditions,
    ExperimentalSystem,
    MeasurementPoint,
    MeasurementSeries,
    ModelDatasetComparisonError,
    ObservableMapping,
    PreprocessingRecord,
    evaluate_model_against_dataset,
    load_experiment_dataset,
)
from fungal_model.results import SimulationResult


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_DATASET = (
    ROOT
    / "data"
    / "experiments"
    / "synthetic"
    / "first_order_ab"
    / "synthetic_first_order_ab.yml"
)
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_configured_model_result_compares_to_synthetic_dataset(tmp_path: Path) -> None:
    result = run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=tmp_path / "model_run",
    )
    dataset = load_experiment_dataset(SYNTHETIC_DATASET)

    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=[
            ObservableMapping(
                dataset_measurement_id="product_mass",
                model_observable="released_product_amount",
                observable_type="state",
            )
        ],
    )

    assert comparison.dataset_id == "synthetic_first_order_ab_v1"
    assert comparison.metrics["rmse"] < 1.0e-5
    assert comparison.metrics["chi_square"] < 1.0e-5
    assert all(validation.passed for validation in comparison.validation_results)


def test_identity_mapping_exact_times_computes_residuals_and_metrics() -> None:
    result = _result(times=[0.0, 1.0, 2.0], values=[0.0, 1.0, 2.0], units="kilogram")
    dataset = _dataset(
        points=[
            MeasurementPoint(time=0.0, value=0.0, uncertainty=0.1),
            MeasurementPoint(time=1.0, value=1.0, uncertainty=0.1),
            MeasurementPoint(time=2.0, value=2.0, uncertainty=0.1),
        ],
    )

    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping={"product_mass": "released_product_amount"},
    )

    assert comparison.metrics["rmse"] == pytest.approx(0.0)
    assert comparison.metrics["chi_square"] == pytest.approx(0.0)
    assert comparison.residuals[0].points[1].standardized_residual == pytest.approx(0.0)


def test_interpolation_computes_predictions_between_model_times() -> None:
    result = _result(times=[0.0, 2.0], values=[0.0, 2.0], units="kilogram")
    dataset = _dataset(points=[MeasurementPoint(time=1.0, value=1.0, uncertainty=0.2)])

    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=[
            ObservableMapping(
                dataset_measurement_id="product_mass",
                model_observable="released_product_amount",
                observable_type="state",
            )
        ],
    )

    point = comparison.residuals[0].points[0]
    assert point.predicted == pytest.approx(1.0)
    assert point.residual == pytest.approx(0.0)


def test_unit_conversion_mapping_converts_model_units() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1000.0], units="gram")
    dataset = _dataset(
        points=[
            MeasurementPoint(time=0.0, value=0.0, uncertainty=0.01),
            MeasurementPoint(time=1.0, value=1.0, uncertainty=0.01),
        ],
    )

    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=[
            ObservableMapping(
                dataset_measurement_id="product_mass",
                model_observable="released_product_amount",
                observable_type="state",
                transform="unit_conversion",
                model_units="gram",
            )
        ],
    )

    assert comparison.residuals[0].points[-1].predicted == pytest.approx(1.0)
    assert comparison.metrics["rmse"] == pytest.approx(0.0)


def test_missing_model_observable_fails() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0], units="kilogram")
    dataset = _dataset(points=[MeasurementPoint(time=1.0, value=1.0, uncertainty=0.1)])

    with pytest.raises(ModelDatasetComparisonError, match="not present"):
        evaluate_model_against_dataset(
            result=result,
            dataset=dataset,
            observable_mapping=[
                ObservableMapping(
                    dataset_measurement_id="product_mass",
                    model_observable="missing_state",
                    observable_type="state",
                )
            ],
        )


def test_missing_dataset_measurement_fails() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0], units="kilogram")
    dataset = _dataset(points=[MeasurementPoint(time=1.0, value=1.0, uncertainty=0.1)])

    with pytest.raises(ModelDatasetComparisonError, match="not present"):
        evaluate_model_against_dataset(
            result=result,
            dataset=dataset,
            observable_mapping=[
                ObservableMapping(
                    dataset_measurement_id="missing_measurement",
                    model_observable="released_product_amount",
                    observable_type="state",
                )
            ],
        )


def test_incompatible_unit_failure() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0], units="kilogram")
    dataset = _dataset(
        value_units="second",
        points=[MeasurementPoint(time=1.0, value=1.0, uncertainty=0.1)],
    )

    with pytest.raises(UnitError):
        evaluate_model_against_dataset(
            result=result,
            dataset=dataset,
            observable_mapping=[
                ObservableMapping(
                    dataset_measurement_id="product_mass",
                    model_observable="released_product_amount",
                    observable_type="state",
                )
            ],
        )


def test_fractional_conversion_requires_initial_value() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 0.5], units="kilogram")
    dataset = _dataset(
        value_units="dimensionless",
        uncertainty_units="dimensionless",
        points=[MeasurementPoint(time=1.0, value=0.5, uncertainty=0.01)],
    )

    with pytest.raises(ModelDatasetComparisonError, match="initial_value"):
        evaluate_model_against_dataset(
            result=result,
            dataset=dataset,
            observable_mapping=[
                ObservableMapping(
                    dataset_measurement_id="product_mass",
                    model_observable="released_product_amount",
                    observable_type="state",
                    transform="fractional_conversion",
                )
            ],
        )


def test_fractional_conversion_compares_dimensionless_observations() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 0.5], units="kilogram")
    dataset = _dataset(
        value_units="dimensionless",
        uncertainty_units="dimensionless",
        points=[MeasurementPoint(time=1.0, value=0.5, uncertainty=0.01)],
    )

    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=[
            ObservableMapping(
                dataset_measurement_id="product_mass",
                model_observable="released_product_amount",
                observable_type="state",
                transform="fractional_conversion",
                initial_value=1.0,
                initial_units="kilogram",
            )
        ],
    )

    assert comparison.residuals[0].points[0].predicted == pytest.approx(0.5)


def test_extrapolation_fails() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0], units="kilogram")
    dataset = _dataset(points=[MeasurementPoint(time=2.0, value=2.0, uncertainty=0.1)])

    with pytest.raises(ModelDatasetComparisonError, match="extrapolation"):
        evaluate_model_against_dataset(
            result=result,
            dataset=dataset,
            observable_mapping=[
                ObservableMapping(
                    dataset_measurement_id="product_mass",
                    model_observable="released_product_amount",
                    observable_type="state",
                )
            ],
        )


def test_missing_uncertainty_warns_without_standardized_residuals() -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0], units="kilogram")
    dataset = _dataset(points=[MeasurementPoint(time=1.0, value=1.0, uncertainty=None)])

    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=[
            ObservableMapping(
                dataset_measurement_id="product_mass",
                model_observable="released_product_amount",
                observable_type="state",
            )
        ],
    )

    assert "chi_square" not in comparison.metrics
    assert comparison.residuals[0].points[0].standardized_residual is None
    assert any(validation.name == "missing_uncertainty" for validation in comparison.validation_results)


def test_comparison_save_writes_output_bundle(tmp_path: Path) -> None:
    result = _result(times=[0.0, 1.0], values=[0.0, 1.0], units="kilogram")
    dataset = _dataset(points=[MeasurementPoint(time=1.0, value=1.0, uncertainty=0.1)])
    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=[
            ObservableMapping(
                dataset_measurement_id="product_mass",
                model_observable="released_product_amount",
                observable_type="state",
            )
        ],
    )

    comparison.save(tmp_path)

    expected_files = (
        "comparison_record.json",
        "dataset_snapshot.json",
        "observable_mapping.json",
        "residuals.csv",
        "metrics.json",
        "validation_report.json",
        "figures/observed_vs_predicted.png",
        "figures/residuals.png",
    )
    for relative_path in expected_files:
        assert (tmp_path / relative_path).exists(), relative_path
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["rmse"] == pytest.approx(0.0)
    rows = list(csv.DictReader((tmp_path / "residuals.csv").open(encoding="utf-8")))
    assert rows[0]["measurement_id"] == "product_mass"


def _result(
    *,
    times: list[float],
    values: list[float],
    units: str,
    state_name: str = "released_product_amount",
) -> SimulationResult:
    return SimulationResult(
        time=Q_(times, "second"),
        states={state_name: Q_(values, units)},
        parameters=ParameterSet(),
        assumptions=(),
        solver_settings=SolverSettings(),
        name="comparison_test_model",
        label="toy",
    )


def _dataset(
    *,
    points: list[MeasurementPoint],
    value_units: str = "kilogram",
    uncertainty_units: str = "kilogram",
) -> ExperimentDataset:
    return ExperimentDataset(
        name="Synthetic comparison dataset",
        dataset_id="synthetic_comparison_dataset",
        maturity="synthetic",
        source=DataSource(
            source_type="generated",
            generated_by="test fixture",
            notes="Synthetic comparison test dataset.",
        ),
        system=ExperimentalSystem(
            substrate="generic dissolved substrate A",
            product="released product B",
            geometry="well_mixed",
            notes="No biology represented.",
        ),
        conditions=ExperimentalConditions(values={"notes": "Synthetic comparison conditions."}),
        measurements=(
            MeasurementSeries(
                measurement_id="product_mass",
                measured_quantity="released_product_amount",
                observable_type="state",
                data_file="inline.csv",
                time_column="time_s",
                value_column="product_mass",
                uncertainty_column="product_mass_sigma",
                time_units="second",
                value_units=value_units,
                uncertainty_units=uncertainty_units,
                uncertainty_type="standard_deviation",
                points=tuple(points),
            ),
        ),
        preprocessing=PreprocessingRecord(
            status="generated",
            raw_data_available=True,
            steps=("constructed directly in unit tests",),
            notes="No literature preprocessing.",
        ),
        validation={"allow_missing_uncertainty": any(point.uncertainty is None for point in points)},
    )
