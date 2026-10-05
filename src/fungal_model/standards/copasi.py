"""Reproduce a FungMod-exported PEtab problem in COPASI.

COPASI is an independent simulator and parameter-estimation tool. This module
imports a PEtab problem written by :func:`fungal_model.standards.conditions_to_petab`
with COPASI's PEtab importer, simulates it, fits it, and reports the results
next to FungMod's own predictions so the two solvers can be compared on the
same objective:

``J(theta) = sum over measurements of ((simulation - measurement) / sigma)**2``

where ``sigma`` is the noise standard deviation the PEtab observable table
declares. COPASI weights a dependent column by a multiplier of the squared
residual; its PEtab importer (``copasi_petab_importer``) stores ``sigma`` in
that slot, which would weight by ``sigma`` instead of ``1/sigma**2``. The
runner therefore rewrites every dependent column's weight to ``1/sigma**2``
and switches off COPASI's per-experiment weight normalisation before any
evaluation, and records that it did so.

The optional dependencies (``python-copasi``, ``copasi-basico``,
``copasi-petab-importer``) are the ``copasi`` extra. Nothing here is imported
unless :func:`reproduce_in_copasi` or :func:`simulate_in_copasi` is called.
"""

from __future__ import annotations

import csv
import json
import locale
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

COPASI_EXTRA = "copasi"
DEFAULT_METHOD = "Levenberg - Marquardt"

Predictor = Callable[[str, np.ndarray], Mapping[str, np.ndarray]]
"""``predictor(condition_id, times_in_seconds) -> {observable_id: values}`` for the cross-solver check."""


class CopasiUnavailableError(RuntimeError):
    """Raised when the ``copasi`` extra is not installed."""


class CopasiReproductionError(RuntimeError):
    """Raised when a PEtab problem cannot be reproduced in COPASI faithfully."""


def _require_copasi() -> tuple[Any, Any, Any]:
    """Import the COPASI stack without letting it change the process text encoding.

    Importing ``COPASI`` calls ``setlocale(LC_ALL, "C")`` in its static
    initialiser, which switches Python's preferred text encoding to ASCII
    for every later ``open()`` call that names no encoding. COPASI needs
    the ``C`` numeric locale for its own parsing, so only ``LC_CTYPE`` is
    restored here.
    """

    ctype = locale.setlocale(locale.LC_CTYPE)
    try:
        import COPASI
        import basico
        import copasi_petab_importer
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised when the extra is absent
        raise CopasiUnavailableError(
            "COPASI reproduction requires the optional 'copasi' dependency group. "
            f"Install it with: pip install fungmod[{COPASI_EXTRA}]"
        ) from exc
    finally:
        if locale.setlocale(locale.LC_CTYPE) != ctype:
            locale.setlocale(locale.LC_CTYPE, ctype)
    return COPASI, basico, copasi_petab_importer


def copasi_available() -> bool:
    try:
        _require_copasi()
    except CopasiUnavailableError:
        return False
    return True


@dataclass(frozen=True)
class PetabObservableSpec:
    observable_id: str
    species_id: str
    factor: float
    noise: float | None


@dataclass(frozen=True)
class PetabTables:
    """The parts of a FungMod-exported PEtab problem the runner needs."""

    problem_yaml: Path
    sbml_path: Path
    observables: dict[str, PetabObservableSpec]
    conditions: dict[str, dict[str, float]]
    measurements: list[dict[str, Any]]
    parameters: list[dict[str, Any]]

    @property
    def condition_ids(self) -> tuple[str, ...]:
        return tuple(self.conditions)

    @property
    def estimated(self) -> list[dict[str, Any]]:
        return [row for row in self.parameters if int(row["estimate"]) == 1]

    def measurement_times(self, condition_id: str) -> np.ndarray:
        times = sorted({float(row["time"]) for row in self.measurements if row["simulationConditionId"] == condition_id})
        return np.asarray(times, dtype=float)

    def noise_of(self, row: Mapping[str, Any]) -> float:
        observable = self.observables[str(row["observableId"])]
        if observable.noise is not None:
            return observable.noise
        value = row.get("noiseParameters")
        if value in (None, ""):
            raise CopasiReproductionError(
                f"Measurement of {observable.observable_id!r} has no noise scale in the observable or measurement table."
            )
        return float(value)


_FORMULA = re.compile(r"^(?:(?P<factor>[0-9.eE+-]+)\s*\*\s*)?(?P<species>[A-Za-z_][A-Za-z0-9_]*)$")


def _read_tsv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def read_petab_tables(problem_yaml: str | Path) -> PetabTables:
    """Read a PEtab problem in the layout :func:`conditions_to_petab` writes."""

    problem_yaml = Path(problem_yaml)
    problem = yaml.safe_load(problem_yaml.read_text(encoding="utf-8"))
    base = problem_yaml.parent
    entry = problem["problems"][0]
    observables: dict[str, PetabObservableSpec] = {}
    for row in _read_tsv(base / entry["observable_files"][0]):
        match = _FORMULA.match(str(row["observableFormula"]).strip())
        if match is None:
            raise CopasiReproductionError(
                f"Observable {row['observableId']!r} formula {row['observableFormula']!r} is not "
                "'[factor *] species', the form FungMod exports."
            )
        noise_text = str(row.get("noiseFormula", "")).strip()
        try:
            noise: float | None = float(noise_text)
        except ValueError:
            noise = None
        observables[str(row["observableId"])] = PetabObservableSpec(
            str(row["observableId"]), match["species"], float(match["factor"] or 1.0), noise
        )
    conditions: dict[str, dict[str, float]] = {}
    for row in _read_tsv(base / entry["condition_files"][0]):
        conditions[str(row["conditionId"])] = {
            key: float(value) for key, value in row.items() if key not in {"conditionId", "conditionName"}
        }
    measurements = _read_tsv(base / entry["measurement_files"][0])
    parameters = _read_tsv(base / problem["parameter_file"])
    return PetabTables(
        problem_yaml, base / entry["sbml_files"][0], observables, conditions, measurements, parameters
    )


def petab_objective(tables: PetabTables, predictions: Mapping[str, Mapping[str, np.ndarray]]) -> dict[str, Any]:
    """``sum(((prediction - measurement) / sigma)**2)`` over every measurement row.

    ``predictions[condition_id][observable_id]`` holds values aligned with
    :meth:`PetabTables.measurement_times` of that condition.
    """

    total = 0.0
    per_observable: dict[str, float] = {}
    count = 0
    for condition_id in tables.condition_ids:
        times = tables.measurement_times(condition_id)
        for row in tables.measurements:
            if row["simulationConditionId"] != condition_id:
                continue
            observable_id = str(row["observableId"])
            position = int(np.searchsorted(times, float(row["time"])))
            predicted = float(predictions[condition_id][observable_id][position])
            residual = (predicted - float(row["measurement"])) / tables.noise_of(row)
            total += residual * residual
            per_observable[observable_id] = per_observable.get(observable_id, 0.0) + residual * residual
            count += 1
    return {"objective": total, "per_observable": per_observable, "measurements": count}


def _set_column_weights(COPASI: Any, basico: Any, tables: PetabTables) -> list[dict[str, Any]]:
    """Rewrite COPASI's dependent-column weights to ``1 / sigma**2`` and disable normalisation."""

    model = basico.get_current_model()
    problem = model.getTask("Parameter Estimation").getProblem()
    experiments = problem.getExperimentSet()
    rewritten: list[dict[str, Any]] = []
    for index in range(experiments.getExperimentCount()):
        experiment = experiments.getExperiment(index)
        condition_id = experiment.getObjectName()
        object_map = experiment.getObjectMap()
        experiment.setNormalizeWeightsPerExperiment(False)
        for column in range(object_map.getLastNotIgnoredColumn() + 1):
            if object_map.getRole(column) != COPASI.CExperiment.dependent:
                continue
            target = str(object_map.getObjectCN(column))
            observable_id = next(
                (spec.observable_id for spec in tables.observables.values() if f"Values[{spec.observable_id}]" in target),
                None,
            )
            if observable_id is None:
                raise CopasiReproductionError(f"COPASI column {column} of {condition_id!r} maps to {target!r}, not a PEtab observable.")
            sigmas = {
                tables.noise_of(row)
                for row in tables.measurements
                if row["simulationConditionId"] == condition_id and row["observableId"] == observable_id
            }
            if len(sigmas) != 1:
                raise CopasiReproductionError(
                    f"COPASI weights one dependent column with one value; {observable_id!r} in {condition_id!r} "
                    f"has {len(sigmas)} noise scales."
                )
            sigma = next(iter(sigmas))
            imported = float(object_map.getScale(column))
            object_map.setScale(column, 1.0 / (sigma * sigma))
            rewritten.append(
                {"condition": condition_id, "observable": observable_id, "sigma": sigma, "importer_weight": imported, "weight": 1.0 / (sigma * sigma)}
            )
        experiment.calculateWeights()
    return rewritten


INTEGRATOR_RELATIVE_TOLERANCE = 1e-9
INTEGRATOR_ABSOLUTE_TOLERANCE = 1e-12


_CONVERSION_SCRIPT = """
import sys
from copasi_petab_importer import PEtabConverter
converter = PEtabConverter.from_yaml(sys.argv[1], out_dir=sys.argv[2], out_name=sys.argv[3])
converter.show_progress_of_fit = False
converter.show_result = False
converter.save_report = False
converter.convert()
print(converter.copasi_file)
"""


def convert_with_importer(problem_yaml: Path, output_dir: Path, *, out_name: str = "copasi_problem") -> Path:
    """Run COPASI's PEtab importer in a fresh interpreter and return the ``.cps`` file it wrote.

    The importer walks libSBML ``ASTNode`` objects. Once ``libsedml`` has been
    imported in the same process (FungMod's SED-ML export does), SWIG's shared
    proxy registry hands it the wrong proxies and the conversion fails, so it
    runs isolated; its stdout names the file.
    """

    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-c", _CONVERSION_SCRIPT, str(problem_yaml), str(output_dir), out_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise CopasiReproductionError(
            f"COPASI's PEtab importer failed (exit {completed.returncode}):\n{completed.stderr.strip()[-2000:]}"
        )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines or not Path(lines[-1]).exists():
        raise CopasiReproductionError("COPASI's PEtab importer did not report the file it wrote.")
    return Path(lines[-1])


def _condition_columns(basico: Any, tables: PetabTables) -> dict[str, tuple[str, float]]:
    """For every condition column: whether it is a species or a parameter, and COPASI's current value."""

    species = basico.get_species()
    parameters = basico.get_parameters()
    columns = {column for values in tables.conditions.values() for column in values}
    baseline: dict[str, tuple[str, float]] = {}
    for column in sorted(columns):
        if column in species.index:
            baseline[column] = ("species", float(species.loc[column, "initial_concentration"]))
        elif column in parameters.index:
            baseline[column] = ("parameter", float(parameters.loc[column, "initial_value"]))
        else:
            raise CopasiReproductionError(f"Condition column {column!r} is neither a species nor a parameter in COPASI.")
    return baseline


def _apply_condition(basico: Any, baseline: Mapping[str, tuple[str, float]], values: Mapping[str, float]) -> None:
    for column, (kind, default) in baseline.items():
        value = float(values.get(column, default))
        if kind == "species":
            basico.set_species(column, exact=True, initial_concentration=value)
        else:
            basico.set_parameters(column, exact=True, initial_value=value)


def set_integrator_tolerances(
    basico: Any, *, relative: float = INTEGRATOR_RELATIVE_TOLERANCE, absolute: float = INTEGRATOR_ABSOLUTE_TOLERANCE
) -> dict[str, Any]:
    """Tighten COPASI's time-course integrator (used by the estimation task too) and return its settings."""

    basico.set_task_settings("Time-Course", {"method": {"Relative Tolerance": float(relative), "Absolute Tolerance": float(absolute)}})
    settings = basico.get_task_settings("Time-Course")
    method = dict(settings.get("method", {})) if isinstance(settings, Mapping) else {}
    if float(method.get("Relative Tolerance", np.nan)) != float(relative):
        raise CopasiReproductionError("COPASI did not accept the requested integrator tolerances.")
    return method


def simulate_in_copasi(basico: Any, tables: PetabTables) -> dict[str, dict[str, np.ndarray]]:
    """Observable time courses at the measurement times for every condition, at COPASI's current parameter values."""

    baseline = _condition_columns(basico, tables)
    results: dict[str, dict[str, np.ndarray]] = {}
    try:
        for condition_id, values in tables.conditions.items():
            _apply_condition(basico, baseline, values)
            times = tables.measurement_times(condition_id)
            course = basico.run_time_course(
                values=times.tolist(),
                start_time=float(times[0]),
                duration=float(times[-1] - times[0]),
                use_initial_values=True,
                r_tol=INTEGRATOR_RELATIVE_TOLERANCE,
                a_tol=INTEGRATOR_ABSOLUTE_TOLERANCE,
            )
            results[condition_id] = {
                spec.observable_id: spec.factor * course[spec.species_id].to_numpy(dtype=float)
                for spec in tables.observables.values()
            }
    finally:
        _apply_condition(basico, baseline, {})
    return results


def _fit_item_names(basico: Any, tables: PetabTables) -> dict[str, str]:
    """Map COPASI fit-item names to PEtab parameter identifiers, refusing dangling items."""

    model_values = set(basico.get_parameters().index)
    items = basico.get_fit_parameters()
    mapping: dict[str, str] = {}
    for name in items.index:
        parameter_id = str(name)[len("Values[") : -1] if str(name).startswith("Values[") else str(name)
        if parameter_id not in model_values:
            raise CopasiReproductionError(f"COPASI fit item {name!r} does not address a model value.")
        mapping[str(name)] = parameter_id
    expected = {row["parameterId"] for row in tables.estimated}
    if set(mapping.values()) != expected:
        raise CopasiReproductionError(
            f"COPASI fit items {sorted(mapping.values())} differ from the PEtab estimated parameters {sorted(expected)}."
        )
    return mapping


def _set_parameter_values(basico: Any, values: Mapping[str, float]) -> None:
    for parameter_id, value in values.items():
        basico.set_parameters(parameter_id, exact=True, initial_value=float(value))


def _run_fit(basico: Any, method: str, starts: Mapping[str, float], names: Mapping[str, str]) -> dict[str, Any]:
    items = basico.get_fit_parameters()
    items["start"] = [float(starts[names[str(name)]]) for name in items.index]
    basico.set_fit_parameters(items)
    solution = basico.run_parameter_estimation(method=method, update_model=False)
    statistic = basico.get_fit_statistic()
    values = {names[str(name)]: float(solution.loc[name, "sol"]) for name in solution.index}
    return {
        "start": {names[str(name)]: float(items.loc[name, "start"]) for name in items.index},
        "values": values,
        "copasi_objective": float(statistic["obj"]),
        "function_evaluations": int(statistic["f_evals"]),
        "failed_evaluations": int(statistic["failed_evals_exception"]) + int(statistic["failed_evals_nan"]),
    }


@dataclass
class CopasiReproduction:
    """What :func:`reproduce_in_copasi` produced."""

    copasi_file: Path
    versions: dict[str, str]
    method: dict[str, Any]
    weights: list[dict[str, Any]]
    nominal: dict[str, float]
    simulation_at_nominal: dict[str, Any]
    local_fit: dict[str, Any]
    starts: list[dict[str, Any]] = field(default_factory=list)
    best: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "copasi_file": self.copasi_file.name,
            "versions": self.versions,
            "method": self.method,
            "weights": self.weights,
            "nominal": self.nominal,
            "simulation_at_nominal": self.simulation_at_nominal,
            "local_fit": self.local_fit,
            "starts": self.starts,
            "best": self.best,
        }


def reproduce_in_copasi(
    problem_yaml: str | Path,
    output_dir: str | Path,
    *,
    predictor: Predictor | None = None,
    method: str = DEFAULT_METHOD,
    starts: int = 0,
    seed: int = 0,
    log: Callable[[str], None] | None = None,
) -> CopasiReproduction:
    """Import, simulate and fit a FungMod PEtab problem in COPASI.

    Steps: convert with COPASI's PEtab importer; rewrite the column weights to
    ``1/sigma**2``; simulate every condition at the nominal parameter values
    and, when ``predictor`` is given, compare with FungMod's predictions on the
    PEtab objective; run one local fit from the nominal values; run ``starts``
    further fits from log-uniform random starting points inside the bounds.
    Every fitted optimum is re-evaluated with COPASI time courses on the PEtab
    objective so the recorded objective does not rely on COPASI's internal
    bookkeeping.
    """

    COPASI, basico, importer = _require_copasi()
    problem_yaml = Path(problem_yaml)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = read_petab_tables(problem_yaml)
    say = log or (lambda message: None)

    copasi_file = convert_with_importer(problem_yaml, output_dir)
    basico.load_model(str(copasi_file))
    names = _fit_item_names(basico, tables)
    weights = _set_column_weights(COPASI, basico, tables)
    integrator = set_integrator_tolerances(basico)
    basico.save_model(str(copasi_file))
    say(f"COPASI problem written to {copasi_file.name}; {len(weights)} column weights set to 1/sigma^2")

    nominal = {row["parameterId"]: float(row["nominalValue"]) for row in tables.estimated}
    _set_parameter_values(basico, nominal)
    copasi_nominal = simulate_in_copasi(basico, tables)
    simulation: dict[str, Any] = {"copasi": petab_objective(tables, copasi_nominal)}
    if predictor is not None:
        fungmod_nominal = {
            condition_id: dict(predictor(condition_id, tables.measurement_times(condition_id)))
            for condition_id in tables.condition_ids
        }
        simulation["fungmod"] = petab_objective(tables, fungmod_nominal)
        scaled: dict[str, float] = {}
        for condition_id in tables.condition_ids:
            for observable_id, spec in tables.observables.items():
                sigma = spec.noise
                if sigma is None:
                    rows = [row for row in tables.measurements if row["simulationConditionId"] == condition_id and row["observableId"] == observable_id]
                    sigma = max(tables.noise_of(row) for row in rows) if rows else 1.0
                difference = np.abs(copasi_nominal[condition_id][observable_id] - np.asarray(fungmod_nominal[condition_id][observable_id], dtype=float))
                scaled[observable_id] = max(scaled.get(observable_id, 0.0), float(np.max(difference) / sigma))
        simulation["max_abs_difference_over_sigma"] = scaled
        simulation["objective_relative_difference"] = abs(simulation["copasi"]["objective"] - simulation["fungmod"]["objective"]) / max(
            abs(simulation["fungmod"]["objective"]), np.finfo(float).tiny
        )
    say(f"objective at nominal: COPASI {simulation['copasi']['objective']:.10g}" + (f", FungMod {simulation['fungmod']['objective']:.10g}" if "fungmod" in simulation else ""))

    def evaluate(values: Mapping[str, float]) -> dict[str, Any]:
        _set_parameter_values(basico, values)
        return petab_objective(tables, simulate_in_copasi(basico, tables))

    local = _run_fit(basico, method, nominal, names)
    local["objective"] = evaluate(local["values"])["objective"]
    say(f"local fit from nominal: objective {local['objective']:.10g} after {local['function_evaluations']} evaluations")

    rng = np.random.default_rng(seed)
    bounds = {row["parameterId"]: (float(row["lowerBound"]), float(row["upperBound"])) for row in tables.estimated}
    runs: list[dict[str, Any]] = []
    for index in range(int(starts)):
        start = {
            parameter_id: float(10.0 ** rng.uniform(math.log10(lower), math.log10(upper)))
            for parameter_id, (lower, upper) in bounds.items()
        }
        run = _run_fit(basico, method, start, names)
        run["objective"] = evaluate(run["values"])["objective"]
        run["index"] = index
        runs.append(run)
        say(f"start {index + 1}/{starts}: objective {run['objective']:.10g}")
    candidates = [local, *runs]
    best = min(candidates, key=lambda run: run["objective"])
    _set_parameter_values(basico, nominal)

    settings = basico.get_task_settings("Parameter Estimation")
    method_settings = dict(settings.get("method", {})) if isinstance(settings, Mapping) else {}
    versions = {
        "copasi": str(COPASI.CVersion.VERSION.getVersion()),
        "basico": str(getattr(basico, "__version__", "unknown")),
        "copasi_petab_importer": str(getattr(importer, "__version__", "unknown")),
    }
    result = CopasiReproduction(
        copasi_file=copasi_file,
        versions=versions,
        method={
            "name": method,
            "settings": method_settings,
            "integrator": integrator,
            "parameter_space": "linear (COPASI's importer ignores PEtab parameter scales)",
        },
        weights=weights,
        nominal=nominal,
        simulation_at_nominal=simulation,
        local_fit=local,
        starts=runs,
        best={"objective": best["objective"], "values": best["values"], "source": "local_fit" if best is local else f"start_{best['index']}"},
    )
    (output_dir / "copasi_reproduction.json").write_text(
        json.dumps(result.to_dict(), indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result


__all__ = [
    "COPASI_EXTRA",
    "DEFAULT_METHOD",
    "INTEGRATOR_ABSOLUTE_TOLERANCE",
    "INTEGRATOR_RELATIVE_TOLERANCE",
    "CopasiReproduction",
    "CopasiReproductionError",
    "CopasiUnavailableError",
    "PetabTables",
    "convert_with_importer",
    "copasi_available",
    "petab_objective",
    "read_petab_tables",
    "reproduce_in_copasi",
    "set_integrator_tolerances",
    "simulate_in_copasi",
]
