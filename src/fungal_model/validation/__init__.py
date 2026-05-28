"""Validation helpers for physical and numerical checks."""

from fungal_model.core.validators import (
    LimitingCase,
    LimitingCaseSuite,
    ValidationResult,
    validate_biomass_yield_limit,
    validate_carbon_conservation,
    validate_mass_balance,
    validate_non_negative,
    validate_oxygen_limitation,
)
from fungal_model.validation.spatial import (
    validate_diffusion_smooths_gradient,
    validate_no_flux_spatial_integral_conserved,
    validate_spatial_average_close_to_expected,
)
from fungal_model.validation.maturity import (
    InvalidDataMaturityError,
    MaturityIssue,
    enforce_run_maturity,
    validate_run_maturity,
)

__all__ = [
    "InvalidDataMaturityError",
    "LimitingCase",
    "LimitingCaseSuite",
    "MaturityIssue",
    "ValidationResult",
    "enforce_run_maturity",
    "validate_biomass_yield_limit",
    "validate_carbon_conservation",
    "validate_diffusion_smooths_gradient",
    "validate_mass_balance",
    "validate_no_flux_spatial_integral_conserved",
    "validate_non_negative",
    "validate_oxygen_limitation",
    "validate_run_maturity",
    "validate_spatial_average_close_to_expected",
]
