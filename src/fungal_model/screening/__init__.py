"""Screening and modelability APIs built on FungMod registries."""

from fungal_model.screening.case_builder import (
    RegistryCaseBuildError,
    RegistryCaseConfigMode,
    build_model_config_from_registry_case,
    select_registry_case_template,
)
from fungal_model.screening.enzyme_chain import (
    BIO002_ENZYME_CHAIN_TEMPLATE_ID,
    EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE,
    EnzymeChainAssemblyError,
    EnzymeChainRunResult,
    build_extracellular_enzyme_chain_config,
    run_extracellular_enzyme_chain_demo,
    write_enzyme_chain_standard_tables,
)
from fungal_model.screening.ensemble import (
    EnsembleSample,
    EnsembleSampleFailure,
    RegistryCaseEnsemble,
    RegistryScreenResult,
    RegistryScreenSimulationError,
    ScreenSimulationMode,
    simulate_screen,
)
from fungal_model.screening.modelability import (
    ModelabilityMode,
    ModelabilityReport,
    ModelabilityStatus,
    ReportItem,
    assess_modelability,
)

__all__ = [
    "RegistryCaseBuildError",
    "RegistryCaseConfigMode",
    "BIO002_ENZYME_CHAIN_TEMPLATE_ID",
    "EnsembleSample",
    "EnsembleSampleFailure",
    "EXTRACELLULAR_ENZYME_CHAIN_PROCESS_TYPE",
    "EnzymeChainAssemblyError",
    "EnzymeChainRunResult",
    "ModelabilityMode",
    "ModelabilityReport",
    "ModelabilityStatus",
    "RegistryCaseEnsemble",
    "RegistryScreenResult",
    "RegistryScreenSimulationError",
    "ReportItem",
    "ScreenSimulationMode",
    "assess_modelability",
    "build_extracellular_enzyme_chain_config",
    "build_model_config_from_registry_case",
    "run_extracellular_enzyme_chain_demo",
    "select_registry_case_template",
    "simulate_screen",
    "write_enzyme_chain_standard_tables",
]
