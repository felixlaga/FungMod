"""Test two candidate mechanisms for the Alvarez-Gonzalez 2022 panel-B discrepancy.

This is an exploratory comparison of candidate explanations for residuals across
conditions. Source-unit uncertainty and limited identifiability prevent a unique
attribution to model structure or parameter estimation.

This script records training and other-condition residuals. It does not infer
mechanism confirmation or falsification from local fits.

Hypothesis 1: first-order thermal deactivation of the free enzyme.
    V_max(t) = V_max(0) * exp(-k_d * t)
    Motivated by the source publication's own subject, which is stabilizing this
    enzyme by immobilization. Fitted on the training series only.
    Interpretation requires independent data and a prospective comparison plan.

Hypothesis 2: sub-linear enzyme scaling.
    V_max_panelB = V_max_panelA * R^n  with R = 296.1 / 59.2 and n < 1
    Motivated by a model-free comparison of the two panels, which gives an
    apparent exponent near 0.28.
    Separate exponents are descriptive estimates, not a confirmed mechanism.

The rate law reproduced here is the one the configured model assembles, namely a
homogeneous Michaelis-Menten base rate under the coupled substrate and double
product-inhibition modifier:

    v = V_max * S / ( K_m * (1 + P/K_p)^2 + S * (1 + S/K_i) )

The standalone integration is checked against the configured-model trajectory
before any hypothesis is tested, so a mismatch fails loudly rather than silently
testing a different model.

Usage::

    python scripts/run_alvarez_gonzalez_2022_mechanism_hypotheses.py
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

from fungal_model import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "data/experiments/literature/alvarez_gonzalez_2022_free_beta_glucosidase"

SERIES_FILES = {
    "A20": "alvarez_gonzalez_2022_figure_s1a_filled_squares.csv",
    "A70": "alvarez_gonzalez_2022_figure_s1a_open_squares.csv",
    "B20": "alvarez_gonzalez_2022_figure_s1b_filled_squares.csv",
    "B70": "alvarez_gonzalez_2022_figure_s1b_open_squares.csv",
}
TRAINING_SERIES = "A20"

ENZYME_RATIO = 296.1 / 59.2

# Published Model 3 point estimates.
PUBLISHED_VMAX, PUBLISHED_KM, PUBLISHED_KP = 19.72544, 43.0, 34.0
# K_i is held at its published value throughout: Stage 2 showed it is
# unidentified from a single progress curve, with an approximate 95% interval
# spanning negative values.
K_I = 1088.0

# Numerical agreement tolerance in mM, not a biological adequacy criterion.
VERIFY_TOLERANCE = 1.0e-5


def load_series(key: str) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.DictReader((DATASET_DIR / SERIES_FILES[key]).open(encoding="utf-8")))
    times = np.array([float(row["time_min"]) for row in rows])
    values = np.array([float(row["cellobiose_millimolar"]) for row in rows])
    return times, values


def _rhs(time: float, state: np.ndarray, vmax: float, km: float, kp: float, kd: float) -> list[float]:
    substrate, product = max(float(state[0]), 0.0), max(float(state[1]), 0.0)
    rate = (
        vmax
        * np.exp(-kd * time)
        * substrate
        / (km * (1.0 + product / kp) ** 2 + substrate * (1.0 + substrate / K_I))
    )
    return [-rate, 2.0 * rate]


def simulate(initial: float, times: np.ndarray, vmax: float, km: float, kp: float, kd: float = 0.0) -> np.ndarray:
    solution = solve_ivp(
        _rhs,
        (0.0, float(times[-1])),
        [initial, 0.0],
        args=(vmax, km, kp, kd),
        t_eval=times,
        rtol=1.0e-10,
        atol=1.0e-12,
        method="LSODA",
    )
    if not solution.success or np.shape(solution.y) != (2, len(times)) or not np.all(np.isfinite(solution.y)):
        raise RuntimeError(f"Hypothesis integration failed or returned incomplete states: {solution.message}")
    return solution.y[0]


def rmse(predicted: np.ndarray, observed: np.ndarray) -> float:
    return float(np.sqrt(np.mean((predicted - observed) ** 2)))


def verify_against_configured_model() -> float:
    """Fail unless this integration reproduces the configured-model trajectory."""

    with tempfile.TemporaryDirectory(prefix="fungmod_hypothesis_reference_") as directory:
        reference = run_configured_model(
            ROOT / "data/model_configs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison.yml",
            output_dir=Path(directory),
        )
    times = np.asarray(reference.time.to("minute").magnitude)
    observed = np.asarray(reference.states["cellobiose_concentration"].magnitude)
    predicted = simulate(float(observed[0]), times, PUBLISHED_VMAX, PUBLISHED_KM, PUBLISHED_KP)
    deviation = float(np.max(np.abs(predicted - observed)))
    if deviation > VERIFY_TOLERANCE:
        raise SystemExit(
            "Standalone integration does not reproduce the configured model.\n"
            f"  deviation {deviation!r} exceeds {VERIFY_TOLERANCE!r}"
        )
    return deviation


def fit_on_training(*, free_kd: bool) -> tuple[dict[str, float], float]:
    times, values = load_series(TRAINING_SERIES)

    def residual(vector: np.ndarray) -> np.ndarray:
        kd = float(vector[3]) if free_kd else 0.0
        return simulate(values[0], times, float(vector[0]), float(vector[1]), float(vector[2]), kd) - values

    start = [PUBLISHED_VMAX, PUBLISHED_KM, PUBLISHED_KP] + ([1.0e-3] if free_kd else [])
    base_rmse = None
    if free_kd:
        base, base_rmse = fit_on_training(free_kd=False)
        start = [base["V_max"], base["K_m"], base["K_p"], 0.0]
    lower = [1.0e-3, 1.0e-3, 1.0e-3] + ([0.0] if free_kd else [])
    upper = [500.0, 1000.0, 1000.0] + ([1.0] if free_kd else [])
    solution = least_squares(residual, start, bounds=(lower, upper), xtol=1.0e-14, ftol=1.0e-14)
    if not solution.success or not np.all(np.isfinite(solution.x)) or not np.all(np.isfinite(solution.fun)):
        raise RuntimeError(f"Hypothesis fit did not converge: {solution.message}")
    fitted_rmse = float(np.sqrt(np.mean(solution.fun**2)))
    if base_rmse is not None and fitted_rmse > base_rmse + 1.0e-8:
        raise RuntimeError("Extended hypothesis fit is worse than its feasible nested base model.")
    fitted = {
        "V_max": float(solution.x[0]),
        "K_m": float(solution.x[1]),
        "K_p": float(solution.x[2]),
        "k_d": float(solution.x[3]) if free_kd else 0.0,
    }
    return fitted, rmse(residual(solution.x) + values, values)


def held_out_errors(fitted: dict[str, float], *, exponent: float = 1.0) -> dict[str, float]:
    errors: dict[str, float] = {}
    for key in ("A70", "B20", "B70"):
        times, values = load_series(key)
        scale = ENZYME_RATIO**exponent if key.startswith("B") else 1.0
        predicted = simulate(values[0], times, fitted["V_max"] * scale, fitted["K_m"], fitted["K_p"], fitted["k_d"])
        errors[key] = rmse(predicted, values)
    return errors


def fit_exponent(key: str, fitted: dict[str, float]) -> float:
    times, values = load_series(key)

    def residual(vector: np.ndarray) -> np.ndarray:
        scale = ENZYME_RATIO ** float(vector[0])
        return simulate(values[0], times, fitted["V_max"] * scale, fitted["K_m"], fitted["K_p"], fitted["k_d"]) - values

    solution = least_squares(residual, [0.3], bounds=([-1.0], [2.0]), xtol=1.0e-14, ftol=1.0e-14)
    if not solution.success or not np.all(np.isfinite(solution.x)) or not np.all(np.isfinite(solution.fun)):
        raise RuntimeError(f"Exponent fit did not converge: {solution.message}")
    return float(solution.x[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/alvarez_gonzalez_2022_mechanisms")
    arguments = parser.parse_args()

    deviation = verify_against_configured_model()
    print(f"standalone integration reproduces the configured model (deviation {deviation:.2e} mM)\n")

    summary: dict = {"schema_version": "2.0.0", "verification_deviation_mM": deviation, "hypotheses": {}}

    baseline, baseline_train = fit_on_training(free_kd=False)
    baseline_held = held_out_errors(baseline)
    deactivation, deactivation_train = fit_on_training(free_kd=True)
    deactivation_held = held_out_errors(deactivation)

    print("HYPOTHESIS 1: first-order enzyme deactivation, k_d fitted on the training series")
    print(f"  H0 (k_d = 0):   train RMSE {baseline_train:.4f} mM   " +
          "  ".join(f"{k} {v:7.4f}" for k, v in baseline_held.items()))
    half_life = None if deactivation["k_d"] <= 0 else float(np.log(2) / deactivation["k_d"])
    print(f"  H1 (k_d fitted): train RMSE {deactivation_train:.4f} mM   " +
          "  ".join(f"{k} {v:7.4f}" for k, v in deactivation_held.items()))
    print(f"    fitted k_d = {deactivation['k_d']:.6g} /min  ->  half-life {half_life} min against a 60 min assay")
    worse = {k: deactivation_held[k] > baseline_held[k] for k in baseline_held}
    print(f"    every held-out condition worse: {all(worse.values())}")
    print("    Mechanism not established: interpret these residuals under the recorded source limitations.\n")

    summary["hypotheses"]["first_order_deactivation"] = {
        "verdict": "not_established_by_exploratory_comparison",
        "baseline": {"fitted": baseline, "train_rmse": baseline_train, "held_out_rmse": baseline_held},
        "with_deactivation": {
            "fitted": deactivation,
            "train_rmse": deactivation_train,
            "held_out_rmse": deactivation_held,
            "half_life_min": half_life,
        },
        "all_held_out_worse": all(worse.values()),
    }

    print("HYPOTHESIS 2: sub-linear enzyme scaling V_max_B = V_max_A * R^n, R = %.4f" % ENZYME_RATIO)
    exponents = {key: fit_exponent(key, baseline) for key in ("B20", "B70")}
    for key, value in exponents.items():
        print(f"  exponent fitted on {key}: n = {value:.3f}   (the linear model assumes n = 1)")
    cross: dict[str, dict[str, float]] = {}
    for source, target in (("B20", "B70"), ("B70", "B20")):
        times, values = load_series(target)
        linear = rmse(simulate(values[0], times, baseline["V_max"] * ENZYME_RATIO, baseline["K_m"], baseline["K_p"]), values)
        transferred = rmse(
            simulate(values[0], times, baseline["V_max"] * ENZYME_RATIO ** exponents[source], baseline["K_m"], baseline["K_p"]),
            values,
        )
        cross[f"{source}_to_{target}"] = {"transferred_rmse": transferred, "linear_rmse": linear}
        verdict = "improves" if transferred < linear else "WORSE than linear"
        print(f"  n from {source} -> {target}: RMSE {transferred:7.4f} mM vs linear {linear:7.4f} mM  ({verdict})")
    print("    Mechanism not established: fitted exponents are descriptive estimates.\n")

    summary["hypotheses"]["sublinear_enzyme_scaling"] = {
        "verdict": "not_established_by_exploratory_comparison",
        "fitted_exponents": exponents,
        "cross_prediction": cross,
    }
    summary["conclusion"] = (
        "These exploratory fits do not confirm or falsify either mechanism. Panel-B results "
        "depend on the assumed mg/L interpretation of a caption printing mg/mL; all conditions "
        "come from one publication. Independent experiments, experimental uncertainty, and "
        "prospective predictive criteria remain necessary for validation claims."
    )
    print("CONCLUSION:", summary["conclusion"])

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "mechanism_hypotheses.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {arguments.output_dir / 'mechanism_hypotheses.json'}")


if __name__ == "__main__":
    main()
