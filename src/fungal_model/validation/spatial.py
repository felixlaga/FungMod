"""Spatial validation helpers for Stage 8 reaction-diffusion models."""

from __future__ import annotations

import numpy as np

from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.core.validators import DEFAULT_VALIDATION_RELATIVE_TOLERANCE, ValidationResult
from fungal_model.transport.diffusion import spatial_integral_1d, spatial_variance


def validate_diffusion_smooths_gradient(
    result,
    *,
    field: str,
) -> ValidationResult:
    """Check that final spatial variance is lower than initial variance."""

    values = result.fields[field]
    initial = Q_(np.asarray(values.magnitude)[0], values.units)
    final = Q_(np.asarray(values.magnitude)[-1], values.units)
    initial_variance = spatial_variance(initial)
    final_variance = spatial_variance(final)
    initial_value = float(initial_variance.magnitude)
    final_value = float(final_variance.to(initial_variance.units).magnitude)
    passed = final_value <= initial_value
    return ValidationResult(
        name="diffusion_smooths_gradient",
        passed=passed,
        message=(
            "Final spatial variance is not greater than initial variance."
            if passed
            else "Final spatial variance increased."
        ),
        details={
            "field": field,
            "initial_variance": initial_value,
            "final_variance": final_value,
            "variance_units": str(initial_variance.units),
        },
    )


def validate_no_flux_spatial_integral_conserved(
    result,
    *,
    field: str,
    relative_tolerance: Quantity | None = None,
) -> ValidationResult:
    """Check that a field's spatial integral is conserved."""

    epsilon = relative_tolerance or DEFAULT_VALIDATION_RELATIVE_TOLERANCE.quantity
    epsilon_value = float(assert_compatible(epsilon, "dimensionless").magnitude)
    values = result.fields[field]
    initial = spatial_integral_1d(
        Q_(np.asarray(values.magnitude)[0], values.units),
        cell_width=result.grid.cell_width,
    )
    final = spatial_integral_1d(
        Q_(np.asarray(values.magnitude)[-1], values.units),
        cell_width=result.grid.cell_width,
    ).to(initial.units)
    initial_value = float(initial.magnitude)
    final_value = float(final.magnitude)
    scale = max(1.0, abs(initial_value), abs(final_value))
    relative_error = abs(final_value - initial_value) / scale
    passed = relative_error <= epsilon_value
    return ValidationResult(
        name="no_flux_spatial_integral_conserved",
        passed=passed,
        message=(
            "Spatial integral was conserved within tolerance."
            if passed
            else "Spatial integral changed beyond tolerance."
        ),
        details={
            "field": field,
            "initial_integral": initial_value,
            "final_integral": final_value,
            "integral_units": str(initial.units),
            "relative_error": relative_error,
            "relative_tolerance": epsilon_value,
        },
    )


def validate_spatial_average_close_to_expected(
    result,
    *,
    field: str,
    expected_average: Quantity,
    relative_tolerance: Quantity | None = None,
) -> ValidationResult:
    """Check final spatial average against an expected well-mixed value."""

    epsilon = relative_tolerance or DEFAULT_VALIDATION_RELATIVE_TOLERANCE.quantity
    epsilon_value = float(assert_compatible(epsilon, "dimensionless").magnitude)
    final_average = result.spatial_average(field)
    expected = assert_compatible(expected_average, str(final_average.units), name="expected_average")
    final_value = float(final_average.magnitude)
    expected_value = float(expected.magnitude)
    scale = max(1.0, abs(final_value), abs(expected_value))
    relative_error = abs(final_value - expected_value) / scale
    passed = relative_error <= epsilon_value
    return ValidationResult(
        name="spatial_average_close_to_expected",
        passed=passed,
        message=(
            "Final spatial average is close to the expected value."
            if passed
            else "Final spatial average differs from the expected value."
        ),
        details={
            "field": field,
            "final_average": final_value,
            "expected_average": expected_value,
            "units": str(final_average.units),
            "relative_error": relative_error,
            "relative_tolerance": epsilon_value,
        },
    )


__all__ = [
    "validate_diffusion_smooths_gradient",
    "validate_no_flux_spatial_integral_conserved",
    "validate_spatial_average_close_to_expected",
]

