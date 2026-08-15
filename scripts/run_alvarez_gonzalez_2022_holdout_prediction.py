"""Predict three held-out Alvarez-Gonzalez 2022 conditions without refitting.

The repository already contains a model configuration whose four kinetic
parameters are transcribed from the publication's own Model 3 and which
reproduces the Figure S1A filled-square (20 g/L) series. This script takes those
same four parameters, changes nothing about the kinetic model, and asks whether
they predict the three remaining series of Figure S1.

Held-out conditions and the exact overrides applied to the base configuration:

- ``panel_a_70gl``: initial cellobiose only. No kinetic parameter is changed, so
  this condition is a parameter-free extrapolation to roughly 3.6 times the
  training initial substrate concentration. It is the assumption-free test.
- ``panel_b_20gl`` and ``panel_b_70gl``: initial cellobiose, plus V_max scaled by
  the caption enzyme-loading ratio 296.1 / 59.2. The scaling follows the
  definition V_max = k_cat * [E] and introduces no fitted quantity, but it does
  depend on reading the panel-B caption unit as mg/L rather than the printed
  mg/mL. That reading is an assumption, not a source statement, and is recorded
  as such in the output.

No parameter is estimated from any held-out series. The exact resolved
configuration used for each condition is archived next to its results.

All four series come from one figure in one publication by one laboratory.
Agreement therefore demonstrates transfer across experimental conditions. It is
not independent experimental replication and must not be reported as such.

Usage::

    python scripts/run_alvarez_gonzalez_2022_holdout_prediction.py \
        --output-dir outputs/alvarez_gonzalez_2022_holdout_prediction
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from fungal_model import run_configured_model
from fungal_model.data import (
    ObservableMapping,
    evaluate_model_against_dataset,
    load_experiment_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "data/model_configs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison.yml"
DATASET_DIR = ROOT / "data/experiments/literature/alvarez_gonzalez_2022_free_beta_glucosidase"

TRAINING_DATASET = DATASET_DIR / "alvarez_gonzalez_2022_free_beta_glucosidase.yml"

# Caption enzyme loadings. The panel-B unit is printed as mg/mL in the source
# while panel A is printed as mg/L; see the dataset records for the unresolved
# inconsistency. Only the ratio enters the model.
PANEL_A_ENZYME_MG_PER_L = 59.2
PANEL_B_ENZYME_CAPTION_VALUE = 296.1
ENZYME_LOADING_RATIO = PANEL_B_ENZYME_CAPTION_VALUE / PANEL_A_ENZYME_MG_PER_L

VMAX_SYMBOL = "V_max_cellobiose_2022"
SUBSTRATE_STATE = "cellobiose_concentration"


@dataclass(frozen=True)
class HoldoutCondition:
    """One held-out series and the overrides needed to predict it."""

    key: str
    dataset_file: str
    initial_cellobiose_mM: float
    vmax_scale: float
    assumption: str


CONDITIONS = (
    HoldoutCondition(
        key="panel_a_70gl",
        dataset_file="alvarez_gonzalez_2022_figure_s1a_open_squares.yml",
        initial_cellobiose_mM=227.18,
        vmax_scale=1.0,
        assumption=(
            "None. Panel A shares the training enzyme loading, so only the initial "
            "substrate concentration changes and no kinetic parameter is altered."
        ),
    ),
    HoldoutCondition(
        key="panel_b_20gl",
        dataset_file="alvarez_gonzalez_2022_figure_s1b_filled_squares.yml",
        initial_cellobiose_mM=62.45,
        vmax_scale=ENZYME_LOADING_RATIO,
        assumption=(
            "Assumes the panel-B caption loading of 296.1 is mg/L rather than the "
            "printed mg/mL, giving a 296.1/59.2 enzyme ratio and a proportional "
            "V_max through V_max = k_cat * [E]. The source prints inconsistent units."
        ),
    ),
    HoldoutCondition(
        key="panel_b_70gl",
        dataset_file="alvarez_gonzalez_2022_figure_s1b_open_squares.yml",
        initial_cellobiose_mM=222.27,
        vmax_scale=ENZYME_LOADING_RATIO,
        assumption=(
            "Assumes the panel-B caption loading of 296.1 is mg/L rather than the "
            "printed mg/mL, giving a 296.1/59.2 enzyme ratio and a proportional "
            "V_max through V_max = k_cat * [E]. The source prints inconsistent units."
        ),
    ),
)

OBSERVABLE_MAPPING = (
    ObservableMapping(
        dataset_measurement_id="cellobiose_concentration",
        model_observable=SUBSTRATE_STATE,
        observable_type="state",
    ),
)


def _absolute_paths(config: dict, config_path: Path) -> dict:
    """Rewrite relative entity paths so a config can run from a temp directory."""

    resolved = copy.deepcopy(config)
    entities = resolved.get("entities", {})
    for value in entities.values():
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict) and "path" in item:
                item["path"] = str((config_path.parent / ".." / ".." / item["path"]).resolve())
    return resolved


def _config_for(condition: HoldoutCondition, base: dict, base_path: Path) -> dict:
    """Apply exactly the documented overrides for one held-out condition."""

    config = _absolute_paths(base, base_path)
    config["name"] = f"{base['name']} - held-out {condition.key}"
    config["initial_state"]["states"][SUBSTRATE_STATE]["value"] = condition.initial_cellobiose_mM

    if condition.vmax_scale != 1.0:
        scaled = False
        for parameter_set in config["parameters"]:
            for parameter in parameter_set["parameters"]:
                if parameter["symbol"] == VMAX_SYMBOL:
                    parameter["value"] = parameter["value"] * condition.vmax_scale
                    parameter["notes"] = (
                        f"{parameter['notes']} Scaled by the caption enzyme-loading ratio "
                        f"{condition.vmax_scale:.6f} for held-out condition {condition.key}; "
                        "no quantity is fitted."
                    )
                    scaled = True
        if not scaled:
            raise SystemExit(f"Could not find {VMAX_SYMBOL} to scale.")

    config["provenance"]["notes"] = (
        f"Held-out prediction for {condition.key}. Kinetic parameters are the publication's "
        f"own Model 3 values; no FungMod fit is performed against any series. {condition.assumption}"
    )
    config["outputs"] = copy.deepcopy(base.get("outputs", {}))
    config["outputs"]["directory"] = f"outputs/alvarez_gonzalez_2022_holdout_prediction/{condition.key}/model"
    return config


def run(output_dir: Path) -> dict:
    base = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Training-condition reference: the already published no-refit comparison.
    training_result = run_configured_model(BASE_CONFIG, output_dir=output_dir / "training_model")
    training_comparison = evaluate_model_against_dataset(
        result=training_result,
        dataset=load_experiment_dataset(TRAINING_DATASET),
        observable_mapping=OBSERVABLE_MAPPING,
    )
    summary: dict = {
        "design": {
            "training_condition": "Figure S1A filled squares, 20 g/L, panel-A enzyme loading",
            "training_role": "reference only; the model parameters are the publication's own Model 3 values and were not fitted by FungMod",
            "held_out_series": [c.key for c in CONDITIONS],
            "fitted_parameters": [],
            "independence": (
                "All series come from one figure in one publication by one laboratory. "
                "This is out-of-sample transfer across experimental conditions, not "
                "independent experimental replication."
            ),
        },
        "training": {
            "dataset_id": training_comparison.dataset_id,
            "metrics": dict(training_comparison.metrics),
        },
        "held_out": {},
    }

    for condition in CONDITIONS:
        config = _config_for(condition, base, BASE_CONFIG)
        condition_dir = output_dir / condition.key
        condition_dir.mkdir(parents=True, exist_ok=True)
        archived = condition_dir / "resolved_config.yml"
        archived.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="fungmod_holdout_") as directory:
            run_path = Path(directory) / "config.yml"
            run_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            result = run_configured_model(run_path, output_dir=condition_dir / "model")

        dataset = load_experiment_dataset(DATASET_DIR / condition.dataset_file)
        comparison = evaluate_model_against_dataset(
            result=result,
            dataset=dataset,
            observable_mapping=OBSERVABLE_MAPPING,
        )
        points = comparison.residuals[0].points
        summary["held_out"][condition.key] = {
            "dataset_id": comparison.dataset_id,
            "initial_cellobiose_mM": condition.initial_cellobiose_mM,
            "vmax_scale": condition.vmax_scale,
            "assumption": condition.assumption,
            "metrics": dict(comparison.metrics),
            "relative_rmse_percent_of_initial": (
                100.0 * float(comparison.metrics["rmse"]) / condition.initial_cellobiose_mM
            ),
            "observed_vs_predicted": [
                {
                    "time_min": float(p.time),
                    "observed_mM": float(p.observed),
                    "predicted_mM": float(p.predicted),
                    "residual_mM": float(p.observed) - float(p.predicted),
                }
                for p in points
            ],
            "validation_report": result.validation_report(),
        }

    (output_dir / "holdout_prediction_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/alvarez_gonzalez_2022_holdout_prediction")
    arguments = parser.parse_args()
    summary = run(arguments.output_dir)

    train_rmse = summary["training"]["metrics"]["rmse"]
    print(f"training condition (reference)  RMSE = {train_rmse:8.4f} mM   n = {summary['training']['metrics']['n_points']}")
    print()
    print("held-out predictions, no parameter fitted against any held-out series:")
    for key, entry in summary["held_out"].items():
        rmse = entry["metrics"]["rmse"]
        rel = entry["relative_rmse_percent_of_initial"]
        worst = max(abs(p["residual_mM"]) for p in entry["observed_vs_predicted"])
        print(
            f"  {key:14s} n={int(entry['metrics']['n_points']):2d}  RMSE = {rmse:8.4f} mM"
            f"  ({rel:5.2f}% of initial)   max|residual| = {worst:7.4f} mM"
        )
    print()
    print(f"wrote {arguments.output_dir / 'holdout_prediction_summary.json'}")


if __name__ == "__main__":
    main()
