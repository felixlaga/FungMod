"""Run the first provenance-matched literature time-course comparison."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from fungal_model import run_configured_model
from fungal_model.data import (
    ModelDatasetComparison,
    ObservableMapping,
    evaluate_model_against_dataset,
    load_experiment_dataset,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data/model_configs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison.yml"
DEFAULT_DATASET = (
    ROOT
    / "data/experiments/literature/alvarez_gonzalez_2022_free_beta_glucosidase"
    / "alvarez_gonzalez_2022_free_beta_glucosidase.yml"
)
DEFAULT_OUTPUT = ROOT / "outputs/alvarez_gonzalez_2022_free_beta_glucosidase_comparison"


def run_comparison(
    *,
    output_dir: str | Path,
    config_path: str | Path = DEFAULT_CONFIG,
    dataset_path: str | Path = DEFAULT_DATASET,
) -> ModelDatasetComparison:
    """Run the fixed-parameter model and persist an explicit comparison bundle."""

    destination = Path(output_dir)
    result = run_configured_model(
        config_path,
        output_dir=destination / "model_bundle",
    )
    dataset = load_experiment_dataset(dataset_path)
    comparison = evaluate_model_against_dataset(
        result=result,
        dataset=dataset,
        observable_mapping=(
            ObservableMapping(
                dataset_measurement_id="cellobiose_concentration",
                model_observable="cellobiose_concentration",
                observable_type="state",
            ),
        ),
    )
    comparison.save(destination / "comparison_bundle")
    return comparison


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Alvarez-Gonzalez 2022 same-source, no-calibration cellobiose "
            "time-course comparison."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the comparison command and print its machine-readable metrics."""

    args = _parser().parse_args(argv)
    comparison = run_comparison(
        output_dir=args.output_dir,
        config_path=args.config,
        dataset_path=args.dataset,
    )
    print(json.dumps(comparison.metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
