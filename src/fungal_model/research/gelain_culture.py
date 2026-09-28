"""Bounded Gelain 2020 culture benchmark, not a general fungal physiology model.

Two explicit study hypotheses are supported: a projection of the deposited
source model, and effective Monod growth with apparent yield and biomass loss.
Numeric kernels use hours and g/L after unit/provenance checks at the boundary.
No activity-to-enzyme conversion or viable/induced biomass mapping is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.data import load_experiment_dataset

MATURITY = "exploratory_software_tested"
REDUCED_UNITS = {"mu": "1/hour", "K": "gram/liter", "Y": "dimensionless", "kd": "1/hour"}
SOURCE_UNITS = {"mu": "1/hour", "K": "gram/liter", "Xmax": "gram/liter", "d": "1/hour",
                "Kd": "gram/liter", "alpha": "liter/gram"}
INDUCTION_UNITS = {"mue": "1/hour", "Ke": "gram/liter", "Amax": "gram/liter",
                   "kda": "1/hour", "beta": "liter/gram"}


def source_projection_rates(state: np.ndarray, p: Mapping[str, float], *, family: str,
                            deposited_glycerol: bool) -> list[float]:
    """Shared numeric kernel for the literal source X/S/A projection (h, g/L)."""
    x, s = max(float(state[0]), 0.0), max(float(state[1]), 0.0)
    growth = p["mu"] * s / (p["K"] + s) * x
    growth *= 1 - x / p["Xmax"]
    death = p["d"] * x
    if family == "cellulose" or deposited_glycerol:
        death *= s / (s + p["Kd"])
    uptake = p["alpha"] * growth * x
    if family == "cellulose":
        a = max(float(state[2]), 0.0)
        production = p["mue"] * s / (s + p["Ke"]) * (1 - a / p["Amax"]) * x
        return [growth - death, -uptake - p["beta"] * production * a, production - p["kda"] * a]
    return [growth - death, -uptake]


class CultureBenchmarkError(ValueError):
    """An explicit study assumption, input, fit or integration failed."""


def _array(value: Quantity, units: str, name: str) -> np.ndarray:
    result = np.asarray(assert_compatible(value, units, name).magnitude, dtype=float)
    if not np.all(np.isfinite(result)):
        raise CultureBenchmarkError(f"{name} must be finite.")
    return result


def _scalar(value: Quantity, units: str, name: str) -> float:
    result = _array(value, units, name)
    if result.ndim or result < 0:
        raise CultureBenchmarkError(f"{name} must be a nonnegative scalar.")
    return float(result)


@dataclass(frozen=True)
class CultureDesign:
    """Prediction inputs only; deliberately contains no response observations."""

    condition_id: str
    family: str
    times: Quantity
    initial_biomass: Quantity
    initial_substrate: Quantity
    source: str

    def __post_init__(self) -> None:
        if not has_text(self.source) or not has_text(self.condition_id):
            raise CultureBenchmarkError("Condition identity and source are required.")
        if self.family not in {"glycerol", "cellulose"}:
            raise CultureBenchmarkError("This study supports only its two named substrate conditions.")
        t = _array(self.times, "hour", "times")
        if t.ndim != 1 or not t.size or t[0] < 0 or t[-1] <= 0 or np.any(np.diff(t) <= 0):
            raise CultureBenchmarkError("Times must increase from >=0 to a positive endpoint.")
        _scalar(self.initial_biomass, "gram/liter", "initial_biomass")
        _scalar(self.initial_substrate, "gram/liter", "initial_substrate")


@dataclass(frozen=True)
class CultureObservations:
    design: CultureDesign
    values: Quantity  # time x [measured biomass, measured substrate]

    def __post_init__(self) -> None:
        values = _array(self.values, "gram/liter", "observations")
        if values.shape != (len(self.design.times.magnitude), 2) or np.any(values < 0):
            raise CultureBenchmarkError("Observations must be a nonnegative time x two-observable array.")


@dataclass(frozen=True)
class CultureTrajectory:
    time: Quantity
    biomass: Quantity
    substrate: Quantity
    induced_proxy: Quantity | None
    model: str
    source: str
    hypothesis_source: str
    solver: Mapping[str, Any]
    maturity: str = MATURITY

    @property
    def observations_g_l(self) -> np.ndarray:
        return np.column_stack([self.biomass.to("gram/liter").magnitude,
                                self.substrate.to("gram/liter").magnitude])


def parameters_from_records(records: Sequence[Mapping[str, Any]], *, source: str | None = None) -> ParameterSet:
    """Preserve explicit unknown uncertainty; do not promote fitted constants."""
    return ParameterSet([
        Parameter(name=str(r["symbol"]), symbol=str(r["symbol"]), value=r["value"], units=str(r["units"]),
                  uncertainty=None, source=source or r.get("source"), confidence_level="unknown",
                  notes="Exploratory culture benchmark; uncertainty unavailable; no registry promotion.")
        for r in records
    ])


def simulate_culture(
    design: CultureDesign, parameters: ParameterSet, *, model: str, hypothesis_source: str,
    method: str = "LSODA", rtol: float = 1e-8, atol: Quantity = Q_(1e-10, "gram/liter"),
) -> CultureTrajectory:
    """Integrate one explicitly labelled hypothesis.

    ``effective_monod_loss_v1``: g=mu*S/(K+S)*X; X'=g-kd*X; S'=-g/Y.
    ``source_deposited_v1``: source Eqs 2-8 projected onto X,S,A, retaining
    the deposited glycerol death Monod term. ``source_paper_v1`` instead
    implements Eq 5 literally (constant glycerol death). Activities have no
    feedback to these states in the source; they are not predicted here.

    Negative trial states are floored only inside the RHS. Returned states are
    never clipped; materially negative, incomplete and failed solutions raise.
    Tiny negative solver roundoff is reported in solver metadata.
    """
    if not has_text(hypothesis_source):
        raise CultureBenchmarkError("An explicit hypothesis_source is required.")
    if model not in {"effective_monod_loss_v1", "source_deposited_v1", "source_paper_v1"}:
        raise CultureBenchmarkError(f"Unsupported study model: {model}")
    if method not in {"LSODA", "DOP853", "BDF", "Radau", "RK45"}:
        raise CultureBenchmarkError(f"Unsupported solver: {method}")
    if not np.isfinite(rtol) or not 0 < rtol < 1:
        raise CultureBenchmarkError("rtol must be finite and between zero and one.")
    abs_tol = _scalar(atol, "gram/liter", "atol")
    if abs_tol <= 0:
        raise CultureBenchmarkError("atol must be positive.")
    parameters.validate(require_values=True)
    reduced = model == "effective_monod_loss_v1"
    expected = dict(REDUCED_UNITS if reduced else SOURCE_UNITS)
    if not reduced and design.family == "cellulose":
        expected.update(INDUCTION_UNITS)
    p = {k: _scalar(parameters.require_quantity(k, units), units, k) for k, units in expected.items()}
    positive = {"K", "Y"} if reduced else {"K", "Xmax", "Kd"}
    if not reduced and design.family == "cellulose":
        positive.update({"Ke", "Amax"})
    if any(p[k] <= 0 for k in positive) or (reduced and p["Y"] > 1):
        raise CultureBenchmarkError("Saturation/capacity constants must be positive; apparent yield is in (0,1].")
    times = _array(design.times, "hour", "times")
    x0 = _scalar(design.initial_biomass, "gram/liter", "initial_biomass")
    s0 = _scalar(design.initial_substrate, "gram/liter", "initial_substrate")
    if not reduced and x0 > p["Xmax"]:
        raise CultureBenchmarkError("Source projection requires initial biomass <= Xmax.")
    induction = not reduced and design.family == "cellulose"

    def rhs(_t: float, state: np.ndarray) -> list[float]:
        x, s = max(float(state[0]), 0.0), max(float(state[1]), 0.0)
        growth = p["mu"] * s / (p["K"] + s) * x
        if reduced:
            return [growth - p["kd"] * x, -growth / p["Y"]]
        return source_projection_rates(state, p, family=design.family,
                                       deposited_glycerol=model == "source_deposited_v1")

    y0 = [x0, s0, 0.0] if induction else [x0, s0]
    # Resolve the actual deposited tiny death constant, rather than letting
    # absolute tolerance erase its late-time effect. Numerical choice, not biology.
    substrate_atol = min(abs_tol, p["Kd"] * 1e-6) if not reduced else abs_tol
    atol_vector = [abs_tol, substrate_atol] + ([abs_tol] if induction else [])
    solution = solve_ivp(rhs, (0.0, float(times[-1])), y0, t_eval=times, method=method,
                         rtol=rtol, atol=atol_vector)
    values = np.asarray(solution.y, dtype=float)
    if (not solution.success or values.shape != (len(y0), times.size)
            or not np.all(np.isfinite(values))):
        raise CultureBenchmarkError(f"Integration failed or returned incomplete/nonfinite states: {solution.message}")
    if np.any(values < -10 * np.asarray(atol_vector)[:, None]):
        raise CultureBenchmarkError("Integration returned materially negative states.")
    return CultureTrajectory(
        Q_(times, "hour"), Q_(values[0], "gram/liter"), Q_(values[1], "gram/liter"),
        Q_(values[2], "gram/liter") if induction else None, model, design.source, hypothesis_source,
        {"method": method, "rtol": rtol, "atol_g_l": atol_vector, "nfev": int(solution.nfev),
         "minimum_state_g_l": float(values.min()), "negative_roundoff_count": int(np.sum(values < 0))},
    )


def load_culture_conditions(root: Path) -> list[CultureObservations]:
    """Use reviewed ExperimentDataset loading; preserve means and missing errors."""
    result = []
    for family, doses in (("glycerol", (5, 10, 20)), ("cellulose", (10, 20, 30))):
        for dose in doses:
            name = f"gelain_2020_{family}_{dose}gl"
            path = root / "data/experiments/literature/gelain_2020_t_harzianum" / f"{name}.yml"
            metadata = yaml.safe_load(path.read_text())
            dataset = load_experiment_dataset(path)
            if not dataset.validate().passed:
                raise CultureBenchmarkError(f"Invalid dataset: {path}")
            series = {s.measurement_id: s for s in dataset.measurements}
            arrays, grids = [], []
            for observable in ("biomass", "substrate"):
                item = series[observable]
                grids.append(Q_([p.time for p in item.points], item.time_units).to("hour").magnitude)
                arrays.append(Q_([p.value for p in item.points], item.value_units).to("gram/liter").magnitude)
            if not np.array_equal(*grids):
                raise CultureBenchmarkError("This study requires aligned biomass and substrate sampling times.")
            initial = metadata["conditions"]
            x, s = initial["source_initial_biomass"], initial["nominal_initial_substrate"]
            design = CultureDesign(name, family, Q_(grids[0], "hour"), Q_(x["value"], x["units"]),
                                   Q_(s["value"], s["units"]), "doi:10.17632/shd3wcczsr.2; " + name)
            result.append(CultureObservations(design, Q_(np.column_stack(arrays), "gram/liter")))
    return result


def fit_effective_culture(
    training: Sequence[CultureObservations], plan: Mapping[str, Any], *, weighting: str,
) -> dict[str, Any]:
    """Fit ONLY supplied training responses, using log parameters and fixed starts.

    Scales are loss weights, never measurement SD. A failed start is recorded;
    all-start failure raises. Jacobian diagnostics describe this objective, not
    biological identifiability or a likelihood. No held-out response is accepted.
    """
    if not training or len({c.design.family for c in training}) != 1:
        raise CultureBenchmarkError("Fit one substrate family at a time with at least one training condition.")
    ids = [c.design.condition_id for c in training]
    if len(set(ids)) != len(ids):
        raise CultureBenchmarkError("Training condition identities must be unique.")
    spec = plan["parameters"]
    if [p["symbol"] for p in spec] != list(REDUCED_UNITS):
        raise CultureBenchmarkError("Plan must specify ordered mu, K, Y, kd parameters.")
    lo = np.array([_scalar(Q_(r["lower"], r["units"]), REDUCED_UNITS[r["symbol"]], r["symbol"]) for r in spec])
    hi = np.array([_scalar(Q_(r["upper"], r["units"]), REDUCED_UNITS[r["symbol"]], r["symbol"]) for r in spec])
    if np.any(lo <= 0) or np.any(hi <= lo) or hi[2] > 1:
        raise CultureBenchmarkError("Search bounds must be positive and ordered with Y <= 1.")
    starts, max_nfev = plan["starts"], plan["max_nfev"]
    if not isinstance(starts, int) or starts < 1 or not isinstance(max_nfev, int) or max_nfev < 1:
        raise CultureBenchmarkError("starts and max_nfev must be positive integers.")
    difference_step = plan["log_parameter_difference_step"]
    if not np.isfinite(difference_step) or not 0 < difference_step < 1:
        raise CultureBenchmarkError("log_parameter_difference_step must be between zero and one.")
    if not has_text(plan.get("parameter_source")) or not has_text(plan.get("hypothesis")):
        raise CultureBenchmarkError("Plan must declare parameter provenance and the hypothesis.")
    measured = [c.values.to("gram/liter").magnitude for c in training]
    if weighting == "training_max":
        scales = np.max(np.concatenate(measured), axis=0)
        if np.any(scales <= 0):
            raise CultureBenchmarkError("Training-derived normalization scales must be positive.")
    elif weighting == "equal_g_l":
        scales = np.ones(2)  # Explicit alternative: residuals in units of 1 g/L.
    else:
        raise CultureBenchmarkError(f"Unknown weighting: {weighting}")
    canonical_spec = [{"symbol": key, "units": units} for key, units in REDUCED_UNITS.items()]

    def records(log_parameters: np.ndarray) -> list[dict[str, Any]]:
        return [dict(r, value=float(v)) for r, v in zip(canonical_spec, np.exp(log_parameters), strict=True)]

    solver = plan["solver"]

    def residual(log_parameters: np.ndarray) -> np.ndarray:
        params = parameters_from_records(records(log_parameters), source=plan["parameter_source"])
        errors = []
        for condition, values in zip(training, measured, strict=True):
            prediction = simulate_culture(condition.design, params, model="effective_monod_loss_v1",
                                          hypothesis_source=plan["hypothesis"], method=solver["method"],
                                          rtol=solver["rtol"], atol=Q_(solver["atol_g_l"], "gram/liter"))
            errors.append(((prediction.observations_g_l - values) / scales).ravel())
        return np.concatenate(errors)

    lower, upper = np.log(lo), np.log(hi)
    rng = np.random.default_rng(plan["seed"])
    guesses = [(lower + upper) / 2] + [rng.uniform(lower, upper) for _ in range(starts - 1)]
    trials, successes = [], []
    for index, guess in enumerate(guesses):
        try:
            fit = least_squares(residual, guess, bounds=(lower, upper), max_nfev=max_nfev,
                                diff_step=difference_step,
                                ftol=1e-8, xtol=1e-8, gtol=1e-8)
            objective = float(np.dot(fit.fun, fit.fun))
            trials.append({"start": index, "success": bool(fit.success), "message": str(fit.message),
                           "nfev": int(fit.nfev), "objective": objective,
                           "initial_parameters": records(guess), "parameters": records(fit.x)})
            if fit.success and np.isfinite(objective):
                successes.append((objective, index, fit))
        except (CultureBenchmarkError, FloatingPointError) as exc:
            trials.append({"start": index, "success": False, "message": str(exc)})
    if not successes:
        raise CultureBenchmarkError(f"All optimization starts failed: {trials}")
    objective, best_index, best = min(successes, key=lambda item: item[0])
    singular_values = np.linalg.svd(best.jac, compute_uv=False)
    bound_fraction = (best.x - lower) / (upper - lower)
    return {
        "parameters": records(best.x), "parameter_source": plan["parameter_source"],
        "training_conditions": ids, "weighting": weighting, "normalization_g_l": scales.tolist(),
        "normalization_is_measurement_uncertainty": False, "objective": objective,
        "best_start": best_index, "starts": trials,
        "jacobian_rank": int(np.linalg.matrix_rank(best.jac)),
        "jacobian_singular_values": singular_values.tolist(),
        "jacobian_condition_number": (float(singular_values[0] / singular_values[-1])
                                      if singular_values[-1] > 0 else None),
        "near_bounds": [r["symbol"] for r, f in zip(spec, bound_fraction, strict=True) if min(f, 1-f) < 0.001],
        "uncertainty": None, "maturity": MATURITY,
    }


def predict_effective_culture(design: CultureDesign, fit: Mapping[str, Any], plan: Mapping[str, Any],
                              *, solver_key: str = "solver") -> CultureTrajectory:
    solver = plan[solver_key]
    return simulate_culture(design, parameters_from_records(fit["parameters"], source=fit["parameter_source"]),
                            model="effective_monod_loss_v1", hypothesis_source=plan["hypothesis"],
                            method=solver["method"], rtol=solver["rtol"], atol=Q_(solver["atol_g_l"], "gram/liter"))


def score_predictions(predicted: np.ndarray, observed: Quantity, scales: Sequence[float]) -> dict[str, Any]:
    """Descriptive errors only. Positive scaling constants are not empirical SD."""
    values = _array(observed, "gram/liter", "observed")
    prediction, weights = np.asarray(predicted, dtype=float), np.asarray(scales, dtype=float)
    if (values.ndim != 2 or values.shape[1] != 2 or values.shape[0] == 0 or prediction.shape != values.shape
            or not np.all(np.isfinite(prediction)) or weights.shape != (2,)
            or not np.all(np.isfinite(weights)) or np.any(weights <= 0)):
        raise CultureBenchmarkError("Prediction shape and finite positive loss scales are required.")
    error = prediction - values
    return {"n": int(values.size), "rmse_g_l": np.sqrt(np.mean(error**2, axis=0)).tolist(),
            "mae_g_l": np.mean(abs(error), axis=0).tolist(), "bias_g_l": np.mean(error, axis=0).tolist(),
            "normalized_rmse": float(np.sqrt(np.mean((error/weights)**2))),
            "observable_order": ["biomass", "substrate"], "error_model": None}
