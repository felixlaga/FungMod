from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any, Callable, cast

import numpy as np
import pytest
import yaml

from fungal_model.registry import load_registry
from fungal_model.screening import (
    EnzymeChainAssemblyError,
    build_extracellular_enzyme_chain_config,
    write_enzyme_chain_standard_tables,
)
from fungal_model.workflows import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
GENERIC_TEMPLATE_ID = "bio002_polymer_x_oligomer_y_monomer_z_template"


def test_second_unrelated_chain_assembles_runs_and_writes_tables(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    _insert_generic_chain_fixture(registry_dir)
    registry = load_registry(registry_dir / "registry_index.yml")

    config = build_extracellular_enzyme_chain_config(
        registry=registry,
        template_id=GENERIC_TEMPLATE_ID,
        output_directory=tmp_path / "bundle",
    )
    config_path = tmp_path / "generic_chain.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=tmp_path / "bundle")
    tables = write_enzyme_chain_standard_tables(config=config, result=result, output_dir=tmp_path / "tables")

    assert config.validate().passed
    assert [process.process_type for process in config.processes] == [
        "surface_catalysis",
        "homogeneous_michaelis_menten",
    ]
    assert [process.id for process in config.processes] == [
        "x_surface_to_y_fixture",
        "y_to_z_homogeneous_fixture",
    ]
    product_maps = {reference.id: reference.data for reference in config.entities.product_maps}
    assert product_maps["x_to_y_fixture_map"]["products"] == {"oligomer_y_pool": 1.5}
    assert product_maps["y_to_z_fixture_map"]["products"] == {"monomer_z_pool": 3.0}

    polymer = result.state("polymer_x_pool").to("mM").magnitude
    oligomer = result.state("oligomer_y_pool").to("mM").magnitude
    monomer = result.state("monomer_z_pool").to("mM").magnitude
    conserved = polymer + (2.0 / 3.0) * oligomer + (2.0 / 9.0) * monomer

    assert result.solver_metadata["success"] is True
    assert polymer[-1] < polymer[0]
    assert np.max(oligomer) > oligomer[0]
    assert monomer[-1] > monomer[0]
    assert conserved[-1] == pytest.approx(conserved[0], rel=1.0e-6, abs=1.0e-6)
    assert set(result.process_rates) == {"x_surface_to_y_fixture", "y_to_z_homogeneous_fixture"}

    for path in tables.values():
        assert Path(path).exists()
    final_metrics = _csv_rows(Path(tables["final_metrics"]))
    time_series = _csv_rows(Path(tables["time_series_long"]))
    thresholds = _csv_rows(Path(tables["threshold_times"]))
    metrics = {row["metric"] for row in final_metrics}
    series_names = {row["state"] for row in time_series}

    assert "z_equivalent_yield" in metrics
    assert "x_pool_depleted_fraction" in metrics
    assert {"polymer_x_remaining", "oligomer_y_amount", "monomer_z_amount"}.issubset(series_names)
    assert "final_glucose_yield" not in metrics
    assert "glucose_yield" not in series_names
    assert {row["metric"] for row in thresholds} == {"x_pool_depleted_fraction"}


@pytest.mark.parametrize("bad_coefficient", [0.0, -1.0, float("nan"), float("inf")])
def test_chain_product_maps_reject_non_positive_or_non_finite_coefficients(
    tmp_path: Path,
    bad_coefficient: float,
) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"]["product_maps"][0]["products"].update(
            {"intermediate": bad_coefficient}
        ),
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="positive and finite"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_chain_product_maps_reject_empty_required_maps(tmp_path: Path) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"]["product_maps"][0].update({"reactants": {}}),
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="product_map .*reactants"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_chain_product_maps_reject_unknown_state_roles(tmp_path: Path) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"]["product_maps"][0]["products"].update({"unknown": 1.5}),
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="unknown state role"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_chain_rejects_state_roles_without_units(tmp_path: Path) -> None:
    def remove_units(template: dict[str, Any]) -> None:
        state_spec = template["initial_state_mapping"]["product"]
        state_spec.pop("units")
        state_spec["units_from_role"] = "missing_parameter_role"

    registry_dir = _registry_with_modified_chain(tmp_path, remove_units)
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="units_from_role"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_chain_rejects_conflicting_legacy_product_state_declarations(tmp_path: Path) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"]["product_maps"][0].update(
            {"product_state": "legacy_product_pool"}
        ),
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="legacy field"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_chain_rejects_missing_conservation_for_mass_balance(tmp_path: Path) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"].pop("conservation"),
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="conservation"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_generic_implementation_has_no_demo_biological_name_guardrail() -> None:
    source = (ROOT / "src" / "fungal_model" / "screening" / "enzyme_chain.py").read_text(encoding="utf-8").casefold()

    forbidden = {"cellulose", "cellobiose", "glucose", "cellulase", "beta_glucosidase", "beta-d"}

    assert not forbidden.intersection(source)


def _registry_with_modified_chain(tmp_path: Path, modify: Callable[[dict[str, Any]], None]) -> Path:
    registry_dir = _copy_registry(tmp_path)
    _insert_generic_chain_fixture(registry_dir)
    path = registry_dir / "case_templates" / "case_templates.yml"
    data = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], data["records"])
    for record in records:
        if record["record_id"] == GENERIC_TEMPLATE_ID:
            modify(record)
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            return registry_dir
    raise AssertionError(f"Missing template {GENERIC_TEMPLATE_ID!r}")


def _insert_generic_chain_fixture(registry_dir: Path) -> None:
    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_data = _yaml_mapping(template_path)
    cast(list[dict[str, Any]], template_data["records"]).insert(0, _generic_chain_template())
    template_path.write_text(yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8")

    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    parameter_data = _yaml_mapping(parameter_path)
    cast(list[dict[str, Any]], parameter_data["records"])[0:0] = _generic_chain_parameters()
    parameter_path.write_text(yaml.safe_dump(parameter_data, sort_keys=False), encoding="utf-8")


def _generic_chain_template() -> dict[str, Any]:
    return {
        "record_id": GENERIC_TEMPLATE_ID,
        "case_template_id": GENERIC_TEMPLATE_ID,
        "name": "BIO-002 polymer X to monomer Z generic chain fixture",
        "maturity": "toy_development",
        "provenance": {
            "source": "BIO-002 genericity test fixture",
            "confidence_level": "testing",
            "bio_milestone": "BIO-002",
            "notes": "Artificial fixture proving chain assembly is data-driven.",
        },
        "schema_version": "1",
        "process_type": "extracellular_enzyme_chain",
        "state_roles": {
            "substrate": "polymer_x_pool",
            "intermediate": "oligomer_y_pool",
            "product": "monomer_z_pool",
            "surface_catalyst": "catalyst_alpha_pool",
            "homogeneous_catalyst": "catalyst_beta_pool",
        },
        "initial_state_mapping": {
            "substrate": {"parameter_role": "x_initial", "units_from_role": "x_initial"},
            "intermediate": {"value": 0.0, "units": "mM"},
            "product": {"value": 0.0, "units": "mM"},
            "surface_catalyst": {"parameter_role": "alpha_initial", "units_from_role": "alpha_initial"},
            "homogeneous_catalyst": {"parameter_role": "beta_initial", "units_from_role": "beta_initial"},
        },
        "product_map": {
            "id": "y_to_z_fixture_map",
            "product_map_type": "stoichiometric",
            "substrate_state_role": "intermediate",
            "product_state_role": "product",
            "stoichiometric_yield": 3.0,
            "notes": "Legacy summary field kept consistent with the chain map.",
        },
        "stoichiometric_yields": {"intermediate": 1.5, "product": 3.0},
        "time_grid": {"start": 0.0, "stop": 400.0, "points": 81, "units": "second"},
        "observable_roles": [
            "substrate",
            "intermediate",
            "product",
            "surface_catalyst",
            "homogeneous_catalyst",
        ],
        "output_state_roles": {
            "substrate": "polymer_x_pool",
            "intermediate": "oligomer_y_pool",
            "product": "monomer_z_pool",
            "surface_catalyst": "catalyst_alpha_pool",
            "homogeneous_catalyst": "catalyst_beta_pool",
        },
        "process_state_metadata": {
            "config_name": "BIO-002 generic polymer X chain fixture",
            "config_mode": "toy",
            "config_maturity": "framework_benchmark",
            "public_path": False,
            "entities": _generic_chain_entities(),
            "parameter_record_ids": {
                "x_initial": "fixture_x_initial_concentration",
                "alpha_initial": "fixture_alpha_initial_concentration",
                "beta_initial": "fixture_beta_initial_concentration",
                "surface_rate_constant": "fixture_x_to_y_surface_rate",
                "adsorption_constant": "fixture_alpha_adsorption_constant",
                "accessible_surface_area": "fixture_x_accessible_surface_area",
                "km": "fixture_y_to_z_km",
                "kcat": "fixture_y_to_z_kcat",
            },
            "product_maps": [
                {
                    "id": "x_to_y_fixture_map",
                    "name": "Fixture X to Y stoichiometric map",
                    "product_map_type": "stoichiometric",
                    "reactants": {"substrate": 1.0},
                    "products": {"intermediate": 1.5},
                    "notes": "Artificial 1.5 yield fixture.",
                },
                {
                    "id": "y_to_z_fixture_map",
                    "name": "Fixture Y to Z stoichiometric map",
                    "product_map_type": "stoichiometric",
                    "reactants": {"intermediate": 1.0},
                    "products": {"product": 3.0},
                    "notes": "Artificial 3.0 yield fixture.",
                },
            ],
            "process_templates": [
                {
                    "id": "x_surface_to_y_fixture",
                    "process_type": "surface_catalysis",
                    "state_roles": {
                        "substrate": "substrate",
                        "catalyst": "surface_catalyst",
                        "product": "intermediate",
                    },
                    "fixed_states": {
                        "bond_type": "fixture_linkage_x",
                        "accessible_site_pool": "fixture X accessible sites",
                    },
                    "parameter_roles": {
                        "surface_rate_constant": "surface_rate_constant",
                        "adsorption_constant": "adsorption_constant",
                        "accessible_surface_area": "accessible_surface_area",
                    },
                    "fixed_parameters": {"rate_units": "mM / second"},
                    "product_map": "x_to_y_fixture_map",
                    "assumptions": ["Artificial surface step fixture."],
                },
                {
                    "id": "y_to_z_homogeneous_fixture",
                    "process_type": "homogeneous_michaelis_menten",
                    "state_roles": {
                        "substrate": "intermediate",
                        "product": "product",
                        "enzyme": "homogeneous_catalyst",
                    },
                    "parameter_roles": {"km": "km", "kcat": "kcat"},
                    "fixed_parameters": {"rate_units": "mM / second"},
                    "product_map": "y_to_z_fixture_map",
                    "assumptions": ["Artificial homogeneous step fixture."],
                },
            ],
            "conservation": {
                "id": "x_equivalent_balance",
                "closed_system": True,
                "state_weights": {
                    "substrate": 1.0,
                    "intermediate": 2.0 / 3.0,
                    "product": 2.0 / 9.0,
                },
            },
            "chain_outputs": {
                "state_series": [
                    {"role": "substrate", "label": "polymer_x_remaining"},
                    {"role": "intermediate", "label": "oligomer_y_amount"},
                    {"role": "product", "label": "monomer_z_amount"},
                    {"role": "surface_catalyst", "label": "alpha_catalyst_amount"},
                    {"role": "homogeneous_catalyst", "label": "beta_catalyst_amount"},
                ],
                "derived_series": [
                    {
                        "id": "x_depletion",
                        "kind": "fractional_depletion",
                        "role": "substrate",
                        "label": "x_pool_depleted_fraction",
                        "units": "dimensionless",
                        "threshold_fractions": [0.1],
                    },
                    {
                        "id": "z_yield",
                        "kind": "conserved_equivalent_fraction",
                        "role": "product",
                        "denominator_role": "substrate",
                        "label": "z_equivalent_yield_curve",
                        "units": "dimensionless",
                    },
                ],
                "final_metrics": [
                    {
                        "id": "final_x_depletion",
                        "kind": "final_derived",
                        "derived_series": "x_depletion",
                        "label": "x_pool_depleted_fraction",
                    },
                    {
                        "id": "final_z_yield",
                        "kind": "final_derived",
                        "derived_series": "z_yield",
                        "label": "z_equivalent_yield",
                    },
                ],
                "process_rate_metrics": {"include_maximum": True},
            },
            "suggested_experiments": [
                {
                    "id": "fixture_chain_timecourse",
                    "priority": "testing",
                    "description": "Artificial fixture time course.",
                    "rationale": "Software verification only.",
                }
            ],
        },
        "limitations": [
            "Artificial generic chain fixture only.",
            "No organism-specific process code or empirical biology is represented.",
        ],
        "validity_notes": ["Software-test fixture; not a scientific data record."],
        "notes": "Artificial BIO-002 generic chain assembly fixture.",
    }


def _generic_chain_entities() -> dict[str, Any]:
    return {
        "geometry": {
            "id": "fixture_geometry",
            "loader": "well_mixed",
            "data": {
                "kind": "geometry",
                "name": "Fixture well-mixed chain geometry",
                "geometry_type": "well_mixed",
                "provenance": {
                    "source": "BIO-002 genericity test fixture",
                    "confidence_level": "testing",
                    "notes": "Artificial geometry fixture.",
                },
                "volume": {"value": 50.0, "units": "milliliter"},
                "surface_area": {"value": 1.0, "units": "meter ** 2"},
                "parameters": [],
            },
        },
        "substrates": [
            {
                "id": "polymer_x_fixture",
                "loader": "generic_solid",
                "data": {
                    "kind": "substrate",
                    "name": "Generic polymer X fixture",
                    "substrate_type": "generic_solid",
                    "chemical_class": "polymer_x_fixture",
                    "physical_state": "solid_polymer",
                    "bond_types": ["fixture_linkage_x"],
                    "accessible_bonds": ["fixture_linkage_x"],
                    "required_enzyme_classes": ["catalyst_alpha_fixture"],
                    "degradation_products": [
                        {
                            "name": "oligomer Y fixture",
                            "source": "BIO-002 genericity test fixture",
                            "notes": "Artificial intermediate fixture.",
                        }
                    ],
                    "completeness": "partial",
                    "default_degradation_model": "heterogeneous_surface",
                    "water_activity_dependence": "unknown",
                    "provenance": {
                        "source": "BIO-002 genericity test fixture",
                        "confidence_level": "testing",
                        "notes": "Artificial substrate fixture.",
                    },
                    "parameters": [],
                },
            }
        ],
        "enzymes": [
            {
                "id": "catalyst_alpha_fixture",
                "data": {
                    "kind": "enzyme",
                    "name": "Catalyst alpha fixture",
                    "enzyme_class": "catalyst_alpha_fixture",
                    "target_bond_types": ["fixture_linkage_x"],
                    "target_substrate_classes": ["polymer_x_fixture"],
                    "target_substrate_names": ["Generic polymer X fixture"],
                    "validity_labels": ["BIO-002", "testing"],
                    "provenance": {
                        "source": "BIO-002 genericity test fixture",
                        "confidence_level": "testing",
                        "notes": "Artificial catalyst fixture.",
                    },
                    "catalytic_parameters": [],
                    "adsorption_parameters": [],
                    "parameters": [],
                },
            },
            {
                "id": "catalyst_beta_fixture",
                "data": {
                    "kind": "enzyme",
                    "name": "Catalyst beta fixture",
                    "enzyme_class": "catalyst_beta_fixture",
                    "target_bond_types": ["fixture_linkage_y"],
                    "target_substrate_classes": ["oligomer_y_fixture"],
                    "target_substrate_names": ["Oligomer Y fixture"],
                    "validity_labels": ["BIO-002", "testing"],
                    "provenance": {
                        "source": "BIO-002 genericity test fixture",
                        "confidence_level": "testing",
                        "notes": "Artificial catalyst fixture.",
                    },
                    "catalytic_parameters": [],
                    "adsorption_parameters": [],
                    "parameters": [],
                },
            },
        ],
    }


def _generic_chain_parameters() -> list[dict[str, Any]]:
    return [
        _parameter("fixture_x_initial_concentration", "X_initial", "extracellular_enzyme_chain", 6.0, "mM"),
        _parameter("fixture_alpha_initial_concentration", "E_alpha_initial", "extracellular_enzyme_chain", 1.0, "mM"),
        _parameter("fixture_beta_initial_concentration", "E_beta_initial", "extracellular_enzyme_chain", 0.5, "mM"),
        _parameter("fixture_x_to_y_surface_rate", "k_surface_x_to_y", "surface_catalysis", 0.01, "mM / meter ** 2 / second"),
        _parameter("fixture_alpha_adsorption_constant", "K_ads_alpha", "surface_catalysis", 1.0, "1 / mM"),
        _parameter("fixture_x_accessible_surface_area", "A_x_accessible", "surface_catalysis", 1.0, "meter ** 2"),
        _parameter("fixture_y_to_z_km", "Km_y", "homogeneous_michaelis_menten", 0.8, "mM"),
        _parameter("fixture_y_to_z_kcat", "kcat_y_to_z", "homogeneous_michaelis_menten", 0.04, "1 / second"),
    ]


def _parameter(record_id: str, symbol: str, process_type: str, value: float, units: str) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": f"Fixture parameter {symbol}",
        "maturity": "toy_development",
        "provenance": {
            "source": "BIO-002 genericity test fixture",
            "confidence_level": "testing",
            "notes": "Artificial exact parameter for generic chain tests only.",
        },
        "parameter_symbol": symbol,
        "process_type": process_type,
        "enzyme_class": None,
        "substrate_class": None,
        "fungus_id": None,
        "substrate_id": None,
        "environment_id": None,
        "value": {
            "kind": "exact",
            "value": value,
            "units": units,
            "source": "BIO-002 genericity test fixture",
            "confidence_level": "testing",
            "notes": "Artificial exact parameter for generic chain tests only.",
        },
        "notes": "Artificial parameter for generic chain software tests only.",
    }


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
