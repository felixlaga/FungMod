"""Markdown report rendering for virtual-experiment standard outputs."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path


TABLE_FILENAMES = {
    "modelability_preflight": "modelability_preflight.csv",
    "case_summary": "case_summary.csv",
    "final_metrics": "final_metrics.csv",
    "threshold_times": "threshold_times.csv",
    "sampled_parameters": "sampled_parameters.csv",
    "mechanism_summary": "mechanism_summary.csv",
    "assumption_summary": "assumption_summary.csv",
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
) -> Path:
    """Write a deterministic Markdown report from existing standard tables."""

    table_root = Path(table_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "virtual_experiment_report.md"
    tables = {name: _read_rows(table_root / filename) for name, filename in TABLE_FILENAMES.items()}
    report_path.write_text(_render_report(tables=tables, quicklook_paths=quicklook_paths), encoding="utf-8")
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
    final_metrics = tables["final_metrics"]
    threshold_times = tables["threshold_times"]
    mechanisms = tables["mechanism_summary"]
    sampled_parameters = tables["sampled_parameters"]
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


def _threshold_lines(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["No threshold-time rows were present in the standard tables."]
    return [
        f"- `{_value(row, 'case_id')}` sample `{_value(row, 'sample_id')}` threshold "
        f"{_value(row, 'threshold_fraction')} (`{_value(row, 'metric')}`): `{_value(row, 'status')}` "
        f"at {_value(row, 'time')} {_value(row, 'units')}. {_value(row, 'note')}".rstrip()
        for row in rows[:12]
    ]


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
        value = _value(row, "value")
        units = _value(row, "units")
        source_class = _value(row, "parameter_source_class")
        allowed_use = _value(row, "allowed_use")
        lines.append(
            f"- `{_value(row, 'symbol')}` = {value} {units}; "
            f"source class `{source_class}`; allowed use `{allowed_use}`."
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


def _value(row: Mapping[str, str], field: str, *, fallback_field: str | None = None) -> str:
    value = row.get(field, "")
    if value or fallback_field is None:
        return value
    return row.get(fallback_field, "")


def _compact_row(row: Mapping[str, str]) -> str:
    pairs = [f"{key}={value}" for key, value in row.items() if value]
    return "; ".join(pairs)


__all__ = ["write_virtual_experiment_report"]
