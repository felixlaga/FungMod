"""Load experiment datasets from YAML plus measurement CSV files."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml

from fungal_model.data.datasets import (
    ALLOWED_DATASET_MATURITIES,
    DataSource,
    ExperimentDataset,
    ExperimentalConditions,
    ExperimentalSystem,
    MeasurementPoint,
    MeasurementSeries,
    PreprocessingRecord,
)


class ExperimentDatasetLoadError(ValueError):
    """Raised when an experiment dataset file is structurally invalid."""


def load_experiment_dataset(path: str | Path) -> ExperimentDataset:
    """Load an experiment dataset YAML file and all referenced measurement CSVs."""

    dataset_path = Path(path)
    data = _load_yaml_mapping(dataset_path)
    if data.get("kind") != "experiment_dataset":
        raise ExperimentDatasetLoadError(
            f"{dataset_path} must set kind: experiment_dataset for the dataset loader."
        )

    maturity = _required_str(data, "maturity", dataset_path)
    if maturity not in ALLOWED_DATASET_MATURITIES:
        raise ExperimentDatasetLoadError(
            f"{dataset_path} has invalid maturity {maturity!r}; "
            f"expected one of {sorted(ALLOWED_DATASET_MATURITIES)}."
        )

    source_data = _required_mapping(data, "source", dataset_path)
    system_data = _required_mapping(data, "system", dataset_path)
    conditions_data = _required_mapping(data, "conditions", dataset_path)
    preprocessing_data = _required_mapping(data, "preprocessing", dataset_path)
    validation_data = _required_mapping(data, "validation", dataset_path)
    measurement_items = _required_sequence(data, "measurements", dataset_path)
    if not measurement_items:
        raise ExperimentDatasetLoadError(f"{dataset_path} must define at least one measurement series.")

    expected_columns = _required_string_sequence(validation_data, "expected_columns", dataset_path)
    allow_missing_uncertainty = _required_bool(
        validation_data,
        "allow_missing_uncertainty",
        dataset_path,
        default=False,
    )
    measurements = tuple(
        _load_measurement_series(
            item,
            dataset_path=dataset_path,
            expected_columns=expected_columns,
            allow_missing_uncertainty=allow_missing_uncertainty,
        )
        for item in measurement_items
    )

    dataset = ExperimentDataset(
        name=_required_str(data, "name", dataset_path),
        dataset_id=_required_str(data, "dataset_id", dataset_path),
        maturity=maturity,
        source=_data_source(source_data, dataset_path),
        system=_experimental_system(system_data),
        conditions=ExperimentalConditions(values=dict(conditions_data)),
        measurements=measurements,
        preprocessing=_preprocessing_record(preprocessing_data, dataset_path),
        notes=_optional_str(data.get("notes")) or "",
        path=dataset_path,
        validation=dict(validation_data),
    )
    validation = dataset.validate()
    if not validation.passed:
        raise ExperimentDatasetLoadError(f"{dataset_path} failed validation: {validation.details}")
    return dataset


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise ExperimentDatasetLoadError(f"Experiment dataset file does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ExperimentDatasetLoadError(f"Experiment dataset YAML must be a mapping: {path}")
    return cast(Mapping[str, Any], data)


def _required_mapping(data: Mapping[str, Any], key: str, path: Path) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ExperimentDatasetLoadError(f"{path} must define a mapping at {key!r}.")
    return cast(Mapping[str, Any], value)


def _required_sequence(data: Mapping[str, Any], key: str, path: Path) -> Sequence[Any]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ExperimentDatasetLoadError(f"{path} must define a sequence at {key!r}.")
    return value


def _required_string_sequence(data: Mapping[str, Any], key: str, path: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ExperimentDatasetLoadError(f"{path} must define a string sequence at {key!r}.")
    items = tuple(_optional_str(item) for item in value)
    if any(item is None or item == "" for item in items):
        raise ExperimentDatasetLoadError(f"{path} has an empty value in {key!r}.")
    return cast(tuple[str, ...], items)


def _required_bool(data: Mapping[str, Any], key: str, path: Path, *, default: bool | None = None) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ExperimentDatasetLoadError(f"{path} must define a boolean at {key!r}.")
    return value


def _required_str(data: Mapping[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExperimentDatasetLoadError(f"{path} must define a non-empty string at {key!r}.")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _data_source(data: Mapping[str, Any], path: Path) -> DataSource:
    return DataSource(
        source_type=_required_str(data, "type", path),
        citation=_optional_str(data.get("citation")),
        doi=_optional_str(data.get("doi")),
        url=_optional_str(data.get("url")),
        generated_by=_optional_str(data.get("generated_by")),
        generation_config=_optional_str(data.get("generation_config")),
        generation_commit=_optional_str(data.get("generation_commit")),
        notes=_optional_str(data.get("notes")) or "",
    )


def _experimental_system(data: Mapping[str, Any]) -> ExperimentalSystem:
    return ExperimentalSystem(
        organism=_optional_str(data.get("organism")),
        enzyme=_optional_str(data.get("enzyme")),
        substrate=_optional_str(data.get("substrate")),
        product=_optional_str(data.get("product")),
        environment=_optional_str(data.get("environment")),
        geometry=_optional_str(data.get("geometry")),
        notes=_optional_str(data.get("notes")) or "",
    )


def _preprocessing_record(data: Mapping[str, Any], path: Path) -> PreprocessingRecord:
    raw_data_available = _required_bool(data, "raw_data_available", path)
    return PreprocessingRecord(
        status=_required_str(data, "status", path),
        raw_data_available=raw_data_available,
        steps=_optional_string_tuple(data.get("steps"), "preprocessing.steps", path),
        excluded_points=_optional_string_tuple(data.get("excluded_points"), "preprocessing.excluded_points", path),
        notes=_optional_str(data.get("notes")) or "",
    )


def _optional_string_tuple(value: Any, name: str, path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ExperimentDatasetLoadError(f"{path} must define a string sequence at {name!r}.")
    result = tuple(_optional_str(item) or "" for item in value)
    if any(item == "" for item in result):
        raise ExperimentDatasetLoadError(f"{path} has an empty value in {name!r}.")
    return result


def _load_measurement_series(
    item: Any,
    *,
    dataset_path: Path,
    expected_columns: Sequence[str],
    allow_missing_uncertainty: bool,
) -> MeasurementSeries:
    if not isinstance(item, Mapping):
        raise ExperimentDatasetLoadError(f"{dataset_path} measurement entries must be mappings.")
    measurement_data = cast(Mapping[str, Any], item)
    units = _required_mapping(measurement_data, "units", dataset_path)
    measurement_id = _required_str(measurement_data, "id", dataset_path)
    time_column = _required_str(measurement_data, "time_column", dataset_path)
    value_column = _required_str(measurement_data, "value_column", dataset_path)
    uncertainty_column = _optional_str(measurement_data.get("uncertainty_column"))
    time_units = _required_str(units, "time", dataset_path)
    value_units = _required_str(units, "value", dataset_path)
    uncertainty_units = _optional_str(units.get("uncertainty"))
    if uncertainty_column is None and not allow_missing_uncertainty:
        raise ExperimentDatasetLoadError(
            f"{dataset_path} measurement {measurement_id!r} must define uncertainty_column "
            "unless validation.allow_missing_uncertainty is true."
        )
    if uncertainty_column is not None and uncertainty_units is None:
        raise ExperimentDatasetLoadError(
            f"{dataset_path} measurement {measurement_id!r} must define units.uncertainty "
            "when an uncertainty column is configured."
        )

    data_file = _required_str(measurement_data, "data_file", dataset_path)
    csv_path = (dataset_path.parent / data_file).resolve()
    points = _load_points(
        csv_path,
        measurement_id=measurement_id,
        time_column=time_column,
        value_column=value_column,
        uncertainty_column=uncertainty_column,
        expected_columns=expected_columns,
        allow_missing_uncertainty=allow_missing_uncertainty,
    )
    return MeasurementSeries(
        measurement_id=measurement_id,
        measured_quantity=_required_str(measurement_data, "measured_quantity", dataset_path),
        observable_type=_required_str(measurement_data, "observable_type", dataset_path),
        data_file=data_file,
        data_path=csv_path,
        time_column=time_column,
        value_column=value_column,
        uncertainty_column=uncertainty_column,
        time_units=time_units,
        value_units=value_units,
        uncertainty_units=uncertainty_units,
        uncertainty_type=_optional_str(measurement_data.get("uncertainty_type")),
        censoring=_optional_str(measurement_data.get("censoring")) or "none",
        replicate_id_column=_optional_str(measurement_data.get("replicate_id_column")),
        notes=_optional_str(measurement_data.get("notes")) or "",
        points=points,
    )


def _load_points(
    csv_path: Path,
    *,
    measurement_id: str,
    time_column: str,
    value_column: str,
    uncertainty_column: str | None,
    expected_columns: Sequence[str],
    allow_missing_uncertainty: bool,
) -> tuple[MeasurementPoint, ...]:
    if not csv_path.exists():
        raise ExperimentDatasetLoadError(f"Measurement CSV file does not exist: {csv_path}")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if not fieldnames:
            raise ExperimentDatasetLoadError(f"Measurement CSV file has no header: {csv_path}")

        required_columns = {time_column, value_column}
        for column in expected_columns:
            if column == uncertainty_column and allow_missing_uncertainty:
                continue
            required_columns.add(column)
        if uncertainty_column is not None and not allow_missing_uncertainty:
            required_columns.add(uncertainty_column)
        missing_columns = sorted(required_columns.difference(fieldnames))
        if missing_columns:
            raise ExperimentDatasetLoadError(
                f"Measurement {measurement_id!r} CSV {csv_path} is missing expected columns: "
                f"{', '.join(missing_columns)}"
            )

        points = [
            _point_from_row(
                row,
                row_number=row_number,
                csv_path=csv_path,
                time_column=time_column,
                value_column=value_column,
                uncertainty_column=uncertainty_column,
                uncertainty_available=uncertainty_column in fieldnames if uncertainty_column is not None else False,
                allow_missing_uncertainty=allow_missing_uncertainty,
            )
            for row_number, row in enumerate(reader, start=2)
        ]
    if not points:
        raise ExperimentDatasetLoadError(f"Measurement {measurement_id!r} CSV {csv_path} has no data rows.")
    return tuple(points)


def _point_from_row(
    row: Mapping[str, str | None],
    *,
    row_number: int,
    csv_path: Path,
    time_column: str,
    value_column: str,
    uncertainty_column: str | None,
    uncertainty_available: bool,
    allow_missing_uncertainty: bool,
) -> MeasurementPoint:
    uncertainty: float | None = None
    if uncertainty_column is not None and uncertainty_available:
        raw_uncertainty = row.get(uncertainty_column)
        if raw_uncertainty in (None, ""):
            if not allow_missing_uncertainty:
                raise ExperimentDatasetLoadError(
                    f"{csv_path} row {row_number} is missing uncertainty value in {uncertainty_column!r}."
                )
        else:
            uncertainty = _parse_float(raw_uncertainty, csv_path, row_number, uncertainty_column)

    return MeasurementPoint(
        time=_parse_float(row.get(time_column), csv_path, row_number, time_column),
        value=_parse_float(row.get(value_column), csv_path, row_number, value_column),
        uncertainty=uncertainty,
    )


def _parse_float(value: str | None, path: Path, row_number: int, column: str) -> float:
    if value in (None, ""):
        raise ExperimentDatasetLoadError(f"{path} row {row_number} is missing a value in {column!r}.")
    try:
        return float(value)
    except ValueError as exc:
        raise ExperimentDatasetLoadError(
            f"{path} row {row_number} has non-numeric value {value!r} in {column!r}."
        ) from exc


__all__ = [
    "ExperimentDatasetLoadError",
    "load_experiment_dataset",
]
