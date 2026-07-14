from __future__ import annotations

import csv
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, cast

import numpy as np
import pytest
import yaml

from fungal_model import VirtualExperiment
from fungal_model.api import VirtualExperimentError
from fungal_model.registry import RegistryValidationError, load_registry
from fungal_model.screening import (
    EnzymeChainAssemblyError,
    RegistryCaseBuildError,
    assess_modelability,
    build_extracellular_enzyme_chain_config,
    build_model_config_from_registry_case,
    write_enzyme_chain_standard_tables,
)
from fungal_model.workflows import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
GENERIC_TEMPLATE_ID = "bio002_polymer_x_oligomer_y_monomer_z_template"
GENERIC_FUNGUS_ID = "fixture_chain_enzyme_source"
GENERIC_SUBSTRATE_ID = "polymer_x_fixture"
GENERIC_ENVIRONMENT_ID = "toy_lab_environment"


def test_artificial_three_step_chain_assembles_runs_and_writes_tables(tmp_path: Path) -> None:
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
        "homogeneous_michaelis_menten",
    ]
    assert [process.id for process in config.processes] == [
        "x_surface_to_y_fixture",
        "y_to_q_homogeneous_fixture",
        "q_to_z_homogeneous_fixture",
    ]
    config_data = config.to_dict()
    assert config_data["case_template"]["chain_topology"] == {
        "topology_type": "linear",
        "process_ids": [
            "x_surface_to_y_fixture",
            "y_to_q_homogeneous_fixture",
            "q_to_z_homogeneous_fixture",
        ],
        "product_map_ids": ["x_to_y_fixture_map", "y_to_q_fixture_map", "q_to_z_fixture_map"],
        "state_roles": ["substrate", "intermediate_1", "intermediate_2", "product"],
        "state_names": ["polymer_x_pool", "oligomer_y_pool", "fragment_q_pool", "monomer_z_pool"],
        "branching_supported": False,
        "cycles_supported": False,
    }
    assert config_data["processes"][0]["modifiers"] == []
    assert config_data["processes"][1]["modifiers"] == []
    assert config_data["processes"][2]["modifiers"] == [
        {
            "type": "product_inhibition",
            "product_state": "monomer_z_pool",
            "inhibition_constant": "K_i_z_fixture",
        }
    ]
    product_maps = {reference.id: reference.data for reference in config.entities.product_maps}
    assert product_maps["x_to_y_fixture_map"]["products"] == {"oligomer_y_pool": 1.5}
    assert product_maps["y_to_q_fixture_map"]["products"] == {"fragment_q_pool": 2.0}
    assert product_maps["q_to_z_fixture_map"]["products"] == {"monomer_z_pool": 3.0}

    polymer = result.state("polymer_x_pool").to("mM").magnitude
    oligomer = result.state("oligomer_y_pool").to("mM").magnitude
    fragment = result.state("fragment_q_pool").to("mM").magnitude
    monomer = result.state("monomer_z_pool").to("mM").magnitude
    conserved = polymer + (2.0 / 3.0) * oligomer + (1.0 / 3.0) * fragment + (1.0 / 9.0) * monomer

    assert result.solver_metadata["success"] is True
    assert polymer[-1] < polymer[0]
    assert np.max(oligomer) > oligomer[0]
    assert np.max(fragment) > fragment[0]
    assert monomer[-1] > monomer[0]
    assert conserved[-1] == pytest.approx(conserved[0], rel=1.0e-6, abs=1.0e-6)
    assert set(result.process_rates) == {
        "x_surface_to_y_fixture",
        "y_to_q_homogeneous_fixture",
        "q_to_z_homogeneous_fixture",
    }

    for path in tables.values():
        assert Path(path).exists()
    final_metrics = _csv_rows(Path(tables["final_metrics"]))
    time_series = _csv_rows(Path(tables["time_series_long"]))
    thresholds = _csv_rows(Path(tables["threshold_times"]))
    metrics = {row["metric"] for row in final_metrics}
    series_names = {row["state"] for row in time_series}

    assert "z_equivalent_yield" in metrics
    assert "x_pool_depleted_fraction" in metrics
    assert {"polymer_x_remaining", "oligomer_y_amount", "fragment_q_amount", "monomer_z_amount"}.issubset(
        series_names
    )
    assert "final_glucose_yield" not in metrics
    assert "glucose_yield" not in series_names
    assert {row["metric"] for row in thresholds} == {"x_pool_depleted_fraction"}


def test_artificial_chain_rejects_coherent_whole_component_role_group_swap(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    _insert_generic_chain_fixture(registry_dir)
    _coherently_swap_generic_second_component(registry_dir)
    with pytest.raises(RegistryValidationError, match="process_type does not match"):
        load_registry(registry_dir / "registry_index.yml")


@pytest.mark.parametrize(
    ("component_id", "old_role", "new_role", "message"),
    [
        (
            "fixture_y_to_q_component",
            "enzyme_initial_concentration",
            "unrelated_initial_role",
            "exact component compatibility role 'enzyme_initial_concentration'",
        ),
        (
            "fixture_q_to_z_component",
            "inhibition_constant",
            "unrelated_modifier_role",
            "exact component compatibility role 'inhibition_constant'",
        ),
    ],
)
def test_artificial_three_step_semantic_role_rewrite_is_rejected_by_every_path(
    tmp_path: Path,
    component_id: str,
    old_role: str,
    new_role: str,
    message: str,
) -> None:
    valid_dir = _copy_registry(tmp_path / "valid")
    _insert_generic_chain_fixture(valid_dir)
    valid_study = VirtualExperiment.from_registry(
        fungi=GENERIC_FUNGUS_ID,
        substrates=GENERIC_SUBSTRATE_ID,
        environments=GENERIC_ENVIRONMENT_ID,
        registry=valid_dir / "registry_index.yml",
    )
    assert valid_study.preflight(mode="exploratory")[0].status == "modelable"
    valid_result = valid_study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=19,
        output_dir=tmp_path / "valid_result",
        quicklook=False,
    )
    _rename_component_role_in_memory(
        valid_study.registry,
        component_id=component_id,
        old_role=old_role,
        new_role=new_role,
    )
    with pytest.raises(RegistryCaseBuildError, match=message):
        valid_result.write_tables(tmp_path / "rewritten_tables")

    drifted_dir = _copy_registry(tmp_path / "drifted")
    _insert_generic_chain_fixture(drifted_dir)
    _rename_component_role_in_file(
        drifted_dir,
        component_id=component_id,
        old_role=old_role,
        new_role=new_role,
    )
    registry = load_registry(drifted_dir / "registry_index.yml")
    report = assess_modelability(
        fungus_id=GENERIC_FUNGUS_ID,
        substrate_id=GENERIC_SUBSTRATE_ID,
        environment_id=GENERIC_ENVIRONMENT_ID,
        registry=registry,
        mode="exploratory",
    )
    assert report.status == "underparameterized"
    assert any(message in item.message for item in report.incompatible)

    study = VirtualExperiment.from_registry(
        fungi=GENERIC_FUNGUS_ID,
        substrates=GENERIC_SUBSTRATE_ID,
        environments=GENERIC_ENVIRONMENT_ID,
        registry=drifted_dir / "registry_index.yml",
    )
    with pytest.raises(VirtualExperimentError, match=message):
        study.simulate(
            mode="exploratory",
            n_samples=1,
            output_dir=tmp_path / "blocked_runtime",
            quicklook=False,
        )
    with pytest.raises(RegistryCaseBuildError, match="modelability status"):
        build_model_config_from_registry_case(
            fungus_id=GENERIC_FUNGUS_ID,
            substrate_id=GENERIC_SUBSTRATE_ID,
            environment_id=GENERIC_ENVIRONMENT_ID,
            registry=registry,
            mode="toy",
        )
    with pytest.raises(EnzymeChainAssemblyError, match=message):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            template_id=GENERIC_TEMPLATE_ID,
            environment_id=GENERIC_ENVIRONMENT_ID,
        )


def test_linear_chain_requires_at_least_two_processes(tmp_path: Path) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"].update(
            {"process_templates": template["process_state_metadata"]["process_templates"][:1]}
        ),
    )
    process_path = registry_dir / "processes" / "process_compatibility.yml"
    process_payload = _yaml_mapping(process_path)
    outer = next(
        record
        for record in cast(list[dict[str, Any]], process_payload["records"])
        if record["record_id"] == "fixture_three_step_chain_compatibility"
    )
    outer["component_bindings"] = outer["component_bindings"][:1]
    for component_id in (
        "fixture_y_to_q_component",
        "fixture_q_to_z_component",
    ):
        process_payload["records"] = [
            record
            for record in cast(list[dict[str, Any]], process_payload["records"])
            if record["record_id"] != component_id
        ]
    process_path.write_text(
        yaml.safe_dump(process_payload, sort_keys=False),
        encoding="utf-8",
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="at least two ordered process_templates"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_linear_chain_rejects_process_product_map_count_mismatch(tmp_path: Path) -> None:
    def add_disconnected_map(template: dict[str, Any]) -> None:
        template["process_state_metadata"]["product_maps"].append(
            {
                "id": "disconnected_fixture_map",
                "name": "Disconnected artificial fixture map",
                "product_map_type": "stoichiometric",
                "reactants": {"intermediate_1": 1.0},
                "products": {"product": 1.0},
                "notes": "Malformed topology fixture only.",
            }
        )

    registry_dir = _registry_with_modified_chain(tmp_path, add_disconnected_map)
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="exactly one product map per process template"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_linear_chain_rejects_disconnected_ordered_steps(tmp_path: Path) -> None:
    def disconnect_second_step(template: dict[str, Any]) -> None:
        metadata = template["process_state_metadata"]
        metadata["product_maps"][1]["reactants"] = {"substrate": 1.0}
        metadata["process_templates"][1]["state_roles"]["substrate"] = "substrate"

    registry_dir = _registry_with_modified_chain(tmp_path, disconnect_second_step)
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="disconnected or non-linear"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_linear_chain_rejects_branching_product_map(tmp_path: Path) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"]["product_maps"][0]["products"].update(
            {"intermediate_2": 1.0}
        ),
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="branching is unsupported"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_linear_chain_rejects_cycles(tmp_path: Path) -> None:
    def introduce_cycle(template: dict[str, Any]) -> None:
        metadata = template["process_state_metadata"]
        metadata["product_maps"][1]["products"] = {"substrate": 1.0}
        metadata["process_templates"][1]["state_roles"]["product"] = "substrate"
        metadata["product_maps"][2]["reactants"] = {"substrate": 1.0}
        metadata["process_templates"][2]["state_roles"]["substrate"] = "substrate"

    registry_dir = _registry_with_modified_chain(tmp_path, introduce_cycle)
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="cycle or repeated state"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


def test_linear_chain_rejects_process_map_role_mismatch(tmp_path: Path) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"]["process_templates"][1]["state_roles"].update(
            {"product": "product"}
        ),
    )
    registry = load_registry(registry_dir / "registry_index.yml")

    with pytest.raises(EnzymeChainAssemblyError, match="state-role mapping does not match product map"):
        build_extracellular_enzyme_chain_config(registry=registry, template_id=GENERIC_TEMPLATE_ID)


@pytest.mark.parametrize("bad_coefficient", [0.0, -1.0, float("nan"), float("inf")])
def test_chain_product_maps_reject_non_positive_or_non_finite_coefficients(
    tmp_path: Path,
    bad_coefficient: float,
) -> None:
    registry_dir = _registry_with_modified_chain(
        tmp_path,
        lambda template: template["process_state_metadata"]["product_maps"][0]["products"].update(
            {"intermediate_1": bad_coefficient}
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
        lambda template: template["process_state_metadata"]["product_maps"][0].update(
            {"products": {"unknown": 1.5}}
        ),
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

    enzyme_path = registry_dir / "enzymes" / "enzyme_classes.yml"
    enzyme_data = _yaml_mapping(enzyme_path)
    cast(list[dict[str, Any]], enzyme_data["records"])[0:0] = _generic_enzyme_classes()
    enzyme_path.write_text(yaml.safe_dump(enzyme_data, sort_keys=False), encoding="utf-8")

    substrate_path = registry_dir / "substrates" / "substrates.yml"
    substrate_data = _yaml_mapping(substrate_path)
    cast(list[dict[str, Any]], substrate_data["records"])[0:0] = _generic_substrates()
    substrate_path.write_text(yaml.safe_dump(substrate_data, sort_keys=False), encoding="utf-8")

    fungus_path = registry_dir / "fungi" / "fungi.yml"
    fungus_data = _yaml_mapping(fungus_path)
    cast(list[dict[str, Any]], fungus_data["records"]).insert(
        0,
        {
            "record_id": GENERIC_FUNGUS_ID,
            "name": "Artificial three-step chain enzyme source",
            "maturity": "toy_development",
            "provenance": {
                "source": "BIO-002 genericity test fixture",
                "confidence_level": "testing",
                "notes": "Artificial source identity for software tests only.",
            },
            "enzyme_classes": ["catalyst_alpha_fixture"],
            "assimilable_products": ["monomer_z_fixture"],
            "notes": "Artificial enzyme-source fixture; not biological evidence.",
        },
    )
    fungus_path.write_text(yaml.safe_dump(fungus_data, sort_keys=False), encoding="utf-8")

    compatibility_path = registry_dir / "processes" / "process_compatibility.yml"
    compatibility_data = _yaml_mapping(compatibility_path)
    cast(list[dict[str, Any]], compatibility_data["records"])[0:0] = (
        _generic_process_compatibilities()
    )
    compatibility_path.write_text(
        yaml.safe_dump(compatibility_data, sort_keys=False),
        encoding="utf-8",
    )


def _generic_chain_template() -> dict[str, Any]:
    return {
        "record_id": GENERIC_TEMPLATE_ID,
        "case_template_id": GENERIC_TEMPLATE_ID,
        "name": "Artificial polymer X to monomer Z three-step chain fixture",
        "maturity": "toy_development",
        "provenance": {
            "source": "BIO-002 genericity test fixture",
            "confidence_level": "testing",
            "bio_milestone": "BIO-002",
            "notes": "Artificial framework benchmark proving arbitrary-length linear assembly is data-driven.",
        },
        "schema_version": "1",
        "process_type": "extracellular_enzyme_chain",
        "state_roles": {
            "substrate": "polymer_x_pool",
            "intermediate": "oligomer_y_pool",
            "intermediate_1": "oligomer_y_pool",
            "intermediate_2": "fragment_q_pool",
            "product": "monomer_z_pool",
            "surface_catalyst": "catalyst_alpha_pool",
            "homogeneous_catalyst": "catalyst_beta_pool",
            "catalyst_3": "catalyst_gamma_pool",
        },
        "initial_state_mapping": {
            "substrate": {"parameter_role": "x_initial", "units_from_role": "x_initial"},
            "intermediate": {"value": 0.0, "units": "mM"},
            "intermediate_1": {"value": 0.0, "units": "mM"},
            "intermediate_2": {"value": 0.0, "units": "mM"},
            "product": {"value": 0.0, "units": "mM"},
            "surface_catalyst": {"parameter_role": "alpha_initial", "units_from_role": "alpha_initial"},
            "homogeneous_catalyst": {"parameter_role": "beta_initial", "units_from_role": "beta_initial"},
            "catalyst_3": {"parameter_role": "gamma_initial", "units_from_role": "gamma_initial"},
        },
        "product_map": {
            "id": "q_to_z_fixture_map",
            "product_map_type": "stoichiometric",
            "substrate_state_role": "intermediate_2",
            "product_state_role": "product",
            "stoichiometric_yield": 3.0,
            "notes": "Legacy summary field kept consistent with the chain map.",
        },
        "stoichiometric_yields": {"intermediate_1": 1.5, "intermediate_2": 2.0, "product": 3.0},
        "time_grid": {"start": 0.0, "stop": 400.0, "points": 81, "units": "second"},
        "observable_roles": [
            "substrate",
            "intermediate_1",
            "intermediate_2",
            "product",
            "surface_catalyst",
            "homogeneous_catalyst",
            "catalyst_3",
        ],
        "output_state_roles": {
            "substrate": "polymer_x_pool",
            "intermediate_1": "oligomer_y_pool",
            "intermediate_2": "fragment_q_pool",
            "product": "monomer_z_pool",
            "surface_catalyst": "catalyst_alpha_pool",
            "homogeneous_catalyst": "catalyst_beta_pool",
            "catalyst_3": "catalyst_gamma_pool",
        },
        "process_state_metadata": {
            "config_name": "Artificial three-step linear chain framework benchmark",
            "config_mode": "toy",
            "config_maturity": "framework_benchmark",
            "public_path": False,
            "entities": _generic_chain_entities(),
            "state_species": {
                "polymer_x_pool": {
                    "species": "polymer_x_fixture",
                    "entity_type": "substrate",
                },
                "oligomer_y_pool": {
                    "species": "oligomer_y_fixture",
                    "entity_type": "substrate",
                },
                "fragment_q_pool": {
                    "species": "fragment_q_fixture",
                    "entity_type": "substrate",
                },
                "catalyst_alpha_pool": {
                    "species": "catalyst_alpha_fixture",
                    "entity_type": "enzyme",
                },
                "catalyst_beta_pool": {
                    "species": "catalyst_beta_fixture",
                    "entity_type": "enzyme",
                },
                "catalyst_gamma_pool": {
                    "species": "catalyst_gamma_fixture",
                    "entity_type": "enzyme",
                },
            },
            "parameter_record_ids": {
                "x_initial": "fixture_x_initial_concentration",
                "alpha_initial": "fixture_alpha_initial_concentration",
                "beta_initial": "fixture_beta_initial_concentration",
                "gamma_initial": "fixture_gamma_initial_concentration",
                "surface_rate_constant": "fixture_x_to_y_surface_rate",
                "adsorption_constant": "fixture_alpha_adsorption_constant",
                "accessible_surface_area": "fixture_x_accessible_surface_area",
                "km_y_to_q": "fixture_y_to_q_km",
                "kcat_y_to_q": "fixture_y_to_q_kcat",
                "km_q_to_z": "fixture_q_to_z_km",
                "kcat_q_to_z": "fixture_q_to_z_kcat",
                "terminal_inhibition_constant": "fixture_z_inhibition_constant",
            },
            "parameter_role_contracts": _generic_parameter_role_contracts(),
            "product_maps": [
                {
                    "id": "x_to_y_fixture_map",
                    "name": "Fixture X to Y stoichiometric map",
                    "product_map_type": "stoichiometric",
                    "reactants": {"substrate": 1.0},
                    "products": {"intermediate_1": 1.5},
                    "notes": "Artificial 1.5 yield fixture.",
                },
                {
                    "id": "y_to_q_fixture_map",
                    "name": "Fixture Y to Q stoichiometric map",
                    "product_map_type": "stoichiometric",
                    "reactants": {"intermediate_1": 1.0},
                    "products": {"intermediate_2": 2.0},
                    "notes": "Artificial 2.0 yield framework fixture.",
                },
                {
                    "id": "q_to_z_fixture_map",
                    "name": "Fixture Q to Z stoichiometric map",
                    "product_map_type": "stoichiometric",
                    "reactants": {"intermediate_2": 1.0},
                    "products": {"product": 3.0},
                    "notes": "Artificial 3.0 yield framework fixture.",
                },
            ],
            "process_templates": [
                {
                    "id": "x_surface_to_y_fixture",
                    "process_type": "surface_catalysis",
                    "state_roles": {
                        "substrate": "substrate",
                        "catalyst": "surface_catalyst",
                        "product": "intermediate_1",
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
                    "id": "y_to_q_homogeneous_fixture",
                    "process_type": "homogeneous_michaelis_menten",
                    "state_roles": {
                        "substrate": "intermediate_1",
                        "product": "intermediate_2",
                        "enzyme": "homogeneous_catalyst",
                    },
                    "parameter_roles": {"km": "km_y_to_q", "kcat": "kcat_y_to_q"},
                    "fixed_parameters": {"rate_units": "mM / second"},
                    "product_map": "y_to_q_fixture_map",
                    "assumptions": ["Artificial homogeneous step fixture."],
                },
                {
                    "id": "q_to_z_homogeneous_fixture",
                    "process_type": "homogeneous_michaelis_menten",
                    "state_roles": {
                        "substrate": "intermediate_2",
                        "product": "product",
                        "enzyme": "catalyst_3",
                    },
                    "parameter_roles": {"km": "km_q_to_z", "kcat": "kcat_q_to_z"},
                    "fixed_parameters": {"rate_units": "mM / second"},
                    "product_map": "q_to_z_fixture_map",
                    "modifiers": [
                        {
                            "type": "product_inhibition",
                            "product_state_role": "product",
                            "inhibition_constant_role": "terminal_inhibition_constant",
                        }
                    ],
                    "assumptions": ["Artificial terminal homogeneous step fixture."],
                },
            ],
            "conservation": {
                "id": "x_equivalent_balance",
                "closed_system": True,
                "state_weights": {
                    "substrate": 1.0,
                    "intermediate_1": 2.0 / 3.0,
                    "intermediate_2": 1.0 / 3.0,
                    "product": 1.0 / 9.0,
                },
            },
            "chain_outputs": {
                "state_series": [
                    {"role": "substrate", "label": "polymer_x_remaining"},
                    {"role": "intermediate_1", "label": "oligomer_y_amount"},
                    {"role": "intermediate_2", "label": "fragment_q_amount"},
                    {"role": "product", "label": "monomer_z_amount"},
                    {"role": "surface_catalyst", "label": "alpha_catalyst_amount"},
                    {"role": "homogeneous_catalyst", "label": "beta_catalyst_amount"},
                    {"role": "catalyst_3", "label": "gamma_catalyst_amount"},
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
            "Artificial three-step linear chain framework fixture only.",
            "No organism-specific process code or empirical biology is represented.",
        ],
        "validity_notes": ["Software-test fixture; not a scientific data record."],
        "notes": "Artificial arbitrary-length linear chain assembly fixture; not scientific or validation data.",
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
            {
                "id": "catalyst_gamma_fixture",
                "data": {
                    "kind": "enzyme",
                    "name": "Catalyst gamma fixture",
                    "enzyme_class": "catalyst_gamma_fixture",
                    "target_bond_types": ["fixture_linkage_q"],
                    "target_substrate_classes": ["fragment_q_fixture"],
                    "target_substrate_names": ["Fragment Q fixture"],
                    "validity_labels": ["framework_benchmark", "testing"],
                    "provenance": {
                        "source": "Artificial three-step chain framework fixture",
                        "confidence_level": "testing",
                        "notes": "Artificial terminal catalyst fixture; not scientific evidence.",
                    },
                    "catalytic_parameters": [],
                    "adsorption_parameters": [],
                    "parameters": [],
                },
            },
        ],
    }


def _generic_enzyme_classes() -> list[dict[str, Any]]:
    return [
        _generic_enzyme_class(
            record_id="catalyst_alpha_fixture",
            substrate_class="polymer_x_fixture",
            bond_class="fixture_linkage_x",
            process_type="surface_catalysis",
            additional_process_types=("extracellular_enzyme_chain",),
        ),
        _generic_enzyme_class(
            record_id="catalyst_beta_fixture",
            substrate_class="oligomer_y_fixture",
            bond_class="fixture_linkage_y",
            process_type="homogeneous_michaelis_menten",
        ),
        _generic_enzyme_class(
            record_id="catalyst_gamma_fixture",
            substrate_class="fragment_q_fixture",
            bond_class="fixture_linkage_q",
            process_type="homogeneous_michaelis_menten",
        ),
    ]


def _generic_enzyme_class(
    *,
    record_id: str,
    substrate_class: str,
    bond_class: str,
    process_type: str,
    additional_process_types: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": f"Artificial enzyme class {record_id}",
        "maturity": "toy_development",
        "provenance": {
            "source": "BIO-002 genericity test fixture",
            "confidence_level": "testing",
            "notes": "Artificial capability metadata for software tests only.",
        },
        "target_bond_classes": [bond_class],
        "compatible_substrate_classes": [substrate_class],
        "compatible_processes": [process_type, *additional_process_types],
        "notes": "Artificial enzyme capability; not scientific evidence.",
    }


def _generic_substrates() -> list[dict[str, Any]]:
    return [
        _generic_substrate(
            record_id="polymer_x_fixture",
            bond_class="fixture_linkage_x",
            product="oligomer_y_fixture",
        ),
        _generic_substrate(
            record_id="oligomer_y_fixture",
            bond_class="fixture_linkage_y",
            product="fragment_q_fixture",
        ),
        _generic_substrate(
            record_id="fragment_q_fixture",
            bond_class="fixture_linkage_q",
            product="monomer_z_fixture",
        ),
    ]


def _generic_substrate(
    *,
    record_id: str,
    bond_class: str,
    product: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": f"Artificial substrate {record_id}",
        "maturity": "toy_development",
        "provenance": {
            "source": "BIO-002 genericity test fixture",
            "confidence_level": "testing",
            "notes": "Artificial substrate identity for software tests only.",
        },
        "substrate_class": record_id,
        "physical_state": "artificial_fixture",
        "bond_classes": [bond_class],
        "products": [product],
        "properties": {},
        "notes": "Artificial substrate record; not scientific evidence.",
    }


def _generic_process_compatibilities() -> list[dict[str, Any]]:
    specs = _generic_parameter_specs()
    symbols = {role: spec["symbol"] for role, spec in specs.items()}
    return [
        _generic_compatibility(
            record_id="fixture_three_step_chain_compatibility",
            enzyme_class="catalyst_alpha_fixture",
            substrate_class="polymer_x_fixture",
            bond_class="fixture_linkage_x",
            process_type="extracellular_enzyme_chain",
            parameter_roles=symbols,
            case_template_id=GENERIC_TEMPLATE_ID,
            component_bindings=[
                {
                    "process_template_id": "x_surface_to_y_fixture",
                    "compatibility_record_id": "fixture_x_surface_component",
                },
                {
                    "process_template_id": "y_to_q_homogeneous_fixture",
                    "compatibility_record_id": "fixture_y_to_q_component",
                },
                {
                    "process_template_id": "q_to_z_homogeneous_fixture",
                    "compatibility_record_id": "fixture_q_to_z_component",
                },
            ],
        ),
        _generic_compatibility(
            record_id="fixture_x_surface_standalone_compatibility",
            enzyme_class="catalyst_alpha_fixture",
            substrate_class="polymer_x_fixture",
            bond_class="fixture_linkage_x",
            process_type="surface_catalysis",
            parameter_roles={
                "substrate_initial_amount": symbols["x_initial"],
                "enzyme_initial_concentration": symbols["alpha_initial"],
                "surface_rate_constant": symbols["surface_rate_constant"],
                "adsorption_constant": symbols["adsorption_constant"],
                "accessible_surface_area": symbols["accessible_surface_area"],
            },
            component_only=False,
        ),
        _generic_compatibility(
            record_id="fixture_x_surface_component",
            enzyme_class="catalyst_alpha_fixture",
            substrate_class="polymer_x_fixture",
            bond_class="fixture_linkage_x",
            process_type="surface_catalysis",
            parameter_roles={
                "substrate_initial_amount": symbols["x_initial"],
                "enzyme_initial_concentration": symbols["alpha_initial"],
                "surface_rate_constant": symbols["surface_rate_constant"],
                "adsorption_constant": symbols["adsorption_constant"],
                "accessible_surface_area": symbols["accessible_surface_area"],
            },
        ),
        _generic_compatibility(
            record_id="fixture_y_to_q_component",
            enzyme_class="catalyst_beta_fixture",
            substrate_class="oligomer_y_fixture",
            bond_class="fixture_linkage_y",
            process_type="homogeneous_michaelis_menten",
            parameter_roles={
                "enzyme_initial_concentration": symbols["beta_initial"],
                "km": symbols["km_y_to_q"],
                "kcat": symbols["kcat_y_to_q"],
            },
        ),
        _generic_compatibility(
            record_id="fixture_q_to_z_component",
            enzyme_class="catalyst_gamma_fixture",
            substrate_class="fragment_q_fixture",
            bond_class="fixture_linkage_q",
            process_type="homogeneous_michaelis_menten",
            parameter_roles={
                "enzyme_initial_concentration": symbols["gamma_initial"],
                "km": symbols["km_q_to_z"],
                "kcat": symbols["kcat_q_to_z"],
                "inhibition_constant": symbols["terminal_inhibition_constant"],
            },
        ),
    ]


def _generic_compatibility(
    *,
    record_id: str,
    enzyme_class: str,
    substrate_class: str,
    bond_class: str,
    process_type: str,
    parameter_roles: dict[str, str],
    case_template_id: str | None = None,
    component_bindings: list[dict[str, str]] | None = None,
    component_only: bool = True,
) -> dict[str, Any]:
    record = {
        "record_id": record_id,
        "name": f"Artificial process compatibility {record_id}",
        "maturity": "toy_development",
        "provenance": {
            "source": "BIO-002 genericity test fixture",
            "confidence_level": "testing",
            "notes": "Artificial component compatibility for software tests only.",
        },
        "enzyme_class": enzyme_class,
        "substrate_class": substrate_class,
        "required_bond_classes": [bond_class],
        "process_type": process_type,
        "required_parameters": list(parameter_roles.values()),
        "parameter_roles": parameter_roles,
        "product_map_required": True,
        "notes": "Artificial compatibility record; not scientific evidence.",
    }
    if case_template_id is not None:
        record["case_template_id"] = case_template_id
    elif component_only:
        record["compatibility_scope"] = "component_only"
    if component_bindings is not None:
        record["component_bindings"] = component_bindings
    return record


def _generic_chain_parameters() -> list[dict[str, Any]]:
    return [
        _parameter(**spec)
        for spec in _generic_parameter_specs().values()
    ]


def _generic_parameter_role_contracts() -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for role, spec in _generic_parameter_specs().items():
        contract = {
            "kind": spec["kind"],
            "parameter_symbol": spec["symbol"],
            "enzyme_class": spec["enzyme_class"],
            "substrate_class": spec["substrate_class"],
            "fungus_id": None,
            "substrate_id": None,
            "environment_id": None,
        }
        if spec["kind"] == "initial_state":
            contract["record_process_type"] = spec["process_type"]
        contracts[role] = contract
    return contracts


def _generic_parameter_specs() -> dict[str, dict[str, Any]]:
    return {
        "x_initial": _parameter_spec("fixture_x_initial_concentration", "X_initial", "extracellular_enzyme_chain", 6.0, "mM", None, "polymer_x_fixture", "initial_state"),
        "alpha_initial": _parameter_spec("fixture_alpha_initial_concentration", "E_alpha_initial", "extracellular_enzyme_chain", 1.0, "mM", "catalyst_alpha_fixture", "polymer_x_fixture", "initial_state"),
        "beta_initial": _parameter_spec("fixture_beta_initial_concentration", "E_beta_initial", "extracellular_enzyme_chain", 0.5, "mM", "catalyst_beta_fixture", "oligomer_y_fixture", "initial_state"),
        "gamma_initial": _parameter_spec("fixture_gamma_initial_concentration", "E_gamma_initial", "extracellular_enzyme_chain", 0.4, "mM", "catalyst_gamma_fixture", "fragment_q_fixture", "initial_state"),
        "surface_rate_constant": _parameter_spec("fixture_x_to_y_surface_rate", "k_surface_x_to_y", "surface_catalysis", 0.01, "mM / meter ** 2 / second", "catalyst_alpha_fixture", "polymer_x_fixture", "process_parameter"),
        "adsorption_constant": _parameter_spec("fixture_alpha_adsorption_constant", "K_ads_alpha", "surface_catalysis", 1.0, "1 / mM", "catalyst_alpha_fixture", "polymer_x_fixture", "process_parameter"),
        "accessible_surface_area": _parameter_spec("fixture_x_accessible_surface_area", "A_x_accessible", "surface_catalysis", 1.0, "meter ** 2", "catalyst_alpha_fixture", "polymer_x_fixture", "process_parameter"),
        "km_y_to_q": _parameter_spec("fixture_y_to_q_km", "Km_y_to_q", "homogeneous_michaelis_menten", 0.8, "mM", "catalyst_beta_fixture", "oligomer_y_fixture", "process_parameter"),
        "kcat_y_to_q": _parameter_spec("fixture_y_to_q_kcat", "kcat_y_to_q", "homogeneous_michaelis_menten", 0.04, "1 / second", "catalyst_beta_fixture", "oligomer_y_fixture", "process_parameter"),
        "km_q_to_z": _parameter_spec("fixture_q_to_z_km", "Km_q_to_z", "homogeneous_michaelis_menten", 0.6, "mM", "catalyst_gamma_fixture", "fragment_q_fixture", "process_parameter"),
        "kcat_q_to_z": _parameter_spec("fixture_q_to_z_kcat", "kcat_q_to_z", "homogeneous_michaelis_menten", 0.03, "1 / second", "catalyst_gamma_fixture", "fragment_q_fixture", "process_parameter"),
        "terminal_inhibition_constant": _parameter_spec("fixture_z_inhibition_constant", "K_i_z_fixture", "homogeneous_michaelis_menten", 8.0, "mM", "catalyst_gamma_fixture", "fragment_q_fixture", "process_parameter"),
    }


def _parameter_spec(
    record_id: str,
    symbol: str,
    process_type: str,
    value: float,
    units: str,
    enzyme_class: str | None,
    substrate_class: str,
    kind: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "symbol": symbol,
        "process_type": process_type,
        "value": value,
        "units": units,
        "enzyme_class": enzyme_class,
        "substrate_class": substrate_class,
        "kind": kind,
    }


def _parameter(
    *,
    record_id: str,
    symbol: str,
    process_type: str,
    value: float,
    units: str,
    enzyme_class: str | None,
    substrate_class: str,
    kind: str,
) -> dict[str, Any]:
    del kind
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
        "enzyme_class": enzyme_class,
        "substrate_class": substrate_class,
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


def _coherently_swap_generic_second_component(registry_dir: Path) -> None:
    selectors = {
        "enzyme_class": "catalyst_alpha_fixture",
        "substrate_class": "polymer_x_fixture",
        "fungus_id": None,
        "substrate_id": None,
    }
    role_record_ids = {
        "beta_initial": "fixture_beta_initial_concentration",
        "km_y_to_q": "fixture_y_to_q_km",
        "kcat_y_to_q": "fixture_y_to_q_kcat",
    }

    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    parameter_data = _yaml_mapping(parameter_path)
    records = cast(list[dict[str, Any]], parameter_data["records"])
    for record in records:
        if record["record_id"] in role_record_ids.values():
            record.update(selectors)
    parameter_path.write_text(
        yaml.safe_dump(parameter_data, sort_keys=False),
        encoding="utf-8",
    )

    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_data = _yaml_mapping(template_path)
    templates = cast(list[dict[str, Any]], template_data["records"])
    template = next(
        record for record in templates if record["record_id"] == GENERIC_TEMPLATE_ID
    )
    contracts = cast(
        dict[str, dict[str, Any]],
        template["process_state_metadata"]["parameter_role_contracts"],
    )
    for role in role_record_ids:
        contracts[role].update(selectors)
    metadata = cast(dict[str, Any], template["process_state_metadata"])
    state_species = cast(dict[str, dict[str, Any]], metadata["state_species"])
    state_species["catalyst_beta_pool"]["species"] = "catalyst_alpha_fixture"
    state_species["oligomer_y_pool"]["species"] = "polymer_x_fixture"
    template_path.write_text(
        yaml.safe_dump(template_data, sort_keys=False),
        encoding="utf-8",
    )

    compatibility_path = registry_dir / "processes" / "process_compatibility.yml"
    compatibility_data = _yaml_mapping(compatibility_path)
    compatibility_records = cast(list[dict[str, Any]], compatibility_data["records"])
    component = next(
        record
        for record in compatibility_records
        if record["record_id"] == "fixture_y_to_q_component"
    )
    component["enzyme_class"] = "catalyst_alpha_fixture"
    component["substrate_class"] = "polymer_x_fixture"
    component["process_type"] = "surface_catalysis"
    compatibility_path.write_text(
        yaml.safe_dump(compatibility_data, sort_keys=False),
        encoding="utf-8",
    )


def _rename_component_role_in_memory(
    registry: Any,
    *,
    component_id: str,
    old_role: str,
    new_role: str,
) -> None:
    component = registry.process_compatibility[component_id]
    roles = dict(component.parameter_roles)
    roles[new_role] = roles.pop(old_role)
    registry.process_compatibility[component_id] = replace(
        component,
        parameter_roles=roles,
    )


def _rename_component_role_in_file(
    registry_dir: Path,
    *,
    component_id: str,
    old_role: str,
    new_role: str,
) -> None:
    path = registry_dir / "processes" / "process_compatibility.yml"
    payload = _yaml_mapping(path)
    component = next(
        record
        for record in cast(list[dict[str, Any]], payload["records"])
        if record["record_id"] == component_id
    )
    roles = cast(dict[str, str], component["parameter_roles"])
    roles[new_role] = roles.pop(old_role)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
