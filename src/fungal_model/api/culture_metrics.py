"""Reductions of explicit culture state trajectories; no inferred biology or cutoffs."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from fungal_model.core.units import Q_


def trajectory_metrics(
    trajectory_rows: Sequence[Mapping[str, Any]],
    state_roles: Mapping[str, str],
    *,
    oxygen_threshold: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Reduce uptake culture pools using output-grid extrema and linear threshold crossings.

    Rows have the existing trajectory.csv form (time, time_units, state,
    state_units). Thresholds are explicit scalar value/units mappings. No
    rows are added to earlier models without these bound state roles.
    """
    if not trajectory_rows or not {"soluble_product", "dissolved_oxygen"}.intersection(state_roles):
        return []
    metrics: list[dict[str, Any]] = []
    time_units = str(trajectory_rows[0]["time_units"])
    times = [float(Q_(float(row["time"]), row["time_units"]).to(time_units).magnitude) for row in trajectory_rows]
    if not all(math.isfinite(t) for t in times) or any(b < a for a, b in zip(times, times[1:])):
        raise ValueError("Culture metric times must be finite and nondecreasing.")

    def series(role: str) -> tuple[list[float], str]:
        state = state_roles[role]
        units = str(trajectory_rows[0][state + "_units"])
        values = [float(Q_(float(row[state]), row[state + "_units"]).to(units).magnitude) for row in trajectory_rows]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Culture metric state {state!r} contains nonfinite values.")
        return values, units

    def add(name: str, value: Any, units: str, notes: str, status: str = "computed") -> None:
        metrics.append({"metric_name": name, "value": value, "units": units, "status": status, "notes": notes})

    if {"soluble_product", "biomass", "ledger_respired_carbon"}.issubset(state_roles):
        sugar, sugar_units = series("soluble_product")
        peak_index = max(range(len(sugar)), key=sugar.__getitem__)
        add("peak_soluble_sugar", sugar[peak_index], sugar_units, "Maximum on the simulated output grid.")
        add("time_of_peak_soluble_sugar", times[peak_index], time_units, "First maximum on the simulated output grid; no unobserved peak inferred.")
        biomass, biomass_units = series("biomass")
        add("final_biomass", biomass[-1], biomass_units, "Biomass at the final simulated time.")
    if "dissolved_oxygen" in state_roles:
        oxygen, oxygen_units = series("dissolved_oxygen")
        add("minimum_dissolved_oxygen", min(oxygen), oxygen_units, "Minimum on the simulated output grid.")
        if oxygen_threshold is None:
            add("time_below_oxygen_threshold", "", time_units, "Unknown: no explicit oxygen threshold was supplied in metric_definitions.", "unknown")
        else:
            if (set(oxygen_threshold) != {"value", "units"}
                    or not isinstance(oxygen_threshold.get("value"), (int, float))
                    or isinstance(oxygen_threshold.get("value"), bool)):
                raise ValueError("oxygen_threshold must give exactly scalar value and units.")
            threshold = float(Q_(oxygen_threshold["value"], oxygen_threshold["units"]).to(oxygen_units).magnitude)
            if not math.isfinite(threshold) or threshold < 0:
                raise ValueError("oxygen_threshold must be finite and nonnegative.")
            duration = time_below_threshold(times, oxygen, threshold)
            add("time_below_oxygen_threshold", duration, time_units,
                f"Time strictly below the supplied threshold {threshold:g} {oxygen_units}; linear interpolation between output points.")
    return metrics


def time_below_threshold(times: Sequence[float], values: Sequence[float], threshold: float) -> float:
    """Measure strict sub-threshold duration along a piecewise-linear trajectory."""
    if len(times) != len(values) or not times:
        raise ValueError("Threshold duration needs equally sized, nonempty time and value arrays.")
    if not all(math.isfinite(value) for value in (*times, *values, threshold)):
        raise ValueError("Threshold duration inputs must be finite.")
    total = 0.0
    for start, end, left, right in zip(times, times[1:], values, values[1:]):
        width = end - start
        if width < 0:
            raise ValueError("Threshold duration times must be nondecreasing.")
        if left < threshold and right < threshold:
            total += width
        elif (left < threshold) != (right < threshold):
            fraction = (threshold - left) / (right - left)
            total += width * (fraction if left < threshold else 1 - fraction)
    return total
