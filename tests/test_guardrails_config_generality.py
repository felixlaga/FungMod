from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from fungal_model import run_configured_model
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.workflows import ConfiguredModelExecutionError


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_all_foundation_configs_run_through_generic_workflow(tmp_path) -> None:
    cases = (
        (
            "toy_homogeneous_ab.yml",
            {},
            {"dissolved_substrate_amount", "released_product_amount"},
        ),
        (
            "toy_surface_dummy_non_pet.yml",
            {},
            {"solid_substrate_amount", "released_product_amount", "free_catalyst_concentration"},
        ),
        (
            "toy_surface_pet_plugin.yml",
            {"substrate_registry": pet_substrate_loader_registry()},
            {"solid_polymer_amount", "released_product_amount", "free_catalyst_concentration"},
        ),
    )

    for filename, options, expected_states in cases:
        output_dir = tmp_path / Path(filename).stem
        result = run_configured_model(MODEL_CONFIGS / filename, output_dir=output_dir, **options)

        assert result.label == "toy"
        assert result.assembly_report is not None
        assert result.assembly_report.success
        assert expected_states == set(result.states)
        assert result.process_rates

        manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))
        metadata = json.loads((output_dir / "configured_metadata.json").read_text(encoding="utf-8"))
        assert manifest["mode"] == "toy"
        assert manifest["maturity"] == "framework_benchmark"
        assert metadata["validation"]["passed"] is True
        assert "input_model_config.json" in manifest["files"]
        assert "entity_snapshots/index.json" in manifest["files"]


def test_surface_state_names_are_config_driven_not_hidden_domain_defaults(tmp_path) -> None:
    for filename, options in (
        ("toy_surface_dummy_non_pet.yml", {}),
        ("toy_surface_pet_plugin.yml", {"substrate_registry": pet_substrate_loader_registry()}),
    ):
        config = yaml.safe_load((MODEL_CONFIGS / filename).read_text(encoding="utf-8"))
        configured_states = set(config["initial_state"]["states"])

        assert "PET" not in configured_states
        assert "hydrolysate" not in configured_states
        assert "E" not in configured_states

        result = run_configured_model(MODEL_CONFIGS / filename, output_dir=tmp_path / Path(filename).stem, **options)

        assert set(result.states) == configured_states


def test_plugin_config_requires_explicit_plugin_registry(tmp_path) -> None:
    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(MODEL_CONFIGS / "toy_surface_pet_plugin.yml", output_dir=tmp_path / "plugin_without_registry")

    report = exc_info.value.report
    assert report.stage == "configured_input_loading"
    assert report.details["error_type"] == "RegistryLookupError"
    assert "Unsupported substrate" in report.message
