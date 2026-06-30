"""Report rendering for virtual-experiment standard outputs."""

from __future__ import annotations

import csv
import html
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


TABLE_FILENAMES = {
    "modelability_preflight": "modelability_preflight.csv",
    "case_summary": "case_summary.csv",
    "time_series_long": "time_series_long.csv",
    "final_metrics": "final_metrics.csv",
    "threshold_times": "threshold_times.csv",
    "summary_metrics": "summary_metrics.csv",
    "sampled_parameters": "sampled_parameters.csv",
    "mechanism_summary": "mechanism_summary.csv",
    "assumption_summary": "assumption_summary.csv",
    "comparison_summary": "comparison_summary.csv",
    "uncertainty_summary": "uncertainty_summary.csv",
    "trajectory_quantiles": "trajectory_quantiles.csv",
    "provenance_table": "provenance_table.csv",
    "limitations_table": "limitations_table.csv",
    "missing_parameters": "missing_parameters.csv",
    "suggested_experiments": "suggested_experiments.csv",
}

THERMODYNAMIC_FILENAMES = {
    "thermodynamic_summary_json": "thermodynamic_summary.json",
    "thermodynamic_summary_csv": "thermodynamic_summary.csv",
}


def write_virtual_experiment_report(
    *,
    table_dir: str | Path,
    output_dir: str | Path,
    quicklook_paths: Sequence[str] = (),
    include_html: bool = False,
    include_index: bool = False,
) -> Path:
    """Write a deterministic Markdown report from existing standard tables.

    When requested, also write an HTML sidecar derived from the Markdown report
    and a folder index derived from the same standard artifact paths.
    """

    table_root = Path(table_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "virtual_experiment_report.md"
    tables = {name: _read_rows(table_root / filename) for name, filename in TABLE_FILENAMES.items()}
    thermodynamic_summary = _read_json_mapping(table_root / THERMODYNAMIC_FILENAMES["thermodynamic_summary_json"])
    thermodynamic_rows = _read_rows(table_root / THERMODYNAMIC_FILENAMES["thermodynamic_summary_csv"])
    markdown = _render_report(
        tables=tables,
        quicklook_paths=quicklook_paths,
        thermodynamic_summary=thermodynamic_summary,
        thermodynamic_rows=thermodynamic_rows,
    )
    report_path.write_text(markdown, encoding="utf-8")
    if include_html:
        html_path = destination / "virtual_experiment_report.html"
        html_path.write_text(
            _render_html_report(
                markdown=markdown,
                table_root=table_root,
                output_dir=destination,
                quicklook_paths=quicklook_paths,
            ),
            encoding="utf-8",
        )
    if include_index:
        index_path = destination / "index.html"
        index_path.write_text(
            _render_report_folder_index(
                table_root=table_root,
                report_dir=destination,
                markdown_path=report_path,
                html_path=destination / "virtual_experiment_report.html" if include_html else None,
                quicklook_paths=quicklook_paths,
            ),
            encoding="utf-8",
        )
    return report_path


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        return {}
    return {str(key): value for key, value in data.items()}


def _render_report(
    *,
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    quicklook_paths: Sequence[str],
    thermodynamic_summary: Mapping[str, Any],
    thermodynamic_rows: Sequence[Mapping[str, str]],
) -> str:
    preflight = tables["modelability_preflight"]
    case_summary = tables["case_summary"]
    time_series = tables["time_series_long"]
    final_metrics = tables["final_metrics"]
    threshold_times = tables["threshold_times"]
    summary_metrics = tables["summary_metrics"]
    mechanisms = tables["mechanism_summary"]
    sampled_parameters = tables["sampled_parameters"]
    uncertainty_summary = tables["uncertainty_summary"]
    trajectory_quantiles = tables["trajectory_quantiles"]
    assumptions = tables["assumption_summary"]
    provenance = tables["provenance_table"]
    limitations = tables["limitations_table"]
    missing_parameters = tables["missing_parameters"]
    suggested_experiments = tables["suggested_experiments"]

    lines = [
        "# FungMod Virtual-Experiment Report",
        "",
        "This report is generated from existing FungMod standard output tables. "
        "It is a presentation artifact, not an additional validation, calibration, or empirical comparison.",
        "",
        "## Run summary",
        "",
        *_case_summary_lines(case_summary),
        "",
        "## Modelability and preflight status",
        "",
        *_preflight_lines(preflight),
        "",
        "## Final metrics",
        "",
        *_metric_lines(final_metrics),
        "",
        "## Degradation-rate inspection",
        "",
        *_degradation_rate_lines(time_series),
        "",
        "## Threshold times",
        "",
        *_threshold_lines(threshold_times, summary_metric_rows=summary_metrics),
        "",
        "## Explicit thermodynamic diagnostics",
        "",
        *_thermodynamic_summary_lines(thermodynamic_summary, thermodynamic_rows),
        "",
        "## Active mechanisms and modifiers",
        "",
        *_mechanism_lines(mechanisms),
        "",
        "## Parameter assumptions",
        "",
        *_sampled_parameter_lines(sampled_parameters),
        "",
        "## Uncertainty and range summary",
        "",
        *_uncertainty_summary_lines(uncertainty_summary),
        "",
        "## Trajectory quantile bands",
        "",
        *_trajectory_quantile_lines(trajectory_quantiles),
        "",
        "## Assumptions",
        "",
        *_message_lines(assumptions, preferred_fields=("message", "allowed_use")),
        "",
        "## Limitations",
        "",
        *_message_lines(limitations, preferred_fields=("limitation", "allowed_use")),
        "",
        "## Missing parameters",
        "",
        *_missing_parameter_lines(missing_parameters),
        "",
        "## Suggested follow-up experiments",
        "",
        *_message_lines(suggested_experiments, preferred_fields=("suggested_experiment", "reason")),
        "",
        "## Provenance",
        "",
        *_provenance_lines(provenance),
        "",
        "## Quicklook figures",
        "",
        *_quicklook_lines(quicklook_paths),
        "",
    ]
    return "\n".join(lines)


def _case_summary_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No case-summary rows were present in the standard tables."]
    lines = []
    for row in rows:
        case_id = _value(row, "case_id")
        fungus_id = _value(row, "fungus_id")
        substrate_id = _value(row, "substrate_id")
        environment_id = _value(row, "environment_id")
        status = _value(row, "modelability_status")
        lines.append(f"- `{case_id}`: `{fungus_id}` on `{substrate_id}` in `{environment_id}`; modelability `{status}`.")
    return lines


def _preflight_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No preflight rows were present in the standard tables."]
    lines = []
    for row in rows:
        allowed = _value(row, "simulation_allowed_for_mode")
        action = _value(row, "recommended_next_action")
        blocking = _value(row, "blocking_reason")
        mode = _value(row, "assessment_mode")
        status = _value(row, "status", fallback_field="modelability_status")
        lines.append(
            f"- `{_value(row, 'case_id')}` assessed in `{mode}` mode: `{status}`; "
            f"simulation allowed `{allowed}`; blocking reason `{blocking}`; recommended next action `{action}`."
        )
    return lines


def _metric_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    computed = [row for row in rows if _value(row, "status") in {"computed", ""}]
    if not computed:
        return ["No computed final metrics were present in the standard tables."]
    return [
        f"- `{_value(row, 'case_id')}` sample `{_value(row, 'sample_id')}` `{_value(row, 'metric')}` = "
        f"{_value(row, 'value')} {_value(row, 'units')}".rstrip()
        for row in computed[:12]
    ]


def _degradation_rate_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    rate_rows = [
        row
        for row in rows
        if _value(row, "state") == "degradation_rate"
        and _value(row, "source") == "simulation_process_rate"
        and _optional_float(_value(row, "value")) is not None
    ]
    if not rate_rows:
        return ["No degradation-rate rows were present in `time_series_long.csv`."]

    lines = [
        "These rows are an inspection summary over existing `time_series_long.csv` "
        "`degradation_rate` rows only. They are not validation, calibration, empirical comparison, "
        "or a new rate law."
    ]
    grouped: dict[tuple[str, str, str, str], list[tuple[float, float]]] = {}
    for row in rate_rows:
        time = _optional_float(_value(row, "time"))
        value = _optional_float(_value(row, "value"))
        if time is None or value is None:
            continue
        key = (
            _value(row, "case_id"),
            _value(row, "sample_id"),
            _value(row, "units"),
            _value(row, "time_units"),
        )
        grouped.setdefault(key, []).append((time, value))

    for (case_id, sample_id, units, time_units), values in sorted(grouped.items())[:12]:
        ordered = sorted(values)
        rate_values = [value for _time, value in ordered]
        time_values = [time for time, _value in ordered]
        lines.append(
            f"- `{case_id}` sample `{sample_id}`: {len(values)} existing rate rows; "
            f"time range {min(time_values)}..{max(time_values)} {_display_units(time_units)}; "
            f"maximum observed rate {max(rate_values)} {_display_units(units)}."
        )
    return lines


def _threshold_lines(
    rows: Sequence[Mapping[str, str]],
    *,
    summary_metric_rows: Sequence[Mapping[str, str]],
) -> list[str]:
    if not rows:
        return ["No threshold-time rows were present in the standard tables."]
    lines = [
        "These rows inspect existing `threshold_times.csv` and `summary_metrics.csv` values only. "
        "They are simulated threshold times, not validation data, calibration results, empirical comparisons, "
        "or observed degradation endpoints."
    ]
    for row in rows[:12]:
        value = _value(row, "value")
        units = _value(row, "units")
        timing = f" at {value} {units}".rstrip() if value else ""
        notes = _value(row, "notes")
        suffix = f" {notes}" if notes else ""
        lines.append(
            f"- `{_value(row, 'case_id')}` sample `{_value(row, 'sample_id')}` threshold "
            f"{_value(row, 'threshold_fraction')} (`{_value(row, 'metric')}`): "
            f"`{_value(row, 'status')}`{timing}.{suffix}"
        )
    threshold_summaries = [
        row
        for row in summary_metric_rows
        if _value(row, "metric").startswith("time_to_")
        and _value(row, "metric").endswith("_percent_substrate_degradation")
    ]
    if threshold_summaries:
        lines.append("Summary rows from `summary_metrics.csv`:")
    else:
        lines.append("No computed threshold summary rows were present in `summary_metrics.csv`.")
    for row in threshold_summaries[:12]:
        lines.append(
            f"- `{_value(row, 'case_id')}` `{_value(row, 'metric')}`: "
            f"count={_value(row, 'count')}; p05={_value(row, 'p05')} "
            f"p50={_value(row, 'p50')} p95={_value(row, 'p95')} {_value(row, 'units')}".rstrip()
        )
    return lines


def _thermodynamic_summary_lines(
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, str]],
) -> list[str]:
    if not summary and not rows:
        return ["No configured thermodynamic-summary artifacts were present."]

    lines = [
        "These diagnostics inspect existing configured-output `thermodynamic_summary.json` "
        "and `thermodynamic_summary.csv` artifacts only. They do not infer activities, "
        "reaction quotients, concentrations, redox potentials, electron balances, validation evidence, "
        "or solver-time thermodynamic enforcement."
    ]
    if summary:
        lines.append(
            "- Summary: "
            f"count={_summary_value(summary, 'count')}; "
            f"status_counts={_format_counts(summary.get('status_counts'))}; "
            f"severity_counts={_format_counts(summary.get('severity_counts'))}; "
            f"explicit reaction-quotient Gibbs rows `{_summary_value(summary, 'has_reaction_quotient_gibbs')}`; "
            f"entropy-production-rate rows `{_summary_value(summary, 'has_entropy_production_rate')}`; "
            f"solver-time enforcement `{_summary_value(summary, 'has_solver_time_enforcement')}`."
        )
        if "has_entropy_budget" in summary:
            entropy_budget_parts = [
                f"available `{_summary_value(summary, 'has_entropy_budget')}`",
                f"status `{_summary_value(summary, 'entropy_budget_status')}`",
                f"evaluated rows={_summary_value(summary, 'entropy_budget_evaluated_count')}",
                f"negative rows={_summary_value(summary, 'entropy_budget_negative_count')}",
            ]
            if summary.get("has_entropy_budget") is True:
                units = _summary_value(summary, "entropy_budget_units")
                entropy_budget_parts.extend(
                    [
                        f"total={_summary_value(summary, 'entropy_budget_total')} {units}".rstrip(),
                        f"minimum={_summary_value(summary, 'entropy_budget_minimum')} {units}".rstrip(),
                    ]
                )
            lines.append("- Entropy budget: " + "; ".join(entropy_budget_parts) + ".")
        for field, label in (
            ("supported_scope", "Supported scope"),
            ("unsupported_scope", "Unsupported scope"),
            ("entropy_budget_limitations", "Entropy-budget limitations"),
        ):
            value = _summary_value(summary, field)
            if value:
                lines.append(f"- {label}: {value}")

    if rows:
        lines.append("Row-level diagnostics from `thermodynamic_summary.csv`:")
    else:
        lines.append("No row-level `thermodynamic_summary.csv` diagnostics were present.")
    for row in rows[:12]:
        details = _thermodynamic_row_details(row)
        suffix = f"; {details}" if details else ""
        message = _value(row, "message")
        message_suffix = f"; {message}" if message else ""
        lines.append(
            f"- `{_value(row, 'name')}`: status `{_value(row, 'status')}`; "
            f"passed `{_value(row, 'passed')}`; severity `{_value(row, 'severity')}`"
            f"{suffix}{message_suffix}."
        )
    return lines


def _thermodynamic_row_details(row: Mapping[str, str]) -> str:
    details = []
    residual_value = _value(row, "residual_value")
    residual_units = _value(row, "residual_units")
    if residual_value:
        details.append(f"residual={residual_value} {_display_units(residual_units)}")
    delta_gibbs = _value(row, "delta_gibbs")
    if delta_gibbs:
        details.append(f"delta_gibbs={delta_gibbs} {_display_units(_value(row, 'delta_gibbs_units'))}")
    entropy_rate = _value(row, "entropy_production_rate")
    if entropy_rate:
        details.append(
            f"entropy_production_rate={entropy_rate} "
            f"{_display_units(_value(row, 'entropy_production_rate_units'))}"
        )
    equation = _value(row, "gibbs_equation") or _value(row, "entropy_equation")
    if equation:
        details.append(f"equation `{equation}`")
    solver_time = _value(row, "solver_time_enforcement")
    if solver_time:
        details.append(f"solver_time_enforcement `{solver_time}`")
    return "; ".join(details)


def _mechanism_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    active = [row for row in rows if _value(row, "active") != "false"]
    if not active:
        return ["No active mechanism-summary rows were present in the standard tables."]
    return [
        f"- `{_value(row, 'mechanism_id')}` (`{_value(row, 'mechanism_kind')}`): "
        f"{_value(row, 'mechanism_family')}; maturity `{_value(row, 'maturity')}`; "
        f"limitations: {_value(row, 'limitations')}"
        for row in active[:12]
    ]


def _message_lines(rows: Sequence[Mapping[str, str]], *, preferred_fields: tuple[str, ...]) -> list[str]:
    if not rows:
        return ["None recorded in the standard table."]
    lines = []
    for row in rows[:12]:
        fields = [_value(row, field) for field in preferred_fields]
        message = "; ".join(field for field in fields if field)
        lines.append(f"- {message}" if message else f"- {_compact_row(row)}")
    return lines


def _sampled_parameter_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No sampled-parameter rows were present in the standard tables."]
    lines = []
    for row in rows[:12]:
        value = _value(row, "sampled_value")
        units = _value(row, "units")
        source_class = _value(row, "parameter_source_class")
        allowed_use = _value(row, "allowed_use")
        lines.append(
            f"- `{_value(row, 'symbol')}` = {value} {units}; "
            f"source class `{source_class}`; allowed use `{allowed_use}`."
        )
    return lines


def _uncertainty_summary_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No uncertainty-summary rows were present in the standard tables."]
    lines = [
        "These rows summarize existing sampled parameters and simulated sample outputs only. "
        "They are not empirical confidence intervals, calibration results, or validation evidence."
    ]
    for row in rows[:12]:
        lines.append(
            f"- `{_value(row, 'summary_type')}` `{_value(row, 'target_id')}`: "
            f"p05={_value(row, 'p05')} p50={_value(row, 'p50')} p95={_value(row, 'p95')} "
            f"{_value(row, 'units')}; status `{_value(row, 'uncertainty_band_status')}`; "
            f"allowed use `{_value(row, 'allowed_use')}`."
        )
    return lines


def _trajectory_quantile_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No trajectory-quantile rows were present in the standard tables."]
    lines = [
        "These rows summarize existing `time_series_long.csv` sample values only. "
        "They are not validation data, calibration results, empirical confidence intervals, or posterior uncertainty."
    ]
    for row in rows[:12]:
        lines.append(
            f"- `{_value(row, 'case_id')}` `{_value(row, 'state')}` at "
            f"{_value(row, 'time')} {_value(row, 'time_units')}: "
            f"p05={_value(row, 'p05')} p50={_value(row, 'p50')} p95={_value(row, 'p95')} "
            f"{_value(row, 'units')}; count={_value(row, 'count')}; "
            f"allowed use `{_value(row, 'allowed_use')}`."
        )
    return lines


def _missing_parameter_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["None recorded in the standard table."]
    return [
        f"- `{_value(row, 'parameter_symbol', fallback_field='item_id')}` expected units `{_value(row, 'expected_units')}`: "
        f"{_value(row, 'message')}"
        for row in rows[:12]
    ]


def _provenance_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No provenance rows were present in the standard tables."]
    return [
        f"- `{_value(row, 'record_type')}` `{_value(row, 'record_id')}`: "
        f"{_value(row, 'source') or _value(row, 'provenance') or _compact_row(row)}"
        for row in rows[:12]
    ]


def _quicklook_lines(paths: Sequence[str]) -> list[str]:
    if not paths:
        return ["No quicklook figure paths were recorded. Generate them with `write_quicklook_plots(...)` if needed."]
    return [f"- `{path}`" for path in paths]


def _render_html_report(
    *,
    markdown: str,
    table_root: Path,
    output_dir: Path,
    quicklook_paths: Sequence[str],
) -> str:
    body = _markdown_to_html_body(markdown)
    table_links = _table_link_items(table_root=table_root, output_dir=output_dir)
    thermodynamic_links = _thermodynamic_link_items(table_root=table_root, output_dir=output_dir)
    quicklook_links = _quicklook_link_items(quicklook_paths, output_dir=output_dir)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            "  <title>FungMod Virtual-Experiment Report</title>",
            "  <style>",
            "    body { font-family: system-ui, sans-serif; line-height: 1.5; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }",
            "    code { background: #f3f4f6; padding: 0.1rem 0.25rem; border-radius: 0.25rem; }",
            "    a { color: #075985; }",
            "    h1, h2 { line-height: 1.2; }",
            "  </style>",
            "</head>",
            "<body>",
            body,
            "<h2>Standard output tables</h2>",
            "<ul>",
            *table_links,
            "</ul>",
            "<h2>Configured thermodynamic diagnostics</h2>",
            "<ul>",
            *thermodynamic_links,
            "</ul>",
            "<h2>Quicklook figure files</h2>",
            "<ul>",
            *quicklook_links,
            "</ul>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _render_report_folder_index(
    *,
    table_root: Path,
    report_dir: Path,
    markdown_path: Path,
    html_path: Path | None,
    quicklook_paths: Sequence[str],
) -> str:
    report_links = _report_link_items(
        report_dir=report_dir,
        markdown_path=markdown_path,
        html_path=html_path,
    )
    manifest_links = _manifest_link_items(table_root=table_root, report_dir=report_dir)
    table_links = _table_link_items(table_root=table_root, output_dir=report_dir)
    thermodynamic_links = _thermodynamic_link_items(table_root=table_root, output_dir=report_dir)
    quicklook_links = _quicklook_link_items(quicklook_paths, output_dir=report_dir)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            "  <title>FungMod Virtual-Experiment Output Index</title>",
            "  <style>",
            "    body { font-family: system-ui, sans-serif; line-height: 1.5; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }",
            "    a { color: #075985; }",
            "    h1, h2 { line-height: 1.2; }",
            "  </style>",
            "</head>",
            "<body>",
            "<h1>FungMod Virtual-Experiment Output Index</h1>",
            "<p>This index links existing output artifacts only. It does not add validation, calibration, "
            "empirical comparison, or scientific interpretation.</p>",
            "<h2>Reports</h2>",
            "<ul>",
            *report_links,
            "</ul>",
            "<h2>Output manifest</h2>",
            "<ul>",
            *manifest_links,
            "</ul>",
            "<h2>Standard CSV tables</h2>",
            "<ul>",
            *table_links,
            "</ul>",
            "<h2>Configured thermodynamic diagnostics</h2>",
            "<ul>",
            *thermodynamic_links,
            "</ul>",
            "<h2>Quicklook figures</h2>",
            "<ul>",
            *quicklook_links,
            "</ul>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _markdown_to_html_body(markdown: str) -> str:
    html_lines: list[str] = []
    in_list = False
    for line in markdown.splitlines():
        if line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"  <li>{_html_inline(line[2:])}</li>")
            continue
        if in_list:
            html_lines.append("</ul>")
            in_list = False
        if line.startswith("# "):
            html_lines.append(f"<h1>{_html_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{_html_inline(line[3:])}</h2>")
        elif line:
            html_lines.append(f"<p>{_html_inline(line)}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def _html_inline(text: str) -> str:
    parts = re.split(r"(`[^`]*`)", text)
    rendered = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) >= 2:
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def _report_link_items(*, report_dir: Path, markdown_path: Path, html_path: Path | None) -> list[str]:
    links = [
        _link_item(
            path=markdown_path,
            base_dir=report_dir,
            label="virtual_experiment_report.md",
            description="Markdown report",
        )
    ]
    if html_path is not None and html_path.exists():
        links.append(
            _link_item(
                path=html_path,
                base_dir=report_dir,
                label="virtual_experiment_report.html",
                description="Optional HTML report sidecar",
            )
        )
    return links


def _manifest_link_items(*, table_root: Path, report_dir: Path) -> list[str]:
    manifest_path = table_root / "output_manifest.json"
    if not manifest_path.exists():
        return ["  <li>No output manifest was present.</li>"]
    return [
        _link_item(
            path=manifest_path,
            base_dir=report_dir,
            label="output_manifest.json",
            description="Output manifest",
        )
    ]


def _table_link_items(*, table_root: Path, output_dir: Path) -> list[str]:
    items = []
    for name, filename in TABLE_FILENAMES.items():
        table_path = table_root / filename
        if table_path.exists():
            items.append(_link_item(path=table_path, base_dir=output_dir, label=filename, description=name))
    if not items:
        return ["  <li>No standard CSV tables were present.</li>"]
    return items


def _thermodynamic_link_items(*, table_root: Path, output_dir: Path) -> list[str]:
    items = []
    for name, filename in THERMODYNAMIC_FILENAMES.items():
        path = table_root / filename
        if path.exists():
            items.append(
                _link_item(
                    path=path,
                    base_dir=output_dir,
                    label=filename,
                    description=name,
                )
            )
    if not items:
        return ["  <li>No configured thermodynamic-summary artifacts were present.</li>"]
    return items


def _quicklook_link_items(paths: Sequence[str], *, output_dir: Path) -> list[str]:
    if not paths:
        return ["  <li>No quicklook figure paths were recorded.</li>"]
    return [
        _link_item(path=Path(path), base_dir=output_dir, label=Path(path).name or path)
        for path in paths
    ]


def _link_item(*, path: Path, base_dir: Path, label: str, description: str = "") -> str:
    href = html.escape(_href_for(path=path, base_dir=base_dir), quote=True)
    rendered_label = html.escape(label)
    rendered_description = f" ({html.escape(description)})" if description else ""
    return f'  <li><a href="{href}">{rendered_label}</a>{rendered_description}</li>'


def _href_for(*, path: Path, base_dir: Path) -> str:
    target = path if path.is_absolute() else Path.cwd() / path
    base = base_dir if base_dir.is_absolute() else Path.cwd() / base_dir
    return Path(os.path.relpath(target, base)).as_posix()


def _value(row: Mapping[str, str], field: str, *, fallback_field: str | None = None) -> str:
    value = row.get(field, "")
    if value or fallback_field is None:
        return value
    return row.get(fallback_field, "")


def _optional_float(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _display_units(units: str) -> str:
    return units if units else "unitless"


def _summary_value(summary: Mapping[str, Any], field: str) -> str:
    value = summary.get(field)
    if value is None:
        return ""
    return str(value)


def _format_counts(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "{}"
    return "{" + ", ".join(f"{key}: {value[key]}" for key in sorted(value)) + "}"


def _compact_row(row: Mapping[str, str]) -> str:
    pairs = [f"{key}={value}" for key, value in row.items() if value]
    return "; ".join(pairs)


__all__ = ["write_virtual_experiment_report"]
