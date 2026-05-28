from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import run_configured_model
from fungal_model.processes import AssembledModel
from fungal_model.results import SimulationResult
from fungal_model.validation.maturity import InvalidDataMaturityError


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_toy_config_runs_in_toy_mode(tmp_path: Path) -> None:
    result = run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=tmp_path / "toy_homogeneous",
    )

    assert isinstance(result, SimulationResult)
    assert result.label == "toy"
    assert result.assembly_report is not None
    assert result.assembly_report.success


def test_toy_config_fails_in_scientific_mode(tmp_path: Path) -> None:
    config = _config("toy_homogeneous_ab.yml")
    config["mode"] = "scientific"

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="model_config", field="maturity")


def test_testing_confidence_fails_in_scientific_mode(tmp_path: Path) -> None:
    config = _scientific_homogeneous_config()
    parameter = _first_parameter(config)
    parameter["confidence_level"] = "testing"

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="parameter", object_id="k_ab", field="confidence_level")


def test_framework_benchmark_maturity_fails_in_scientific_mode(tmp_path: Path) -> None:
    config = _scientific_homogeneous_config()
    config["maturity"] = "framework_benchmark"

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="model_config", field="maturity")


def test_unknown_required_parameter_value_fails_before_solving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _scientific_homogeneous_config()
    _first_parameter(config)["value"] = None

    def fail_if_called(*args: Any, **kwargs: Any) -> SimulationResult:
        raise AssertionError("maturity policy should fail before AssembledModel.run")

    monkeypatch.setattr(AssembledModel, "run", fail_if_called)
    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="parameter", object_id="k_ab", field="value")


def test_missing_parameter_source_fails_in_scientific_mode(tmp_path: Path) -> None:
    config = _scientific_homogeneous_config()
    _first_parameter(config)["source"] = None

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="parameter", object_id="k_ab", field="source")


def test_missing_measurement_method_fails_in_scientific_mode(tmp_path: Path) -> None:
    config = _scientific_homogeneous_config()
    _first_parameter(config)["measurement_method"] = None

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="parameter", object_id="k_ab", field="measurement_method")


def test_missing_validity_range_fails_in_scientific_mode(tmp_path: Path) -> None:
    config = _scientific_homogeneous_config()
    _first_parameter(config)["validity_range"] = None

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="parameter", object_id="k_ab", field="validity_range")


def test_toy_product_map_fails_in_scientific_mode(tmp_path: Path) -> None:
    config = _config("toy_surface_dummy_non_pet.yml")
    config["mode"] = "scientific"
    config["maturity"] = "scientific"

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, config))

    assert _has_issue(error.value, object_type="product_map", object_id="dummy_release_map", field="maturity")


def test_strict_mode_rejects_missing_required_parameter_uncertainty_beyond_scientific(
    tmp_path: Path,
) -> None:
    scientific_config = _clean_reference_config(mode="scientific")
    strict_config = _clean_reference_config(mode="strict")

    scientific_result = run_configured_model(
        _write_config(tmp_path, scientific_config, name="scientific_reference.yml"),
        output_dir=tmp_path / "scientific_output",
    )

    with pytest.raises(InvalidDataMaturityError) as error:
        run_configured_model(_write_config(tmp_path, strict_config, name="strict_reference.yml"))

    assert scientific_result.label == "scientific"
    assert _has_issue(error.value, object_type="parameter", object_id="k_reference", field="uncertainty")


def _config(name: str) -> dict[str, Any]:
    return yaml.safe_load((MODEL_CONFIGS / name).read_text(encoding="utf-8"))


def _scientific_homogeneous_config() -> dict[str, Any]:
    config = _config("toy_homogeneous_ab.yml")
    config["mode"] = "scientific"
    config["maturity"] = "scientific"
    config["entities"] = {}
    config["processes"][0]["assumptions"] = ["reference software process"]
    parameter = _first_parameter(config)
    parameter["source"] = "Controlled reference dataset for maturity policy tests."
    parameter["confidence_level"] = "high"
    parameter["notes"] = "Reference value for maturity policy tests."
    parameter["measurement_method"] = "defined reference value"
    parameter["validity_range"] = "controlled reference domain"
    return config


def _clean_reference_config(*, mode: str) -> dict[str, Any]:
    return {
        "kind": "model_config",
        "name": "clean reference maturity policy config",
        "mode": mode,
        "maturity": "scientific",
        "entities": {},
        "parameters": [
            {
                "id": "reference_parameters",
                "parameters": [
                    {
                        "name": "reference first-order conversion constant",
                        "symbol": "k_reference",
                        "value": 0.1,
                        "units": "1 / second",
                        "uncertainty": None,
                        "source": "Controlled reference dataset for maturity policy tests.",
                        "confidence_level": "high",
                        "notes": "Reference value for maturity policy tests.",
                        "measurement_method": "defined reference value",
                        "validity_range": "controlled reference domain",
                    }
                ],
            }
        ],
        "processes": [
            {
                "id": "reference_conversion",
                "process_type": "first_order",
                "states": {
                    "source": "source_amount",
                    "product": "product_amount",
                },
                "parameters": {
                    "rate_constant": "k_reference",
                },
                "assumptions": ["reference software process"],
            }
        ],
        "initial_state": {
            "states": {
                "source_amount": {
                    "value": 1.0,
                    "units": "kilogram",
                },
                "product_amount": {
                    "value": 0.0,
                    "units": "kilogram",
                },
            }
        },
        "time": {
            "start": {
                "value": 0.0,
                "units": "second",
            },
            "stop": {
                "value": 1.0,
                "units": "second",
            },
            "points": 3,
        },
        "validators": [],
        "outputs": {},
    }


def _first_parameter(config: dict[str, Any]) -> dict[str, Any]:
    return config["parameters"][0]["parameters"][0]


def _write_config(tmp_path: Path, config: dict[str, Any], *, name: str = "model.yml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(deepcopy(config), sort_keys=False), encoding="utf-8")
    return path


def _has_issue(
    error: InvalidDataMaturityError,
    *,
    object_type: str,
    field: str,
    object_id: str | None = None,
) -> bool:
    return any(
        issue.object_type == object_type
        and issue.field == field
        and (object_id is None or issue.object_id == object_id)
        for issue in error.issues
    )
