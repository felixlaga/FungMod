from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from fungal_model import load_model_config
from fungal_model.data import load_experiment_dataset


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_CONFIG = (
    ROOT
    / "data"
    / "calibration"
    / "synthetic"
    / "first_order_ab"
    / "calibration_config.yml"
)


def test_synthetic_calibration_config_is_inspectable() -> None:
    config = _calibration_config()

    assert config["kind"] == "calibration_config"
    assert config["maturity"] == "synthetic"
    assert "not empirical evidence" in str(config["notes"])
    assert config["parameter_symbols"] == ["k_ab"]

    model_config = load_model_config(ROOT / str(config["model_config"]))
    dataset = load_experiment_dataset(ROOT / str(config["dataset"]))

    assert model_config.maturity == "synthetic"
    assert model_config.mode == "toy"
    assert dataset.maturity == "synthetic"


def test_synthetic_calibration_config_declares_mapping_and_split() -> None:
    config = _calibration_config()
    mappings = cast(list[dict[str, Any]], config["observable_mapping"])
    split = cast(dict[str, Any], config["split"])

    assert mappings == [
        {
            "dataset_measurement_id": "product_mass",
            "model_observable": "released_product_amount",
            "observable_type": "state",
            "transform": "identity",
        }
    ]
    assert split["method"] == "by_time"
    assert split["train_fraction"] == 0.7
    assert split["validation_fraction"] == 0.3


def _calibration_config() -> dict[str, Any]:
    data = yaml.safe_load(CALIBRATION_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
