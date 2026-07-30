from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import (
    ProcessComponentBinding,
    RegistryLoadError,
    RegistryLookupError,
    RegistryValidationError,
    ValueSpec,
    load_registry,
    load_registry_record_mapping,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_load_toy_registry_index() -> None:
    registry = load_registry(REGISTRY_INDEX)

    assert registry.registry_id == "toy_registry"
    assert registry.version == "0.1.0"
    assert registry.maturity == "development"
    assert registry.product_maps == {}


def test_product_map_record_loader_never_translates_participant_identity() -> None:
    with pytest.raises(
        RegistryLoadError,
        match="does not translate participant identities",
    ):
        load_registry_record_mapping(
            "product_maps",
            {
                "record_id": "nontext_participant_fixture",
                "name": "Nontext participant fixture",
                "maturity": "synthetic_fixture",
                "provenance": {"source": "Synthetic software fixture."},
                "notes": "Loader rejection fixture only.",
                "product_map_type": "stoichiometric",
                "reactants": {1: 1.0},
                "products": {"product": 1.0},
            },
        )


def test_load_toy_fungus_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    fungus = registry.get_fungus("toy_fungus_alpha")

    assert fungus.name == "Toy fungus alpha"
    assert fungus.enzyme_classes == ("toy_cellulase",)
    assert "not a real fungus" in fungus.notes


def test_load_toy_substrate_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    substrate = registry.get_substrate("toy_cellulose_like_solid")

    assert substrate.substrate_class == "toy_cellulose_like"
    assert substrate.bond_classes == ("toy_beta_1_4_glycosidic",)
    assert isinstance(substrate.properties["accessible_surface_area"], ValueSpec)
    assert substrate.properties["accessible_surface_area"].kind == "range"


def test_load_toy_environment_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    environment = registry.get_environment("toy_lab_environment")

    assert environment.conditions["temperature"].to_quantity().to("kelvin").magnitude == pytest.approx(303.15)
    assert environment.conditions["ph"].kind == "range"
    assert environment.conditions["oxygen_concentration"].kind == "not_applicable"


def test_load_toy_enzyme_class_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    enzyme = registry.get_enzyme_class("toy_cellulase")

    assert enzyme.target_bond_classes == ("toy_beta_1_4_glycosidic",)
    assert enzyme.compatible_substrate_classes == ("toy_cellulose_like",)
    assert enzyme.compatible_processes == ("surface_catalysis",)


def test_load_toy_process_compatibility_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    records = registry.get_process_compatibility(
        enzyme_class="toy_cellulase",
        substrate_class="toy_cellulose_like",
        process_type="surface_catalysis",
    )

    assert len(records) == 1
    assert records[0].product_map_required
    assert "k_surface_exact" in records[0].required_parameters
    assert records[0].parameter_roles["surface_rate_constant"] == "k_surface_exact"
    assert "component_bindings" not in records[0].to_dict()


def test_load_ordered_chain_component_compatibility_bindings() -> None:
    registry = load_registry(REGISTRY_INDEX)
    chain = registry.process_compatibility[
        "bio002_cellulase_cellulose_film_extracellular_chain"
    ]
    assert chain.compatibility_scope == "standalone"
    assert "compatibility_scope" not in chain.to_dict()
    assert [binding.to_dict() for binding in chain.component_bindings] == [
        {
            "process_template_id": "bio002_surface_cellulose_to_cellobiose",
            "compatibility_record_id": "bio002_cellulase_cellulose_surface_component",
        },
        {
            "process_template_id": "bio002_cellobiose_to_glucose_mm",
            "compatibility_record_id": "bio002_beta_glucosidase_cellobiose_component",
        },
    ]


def test_in_memory_component_binding_mutation_fails_registry_validation() -> None:
    registry = load_registry(REGISTRY_INDEX)
    record_id = "bio002_cellulase_cellulose_film_extracellular_chain"
    outer = registry.process_compatibility[record_id]
    whitespace_binding = replace(
        outer,
        component_bindings=(
            ProcessComponentBinding(
                process_template_id=" ",
                compatibility_record_id="component",
            ),
        ),
    )
    assert not whitespace_binding.validate().passed

    registry.process_compatibility[record_id] = replace(
        outer,
        component_bindings=cast(Any, ({"process_template_id": "step"},)),
    )
    with pytest.raises(RegistryValidationError, match="Invalid process compatibility record"):
        registry.get_process_compatibility()


@pytest.mark.parametrize("malformation", ["list_role_symbol", "list_process_template_id"])
def test_malformed_in_memory_compatibility_values_raise_registry_validation(
    malformation: str,
) -> None:
    registry = load_registry(REGISTRY_INDEX)
    record_id = "bio002_cellulase_cellulose_film_extracellular_chain"
    outer = registry.process_compatibility[record_id]
    if malformation == "list_role_symbol":
        registry.process_compatibility[record_id] = replace(
            outer,
            parameter_roles=cast(Any, {"kcat": ["kcat_cellobiose"]}),
        )
    else:
        registry.process_compatibility[record_id] = replace(
            outer,
            component_bindings=(
                replace(
                    outer.component_bindings[0],
                    process_template_id=cast(Any, ["not-text"]),
                ),
                outer.component_bindings[1],
            ),
        )

    with pytest.raises(RegistryValidationError, match="Invalid process compatibility record"):
        registry.get_process_compatibility()


def test_component_only_scope_survives_removed_owner_bindings_at_query_time() -> None:
    registry = load_registry(REGISTRY_INDEX)
    outer_id = "bio002_cellulase_cellulose_film_extracellular_chain"
    component_id = "bio002_beta_glucosidase_cellobiose_component"
    component = registry.process_compatibility[component_id]

    assert component.compatibility_scope == "component_only"
    assert component.to_dict()["compatibility_scope"] == "component_only"
    registry.process_compatibility[outer_id] = replace(
        registry.process_compatibility[outer_id],
        component_bindings=(),
    )

    with pytest.raises(RegistryValidationError, match="exactly one owner binding; found 0"):
        registry.get_process_compatibility(
            enzyme_class="beta_glucosidase",
            substrate_class="cellobiose",
            process_type="homogeneous_michaelis_menten",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("whitespace_process_id", "Invalid process compatibility record"),
        ("standalone_component", "intrinsic component-only"),
        ("nested_component", "cannot declare case_template_id or component_bindings"),
        ("component_case_template", "cannot declare case_template_id or component_bindings"),
        ("incomplete_component_content", "bind every required parameter"),
        ("incomplete_owner_content", "must bind every required parameter"),
        ("missing_component", "references missing component compatibility"),
        ("duplicate_owner", "exactly one owner binding; found 2"),
    ],
)
def test_component_authority_graph_fails_closed_under_in_memory_mutation(
    mutation: str,
    message: str,
) -> None:
    registry = load_registry(REGISTRY_INDEX)
    outer_id = "bio002_cellulase_cellulose_film_extracellular_chain"
    component_id = "bio002_beta_glucosidase_cellobiose_component"
    outer = registry.process_compatibility[outer_id]
    component = registry.process_compatibility[component_id]
    if mutation == "whitespace_process_id":
        registry.process_compatibility[outer_id] = replace(
            outer,
            component_bindings=(
                outer.component_bindings[0],
                replace(
                    outer.component_bindings[1],
                    process_template_id=(
                        f" {outer.component_bindings[1].process_template_id}"
                    ),
                ),
            ),
        )
    elif mutation == "standalone_component":
        registry.process_compatibility[component_id] = replace(
            component,
            compatibility_scope="standalone",
        )
    elif mutation == "nested_component":
        registry.process_compatibility[component_id] = replace(
            component,
            component_bindings=(outer.component_bindings[0],),
        )
    elif mutation == "component_case_template":
        registry.process_compatibility[component_id] = replace(
            component,
            case_template_id="sabiork_reaction_618_homogeneous_mm_template",
        )
    elif mutation == "incomplete_component_content":
        registry.process_compatibility[component_id] = replace(
            component,
            required_parameters=(*component.required_parameters, "unbound_symbol"),
        )
    elif mutation == "incomplete_owner_content":
        roles = dict(outer.parameter_roles)
        roles.pop("kcat")
        registry.process_compatibility[outer_id] = replace(
            outer,
            parameter_roles=roles,
        )
    elif mutation == "missing_component":
        registry.process_compatibility.pop(component_id)
    else:
        registry.process_compatibility["duplicate_component_owner"] = replace(
            outer,
            record_id="duplicate_component_owner",
        )

    with pytest.raises(RegistryValidationError, match=message):
        registry.get_process_compatibility()


@pytest.mark.parametrize("scope", [None, "component", " component_only"])
def test_component_scope_loader_accepts_only_the_closed_intrinsic_value(
    tmp_path: Path,
    scope: Any,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    path = registry_dir / "processes" / "process_compatibility.yml"
    payload = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], payload["records"])
    component = next(
        record
        for record in records
        if record["record_id"] == "bio002_beta_glucosidase_cellobiose_component"
    )
    component["compatibility_scope"] = scope
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(RegistryLoadError, match="compatibility_scope"):
        load_registry(registry_dir / "registry_index.yml")


@pytest.mark.parametrize(
    ("bindings", "message"),
    [
        (None, "must be a sequence"),
        ([None], "must be a mapping"),
        ([{"process_template_id": "step"}], "must contain exactly"),
        (
            [
                {
                    "process_template_id": "step",
                    "compatibility_record_id": "compatibility",
                    "extra": True,
                }
            ],
            "must contain exactly",
        ),
        (
            [
                {
                    "process_template_id": " ",
                    "compatibility_record_id": "compatibility",
                }
            ],
            "must be nonblank text",
        ),
        (
            [
                {
                    "process_template_id": "step",
                    "compatibility_record_id": None,
                }
            ],
            "must be nonblank text",
        ),
    ],
)
def test_component_compatibility_binding_loader_fails_closed(
    tmp_path: Path,
    bindings: Any,
    message: str,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    path = registry_dir / "processes" / "process_compatibility.yml"
    payload = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], payload["records"])
    outer = next(
        record
        for record in records
        if record["record_id"] == "bio002_cellulase_cellulose_film_extracellular_chain"
    )
    outer["component_bindings"] = bindings
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(RegistryLoadError, match=message):
        load_registry(registry_dir / "registry_index.yml")


def test_load_exact_range_distribution_and_unknown_parameter_records() -> None:
    registry = load_registry(REGISTRY_INDEX)

    exact = registry.get_parameter_records(parameter_symbol="k_surface_exact")[0]
    range_record = registry.get_parameter_records(parameter_symbol="k_surface_range")[0]
    distribution = registry.get_parameter_records(parameter_symbol="k_surface_prior")[0]
    unknown = registry.get_parameter_records(parameter_symbol="k_ads_unknown")[0]
    exact_adsorption = registry.get_parameter_records(parameter_symbol="k_ads_exact")[0]

    assert exact.value.kind == "exact"
    assert range_record.value.kind == "range"
    assert range_record.allowed_use == "software_tests_only_not_scientific"
    assert distribution.value.kind == "distribution"
    assert distribution.value.distribution == "loguniform"
    assert distribution.range_interpretation == "software_test_fixture_not_scientific_uncertainty"
    assert unknown.value.kind == "unknown"
    assert unknown.allowed_use == "software_tests_only_not_scientific"
    assert exact_adsorption.value.kind == "exact"


def test_parameter_records_expose_range_use_semantics() -> None:
    registry = load_registry(REGISTRY_INDEX)

    literature_range = registry.get_parameter_records(
        parameter_symbol="Km_cellobiose",
        maturity="literature_range",
    )[0]
    exploratory_prior = registry.get_parameter_records(
        parameter_symbol="enzyme_concentration_beta_glucosidase",
        maturity="exploratory_prior",
    )[0]
    selected_exact = registry.get_parameter_records(
        parameter_symbol="Km_cellobiose",
        maturity="literature_processed",
    )[0]

    assert literature_range.range_scope == "all_eligible"
    assert literature_range.range_interpretation == "cross_entry_literature_spread_not_selected_entry_uncertainty"
    assert literature_range.allowed_use == "exploratory_screening_only_not_calibrated_uncertainty_not_environment_response"
    assert exploratory_prior.range_scope == "user_supplied_case_prior"
    assert exploratory_prior.allowed_use == "exploratory_simulation_only_not_literature_curated"
    assert selected_exact.range_scope == "not_applicable"
    assert selected_exact.allowed_use == "scientific_or_exploratory_when_all_other_inputs_are_valid"


def test_duplicate_record_ids_fail(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    fungi_path = registry_dir / "fungi" / "fungi.yml"
    data = _yaml_mapping(fungi_path)
    records = cast(list[dict[str, Any]], data["records"])
    records.append(dict(records[0]))
    fungi_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(RegistryValidationError, match="Duplicate"):
        load_registry(registry_dir / "registry_index.yml")


def test_unknown_record_id_fails_clearly() -> None:
    registry = load_registry(REGISTRY_INDEX)

    with pytest.raises(RegistryLookupError, match="Unknown fungus"):
        registry.get_fungus("not_present")


def test_missing_referenced_registry_file_fails_clearly(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    index_path = registry_dir / "registry_index.yml"
    data = _yaml_mapping(index_path)
    records = cast(dict[str, Any], data["records"])
    records["fungi"] = "fungi/missing.yml"
    index_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(RegistryLoadError, match="does not exist"):
        load_registry(index_path)


def test_registry_records_are_json_safe() -> None:
    registry = load_registry(REGISTRY_INDEX)

    encoded = json.dumps(registry.to_dict())

    assert "toy_registry" in encoded
    assert "toy_param_k_surface_loguniform" in encoded


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
