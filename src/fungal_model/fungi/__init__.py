"""Fungal physiology interfaces."""

from .base import Fungus, fungal_stage6_assumption, make_fungal_parameter_set
from .coupling import FUNGAL_COUPLING_MATURITY, FungalCouplingModel
from .energetics import GibbsEnergyYieldBound, GrowthEnergeticsError
from .enzyme_profile import (
    EnzymeCapability,
    EnzymeDecayRateLaw,
    EnzymeProductionCostRateLaw,
    EnzymeProfile,
    EnzymeSecretionRateLaw,
    enzyme_decay_rate,
    enzyme_production_cost_rate,
    enzyme_secretion_rate,
)
from .growth import BiomassMaintenanceRateLaw, biomass_maintenance_rate
from .degradation import DegradingCulture, DegradingCultureTrajectory, DEGRADING_CULTURE_MATURITY, secretion_allocation
from .respiration import CultureTrajectory, ResourceLimitedCulture, RespiratoryGrowthModel, RESPIRATION_MATURITY
from .metabolism import (
    ProductAssimilation,
    ProductUptakeRateLaw,
    biomass_yield_coefficient,
    product_uptake_rate,
)

__all__ = [
    "DegradingCulture",
    "DegradingCultureTrajectory",
    "DEGRADING_CULTURE_MATURITY",
    "secretion_allocation",
    "CultureTrajectory",
    "ResourceLimitedCulture",
    "RespiratoryGrowthModel",
    "RESPIRATION_MATURITY",
    "GibbsEnergyYieldBound",
    "GrowthEnergeticsError",
    "BiomassMaintenanceRateLaw",
    "EnzymeCapability",
    "EnzymeDecayRateLaw",
    "EnzymeProductionCostRateLaw",
    "EnzymeProfile",
    "EnzymeSecretionRateLaw",
    "FUNGAL_COUPLING_MATURITY",
    "FungalCouplingModel",
    "Fungus",
    "ProductAssimilation",
    "ProductUptakeRateLaw",
    "biomass_maintenance_rate",
    "biomass_yield_coefficient",
    "enzyme_decay_rate",
    "enzyme_production_cost_rate",
    "enzyme_secretion_rate",
    "fungal_stage6_assumption",
    "make_fungal_parameter_set",
    "product_uptake_rate",
]
