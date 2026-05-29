from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.data import (
    ExperimentDatasetLoadError,
    MeasurementSeries,
    load_experiment_dataset,
)


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = (
    ROOT
    / "data"
    / "experiments"
    / "synthetic"
    / "first_order_ab"
    / "synthetic_first_order_ab.yml"
)


VALID_CSV = """time_s,product_mass_kg,product_mass_sigma_kg
0.0,0.000000,0.005000
10.0,0.181269,0.005000
"""


def _valid_dataset_mapping() -> dict[str, Any]:
    data = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _write_dataset_case(
    tmp_path: Path,
    data: dict[str, Any],
    *,
    csv_text: str | None = VALID_CSV,
) -> Path:
    dataset_path = tmp_path / "dataset.yml"
    measurements = cast(list[dict[str, Any]], data.get("measurements", []))
    if csv_text is not None and measurements:
        csv_path = tmp_path / "observations.csv"
        csv_path.write_text(csv_text, encoding="utf-8")
        measurements[0]["data_file"] = csv_path.name
    dataset_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return dataset_path


def test_valid_synthetic_dataset_loads() -> None:
    dataset = load_experiment_dataset(DATASET_PATH)

    assert dataset.dataset_id == "synthetic_first_order_ab_v1"
    assert dataset.maturity == "synthetic"
    assert dataset.source.source_type == "generated"
    assert dataset.source.generated_by == "FungMod synthetic dataset fixture"
    assert dataset.preprocessing.status == "generated"
    assert "known first-order" in dataset.preprocessing.steps[0]
    assert dataset.measurements

    series = dataset.measurements[0]
    assert isinstance(series, MeasurementSeries)
    assert series.measurement_id == "product_mass"
    assert series.time_units == "second"
    assert series.value_units == "kilogram"
    assert series.uncertainty_units == "kilogram"
    assert series.points[1].value == pytest.approx(0.181269)
    assert series.points[1].uncertainty == pytest.approx(0.005)


def test_valid_synthetic_dataset_validate_passes() -> None:
    dataset = load_experiment_dataset(DATASET_PATH)

    validation = dataset.validate()

    assert validation.passed
    assert validation.details["dataset_id"] == "synthetic_first_order_ab_v1"


def test_experiment_dataset_to_dict_is_json_safe() -> None:
    dataset = load_experiment_dataset(DATASET_PATH)

    encoded = json.dumps(dataset.to_dict())

    assert "synthetic_first_order_ab_v1" in encoded


def test_missing_kind_fails(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    data.pop("kind")
    dataset_path = _write_dataset_case(tmp_path, data)

    with pytest.raises(ExperimentDatasetLoadError, match="kind"):
        load_experiment_dataset(dataset_path)


def test_invalid_maturity_fails(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    data["maturity"] = "almost_scientific"
    dataset_path = _write_dataset_case(tmp_path, data)

    with pytest.raises(ExperimentDatasetLoadError, match="invalid maturity"):
        load_experiment_dataset(dataset_path)


def test_missing_source_fails(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    data.pop("source")
    dataset_path = _write_dataset_case(tmp_path, data)

    with pytest.raises(ExperimentDatasetLoadError, match="source"):
        load_experiment_dataset(dataset_path)


def test_missing_csv_file_fails(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    measurements = cast(list[dict[str, Any]], data["measurements"])
    measurements[0]["data_file"] = "missing_observations.csv"
    dataset_path = _write_dataset_case(tmp_path, data, csv_text=None)

    with pytest.raises(ExperimentDatasetLoadError, match="does not exist"):
        load_experiment_dataset(dataset_path)


def test_missing_value_column_fails(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    dataset_path = _write_dataset_case(
        tmp_path,
        data,
        csv_text="""time_s,product_mass_sigma_kg
0.0,0.005000
""",
    )

    with pytest.raises(ExperimentDatasetLoadError, match="product_mass_kg"):
        load_experiment_dataset(dataset_path)


def test_missing_uncertainty_column_fails_by_default(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    dataset_path = _write_dataset_case(
        tmp_path,
        data,
        csv_text="""time_s,product_mass_kg
0.0,0.000000
""",
    )

    with pytest.raises(ExperimentDatasetLoadError, match="product_mass_sigma_kg"):
        load_experiment_dataset(dataset_path)


def test_missing_uncertainty_column_can_be_explicitly_allowed(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    validation = cast(dict[str, Any], data["validation"])
    validation["allow_missing_uncertainty"] = True
    dataset_path = _write_dataset_case(
        tmp_path,
        data,
        csv_text="""time_s,product_mass_kg
0.0,0.000000
10.0,0.181269
""",
    )

    dataset = load_experiment_dataset(dataset_path)

    series = dataset.measurements[0]
    assert series.uncertainty_units == "kilogram"
    assert all(point.uncertainty is None for point in series.points)


def test_missing_value_units_fail(tmp_path: Path) -> None:
    data = _valid_dataset_mapping()
    measurements = cast(list[dict[str, Any]], data["measurements"])
    units = cast(dict[str, Any], measurements[0]["units"])
    units.pop("value")
    dataset_path = _write_dataset_case(tmp_path, data)

    with pytest.raises(ExperimentDatasetLoadError, match="value"):
        load_experiment_dataset(dataset_path)
