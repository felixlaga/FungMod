"""Report rendering for virtual-experiment standard outputs."""

from __future__ import annotations

import csv
import html
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path


TABLE_FILENAMES = {
    "modelability_preflight": "modelability_preflight.csv",
    "case_summary": "case_summary.csv",
    "time_series_long": "time_series_long.csv",
    "final_metrics": "final_metrics.csv",
    "threshold_times": "threshold_times.csv",
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
    markdown = _render_report(tables=tables, quicklook_paths=quicklook_paths)
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


def _render_report(
    *,
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    quicklook_paths: Sequence[str],
) -> str:
    preflight = tables["modelability_preflight"]
    case_summary = tables["case_summary"]
    time_series = tables["time_series_long"]
    final_metrics = tables["final_metrics"]
    threshold_times = tables["threshold_times"]
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
        *_threshold_lines(threshold_times),
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


def _threshold_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No threshold-time rows were present in the standard tables."]
    lines = []
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
    return lines


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


def _compact_row(row: Mapping[str, str]) -> str:
    pairs = [f"{key}={value}" for key, value in row.items() if value]
    return "; ".join(pairs)


__all__ = ["write_virtual_experiment_report"]
