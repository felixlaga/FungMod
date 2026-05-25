"""Residual analysis for unit-aware calibration.

Residuals are stored with units and with the data indices used to compute them.
Least-squares optimizers necessarily consume dimensionless numeric vectors, so
callers may provide residual scales. If no scale is provided for a species, the
numeric residual is expressed in the observation unit and this choice is recorded
by the calibration result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity

DEFAULT_VALIDATION_FRACTION = Parameter(
    name="default calibration validation fraction",
    symbol="f_validation_default",
    value=0.2,
    units="dimensionless",
    uncertainty=None,
    source="Software convention for calibration examples and tests; not a physical parameter.",
    confidence_level="testing",
    notes="Used only when a caller asks for an automatic sequential train/validation split.",
    measurement_method="software configuration",
)


def _serialize_quantity(quantity: Quantity) -> dict[str, Any]:
    return {
        "value": np.asarray(quantity.magnitude, dtype=float).tolist(),
        "units": str(quantity.units),
    }


def sequential_train_validation_split(
    n_points: int,
    *,
    validation_fraction: Parameter = DEFAULT_VALIDATION_FRACTION,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return deterministic sequential train/validation indices.

    The final fraction of points is held out for validation. This is a simple
    utility, not a universal best practice for time-series data.
    """

    validation_fraction.validate_provenance()
    validation_fraction.validate_value()
    fraction = float(
        assert_compatible(
            validation_fraction.quantity,
            "dimensionless",
            name=validation_fraction.symbol,
        ).magnitude
    )
    if n_points < 2:
        raise ValueError("At least two data points are required for a train/validation split.")
    if not 0.0 < fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1.")
    n_validation = max(1, int(np.ceil(n_points * fraction)))
    if n_validation >= n_points:
        n_validation = n_points - 1
    split = n_points - n_validation
    return tuple(range(split)), tuple(range(split, n_points))


@dataclass(frozen=True)
class CalibrationResiduals:
    """Unit-bearing residuals for one data split."""

    label: str
    residuals: Mapping[str, Quantity]
    indices: tuple[int, ...] | None = None
    residual_scales: Mapping[str, Quantity] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "residuals", dict(self.residuals))
        object.__setattr__(self, "residual_scales", dict(self.residual_scales))
        for species, residual in self.residuals.items():
            require_quantity(residual, name=f"residuals[{species}]")
            if species in self.residual_scales:
                assert_compatible(
                    self.residual_scales[species],
                    str(residual.units),
                    name=f"residual_scales[{species}]",
                )

    def flattened_scaled(self) -> np.ndarray:
        """Return residuals as the dimensionless vector used by optimizers."""

        pieces: list[np.ndarray] = []
        for species, residual in self.residuals.items():
            residual_values = np.asarray(residual.magnitude, dtype=float)
            scale = self.residual_scales.get(species)
            if scale is None:
                pieces.append(residual_values.reshape(-1))
                continue
            scale_value = float(
                assert_compatible(scale, str(residual.units), name=f"{species} residual scale").magnitude
            )
            if scale_value <= 0.0:
                raise ValueError(f"Residual scale for {species} must be positive.")
            pieces.append((residual_values / scale_value).reshape(-1))
        if not pieces:
            return np.array([], dtype=float)
        return np.concatenate(pieces)

    def sum_squared_by_species(self) -> dict[str, float]:
        return {
            species: float(np.sum(np.asarray(residual.magnitude, dtype=float) ** 2))
            for species, residual in self.residuals.items()
        }

    def rmse_by_species(self) -> dict[str, dict[str, float | str]]:
        output: dict[str, dict[str, float | str]] = {}
        for species, residual in self.residuals.items():
            values = np.asarray(residual.magnitude, dtype=float)
            output[species] = {
                "rmse": float(np.sqrt(np.mean(values**2))) if values.size else 0.0,
                "units": str(residual.units),
            }
        return output

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "indices": None if self.indices is None else list(self.indices),
            "residuals": {
                species: _serialize_quantity(residual)
                for species, residual in self.residuals.items()
            },
            "residual_scales": {
                species: _serialize_quantity(scale)
                for species, scale in self.residual_scales.items()
            },
            "sum_squared_by_species": self.sum_squared_by_species(),
            "rmse_by_species": self.rmse_by_species(),
            "notes": self.notes,
        }

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def plot(self, path: str | Path, *, independent: Quantity | None = None) -> None:
        """Save a residual plot."""

        n_species = max(1, len(self.residuals))
        fig, axes = plt.subplots(n_species, 1, figsize=(7, 2.8 * n_species), squeeze=False)
        for axis, (species, residual) in zip(axes.flat, self.residuals.items(), strict=False):
            values = np.asarray(residual.magnitude, dtype=float)
            if independent is None:
                x_values = np.arange(values.size)
                x_label = "data index"
            else:
                x_quantity = independent
                if self.indices is not None:
                    x_quantity = Q_(np.asarray(independent.magnitude)[list(self.indices)], independent.units)
                x_values = np.asarray(x_quantity.magnitude, dtype=float)
                x_label = f"independent variable ({x_quantity.units})"
            axis.axhline(0.0, color="black", linewidth=0.8)
            axis.plot(x_values, values, marker="o", linewidth=1.0)
            axis.set_title(f"{species} residuals: {self.label}")
            axis.set_xlabel(x_label)
            axis.set_ylabel(f"residual ({residual.units})")
        fig.tight_layout()
        fig.savefig(path, dpi=200)
        plt.close(fig)


def residuals_between(
    predictions: Mapping[str, Quantity],
    observations: Mapping[str, Quantity],
    *,
    indices: Sequence[int] | None = None,
    residual_scales: Mapping[str, Quantity] | None = None,
    label: str = "residuals",
    notes: str = "",
) -> CalibrationResiduals:
    """Compute prediction-minus-observation residuals with unit checks."""

    missing = set(observations).difference(predictions)
    if missing:
        raise KeyError(f"Predictions are missing observed species: {sorted(missing)}")
    selected = None if indices is None else tuple(int(index) for index in indices)
    residuals: dict[str, Quantity] = {}
    for species, observed in observations.items():
        observed_q = require_quantity(observed, name=f"observations[{species}]")
        predicted_q = assert_compatible(
            predictions[species],
            str(observed_q.units),
            name=f"predictions[{species}]",
        )
        difference = predicted_q - observed_q
        if selected is not None:
            difference = Q_(np.asarray(difference.magnitude)[list(selected)], difference.units)
        residuals[species] = difference
    return CalibrationResiduals(
        label=label,
        residuals=residuals,
        indices=selected,
        residual_scales=residual_scales or {},
        notes=notes,
    )


__all__ = [
    "CalibrationResiduals",
    "DEFAULT_VALIDATION_FRACTION",
    "residuals_between",
    "sequential_train_validation_split",
]
