"""COLONY-001: the De Ligne 2019 colony comparison under its frozen plan, stage 0.

Stage 0 is software only. This module reads the frozen plan and verifies the
dataset digests it pins, loads the observations under the plan's row rules,
fits the plan's per-series error model, builds the plan's colony model on the
axisymmetric calibration grid or on the two-dimensional reference grid from a
caller-supplied parameter set, evaluates the plan's two observation operators,
and records the plan's software checks (grid, solver, symmetry, timing). No
parameter is fitted here and nothing in this module reads a value from the
data into a model.

Every output cites the plan's SHA-256. The check values used by the software
checks are artificial framework values declared in this module, labelled
``testing``, and recorded with the checks; they are not estimates of either
species.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, Quantity
from fungal_model.mycelium import (
    Anastomosis,
    FieldSpec,
    FirstOrderLoss,
    LateralBranching,
    LocalUptake,
    MyceliumModel,
    MyceliumResult,
    SpatialGrid,
    TipExtension,
    TipMotion,
    Translocation,
    colony_count_outside_disc,
    colony_hull_area,
)

PLAN_PATH = Path("data/benchmarks/de_ligne_2019_colony/plan.json")
RESULTS_PATH = Path("data/benchmarks/de_ligne_2019_colony/results")
DATASET_DIR = Path("data/experiments/literature/de_ligne_2019_colony_growth")
PANEL_TABLE = Path("data/experiments/source_intake/de_ligne_2019/digitized_panels.csv")

TEMPERATURES_C = (15, 20, 25, 30)
HUMIDITIES_PERCENT = (65, 70, 75, 80)
QUANTITIES = ("area", "tips")
VALUE_COLUMNS = {"area": "mycelial_area_cm2", "tips": "tip_count"}
SD_COLUMNS = {"area": "mycelial_area_sd_cm2", "tips": "tip_count_sd"}
UNCERTAINTY_COLUMNS = {"area": "digitization_uncertainty_cm2", "tips": "digitization_uncertainty"}
OBSERVABLE_UNITS = {"area": "centimeter ** 2", "tips": "dimensionless"}
READABLE_EXCLUDES = ("sd_one_sided", "sd_asymmetric_bar")

FIELD_ROLES = {"tips": "tips", "hyphae": "hyphae", "internal": "internal_substrate", "reserve": "external_substrate"}
SHARED_SYMBOLS = ("Kv", "c_ext", "Dn", "a", "dn", "cu", "Di", "Da", "R0", "n0", "rho0")
SCALED_SYMBOLS = ("v", "b")
CHECK_SOURCE = (
    "COLONY-001 stage 0 software-check value: an artificial framework value inside the plan's bounds, "
    "declared for the grid, solver and symmetry checks; no estimate of either species."
)
# Artificial values inside the plan's bounds for the software checks only.
STAGE_0_CHECK_VALUES: dict[str, float] = {
    "v": 0.5,
    "b": 0.1,
    "Kv": 1.0,
    "c_ext": 0.001,
    "Dn": 1.0,
    "a": 0.02,
    "dn": 0.02,
    "cu": 0.1,
    "Di": 5.0,
    "Da": 1.0,
    "R0": 50.0,
    "n0": 5.0,
    "rho0": 10.0,
}
STAGE_0_CHECK_PHI = 1.0


class ColonyComparisonError(ValueError):
    """Raised when the plan, the data or a check is not what the plan declares."""


# --------------------------------------------------------------------------- #
# Plan and observations
# --------------------------------------------------------------------------- #


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(root: Path, *, plan_path: Path | None = None) -> dict[str, Any]:
    """Read the frozen plan and verify every dataset digest it pins."""

    path = root / (plan_path or PLAN_PATH)
    plan = json.loads(path.read_text(encoding="utf-8"))
    for name, digest in plan["data"]["dataset_sha256"].items():
        found = file_digest(root / plan["data"]["directory"] / name)
        if found != digest:
            raise ColonyComparisonError(f"{name}: digest {found} differs from the plan's {digest}.")
    panel_digest = file_digest(root / PANEL_TABLE)
    if panel_digest != plan["data"]["panel_table_sha256"]:
        raise ColonyComparisonError("The panel table's digest differs from the plan's.")
    plan["_sha256"] = file_digest(path)
    return plan


@dataclass(frozen=True)
class ConditionObservations:
    species: str
    quantity: str
    temperature_c: int
    humidity_percent: int
    hours: tuple[int, ...]
    values: tuple[float, ...]
    standard_deviations: tuple[float | None, ...]
    digitization_uncertainties: tuple[float, ...]
    flags: tuple[tuple[str, ...], ...]
    excluded: tuple[tuple[int, str], ...]

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.quantity, self.temperature_c, self.humidity_percent)


def _dataset_file(species: str, quantity: str) -> str:
    return f"de_ligne_2019_{species}_{quantity}.yml"


def load_observations(root: Path, plan: Mapping[str, Any], species: str) -> dict[tuple[str, int, int], ConditionObservations]:
    """Every condition series of one species under the plan's row rules."""

    directory = root / plan["data"]["directory"]
    rules = plan["data"]["row_rules"]
    exclude_disagreement = str(rules["panel_disagreement"]).startswith("excluded")
    observations: dict[tuple[str, int, int], ConditionObservations] = {}
    for quantity in QUANTITIES:
        metadata = yaml.safe_load((directory / _dataset_file(species, quantity)).read_text(encoding="utf-8"))
        for entry in metadata["measurements"]:
            temperature = int(entry["conditions"]["temperature"]["value"])
            humidity = int(entry["conditions"]["relative_humidity"]["value"])
            hours: list[int] = []
            values: list[float] = []
            sds: list[float | None] = []
            uncertainties: list[float] = []
            flags: list[tuple[str, ...]] = []
            excluded: list[tuple[int, str]] = []
            with (directory / entry["data_file"]).open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    row_flags = tuple(flag for flag in row["flags"].split(";") if flag)
                    hour = int(row["time_h"])
                    if exclude_disagreement and "panel_disagreement" in row_flags:
                        excluded.append((hour, "panel_disagreement"))
                        continue
                    hours.append(hour)
                    values.append(float(row[VALUE_COLUMNS[quantity]]))
                    sd_text = row[SD_COLUMNS[quantity]]
                    sds.append(float(sd_text) if sd_text else None)
                    uncertainties.append(float(row[UNCERTAINTY_COLUMNS[quantity]]))
                    flags.append(row_flags)
            observations[(quantity, temperature, humidity)] = ConditionObservations(
                species, quantity, temperature, humidity, tuple(hours), tuple(values), tuple(sds),
                tuple(uncertainties), tuple(flags), tuple(excluded),
            )
    expected = len(QUANTITIES) * len(TEMPERATURES_C) * len(HUMIDITIES_PERCENT)
    if len(observations) != expected:
        raise ColonyComparisonError(f"{species}: {len(observations)} condition series loaded; expected {expected}.")
    return observations


# --------------------------------------------------------------------------- #
# Error model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ErrorModel:
    """``sigma(t) = s0 + s1 * y(t)``, floored at the row's digitization uncertainty."""

    species: str
    quantity: str
    temperature_c: int
    humidity_percent: int
    s0: float
    s1: float
    readable_rows: int
    pooled: bool
    pooled_rows: int

    def sigma(self, values: np.ndarray, floor: np.ndarray) -> np.ndarray:
        return np.maximum(self.s0 + self.s1 * np.asarray(values, dtype=float), np.asarray(floor, dtype=float))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _readable(series: ConditionObservations) -> tuple[np.ndarray, np.ndarray]:
    ys: list[float] = []
    sds: list[float] = []
    for value, sd, flags in zip(series.values, series.standard_deviations, series.flags, strict=True):
        if sd is None or any(flag in flags for flag in READABLE_EXCLUDES):
            continue
        ys.append(value)
        sds.append(sd)
    return np.asarray(ys, dtype=float), np.asarray(sds, dtype=float)


def _linear_fit(ys: np.ndarray, sds: np.ndarray) -> tuple[float, float]:
    if ys.size < 2 or np.ptp(ys) == 0.0:
        raise ColonyComparisonError("The error model needs at least two readable rows with distinct values.")
    slope, intercept = np.polyfit(ys, sds, 1)
    return float(intercept), float(slope)


def fit_error_models(observations: Mapping[tuple[str, int, int], ConditionObservations], plan: Mapping[str, Any]) -> dict[tuple[str, int, int], ErrorModel]:
    """The plan's per-series linear standard-deviation model, pooled where a series has too few readable rows."""

    minimum = int(plan["error_model"]["minimum_readable_rows"])
    readable = {key: _readable(series) for key, series in observations.items()}
    models: dict[tuple[str, int, int], ErrorModel] = {}
    for key, series in observations.items():
        ys, sds = readable[key]
        if ys.size >= minimum:
            s0, s1 = _linear_fit(ys, sds)
            models[key] = ErrorModel(series.species, series.quantity, series.temperature_c, series.humidity_percent, s0, s1, int(ys.size), False, 0)
            continue
        pool_y = np.concatenate([readable[other][0] for other in observations if other != key and other[0] == key[0]])
        pool_sd = np.concatenate([readable[other][1] for other in observations if other != key and other[0] == key[0]])
        s0, s1 = _linear_fit(pool_y, pool_sd)
        models[key] = ErrorModel(series.species, series.quantity, series.temperature_c, series.humidity_percent, s0, s1, int(ys.size), True, int(pool_y.size))
    return models


# --------------------------------------------------------------------------- #
# The plan's model
# --------------------------------------------------------------------------- #


def plan_parameter_units(plan: Mapping[str, Any]) -> dict[str, str]:
    return {item["symbol"]: item["units"] for item in plan["model"]["parameters"]}


def plan_bounds(plan: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    return {item["symbol"]: (float(item["lower"]), float(item["upper"])) for item in plan["model"]["parameters"]}


def check_within_bounds(plan: Mapping[str, Any], values: Mapping[str, float]) -> None:
    bounds = plan_bounds(plan)
    for symbol in SHARED_SYMBOLS + SCALED_SYMBOLS:
        if symbol not in values:
            raise ColonyComparisonError(f"Parameter {symbol!r} is missing.")
        lower, upper = bounds[symbol]
        if not lower <= values[symbol] <= upper:
            raise ColonyComparisonError(f"Parameter {symbol!r} = {values[symbol]} lies outside the plan's bounds [{lower}, {upper}].")


def scaled_values(values: Mapping[str, float], phi: float) -> dict[str, float]:
    """The condition's rates: ``phi`` multiplies the extension speed and the branching rate."""

    if not 0.0 <= phi <= 1.0:
        raise ColonyComparisonError(f"phi must lie in [0, 1]; got {phi}.")
    scaled = dict(values)
    for symbol in SCALED_SYMBOLS:
        scaled[symbol] = values[symbol] * phi
    return scaled


def colony_grid(plan: Mapping[str, Any], *, geometry: str = "axisymmetric", cells: int | None = None, source: str = CHECK_SOURCE) -> SpatialGrid:
    domain = plan["geometry"]["domain"]
    if geometry == "axisymmetric":
        radius = Parameter(name="colony domain radius", symbol="R_domain", value=float(domain["radius_mm"]), units="millimeter", uncertainty=None, source=source, confidence_level="testing", notes="The half-diagonal of the scan window, from the plan.")
        return SpatialGrid.axisymmetric(radius, int(cells or domain["cells"]))
    if geometry == "cartesian":
        side = 2.0 * float(domain["radius_mm"]) / np.sqrt(2.0)
        length = Parameter(name="scan window side", symbol="L_window", value=side, units="millimeter", uncertainty=None, source=source, confidence_level="testing", notes="The scan window side, from the plan.")
        if cells is None:
            raise ColonyComparisonError("A cartesian grid needs an explicit cell count per axis.")
        return SpatialGrid.no_flux((length, length), (int(cells), int(cells)))
    raise ColonyComparisonError(f"Unsupported geometry {geometry!r}.")


def colony_model(
    plan: Mapping[str, Any],
    values: Mapping[str, float],
    *,
    geometry: str = "axisymmetric",
    cells: int | None = None,
    source: str = CHECK_SOURCE,
    confidence_level: str = "testing",
    time_units: str = "hour",
) -> MyceliumModel:
    """The plan's ``colony_reserve_v1`` model with the given parameter values (already scaled by phi)."""

    check_within_bounds(plan, values)
    units = plan_parameter_units(plan)
    fields = plan["model"]["fields"]
    tip_units, hypha_units = fields["tips"]["units"], fields["hyphae"]["units"]
    internal_units, reserve_units = fields["internal"]["units"], fields["reserve"]["units"]
    specs = tuple(FieldSpec(name, spec["units"], spec["meaning"], FIELD_ROLES[name]) for name, spec in fields.items())
    processes = (
        TipExtension(
            name="extension", tip_field="tips", tip_units=tip_units, hypha_field="hyphae", hypha_units=hypha_units,
            speed_symbol="v", substrate_field="internal", substrate_units=internal_units, half_saturation_symbol="Kv",
            cost_field="internal", cost_units=internal_units, cost_symbol="c_ext",
        ),
        TipMotion(name="motion", tip_field="tips", tip_units=tip_units, diffusivity_symbol="Dn"),
        LateralBranching(
            name="branching", tip_field="tips", tip_units=tip_units, hypha_field="hyphae", hypha_units=hypha_units,
            rate_symbol="b", substrate_field="internal", substrate_units=internal_units,
        ),
        Anastomosis(name="anastomosis", tip_field="tips", tip_units=tip_units, hypha_field="hyphae", hypha_units=hypha_units, rate_symbol="a"),
        FirstOrderLoss(name="tip_death", field="tips", field_units=tip_units, rate_symbol="dn"),
        LocalUptake(
            name="uptake", external_field="reserve", external_units=reserve_units, internal_field="internal",
            internal_units=internal_units, hypha_field="hyphae", hypha_units=hypha_units, rate_symbol="cu",
        ),
        Translocation(
            name="translocation", internal_field="internal", internal_units=internal_units, diffusivity_symbol="Di",
            tip_field="tips", tip_units=tip_units, active_diffusivity_symbol="Da",
        ),
    )
    parameters = ParameterSet(
        [
            Parameter(
                name=f"colony_reserve_v1 {symbol}", symbol=symbol, value=float(values[symbol]), units=units[symbol],
                uncertainty=None, source=source, confidence_level=confidence_level,  # type: ignore[arg-type]
                notes=next(item["meaning"] for item in plan["model"]["parameters"] if item["symbol"] == symbol),
            )
            for symbol in ("v", "b", "Kv", "c_ext", "Dn", "a", "dn", "cu", "Di", "Da")
        ]
    )
    return MyceliumModel(grid=colony_grid(plan, geometry=geometry, cells=cells, source=source), fields=specs, processes=processes, parameters=parameters, time_units=time_units)


def initial_fields(model: MyceliumModel, plan: Mapping[str, Any], values: Mapping[str, float]) -> dict[str, Quantity]:
    """Tips, hyphae and the reserve inside the inoculum disc; nothing outside; no internal reserve anywhere."""

    fields = plan["model"]["fields"]
    disc_mm = float(plan["geometry"]["inoculum"]["radius_mm"])
    grid = model.grid
    if grid.geometry == "axisymmetric":
        squared = (grid.coordinates[0] * 1e3) ** 2
    else:
        axes = np.meshgrid(*[axis * 1e3 for axis in grid.coordinates], indexing="ij")
        centre = [0.5 * float(length.quantity.to("millimeter").magnitude) for length in grid.axis_lengths if length.quantity is not None]
        squared = sum((axis - origin) ** 2 for axis, origin in zip(axes, centre, strict=True))
    inside = squared < disc_mm**2
    return {
        "tips": Q_(np.where(inside, float(values["n0"]), 0.0), fields["tips"]["units"]),
        "hyphae": Q_(np.where(inside, float(values["rho0"]), 0.0), fields["hyphae"]["units"]),
        "internal": Q_(np.zeros(grid.shape), fields["internal"]["units"]),
        "reserve": Q_(np.where(inside, float(values["R0"]), 0.0), fields["reserve"]["units"]),
    }


def plan_solver(plan: Mapping[str, Any], which: str = "primary") -> SolverSettings:
    settings = plan["geometry"]["solver_check"][which]
    return SolverSettings(method=str(settings["method"]), rtol=float(settings["rtol"]), atol=float(settings["atol"]))


def simulate_condition(
    plan: Mapping[str, Any],
    values: Mapping[str, float],
    phi: float,
    *,
    hours: Sequence[int] | None = None,
    geometry: str = "axisymmetric",
    cells: int | None = None,
    solver: SolverSettings | None = None,
) -> MyceliumResult:
    """Run the plan's model for one condition activity ``phi`` to the requested hours (1 to 62 by default)."""

    model = colony_model(plan, scaled_values(values, phi), geometry=geometry, cells=cells)
    compiled = model.compile()
    times = np.asarray(sorted({0, *(hours if hours is not None else range(1, 63))}), dtype=float)
    return compiled.simulate(
        initial_fields=initial_fields(model, plan, values),
        t_span=(Q_(0.0, "hour"), Q_(float(times[-1]), "hour")),
        t_eval=Q_(times, "hour"),
        solver_settings=solver or plan_solver(plan),
        record_rates=False,
    )


def observables(result: MyceliumResult, plan: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """The plan's operators: tip count outside the disc, mycelial area as the window-truncated hull, per output time."""

    disc = Q_(float(plan["geometry"]["inoculum"]["radius_mm"]), "millimeter")
    half_side = Q_(float(plan["geometry"]["domain"]["radius_mm"]) / np.sqrt(2.0), "millimeter")
    declared = plan["observation_operators"]["detection_density"]
    detection = Q_(float(declared["value"]), str(declared["units"]))
    tips = colony_count_outside_disc(result, field="tips", disc_radius=disc, window_half_side=half_side)
    area = colony_hull_area(result, field="hyphae", detection_density=detection, disc_radius=disc, window_half_side=half_side)
    return {
        "time_h": np.asarray(result.time.to("hour").magnitude, dtype=float),
        "tip_count": np.asarray(tips.to("dimensionless").magnitude, dtype=float),
        "mycelial_area_cm2": np.asarray(area.to("centimeter ** 2").magnitude, dtype=float),
    }


# --------------------------------------------------------------------------- #
# Stage 0: recorded software checks
# --------------------------------------------------------------------------- #


def _relative_difference(a: np.ndarray, b: np.ndarray) -> float:
    scale = max(float(np.max(np.abs(a))), float(np.max(np.abs(b))), 1e-12)
    return float(np.max(np.abs(a - b)) / scale)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_jsonable) + "\n", encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    raise TypeError(f"Cannot serialise {type(value).__name__}.")


def run_stage_0(
    root: Path,
    output_dir: Path | None = None,
    *,
    hours: Sequence[int] | None = None,
    radial_cells: int | None = None,
    cartesian_cells: int | None = 80,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Record the plan's stage 0: error models, timing, grid, solver and symmetry checks.

    ``hours``, ``radial_cells`` and ``cartesian_cells`` default to the plan's
    declarations; smaller values exist for tests and must be recorded as such.
    ``cartesian_cells=None`` skips the symmetry check and records it as not run.
    """

    say = log or (lambda message: None)
    plan = load_plan(root)
    output = root / (output_dir or RESULTS_PATH) / "stage_0"
    output.mkdir(parents=True, exist_ok=True)
    geometry = plan["geometry"]
    thresholds = {
        "grid": 0.02,
        "solver": float(geometry["solver_check"]["max_relative_difference"]),
        "symmetry": 0.03,
    }
    hour_list = list(hours) if hours is not None else list(range(1, 63))
    cells = int(radial_cells or geometry["domain"]["cells"])
    values = dict(STAGE_0_CHECK_VALUES)
    check_within_bounds(plan, values)
    inputs: dict[str, Any] = {
        "plan_sha256": plan["_sha256"],
        "amendments": plan["amendments"],
        "check_values": values,
        "check_values_source": CHECK_SOURCE,
        "check_phi": STAGE_0_CHECK_PHI,
        "hours": hour_list,
        "radial_cells": cells,
        "cartesian_cells": cartesian_cells,
        "as_declared": hours is None and radial_cells is None and cartesian_cells == 80,
    }
    _write_json(output / "inputs.json", inputs)

    error_models: dict[str, Any] = {}
    for species in plan["data"]["species_order"]:
        observations = load_observations(root, plan, species)
        fitted = fit_error_models(observations, plan)
        error_models[species] = {
            f"{quantity}_{temperature}c_{humidity}rh": {
                **model.to_dict(),
                "excluded_rows": list(observations[(quantity, temperature, humidity)].excluded),
                "rows": len(observations[(quantity, temperature, humidity)].hours),
            }
            for (quantity, temperature, humidity), model in sorted(fitted.items())
        }
        say(f"{species}: error models fitted for {len(fitted)} series, {sum(m.pooled for m in fitted.values())} pooled")
    _write_json(output / "error_models.json", {"plan_sha256": plan["_sha256"], "definition": plan["error_model"], "series": error_models})

    checks: dict[str, Any] = {"plan_sha256": plan["_sha256"], "thresholds": thresholds}
    started = time.perf_counter()
    reference = simulate_condition(plan, values, STAGE_0_CHECK_PHI, hours=hour_list, cells=cells)
    elapsed = time.perf_counter() - started
    reference_observables = observables(reference, plan)
    checks["timing"] = {
        "radial_cells": cells,
        "hours": hour_list[-1],
        "seconds_per_condition": elapsed,
        "nfev": reference.solver_metadata["nfev"],
        "solver": plan_solver(plan).to_dict(),
    }
    checks["reference_observables"] = reference_observables
    say(f"radial reference: {elapsed:.1f} s, {reference.solver_metadata['nfev']} right-hand sides")

    fine = simulate_condition(plan, values, STAGE_0_CHECK_PHI, hours=hour_list, cells=2 * cells)
    fine_observables = observables(fine, plan)
    grid_differences = {
        name: _relative_difference(reference_observables[name], fine_observables[name])
        for name in ("tip_count", "mycelial_area_cm2")
    }
    checks["grid"] = {"cells": [cells, 2 * cells], "relative_differences": grid_differences, "passed": max(grid_differences.values()) <= thresholds["grid"]}
    say(f"grid check: {grid_differences}")

    alternative = simulate_condition(plan, values, STAGE_0_CHECK_PHI, hours=hour_list, cells=cells, solver=plan_solver(plan, "check"))
    alternative_observables = observables(alternative, plan)
    solver_differences = {
        name: _relative_difference(reference_observables[name], alternative_observables[name])
        for name in ("tip_count", "mycelial_area_cm2")
    }
    checks["solver"] = {
        "methods": [plan_solver(plan).method, plan_solver(plan, "check").method],
        "relative_differences": solver_differences,
        "passed": max(solver_differences.values()) <= thresholds["solver"],
    }
    say(f"solver check: {solver_differences}")

    if cartesian_cells is None:
        checks["symmetry"] = {"status": "not run", "reason": "cartesian reference skipped by the caller"}
    else:
        started = time.perf_counter()
        planar = simulate_condition(plan, values, STAGE_0_CHECK_PHI, hours=hour_list, geometry="cartesian", cells=cartesian_cells, solver=plan_solver(plan, "check"))
        planar_elapsed = time.perf_counter() - started
        planar_observables = observables(planar, plan)
        symmetry_differences = {
            name: _relative_difference(reference_observables[name], planar_observables[name])
            for name in ("tip_count", "mycelial_area_cm2")
        }
        checks["symmetry"] = {
            "status": "run",
            "cartesian_cells": cartesian_cells,
            "cartesian_cell_mm": 2.0 * float(geometry["domain"]["radius_mm"]) / np.sqrt(2.0) / cartesian_cells,
            "cartesian_seconds": planar_elapsed,
            "cartesian_nfev": planar.solver_metadata["nfev"],
            "relative_differences": symmetry_differences,
            "cartesian_observables": planar_observables,
            "passed": max(symmetry_differences.values()) <= thresholds["symmetry"],
        }
        say(f"symmetry check: {symmetry_differences} in {planar_elapsed:.0f} s")
    _write_json(output / "checks.json", checks)
    return {"inputs": inputs, "checks": checks, "error_models": error_models}


__all__ = [
    "CHECK_SOURCE",
    "DATASET_DIR",
    "PLAN_PATH",
    "RESULTS_PATH",
    "SCALED_SYMBOLS",
    "SHARED_SYMBOLS",
    "STAGE_0_CHECK_PHI",
    "STAGE_0_CHECK_VALUES",
    "ColonyComparisonError",
    "ConditionObservations",
    "ErrorModel",
    "check_within_bounds",
    "colony_grid",
    "colony_model",
    "file_digest",
    "fit_error_models",
    "initial_fields",
    "load_observations",
    "load_plan",
    "observables",
    "plan_bounds",
    "plan_parameter_units",
    "plan_solver",
    "run_stage_0",
    "scaled_values",
    "simulate_condition",
]
