from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from fungal_model.data import (
    load_experiment_dataset,
    validate_literature_dataset_metadata,
)
from fungal_model.resources import example_data_path


ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    ROOT
    / "data"
    / "experiments"
    / "literature"
    / "alvarez_gonzalez_2022_free_beta_glucosidase"
    / "alvarez_gonzalez_2022_free_beta_glucosidase.yml"
)


def test_alvarez_gonzalez_time_course_passes_literature_and_dataset_schemas() -> None:
    metadata = yaml.safe_load(DATASET.read_text(encoding="utf-8"))
    literature_validation = validate_literature_dataset_metadata(metadata)[0]
    dataset = load_experiment_dataset(DATASET)

    assert literature_validation.passed, literature_validation.details
    assert dataset.validate().passed
    assert dataset.dataset_id == (
        "alvarez_gonzalez_2022_free_beta_glucosidase_cellobiose_20gl_v1"
    )
    assert dataset.maturity == "literature_raw"
    assert dataset.source.doi == "10.3390/catal12010080"
    assert dataset.system.organism is None
    assert "biological source organism" in dataset.system.notes


def test_alvarez_gonzalez_time_course_preserves_digitized_points_and_scope() -> None:
    dataset = load_experiment_dataset(DATASET)
    series = dataset.measurements[0]

    assert series.measurement_id == "cellobiose_concentration"
    assert series.time_units == "minute"
    assert series.value_units == "millimolar"
    assert series.uncertainty_type == (
        "estimated digitization error, not experimental uncertainty"
    )
    assert [point.time for point in series.points] == [
        0.0,
        5.0,
        10.0,
        15.0,
        20.0,
        30.0,
        40.0,
        50.0,
        60.0,
    ]
    assert series.points[0].value == pytest.approx(62.455)
    assert series.points[-1].value == pytest.approx(5.182)
    assert all(point.uncertainty == pytest.approx(0.6) for point in series.points)
    assert "not whole-fungus" in dataset.notes


def test_alvarez_gonzalez_digitization_is_recomputable_from_recorded_pixels() -> None:
    dataset = load_experiment_dataset(DATASET)
    series = dataset.measurements[0]
    metadata = yaml.safe_load(DATASET.read_text(encoding="utf-8"))
    csv_path = DATASET.parent / series.data_file
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert metadata["digitization"]["included_points"] == len(rows) == 9
    for row, point in zip(rows, series.points, strict=True):
        y_pixel = float(row["marker_center_y_pixel"])
        recomputed = (724.0 - y_pixel) * 240.0 / 440.0
        assert point.value == pytest.approx(recomputed, abs=0.0006)


def test_alvarez_gonzalez_dataset_resolves_from_the_canonical_resource_contract() -> None:
    relative_yaml = DATASET.relative_to(ROOT / "data")
    csv_path = DATASET.parent / "alvarez_gonzalez_2022_figure_s1a_filled_squares.csv"
    relative_csv = csv_path.relative_to(ROOT / "data")

    assert example_data_path(relative_yaml).read_bytes() == DATASET.read_bytes()
    assert example_data_path(relative_csv).read_bytes() == csv_path.read_bytes()
