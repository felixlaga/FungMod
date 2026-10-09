"""FungMod showcase study: can a fungus model trained on three cultures predict two it never saw?

One end-to-end study of *Trichoderma harzianum* P49P11 degrading cellulose
(Gelain et al. 2020, doi:10.1016/j.cesx.2020.100085), plus one enzyme-level
environment screen, run through FungMod's public and research APIs:

1. registry-backed virtual experiments in ``scientific`` mode for the three
   training loadings (10, 20, 30 g/L) and the two held-out loadings (5, 40 g/L);
2. posterior predictive bands from the recorded BAYES-001 posterior;
3. frozen predictions of five competing models on the held-out loadings,
   scored against the digitized Figure 3 data (no parameter is fitted here);
4. a model-free biomass-yield diagnosis of what the models miss;
5. a virtual loading sweep of degradation threshold times and enzyme titres;
6. variance-based global sensitivity of the threshold time;
7. an enzyme-level pH screen (P. chrysosporium BGL1A on cellobiose) with the
   environment-response guardrails it triggers.

Run from the repository root:

    python scripts/run_showcase_study.py --output outputs/showcase-study

Everything is retrospective. Held-out agreement is evidence about model
structure under these conditions, never biological validation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Callable

for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_variable, "1")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from fungal_model import VirtualExperiment  # noqa: E402
from fungal_model.api import EnvironmentGrid  # noqa: E402
from fungal_model.core.parameters import Parameter, ParameterSet  # noqa: E402
from fungal_model.core.units import Q_  # noqa: E402
from fungal_model.research import gelain_bayesian, gelain_heldout as gh  # noqa: E402
from fungal_model.uncertainty.global_sensitivity import global_sensitivity  # noqa: E402
from fungal_model.uncertainty.monte_carlo import ParameterUncertaintySpec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
POSTERIOR = ROOT / "data/benchmarks/gelain_2020_bayesian/results/posterior_samples.csv"
BAYES_RESULT = ROOT / "data/benchmarks/gelain_2020_bayesian/results/bayesian_calibration.json"
CRITICISM_COMPARISON = ROOT / "data/benchmarks/gelain_2020_criticism/results/stage_a/comparison.json"
REGISTRY_INDEX = ROOT / "data_registry/registry_index.yml"
SEED = 20261009
DENSE_TIMES = np.arange(0.0, 96.0 + 1e-9, 1.0)
SWEEP_LOADINGS = (2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0)
SHORT = {
    "k_h": "gelain_hydrolysis_k_h", "Kh": "gelain_hydrolysis_Kh", "Y": "gelain_hydrolysis_Y",
    "kd": "gelain_hydrolysis_kd", "K_ind": "gelain_hydrolysis_K_ind", "qF": "gelain_hydrolysis_qF",
    "kF": "gelain_hydrolysis_kF", "qB": "gelain_hydrolysis_qB", "kB": "gelain_hydrolysis_kB",
}
MEANING = {
    "k_h": "cellulose hydrolysis per unit cellulase",
    "Kh": "cellulose half-saturation of hydrolysis",
    "Y": "biomass yield on consumed cellulose",
    "kd": "biomass loss rate",
    "K_ind": "cellulose half-saturation of enzyme induction",
    "qF": "specific cellulase (FPase) production",
    "kF": "cellulase activity loss rate",
    "qB": "specific beta-glucosidase production",
    "kB": "beta-glucosidase activity loss rate",
}
OBS_LABEL = {
    "biomass": ("Biomass", "g/L"),
    "substrate": ("Cellulose", "g/L"),
    "cellulase_activity": ("Cellulase (FPase)", "FPU/L"),
    "beta_glucosidase_activity": ("β-glucosidase", "U/L"),
}

THEMES = {
    "light": {
        "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7",
        "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
        "s1_band": "#9ec5f4", "s1_band_light": "#cde2fb", "shade": "#f0efec",
        "seq": ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"],
    },
    "dark": {
        "surface": "#1a1a19", "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835",
        "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70",
        "s1_band": "#1c5cab", "s1_band_light": "#104281", "shade": "#262624",
        "seq": ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"],
    },
}


def log(message: str, started: float = time.perf_counter()) -> None:
    print(f"[{time.perf_counter() - started:7.1f} s] {message}", flush=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# =========================================================================== computations


def posterior_draws(n: int, rng: np.random.Generator) -> list[dict[str, float]]:
    rows = read_csv(POSTERIOR)
    picks = rng.choice(len(rows), size=n, replace=False)
    return [{key: float(rows[i][key]) for key in rows[i]} for i in picks]


def run_public_api(output: Path) -> dict[str, Any]:
    """The five culture conditions through VirtualExperiment in scientific mode."""

    study = VirtualExperiment.from_names(
        fungi=["T. harzianum P49P11"],
        substrates=["Celufloc 200"],
        environments=[gh.ENVIRONMENTS[loading] for loading in (10.0, 20.0, 30.0, 5.0, 40.0)],
        registry=REGISTRY_INDEX,
    )
    started = time.perf_counter()
    result = study.simulate(mode="scientific", output_dir=output / "virtual_experiment_t_harzianum")
    elapsed = time.perf_counter() - started
    bundle = Path(result.output_directory)
    thresholds = {}
    for row in read_csv(bundle / "threshold_times.csv"):
        thresholds.setdefault(row["environment_id"], {})[row["metric"]] = float(row["value"]) if row["value"] else None
    limitations = [row["limitation"] for row in read_csv(bundle / "limitations_table.csv")
                   if row["environment_id"] == gh.ENVIRONMENTS[40.0]]
    suggestions = sorted({(row["suggested_experiment"], row["rationale"]) for row in read_csv(bundle / "suggested_experiments.csv")})
    environment = read_csv(bundle / "environment_summary.csv")
    return {
        "output_directory": str(bundle.relative_to(ROOT)) if bundle.is_relative_to(ROOT) else str(bundle),
        "wall_time_s": elapsed,
        "files_written": sorted(p.name for p in bundle.iterdir() if p.is_file()),
        "threshold_times_h": thresholds,
        "scope_limitations_40gl": [text for text in limitations if "10-30 g/L" in text or "Scope" in text],
        "environment_guardrail": sorted({row["environment_guardrail"] for row in environment}),
        "environment_effect_status": sorted({row["environment_effect_status"] for row in environment}),
        "suggested_experiments": [{"experiment": e, "rationale": r} for e, r in suggestions],
    }


def predictive_bands(
    predictor: gh.FrozenPredictor, draws: list[dict[str, float]], loadings: tuple[float, ...], scales: np.ndarray,
    rng: np.random.Generator,
) -> dict[float, dict[str, np.ndarray]]:
    """5/50/95 % bands of the model mean and of new observations (mean plus the posterior noise model)."""

    relative_sd = float(gelain_bayesian.load_plan(ROOT)["error_model"]["relative_sd_to_training_max"])
    base_sd = relative_sd * scales
    bands = {}
    for loading in loadings:
        means = np.empty((len(draws), DENSE_TIMES.size, 4))
        for index, draw in enumerate(draws):
            values = {symbol: draw[symbol] for symbol in predictor.registry_symbols}
            means[index] = predictor.predict("registry_M0", loading, DENSE_TIMES, values=values)
        noise_scale = np.array([draw["noise_scale:all_observables"] for draw in draws])
        noisy = means + rng.standard_normal(means.shape) * (noise_scale[:, None, None] * base_sd[None, None, :])
        bands[loading] = {
            "mean_q": np.quantile(means, [0.05, 0.5, 0.95], axis=0),
            "obs_q": np.quantile(noisy, [0.05, 0.5, 0.95], axis=0),
            "frozen": predictor.predict("registry_M0", loading, DENSE_TIMES),
        }
    return bands


def coverage(bands: dict[float, dict[str, np.ndarray]], points: list[tuple[float, str, float, float]]) -> dict[str, Any]:
    """Fraction of observations inside the 90 % predictive interval for new observations."""

    inside, total = {}, {}
    for loading, name, t, value in points:
        k = gh.OBSERVABLES.index(name)
        i = int(np.argmin(np.abs(DENSE_TIMES - t)))
        lo, hi = bands[loading]["obs_q"][0, i, k], bands[loading]["obs_q"][2, i, k]
        key = f"{loading:g}gl"
        total[key] = total.get(key, 0) + 1
        inside[key] = inside.get(key, 0) + int(lo <= value <= hi)
    return {key: {"inside": inside[key], "n": total[key], "fraction": inside[key] / total[key]} for key in total}


def observed_metrics(series: dict[str, np.ndarray], loading: float) -> dict[str, float | None]:
    times = np.array((0.0, *gh.SAMPLING_TIMES_H))
    cellulose = np.concatenate([[loading], series["substrate"]])
    return {
        "t50_h": gh.threshold_time(times, cellulose, loading, 0.5),
        "t90_h": gh.threshold_time(times, cellulose, loading, 0.9),
        "peak_biomass": float(np.max(series["biomass"])),
        "peak_cellulase": float(np.max(series["cellulase_activity"])),
        "peak_beta_glucosidase": float(np.max(series["beta_glucosidase_activity"])),
        **{f"apparent_{k}": v for k, v in gh.apparent_yield(
            gh.SAMPLING_TIMES_H, series["biomass"], series["substrate"], gh.INITIAL_BIOMASS_G_L, loading).items()},
    }


def trajectory_metrics(trajectory: np.ndarray, loading: float) -> dict[str, float | None]:
    biomass, cellulose, fpase, bgl = (trajectory[:, k] for k in range(4))
    return {
        "t50_h": gh.threshold_time(DENSE_TIMES, cellulose, loading, 0.5),
        "t90_h": gh.threshold_time(DENSE_TIMES, cellulose, loading, 0.9),
        "peak_biomass": float(np.max(biomass)),
        "peak_cellulase": float(np.max(fpase)),
        "peak_beta_glucosidase": float(np.max(bgl)),
        "apparent_yield": gh.apparent_yield(DENSE_TIMES, biomass, cellulose, gh.INITIAL_BIOMASS_G_L, loading)["apparent_yield"],
    }


def loading_sweep(predictor: gh.FrozenPredictor, draws: list[dict[str, float]]) -> list[dict[str, Any]]:
    rows = []
    for loading in SWEEP_LOADINGS:
        _, virtual = predictor.environment_for(loading)
        per_draw = [trajectory_metrics(predictor.predict(
            "registry_M0", loading, DENSE_TIMES, values={s: d[s] for s in predictor.registry_symbols}), loading) for d in draws]
        point = {model: trajectory_metrics(predictor.predict(model, loading, DENSE_TIMES), loading)
                 for model in ("registry_M0", "M2_soluble_product_pool", "gelain_published")}
        for metric in ("t50_h", "t90_h", "peak_biomass", "peak_cellulase", "peak_beta_glucosidase", "apparent_yield"):
            values = np.array([m[metric] for m in per_draw if m[metric] is not None], dtype=float)
            rows.append({
                "loading_g_l": loading,
                "condition": "virtual" if virtual else ("held_out" if loading in gh.HELDOUT_LOADINGS else "training"),
                "metric": metric,
                "registry_M0_q05": float(np.quantile(values, 0.05)) if values.size else "",
                "registry_M0_median": float(np.median(values)) if values.size else "",
                "registry_M0_q95": float(np.quantile(values, 0.95)) if values.size else "",
                "draws_not_reaching_threshold": len(per_draw) - int(values.size),
                "registry_M0_frozen": point["registry_M0"][metric],
                "M2_frozen": point["M2_soluble_product_pool"][metric],
                "gelain_published": point["gelain_published"][metric],
            })
    return rows


def sensitivity(predictor: gh.FrozenPredictor, posterior: list[dict[str, str]], n_base: int) -> list[dict[str, Any]]:
    """Sobol/Jansen indices of threshold time and peak cellulase over independent posterior-marginal approximations."""

    logs = {short: np.log([float(r[symbol]) for r in posterior]) for short, symbol in SHORT.items()}
    base = []
    for short, symbol in SHORT.items():
        median = float(np.exp(np.median(logs[short])))
        base.append(Parameter(
            name=MEANING[short], symbol=symbol, value=median,
            units=str(predictor_units(predictor)[symbol]), uncertainty=None,
            source="Posterior median of the BAYES-001 posterior (data/benchmarks/gelain_2020_bayesian).",
            confidence_level="medium",
            notes="Nominal value for the sensitivity design only.",
        ))
    parameters = ParameterSet(base)
    def bound(short: str, value: float, which: str) -> Parameter:
        return Parameter(
            name=f"{short} posterior {which}", symbol=f"{which}_{short}", value=value,
            units=str(predictor_units(predictor)[SHORT[short]]), uncertainty=None,
            source="95% credible bound from data/benchmarks/gelain_2020_bayesian/results/posterior_samples.csv.",
            confidence_level="medium", notes="Sensitivity design bound.",
        )

    specs = []
    for short, symbol in SHORT.items():
        if short == "Y":
            # A yield must stay in [0, 1] (the template's dry-mass balance refuses anything else), so Y is
            # sampled uniformly over its 95% credible interval instead of from an unbounded lognormal.
            lo, hi = np.exp(np.quantile(logs[short], [0.025, 0.975]))
            specs.append(ParameterUncertaintySpec(
                symbol=symbol, distribution="uniform",
                source="Uniform over the BAYES-001 95% credible interval of the yield.",
                lower_bound=bound(short, float(lo), "lower"), upper_bound=bound(short, float(hi), "upper"),
                notes="Sobol indices assume independent inputs; posterior correlations are dropped.",
            ))
            continue
        specs.append(ParameterUncertaintySpec(
            symbol=symbol, distribution="lognormal",
            source="Lognormal approximation of the BAYES-001 posterior marginal (log-space standard deviation of the thinned samples).",
            log_standard_deviation=Parameter(
                name=f"{short} posterior log SD", symbol=f"log_sd_{short}", value=float(np.std(logs[short])),
                units="dimensionless", uncertainty=None,
                source="Computed from data/benchmarks/gelain_2020_bayesian/results/posterior_samples.csv.",
                confidence_level="medium", notes="Independent-input approximation.",
            ),
            notes="Sobol indices assume independent inputs; posterior correlations are dropped.",
        ))
    cache: dict[tuple[float, tuple[float, ...]], np.ndarray] = {}

    def trajectory(parameter_set: ParameterSet, loading: float) -> np.ndarray:
        values = {s: float(parameter_set.require_quantity(s).magnitude) for s in SHORT.values()}
        key = (loading, tuple(values[s] for s in SHORT.values()))
        if key not in cache:
            cache[key] = predictor.predict("registry_M0", loading, DENSE_TIMES, values=values)
        return cache[key]

    def t90(loading: float) -> Callable[[ParameterSet], Any]:
        def evaluate(parameter_set: ParameterSet) -> Any:
            value = gh.threshold_time(DENSE_TIMES, trajectory(parameter_set, loading)[:, 1], loading, 0.9)
            return Q_(96.0 if value is None else value, "hour")
        return evaluate

    def peak_fpase(loading: float) -> Callable[[ParameterSet], Any]:
        return lambda parameter_set: Q_(float(np.max(trajectory(parameter_set, loading)[:, 2])), "filter_paper_unit / liter")

    rows = []
    for output_id, function, units in (
        ("t90_20gl", t90(20.0), "hour"),
        ("t90_40gl", t90(40.0), "hour"),
        ("peak_cellulase_20gl", peak_fpase(20.0), "filter_paper_unit / liter"),
    ):
        result = global_sensitivity(
            base_parameters=parameters, uncertainty_specs=specs, predict_scalar=function, output_units=units,
            n_base_samples=n_base, random_seed=SEED, n_bootstrap=200, bootstrap_seed=SEED + 1,
        )
        for index in result.indices:
            short = next(k for k, v in SHORT.items() if v == index.symbol)
            rows.append({
                "output": output_id, "parameter": short, "meaning": MEANING[short],
                "first_order": index.first_order, "total_order": index.total_order,
                "first_order_lo": index.first_order_interval[0] if index.first_order_interval else "",
                "first_order_hi": index.first_order_interval[1] if index.first_order_interval else "",
                "total_order_lo": index.total_order_interval[0] if index.total_order_interval else "",
                "total_order_hi": index.total_order_interval[1] if index.total_order_interval else "",
                "output_sd": float(np.sqrt(result.output_variance.magnitude)), "units": units,
                "n_model_evaluations": result.n_model_evaluations,
            })
    return rows


_UNITS_CACHE: dict[str, str] = {}


def predictor_units(predictor: gh.FrozenPredictor) -> dict[str, str]:
    if not _UNITS_CACHE:
        config = predictor._base_factory(gh.VIRTUAL_BASE_ENVIRONMENT)({})  # noqa: SLF001 - reads the public config
        for block in config.parameters:
            for entry in block.parameters:
                parameter = Parameter.from_dict(entry)
                _UNITS_CACHE[parameter.symbol] = str(parameter.units)
    return _UNITS_CACHE


def ph_screen(output: Path) -> dict[str, Any]:
    """BGL1A on cellobiose across pH, plus the guardrails a careless screen would trip."""

    grid_ph = [round(float(v), 2) for v in np.arange(4.0, 8.0 + 1e-9, 0.25)]
    named = VirtualExperiment.from_names(
        fungi="P. chrysosporium", substrates="cellobiose",
        environments=[f"tsukada_2008_bgl1a_assay_30c_ph{p}" for p in (4, 5, 6, 7, 8)], registry=REGISTRY_INDEX,
    )
    registry_result = named.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=output / "virtual_experiment_bgl1a_ph", quicklook=False)
    bundle = Path(registry_result.output_directory)
    case_rows = read_csv(bundle / "case_summary.csv")
    fungus_id, substrate_id = case_rows[0]["fungus_id"], case_rows[0]["substrate_id"]
    curves: dict[float, dict[str, list[float]]] = {}
    for row in read_csv(bundle / "time_series_long.csv"):
        if row["state_role"] == "substrate":
            curves.setdefault(float(row["ph"]), {"t": [], "s": []})
            curves[float(row["ph"])]["t"].append(float(row["time"]))
            curves[float(row["ph"])]["s"].append(float(row["value"]))
    units = {row["units"] for row in read_csv(bundle / "time_series_long.csv") if row["state_role"] == "substrate"}
    time_units = {row["time_units"] for row in read_csv(bundle / "time_series_long.csv")}

    grid = VirtualExperiment.from_registry(
        fungi=fungus_id, substrates=substrate_id,
        environments=EnvironmentGrid(temperature_C=[30.0], ph=grid_ph), registry=REGISTRY_INDEX,
    )
    grid_result = grid.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=output / "virtual_experiment_bgl1a_ph_grid", quicklook=False)
    grid_rows = read_csv(Path(grid_result.output_directory) / "environment_summary.csv")
    half_times = sorted(
        (float(row["ph"]), float(row["median_time_to_50_percent_degradation"])) for row in grid_rows
    )

    blocked = VirtualExperiment.from_registry(
        fungi=fungus_id, substrates=substrate_id,
        environments=EnvironmentGrid(temperature_C=[30.0, 40.0], ph=[5.0]), registry=REGISTRY_INDEX,
    )
    blocked_result = blocked.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=output / "virtual_experiment_bgl1a_temperature_guardrail", quicklook=False)
    blocked_rows = read_csv(Path(blocked_result.output_directory) / "comparison_summary.csv")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        outside = VirtualExperiment.from_registry(
            fungi=fungus_id, substrates=substrate_id,
            environments=EnvironmentGrid(temperature_C=[30.0], ph=[9.0]), registry=REGISTRY_INDEX,
        )
        outside.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=output / "virtual_experiment_bgl1a_ph9_warning", quicklook=False)
    preflight = named.preflight(mode="scientific")[0]
    return {
        "fungus_id": fungus_id, "substrate_id": substrate_id,
        "substrate_units": sorted(units), "time_units": sorted(time_units),
        "curves": {str(k): v for k, v in sorted(curves.items())},
        "half_time_by_ph": half_times,
        "fastest_ph": min(half_times, key=lambda item: item[1]),
        "slowest_ph": max(half_times, key=lambda item: item[1]),
        "grid_comparison_allowed": sorted({row["environment_comparison_allowed"] for row in grid_rows}),
        "grid_ranking_allowed": sorted({row["environment_ranking_allowed"] for row in grid_rows}),
        "temperature_grid_ranking_allowed": sorted({row["ranking_allowed"] for row in blocked_rows}),
        "temperature_grid_blocking_reason": sorted({row["ranking_blocking_reason"] for row in blocked_rows}),
        "ph9_warnings": sorted({str(w.message) for w in caught if "pH" in str(w.message)})[:3],
        "scientific_preflight_status": preflight.status,
        "scientific_preflight_missing": sorted(item.item_id for item in preflight.missing),
    }


# =========================================================================== figures


def styled(theme: dict[str, Any]) -> dict[str, Any]:
    return {
        "figure.facecolor": theme["surface"], "axes.facecolor": theme["surface"], "savefig.facecolor": theme["surface"],
        "axes.edgecolor": theme["axis"], "axes.labelcolor": theme["ink2"], "axes.titlecolor": theme["ink"],
        "xtick.color": theme["muted"], "ytick.color": theme["muted"], "xtick.labelcolor": theme["ink2"],
        "ytick.labelcolor": theme["ink2"], "text.color": theme["ink"], "grid.color": theme["grid"],
        "axes.grid": True, "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
        "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"], "font.size": 9.5,
        "axes.titlesize": 10.5, "axes.titleweight": "semibold", "axes.titlelocation": "left",
        "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 2.0, "axes.axisbelow": True,
    }


def save(figure_function: Callable[[dict[str, Any]], Figure], name: str, directory: Path) -> list[str]:
    written = []
    for mode, theme in THEMES.items():
        with plt.rc_context(styled(theme)):
            figure = figure_function(theme)
            path = directory / f"{name}_{mode}.png"
            figure.savefig(path, dpi=180, bbox_inches="tight")
            plt.close(figure)
            written.append(path.name)
    return written


def _data_marker(ax: Any, theme: dict[str, Any], t: Any, y: Any, sd: Any = None, *, label: str | None = None,
                 hollow: bool = False) -> None:
    ax.errorbar(t, y, yerr=sd, fmt="o", ms=5.5, mfc=theme["surface"] if hollow else theme["ink"],
                mec=theme["ink"], mew=1.3, ecolor=theme["ink2"], elinewidth=1.0, capsize=2.5, zorder=6, label=label)


def figure_training(bands: dict, deposited: dict, training_sd: dict, published: dict) -> Callable:
    def build(theme: dict[str, Any]) -> Figure:
        fig, axes = plt.subplots(4, 3, figsize=(10.5, 10.2), sharex=True, constrained_layout=True)
        for col, loading in enumerate(gh.TRAINING_LOADINGS):
            band = bands[loading]
            for row, name in enumerate(gh.OBSERVABLES):
                ax = axes[row, col]
                ax.fill_between(DENSE_TIMES, band["mean_q"][0, :, row], band["mean_q"][2, :, row], color=theme["s1_band"],
                                lw=0, label="FungMod 90% posterior band" if (row, col) == (0, 0) else None)
                ax.plot(DENSE_TIMES, band["mean_q"][1, :, row], color=theme["s1"], label="FungMod registry case (posterior median)" if (row, col) == (0, 0) else None)
                ax.plot(DENSE_TIMES, published[loading][:, row], color=theme["s2"], ls=(0, (5, 2)), lw=1.6,
                        label="Gelain 2020 published model" if (row, col) == (0, 0) else None)
                sd = training_sd.get((loading, name))
                _data_marker(ax, theme, gh.SAMPLING_TIMES_H, deposited[loading][name], sd,
                             label="Measured (deposited means, digitized SD)" if (row, col) == (0, 0) else None)
                if row == 0:
                    ax.set_title(f"{loading:g} g/L cellulose (training)")
                if col == 0:
                    ax.set_ylabel(f"{OBS_LABEL[name][0]} ({OBS_LABEL[name][1]})")
                ax.set_ylim(bottom=0)
                if row == 3:
                    ax.set_xlabel("Time (h)")
        fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.045))
        return fig
    return build


def figure_identifiability(verdicts: dict[str, Any]) -> Callable:
    order = ["qB", "qF", "kd", "Y", "k_h", "Kh", "K_ind", "kF", "kB"]
    labels = {"identified": "identified", "bounded_below_only": "lower bound only", "bounded_above_only": "upper bound only",
              "weakly_identified": "weakly identified", "prior_dominated": "not identified"}

    def build(theme: dict[str, Any]) -> Figure:
        fig, ax = plt.subplots(figsize=(9.0, 4.6), constrained_layout=True)
        for i, short in enumerate(order):
            v = verdicts[SHORT[short]]
            lo, hi = (np.log10(x) for x in v["prior_box"])
            c_lo, c_hi = (np.log10(x) for x in v["credible_interval"])
            med = np.log10(v["posterior_median"])
            f = lambda x: (x - lo) / (hi - lo)  # noqa: E731
            y = len(order) - 1 - i
            ax.barh(y, 1.0, left=0, height=0.55, color=theme["shade"], edgecolor=theme["axis"], lw=0.6)
            colour = theme["s1"] if v["class"] == "identified" else theme["muted"]
            ax.barh(y, f(c_hi) - f(c_lo), left=f(c_lo), height=0.55, color=colour)
            ax.plot([f(med)], [y], marker="|", ms=16, mew=2.2, color=theme["ink"])
            ax.text(1.02, y, labels[v["class"]], va="center", fontsize=9, color=theme["ink2"])
        ax.set_yticks(range(len(order)), [f"{s}  ·  {MEANING[s]}" for s in reversed(order)])
        ax.set_xlim(0, 1.0)
        ax.set_xticks([0, 0.5, 1], ["prior lower bound", "", "prior upper bound"])
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("Position inside the prior range (log scale)")
        ax.set_title("What three published cultures can and cannot pin down (95% credible intervals)")
        return fig
    return build


def figure_digitization(check: dict[str, Any]) -> Callable:
    def build(theme: dict[str, Any]) -> Figure:
        fig, axes = plt.subplots(1, 4, figsize=(11.5, 3.2), constrained_layout=True)
        for ax, name in zip(axes, gh.OBSERVABLES, strict=True):
            rows = [r for r in check["rows"] if r["observable"] == name]
            plain = [r for r in rows if r["censored_upper_limit"] is None]
            cens = [r for r in rows if r["censored_upper_limit"] is not None]
            top = max(r["deposited"] for r in rows) * 1.08
            ax.plot([0, top], [0, top], color=theme["axis"], lw=1.2, zorder=1)
            ax.scatter([r["deposited"] for r in plain], [r["digitized"] for r in plain], s=26, color=theme["s1"],
                       edgecolor=theme["surface"], lw=0.8, zorder=3)
            if cens:
                ax.errorbar([r["deposited"] for r in cens], [0] * len(cens),
                            yerr=[[0] * len(cens), [r["censored_upper_limit"] for r in cens]], fmt="v", ms=5,
                            color=theme["muted"], elinewidth=1, capsize=2, zorder=2)
            errs = [abs(r["error_fraction_of_axis_span"]) * 100 for r in plain]
            ax.set_title(OBS_LABEL[name][0])
            ax.text(0.04, 0.95, f"n = {len(plain)} (+{len(cens)} at zero)\nmedian error {np.median(errs):.2f}% of axis\nworst {max(errs):.2f}%",
                    transform=ax.transAxes, va="top", fontsize=8.5, color=theme["ink2"])
            ax.set_xlabel(f"Deposited value ({OBS_LABEL[name][1]})")
            ax.set_xlim(0, top)
            ax.set_ylim(0, top)
        axes[0].set_ylabel("Digitized from Figure 2")
        return fig
    return build


def figure_heldout(bands: dict, heldout: list[gh.DigitizedObservation], predictions: dict) -> Callable:
    def build(theme: dict[str, Any]) -> Figure:
        fig, axes = plt.subplots(2, 4, figsize=(12.5, 6.3), sharex=True, constrained_layout=True)
        for r, loading in enumerate(gh.HELDOUT_LOADINGS):
            band = bands[loading]
            for k, name in enumerate(gh.OBSERVABLES):
                ax = axes[r, k]
                first = (r, k) == (0, 0)
                ax.fill_between(DENSE_TIMES, band["mean_q"][0, :, k], band["mean_q"][2, :, k], color=theme["s1_band"], lw=0,
                                label="FungMod registry case: 90% posterior band" if first else None)
                ax.plot(DENSE_TIMES, band["mean_q"][1, :, k], color=theme["s1"], label="FungMod registry case (M0)" if first else None)
                ax.plot(DENSE_TIMES, predictions["M2_soluble_product_pool"][loading][:, k], color=theme["s3"], ls=(0, (1.2, 1.6)), lw=2.2,
                        label="FungMod M2 soluble product pool" if first else None)
                ax.plot(DENSE_TIMES, predictions["gelain_published"][loading][:, k], color=theme["s2"], ls=(0, (5, 2)), lw=1.8,
                        label="Gelain 2020 published model" if first else None)
                rows = [o for o in heldout if o.condition_g_l == loading and o.observable == name]
                plain = [o for o in rows if not o.censored]
                _data_marker(ax, theme, [o.time_h for o in plain], [o.mean for o in plain], [o.sd or 0.0 for o in plain],
                             label="Held-out measurement (digitized mean ± SD)" if first else None)
                cens = [o for o in rows if o.censored]
                if cens:
                    ax.errorbar([o.time_h for o in cens], [0] * len(cens), yerr=[[0] * len(cens), [o.censored_upper_limit for o in cens]],
                                fmt="v", ms=5, mfc=theme["surface"], mec=theme["ink"], ecolor=theme["ink2"], elinewidth=1, capsize=2, zorder=6,
                                label="Held-out, at the zero line (upper limit)" if first else None)
                if r == 0:
                    ax.set_title(f"{OBS_LABEL[name][0]} ({OBS_LABEL[name][1]})")
                if k == 0:
                    ax.set_ylabel(f"{loading:g} g/L cellulose\n(never used for fitting)")
                if r == 1:
                    ax.set_xlabel("Time (h)")
                ax.set_ylim(bottom=0)
        fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.085))
        return fig
    return build


def figure_scoreboard(scores: dict[str, Any], internal: dict[str, float]) -> Callable:
    cells = [f"{L:g}gl:{n}" for L in gh.HELDOUT_LOADINGS for n in gh.OBSERVABLES]
    order = ["gelain_published", "M2_soluble_product_pool", "registry_M0", "M1_induction_state", "M3_conversion_dependent_accessibility"]

    def build(theme: dict[str, Any]) -> Figure:
        fig, (ax, bx) = plt.subplots(1, 2, figsize=(12.5, 3.9), gridspec_kw={"width_ratios": [2.3, 1]}, constrained_layout=True)
        matrix = np.array([[scores[m]["cells"][c]["nrmse_observed_range"] for c in cells] for m in order])
        # Sequential blue: low error recedes toward the surface, high error stands out, in both modes.
        dark_mode = theme["surface"] == THEMES["dark"]["surface"]
        steps = ["#1a2f4d", "#184f95", "#2a78d6", "#6da7ec", "#cde2fb"] if dark_mode else ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
        cmap = LinearSegmentedColormap.from_list("seq", steps)
        ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1.1, aspect="auto")
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                strong = matrix[i, j] >= 0.55
                ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=8.5,
                        color=("#0b0b0b" if strong else "#ffffff") if dark_mode else ("#ffffff" if strong else "#0b0b0b"))
        ax.set_xticks(range(len(cells)), [f"{c.split(':')[0].replace('gl', ' g/L')}\n{OBS_LABEL[c.split(':')[1]][0]}" for c in cells], fontsize=8)
        ax.set_yticks(range(len(order)), [gh.MODEL_LABELS[m] for m in order])
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title("Held-out error: RMSE / observed range (lower is better)")
        fungmod = ["M2_soluble_product_pool", "registry_M0", "M1_induction_state", "M3_conversion_dependent_accessibility"]
        short = {"registry_M0": "M0 (registry)", "M1_induction_state": "M1", "M2_soluble_product_pool": "M2",
                 "M3_conversion_dependent_accessibility": "M3"}
        y = np.arange(len(fungmod))[::-1]
        bx.barh(y + 0.19, [internal[m] for m in fungmod], height=0.36, color=theme["s1_band"],
                label="internal holdouts (inside 10-30 g/L)")
        bx.barh(y - 0.19, [scores[m]["mean_normalized_mse"] for m in fungmod], height=0.36, color=theme["s1"],
                label="external holdouts (5 and 40 g/L)")
        for yy, m in zip(y, fungmod, strict=True):
            bx.text(internal[m] + 0.003, yy + 0.19, f"{internal[m]:.3f}", va="center", fontsize=8, color=theme["ink2"])
            bx.text(scores[m]["mean_normalized_mse"] + 0.003, yy - 0.19, f"{scores[m]['mean_normalized_mse']:.3f}",
                    va="center", fontsize=8, color=theme["ink2"])
        bx.set_yticks(y, [short[m] for m in fungmod])
        published = scores["gelain_published"]["mean_normalized_mse"]
        bx.axvline(published, color=theme["s2"], lw=1.6, ls=(0, (5, 2)))
        bx.text(published + 0.003, y[0] + 0.62, f"Gelain published model, external {published:.3f}", fontsize=8,
                color=theme["ink2"], va="center")
        bx.set_xlim(0, 0.2)
        bx.set_ylim(-1.15, len(fungmod) - 0.15)
        bx.grid(axis="y", visible=False)
        bx.set_xlabel("Mean normalized MSE (lower is better)")
        bx.set_title("M2 ranks first inside and outside")
        bx.legend(loc="lower right", fontsize=8)
        return fig
    return build


def figure_yield(observed: dict[float, dict], sweep: list[dict[str, Any]], y_interval: tuple[float, float]) -> Callable:
    def series(metric: str, column: str) -> tuple[np.ndarray, np.ndarray]:
        rows = [r for r in sweep if r["metric"] == metric]
        return np.array([r["loading_g_l"] for r in rows]), np.array([float(r[column]) if r[column] != "" else np.nan for r in rows])

    def build(theme: dict[str, Any]) -> Figure:
        fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.9), constrained_layout=True)
        panels = (("apparent_yield", "apparent_apparent_yield", "Apparent yield at the biomass peak\n(g biomass per g cellulose consumed)"),
                  ("peak_biomass", "peak_biomass", "Peak biomass (g/L)"),
                  ("peak_cellulase", "peak_cellulase", "Peak cellulase (FPU/L)"))
        for ax, (metric, key, label) in zip(axes, panels, strict=True):
            ax.axvspan(10, 30, color=theme["shade"], lw=0, zorder=0)
            x, lo = series(metric, "registry_M0_q05")
            _, hi = series(metric, "registry_M0_q95")
            _, med = series(metric, "registry_M0_median")
            ax.fill_between(x, lo, hi, color=theme["s1_band"], lw=0)
            ax.plot(x, med, color=theme["s1"], label="FungMod registry case (M0)")
            _, m2 = series(metric, "M2_frozen")
            ax.plot(x, m2, color=theme["s3"], ls=(0, (1.2, 1.6)), lw=2.2, label="FungMod M2")
            _, pub = series(metric, "gelain_published")
            ax.plot(x, pub, color=theme["s2"], ls=(0, (5, 2)), lw=1.8, label="Gelain 2020 published")
            for loading, values in sorted(observed.items()):
                held = loading in gh.HELDOUT_LOADINGS
                ax.plot([loading], [values[key]], marker="D" if held else "o", ms=7, mfc=theme["surface"] if held else theme["ink"],
                        mec=theme["ink"], mew=1.5, ls="none", zorder=6)
            if metric == "apparent_yield":
                ax.axhspan(*y_interval, color=theme["s1_band_light"], lw=0, zorder=0.5)
                ax.text(58, y_interval[1] + 0.02, "M0 yield constant Y\n(95% credible)", ha="right", va="bottom", fontsize=8, color=theme["ink2"])
            ax.set_xlabel("Initial cellulose (g/L)")
            ax.set_title(label)
            ax.set_ylim(bottom=0)
            ax.text(20, ax.get_ylim()[1] * 0.97, "training range", ha="center", va="top", fontsize=8, color=theme["muted"])
        handles, labels = axes[1].get_legend_handles_labels()
        handles += [Line2D([], [], marker="o", ls="none", mfc=theme["ink"], mec=theme["ink"], ms=7),
                    Line2D([], [], marker="D", ls="none", mfc=theme["surface"], mec=theme["ink"], mew=1.5, ms=7)]
        labels += ["Measured, training loading", "Measured, held-out loading"]
        fig.legend(handles, labels, loc="upper center", ncol=5, bbox_to_anchor=(0.5, 1.1))
        return fig
    return build


def figure_thresholds(observed: dict[float, dict], sweep: list[dict[str, Any]]) -> Callable:
    def build(theme: dict[str, Any]) -> Figure:
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9), sharey=True, constrained_layout=True)
        for ax, metric, title in ((axes[0], "t50_h", "Time to degrade 50% of the cellulose"),
                                  (axes[1], "t90_h", "Time to degrade 90% of the cellulose")):
            rows = [r for r in sweep if r["metric"] == metric]
            x = np.array([r["loading_g_l"] for r in rows])
            ax.axvspan(10, 30, color=theme["shade"], lw=0, zorder=0)
            ax.fill_between(x, [r["registry_M0_q05"] for r in rows], [r["registry_M0_q95"] for r in rows], color=theme["s1_band"], lw=0)
            ax.plot(x, [r["registry_M0_median"] for r in rows], color=theme["s1"], label="FungMod registry case (M0), 90% band")
            ax.plot(x, [r["M2_frozen"] for r in rows], color=theme["s3"], ls=(0, (1.2, 1.6)), lw=2.2, label="FungMod M2")
            ax.plot(x, [r["gelain_published"] for r in rows], color=theme["s2"], ls=(0, (5, 2)), lw=1.8, label="Gelain 2020 published")
            for loading, values in sorted(observed.items()):
                held = loading in gh.HELDOUT_LOADINGS
                ax.plot([loading], [values[metric]], marker="D" if held else "o", ms=7, mfc=theme["surface"] if held else theme["ink"],
                        mec=theme["ink"], mew=1.5, ls="none", zorder=6)
            ax.set_title(title)
            ax.set_xlabel("Initial cellulose (g/L)")
            ax.text(20, 3, "training range", ha="center", fontsize=8, color=theme["muted"])
        axes[0].set_ylabel("Hours after inoculation")
        axes[0].set_ylim(0, None)
        handles, labels = axes[0].get_legend_handles_labels()
        handles += [Line2D([], [], marker="o", ls="none", mfc=theme["ink"], mec=theme["ink"], ms=7),
                    Line2D([], [], marker="D", ls="none", mfc=theme["surface"], mec=theme["ink"], mew=1.5, ms=7)]
        labels += ["Measured (interpolated), training", "Measured (interpolated), held-out"]
        fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.13))
        return fig
    return build


def figure_sensitivity(rows: list[dict[str, Any]]) -> Callable:
    outputs = (("t90_20gl", "Time to 90% degradation, 20 g/L"), ("t90_40gl", "Time to 90% degradation, 40 g/L"),
               ("peak_cellulase_20gl", "Peak cellulase, 20 g/L"))

    def build(theme: dict[str, Any]) -> Figure:
        fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.9), sharey=True, constrained_layout=True)
        order = list(SHORT)
        for ax, (output_id, title) in zip(axes, outputs, strict=True):
            sub = {r["parameter"]: r for r in rows if r["output"] == output_id}
            y = np.arange(len(order))[::-1]
            total = [sub[p]["total_order"] for p in order]
            first = [sub[p]["first_order"] for p in order]
            ax.barh(y, total, height=0.62, color=theme["s1_band"], label="total effect (with interactions)")
            ax.barh(y, first, height=0.32, color=theme["s1"], label="first-order effect (alone)")
            ax.set_yticks(y, [f"{p}" for p in order])
            ax.set_xlim(0, max(1.0, max(total) * 1.05))
            sd = next(iter(sub.values()))["output_sd"]
            ax.set_title(f"{title}\n(output SD {sd:.1f} {'h' if output_id.startswith('t90') else 'FPU/L'})")
            ax.set_xlabel("Share of output variance")
            ax.grid(axis="y", visible=False)
        fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.08))
        return fig
    return build


def figure_ph(ph: dict[str, Any]) -> Callable:
    def build(theme: dict[str, Any]) -> Figure:
        fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.5, 3.8), constrained_layout=True)
        scale = 60.0 if ph["time_units"] == ["second"] else 1.0
        ends: list[tuple[float, float, list[str]]] = []
        for colour, (key, curve) in zip(theme["seq"], ph["curves"].items(), strict=True):
            t = np.array(curve["t"]) / scale
            ax.plot(t, curve["s"], color=colour, label=f"pH {float(key):g}")
            for end in ends:
                if abs(end[1] - curve["s"][-1]) < 0.15:
                    end[2].append(f"{float(key):g}")
                    break
            else:
                ends.append((float(t[-1]), float(curve["s"][-1]), [f"{float(key):g}"]))
        for t_end, s_end, keys in ends:
            ax.text(t_end * 1.01, s_end, "pH " + " and ".join(keys), va="center", fontsize=8, color=theme["ink2"])
        ax.set_xlim(right=ax.get_xlim()[1] * 1.12)
        ax.set_xlabel("Time (min)" if scale == 60.0 else f"Time ({ph['time_units'][0]})")
        ax.set_ylabel(f"Cellobiose remaining ({ph['substrate_units'][0]})")
        ax.set_title("BGL1A hydrolysing cellobiose at five assay pH values")
        ax.set_ylim(bottom=0)
        x = [p for p, _ in ph["half_time_by_ph"]]
        y = [h / scale for _, h in ph["half_time_by_ph"]]
        bx.plot(x, y, color=theme["s1"], marker="o", ms=4)
        best = ph["fastest_ph"]
        bx.annotate(f"fastest at pH {best[0]:g}\n({best[1] / scale:.1f} min)", (best[0], best[1] / scale),
                    xytext=(best[0] + 0.6, best[1] / scale + (max(y) - min(y)) * 0.35), fontsize=8.5, color=theme["ink2"],
                    arrowprops={"arrowstyle": "-", "color": theme["muted"], "lw": 0.8})
        bx.set_xlabel("Assay pH (registry law measured on pH 4-8)")
        bx.set_ylabel("Time to 50% conversion (min)" if scale == 60.0 else "Time to 50% conversion")
        bx.set_title("Half-conversion time across a 17-point pH grid")
        return fig
    return build


# =========================================================================== main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draws", type=int, default=400, help="Posterior draws for the predictive bands.")
    parser.add_argument("--sweep-draws", type=int, default=200, help="Posterior draws per sweep loading.")
    parser.add_argument("--sobol-n", type=int, default=512, help="Base samples for each Sobol design.")
    args = parser.parse_args(argv)
    output: Path = args.output if args.output.is_absolute() else ROOT / args.output
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    log("1/7 public API: VirtualExperiment in scientific mode for five culture conditions")
    public = run_public_api(output)
    log(f"    wrote {len(public['files_written'])} tables in {public['wall_time_s']:.1f} s")

    log("2/7 posterior predictive bands from the recorded BAYES-001 posterior")
    predictor = gh.FrozenPredictor(ROOT)
    scales = gh.training_scales(ROOT)
    draws = posterior_draws(args.draws, rng)
    bands = predictive_bands(predictor, draws, (10.0, 20.0, 30.0, 5.0, 40.0), scales, rng)

    log("3/7 frozen predictions of five models on the held-out loadings")
    heldout = list(gh.load_digitized(ROOT))
    training_digitized = gh.load_digitized(ROOT, gh.TRAINING_SD_CSV)
    deposited = gh.deposited_training_means(ROOT)
    predictions = {m: {L: predictor.predict(m, L, DENSE_TIMES) for L in (5.0, 10.0, 20.0, 30.0, 40.0)} for m in gh.MODEL_IDS}
    scores = {m: gh.score_model(lambda L, m=m: predictor.predict(m, L, gh.SAMPLING_TIMES_H), heldout, scales) for m in gh.MODEL_IDS}
    internal = {m: json.loads(CRITICISM_COMPARISON.read_text())["models"][m]["scenarios"]["primary"]["mean_normalized_mse"]
                for m in ("M0_baseline", *gh.CRITICISM_MODELS)}
    internal["registry_M0"] = internal.pop("M0_baseline")
    training_scores = {m: gh.score_model(
        lambda L, m=m: predictor.predict(m, L, gh.SAMPLING_TIMES_H),
        [gh.DigitizedObservation(L, n, t, float(deposited[L][n][i]), None, 0.0, None, 0.0, ()) for L in gh.TRAINING_LOADINGS
         for n in gh.OBSERVABLES for i, t in enumerate(gh.SAMPLING_TIMES_H)],
        scales, loadings=gh.TRAINING_LOADINGS)["mean_normalized_mse"] for m in gh.MODEL_IDS}
    heldout_points = [(o.condition_g_l, o.observable, o.time_h, o.mean) for o in heldout if not o.censored]
    training_points = [(L, n, t, float(deposited[L][n][i])) for L in gh.TRAINING_LOADINGS for n in gh.OBSERVABLES
                       for i, t in enumerate(gh.SAMPLING_TIMES_H)]
    cover = {"held_out": coverage(bands, heldout_points), "training": coverage(bands, training_points)}
    log(f"    held-out mean normalized MSE: { {m: round(s['mean_normalized_mse'], 4) for m, s in scores.items()} }")

    log("4/7 model-free yield diagnosis and 5/7 virtual loading sweep")
    observed: dict[float, dict[str, Any]] = {}
    for loading in gh.TRAINING_LOADINGS:
        observed[loading] = observed_metrics(deposited[loading], loading)
    for loading in gh.HELDOUT_LOADINGS:
        series = {}
        for name in gh.OBSERVABLES:
            lookup = {o.time_h: o.mean for o in heldout if o.condition_g_l == loading and o.observable == name}
            series[name] = np.array([lookup.get(t, np.nan) for t in gh.SAMPLING_TIMES_H])
        series["beta_glucosidase_activity"] = np.nan_to_num(series["beta_glucosidase_activity"], nan=0.0)
        observed[loading] = observed_metrics(series, loading)
    sweep = loading_sweep(predictor, draws[: args.sweep_draws])
    posterior_rows = read_csv(POSTERIOR)
    y_values = np.array([float(r[SHORT["Y"]]) for r in posterior_rows])
    y_interval = (float(np.quantile(y_values, 0.025)), float(np.quantile(y_values, 0.975)))

    log("6/7 global sensitivity of the degradation threshold time")
    sobol = sensitivity(predictor, posterior_rows, args.sobol_n)

    log("7/7 enzyme-level pH screen and guardrails")
    ph = ph_screen(output)

    log("figures")
    bayes = json.loads(BAYES_RESULT.read_text(encoding="utf-8"))
    verdicts = {
        symbol: {
            "class": verdict["class"],
            "credible_interval": verdict["credible_interval"],
            "prior_box": verdict["prior_bounds"],
            "posterior_median": bayes["summaries"][symbol]["median"],
        }
        for symbol, verdict in bayes["identifiability"].items()
    }
    calibration_check = json.loads((ROOT / gh.HELDOUT_DIR / "digitization_calibration.json").read_text())["calibration_check"]
    training_sd = {}
    for o in training_digitized:
        training_sd.setdefault((o.condition_g_l, o.observable), {})[o.time_h] = o.sd or 0.0
    training_sd = {key: [value.get(t, 0.0) for t in gh.SAMPLING_TIMES_H] for key, value in training_sd.items()}
    published_dense = {L: predictions["gelain_published"][L] for L in gh.TRAINING_LOADINGS}
    written = []
    written += save(figure_training(bands, deposited, training_sd, published_dense), "fig1_training_fit", figures)
    written += save(figure_identifiability(verdicts), "fig2_identifiability", figures)
    written += save(figure_digitization(calibration_check), "fig3_digitization_check", figures)
    written += save(figure_heldout(bands, heldout, predictions), "fig4_heldout_prediction", figures)
    written += save(figure_scoreboard(scores, internal), "fig5_scoreboard", figures)
    written += save(figure_yield(observed, sweep, y_interval), "fig6_yield_diagnosis", figures)
    written += save(figure_thresholds(observed, sweep), "fig7_threshold_times", figures)
    written += save(figure_sensitivity(sobol), "fig8_sensitivity", figures)
    written += save(figure_ph(ph), "fig9_ph_screen", figures)

    score_rows = []
    for m, s in scores.items():
        for cell in s["cells"].values():
            score_rows.append({"model": m, "label": gh.MODEL_LABELS[m], **cell})
    write_csv(output / "heldout_scores.csv", score_rows)
    write_csv(output / "loading_sweep.csv", sweep)
    write_csv(output / "sensitivity_indices.csv", sobol)
    results = {
        "study": "FungMod showcase: T. harzianum P49P11 on cellulose, frozen predictions of held-out loadings",
        "claim_boundary": gh.CLAIM_BOUNDARY,
        "seed": SEED,
        "settings": {"posterior_draws": args.draws, "sweep_draws": args.sweep_draws, "sobol_base_samples": args.sobol_n},
        "inputs": {str(p.relative_to(ROOT)): sha256(p) for p in (
            POSTERIOR, BAYES_RESULT, CRITICISM_COMPARISON, ROOT / gh.HELDOUT_CSV, ROOT / gh.TRAINING_SD_CSV,
            ROOT / gh.SOURCE_PARAMETERS, ROOT / "data_registry/parameters/parameter_records.yml",
            ROOT / "data_registry/environments/environments.yml")},
        "frozen_models": {m: {"label": f.label, "source": f.source, "source_sha256": f.source_sha256} for m, f in predictor.models.items()},
        "public_api": public,
        "digitization_check": {k: v for k, v in calibration_check.items() if k != "rows"},
        "heldout_counts": {"observations": len(heldout), "with_sd": sum(o.sd is not None for o in heldout),
                           "censored": sum(o.censored for o in heldout)},
        "heldout_scores": {m: {k: v for k, v in s.items() if k != "cells"} for m, s in scores.items()},
        "heldout_cells": {m: s["cells"] for m, s in scores.items()},
        "internal_holdout_mean_normalized_mse": internal,
        "training_fit_mean_normalized_mse": training_scores,
        "predictive_coverage_90": cover,
        "observed_metrics": {f"{k:g}": v for k, v in observed.items()},
        "posterior_yield_95": y_interval,
        "identifiability": verdicts,
        "ph_screen": {k: v for k, v in ph.items() if k != "curves"},
        "figures": written,
    }
    (output / "results.json").write_text(json.dumps(results, indent=1, default=float) + "\n", encoding="utf-8")
    log(f"wrote results.json, three tables and {len(written)} figure files to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
