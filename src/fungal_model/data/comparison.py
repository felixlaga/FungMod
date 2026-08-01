"""Explicit model-dataset comparison utilities."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from fungal_model.core.units import Q_, Quantity, assert_compatible, is_quantity
from fungal_model.core.validators import ValidationResult
from fungal_model.data.datasets import ExperimentDataset, MeasurementSeries
from fungal_model.results import SimulationResult

ObservableType = Literal["state", "process_rate", "derived"]
ObservableTransform = Literal["identity", "unit_conversion", "fractional_conversion"]


class ModelDatasetComparisonError(ValueError):
    """Raised when a model result cannot be compared to a dataset."""


@dataclass(frozen=True)
class ObservableMapping:
    """Explicit mapping from one dataset measurement to one model observable."""

    dataset_measurement_id: str
    model_observable: str
    observable_type: ObservableType
    transform: ObservableTransform = "identity"
    model_units: str | None = None
    initial_value: float | None = None
    initial_units: str | None = None

    def __post_init__(self) -> None:
        if not self.dataset_measurement_id:
            raise ModelDatasetComparisonError("ObservableMapping.dataset_measurement_id is required.")
        if not self.model_observable:
            raise ModelDatasetComparisonError("ObservableMapping.model_observable is required.")
        if self.observable_type not in {"state", "process_rate", "derived"}:
            raise ModelDatasetComparisonError(f"Unsupported observable_type: {self.observable_type!r}.")
        if self.transform not in {"identity", "unit_conversion", "fractional_conversion"}:
            raise ModelDatasetComparisonError(f"Unsupported transform: {self.transform!r}.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_measurement_id": self.dataset_measurement_id,
            "model_observable": self.model_observable,
            "observable_type": self.observable_type,
            "transform": self.transform,
            "model_units": self.model_units,
            "initial_value": self.initial_value,
            "initial_units": self.initial_units,
        }


@dataclass(frozen=True)
class ResidualPoint:
    """One model-data residual at one dataset time."""

    time: float
    observed: float
    predicted: float
    residual: float
    uncertainty: float | None = None
    standardized_residual: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "observed": self.observed,
            "predicted": self.predicted,
            "residual": self.residual,
            "uncertainty": self.uncertainty,
            "standardized_residual": self.standardized_residual,
        }


@dataclass(frozen=True)
class ResidualSeries:
    """Residuals for one mapped dataset measurement."""

    measurement_id: str
    model_observable: str
    observable_type: ObservableType
    units: str
    time_units: str
    points: tuple[ResidualPoint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "measurement_id": self.measurement_id,
            "model_observable": self.model_observable,
            "observable_type": self.observable_type,
            "units": self.units,
            "time_units": self.time_units,
            "points": [point.to_dict() for point in self.points],
        }


@dataclass(frozen=True)
class ModelDatasetComparison:
    """Result of comparing model output to one experiment dataset."""

    dataset_id: str
    model_name: str
    mappings: tuple[ObservableMapping, ...]
    residuals: tuple[ResidualSeries, ...]
    metrics: dict[str, float]
    validation_results: tuple[ValidationResult, ...]
    dataset_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "model_name": self.model_name,
            "mappings": [mapping.to_dict() for mapping in self.mappings],
            "residuals": [series.to_dict() for series in self.residuals],
            "metrics": dict(self.metrics),
            "validation_results": [validation.to_dict() for validation in self.validation_results],
        }

    def save(self, output_dir: str | Path) -> None:
        path = Path(output_dir)
        figures = path / "figures"
        path.mkdir(parents=True, exist_ok=True)
        figures.mkdir(parents=True, exist_ok=True)

        _write_json(path / "comparison_record.json", self.to_dict())
        _write_json(path / "dataset_snapshot.json", self.dataset_snapshot)
        _write_json(path / "observable_mapping.json", [mapping.to_dict() for mapping in self.mappings])
        _write_json(path / "metrics.json", self.metrics)
        _write_json(path / "validation_report.json", [validation.to_dict() for validation in self.validation_results])
        _write_residuals_csv(path / "residuals.csv", self.residuals)
        _write_residuals_csv(path / "model_comparison.csv", self.residuals)
        _write_validation_report(path / "validation_report.md", self)
        self.plot_observed_vs_predicted(figures / "observed_vs_predicted.png")
        self.plot_residuals(figures / "residuals.png")

    def plot_observed_vs_predicted(self, path: str | Path) -> Path:
        plt = _pyplot()
        fig, ax = plt.subplots(figsize=(5, 5))
        observed_values: list[float] = []
        predicted_values: list[float] = []
        for series in self.residuals:
            observed = [point.observed for point in series.points]
            predicted = [point.predicted for point in series.points]
            observed_values.extend(observed)
            predicted_values.extend(predicted)
            ax.scatter(observed, predicted, label=series.measurement_id)
        if observed_values and predicted_values:
            lower = min(observed_values + predicted_values)
            upper = max(observed_values + predicted_values)
            ax.plot([lower, upper], [lower, upper], color="black", linewidth=1)
        ax.set_xlabel("observed")
        ax.set_ylabel("predicted")
        ax.legend()
        fig.tight_layout()
        return _finish_plot(fig, path)

    def plot_residuals(self, path: str | Path) -> Path:
        plt = _pyplot()
        fig, ax = plt.subplots(figsize=(7, 4))
        for series in self.residuals:
            ax.axhline(0.0, color="black", linewidth=1)
            ax.plot(
                [point.time for point in series.points],
                [point.residual for point in series.points],
                marker="o",
                label=series.measurement_id,
            )
        ax.set_xlabel("time")
        ax.set_ylabel("residual")
        ax.legend()
        fig.tight_layout()
        return _finish_plot(fig, path)


def evaluate_model_against_dataset(
    *,
    result: SimulationResult,
    dataset: ExperimentDataset,
    observable_mapping: Sequence[ObservableMapping] | Mapping[str, str],
) -> ModelDatasetComparison:
    """Compare a model result against a dataset through explicit observable mappings."""

    series_by_id = {series.measurement_id: series for series in dataset.measurements}
    mappings = _normalize_mappings(observable_mapping, series_by_id)
    if not mappings:
        raise ModelDatasetComparisonError("At least one observable mapping is required.")

    residual_series: list[ResidualSeries] = []
    validations: list[ValidationResult] = []
    for mapping in mappings:
        series = _measurement_series(series_by_id, mapping.dataset_measurement_id)
        if series.observable_type != mapping.observable_type:
            raise ModelDatasetComparisonError(
                f"Mapping for dataset measurement {series.measurement_id!r} uses observable_type "
                f"{mapping.observable_type!r}, but the dataset declares {series.observable_type!r}."
            )
        model_quantity = _model_quantity(result, mapping)
        predictions = _interpolated_predictions(
            result_time=result.time,
            model_quantity=model_quantity,
            series=series,
            mapping=mapping,
        )
        residuals, warnings = _residual_series(series, mapping, predictions)
        residual_series.append(residuals)
        validations.extend(warnings)

    validations.insert(
        0,
        ValidationResult(
            name="model_dataset_comparison",
            passed=True,
            message="Model result was compared against the dataset through explicit observable mappings.",
            details={
                "dataset_id": dataset.dataset_id,
                "mappings": [mapping.to_dict() for mapping in mappings],
            },
        ),
    )
    return ModelDatasetComparison(
        dataset_id=dataset.dataset_id,
        model_name=result.name,
        mappings=mappings,
        residuals=tuple(residual_series),
        metrics=_comparison_metrics(residual_series),
        validation_results=tuple(validations),
        dataset_snapshot=dataset.to_dict(),
    )


def _normalize_mappings(
    observable_mapping: Sequence[ObservableMapping] | Mapping[str, str],
    series_by_id: Mapping[str, MeasurementSeries],
) -> tuple[ObservableMapping, ...]:
    if isinstance(observable_mapping, Mapping):
        return tuple(
            ObservableMapping(
                dataset_measurement_id=measurement_id,
                model_observable=model_observable,
                observable_type=cast(ObservableType, _measurement_series(series_by_id, measurement_id).observable_type),
            )
            for measurement_id, model_observable in observable_mapping.items()
        )
    return tuple(observable_mapping)


def _measurement_series(
    series_by_id: Mapping[str, MeasurementSeries],
    measurement_id: str,
) -> MeasurementSeries:
    try:
        return series_by_id[measurement_id]
    except KeyError as exc:
        raise ModelDatasetComparisonError(f"Dataset measurement {measurement_id!r} is not present.") from exc


def _model_quantity(result: SimulationResult, mapping: ObservableMapping) -> Quantity:
    if mapping.observable_type == "state":
        container = result.states
    elif mapping.observable_type == "process_rate":
        container = result.process_rates
    else:
        container = result.derived_quantities
    try:
        return container[mapping.model_observable]
    except KeyError as exc:
        raise ModelDatasetComparisonError(
            f"Model observable {mapping.model_observable!r} is not present in {mapping.observable_type} outputs."
        ) from exc


def _interpolated_predictions(
    *,
    result_time: Quantity,
    model_quantity: Quantity,
    series: MeasurementSeries,
    mapping: ObservableMapping,
) -> np.ndarray:
    model_time = assert_compatible(result_time, series.time_units, name="model time")
    model_time_values = np.asarray(model_time.magnitude, dtype=float)
    if model_time_values.ndim != 1:
        raise ModelDatasetComparisonError("Model time must be one-dimensional for dataset comparison.")
    if np.any(np.diff(model_time_values) <= 0.0):
        raise ModelDatasetComparisonError("Model time must be strictly increasing for interpolation.")

    dataset_times = np.asarray([point.time for point in series.points], dtype=float)
    lower = float(model_time_values[0])
    upper = float(model_time_values[-1])
    tolerance = 1e-12 * max(1.0, abs(lower), abs(upper))
    if np.min(dataset_times) < lower - tolerance or np.max(dataset_times) > upper + tolerance:
        raise ModelDatasetComparisonError(
            f"Dataset measurement {series.measurement_id!r} requires extrapolation outside model time range "
            f"[{lower}, {upper}] {series.time_units}."
        )

    prediction_quantity = _prediction_quantity(model_quantity, series, mapping)
    prediction_values = np.asarray(prediction_quantity.magnitude, dtype=float)
    if prediction_values.ndim != 1:
        raise ModelDatasetComparisonError("Only one-dimensional model observables can be compared in D2.")
    if prediction_values.shape[0] != model_time_values.shape[0]:
        raise ModelDatasetComparisonError(
            f"Model observable {mapping.model_observable!r} does not align with model time."
        )
    return np.interp(dataset_times, model_time_values, prediction_values)


def _prediction_quantity(
    model_quantity: Quantity,
    series: MeasurementSeries,
    mapping: ObservableMapping,
) -> Quantity:
    if mapping.transform in {"identity", "unit_conversion"}:
        quantity = model_quantity
        if mapping.model_units is not None:
            quantity = assert_compatible(quantity, mapping.model_units, name=mapping.model_observable)
        return assert_compatible(quantity, series.value_units, name=mapping.model_observable)

    if mapping.initial_value is None or mapping.initial_units is None:
        raise ModelDatasetComparisonError(
            "fractional_conversion requires ObservableMapping.initial_value and initial_units."
        )
    numerator = assert_compatible(model_quantity, mapping.initial_units, name=mapping.model_observable)
    fraction = numerator / Q_(mapping.initial_value, mapping.initial_units)
    return assert_compatible(fraction, series.value_units, name=mapping.model_observable)


def _residual_series(
    series: MeasurementSeries,
    mapping: ObservableMapping,
    predictions: np.ndarray,
) -> tuple[ResidualSeries, tuple[ValidationResult, ...]]:
    points: list[ResidualPoint] = []
    missing_uncertainty = False
    invalid_uncertainty = False
    for point, prediction in zip(series.points, predictions, strict=True):
        residual = float(prediction - point.value)
        standardized: float | None = None
        if point.uncertainty is None:
            missing_uncertainty = True
        elif point.uncertainty <= 0.0:
            invalid_uncertainty = True
        else:
            standardized = residual / point.uncertainty
        points.append(
            ResidualPoint(
                time=point.time,
                observed=point.value,
                predicted=float(prediction),
                residual=residual,
                uncertainty=point.uncertainty,
                standardized_residual=standardized,
            )
        )

    warnings: list[ValidationResult] = []
    if missing_uncertainty:
        warnings.append(
            ValidationResult(
                name="missing_uncertainty",
                passed=True,
                message="At least one point lacks uncertainty; standardized residuals were not computed there.",
                details={"measurement_id": series.measurement_id, "severity": "warning"},
            )
        )
    if invalid_uncertainty:
        warnings.append(
            ValidationResult(
                name="invalid_uncertainty",
                passed=True,
                message="At least one point has non-positive uncertainty; standardized residuals were not computed there.",
                details={"measurement_id": series.measurement_id, "severity": "warning"},
            )
        )
    return (
        ResidualSeries(
            measurement_id=series.measurement_id,
            model_observable=mapping.model_observable,
            observable_type=mapping.observable_type,
            units=series.value_units,
            time_units=series.time_units,
            points=tuple(points),
        ),
        tuple(warnings),
    )


def _comparison_metrics(residuals: Sequence[ResidualSeries]) -> dict[str, float]:
    raw = np.asarray(
        [point.residual for series in residuals for point in series.points],
        dtype=float,
    )
    if raw.size == 0:
        return {"n_points": 0.0}
    metrics = {
        "n_points": float(raw.size),
        "rmse": float(np.sqrt(np.mean(raw**2))),
        "mean_abs_residual": float(np.mean(np.abs(raw))),
    }
    standardized = [
        point.standardized_residual
        for series in residuals
        for point in series.points
        if point.standardized_residual is not None
    ]
    if len(standardized) == raw.size:
        standardized_values = np.asarray(standardized, dtype=float)
        chi_square = float(np.sum(standardized_values**2))
        metrics["chi_square"] = chi_square
        metrics["reduced_chi_square"] = chi_square / max(1.0, float(raw.size - len(residuals)))
    return metrics


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: Any) -> Any:
    if is_quantity(value):
        return {"value": np.asarray(value.magnitude, dtype=float).tolist(), "units": str(value.units)}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")


def _write_residuals_csv(path: Path, residuals: Sequence[ResidualSeries]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "measurement_id",
                "model_observable",
                "observable_type",
                "time",
                "time_units",
                "observed",
                "predicted",
                "residual",
                "units",
                "uncertainty",
                "standardized_residual",
            ],
        )
        writer.writeheader()
        for series in residuals:
            for point in series.points:
                writer.writerow(
                    {
                        "measurement_id": series.measurement_id,
                        "model_observable": series.model_observable,
                        "observable_type": series.observable_type,
                        "time": point.time,
                        "time_units": series.time_units,
                        "observed": point.observed,
                        "predicted": point.predicted,
                        "residual": point.residual,
                        "units": series.units,
                        "uncertainty": "" if point.uncertainty is None else point.uncertainty,
                        "standardized_residual": (
                            "" if point.standardized_residual is None else point.standardized_residual
                        ),
                    }
                )


def _write_validation_report(path: Path, comparison: ModelDatasetComparison) -> None:
    source = comparison.dataset_snapshot.get("source", {})
    source_label = source.get("doi") or source.get("citation") or source.get("url") or "unavailable"
    measurements = comparison.dataset_snapshot.get("measurements", [])
    uncertainty_types = sorted(
        {
            str(measurement.get("uncertainty_type"))
            for measurement in measurements
            if measurement.get("uncertainty_type")
        }
    )
    lines = [
        "# Model-Dataset Comparison Report",
        "",
        f"- Dataset: `{comparison.dataset_id}`",
        f"- Model: `{comparison.model_name}`",
        f"- Dataset source: `{source_label}`",
        "",
        "## Metrics",
        "",
    ]
    lines.extend(f"- `{name}`: {value:.12g}" for name, value in sorted(comparison.metrics.items()))
    lines.extend(
        [
            "",
            "## Observable Mapping",
            "",
        ]
    )
    lines.extend(
        (
            f"- `{mapping.dataset_measurement_id}` -> `{mapping.model_observable}` "
            f"(`{mapping.observable_type}`, `{mapping.transform}`)"
        )
        for mapping in comparison.mappings
    )
    lines.extend(["", "## Validation Checks", ""])
    lines.extend(
        f"- {'PASS' if validation.passed else 'FAIL'} `{validation.name}`: {validation.message}"
        for validation in comparison.validation_results
    )
    lines.extend(["", "## Interpretation Limits", ""])
    if uncertainty_types:
        lines.append(f"- Dataset uncertainty field(s): {'; '.join(uncertainty_types)}.")
    lines.extend(
        [
            "- These metrics describe agreement for the explicit dataset, model, and mapping in this bundle.",
            "- This report does not by itself establish independent validation, calibration, parameter independence, or biological generality.",
            "- Read the dataset snapshot and model provenance before interpreting standardized residuals or goodness-of-fit metrics.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _finish_plot(fig: Any, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200)
    _pyplot().close(fig)
    return output


__all__ = [
    "ModelDatasetComparison",
    "ModelDatasetComparisonError",
    "ObservableMapping",
    "ResidualPoint",
    "ResidualSeries",
    "evaluate_model_against_dataset",
]
