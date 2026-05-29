"""Dataset objects for traceable experiment and synthetic data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fungal_model.core.validators import ValidationResult


ALLOWED_DATASET_MATURITIES = frozenset(
    {
        "toy",
        "synthetic",
        "literature_raw",
        "literature_processed",
        "calibrated",
        "validated",
    }
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    return value


@dataclass(frozen=True)
class DataSource:
    """Source and provenance metadata for a dataset."""

    source_type: str
    citation: str | None = None
    doi: str | None = None
    url: str | None = None
    generated_by: str | None = None
    generation_config: str | None = None
    generation_commit: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.source_type,
            "citation": self.citation,
            "doi": self.doi,
            "url": self.url,
            "generated_by": self.generated_by,
            "generation_config": self.generation_config,
            "generation_commit": self.generation_commit,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExperimentalSystem:
    """High-level system labels for a dataset."""

    organism: str | None = None
    enzyme: str | None = None
    substrate: str | None = None
    product: str | None = None
    environment: str | None = None
    geometry: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "organism": self.organism,
            "enzyme": self.enzyme,
            "substrate": self.substrate,
            "product": self.product,
            "environment": self.environment,
            "geometry": self.geometry,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExperimentalConditions:
    """Condition metadata preserved from dataset configuration."""

    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(self.values)


@dataclass(frozen=True)
class MeasurementPoint:
    """One observed point in a measurement series."""

    time: float
    value: float
    uncertainty: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "value": self.value,
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True)
class MeasurementSeries:
    """Measured observable loaded from a CSV file."""

    measurement_id: str
    measured_quantity: str
    observable_type: str
    data_file: str
    time_column: str
    value_column: str
    time_units: str
    value_units: str
    uncertainty_column: str | None = None
    uncertainty_units: str | None = None
    uncertainty_type: str | None = None
    censoring: str = "none"
    replicate_id_column: str | None = None
    notes: str = ""
    points: tuple[MeasurementPoint, ...] = ()
    data_path: Path | None = None

    @property
    def id(self) -> str:
        return self.measurement_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.measurement_id,
            "measured_quantity": self.measured_quantity,
            "observable_type": self.observable_type,
            "data_file": self.data_file,
            "data_path": str(self.data_path) if self.data_path is not None else None,
            "time_column": self.time_column,
            "value_column": self.value_column,
            "uncertainty_column": self.uncertainty_column,
            "units": {
                "time": self.time_units,
                "value": self.value_units,
                "uncertainty": self.uncertainty_units,
            },
            "uncertainty_type": self.uncertainty_type,
            "censoring": self.censoring,
            "replicate_id_column": self.replicate_id_column,
            "notes": self.notes,
            "points": [point.to_dict() for point in self.points],
        }


@dataclass(frozen=True)
class PreprocessingRecord:
    """Preprocessing metadata for a dataset."""

    status: str
    raw_data_available: bool
    steps: tuple[str, ...] = ()
    excluded_points: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "raw_data_available": self.raw_data_available,
            "steps": list(self.steps),
            "excluded_points": list(self.excluded_points),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExperimentDataset:
    """Experiment or synthetic dataset with provenance, units, and observations."""

    name: str
    dataset_id: str
    maturity: str
    source: DataSource
    system: ExperimentalSystem
    conditions: ExperimentalConditions
    measurements: tuple[MeasurementSeries, ...]
    preprocessing: PreprocessingRecord
    notes: str = ""
    path: Path | None = None
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> ValidationResult:
        issues: list[dict[str, Any]] = []
        if not self.dataset_id:
            issues.append({"field": "dataset_id", "message": "Dataset id is required."})
        if not self.name:
            issues.append({"field": "name", "message": "Dataset name is required."})
        if self.maturity not in ALLOWED_DATASET_MATURITIES:
            issues.append(
                {
                    "field": "maturity",
                    "value": self.maturity,
                    "allowed": sorted(ALLOWED_DATASET_MATURITIES),
                    "message": "Dataset maturity is not supported.",
                }
            )
        if not self.source.source_type:
            issues.append({"field": "source.type", "message": "Dataset source type is required."})
        if not self.measurements:
            issues.append({"field": "measurements", "message": "At least one measurement series is required."})
        if not self.preprocessing.status:
            issues.append({"field": "preprocessing.status", "message": "Preprocessing status is required."})

        for series in self.measurements:
            if not series.measurement_id:
                issues.append({"field": "measurements[].id", "message": "Measurement id is required."})
            if not series.points:
                issues.append({"field": series.measurement_id, "message": "Measurement series has no data points."})
            if not series.time_units:
                issues.append({"field": f"{series.measurement_id}.units.time", "message": "Time units are required."})
            if not series.value_units:
                issues.append({"field": f"{series.measurement_id}.units.value", "message": "Value units are required."})
            if series.uncertainty_column and not series.uncertainty_units:
                issues.append(
                    {
                        "field": f"{series.measurement_id}.units.uncertainty",
                        "message": "Uncertainty units are required when uncertainty data are configured.",
                    }
                )

        return ValidationResult(
            name="experiment_dataset",
            passed=not issues,
            message="Experiment dataset is valid." if not issues else "Experiment dataset failed validation.",
            details={"issues": issues, "dataset_id": self.dataset_id},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "experiment_dataset",
            "dataset_id": self.dataset_id,
            "name": self.name,
            "maturity": self.maturity,
            "source": self.source.to_dict(),
            "system": self.system.to_dict(),
            "conditions": self.conditions.to_dict(),
            "measurements": [series.to_dict() for series in self.measurements],
            "preprocessing": self.preprocessing.to_dict(),
            "validation": _json_safe(self.validation),
            "notes": self.notes,
            "path": str(self.path) if self.path is not None else None,
        }


__all__ = [
    "ALLOWED_DATASET_MATURITIES",
    "DataSource",
    "ExperimentDataset",
    "ExperimentalConditions",
    "ExperimentalSystem",
    "MeasurementPoint",
    "MeasurementSeries",
    "PreprocessingRecord",
]
