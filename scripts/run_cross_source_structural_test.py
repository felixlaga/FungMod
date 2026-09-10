"""Test whether one rate-law structure is adequate across three literature sources.

FungMod now holds three independent literature sources spanning four enzyme
preparations and three kinetic regimes:

  source 1  Alvarez-Gonzalez 2022  commercial beta-glucosidase   60 min    62-227 mM
  source 2  Ariaeenejad 2020       PersiBGL1 (rumen metagenome)  380 h     29 mM
  source 3  Cao 2015               Bgl6 and mutant M3            10 h      292 mM

The shared structure under test is the configured model's own rate law, a
homogeneous Michaelis-Menten base rate under coupled substrate and double
product inhibition, optionally multiplied by first-order enzyme deactivation:

    v = V_max * exp(-k_d * t) * S / ( K_m * (1 + P/K_p)^2 + S * (1 + S/K_i) )

For each series the script fits the structure with and without the deactivation
term and reports training residuals and numerical diagnostics. A lower training
error does not establish a mechanism or predictive validity.

WHAT THIS IS AND IS NOT
-----------------------
Sources 2 and 3 each provide a single condition per enzyme, so for those the test
is exploratory structural fitting, not held-out prediction. Although source 1
has held-out conditions in a separate script, every series here is fitted.
Kinetic parameters are
specific to an enzyme preparation and assay and are never transferred between
sources; each series gets its own values. Nothing here is independent
experimental replication of any other series.

Usage::

    python scripts/run_cross_source_structural_test.py
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
LIT = ROOT / "data/experiments/literature"

@dataclass(frozen=True)
class Series:
    """One digitized progress curve and the regime it came from."""

    key: str
    source: str
    enzyme: str
    csv_path: Path
    time_column: str
    value_column: str
    observable: str            # "substrate" or "product"
    initial_substrate_mM: float
    time_units: str
    k_i_mM: float | None  # None explicitly omits substrate inhibition as a model hypothesis.
    notes: str = ""


SERIES = (
    Series(
        key="alvarez_A20",
        source="Alvarez-Gonzalez 2022",
        enzyme="commercial beta-glucosidase 1000",
        csv_path=LIT / "alvarez_gonzalez_2022_free_beta_glucosidase/alvarez_gonzalez_2022_figure_s1a_filled_squares.csv",
        time_column="time_min", value_column="cellobiose_millimolar",
        observable="substrate", initial_substrate_mM=62.455, time_units="minute",
        k_i_mM=1088.0,
        notes="60 min assay; the source's own model includes substrate inhibition.",
    ),
    Series(
        key="alvarez_A70",
        source="Alvarez-Gonzalez 2022",
        enzyme="commercial beta-glucosidase 1000",
        csv_path=LIT / "alvarez_gonzalez_2022_free_beta_glucosidase/alvarez_gonzalez_2022_figure_s1a_open_squares.csv",
        time_column="time_min", value_column="cellobiose_millimolar",
        observable="substrate", initial_substrate_mM=227.18, time_units="minute",
        k_i_mM=1088.0,
        notes="Held-out condition for source 1; fitted here only for structural comparison.",
    ),
    Series(
        key="ariaeenejad_persibgl1",
        source="Ariaeenejad 2020",
        enzyme="PersiBGL1",
        csv_path=LIT / "ariaeenejad_2020_persibgl1_cellobiose/ariaeenejad_2020_figure_6_glucose.csv",
        time_column="time_h", value_column="glucose_millimolar",
        observable="product", initial_substrate_mM=29.214, time_units="hour",
        k_i_mM=None,
        notes=(
            "Cellobiose K_m is unknown and is estimated from this curve, with possible weak "
            "identifiability. The paper's 1.25 mM K_m was measured with pNPG at pH 7, "
            "not cellobiose at pH 8, and is not transferred. Source: "
            "https://doi.org/10.3389/fbioe.2020.00813, enzyme assay and kinetic-parameter sections. "
            "Omission of substrate inhibition is an explicit exploratory hypothesis."
        ),
    ),
    Series(
        key="cao_bgl6",
        source="Cao 2015",
        enzyme="Bgl6 wild type",
        csv_path=LIT / "cao_2015_bgl6_cellobiose/cao_2015_figure_5a_bgl6.csv",
        time_column="time_h", value_column="cellobiose_millimolar",
        observable="substrate", initial_substrate_mM=292.141, time_units="hour",
        k_i_mM=None,
        notes="10 h assay; omission of substrate inhibition is an explicit exploratory hypothesis.",
    ),
    Series(
        key="cao_m3",
        source="Cao 2015",
        enzyme="mutant M3",
        csv_path=LIT / "cao_2015_bgl6_cellobiose/cao_2015_figure_5a_m3.csv",
        time_column="time_h", value_column="cellobiose_millimolar",
        observable="substrate", initial_substrate_mM=292.141, time_units="hour",
        k_i_mM=None,
        notes="10 h assay; omission of substrate inhibition is an explicit exploratory hypothesis.",
    ),
)

START = {"V_max": 1.0, "K_m": 30.0, "K_p": 50.0, "k_d": 1.0e-3}
BOUNDS = {
    "V_max": (1.0e-6, 1.0e4),
    "K_m": (1.0e-3, 5.0e3),
    "K_p": (1.0e-3, 1.0e5),
    "k_d": (0.0, 10.0),
}


class StudyError(ValueError):
    """A numerical or data failure prevents an interpretable study result."""


def load(series: Series) -> tuple[np.ndarray, np.ndarray]:
    with series.csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    times = np.array([float(row[series.time_column]) for row in rows])
    values = np.array([float(row[series.value_column]) for row in rows])
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise StudyError(f"{series.key}: observations must be finite and nonnegative.")
    return times, values


def simulate(series: Series, times: np.ndarray, parameters: dict[str, float]) -> np.ndarray:
    """Integrate the declared exploratory law; tests compare it to package trajectories."""

    if (times.ndim != 1 or not times.size or not np.all(np.isfinite(times))
            or times[0] < 0 or times[-1] <= 0 or np.any(np.diff(times) <= 0)):
        raise StudyError("Times must be finite, increasing and nonnegative, with a positive endpoint.")
    if series.observable not in {"substrate", "product"}:
        raise StudyError(f"Unknown observable {series.observable!r}.")
    v_max, k_m, k_p = (parameters[name] for name in ("V_max", "K_m", "K_p"))
    k_d = parameters.get("k_d", 0.0)  # No decay in the declared base model.
    if not all(np.isfinite(v) and v > 0 for v in (v_max, k_m, k_p, series.initial_substrate_mM)):
        raise StudyError("Initial substrate and kinetic parameters must be finite and positive.")
    if not np.isfinite(k_d) or k_d < 0:
        raise StudyError("The decay rate must be finite and nonnegative.")
    if series.k_i_mM is not None and (not np.isfinite(series.k_i_mM) or series.k_i_mM <= 0):
        raise StudyError("Explicit substrate-inhibition constants must be finite and positive.")

    def rhs(time: float, state: np.ndarray) -> list[float]:
        substrate, product = max(float(state[0]), 0.0), max(float(state[1]), 0.0)
        inhibition = 0.0 if series.k_i_mM is None else substrate / series.k_i_mM
        rate = (v_max * np.exp(-k_d * time) * substrate
                / (k_m * (1.0 + product / k_p) ** 2 + substrate * (1.0 + inhibition)))
        return [-rate, 2.0 * rate]

    solution = solve_ivp(
        rhs, (0.0, float(times[-1])), [series.initial_substrate_mM, 0.0],
        t_eval=times, rtol=1.0e-10, atol=1.0e-12, method="LSODA",
    )
    if not solution.success:
        raise StudyError(f"{series.key}: integration failed: {solution.message}")
    values = np.asarray(solution.y, dtype=float)
    if values.shape != (2, len(times)) or not np.all(np.isfinite(values)):
        raise StudyError(f"{series.key}: integration returned incomplete or nonfinite states.")
    return values[0] if series.observable == "substrate" else values[1]


# Numerical diagnostics only; neither threshold proves biological identifiability.
BOUND_PROXIMITY_FACTOR = 1.05
MAX_CONDITION_NUMBER = 1.0e8


def _bound_pinned(symbols: list[str], vector: np.ndarray) -> list[str]:
    pinned: list[str] = []
    for symbol, value in zip(symbols, vector, strict=True):
        low, high = BOUNDS[symbol]
        numeric = float(value)
        near_lower = numeric <= low * BOUND_PROXIMITY_FACTOR if low > 0 else numeric <= 1.0e-10
        if numeric >= high / BOUND_PROXIMITY_FACTOR or near_lower:
            pinned.append(symbol)
    return pinned


def _condition_number(jacobian: np.ndarray) -> float:
    if not jacobian.size or not np.all(np.isfinite(jacobian)):
        return float("inf")
    singular = np.linalg.svd(jacobian, compute_uv=False)
    return float("inf") if singular[-1] <= 0 else float(singular[0] / singular[-1])


def fit(series: Series, *, with_deactivation: bool, base_fit: dict | None = None) -> dict:
    """Retain the best converged deterministic start, including the nested base fit."""

    times, observed = load(series)
    symbols = ["V_max", "K_m", "K_p"] + (["k_d"] if with_deactivation else [])
    starts = [dict(START), {**START, "V_max": 10.0, "K_m": 100.0, "K_p": 100.0}]
    if with_deactivation:
        if base_fit is None:
            raise StudyError("The extended fit requires its converged base fit.")
        starts = [{**base_fit["fitted"], "k_d": 0.0},
                  {**base_fit["fitted"], "k_d": 1.0 / float(times[-1])}, *starts]
    attempts: list[dict] = []
    best = None
    best_sse = float("inf")

    def unpack(vector: np.ndarray) -> dict[str, float]:
        return dict(zip(symbols, map(float, vector), strict=True))

    def residual(vector: np.ndarray) -> np.ndarray:
        return simulate(series, times, unpack(vector)) - observed

    for start in starts:
        solution = least_squares(
            residual, [start[s] for s in symbols],
            bounds=([BOUNDS[s][0] for s in symbols], [BOUNDS[s][1] for s in symbols]),
            x_scale="jac", xtol=1.0e-10, ftol=1.0e-10, gtol=1.0e-10, max_nfev=20000,
        )
        valid = bool(solution.success and np.all(np.isfinite(solution.x))
                     and np.all(np.isfinite(solution.fun)) and np.all(np.isfinite(solution.jac)))
        sse = float(np.sum(solution.fun ** 2)) if valid else None
        attempts.append({"start": {s: start[s] for s in symbols}, "success": valid,
                         "message": str(solution.message), "nfev": int(solution.nfev), "sse": sse})
        if sse is not None and sse < best_sse:
            best, best_sse = solution, sse
    if best is None:
        raise StudyError(f"{series.key}: no optimizer start converged: {attempts}")
    rmse = float(np.sqrt(best_sse / len(observed)))
    if base_fit is not None and rmse > base_fit["rmse"] + 1.0e-8 * max(1.0, base_fit["rmse"]):
        raise StudyError(f"{series.key}: extended fit is worse than its feasible nested base model.")
    condition = _condition_number(np.asarray(best.jac, dtype=float))
    pinned = _bound_pinned(symbols, best.x)
    return {
        "fitted": unpack(best.x), "rmse": rmse, "n_free": len(symbols),
        "bound_pinned_symbols": pinned,
        "jacobian_condition_number": condition if np.isfinite(condition) else None,
        "jacobian_rank": int(np.linalg.matrix_rank(best.jac)),
        "numerical_diagnostic_flags": (["parameter_at_search_bound"] if pinned else [])
        + (["ill_conditioned_jacobian"] if condition >= MAX_CONDITION_NUMBER else []),
        "identifiability": "not_established_by_local_optimizer_diagnostics",
        "optimizer_attempts": attempts,
    }


def run(output_dir: Path) -> dict:
    summary: dict = {
        "schema_version": "2.0.0",
        "structure": "v = V_max*exp(-k_d*t)*S / (K_m*(1+P/K_p)^2 + S*(1+S/K_i))",
        "claim_boundary": (
            "Every series here is fitted. These are exploratory training residuals, not held-out "
            "predictions, independent validation, or evidence establishing a biological mechanism. "
            "Parameters are not transferred between enzyme preparations or substrates."
        ),
        "numerical_policy": {
            "bounds": BOUNDS, "bounds_meaning": "optimizer search choices, not biological ranges",
            "condition_threshold": MAX_CONDITION_NUMBER,
            "bound_proximity_factor": BOUND_PROXIMITY_FACTOR,
            "extended_model_start": "includes the fitted base model with k_d=0",
            "uncertainty": "unweighted training residuals; no empirical noise model or confidence claim",
        },
        "series": {},
    }
    for series in SERIES:
        times, _ = load(series)
        base = fit(series, with_deactivation=False)
        deact = fit(series, with_deactivation=True, base_fit=base)
        improvement = (base["rmse"] - deact["rmse"]) / base["rmse"] if base["rmse"] > 0 else None
        half_life = float(np.log(2) / deact["fitted"]["k_d"]) if deact["fitted"]["k_d"] > 0 else None
        if half_life is not None and not np.isfinite(half_life):
            half_life = None
        summary["series"][series.key] = {
            "source": series.source, "enzyme": series.enzyme, "notes": series.notes,
            "n_points": len(times), "timespan": float(times[-1]), "time_units": series.time_units,
            "initial_substrate_mM": series.initial_substrate_mM, "observable": series.observable,
            "fixed_substrate_inhibition_mM": series.k_i_mM,
            "substrate_inhibition": "omitted_as_explicit_hypothesis" if series.k_i_mM is None else "source_point_estimate",
            "base": base, "with_deactivation": deact,
            "training_rmse_improvement_fraction": improvement,
            "fitted_half_life": half_life,
            "mechanism_conclusion": "not_established_by_training_fit",
        }
        print(f"{series.key:24s} base RMSE={base['rmse']:.4f}, extended RMSE={deact['rmse']:.4f} mM; "
              "mechanism not established")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cross_source_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/cross_source_structural_test")
    arguments = parser.parse_args()
    run(arguments.output_dir)
    print(f"wrote {arguments.output_dir / 'cross_source_summary.json'}")


if __name__ == "__main__":
    main()
