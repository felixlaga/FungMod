"""Screening and modelability APIs built on FungMod registries."""

from fungal_model.screening.case_builder import (
    RegistryCaseBuildError,
    RegistryCaseConfigMode,
    ResolvedRegistryCase,
    build_model_config_from_registry_case,
    build_resolved_case_config,
    registry_case_config_factory,
    resolve_registry_case,
    select_registry_case_template,
)
from fungal_model.screening.culture_physiology import (
    CULTURE_PHYSIOLOGY_PROCESS_TYPE,
    build_culture_physiology_config_data,
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
    resolve_screen_role_records,
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
    "CULTURE_PHYSIOLOGY_PROCESS_TYPE",
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
    "ResolvedRegistryCase",
    "ScreenSimulationMode",
    "assess_modelability",
    "build_culture_physiology_config_data",
    "build_extracellular_enzyme_chain_config",
    "build_model_config_from_registry_case",
    "build_resolved_case_config",
    "registry_case_config_factory",
    "resolve_registry_case",
    "resolve_screen_role_records",
    "run_extracellular_enzyme_chain_demo",
    "select_registry_case_template",
    "simulate_screen",
    "write_enzyme_chain_standard_tables",
]
