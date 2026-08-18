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
term and reports whether the extra parameter is warranted. This is the same
falsification protocol already applied to source 1, where deactivation was
rejected on a 60 minute assay.

WHAT THIS IS AND IS NOT
-----------------------
Sources 2 and 3 each provide a single condition per enzyme, so for those the test
is STRUCTURAL ADEQUACY under fitting, not held-out prediction. Only source 1
carries a genuine within-source held-out condition. Kinetic parameters are
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
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
LIT = ROOT / "data/experiments/literature"

NO_SUBSTRATE_INHIBITION = 1.0e9  # K_i large enough to switch the term off


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
    k_i_mM: float = NO_SUBSTRATE_INHIBITION
    fixed_km_mM: float | None = None
    notes: str = ""
    free_symbols: tuple[str, ...] = field(default=("V_max", "K_m", "K_p"))


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
        fixed_km_mM=1.25,
        notes=(
            "380 h assay. K_m is held at the source's own reported 1.25 mM because the "
            "observable is product and the substrate stays far above K_m throughout, "
            "leaving K_m unidentifiable from this curve."
        ),
        free_symbols=("V_max", "K_p"),
    ),
    Series(
        key="cao_bgl6",
        source="Cao 2015",
        enzyme="Bgl6 wild type",
        csv_path=LIT / "cao_2015_bgl6_cellobiose/cao_2015_figure_5a_bgl6.csv",
        time_column="time_h", value_column="cellobiose_millimolar",
        observable="substrate", initial_substrate_mM=292.141, time_units="hour",
        notes="10 h assay at a very high substrate charge; plateaus near 80 % conversion.",
    ),
    Series(
        key="cao_m3",
        source="Cao 2015",
        enzyme="mutant M3",
        csv_path=LIT / "cao_2015_bgl6_cellobiose/cao_2015_figure_5a_m3.csv",
        time_column="time_h", value_column="cellobiose_millimolar",
        observable="substrate", initial_substrate_mM=292.141, time_units="hour",
        notes="10 h assay at a very high substrate charge; reaches near-complete conversion.",
    ),
)

START = {"V_max": 1.0, "K_m": 30.0, "K_p": 50.0, "k_d": 1.0e-3}
BOUNDS = {
    "V_max": (1.0e-6, 1.0e4),
    "K_m": (1.0e-3, 5.0e3),
    "K_p": (1.0e-3, 1.0e5),
    "k_d": (0.0, 10.0),
}


def load(series: Series) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(series.csv_path.open(encoding="utf-8")))
    times = np.array([float(row[series.time_column]) for row in rows])
    values = np.array([float(row[series.value_column]) for row in rows])
    return times, values


def simulate(series: Series, times: np.ndarray, parameters: dict[str, float]) -> np.ndarray:
    v_max = parameters["V_max"]
    k_m = parameters["K_m"]
    k_p = parameters["K_p"]
    k_d = parameters.get("k_d", 0.0)
    k_i = series.k_i_mM

    def rhs(time: float, state: np.ndarray) -> list[float]:
        substrate, product = max(float(state[0]), 0.0), max(float(state[1]), 0.0)
        rate = (
            v_max * np.exp(-k_d * time) * substrate
            / (k_m * (1.0 + product / k_p) ** 2 + substrate * (1.0 + substrate / k_i))
        )
        return [-rate, 2.0 * rate]

    solution = solve_ivp(
        rhs, (0.0, float(times[-1])), [series.initial_substrate_mM, 0.0],
        t_eval=times, rtol=1.0e-10, atol=1.0e-12, method="LSODA",
    )
    return solution.y[0] if series.observable == "substrate" else solution.y[1]


def fit(series: Series, *, with_deactivation: bool) -> tuple[dict[str, float], float, int]:
    times, observed = load(series)
    symbols = list(series.free_symbols) + (["k_d"] if with_deactivation else [])

    def unpack(vector: np.ndarray) -> dict[str, float]:
        parameters = {"K_m": series.fixed_km_mM if series.fixed_km_mM is not None else START["K_m"]}
        parameters.update({symbol: float(value) for symbol, value in zip(symbols, vector, strict=True)})
        return parameters

    def residual(vector: np.ndarray) -> np.ndarray:
        return simulate(series, times, unpack(vector)) - observed

    solution = least_squares(
        residual,
        [START[s] for s in symbols],
        bounds=([BOUNDS[s][0] for s in symbols], [BOUNDS[s][1] for s in symbols]),
        xtol=1.0e-14, ftol=1.0e-14, max_nfev=20000,
    )
    fitted = unpack(solution.x)
    rmse = float(np.sqrt(np.mean(residual(solution.x) ** 2)))
    pinned = _bound_pinned(symbols, solution.x)
    condition = _condition_number(np.asarray(solution.jac, dtype=float))
    return fitted, rmse, len(symbols), pinned, condition


#: Search bounds span many orders of magnitude, so bound proximity is measured
#: as a RELATIVE factor, not as a fraction of the linear span. A linear-span test
#: would flag every small parameter as pinned to a tiny lower bound.
BOUND_PROXIMITY_FACTOR = 1.05

#: Jacobian condition number above which the fit is treated as unidentified.
MAX_CONDITION_NUMBER = 1.0e8


def _bound_pinned(symbols: list[str], vector: np.ndarray) -> list[str]:
    """Return symbols that ran to a search bound instead of an interior optimum.

    A low RMSE reached with a parameter pinned at its bound is a compensating
    fit, not an identified one, and must not be reported as a success.
    """

    pinned: list[str] = []
    for symbol, value in zip(symbols, vector, strict=True):
        low, high = BOUNDS[symbol]
        numeric = float(value)
        if numeric >= high / BOUND_PROXIMITY_FACTOR or numeric <= low * BOUND_PROXIMITY_FACTOR:
            pinned.append(symbol)
    return pinned


def _condition_number(jacobian: np.ndarray) -> float:
    """Return the Jacobian condition number, or infinity if it is rank deficient."""

    if jacobian.size == 0:
        return float("inf")
    singular = np.linalg.svd(jacobian, compute_uv=False)
    if singular.size == 0 or singular[-1] <= 0.0:
        return float("inf")
    return float(singular[0] / singular[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/cross_source_structural_test")
    arguments = parser.parse_args()

    summary: dict = {
        "structure": "v = V_max*exp(-k_d*t)*S / (K_m*(1+P/K_p)^2 + S*(1+S/K_i))",
        "claim_boundary": (
            "Sources 2 and 3 provide one condition per enzyme, so for those this is structural "
            "adequacy under fitting, not held-out prediction. Only source 1 carries a genuine "
            "within-source held-out condition. Parameters are never transferred between sources."
        ),
        "series": {},
    }

    header = f"{'series':24s} {'regime':>10s} {'n':>3s} {'RMSE base':>10s} {'RMSE +k_d':>10s} {'scale%':>7s}  deactivation"
    print(header)
    print("-" * len(header))

    for series in SERIES:
        times, observed = load(series)
        base, base_rmse, base_k, base_pinned, base_condition = fit(series, with_deactivation=False)
        deact, deact_rmse, deact_k, _, _ = fit(series, with_deactivation=True)
        identified = not base_pinned and base_condition < MAX_CONDITION_NUMBER
        scale = float(np.max(np.abs(observed)))
        improvement = (base_rmse - deact_rmse) / base_rmse if base_rmse > 0 else 0.0
        half_life = float("inf") if deact["k_d"] <= 0 else float(np.log(2) / deact["k_d"])
        span = float(times[-1])
        # Warranted only if it cuts the error substantially AND acts on the assay timescale.
        warranted = improvement > 0.25 and half_life < 3.0 * span
        verdict = "REQUIRED" if warranted else "not warranted"
        if base_pinned:
            flag = "  <-- DEGENERATE: " + ",".join(base_pinned) + " at bound"
        elif not identified:
            flag = f"  <-- DEGENERATE: Jacobian cond {base_condition:.1e}"
        else:
            flag = ""
        print(
            f"{series.key:24s} {series.time_units[:4]+' '+str(int(span)):>10s} {len(times):3d} "
            f"{base_rmse:10.4f} {deact_rmse:10.4f} {100*base_rmse/scale:6.2f}%  {verdict}"
            + (f"  (t1/2 {half_life:.3g} {series.time_units})" if warranted else "")
            + flag
        )
        summary["series"][series.key] = {
            "source": series.source, "enzyme": series.enzyme, "notes": series.notes,
            "n_points": len(times), "timespan": span, "time_units": series.time_units,
            "initial_substrate_mM": series.initial_substrate_mM, "observable": series.observable,
            "base": {"fitted": base, "rmse": base_rmse, "n_free": base_k,
                     "relative_rmse_percent_of_scale": 100 * base_rmse / scale,
                     "bound_pinned_symbols": base_pinned,
                     "jacobian_condition_number": base_condition,
                     "identified": bool(identified)},
            "with_deactivation": {"fitted": deact, "rmse": deact_rmse, "n_free": deact_k,
                                  "half_life": half_life, "improvement_fraction": improvement},
            "deactivation_warranted": bool(warranted),
        }

    print()
    print("Deactivation is judged warranted only when it cuts RMSE by more than 25 % AND the")
    print("fitted half-life is shorter than three times the assay duration, so a fitted decay")
    print("far slower than the experiment cannot count as an explanation.")
    degenerate = [k for k, e in summary["series"].items() if not e["base"]["identified"]]
    print()
    if degenerate:
        print(f"DEGENERATE FITS ({len(degenerate)} of {len(SERIES)}): " + ", ".join(degenerate))
        print("A parameter pinned at its search bound has not been identified by the data.")
        print("These series reach a low RMSE by parameter compensation and must NOT be")
        print("reported as evidence that the structure works.")
    summary["degenerate_series"] = degenerate
    summary["identified_series"] = [k for k in summary["series"] if k not in degenerate]

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "cross_source_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {arguments.output_dir / 'cross_source_summary.json'}")


if __name__ == "__main__":
    main()
