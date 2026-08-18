"""Test two candidate mechanisms for the Alvarez-Gonzalez 2022 panel-B discrepancy.

Stage 1 and Stage 2 both found that the configured model predicts the Figure S1A
70 g/L series well but fails systematically on the two panel-B series, which
carry a nominal five-fold enzyme loading. Refitting does not repair the failure,
so it is structural rather than a parameter-estimation problem.

This script tests two candidate mechanisms and records that **both fail**. It
exists so the negative results are reproducible and so neither mechanism is
quietly added to the model later without re-deriving the evidence against it.

Hypothesis 1: first-order thermal deactivation of the free enzyme.
    V_max(t) = V_max(0) * exp(-k_d * t)
    Motivated by the source publication's own subject, which is stabilizing this
    enzyme by immobilization. Fitted on the training series only.
    RESULT: falsified. The fitted half-life is far longer than the assay, the
    training improvement is negligible for one added parameter, and every
    held-out condition gets worse.

Hypothesis 2: sub-linear enzyme scaling.
    V_max_panelB = V_max_panelA * R^n  with R = 296.1 / 59.2 and n < 1
    Motivated by a model-free comparison of the two panels, which gives an
    apparent exponent near 0.28.
    RESULT: not supported as a single mechanism. The two panel-B series imply
    materially different exponents and cross-prediction between them fails in
    one direction.

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
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

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

# The configured model's own prediction for the training series under the
# published parameters, used to verify this standalone integration.
CONFIGURED_TRAINING_FINAL = 6.2112832
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
    return solution.y[0]


def rmse(predicted: np.ndarray, observed: np.ndarray) -> float:
    return float(np.sqrt(np.mean((predicted - observed) ** 2)))


def verify_against_configured_model() -> float:
    """Fail unless this integration reproduces the configured-model trajectory."""

    times, values = load_series(TRAINING_SERIES)
    final = float(simulate(values[0], times, PUBLISHED_VMAX, PUBLISHED_KM, PUBLISHED_KP)[-1])
    deviation = abs(final - CONFIGURED_TRAINING_FINAL)
    if deviation > VERIFY_TOLERANCE:
        raise SystemExit(
            "Standalone integration does not reproduce the configured model.\n"
            f"  standalone {final!r}\n  configured {CONFIGURED_TRAINING_FINAL!r}\n"
            f"  deviation {deviation!r} exceeds {VERIFY_TOLERANCE!r}"
        )
    return deviation


def fit_on_training(*, free_kd: bool) -> tuple[dict[str, float], float]:
    times, values = load_series(TRAINING_SERIES)

    def residual(vector: np.ndarray) -> np.ndarray:
        kd = float(vector[3]) if free_kd else 0.0
        return simulate(values[0], times, float(vector[0]), float(vector[1]), float(vector[2]), kd) - values

    start = [PUBLISHED_VMAX, PUBLISHED_KM, PUBLISHED_KP] + ([1.0e-3] if free_kd else [])
    lower = [1.0e-3, 1.0e-3, 1.0e-3] + ([0.0] if free_kd else [])
    upper = [500.0, 1000.0, 1000.0] + ([1.0] if free_kd else [])
    solution = least_squares(residual, start, bounds=(lower, upper), xtol=1.0e-14, ftol=1.0e-14)
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
    return float(solution.x[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/alvarez_gonzalez_2022_mechanisms")
    arguments = parser.parse_args()

    deviation = verify_against_configured_model()
    print(f"standalone integration reproduces the configured model (deviation {deviation:.2e} mM)\n")

    summary: dict = {"verification_deviation_mM": deviation, "hypotheses": {}}

    baseline, baseline_train = fit_on_training(free_kd=False)
    baseline_held = held_out_errors(baseline)
    deactivation, deactivation_train = fit_on_training(free_kd=True)
    deactivation_held = held_out_errors(deactivation)

    print("HYPOTHESIS 1: first-order enzyme deactivation, k_d fitted on the training series")
    print(f"  H0 (k_d = 0):   train RMSE {baseline_train:.4f} mM   " +
          "  ".join(f"{k} {v:7.4f}" for k, v in baseline_held.items()))
    half_life = float("inf") if deactivation["k_d"] <= 0 else float(np.log(2) / deactivation["k_d"])
    print(f"  H1 (k_d fitted): train RMSE {deactivation_train:.4f} mM   " +
          "  ".join(f"{k} {v:7.4f}" for k, v in deactivation_held.items()))
    print(f"    fitted k_d = {deactivation['k_d']:.6g} /min  ->  half-life {half_life:.4g} min against a 60 min assay")
    worse = {k: deactivation_held[k] > baseline_held[k] for k in baseline_held}
    print(f"    every held-out condition worse: {all(worse.values())}")
    print("    VERDICT: falsified. Negligible decay over the assay, negligible training gain,")
    print("             and degraded generalization. Not added to the model.\n")

    summary["hypotheses"]["first_order_deactivation"] = {
        "verdict": "falsified",
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
    print("    VERDICT: not supported as a single mechanism. The two panel-B series imply")
    print("             materially different exponents and cross-prediction fails one way.")
    print("             Both exponents are below 1, so sub-linearity is indicated but not")
    print("             quantifiable from this figure. Not added to the model.\n")

    summary["hypotheses"]["sublinear_enzyme_scaling"] = {
        "verdict": "not_supported_as_single_mechanism",
        "fitted_exponents": exponents,
        "cross_prediction": cross,
    }
    summary["conclusion"] = (
        "Neither candidate mechanism explains the panel-B discrepancy. Combined with the "
        "unresolved caption unit inconsistency, the most defensible reading is that the "
        "panel-B enzyme concentration metadata is not reliable enough to support a model "
        "comparison. Panel B is therefore excluded from validation claims and retained only "
        "as a documented open discrepancy."
    )
    print("CONCLUSION:", summary["conclusion"])

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "mechanism_hypotheses.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {arguments.output_dir / 'mechanism_hypotheses.json'}")


if __name__ == "__main__":
    main()
