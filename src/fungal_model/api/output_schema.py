"""Versioned output schema for standard virtual-experiment tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

OUTPUT_SCHEMA_VERSION = "1.6.0"
OUTPUT_SCHEMA_NAME = "fungmod_virtual_experiment_outputs"


def _column(
    name: str,
    description: str,
    *,
    required: bool = True,
    units_policy: str = "not_applicable",
    semantic_type: str = "text",
    allowed_values: str = "",
    join_notes: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "required": required,
        "units_policy": units_policy,
        "semantic_type": semantic_type,
        "allowed_values": allowed_values,
        "join_notes": join_notes,
    }


COMMON_CASE_COLUMNS = (
    _column("output_schema_version", "Version of this virtual-experiment output schema."),
    _column("case_id", "Stable case identifier within one output bundle.", semantic_type="identifier"),
    _column("fungus_id", "Registry ID for the fungus or enzyme-source record.", semantic_type="identifier"),
    _column("fungus_name", "Display name for the fungus or enzyme-source record."),
    _column("substrate_id", "Registry ID for the substrate record.", semantic_type="identifier"),
    _column("substrate_name", "Display name for the substrate record."),
    _column("environment_id", "Registry or runtime ID for the environment case.", semantic_type="identifier"),
    _column("environment_name", "Display name for the environment case."),
    _column(
        "temperature_C",
        "Environment temperature metadata in degrees Celsius.",
        required=False,
        units_policy="degree_Celsius",
    ),
    _column("ph", "Environment pH metadata.", required=False, units_policy="dimensionless"),
    _column("oxygen", "Environment oxygen label or value metadata.", required=False),
    _column("environment_source", "Whether the environment came from the registry or a runtime grid."),
    _column(
        "environment_effect_status",
        "How environment fields affected the model.",
        allowed_values="metadata_only; condition_specific_parameters; active_response_model; preflight_only; not_applicable",
    ),
    _column("environment_response_model", "Active environment-response model identifier, or none."),
    _column(
        "environment_comparison_allowed", "Whether environment-level outcome comparisons are scientifically supported."
    ),
    _column("environment_ranking_allowed", "Whether this table may be used to rank environments by model response."),
    _column("environment_response_plot_allowed", "Whether environment-response plots are scientifically supported."),
    _column("environment_guardrail", "Short policy explaining environment comparison and plotting limits."),
    _column("process_type", "Implemented process type used for this case."),
)

SAMPLE_COLUMNS = (
    _column("sample_id", "Stable sample identifier within the case.", semantic_type="identifier"),
    _column("sample_index", "Zero-based sample index.", semantic_type="integer"),
)


def _table(
    description: str,
    columns: Sequence[Mapping[str, Any]],
    *,
    primary_key: Sequence[str],
    join_keys: Sequence[str] = ("case_id",),
) -> dict[str, Any]:
    return {
        "description": description,
        "primary_key": list(primary_key),
        "join_keys": list(join_keys),
        "columns": [dict(column) for column in columns],
    }


OUTPUT_TABLE_SCHEMAS: dict[str, dict[str, Any]] = {
    "modelability_preflight": _table(
        "Preflight guardrail status before simulation.",
        (
            *COMMON_CASE_COLUMNS,
            _column(
                "assessment_mode",
                "Mode used for this preflight assessment.",
                allowed_values="scientific; exploratory; toy",
            ),
            _column("status", "Modelability status for the case."),
            _column(
                "simulation_allowed_for_mode",
                "Whether simulate(...) would accept this case in the assessed mode.",
                semantic_type="boolean",
            ),
            _column("blocking_reason", "Machine-readable reason simulation is blocked, or not_blocked."),
            _column("recommended_next_action", "Machine-readable next action suggested by the preflight policy."),
            _column("known_count", "Number of known modelability facts.", semantic_type="integer"),
            _column("uncertain_count", "Number of uncertain modelability facts.", semantic_type="integer"),
            _column("missing_count", "Number of missing modelability facts.", semantic_type="integer"),
            _column("incompatible_count", "Number of incompatible modelability facts.", semantic_type="integer"),
            _column("required_processes", "Semicolon-separated process types required by the case."),
            _column("candidate_processes", "Semicolon-separated process types found by registry compatibility."),
            _column("required_parameters", "Semicolon-separated required parameter symbols."),
            _column("suggested_experiments", "Semicolon-separated experimental suggestions from missing inputs."),
        ),
        primary_key=("case_id",),
    ),
    "modelability_items": _table(
        "Flat per-case modelability facts from preflight, including known, uncertain, missing, and incompatible items.",
        (
            *COMMON_CASE_COLUMNS,
            _column("item_index", "Zero-based modelability item index within the case.", semantic_type="integer"),
            _column(
                "item_status",
                "Modelability fact class.",
                allowed_values="known; uncertain; missing; incompatible",
            ),
            _column("item_type", "Modelability item type."),
            _column("item_id", "Stable item identifier from the modelability report.", semantic_type="identifier"),
            _column("modelability_status", "Overall modelability status for the case."),
            _column("message", "Human-readable modelability message."),
            _column("details", "JSON details from the structured modelability item.", required=False),
            _column("allowed_use", "Machine-readable policy for interpreting this item."),
        ),
        primary_key=("case_id", "item_index"),
    ),
    "case_summary": _table(
        "One-row simulation summary per case.",
        (
            *COMMON_CASE_COLUMNS,
            _column("modelability_status", "Preflight modelability status used as a simulation guardrail."),
            _column("sample_count", "Number of successful samples.", semantic_type="integer"),
            _column("sample_failure_count", "Number of failed samples.", semantic_type="integer"),
            _column("simulated", "Whether at least one sample was simulated.", semantic_type="boolean"),
            _column("preflight_guardrail", "Guardrail family applied before simulation."),
        ),
        primary_key=("case_id",),
    ),
    "time_series_long": _table(
        "Long-format simulated and derived time-series observables.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column("validation_passed", "Whether validators passed for this sample.", semantic_type="boolean"),
            _column("time_index", "Zero-based index in the simulated time grid.", semantic_type="integer"),
            _column("time", "Simulation time.", units_policy="time_units", semantic_type="number"),
            _column("time_units", "Units for the time column."),
            _column("state", "State or derived observable name."),
            _column("state_role", "Semantic role for the state or observable."),
            _column("value", "State or derived observable value.", units_policy="units", semantic_type="number"),
            _column("units", "Units for value."),
            _column("source", "Whether the row is a simulated state, process rate, or derived observable."),
        ),
        primary_key=("case_id", "sample_id", "time_index", "state"),
        join_keys=("case_id", "sample_id"),
    ),
    "final_states": _table(
        "Final simulated state values per sample.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column("state", "Simulated state name."),
            _column("state_role", "Semantic role for the state."),
            _column("value", "Final state value.", units_policy="units", semantic_type="number"),
            _column("units", "Units for value."),
            _column("source", "Source of the final-state row."),
        ),
        primary_key=("case_id", "sample_id", "state"),
        join_keys=("case_id", "sample_id"),
    ),
    "final_metrics": _table(
        "Per-sample final metrics and not-applicable rows.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column("metric", "Metric name."),
            _column(
                "value",
                "Metric value when status permits.",
                required=False,
                units_policy="units",
                semantic_type="number",
            ),
            _column("units", "Units for value, or not_applicable."),
            _column("status", "Metric status.", allowed_values="computed; derived_proxy; not_applicable"),
            _column("notes", "Metric caveats or not-applicable explanation.", required=False),
        ),
        primary_key=("case_id", "sample_id", "metric"),
        join_keys=("case_id", "sample_id"),
    ),
    "threshold_times": _table(
        "Per-sample times to configured substrate-degradation thresholds.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column(
                "threshold_fraction",
                "Substrate degradation threshold.",
                units_policy="dimensionless",
                semantic_type="number",
            ),
            _column("metric", "Threshold metric name."),
            _column(
                "value", "Crossing time when reached.", required=False, units_policy="units", semantic_type="number"
            ),
            _column("units", "Time units."),
            _column("status", "Threshold status.", allowed_values="computed; not_reached; not_applicable"),
            _column("notes", "Threshold caveats or not-applicable explanation.", required=False),
        ),
        primary_key=("case_id", "sample_id", "threshold_fraction"),
        join_keys=("case_id", "sample_id"),
    ),
    "sampled_parameters": _table(
        "Per-sample parameter values with source maturity and range-use policy.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column("role", "Process-factory role for the parameter."),
            _column("symbol", "Parameter symbol."),
            _column("sampled_value", "Exact value used in this sample.", units_policy="units", semantic_type="number"),
            _column("units", "Units for sampled_value."),
            _column("sampled_value_kind", "Value kind used by the sampled run."),
            _column(
                "source_record_id", "Registry parameter record that generated this sample.", semantic_type="identifier"
            ),
            _column("source_value_kind", "Original ValueSpec kind on the source record."),
            _column("source_maturity", "Maturity label on the source parameter record."),
            _column("parameter_source_class", "Normalized source class for researcher filtering."),
            _column("source", "Human-readable value source."),
            _column("confidence_level", "Confidence or maturity label from the ValueSpec."),
            _column(
                "exploratory_prior", "Whether the source is a user-supplied exploratory prior.", semantic_type="boolean"
            ),
            _column("range_scope", "Machine-readable scope of a range or distribution."),
            _column("range_interpretation", "How a range or distribution may be interpreted."),
            _column("allowed_use", "Machine-readable policy for allowed downstream use."),
            _column("notes", "Source parameter notes."),
        ),
        primary_key=("case_id", "sample_id", "role"),
        join_keys=("case_id", "sample_id"),
    ),
    "assumption_summary": _table(
        "Per-case assumptions, uncertain inputs, blockers, and follow-up suggestions.",
        (
            *COMMON_CASE_COLUMNS,
            _column(
                "row_type",
                "Kind of summary row.",
                allowed_values="assumption; uncertain; missing; incompatible; suggested_experiment",
            ),
            _column("item_type", "Modelability item type or summary item family."),
            _column("item_id", "Stable item identifier within the case.", semantic_type="identifier"),
            _column("modelability_status", "Modelability status for the case."),
            _column("message", "Human-readable assumption, uncertainty, blocker, or suggestion."),
            _column("details", "JSON details for structured modelability items.", required=False),
            _column("allowed_use", "Machine-readable policy for interpreting this row."),
        ),
        primary_key=("case_id", "row_type", "item_id"),
    ),
    "mechanism_summary": _table(
        "Per-case implemented process laws, modifiers, maturity labels, and limitations.",
        (
            *COMMON_CASE_COLUMNS,
            _column("mechanism_index", "Zero-based mechanism index within the case.", semantic_type="integer"),
            _column(
                "mechanism_kind",
                "Mechanism row kind.",
                allowed_values="process_law; rate_modifier; thermodynamic_validator",
            ),
            _column("mechanism_id", "Stable mechanism identifier.", semantic_type="identifier"),
            _column("mechanism_family", "Reusable mechanism family."),
            _column(
                "active",
                "Whether this mechanism actively affected simulated rates or outputs.",
                semantic_type="boolean",
            ),
            _column("maturity", "Mechanism maturity label."),
            _column("configured_by", "Registry/config source that selected this mechanism."),
            _column("equation_or_law", "Short mathematical law or process description."),
            _column("state_variables", "Semicolon-separated configured state variables."),
            _column("parameters", "Semicolon-separated parameter roles or symbols."),
            _column("assumptions", "Semicolon-separated mechanism assumptions."),
            _column("limitations", "Semicolon-separated mechanism limitations."),
            _column("provenance", "JSON provenance payload.", required=False),
        ),
        primary_key=("case_id", "mechanism_index"),
    ),
    "summary_metrics": _table(
        "Per-case ensemble summary statistics for computed metrics.",
        (
            *COMMON_CASE_COLUMNS,
            _column("metric", "Metric name."),
            _column("units", "Units for the summarized metric."),
            _column("count", "Number of samples summarized.", semantic_type="integer"),
            _column("mean", "Mean value.", semantic_type="number"),
            _column("min", "Minimum value.", semantic_type="number"),
            _column("max", "Maximum value.", semantic_type="number"),
            _column("p05", "5th percentile.", semantic_type="number"),
            _column("p50", "Median value.", semantic_type="number"),
            _column("p95", "95th percentile.", semantic_type="number"),
        ),
        primary_key=("case_id", "metric", "units"),
    ),
    "environment_summary": _table(
        "Environment-level metadata and guarded aggregate metrics.",
        (
            _column("output_schema_version", "Version of this virtual-experiment output schema."),
            _column("environment_id", "Environment ID.", semantic_type="identifier"),
            _column(
                "temperature_C", "Environment temperature metadata.", required=False, units_policy="degree_Celsius"
            ),
            _column("ph", "Environment pH metadata.", required=False, units_policy="dimensionless"),
            _column("oxygen", "Environment oxygen metadata.", required=False),
            _column("environment_source", "Environment source."),
            _column("environment_effect_status", "How environment fields affected the model."),
            _column("environment_response_model", "Active environment-response model identifier, or none."),
            _column("environment_comparison_allowed", "Whether environment-level outcome comparisons are supported."),
            _column("environment_ranking_allowed", "Whether ranking environments by outputs is supported."),
            _column("environment_response_plot_allowed", "Whether response plots are supported."),
            _column("environment_response_metric_status", "Status for aggregate response metric columns."),
            _column("environment_guardrail", "Policy explaining environment comparison and plotting limits."),
            _column("n_cases", "Number of cases using this environment.", semantic_type="integer"),
            _column("n_samples", "Number of attempted samples.", semantic_type="integer"),
            _column("n_successful_samples", "Number of successful samples.", semantic_type="integer"),
            _column("n_failed_samples", "Number of failed samples.", semantic_type="integer"),
            _column(
                "median_final_substrate_degraded_fraction",
                "Median degradation fraction when comparison is allowed.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "p05_final_substrate_degraded_fraction",
                "5th percentile when comparison is allowed.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "p95_final_substrate_degraded_fraction",
                "95th percentile when comparison is allowed.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "median_time_to_50_percent_degradation",
                "Median time-to-50-percent degradation when comparison is allowed.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "p05_time_to_50_percent_degradation",
                "5th percentile when comparison is allowed.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "p95_time_to_50_percent_degradation",
                "95th percentile when comparison is allowed.",
                required=False,
                semantic_type="number",
            ),
            _column("limitations", "Semicolon-separated limitations for the environment rows."),
        ),
        primary_key=("environment_id",),
        join_keys=("environment_id",),
    ),
    "comparison_summary": _table(
        "Guarded screen-comparison index over existing final-metric and threshold rows.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column("comparison_scope", "Comparison scope represented by this row."),
            _column("source_table", "Standard output table that supplied this row."),
            _column("source_metric", "Metric from the source row."),
            _column(
                "threshold_fraction",
                "Threshold fraction for threshold rows.",
                required=False,
                units_policy="dimensionless",
                semantic_type="number",
            ),
            _column("value", "Source row value when present.", required=False, semantic_type="number"),
            _column("units", "Source row units."),
            _column("source_status", "Status from the source row."),
            _column("source_notes", "Notes from the source row.", required=False),
            _column("comparable_group_id", "Stable group ID for rows with the same source table, metric, and units."),
            _column(
                "comparison_allowed",
                "Whether side-by-side comparison is allowed for this row.",
                semantic_type="boolean",
            ),
            _column("ranking_allowed", "Whether this row may be ranked against peer rows.", semantic_type="boolean"),
            _column(
                "ranking_blocking_reason",
                "Reason ranking is blocked, or blank when ranking is allowed.",
                required=False,
            ),
            _column("recommended_next_action", "Machine-readable recommendation for interpreting this row."),
        ),
        primary_key=("case_id", "sample_id", "source_table", "source_metric", "threshold_fraction"),
        join_keys=("case_id", "sample_id"),
    ),
    "uncertainty_summary": _table(
        "Derived uncertainty/range index over existing sampled parameters and per-case summary metrics.",
        (
            *COMMON_CASE_COLUMNS,
            _column(
                "summary_type",
                "Kind of uncertainty summary row.",
                allowed_values="sampled_parameter_distribution; output_metric_sample_distribution",
            ),
            _column("target_id", "Parameter symbol or metric represented by the row.", semantic_type="identifier"),
            _column("target_label", "Human-readable target label."),
            _column("source_table", "Standard output table that supplied the values."),
            _column("source_metric", "Source value or metric summarized."),
            _column("units", "Units for p05/p50/p95."),
            _column("count", "Number of values summarized.", semantic_type="integer"),
            _column("p05", "5th percentile over existing sampled values or sample outputs.", semantic_type="number"),
            _column("p50", "Median over existing sampled values or sample outputs.", semantic_type="number"),
            _column("p95", "95th percentile over existing sampled values or sample outputs.", semantic_type="number"),
            _column(
                "source_record_id",
                "Registry parameter record for sampled-parameter rows.",
                required=False,
                semantic_type="identifier",
            ),
            _column("source_value_kind", "Original ValueSpec kind for sampled-parameter rows.", required=False),
            _column("source_maturity", "Maturity label for sampled-parameter source records.", required=False),
            _column("parameter_source_class", "Normalized source class for sampled-parameter rows.", required=False),
            _column(
                "exploratory_prior",
                "Whether the sampled-parameter source is exploratory.",
                required=False,
                semantic_type="boolean",
            ),
            _column("range_scope", "Range/distribution scope for sampled-parameter rows.", required=False),
            _column("range_interpretation", "Allowed interpretation for sampled-parameter ranges.", required=False),
            _column("allowed_use", "Machine-readable allowed-use policy for the summarized values."),
            _column("uncertainty_band_status", "Machine-readable status for how the band was produced."),
            _column(
                "interpretation_guardrail", "Human-readable guardrail preventing validation/calibration overclaims."
            ),
        ),
        primary_key=("case_id", "summary_type", "target_id", "source_table", "source_metric", "source_record_id"),
    ),
    "trajectory_quantiles": _table(
        "Derived trajectory quantile bands over existing time_series_long rows.",
        (
            *COMMON_CASE_COLUMNS,
            _column("time_index", "Zero-based index in the simulated time grid.", semantic_type="integer"),
            _column(
                "time",
                "Simulation time represented by this quantile row.",
                units_policy="time_units",
                semantic_type="number",
            ),
            _column("time_units", "Units for the time column."),
            _column("state", "State or derived observable name summarized from time_series_long."),
            _column("state_role", "Semantic role for the state or observable."),
            _column("source_table", "Standard output table that supplied the values."),
            _column("source_metric", "Source value summarized from the source table."),
            _column("source", "Source class from time_series_long."),
            _column("units", "Units for p05/p50/p95."),
            _column("count", "Number of finite numeric sample rows summarized.", semantic_type="integer"),
            _column("p05", "5th percentile over existing sample time-series values.", semantic_type="number"),
            _column("p50", "Median over existing sample time-series values.", semantic_type="number"),
            _column("p95", "95th percentile over existing sample time-series values.", semantic_type="number"),
            _column("allowed_use", "Machine-readable allowed-use policy for the summarized values."),
            _column("trajectory_band_status", "Machine-readable status for how the trajectory band was produced."),
            _column(
                "interpretation_guardrail", "Human-readable guardrail preventing validation/calibration overclaims."
            ),
        ),
        primary_key=("case_id", "time_index", "state", "state_role", "source", "units"),
    ),
    "thermodynamic_diagnostics": _table(
        "Configured-output thermodynamic diagnostics copied from existing per-sample thermodynamic_summary artifacts.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column("artifact_source_directory", "Sample configured-output bundle directory inspected for artifacts."),
            _column(
                "thermodynamic_summary_json_present",
                "Whether thermodynamic_summary.json existed in the sample bundle.",
                semantic_type="boolean",
            ),
            _column(
                "thermodynamic_summary_csv_present",
                "Whether thermodynamic_summary.csv existed in the sample bundle.",
                semantic_type="boolean",
            ),
            _column("summary_kind", "Top-level kind field from thermodynamic_summary.json.", required=False),
            _column(
                "summary_count",
                "Top-level count from thermodynamic_summary.json.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "summary_status_counts",
                "JSON status-count mapping copied from thermodynamic_summary.json.",
                required=False,
            ),
            _column(
                "summary_severity_counts",
                "JSON severity-count mapping copied from thermodynamic_summary.json.",
                required=False,
            ),
            _column(
                "summary_has_reaction_quotient_gibbs",
                "Whether the configured summary reported explicit-Q Gibbs rows.",
                required=False,
                semantic_type="boolean",
            ),
            _column(
                "summary_has_entropy_production_rate",
                "Whether the configured summary reported entropy-production-rate rows.",
                required=False,
                semantic_type="boolean",
            ),
            _column(
                "summary_has_entropy_budget",
                "Whether the configured summary reported an evaluated entropy budget.",
                required=False,
                semantic_type="boolean",
            ),
            _column(
                "entropy_budget_scope",
                "Entropy-budget scope text copied from thermodynamic_summary.json.",
                required=False,
            ),
            _column(
                "entropy_budget_units", "Entropy-budget units copied from thermodynamic_summary.json.", required=False
            ),
            _column(
                "entropy_budget_total",
                "Entropy-budget total copied from thermodynamic_summary.json.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "entropy_budget_minimum",
                "Entropy-budget minimum copied from thermodynamic_summary.json.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "entropy_budget_negative_count",
                "Entropy-budget negative-row count copied from thermodynamic_summary.json.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "entropy_budget_evaluated_count",
                "Entropy-budget evaluated-row count copied from thermodynamic_summary.json.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "entropy_budget_status", "Entropy-budget status copied from thermodynamic_summary.json.", required=False
            ),
            _column(
                "entropy_budget_limitations",
                "Entropy-budget limitations copied from thermodynamic_summary.json.",
                required=False,
            ),
            _column(
                "row_index",
                "Zero-based thermodynamic_summary.csv row index within the sample bundle.",
                semantic_type="integer",
            ),
            _column("row_name", "Validation row name copied from thermodynamic_summary.csv."),
            _column("row_status", "Validation row status copied from thermodynamic_summary.csv.", required=False),
            _column("row_passed", "Validation row passed flag copied from thermodynamic_summary.csv.", required=False),
            _column("row_severity", "Validation row severity copied from thermodynamic_summary.csv.", required=False),
            _column(
                "residual_value",
                "Residual value copied from thermodynamic_summary.csv when present.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "residual_units", "Residual units copied from thermodynamic_summary.csv when present.", required=False
            ),
            _column(
                "delta_gibbs",
                "Delta Gibbs value copied from thermodynamic_summary.csv when present.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "delta_gibbs_units",
                "Delta Gibbs units copied from thermodynamic_summary.csv when present.",
                required=False,
            ),
            _column(
                "entropy_production_per_mole",
                "Entropy production per mole copied from thermodynamic_summary.csv when present.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "entropy_production_rate",
                "Entropy production rate copied from thermodynamic_summary.csv when present.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "entropy_production_rate_units",
                "Entropy production rate units copied from thermodynamic_summary.csv when present.",
                required=False,
            ),
            _column(
                "gibbs_equation", "Equation text copied from thermodynamic_summary.csv when present.", required=False
            ),
            _column(
                "entropy_equation", "Equation text copied from thermodynamic_summary.csv when present.", required=False
            ),
            _column(
                "dynamic_reaction_quotient",
                "Dynamic reaction quotient status copied from thermodynamic_summary.csv when present.",
                required=False,
            ),
            _column(
                "activity_model",
                "Activity-model status copied from thermodynamic_summary.csv when present.",
                required=False,
            ),
            _column(
                "solver_time_enforcement",
                "Solver-time enforcement status copied from thermodynamic_summary.csv when present.",
                required=False,
            ),
            _column("supported_scope", "Supported-scope text copied from thermodynamic_summary.json.", required=False),
            _column(
                "unsupported_scope", "Unsupported-scope text copied from thermodynamic_summary.json.", required=False
            ),
            _column(
                "message", "Validation row message copied from thermodynamic_summary.csv when present.", required=False
            ),
            _column("allowed_use", "Machine-readable policy for interpreting this row."),
            _column("interpretation_guardrail", "Human-readable no-inference guardrail for this diagnostics row."),
        ),
        primary_key=("case_id", "sample_id", "row_index", "row_name"),
        join_keys=("case_id", "sample_id"),
    ),
    "solver_diagnostics": _table(
        "Configured-output solver diagnostics copied from existing per-sample solver_diagnostics artifacts.",
        (
            *COMMON_CASE_COLUMNS,
            *SAMPLE_COLUMNS,
            _column("artifact_source_directory", "Sample configured-output bundle directory inspected for artifacts."),
            _column(
                "solver_diagnostics_json_present",
                "Whether solver_diagnostics.json existed in the sample bundle.",
                semantic_type="boolean",
            ),
            _column(
                "solver_diagnostics_csv_present",
                "Whether solver_diagnostics.csv existed in the sample bundle.",
                semantic_type="boolean",
            ),
            _column("summary_kind", "Top-level kind field from solver_diagnostics.json.", required=False),
            _column("summary_status", "Top-level status field from solver_diagnostics.json.", required=False),
            _column(
                "summary_metadata_available",
                "Whether solver metadata was available according to solver_diagnostics.json.",
                required=False,
                semantic_type="boolean",
            ),
            _column(
                "summary_row_count",
                "Top-level row_count from solver_diagnostics.json.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "summary_missing_metadata_fields",
                "JSON list of missing solver metadata fields copied from solver_diagnostics.json.",
                required=False,
            ),
            _column(
                "summary_allowed_use",
                "Top-level allowed-use text copied from solver_diagnostics.json.",
                required=False,
            ),
            _column(
                "unsupported_scope",
                "Unsupported-scope text copied from solver_diagnostics.json.",
                required=False,
            ),
            _column(
                "row_index",
                "Zero-based solver_diagnostics.csv row index within the sample bundle.",
                semantic_type="integer",
            ),
            _column("config_name", "Configured model name copied from solver_diagnostics.csv.", required=False),
            _column("config_path", "Configured model path copied from solver_diagnostics.csv.", required=False),
            _column("mode", "Configured model mode copied from solver_diagnostics.csv.", required=False),
            _column("maturity", "Configured model maturity copied from solver_diagnostics.csv.", required=False),
            _column("kind", "Configured model kind copied from solver_diagnostics.csv.", required=False),
            _column("result_name", "Simulation result name copied from solver_diagnostics.csv.", required=False),
            _column("result_label", "Simulation result label copied from solver_diagnostics.csv.", required=False),
            _column("model_version", "Simulation model version copied from solver_diagnostics.csv.", required=False),
            _column(
                "state_count",
                "State count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "configured_process_count",
                "Configured process count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "process_rate_count",
                "Process-rate count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column("time_units", "Time units copied from solver_diagnostics.csv.", required=False),
            _column(
                "configured_time_start",
                "Configured time-grid start copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "configured_time_stop",
                "Configured time-grid stop copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "configured_time_evaluation_count",
                "Configured time-grid evaluation count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "result_time_point_count",
                "Result time-point count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column("solver_backend", "Solver backend copied from solver_diagnostics.csv.", required=False),
            _column("solver_method", "Solver method copied from solver_diagnostics.csv.", required=False),
            _column(
                "solver_success",
                "Solver success flag copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="boolean",
            ),
            _column("solver_status", "Solver status copied from solver_diagnostics.csv.", required=False),
            _column("solver_message", "Solver message copied from solver_diagnostics.csv.", required=False),
            _column(
                "nfev",
                "Solver function-evaluation count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "njev",
                "Solver Jacobian-evaluation count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "nlu",
                "Solver LU-decomposition count copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="integer",
            ),
            _column(
                "rtol",
                "Relative tolerance copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "atol",
                "Absolute tolerance copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="number",
            ),
            _column(
                "max_step_value",
                "Maximum step value copied from solver_diagnostics.csv when present.",
                required=False,
                semantic_type="number",
            ),
            _column("max_step_units", "Maximum step units copied from solver_diagnostics.csv.", required=False),
            _column(
                "metadata_available",
                "Row-level metadata availability copied from solver_diagnostics.csv.",
                required=False,
                semantic_type="boolean",
            ),
            _column("allowed_use", "Machine-readable policy for interpreting this row."),
            _column(
                "interpretation_guardrail",
                "Human-readable guardrail preventing solver-quality, validation, or biology overclaims.",
            ),
        ),
        primary_key=("case_id", "sample_id", "row_index", "config_name", "result_name"),
        join_keys=("case_id", "sample_id"),
    ),
    "provenance_table": _table(
        "Registry and parameter provenance rows used by each case.",
        (
            *COMMON_CASE_COLUMNS,
            _column("record_type", "Type of provenance record."),
            _column("record_id", "Record ID.", semantic_type="identifier"),
            _column("role", "Process-factory role when applicable.", required=False),
            _column("symbol", "Parameter symbol when applicable.", required=False),
            _column("maturity", "Record maturity label.", required=False),
            _column("value_kind", "ValueSpec kind or missing/incompatible marker.", required=False),
            _column("source", "Human-readable source.", required=False),
            _column("confidence_level", "Confidence or maturity level.", required=False),
            _column(
                "exploratory_prior", "Whether the row is an exploratory prior.", required=False, semantic_type="boolean"
            ),
            _column("range_scope", "Range/distribution scope when applicable.", required=False),
            _column("range_interpretation", "Range/distribution interpretation when applicable.", required=False),
            _column("allowed_use", "Allowed downstream use policy.", required=False),
            _column("notes", "Record notes.", required=False),
            _column("provenance", "JSON provenance payload.", required=False),
        ),
        primary_key=("case_id", "record_type", "record_id", "role", "symbol"),
    ),
    "limitations_table": _table(
        "Case limitations and scientific guardrails.",
        (
            *COMMON_CASE_COLUMNS,
            _column("category", "Limitation category."),
            _column("severity", "Severity level.", allowed_values="info; important; blocking"),
            _column("limitation", "Human-readable limitation."),
            _column("source", "Source system or process for the limitation."),
        ),
        primary_key=("case_id", "category", "source", "limitation"),
    ),
    "missing_parameters": _table(
        "First-class missing-input table for experimental planning.",
        (
            *COMMON_CASE_COLUMNS,
            _column("missing_item_type", "Type of missing item."),
            _column("parameter_symbol", "Missing parameter symbol when applicable.", required=False),
            _column("source_record_id", "Record ID when the missing item is an explicit unknown.", required=False),
            _column("expected_units", "Expected or recorded units for the missing parameter.", required=False),
            _column("missing_status", "Missing-input status.", allowed_values="absent; explicit_unknown; incompatible"),
            _column("message", "Modelability message for the missing input."),
            _column("suggested_experiment", "Suggested experiment or curation task.", required=False),
            _column("details", "JSON detail payload.", required=False),
        ),
        primary_key=("case_id", "missing_item_type", "parameter_symbol", "source_record_id"),
    ),
    "suggested_experiments": _table(
        "First-class suggested experiment and curation task table.",
        (
            *COMMON_CASE_COLUMNS,
            _column("suggestion_id", "Stable suggestion identifier within the case.", semantic_type="identifier"),
            _column("parameter_symbol", "Parameter symbol targeted by the suggestion.", required=False),
            _column("suggested_experiment", "Suggested experiment or curation task."),
            _column("priority", "Suggested priority for resolving the missing input."),
            _column("rationale", "Why this suggestion is emitted."),
            _column("allowed_use_after_resolution", "Allowed use once the parameter is measured or curated."),
        ),
        primary_key=("case_id", "suggestion_id"),
    ),
}


DATA_DICTIONARY_COLUMNS = (
    "output_schema_version",
    "table",
    "column",
    "description",
    "required",
    "units_policy",
    "semantic_type",
    "allowed_values",
    "join_notes",
)


def table_fieldnames(table_name: str, rows: Sequence[Mapping[str, Any]] = ()) -> tuple[str, ...]:
    """Return versioned fieldnames for a standard table plus row extras."""

    schema = OUTPUT_TABLE_SCHEMAS.get(table_name)
    ordered: dict[str, None] = {}
    if schema is not None:
        for column in schema["columns"]:
            ordered[str(column["name"])] = None
    for row in rows:
        for key in row:
            ordered.setdefault(str(key), None)
    return tuple(ordered)


def output_schema_document() -> dict[str, Any]:
    """Return a JSON-serializable output schema document."""

    return {
        "schema_name": OUTPUT_SCHEMA_NAME,
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "tables": {name: dict(schema) for name, schema in OUTPUT_TABLE_SCHEMAS.items()},
    }


def output_data_dictionary_rows() -> list[dict[str, Any]]:
    """Return one data-dictionary row per standard table column."""

    rows: list[dict[str, Any]] = []
    for table_name, schema in OUTPUT_TABLE_SCHEMAS.items():
        for column in schema["columns"]:
            rows.append(
                {
                    "output_schema_version": OUTPUT_SCHEMA_VERSION,
                    "table": table_name,
                    "column": column["name"],
                    "description": column["description"],
                    "required": column["required"],
                    "units_policy": column["units_policy"],
                    "semantic_type": column["semantic_type"],
                    "allowed_values": column["allowed_values"],
                    "join_notes": column["join_notes"],
                }
            )
    return rows


__all__ = [
    "DATA_DICTIONARY_COLUMNS",
    "OUTPUT_SCHEMA_NAME",
    "OUTPUT_SCHEMA_VERSION",
    "OUTPUT_TABLE_SCHEMAS",
    "output_data_dictionary_rows",
    "output_schema_document",
    "table_fieldnames",
]
