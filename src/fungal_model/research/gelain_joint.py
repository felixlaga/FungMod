"""Joint culture/activity fitting with explicit training-only error assumptions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares

from fungal_model.calibration.observation_error import GaussianObservationError
from fungal_model.core.units import Q_
from fungal_model.research.gelain_culture import CultureBenchmarkError, CultureDesign, parameters_from_records
from fungal_model.research.gelain_models import (
    CultureMeasurements, OBSERVABLE_UNITS, _integrate, parameter_units, simulate_candidate,
)


def load_joint_cultures(root: Path) -> list[CultureMeasurements]:
    records = json.loads((root / "data/benchmarks/gelain_2020_v2/observations.json").read_text())
    result = []
    source_units = {"biomass": "g/L", "substrate": "g/L", "cellulase_activity": "FPU/L",
                    "beta_glucosidase_activity": "U/L"}
    for r in records:
        for key, observation in r["observations"].items():
            if observation["units"] != source_units[key]:
                raise CultureBenchmarkError("Source assay units changed; review observation mapping.")
        initial = r["initial"]
        design = CultureDesign(r["condition_id"], r["family"], Q_(r["times_h"], "hour"),
                               Q_(initial["biomass"]["value"], initial["biomass"]["units"]),
                               Q_(initial["substrate"]["value"], initial["substrate"]["units"]), r["source"])
        result.append(CultureMeasurements(design,
            {k: Q_(v["values"], OBSERVABLE_UNITS[k]) for k, v in r["observations"].items()},
            {k: Q_(initial[k]["value"], OBSERVABLE_UNITS[k]) for k in r["observations"] if k.endswith("activity")},
            r["source"]))
    return result


def noise_for_condition(condition: CultureMeasurements, scales: np.ndarray, scenario: Mapping[str, Any]) -> GaussianObservationError:
    if scenario["loss"] != "gaussian":
        raise CultureBenchmarkError("A probability model requires an explicit Gaussian error declaration.")
    correlation = np.eye(len(condition.names))
    correlation[0, 1] = correlation[1, 0] = scenario["rho_biomass_substrate"]
    sd = np.asarray(scales)*scenario["relative_sd_to_training_max"]
    return GaussianObservationError(condition.names, tuple(OBSERVABLE_UNITS[k] for k in condition.names),
        {k: Q_(v, OBSERVABLE_UNITS[k]) for k, v in zip(condition.names, sd, strict=True)}, correlation,
        scenario["source"], scenario["error_evidence"])


def _initial(condition: CultureMeasurements) -> np.ndarray:
    return np.array([float(condition.design.initial_biomass.to("gram/liter").magnitude),
                     float(condition.design.initial_substrate.to("gram/liter").magnitude)] +
                    [float(condition.initial_activities[k].to(OBSERVABLE_UNITS[k]).magnitude) for k in condition.names[2:]])


def fit_joint(training: Sequence[CultureMeasurements], plan: Mapping[str, Any], *, model: str, scenario: str,
              warm_start: Sequence[Mapping[str, Any]] | None = None, fixed_scales: Sequence[float] | None = None,
              observation_errors: Mapping[str, GaussianObservationError] | None = None) -> dict[str, Any]:
    """Fit specified training responses only. Missing errors remain unknown.

    Caller-supplied observation_errors supports sourced SD/SE, covariance and
    censoring. Scenario-based errors in the shipped study are assumptions only.
    Hidden response data are never an argument. Failures are returned, not
    converted into apparently successful fits.
    """
    if not training or len({c.design.family for c in training}) != 1:
        raise CultureBenchmarkError("Train on a nonempty set from one substrate family.")
    ids = [c.design.condition_id for c in training]
    if len(set(ids)) != len(ids):
        raise CultureBenchmarkError("Repeated training condition IDs.")
    family, names = training[0].design.family, training[0].names
    if any(c.names != names for c in training):
        raise CultureBenchmarkError("Joint training requires the same observation operators.")
    units = parameter_units(model, family)
    declaration = plan["models"][family][model]
    free, fixed = declaration["parameters"], declaration["fixed_parameters"]
    symbols = [r["symbol"] for r in free + fixed]
    if len(set(symbols)) != len(symbols) or set(symbols) != set(units):
        raise CultureBenchmarkError("Free plus fixed parameters must match the entire model, without duplicates.")
    if not plan.get("parameter_source") or not plan["hypotheses"].get(model):
        raise CultureBenchmarkError("Parameter and hypothesis provenance are mandatory.")
    lo = np.array([Q_(r["lower"], r["units"]).to(units[r["symbol"]]).magnitude for r in free], dtype=float)
    hi = np.array([Q_(r["upper"], r["units"]).to(units[r["symbol"]]).magnitude for r in free], dtype=float)
    if not lo.size or not np.all(np.isfinite(lo+hi)) or np.any(lo <= 0) or np.any(hi <= lo):
        raise CultureBenchmarkError("Finite positive ordered log-parameter bounds are required.")
    fixed_parameters = {r["symbol"]: float(Q_(r["value"], r["units"]).to(units[r["symbol"]]).magnitude) for r in fixed}
    for r, upper in zip(free, hi, strict=True):
        if r["symbol"] in {"Y", "f_retained", "initial_retained_fraction"} and upper > 1:
            raise CultureBenchmarkError("Yield/retained fractions cannot exceed one.")
    if any(not r.get("source") for r in fixed):
        raise CultureBenchmarkError("Every fixed parameter needs an explicit source.")
    if any(not np.isfinite(v) or v < 0 for v in fixed_parameters.values()):
        raise CultureBenchmarkError("Fixed parameters must be finite and nonnegative.")
    if any(fixed_parameters.get(k, 0) > 1 for k in ("Y", "f_retained", "initial_retained_fraction")):
        raise CultureBenchmarkError("Fixed fractions cannot exceed one.")
    if any(v <= 0 for k, v in fixed_parameters.items() if k in {"K","Y","Kh","K_ind","Xmax","Kd","Ke","KI_F","KI_B","Fmax","Bmax"}):
        raise CultureBenchmarkError("Fixed denominator/capacity constants must be positive.")
    scales = (np.max(np.concatenate([c.values for c in training]), axis=0) if fixed_scales is None
              else np.asarray(fixed_scales, dtype=float))
    if scales.shape != (len(names),) or not np.all(np.isfinite(scales)) or np.any(scales <= 0):
        raise CultureBenchmarkError("Training loss scales must be finite positive values for every observable.")
    scenario_spec = plan["scenarios"][scenario]
    if observation_errors is not None and set(observation_errors) != set(ids):
        raise CultureBenchmarkError("Exactly one error model is required for each training condition.")
    noise = (dict(observation_errors) if observation_errors is not None else
             {c.design.condition_id: noise_for_condition(c, scales, scenario_spec) for c in training}
             if scenario_spec["loss"] == "gaussian" else {})
    for c in training:
        if c.design.condition_id in noise:
            error = noise[c.design.condition_id]
            if error.observables != names or error.units != tuple(OBSERVABLE_UNITS[k] for k in names):
                raise CultureBenchmarkError("Error model order and canonical assay units must match the observations.")
            error.arrays(len(c.values))
    if not noise and scenario_spec["loss"] != "training_max":
        raise CultureBenchmarkError("Unsupported loss declaration.")
    solver = plan["solver"]
    entries = [(c, c.values, np.asarray(c.design.times.to("hour").magnitude), _initial(c)) for c in training]

    def numeric(log_values: np.ndarray) -> dict[str, float]:
        return fixed_parameters | {r["symbol"]: float(v) for r, v in zip(free, np.exp(log_values), strict=True)}

    def residual(log_values: np.ndarray) -> np.ndarray:
        parameters = numeric(log_values)
        residuals = []
        for c, observed, times, initial in entries:
            predicted = _integrate(model, family, times, initial, parameters, **solver)[0]
            residuals.append(noise[c.design.condition_id].residuals(predicted, observed) if noise
                             else ((predicted-observed)/scales).ravel())
        return np.concatenate(residuals)

    starts, budget, difference_step = plan["starts"], plan["max_nfev"], plan["log_parameter_difference_step"]
    if (not isinstance(starts, int) or starts < 1 or not isinstance(budget, int) or budget < 1
            or not np.isfinite(difference_step) or not 0 < difference_step < 1):
        raise CultureBenchmarkError("Invalid optimizer budget, starts or log-parameter difference step.")
    lower, upper = np.log(lo), np.log(hi)
    rng = np.random.default_rng(plan["seed"])
    center = (lower+upper)/2
    if warm_start is not None:
        by_symbol = {r["symbol"]: r for r in warm_start}
        center = np.log([float(Q_(by_symbol[r["symbol"]]["value"], by_symbol[r["symbol"]]["units"])
                               .to(units[r["symbol"]]).magnitude) for r in free])
        if not np.all(np.isfinite(center)) or np.any(center < lower-1e-10) or np.any(center > upper+1e-10):
            raise CultureBenchmarkError("Warm starts must lie within the explicit bounds.")
        center = np.clip(center, lower, upper)
    guesses = [center] + [rng.uniform(lower, upper) for _ in range(starts-1)]

    def records(x: np.ndarray) -> list[dict]:
        p = numeric(x)
        return [{"symbol": k, "value": p[k], "units": u, "uncertainty": None,
                 "source": (next(r["source"] for r in fixed if r["symbol"] == k) if k in fixed_parameters
                            else f"Training-only fit: {', '.join(ids)}; {plan['parameter_source']}")}
                for k, u in units.items()]

    attempts, successes = [], []
    for i, guess in enumerate(guesses):
        try:
            fit = least_squares(residual, guess, bounds=(lower, upper), diff_step=difference_step,
                                max_nfev=budget, ftol=1e-7, gtol=1e-7, xtol=1e-7)
            cost = float(fit.fun @ fit.fun)
            valid = bool(fit.success and np.isfinite(cost))
            attempts.append({"start": i, "success": valid, "message": str(fit.message), "objective": cost,
                             "nfev": int(fit.nfev), "optimality": float(fit.optimality),
                             "initial_parameters": records(guess), "parameters": records(fit.x)})
            if valid:
                successes.append((cost, i, fit))
        except (ValueError, FloatingPointError, RuntimeError) as exc:
            attempts.append({"start": i, "success": False, "message": f"{type(exc).__name__}: {exc}"})
    result: dict[str, Any] = {"success": bool(successes), "model": model, "family": family, "scenario": scenario,
        "training_conditions": ids, "observables": list(names), "observable_units": [OBSERVABLE_UNITS[k] for k in names],
        "normalization": scales.tolist(), "normalization_is_measurement_sd": False,
        "noise": {k: v.to_dict(len(training[ids.index(k)].values)) for k, v in noise.items()},
        "measurement_uncertainty": None if not noise else sorted({v.evidence for v in noise.values()}),
        "parameter_count": len(free), "fixed_parameters": deepcopy(fixed), "starts": attempts,
        "hypothesis_source": plan["hypotheses"][model], "confidence_intervals": None,
        "maturity": "exploratory_software_tested"}
    if not successes:
        result["failure"] = "No optimization start converged; no successful prediction or model promotion is permitted."
        return result
    cost, chosen, best = min(successes, key=lambda v: v[0])
    singular = np.linalg.svd(best.jac, compute_uv=False)
    cutoff = plan["complexity_screen"]["relative_singular_value_cutoff"]
    rank = int(np.sum(singular > singular[0]*cutoff)) if singular[0] else 0
    position = (best.x-lower)/(upper-lower)
    information = np.linalg.pinv(best.jac.T@best.jac)
    denominator = np.sqrt(np.maximum(np.diag(information), 0))
    correlations = np.divide(information, np.outer(denominator, denominator), out=np.zeros_like(information),
                             where=np.outer(denominator, denominator) > 0)
    result.update(objective=cost, best_start=chosen, parameters=records(best.x), singular_values=singular.tolist(),
                  practical_rank=rank, condition_number=float(singular[0]/singular[-1]) if singular[-1] > 0 else None,
                  near_bounds=[r["symbol"] for r, f in zip(free, position, strict=True)
                               if min(f, 1-f) < plan["complexity_screen"]["near_bound_log_fraction"]],
                  local_parameter_tradeoff_matrix=correlations.tolist(),
                  tradeoff_symbols=[r["symbol"] for r in free],
                  tradeoff_interpretation="Local normalized sensitivity diagnostic, not empirical parameter covariance.")
    return result


def predict_joint(condition: CultureMeasurements, fit: Mapping[str, Any], plan: Mapping[str, Any], *, solver_key: str = "solver"):
    if not fit["success"]:
        raise CultureBenchmarkError("Cannot predict from an unsuccessful fit.")
    settings = {k:v for k,v in plan[solver_key].items() if k in {"method", "rtol", "atol"}}
    return simulate_candidate(condition.design, condition.initial_activities, parameters_from_records(fit["parameters"]),
                              model=fit["model"], hypothesis_source=fit["hypothesis_source"], **settings)


def score_joint(predicted: np.ndarray, condition: CultureMeasurements, scales: Sequence[float]) -> dict:
    values, normalizer = np.asarray(predicted), np.asarray(scales)
    if (values.shape != condition.values.shape or not np.all(np.isfinite(values))
            or normalizer.shape != (len(condition.names),) or not np.all(np.isfinite(normalizer)) or np.any(normalizer <= 0)):
        raise CultureBenchmarkError("Aligned finite predictions and explicit positive scoring scales required.")
    error = values-condition.values
    return {"rmse": dict(zip(condition.names, np.sqrt(np.mean(error**2, axis=0)).tolist(), strict=True)),
            "bias": dict(zip(condition.names, np.mean(error, axis=0).tolist(), strict=True)),
            "normalized_mse": dict(zip(condition.names, np.mean((error/normalizer)**2, axis=0).tolist(), strict=True)),
            "units": {k: OBSERVABLE_UNITS[k] for k in condition.names}, "n": int(values.size)}


def profile_joint(training: Sequence[CultureMeasurements], fit: Mapping[str, Any], plan: Mapping[str, Any]) -> dict:
    if not fit["success"]:
        raise CultureBenchmarkError("A successful training fit is required for profile loss.")
    spec = plan["models"][fit["family"]][fit["model"]]
    values = {r["symbol"]: r["value"] for r in fit["parameters"]}
    errors = {key:GaussianObservationError.from_dict(record) for key,record in fit["noise"].items()}
    profiles = {}
    for parameter in spec["parameters"]:
        symbol = parameter["symbol"]
        grid = sorted(set(float(np.clip(values[symbol]*factor, parameter["lower"], parameter["upper"]))
                          for factor in plan["profile"]["factors"]))
        points = []
        for value in grid:
            revised = deepcopy(dict(plan))
            fixed = revised["models"][fit["family"]][fit["model"]]
            fixed["parameters"] = [r for r in fixed["parameters"] if r["symbol"] != symbol]
            fixed["fixed_parameters"].append({"symbol": symbol, "value": value, "units": parameter["units"],
                "source": "Explicit profile grid; nuisance parameters refitted to the same training responses."})
            revised.update(starts=1, max_nfev=plan["profile"]["max_nfev"])
            trial = fit_joint(training, revised, model=fit["model"], scenario=fit["scenario"],
                              warm_start=fit["parameters"], fixed_scales=fit["normalization"],
                              observation_errors=errors or None)
            points.append({"value": value, "success": trial["success"], "objective": trial.get("objective"),
                           "delta_objective": trial["objective"]-fit["objective"] if trial["success"] else None,
                           "parameters": trial.get("parameters"), "attempts": trial["starts"]})
        profiles[symbol] = points
    return {"reference_objective": fit["objective"], "profiles": profiles,
            "complete": all(p["success"] for points in profiles.values() for p in points),
            "reference_improved": any(p["success"] and p["delta_objective"] < -1e-5*max(1,fit["objective"])
                                      for points in profiles.values() for p in points),
            "meaning": plan["profile"]["meaning"], "confidence_intervals": None}


def conditional_bootstrap(training: Sequence[CultureMeasurements], fit: Mapping[str, Any], plan: Mapping[str, Any]) -> dict:
    """Synthetic resampling is kept out of the experimental data library."""
    if not fit["success"]:
        raise CultureBenchmarkError("Bootstrap requires a successful base fit.")
    settings, rng = plan["bootstrap"], np.random.default_rng(plan["seed"]+1)
    if (not isinstance(settings["samples"], int) or not isinstance(settings["minimum_successful"], int)
            or not 1 <= settings["minimum_successful"] <= settings["samples"]
            or len(settings["quantiles"]) != 2 or not 0 < settings["quantiles"][0] < settings["quantiles"][1] < 1):
        raise CultureBenchmarkError("Bootstrap needs positive draw counts and two ordered interior quantiles.")
    scenario = dict(plan["scenarios"]["correlated_assumption"])
    scenario["relative_sd_to_training_max"] = settings["relative_sd_to_training_max"]
    if fit["family"] == "glycerol":
        scenario["rho_biomass_substrate"] = 0
    predictions = [predict_joint(c, fit, plan).values for c in training]
    noise = [noise_for_condition(c, np.asarray(fit["normalization"]), scenario) for c in training]
    revised = deepcopy(dict(plan))
    revised.update(starts=1, max_nfev=settings["max_nfev"])
    revised["scenarios"]["bootstrap_assumption"] = scenario
    attempts, draws = [], {c.design.condition_id: [] for c in training}
    for i in range(settings["samples"]):
        synthetic = []
        for c, mean, error in zip(training, predictions, noise, strict=True):
            sd, _ = error.arrays(len(mean))
            random_errors = rng.standard_normal(mean.shape) @ np.linalg.cholesky(error.correlation).T * sd
            synthetic.append(replace(c, observations={k: Q_(mean[:, j]+random_errors[:, j], OBSERVABLE_UNITS[k])
                                 for j, k in enumerate(c.names)}, source="Synthetic bootstrap draw; never experimental evidence"))
        trial = fit_joint(synthetic, revised, model=fit["model"], scenario="bootstrap_assumption",
                          warm_start=fit["parameters"], fixed_scales=fit["normalization"])
        attempts.append({"draw": i, "success": trial["success"], "parameters": trial.get("parameters"),
                         "attempts": trial["starts"]})
        if trial["success"]:
            for c in training:
                draws[c.design.condition_id].append(predict_joint(c, trial, plan).values)
    successful = sum(a["success"] for a in attempts)
    enough = successful >= settings["minimum_successful"]
    bands = {key: np.quantile(values, settings["quantiles"], axis=0).tolist() for key, values in draws.items()} if enough else None
    return {"attempts": attempts, "successful": successful, "requested": settings["samples"],
            "sufficient_draws": enough, "bands": bands, "quantiles": settings["quantiles"],
            "error_assumption": scenario, "meaning": settings["meaning"],
            "prediction_interval_includes_new_measurement_noise": False,
            "empirical_coverage_validated": False, "experimental_replicates_generated": False}
