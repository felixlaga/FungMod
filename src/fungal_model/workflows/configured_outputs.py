"""Output writing for generic configured-model workflows."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
import json
import platform
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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
        thermodynamic_summary = _thermodynamic_summary(result)
        if thermodynamic_summary["count"] > 0:
            _write_json(destination / "thermodynamic_summary.json", thermodynamic_summary)
            _write_csv(
                destination / "thermodynamic_summary.csv",
                thermodynamic_summary["rows"],
            )
        _write_json(destination / "merged_parameters.json", inputs.parameters.to_dict())
        _write_json(destination / "run_environment.json", _run_environment())
        _write_json(destination / "package_versions.json", _package_versions(result))
        _write_json(destination / "source_revision.json", _source_revision(config))
        _write_json(destination / "solver_settings.json", _solver_settings(result))
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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(value) for key, value in row.items()})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, sort_keys=True, default=_json_default)
    return value


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
    provenance = config.raw.get("provenance", {})
    return {
        "config_name": config.name,
        "config_path": "" if config.path is None else str(config.path),
        "mode": config.mode,
        "maturity": config.maturity,
        "kind": config.kind,
        "provenance": dict(provenance) if isinstance(provenance, Mapping) else {},
        "result_name": result.name,
        "result_label": result.label,
        "model_version": result.model_version,
        "state_count": len(result.states),
        "process_rate_count": len(result.process_rates),
        "configured_process_modifiers": _configured_process_modifiers(config),
        "validation": _validation_summary(result),
    }


def _configured_process_modifiers(config: ModelConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for process in config.processes:
        for index, modifier in enumerate(process.modifiers):
            rows.append(_configured_process_modifier_row(process.id, index, modifier))
    return rows


def _configured_process_modifier_row(
    process_id: str,
    index: int,
    modifier: Mapping[str, Any],
) -> dict[str, Any]:
    modifier_type = modifier.get("type", modifier.get("modifier_type", ""))
    row: dict[str, Any] = {
        "process_id": process_id,
        "modifier_index": index,
        "type": modifier_type,
    }
    if modifier_type == "product_inhibition":
        row.update(
            {
                "product_state": modifier.get("product_state", ""),
                "inhibition_constant": modifier.get(
                    "inhibition_constant",
                    modifier.get("inhibition_constant_symbol", modifier.get("K_i", "")),
                ),
                "maturity": "exploratory_configured_mechanism",
                "limitation": (
                    "Single-product reversible inhibition only; configured "
                    "only when product_state and positive unit-compatible K_i are explicit."
                ),
            }
        )
    elif modifier_type == "temperature_arrhenius_reference":
        row.update(
            {
                "environment_value": "temperature",
                "activation_energy_symbol": modifier.get(
                    "activation_energy_symbol",
                    modifier.get("activation_energy", ""),
                ),
                "reference_temperature_symbol": modifier.get(
                    "reference_temperature_symbol",
                    modifier.get("reference_temperature", ""),
                ),
                "minimum_temperature_symbol": modifier.get(
                    "minimum_temperature_symbol",
                    modifier.get("minimum_temperature", ""),
                ),
                "maximum_temperature_symbol": modifier.get(
                    "maximum_temperature_symbol",
                    modifier.get("maximum_temperature", ""),
                ),
                "maturity": "exploratory_configured_mechanism",
                "limitation": (
                    "Arrhenius reference-temperature scaling only; configured only when "
                    "environment temperature and explicit unit-compatible parameters are present."
                ),
            }
        )
    elif modifier_type == "ph_gaussian":
        row.update(
            {
                "environment_value": "ph",
                "optimum_symbol": modifier.get(
                    "optimum_symbol",
                    modifier.get("optimum_ph_symbol", modifier.get("optimum", modifier.get("optimum_ph", ""))),
                ),
                "width_symbol": modifier.get("width_symbol", modifier.get("width", "")),
                "minimum_ph_symbol": modifier.get("minimum_ph_symbol", modifier.get("minimum_ph", "")),
                "maximum_ph_symbol": modifier.get("maximum_ph_symbol", modifier.get("maximum_ph", "")),
                "maturity": "exploratory_configured_mechanism",
                "limitation": (
                    "Gaussian empirical pH activity scaling only; configured only when "
                    "environment pH and explicit unit-compatible parameters are present."
                ),
            }
        )
    elif modifier_type == "oxygen_monod":
        row.update(
            {
                "environment_value": "oxygen_concentration",
                "half_saturation_symbol": modifier.get(
                    "half_saturation_symbol",
                    modifier.get("oxygen_half_saturation_symbol", modifier.get("half_saturation", modifier.get("K_O2", ""))),
                ),
                "oxygen_units": modifier.get("oxygen_units", ""),
                "maturity": "exploratory_configured_mechanism",
                "limitation": (
                    "Monod oxygen scaling only; configured only when environment oxygen "
                    "concentration and explicit positive unit-compatible half-saturation are present. "
                    "No oxygen consumption, gas transfer, redox balance, or anaerobic metabolism."
                ),
            }
        )
    elif modifier_type == "water_activity_threshold":
        row.update(
            {
                "environment_value": "water_activity",
                "minimum_water_activity_symbol": modifier.get(
                    "minimum_water_activity_symbol",
                    modifier.get("minimum_water_activity", ""),
                ),
                "maturity": "exploratory_configured_mechanism",
                "limitation": (
                    "Binary water-activity threshold scaling only; configured only when environment "
                    "water activity and an explicit unit-compatible threshold parameter are present. "
                    "No smooth response curve, hysteresis, substrate water binding, or spatial moisture model."
                ),
            }
        )
    else:
        row.update(
            {
                "maturity": "unsupported_configured_modifier",
                "limitation": "Unsupported modifier type; configured execution should reject this process modifier.",
            }
        )
    return row


def _validation_summary(result: SimulationResult) -> dict[str, Any]:
    report = result.validation_report()
    return {
        "count": len(report),
        "passed": bool(report) and all(bool(item.get("passed")) for item in report),
        "status_counts": _count_by_key(report, "status"),
        "severity_counts": _count_by_key(report, "severity"),
        "inconclusive": [item for item in report if item.get("status") == "inconclusive"],
        "unsupported": [item for item in report if item.get("status") == "unsupported"],
        "failed": [item for item in report if not bool(item.get("passed"))],
    }


def _thermodynamic_summary(result: SimulationResult) -> dict[str, Any]:
    thermodynamic_rows = [
        item
        for item in result.validation_report()
        if _is_thermodynamic_validation(item)
    ]
    reaction_quotient_rows = [
        item
        for item in thermodynamic_rows
        if item.get("name") == "reaction_quotient_thermodynamic_feasibility"
    ]
    entropy_rate_rows = [
        item
        for item in thermodynamic_rows
        if item.get("name") == "entropy_production_rate_metadata"
    ]
    entropy_budget = _entropy_budget_summary(entropy_rate_rows)
    return {
        "kind": "configured_thermodynamic_summary",
        "count": len(thermodynamic_rows),
        "status_counts": _count_by_key(thermodynamic_rows, "status"),
        "severity_counts": _count_by_key(thermodynamic_rows, "severity"),
        "has_reaction_quotient_gibbs": bool(reaction_quotient_rows),
        "has_entropy_production_rate": bool(entropy_rate_rows),
        **entropy_budget,
        "has_solver_time_enforcement": False,
        "supported_scope": (
            "Explicit condition-specific and caller-supplied reaction-quotient "
            "Gibbs metadata checks plus configured entropy-production-rate diagnostics only."
        ),
        "unsupported_scope": (
            "No inferred activity model, inferred reaction quotient, concentration model, "
            "redox-potential model, electron-balance model, or solver-time thermodynamic enforcement."
        ),
        "rows": [_thermodynamic_summary_row(item) for item in thermodynamic_rows],
    }


def _entropy_budget_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    for row in rows:
        details = row.get("details", {})
        if not isinstance(details, Mapping):
            continue
        if details.get("entropy_production_rate_units") != "joule / second / kelvin":
            continue
        value = details.get("entropy_production_rate")
        if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
            continue
        numeric_value = float(cast(float, value))
        if np.isfinite(numeric_value):
            values.append(numeric_value)

    negative_count = sum(1 for value in values if value < 0.0)
    if not values:
        status = "not_evaluated"
    elif negative_count:
        status = "negative_entropy_production_rate_detected"
    else:
        status = "non_negative"

    return {
        "has_entropy_budget": bool(values),
        "entropy_budget_scope": (
            "Aggregate over explicit configured entropy_production_rate_metadata rows "
            "with numeric entropy_production_rate values and units exactly "
            "joule / second / kelvin."
        ),
        "entropy_budget_units": "joule / second / kelvin",
        "entropy_budget_total": sum(values) if values else None,
        "entropy_budget_minimum": min(values) if values else None,
        "entropy_budget_negative_count": negative_count,
        "entropy_budget_evaluated_count": len(values),
        "entropy_budget_status": status,
        "entropy_budget_limitations": (
            "Missing, non-numeric, or differently unitized entropy-rate values are "
            "left unevaluated and are not treated as zero. This is a configured "
            "metadata summary only; it does not infer thermodynamic quantities or "
            "enforce solver-time feasibility."
        ),
    }

def _is_thermodynamic_validation(item: Mapping[str, Any]) -> bool:
    name = str(item.get("name", ""))
    details = item.get("details", {})
    return (
        name
        in {
            "thermodynamic_feasibility",
            "reaction_quotient_thermodynamic_feasibility",
            "entropy_production_rate_metadata",
        }
        or (
            isinstance(details, Mapping)
            and str(details.get("residual_name", "")).endswith("delta_gibbs")
        )
    )


def _thermodynamic_summary_row(item: Mapping[str, Any]) -> dict[str, Any]:
    details = item.get("details", {})
    details_map = details if isinstance(details, Mapping) else {}
    residual_name = details_map.get("residual_name", "")
    is_gibbs_residual = str(residual_name).endswith("delta_gibbs")
    residual_value = details_map.get("residual_value", "")
    residual_units = details_map.get("residual_units", "")
    return {
        "name": item.get("name", ""),
        "status": item.get("status", ""),
        "passed": bool(item.get("passed")),
        "severity": item.get("severity", ""),
        "required": bool(item.get("required")),
        "message": item.get("message", ""),
        "reaction_name": details_map.get("reaction_name", ""),
        "residual_name": residual_name,
        "residual_value": residual_value,
        "residual_units": residual_units,
        "delta_gibbs": residual_value if is_gibbs_residual else "",
        "delta_gibbs_units": residual_units if is_gibbs_residual else "",
        "standard_delta_gibbs": details_map.get("standard_delta_gibbs", ""),
        "reaction_quotient": details_map.get("reaction_quotient", ""),
        "temperature_K": details_map.get("temperature_K", ""),
        "rt_ln_q": details_map.get("rt_ln_q", ""),
        "entropy_production_per_mole": details_map.get("entropy_production_per_mole", ""),
        "entropy_production_units": details_map.get("entropy_production_units", ""),
        "condition_specific_delta_gibbs": details_map.get("condition_specific_delta_gibbs", ""),
        "condition_specific_delta_gibbs_units": details_map.get("condition_specific_delta_gibbs_units", ""),
        "reaction_extent_rate": details_map.get("reaction_extent_rate", ""),
        "reaction_extent_rate_units": details_map.get("reaction_extent_rate_units", ""),
        "entropy_production_rate": details_map.get("entropy_production_rate", ""),
        "entropy_production_rate_units": details_map.get("entropy_production_rate_units", ""),
        "gibbs_equation": details_map.get("gibbs_equation", ""),
        "entropy_equation": details_map.get("entropy_equation", ""),
        "dynamic_reaction_quotient": details_map.get("dynamic_reaction_quotient", ""),
        "activity_model": details_map.get("activity_model", ""),
        "solver_time_enforcement": details_map.get("solver_time_enforcement", ""),
        "missing_metadata": details_map.get("missing_metadata", []),
        "provenance_refs": details_map.get("provenance_refs", []),
    }


def _count_by_key(report: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report:
        value = str(item.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _run_environment() -> dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "python": {
            "version": sys.version,
            "version_info": list(sys.version_info[:3]),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "working_directory": str(Path.cwd()),
    }


def _package_versions(result: SimulationResult) -> dict[str, Any]:
    distributions = ("fungal-model", "numpy", "scipy", "pint", "matplotlib", "PyYAML")
    return {
        "fungal_model": {
            "version": result.model_version,
            "distribution": "fungal-model",
        },
        "distributions": {
            distribution: _distribution_version(distribution)
            for distribution in distributions
        },
    }


def _distribution_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def _source_revision(config: ModelConfig) -> dict[str, Any]:
    cwd = Path.cwd() if config.path is None else config.path.parent
    root, root_error = _git_text(("git", "rev-parse", "--show-toplevel"), cwd=cwd)
    if root is None:
        return {
            "available": False,
            "root": None,
            "commit": None,
            "branch": None,
            "dirty": None,
            "error": root_error,
        }
    root_path = Path(root)
    commit, commit_error = _git_text(("git", "rev-parse", "HEAD"), cwd=root_path)
    branch, branch_error = _git_text(("git", "rev-parse", "--abbrev-ref", "HEAD"), cwd=root_path)
    status, status_error = _git_text(("git", "status", "--porcelain"), cwd=root_path)
    errors = [error for error in (commit_error, branch_error, status_error) if error is not None]
    return {
        "available": commit is not None,
        "root": root,
        "commit": commit,
        "branch": branch,
        "dirty": None if status is None else bool(status),
        "error": "; ".join(errors) if errors else None,
    }


def _git_text(command: tuple[str, ...], *, cwd: Path) -> tuple[str | None, str | None]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        message = stderr or stdout or f"{command[0]} exited with status {completed.returncode}"
        return None, message
    return stdout, None


def _solver_settings(result: SimulationResult) -> dict[str, Any]:
    return {
        "solver_settings": result.solver_settings.to_dict(),
        "solver_metadata": dict(result.solver_metadata),
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
