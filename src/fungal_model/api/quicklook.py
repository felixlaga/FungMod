"""Quick-look plots generated from virtual-experiment tables.

Every figure is drawn from the standard CSV tables of a run directory; nothing
is simulated, fitted or inferred here. The run-level figures overlay the cases
of a run. A case whose time series hold the rates of more than one process (an
enzyme network of several classes, a culture, an enzyme chain) also gets two
figures of its own: every simulated state, and every process rate, one panel
per state or process in its own units, so that two units never share an axis.
"""

from __future__ import annotations

import csv
import json
import math
import re
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROCESS_RATE_STATE_PREFIX = "process_rate."
CASE_STATE_TRAJECTORIES_SUFFIX = "_state_trajectories.png"
CASE_PROCESS_RATES_SUFFIX = "_process_rates.png"

_STATE_SOURCE = "simulation_state"
_PROCESS_RATE_SOURCE = "simulation_process_rate"
_THRESHOLD_LINESTYLES = (":", "--", "-.")


def write_quicklook_plots(
    *,
    table_dir: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[Path, ...]:
    """Write optional quick-look plots reproducible from the standard CSV tables.

    Every run gets the run-level figures ``substrate_remaining_vs_time.png``,
    ``product_release_vs_time.png``, ``degradation_fraction_vs_time.png``,
    ``degradation_rate_vs_time.png`` and ``trajectory_quantile_bands.png``.
    Each case whose ``time_series_long.csv`` rows hold the rates of more than
    one process also gets ``<case_id>_state_trajectories.png`` (one panel per
    simulated state in its own units, the substrate panel marked with the
    degradation-threshold times of ``threshold_times.csv``) and
    ``<case_id>_process_rates.png`` (one panel per ``process_rate.<id>`` row
    set in its own units, named with the enzyme class, pool and rate modifiers
    that ``mechanism_summary.csv`` records). Paths are returned in that order,
    the case figures by case id.
    """

    table_root = Path(table_dir)
    figure_root = Path(output_dir) if output_dir is not None else table_root / "figures"
    rows = _read_csv(table_root / "time_series_long.csv")
    trajectory_quantile_rows = _read_csv(table_root / "trajectory_quantiles.csv")
    if not rows and not trajectory_quantile_rows:
        return ()
    figure_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if rows:
        written.append(
            _plot_rows(
                rows,
                output_path=figure_root / "substrate_remaining_vs_time.png",
                include=lambda row: row.get("source") == "simulation_state" and row.get("state_role") == "substrate",
                ylabel="substrate remaining",
            )
        )
        written.append(
            _plot_rows(
                rows,
                output_path=figure_root / "product_release_vs_time.png",
                include=lambda row: row.get("state") == "product_formed",
                ylabel="product formed",
            )
        )
        written.append(
            _plot_rows(
                rows,
                output_path=figure_root / "degradation_fraction_vs_time.png",
                include=lambda row: row.get("state") == "substrate_degraded_fraction",
                ylabel="substrate degraded fraction",
            )
        )
        written.append(
            _plot_rows(
                rows,
                output_path=figure_root / "degradation_rate_vs_time.png",
                include=lambda row: (
                    row.get("state") == "degradation_rate" and row.get("source") == "simulation_state_rate"
                ),
                ylabel="degradation rate",
            )
        )
    trajectory_quantile_path = _plot_trajectory_quantile_bands(
        trajectory_quantile_rows,
        output_path=figure_root / "trajectory_quantile_bands.png",
    )
    if trajectory_quantile_path is not None:
        written.append(trajectory_quantile_path)
    if rows:
        written.extend(
            _write_case_figures(
                rows,
                trajectory_quantile_rows,
                table_root=table_root,
                figure_root=figure_root,
            )
        )
    return tuple(written)


def _plot_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    output_path: Path,
    include: Any,
    ylabel: str,
) -> Path:
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = {}
    unit_groups: dict[tuple[str, str], dict[tuple[str, str], list[tuple[float, float]]]] = {}
    units = ""
    for row in rows:
        if not include(row):
            continue
        time = _optional_float(row.get("time"))
        value = _optional_float(row.get("value"))
        if time is None or value is None:
            continue
        key = (str(row.get("case_id", "")), str(row.get("sample_id", "")))
        grouped.setdefault(key, []).append((time, value))
        units = units or str(row.get("units", ""))
        unit_key = (str(row.get("units", "")), str(row.get("time_units", "")))
        unit_groups.setdefault(unit_key, {}).setdefault(key, []).append((time, value))
    if len(unit_groups) > 1:
        # Cases (or rows) in different value or time units never share an axis.
        return _plot_rows_by_units(unit_groups, output_path=output_path, ylabel=ylabel)
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(7, 4))
    for (_case_id, sample_id), values in sorted(grouped.items()):
        ordered = sorted(values)
        ax.plot(
            [item[0] for item in ordered],
            [item[1] for item in ordered],
            alpha=0.35,
            linewidth=1.0,
            label=sample_id if len(grouped) <= 8 else None,
        )
    ax.set_xlabel("time")
    ax.set_ylabel(f"{ylabel} ({units})" if units else ylabel)
    if grouped and len(grouped) <= 8:
        ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def _plot_rows_by_units(
    unit_groups: Mapping[tuple[str, str], Mapping[tuple[str, str], list[tuple[float, float]]]],
    *,
    output_path: Path,
    ylabel: str,
) -> Path:
    """One panel per (value units, time units) of the run-level figure, in order of first appearance."""

    plt = _pyplot()
    fig, axes = plt.subplots(len(unit_groups), 1, figsize=(7, 3.4 * len(unit_groups)), squeeze=False)
    for axis, ((units, time_units), grouped) in zip(axes.flat, unit_groups.items(), strict=True):
        for (case_id, sample_id), values in sorted(grouped.items()):
            ordered = sorted(values)
            axis.plot(
                [item[0] for item in ordered],
                [item[1] for item in ordered],
                alpha=0.35,
                linewidth=1.0,
                label=f"{case_id} {sample_id}" if len(grouped) <= 8 else None,
            )
        case_ids = sorted({case_id for case_id, _sample_id in grouped})
        cases = ", ".join(case_ids) if len(case_ids) <= 6 else f"{len(case_ids)} cases, {case_ids[0]} to {case_ids[-1]}"
        axis.set_title(cases, fontsize=9)
        axis.set_xlabel(f"time ({time_units})" if time_units else "time (units not recorded)")
        axis.set_ylabel(f"{ylabel} ({units})" if units else f"{ylabel} (units not recorded)")
        if len(grouped) <= 8:
            axis.legend(fontsize=7)
    fig.suptitle(f"{ylabel}: rows in different units are drawn in separate panels", fontsize=10)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def _plot_trajectory_quantile_bands(
    rows: Sequence[Mapping[str, str]],
    *,
    output_path: Path,
) -> Path | None:
    groups = _trajectory_quantile_groups(rows)
    if not groups:
        return None

    plt = _pyplot()
    fig, axes = plt.subplots(len(groups), 1, figsize=(7, 3.1 * len(groups)), squeeze=False)
    for axis, (label, values) in zip(axes.flat, groups, strict=True):
        ordered = sorted(values, key=lambda item: item[0])
        times = [item[0] for item in ordered]
        p05 = [item[1] for item in ordered]
        p50 = [item[2] for item in ordered]
        p95 = [item[3] for item in ordered]
        time_units = next((item[4] for item in ordered if item[4]), "")
        units = next((item[5] for item in ordered if item[5]), "")
        axis.fill_between(times, p05, p95, alpha=0.2, label="p05-p95")
        axis.plot(times, p50, linewidth=1.5, label="p50")
        axis.set_title(label)
        axis.set_xlabel(f"time ({time_units})" if time_units else "time")
        axis.set_ylabel(f"value ({units})" if units else "value")
        axis.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def _trajectory_quantile_groups(
    rows: Sequence[Mapping[str, str]],
) -> list[tuple[str, list[tuple[float, float, float, float, str, str]]]]:
    grouped: dict[tuple[str, str, str, str], list[tuple[float, float, float, float, str, str]]] = {}
    for row in rows:
        if row.get("source_table") != "time_series_long":
            continue
        time = _optional_float(row.get("time"))
        p05 = _optional_float(row.get("p05"))
        p50 = _optional_float(row.get("p50"))
        p95 = _optional_float(row.get("p95"))
        if time is None or p05 is None or p50 is None or p95 is None:
            continue
        key = (
            str(row.get("case_id", "")),
            str(row.get("state", "")),
            str(row.get("state_role", "")),
            str(row.get("units", "")),
        )
        grouped.setdefault(key, []).append(
            (
                time,
                p05,
                p50,
                p95,
                str(row.get("time_units", "")),
                str(row.get("units", "")),
            )
        )

    selected_keys = sorted(grouped, key=_trajectory_quantile_group_sort_key)[:3]
    return [
        (_trajectory_quantile_label(key), grouped[key])
        for key in selected_keys
    ]


def _trajectory_quantile_group_sort_key(key: tuple[str, str, str, str]) -> tuple[int, str, str, str]:
    _case_id, state, state_role, _units = key
    if state_role == "substrate":
        priority = 0
    elif state == "product_formed":
        priority = 1
    elif state == "substrate_degraded_fraction":
        priority = 2
    else:
        priority = 10
    return (priority, state_role, state, key[0])


def _trajectory_quantile_label(key: tuple[str, str, str, str]) -> str:
    case_id, state, state_role, _units = key
    role = f" ({state_role})" if state_role else ""
    return f"{case_id}: {state}{role}"


# ---------------------------------------------------------------------------
# Per-case figures of cases with several processes


@dataclass(frozen=True)
class _ThresholdMarker:
    """One degradation-threshold time of the case's substrate, as the tables record it."""

    label: str
    p05: float | None = None
    p50: float | None = None
    p95: float | None = None


@dataclass
class _Panel:
    """One state or process of a case in one units text."""

    state: str
    units: str
    role: str
    first_index: int
    title: str = ""
    samples: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    band: list[tuple[float, float, float, float]] = field(default_factory=list)
    band_count: int = 0
    markers: list[_ThresholdMarker] = field(default_factory=list)


def _write_case_figures(
    rows: Sequence[Mapping[str, str]],
    quantile_rows: Sequence[Mapping[str, str]],
    *,
    table_root: Path,
    figure_root: Path,
) -> list[Path]:
    case_ids = _several_process_case_ids(rows)
    if not case_ids:
        return []
    threshold_rows = _read_csv(table_root / "threshold_times.csv")
    summary_rows = _read_csv(table_root / "summary_metrics.csv")
    mechanism_rows = _read_csv(table_root / "mechanism_summary.csv")
    rows_by_case = _rows_by_case(rows, case_ids)
    quantiles_by_case = _rows_by_case(
        [row for row in quantile_rows if row.get("source_table") == "time_series_long"], case_ids
    )
    written: list[Path] = []
    for case_id in case_ids:
        case_rows = rows_by_case[case_id]
        case_quantiles = quantiles_by_case[case_id]
        sample_count = len({str(row.get("sample_id", "")) for row in case_rows})
        time_units = next((str(row.get("time_units", "")) for row in case_rows if row.get("time_units")), "")
        context = _case_context(case_rows[0])

        state_panels = sorted(
            _case_panels(case_rows, case_quantiles, include=lambda row: row.get("source") == _STATE_SOURCE),
            key=_state_panel_order,
        )
        markers = _threshold_markers(threshold_rows, summary_rows, case_id=case_id, time_units=time_units)
        substrate_panels = [panel for panel in state_panels if panel.role == "substrate"]
        for panel in state_panels:
            panel.title = f"{panel.state} ({panel.role})" if panel.role else panel.state
        for panel in substrate_panels:
            panel.markers = list(markers)
        state_notes = [
            "Every simulation_state row of time_series_long.csv for this case; each state in its own units.",
            _band_note(sample_count, state_panels),
        ]
        if substrate_panels and any(marker.p50 is not None for marker in markers):
            state_notes.append(
                "Grey lines on the substrate panel: times to the degradation fractions of threshold_times.csv "
                "((S0 - S) / S0 of the case's substrate state; p50 over samples from summary_metrics.csv)."
            )
        written.append(
            _plot_panel_figure(
                state_panels,
                output_path=figure_root / f"{case_id}{CASE_STATE_TRAJECTORIES_SUFFIX}",
                suptitle=f"{case_id}: every simulated state, one panel per state in its own units\n{context}",
                footnote=" ".join(state_notes),
                time_units=time_units,
                sample_count=sample_count,
                value_label="value",
            )
        )

        process_panels = _case_panels(case_rows, case_quantiles, include=_is_process_rate_row)
        descriptions = _process_descriptions(mechanism_rows, case_id=case_id)
        for panel in process_panels:
            process_id = panel.state[len(PROCESS_RATE_STATE_PREFIX) :]
            panel.title = "\n".join((process_id, *descriptions.get(process_id, ())))
        written.append(
            _plot_panel_figure(
                process_panels,
                output_path=figure_root / f"{case_id}{CASE_PROCESS_RATES_SUFFIX}",
                suptitle=f"{case_id}: rate of each process, one panel per process in its own units\n{context}",
                footnote=" ".join(
                    (
                        "process_rate.<process id> rows of time_series_long.csv: each process law evaluated by the "
                        "solver at the returned times (the sample bundles' process_rates.csv), not finite "
                        "differences; enzyme class, pool and rate modifiers from mechanism_summary.csv where it "
                        "records them.",
                        _band_note(sample_count, process_panels),
                    )
                ),
                time_units=time_units,
                sample_count=sample_count,
                value_label="rate",
            )
        )
    return written


def _several_process_case_ids(rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Cases whose time series hold the rates of more than one process, sorted by case id."""

    processes: dict[str, set[str]] = {}
    for row in rows:
        if _is_process_rate_row(row):
            processes.setdefault(str(row.get("case_id", "")), set()).add(str(row.get("state", "")))
    return sorted(case_id for case_id, states in processes.items() if len(states) > 1)


def _rows_by_case(
    rows: Sequence[Mapping[str, str]], case_ids: Sequence[str]
) -> dict[str, list[Mapping[str, str]]]:
    """The rows of each of the cases, in table order, in one pass over the table."""

    grouped: dict[str, list[Mapping[str, str]]] = {case_id: [] for case_id in case_ids}
    for row in rows:
        case_rows = grouped.get(str(row.get("case_id", "")))
        if case_rows is not None:
            case_rows.append(row)
    return grouped


def _is_process_rate_row(row: Mapping[str, str]) -> bool:
    return row.get("source") == _PROCESS_RATE_SOURCE and str(row.get("state", "")).startswith(
        PROCESS_RATE_STATE_PREFIX
    )


def _case_context(row: Mapping[str, str]) -> str:
    fungus = row.get("fungus_id", "")
    substrate = row.get("substrate_id", "")
    environment = row.get("environment_id", "")
    process_type = row.get("process_type", "")
    return f"{fungus} on {substrate}, {environment} ({process_type})"


def _case_panels(
    case_rows: Sequence[Mapping[str, str]],
    case_quantiles: Sequence[Mapping[str, str]],
    *,
    include: Callable[[Mapping[str, str]], bool],
) -> list[_Panel]:
    """One panel per (state, units) of the included rows, in order of first appearance."""

    panels: dict[tuple[str, str], _Panel] = {}
    for index, row in enumerate(case_rows):
        if not include(row):
            continue
        key = (str(row.get("state", "")), str(row.get("units", "")))
        panel = panels.get(key)
        if panel is None:
            panel = panels[key] = _Panel(
                state=key[0], units=key[1], role=str(row.get("state_role", "")), first_index=index
            )
        time = _optional_float(row.get("time"))
        value = _optional_float(row.get("value"))
        if time is None or value is None:
            continue
        panel.samples.setdefault(str(row.get("sample_id", "")), []).append((time, value))
    for row in case_quantiles:
        panel = panels.get((str(row.get("state", "")), str(row.get("units", ""))))
        if panel is None:
            continue
        time = _optional_float(row.get("time"))
        p05 = _optional_float(row.get("p05"))
        p50 = _optional_float(row.get("p50"))
        p95 = _optional_float(row.get("p95"))
        if time is None or p05 is None or p50 is None or p95 is None:
            continue
        panel.band.append((time, p05, p50, p95))
        panel.band_count = max(panel.band_count, int(_optional_float(row.get("count")) or 0))
    return list(panels.values())


def _state_panel_order(panel: _Panel) -> tuple[int, int, int]:
    """Substrate, intermediates in their numbered order, product, then every other state as the table lists it."""

    if panel.role == "substrate":
        return (0, 0, panel.first_index)
    intermediate = re.fullmatch(r"intermediate(?:_(\d+))?", panel.role)
    if intermediate is not None:
        return (1, int(intermediate.group(1) or 0), panel.first_index)
    if panel.role == "product":
        return (2, 0, panel.first_index)
    return (3, 0, panel.first_index)


def _threshold_markers(
    threshold_rows: Sequence[Mapping[str, str]],
    summary_rows: Sequence[Mapping[str, str]],
    *,
    case_id: str,
    time_units: str,
) -> list[_ThresholdMarker]:
    """The case's degradation-threshold times: p05/p50/p95 from summary_metrics.csv, statuses from threshold_times.csv."""

    thresholds: dict[str, tuple[str, dict[str, int]]] = {}
    for row in threshold_rows:
        if row.get("case_id") != case_id:
            continue
        metric = str(row.get("metric", ""))
        fraction, statuses = thresholds.setdefault(metric, (str(row.get("threshold_fraction", "")), {}))
        status = str(row.get("status", ""))
        statuses[status] = statuses.get(status, 0) + 1
    summaries = {str(row.get("metric", "")): row for row in summary_rows if row.get("case_id") == case_id}
    markers: list[_ThresholdMarker] = []
    for metric, (fraction, statuses) in thresholds.items():
        name = f"{_percent_text(fraction) or metric} degraded"
        total = sum(statuses.values())
        summary = summaries.get(metric, {})
        p50 = _optional_float(summary.get("p50"))
        count = int(_optional_float(summary.get("count")) or 0)
        units = str(summary.get("units", ""))
        if p50 is None or count == 0:
            if set(statuses) == {"not_reached"}:
                markers.append(_ThresholdMarker(label=f"{name}: not reached within the simulated time"))
            else:
                status_text = ", ".join(f"{status} {number}" for status, number in sorted(statuses.items()))
                markers.append(_ThresholdMarker(label=f"{name}: no time ({status_text})"))
            continue
        if units != time_units:
            markers.append(_ThresholdMarker(label=f"{name}: time in {units}, not drawn on the {time_units} axis"))
            continue
        p05 = _optional_float(summary.get("p05"))
        p95 = _optional_float(summary.get("p95"))
        if total == 1:
            label = f"{name} at {p50:.4g} {units}"
        else:
            label = f"{name}: p50 {p50:.4g} {units}"
            if p05 is not None and p95 is not None and p95 > p05:
                label += f", p05-p95 {p05:.4g}-{p95:.4g} (shaded)"
            label += f"; reached in {count} of {total} samples"
        markers.append(_ThresholdMarker(label=label, p05=p05, p50=p50, p95=p95))
    return markers


def _percent_text(fraction: str) -> str:
    value = _optional_float(fraction)
    return "" if value is None else f"{value * 100:g} %"


def _process_descriptions(mechanism_rows: Sequence[Mapping[str, str]], *, case_id: str) -> dict[str, tuple[str, ...]]:
    """Per process id: its enzyme class and pool, and its rate modifiers, as mechanism_summary.csv records them."""

    descriptions: dict[str, list[str]] = {}
    for row in mechanism_rows:
        if row.get("case_id") != case_id or row.get("mechanism_kind") != "process_law":
            continue
        provenance = _json_mapping(row.get("provenance", ""))
        process_id = str(provenance.get("process_id", ""))
        enzyme_class = str(provenance.get("enzyme_class", ""))
        if not process_id or process_id != row.get("mechanism_id") or not enzyme_class:
            continue
        pool = _state_variables(row.get("state_variables", "")).get("substrate", "")
        text = f"enzyme class {enzyme_class}" + (f" on pool {pool}" if pool else "")
        descriptions.setdefault(process_id, []).append(text)
    for row in mechanism_rows:
        if row.get("case_id") != case_id or row.get("mechanism_kind") != "rate_modifier":
            continue
        process_id = str(row.get("configured_by", ""))
        if process_id not in descriptions:
            continue
        acting = ", ".join(
            f"{variable}: {state}"
            for variable, state in _state_variables(row.get("state_variables", "")).items()
            if variable != "substrate"
        )
        modifier = str(row.get("mechanism_id", ""))
        descriptions[process_id].append(f"modifier {modifier} ({acting})" if acting else f"modifier {modifier}")
    return {process_id: tuple(lines) for process_id, lines in descriptions.items()}


def _state_variables(text: str | None) -> dict[str, str]:
    """``field:state;field:state`` of a mechanism row, fields without a state left out."""

    variables: dict[str, str] = {}
    for item in str(text or "").split(";"):
        variable, separator, state = item.partition(":")
        if separator and variable and state:
            variables.setdefault(variable, state)
    return variables


def _band_note(sample_count: int, panels: Sequence[_Panel]) -> str:
    if sample_count > 1 and any(panel.band for panel in panels):
        return (
            f"Shaded: p05-p95 of the {sample_count} samples at each time, line: p50 (trajectory_quantiles.csv; "
            "a summary of simulated samples, not validation or a confidence interval)."
        )
    if sample_count > 1:
        return f"One line per sample ({sample_count} samples); no trajectory_quantiles.csv rows, so no band."
    return "One simulated sample, no ensemble band."


def _plot_panel_figure(
    panels: Sequence[_Panel],
    *,
    output_path: Path,
    suptitle: str,
    footnote: str,
    time_units: str,
    sample_count: int,
    value_label: str,
) -> Path:
    plt = _pyplot()
    columns = 2 if len(panels) > 2 else 1
    rows = max(math.ceil(len(panels) / columns), 1)
    width = 13.0 if columns == 2 else 10.0
    # Wrapped here rather than by matplotlib, so the layout does not depend on the renderer.
    title_lines = [
        line
        for part in suptitle.split("\n")
        for line in (textwrap.wrap(part, width=int(width * 11)) or [""])
    ]
    note_lines = textwrap.wrap(footnote, width=int(width * 17))
    title_height = 0.22 * len(title_lines) + 0.15
    note_height = 0.14 * len(note_lines) + 0.15
    height = 3.3 * rows + title_height + note_height
    fig, axes = plt.subplots(rows, columns, figsize=(width, height), squeeze=False)
    flat_axes = list(axes.flat)
    for axis, panel in zip(flat_axes, panels):
        _draw_panel(axis, panel, time_units=time_units, sample_count=sample_count, value_label=value_label)
    for axis in flat_axes[len(panels) :]:
        fig.delaxes(axis)
    fig.suptitle(_plain("\n".join(title_lines)), fontsize=10)
    fig.text(0.01, 0.01, _plain("\n".join(note_lines)), fontsize=7, ha="left", va="bottom")
    fig.tight_layout(rect=(0.0, note_height / height, 1.0, 1.0 - title_height / height))
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _draw_panel(axis: Any, panel: _Panel, *, time_units: str, sample_count: int, value_label: str) -> None:
    if sample_count > 1 and panel.band:
        ordered_band = sorted(panel.band)
        times = [item[0] for item in ordered_band]
        axis.fill_between(
            times,
            [item[1] for item in ordered_band],
            [item[3] for item in ordered_band],
            alpha=0.2,
            color="C0",
            label=f"p05-p95 of {panel.band_count} samples",
        )
        axis.plot(times, [item[2] for item in ordered_band], color="C0", linewidth=1.5, label="p50")
    else:
        single = len(panel.samples) == 1
        for sample_id, values in sorted(panel.samples.items()):
            ordered = sorted(values)
            axis.plot(
                [item[0] for item in ordered],
                [item[1] for item in ordered],
                alpha=1.0 if single else 0.35,
                linewidth=1.5 if single else 1.0,
                label=_plain(sample_id) if len(panel.samples) <= 8 else None,
            )
    if not panel.samples and not panel.band:
        axis.text(
            0.5,
            0.5,
            "no numeric values in time_series_long.csv",
            ha="center",
            va="center",
            fontsize=8,
            transform=axis.transAxes,
        )
    for index, marker in enumerate(panel.markers):
        style = _THRESHOLD_LINESTYLES[index % len(_THRESHOLD_LINESTYLES)]
        if marker.p50 is None:
            axis.plot([], [], linestyle="none", label=_plain(marker.label))
            continue
        if marker.p05 is not None and marker.p95 is not None and marker.p95 > marker.p05:
            axis.axvspan(marker.p05, marker.p95, color="0.5", alpha=0.12, linewidth=0)
        axis.axvline(marker.p50, color="0.35", linestyle=style, linewidth=1.2, label=_plain(marker.label))
    axis.set_title(_plain(panel.title), fontsize=8)
    axis.set_xlabel(_plain(f"time ({time_units})" if time_units else "time (units not recorded)"))
    axis.set_ylabel(
        _plain(f"{value_label} ({panel.units})" if panel.units else f"{value_label} (units not recorded)")
    )
    _handles, labels = axis.get_legend_handles_labels()
    if labels:
        axis.legend(fontsize=7)


def _plain(text: str) -> str:
    """Text as written: a ``$`` in an identifier or units text is not a matplotlib math delimiter."""

    return text.replace("$", r"\$")


def _json_mapping(text: str | None) -> Mapping[str, Any]:
    try:
        value = json.loads(text or "")
    except ValueError:
        return {}
    return value if isinstance(value, Mapping) else {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


__all__ = ["write_quicklook_plots"]
