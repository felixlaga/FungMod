"""Synthetic-only calibration for configured FungMod models."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
import yaml

from fungal_model.calibration.fitting import FittableParameter, fit_least_squares
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, Quantity
from fungal_model.data.comparison import (
    ModelDatasetComparison,
    ObservableMapping,
    ResidualSeries,
    evaluate_model_against_dataset,
)
from fungal_model.data.datasets import ExperimentDataset, MeasurementSeries
from fungal_model.data.loaders import load_experiment_dataset
from fungal_model.results import SimulationResult
from fungal_model.workflows import ConfiguredInputLoader, run_configured_model
from fungal_model.io.model_config import load_model_config


class ConfiguredCalibrationError(ValueError):
    """Raised when configured-model calibration cannot be run honestly."""


@dataclass(frozen=True)
class CalibrationSplit:
    """Train/validation/holdout split indices for each dataset measurement."""

    method: str
    train_indices: dict[str, tuple[int, ...]]
    validation_indices: dict[str, tuple[int, ...]]
    holdout_indices: dict[str, tuple[int, ...]] = field(default_factory=dict)

    @property
    def has_validation(self) -> bool:
        return any(indices for indices in self.validation_indices.values())

    @property
    def has_holdout(self) -> bool:
        return any(indices for indices in self.holdout_indices.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "train_indices": {key: list(value) for key, value in self.train_indices.items()},
            "validation_indices": {key: list(value) for key, value in self.validation_indices.items()},
            "holdout_indices": {key: list(value) for key, value in self.holdout_indices.items()},
            "has_validation": self.has_validation,
            "has_holdout": self.has_holdout,
        }


@dataclass(frozen=True)
class CalibrationResult:
    """Report for a synthetic configured-model calibration."""

    dataset_id: str
    model_config: str
    parameter_symbols: tuple[str, ...]
    fitted_parameters: ParameterSet
    initial_guess: dict[str, float]
    bounds: dict[str, tuple[float, float]]
    metrics: dict[str, float]
    residuals: tuple[ResidualSeries, ...]
    success: bool
    optimizer_metadata: dict[str, Any]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    validation_residuals: tuple[ResidualSeries, ...] = ()
    split: CalibrationSplit | None = None
    source_model_config: dict[str, Any] = field(default_factory=dict)
    dataset_snapshot: dict[str, Any] = field(default_factory=dict)
    train_comparison: ModelDatasetComparison | None = None
    validation_comparison: ModelDatasetComparison | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "model_config": self.model_config,
            "parameter_symbols": list(self.parameter_symbols),
            "fitted_parameters": self.fitted_parameters.to_dict(),
            "initial_guess": dict(self.initial_guess),
            "bounds": {key: list(value) for key, value in self.bounds.items()},
            "metrics": dict(self.metrics),
            "residuals": [series.to_dict() for series in self.residuals],
            "validation_residuals": [series.to_dict() for series in self.validation_residuals],
            "success": self.success,
            "optimizer_metadata": dict(self.optimizer_metadata),
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "split": None if self.split is None else self.split.to_dict(),
        }

    def save(self, output_dir: str | Path) -> None:
        path = Path(output_dir)
        figures = path / "figures"
        path.mkdir(parents=True, exist_ok=True)
        figures.mkdir(parents=True, exist_ok=True)

        _write_json(path / "calibration_record.json", self.to_dict())
        _write_json(path / "source_model_config.json", self.source_model_config)
        _write_json(path / "dataset_snapshot.json", self.dataset_snapshot)
        self.fitted_parameters.to_yaml(path / "fitted_parameters.yml")
        self.fitted_parameters.to_json(path / "fitted_parameters.json")
        _write_json(path / "optimizer_metadata.json", self.optimizer_metadata)
        _write_residuals_csv(path / "train_residuals.csv", self.residuals)
        _write_residuals_csv(path / "validation_residuals.csv", self.validation_residuals)
        _write_json(path / "metrics.json", self.metrics)
        _write_json(path / "assumptions.json", list(self.assumptions))
        _write_json(path / "warnings.json", list(self.warnings))
        if self.train_comparison is not None:
            self.train_comparison.plot_observed_vs_predicted(figures / "observed_vs_predicted_train.png")
            self.train_comparison.plot_residuals(figures / "residuals_train.png")
        else:
            _empty_plot(figures / "observed_vs_predicted_train.png", "no training comparison")
            _empty_plot(figures / "residuals_train.png", "no training residuals")
        if self.validation_comparison is not None:
            self.validation_comparison.plot_observed_vs_predicted(figures / "observed_vs_predicted_validation.png")
            self.validation_comparison.plot_residuals(figures / "residuals_validation.png")
        else:
            _empty_plot(figures / "observed_vs_predicted_validation.png", "no independent validation split")
            _empty_plot(figures / "residuals_validation.png", "no independent validation split")


def calibrate_configured_model(
    *,
    model_config: str | Path,
    dataset: ExperimentDataset | str | Path,
    parameter_symbols: Sequence[str],
    observable_mapping: Sequence[ObservableMapping] | Mapping[str, str],
    initial_guess: Mapping[str, float],
    bounds: Mapping[str, tuple[float, float]] | None = None,
    output_dir: str | Path | None = None,
    split: Mapping[str, Any] | None = None,
    max_nfev: int | None = None,
) -> CalibrationResult:
    """Fit configured-model parameters against a synthetic dataset only."""

    source_config_path = Path(model_config).expanduser().resolve()
    source_config_data = _load_yaml_mapping(source_config_path)
    run_config_data = _config_with_resolved_paths(source_config_data, source_config_path)
    dataset_obj = load_experiment_dataset(dataset) if isinstance(dataset, (str, Path)) else dataset
    if dataset_obj.maturity != "synthetic":
        raise ConfiguredCalibrationError(
            "Configured calibration is currently synthetic-only; received "
            f"dataset maturity {dataset_obj.maturity!r}."
        )
    symbols = tuple(str(symbol) for symbol in parameter_symbols)
    if not symbols:
        raise ConfiguredCalibrationError("At least one parameter symbol is required.")
    missing_initial = sorted(set(symbols).difference(initial_guess))
    if missing_initial:
        raise ConfiguredCalibrationError(f"Missing initial guesses for: {missing_initial}.")

    mappings = _normalize_mappings(observable_mapping)
    with tempfile.TemporaryDirectory(prefix="fungmod_calibration_input_") as directory:
        resolved_config_path = Path(directory) / source_config_path.name
        resolved_config_path.write_text(yaml.safe_dump(run_config_data, sort_keys=False), encoding="utf-8")
        config = load_model_config(resolved_config_path)
        inputs = ConfiguredInputLoader().load(config)
    missing_parameters = sorted(symbol for symbol in symbols if symbol not in inputs.parameters)
    if missing_parameters:
        raise ConfiguredCalibrationError(
            "Configured calibration can only fit parameters present in the merged "
            f"configured inputs. Missing parameter symbols: {missing_parameters}."
        )
    initial_parameters = _parameters_with_initial_guess(inputs.parameters, symbols, initial_guess)
    _validate_requested_bounds(
        parameters=initial_parameters,
        symbols=symbols,
        bounds=bounds,
    )
    fittables = tuple(
        _fittable_parameter(
            initial_parameters=initial_parameters,
            symbol=symbol,
            bounds=bounds,
        )
        for symbol in symbols
    )
    calibration_split = _build_split(dataset_obj, split)
    train_dataset = _dataset_subset(dataset_obj, calibration_split.train_indices)
    validation_dataset = (
        _dataset_subset(dataset_obj, calibration_split.validation_indices)
        if calibration_split.has_validation
        else None
    )
    observations = _observations(train_dataset)
    residual_scales = _residual_scales(train_dataset)

    def predict(parameters: ParameterSet) -> Mapping[str, Quantity]:
        result = _run_with_parameters(run_config_data, source_config_path, parameters, symbols)
        comparison = evaluate_model_against_dataset(
            result=result,
            dataset=train_dataset,
            observable_mapping=mappings,
        )
        return _predictions_from_comparison(comparison)

    fit_result = fit_least_squares(
        base_parameters=initial_parameters,
        fittable_parameters=fittables,
        predict=predict,
        observations=observations,
        residual_scales=residual_scales,
        validation_indices=(),
        calibration_source=(
            "Synthetic-only least-squares calibration; not empirical validation. "
            f"Dataset ID: {dataset_obj.dataset_id}."
        ),
        max_nfev=max_nfev,
    )
    final_result = _run_with_parameters(run_config_data, source_config_path, fit_result.fitted_parameters, symbols)
    train_comparison = evaluate_model_against_dataset(
        result=final_result,
        dataset=train_dataset,
        observable_mapping=mappings,
    )
    validation_comparison = (
        evaluate_model_against_dataset(
            result=final_result,
            dataset=validation_dataset,
            observable_mapping=mappings,
        )
        if validation_dataset is not None
        else None
    )
    warnings = list(fit_result.warnings)
    if not calibration_split.has_validation:
        warnings.append("No independent validation split was supplied; no validation claim is made.")
    result = CalibrationResult(
        dataset_id=dataset_obj.dataset_id,
        model_config=str(source_config_path),
        parameter_symbols=symbols,
        fitted_parameters=fit_result.fitted_parameters,
        initial_guess={symbol: float(initial_guess[symbol]) for symbol in symbols},
        bounds=_bounds_for_report(initial_parameters, symbols, bounds),
        metrics=_calibration_metrics(train_comparison, validation_comparison),
        residuals=train_comparison.residuals,
        success=fit_result.success,
        optimizer_metadata={
            **dict(fit_result.optimizer_metadata),
            "message": fit_result.message,
            "cost": fit_result.cost,
            "jacobian_rank": fit_result.jacobian_rank,
            "covariance": fit_result.covariance,
            "confidence_intervals": fit_result.confidence_intervals,
        },
        assumptions=(
            "Synthetic-only calibration; not empirical validation.",
            "Source model config is copied into temporary files and is not mutated in place.",
            "No real fungal biology or literature data are introduced by this calibration.",
        ),
        warnings=tuple(warnings),
        validation_residuals=() if validation_comparison is None else validation_comparison.residuals,
        split=calibration_split,
        source_model_config=dict(source_config_data),
        dataset_snapshot=dataset_obj.to_dict(),
        train_comparison=train_comparison,
        validation_comparison=validation_comparison,
    )
    if output_dir is not None:
        result.save(output_dir)
    return result


def _normalize_mappings(
    observable_mapping: Sequence[ObservableMapping] | Mapping[str, str],
) -> tuple[ObservableMapping, ...]:
    if isinstance(observable_mapping, Mapping):
        return tuple(
            ObservableMapping(
                dataset_measurement_id=measurement_id,
                model_observable=model_observable,
                observable_type="state",
            )
            for measurement_id, model_observable in observable_mapping.items()
        )
    return tuple(observable_mapping)


def _parameters_with_initial_guess(
    parameters: ParameterSet,
    symbols: Sequence[str],
    initial_guess: Mapping[str, float],
) -> ParameterSet:
    replacements = {
        symbol: replace(
            parameters.get(symbol),
            value=float(initial_guess[symbol]),
            source=f"Synthetic calibration initial guess for {symbol}.",
            confidence_level="testing",
            notes=f"Initial guess for synthetic-only configured calibration of {symbol}.",
            measurement_method="synthetic calibration initial guess",
        )
        for symbol in symbols
    }
    return ParameterSet(replacements.get(parameter.symbol, parameter) for parameter in parameters)


def _fittable_parameter(
    *,
    initial_parameters: ParameterSet,
    symbol: str,
    bounds: Mapping[str, tuple[float, float]] | None,
) -> FittableParameter:
    base = initial_parameters.get(symbol)
    if bounds is None or symbol not in bounds:
        lower, upper = -np.inf, np.inf
    else:
        lower, upper = bounds[symbol]
    return FittableParameter(
        symbol=symbol,
        lower_bound=_bound_parameter(symbol=symbol, label="lower", value=float(lower), units=base.units),
        upper_bound=_bound_parameter(symbol=symbol, label="upper", value=float(upper), units=base.units),
        notes="Configured synthetic calibration fittable parameter.",
    )


def _validate_requested_bounds(
    *,
    parameters: ParameterSet,
    symbols: Sequence[str],
    bounds: Mapping[str, tuple[float, float]] | None,
) -> None:
    if bounds is None:
        return
    unknown_bounds = sorted(set(bounds).difference(symbols))
    if unknown_bounds:
        raise ConfiguredCalibrationError(
            f"Bounds were provided for non-fitted parameter symbols: {unknown_bounds}."
        )
    for symbol in symbols:
        if symbol not in bounds:
            continue
        lower, upper = bounds[symbol]
        lower_value = float(lower)
        upper_value = float(upper)
        if not lower_value < upper_value:
            raise ConfiguredCalibrationError(
                f"Bounds for {symbol!r} must satisfy lower < upper; got {bounds[symbol]!r}."
            )
        initial_value = float(parameters.get(symbol).quantity.to(parameters.get(symbol).units).magnitude)
        if not lower_value <= initial_value <= upper_value:
            raise ConfiguredCalibrationError(
                f"Initial guess for {symbol!r} must fall inside its bounds; "
                f"got initial={initial_value!r}, bounds={bounds[symbol]!r}."
            )


def _bound_parameter(*, symbol: str, label: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"{label} calibration bound for {symbol}",
        symbol=f"{symbol}_{label}_bound",
        value=value,
        units=units,
        uncertainty=None,
        source="User-provided or unbounded synthetic calibration optimizer bound.",
        confidence_level="testing",
        notes="Optimizer bound for synthetic-only configured calibration; not a physical constant.",
        measurement_method="synthetic calibration configuration",
    )


def _build_split(dataset: ExperimentDataset, split: Mapping[str, Any] | None) -> CalibrationSplit:
    if split is None:
        train = {
            series.measurement_id: tuple(range(len(series.points)))
            for series in dataset.measurements
        }
        validation = {series.measurement_id: () for series in dataset.measurements}
        holdout = {series.measurement_id: () for series in dataset.measurements}
        return CalibrationSplit(
            method="none",
            train_indices=train,
            validation_indices=validation,
            holdout_indices=holdout,
        )
    method = str(split.get("method", "")).strip()
    if method != "by_time":
        raise ConfiguredCalibrationError("Only split method 'by_time' is supported in D5.")
    train_fraction = float(split.get("train_fraction", 0.0))
    validation_fraction = float(split.get("validation_fraction", 1.0 - train_fraction))
    if not 0.0 < train_fraction < 1.0 or not 0.0 < validation_fraction < 1.0:
        raise ConfiguredCalibrationError("train_fraction and validation_fraction must be between 0 and 1.")
    if train_fraction + validation_fraction > 1.0 + 1e-12:
        raise ConfiguredCalibrationError("train_fraction + validation_fraction must be <= 1.")
    train_indices: dict[str, tuple[int, ...]] = {}
    validation_indices: dict[str, tuple[int, ...]] = {}
    holdout_indices: dict[str, tuple[int, ...]] = {}
    for series in dataset.measurements:
        n_points = len(series.points)
        if n_points < 2:
            raise ConfiguredCalibrationError("At least two points are required for a train/validation split.")
        order = tuple(index for index, _ in sorted(enumerate(series.points), key=lambda item: item[1].time))
        train_end = int(np.floor(n_points * train_fraction))
        validation_end = int(np.floor(n_points * (train_fraction + validation_fraction)))
        if train_end <= 0:
            raise ConfiguredCalibrationError("The by_time split produced an empty training set.")
        if validation_end <= train_end:
            raise ConfiguredCalibrationError("The by_time split produced an empty validation set.")
        if validation_end > n_points:
            raise ConfiguredCalibrationError("The by_time split exceeded the dataset length.")
        train_indices[series.measurement_id] = order[:train_end]
        validation_indices[series.measurement_id] = order[train_end:validation_end]
        holdout_indices[series.measurement_id] = order[validation_end:]
        _require_disjoint_split(
            train=train_indices[series.measurement_id],
            validation=validation_indices[series.measurement_id],
            holdout=holdout_indices[series.measurement_id],
        )
    return CalibrationSplit(
        method="by_time",
        train_indices=train_indices,
        validation_indices=validation_indices,
        holdout_indices=holdout_indices,
    )


def _require_disjoint_split(
    *,
    train: Sequence[int],
    validation: Sequence[int],
    holdout: Sequence[int],
) -> None:
    train_set = set(train)
    validation_set = set(validation)
    holdout_set = set(holdout)
    if train_set.intersection(validation_set) or train_set.intersection(holdout_set) or validation_set.intersection(holdout_set):
        raise ConfiguredCalibrationError("Train, validation, and holdout indices must be disjoint.")


def _dataset_subset(dataset: ExperimentDataset, indices_by_measurement: Mapping[str, Sequence[int]]) -> ExperimentDataset:
    measurements: list[MeasurementSeries] = []
    for series in dataset.measurements:
        indices = tuple(indices_by_measurement.get(series.measurement_id, ()))
        measurements.append(replace(series, points=tuple(series.points[index] for index in indices)))
    return replace(dataset, measurements=tuple(measurements))


def _observations(dataset: ExperimentDataset) -> dict[str, Quantity]:
    return {
        series.measurement_id: Q_([point.value for point in series.points], series.value_units)
        for series in dataset.measurements
    }


def _residual_scales(dataset: ExperimentDataset) -> dict[str, Quantity]:
    scales: dict[str, Quantity] = {}
    for series in dataset.measurements:
        positive = [point.uncertainty for point in series.points if point.uncertainty is not None and point.uncertainty > 0]
        if positive:
            scales[series.measurement_id] = Q_(float(np.mean(positive)), series.value_units)
    return scales


def _predictions_from_comparison(comparison: ModelDatasetComparison) -> dict[str, Quantity]:
    return {
        series.measurement_id: Q_([point.predicted for point in series.points], series.units)
        for series in comparison.residuals
    }


def _run_with_parameters(
    source_config: Mapping[str, Any],
    source_config_path: Path,
    parameters: ParameterSet,
    parameter_symbols: Sequence[str],
) -> SimulationResult:
    config_data = _config_with_parameter_values(source_config, parameters, parameter_symbols)
    with tempfile.TemporaryDirectory(prefix="fungmod_calibration_") as directory:
        path = Path(directory) / source_config_path.name
        path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")
        return run_configured_model(path)


def _config_with_parameter_values(
    source_config: Mapping[str, Any],
    parameters: ParameterSet,
    parameter_symbols: Sequence[str],
) -> dict[str, Any]:
    data = json.loads(json.dumps(source_config))
    replacements = {symbol: parameters.get(symbol) for symbol in parameter_symbols}
    replaced: set[str] = set()
    for parameter_set in data.get("parameters", []):
        for parameter_data in parameter_set.get("parameters", []) or []:
            symbol = parameter_data.get("symbol")
            if symbol in replacements:
                parameter_data.update(replacements[symbol].to_dict())
                replaced.add(symbol)
    missing = sorted(set(replacements).difference(replaced))
    if missing:
        raise ConfiguredCalibrationError(
            "Configured calibration can only update parameters already present in the "
            f"source model config. Missing configured parameter symbols: {missing}."
        )
    outputs = dict(data.get("outputs", {}))
    outputs["directory"] = None
    outputs["save"] = []
    outputs["plots"] = []
    data["outputs"] = outputs
    return data


def _calibration_metrics(
    train: ModelDatasetComparison,
    validation: ModelDatasetComparison | None,
) -> dict[str, float]:
    metrics = {
        f"train_{key}": value
        for key, value in train.metrics.items()
    }
    if validation is not None:
        metrics.update({f"validation_{key}": value for key, value in validation.metrics.items()})
    return metrics


def _bounds_for_report(
    initial_parameters: ParameterSet,
    symbols: Sequence[str],
    bounds: Mapping[str, tuple[float, float]] | None,
) -> dict[str, tuple[float, float]]:
    return {
        symbol: (
            (-np.inf, np.inf)
            if bounds is None or symbol not in bounds
            else (float(bounds[symbol][0]), float(bounds[symbol][1]))
        )
        for symbol in symbols
        if initial_parameters.get(symbol) is not None
    }


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


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")


def _empty_plot(path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.set_title(title)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ConfiguredCalibrationError(f"Model config must load to a mapping: {path}")
    return data


def _config_with_resolved_paths(
    source_config: Mapping[str, Any],
    source_config_path: Path,
) -> dict[str, Any]:
    data = json.loads(json.dumps(source_config))
    entities = data.get("entities", {})
    if isinstance(entities, dict):
        for value in entities.values():
            if isinstance(value, dict):
                _resolve_reference_path_in_place(value, source_config_path)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        _resolve_reference_path_in_place(item, source_config_path)
    for parameter_set in data.get("parameters", []) or []:
        if isinstance(parameter_set, dict):
            _resolve_reference_path_in_place(parameter_set, source_config_path)
    return data


def _resolve_reference_path_in_place(
    data: dict[str, Any],
    source_config_path: Path,
) -> None:
    path_value = data.get("path")
    if path_value is None:
        return
    data["path"] = str(_resolve_external_config_path(str(path_value), source_config_path))


def _resolve_external_config_path(path: str, source_config_path: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        if candidate.exists():
            return candidate.resolve()
        raise ConfiguredCalibrationError(f"Referenced config path does not exist: {candidate}")
    bases = (Path.cwd(), source_config_path.parent, *source_config_path.parents)
    for base in bases:
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return resolved
    raise ConfiguredCalibrationError(
        "Could not resolve referenced config path "
        f"{path!r} from current working directory or ancestors of {source_config_path}."
    )


__all__ = [
    "CalibrationResult",
    "CalibrationSplit",
    "ConfiguredCalibrationError",
    "calibrate_configured_model",
]
