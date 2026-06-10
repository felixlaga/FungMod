from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.io.model_config import ProcessConfig
from fungal_model.processes import ProcessBuildContext, ProcessLibrary, ProductReleaseMap
from fungal_model.processes.homogeneous import HomogeneousMichaelisMentenProcess
from fungal_model.registry import load_registry
from fungal_model.screening import build_model_config_from_registry_case
from fungal_model.workflows import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

REACTION_FUNGUS_ID = "sabiork_beta_glucosidase_source"
REACTION_SUBSTRATE_ID = "cellobiose"
REACTION_ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"
ENZYME_CONCENTRATION_SYMBOL = "enzyme_concentration_beta_glucosidase"


def test_reaction_618_glucose_formed_is_twice_cellobiose_consumed(tmp_path: Path) -> None:
    registry = _registry_with_exact_reaction_618_enzyme_concentration(tmp_path)
    config = build_model_config_from_registry_case(
        fungus_id=REACTION_FUNGUS_ID,
        substrate_id=REACTION_SUBSTRATE_ID,
        environment_id=REACTION_ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "outputs"),
    )
    config_path = tmp_path / "reaction_618.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")

    result = run_configured_model(config_path, output_dir=tmp_path / "bundle")

    cellobiose = result.state("cellobiose_concentration").to("mM").magnitude
    glucose = result.state("beta_D_glucose_concentration").to("mM").magnitude
    cellobiose_consumed = cellobiose[0] - cellobiose[-1]
    glucose_formed = glucose[-1] - glucose[0]

    assert cellobiose_consumed > 0.0
    assert glucose_formed == pytest.approx(2.0 * cellobiose_consumed, rel=1.0e-6, abs=1.0e-9)


def test_homogeneous_mm_factory_uses_stoichiometric_product_map_coefficients() -> None:
    process_config = ProcessConfig.from_mapping(
        {
            "id": "stoichiometric_mm",
            "process_type": "homogeneous_michaelis_menten",
            "states": {"substrate": "S", "product": "P"},
            "parameters": {
                "km": "Km",
                "vmax": "Vmax",
                "rate_units": "mole / liter / second",
            },
            "product_map": "two_product_map",
        }
    )
    context = ProcessBuildContext(
        state_units={"S": "mole / liter", "P": "mole / liter"},
        product_maps={
            "two_product_map": ProductReleaseMap(
                reactants={"S": 1.0},
                products={"P": 2.0},
                notes="2:1 product map fixture.",
            )
        },
    )

    process = ProcessLibrary.default_foundation().build_processes(context, (process_config,))[0]

    assert isinstance(process, HomogeneousMichaelisMentenProcess)
    assert process.product_coefficients == {"P": 2.0}


def test_new_surface_catalysis_template_assembles_without_record_id_specific_branch(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _insert_surface_template_fixture(registry_dir)
    _insert_surface_compatibility_fixture(registry_dir)
    registry = load_registry(registry_dir / "registry_index.yml")

    config = build_model_config_from_registry_case(
        fungus_id="toy_fungus_alpha",
        substrate_id="toy_cellulose_like_solid",
        environment_id="toy_lab_environment",
        registry=registry,
        output_directory=str(tmp_path / "outputs"),
    )
    data = config.to_dict()

    assert data["case_template"]["case_template_id"] == "pre_bio_surface_template_fixture"
    assert data["name"] == "PRE-BIO generic surface template toy_fungus_alpha on toy_cellulose_like_solid"
    assert data["mode"] == "toy"
    assert data["maturity"] == "framework_benchmark"
    assert data["entities"]["geometry"]["data"]["surface_area"]["value"] == pytest.approx(0.33)
    assert data["processes"][0]["states"] == {
        "substrate": "custom_surface_substrate_pool",
        "catalyst": "custom_surface_catalyst_pool",
        "product": "custom_surface_product_pool",
        "bond_type": "toy_beta_1_4_glycosidic",
        "accessible_site_pool": "pre-bio template accessible pool",
    }


def test_toy_case_template_is_marked_outside_public_path() -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = registry.get_case_template("toy_surface_catalysis_registry_template")

    assert template.process_state_metadata["public_path"] is False


def _registry_with_exact_reaction_618_enzyme_concentration(tmp_path: Path):
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
    raise AssertionError("Missing Reaction 618 enzyme concentration record")


def _insert_surface_template_fixture(registry_dir: Path) -> None:
    path = registry_dir / "case_templates" / "case_templates.yml"
    data = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], data["records"])
    records.insert(
        0,
        {
            "record_id": "pre_bio_surface_template_fixture",
            "case_template_id": "pre_bio_surface_template_fixture",
            "name": "PRE-BIO generic surface-catalysis template fixture",
            "maturity": "toy_development",
            "provenance": {
                "source": "PRE-BIO-001 test fixture",
                "confidence_level": "testing",
                "notes": "Template fixture with new IDs to prove assembly is template-driven.",
            },
            "schema_version": "1",
            "process_type": "surface_catalysis",
            "state_roles": {
                "substrate": "custom_surface_substrate_pool",
                "product": "custom_surface_product_pool",
                "catalyst": "custom_surface_catalyst_pool",
            },
            "initial_state_mapping": {
                "substrate": {"value": 0.0001, "units": "kilogram"},
                "product": {"value": 0.0, "units": "kilogram"},
                "catalyst": {"value": 1.0, "units": "mole / liter"},
            },
            "product_map": {
                "id": "pre_bio_surface_product_map_fixture",
                "product_map_type": "one_to_one",
                "substrate_state_role": "substrate",
                "product_state_role": "product",
                "stoichiometric_yield": 1.0,
                "notes": "Template fixture product map.",
            },
            "stoichiometric_yields": {"product": 1.0},
            "time_grid": {"start": 0.0, "stop": 10.0, "points": 6, "units": "second"},
            "observable_roles": ["substrate", "product", "catalyst"],
            "output_state_roles": {
                "substrate": "custom_surface_substrate_pool",
                "product": "custom_surface_product_pool",
                "catalyst": "custom_surface_catalyst_pool",
            },
            "process_state_metadata": {
                "config_name": "PRE-BIO generic surface template {fungus_id} on {substrate_id}",
                "config_mode": "toy",
                "config_maturity": "framework_benchmark",
                "public_path": False,
                "bond_type": "toy_beta_1_4_glycosidic",
                "accessible_site_pool": "pre-bio template accessible pool",
                "geometry": {
                    "kind": "geometry",
                    "name": "PRE-BIO template geometry fixture",
                    "geometry_type": "well_mixed",
                    "provenance": {
                        "source": "PRE-BIO-001 test fixture",
                        "confidence_level": "testing",
                        "notes": "Template-owned geometry fixture.",
                    },
                    "volume": {"value": 100.0, "units": "milliliter"},
                    "surface_area": {"value": 0.33, "units": "meter ** 2"},
                    "parameters": [],
                },
            },
            "limitations": ["Template-driven surface-catalysis assembly fixture only."],
            "validity_notes": ["Software-test fixture only; no biology added."],
            "notes": "PRE-BIO-001 generic template assembly fixture.",
        },
    )
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _insert_surface_compatibility_fixture(registry_dir: Path) -> None:
    path = registry_dir / "processes" / "process_compatibility.yml"
    data = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], data["records"])
    fixture = {
            "record_id": "pre_bio_surface_compatibility_fixture",
            "name": "PRE-BIO generic surface compatibility fixture",
            "maturity": "toy_development",
            "provenance": {
                "source": "PRE-BIO-001 test fixture",
                "confidence_level": "testing",
                "notes": "New record ID fixture to prove assembly avoids case-specific branches.",
            },
            "enzyme_class": "toy_cellulase",
            "substrate_class": "toy_cellulose_like",
            "required_bond_classes": ["toy_beta_1_4_glycosidic"],
            "process_type": "surface_catalysis",
            "required_parameters": ["k_surface_exact", "k_ads_exact", "A_surface_exact"],
            "parameter_roles": {
                "surface_rate_constant": "k_surface_exact",
                "adsorption_constant": "k_ads_exact",
                "accessible_surface_area": "A_surface_exact",
            },
            "product_map_required": True,
            "case_template_id": "pre_bio_surface_template_fixture",
            "notes": "PRE-BIO-001 generic compatibility fixture.",
    }
    data["records"] = [
        fixture,
        *(
            record
            for record in records
            if record.get("record_id") != "toy_cellulase_on_toy_cellulose_like_surface"
        ),
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
