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
from fungal_model.screening import (
    EnzymeChainAssemblyError,
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

    with pytest.raises(EnzymeChainAssemblyError, match="Unknown parameter record"):
        build_extracellular_enzyme_chain_config(registry=registry)


def test_registry_product_inhibition_rejects_non_positive_ki_without_fallback(tmp_path: Path) -> None:
    registry_dir = _registry_with_bio002_product_inhibition(tmp_path, ki_value=0.0)
    registry = load_registry(registry_dir / "registry_index.yml")
    config = build_extracellular_enzyme_chain_config(registry=registry, output_directory=tmp_path / "bad_ki")
    config_path = tmp_path / "bad_ki.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "bad_ki")

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
                "enzyme_class": None,
                "substrate_class": None,
                "fungus_id": None,
                "substrate_id": None,
                "environment_id": None,
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
                "allowed_use": "software_testing_only_not_scientific_validation",
                "notes": "Fixture K_i for proving explicit registry-backed product-inhibition assembly.",
            },
        )
        parameter_path.write_text(yaml.safe_dump(parameter_data, sort_keys=False), encoding="utf-8")
    return registry_dir


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
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
