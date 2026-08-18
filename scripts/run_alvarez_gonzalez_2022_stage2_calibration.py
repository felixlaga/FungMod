"""Fit FungMod parameters on one Alvarez-Gonzalez 2022 series, then predict held-out ones.

Stage 1 (``run_alvarez_gonzalez_2022_holdout_prediction.py``) asked whether the
publication's own Model 3 parameters predict the three undigitized Figure S1
series. This script asks the different question: if FungMod estimates the
parameters itself from a single training series, do those estimates transfer?

Design:

- Training series: Figure S1A filled squares, 20 g/L cellobiose, 59.2 mg/L free
  enzyme. All nine points are used for fitting; no split is taken inside it.
- Held-out series: the other three Figure S1 series. None of them influences the
  fit in any way.

The headline held-out condition is Figure S1A open squares. It shares the
training enzyme loading, so predicting it requires changing only the initial
substrate concentration and no parameter at all.

The two panel-B conditions additionally require an enzyme-loading assumption.
The Figure S1 caption prints panel A as 59.2 mg/L and panel B as 296.1 mg/mL.
The literal mg/mL reading is refuted by the data itself: it implies an initial
rate near 7.06e4 mM/min, which would exhaust the 222 mM panel-B charge in about
0.19 s, whereas the source reports 36.66 mM still present at 60 min. The mg/L
reading is therefore adopted, giving an enzyme ratio of 296.1/59.2 = 5.002. That
adoption is recorded as an assumption, not as a source statement.

Fitting a published dataset is parameter estimation. It is not validation, and
all four series come from one figure in one publication by one laboratory, so
even the held-out results demonstrate transfer across conditions rather than
independent replication.

Usage::

    python scripts/run_alvarez_gonzalez_2022_stage2_calibration.py
"""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from fungal_model import run_configured_model
from fungal_model.calibration import calibrate_configured_model
from fungal_model.data import (
    ObservableMapping,
    evaluate_model_against_dataset,
    load_experiment_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "data/model_configs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison.yml"
DATASET_DIR = ROOT / "data/experiments/literature/alvarez_gonzalez_2022_free_beta_glucosidase"
TRAINING_DATASET = DATASET_DIR / "alvarez_gonzalez_2022_free_beta_glucosidase.yml"

ENZYME_LOADING_RATIO = 296.1 / 59.2
SUBSTRATE_STATE = "cellobiose_concentration"
VMAX_SYMBOL = "V_max_cellobiose_2022"

# Published Model 3 point estimates, used as the optimizer starting point.
PUBLISHED = {
    "V_max_cellobiose_2022": 19.72544,
    "K_m_cellobiose_2022": 43.0,
    "K_p_glucose_2022": 34.0,
    "K_i_cellobiose_2022": 1088.0,
}

# Physically admissible search ranges. These are model-domain bounds, not
# sourced biological ranges.
BOUNDS = {
    "V_max_cellobiose_2022": (1.0e-3, 500.0),
    "K_m_cellobiose_2022": (1.0e-3, 1000.0),
    "K_p_glucose_2022": (1.0e-3, 1000.0),
    "K_i_cellobiose_2022": (1.0, 100000.0),
}

OBSERVABLE_MAPPING = (
    ObservableMapping(
        dataset_measurement_id="cellobiose_concentration",
        model_observable=SUBSTRATE_STATE,
        observable_type="state",
    ),
)


@dataclass(frozen=True)
class Holdout:
    key: str
    dataset_file: str
    initial_cellobiose_mM: float
    vmax_scale: float
    assumption: str


HOLDOUTS = (
    Holdout(
        "panel_a_70gl",
        "alvarez_gonzalez_2022_figure_s1a_open_squares.yml",
        227.18,
        1.0,
        "None. Same enzyme loading as training; only the initial substrate concentration changes.",
    ),
    Holdout(
        "panel_b_20gl",
        "alvarez_gonzalez_2022_figure_s1b_filled_squares.yml",
        62.45,
        ENZYME_LOADING_RATIO,
        "Adopts the mg/L reading of the panel-B caption; V_max scaled by 296.1/59.2 via V_max = k_cat*[E].",
    ),
    Holdout(
        "panel_b_70gl",
        "alvarez_gonzalez_2022_figure_s1b_open_squares.yml",
        222.27,
        ENZYME_LOADING_RATIO,
        "Adopts the mg/L reading of the panel-B caption; V_max scaled by 296.1/59.2 via V_max = k_cat*[E].",
    ),
)

# Two parameterizations: the full four-parameter model, and a reduced model that
# holds the weakly-informed substrate-inhibition constant at its published value.
PARAMETERIZATIONS = {
    "full_4p": ("V_max_cellobiose_2022", "K_m_cellobiose_2022", "K_p_glucose_2022", "K_i_cellobiose_2022"),
    "reduced_3p": ("V_max_cellobiose_2022", "K_m_cellobiose_2022", "K_p_glucose_2022"),
}


def _absolute_paths(config: dict) -> dict:
    resolved = copy.deepcopy(config)
    for value in resolved.get("entities", {}).values():
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and "path" in item:
                item["path"] = str((BASE_CONFIG.parent / ".." / ".." / item["path"]).resolve())
    return resolved


def _config_with(values: dict[str, float], initial: float, vmax_scale: float, outdir: str) -> dict:
    config = _absolute_paths(yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8")))
    config["initial_state"]["states"][SUBSTRATE_STATE]["value"] = float(initial)
    for parameter_set in config["parameters"]:
        for parameter in parameter_set["parameters"]:
            symbol = parameter["symbol"]
            if symbol in values:
                parameter["value"] = float(values[symbol])
            if symbol == VMAX_SYMBOL:
                parameter["value"] = float(parameter["value"] * vmax_scale)
    config["outputs"]["directory"] = outdir
    return config


def _predict(values: dict[str, float], holdout: Holdout) -> dict:
    config = _config_with(values, holdout.initial_cellobiose_mM, holdout.vmax_scale, f"outputs/_stage2/{holdout.key}")
    with tempfile.TemporaryDirectory(prefix="fungmod_stage2_") as directory:
        path = Path(directory) / "config.yml"
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        result = run_configured_model(path, output_dir=Path(directory) / "out")
    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=load_experiment_dataset(DATASET_DIR / holdout.dataset_file),
        observable_mapping=OBSERVABLE_MAPPING,
    )
    return {
        "dataset_id": comparison.dataset_id,
        "rmse": float(comparison.metrics["rmse"]),
        "n_points": int(comparison.metrics["n_points"]),
        "relative_rmse_percent": 100.0 * float(comparison.metrics["rmse"]) / holdout.initial_cellobiose_mM,
        "assumption": holdout.assumption,
    }


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "design": {
            "training_series": "Figure S1A filled squares, 20 g/L, 59.2 mg/L free enzyme, all 9 points",
            "held_out_series": [h.key for h in HOLDOUTS],
            "independence": (
                "All series come from one figure in one publication by one laboratory. "
                "Held-out agreement demonstrates transfer across experimental conditions, "
                "not independent experimental replication."
            ),
            "unit_decision": (
                "The literal panel-B caption unit mg/mL is refuted by the data: it implies "
                "exhaustion of the 222 mM charge in about 0.19 s against 36.66 mM observed at "
                "60 min. The mg/L reading (ratio 5.002) is adopted as a recorded assumption."
            ),
        },
        "published_reference": PUBLISHED,
        "parameterizations": {},
    }

    for label, symbols in PARAMETERIZATIONS.items():
        calibration = calibrate_configured_model(
            model_config=BASE_CONFIG,
            dataset=TRAINING_DATASET,
            parameter_symbols=list(symbols),
            observable_mapping=OBSERVABLE_MAPPING,
            initial_guess={s: PUBLISHED[s] for s in symbols},
            bounds={s: BOUNDS[s] for s in symbols},
            output_dir=output_dir / label / "calibration",
        )
        fitted = {
            symbol: float(calibration.fitted_parameters.get(symbol).value)
            for symbol in symbols
        }
        held = {h.key: _predict({**PUBLISHED, **fitted}, h) for h in HOLDOUTS}
        summary["parameterizations"][label] = {
            "fitted_symbols": list(symbols),
            "dataset_maturity": calibration.dataset_maturity,
            "success": calibration.success,
            "fitted_values": fitted,
            "published_values": {s: PUBLISHED[s] for s in symbols},
            "ratio_fitted_over_published": {s: fitted[s] / PUBLISHED[s] for s in symbols},
            "train_metrics": {k: float(v) for k, v in calibration.metrics.items()},
            "jacobian_rank": calibration.optimizer_metadata.get("jacobian_rank"),
            "confidence_intervals": calibration.optimizer_metadata.get("confidence_intervals"),
            "warnings": list(calibration.warnings),
            "held_out": held,
        }

    (output_dir / "stage2_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/alvarez_gonzalez_2022_stage2")
    arguments = parser.parse_args()
    summary = run(arguments.output_dir)

    for label, entry in summary["parameterizations"].items():
        print(f"\n=== {label}  (maturity fitted: {entry['dataset_maturity']}, success={entry['success']}) ===")
        print(f"  training RMSE = {entry['train_metrics'].get('train_rmse', float('nan')):.4f} mM"
              f"   Jacobian rank = {entry['jacobian_rank']} of {len(entry['fitted_symbols'])}")
        print("  fitted vs published:")
        for symbol in entry["fitted_symbols"]:
            print(f"    {symbol:26s} {entry['fitted_values'][symbol]:12.4f}"
                  f"  (published {entry['published_values'][symbol]:9.3f},"
                  f"  ratio {entry['ratio_fitted_over_published'][symbol]:6.3f})")
        print("  held-out predictions:")
        for key, held in entry["held_out"].items():
            print(f"    {key:14s} RMSE = {held['rmse']:8.4f} mM  ({held['relative_rmse_percent']:5.2f}% of initial)")
    print(f"\nwrote {arguments.output_dir / 'stage2_summary.json'}")


if __name__ == "__main__":
    main()
