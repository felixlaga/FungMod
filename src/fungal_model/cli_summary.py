"""Machine-readable summaries of ``fungmod`` subcommands: ``--json PATH`` (CLI-003).

``fungmod run``, ``assemble``, ``check-data`` and ``fit`` take ``--json PATH``
(``-`` for standard output) and then write one JSON document besides their
printed text: the command and its arguments, the FungMod version, the
``schema_version`` of this summary format, the exit code and its meaning, the
error (if any) and a ``result`` object of the command. The format is documented
in ``docs/cli.md`` ("Machine-readable summaries: --json").

The summary is built from what the command already computed, printed or
wrote: the API's objects and the files of the output directory. It makes no
scientific decision, converts no unit and fills no unknown with a default.
Every number of a physical quantity has its units as a string beside it.
Every ``null`` is an explicit unknown, or a value that does not apply, and the
object holding it has a ``null_reasons`` object whose entry of the same key
says why; a section the command never reached is ``null`` with the reason
:data:`NOT_REACHED`. No NaN or infinity is written: a non-finite number of a
table or report becomes ``null`` with the value quoted in its reason.
"""

from __future__ import annotations

import json
import math
import numbers
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fungal_model.api.result_tables import CASE_STATUS_NOT_SIMULATED, preflight_policy, standard_case_id
from fungal_model.api.user_data import USER_DATASET_MATURITY_GAP, UserDataset
from fungal_model.api.user_data_assembly import ASSEMBLY_STATUSES, AssembledTablesDraft
from fungal_model.api.user_data_fit import FIT_REPORT_KIND, TimecourseComparison
from fungal_model.api.virtual_experiment import DegradationScreenResult, VirtualExperiment
from fungal_model.screening import ModelabilityReport
from fungal_model.sources.uniprot import ProteomeNameResolution, UniprotSnapshot

SUMMARY_SCHEMA_VERSION = "1.0.0"
"""Version of the summary format; a change of a key's name, type or meaning changes it."""

SUMMARY_KIND = "fungmod_command_summary"
NULL_REASONS = "null_reasons"
NOT_REACHED = "not reached: the command stopped before this step (see exit_code and error)"
NO_ERROR = "the command reported no error"

# The status of each requested case in a run summary.
CASE_RAN = "ran"
CASE_BLOCKED = "blocked"
CASE_REFUSED = "refused"
CASE_FAILED = "failed"
RUN_CASE_STATUSES: Mapping[str, str] = {
    CASE_RAN: "simulated; its samples, metrics and threshold times are in the output bundle",
    CASE_BLOCKED: "the preflight blocks the case in the requested mode, so it was not simulated",
    CASE_REFUSED: (
        "runnable, but not simulated: another requested case is blocked and --runnable-only was not given, so "
        "nothing was simulated"
    ),
    CASE_FAILED: "runnable, but the simulation failed after a passing preflight, so it has no results",
}

# Commands that take --json, and the sections of their result object.
RESULT_SECTIONS: Mapping[str, tuple[str, ...]] = {
    "run": ("request", "experiment", "cases", "measurement_requests", "simulation", "timecourse_comparison"),
    "assemble": ("request", "proteome", "draft"),
    "check-data": ("directory", "base_registry", "valid", "errors", "dataset", "gaps"),
    "fit": ("request", "fit", "fitted_dataset", "next_steps"),
}

_STATISTICS = (("median", "p50"), ("p05", "p05"), ("p95", "p95"), ("mean", "mean"), ("min", "min"), ("max", "max"))


class SummaryContractError(ValueError):
    """A summary value breaks the format: a null without a reason, a non-finite number or a non-JSON value."""


@dataclass(frozen=True)
class Unknown:
    """A value the summary writes as ``null``, with the reason written to ``null_reasons``."""

    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise SummaryContractError("A null of the summary needs a stated reason.")


def known(value: Any, reason: str) -> Any:
    """``value``, or an :class:`Unknown` with ``reason`` when it is ``None``."""

    return Unknown(reason) if value is None else value


def new_result(command: str) -> dict[str, Any]:
    """The result object of ``command`` before the command runs: every section not reached."""

    return {section: Unknown(NOT_REACHED) for section in RESULT_SECTIONS[command]}


def document(
    *,
    command: str,
    arguments: Sequence[str],
    version: str,
    exit_code: int,
    exit_meaning: str,
    error: Mapping[str, Any] | None,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """The summary document of one command (before :func:`render`)."""

    return {
        "kind": SUMMARY_KIND,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "fungmod_version": version,
        "command": command,
        "arguments": list(arguments),
        "exit_code": exit_code,
        "exit_meaning": exit_meaning,
        "error": Unknown(NO_ERROR) if error is None else dict(error),
        "result": dict(result),
    }


def render(summary: Mapping[str, Any]) -> str:
    """The JSON text of a summary document: nulls with reasons, finite numbers only, one trailing newline."""

    return json.dumps(finalize(summary), indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def finalize(value: Any, path: str = "$") -> Any:
    """Turn a summary value into JSON values, moving each :class:`Unknown` into its object's ``null_reasons``.

    Refuses a bare ``None`` (a null without a reason), a non-finite number and
    any value that is not a JSON value, naming its path.
    """

    if isinstance(value, Unknown):
        raise SummaryContractError(f"{path}: an unknown outside an object has no place for its reason.")
    if value is None:
        raise SummaryContractError(f"{path} is null without a stated reason.")
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        reasons: dict[str, str] = {}
        for key, item in value.items():
            name = str(key)
            if name == NULL_REASONS:
                raise SummaryContractError(f"{path}: {NULL_REASONS} is written by the summary itself.")
            if isinstance(item, Unknown):
                output[name] = None
                reasons[name] = item.reason
            else:
                output[name] = finalize(item, f"{path}.{name}")
        if reasons:
            output[NULL_REASONS] = reasons
        return output
    if isinstance(value, (list, tuple)):
        return [finalize(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        if not math.isfinite(number):
            raise SummaryContractError(f"{path} is not a finite number ({number!r}).")
        return number
    if isinstance(value, Path):
        return str(value)
    raise SummaryContractError(f"{path}: a {type(value).__name__} is not a JSON value.")


# ---------------------------------------------------------------------------
# Values


def _number(value: Any, reason: str) -> Any:
    """A finite number, or an unknown: ``reason`` when absent, the value quoted when not finite."""

    if value is None or value == "":
        return Unknown(reason)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return Unknown(f"{reason} (the source holds {value!r}, not a number)")
    if not math.isfinite(number):
        return Unknown(f"the source holds the non-finite value {value!r}")
    return number


def _text(value: Any, reason: str) -> Any:
    """A non-empty string, or an unknown with ``reason``."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return Unknown(reason)
    return str(value)


def issue_location(issue: Mapping[str, Any]) -> str:
    """``file:row:column`` of a user-data issue (``-`` for no row or no column), as the command line prints it."""

    row = "-" if issue["row"] is None else str(issue["row"])
    column = issue["column"] if issue["column"] else "-"
    return f"{issue['file']}:{row}:{column}"


def data_issues(issues: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """User-data issues with file, spreadsheet line (header = line 1), column, message and printed location."""

    return [
        {
            "file": issue["file"],
            "line": known(issue["row"], "a file-level issue: it names no line"),
            "column": _text(issue["column"], "the issue names no column"),
            "message": issue["message"],
            "location": issue_location(issue),
        }
        for issue in issues
    ]


def error(message: str, details: Sequence[str]) -> dict[str, Any]:
    """The ``error`` object: the printed error message and its detail lines."""

    return {"message": message, "details": list(details)}


# ---------------------------------------------------------------------------
# run


def run_request(
    *,
    mode: str,
    samples: int | None,
    seed: int | None,
    runnable_only: bool,
    html_report: bool,
    figures: bool,
    compare_timecourses: bool,
    output: Path,
) -> dict[str, Any]:
    """What ``run`` was asked to do, once its options are checked."""

    exploratory = mode == "exploratory"
    return {
        "mode": mode,
        "samples_per_case": samples if exploratory else 1,
        "seed": seed if exploratory else Unknown("scientific mode runs each case once with exact values; no seed applies"),
        "runnable_only": runnable_only,
        "html_report": html_report,
        "quicklook_figures": figures,
        "compare_timecourses": compare_timecourses,
        "output_directory": str(output),
    }


def experiment(study: VirtualExperiment) -> dict[str, Any]:
    """The registry, user dataset, resolved names and grid of a virtual experiment, as ``run`` prints them."""

    registry = study.registry
    user_dataset: Any
    if study.user_dataset_id is None:
        user_dataset = Unknown("no --user-data was given")
    else:
        user_dataset = {"dataset_id": study.user_dataset_id, "digest": study.user_dataset_digest}
    return {
        "registry": {
            "path": str(study.registry_source),
            "registry_id": registry.registry_id,
            "version": str(registry.version),
            "maturity": registry.maturity,
        },
        "user_dataset": user_dataset,
        "resolved_names": [
            {
                "record_type": item.record_type,
                "query": item.query,
                "record_id": item.record_id,
                "name": item.record.name,
            }
            for item in study.resolved_records
        ],
        "environment_grid_cases": [
            {
                "environment_id": case.environment_id,
                "temperature": _number(case.temperature, "the grid case states no temperature"),
                "temperature_units": case.temperature_units,
                "ph": _number(case.ph, "the grid case states no pH"),
                "oxygen": case.oxygen,
            }
            for case in study.environment_cases
        ],
        "fungus_count": len(study.fungus_ids),
        "substrate_count": len(study.substrate_ids),
        "environment_count": len(study.environment_ids),
        "case_count": study.case_count,
    }


def measurement_requests(blocked: Sequence[ModelabilityReport]) -> list[str]:
    """The measurement requests of the blocked cases, each once, in the order ``run`` prints them."""

    return list(dict.fromkeys(request for report in blocked for request in report.suggested_experiments))


def run_cases(
    reports: Sequence[ModelabilityReport],
    *,
    result: DegradationScreenResult | None = None,
    refused: str | None = None,
    failed: str | None = None,
) -> list[dict[str, Any]]:
    """Every requested case with its preflight, its status (ran, blocked, refused, failed) and its results.

    With ``result`` the runnable cases ran and their samples, metrics and
    threshold times are read from the bundle's tables; otherwise the runnable
    cases were ``refused`` or ``failed`` with the reason given.
    """

    rows: dict[str, Mapping[str, str]] = {}
    final_metrics: Sequence[Mapping[str, str]] = ()
    threshold_times: Sequence[Mapping[str, str]] = ()
    summaries: Sequence[Mapping[str, str]] = ()
    if result is not None:
        rows = {row["case_id"]: row for row in result.case_summary()}
        final_metrics = result.final_metrics()
        threshold_times = result.threshold_times()
        summaries = result.summary_metrics()
    cases = []
    for index, report in enumerate(reports):
        case_id = standard_case_id(index)
        policy = preflight_policy(report)
        runnable = bool(policy["simulation_allowed_for_mode"])
        row = rows.get(case_id)
        case: dict[str, Any] = {
            "case_id": case_id,
            "number": index + 1,
            "fungus_id": report.fungus_id,
            "substrate_id": report.substrate_id,
            "environment_id": report.environment_id,
            "preflight": {
                "mode": report.mode,
                "status": report.status,
                "runnable": runnable,
                "blocking_reason": policy["blocking_reason"],
                "recommended_next_action": policy["recommended_next_action"],
                "uncertain_inputs": [item.item_id for item in report.uncertain],
                "missing_inputs": [item.item_id for item in report.missing],
                "incompatible_inputs": [item.item_id for item in report.incompatible],
                "measurement_requests": list(report.suggested_experiments),
            },
        }
        if runnable and result is not None and row is not None:
            selected = [item for item in summaries if item["case_id"] == case_id]
            case.update(
                status=CASE_RAN,
                reason=Unknown("the case ran"),
                samples={"simulated": int(row["sample_count"]), "failed": int(row["sample_failure_count"])},
                environment_effect={
                    "status": row["environment_effect_status"],
                    "response_model": row["environment_response_model"],
                    "guardrail": row["environment_guardrail"],
                },
                final_metrics=_metrics([item for item in final_metrics if item["case_id"] == case_id], selected),
                threshold_times=_metrics([item for item in threshold_times if item["case_id"] == case_id], selected),
            )
            cases.append(case)
            continue
        if not runnable:
            if row is not None and row["case_status"] == CASE_STATUS_NOT_SIMULATED:
                reason = row["not_simulated_reason"]
            else:
                reason = (
                    f"blocked_by_preflight: the {report.mode}-mode preflight reports {report.status} (blocking "
                    f"reason {policy['blocking_reason']}; next action {policy['recommended_next_action']})"
                )
            case.update(status=CASE_BLOCKED, reason=reason)
        elif failed is not None:
            case.update(status=CASE_FAILED, reason=failed)
        elif refused is not None:
            case.update(status=CASE_REFUSED, reason=refused)
        else:
            raise SummaryContractError(f"{case_id} is runnable, but the run summary states neither result nor reason.")
        absent = Unknown(f"the case was not simulated ({case['status']}), so it has no samples or results")
        case.update(samples=absent, environment_effect=absent, final_metrics=absent, threshold_times=absent)
        cases.append(case)
    return cases


def _metrics(rows: Sequence[Mapping[str, str]], summaries: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    """One entry per metric: units, sample counts, the summary statistics and the samples not computed."""

    by_metric: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        by_metric.setdefault(row["metric"], []).append(row)
    entries = []
    for metric, metric_rows in by_metric.items():
        matching = [item for item in summaries if item["metric"] == metric]
        statuses = Counter(row["status"] for row in metric_rows if row["status"] != "computed")
        not_computed = [
            {
                "status": status,
                "samples": count,
                "notes": sorted({row["notes"] for row in metric_rows if row["status"] == status and row["notes"]}),
            }
            for status, count in statuses.items()
        ]
        units = sorted({row["units"] for row in metric_rows})
        entry: dict[str, Any] = {
            "metric": metric,
            "units": units[0] if len(units) == 1 else Unknown(f"the samples of this metric state units {units}"),
            "samples": len(metric_rows),
        }
        if len(matching) == 1:
            summary = matching[0]
            entry["computed_samples"] = int(summary["count"])
            for name, column in _STATISTICS:
                entry[name] = _number(summary[column], f"summary_metrics.csv states no {column}")
            if summary["units"] != entry["units"]:
                entry["units"] = Unknown(
                    f"summary_metrics.csv states units {summary['units']!r} and the samples {units}"
                )
        else:
            if matching:
                reason = f"summary_metrics.csv holds {len(matching)} rows for this metric of one case"
                entry["computed_samples"] = Unknown(reason)
            else:
                entry["computed_samples"] = 0
                texts = [
                    f"{item['status']} in {item['samples']} of {len(metric_rows)} samples"
                    + (f" ({'; '.join(item['notes'])})" if item["notes"] else "")
                    for item in not_computed
                ]
                reason = (
                    f"no sample computed this metric: {'; '.join(texts)}"
                    if texts
                    else "summary_metrics.csv holds no row for this metric"
                )
            for name, _ in _STATISTICS:
                entry[name] = Unknown(reason)
        entry["not_computed"] = not_computed
        entries.append(entry)
    return entries


def simulation(result: DegradationScreenResult, *, report_path: Path, html_report: bool) -> dict[str, Any]:
    """The output bundle of a run: label, scope, directory, files, and the limitation, provenance and request counts."""

    root = Path(result.output_directory)
    manifest_path = root / "output_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tables: Mapping[str, str] = manifest["tables"]
    limitations = result.limitations()
    severities = Counter(row["severity"] for row in limitations)
    no_html = Unknown("--report was not given: only the Markdown report was written")
    return {
        "run_label": manifest["run_label"],
        "scientific_mode_note": _text(manifest["scientific_mode_note"], "the note is written in scientific mode only"),
        "samples_per_case": result.n_samples,
        "seed": known(result.seed, "scientific mode runs each case once with exact values; no seed applies"),
        "partial_run": manifest["partial_run"],
        "requested_case_count": manifest["requested_case_count"],
        "simulated_case_count": manifest["simulated_case_count"],
        "output_directory": str(root),
        "manifest": str(manifest_path),
        "report": str(report_path),
        "html_report": str(report_path.parent / "virtual_experiment_report.html") if html_report else no_html,
        "report_index": str(report_path.parent / "index.html") if html_report else no_html,
        "tables": dict(sorted(tables.items())),
        "figures": list(manifest["quicklook_paths"]),
        # The manifest lists every file of the directory; the per-sample bundles make that list long.
        "file_count": len(manifest["files"]),
        "limitations": {
            "count": len(limitations),
            "by_severity": dict(sorted(severities.items())),
            "table": tables["limitations_table"],
        },
        "provenance": {"rows": len(result.provenance()), "table": tables["provenance_table"]},
        "suggested_experiments": {
            "rows": len(result.suggested_experiments()),
            "table": tables["suggested_experiments"],
        },
    }


def timecourse_comparison(comparison: TimecourseComparison) -> dict[str, Any]:
    """The comparison of ``run --compare-timecourses``: per series RMSE and mean residual in the series' units."""

    used = Counter((row["case_id"], row["observable"]) for row in comparison.rows if row["used_in_fit"])
    return {
        "dataset_id": comparison.dataset_id,
        "dataset_digest": comparison.dataset_digest,
        "table": known(comparison.path, "the comparison table was not written"),
        "series": [
            {
                "case_id": series["case_id"],
                "timecourse_case_id": series["timecourse_case_id"],
                "series_id": series["series_id"],
                "observable": series["observable"],
                "simulated_state": series["simulated_state"],
                "n_observations": series["n_observations"],
                "n_with_sd": series["n_with_sd"],
                "rmse": _number(series["rmse"], "the comparison states no RMSE"),
                "mean_residual": _number(series["mean_residual"], "the comparison states no mean residual"),
                "units": series["units"],
                "time_units": series["time_units"],
                "fraction_inside_band": _number(
                    series["fraction_inside_band"], "the comparison states no fraction inside the band"
                ),
                "used_in_fit": used[(series["case_id"], series["observable"])],
            }
            for series in comparison.series
        ],
        "not_compared": [{"series_id": item["series_id"], "reason": item["reason"]} for item in comparison.not_compared],
        "note": comparison.note,
        "interpolation": comparison.interpolation,
    }


# ---------------------------------------------------------------------------
# check-data


def registry_identity(path: Path, registry_id: str) -> dict[str, Any]:
    return {"path": str(path), "registry_id": registry_id}


def check_data_refused(issues: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The ``check-data`` sections of a dataset that does not load: every issue with file, line and column."""

    return {
        "valid": False,
        "errors": data_issues(issues),
        "dataset": Unknown("the dataset did not load: see errors"),
        "gaps": Unknown("the dataset did not load, so its gaps are not known"),
    }


def check_data_loaded(loaded: UserDataset) -> dict[str, Any]:
    """The ``check-data`` sections of a loaded dataset: what it holds, and its gaps with their measurement requests."""

    simulation_grid = loaded.manifest["simulation"]
    parameter_records = loaded.records["parameter_records"]
    gaps = [mapping for mapping in parameter_records if mapping["maturity"] == USER_DATASET_MATURITY_GAP]
    series = [item for items in loaded.timecourses.values() for item in items]
    fit_block = loaded.manifest.get("fit")
    fitted: Any
    if isinstance(fit_block, Mapping):
        fitted = {
            "input_dataset_id": fit_block["input_dataset_id"],
            "input_dataset_digest": fit_block["input_dataset_digest"],
            "error_model": fit_block["error_model"],
            "conditions": list(fit_block["conditions"]),
            "quantities": [
                _fitted_quantity(item, None, level_reason="the fit block states no confidence level; fit_report.json holds it")
                for item in fit_block["quantities"]
            ],
            "claim_boundary": fit_block["claim_boundary"],
        }
    else:
        fitted = Unknown("the dataset holds no fit block (it was not written by fungmod fit)")
    summary = {
        "dataset_id": loaded.dataset_id,
        "digest": loaded.digest,
        "directory": str(loaded.source_directory),
        "time_grid": {
            "duration": simulation_grid["duration"],
            "units": simulation_grid["units"],
            "points": simulation_grid["points"],
        },
        "record_counts": {record_type: len(mappings) for record_type, mappings in loaded.records.items()},
        "kinetic_values": len(parameter_records) - len(gaps),
        "gap_count": len(gaps),
        "genome_annotations": len(loaded.genome_annotations),
        "genome_resolved_classes": len(loaded.genome_resolved_classes),
        "cultures": len(loaded.cultures),
        "enzyme_networks": len(loaded.enzyme_networks),
        "timecourses": {"series": len(series), "cases": len(loaded.timecourses)},
        "fitted_values": fitted,
    }
    return {
        "valid": True,
        "errors": [],
        "dataset": summary,
        "gaps": [
            {"record_id": gap["record_id"], "measurement_request": gap["provenance"]["measurement_request"]}
            for gap in gaps
        ],
    }


# ---------------------------------------------------------------------------
# fit


def fit_request(
    *,
    directory: Path,
    case: Sequence[str],
    bounds: Mapping[str, tuple[float, float, str]],
    initial: Mapping[str, float] | None,
    output: Path,
) -> dict[str, Any]:
    """The fitted case, each quantity's bounds and start as given, and the output directory."""

    strain_id, enzyme_class, substrate_id = case
    starts = initial or {}
    return {
        "directory": str(directory),
        "case": {"strain_id": strain_id, "enzyme_class": enzyme_class, "substrate_id": substrate_id},
        "quantities": [
            {
                "quantity": quantity,
                "lower": lower,
                "upper": upper,
                "units": units,
                "initial": known(starts.get(quantity), "no --initial: the dataset's exact value is the start"),
            }
            for quantity, (lower, upper, units) in bounds.items()
        ],
        "output_directory": str(output),
    }


def fit_report(report: Mapping[str, Any] | None) -> Any:
    """What a fit found: case, observations, error model, convergence, quantities and residuals per series.

    ``report`` is the fit report (``fit_report.json``), or the part of it a
    refused fit carries; what the fit did not reach is ``null`` with the reason.
    """

    if report is None or report.get("kind") != FIT_REPORT_KIND:
        return Unknown("the fit was refused before it ran, so there is no fit report (see error)")

    stopped = "not in the fit report: the fit stopped before this step"
    convergence = report.get("convergence") or {}
    settings = report.get("settings") or {}
    level = settings.get("confidence_level")
    quantities: Any = Unknown(stopped)
    if "quantities" in report:
        quantities = [
            _fitted_quantity(item, level, level_reason="the fit report states no confidence level")
            for item in report["quantities"]
        ]
    residuals: Any = Unknown(stopped)
    if "residuals" in report:
        residuals = [
            {
                "series_id": item["series_id"],
                "condition_id": item["condition_id"],
                "observable": item["observable"],
                "n_observations": len(item["points"]),
                "rmse": _number(item["rmse"], "the fit report states no RMSE"),
                "units": item["units"],
                "time_units": item["time_units"],
            }
            for item in report["residuals"]
        ]
    return {
        "input_dataset_id": report["input_dataset_id"],
        "input_dataset_digest": report["input_dataset_digest"],
        "case": dict(report["case"]),
        "conditions": list(report["conditions"]),
        "error_model": report["error_model"],
        "objective": report["objective"],
        "confidence_level": _number(level, "the fit report states no confidence level"),
        "n_observations": report["n_observations"],
        "n_parameters": report["n_parameters"],
        "residual_degrees_of_freedom": report["residual_degrees_of_freedom"],
        "timecourse_file": report["timecourse_file"],
        "timecourse_rows": list(report["timecourse_rows"]),
        "converged": known(convergence.get("success"), "the fit report states no convergence"),
        "optimizer_message": _text(convergence.get("message"), "the fit report states no optimizer message"),
        "identified": known(report.get("identified"), stopped),
        "quantities": quantities,
        "residuals": residuals,
        "warnings": list(report.get("warnings", [])),
        "claim_boundary": report["claim_boundary"],
    }


def _fitted_quantity(item: Mapping[str, Any], level: Any, *, level_reason: str) -> dict[str, Any]:
    """One fitted quantity with value, units, interval, verdict, bounds and start (from a report or a fit block)."""

    interval = item.get("interval")
    units = item["units"]
    if interval is None:
        why = "; ".join(part for part in (item["identifiability"], item.get("reason")) if part)
        interval_value: Any = Unknown(f"no interval was computed: {why}")
    else:
        interval_value = {
            "lower": _number(interval[0], "the interval states no lower end"),
            "upper": _number(interval[1], "the interval states no upper end"),
            "units": units,
            "confidence_level": _number(level, level_reason),
        }
    entry: dict[str, Any] = {
        "quantity": item["quantity"],
        "value": _number(item["value"], "the fit states no value"),
        "units": units,
        "interval": interval_value,
        "identifiability": item["identifiability"],
        "identifiability_method": _text(item.get("identifiability_method"), "the fit states no method"),
        "reason": _text(item.get("reason"), "the fit block states no reason; fit_report.json holds it"),
    }
    if "bounds" in item:
        entry["bounds"] = {"lower": item["bounds"][0], "upper": item["bounds"][1], "units": units}
    if "initial" in item:
        entry["initial"] = {
            "value": _number(item["initial"], "the fit states no starting value"),
            "units": units,
            "source": _text(item.get("initial_source"), "the fit block states no source; fit_report.json holds it"),
        }
    return entry


def fitted_dataset(fitted: UserDataset, *, report_path: Path) -> dict[str, Any]:
    return {
        "dataset_id": fitted.dataset_id,
        "digest": fitted.digest,
        "directory": str(fitted.source_directory),
        "fit_report": str(report_path),
    }


# ---------------------------------------------------------------------------
# assemble


def proteome(
    snapshot: UniprotSnapshot,
    resolution: ProteomeNameResolution | None,
    *,
    proteome_id: str | None,
    snapshot_dir: Path,
    fetched: bool,
    name_from: str,
) -> dict[str, Any]:
    """The UniProt proteome of ``assemble``: how it was chosen, its candidates and its frozen snapshots."""

    by_identifier = "--proteome names the proteome; no name was searched"
    chosen = resolution.proteome_id if resolution is not None else proteome_id
    metadata = snapshot.metadata
    return {
        "proteome_id": known(chosen, "the proteome identifier is not stated"),
        "chosen_by": "--fetch-proteome" if resolution is not None else "--proteome",
        "name_searched": Unknown(by_identifier) if resolution is None else resolution.name,
        "name_from": Unknown(by_identifier) if resolution is None else name_from,
        "match_rule": Unknown(by_identifier) if resolution is None else resolution.match_rule,
        "candidates": Unknown(by_identifier)
        if resolution is None
        else [
            {
                "proteome_id": item.proteome_id,
                "organism": item.organism,
                "taxonomy_id": _text(item.organism_id, "the search response states no taxonomy id"),
                "proteome_type": item.proteome_type,
                "protein_count": known(item.protein_count, "the search response states no protein count"),
                "chosen": item.proteome_id == resolution.proteome_id,
            }
            for item in resolution.candidates
        ],
        "network_used": fetched,
        "snapshot_directory": str(snapshot_dir),
        "search_snapshot": Unknown(by_identifier) if resolution is None else str(resolution.search.directory),
        "export_snapshot": str(snapshot.directory),
        "export_query": snapshot.query,
        "organism": _text(metadata.get("organism"), "the export snapshot names no organism"),
        "entry_rows": known(metadata.get("entry_rows"), "the export snapshot states no entry count"),
        "sha256": snapshot.sha256,
        "retrieved_at": snapshot.retrieved_at,
        "uniprot_release": known(
            snapshot.uniprot_release, "UniProt sent no release header; the retrieval date stands for the version"
        ),
    }


def assembly(
    draft: AssembledTablesDraft,
    *,
    written: Mapping[str, Path],
    output: Path,
    kinetics_dir: Path,
    fetched: bool,
    proteome_snapshots: Sequence[str],
    next_steps: Mapping[str, Any],
) -> dict[str, Any]:
    """The draft of ``assemble``: classes found and acting, per-case kinetics status, REVIEW: fields, files."""

    report = draft.assembly
    fungus = report["fungus"]
    cases = report["cases"]
    statuses = Counter(case["kinetics_status"] for case in cases)
    lookup: Any = Unknown("--fetch-kinetics was not given")
    kinetics_snapshots: list[str] = []
    if "kinetics_lookup" in report:
        lookup = _kinetics_lookup(report["kinetics_lookup"], kinetics_dir=kinetics_dir, fetched=fetched)
        kinetics_snapshots = [str(kinetics_dir / item["snapshot"]) for item in report["kinetics_lookup"]["queries"]]
    network: Any = Unknown("--network was not given")
    if "network" in report:
        network = _network(report["network"])
    return {
        "dataset_id": draft.dataset_id,
        "directory": str(output),
        "fungus": {
            "input": fungus["input"],
            "name": fungus["name"],
            "strain_id": fungus["strain_id"],
            "resolved_as": fungus["resolved_as"],
            "registry_fungus_id": known(
                fungus["registry_fungus_id"], f"the fungus is not a registry record (resolved as {fungus['resolved_as']})"
            ),
        },
        "substrates": [
            {
                "input": _text(item.get("input"), "not a requested name"),
                "substrate_id": item["substrate_id"],
                "name": item["name"],
                "resolved_as": item["resolved_as"],
                "registry_substrate": _text(item.get("registry_substrate"), "not a registry substrate"),
                "network_role": _text(item.get("network_role"), "--network was not given"),
            }
            for item in report["substrates"]
        ],
        "conditions": [
            {
                "condition_id": item["condition_id"],
                "temperature": _number(item["temperature"], "the condition states no temperature"),
                "temperature_units": item["temperature_units"],
                "ph": _number(item["ph"], "the condition states no pH"),
                "in_conditions_csv": item["in_conditions_csv"],
            }
            for item in report["requested_conditions"]
        ],
        "enzyme_classes": [
            {
                "enzyme_class": item["enzyme_class"],
                "declared_in": item["declared_in"],
                "evidence": [evidence["evidence"] for evidence in item["evidence"]],
            }
            for item in report["enzyme_classes"]
        ],
        "acting_classes": [
            {
                "substrate_id": item["substrate_id"],
                "substrate": item["substrate"],
                "acting": [entry["enzyme_class"] for entry in item["acting"]],
                "not_acting": [
                    {"enzyme_class": entry["enzyme_class"], "reason": entry["reason"]} for entry in item["not_acting"]
                ],
                "acting_without_evidence": [
                    {"enzyme_class": entry["enzyme_class"], "reason": entry["reason"]}
                    for entry in item["acting_without_evidence"]
                ],
                "undetermined": _text(item["undetermined"], "every class's action on this substrate is determined"),
            }
            for item in report["substrate_compatibility"]
        ],
        "unmodellable_enzyme_classes": [
            {"enzyme_class": item["enzyme_class"], "families": list(item["families"]), "reason": item["reason"]}
            for item in report["unmodellable_enzyme_classes"]
        ],
        "unmapped_families": [{"family": item["family"], "reason": item["reason"]} for item in report["unmapped_families"]],
        "cases": [
            {
                "number": index,
                "enzyme_class": case["enzyme_class"],
                "substrate_id": case["substrate_id"],
                "condition": case["condition"],
                "kinetics_status": case["kinetics_status"],
                "condition_route": case["condition_route"],
                "source_ids": list(case["source_ids"]),
                "reason": case["reason"],
            }
            for index, case in enumerate(cases, start=1)
        ],
        "kinetics_status_counts": {status: statuses.get(status, 0) for status in ASSEMBLY_STATUSES},
        "kinetics_lookup": lookup,
        "network": network,
        "transferred_entry_ids": list(report["transferred_entry_ids"]),
        "entries_considered": len(report["entries"]),
        "limitations": list(report["limitations"]),
        "written_files": {name: str(written[name]) for name in sorted(written)},
        "review_fields": [
            {
                "file": field["file"],
                "line": known(field["row"], "a field of user_dataset.yml: it has no line"),
                "column": _text(field["column"], "the field names no column"),
                "note": field["note"],
                "location": issue_location(field),
            }
            for field in draft.review_fields
        ],
        "snapshots": {"proteome": list(proteome_snapshots), "kinetics": kinetics_snapshots},
        "next_steps": dict(next_steps),
    }


def _kinetics_lookup(lookup: Mapping[str, Any], *, kinetics_dir: Path, fetched: bool) -> dict[str, Any]:
    return {
        "database": lookup["database"],
        "endpoint": lookup["endpoint"],
        "query_form": lookup["query_form"],
        "cache_directory": str(kinetics_dir),
        "network_used": bool(fetched and lookup["queries"]),
        "queries": [
            {
                "enzyme_class": item["enzyme_class"],
                "class_defined_in": _text(item.get("class_defined_in"), "a registry class"),
                "substrate_id": item["substrate_id"],
                "ec_number": item["ec_number"],
                "query": item["query"],
                # The lookup report states the snapshot relative to the cache directory.
                "snapshot": str(kinetics_dir / item["snapshot"]),
                "export": str(kinetics_dir / item["export"]),
                "retrieved_at": item["retrieved_at"],
                "http_status": item["http_status"],
                "raw_sha256": list(item["raw_sha256"]),
                "entries": item["entries"],
                "counts": dict(item["counts"]),
                "converted": [
                    {
                        "entry_id": entry["entry_id"],
                        "organism": _text(entry["organism"], "the entry names no organism"),
                        "cases": [dict(case) for case in entry["cases"]],
                    }
                    for entry in item["converted"]
                ],
                "not_converted": [
                    {
                        "entry_id": entry["entry_id"],
                        "organism": _text(entry["organism"], "the entry names no organism"),
                        "use": entry["use"],
                        "reason": entry["reason"],
                    }
                    for entry in item["not_converted"]
                ],
            }
            for item in lookup["queries"]
        ],
        "not_queried": [
            {
                "enzyme_class": _text(item["enzyme_class"], "no class: the substrate's acting classes are not decided"),
                "substrate_id": item["substrate_id"],
                "reason": item["reason"],
            }
            for item in lookup["not_queried"]
        ],
    }


def _network(network: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "manifest_field": network["manifest_field"],
        "entry_substrates": list(network["entry_substrates"]),
        "networks": [
            {
                "entry_substrate": item["entry_substrate"],
                "pools": list(item["pools"]),
                "members": [
                    {
                        "enzyme_class": member["enzyme_class"],
                        "pool": member["pool"],
                        "pool_role": member["pool_role"],
                        "kinetics_status": dict(member["kinetics_status"]),
                    }
                    for member in item["members"]
                ],
                "not_members": [
                    {"enzyme_class": member["enzyme_class"], "reasons": list(member["reasons"])}
                    for member in item["not_members"]
                ],
                "undetermined_pools": list(item["undetermined_pools"]),
                "conditions": [
                    {
                        "condition": entry["condition"],
                        "status": entry["status"],
                        "initial_concentration": str(entry["initial_concentration"]),
                        "blocked_by": list(entry["blocked_by"]),
                    }
                    for entry in item["conditions"]
                ],
            }
            for item in network["networks"]
        ],
        "status_meaning": dict(network["status_meaning"]),
    }


def next_command(command: str, complete_with: str | None = None, notes: Sequence[str] = ()) -> dict[str, Any]:
    """A printed next command; ``complete_with`` holds the options the printed line continues with."""

    return {
        "command": command,
        "complete_with": known(complete_with, "the command is complete as printed"),
        "notes": list(notes),
    }


__all__ = [
    "CASE_BLOCKED",
    "CASE_FAILED",
    "CASE_RAN",
    "CASE_REFUSED",
    "NOT_REACHED",
    "NULL_REASONS",
    "RESULT_SECTIONS",
    "RUN_CASE_STATUSES",
    "SUMMARY_KIND",
    "SUMMARY_SCHEMA_VERSION",
    "SummaryContractError",
    "Unknown",
    "finalize",
    "render",
]
