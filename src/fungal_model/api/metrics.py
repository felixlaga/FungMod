"""Metric helpers for virtual-experiment output tables."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

DEGRADATION_THRESHOLDS: tuple[float, ...] = (0.10, 0.50, 0.90)
SUMMARY_QUANTILES: tuple[tuple[str, float], ...] = (
    ("p05", 0.05),
    ("p50", 0.50),
    ("p95", 0.95),
)


def summarize_numeric_values(values: Sequence[float]) -> dict[str, Any]:
    """Return the standard uncertainty summary for one numeric metric."""

    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    if data.size == 0:
        return {
            "count": 0,
            "mean": "",
            "min": "",
            "max": "",
            "p05": "",
            "p50": "",
            "p95": "",
        }
    summary: dict[str, Any] = {
        "count": int(data.size),
        "mean": float(np.mean(data)),
        "min": float(np.min(data)),
        "max": float(np.max(data)),
    }
    for name, quantile in SUMMARY_QUANTILES:
        summary[name] = float(np.quantile(data, quantile))
    return summary


def threshold_crossing_time(
    *,
    time_values: Sequence[float],
    degraded_fraction: Sequence[float],
    threshold: float,
) -> float | None:
    """Return the first linearly interpolated threshold crossing time."""

    times = np.asarray(time_values, dtype=float)
    fractions = np.asarray(degraded_fraction, dtype=float)
    if times.size == 0 or fractions.size == 0 or times.size != fractions.size:
        return None
    for index, fraction in enumerate(fractions):
        if fraction < threshold:
            continue
        if index == 0:
            return float(times[index])
        previous_fraction = float(fractions[index - 1])
        previous_time = float(times[index - 1])
        current_fraction = float(fraction)
        current_time = float(times[index])
        if current_fraction == previous_fraction:
            return current_time
        weight = (threshold - previous_fraction) / (current_fraction - previous_fraction)
        return float(previous_time + weight * (current_time - previous_time))
    return None


__all__ = [
    "DEGRADATION_THRESHOLDS",
    "SUMMARY_QUANTILES",
    "summarize_numeric_values",
    "threshold_crossing_time",
]
