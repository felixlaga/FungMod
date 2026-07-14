from __future__ import annotations

import csv
import json
import shutil
import socket
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model import ConfiguredModelExecutionError, VirtualExperiment
from fungal_model.registry import load_registry
from fungal_model.registry.records import (
    PARAMETER_ALLOWED_USE_SCIENTIFIC,
    PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY,
)
from fungal_model.screening import (
    EnzymeChainAssemblyError,
    RegistryCaseBuildError,
    build_extracellular_enzyme_chain_config,
    build_model_config_from_registry_case,
)
from fungal_model.screening.ensemble import simulate_screen
from fungal_model.workflows import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

REACTION_FUNGUS_ID = "sabiork_beta_glucosidase_source"
REACTION_SUBSTRATE_ID = "cellobiose"
REACTION_ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"
ENZYME_CONCENTRATION_SYMBOL = "enzyme_concentration_beta_glucosidase"

BIO_FUNGUS_ID = "generic_cellulase_source"
BIO_SUBSTRATE_ID = "cellulose_film_generic"
BIO_ENVIRONMENT_ID = "bio001_cellulose_surface_pilot_environment"


def test_reaction_618_assembles_and_simulates_from_template(tmp_path: Path) -> None:
    registry = _registry_with_exact_enzyme_concentration(tmp_path)

    config = build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "outputs"),
    )
    data = config.to_dict()

    assert data["case_template"]["case_template_id"] == "sabiork_reaction_618_homogeneous_mm_template"
    assert data["processes"][0]["states"] == {
        "substrate": "cellobiose_concentration",
        "product": "beta_D_glucose_concentration",
        "enzyme": "beta_glucosidase_concentration",
    }
    assert data["processes"][0]["product_map"] == "sabiork_reaction_618_product_map"
    assert data["entities"]["product_maps"][0]["data"]["products"] == {"beta_D_glucose_concentration": 2.0}
    assert data["initial_state"]["states"]["cellobiose_concentration"]["value"] == pytest.approx(3.06)
    assert data["time"] == {
        "start": {"value": 0.0, "units": "second"},
        "stop": {"value": 1000.0, "units": "second"},
        "points": 101,
    }

    config_path = tmp_path / "reaction_618_config.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=tmp_path / "bundle")

    substrate = result.state("cellobiose_concentration").to("mM").magnitude
    product = result.state("beta_D_glucose_concentration").to("mM").magnitude
    assert substrate[-1] < substrate[0]
    assert product[-1] > product[0]


def test_bio001_assembles_and_simulates_from_template(tmp_path: Path) -> None:
    output_dir = tmp_path / "bio001"
    study = VirtualExperiment.from_registry(
        fungi=BIO_FUNGUS_ID,
        substrates=BIO_SUBSTRATE_ID,
        environments=BIO_ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    result = study.simulate(mode="exploratory", n_samples=2, seed=21, output_dir=output_dir, quicklook=False)
    sample = result.screen_result.case_results[0].samples[0]
    config_data = _yaml_mapping(Path(sample.config_path))

    assert config_data["case_template"]["case_template_id"] == "bio001_cellulose_surface_catalysis_template"
    assert config_data["processes"][0]["states"] == {
        "substrate": "solid_substrate_remaining",
        "catalyst": "free_enzyme_concentration",
        "product": "soluble_product_amount",
        "bond_type": "beta_1_4_glycosidic",
        "accessible_site_pool": "cellulose accessible beta-1,4-glycosidic surface",
    }
    assert config_data["processes"][0]["product_map"] == "bio001_cellulose_surface_release_map"
    assert config_data["time"] == {
        "start": {"value": 0.0, "units": "second"},
        "stop": {"value": 4000.0, "units": "second"},
        "points": 81,
    }
    assert {"solid_substrate_remaining", "soluble_product_amount", "free_enzyme_concentration"} <= set(sample.final_states)


def test_registry_chain_template_emits_configured_product_inhibition_modifier(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_product_inhibition(tmp_path)
    output_dir = tmp_path / "bio003_registry_product_inhibition"

    study = VirtualExperiment.from_registry(
        fungi=BIO_FUNGUS_ID,
        substrates=BIO_SUBSTRATE_ID,
        environments=REACTION_ENVIRONMENT_ID,
        registry=registry_dir / "registry_index.yml",
    )
    result = study.simulate(mode="exploratory", n_samples=1, seed=31, output_dir=output_dir, quicklook=False)
    sample = result.screen_result.case_results[0].samples[0]
    config_data = _yaml_mapping(Path(sample.config_path))
    sample_output = Path(sample.output_directory)
    metadata = json.loads((sample_output / "configured_metadata.json").read_text(encoding="utf-8"))
    assumptions = json.loads((sample_output / "assumptions.json").read_text(encoding="utf-8"))
    mechanism_rows = _csv_rows(output_dir / "mechanism_summary.csv")

    inhibited_process = config_data["processes"][1]
    assert inhibited_process["id"] == "bio002_cellobiose_to_glucose_mm"
    assert inhibited_process["modifiers"] == [
        {
            "type": "product_inhibition",
            "product_state": "beta_D_glucose_concentration",
            "inhibition_constant": "K_i_bio003_product_fixture",
        }
    ]
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "bio002_cellobiose_to_glucose_mm",
            "modifier_index": 0,
            "type": "product_inhibition",
            "product_state": "beta_D_glucose_concentration",
            "inhibition_constant": "K_i_bio003_product_fixture",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Single-product reversible inhibition only; configured only when product_state "
                "and positive unit-compatible K_i are explicit."
            ),
        }
    ]
    assert any(item["name"] == "reversible product inhibition modifier" for item in assumptions)
    assert any(
        row["mechanism_kind"] == "rate_modifier"
        and row["mechanism_id"] == "product_inhibition"
        and row["parameters"] == "inhibition_constant:K_i_bio003_product_fixture"
        for row in mechanism_rows
    )


def test_registry_product_inhibition_requires_explicit_ki_record(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_product_inhibition(tmp_path, include_ki_record=False)
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="missing parameter record"):
        build_extracellular_enzyme_chain_config(registry=registry)


def test_registry_product_inhibition_rejects_non_positive_ki_without_fallback(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_product_inhibition(tmp_path, ki_value=0.0)
    registry = load_registry(registry_dir / "registry_index.yml")
    config = build_extracellular_enzyme_chain_config(
        registry=registry,
        output_directory=tmp_path / "bad_ki",
    )
    config_path = tmp_path / "bad_ki.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "bad_ki")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "Product inhibition constant must be positive" in report["message"]


def test_registry_chain_template_emits_temperature_ph_environment_modifiers(tmp_path: Path) -> None:
    base_registry = load_registry(REGISTRY_INDEX)
    modified_registry_dir = _registry_with_bio002_environment_modifiers(
        tmp_path / "modified",
        modifier_set="temperature_ph",
    )
    modified_registry = load_registry(modified_registry_dir / "registry_index.yml")

    base_config = build_extracellular_enzyme_chain_config(
        registry=base_registry,
        environment_id=REACTION_ENVIRONMENT_ID,
        output_directory=tmp_path / "base_chain_outputs",
    )
    modified_config = build_extracellular_enzyme_chain_config(
        registry=modified_registry,
        environment_id=REACTION_ENVIRONMENT_ID,
        output_directory=tmp_path / "temperature_ph_outputs",
    )
    modified_data = modified_config.to_dict()

    assert modified_data["entities"]["environment"]["id"] == REACTION_ENVIRONMENT_ID
    assert set(modified_data["entities"]["environment"]["data"]["conditions"]) == {"temperature", "ph"}
    assert modified_data["processes"][1]["modifiers"] == [
        {
            "type": "temperature_arrhenius_reference",
            "activation_energy_symbol": "E_a_bio002_chain_env_fixture",
            "reference_temperature_symbol": "T_ref_bio002_chain_env_fixture",
        },
        {
            "type": "ph_gaussian",
            "optimum_symbol": "pH_opt_bio002_chain_env_fixture",
            "width_symbol": "pH_width_bio002_chain_env_fixture",
        },
    ]

    base_path = tmp_path / "bio002_base_chain.yml"
    modified_path = tmp_path / "bio002_temperature_ph_chain.yml"
    base_path.write_text(yaml.safe_dump(base_config.to_dict(), sort_keys=False), encoding="utf-8")
    modified_path.write_text(yaml.safe_dump(modified_data, sort_keys=False), encoding="utf-8")
    base_result = run_configured_model(base_path, output_dir=tmp_path / "base_chain_outputs")
    modified_result = run_configured_model(modified_path, output_dir=tmp_path / "temperature_ph_outputs")
    metadata = json.loads((tmp_path / "temperature_ph_outputs" / "configured_metadata.json").read_text(encoding="utf-8"))
    environment_snapshot = json.loads(
        (tmp_path / "temperature_ph_outputs" / "entity_snapshots" / "environment.json").read_text(encoding="utf-8")
    )

    assert max(modified_result.process_rates["bio002_cellobiose_to_glucose_mm"].magnitude) != pytest.approx(
        max(base_result.process_rates["bio002_cellobiose_to_glucose_mm"].magnitude)
    )
    assert environment_snapshot["temperature"]["value"] == pytest.approx(303.15)
    assert environment_snapshot["ph"]["value"] == pytest.approx(5.0)
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "bio002_cellobiose_to_glucose_mm",
            "modifier_index": 0,
            "type": "temperature_arrhenius_reference",
            "environment_value": "temperature",
            "activation_energy_symbol": "E_a_bio002_chain_env_fixture",
            "reference_temperature_symbol": "T_ref_bio002_chain_env_fixture",
            "minimum_temperature_symbol": "",
            "maximum_temperature_symbol": "",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Arrhenius reference-temperature scaling only; configured only when environment "
                "temperature and explicit unit-compatible parameters are present."
            ),
        },
        {
            "process_id": "bio002_cellobiose_to_glucose_mm",
            "modifier_index": 1,
            "type": "ph_gaussian",
            "environment_value": "ph",
            "optimum_symbol": "pH_opt_bio002_chain_env_fixture",
            "width_symbol": "pH_width_bio002_chain_env_fixture",
            "minimum_ph_symbol": "",
            "maximum_ph_symbol": "",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Gaussian empirical pH activity scaling only; configured only when environment "
                "pH and explicit unit-compatible parameters are present."
            ),
        },
    ]


def test_registry_chain_template_emits_oxygen_water_activity_environment_modifiers(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_environment_modifiers(tmp_path, modifier_set="oxygen_water")
    registry = load_registry(registry_dir / "registry_index.yml")

    config = build_extracellular_enzyme_chain_config(
        registry=registry,
        environment_id=REACTION_ENVIRONMENT_ID,
        output_directory=tmp_path / "oxygen_water_outputs",
    )
    data = config.to_dict()

    assert set(data["entities"]["environment"]["data"]["conditions"]) == {"oxygen_concentration", "water_activity"}
    assert data["processes"][1]["modifiers"] == [
        {
            "type": "oxygen_monod",
            "half_saturation_symbol": "K_O2_bio002_chain_env_fixture",
            "oxygen_units": "mole / liter",
        },
        {
            "type": "water_activity_threshold",
            "minimum_water_activity_symbol": "a_w_min_bio002_chain_env_fixture",
        },
    ]

    config_path = tmp_path / "bio002_oxygen_water_chain.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=tmp_path / "oxygen_water_outputs")
    metadata = json.loads((tmp_path / "oxygen_water_outputs" / "configured_metadata.json").read_text(encoding="utf-8"))
    environment_snapshot = json.loads(
        (tmp_path / "oxygen_water_outputs" / "entity_snapshots" / "environment.json").read_text(encoding="utf-8")
    )

    assert result.solver_metadata["success"] is True
    assert environment_snapshot["oxygen_concentration"]["value"] == pytest.approx(0.00025)
    assert environment_snapshot["water_activity"]["value"] == pytest.approx(0.96)
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "bio002_cellobiose_to_glucose_mm",
            "modifier_index": 0,
            "type": "oxygen_monod",
            "environment_value": "oxygen_concentration",
            "half_saturation_symbol": "K_O2_bio002_chain_env_fixture",
            "oxygen_units": "mole / liter",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Monod oxygen scaling only; configured only when environment oxygen concentration "
                "and explicit positive unit-compatible half-saturation are present. No oxygen consumption, "
                "gas transfer, redox balance, or anaerobic metabolism."
            ),
        },
        {
            "process_id": "bio002_cellobiose_to_glucose_mm",
            "modifier_index": 1,
            "type": "water_activity_threshold",
            "environment_value": "water_activity",
            "minimum_water_activity_symbol": "a_w_min_bio002_chain_env_fixture",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Binary water-activity threshold scaling only; configured only when environment water activity "
                "and an explicit unit-compatible threshold parameter are present. No smooth response curve, "
                "hysteresis, substrate water binding, or spatial moisture model."
            ),
        },
    ]


def test_registry_chain_environment_modifier_requires_environment_condition(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_environment_modifiers(
        tmp_path,
        modifier_set="oxygen_water",
        include_environment_oxygen=False,
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="requires environment condition 'oxygen_concentration'"):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=REACTION_ENVIRONMENT_ID,
            output_directory=tmp_path / "missing_environment_oxygen",
        )


def test_registry_chain_environment_modifier_requires_exact_environment_value(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_environment_modifiers(
        tmp_path,
        modifier_set="temperature_ph",
        ph_value_kind="range",
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="requires exact environment condition 'ph'"):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=REACTION_ENVIRONMENT_ID,
            output_directory=tmp_path / "non_exact_ph",
        )


def test_registry_chain_environment_modifier_requires_role_field(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_environment_modifiers(
        tmp_path,
        modifier_set="temperature_ph",
        include_ph_width_role=False,
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="not owned by exactly one component process"):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=REACTION_ENVIRONMENT_ID,
            output_directory=tmp_path / "missing_width_role",
        )


def test_registry_chain_environment_modifier_requires_resolved_role(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_environment_modifiers(
        tmp_path,
        modifier_set="temperature_ph",
        ph_width_role="missing_ph_width_role",
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="not owned by exactly one component process"):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=REACTION_ENVIRONMENT_ID,
            output_directory=tmp_path / "unresolved_width_role",
        )


def test_registry_chain_environment_modifier_requires_oxygen_units_field(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_environment_modifiers(
        tmp_path,
        modifier_set="oxygen_water",
        include_oxygen_units=False,
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="requires oxygen_units"):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=REACTION_ENVIRONMENT_ID,
            output_directory=tmp_path / "missing_oxygen_units",
        )


def test_registry_chain_environment_modifier_requires_explicit_environment_id(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_environment_modifiers(tmp_path, modifier_set="temperature_ph")
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="no explicit environment_id"):
        build_extracellular_enzyme_chain_config(registry=registry, output_directory=tmp_path / "missing_environment_id")


def test_one_process_registry_template_emits_configured_product_inhibition_modifier(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_process_modifier(tmp_path)
    registry = load_registry(registry_dir / "registry_index.yml")

    config = build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "one_process_outputs"),
    )
    config_path = tmp_path / "one_process_product_inhibition.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=tmp_path / "one_process_outputs")
    metadata = json.loads((tmp_path / "one_process_outputs" / "configured_metadata.json").read_text(encoding="utf-8"))

    assert result.solver_metadata["success"] is True
    assert config.to_dict()["processes"][0]["modifiers"] == [
        {
            "type": "product_inhibition",
            "product_state": "beta_D_glucose_concentration",
            "inhibition_constant": "K_i_reaction618_product_fixture",
        }
    ]
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "sabiork_reaction_618_homogeneous_mm",
            "modifier_index": 0,
            "type": "product_inhibition",
            "product_state": "beta_D_glucose_concentration",
            "inhibition_constant": "K_i_reaction618_product_fixture",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Single-product reversible inhibition only; configured only when product_state "
                "and positive unit-compatible K_i are explicit."
            ),
        }
    ]


def test_one_process_registry_template_emits_temperature_ph_modifiers(tmp_path: Path) -> None:
    base_registry = _registry_with_exact_enzyme_concentration(tmp_path / "base")
    modified_registry_dir = _registry_with_reaction618_environment_modifiers(tmp_path / "modified", modifier_set="temperature_ph")
    modified_registry = load_registry(modified_registry_dir / "registry_index.yml")

    base_config = build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=base_registry,
        mode="scientific",
        output_directory=str(tmp_path / "base_outputs"),
    )
    modified_config = build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=modified_registry,
        mode="scientific",
        output_directory=str(tmp_path / "temperature_ph_outputs"),
    )
    modified_data = modified_config.to_dict()

    assert modified_data["entities"]["environment"]["id"] == REACTION_ENVIRONMENT_ID
    assert set(modified_data["entities"]["environment"]["data"]["conditions"]) == {"temperature", "ph"}
    assert modified_data["processes"][0]["modifiers"] == [
        {
            "type": "temperature_arrhenius_reference",
            "activation_energy_symbol": "E_a_reaction618_env_fixture",
            "reference_temperature_symbol": "T_ref_reaction618_env_fixture",
        },
        {
            "type": "ph_gaussian",
            "optimum_symbol": "pH_opt_reaction618_env_fixture",
            "width_symbol": "pH_width_reaction618_env_fixture",
        },
    ]

    base_path = tmp_path / "base_temperature_ph.yml"
    modified_path = tmp_path / "reaction618_temperature_ph.yml"
    base_path.write_text(yaml.safe_dump(base_config.to_dict(), sort_keys=False), encoding="utf-8")
    modified_path.write_text(yaml.safe_dump(modified_data, sort_keys=False), encoding="utf-8")
    base_result = run_configured_model(base_path, output_dir=tmp_path / "base_outputs")
    modified_result = run_configured_model(modified_path, output_dir=tmp_path / "temperature_ph_outputs")
    metadata = json.loads((tmp_path / "temperature_ph_outputs" / "configured_metadata.json").read_text(encoding="utf-8"))
    environment_snapshot = json.loads(
        (tmp_path / "temperature_ph_outputs" / "entity_snapshots" / "environment.json").read_text(encoding="utf-8")
    )

    assert modified_result.process_rates["sabiork_reaction_618_homogeneous_mm"].magnitude[0] != pytest.approx(
        base_result.process_rates["sabiork_reaction_618_homogeneous_mm"].magnitude[0]
    )
    assert environment_snapshot["temperature"]["value"] == pytest.approx(303.15)
    assert environment_snapshot["ph"]["value"] == pytest.approx(5.0)
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "sabiork_reaction_618_homogeneous_mm",
            "modifier_index": 0,
            "type": "temperature_arrhenius_reference",
            "environment_value": "temperature",
            "activation_energy_symbol": "E_a_reaction618_env_fixture",
            "reference_temperature_symbol": "T_ref_reaction618_env_fixture",
            "minimum_temperature_symbol": "",
            "maximum_temperature_symbol": "",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Arrhenius reference-temperature scaling only; configured only when environment "
                "temperature and explicit unit-compatible parameters are present."
            ),
        },
        {
            "process_id": "sabiork_reaction_618_homogeneous_mm",
            "modifier_index": 1,
            "type": "ph_gaussian",
            "environment_value": "ph",
            "optimum_symbol": "pH_opt_reaction618_env_fixture",
            "width_symbol": "pH_width_reaction618_env_fixture",
            "minimum_ph_symbol": "",
            "maximum_ph_symbol": "",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Gaussian empirical pH activity scaling only; configured only when environment "
                "pH and explicit unit-compatible parameters are present."
            ),
        },
    ]


def test_one_process_registry_template_emits_oxygen_water_activity_modifiers(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_environment_modifiers(tmp_path, modifier_set="oxygen_water")
    registry = load_registry(registry_dir / "registry_index.yml")

    config = build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "oxygen_water_outputs"),
    )
    data = config.to_dict()

    assert set(data["entities"]["environment"]["data"]["conditions"]) == {"oxygen_concentration", "water_activity"}
    assert data["processes"][0]["modifiers"] == [
        {
            "type": "oxygen_monod",
            "half_saturation_symbol": "K_O2_reaction618_env_fixture",
            "oxygen_units": "mole / liter",
        },
        {
            "type": "water_activity_threshold",
            "minimum_water_activity_symbol": "a_w_min_reaction618_env_fixture",
        },
    ]

    config_path = tmp_path / "reaction618_oxygen_water.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=tmp_path / "oxygen_water_outputs")
    metadata = json.loads((tmp_path / "oxygen_water_outputs" / "configured_metadata.json").read_text(encoding="utf-8"))

    assert result.solver_metadata["success"] is True
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "sabiork_reaction_618_homogeneous_mm",
            "modifier_index": 0,
            "type": "oxygen_monod",
            "environment_value": "oxygen_concentration",
            "half_saturation_symbol": "K_O2_reaction618_env_fixture",
            "oxygen_units": "mole / liter",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Monod oxygen scaling only; configured only when environment oxygen concentration "
                "and explicit positive unit-compatible half-saturation are present. No oxygen consumption, "
                "gas transfer, redox balance, or anaerobic metabolism."
            ),
        },
        {
            "process_id": "sabiork_reaction_618_homogeneous_mm",
            "modifier_index": 1,
            "type": "water_activity_threshold",
            "environment_value": "water_activity",
            "minimum_water_activity_symbol": "a_w_min_reaction618_env_fixture",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Binary water-activity threshold scaling only; configured only when environment water activity "
                "and an explicit unit-compatible threshold parameter are present. No smooth response curve, "
                "hysteresis, substrate water binding, or spatial moisture model."
            ),
        },
    ]


def test_one_process_registry_environment_modifier_requires_resolved_role(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_environment_modifiers(
        tmp_path,
        modifier_set="temperature_ph",
        ph_width_role="missing_ph_width_role",
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="width_role 'missing_ph_width_role'"):
        build_model_config_from_registry_case(
            fungus_id=REACTION_FUNGUS_ID,
            substrate_id=REACTION_SUBSTRATE_ID,
            environment_id=REACTION_ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
            output_directory=str(tmp_path / "missing_role"),
        )


def test_one_process_registry_environment_modifier_requires_environment_condition(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_environment_modifiers(
        tmp_path,
        modifier_set="oxygen_water",
        include_environment_oxygen=False,
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="requires environment condition 'oxygen_concentration'"):
        build_model_config_from_registry_case(
            fungus_id=REACTION_FUNGUS_ID,
            substrate_id=REACTION_SUBSTRATE_ID,
            environment_id=REACTION_ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
            output_directory=str(tmp_path / "missing_environment_oxygen"),
        )


def test_one_process_registry_environment_modifier_requires_exact_environment_value(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_environment_modifiers(
        tmp_path,
        modifier_set="temperature_ph",
        ph_value_kind="range",
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="requires exact environment condition 'ph'"):
        build_model_config_from_registry_case(
            fungus_id=REACTION_FUNGUS_ID,
            substrate_id=REACTION_SUBSTRATE_ID,
            environment_id=REACTION_ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
            output_directory=str(tmp_path / "non_exact_ph"),
        )


def test_one_process_registry_oxygen_modifier_requires_units_field(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_environment_modifiers(
        tmp_path,
        modifier_set="oxygen_water",
        include_oxygen_units=False,
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="requires oxygen_units"):
        build_model_config_from_registry_case(
            fungus_id=REACTION_FUNGUS_ID,
            substrate_id=REACTION_SUBSTRATE_ID,
            environment_id=REACTION_ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
            output_directory=str(tmp_path / "missing_oxygen_units"),
        )


def test_one_process_registry_environment_modifier_rejects_unsupported_type(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_environment_modifiers(tmp_path, modifier_set="unsupported")
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="unsupported modifier type 'temperature_magic'"):
        build_model_config_from_registry_case(
            fungus_id=REACTION_FUNGUS_ID,
            substrate_id=REACTION_SUBSTRATE_ID,
            environment_id=REACTION_ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
            output_directory=str(tmp_path / "unsupported_environment_modifier"),
        )


def test_one_process_registry_product_inhibition_requires_explicit_ki_record(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_process_modifier(tmp_path, include_ki_record=False)
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(RegistryCaseBuildError, match="product_inhibition_constant"):
        build_model_config_from_registry_case(
            fungus_id=REACTION_FUNGUS_ID,
            substrate_id=REACTION_SUBSTRATE_ID,
            environment_id=REACTION_ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
            output_directory=str(tmp_path / "missing_one_process_ki"),
        )


def test_one_process_registry_product_inhibition_rejects_non_positive_ki(tmp_path: Path) -> None:
    registry_dir = _registry_with_reaction618_process_modifier(tmp_path, ki_value=0.0)
    registry = load_registry(registry_dir / "registry_index.yml")
    config = build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "bad_one_process_ki"),
    )
    config_path = tmp_path / "bad_one_process_ki.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "bad_one_process_ki")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "Product inhibition constant must be positive" in report["message"]


def test_output_tables_preserve_template_biological_states_and_metrics(tmp_path: Path) -> None:
    output_dir = tmp_path / "reaction_618_tables"
    study = VirtualExperiment.from_registry(
        fungi=REACTION_FUNGUS_ID,
        substrates=REACTION_SUBSTRATE_ID,
        environments=REACTION_ENVIRONMENT_ID,
        registry=REGISTRY_INDEX,
    )

    study.simulate(mode="exploratory", n_samples=2, seed=5, output_dir=output_dir, quicklook=False)

    time_rows = _csv_rows(output_dir / "time_series_long.csv")
    final_rows = _csv_rows(output_dir / "final_metrics.csv")
    provenance_rows = _csv_rows(output_dir / "provenance_table.csv")
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")

    assert any(row["state"] == "cellobiose_concentration" and row["state_role"] == "substrate" for row in time_rows)
    assert any(row["state"] == "beta_D_glucose_concentration" and row["state_role"] == "product" for row in time_rows)
    assert any(row["state"] == "beta_glucosidase_concentration" and row["state_role"] == "enzyme" for row in time_rows)
    assert any(row["metric"] == "final_product_concentration" and row["status"] == "computed" for row in final_rows)
    assert any(row["record_type"] == "case_template" for row in provenance_rows)
    assert any(row["category"] == "case_template" for row in limitation_rows)


def test_case_template_assembly_does_not_mutate_registry_records(tmp_path: Path) -> None:
    registry = _registry_with_exact_enzyme_concentration(tmp_path)
    template_before = registry.get_case_template("sabiork_reaction_618_homogeneous_mm_template").to_dict()
    compatibility_before = registry.get_process_compatibility(
        enzyme_class="beta_glucosidase",
        substrate_class="cellobiose",
        process_type="homogeneous_michaelis_menten",
    )[0].to_dict()

    build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "outputs"),
    )

    assert registry.get_case_template("sabiork_reaction_618_homogeneous_mm_template").to_dict() == template_before
    assert (
        registry.get_process_compatibility(
            enzyme_class="beta_glucosidase",
            substrate_class="cellobiose",
            process_type="homogeneous_michaelis_menten",
        )[0].to_dict()
        == compatibility_before
    )


def test_config_driven_case_assembly_uses_no_live_external_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def blocked_connect(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Live external API calls are not allowed during registry case assembly.")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    registry = load_registry(REGISTRY_INDEX)

    simulate_screen(
        fungus_ids=[BIO_FUNGUS_ID],
        substrate_ids=[BIO_SUBSTRATE_ID],
        environment_ids=[BIO_ENVIRONMENT_ID],
        registry=registry,
        n_samples=1,
        seed=9,
        output_dir=tmp_path / "screen",
    )


def _registry_with_bio002_product_inhibition(
    tmp_path: Path,
    *,
    include_ki_record: bool = True,
    ki_value: float = 2.0,
) -> Path:
    registry_dir = _copy_registry(tmp_path)
    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_data = _yaml_mapping(template_path)
    records = cast(list[dict[str, Any]], template_data["records"])
    for record in records:
        if record["record_id"] == "bio002_extracellular_enzyme_chain_template":
            metadata = record["process_state_metadata"]
            metadata["parameter_record_ids"]["product_inhibition_constant"] = "bio003_fixture_product_inhibition_constant"
            metadata["parameter_role_contracts"]["product_inhibition_constant"] = (
                _bio002_homogeneous_role_contract("K_i_bio003_product_fixture")
            )
            metadata["process_templates"][1]["modifiers"] = [
                {
                    "type": "product_inhibition",
                    "product_state_role": "product",
                    "inhibition_constant_role": "product_inhibition_constant",
                }
            ]
            record["limitations"].append(
                "Optional BIO-003 software-test product inhibition uses a configured K_i fixture only; it is not validation data."
            )
            break
    else:
        raise AssertionError("Missing BIO-002 chain template")
    template_path.write_text(yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8")
    _add_bio002_component_role_mappings(
        registry_dir,
        {"inhibition_constant": "K_i_bio003_product_fixture"},
    )

    if include_ki_record:
        parameter_path = registry_dir / "parameters" / "parameter_records.yml"
        parameter_data = _yaml_mapping(parameter_path)
        cast(list[dict[str, Any]], parameter_data["records"]).insert(
            0,
            {
                "record_id": "bio003_fixture_product_inhibition_constant",
                "name": "BIO-003 configured product inhibition K_i fixture",
                "maturity": "toy_development",
                "provenance": {
                    "source": "FungMod BIO-003 registry product-inhibition software test fixture.",
                    "confidence_level": "testing",
                    "bio_milestone": "BIO-003",
                    "notes": "Artificial K_i value used only to verify registry-backed modifier assembly.",
                },
                "parameter_symbol": "K_i_bio003_product_fixture",
                "process_type": "homogeneous_michaelis_menten",
                "enzyme_class": "beta_glucosidase",
                "substrate_class": "cellobiose",
                "fungus_id": REACTION_FUNGUS_ID,
                "substrate_id": REACTION_SUBSTRATE_ID,
                "environment_id": REACTION_ENVIRONMENT_ID,
                "value": {
                    "kind": "exact",
                    "value": ki_value,
                    "units": "mM",
                    "source": "FungMod BIO-003 registry product-inhibition software test fixture.",
                    "confidence_level": "testing",
                    "notes": "Artificial value for configured product-inhibition tests; not validation data.",
                },
                "range_scope": "software_test_fixture",
                "range_interpretation": "configured mechanics only",
                "allowed_use": PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY,
                "notes": "Fixture K_i for proving explicit registry-backed product-inhibition assembly.",
            },
        )
        parameter_path.write_text(yaml.safe_dump(parameter_data, sort_keys=False), encoding="utf-8")
    return registry_dir


def _registry_with_bio002_environment_modifiers(
    tmp_path: Path,
    *,
    modifier_set: str,
    ph_width_role: str = "ph_width",
    include_ph_width_role: bool = True,
    include_environment_oxygen: bool = True,
    include_oxygen_units: bool = True,
    ph_value_kind: str = "exact",
) -> Path:
    registry_dir = _copy_registry(tmp_path)

    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_data = _yaml_mapping(template_path)
    for record in cast(list[dict[str, Any]], template_data["records"]):
        if record["record_id"] == "bio002_extracellular_enzyme_chain_template":
            metadata = record["process_state_metadata"]
            if modifier_set == "temperature_ph":
                metadata["parameter_record_ids"].update(
                    {
                        "activation_energy": "bio002_chain_activation_energy_fixture",
                        "reference_temperature": "bio002_chain_reference_temperature_fixture",
                        "ph_optimum": "bio002_chain_ph_optimum_fixture",
                        "ph_width": "bio002_chain_ph_width_fixture",
                    }
                )
                metadata["parameter_role_contracts"].update(
                    {
                        "activation_energy": _bio002_homogeneous_role_contract("E_a_bio002_chain_env_fixture"),
                        "reference_temperature": _bio002_homogeneous_role_contract("T_ref_bio002_chain_env_fixture"),
                        "ph_optimum": _bio002_homogeneous_role_contract("pH_opt_bio002_chain_env_fixture"),
                        "ph_width": _bio002_homogeneous_role_contract("pH_width_bio002_chain_env_fixture"),
                    }
                )
                ph_modifier = {
                    "type": "ph_gaussian",
                    "optimum_role": "ph_optimum",
                }
                if include_ph_width_role:
                    ph_modifier["width_role"] = ph_width_role
                metadata["process_templates"][1]["modifiers"] = [
                    {
                        "type": "temperature_arrhenius_reference",
                        "activation_energy_role": "activation_energy",
                        "reference_temperature_role": "reference_temperature",
                    },
                    ph_modifier,
                ]
            elif modifier_set == "oxygen_water":
                metadata["parameter_record_ids"].update(
                    {
                        "oxygen_half_saturation": "bio002_chain_oxygen_half_saturation_fixture",
                        "minimum_water_activity": "bio002_chain_minimum_water_activity_fixture",
                    }
                )
                metadata["parameter_role_contracts"].update(
                    {
                        "oxygen_half_saturation": _bio002_homogeneous_role_contract("K_O2_bio002_chain_env_fixture"),
                        "minimum_water_activity": _bio002_homogeneous_role_contract("a_w_min_bio002_chain_env_fixture"),
                    }
                )
                oxygen_modifier = {
                    "type": "oxygen_monod",
                    "half_saturation_role": "oxygen_half_saturation",
                }
                if include_oxygen_units:
                    oxygen_modifier["oxygen_units"] = "mole / liter"
                metadata["process_templates"][1]["modifiers"] = [
                    oxygen_modifier,
                    {
                        "type": "water_activity_threshold",
                        "minimum_water_activity_role": "minimum_water_activity",
                    },
                ]
            else:
                raise AssertionError(f"Unknown modifier set {modifier_set!r}")
            break
    else:
        raise AssertionError("Missing BIO-002 chain template")
    template_path.write_text(yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8")
    if modifier_set == "temperature_ph":
        component_roles = {
            "activation_energy": "E_a_bio002_chain_env_fixture",
            "reference_temperature": "T_ref_bio002_chain_env_fixture",
            "ph_optimum": "pH_opt_bio002_chain_env_fixture",
            "ph_width": "pH_width_bio002_chain_env_fixture",
        }
    else:
        component_roles = {
            "oxygen_half_saturation": "K_O2_bio002_chain_env_fixture",
            "minimum_water_activity": "a_w_min_bio002_chain_env_fixture",
        }
    _add_bio002_component_role_mappings(registry_dir, component_roles)

    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    parameter_data = _yaml_mapping(parameter_path)
    parameter_records = cast(list[dict[str, Any]], parameter_data["records"])
    if modifier_set == "temperature_ph":
        parameter_records[0:0] = [
            _chain_environment_modifier_parameter_record(
                record_id="bio002_chain_activation_energy_fixture",
                name="BIO-002 chain Arrhenius activation energy fixture",
                symbol="E_a_bio002_chain_env_fixture",
                value=50000.0,
                units="joule / mole",
                notes="Artificial activation energy for chain environment-modifier tests; not a fitted response.",
            ),
            _chain_environment_modifier_parameter_record(
                record_id="bio002_chain_reference_temperature_fixture",
                name="BIO-002 chain Arrhenius reference temperature fixture",
                symbol="T_ref_bio002_chain_env_fixture",
                value=293.15,
                units="kelvin",
                notes="Artificial reference temperature for chain environment-modifier tests; not a fitted response.",
            ),
            _chain_environment_modifier_parameter_record(
                record_id="bio002_chain_ph_optimum_fixture",
                name="BIO-002 chain pH optimum fixture",
                symbol="pH_opt_bio002_chain_env_fixture",
                value=6.0,
                units="dimensionless",
                notes="Artificial pH optimum for chain environment-modifier tests; not a fitted response.",
            ),
            _chain_environment_modifier_parameter_record(
                record_id="bio002_chain_ph_width_fixture",
                name="BIO-002 chain pH width fixture",
                symbol="pH_width_bio002_chain_env_fixture",
                value=1.5,
                units="dimensionless",
                notes="Artificial pH width for chain environment-modifier tests; not a fitted response.",
            ),
        ]
    else:
        parameter_records[0:0] = [
            _chain_environment_modifier_parameter_record(
                record_id="bio002_chain_oxygen_half_saturation_fixture",
                name="BIO-002 chain oxygen half-saturation fixture",
                symbol="K_O2_bio002_chain_env_fixture",
                value=0.0001,
                units="mole / liter",
                notes="Artificial oxygen half-saturation for chain environment-modifier tests; not a fitted response.",
            ),
            _chain_environment_modifier_parameter_record(
                record_id="bio002_chain_minimum_water_activity_fixture",
                name="BIO-002 chain minimum water-activity fixture",
                symbol="a_w_min_bio002_chain_env_fixture",
                value=0.75,
                units="dimensionless",
                notes="Artificial water-activity threshold for chain environment-modifier tests; not a fitted response.",
            ),
        ]
    parameter_path.write_text(yaml.safe_dump(parameter_data, sort_keys=False), encoding="utf-8")

    environment_path = registry_dir / "environments" / "environments.yml"
    environment_data = _yaml_mapping(environment_path)
    for record in cast(list[dict[str, Any]], environment_data["records"]):
        if record["record_id"] == REACTION_ENVIRONMENT_ID:
            conditions = record["conditions"]
            if ph_value_kind == "range":
                conditions["ph"] = {
                    "kind": "range",
                    "lower": 4.8,
                    "upper": 5.2,
                    "units": "dimensionless",
                    "source": "FungMod PR-33 chain environment-modifier software test fixture.",
                    "confidence_level": "testing",
                    "notes": "Artificial pH range used to prove exact-value guardrails.",
                }
            if modifier_set == "oxygen_water":
                if include_environment_oxygen:
                    conditions["oxygen_concentration"] = {
                        "kind": "exact",
                        "value": 0.00025,
                        "units": "mole / liter",
                        "source": "FungMod PR-33 chain environment-modifier software test fixture.",
                        "confidence_level": "testing",
                        "notes": "Artificial exact oxygen value for configured modifier assembly tests.",
                    }
                else:
                    conditions.pop("oxygen_concentration", None)
                conditions["water_activity"] = {
                    "kind": "exact",
                    "value": 0.96,
                    "units": "dimensionless",
                    "source": "FungMod PR-33 chain environment-modifier software test fixture.",
                    "confidence_level": "testing",
                    "notes": "Artificial exact water activity for configured modifier assembly tests.",
                }
            break
    else:
        raise AssertionError("Missing Reaction 618 environment")
    environment_path.write_text(yaml.safe_dump(environment_data, sort_keys=False), encoding="utf-8")
    return registry_dir


def _chain_environment_modifier_parameter_record(
    *,
    record_id: str,
    name: str,
    symbol: str,
    value: float,
    units: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": name,
        "maturity": "software_test_fixture",
        "provenance": {
            "source": "FungMod PR-33 chain environment-modifier software test fixture.",
            "confidence_level": "testing",
            "bio_milestone": "PR-33",
            "notes": notes,
        },
        "parameter_symbol": symbol,
        "process_type": "homogeneous_michaelis_menten",
        "enzyme_class": "beta_glucosidase",
        "substrate_class": "cellobiose",
        "fungus_id": REACTION_FUNGUS_ID,
        "substrate_id": REACTION_SUBSTRATE_ID,
        "environment_id": REACTION_ENVIRONMENT_ID,
        "value": {
            "kind": "exact",
            "value": value,
            "units": units,
            "source": "FungMod PR-33 chain environment-modifier software test fixture.",
            "confidence_level": "testing",
            "notes": notes,
        },
        "range_scope": "software_test_fixture",
        "range_interpretation": "configured mechanics only",
        "allowed_use": PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY,
        "notes": notes,
    }


def _bio002_homogeneous_role_contract(symbol: str) -> dict[str, Any]:
    return {
        "kind": "process_parameter",
        "parameter_symbol": symbol,
        "enzyme_class": "beta_glucosidase",
        "substrate_class": "cellobiose",
        "fungus_id": REACTION_FUNGUS_ID,
        "substrate_id": REACTION_SUBSTRATE_ID,
        "environment_id": REACTION_ENVIRONMENT_ID,
    }


def _registry_with_reaction618_process_modifier(
    tmp_path: Path,
    *,
    include_ki_record: bool = True,
    ki_value: float = 2.0,
) -> Path:
    registry_dir = _copy_registry(tmp_path)

    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_data = _yaml_mapping(template_path)
    for record in cast(list[dict[str, Any]], template_data["records"]):
        if record["record_id"] == "sabiork_reaction_618_homogeneous_mm_template":
            record["process_state_metadata"]["process_modifiers"] = [
                {
                    "type": "product_inhibition",
                    "product_state_role": "product",
                    "inhibition_constant_role": "product_inhibition_constant",
                }
            ]
            break
    else:
        raise AssertionError("Missing Reaction 618 case template")
    template_path.write_text(yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8")

    compatibility_path = registry_dir / "processes" / "process_compatibility.yml"
    compatibility_data = _yaml_mapping(compatibility_path)
    for record in cast(list[dict[str, Any]], compatibility_data["records"]):
        if record["record_id"] == "beta_glucosidase_cellobiose_homogeneous_mm":
            record["required_parameters"].append("K_i_reaction618_product_fixture")
            record["parameter_roles"]["product_inhibition_constant"] = "K_i_reaction618_product_fixture"
            break
    else:
        raise AssertionError("Missing Reaction 618 process compatibility")
    compatibility_path.write_text(yaml.safe_dump(compatibility_data, sort_keys=False), encoding="utf-8")

    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    parameter_data = _yaml_mapping(parameter_path)
    parameter_records = cast(list[dict[str, Any]], parameter_data["records"])
    for record in parameter_records:
        if (
            record.get("parameter_symbol") == ENZYME_CONCENTRATION_SYMBOL
            and record.get("process_type") == "homogeneous_michaelis_menten"
            and record.get("maturity") == "literature_processed"
        ):
            record["value"] = {
                "kind": "exact",
                "value": 0.01,
                "units": "mM",
                "source": "Local deterministic enzyme concentration fixture",
                "confidence_level": "synthetic_control",
                "notes": "Used only to exercise homogeneous builder mechanics; not a SABIO-RK value.",
            }
            break
    else:
        raise AssertionError("Missing enzyme concentration record")

    if include_ki_record:
        parameter_records.insert(
            0,
            {
                "record_id": "reaction618_product_inhibition_constant_fixture",
                "name": "Reaction 618 product inhibition K_i fixture",
                "maturity": "software_test_fixture",
                "provenance": {
                    "source": "FungMod one-process product-inhibition software test fixture.",
                    "confidence_level": "testing",
                    "bio_milestone": "BIO-003",
                    "notes": "Artificial K_i value used only to verify one-process registry-template modifier assembly.",
                },
                "parameter_symbol": "K_i_reaction618_product_fixture",
                "process_type": "homogeneous_michaelis_menten",
                "enzyme_class": None,
                "substrate_class": None,
                "fungus_id": None,
                "substrate_id": None,
                "environment_id": None,
                "value": {
                    "kind": "exact",
                    "value": ki_value,
                    "units": "mM",
                    "source": "FungMod one-process product-inhibition software test fixture.",
                    "confidence_level": "testing",
                    "notes": "Artificial value for one-process configured product-inhibition tests; not validation data.",
                },
                "range_scope": "software_test_fixture",
                "range_interpretation": "configured mechanics only",
                "allowed_use": PARAMETER_ALLOWED_USE_SCIENTIFIC,
                "notes": "Fixture K_i for proving explicit one-process registry-backed product-inhibition assembly.",
            },
        )
    parameter_path.write_text(yaml.safe_dump(parameter_data, sort_keys=False), encoding="utf-8")
    return registry_dir


def _registry_with_reaction618_environment_modifiers(
    tmp_path: Path,
    *,
    modifier_set: str,
    ph_width_role: str = "ph_width",
    include_environment_oxygen: bool = True,
    include_oxygen_units: bool = True,
    ph_value_kind: str = "exact",
) -> Path:
    registry_dir = _copy_registry(tmp_path)

    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_data = _yaml_mapping(template_path)
    for record in cast(list[dict[str, Any]], template_data["records"]):
        if record["record_id"] == "sabiork_reaction_618_homogeneous_mm_template":
            if modifier_set == "temperature_ph":
                record["process_state_metadata"]["process_modifiers"] = [
                    {
                        "type": "temperature_arrhenius_reference",
                        "activation_energy_role": "activation_energy",
                        "reference_temperature_role": "reference_temperature",
                    },
                    {
                        "type": "ph_gaussian",
                        "optimum_role": "ph_optimum",
                        "width_role": ph_width_role,
                    },
                ]
            elif modifier_set == "oxygen_water":
                oxygen_modifier = {
                    "type": "oxygen_monod",
                    "half_saturation_role": "oxygen_half_saturation",
                }
                if include_oxygen_units:
                    oxygen_modifier["oxygen_units"] = "mole / liter"
                record["process_state_metadata"]["process_modifiers"] = [
                    oxygen_modifier,
                    {
                        "type": "water_activity_threshold",
                        "minimum_water_activity_role": "minimum_water_activity",
                    },
                ]
            elif modifier_set == "unsupported":
                record["process_state_metadata"]["process_modifiers"] = [
                    {
                        "type": "temperature_magic",
                        "activation_energy_role": "activation_energy",
                    }
                ]
            else:
                raise AssertionError(f"Unknown modifier set {modifier_set!r}")
            break
    else:
        raise AssertionError("Missing Reaction 618 case template")
    template_path.write_text(yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8")

    compatibility_path = registry_dir / "processes" / "process_compatibility.yml"
    compatibility_data = _yaml_mapping(compatibility_path)
    for record in cast(list[dict[str, Any]], compatibility_data["records"]):
        if record["record_id"] == "beta_glucosidase_cellobiose_homogeneous_mm":
            if modifier_set == "temperature_ph":
                _add_role_mapping(record, "activation_energy", "E_a_reaction618_env_fixture")
                _add_role_mapping(record, "reference_temperature", "T_ref_reaction618_env_fixture")
                _add_role_mapping(record, "ph_optimum", "pH_opt_reaction618_env_fixture")
                _add_role_mapping(record, "ph_width", "pH_width_reaction618_env_fixture")
            else:
                _add_role_mapping(record, "oxygen_half_saturation", "K_O2_reaction618_env_fixture")
                _add_role_mapping(record, "minimum_water_activity", "a_w_min_reaction618_env_fixture")
            break
    else:
        raise AssertionError("Missing Reaction 618 process compatibility")
    compatibility_path.write_text(yaml.safe_dump(compatibility_data, sort_keys=False), encoding="utf-8")

    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    parameter_data = _yaml_mapping(parameter_path)
    parameter_records = cast(list[dict[str, Any]], parameter_data["records"])
    _set_reaction618_enzyme_concentration_exact(parameter_records)
    if modifier_set == "temperature_ph":
        parameter_records[0:0] = [
            _environment_modifier_parameter_record(
                record_id="reaction618_activation_energy_fixture",
                name="Reaction 618 Arrhenius activation energy fixture",
                symbol="E_a_reaction618_env_fixture",
                value=50000.0,
                units="joule / mole",
                notes="Artificial activation energy for registry environment-modifier tests; not a fitted response.",
            ),
            _environment_modifier_parameter_record(
                record_id="reaction618_reference_temperature_fixture",
                name="Reaction 618 Arrhenius reference temperature fixture",
                symbol="T_ref_reaction618_env_fixture",
                value=293.15,
                units="kelvin",
                notes="Artificial reference temperature for registry environment-modifier tests; not a fitted response.",
            ),
            _environment_modifier_parameter_record(
                record_id="reaction618_ph_optimum_fixture",
                name="Reaction 618 pH optimum fixture",
                symbol="pH_opt_reaction618_env_fixture",
                value=6.0,
                units="dimensionless",
                notes="Artificial pH optimum for registry environment-modifier tests; not a fitted response.",
            ),
            _environment_modifier_parameter_record(
                record_id="reaction618_ph_width_fixture",
                name="Reaction 618 pH width fixture",
                symbol="pH_width_reaction618_env_fixture",
                value=1.5,
                units="dimensionless",
                notes="Artificial pH width for registry environment-modifier tests; not a fitted response.",
            ),
        ]
    else:
        parameter_records[0:0] = [
            _environment_modifier_parameter_record(
                record_id="reaction618_oxygen_half_saturation_fixture",
                name="Reaction 618 oxygen half-saturation fixture",
                symbol="K_O2_reaction618_env_fixture",
                value=0.25,
                units="mole / liter",
                notes="Artificial oxygen half-saturation for registry modifier tests; not oxygen physiology.",
            ),
            _environment_modifier_parameter_record(
                record_id="reaction618_minimum_water_activity_fixture",
                name="Reaction 618 minimum water-activity fixture",
                symbol="a_w_min_reaction618_env_fixture",
                value=0.9,
                units="dimensionless",
                notes="Artificial water-activity threshold for registry modifier tests; not a fitted moisture response.",
            ),
        ]
    parameter_path.write_text(yaml.safe_dump(parameter_data, sort_keys=False), encoding="utf-8")

    environment_path = registry_dir / "environments" / "environments.yml"
    environment_data = _yaml_mapping(environment_path)
    for record in cast(list[dict[str, Any]], environment_data["records"]):
        if record["record_id"] == REACTION_ENVIRONMENT_ID:
            conditions = cast(dict[str, Any], record["conditions"])
            if ph_value_kind == "range":
                conditions["ph"] = {
                    "kind": "range",
                    "lower": 4.5,
                    "upper": 5.5,
                    "units": "dimensionless",
                    "source": "FungMod PR-31 non-exact environment fixture.",
                    "confidence_level": "testing",
                    "notes": "Range value used only to prove registry builder rejects non-exact modifier environments.",
                }
            if modifier_set == "oxygen_water":
                if include_environment_oxygen:
                    conditions["oxygen_concentration"] = {
                        "kind": "exact",
                        "value": 0.25,
                        "units": "mole / liter",
                        "source": "FungMod PR-31 oxygen-water environment fixture.",
                        "confidence_level": "testing",
                        "notes": "Artificial oxygen concentration for configured modifier mechanics only.",
                    }
                conditions["water_activity"] = {
                    "kind": "exact",
                    "value": 0.98,
                    "units": "dimensionless",
                    "source": "FungMod PR-31 oxygen-water environment fixture.",
                    "confidence_level": "testing",
                    "notes": "Artificial water activity for configured modifier mechanics only.",
                }
            break
    else:
        raise AssertionError("Missing Reaction 618 environment")
    environment_path.write_text(yaml.safe_dump(environment_data, sort_keys=False), encoding="utf-8")
    return registry_dir


def _add_role_mapping(record: dict[str, Any], role: str, symbol: str) -> None:
    parameter_roles = cast(dict[str, str], record["parameter_roles"])
    parameter_roles[role] = symbol
    required_parameters = cast(list[str], record["required_parameters"])
    if symbol not in required_parameters:
        required_parameters.append(symbol)


def _add_bio002_component_role_mappings(
    registry_dir: Path,
    mappings: dict[str, str],
) -> None:
    path = registry_dir / "processes" / "process_compatibility.yml"
    data = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], data["records"])
    component = next(
        (
            record
            for record in records
            if record["record_id"] == "bio002_beta_glucosidase_cellobiose_component"
        ),
        None,
    )
    if component is None:
        raise AssertionError("Missing BIO-002 homogeneous component compatibility")
    for role, symbol in mappings.items():
        _add_role_mapping(component, role, symbol)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _set_reaction618_enzyme_concentration_exact(parameter_records: list[dict[str, Any]]) -> None:
    for record in parameter_records:
        if (
            record.get("parameter_symbol") == ENZYME_CONCENTRATION_SYMBOL
            and record.get("process_type") == "homogeneous_michaelis_menten"
            and record.get("maturity") == "literature_processed"
        ):
            record["value"] = {
                "kind": "exact",
                "value": 0.01,
                "units": "mM",
                "source": "Local deterministic enzyme concentration fixture",
                "confidence_level": "synthetic_control",
                "notes": "Used only to exercise homogeneous builder mechanics; not a SABIO-RK value.",
            }
            return
    raise AssertionError("Missing enzyme concentration record")


def _environment_modifier_parameter_record(
    *,
    record_id: str,
    name: str,
    symbol: str,
    value: float,
    units: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": name,
        "maturity": "software_test_fixture",
        "provenance": {
            "source": "FungMod PR-31 registry environment-modifier software test fixture.",
            "confidence_level": "testing",
            "bio_milestone": "PR-31",
            "notes": notes,
        },
        "parameter_symbol": symbol,
        "process_type": "homogeneous_michaelis_menten",
        "enzyme_class": None,
        "substrate_class": None,
        "fungus_id": None,
        "substrate_id": None,
        "environment_id": None,
        "value": {
            "kind": "exact",
            "value": value,
            "units": units,
            "source": "FungMod PR-31 registry environment-modifier software test fixture.",
            "confidence_level": "testing",
            "notes": notes,
        },
        "range_scope": "software_test_fixture",
        "range_interpretation": "configured mechanics only",
        "allowed_use": PARAMETER_ALLOWED_USE_SCIENTIFIC,
        "notes": notes,
    }


def _registry_with_exact_enzyme_concentration(tmp_path: Path):
    registry_dir = _copy_registry(tmp_path)
    parameters_path = registry_dir / "parameters" / "parameter_records.yml"
    data = _yaml_mapping(parameters_path)
    records = cast(list[dict[str, Any]], data["records"])
    for record in records:
        if (
            record.get("parameter_symbol") == ENZYME_CONCENTRATION_SYMBOL
            and record.get("process_type") == "homogeneous_michaelis_menten"
            and record.get("maturity") == "literature_processed"
        ):
            record["value"] = {
                "kind": "exact",
                "value": 0.01,
                "units": "mM",
                "source": "Local deterministic enzyme concentration fixture",
                "confidence_level": "synthetic_control",
                "notes": "Used only to exercise homogeneous builder mechanics; not a SABIO-RK value.",
            }
            parameters_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            return load_registry(registry_dir / "registry_index.yml")
    raise AssertionError("Missing enzyme concentration record")


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
