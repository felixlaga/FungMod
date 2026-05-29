"""Synthetic dataset generation from existing simulation results."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import yaml

from fungal_model.core.units import Q_, Quantity, assert_compatible, is_quantity
from fungal_model.data.comparison import ObservableMapping
from fungal_model.data.datasets import ExperimentDataset
from fungal_model.data.loaders import load_experiment_dataset
from fungal_model.results import SimulationResult


class SyntheticDatasetGenerationError(ValueError):
    """Raised when a synthetic dataset cannot be generated structurally."""


@dataclass(frozen=True)
class GaussianNoise:
    """Simple additive Gaussian noise model for synthetic observations."""

    sigma: Quantity
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "gaussian",
            "sigma": {
                "value": float(np.asarray(self.sigma.magnitude, dtype=float)),
                "units": str(self.sigma.units),
            },
            "seed": self.seed,
        }


def generate_synthetic_dataset_from_result(
    *,
    result: SimulationResult,
    observable_mapping: Sequence[ObservableMapping] | Mapping[str, str],
    output_dir: str | Path,
    noise_model: GaussianNoise,
    dataset_id: str = "synthetic_from_result",
    name: str | None = None,
    source_config: str | Path | None = None,
    file_stem: str | None = None,
    include_true_values: bool = True,
) -> ExperimentDataset:
    """Write and reload a synthetic experiment dataset generated from a result."""

    mappings = _normalize_mappings(observable_mapping)
    if not mappings:
        raise SyntheticDatasetGenerationError("At least one observable mapping is required.")
    measurement_ids = [mapping.dataset_measurement_id for mapping in mappings]
    duplicate_measurements = sorted({item for item in measurement_ids if measurement_ids.count(item) > 1})
    if duplicate_measurements:
        raise SyntheticDatasetGenerationError(f"Duplicate dataset measurement ids: {duplicate_measurements}.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stem = _safe_name(file_stem or dataset_id)
    yaml_path = output_path / f"{stem}.yml"
    csv_path = output_path / f"{stem}_observations.csv"
    generation_record_path = output_path / "generation_record.json"

    time_units = str(result.time.units)
    time_values = np.asarray(result.time.magnitude, dtype=float)
    if time_values.ndim != 1:
        raise SyntheticDatasetGenerationError("Synthetic dataset generation requires one-dimensional result time.")
    time_column = _time_column_name(time_units)
    rng = np.random.default_rng(noise_model.seed)

    generated_series = [
        _generate_series(
            result=result,
            mapping=mapping,
            time_values=time_values,
            time_units=time_units,
            csv_file_name=csv_path.name,
            noise_model=noise_model,
            rng=rng,
        )
        for mapping in mappings
    ]
    _write_observations_csv(csv_path, time_column=time_column, time_values=time_values, series=generated_series)

    yaml_data = _dataset_yaml(
        dataset_id=dataset_id,
        name=name or f"Synthetic dataset generated from {result.name}",
        csv_file_name=csv_path.name,
        source_config=None if source_config is None else str(source_config),
        time_column=time_column,
        time_units=time_units,
        series=generated_series,
    )
    yaml_path.write_text(yaml.safe_dump(yaml_data, sort_keys=False), encoding="utf-8")
    _write_generation_record(
        generation_record_path,
        dataset_id=dataset_id,
        result=result,
        source_config=None if source_config is None else str(source_config),
        mappings=mappings,
        noise_model=noise_model,
        yaml_path=yaml_path,
        csv_path=csv_path,
        generated_series=generated_series,
        time_values=time_values,
        time_units=time_units,
        include_true_values=include_true_values,
    )
    return load_experiment_dataset(yaml_path)


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


def _generate_series(
    *,
    result: SimulationResult,
    mapping: ObservableMapping,
    time_values: np.ndarray,
    time_units: str,
    csv_file_name: str,
    noise_model: GaussianNoise,
    rng: np.random.Generator,
) -> dict[str, Any]:
    model_quantity = _model_quantity(result, mapping)
    value_quantity = _prediction_quantity(model_quantity, mapping)
    true_values = np.asarray(value_quantity.magnitude, dtype=float)
    if true_values.ndim != 1:
        raise SyntheticDatasetGenerationError(
            f"Model observable {mapping.model_observable!r} must be one-dimensional."
        )
    if true_values.shape != time_values.shape:
        raise SyntheticDatasetGenerationError(
            f"Model observable {mapping.model_observable!r} does not align with result time."
        )

    value_units = str(value_quantity.units)
    sigma = _sigma_value(noise_model.sigma, value_units)
    noise = rng.normal(loc=0.0, scale=sigma, size=true_values.shape)
    observed_values = true_values + noise
    safe_id = _safe_name(mapping.dataset_measurement_id)
    unit_suffix = _unit_suffix(value_units)
    value_column = f"{safe_id}_{unit_suffix}"
    uncertainty_column = f"{safe_id}_sigma_{unit_suffix}"
    return {
        "mapping": mapping,
        "measurement_id": mapping.dataset_measurement_id,
        "measured_quantity": mapping.model_observable,
        "observable_type": mapping.observable_type,
        "data_file": csv_file_name,
        "value_units": value_units,
        "uncertainty_units": value_units,
        "value_column": value_column,
        "uncertainty_column": uncertainty_column,
        "uncertainty_type": "standard_deviation",
        "time_units": time_units,
        "true_values": true_values.tolist(),
        "observed_values": observed_values.tolist(),
        "uncertainty_values": np.full(true_values.shape, sigma, dtype=float).tolist(),
    }


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
        raise SyntheticDatasetGenerationError(
            f"Model observable {mapping.model_observable!r} is not present in {mapping.observable_type} outputs."
        ) from exc


def _prediction_quantity(model_quantity: Quantity, mapping: ObservableMapping) -> Quantity:
    if mapping.transform in {"identity", "unit_conversion"}:
        if mapping.model_units is not None:
            return assert_compatible(model_quantity, mapping.model_units, name=mapping.model_observable)
        return model_quantity
    if mapping.initial_value is None or mapping.initial_units is None:
        raise SyntheticDatasetGenerationError(
            "fractional_conversion requires ObservableMapping.initial_value and initial_units."
        )
    numerator = assert_compatible(model_quantity, mapping.initial_units, name=mapping.model_observable)
    return numerator / Q_(mapping.initial_value, mapping.initial_units)


def _sigma_value(sigma: Quantity, value_units: str) -> float:
    sigma_quantity = assert_compatible(sigma, value_units, name="GaussianNoise.sigma")
    sigma_values = np.asarray(sigma_quantity.magnitude, dtype=float)
    if sigma_values.ndim != 0:
        raise SyntheticDatasetGenerationError("GaussianNoise.sigma must be a scalar quantity.")
    sigma_value = float(sigma_values)
    if sigma_value < 0.0:
        raise SyntheticDatasetGenerationError("GaussianNoise.sigma must be non-negative.")
    return sigma_value


def _write_observations_csv(
    path: Path,
    *,
    time_column: str,
    time_values: np.ndarray,
    series: Sequence[Mapping[str, Any]],
) -> None:
    fieldnames = [time_column]
    for item in series:
        fieldnames.extend([str(item["value_column"]), str(item["uncertainty_column"])])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, time_value in enumerate(time_values):
            row: dict[str, str] = {time_column: _format_float(float(time_value))}
            for item in series:
                observed = cast(list[float], item["observed_values"])
                uncertainty = cast(list[float], item["uncertainty_values"])
                row[str(item["value_column"])] = _format_float(observed[index])
                row[str(item["uncertainty_column"])] = _format_float(uncertainty[index])
            writer.writerow(row)


def _dataset_yaml(
    *,
    dataset_id: str,
    name: str,
    csv_file_name: str,
    source_config: str | None,
    time_column: str,
    time_units: str,
    series: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_columns = [time_column]
    measurements: list[dict[str, Any]] = []
    for item in series:
        expected_columns.extend([str(item["value_column"]), str(item["uncertainty_column"])])
        measurements.append(
            {
                "id": item["measurement_id"],
                "measured_quantity": item["measured_quantity"],
                "observable_type": item["observable_type"],
                "data_file": csv_file_name,
                "time_column": time_column,
                "value_column": item["value_column"],
                "uncertainty_column": item["uncertainty_column"],
                "units": {
                    "time": time_units,
                    "value": item["value_units"],
                    "uncertainty": item["uncertainty_units"],
                },
                "uncertainty_type": item["uncertainty_type"],
                "censoring": "none",
                "replicate_id_column": None,
                "notes": "Synthetic observations generated from a FungMod SimulationResult.",
            }
        )
    return {
        "kind": "experiment_dataset",
        "dataset_id": dataset_id,
        "name": name,
        "maturity": "synthetic",
        "source": {
            "type": "generated",
            "citation": None,
            "doi": None,
            "url": None,
            "generated_by": "FungMod synthetic dataset generator",
            "generation_config": source_config,
            "generation_commit": None,
            "notes": "Synthetic dataset generated from model output for infrastructure tests only.",
        },
        "system": {
            "organism": None,
            "enzyme": None,
            "substrate": "synthetic model observable",
            "product": "synthetic model observable",
            "environment": "synthetic result replay",
            "geometry": None,
            "notes": "No empirical organism, enzyme, substrate, or biology is represented.",
        },
        "conditions": {
            "notes": "Synthetic observations generated from an existing SimulationResult.",
        },
        "measurements": measurements,
        "preprocessing": {
            "status": "generated",
            "raw_data_available": True,
            "steps": [
                "sampled model observables from an existing SimulationResult",
                "added configured Gaussian noise with a fixed seed",
            ],
            "excluded_points": [],
            "notes": "No literature preprocessing was performed.",
        },
        "validation": {
            "expected_columns": expected_columns,
            "allow_missing_uncertainty": False,
        },
        "notes": "Synthetic infrastructure dataset only; not empirical evidence.",
    }


def _write_generation_record(
    path: Path,
    *,
    dataset_id: str,
    result: SimulationResult,
    source_config: str | None,
    mappings: Sequence[ObservableMapping],
    noise_model: GaussianNoise,
    yaml_path: Path,
    csv_path: Path,
    generated_series: Sequence[Mapping[str, Any]],
    time_values: np.ndarray,
    time_units: str,
    include_true_values: bool,
) -> None:
    record: dict[str, Any] = {
        "kind": "synthetic_generation_record",
        "dataset_id": dataset_id,
        "generated_by": "FungMod synthetic dataset generator",
        "source_result": {
            "name": result.name,
            "label": result.label,
            "model_version": result.model_version,
        },
        "source_config": source_config,
        "noise_model": noise_model.to_dict(),
        "observable_mapping": [mapping.to_dict() for mapping in mappings],
        "output_files": {
            "dataset_yaml": yaml_path.name,
            "observations_csv": csv_path.name,
            "generation_record": path.name,
        },
        "notes": "Synthetic infrastructure record only; not empirical evidence.",
    }
    if include_true_values:
        record["true_values"] = {
            str(item["measurement_id"]): {
                "time": time_values.tolist(),
                "time_units": time_units,
                "values": item["true_values"],
                "units": item["value_units"],
            }
            for item in generated_series
        }
    path.write_text(json.dumps(record, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: Any) -> Any:
    if is_quantity(value):
        return {
            "value": np.asarray(value.magnitude, dtype=float).tolist(),
            "units": str(value.units),
        }
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")


def _time_column_name(units: str) -> str:
    return f"time_{_unit_suffix(units)}"


def _unit_suffix(units: str) -> str:
    normalized = units.strip()
    if normalized == "second":
        return "s"
    if normalized == "kilogram":
        return "kg"
    if normalized == "gram":
        return "g"
    if normalized == "dimensionless":
        return "dimensionless"
    return _safe_name(normalized)


def _safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return text or "value"


def _format_float(value: float) -> str:
    return f"{value:.12g}"


__all__ = [
    "GaussianNoise",
    "SyntheticDatasetGenerationError",
    "generate_synthetic_dataset_from_result",
]
