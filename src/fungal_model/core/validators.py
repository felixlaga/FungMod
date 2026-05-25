"""Validation helpers for simulation outputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.chemistry.stoichiometry import CarbonContent, OxygenDemand
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.units import Q_, Quantity, assert_compatible, is_quantity

DEFAULT_VALIDATION_RELATIVE_TOLERANCE = Parameter(
    name="default validation relative tolerance",
    symbol="epsilon_validation",
    value=1e-9,
    units="dimensionless",
    uncertainty=None,
    source="Numerical validation convention for floating-point ODE outputs; not a physical parameter.",
    confidence_level="testing",
    notes="Used only as a named numerical tolerance when a caller does not supply one.",
    measurement_method="software configuration",
)


@dataclass(frozen=True)
class ValidationResult:
    """Structured result of a validation check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


def validate_non_negative(
    result: Any,
    *,
    species: Sequence[str] | None = None,
    relative_tolerance: Quantity | None = None,
) -> ValidationResult:
    """Check that physical concentrations/amounts do not become negative."""

    epsilon = relative_tolerance or DEFAULT_VALIDATION_RELATIVE_TOLERANCE.quantity
    epsilon_value = float(assert_compatible(epsilon, "dimensionless").magnitude)
    selected_species = list(species) if species is not None else list(result.species)
    minima: dict[str, float] = {}
    failures: dict[str, dict[str, float]] = {}
    for name in selected_species:
        quantity = result.species[name]
        values = np.asarray(quantity.magnitude, dtype=float)
        minimum = float(np.min(values))
        scale = max(1.0, float(np.max(np.abs(values))))
        threshold = -epsilon_value * scale
        minima[name] = minimum
        if minimum < threshold:
            failures[name] = {
                "minimum": minimum,
                "allowed_minimum": threshold,
                "units": str(quantity.units),
            }
    if failures:
        return ValidationResult(
            name="non_negative",
            passed=False,
            message="At least one physical state variable became negative beyond tolerance.",
            details={"failures": failures, "minima": minima},
        )
    return ValidationResult(
        name="non_negative",
        passed=True,
        message="All checked physical state variables remained non-negative within tolerance.",
        details={"minima": minima, "relative_tolerance": epsilon_value},
    )


def _as_weighted_quantity(values: Quantity, weight: float | Quantity) -> Quantity:
    if is_quantity(weight):
        return values * weight
    return values * float(weight)


def validate_mass_balance(
    result: Any,
    *,
    conserved_weights: Mapping[str, float | Quantity] | None = None,
    closed_system: bool = True,
    relative_tolerance: Quantity | None = None,
) -> ValidationResult:
    """Validate conservation of a weighted total for closed systems."""

    epsilon = relative_tolerance or DEFAULT_VALIDATION_RELATIVE_TOLERANCE.quantity
    epsilon_value = float(assert_compatible(epsilon, "dimensionless").magnitude)
    if not closed_system:
        return ValidationResult(
            name="mass_balance",
            passed=True,
            message="Open system: mass conservation was not enforced; external fluxes must be reported by the model.",
            details={"closed_system": False},
        )

    weights = conserved_weights or {name: 1.0 for name in result.species}
    total: Quantity | None = None
    included_species: list[str] = []
    for name, weight in weights.items():
        if name not in result.species:
            raise KeyError(f"Conserved weight provided for unknown species {name!r}.")
        term = _as_weighted_quantity(result.species[name], weight)
        total = term if total is None else total + term.to(total.units)
        included_species.append(name)
    if total is None:
        raise ValueError("At least one conserved species weight is required.")

    values = np.asarray(total.magnitude, dtype=float)
    initial = float(values.flat[0])
    deviations = np.abs(values - initial)
    max_deviation = float(np.max(deviations))
    scale = max(1.0, abs(initial), float(np.max(np.abs(values))))
    relative_deviation = max_deviation / scale
    passed = relative_deviation <= epsilon_value
    return ValidationResult(
        name="mass_balance",
        passed=passed,
        message=(
            "Weighted conserved total remained constant within tolerance."
            if passed
            else "Weighted conserved total changed beyond tolerance."
        ),
        details={
            "closed_system": True,
            "included_species": included_species,
            "units": str(total.units),
            "initial_total": initial,
            "final_total": float(values.flat[-1]),
            "max_deviation": max_deviation,
            "relative_deviation": relative_deviation,
            "relative_tolerance": epsilon_value,
        },
    )


def validate_carbon_conservation(
    result: Any,
    *,
    carbon_contents: Sequence[CarbonContent],
    external_carbon: Quantity | None = None,
    relative_tolerance: Quantity | None = None,
) -> ValidationResult:
    """Check that tracked carbon does not exceed initial plus external carbon."""

    epsilon = relative_tolerance or DEFAULT_VALIDATION_RELATIVE_TOLERANCE.quantity
    epsilon_value = float(assert_compatible(epsilon, "dimensionless").magnitude)
    external = (
        Q_(0.0, "kilogram")
        if external_carbon is None
        else assert_compatible(external_carbon, "kilogram", name="external_carbon")
    )
    total: Quantity | None = None
    included_species: list[str] = []
    for content in carbon_contents:
        if content.species not in result.species:
            raise KeyError(f"Carbon content provided for unknown species {content.species!r}.")
        carbon = content.carbon_mass(result.species[content.species])
        total = carbon if total is None else total + carbon.to(total.units)
        included_species.append(content.species)
    if total is None:
        raise ValueError("At least one carbon content entry is required.")

    values = np.asarray(total.to("kilogram").magnitude, dtype=float)
    initial = float(values.flat[0])
    allowance = initial + float(external.to("kilogram").magnitude)
    max_carbon = float(np.max(values))
    scale = max(1.0, abs(allowance), abs(max_carbon))
    excess = max(0.0, max_carbon - allowance)
    passed = excess <= epsilon_value * scale
    return ValidationResult(
        name="carbon_conservation",
        passed=passed,
        message=(
            "Tracked carbon did not exceed initial plus external carbon."
            if passed
            else "Tracked carbon exceeded initial plus external carbon."
        ),
        details={
            "included_species": included_species,
            "units": "kilogram carbon equivalent",
            "initial_carbon": initial,
            "external_carbon": float(external.to("kilogram").magnitude),
            "allowed_carbon": allowance,
            "maximum_tracked_carbon": max_carbon,
            "excess_carbon": excess,
            "relative_tolerance": epsilon_value,
        },
    )


def validate_oxygen_limitation(
    result: Any,
    *,
    oxygen_demand: OxygenDemand,
    oxygen_available: Quantity | None = None,
    oxygen_species: str | None = None,
    relative_tolerance: Quantity | None = None,
) -> ValidationResult:
    """Check whether aerobic substrate consumption exceeds available oxygen."""

    epsilon = relative_tolerance or DEFAULT_VALIDATION_RELATIVE_TOLERANCE.quantity
    epsilon_value = float(assert_compatible(epsilon, "dimensionless").magnitude)
    if oxygen_demand.substrate_species not in result.species:
        raise KeyError(f"Unknown substrate species {oxygen_demand.substrate_species!r}.")
    if oxygen_available is None and oxygen_species is None:
        raise ValueError("oxygen_available or oxygen_species must be provided.")
    if oxygen_available is not None and oxygen_species is not None:
        raise ValueError("Provide only one of oxygen_available or oxygen_species.")

    substrate = assert_compatible(
        result.species[oxygen_demand.substrate_species],
        "kilogram",
        name=oxygen_demand.substrate_species,
    )
    substrate_values = np.asarray(substrate.magnitude, dtype=float)
    consumed = max(0.0, float(substrate_values.flat[0] - np.min(substrate_values)))
    required = oxygen_demand.required_oxygen(Q_(consumed, "kilogram"))

    if oxygen_species is not None:
        if oxygen_species not in result.species:
            raise KeyError(f"Unknown oxygen species {oxygen_species!r}.")
        available = assert_compatible(
            result.species[oxygen_species],
            "kilogram",
            name=oxygen_species,
        )
        available_value = float(np.asarray(available.magnitude, dtype=float).flat[0])
    else:
        available_value = float(
            assert_compatible(oxygen_available, "kilogram", name="oxygen_available").magnitude
        )
    required_value = float(required.to("kilogram").magnitude)
    scale = max(1.0, abs(available_value), abs(required_value))
    deficit = max(0.0, required_value - available_value)
    passed = deficit <= epsilon_value * scale
    return ValidationResult(
        name="oxygen_limitation",
        passed=passed,
        message=(
            "Available oxygen is sufficient for tracked aerobic substrate consumption."
            if passed
            else "Tracked aerobic substrate consumption exceeds available oxygen."
        ),
        details={
            "process_name": oxygen_demand.process_name,
            "substrate_species": oxygen_demand.substrate_species,
            "substrate_consumed": consumed,
            "oxygen_required": required_value,
            "oxygen_available": available_value,
            "oxygen_deficit": deficit,
            "units": "kilogram",
            "relative_tolerance": epsilon_value,
        },
    )


def validate_biomass_yield_limit(
    *,
    yield_parameter: Parameter,
    maximum_yield_parameter: Parameter,
) -> ValidationResult:
    """Check that biomass yield does not exceed a configured maximum."""

    if yield_parameter.quantity is None:
        raise UnknownParameterError(f"Biomass yield {yield_parameter.symbol} is unknown.")
    if maximum_yield_parameter.quantity is None:
        raise UnknownParameterError(f"Maximum biomass yield {maximum_yield_parameter.symbol} is unknown.")
    yield_value = assert_compatible(yield_parameter.quantity, "dimensionless", name=yield_parameter.symbol)
    maximum = assert_compatible(maximum_yield_parameter.quantity, "dimensionless", name=maximum_yield_parameter.symbol)
    y = float(yield_value.magnitude)
    y_max = float(maximum.magnitude)
    if y < 0.0:
        return ValidationResult(
            name="biomass_yield_limit",
            passed=False,
            message="Biomass yield is negative.",
            details={"yield": y, "maximum_yield": y_max},
        )
    if y_max < 0.0 or y_max > 1.0:
        return ValidationResult(
            name="biomass_yield_limit",
            passed=False,
            message="Configured maximum biomass yield must be between 0 and 1.",
            details={"yield": y, "maximum_yield": y_max},
        )
    passed = y <= y_max
    return ValidationResult(
        name="biomass_yield_limit",
        passed=passed,
        message=(
            "Biomass yield is within the configured maximum."
            if passed
            else "Biomass yield exceeds the configured maximum."
        ),
        details={"yield": y, "maximum_yield": y_max},
    )


@dataclass
class LimitingCase:
    """A named limiting case with executable setup and validation functions."""

    name: str
    description: str
    run: Callable[[], Any]
    validate: Callable[[Any], ValidationResult]

    def evaluate(self) -> ValidationResult:
        try:
            output = self.run()
            result = self.validate(output)
        except Exception as exc:  # pragma: no cover - exercised by downstream suites
            return ValidationResult(
                name=self.name,
                passed=False,
                message=f"Limiting case raised {type(exc).__name__}: {exc}",
                details={"description": self.description},
            )
        return ValidationResult(
            name=self.name,
            passed=result.passed,
            message=result.message,
            details={"description": self.description, "result": result.to_dict()},
        )


@dataclass
class LimitingCaseSuite:
    """A collection of limiting cases to run as a validation suite."""

    cases: list[LimitingCase] = field(default_factory=list)

    def add(self, case: LimitingCase) -> None:
        self.cases.append(case)

    def run(self) -> list[ValidationResult]:
        return [case.evaluate() for case in self.cases]


__all__ = [
    "DEFAULT_VALIDATION_RELATIVE_TOLERANCE",
    "LimitingCase",
    "LimitingCaseSuite",
    "ValidationResult",
    "validate_biomass_yield_limit",
    "validate_carbon_conservation",
    "validate_mass_balance",
    "validate_non_negative",
    "validate_oxygen_limitation",
]
