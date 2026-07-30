"""Process assembly for generic configured-model workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fungal_model.core.errors import (
    IncompatibleUnitsError,
    InvalidMechanismError,
    MissingParameterError,
    MissingProcessError,
    ModelAssemblyError,
)
from fungal_model.io.model_config import ModelConfig
from fungal_model.processes import (
    AssembledModel,
    ModelBuilder,
    Process,
    ProcessBuildContext,
    ProcessLibrary,
    ProcessRegistry,
)
from fungal_model.workflows.configured_errors import raise_configured_model_execution_error
from fungal_model.workflows.configured_inputs import ConfiguredInputs
from fungal_model.workflows.dynamic_thermodynamics import (
    configured_dynamic_thermodynamic_constraints,
)
from fungal_model.workflows.static_balance import (
    blocking_static_balance_validations,
    configured_static_balance_validations,
    static_validation_callable,
)


@dataclass(frozen=True)
class ConfiguredProcessAssembly:
    """Built process decisions and assembled model for a configured run."""

    decisions: tuple[Any, ...]
    processes: tuple[Process, ...]
    model: AssembledModel


@dataclass(frozen=True)
class ConfiguredProcessAssembler:
    """Build process objects and assemble an executable model from loaded inputs."""

    process_library: ProcessLibrary | None = None

    def assemble(self, config: ModelConfig, inputs: ConfiguredInputs) -> ConfiguredProcessAssembly:
        library = self.process_library or ProcessLibrary.default_foundation()
        build_context = ProcessBuildContext(
            state_units=inputs.state_units(),
            product_maps=inputs.product_maps,
            source=f"Configured process factory for {config.name}.",
        )
        try:
            decisions = library.build_decisions(build_context, config.processes)
        except InvalidMechanismError as exc:
            raise_configured_model_execution_error(
                config,
                stage="process_factory_build",
                missing_capabilities=("process_factory",),
                message=str(exc),
                details={
                    "error_type": type(exc).__name__,
                    "factory_types": list(library.factory_types()),
                    "process_types": [process.process_type for process in config.processes],
                },
            )
        rejected = tuple(decision for decision in decisions if not decision.can_build)
        if rejected:
            raise_configured_model_execution_error(
                config,
                stage="process_factory_build",
                missing_capabilities=("process_factory_requirements",),
                message="At least one configured process cannot be built by the process library.",
                details={"decisions": [decision.to_dict() for decision in decisions]},
            )
        try:
            processes = library.build_processes(build_context, config.processes)
        except ValueError as exc:
            raise_configured_model_execution_error(
                config,
                stage="process_factory_build",
                missing_capabilities=("process_factory_requirements",),
                message=str(exc),
                details={"error_type": type(exc).__name__},
            )
        try:
            static_balance_validations = configured_static_balance_validations(
                config,
                processes=processes,
                product_maps=inputs.product_maps,
            )
        except ValueError as exc:
            raise_configured_model_execution_error(
                config,
                stage="model_assembly",
                missing_capabilities=("static_balance_metadata",),
                message=str(exc),
                details={"error_type": type(exc).__name__},
            )
        blocking_validations = blocking_static_balance_validations(
            mode=config.mode,
            validations=static_balance_validations,
        )
        if blocking_validations:
            raise_configured_model_execution_error(
                config,
                stage="model_assembly",
                missing_capabilities=("static_balance_checks",),
                message="Assembly-time static balance checks failed or were inconclusive.",
                details={
                    "assembly_static_balance_checks": [
                        validation.to_dict()
                        for validation in static_balance_validations
                    ],
                    "blocking_static_balance_checks": [
                        validation.to_dict()
                        for validation in blocking_validations
                    ],
                },
            )
        try:
            thermodynamic_constraints = (
                configured_dynamic_thermodynamic_constraints(
                    config,
                    processes=processes,
                    state_units=inputs.state_units(),
                    static_balance_validations=static_balance_validations,
                )
            )
        except ValueError as exc:
            raise_configured_model_execution_error(
                config,
                stage="model_assembly",
                missing_capabilities=("dynamic_thermodynamic_constraints",),
                message=str(exc),
                details={"error_type": type(exc).__name__},
            )
        try:
            validators = (
                *inputs.validators,
                *(static_validation_callable(validation) for validation in static_balance_validations),
            )
            model = ModelBuilder(
                fungus=inputs.fungus,
                substrates=inputs.substrates,
                enzymes=inputs.enzymes,
                environment=inputs.environment,
                geometry=inputs.geometry,
                process_library=ProcessRegistry(processes),
                parameters=inputs.parameters,
                requested_processes=tuple(process.name for process in processes),
                validators=validators,
                static_balance_checks=tuple(
                    validation.to_dict()
                    for validation in static_balance_validations
                ),
                thermodynamic_constraints=thermodynamic_constraints,
                allow_unsourced_for_testing=config.mode == "toy",
            ).assemble()
        except ModelAssemblyError as exc:
            details: dict[str, Any] = {"error_type": type(exc).__name__}
            if exc.report is not None and hasattr(exc.report, "to_dict"):
                details["assembly_report"] = exc.report.to_dict()
            raise_configured_model_execution_error(
                config,
                stage="model_assembly",
                missing_capabilities=_assembly_missing_capabilities(exc),
                message=str(exc),
                details=details,
            )
        return ConfiguredProcessAssembly(
            decisions=decisions,
            processes=tuple(processes),
            model=model,
        )


def require_runnable_config(config: ModelConfig) -> None:
    missing: list[str] = []
    if not config.processes:
        missing.append("configured_processes")
    if not config.initial_state.states:
        missing.append("configured_initial_state")
    if missing:
        raise_configured_model_execution_error(
            config,
            stage="configured_model_execution",
            missing_capabilities=tuple(missing),
            message="Configured model is missing sections required for execution.",
        )


def _assembly_missing_capabilities(error: ModelAssemblyError) -> tuple[str, ...]:
    if isinstance(error, MissingParameterError):
        return ("required_parameters",)
    if isinstance(error, IncompatibleUnitsError):
        return ("compatible_parameter_units",)
    if isinstance(error, MissingProcessError):
        return ("requested_processes",)
    if isinstance(error, InvalidMechanismError):
        return ("compatible_mechanisms",)
    return ("model_assembly",)


__all__ = [
    "ConfiguredProcessAssembler",
    "ConfiguredProcessAssembly",
    "require_runnable_config",
]
