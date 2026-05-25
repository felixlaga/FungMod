"""Local sensitivity analysis.

This module implements a conservative finite-difference local sensitivity tool.
It reports both dimensional derivatives and normalized sensitivities when the
base parameter and output values are non-zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible, require_quantity

ScalarPredictionFunction = Callable[[ParameterSet], Quantity]

DEFAULT_LOCAL_RELATIVE_STEP = Parameter(
    name="default local sensitivity relative perturbation",
    symbol="h_local_sensitivity_default",
    value=1.0e-4,
    units="dimensionless",
    uncertainty=None,
    source="Numerical finite-difference convention for local sensitivity analysis; not a physical parameter.",
    confidence_level="testing",
    notes="Used only when constructing default local perturbation specifications.",
    measurement_method="software configuration",
)


def _replace_parameter(parameter: Parameter, value: float, *, notes: str) -> Parameter:
    return replace(
        parameter,
        value=float(value),
        uncertainty=None,
        source=f"Finite-difference local sensitivity perturbation. Base source: {parameter.source}",
        confidence_level="testing",
        notes=notes,
        measurement_method="finite-difference perturbation",
    )


def _replace_in_set(base: ParameterSet, replacement: Parameter) -> ParameterSet:
    return ParameterSet(
        [
            replacement if parameter.symbol == replacement.symbol else parameter
            for parameter in base
        ]
    )


@dataclass(frozen=True)
class LocalSensitivitySpec:
    """Perturbation settings for one parameter."""

    symbol: str
    relative_step: Parameter = DEFAULT_LOCAL_RELATIVE_STEP
    source: str = "Local sensitivity configuration."
    notes: str = ""

    def validate(self, base_parameters: ParameterSet) -> None:
        if not has_text(self.source):
            raise ProvenanceError(f"Local sensitivity spec for {self.symbol} needs a source.")
        base = base_parameters.get(self.symbol)
        base.validate_provenance()
        base.validate_value()
        self.relative_step.validate_provenance()
        self.relative_step.validate_value()
        step = float(
            assert_compatible(
                self.relative_step.quantity,
                "dimensionless",
                name=f"{self.symbol} relative step",
            ).magnitude
        )
        if step <= 0.0:
            raise ValueError(f"Relative step for {self.symbol} must be positive.")
        base_value = float(base.quantity.to(base.units).magnitude)
        if base_value == 0.0:
            raise ValueError(
                f"Local relative sensitivity for {self.symbol} requires a non-zero base value."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "relative_step": self.relative_step.to_dict(),
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LocalSensitivityEntry:
    """Sensitivity of one scalar output to one parameter."""

    symbol: str
    base_parameter: Parameter
    lower_parameter_value: float
    upper_parameter_value: float
    output_base: Quantity
    output_lower: Quantity
    output_upper: Quantity
    derivative: Quantity
    normalized_sensitivity: float | None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "base_parameter": self.base_parameter.to_dict(),
            "lower_parameter_value": self.lower_parameter_value,
            "upper_parameter_value": self.upper_parameter_value,
            "output_base": {
                "value": float(np.asarray(self.output_base.magnitude)),
                "units": str(self.output_base.units),
            },
            "output_lower": {
                "value": float(np.asarray(self.output_lower.magnitude)),
                "units": str(self.output_lower.units),
            },
            "output_upper": {
                "value": float(np.asarray(self.output_upper.magnitude)),
                "units": str(self.output_upper.units),
            },
            "derivative": {
                "value": float(np.asarray(self.derivative.magnitude)),
                "units": str(self.derivative.units),
            },
            "normalized_sensitivity": self.normalized_sensitivity,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LocalSensitivityResult:
    """Collection of local sensitivities and ranking."""

    entries: tuple[LocalSensitivityEntry, ...]
    output_units: str
    warnings: tuple[str, ...] = ()

    def ranked(self) -> tuple[LocalSensitivityEntry, ...]:
        return tuple(
            sorted(
                self.entries,
                key=lambda entry: (
                    -abs(entry.normalized_sensitivity)
                    if entry.normalized_sensitivity is not None
                    else -abs(float(np.asarray(entry.derivative.magnitude)))
                ),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_units": self.output_units,
            "entries": [entry.to_dict() for entry in self.entries],
            "ranking": [entry.symbol for entry in self.ranked()],
            "warnings": list(self.warnings),
        }

    def save(self, output_dir: str | Path) -> None:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "local_sensitivity.json").write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def local_sensitivity(
    *,
    base_parameters: ParameterSet,
    sensitivity_specs: Sequence[LocalSensitivitySpec],
    predict_scalar: ScalarPredictionFunction,
    output_units: str,
) -> LocalSensitivityResult:
    """Compute central finite-difference local sensitivities."""

    base_parameters.validate(require_values=True)
    specs = tuple(sensitivity_specs)
    if not specs:
        raise ValueError("At least one sensitivity specification is required.")
    for spec in specs:
        spec.validate(base_parameters)
    base_output = assert_compatible(
        require_quantity(predict_scalar(base_parameters), name="base output"),
        output_units,
        name="base output",
    )
    base_output_value = float(np.asarray(base_output.magnitude))
    warnings: list[str] = []
    entries: list[LocalSensitivityEntry] = []
    for spec in specs:
        parameter = base_parameters.get(spec.symbol)
        parameter_value = float(parameter.quantity.to(parameter.units).magnitude)
        step = float(spec.relative_step.quantity.to("dimensionless").magnitude)
        lower_value = parameter_value * (1.0 - step)
        upper_value = parameter_value * (1.0 + step)
        lower_parameter = _replace_parameter(
            parameter,
            lower_value,
            notes=f"Lower local sensitivity perturbation for {spec.symbol}. {spec.notes}".strip(),
        )
        upper_parameter = _replace_parameter(
            parameter,
            upper_value,
            notes=f"Upper local sensitivity perturbation for {spec.symbol}. {spec.notes}".strip(),
        )
        lower_output = assert_compatible(
            predict_scalar(_replace_in_set(base_parameters, lower_parameter)),
            output_units,
            name=f"{spec.symbol} lower output",
        )
        upper_output = assert_compatible(
            predict_scalar(_replace_in_set(base_parameters, upper_parameter)),
            output_units,
            name=f"{spec.symbol} upper output",
        )
        denominator = upper_parameter.quantity - lower_parameter.quantity
        derivative = (upper_output - lower_output) / denominator
        if base_output_value == 0.0:
            normalized = None
            warnings.append(
                f"Base output is zero; normalized sensitivity for {spec.symbol} is undefined."
            )
        else:
            normalized_quantity = derivative * parameter.quantity / base_output
            normalized = float(
                assert_compatible(
                    normalized_quantity,
                    "dimensionless",
                    name=f"{spec.symbol} normalized sensitivity",
                ).magnitude
            )
        entries.append(
            LocalSensitivityEntry(
                symbol=spec.symbol,
                base_parameter=parameter,
                lower_parameter_value=lower_value,
                upper_parameter_value=upper_value,
                output_base=base_output,
                output_lower=lower_output,
                output_upper=upper_output,
                derivative=derivative,
                normalized_sensitivity=normalized,
                notes=spec.notes,
            )
        )
    return LocalSensitivityResult(
        entries=tuple(entries),
        output_units=output_units,
        warnings=tuple(warnings),
    )


__all__ = [
    "DEFAULT_LOCAL_RELATIVE_STEP",
    "LocalSensitivityEntry",
    "LocalSensitivityResult",
    "LocalSensitivitySpec",
    "ScalarPredictionFunction",
    "local_sensitivity",
]
