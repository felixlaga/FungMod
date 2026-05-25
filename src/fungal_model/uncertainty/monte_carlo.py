"""Monte Carlo uncertainty propagation.

The Monte Carlo layer samples explicit parameter uncertainty specifications and
passes each sampled `ParameterSet` into a caller-supplied prediction function.
It does not clip bad samples or hide failed predictions; failures are recorded
with their sample index.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible

DistributionName = Literal["normal", "uniform", "lognormal"]
PredictionFunction = Callable[[ParameterSet], Mapping[str, Quantity]]

DEFAULT_MONTE_CARLO_QUANTILES = (
    Parameter(
        name="lower Monte Carlo summary quantile",
        symbol="q_mc_lower",
        value=0.05,
        units="dimensionless",
        uncertainty=None,
        source="Software convention for uncertainty summary intervals; not a physical parameter.",
        confidence_level="testing",
        notes="Used to report a central 90 percent interval by default.",
        measurement_method="software configuration",
    ),
    Parameter(
        name="median Monte Carlo summary quantile",
        symbol="q_mc_median",
        value=0.5,
        units="dimensionless",
        uncertainty=None,
        source="Statistical definition of the median quantile.",
        confidence_level="high",
        notes="Used to report the median prediction.",
        measurement_method="statistical definition",
    ),
    Parameter(
        name="upper Monte Carlo summary quantile",
        symbol="q_mc_upper",
        value=0.95,
        units="dimensionless",
        uncertainty=None,
        source="Software convention for uncertainty summary intervals; not a physical parameter.",
        confidence_level="testing",
        notes="Used to report a central 90 percent interval by default.",
        measurement_method="software configuration",
    ),
)


def _serialize_quantity(quantity: Quantity) -> dict[str, Any]:
    return {
        "value": np.asarray(quantity.magnitude, dtype=float).tolist(),
        "units": str(quantity.units),
    }


def _replace_parameter(parameter: Parameter, value: float, *, sample_index: int) -> Parameter:
    return replace(
        parameter,
        value=float(value),
        uncertainty=None,
        source=(
            f"Monte Carlo sample {sample_index} drawn from explicit uncertainty "
            f"specification. Nominal source: {parameter.source}"
        ),
        confidence_level="low",
        notes=f"Sampled value for uncertainty propagation. Nominal notes: {parameter.notes}",
        measurement_method="Monte Carlo sampling",
    )


@dataclass(frozen=True)
class ParameterUncertaintySpec:
    """Distribution for sampling one model parameter."""

    symbol: str
    distribution: DistributionName
    source: str
    standard_deviation: Parameter | None = None
    lower_bound: Parameter | None = None
    upper_bound: Parameter | None = None
    log_standard_deviation: Parameter | None = None
    notes: str = ""

    def validate(self, base_parameters: ParameterSet) -> None:
        if not has_text(self.source):
            raise ProvenanceError(f"Uncertainty specification for {self.symbol} needs a source.")
        nominal = base_parameters.get(self.symbol)
        nominal.validate_provenance()
        nominal.validate_value()
        if self.distribution == "normal":
            if self.standard_deviation is None:
                raise ValueError(f"Normal uncertainty for {self.symbol} requires standard_deviation.")
            self.standard_deviation.validate_provenance()
            self.standard_deviation.validate_value()
            std = float(
                assert_compatible(
                    self.standard_deviation.quantity,
                    nominal.units,
                    name=f"{self.symbol} standard deviation",
                ).magnitude
            )
            if std < 0.0:
                raise ValueError(f"Standard deviation for {self.symbol} must be non-negative.")
        elif self.distribution == "uniform":
            if self.lower_bound is None or self.upper_bound is None:
                raise ValueError(f"Uniform uncertainty for {self.symbol} requires lower and upper bounds.")
            self.lower_bound.validate_provenance()
            self.lower_bound.validate_value()
            self.upper_bound.validate_provenance()
            self.upper_bound.validate_value()
            lower = float(self.lower_bound.quantity.to(nominal.units).magnitude)
            upper = float(self.upper_bound.quantity.to(nominal.units).magnitude)
            if not lower < upper:
                raise ValueError(f"Uniform bounds for {self.symbol} must satisfy lower < upper.")
        elif self.distribution == "lognormal":
            if self.log_standard_deviation is None:
                raise ValueError(f"Lognormal uncertainty for {self.symbol} requires log_standard_deviation.")
            self.log_standard_deviation.validate_provenance()
            self.log_standard_deviation.validate_value()
            sigma = float(
                assert_compatible(
                    self.log_standard_deviation.quantity,
                    "dimensionless",
                    name=f"{self.symbol} log standard deviation",
                ).magnitude
            )
            if sigma < 0.0:
                raise ValueError(f"Log standard deviation for {self.symbol} must be non-negative.")
            nominal_value = float(nominal.quantity.to(nominal.units).magnitude)
            if nominal_value <= 0.0:
                raise ValueError(f"Lognormal uncertainty requires positive nominal {self.symbol}.")
        else:
            raise ValueError(f"Unsupported uncertainty distribution: {self.distribution}")

    def sample(self, base_parameters: ParameterSet, rng: np.random.Generator, n_samples: int) -> np.ndarray:
        self.validate(base_parameters)
        nominal = base_parameters.get(self.symbol)
        nominal_value = float(nominal.quantity.to(nominal.units).magnitude)
        if self.distribution == "normal":
            std = float(self.standard_deviation.quantity.to(nominal.units).magnitude)
            return rng.normal(loc=nominal_value, scale=std, size=n_samples)
        if self.distribution == "uniform":
            lower = float(self.lower_bound.quantity.to(nominal.units).magnitude)
            upper = float(self.upper_bound.quantity.to(nominal.units).magnitude)
            return rng.uniform(low=lower, high=upper, size=n_samples)
        sigma = float(self.log_standard_deviation.quantity.to("dimensionless").magnitude)
        return rng.lognormal(mean=np.log(nominal_value), sigma=sigma, size=n_samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "distribution": self.distribution,
            "source": self.source,
            "standard_deviation": None if self.standard_deviation is None else self.standard_deviation.to_dict(),
            "lower_bound": None if self.lower_bound is None else self.lower_bound.to_dict(),
            "upper_bound": None if self.upper_bound is None else self.upper_bound.to_dict(),
            "log_standard_deviation": (
                None if self.log_standard_deviation is None else self.log_standard_deviation.to_dict()
            ),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class MonteCarloResult:
    """Summary and raw outputs from uncertainty propagation."""

    n_requested: int
    n_successful: int
    random_seed: int | None
    sampled_parameter_values: Mapping[str, np.ndarray]
    predictions: Mapping[str, Quantity]
    summary: Mapping[str, Mapping[str, Quantity]]
    failures: tuple[dict[str, Any], ...]
    uncertainty_specs: tuple[ParameterUncertaintySpec, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_requested": self.n_requested,
            "n_successful": self.n_successful,
            "random_seed": self.random_seed,
            "sampled_parameter_values": {
                symbol: np.asarray(values, dtype=float).tolist()
                for symbol, values in self.sampled_parameter_values.items()
            },
            "predictions": {
                name: _serialize_quantity(quantity)
                for name, quantity in self.predictions.items()
            },
            "summary": {
                name: {
                    quantile: _serialize_quantity(quantity)
                    for quantile, quantity in species_summary.items()
                }
                for name, species_summary in self.summary.items()
            },
            "failures": list(self.failures),
            "uncertainty_specs": [spec.to_dict() for spec in self.uncertainty_specs],
            "warnings": list(self.warnings),
        }

    def save(self, output_dir: str | Path) -> None:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "monte_carlo_result.json").write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _parameter_set_for_sample(
    base_parameters: ParameterSet,
    sampled_values: Mapping[str, np.ndarray],
    sample_index: int,
) -> ParameterSet:
    replacements = {
        symbol: _replace_parameter(
            base_parameters.get(symbol),
            float(values[sample_index]),
            sample_index=sample_index,
        )
        for symbol, values in sampled_values.items()
    }
    return ParameterSet(
        [replacements.get(parameter.symbol, parameter) for parameter in base_parameters]
    )


def _quantile_parameters(
    quantiles: Sequence[Parameter],
) -> tuple[tuple[str, float], ...]:
    values: list[tuple[str, float]] = []
    for quantile in quantiles:
        quantile.validate_provenance()
        quantile.validate_value()
        value = float(
            assert_compatible(
                quantile.quantity,
                "dimensionless",
                name=quantile.symbol,
            ).magnitude
        )
        if not 0.0 <= value <= 1.0:
            raise ValueError("Monte Carlo summary quantiles must lie between 0 and 1.")
        values.append((quantile.symbol, value))
    return tuple(values)


def run_monte_carlo(
    *,
    base_parameters: ParameterSet,
    uncertainty_specs: Sequence[ParameterUncertaintySpec],
    predict: PredictionFunction,
    n_samples: int,
    random_seed: int | None = None,
    quantiles: Sequence[Parameter] = DEFAULT_MONTE_CARLO_QUANTILES,
) -> MonteCarloResult:
    """Propagate parameter uncertainty through a prediction function."""

    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")
    base_parameters.validate(require_values=True)
    specs = tuple(uncertainty_specs)
    if not specs:
        raise ValueError("At least one uncertainty specification is required.")
    for spec in specs:
        spec.validate(base_parameters)
    quantile_values = _quantile_parameters(quantiles)
    warnings: list[str] = []
    if random_seed is None:
        warnings.append("No random_seed supplied; Monte Carlo run is not exactly reproducible.")
    rng = np.random.default_rng(random_seed)
    sampled_values = {
        spec.symbol: spec.sample(base_parameters, rng, n_samples)
        for spec in specs
    }
    collected: dict[str, list[Quantity]] = {}
    failures: list[dict[str, Any]] = []
    for sample_index in range(n_samples):
        parameter_set = _parameter_set_for_sample(
            base_parameters,
            sampled_values,
            sample_index,
        )
        try:
            prediction = predict(parameter_set)
        except Exception as exc:
            failures.append(
                {
                    "sample_index": sample_index,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            continue
        for name, quantity in prediction.items():
            collected.setdefault(name, []).append(quantity)
    predictions: dict[str, Quantity] = {}
    summary: dict[str, dict[str, Quantity]] = {}
    for name, quantities in collected.items():
        if not quantities:
            continue
        units = str(quantities[0].units)
        values = np.stack(
            [
                np.asarray(assert_compatible(quantity, units, name=name).magnitude, dtype=float)
                for quantity in quantities
            ],
            axis=0,
        )
        predictions[name] = Q_(values, units)
        summary[name] = {
            symbol: Q_(np.quantile(values, quantile, axis=0), units)
            for symbol, quantile in quantile_values
        }
    return MonteCarloResult(
        n_requested=n_samples,
        n_successful=n_samples - len(failures),
        random_seed=random_seed,
        sampled_parameter_values=sampled_values,
        predictions=predictions,
        summary=summary,
        failures=tuple(failures),
        uncertainty_specs=specs,
        warnings=tuple(warnings),
    )


__all__ = [
    "DEFAULT_MONTE_CARLO_QUANTILES",
    "DistributionName",
    "MonteCarloResult",
    "ParameterUncertaintySpec",
    "PredictionFunction",
    "run_monte_carlo",
]
