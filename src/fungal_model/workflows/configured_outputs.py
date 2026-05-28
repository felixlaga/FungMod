"""Output writing for generic configured-model workflows."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fungal_model.core.units import Quantity, is_quantity
from fungal_model.io.model_config import ConfigReference, ModelConfig
from fungal_model.results import SimulationResult
from fungal_model.workflows.configured_inputs import ConfiguredInputs


@dataclass(frozen=True)
class ConfiguredOutputWriter:
    """Persist configured-model result bundles."""

    def write_result_bundle(
        self,
        *,
        config: ModelConfig,
        inputs: ConfiguredInputs,
        decisions: tuple[Any, ...],
        result: SimulationResult,
        output_dir: str | Path | None = None,
    ) -> Path | None:
        destination = self.output_directory(config, output_dir)
        if destination is None:
            return None
        result.save(destination, mass_balance_weights=_mass_balance_weights(config))
        self.write_configured_bundle(
            destination,
            config=config,
            inputs=inputs,
            decisions=decisions,
            result=result,
        )
        return destination

    def output_directory(self, config: ModelConfig, override: str | Path | None) -> Path | None:
        if override is not None:
            return Path(override)
        if config.outputs.directory is None:
            return None
        return Path(config.outputs.directory)

    def write_configured_bundle(
        self,
        destination: Path,
        *,
        config: ModelConfig,
        inputs: ConfiguredInputs,
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


def _mass_balance_weights(config: ModelConfig) -> Mapping[str, float] | None:
    for validator in config.validators:
        if validator.validator_type == "mass_balance" and "conserved_weights" in validator.settings:
            return {
                str(name): float(value)
                for name, value in validator.settings["conserved_weights"].items()
            }
    return None


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
    inputs: ConfiguredInputs,
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
    "ConfiguredOutputWriter",
]
