from __future__ import annotations

import csv
import shutil
import socket
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model import VirtualExperiment
from fungal_model.registry import load_registry
from fungal_model.screening import build_model_config_from_registry_case
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
