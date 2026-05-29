from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.data import ExperimentDatasetLoadError, load_experiment_dataset


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
1.0,0.095163,0.005000
"""


def _valid_data() -> dict[str, Any]:
    data = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _write_case(tmp_path: Path, data: dict[str, Any], csv_text: str = VALID_CSV) -> Path:
    path = tmp_path / "dataset.yml"
    csv_path = tmp_path / "observations.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    measurements = cast(list[dict[str, Any]], data["measurements"])
    for measurement in measurements:
        measurement["data_file"] = csv_path.name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_dataset_validation_rules_pass_for_valid_dataset() -> None:
    dataset = load_experiment_dataset(DATASET_PATH)

    assert dataset.validate().passed


def test_bad_units_fail(tmp_path: Path) -> None:
    data = _valid_data()
    units = cast(dict[str, Any], cast(list[dict[str, Any]], data["measurements"])[0]["units"])
    units["value"] = "not_a_unit"

    with pytest.raises(ExperimentDatasetLoadError, match="Value units"):
        load_experiment_dataset(_write_case(tmp_path, data))


def test_nonfinite_value_fails(tmp_path: Path) -> None:
    data = _valid_data()

    with pytest.raises(ExperimentDatasetLoadError, match="finite"):
        load_experiment_dataset(
            _write_case(
                tmp_path,
                data,
                csv_text="""time_s,product_mass_kg,product_mass_sigma_kg
0.0,nan,0.005000
1.0,0.095163,0.005000
""",
            )
        )


def test_negative_time_fails(tmp_path: Path) -> None:
    data = _valid_data()

    with pytest.raises(ExperimentDatasetLoadError, match="nonnegative"):
        load_experiment_dataset(
            _write_case(
                tmp_path,
                data,
                csv_text="""time_s,product_mass_kg,product_mass_sigma_kg
-1.0,0.000000,0.005000
1.0,0.095163,0.005000
""",
            )
        )


def test_nonmonotonic_time_fails(tmp_path: Path) -> None:
    data = _valid_data()

    with pytest.raises(ExperimentDatasetLoadError, match="strictly increasing"):
        load_experiment_dataset(
            _write_case(
                tmp_path,
                data,
                csv_text="""time_s,product_mass_kg,product_mass_sigma_kg
1.0,0.095163,0.005000
0.0,0.000000,0.005000
""",
            )
        )


def test_negative_uncertainty_fails(tmp_path: Path) -> None:
    data = _valid_data()

    with pytest.raises(ExperimentDatasetLoadError, match="nonnegative"):
        load_experiment_dataset(
            _write_case(
                tmp_path,
                data,
                csv_text="""time_s,product_mass_kg,product_mass_sigma_kg
0.0,0.000000,-0.005000
1.0,0.095163,0.005000
""",
            )
        )


def test_duplicate_measurement_ids_fail(tmp_path: Path) -> None:
    data = _valid_data()
    measurements = cast(list[dict[str, Any]], data["measurements"])
    measurements.append(dict(measurements[0]))

    with pytest.raises(ExperimentDatasetLoadError, match="unique"):
        load_experiment_dataset(_write_case(tmp_path, data))


def test_missing_preprocessing_notes_fail(tmp_path: Path) -> None:
    data = _valid_data()
    preprocessing = cast(dict[str, Any], data["preprocessing"])
    preprocessing["notes"] = ""

    with pytest.raises(ExperimentDatasetLoadError, match="Preprocessing notes"):
        load_experiment_dataset(_write_case(tmp_path, data))
