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
from pint.errors import DimensionalityError, PintError

from fungal_model.core.units import Q_, Quantity, is_quantity
from fungal_model.io.model_config import (
    ConfigReference,
    EntropyProductionRateTimeseriesConfig,
    ModelConfig,
)
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
        _clear_stale_entropy_artifacts(destination)
        entropy_timeseries = (
            _entropy_production_rate_timeseries(config, result)
            if config.outputs.entropy_production_rate_timeseries
            else None
        )
        result.save(destination, mass_balance_weights=_mass_balance_weights(config))
        self.write_configured_bundle(
            destination,
            config=config,
            inputs=inputs,
            decisions=decisions,
            result=result,
            entropy_timeseries=entropy_timeseries,
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
        entropy_timeseries: dict[str, Any] | None = None,
    ) -> None:
        _clear_stale_entropy_artifacts(destination)
        if entropy_timeseries is None and config.outputs.entropy_production_rate_timeseries:
            entropy_timeseries = _entropy_production_rate_timeseries(config, result)
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
        if entropy_timeseries is not None:
            _write_json(
                destination / "entropy_production_rate_timeseries.json",
                entropy_timeseries,
            )
            _write_csv_with_fieldnames(
                destination / "entropy_production_rate_timeseries.csv",
                entropy_timeseries["rows"],
                _ENTROPY_PRODUCTION_RATE_TIMESERIES_COLUMNS,
            )
        conservation_diagnostics = _conservation_diagnostics(config, result)
        _write_json(destination / "conservation_diagnostics.json", conservation_diagnostics)
        _write_csv_with_fieldnames(
            destination / "conservation_diagnostics.csv",
            conservation_diagnostics["rows"],
            _CONSERVATION_DIAGNOSTIC_COLUMNS,
        )
        solver_diagnostics = _solver_diagnostics(config, inputs, result)
        _write_json(destination / "solver_diagnostics.json", solver_diagnostics)
        _write_csv_with_fieldnames(
            destination / "solver_diagnostics.csv",
            solver_diagnostics["rows"],
            _SOLVER_DIAGNOSTIC_COLUMNS,
        )
        _write_json(destination / "merged_parameters.json", inputs.parameters.to_dict())
        _write_json(destination / "run_environment.json", _run_environment())
        _write_json(destination / "package_versions.json", _package_versions(result))
        _write_json(destination / "source_revision.json", _source_revision(config))
        _write_json(destination / "solver_settings.json", _solver_settings(result))
        _write_entity_snapshots(destination, config=config, inputs=inputs)
        _write_output_manifest(destination, config=config, result=result)


def _clear_stale_entropy_artifacts(destination: Path) -> None:
    for filename in (
        "entropy_production_rate_timeseries.json",
        "entropy_production_rate_timeseries.csv",
        "output_manifest.json",
    ):
        (destination / filename).unlink(missing_ok=True)


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
    _write_csv_with_fieldnames(path, rows, fieldnames)


def _write_csv_with_fieldnames(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: tuple[str, ...] | list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


class ConfiguredEntropyProductionError(ValueError):
    """Raised when configured process entropy diagnostics cannot be evaluated honestly."""


_ENTROPY_PRODUCTION_RATE_GUARDRAIL = (
    "Post-simulation diagnostic from an explicitly bound native process-rate trajectory, "
    "explicit condition-specific delta Gibbs, explicit positive temperature, and any "
    "explicit unit conversion shown in this artifact. No dynamic delta Gibbs, inferred "
    "activities or concentrations, solver-time enforcement, validation, calibration, or "
    "biological claim."
)

_ENTROPY_PRODUCTION_RATE_TIMESERIES_COLUMNS = (
    "diagnostic_id",
    "process_id",
    "index",
    "time",
    "time_units",
    "process_rate",
    "process_rate_units",
    "extent_rate",
    "extent_rate_units",
    "condition_specific_delta_gibbs",
    "condition_specific_delta_gibbs_units",
    "temperature",
    "temperature_units",
    "entropy_production_rate",
    "entropy_production_rate_units",
    "status",
    "condition_specific_delta_gibbs_source",
    "temperature_source",
    "process_rate_to_extent_rate_source",
    "provenance_refs",
    "guardrails",
)


def _entropy_production_rate_timeseries(
    config: ModelConfig,
    result: SimulationResult,
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    configured_process_ids = {process.id for process in config.processes}
    for metadata in config.outputs.entropy_production_rate_timeseries:
        if metadata.process_id not in configured_process_ids:
            raise ConfiguredEntropyProductionError(
                f"Entropy diagnostic {metadata.id!r} binds unknown configured process "
                f"{metadata.process_id!r}."
            )
        process_rate = result.process_rates.get(metadata.process_id)
        if process_rate is None:
            raise ConfiguredEntropyProductionError(
                f"Entropy diagnostic {metadata.id!r} process {metadata.process_id!r} "
                "has no native process-rate trajectory in SimulationResult."
            )
        diagnostic, diagnostic_rows = _process_entropy_diagnostic(
            metadata=metadata,
            process_rate=process_rate,
            time=result.time,
        )
        diagnostics.append(diagnostic)
        rows.extend(diagnostic_rows)
    return {
        "kind": "configured_process_entropy_production_rate_timeseries",
        "diagnostic_count": len(diagnostics),
        "evaluated_count": len(diagnostics),
        "row_count": len(rows),
        "status": "evaluated",
        "equation": "entropy_production_rate(t) = -condition_specific_delta_gibbs * extent_rate(t) / temperature",
        "has_dynamic_delta_gibbs": False,
        "has_solver_time_enforcement": False,
        "supported_scope": (
            "Explicit process-bound post-simulation entropy-production-rate trajectories "
            "derived from native process-rate trajectories and dimensionally compatible "
            "caller-supplied metadata only."
        ),
        "unsupported_scope": (
            "No inferred reaction quotient, activity, concentration, redox potential, "
            "electron balance, dynamic delta Gibbs, solver-time enforcement, validation, "
            "calibration, or biological interpretation."
        ),
        "diagnostics": diagnostics,
        "rows": rows,
    }


def _process_entropy_diagnostic(
    *,
    metadata: EntropyProductionRateTimeseriesConfig,
    process_rate: Quantity,
    time: Quantity,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    delta_gibbs = _sourced_scalar_quantity(
        metadata.condition_specific_delta_gibbs,
        diagnostic_id=metadata.id,
        field_name="condition_specific_delta_gibbs",
    )
    temperature = _sourced_scalar_quantity(
        metadata.temperature,
        diagnostic_id=metadata.id,
        field_name="temperature",
    )
    if _is_temperature_interval(temperature):
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} temperature must be an absolute "
            "temperature, not a temperature interval."
        )
    try:
        delta_gibbs_canonical = delta_gibbs.to("joule / mole")
    except DimensionalityError as exc:
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} condition_specific_delta_gibbs must be "
            "compatible with energy per amount of substance."
        ) from exc
    try:
        temperature_canonical = temperature.to("kelvin")
    except DimensionalityError as exc:
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} temperature must be compatible with kelvin."
        ) from exc
    if float(temperature_canonical.magnitude) <= 0.0:
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} temperature must be positive in kelvin."
        )

    conversion = None
    converted_rate = process_rate
    if metadata.process_rate_to_extent_rate is not None:
        conversion = _sourced_scalar_quantity(
            metadata.process_rate_to_extent_rate,
            diagnostic_id=metadata.id,
            field_name="process_rate_to_extent_rate",
        )
        if float(conversion.magnitude) <= 0.0:
            raise ConfiguredEntropyProductionError(
                f"Entropy diagnostic {metadata.id!r} process_rate_to_extent_rate must be positive."
            )
        converted_rate = process_rate * conversion
    try:
        Q_(1.0, metadata.extent_rate_units).to("mole / second")
        extent_rate = converted_rate.to(metadata.extent_rate_units)
    except (PintError, TypeError, ValueError) as exc:
        conversion_note = "with the explicit conversion" if conversion is not None else "without an explicit conversion"
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} native process rate {process_rate.units} "
            f"is not compatible with extent-rate units {metadata.extent_rate_units!r} "
            f"{conversion_note}."
        ) from exc

    time_values = np.asarray(time.magnitude, dtype=float)
    process_rate_values = np.asarray(process_rate.magnitude, dtype=float)
    extent_rate_values = np.asarray(extent_rate.magnitude, dtype=float)
    if time_values.ndim != 1 or process_rate_values.ndim != 1 or extent_rate_values.ndim != 1:
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} requires one-dimensional time and process-rate trajectories."
        )
    if time_values.shape != process_rate_values.shape or time_values.shape != extent_rate_values.shape:
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} process-rate trajectory does not align with result time."
        )
    if not (
        np.all(np.isfinite(time_values))
        and np.all(np.isfinite(process_rate_values))
        and np.all(np.isfinite(extent_rate_values))
    ):
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} time and process-rate trajectories must be finite."
        )

    extent_rate_canonical = extent_rate.to("mole / second")
    entropy_rate = (
        -delta_gibbs_canonical * extent_rate_canonical / temperature_canonical
    ).to("joule / second / kelvin")
    entropy_values = np.asarray(entropy_rate.magnitude, dtype=float)
    if not np.all(np.isfinite(entropy_values)):
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {metadata.id!r} produced non-finite entropy-production rates."
        )

    rows = [
        {
            "diagnostic_id": metadata.id,
            "process_id": metadata.process_id,
            "index": index,
            "time": float(time_value),
            "time_units": str(time.units),
            "process_rate": float(process_rate_value),
            "process_rate_units": str(process_rate.units),
            "extent_rate": float(extent_rate_value),
            "extent_rate_units": str(extent_rate.units),
            "condition_specific_delta_gibbs": float(delta_gibbs.magnitude),
            "condition_specific_delta_gibbs_units": str(delta_gibbs.units),
            "temperature": float(temperature_canonical.magnitude),
            "temperature_units": str(temperature_canonical.units),
            "entropy_production_rate": float(entropy_value),
            "entropy_production_rate_units": str(entropy_rate.units),
            "status": "evaluated",
            "condition_specific_delta_gibbs_source": metadata.condition_specific_delta_gibbs["source"],
            "temperature_source": metadata.temperature["source"],
            "process_rate_to_extent_rate_source": (
                "" if metadata.process_rate_to_extent_rate is None else metadata.process_rate_to_extent_rate["source"]
            ),
            "provenance_refs": list(metadata.provenance_refs),
            "guardrails": _ENTROPY_PRODUCTION_RATE_GUARDRAIL,
        }
        for index, (
            time_value,
            process_rate_value,
            extent_rate_value,
            entropy_value,
        ) in enumerate(
            zip(
                time_values,
                process_rate_values,
                extent_rate_values,
                entropy_values,
                strict=True,
            )
        )
    ]
    return (
        {
            "diagnostic_id": metadata.id,
            "process_id": metadata.process_id,
            "status": "evaluated",
            "process_rate_interpretation": metadata.process_rate_interpretation,
            "process_rate_units": str(process_rate.units),
            "extent_rate_units": str(extent_rate.units),
            "entropy_production_rate_units": str(entropy_rate.units),
            "condition_specific_delta_gibbs": dict(metadata.condition_specific_delta_gibbs),
            "temperature": dict(metadata.temperature),
            "process_rate_to_extent_rate": (
                None
                if metadata.process_rate_to_extent_rate is None
                else dict(metadata.process_rate_to_extent_rate)
            ),
            "provenance_refs": list(metadata.provenance_refs),
            "guardrails": _ENTROPY_PRODUCTION_RATE_GUARDRAIL,
        },
        rows,
    )


def _sourced_scalar_quantity(
    metadata: Mapping[str, Any],
    *,
    diagnostic_id: str,
    field_name: str,
) -> Quantity:
    try:
        quantity = Q_(metadata["value"], str(metadata["units"]))
        values = np.asarray(quantity.magnitude, dtype=float)
    except (PintError, TypeError, ValueError) as exc:
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {diagnostic_id!r} {field_name} must be a numeric unit-bearing scalar."
        ) from exc
    if values.ndim != 0 or not np.isfinite(values.item()):
        raise ConfiguredEntropyProductionError(
            f"Entropy diagnostic {diagnostic_id!r} {field_name} must be a finite scalar."
        )
    return Q_(float(values.item()), quantity.units)


def _is_temperature_interval(quantity: Quantity) -> bool:
    return re.search(
        r"(?<![A-Za-z0-9_])delta_[A-Za-z0-9_]+",
        str(quantity.units),
    ) is not None


_CONSERVATION_DIAGNOSTIC_ALLOWED_USE = (
    "Diagnostic copy over existing SimulationResult trajectories and explicit "
    "configured mass_balance conserved_weights only; not validation, calibration, "
    "thresholding, or solver-time enforcement."
)

_CONSERVATION_DIAGNOSTIC_COLUMNS = (
    "validator_id",
    "status",
    "reason",
    "closed_system",
    "weighted_states",
    "initial_conserved_total",
    "final_conserved_total",
    "final_drift",
    "max_absolute_drift",
    "relative_max_absolute_drift",
    "units",
    "allowed_use",
)


def _conservation_diagnostics(config: ModelConfig, result: SimulationResult) -> dict[str, Any]:
    rows = [
        _conservation_diagnostic_row(
            validator_id=validator.id,
            closed_system=validator.settings.get("closed_system"),
            conserved_weights=cast(Mapping[str, Any], validator.settings["conserved_weights"]),
            result=result,
        )
        for validator in config.validators
        if validator.validator_type == "mass_balance"
        and isinstance(validator.settings.get("conserved_weights"), Mapping)
    ]
    evaluated_count = sum(1 for row in rows if row["status"] == "evaluated")
    return {
        "kind": "configured_conservation_diagnostics",
        "validator_count": len(rows),
        "evaluated_count": evaluated_count,
        "status_counts": _count_by_key(rows, "status"),
        "allowed_use": _CONSERVATION_DIAGNOSTIC_ALLOWED_USE,
        "unsupported_scope": (
            "No new validation rule, solver equation, calibration target, threshold "
            "change, thermodynamic enforcement, or biological claim is created by "
            "this artifact."
        ),
        "rows": rows,
    }


def _conservation_diagnostic_row(
    *,
    validator_id: str,
    closed_system: Any,
    conserved_weights: Mapping[str, Any],
    result: SimulationResult,
) -> dict[str, Any]:
    weights = {str(name): value for name, value in sorted(conserved_weights.items(), key=lambda item: str(item[0]))}
    base_row: dict[str, Any] = {
        "validator_id": validator_id,
        "status": "unsupported",
        "reason": "",
        "closed_system": closed_system if isinstance(closed_system, bool) else None,
        "weighted_states": weights,
        "initial_conserved_total": None,
        "final_conserved_total": None,
        "final_drift": None,
        "max_absolute_drift": None,
        "relative_max_absolute_drift": None,
        "units": "",
        "allowed_use": _CONSERVATION_DIAGNOSTIC_ALLOWED_USE,
    }
    try:
        total = _weighted_conserved_total(result, weights)
    except KeyError as exc:
        base_row["reason"] = str(exc)
        return base_row
    except (DimensionalityError, TypeError, ValueError) as exc:
        base_row["reason"] = f"Conserved total could not be evaluated with configured weights: {exc}"
        return base_row

    values = np.asarray(total.magnitude, dtype=float)
    if values.size == 0:
        base_row["reason"] = "Conserved total has no numeric trajectory values."
        return base_row
    initial = float(values.flat[0])
    final = float(values.flat[-1])
    drift = values - initial
    max_absolute_drift = float(np.max(np.abs(drift)))
    relative_max_absolute_drift = (
        max_absolute_drift / abs(initial)
        if np.isfinite(initial) and initial != 0.0
        else None
    )
    base_row.update(
        {
            "status": "evaluated",
            "reason": "",
            "initial_conserved_total": initial,
            "final_conserved_total": final,
            "final_drift": final - initial,
            "max_absolute_drift": max_absolute_drift,
            "relative_max_absolute_drift": relative_max_absolute_drift,
            "units": str(total.units),
        }
    )
    return base_row


def _weighted_conserved_total(
    result: SimulationResult,
    conserved_weights: Mapping[str, Any],
) -> Quantity:
    if not conserved_weights:
        raise ValueError("At least one conserved weight is required.")
    total: Quantity | None = None
    for state_name, raw_weight in conserved_weights.items():
        if state_name not in result.states:
            raise KeyError(f"Conserved weight provided for unknown state {state_name!r}.")
        weight = raw_weight if is_quantity(raw_weight) else float(raw_weight)
        term = result.states[state_name] * weight
        total = term if total is None else cast(Quantity, total + term.to(total.units))
    if total is None:
        raise ValueError("At least one conserved weight is required.")
    return total


_SOLVER_DIAGNOSTIC_ALLOWED_USE = (
    "Diagnostic copy over existing configured run metadata, solver settings, "
    "solver metadata, time-grid counts, state counts, and process counts only; "
    "not validation, calibration, numerical thresholding, solver tuning advice, "
    "or solver-time enforcement."
)

_SOLVER_DIAGNOSTIC_GUARDRAIL = (
    "This artifact reports recorded solver/configuration metadata only. It does "
    "not infer scientific values, alter solver behavior, compare against empirical "
    "data, or establish numerical quality thresholds."
)

_SOLVER_METADATA_FIELDS = ("backend", "method", "success", "status", "message", "nfev", "njev", "nlu")

_SOLVER_DIAGNOSTIC_COLUMNS = (
    "config_name",
    "config_path",
    "mode",
    "maturity",
    "kind",
    "result_name",
    "result_label",
    "model_version",
    "state_count",
    "configured_process_count",
    "process_rate_count",
    "time_units",
    "configured_time_start",
    "configured_time_stop",
    "configured_time_evaluation_count",
    "result_time_point_count",
    "solver_backend",
    "solver_method",
    "solver_success",
    "solver_status",
    "solver_message",
    "nfev",
    "njev",
    "nlu",
    "rtol",
    "atol",
    "max_step_value",
    "max_step_units",
    "metadata_available",
    "allowed_use",
    "interpretation_guardrail",
)


def _solver_diagnostics(
    config: ModelConfig,
    inputs: ConfiguredInputs,
    result: SimulationResult,
) -> dict[str, Any]:
    metadata = dict(result.solver_metadata)
    metadata_available = bool(metadata)
    rows = [_solver_diagnostic_row(config, inputs, result, metadata)] if metadata_available else []
    missing_metadata_fields = [field for field in _SOLVER_METADATA_FIELDS if field not in metadata]
    return {
        "kind": "configured_solver_diagnostics",
        "metadata_available": metadata_available,
        "row_count": len(rows),
        "status": "available" if metadata_available else "unavailable",
        "missing_metadata_fields": missing_metadata_fields,
        "allowed_use": _SOLVER_DIAGNOSTIC_ALLOWED_USE,
        "unsupported_scope": (
            "No solver behavior change, numerical threshold, validation rule, "
            "calibration target, empirical comparison, thermodynamic enforcement, "
            "or biological claim is created by this artifact."
        ),
        "rows": rows,
    }


def _solver_diagnostic_row(
    config: ModelConfig,
    inputs: ConfiguredInputs,
    result: SimulationResult,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    settings = result.solver_settings.to_dict()
    max_step = settings.get("max_step")
    if isinstance(max_step, Mapping):
        max_step_value = max_step.get("value")
        max_step_units = max_step.get("units")
    else:
        max_step_value = None
        max_step_units = ""
    time_units = str(inputs.t_span[1].units)
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
        "configured_process_count": len(config.processes),
        "process_rate_count": len(result.process_rates),
        "time_units": time_units,
        "configured_time_start": _quantity_scalar(inputs.t_span[0], time_units),
        "configured_time_stop": _quantity_scalar(inputs.t_span[1], time_units),
        "configured_time_evaluation_count": _quantity_value_count(inputs.t_eval),
        "result_time_point_count": _quantity_value_count(result.time),
        "solver_backend": metadata.get("backend"),
        "solver_method": metadata.get("method", settings.get("method")),
        "solver_success": metadata.get("success"),
        "solver_status": metadata.get("status"),
        "solver_message": metadata.get("message"),
        "nfev": metadata.get("nfev"),
        "njev": metadata.get("njev"),
        "nlu": metadata.get("nlu"),
        "rtol": settings.get("rtol"),
        "atol": settings.get("atol"),
        "max_step_value": max_step_value,
        "max_step_units": max_step_units,
        "metadata_available": True,
        "allowed_use": _SOLVER_DIAGNOSTIC_ALLOWED_USE,
        "interpretation_guardrail": _SOLVER_DIAGNOSTIC_GUARDRAIL,
    }


def _quantity_scalar(quantity: Quantity, units: str) -> float:
    value = quantity.to(units)
    values = np.asarray(value.magnitude, dtype=float)
    return float(values.flat[0])


def _quantity_value_count(quantity: Quantity | None) -> int | None:
    if quantity is None:
        return None
    return int(np.asarray(quantity.magnitude).size)


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
