"""Generic configured-model workflow entry points."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, is_quantity
from fungal_model.io.model_config import ConfigReference, ModelConfig, load_model_config
from fungal_model.io.parameters import (
    ParameterMergeError,
    merge_parameter_sets,
    parameter_set_from_config,
)
from fungal_model.io.product_maps import load_product_map
from fungal_model.io.registries import (
    GeometryLoaderRegistry,
    ProductMapRegistry,
    RegistryLookupError,
    SubstrateLoaderRegistry,
    ValidatorRegistry,
)
from fungal_model.io.yaml_loader import (
    load_enzyme,
    load_environment,
    load_fungus,
    load_geometry,
    load_parameter_set,
    load_substrate,
)
from fungal_model.processes import ModelBuilder, ProcessBuildContext, ProcessLibrary, ProcessRegistry
from fungal_model.results import SimulationResult


@dataclass(frozen=True)
class ConfiguredModelRunReport:
    """Structured report for configured-model run attempts."""

    config_name: str
    config_path: str
    stage: str
    missing_capabilities: tuple[str, ...]
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_name": self.config_name,
            "config_path": self.config_path,
            "stage": self.stage,
            "missing_capabilities": list(self.missing_capabilities),
            "message": self.message,
            "details": dict(self.details),
        }


class ConfiguredModelExecutionError(RuntimeError):
    """Raised when a configured model cannot be executed generically."""

    def __init__(self, message: str, *, report: ConfiguredModelRunReport) -> None:
        super().__init__(message)
        self.report = report


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

    config = load_model_config(config_path)
    _require_runnable_config(config)
    inputs = _load_configured_inputs(
        config,
        substrate_registry=substrate_registry,
        geometry_registry=geometry_registry,
        product_map_registry=product_map_registry,
        validator_registry=validator_registry,
    )
    library = process_library or ProcessLibrary.default_foundation()
    build_context = ProcessBuildContext(
        state_units=_state_units(inputs.initial_state),
        product_maps=inputs.product_maps,
        source=f"Configured process factory for {config.name}.",
    )
    decisions = library.build_decisions(build_context, config.processes)
    rejected = tuple(decision for decision in decisions if not decision.can_build)
    if rejected:
        _raise_execution_error(
            config,
            stage="process_factory_build",
            missing_capabilities=("process_factory_requirements",),
            message="At least one configured process cannot be built by the process library.",
            details={"decisions": [decision.to_dict() for decision in decisions]},
        )
    processes = library.build_processes(build_context, config.processes)
    model = ModelBuilder(
        fungus=inputs.fungus,
        substrates=inputs.substrates,
        enzymes=inputs.enzymes,
        environment=inputs.environment,
        geometry=inputs.geometry,
        process_library=ProcessRegistry(processes),
        parameters=inputs.parameters,
        requested_processes=tuple(process.name for process in processes),
        validators=inputs.validators,
        allow_unsourced_for_testing=config.mode == "toy",
    ).assemble()
    result = model.run(
        initial_state=inputs.initial_state,
        t_span=inputs.t_span,
        t_eval=inputs.t_eval,
        label=config.mode,
        name=config.name,
    )
    destination = _output_directory(config, output_dir)
    if destination is not None:
        result.save(destination, mass_balance_weights=_mass_balance_weights(config))
        _save_configured_output_bundle(
            destination,
            config=config,
            inputs=inputs,
            decisions=decisions,
            result=result,
        )
    return result


@dataclass(frozen=True)
class _ConfiguredInputs:
    fungus: Any | None
    substrates: tuple[Any, ...]
    enzymes: tuple[Any, ...]
    environment: Any | None
    geometry: Any | None
    product_maps: Mapping[str, Any]
    parameters: ParameterSet
    validators: tuple[Any, ...]
    initial_state: Mapping[str, Quantity]
    t_span: tuple[Quantity, Quantity]
    t_eval: Quantity | None


def _load_configured_inputs(
    config: ModelConfig,
    *,
    substrate_registry: SubstrateLoaderRegistry | None,
    geometry_registry: GeometryLoaderRegistry | None,
    product_map_registry: ProductMapRegistry | None,
    validator_registry: ValidatorRegistry | None,
) -> _ConfiguredInputs:
    try:
        substrates = tuple(
            _load_substrate_reference(reference, config, substrate_registry)
            for reference in config.entities.substrates
        )
        geometry = _load_geometry_reference(config.entities.geometry, config, geometry_registry)
        product_maps = {
            reference.id: _load_product_map_reference(reference, config, product_map_registry)
            for reference in config.entities.product_maps
        }
        parameter_sets = [
            *_entity_parameter_sets(
                fungus=None,
                substrates=substrates,
                enzymes=(),
            ),
            *_configured_parameter_sets(config),
        ]
        fungus = _load_fungus_reference(config.entities.fungus, config)
        enzymes = tuple(_load_enzyme_reference(reference, config) for reference in config.entities.enzymes)
        environment = _load_environment_reference(config.entities.environment, config)
        parameter_sets.extend(_entity_parameter_sets(fungus=fungus, substrates=(), enzymes=enzymes))
        parameters = merge_parameter_sets(parameter_sets)
        validators = tuple(
            (validator_registry or ValidatorRegistry.default()).load(validator.to_dict())
            for validator in config.validators
        )
    except (ParameterMergeError, RegistryLookupError, ValueError) as exc:
        _raise_execution_error(
            config,
            stage="configured_input_loading",
            missing_capabilities=(),
            message=str(exc),
            details={"error_type": type(exc).__name__},
        )

    return _ConfiguredInputs(
        fungus=fungus,
        substrates=substrates,
        enzymes=enzymes,
        environment=environment,
        geometry=geometry,
        product_maps=product_maps,
        parameters=parameters,
        validators=validators,
        initial_state=_initial_state(config),
        t_span=_time_span(config),
        t_eval=_time_eval(config),
    )


def _require_runnable_config(config: ModelConfig) -> None:
    missing: list[str] = []
    if not config.processes:
        missing.append("configured_processes")
    if not config.initial_state.states:
        missing.append("configured_initial_state")
    if missing:
        _raise_execution_error(
            config,
            stage="configured_model_execution",
            missing_capabilities=tuple(missing),
            message="Configured model is missing sections required for execution.",
        )


def _load_substrate_reference(
    reference: ConfigReference,
    config: ModelConfig,
    registry: SubstrateLoaderRegistry | None,
) -> Any:
    if reference.data is not None:
        return (registry or SubstrateLoaderRegistry.default()).load(
            _with_loader_key(reference.data, reference.loader, key="substrate_type")
        )
    return load_substrate(_resolve_path(reference, config), registry=registry)


def _load_geometry_reference(
    reference: ConfigReference | None,
    config: ModelConfig,
    registry: GeometryLoaderRegistry | None,
) -> Any | None:
    if reference is None:
        return None
    if reference.data is not None:
        return (registry or GeometryLoaderRegistry.default()).load(
            _with_loader_key(reference.data, reference.loader, key="geometry_type")
        )
    return load_geometry(_resolve_path(reference, config), registry=registry)


def _load_product_map_reference(
    reference: ConfigReference,
    config: ModelConfig,
    registry: ProductMapRegistry | None,
) -> Any:
    if reference.data is not None:
        return (registry or ProductMapRegistry.default()).load(
            _with_loader_key(reference.data, reference.loader, key="product_map_type")
        )
    return load_product_map(_resolve_path(reference, config), registry=registry)


def _load_environment_reference(reference: ConfigReference | None, config: ModelConfig) -> Any | None:
    if reference is None:
        return None
    _require_path_reference(reference, entity_name="environment")
    return load_environment(_resolve_path(reference, config))


def _load_fungus_reference(reference: ConfigReference | None, config: ModelConfig) -> Any | None:
    if reference is None:
        return None
    _require_path_reference(reference, entity_name="fungus")
    return load_fungus(_resolve_path(reference, config))


def _load_enzyme_reference(reference: ConfigReference, config: ModelConfig) -> Any:
    _require_path_reference(reference, entity_name="enzyme")
    return load_enzyme(_resolve_path(reference, config))


def _configured_parameter_sets(config: ModelConfig) -> list[ParameterSet]:
    parameter_sets: list[ParameterSet] = []
    for parameter_config in config.parameters:
        if parameter_config.path is not None:
            parameter_sets.append(load_parameter_set(_resolve_config_path(parameter_config.path, config)))
        if parameter_config.parameters:
            parameter_sets.append(parameter_set_from_config({"parameters": list(parameter_config.parameters)}))
    return parameter_sets


def _entity_parameter_sets(
    *,
    fungus: Any | None,
    substrates: tuple[Any, ...],
    enzymes: tuple[Any, ...],
) -> list[ParameterSet]:
    parameter_sets: list[ParameterSet] = []
    if fungus is not None and hasattr(fungus, "parameters"):
        parameter_sets.append(fungus.parameters)
    for substrate in substrates:
        if hasattr(substrate, "parameters"):
            parameter_sets.append(substrate.parameters)
    for enzyme in enzymes:
        if hasattr(enzyme, "catalytic_parameters"):
            parameter_sets.append(enzyme.catalytic_parameters)
        if hasattr(enzyme, "adsorption_parameters"):
            parameter_sets.append(enzyme.adsorption_parameters)
    return parameter_sets


def _initial_state(config: ModelConfig) -> dict[str, Quantity]:
    return {
        name: _quantity(value, field_name=f"initial_state.{name}")
        for name, value in config.initial_state.states.items()
    }


def _time_span(config: ModelConfig) -> tuple[Quantity, Quantity]:
    return (
        _quantity(config.time.start, field_name="time.start"),
        _quantity(config.time.stop, field_name="time.stop"),
    )


def _time_eval(config: ModelConfig) -> Quantity | None:
    if config.time.points is None:
        return None
    start, stop = _time_span(config)
    units = str(stop.units)
    values = np.linspace(
        float(start.to(units).magnitude),
        float(stop.to(units).magnitude),
        config.time.points,
    )
    return Q_(values, units)


def _state_units(initial_state: Mapping[str, Quantity]) -> dict[str, str]:
    return {name: str(quantity.units) for name, quantity in initial_state.items()}


def _quantity(data: Mapping[str, Any], *, field_name: str) -> Quantity:
    if "value" not in data or "units" not in data:
        raise ValueError(f"{field_name} requires value and units.")
    return Q_(data["value"], data["units"])


def _mass_balance_weights(config: ModelConfig) -> Mapping[str, float] | None:
    for validator in config.validators:
        if validator.validator_type == "mass_balance" and "conserved_weights" in validator.settings:
            return {
                str(name): float(value)
                for name, value in validator.settings["conserved_weights"].items()
            }
    return None


def _output_directory(config: ModelConfig, override: str | Path | None) -> Path | None:
    if override is not None:
        return Path(override)
    if config.outputs.directory is None:
        return None
    return Path(config.outputs.directory)


def _save_configured_output_bundle(
    destination: Path,
    *,
    config: ModelConfig,
    inputs: _ConfiguredInputs,
    decisions: tuple[Any, ...],
    result: SimulationResult,
) -> None:
    _write_json(destination / "input_model_config.json", config.to_dict())
    _write_json(destination / "configured_model_run.json", _run_summary(config, result))
    _write_json(destination / "configured_metadata.json", _configured_metadata(config, result))
    _write_json(
        destination / "process_build_decisions.json",
        {
            "decisions": [decision.to_dict() for decision in decisions],
        },
    )
    _write_json(
        destination / "initial_state.json",
        {
            name: _quantity_to_dict(quantity)
            for name, quantity in inputs.initial_state.items()
        },
    )
    _write_json(
        destination / "time_grid.json",
        {
            "span": [_quantity_to_dict(value) for value in inputs.t_span],
            "evaluation": None if inputs.t_eval is None else _quantity_to_dict(inputs.t_eval),
        },
    )
    _write_json(
        destination / "validators.json",
        {
            "configured": [validator.to_dict() for validator in config.validators],
            "summary": _validation_summary(result),
        },
    )
    _write_json(destination / "merged_parameters.json", inputs.parameters.to_dict())
    _write_entity_snapshots(destination, config=config, inputs=inputs)
    _write_output_manifest(destination, config=config, result=result)


def _resolve_path(reference: ConfigReference, config: ModelConfig) -> Path:
    _require_path_reference(reference, entity_name=reference.id)
    assert reference.path is not None
    return _resolve_config_path(reference.path, config)


def _resolve_config_path(path: str, config: ModelConfig) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    if config.path is not None:
        sibling = config.path.parent / candidate
        if sibling.exists():
            return sibling
    return candidate


def _require_path_reference(reference: ConfigReference, *, entity_name: str) -> None:
    if reference.path is None:
        raise ValueError(f"Configured {entity_name} loading currently requires a path reference.")


def _with_loader_key(
    data: Mapping[str, Any],
    loader: str | None,
    *,
    key: str,
) -> Mapping[str, Any]:
    if loader is None or key in data:
        return data
    copied = dict(data)
    copied[key] = loader
    return copied


def _raise_execution_error(
    config: ModelConfig,
    *,
    stage: str,
    missing_capabilities: tuple[str, ...],
    message: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    report = _report(
        config,
        stage=stage,
        missing_capabilities=missing_capabilities,
        message=message,
        details={} if details is None else details,
    )
    raise ConfiguredModelExecutionError(message, report=report)


def _report(
    config: ModelConfig,
    *,
    stage: str,
    missing_capabilities: tuple[str, ...],
    message: str,
    details: Mapping[str, Any],
) -> ConfiguredModelRunReport:
    path = "" if config.path is None else str(config.path)
    return ConfiguredModelRunReport(
        config_name=config.name,
        config_path=path,
        stage=stage,
        missing_capabilities=missing_capabilities,
        message=message,
        details=details,
    )


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _run_summary(config: ModelConfig, result: SimulationResult) -> dict[str, Any]:
    assembly_report = result.assembly_report
    if assembly_report is None:
        assembly_success = None
    elif isinstance(assembly_report, Mapping):
        assembly_success = assembly_report.get("success")
    else:
        assembly_success = assembly_report.success
    return {
        "config_name": config.name,
        "config_path": "" if config.path is None else str(config.path),
        "mode": config.mode,
        "maturity": config.maturity,
        "result_name": result.name,
        "result_label": result.label,
        "assembly_success": assembly_success,
        "state_names": sorted(result.states),
        "process_rate_names": sorted(result.process_rates),
        "validation": _validation_summary(result),
        "validation_report": result.validation_report(),
        "solver_metadata": dict(result.solver_metadata),
    }


def _configured_metadata(config: ModelConfig, result: SimulationResult) -> dict[str, Any]:
    return {
        "config_name": config.name,
        "config_path": "" if config.path is None else str(config.path),
        "mode": config.mode,
        "maturity": config.maturity,
        "kind": config.kind,
        "result_name": result.name,
        "result_label": result.label,
        "model_version": result.model_version,
        "state_count": len(result.states),
        "process_rate_count": len(result.process_rates),
        "validation": _validation_summary(result),
    }


def _validation_summary(result: SimulationResult) -> dict[str, Any]:
    report = result.validation_report()
    return {
        "count": len(report),
        "passed": bool(report) and all(bool(item.get("passed")) for item in report),
        "failed": [item for item in report if not bool(item.get("passed"))],
    }


def _write_entity_snapshots(
    destination: Path,
    *,
    config: ModelConfig,
    inputs: _ConfiguredInputs,
) -> None:
    root = destination / "entity_snapshots"
    entries: list[dict[str, Any]] = []
    if config.entities.fungus is not None and inputs.fungus is not None:
        entries.append(
            _write_entity_snapshot(
                root / "fungus.json",
                role="fungus",
                reference=config.entities.fungus,
                entity=inputs.fungus,
                output_root=destination,
            )
        )
    if config.entities.environment is not None and inputs.environment is not None:
        entries.append(
            _write_entity_snapshot(
                root / "environment.json",
                role="environment",
                reference=config.entities.environment,
                entity=inputs.environment,
                output_root=destination,
            )
        )
    if config.entities.geometry is not None and inputs.geometry is not None:
        entries.append(
            _write_entity_snapshot(
                root / "geometry.json",
                role="geometry",
                reference=config.entities.geometry,
                entity=inputs.geometry,
                output_root=destination,
            )
        )
    for reference, substrate in zip(config.entities.substrates, inputs.substrates, strict=True):
        entries.append(
            _write_entity_snapshot(
                root / "substrates" / f"{_safe_id(reference.id)}.json",
                role="substrate",
                reference=reference,
                entity=substrate,
                output_root=destination,
            )
        )
    for reference, enzyme in zip(config.entities.enzymes, inputs.enzymes, strict=True):
        entries.append(
            _write_entity_snapshot(
                root / "enzymes" / f"{_safe_id(reference.id)}.json",
                role="enzyme",
                reference=reference,
                entity=enzyme,
                output_root=destination,
            )
        )
    for reference in config.entities.product_maps:
        entries.append(
            _write_entity_snapshot(
                root / "product_maps" / f"{_safe_id(reference.id)}.json",
                role="product_map",
                reference=reference,
                entity=inputs.product_maps[reference.id],
                output_root=destination,
            )
        )
    _write_json(root / "index.json", {"entities": entries})


def _write_entity_snapshot(
    path: Path,
    *,
    role: str,
    reference: ConfigReference,
    entity: Any,
    output_root: Path,
) -> dict[str, Any]:
    _write_json(path, entity.to_dict() if hasattr(entity, "to_dict") else {"value": str(entity)})
    return {
        "role": role,
        "id": reference.id,
        "loader": reference.loader,
        "source_path": reference.path,
        "snapshot_path": _relative_output_path(path, output_root),
    }


def _write_output_manifest(
    destination: Path,
    *,
    config: ModelConfig,
    result: SimulationResult,
) -> None:
    manifest_path = destination / "output_manifest.json"
    files = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file() and path != manifest_path
    )
    _write_json(
        manifest_path,
        {
            "config_name": config.name,
            "mode": config.mode,
            "maturity": config.maturity,
            "result_name": result.name,
            "files": [*files, "output_manifest.json"],
        },
    )


def _relative_output_path(path: Path, output_root: Path) -> str:
    return path.relative_to(output_root).as_posix()


def _safe_id(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    if clean:
        return clean
    return "snapshot"


def _quantity_to_dict(quantity: Quantity) -> dict[str, Any]:
    return {
        "value": np.asarray(quantity.magnitude, dtype=float).tolist(),
        "units": str(quantity.units),
    }


def _json_default(value: Any) -> Any:
    if is_quantity(value):
        return {"value": np.asarray(value.magnitude, dtype=float).tolist(), "units": str(value.units)}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")


__all__ = [
    "ConfiguredModelExecutionError",
    "ConfiguredModelRunReport",
    "run_configured_model",
]
