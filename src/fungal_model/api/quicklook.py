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
    if not rows:
        return ()
    figure_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
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


def _read_csv(path: Path) -> list[dict[str, str]]:
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
