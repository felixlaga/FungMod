"""Variance-based global sensitivity analysis for scalar model outputs.

The implementation uses two independent parameter designs and pick-freeze
hybrid designs. First-order effects use the Saltelli covariance estimator and
total-order effects use the Jansen squared-difference estimator. Every input
distribution remains an explicit, provenance-bearing uncertainty record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.uncertainty.monte_carlo import ParameterUncertaintySpec

ScalarPredictionFunction = Callable[[ParameterSet], Quantity]

SALTELLI_FIRST_ORDER_SOURCE = "https://doi.org/10.1016/j.cpc.2009.09.018"
JANSEN_TOTAL_ORDER_SOURCE = "https://doi.org/10.1016/S0010-4655(98)00154-4"

DEFAULT_GLOBAL_SENSITIVITY_CONFIDENCE_LEVEL = Parameter(
    name="global sensitivity bootstrap confidence level",
    symbol="confidence_global_sensitivity",
    value=0.95,
    units="dimensionless",
    uncertainty=None,
    source="Software reporting convention; not a physical or biological parameter.",
    confidence_level="testing",
    notes="Used only to form equal-tailed nonparametric bootstrap intervals.",
    measurement_method="software configuration",
)


def _serialize_quantity(quantity: Quantity) -> dict[str, Any]:
    return {
        "value": float(np.asarray(quantity.magnitude, dtype=float)),
        "units": str(quantity.units),
    }


def _sampled_parameter(
    parameter: Parameter,
    value: float,
    *,
    design: str,
    row_index: int,
    uncertainty_source: str,
) -> Parameter:
    return replace(
        parameter,
        value=float(value),
        uncertainty=None,
        source=(
            f"Global sensitivity {design} design row {row_index}; sampled from "
            f"uncertainty source: {uncertainty_source}. Nominal source: {parameter.source}"
        ),
        confidence_level="low",
        notes=(
            "Sampled value for variance-based global sensitivity analysis. "
            f"Nominal notes: {parameter.notes}"
        ),
        measurement_method="independent Monte Carlo pick-freeze design",
    )


def _parameter_set_for_row(
    *,
    base_parameters: ParameterSet,
    specs: Sequence[ParameterUncertaintySpec],
    sampled_values: Mapping[str, np.ndarray],
    row_index: int,
    design: str,
) -> ParameterSet:
    replacements = {
        spec.symbol: _sampled_parameter(
            base_parameters.get(spec.symbol),
            float(sampled_values[spec.symbol][row_index]),
            design=design,
            row_index=row_index,
            uncertainty_source=spec.source,
        )
        for spec in specs
    }
    return ParameterSet(
        [replacements.get(parameter.symbol, parameter) for parameter in base_parameters]
    )


def _evaluate_design(
    *,
    base_parameters: ParameterSet,
    specs: Sequence[ParameterUncertaintySpec],
    sampled_values: Mapping[str, np.ndarray],
    design: str,
    predict_scalar: ScalarPredictionFunction,
    output_units: str,
) -> np.ndarray:
    n_rows = len(next(iter(sampled_values.values())))
    values = np.empty(n_rows, dtype=float)
    for row_index in range(n_rows):
        parameters = _parameter_set_for_row(
            base_parameters=base_parameters,
            specs=specs,
            sampled_values=sampled_values,
            row_index=row_index,
            design=design,
        )
        try:
            prediction = require_quantity(
                predict_scalar(parameters),
                name=f"{design} row {row_index} prediction",
            )
            compatible = assert_compatible(
                prediction,
                output_units,
                name=f"{design} row {row_index} prediction",
            )
            magnitude = np.asarray(compatible.magnitude, dtype=float)
            if magnitude.ndim != 0:
                raise ValueError(
                    "Global sensitivity requires predict_scalar to return one scalar quantity."
                )
            value = float(magnitude)
            if not np.isfinite(value):
                raise ValueError("Global sensitivity predictions must be finite.")
            values[row_index] = value
        except Exception as exc:
            raise RuntimeError(
                f"Global sensitivity model evaluation failed for {design} row "
                f"{row_index}: {exc}"
            ) from exc
    return values


@dataclass(frozen=True)
class GlobalSensitivityIndex:
    """First- and total-order variance contributions for one parameter."""

    symbol: str
    first_order: float
    total_order: float
    first_order_interval: tuple[float, float] | None
    total_order_interval: tuple[float, float] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "first_order": self.first_order,
            "total_order": self.total_order,
            "first_order_interval": (
                None if self.first_order_interval is None else list(self.first_order_interval)
            ),
            "total_order_interval": (
                None if self.total_order_interval is None else list(self.total_order_interval)
            ),
        }


@dataclass(frozen=True)
class GlobalSensitivityResult:
    """Reproducible Sobol/Jansen sensitivity report."""

    output_units: str
    output_variance: Quantity
    n_base_samples: int
    n_model_evaluations: int
    random_seed: int | None
    n_bootstrap: int
    bootstrap_seed: int | None
    confidence_level: Parameter
    indices: tuple[GlobalSensitivityIndex, ...]
    uncertainty_specs: tuple[ParameterUncertaintySpec, ...]
    method_sources: Mapping[str, str]
    warnings: tuple[str, ...]

    def ranked_total_order(self) -> tuple[GlobalSensitivityIndex, ...]:
        return tuple(sorted(self.indices, key=lambda entry: abs(entry.total_order), reverse=True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_units": self.output_units,
            "output_variance": _serialize_quantity(self.output_variance),
            "n_base_samples": self.n_base_samples,
            "n_model_evaluations": self.n_model_evaluations,
            "random_seed": self.random_seed,
            "n_bootstrap": self.n_bootstrap,
            "bootstrap_seed": self.bootstrap_seed,
            "confidence_level": self.confidence_level.to_dict(),
            "indices": [entry.to_dict() for entry in self.indices],
            "total_order_ranking": [entry.symbol for entry in self.ranked_total_order()],
            "uncertainty_specs": [spec.to_dict() for spec in self.uncertainty_specs],
            "method": {
                "design": "two-independent-matrix pick-freeze",
                "first_order": "Saltelli covariance estimator",
                "total_order": "Jansen squared-difference estimator",
                "bootstrap": "row-resampled equal-tailed nonparametric interval",
                "sources": dict(self.method_sources),
            },
            "warnings": list(self.warnings),
        }

    def save(self, output_dir: str | Path) -> None:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "global_sensitivity.json").write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _indices(
    output_a: np.ndarray,
    output_b: np.ndarray,
    output_hybrids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    variance = float(np.var(np.concatenate((output_a, output_b)), ddof=1))
    if not np.isfinite(variance) or variance <= 0.0:
        raise ValueError(
            "Global sensitivity indices are undefined because sampled output variance is not positive."
        )
    first_order = np.mean(output_b[:, None] * (output_hybrids - output_a[:, None]), axis=0) / variance
    total_order = 0.5 * np.mean((output_a[:, None] - output_hybrids) ** 2, axis=0) / variance
    return first_order, total_order, variance


def _bootstrap_intervals(
    *,
    output_a: np.ndarray,
    output_b: np.ndarray,
    output_hybrids: np.ndarray,
    n_bootstrap: int,
    bootstrap_seed: int | None,
    confidence_level: float,
) -> tuple[np.ndarray, np.ndarray, int]:
    rng = np.random.default_rng(bootstrap_seed)
    n_rows, n_parameters = output_hybrids.shape
    first_replicates = np.empty((n_bootstrap, n_parameters), dtype=float)
    total_replicates = np.empty((n_bootstrap, n_parameters), dtype=float)
    valid = 0
    for _ in range(n_bootstrap):
        rows = rng.integers(0, n_rows, size=n_rows)
        try:
            first, total, _ = _indices(
                output_a[rows],
                output_b[rows],
                output_hybrids[rows, :],
            )
        except ValueError:
            continue
        first_replicates[valid, :] = first
        total_replicates[valid, :] = total
        valid += 1
    if valid == 0:
        raise ValueError("No bootstrap replicate had positive sampled output variance.")
    alpha = 1.0 - confidence_level
    quantiles = (alpha / 2.0, 1.0 - alpha / 2.0)
    first_intervals = np.quantile(first_replicates[:valid, :], quantiles, axis=0).T
    total_intervals = np.quantile(total_replicates[:valid, :], quantiles, axis=0).T
    return first_intervals, total_intervals, n_bootstrap - valid


def global_sensitivity(
    *,
    base_parameters: ParameterSet,
    uncertainty_specs: Sequence[ParameterUncertaintySpec],
    predict_scalar: ScalarPredictionFunction,
    output_units: str,
    n_base_samples: int,
    random_seed: int | None = None,
    n_bootstrap: int = 0,
    bootstrap_seed: int | None = None,
    confidence_level: Parameter = DEFAULT_GLOBAL_SENSITIVITY_CONFIDENCE_LEVEL,
) -> GlobalSensitivityResult:
    """Estimate first- and total-order indices for independent inputs.

    Finite-sample estimates are intentionally not clipped to ``[0, 1]`` because
    clipping would hide estimator uncertainty or convergence problems.
    """

    if n_base_samples < 2:
        raise ValueError("n_base_samples must be at least 2.")
    if n_bootstrap < 0:
        raise ValueError("n_bootstrap cannot be negative.")
    base_parameters.validate(require_values=True)
    specs = tuple(uncertainty_specs)
    if not specs:
        raise ValueError("At least one uncertainty specification is required.")
    symbols = [spec.symbol for spec in specs]
    if len(set(symbols)) != len(symbols):
        raise ValueError("Global sensitivity uncertainty symbols must be unique.")
    for spec in specs:
        spec.validate(base_parameters)
    confidence_level.validate_provenance()
    confidence_level.validate_value()
    confidence = float(
        assert_compatible(
            cast(Quantity, confidence_level.quantity),
            "dimensionless",
            name=confidence_level.symbol,
        ).magnitude
    )
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence_level must lie strictly between 0 and 1.")

    warnings: list[str] = []
    if random_seed is None:
        warnings.append("No random_seed supplied; sampling designs are not exactly reproducible.")
    if n_bootstrap > 0 and bootstrap_seed is None:
        warnings.append("No bootstrap_seed supplied; bootstrap intervals are not exactly reproducible.")

    rng = np.random.default_rng(random_seed)
    design_a = {spec.symbol: spec.sample(base_parameters, rng, n_base_samples) for spec in specs}
    design_b = {spec.symbol: spec.sample(base_parameters, rng, n_base_samples) for spec in specs}
    output_a = _evaluate_design(
        base_parameters=base_parameters,
        specs=specs,
        sampled_values=design_a,
        design="A",
        predict_scalar=predict_scalar,
        output_units=output_units,
    )
    output_b = _evaluate_design(
        base_parameters=base_parameters,
        specs=specs,
        sampled_values=design_b,
        design="B",
        predict_scalar=predict_scalar,
        output_units=output_units,
    )
    output_hybrids = np.empty((n_base_samples, len(specs)), dtype=float)
    for parameter_index, spec in enumerate(specs):
        hybrid = dict(design_a)
        hybrid[spec.symbol] = design_b[spec.symbol]
        output_hybrids[:, parameter_index] = _evaluate_design(
            base_parameters=base_parameters,
            specs=specs,
            sampled_values=hybrid,
            design=f"A_B[{spec.symbol}]",
            predict_scalar=predict_scalar,
            output_units=output_units,
        )

    first_order, total_order, variance = _indices(output_a, output_b, output_hybrids)
    first_intervals: np.ndarray | None = None
    total_intervals: np.ndarray | None = None
    if n_bootstrap > 0:
        first_intervals, total_intervals, invalid_replicates = _bootstrap_intervals(
            output_a=output_a,
            output_b=output_b,
            output_hybrids=output_hybrids,
            n_bootstrap=n_bootstrap,
            bootstrap_seed=bootstrap_seed,
            confidence_level=confidence,
        )
        if invalid_replicates:
            warnings.append(
                f"{invalid_replicates} of {n_bootstrap} bootstrap replicates had zero "
                "output variance and were excluded from intervals."
            )

    entries = tuple(
        GlobalSensitivityIndex(
            symbol=spec.symbol,
            first_order=float(first_order[index]),
            total_order=float(total_order[index]),
            first_order_interval=(
                None
                if first_intervals is None
                else (float(first_intervals[index, 0]), float(first_intervals[index, 1]))
            ),
            total_order_interval=(
                None
                if total_intervals is None
                else (float(total_intervals[index, 0]), float(total_intervals[index, 1]))
            ),
        )
        for index, spec in enumerate(specs)
    )
    output_unit = Q_(1.0, output_units).units
    return GlobalSensitivityResult(
        output_units=str(output_unit),
        output_variance=Q_(variance, output_unit**2),
        n_base_samples=n_base_samples,
        n_model_evaluations=n_base_samples * (len(specs) + 2),
        random_seed=random_seed,
        n_bootstrap=n_bootstrap,
        bootstrap_seed=bootstrap_seed,
        confidence_level=confidence_level,
        indices=entries,
        uncertainty_specs=specs,
        method_sources={
            "first_order": SALTELLI_FIRST_ORDER_SOURCE,
            "total_order": JANSEN_TOTAL_ORDER_SOURCE,
        },
        warnings=tuple(warnings),
    )


__all__ = [
    "DEFAULT_GLOBAL_SENSITIVITY_CONFIDENCE_LEVEL",
    "GlobalSensitivityIndex",
    "GlobalSensitivityResult",
    "JANSEN_TOTAL_ORDER_SOURCE",
    "SALTELLI_FIRST_ORDER_SOURCE",
    "ScalarPredictionFunction",
    "global_sensitivity",
]
