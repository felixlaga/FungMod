"""Standard CSV table generation for virtual experiments."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from fungal_model.api.metrics import (
    DEGRADATION_THRESHOLDS,
    summarize_numeric_values,
    threshold_crossing_time,
)
from fungal_model.api.output_schema import (
    DATA_DICTIONARY_COLUMNS,
    OUTPUT_SCHEMA_VERSION,
    output_data_dictionary_rows,
    output_schema_document,
    table_fieldnames,
)
from fungal_model.registry.records import ParameterRecord, RegistryRecord
from fungal_model.registry.store import FungModRegistry, RegistryLookupError
from fungal_model.screening import (
    EnsembleSample,
    ModelabilityReport,
    RegistryCaseEnsemble,
    RegistryScreenResult,
)
from fungal_model.screening.case_builder import (
    RegistryCaseBuildError,
    get_registry_process_assembler,
    select_registry_case_compatibility,
)


@dataclass(frozen=True)
class WrittenTables:
    """Paths written by the standard virtual-experiment table writer."""

    paths: Mapping[str, str]

    def to_dict(self) -> dict[str, str]:
        return dict(self.paths)


def write_standard_tables(
    *,
    screen_result: RegistryScreenResult,
    registry: FungModRegistry,
    preflight_reports: Sequence[ModelabilityReport],
    output_dir: str | Path,
) -> WrittenTables:
    """Write API-001 biological output tables."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    reports_by_case = {
        (report.fungus_id, report.substrate_id, report.environment_id): report
        for report in preflight_reports
    }
    table_rows = _build_table_rows(
        screen_result=screen_result,
        registry=registry,
        reports_by_case=reports_by_case,
    )
    paths = {
        "modelability_preflight": destination / "modelability_preflight.csv",
        "modelability_items": destination / "modelability_items.csv",
        "case_summary": destination / "case_summary.csv",
        "time_series_long": destination / "time_series_long.csv",
        "final_states": destination / "final_states.csv",
        "final_metrics": destination / "final_metrics.csv",
        "threshold_times": destination / "threshold_times.csv",
        "sampled_parameters": destination / "sampled_parameters.csv",
        "assumption_summary": destination / "assumption_summary.csv",
        "mechanism_summary": destination / "mechanism_summary.csv",
        "summary_metrics": destination / "summary_metrics.csv",
        "environment_summary": destination / "environment_summary.csv",
        "provenance_table": destination / "provenance_table.csv",
        "limitations_table": destination / "limitations_table.csv",
        "missing_parameters": destination / "missing_parameters.csv",
        "suggested_experiments": destination / "suggested_experiments.csv",
        "output_data_dictionary": destination / "virtual_experiment_output_data_dictionary.csv",
        "output_schema": destination / "virtual_experiment_output_schema.json",
    }
    for table_name, rows in table_rows.items():
        _write_table(paths[table_name], table_name=table_name, rows=rows)
    _write_csv(
        paths["output_data_dictionary"],
        output_data_dictionary_rows(),
        fieldnames=DATA_DICTIONARY_COLUMNS,
    )
    paths["output_schema"].write_text(
        json.dumps(output_schema_document(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return WrittenTables(paths={name: str(path) for name, path in paths.items()})


def write_preflight_tables(
    *,
    registry: FungModRegistry,
    preflight_reports: Sequence[ModelabilityReport],
    output_dir: str | Path,
) -> WrittenTables:
    """Write preflight-only modelability tables without simulating."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    table_rows = _build_preflight_table_rows(
        registry=registry,
        preflight_reports=preflight_reports,
    )
    paths = {
        "modelability_preflight": destination / "modelability_preflight.csv",
        "modelability_items": destination / "modelability_items.csv",
        "output_data_dictionary": destination / "virtual_experiment_output_data_dictionary.csv",
        "output_schema": destination / "virtual_experiment_output_schema.json",
    }
    for table_name, rows in table_rows.items():
        _write_table(paths[table_name], table_name=table_name, rows=rows)
    _write_csv(
        paths["output_data_dictionary"],
        output_data_dictionary_rows(),
        fieldnames=DATA_DICTIONARY_COLUMNS,
    )
    paths["output_schema"].write_text(
        json.dumps(output_schema_document(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return WrittenTables(paths={name: str(path) for name, path in paths.items()})


def _build_table_rows(
    *,
    screen_result: RegistryScreenResult,
    registry: FungModRegistry,
    reports_by_case: Mapping[tuple[str, str, str], ModelabilityReport],
) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {
        "modelability_preflight": [],
        "modelability_items": [],
        "case_summary": [],
        "time_series_long": [],
        "final_states": [],
        "final_metrics": [],
        "threshold_times": [],
        "sampled_parameters": [],
        "assumption_summary": [],
        "mechanism_summary": [],
        "summary_metrics": [],
        "environment_summary": [],
        "provenance_table": [],
        "limitations_table": [],
        "missing_parameters": [],
        "suggested_experiments": [],
    }
    for case_index, case in enumerate(screen_result.case_results):
        report = reports_by_case.get(
            (case.fungus_id, case.substrate_id, case.environment_id),
            case.modelability_report,
        )
        role_records = _role_parameter_records(registry=registry, case=case, mode=screen_result.mode)
        context = _case_context(
            registry=registry,
            case=case,
            case_index=case_index,
            role_records=role_records,
        )
        rows["modelability_preflight"].append(_preflight_row(context, report))
        rows["modelability_items"].extend(_modelability_item_rows(context, report))
        rows["case_summary"].append(_case_summary_row(context, case, report))
        rows["provenance_table"].extend(_provenance_rows(context, registry, case, report, role_records))
        rows["limitations_table"].extend(_limitation_rows(context, registry, case, report, role_records))
        rows["missing_parameters"].extend(_missing_parameter_rows(context, report))
        rows["suggested_experiments"].extend(_suggested_experiment_rows(context, registry, case, report))
        rows["assumption_summary"].extend(_assumption_summary_rows(context, report))
        rows["mechanism_summary"].extend(_mechanism_summary_rows(context, registry, case, report, role_records))
        for sample in case.samples:
            sample_context = _sample_context(context, sample)
            state_roles = _state_roles(sample)
            trajectory_rows = _read_trajectory(sample)
            rate_rows = _read_process_rates(sample)
            rows["time_series_long"].extend(
                _time_series_rows(
                    sample_context=sample_context,
                    trajectory_rows=trajectory_rows,
                    rate_rows=rate_rows,
                    state_roles=state_roles,
                )
            )
            rows["final_states"].extend(_final_state_rows(sample_context, sample=sample, state_roles=state_roles))
            rows["final_metrics"].extend(
                _final_metric_rows(
                    sample_context=sample_context,
                    trajectory_rows=trajectory_rows,
                    rate_rows=rate_rows,
                    state_roles=state_roles,
                )
            )
            rows["threshold_times"].extend(
                _threshold_rows(
                    sample_context=sample_context,
                    trajectory_rows=trajectory_rows,
                    state_roles=state_roles,
                )
            )
            rows["sampled_parameters"].extend(
                _sampled_parameter_rows(
                    sample_context=sample_context,
                    sample=sample,
                    role_records=role_records,
                )
            )
    rows["summary_metrics"] = _summary_metric_rows(rows["final_metrics"], rows["threshold_times"])
    rows["environment_summary"] = _environment_summary_rows(
        case_summary_rows=rows["case_summary"],
        final_metric_rows=rows["final_metrics"],
        threshold_rows=rows["threshold_times"],
        limitation_rows=rows["limitations_table"],
    )
    return rows


def _build_preflight_table_rows(
    *,
    registry: FungModRegistry,
    preflight_reports: Sequence[ModelabilityReport],
) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {
        "modelability_preflight": [],
        "modelability_items": [],
    }
    for case_index, report in enumerate(preflight_reports):
        context = _preflight_context(registry=registry, report=report, case_index=case_index)
        rows["modelability_preflight"].append(_preflight_row(context, report))
        rows["modelability_items"].extend(_modelability_item_rows(context, report))
    return rows


def _case_context(
    *,
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    case_index: int,
    role_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    fungus = registry.get_fungus(case.fungus_id)
    substrate = registry.get_substrate(case.substrate_id)
    environment = registry.get_environment(case.environment_id)
    env_values = _environment_values(environment.conditions, environment.provenance)
    environment_effect_status = _environment_effect_status(
        environment_id=case.environment_id,
        environment_provenance=environment.provenance,
        role_records=role_records,
    )
    environment_policy = _environment_policy(environment_effect_status)
    return {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "case_id": f"case_{case_index:04d}",
        "fungus_id": case.fungus_id,
        "fungus_name": fungus.name,
        "substrate_id": case.substrate_id,
        "substrate_name": substrate.name,
        "environment_id": case.environment_id,
        "environment_name": environment.name,
        "temperature_C": env_values["temperature_C"],
        "ph": env_values["ph"],
        "oxygen": env_values["oxygen"],
        "environment_source": _environment_source(environment.provenance),
        "environment_effect_status": environment_effect_status,
        **environment_policy,
        "process_type": case.process_type,
    }


def _preflight_context(
    *,
    registry: FungModRegistry,
    report: ModelabilityReport,
    case_index: int,
) -> dict[str, Any]:
    fungus = registry.get_fungus(report.fungus_id)
    substrate = registry.get_substrate(report.substrate_id)
    environment = registry.get_environment(report.environment_id)
    env_values = _environment_values(environment.conditions, environment.provenance)
    environment_policy = _environment_policy("preflight_only")
    return {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "case_id": f"case_{case_index:04d}",
        "fungus_id": report.fungus_id,
        "fungus_name": fungus.name,
        "substrate_id": report.substrate_id,
        "substrate_name": substrate.name,
        "environment_id": report.environment_id,
        "environment_name": environment.name,
        "temperature_C": env_values["temperature_C"],
        "ph": env_values["ph"],
        "oxygen": env_values["oxygen"],
        "environment_source": _environment_source(environment.provenance),
        "environment_effect_status": "preflight_only",
        **environment_policy,
        "process_type": ";".join(report.required_processes),
    }


def _environment_values(conditions: Mapping[str, Any], provenance: Mapping[str, Any]) -> dict[str, Any]:
    temperature = conditions.get("temperature")
    ph = conditions.get("ph")
    oxygen = conditions.get("oxygen") or conditions.get("oxygen_concentration")
    return {
        "temperature_C": provenance.get("temperature_C", _temperature_c(temperature)),
        "ph": provenance.get("ph", _condition_value(ph)),
        "oxygen": provenance.get("oxygen", _oxygen_value(oxygen)),
    }


def _temperature_c(value_spec: Any | None) -> Any:
    if value_spec is None or getattr(value_spec, "value", None) is None:
        return ""
    value = float(value_spec.value)
    units = str(getattr(value_spec, "units", "") or "")
    if units.lower() in {"kelvin", "k"}:
        return value - 273.15
    return value


def _condition_value(value_spec: Any | None) -> Any:
    if value_spec is None:
        return ""
    if getattr(value_spec, "value", None) is not None:
        return float(value_spec.value)
    if getattr(value_spec, "lower", None) is not None and getattr(value_spec, "upper", None) is not None:
        return f"{float(value_spec.lower)}..{float(value_spec.upper)}"
    return getattr(value_spec, "kind", "") or ""


def _oxygen_value(value_spec: Any | None) -> Any:
    if value_spec is None:
        return ""
    if getattr(value_spec, "kind", "") == "not_applicable":
        return "not_applicable"
    return _condition_value(value_spec)


def _environment_source(provenance: Mapping[str, Any]) -> str:
    source = provenance.get("environment_source")
    if source is not None:
        return str(source)
    return "registry"


def _environment_effect_status(
    *,
    environment_id: str,
    environment_provenance: Mapping[str, Any],
    role_records: Mapping[str, ParameterRecord],
) -> str:
    status = environment_provenance.get("environment_effect_status")
    if status is not None:
        return str(status)
    if any(record.environment_id == environment_id for record in role_records.values()):
        return "condition_specific_parameters"
    if not environment_id:
        return "not_applicable"
    return "metadata_only"


def _environment_policy(environment_effect_status: str) -> dict[str, Any]:
    if environment_effect_status == "metadata_only":
        return {
            "environment_response_model": "none",
            "environment_comparison_allowed": False,
            "environment_ranking_allowed": False,
            "environment_response_plot_allowed": False,
            "environment_guardrail": (
                "Metadata-only environment cases cannot be ranked or plotted as "
                "environmental response models."
            ),
        }
    if environment_effect_status in {"condition_specific_parameters", "active_response_model"}:
        return {
            "environment_response_model": environment_effect_status,
            "environment_comparison_allowed": True,
            "environment_ranking_allowed": True,
            "environment_response_plot_allowed": True,
            "environment_guardrail": "Environment comparisons are allowed for this status with documented limitations.",
        }
    return {
        "environment_response_model": "none",
        "environment_comparison_allowed": False,
        "environment_ranking_allowed": False,
        "environment_response_plot_allowed": False,
        "environment_guardrail": "No environment response interpretation is available for this case.",
    }


def _sample_context(context: Mapping[str, Any], sample: EnsembleSample) -> dict[str, Any]:
    data = dict(context)
    data["sample_id"] = f"sample_{sample.sample_index:04d}"
    data["sample_index"] = sample.sample_index
    data["validation_passed"] = sample.validation_passed
    return data


def _preflight_row(context: Mapping[str, Any], report: ModelabilityReport) -> dict[str, Any]:
    policy = _preflight_policy(report)
    return {
        **_case_columns(context),
        "assessment_mode": report.mode,
        "status": report.status,
        **policy,
        "known_count": len(report.known),
        "uncertain_count": len(report.uncertain),
        "missing_count": len(report.missing),
        "incompatible_count": len(report.incompatible),
        "required_processes": ";".join(report.required_processes),
        "candidate_processes": ";".join(report.candidate_processes),
        "required_parameters": ";".join(report.required_parameters),
        "suggested_experiments": "; ".join(report.suggested_experiments),
    }


def _preflight_policy(report: ModelabilityReport) -> dict[str, Any]:
    if report.mode == "scientific":
        if report.status == "modelable":
            return {
                "simulation_allowed_for_mode": True,
                "blocking_reason": "not_blocked",
                "recommended_next_action": "simulate_scientific_unvalidated",
            }
        return {
            "simulation_allowed_for_mode": False,
            "blocking_reason": _blocking_reason(report),
            "recommended_next_action": _recommended_next_action(report),
        }
    if report.mode == "exploratory":
        if report.status in {"modelable", "exploratory"}:
            return {
                "simulation_allowed_for_mode": True,
                "blocking_reason": "not_blocked",
                "recommended_next_action": "simulate_exploratory",
            }
        return {
            "simulation_allowed_for_mode": False,
            "blocking_reason": _blocking_reason(report),
            "recommended_next_action": _recommended_next_action(report),
        }
    return {
        "simulation_allowed_for_mode": False,
        "blocking_reason": "toy_preflight_only",
        "recommended_next_action": "use_exploratory_or_scientific_mode_for_simulation",
    }


def _blocking_reason(report: ModelabilityReport) -> str:
    if not report.candidate_processes:
        return "unsupported_mechanism"
    if report.missing:
        return "missing_inputs"
    if report.incompatible:
        return "incompatible_inputs"
    if report.uncertain and report.mode == "scientific":
        return "uncertain_inputs_rejected_by_scientific_mode"
    return "not_blocked"


def _recommended_next_action(report: ModelabilityReport) -> str:
    reason = _blocking_reason(report)
    if reason == "missing_inputs":
        return "measure_or_curate_missing_inputs"
    if reason == "incompatible_inputs":
        return "change_case_or_curate_compatible_mechanism"
    if reason == "unsupported_mechanism":
        return "add_generic_provenance_backed_mechanism"
    if reason == "uncertain_inputs_rejected_by_scientific_mode":
        return "use_exploratory_mode_or_curate_exact_scientific_inputs"
    return "inspect_modelability_items"


def _modelability_item_rows(context: Mapping[str, Any], report: ModelabilityReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = _case_columns(context)
    item_index = 0
    for item_status, items in (
        ("known", report.known),
        ("uncertain", report.uncertain),
        ("missing", report.missing),
        ("incompatible", report.incompatible),
    ):
        for item in items:
            rows.append(
                {
                    **base,
                    "item_index": item_index,
                    "item_status": item_status,
                    "item_type": item.item_type,
                    "item_id": item.item_id,
                    "modelability_status": report.status,
                    "message": item.message,
                    "details": json.dumps(item.details, sort_keys=True),
                    "allowed_use": _modelability_item_allowed_use(item_status),
                }
            )
            item_index += 1
    return rows


def _modelability_item_allowed_use(item_status: str) -> str:
    if item_status == "known":
        return "supports_case_interpretation"
    if item_status == "uncertain":
        return "exploratory_simulation_only"
    if item_status == "missing":
        return "blocks_scientific_simulation"
    if item_status == "incompatible":
        return "blocks_simulation"
    return "not_applicable"


def _case_summary_row(
    context: Mapping[str, Any],
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
) -> dict[str, Any]:
    return {
        **_case_columns(context),
        "modelability_status": report.status,
        "sample_count": len(case.samples),
        "sample_failure_count": len(case.sample_failures),
        "simulated": bool(case.samples),
        "preflight_guardrail": "modelability",
    }


def _assumption_summary_rows(context: Mapping[str, Any], report: ModelabilityReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = _case_columns(context)
    for index, assumption in enumerate(report.assumptions):
        rows.append(
            {
                **base,
                "row_type": "assumption",
                "item_type": "modelability_assumption",
                "item_id": f"assumption_{index:02d}",
                "modelability_status": report.status,
                "message": assumption,
                "details": "",
                "allowed_use": "exploratory_context_not_validation",
            }
        )
    for row_type, items in (
        ("uncertain", report.uncertain),
        ("missing", report.missing),
        ("incompatible", report.incompatible),
    ):
        for item in items:
            rows.append(
                {
                    **base,
                    "row_type": row_type,
                    "item_type": item.item_type,
                    "item_id": item.item_id,
                    "modelability_status": report.status,
                    "message": item.message,
                    "details": json.dumps(item.details, sort_keys=True),
                    "allowed_use": _assumption_allowed_use(row_type),
                }
            )
    for index, suggestion in enumerate(report.suggested_experiments):
        rows.append(
            {
                **base,
                "row_type": "suggested_experiment",
                "item_type": "suggested_experiment",
                "item_id": f"suggested_experiment_{index:02d}",
                "modelability_status": report.status,
                "message": suggestion,
                "details": "",
                "allowed_use": "follow_up_experiment_recommendation",
            }
        )
    return rows


def _assumption_allowed_use(row_type: str) -> str:
    if row_type == "uncertain":
        return "exploratory_simulation_only"
    if row_type == "missing":
        return "blocks_scientific_simulation"
    if row_type == "incompatible":
        return "blocks_simulation"
    return "not_applicable"


def _mechanism_summary_rows(
    context: Mapping[str, Any],
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
    role_records: Mapping[str, ParameterRecord],
) -> list[dict[str, Any]]:
    mechanism = _process_mechanism_descriptor(
        context=context,
        registry=registry,
        case=case,
        report=report,
        role_records=role_records,
    )
    return [{**_case_columns(context), "mechanism_index": 0, **mechanism}]


def _process_mechanism_descriptor(
    *,
    context: Mapping[str, Any],
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
    role_records: Mapping[str, ParameterRecord],
) -> dict[str, Any]:
    process_type = str(context.get("process_type", case.process_type))
    try:
        compatibility = select_registry_case_compatibility(
            registry=registry,
            fungus_id=case.fungus_id,
            substrate_id=case.substrate_id,
            report=report,
        )
    except RegistryCaseBuildError:
        compatibility = None
    configured_by = (
        getattr(compatibility, "case_template_id", "") or getattr(compatibility, "record_id", "")
        if compatibility is not None
        else ""
    )
    return {
        "mechanism_kind": "process_law",
        "mechanism_id": process_type,
        "mechanism_family": _mechanism_family(process_type),
        "active": bool(case.samples),
        "maturity": _mechanism_maturity(process_type, role_records),
        "configured_by": configured_by or "registry_compatibility",
        "equation_or_law": _mechanism_law(process_type),
        "state_variables": ";".join(_mechanism_state_variables(process_type)),
        "parameters": ";".join(_mechanism_parameters(report, role_records)),
        "assumptions": "; ".join(report.assumptions),
        "limitations": "; ".join(_mechanism_limitations(process_type)),
        "provenance": json.dumps(
            {
                "process_type": process_type,
                "role_record_ids": {
                    role: record.record_id for role, record in sorted(role_records.items())
                },
                "case_template_id": configured_by,
            },
            sort_keys=True,
        ),
    }


def _mechanism_family(process_type: str) -> str:
    if process_type == "homogeneous_michaelis_menten":
        return "generic homogeneous Michaelis-Menten process"
    if process_type == "surface_catalysis":
        return "generic equilibrium surface catalysis"
    if process_type == "extracellular_enzyme_chain":
        return "generic two-step extracellular enzyme chain"
    return "generic configured process law"


def _mechanism_law(process_type: str) -> str:
    if process_type == "homogeneous_michaelis_menten":
        return "r = Vmax * S / (Km + S), or explicit-enzyme equivalent when configured"
    if process_type == "surface_catalysis":
        return "r = k_surface * theta(E, K_ads) * accessible_surface_area"
    if process_type == "extracellular_enzyme_chain":
        return "configured surface step followed by configured homogeneous product-conversion step"
    return "configured process law"


def _mechanism_state_variables(process_type: str) -> tuple[str, ...]:
    if process_type == "homogeneous_michaelis_menten":
        return ("substrate", "product", "enzyme_or_vmax")
    if process_type == "surface_catalysis":
        return ("solid_substrate", "free_catalyst", "product")
    if process_type == "extracellular_enzyme_chain":
        return ("substrate", "intermediate", "product", "surface_catalyst", "homogeneous_catalyst")
    return ()


def _mechanism_parameters(
    report: ModelabilityReport,
    role_records: Mapping[str, ParameterRecord],
) -> tuple[str, ...]:
    role_symbols = tuple(
        f"{role}:{record.parameter_symbol}"
        for role, record in sorted(role_records.items())
    )
    if role_symbols:
        return role_symbols
    return tuple(report.required_parameters)


def _mechanism_maturity(process_type: str, role_records: Mapping[str, ParameterRecord]) -> str:
    if not role_records:
        return "software_tested_no_parameter_records"
    maturities = {record.maturity for record in role_records.values()}
    if maturities == {"literature_processed"}:
        return "software_tested_literature_parameterized"
    if "exploratory_prior" in maturities:
        return "software_tested_exploratory_parameterized"
    return "software_tested_mixed_parameter_maturity"


def _mechanism_limitations(process_type: str) -> tuple[str, ...]:
    if process_type == "homogeneous_michaelis_menten":
        return (
            "Well-mixed homogeneous process only.",
            "Not a whole-fungus physiology, secretion, uptake, or biomass model.",
            "No empirical validation claim is implied by simulation output.",
        )
    if process_type == "surface_catalysis":
        return (
            "Accessible surface area is explicit or sampled, not dynamically evolved.",
            "No surface renewal, pore accessibility, crystallinity, or morphology dynamics.",
            "No empirical validation claim is implied by simulation output.",
        )
    if process_type == "extracellular_enzyme_chain":
        return (
            "Exactly the configured chain steps are represented.",
            "No whole-fungus growth, secretion, uptake, or biomass model.",
            "No empirical validation claim is implied by simulation output.",
        )
    return ("No empirical validation claim is implied by simulation output.",)


def _case_columns(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "output_schema_version": context["output_schema_version"],
        "case_id": context["case_id"],
        "fungus_id": context["fungus_id"],
        "fungus_name": context["fungus_name"],
        "substrate_id": context["substrate_id"],
        "substrate_name": context["substrate_name"],
        "environment_id": context["environment_id"],
        "environment_name": context["environment_name"],
        "temperature_C": context["temperature_C"],
        "ph": context["ph"],
        "oxygen": context["oxygen"],
        "environment_source": context["environment_source"],
        "environment_effect_status": context["environment_effect_status"],
        "environment_response_model": context["environment_response_model"],
        "environment_comparison_allowed": context["environment_comparison_allowed"],
        "environment_ranking_allowed": context["environment_ranking_allowed"],
        "environment_response_plot_allowed": context["environment_response_plot_allowed"],
        "environment_guardrail": context["environment_guardrail"],
        "process_type": context["process_type"],
    }


def _base_sample_columns(context: Mapping[str, Any]) -> dict[str, Any]:
    data = _case_columns(context)
    data.update(
        {
            "sample_id": context["sample_id"],
            "sample_index": context["sample_index"],
        }
    )
    return data


def _state_roles(sample: EnsembleSample) -> dict[str, str]:
    config_path = Path(sample.config_path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    template_roles = _template_state_roles(data)
    if template_roles:
        return template_roles
    process_configs = data.get("processes", []) if isinstance(data, Mapping) else []
    if not process_configs:
        return {}
    states = process_configs[0].get("states", {})
    if not isinstance(states, Mapping):
        return {}
    roles: dict[str, str] = {}
    for role, state_name in states.items():
        if isinstance(state_name, str):
            roles[str(role)] = state_name
    if "catalyst" in roles and "enzyme" not in roles:
        roles["enzyme"] = roles["catalyst"]
    return roles


def _template_state_roles(data: Any) -> dict[str, str]:
    if not isinstance(data, Mapping):
        return {}
    case_template = data.get("case_template")
    if not isinstance(case_template, Mapping):
        return {}
    roles_data = case_template.get("output_state_roles") or case_template.get("state_roles")
    if not isinstance(roles_data, Mapping):
        return {}
    roles = {
        str(role): str(state_name)
        for role, state_name in roles_data.items()
        if isinstance(state_name, str) and state_name
    }
    if "catalyst" in roles and "enzyme" not in roles:
        roles["enzyme"] = roles["catalyst"]
    return roles


def _read_trajectory(sample: EnsembleSample) -> list[dict[str, str]]:
    if sample.trajectory_path is None:
        return []
    return _read_csv(Path(sample.trajectory_path))


def _read_process_rates(sample: EnsembleSample) -> list[dict[str, str]]:
    path = Path(sample.output_directory) / "process_rates.csv"
    if not path.exists():
        return []
    return _read_csv(path)


def _time_series_rows(
    *,
    sample_context: Mapping[str, Any],
    trajectory_rows: Sequence[Mapping[str, str]],
    rate_rows: Sequence[Mapping[str, str]],
    state_roles: Mapping[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if not trajectory_rows:
        return output
    state_names = _trajectory_state_names(trajectory_rows[0])
    substrate_state = state_roles.get("substrate")
    product_state = state_roles.get("product")
    initial_substrate = _initial_state_value(trajectory_rows, substrate_state)
    initial_product = _initial_state_value(trajectory_rows, product_state)
    rate_by_index = _rate_by_index(rate_rows)
    for index, row in enumerate(trajectory_rows):
        base = {
            **_base_sample_columns(sample_context),
            "time_index": index,
            "time": _float_or_blank(row.get("time")),
            "time_units": row.get("time_units", ""),
        }
        for state_name in state_names:
            output.append(
                {
                    **base,
                    "state": state_name,
                    "state_role": _role_for_state(state_name, state_roles),
                    "value": _float_or_blank(row.get(state_name)),
                    "units": row.get(f"{state_name}_units", ""),
                    "source": "simulation_state",
                }
            )
        if substrate_state is not None and initial_substrate is not None and initial_substrate != 0.0:
            substrate_value = _optional_float(row.get(substrate_state))
            if substrate_value is not None:
                degraded_fraction = (initial_substrate - substrate_value) / initial_substrate
                output.append(
                    {
                        **base,
                        "state": "substrate_degraded_fraction",
                        "state_role": "derived_substrate_loss",
                        "value": degraded_fraction,
                        "units": "dimensionless",
                        "source": "derived_from_states",
                    }
                )
                if _is_surface_case(sample_context):
                    output.append(
                        {
                            **base,
                            "state": "solid_substrate_degraded_fraction",
                            "state_role": "derived_solid_substrate_loss",
                            "value": degraded_fraction,
                            "units": "dimensionless",
                            "source": "derived_from_solid_substrate_state",
                        }
                    )
                    output.append(
                        {
                            **base,
                            "state": "accessible_site_fraction_remaining_proxy",
                            "state_role": "derived_accessible_site_proxy",
                            "value": substrate_value / initial_substrate,
                            "units": "dimensionless",
                            "source": "derived_proxy_from_solid_substrate_state",
                        }
                    )
        if product_state is not None and initial_product is not None:
            product_value = _optional_float(row.get(product_state))
            if product_value is not None:
                output.append(
                    {
                        **base,
                        "state": "product_formed",
                        "state_role": "derived_product_release",
                        "value": product_value - initial_product,
                        "units": row.get(f"{product_state}_units", ""),
                        "source": "derived_from_states",
                    }
                )
        if index in rate_by_index:
            rate = rate_by_index[index]
            for state_name in ("degradation_rate", "product_release_rate"):
                output.append(
                    {
                        **base,
                        "state": state_name,
                        "state_role": "derived_rate",
                        "value": rate["value"],
                        "units": rate["units"],
                        "source": "simulation_process_rate",
                    }
                )
    return output


def _final_metric_rows(
    *,
    sample_context: Mapping[str, Any],
    trajectory_rows: Sequence[Mapping[str, str]],
    rate_rows: Sequence[Mapping[str, str]],
    state_roles: Mapping[str, str],
) -> list[dict[str, Any]]:
    base = _base_sample_columns(sample_context)
    if not trajectory_rows:
        return [_metric_row(base, "trajectory_available", "", "not_applicable", "not_applicable", "No trajectory was written.")]
    final_row = trajectory_rows[-1]
    substrate_state = state_roles.get("substrate")
    product_state = state_roles.get("product")
    initial_substrate = _initial_state_value(trajectory_rows, substrate_state)
    final_substrate = _optional_float(final_row.get(substrate_state or ""))
    initial_product = _initial_state_value(trajectory_rows, product_state)
    final_product = _optional_float(final_row.get(product_state or ""))
    max_rate = _maximum_process_rate(rate_rows)
    rows: list[dict[str, Any]] = []
    if substrate_state is None or final_substrate is None:
        rows.append(_metric_row(base, "final_substrate_remaining", "", "not_applicable", "not_applicable", "No substrate state mapping was available."))
        rows.append(_metric_row(base, "final_substrate_degraded_fraction", "", "dimensionless", "not_applicable", "No substrate state mapping was available."))
    else:
        rows.append(
            _metric_row(
                base,
                "final_substrate_remaining",
                final_substrate,
                final_row.get(f"{substrate_state}_units", ""),
                "computed",
                "",
            )
        )
        if initial_substrate is None or initial_substrate == 0.0:
            rows.append(_metric_row(base, "final_substrate_degraded_fraction", "", "dimensionless", "not_applicable", "Initial substrate was unavailable or zero."))
        else:
            rows.append(
                _metric_row(
                    base,
                    "final_substrate_degraded_fraction",
                    (initial_substrate - final_substrate) / initial_substrate,
                    "dimensionless",
                    "computed",
                    "",
                )
            )
            if _is_surface_case(sample_context):
                final_fraction_remaining = final_substrate / initial_substrate
                rows.append(
                    _metric_row(
                        base,
                        "solid_substrate_remaining",
                        final_substrate,
                        final_row.get(f"{substrate_state}_units", ""),
                        "computed",
                        "",
                    )
                )
                rows.append(
                    _metric_row(
                        base,
                        "solid_substrate_degraded_fraction",
                        1.0 - final_fraction_remaining,
                        "dimensionless",
                        "computed",
                        "",
                    )
                )
                rows.append(
                    _metric_row(
                        base,
                        "accessible_site_fraction_remaining_proxy",
                        final_fraction_remaining,
                        "dimensionless",
                        "derived_proxy",
                        "Derived as proportional to remaining solid substrate; accessible surface is not dynamically renewed.",
                    )
                )
    if product_state is None or final_product is None:
        rows.append(_metric_row(base, "final_product_concentration", "", "not_applicable", "not_applicable", "No product state mapping was available."))
        rows.append(_metric_row(base, "final_product_formed", "", "not_applicable", "not_applicable", "No product state mapping was available."))
    else:
        product_units = final_row.get(f"{product_state}_units", "")
        product_metric = _final_product_metric_name(product_units)
        rows.append(_metric_row(base, product_metric, final_product, product_units, "computed", ""))
        if _is_surface_case(sample_context):
            rows.append(_metric_row(base, "soluble_product_amount", final_product, product_units, "computed", ""))
        if initial_product is None:
            rows.append(_metric_row(base, "final_product_formed", "", product_units, "not_applicable", "Initial product was unavailable."))
        else:
            rows.append(_metric_row(base, "final_product_formed", final_product - initial_product, product_units, "computed", ""))
            if initial_substrate is None or initial_substrate == 0.0:
                rows.append(_metric_row(base, "final_product_yield", "", "dimensionless", "not_applicable", "Initial substrate was unavailable or zero."))
            else:
                rows.append(_metric_row(base, "final_product_yield", (final_product - initial_product) / initial_substrate, "dimensionless", "computed", ""))
    for metric_name in ("maximum_product_release_rate", "maximum_substrate_depletion_rate"):
        if max_rate is None:
            rows.append(_metric_row(base, metric_name, "", "not_applicable", "not_applicable", "No process-rate trajectory was available."))
        else:
            rows.append(_metric_row(base, metric_name, max_rate["value"], max_rate["units"], "computed", ""))
    return rows


def _final_state_rows(
    sample_context: Mapping[str, Any],
    *,
    sample: EnsembleSample,
    state_roles: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for state_name, final_state in sample.final_states.items():
        rows.append(
            {
                **_base_sample_columns(sample_context),
                "state": state_name,
                "state_role": _role_for_state(state_name, state_roles),
                "value": final_state.get("value", ""),
                "units": final_state.get("units", ""),
                "source": "simulation_final_state",
            }
        )
    return rows


def _threshold_rows(
    *,
    sample_context: Mapping[str, Any],
    trajectory_rows: Sequence[Mapping[str, str]],
    state_roles: Mapping[str, str],
) -> list[dict[str, Any]]:
    base = _base_sample_columns(sample_context)
    substrate_state = state_roles.get("substrate")
    if not trajectory_rows or substrate_state is None:
        return [
            _threshold_row(base, threshold, "", "not_applicable", "not_applicable", "No substrate trajectory was available.")
            for threshold in DEGRADATION_THRESHOLDS
        ]
    initial_substrate = _initial_state_value(trajectory_rows, substrate_state)
    if initial_substrate is None or initial_substrate == 0.0:
        return [
            _threshold_row(base, threshold, "", "not_applicable", "not_applicable", "Initial substrate was unavailable or zero.")
            for threshold in DEGRADATION_THRESHOLDS
        ]
    time_values = [_optional_float(row.get("time")) for row in trajectory_rows]
    substrate_values = [_optional_float(row.get(substrate_state)) for row in trajectory_rows]
    if any(value is None for value in time_values) or any(value is None for value in substrate_values):
        return [
            _threshold_row(base, threshold, "", "not_applicable", "not_applicable", "Trajectory contains missing numeric values.")
            for threshold in DEGRADATION_THRESHOLDS
        ]
    numeric_time_values = [float(value) for value in time_values if value is not None]
    numeric_substrate_values = [float(value) for value in substrate_values if value is not None]
    degraded = [
        (initial_substrate - value) / initial_substrate
        for value in numeric_substrate_values
    ]
    units = trajectory_rows[0].get("time_units", "")
    rows: list[dict[str, Any]] = []
    for threshold in DEGRADATION_THRESHOLDS:
        crossing = threshold_crossing_time(
            time_values=numeric_time_values,
            degraded_fraction=degraded,
            threshold=threshold,
        )
        if crossing is None:
            rows.append(_threshold_row(base, threshold, "", units, "not_reached", "Threshold was not reached within the simulated time span."))
        else:
            rows.append(_threshold_row(base, threshold, crossing, units, "computed", ""))
    return rows


def _metric_row(
    base: Mapping[str, Any],
    metric: str,
    value: Any,
    units: str,
    status: str,
    notes: str,
) -> dict[str, Any]:
    return {
        **base,
        "metric": metric,
        "value": value,
        "units": units,
        "status": status,
        "notes": notes,
    }


def _threshold_row(
    base: Mapping[str, Any],
    threshold: float,
    value: Any,
    units: str,
    status: str,
    notes: str,
) -> dict[str, Any]:
    return {
        **base,
        "threshold_fraction": threshold,
        "metric": f"time_to_{int(round(threshold * 100))}_percent_substrate_degradation",
        "value": value,
        "units": units,
        "status": status,
        "notes": notes,
    }


def _sampled_parameter_rows(
    *,
    sample_context: Mapping[str, Any],
    sample: EnsembleSample,
    role_records: Mapping[str, ParameterRecord],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role, parameter in sample.parameters.items():
        source_record = role_records.get(role)
        value_kind = "" if source_record is None else source_record.value.kind
        rows.append(
            {
                **_base_sample_columns(sample_context),
                "role": role,
                "symbol": parameter.get("symbol", ""),
                "sampled_value": parameter.get("value", ""),
                "units": parameter.get("units", ""),
                "sampled_value_kind": "exact",
                "source_record_id": "" if source_record is None else source_record.record_id,
                "source_value_kind": value_kind,
                "source_maturity": "" if source_record is None else source_record.maturity,
                "parameter_source_class": _parameter_source_class(source_record),
                "source": "" if source_record is None else _value_source(source_record),
                "confidence_level": "" if source_record is None else (source_record.value.confidence_level or ""),
                "exploratory_prior": "" if source_record is None else _is_exploratory_record(source_record),
                "range_scope": "" if source_record is None else source_record.range_scope,
                "range_interpretation": "" if source_record is None else source_record.range_interpretation,
                "allowed_use": "" if source_record is None else source_record.allowed_use,
                "notes": "" if source_record is None else source_record.notes,
            }
        )
    return rows


def _summary_metric_rows(
    final_metric_rows: Sequence[Mapping[str, Any]],
    threshold_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[float]] = {}
    contexts: dict[str, Mapping[str, Any]] = {}
    for row in tuple(final_metric_rows) + tuple(threshold_rows):
        case_id = str(row.get("case_id", ""))
        if case_id:
            contexts.setdefault(case_id, row)
        if row.get("status") != "computed":
            continue
        value = _optional_float(row.get("value"))
        if value is None:
            continue
        key = (case_id, str(row.get("metric", "")), str(row.get("units", "")))
        grouped.setdefault(key, []).append(value)
    rows: list[dict[str, Any]] = []
    for (case_id, metric, units), values in sorted(grouped.items()):
        context = contexts.get(case_id, {})
        base = (
            _case_columns(context)
            if context
            else {"output_schema_version": OUTPUT_SCHEMA_VERSION, "case_id": case_id}
        )
        rows.append(
            {
                **base,
                "metric": metric,
                "units": units,
                **summarize_numeric_values(values),
            }
        )
    return rows


def _environment_summary_rows(
    *,
    case_summary_rows: Sequence[Mapping[str, Any]],
    final_metric_rows: Sequence[Mapping[str, Any]],
    threshold_rows: Sequence[Mapping[str, Any]],
    limitation_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    contexts: dict[str, Mapping[str, Any]] = {}
    n_cases: dict[str, int] = {}
    n_samples: dict[str, int] = {}
    n_successful: dict[str, int] = {}
    n_failed: dict[str, int] = {}
    final_degradation: dict[str, list[float]] = {}
    time_to_50: dict[str, list[float]] = {}
    limitations: dict[str, list[str]] = {}
    for row in case_summary_rows:
        environment_id = str(row.get("environment_id", ""))
        contexts.setdefault(environment_id, row)
        sample_count = int(float(row.get("sample_count", 0) or 0))
        failure_count = int(float(row.get("sample_failure_count", 0) or 0))
        n_cases[environment_id] = n_cases.get(environment_id, 0) + 1
        n_successful[environment_id] = n_successful.get(environment_id, 0) + sample_count
        n_failed[environment_id] = n_failed.get(environment_id, 0) + failure_count
        n_samples[environment_id] = n_samples.get(environment_id, 0) + sample_count + failure_count
    for row in final_metric_rows:
        if row.get("metric") != "final_substrate_degraded_fraction" or row.get("status") != "computed":
            continue
        value = _optional_float(row.get("value"))
        if value is not None:
            final_degradation.setdefault(str(row.get("environment_id", "")), []).append(value)
    for row in threshold_rows:
        if row.get("metric") != "time_to_50_percent_substrate_degradation" or row.get("status") != "computed":
            continue
        value = _optional_float(row.get("value"))
        if value is not None:
            time_to_50.setdefault(str(row.get("environment_id", "")), []).append(value)
    for row in limitation_rows:
        environment_id = str(row.get("environment_id", ""))
        limitation = str(row.get("limitation", "") or "")
        if limitation:
            limitations.setdefault(environment_id, [])
            if limitation not in limitations[environment_id]:
                limitations[environment_id].append(limitation)
    output: list[dict[str, Any]] = []
    for environment_id, context in sorted(contexts.items()):
        degradation_summary = summarize_numeric_values(final_degradation.get(environment_id, ()))
        threshold_summary = summarize_numeric_values(time_to_50.get(environment_id, ()))
        comparison_allowed = bool(context.get("environment_comparison_allowed"))
        if comparison_allowed:
            metric_status = "computed"
            degradation_values = {
                "median_final_substrate_degraded_fraction": degradation_summary["p50"],
                "p05_final_substrate_degraded_fraction": degradation_summary["p05"],
                "p95_final_substrate_degraded_fraction": degradation_summary["p95"],
                "median_time_to_50_percent_degradation": threshold_summary["p50"],
                "p05_time_to_50_percent_degradation": threshold_summary["p05"],
                "p95_time_to_50_percent_degradation": threshold_summary["p95"],
            }
        else:
            metric_status = "not_applicable_metadata_only"
            degradation_values = {
                "median_final_substrate_degraded_fraction": "",
                "p05_final_substrate_degraded_fraction": "",
                "p95_final_substrate_degraded_fraction": "",
                "median_time_to_50_percent_degradation": "",
                "p05_time_to_50_percent_degradation": "",
                "p95_time_to_50_percent_degradation": "",
            }
        output.append(
            {
                "output_schema_version": OUTPUT_SCHEMA_VERSION,
                "environment_id": environment_id,
                "temperature_C": context.get("temperature_C", ""),
                "ph": context.get("ph", ""),
                "oxygen": context.get("oxygen", ""),
                "environment_source": context.get("environment_source", ""),
                "environment_effect_status": context.get("environment_effect_status", ""),
                "environment_response_model": context.get("environment_response_model", ""),
                "environment_comparison_allowed": context.get("environment_comparison_allowed", ""),
                "environment_ranking_allowed": context.get("environment_ranking_allowed", ""),
                "environment_response_plot_allowed": context.get("environment_response_plot_allowed", ""),
                "environment_response_metric_status": metric_status,
                "environment_guardrail": context.get("environment_guardrail", ""),
                "n_cases": n_cases.get(environment_id, 0),
                "n_samples": n_samples.get(environment_id, 0),
                "n_successful_samples": n_successful.get(environment_id, 0),
                "n_failed_samples": n_failed.get(environment_id, 0),
                **degradation_values,
                "limitations": "; ".join(limitations.get(environment_id, ())) or "not_applicable",
            }
        )
    return output


def _provenance_rows(
    context: Mapping[str, Any],
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
    role_records: Mapping[str, ParameterRecord],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record_type, record in (
        ("fungus", registry.get_fungus(case.fungus_id)),
        ("substrate", registry.get_substrate(case.substrate_id)),
        ("environment", registry.get_environment(case.environment_id)),
    ):
        rows.append(_record_provenance_row(context, record_type, record, role="", symbol="", value_kind=""))
    try:
        compatibility = select_registry_case_compatibility(
            registry=registry,
            fungus_id=case.fungus_id,
            substrate_id=case.substrate_id,
            report=report,
        )
    except RegistryCaseBuildError:
        compatibility = None
    if compatibility is not None:
        rows.append(_record_provenance_row(context, "process_compatibility", compatibility, role="", symbol="", value_kind=""))
        if compatibility.case_template_id:
            try:
                template = registry.get_case_template(compatibility.case_template_id)
            except RegistryLookupError:
                template = None
            if template is not None:
                rows.append(_record_provenance_row(context, "case_template", template, role="", symbol="", value_kind=""))
    for role, record in role_records.items():
        rows.append(_record_provenance_row(context, "parameter", record, role=role, symbol=record.parameter_symbol, value_kind=record.value.kind))
    for item in tuple(report.missing) + tuple(report.incompatible):
        rows.append(
            {
                **_case_columns(context),
                "record_type": item.item_type,
                "record_id": item.details.get("record_id", item.item_id),
                "role": "",
                "symbol": item.item_id if item.item_type == "parameter" else "",
                "maturity": "",
                "value_kind": "missing" if item in report.missing else "incompatible",
                "source": "",
                "confidence_level": "",
                "exploratory_prior": "",
                "range_scope": "",
                "range_interpretation": "",
                "allowed_use": "",
                "notes": item.message,
                "provenance": json.dumps(item.details, sort_keys=True),
            }
        )
    return rows


def _record_provenance_row(
    context: Mapping[str, Any],
    record_type: str,
    record: RegistryRecord | ParameterRecord,
    *,
    role: str,
    symbol: str,
    value_kind: str,
) -> dict[str, Any]:
    value = record.value if isinstance(record, ParameterRecord) else None
    return {
        **_case_columns(context),
        "record_type": record_type,
        "record_id": record.record_id,
        "role": role,
        "symbol": symbol,
        "maturity": record.maturity,
        "value_kind": value_kind,
        "source": _value_source(record) if isinstance(record, ParameterRecord) else _provenance_source(record.provenance),
        "confidence_level": "" if value is None else (value.confidence_level or ""),
        "exploratory_prior": _is_exploratory_record(record) if isinstance(record, ParameterRecord) else "",
        "range_scope": record.range_scope if isinstance(record, ParameterRecord) else "",
        "range_interpretation": record.range_interpretation if isinstance(record, ParameterRecord) else "",
        "allowed_use": record.allowed_use if isinstance(record, ParameterRecord) else "",
        "notes": record.notes,
        "provenance": json.dumps(dict(record.provenance), sort_keys=True),
    }


def _limitation_rows(
    context: Mapping[str, Any],
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
    role_records: Mapping[str, ParameterRecord],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if context.get("environment_effect_status") == "metadata_only":
        rows.append(
            _limitation_row(
                context,
                "environment_effect",
                "important",
                (
                    "Environment is metadata/context only. The simulation used "
                    "the same kinetic parameter values across environments; no "
                    "temperature or pH response law was applied. Do not rank "
                    "or plot these cases as environmental response models."
                ),
                "EnvironmentGrid",
            )
        )
    for assumption in report.assumptions:
        rows.append(_limitation_row(context, "preflight", "info", assumption, "modelability"))
    for item in report.missing:
        rows.append(_limitation_row(context, "missing_input", "blocking", item.message, item.item_id))
    for item in report.incompatible:
        rows.append(_limitation_row(context, "incompatible_input", "blocking", item.message, item.item_id))
    rows.extend(_case_template_limitation_rows(context, registry=registry, case=case, report=report))
    if any(_is_exploratory_record(record) for record in role_records.values()):
        rows.append(
            _limitation_row(
                context,
                "exploratory_prior",
                "important",
                "Exploratory priors are simulation assumptions and must not be cited as literature-curated values.",
                "parameter_records",
            )
        )
    if case.process_type == "homogeneous_michaelis_menten":
        rows.append(
            _limitation_row(
                context,
                "not_modelled",
                "important",
                "This is an enzyme-source homogeneous kinetics simulation, not a whole-fungus growth, secretion, uptake, biomass, or respiration model.",
                case.process_type,
            )
        )
        rows.append(
            _limitation_row(
                context,
                "not_modelled",
                "important",
                "The process is well-mixed and does not represent spatial gradients, solid-substrate accessibility, adsorption, or surface morphology.",
                case.process_type,
            )
        )
    if case.process_type == "surface_catalysis":
        rows.append(
            _limitation_row(
                context,
                "not_modelled",
                "important",
                "This is enzyme-mediated surface degradation of an insoluble substrate, not a whole-fungus growth, secretion, uptake, biomass, or oxygen-limitation model.",
                case.process_type,
            )
        )
        rows.append(
            _limitation_row(
                context,
                "surface_accessibility",
                "important",
                "Accessible surface area is sampled as a constant parameter in each run; accessible-site fraction outputs are derived proxies from remaining substrate, and surface renewal, pore accessibility, crystallinity, and morphology changes are not modeled.",
                case.process_type,
            )
        )
    return rows


def _case_template_limitation_rows(
    context: Mapping[str, Any],
    *,
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
) -> list[dict[str, Any]]:
    try:
        compatibility = select_registry_case_compatibility(
            registry=registry,
            fungus_id=case.fungus_id,
            substrate_id=case.substrate_id,
            report=report,
        )
        template = registry.get_case_template(compatibility.case_template_id)
    except (RegistryLookupError, RegistryCaseBuildError):
        return []
    rows: list[dict[str, Any]] = []
    for limitation in template.limitations:
        rows.append(_limitation_row(context, "case_template", "info", limitation, template.case_template_id))
    for note in template.validity_notes:
        rows.append(_limitation_row(context, "case_template_validity", "info", note, template.case_template_id))
    return rows


def _limitation_row(
    context: Mapping[str, Any],
    category: str,
    severity: str,
    limitation: str,
    source: str,
) -> dict[str, Any]:
    return {
        **_case_columns(context),
        "category": category,
        "severity": severity,
        "limitation": limitation,
        "source": source,
    }


def _missing_parameter_rows(
    context: Mapping[str, Any],
    report: ModelabilityReport,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.missing:
        details = dict(item.details)
        value = details.get("value")
        value_data = value if isinstance(value, Mapping) else {}
        record_id = str(details.get("record_id", "") or "")
        missing_status = "explicit_unknown" if value_data.get("kind") == "unknown" else "absent"
        rows.append(
            {
                **_case_columns(context),
                "missing_item_type": item.item_type,
                "parameter_symbol": item.item_id if item.item_type == "parameter" else "",
                "source_record_id": record_id,
                "expected_units": value_data.get("units", ""),
                "missing_status": missing_status,
                "message": item.message,
                "suggested_experiment": _suggestion_for_missing_item(item),
                "details": json.dumps(details, sort_keys=True),
            }
        )
    for item in report.incompatible:
        rows.append(
            {
                **_case_columns(context),
                "missing_item_type": item.item_type,
                "parameter_symbol": item.item_id if item.item_type == "parameter" else "",
                "source_record_id": str(item.details.get("record_id", "") or ""),
                "expected_units": "",
                "missing_status": "incompatible",
                "message": item.message,
                "suggested_experiment": _suggestion_for_missing_item(item),
                "details": json.dumps(item.details, sort_keys=True),
            }
        )
    return rows


def _suggested_experiment_rows(
    context: Mapping[str, Any],
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    suggestions = tuple(report.suggested_experiments)
    if not suggestions:
        suggestions = tuple(
            _suggestion_for_missing_item(item)
            for item in tuple(report.missing) + tuple(report.incompatible)
            if _suggestion_for_missing_item(item)
        )
    for index, suggestion in enumerate(dict.fromkeys(suggestions)):
        parameter_symbol = _parameter_symbol_for_suggestion(suggestion, report)
        rows.append(
            {
                **_case_columns(context),
                "suggestion_id": f"{context['case_id']}_suggestion_{index:03d}",
                "parameter_symbol": parameter_symbol,
                "suggested_experiment": suggestion,
                "priority": "high" if parameter_symbol else "medium",
                "rationale": "Required input is missing, explicitly unknown, or incompatible for this registry case.",
                "allowed_use_after_resolution": "scientific_or_exploratory_when_recorded_with_provenance_and_units",
            }
        )
    rows.extend(_case_template_suggested_experiment_rows(context, registry=registry, case=case, report=report))
    return rows


def _case_template_suggested_experiment_rows(
    context: Mapping[str, Any],
    *,
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    report: ModelabilityReport,
) -> list[dict[str, Any]]:
    try:
        compatibility = select_registry_case_compatibility(
            registry=registry,
            fungus_id=case.fungus_id,
            substrate_id=case.substrate_id,
            report=report,
        )
        template = registry.get_case_template(compatibility.case_template_id)
    except (RegistryLookupError, RegistryCaseBuildError):
        return []
    suggestions = template.process_state_metadata.get("suggested_experiments", ())
    if not isinstance(suggestions, Sequence) or isinstance(suggestions, str):
        return []
    rows: list[dict[str, Any]] = []
    for index, suggestion in enumerate(suggestions):
        if not isinstance(suggestion, Mapping):
            continue
        description = str(suggestion.get("description", "")).strip()
        if not description:
            continue
        rows.append(
            {
                **_case_columns(context),
                "suggestion_id": str(suggestion.get("id") or f"{context['case_id']}_template_suggestion_{index:03d}"),
                "parameter_symbol": "",
                "suggested_experiment": description,
                "priority": str(suggestion.get("priority", "medium")),
                "rationale": str(suggestion.get("rationale", "Suggested by the registry case template.")),
                "allowed_use_after_resolution": "update_registry_records_and_re-run_as_exploratory_or_scientific_only_when_provenance_supports_it",
            }
        )
    return rows


def _suggestion_for_missing_item(item: Any) -> str:
    if getattr(item, "item_type", "") == "parameter":
        return f"Measure or curate {item.item_id} for the selected registry case."
    return f"Resolve missing or incompatible {item.item_type}: {item.item_id}."


def _parameter_symbol_for_suggestion(suggestion: str, report: ModelabilityReport) -> str:
    for item in tuple(report.missing) + tuple(report.incompatible):
        if item.item_type == "parameter" and item.item_id in suggestion:
            return item.item_id
    return ""


def _role_parameter_records(
    *,
    registry: FungModRegistry,
    case: RegistryCaseEnsemble,
    mode: str,
) -> dict[str, ParameterRecord]:
    try:
        compatibility = select_registry_case_compatibility(
            registry=registry,
            fungus_id=case.fungus_id,
            substrate_id=case.substrate_id,
            report=case.modelability_report,
        )
    except RegistryCaseBuildError:
        return {}
    assembler = get_registry_process_assembler(compatibility.process_type)
    if assembler is None:
        return {}
    chain_records = _chain_template_role_records(
        registry=registry,
        compatibility=compatibility,
        required_roles=assembler.required_parameter_roles,
    )
    if chain_records is not None:
        return dict(chain_records)
    records: dict[str, ParameterRecord] = {}
    roles = tuple(dict.fromkeys((*assembler.required_parameter_roles, *compatibility.parameter_roles.keys())))
    for role in roles:
        symbol = compatibility.parameter_roles.get(role)
        if symbol is None:
            continue
        record = _best_case_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            process_type=compatibility.process_type,
            enzyme_class=compatibility.enzyme_class,
            substrate_class=compatibility.substrate_class,
            fungus_id=case.fungus_id,
            substrate_id=case.substrate_id,
            environment_id=case.environment_id,
            mode=mode,
        )
        if record is not None:
            records[role] = record
    return records


def _chain_template_role_records(
    *,
    registry: FungModRegistry,
    compatibility: Any,
    required_roles: tuple[str, ...],
) -> Mapping[str, ParameterRecord] | None:
    if compatibility.process_type != "extracellular_enzyme_chain":
        return None
    if not compatibility.case_template_id:
        return {}
    try:
        template = registry.get_case_template(compatibility.case_template_id)
    except RegistryLookupError:
        return {}
    parameter_ids = template.process_state_metadata.get("parameter_record_ids")
    if not isinstance(parameter_ids, dict):
        return {}
    roles = tuple(dict.fromkeys((*required_roles, *compatibility.parameter_roles.keys())))
    records: dict[str, ParameterRecord] = {}
    for role in roles:
        record_id = parameter_ids.get(role)
        if record_id is None:
            continue
        record = registry.parameters.get(str(record_id))
        if record is not None:
            records[role] = record
    return records


def _best_case_parameter_record(
    *,
    registry: FungModRegistry,
    parameter_symbol: str,
    process_type: str,
    enzyme_class: str,
    substrate_class: str,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    mode: str,
) -> ParameterRecord | None:
    candidates = [
        record
        for record in registry.parameters.values()
        if record.parameter_symbol == parameter_symbol
        and record.process_type == process_type
        and _matches(record.enzyme_class, enzyme_class)
        and _matches(record.substrate_class, substrate_class)
        and _matches(record.fungus_id, fungus_id)
        and _matches(record.substrate_id, substrate_id)
        and _matches(record.environment_id, environment_id)
    ]
    if mode == "scientific":
        candidates = [record for record in candidates if not _is_exploratory_record(record)]
    if not candidates:
        return None
    return max(candidates, key=_scientific_parameter_record_priority if mode == "scientific" else _parameter_record_priority)


def _matches(record_value: str | None, requested: str) -> bool:
    return record_value is None or record_value == requested


def _parameter_record_priority(record: ParameterRecord) -> tuple[int, int, int]:
    selector_score = sum(
        value is not None
        for value in (
            record.enzyme_class,
            record.substrate_class,
            record.fungus_id,
            record.substrate_id,
            record.environment_id,
        )
    )
    value_score = 2 if record.value.is_uncertain else 1 if record.value.is_exact else 0
    exploratory_score = 1 if _is_exploratory_record(record) else 0
    return selector_score, value_score, exploratory_score


def _scientific_parameter_record_priority(record: ParameterRecord) -> tuple[int, int, int]:
    selector_score = sum(
        value is not None
        for value in (
            record.enzyme_class,
            record.substrate_class,
            record.fungus_id,
            record.substrate_id,
            record.environment_id,
        )
    )
    value_score = 2 if record.value.is_exact else 1 if record.value.is_uncertain else 0
    maturity_score = 1 if record.maturity == "calibrated" else 0
    return selector_score, value_score, maturity_score


def _trajectory_state_names(row: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        name
        for name in row
        if name not in {"time", "time_units"} and not name.endswith("_units")
    )


def _role_for_state(state_name: str, state_roles: Mapping[str, str]) -> str:
    for role, configured_state in state_roles.items():
        if configured_state == state_name:
            return "enzyme" if role == "catalyst" else role
    return ""


def _is_surface_case(context: Mapping[str, Any]) -> bool:
    return context.get("process_type") == "surface_catalysis"


def _final_product_metric_name(product_units: str) -> str:
    return "final_product_concentration" if _is_concentration_units(product_units) else "final_product_amount"


def _is_concentration_units(units: str) -> bool:
    text = units.strip().lower()
    if text in {"mm", "millimolar", "molar", "mol / l", "mol/l", "mole / liter", "mole/liter"}:
        return True
    volume_tokens = ("liter", "litre", "l", "meter ** 3", "metre ** 3")
    if "/" not in text:
        return False
    return any(token in text for token in volume_tokens)


def _initial_state_value(
    trajectory_rows: Sequence[Mapping[str, str]],
    state_name: str | None,
) -> float | None:
    if not trajectory_rows or state_name is None:
        return None
    return _optional_float(trajectory_rows[0].get(state_name))


def _rate_by_index(rate_rows: Sequence[Mapping[str, str]]) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    for row in rate_rows:
        try:
            index = int(str(row.get("index", "")))
        except ValueError:
            continue
        value = _optional_float(row.get("value"))
        if value is None:
            continue
        output[index] = {
            "name": row.get("name", ""),
            "value": value,
            "units": row.get("units", ""),
        }
    return output


def _maximum_process_rate(rate_rows: Sequence[Mapping[str, str]]) -> dict[str, Any] | None:
    values: list[tuple[float, str]] = []
    for row in rate_rows:
        value = _optional_float(row.get("value"))
        if value is not None:
            values.append((value, row.get("units", "")))
    if not values:
        return None
    value, units = max(values, key=lambda item: item[0])
    return {"value": value, "units": units}


def _value_source(record: ParameterRecord) -> str:
    return record.value.source or _provenance_source(record.provenance)


def _provenance_source(provenance: Mapping[str, Any]) -> str:
    source = provenance.get("source")
    if source is not None:
        return str(source)
    database = provenance.get("source_database")
    reaction = provenance.get("source_reaction_id")
    if database is not None and reaction is not None:
        return f"{database} reaction {reaction}"
    if database is not None:
        return str(database)
    return ""


def _is_exploratory_record(record: ParameterRecord) -> bool:
    return record.maturity == "exploratory_prior" or bool(record.provenance.get("exploratory_prior"))


def _parameter_source_class(record: ParameterRecord | None) -> str:
    if record is None:
        return "unknown"
    if record.value.kind == "unknown":
        return "unknown"
    if _is_exploratory_record(record):
        return "user_supplied_exploratory_prior"
    if record.maturity == "literature_range" or record.value.kind == "range":
        return "literature_range"
    if record.maturity == "literature_processed" and record.value.kind == "exact":
        return "selected_exact_value"
    return "unknown"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_table(path: Path, *, table_name: str, rows: Sequence[Mapping[str, Any]]) -> None:
    _write_csv(path, rows, fieldnames=table_fieldnames(table_name, rows))


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved_fieldnames = tuple(fieldnames) if fieldnames is not None else _fieldnames(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=resolved_fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in resolved_fieldnames})


def _fieldnames(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    ordered: dict[str, None] = {}
    for row in rows:
        for key in row:
            ordered.setdefault(str(key), None)
    return tuple(ordered)


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, np.generic):
        return value.item()
    return "" if value is None else value


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_blank(value: Any) -> Any:
    number = _optional_float(value)
    return "" if number is None else number


__all__ = ["WrittenTables", "write_standard_tables"]
