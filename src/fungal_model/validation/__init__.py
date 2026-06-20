"""Validation helpers for physical and numerical checks."""

from fungal_model.core.validators import (
    LimitingCase,
    LimitingCaseSuite,
    ValidationResult,
    validate_biomass_yield_limit,
    validate_carbon_conservation,
    validate_charge_balance,
    validate_condition_specific_gibbs_feasibility,
    validate_electron_balance,
    validate_elemental_balance,
    validate_mass_balance,
    validate_non_negative,
    validate_oxygen_limitation,
    validate_reaction_quotient_gibbs_feasibility,
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
from fungal_model.validation.bio_readiness import (
    BioReadinessIssue,
    BioReadinessReport,
    BioReadinessValidationError,
    REQUIRED_BIO_MECHANISM_FIELDS,
    enforce_bio_mechanism_proposal,
    load_bio_mechanism_proposal,
    validate_bio_mechanism_proposal,
    validate_bio_mechanism_proposal_file,
)

__all__ = [
    "BioReadinessIssue",
    "BioReadinessReport",
    "BioReadinessValidationError",
    "InvalidDataMaturityError",
    "LimitingCase",
    "LimitingCaseSuite",
    "MaturityIssue",
    "REQUIRED_BIO_MECHANISM_FIELDS",
    "ValidationResult",
    "enforce_run_maturity",
    "enforce_bio_mechanism_proposal",
    "load_bio_mechanism_proposal",
    "validate_biomass_yield_limit",
    "validate_bio_mechanism_proposal",
    "validate_bio_mechanism_proposal_file",
    "validate_carbon_conservation",
    "validate_charge_balance",
    "validate_condition_specific_gibbs_feasibility",
    "validate_diffusion_smooths_gradient",
    "validate_electron_balance",
    "validate_elemental_balance",
    "validate_mass_balance",
    "validate_no_flux_spatial_integral_conserved",
    "validate_non_negative",
    "validate_oxygen_limitation",
    "validate_reaction_quotient_gibbs_feasibility",
    "validate_run_maturity",
    "validate_spatial_average_close_to_expected",
]
