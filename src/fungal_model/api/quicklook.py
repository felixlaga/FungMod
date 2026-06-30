"""Quick-look plots generated from virtual-experiment tables."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def write_quicklook_plots(
    *,
    table_dir: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[Path, ...]:
    """Write optional API-001 plots reproducible from CSV tables."""

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
    trajectory_quantile_path = _plot_trajectory_quantile_bands(
        trajectory_quantile_rows,
        output_path=figure_root / "trajectory_quantile_bands.png",
    )
    if trajectory_quantile_path is not None:
        written.append(trajectory_quantile_path)
    return tuple(written)


def _plot_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    output_path: Path,
    include: Any,
    ylabel: str,
) -> Path:
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(7, 4))
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = {}
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
