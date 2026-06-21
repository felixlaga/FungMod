"""Validation helpers for simulation outputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np

from fungal_model.chemistry.stoichiometry import (
    CarbonContent,
    DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE,
    OxygenDemand,
    StoichiometricReactionMetadata,
    charge_balance_residual,
    electron_balance_residual,
    element_balance_residual,
)
from fungal_model.chemistry.thermodynamics import GibbsFreeEnergyEstimate
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError, has_text
from fungal_model.core.units import Q_, Quantity, UnitError, assert_compatible, is_quantity

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

DEFAULT_THERMODYNAMIC_ABSOLUTE_TOLERANCE = Parameter(
    name="default thermodynamic absolute tolerance",
    symbol="epsilon_delta_g",
    value=0.0,
    units="joule / mole",
    uncertainty=None,
    source="Numerical sign-boundary convention for static Gibbs metadata checks; not a measured value.",
    confidence_level="testing",
    notes="Used only to compare explicitly supplied condition-specific Gibbs estimates to the zero boundary.",
    measurement_method="software configuration",
)


DEFAULT_ENTROPY_PRODUCTION_RATE_ABSOLUTE_TOLERANCE = Parameter(
    name="default entropy production rate absolute tolerance",
    symbol="epsilon_entropy_rate",
    value=0.0,
    units="joule / second / kelvin",
    uncertainty=None,
    source="Numerical sign-boundary convention for configured entropy-production-rate metadata checks.",
    confidence_level="testing",
    notes="Used only to compare explicitly supplied entropy-production-rate diagnostics to the zero boundary.",
    measurement_method="software configuration",
)


IDEAL_GAS_CONSTANT = Parameter(
    name="molar gas constant",
    symbol="R",
    value=8.31446261815324,
    units="joule / mole / kelvin",
    uncertainty=0.0,
    source="2019 SI definition/CODATA exact molar gas constant.",
    confidence_level="high",
    notes="Used only in explicit reaction-quotient Gibbs calculations.",
    measurement_method="physical constant",
)


@dataclass(frozen=True)
class ValidationResult:
    """Structured result of a validation check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    status: str | None = None
    severity: str | None = None
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        status = self.status or ("passed" if self.passed else "failed")
        severity = self.severity or ("info" if self.passed else "error")
        return {
            "name": self.name,
            "status": status,
            "passed": self.passed,
            "severity": severity,
            "required": self.required,
            "message": self.message,
            "details": self.details,
        }


def validate_elemental_balance(
    reaction: StoichiometricReactionMetadata,
    *,
    absolute_tolerance: float | None = None,
    required: bool = True,
    allow_unsourced_for_testing: bool = False,
) -> ValidationResult:
    """Validate explicit elemental stoichiometry metadata without inferring missing chemistry."""

    tolerance = _stoichiometric_tolerance_value(absolute_tolerance)
    base_details = _static_balance_details(
        reaction,
        residual_name="element_balance",
        residual_units="atom equivalents per reaction event",
        absolute_tolerance=tolerance,
        absolute_tolerance_units="atom equivalents per reaction event",
        required=required,
    )
    provenance_failure = _reaction_provenance_failure(
        reaction,
        allow_unsourced_for_testing=allow_unsourced_for_testing,
    )
    if provenance_failure is not None:
        return _status_result(
            name="elemental_balance",
            status="failed",
            message=str(provenance_failure),
            required=required,
            details={**base_details, "error_type": type(provenance_failure).__name__},
        )
    missing = _missing_compositions(reaction)
    if missing:
        return _status_result(
            name="elemental_balance",
            status="inconclusive",
            message="Elemental balance is inconclusive because at least one participant lacks composition metadata.",
            required=required,
            details={**base_details, "missing_metadata": missing},
        )
    residuals = element_balance_residual(reaction)
    max_abs_residual = max((abs(value) for value in residuals.values()), default=0.0)
    passed = max_abs_residual <= tolerance
    return _status_result(
        name="elemental_balance",
        status="passed" if passed else "failed",
        message=(
            "Elemental stoichiometry is balanced within tolerance."
            if passed
            else "Elemental stoichiometry is not balanced within tolerance."
        ),
        required=required,
        details={
            **base_details,
            "residuals": {
                element: {
                    "residual_value": residual,
                    "residual_units": "atom equivalents per reaction event",
                }
                for element, residual in sorted(residuals.items())
            },
            "max_abs_residual": max_abs_residual,
            "max_relative_residual": None,
        },
    )


def validate_charge_balance(
    reaction: StoichiometricReactionMetadata,
    *,
    absolute_tolerance: float | None = None,
    required: bool = True,
    allow_unsourced_for_testing: bool = False,
) -> ValidationResult:
    """Validate explicit charge stoichiometry metadata without inferring charges."""

    tolerance = _stoichiometric_tolerance_value(absolute_tolerance)
    base_details = _static_balance_details(
        reaction,
        residual_name="charge_balance",
        residual_units="elementary-charge equivalents per reaction event",
        absolute_tolerance=tolerance,
        absolute_tolerance_units="elementary-charge equivalents per reaction event",
        required=required,
    )
    provenance_failure = _reaction_provenance_failure(
        reaction,
        allow_unsourced_for_testing=allow_unsourced_for_testing,
    )
    if provenance_failure is not None:
        return _status_result(
            name="charge_balance",
            status="failed",
            message=str(provenance_failure),
            required=required,
            details={**base_details, "error_type": type(provenance_failure).__name__},
        )
    missing = _missing_scalar_metadata(reaction, field_name="charge")
    if missing:
        return _status_result(
            name="charge_balance",
            status="inconclusive",
            message="Charge balance is inconclusive because at least one participant lacks explicit charge metadata.",
            required=required,
            details={**base_details, "missing_metadata": missing},
        )
    missing_sources = _missing_scalar_sources(reaction, value_field="charge", source_field="charge_source")
    if missing_sources and not allow_unsourced_for_testing:
        return _status_result(
            name="charge_balance",
            status="failed",
            message="Charge balance metadata is missing provenance for at least one participant.",
            required=required,
            details={**base_details, "missing_metadata": missing_sources},
        )
    residual = charge_balance_residual(reaction)
    passed = abs(residual) <= tolerance
    return _status_result(
        name="charge_balance",
        status="passed" if passed else "failed",
        message=(
            "Charge stoichiometry is balanced within tolerance."
            if passed
            else "Charge stoichiometry is not balanced within tolerance."
        ),
        required=required,
        details={
            **base_details,
            "residual_value": residual,
            "max_abs_residual": abs(residual),
            "max_relative_residual": None,
        },
    )


def validate_electron_balance(
    reaction: StoichiometricReactionMetadata,
    *,
    absolute_tolerance: float | None = None,
    required: bool = True,
    allow_unsourced_for_testing: bool = False,
) -> ValidationResult:
    """Validate explicit electron-equivalent metadata without inferring redox chemistry."""

    tolerance = _stoichiometric_tolerance_value(absolute_tolerance)
    base_details = _static_balance_details(
        reaction,
        residual_name="electron_balance",
        residual_units="electron equivalents per reaction event",
        absolute_tolerance=tolerance,
        absolute_tolerance_units="electron equivalents per reaction event",
        required=required,
    )
    provenance_failure = _reaction_provenance_failure(
        reaction,
        allow_unsourced_for_testing=allow_unsourced_for_testing,
    )
    if provenance_failure is not None:
        return _status_result(
            name="electron_balance",
            status="failed",
            message=str(provenance_failure),
            required=required,
            details={**base_details, "error_type": type(provenance_failure).__name__},
        )
    missing = _missing_scalar_metadata(reaction, field_name="electron_equivalents")
    if missing:
        return _status_result(
            name="electron_balance",
            status="inconclusive",
            message=(
                "Electron/redox balance is inconclusive because at least one participant lacks "
                "explicit electron-equivalent metadata."
            ),
            required=required,
            details={**base_details, "missing_metadata": missing},
        )
    missing_sources = _missing_scalar_sources(
        reaction,
        value_field="electron_equivalents",
        source_field="electron_source",
    )
    if missing_sources and not allow_unsourced_for_testing:
        return _status_result(
            name="electron_balance",
            status="failed",
            message="Electron/redox balance metadata is missing provenance for at least one participant.",
            required=required,
            details={**base_details, "missing_metadata": missing_sources},
        )
    residual = electron_balance_residual(reaction)
    passed = abs(residual) <= tolerance
    return _status_result(
        name="electron_balance",
        status="passed" if passed else "failed",
        message=(
            "Electron/redox stoichiometry is balanced within tolerance."
            if passed
            else "Electron/redox stoichiometry is not balanced within tolerance."
        ),
        required=required,
        details={
            **base_details,
            "residual_value": residual,
            "max_abs_residual": abs(residual),
            "max_relative_residual": None,
        },
    )


def validate_condition_specific_gibbs_feasibility(
    estimate: GibbsFreeEnergyEstimate,
    *,
    absolute_tolerance: Quantity | None = None,
    required: bool = True,
    allow_unsourced_for_testing: bool = False,
) -> ValidationResult:
    """Validate an explicitly supplied condition-specific Gibbs estimate.

    This is a static metadata check. It does not compute reaction quotients,
    activities, or dynamic reaction Gibbs energy from a simulation trajectory.
    """

    tolerance = absolute_tolerance or DEFAULT_THERMODYNAMIC_ABSOLUTE_TOLERANCE.quantity
    tolerance_quantity = assert_compatible(tolerance, "joule / mole", name="absolute_tolerance")
    tolerance_value = float(tolerance_quantity.to("joule / mole").magnitude)
    base_details = {
        "reaction_name": estimate.reaction_name,
        "residual_name": "condition_specific_delta_gibbs",
        "residual_units": "joule / mole",
        "absolute_tolerance": tolerance_value,
        "absolute_tolerance_units": "joule / mole",
        "relative_tolerance": None,
        "scale_value": 1.0,
        "scale_units": "joule / mole",
        "required": required,
        "dynamic_reaction_quotient": "not_evaluated",
        "activity_model": "not_evaluated",
        "provenance_refs": _gibbs_provenance_refs(estimate),
        "evidence": {
            "source": estimate.source,
            "delta_gibbs_source": estimate.delta_gibbs.source,
            "condition_symbols": [parameter.symbol for parameter in estimate.conditions],
        },
        "missing_metadata": [],
    }
    try:
        estimate.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_value=False,
        )
    except ProvenanceError as exc:
        return _status_result(
            name="thermodynamic_feasibility",
            status="failed",
            message=str(exc),
            required=required,
            details={**base_details, "error_type": type(exc).__name__},
        )
    if len(estimate.conditions) == 0:
        return _status_result(
            name="thermodynamic_feasibility",
            status="inconclusive",
            message="Thermodynamic metadata is inconclusive because no condition-specific metadata were supplied.",
            required=required,
            details={**base_details, "missing_metadata": ["condition_specific_conditions"]},
        )
    unknown_conditions = [parameter.symbol for parameter in estimate.conditions if parameter.quantity is None]
    if unknown_conditions:
        return _status_result(
            name="thermodynamic_feasibility",
            status="inconclusive",
            message="Thermodynamic metadata is inconclusive because at least one condition value is unknown.",
            required=required,
            details={**base_details, "missing_metadata": [f"conditions.{symbol}" for symbol in unknown_conditions]},
        )
    if estimate.delta_gibbs.quantity is None:
        return _status_result(
            name="thermodynamic_feasibility",
            status="inconclusive",
            message="Thermodynamic metadata is inconclusive because delta G is explicitly unknown.",
            required=required,
            details={**base_details, "missing_metadata": ["delta_gibbs"]},
        )
    delta_g = estimate.value().to("joule / mole")
    delta_g_value = float(delta_g.magnitude)
    passed = delta_g_value <= tolerance_value
    return _status_result(
        name="thermodynamic_feasibility",
        status="passed" if passed else "failed",
        message=(
            "Stored condition-specific Gibbs estimate is favorable within tolerance; "
            "dynamic thermodynamic feasibility was not evaluated."
            if passed
            else "Stored condition-specific Gibbs estimate is unfavorable within tolerance; "
            "dynamic thermodynamic feasibility was not evaluated."
        ),
        required=required,
        details={
            **base_details,
            "residual_value": delta_g_value,
            "max_abs_residual": abs(delta_g_value),
            "max_relative_residual": None,
        },
    )


def validate_reaction_quotient_gibbs_feasibility(
    *,
    standard_estimate: GibbsFreeEnergyEstimate,
    reaction_quotient: Parameter,
    temperature: Parameter,
    absolute_tolerance: Quantity | None = None,
    required: bool = True,
    allow_unsourced_for_testing: bool = False,
) -> ValidationResult:
    """Validate explicitly supplied reaction-quotient Gibbs feasibility.

    Computes ``delta_g = delta_g_standard + R * T * ln(Q)`` from explicit,
    provenance-backed inputs. This does not infer activities, concentrations,
    or reaction quotients from a trajectory.
    """

    tolerance = absolute_tolerance or DEFAULT_THERMODYNAMIC_ABSOLUTE_TOLERANCE.quantity
    tolerance_quantity = assert_compatible(tolerance, "joule / mole", name="absolute_tolerance")
    tolerance_value = float(tolerance_quantity.to("joule / mole").magnitude)
    base_details = {
        "reaction_name": standard_estimate.reaction_name,
        "residual_name": "reaction_quotient_delta_gibbs",
        "residual_units": "joule / mole",
        "absolute_tolerance": tolerance_value,
        "absolute_tolerance_units": "joule / mole",
        "relative_tolerance": None,
        "scale_value": 1.0,
        "scale_units": "joule / mole",
        "required": required,
        "dynamic_reaction_quotient": "explicit_parameter",
        "activity_model": "caller_supplied_dimensionless_reaction_quotient",
        "gibbs_equation": "delta_g = delta_g_standard + R*T*ln(Q)",
        "entropy_equation": "entropy_production_per_mole = -delta_g / T",
        "provenance_refs": _gibbs_provenance_refs(standard_estimate)
        + _parameter_provenance_refs(reaction_quotient, temperature, IDEAL_GAS_CONSTANT),
        "missing_metadata": [],
    }
    try:
        standard_estimate.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_value=False,
        )
        reaction_quotient.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
        temperature.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
    except ProvenanceError as exc:
        return _status_result(
            name="reaction_quotient_thermodynamic_feasibility",
            status="failed",
            message=str(exc),
            required=required,
            details={**base_details, "error_type": type(exc).__name__},
        )
    standard_quantity = standard_estimate.delta_gibbs.quantity
    quotient_quantity = reaction_quotient.quantity
    temperature_quantity = temperature.quantity
    missing = []
    if standard_quantity is None:
        missing.append("delta_gibbs_standard")
    if quotient_quantity is None:
        missing.append("reaction_quotient")
    if temperature_quantity is None:
        missing.append("temperature")
    if missing:
        return _status_result(
            name="reaction_quotient_thermodynamic_feasibility",
            status="inconclusive",
            message="Reaction-quotient Gibbs feasibility is inconclusive because required metadata are unknown.",
            required=required,
            details={**base_details, "missing_metadata": missing},
        )
    standard_delta_g = assert_compatible(standard_quantity, "joule / mole", name=standard_estimate.delta_gibbs.symbol).to("joule / mole")
    q_value = float(assert_compatible(quotient_quantity, "dimensionless", name=reaction_quotient.symbol).magnitude)
    temperature_k = float(assert_compatible(temperature_quantity, "kelvin", name=temperature.symbol).to("kelvin").magnitude)
    if q_value <= 0.0:
        return _status_result(
            name="reaction_quotient_thermodynamic_feasibility",
            status="failed",
            message="Reaction quotient must be positive for ln(Q).",
            required=required,
            details={**base_details, "invalid_metadata": ["reaction_quotient_nonpositive"], "reaction_quotient": q_value},
        )
    if temperature_k <= 0.0:
        return _status_result(
            name="reaction_quotient_thermodynamic_feasibility",
            status="failed",
            message="Temperature must be positive in kelvin for reaction-quotient Gibbs feasibility.",
            required=required,
            details={**base_details, "invalid_metadata": ["temperature_nonpositive"], "temperature_K": temperature_k},
        )
    gas_constant_quantity = IDEAL_GAS_CONSTANT.quantity
    assert gas_constant_quantity is not None
    gas_constant = float(gas_constant_quantity.to("joule / mole / kelvin").magnitude)
    rt_ln_q = gas_constant * temperature_k * float(np.log(q_value))
    delta_g_value = float(standard_delta_g.magnitude) + rt_ln_q
    entropy_production = -delta_g_value / temperature_k
    passed = delta_g_value <= tolerance_value
    return _status_result(
        name="reaction_quotient_thermodynamic_feasibility",
        status="passed" if passed else "failed",
        message=(
            "Reaction-quotient Gibbs estimate is favorable within tolerance."
            if passed
            else "Reaction-quotient Gibbs estimate is unfavorable within tolerance."
        ),
        required=required,
        details={
            **base_details,
            "standard_delta_gibbs": float(standard_delta_g.magnitude),
            "standard_delta_gibbs_units": "joule / mole",
            "reaction_quotient": q_value,
            "temperature_K": temperature_k,
            "rt_ln_q": rt_ln_q,
            "rt_ln_q_units": "joule / mole",
            "residual_value": delta_g_value,
            "max_abs_residual": abs(delta_g_value),
            "max_relative_residual": None,
            "entropy_production_per_mole": entropy_production,
            "entropy_production_units": "joule / mole / kelvin",
        },
    )


def validate_entropy_production_rate(
    *,
    condition_specific_delta_gibbs: Parameter,
    reaction_extent_rate: Parameter,
    temperature: Parameter,
    absolute_tolerance: Quantity | None = None,
    required: bool = True,
    allow_unsourced_for_testing: bool = False,
) -> ValidationResult:
    """Validate configured entropy-production-rate metadata from explicit inputs.

    Computes ``entropy_production_rate = -delta_g * reaction_extent_rate / T``
    from caller-supplied, provenance-backed quantities. This is a metadata
    diagnostic only; it does not infer concentrations, activities, reaction
    quotients, redox potentials, or solver-time thermodynamic feasibility.
    """

    tolerance = absolute_tolerance or DEFAULT_ENTROPY_PRODUCTION_RATE_ABSOLUTE_TOLERANCE.quantity
    tolerance_quantity = assert_compatible(tolerance, "joule / second / kelvin", name="absolute_tolerance")
    tolerance_value = float(tolerance_quantity.to("joule / second / kelvin").magnitude)
    base_details = {
        "reaction_name": "configured explicit entropy-production-rate diagnostic",
        "residual_name": "entropy_production_rate",
        "residual_units": "joule / second / kelvin",
        "absolute_tolerance": tolerance_value,
        "absolute_tolerance_units": "joule / second / kelvin",
        "relative_tolerance": None,
        "scale_value": 1.0,
        "scale_units": "joule / second / kelvin",
        "required": required,
        "dynamic_reaction_quotient": "not_evaluated",
        "activity_model": "not_evaluated",
        "solver_time_enforcement": "not_evaluated",
        "entropy_equation": "entropy_production_rate = -condition_specific_delta_gibbs * reaction_extent_rate / temperature",
        "supported_scope": (
            "Configured entropy-production-rate diagnostic from explicit condition-specific delta G, "
            "reaction extent rate, and temperature metadata."
        ),
        "unsupported_scope": (
            "No inferred activities, reaction quotients, concentrations, redox potentials, electron balances, "
            "thermodynamic feasibility, or solver-time enforcement."
        ),
        "provenance_refs": _parameter_provenance_refs(
            condition_specific_delta_gibbs,
            reaction_extent_rate,
            temperature,
        ),
        "evidence": {
            "condition_specific_delta_gibbs_source": condition_specific_delta_gibbs.source,
            "reaction_extent_rate_source": reaction_extent_rate.source,
            "temperature_source": temperature.source,
            "input_symbols": [
                condition_specific_delta_gibbs.symbol,
                reaction_extent_rate.symbol,
                temperature.symbol,
            ],
        },
        "missing_metadata": [],
    }
    try:
        condition_specific_delta_gibbs.validate_provenance(
            allow_unsourced_for_testing=allow_unsourced_for_testing
        )
        reaction_extent_rate.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
        temperature.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
    except ProvenanceError as exc:
        return _status_result(
            name="entropy_production_rate_metadata",
            status="failed",
            message=str(exc),
            required=required,
            details={**base_details, "error_type": type(exc).__name__},
        )
    delta_g_quantity = condition_specific_delta_gibbs.quantity
    extent_rate_quantity = reaction_extent_rate.quantity
    temperature_quantity = temperature.quantity
    missing = []
    if delta_g_quantity is None:
        missing.append("condition_specific_delta_gibbs")
    if extent_rate_quantity is None:
        missing.append("reaction_extent_rate")
    if temperature_quantity is None:
        missing.append("temperature")
    if missing:
        return _status_result(
            name="entropy_production_rate_metadata",
            status="inconclusive",
            message="Entropy-production-rate metadata are inconclusive because required quantities are unknown.",
            required=required,
            details={**base_details, "missing_metadata": missing},
        )
    try:
        delta_g = assert_compatible(
            delta_g_quantity,
            "joule / mole",
            name=condition_specific_delta_gibbs.symbol,
        ).to("joule / mole")
        extent_rate = assert_compatible(
            extent_rate_quantity,
            "mole / second",
            name=reaction_extent_rate.symbol,
        ).to("mole / second")
        temperature_k = float(
            assert_compatible(temperature_quantity, "kelvin", name=temperature.symbol)
            .to("kelvin")
            .magnitude
        )
    except UnitError as exc:
        return _status_result(
            name="entropy_production_rate_metadata",
            status="failed",
            message=str(exc),
            required=required,
            details={**base_details, "error_type": type(exc).__name__},
        )
    if temperature_k <= 0.0:
        return _status_result(
            name="entropy_production_rate_metadata",
            status="failed",
            message="Temperature must be positive in kelvin for entropy-production-rate diagnostics.",
            required=required,
            details={**base_details, "invalid_metadata": ["temperature_nonpositive"], "temperature_K": temperature_k},
        )
    delta_g_value = float(delta_g.magnitude)
    extent_rate_value = float(extent_rate.magnitude)
    entropy_rate = -delta_g_value * extent_rate_value / temperature_k
    passed = entropy_rate >= -tolerance_value
    return _status_result(
        name="entropy_production_rate_metadata",
        status="passed" if passed else "failed",
        message=(
            "Configured entropy-production-rate diagnostic is non-negative within tolerance."
            if passed
            else "Configured entropy-production-rate diagnostic is negative within tolerance."
        ),
        required=required,
        details={
            **base_details,
            "condition_specific_delta_gibbs": delta_g_value,
            "condition_specific_delta_gibbs_units": "joule / mole",
            "reaction_extent_rate": extent_rate_value,
            "reaction_extent_rate_units": "mole / second",
            "temperature_K": temperature_k,
            "residual_value": entropy_rate,
            "max_abs_residual": abs(entropy_rate),
            "max_relative_residual": None,
            "entropy_production_rate": entropy_rate,
            "entropy_production_rate_units": "joule / second / kelvin",
        },
    )


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
    failures: dict[str, dict[str, float | str]] = {}
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
        total = term if total is None else cast(Quantity, total + term.to(total.units))
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
        total = carbon if total is None else cast(Quantity, total + carbon.to(total.units))
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


def _status_result(
    *,
    name: str,
    status: str,
    message: str,
    details: dict[str, Any],
    required: bool,
) -> ValidationResult:
    passed = status in {"passed", "not_applicable", "skipped"}
    severity = _severity_for_status(status=status, required=required)
    enriched_details = {
        **details,
        "status": status,
        "severity": severity,
        "required": required,
    }
    return ValidationResult(
        name=name,
        passed=passed,
        status=status,
        severity=severity,
        required=required,
        message=message,
        details=enriched_details,
    )


def _severity_for_status(*, status: str, required: bool) -> str:
    if status == "passed":
        return "info"
    if status == "inconclusive":
        return "error" if required else "warning"
    if status in {"failed", "unsupported"}:
        return "error" if required else "warning"
    return "info"


def _stoichiometric_tolerance_value(absolute_tolerance: float | None) -> float:
    if absolute_tolerance is None:
        return float(DEFAULT_STOICHIOMETRIC_ABSOLUTE_TOLERANCE.quantity.magnitude)
    tolerance = float(absolute_tolerance)
    if tolerance < 0.0:
        raise ValueError("absolute_tolerance must be non-negative.")
    return tolerance


def _static_balance_details(
    reaction: StoichiometricReactionMetadata,
    *,
    residual_name: str,
    residual_units: str,
    absolute_tolerance: float,
    absolute_tolerance_units: str,
    required: bool,
) -> dict[str, Any]:
    return {
        "reaction_name": reaction.name,
        "residual_name": residual_name,
        "residual_units": residual_units,
        "absolute_tolerance": absolute_tolerance,
        "absolute_tolerance_units": absolute_tolerance_units,
        "relative_tolerance": None,
        "scale_value": 1.0,
        "scale_units": residual_units,
        "time_of_max_residual": None,
        "required": required,
        "missing_metadata": [],
        "provenance_refs": _reaction_provenance_refs(reaction),
        "evidence": {
            "reaction_source": reaction.source,
            "reactants": [_term_evidence(term) for term in reaction.reactants],
            "products": [_term_evidence(term) for term in reaction.products],
        },
    }


def _reaction_provenance_failure(
    reaction: StoichiometricReactionMetadata,
    *,
    allow_unsourced_for_testing: bool,
) -> ProvenanceError | None:
    try:
        reaction.validate(allow_unsourced_for_testing=allow_unsourced_for_testing)
    except ProvenanceError as exc:
        return exc
    return None


def _missing_compositions(reaction: StoichiometricReactionMetadata) -> list[dict[str, str]]:
    return [
        {"species": term.species, "field": "composition"}
        for term in (*reaction.reactants, *reaction.products)
        if term.composition is None
    ]


def _missing_scalar_metadata(
    reaction: StoichiometricReactionMetadata,
    *,
    field_name: str,
) -> list[dict[str, str]]:
    return [
        {"species": term.species, "field": field_name}
        for term in (*reaction.reactants, *reaction.products)
        if getattr(term, field_name) is None
    ]


def _missing_scalar_sources(
    reaction: StoichiometricReactionMetadata,
    *,
    value_field: str,
    source_field: str,
) -> list[dict[str, str]]:
    return [
        {"species": term.species, "field": source_field}
        for term in (*reaction.reactants, *reaction.products)
        if getattr(term, value_field) is not None and not has_text(getattr(term, source_field))
    ]


def _reaction_provenance_refs(reaction: StoichiometricReactionMetadata) -> list[str]:
    refs: list[str] = []
    if has_text(reaction.source):
        refs.append(str(reaction.source))
    for term in (*reaction.reactants, *reaction.products):
        if term.composition is not None and has_text(term.composition.source):
            refs.append(str(term.composition.source))
        if has_text(term.charge_source):
            refs.append(str(term.charge_source))
        if has_text(term.electron_source):
            refs.append(str(term.electron_source))
    return sorted(set(refs))


def _term_evidence(term: Any) -> dict[str, Any]:
    return {
        "species": term.species,
        "coefficient": term.coefficient,
        "composition_source": None if term.composition is None else term.composition.source,
        "charge_source": term.charge_source,
        "electron_source": term.electron_source,
    }


def _gibbs_provenance_refs(estimate: GibbsFreeEnergyEstimate) -> list[str]:
    refs: list[str] = []
    if has_text(estimate.source):
        refs.append(str(estimate.source))
    if has_text(estimate.delta_gibbs.source):
        refs.append(str(estimate.delta_gibbs.source))
    refs.extend(str(parameter.source) for parameter in estimate.conditions if has_text(parameter.source))
    return sorted(set(refs))


def _parameter_provenance_refs(*parameters: Parameter) -> list[str]:
    return sorted({str(parameter.source) for parameter in parameters if has_text(parameter.source)})


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
    "DEFAULT_ENTROPY_PRODUCTION_RATE_ABSOLUTE_TOLERANCE",
    "DEFAULT_THERMODYNAMIC_ABSOLUTE_TOLERANCE",
    "DEFAULT_VALIDATION_RELATIVE_TOLERANCE",
    "LimitingCase",
    "LimitingCaseSuite",
    "ValidationResult",
    "validate_biomass_yield_limit",
    "validate_carbon_conservation",
    "validate_charge_balance",
    "validate_condition_specific_gibbs_feasibility",
    "validate_electron_balance",
    "validate_elemental_balance",
    "validate_entropy_production_rate",
    "validate_mass_balance",
    "validate_non_negative",
    "validate_oxygen_limitation",
    "validate_reaction_quotient_gibbs_feasibility",
]
