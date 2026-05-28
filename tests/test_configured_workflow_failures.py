from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import run_configured_model
from fungal_model.workflows import ConfiguredModelExecutionError


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_missing_config_file_fails_structurally(tmp_path: Path) -> None:
    config_path = tmp_path / "does_not_exist.yml"
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="model_config_loading",
        output_dir=output_dir,
        missing_capability="model_config",
        error_type="FileNotFoundError",
        message_contains="does_not_exist.yml",
    )


def test_invalid_top_level_config_kind_fails_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["kind"] = "not_model_config"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="model_config_loading",
        output_dir=output_dir,
        missing_capability="model_config",
        error_type="ModelConfigError",
        message_contains="kind",
    )


def test_missing_processes_fail_before_loading_outputs(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["processes"] = []
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="configured_model_execution",
        output_dir=output_dir,
        missing_capability="configured_processes",
        message_contains="Configured model is missing sections",
    )


def test_missing_initial_state_fails_before_loading_outputs(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["initial_state"] = {"states": {}}
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="configured_model_execution",
        output_dir=output_dir,
        missing_capability="configured_initial_state",
        message_contains="Configured model is missing sections",
    )


def test_unknown_substrate_loader_fails_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["entities"]["substrates"][0]["data"]["substrate_type"] = "unknown_substrate"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="configured_input_loading",
        output_dir=output_dir,
        error_type="RegistryLookupError",
        message_contains="Unsupported substrate",
    )


def test_plugin_config_without_explicit_registry_fails_structurally(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(MODEL_CONFIGS / "toy_surface_pet_plugin.yml", output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="configured_input_loading",
        output_dir=output_dir,
        error_type="RegistryLookupError",
        message_contains="Unsupported substrate",
    )


def test_unknown_product_map_loader_fails_structurally(tmp_path: Path) -> None:
    config = _dummy_surface_config()
    config["entities"]["product_maps"] = [
        {
            "id": "unknown_release_map",
            "loader": "unknown_map",
            "data": {
                "kind": "product_map",
                "name": "unknown release map",
                "product_map_type": "unknown_map",
                "substrate_state": "solid_substrate_amount",
                "product_state": "released_product_amount",
            },
        }
    ]
    config["processes"][0]["product_map"] = "unknown_release_map"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="configured_input_loading",
        output_dir=output_dir,
        error_type="RegistryLookupError",
        message_contains="Unsupported product map",
    )


def test_unknown_validator_type_fails_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["validators"][0]["validator_type"] = "unknown_validator"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="configured_input_loading",
        output_dir=output_dir,
        error_type="RegistryLookupError",
        message_contains="Unsupported validator",
    )


def test_unknown_process_type_fails_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["processes"][0]["process_type"] = "unknown_process"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="process_factory_build",
        output_dir=output_dir,
        missing_capability="process_factory",
        error_type="InvalidMechanismError",
        message_contains="No process factory registered",
    )


def test_missing_product_map_fails_structurally(tmp_path: Path) -> None:
    config = _dummy_surface_config()
    config["processes"][0]["product_map"] = "missing_release_map"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="process_factory_build",
        output_dir=output_dir,
        missing_capability="process_factory_requirements",
        message_contains="cannot be built",
    )
    decision = error.value.report.details["decisions"][0]
    assert "product_maps.missing_release_map" in decision["missing_fields"]


def test_missing_state_unit_fails_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["processes"][0]["states"]["source"] = "missing_source_state"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="process_factory_build",
        output_dir=output_dir,
        missing_capability="process_factory_requirements",
        message_contains="cannot be built",
    )
    decision = error.value.report.details["decisions"][0]
    assert "state_units.missing_source_state" in decision["missing_fields"]


def test_missing_required_parameter_fails_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["processes"][0]["parameters"]["rate_constant"] = "k_missing"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="model_assembly",
        output_dir=output_dir,
        missing_capability="required_parameters",
        error_type="MissingParameterError",
        message_contains="missing parameter",
    )
    report = error.value.report.details["assembly_report"]
    assert report["missing_parameters"][0]["symbol"] == "k_missing"


def test_conflicting_duplicate_parameters_fail_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    duplicate_set = deepcopy(config["parameters"][0])
    duplicate_set["id"] = "conflicting_parameters"
    duplicate_set["parameters"][0]["value"] = 0.2
    config["parameters"].append(duplicate_set)
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="configured_input_loading",
        output_dir=output_dir,
        error_type="ParameterMergeError",
        message_contains="Conflicting parameter definitions",
    )


def test_incompatible_initial_state_units_fail_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["initial_state"]["states"]["released_product_amount"]["units"] = "second"
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="model_execution",
        output_dir=output_dir,
        missing_capability="successful_model_execution",
        error_type="UnitError",
        message_contains="released_product_amount",
    )


def test_unsupported_geometry_fails_structurally(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["entities"]["geometry"] = {
        "id": "geometry",
        "path": "data/geometries/pet_film_1d.yml",
        "loader": "film_1d",
    }
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="model_execution",
        output_dir=output_dir,
        missing_capability="successful_model_execution",
        error_type="ValueError",
        message_contains="supports only well_mixed geometry",
    )


def test_failed_validation_in_non_strict_mode_is_recorded(tmp_path: Path) -> None:
    config = _homogeneous_config()
    config["validators"][1]["conserved_weights"]["released_product_amount"] = 2.0
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    result = run_configured_model(config_path, output_dir=output_dir)

    validation_report = result.validation_report()
    metadata = json.loads((output_dir / "configured_metadata.json").read_text(encoding="utf-8"))
    assert any(not validation["passed"] for validation in validation_report)
    assert metadata["validation"]["passed"] is False
    assert (output_dir / "output_manifest.json").exists()


def test_failed_validation_in_strict_mode_raises_structurally(tmp_path: Path) -> None:
    config = _strict_reference_config()
    config_path = _write_config(tmp_path, config)
    output_dir = tmp_path / "output"

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=output_dir)

    _assert_failure(
        error.value,
        stage="result_validation",
        output_dir=output_dir,
        missing_capability="passing_validators",
        message_contains="Strict mode requires all configured validators to pass",
    )
    failed_validation = error.value.report.details["failed_validations"][0]
    assert failed_validation["name"] == "mass_balance"
    assert failed_validation["passed"] is False


def _homogeneous_config() -> dict[str, Any]:
    return _config("toy_homogeneous_ab.yml")


def _dummy_surface_config() -> dict[str, Any]:
    return _config("toy_surface_dummy_non_pet.yml")


def _config(filename: str) -> dict[str, Any]:
    return yaml.safe_load((MODEL_CONFIGS / filename).read_text(encoding="utf-8"))


def _write_config(tmp_path: Path, config: dict[str, Any], *, name: str = "model.yml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _assert_failure(
    error: ConfiguredModelExecutionError,
    *,
    stage: str,
    output_dir: Path,
    message_contains: str,
    missing_capability: str | None = None,
    error_type: str | None = None,
) -> None:
    report = error.report
    assert report.stage == stage
    if missing_capability is not None:
        assert missing_capability in report.missing_capabilities
    if error_type is not None:
        assert report.details["error_type"] == error_type
    assert message_contains in str(error)
    assert not (output_dir / "output_manifest.json").exists()


def _strict_reference_config() -> dict[str, Any]:
    return {
        "kind": "model_config",
        "name": "strict validation failure reference",
        "mode": "strict",
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
                        "uncertainty": 0.0,
                        "source": "Controlled reference dataset for failure-path tests.",
                        "confidence_level": "high",
                        "notes": "Reference value for configured workflow failure-path tests.",
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
        "validators": [
            {
                "id": "strict_mass_balance",
                "validator_type": "mass_balance",
                "conserved_weights": {
                    "source_amount": 1.0,
                    "product_amount": 2.0,
                },
            }
        ],
        "outputs": {},
    }
