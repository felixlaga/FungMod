"""Generic configured-model workflow entry points."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fungal_model.io.model_config import ModelConfigError, load_model_config
from fungal_model.io.registries import (
    GeometryLoaderRegistry,
    ProductMapRegistry,
    SubstrateLoaderRegistry,
    ValidatorRegistry,
)
from fungal_model.processes import ProcessLibrary
from fungal_model.results import SimulationResult
from fungal_model.validation.maturity import enforce_run_maturity
from fungal_model.workflows.configured_errors import (
    ConfiguredModelExecutionError,
    ConfiguredModelRunReport,
    raise_configured_model_execution_error,
    raise_configured_model_loading_error,
)
from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
from fungal_model.workflows.configured_outputs import ConfiguredOutputWriter
from fungal_model.workflows.configured_processes import (
    ConfiguredProcessAssembler,
    require_runnable_config,
)


@dataclass(frozen=True)
class ConfiguredModelRunner:
    """Orchestrate loading, maturity preflight, assembly, execution, and output."""

    input_loader: ConfiguredInputLoader = field(default_factory=ConfiguredInputLoader)
    process_assembler: ConfiguredProcessAssembler = field(default_factory=ConfiguredProcessAssembler)
    output_writer: ConfiguredOutputWriter = field(default_factory=ConfiguredOutputWriter)

    def run(
        self,
        config_path: str | Path,
        output_dir: str | Path | None = None,
    ) -> SimulationResult:
        try:
            config = load_model_config(config_path)
        except (OSError, ModelConfigError, ValueError) as exc:
            raise_configured_model_loading_error(
                config_path,
                message=str(exc),
                details={"error_type": type(exc).__name__},
            )
        require_runnable_config(config)
        inputs = self.input_loader.load(config)
        enforce_run_maturity(
            mode=config.mode,
            maturity=config.maturity,
            parameters=inputs.parameters,
            entities=inputs.maturity_entities(),
            product_maps=inputs.product_maps,
            process_configs=config.processes,
        )
        assembly = self.process_assembler.assemble(config, inputs)
        try:
            result = assembly.model.run(
                initial_state=inputs.initial_state,
                t_span=inputs.t_span,
                t_eval=inputs.t_eval,
                label=config.mode,
                name=config.name,
            )
        except ValueError as exc:
            raise_configured_model_execution_error(
                config,
                stage="model_execution",
                missing_capabilities=("successful_model_execution",),
                message=str(exc),
                details={"error_type": type(exc).__name__},
            )
        failed_validations = [
            validation
            for validation in result.validation_report()
            if _strict_validation_blocks(validation)
        ]
        if config.mode == "strict" and failed_validations:
            raise_configured_model_execution_error(
                config,
                stage="result_validation",
                missing_capabilities=("passing_validators",),
                message="Strict mode requires all configured validators to pass.",
                details={"failed_validations": failed_validations},
            )
        self.output_writer.write_result_bundle(
            config=config,
            inputs=inputs,
            decisions=assembly.decisions,
            result=result,
            output_dir=output_dir,
        )
        return result


def run_configured_model(
    config_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    substrate_registry: SubstrateLoaderRegistry | None = None,
    geometry_registry: GeometryLoaderRegistry | None = None,
    product_map_registry: ProductMapRegistry | None = None,
    validator_registry: ValidatorRegistry | None = None,
    process_library: ProcessLibrary | None = None,
) -> SimulationResult:
    """Load, assemble, run, validate, and optionally save a generic model config."""

    runner = ConfiguredModelRunner(
        input_loader=ConfiguredInputLoader(
            substrate_registry=substrate_registry,
            geometry_registry=geometry_registry,
            product_map_registry=product_map_registry,
            validator_registry=validator_registry,
        ),
        process_assembler=ConfiguredProcessAssembler(process_library=process_library),
    )
    return runner.run(config_path, output_dir=output_dir)


def _strict_validation_blocks(validation: dict[str, object]) -> bool:
    passed = bool(validation.get("passed"))
    status = str(validation.get("status") or ("passed" if passed else "failed"))
    severity = str(validation.get("severity") or ("info" if passed else "error"))
    required = bool(validation.get("required", True))
    if status == "inconclusive":
        return required
    if status == "unsupported":
        return True
    if status == "failed":
        return severity in {"error", "blocker"} or required
    return not passed and required


__all__ = [
    "ConfiguredModelExecutionError",
    "ConfiguredModelRunReport",
    "ConfiguredModelRunner",
    "run_configured_model",
]
