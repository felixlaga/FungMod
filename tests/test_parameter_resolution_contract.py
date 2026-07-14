from __future__ import annotations

import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model import VirtualExperiment
from fungal_model.api import VirtualExperimentError
from fungal_model.examples.product_inhibition import (
    prepare_reversible_product_inhibition_example_registry,
)
from fungal_model.registry import FungModRegistry, RegistryValidationError, load_registry
from fungal_model.registry.records import (
    CaseTemplateRecord,
    PARAMETER_ALLOWED_USE_EXPLORATORY,
    PARAMETER_ALLOWED_USE_SCIENTIFIC,
    PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY,
    PARAMETER_ALLOWED_USE_STORAGE_ONLY,
    parameter_record_mode_eligibility_blocker,
)
from fungal_model.screening import (
    EnzymeChainAssemblyError,
    RegistryCaseBuildError,
    assess_modelability,
    build_extracellular_enzyme_chain_config,
    build_model_config_from_registry_case,
)
from fungal_model.screening.parameter_resolution import (
    ExactTemplateParameterError,
    resolve_exact_template_parameter_records,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
CHAIN_TEMPLATE_ID = "bio002_extracellular_enzyme_chain_template"
CHAIN_COMPATIBILITY_ID = "bio002_cellulase_cellulose_film_extracellular_chain"
SURFACE_RECORD_ID = "bio002_cellulose_to_cellobiose_surface_rate"
KM_RECORD_ID = "sabiork_reaction_618_Km_cellobiose"
KCAT_RECORD_ID = "sabiork_reaction_618_kcat_cellobiose"
BETA_INITIAL_RECORD_ID = "bio002_beta_glucosidase_initial_concentration"
FUNGUS_ID = "generic_cellulase_source"
CHAIN_FIXTURE_FUNGUS_ID = "exact_chain_test_source"
SUBSTRATE_ID = "cellulose_film_generic"
ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"


@pytest.mark.parametrize(
    ("mode", "allowed_use", "permitted"),
    [
        ("scientific", PARAMETER_ALLOWED_USE_SCIENTIFIC, True),
        ("exploratory", PARAMETER_ALLOWED_USE_SCIENTIFIC, True),
        ("toy", PARAMETER_ALLOWED_USE_SCIENTIFIC, True),
        ("scientific", PARAMETER_ALLOWED_USE_EXPLORATORY, False),
        ("exploratory", PARAMETER_ALLOWED_USE_EXPLORATORY, True),
        ("toy", PARAMETER_ALLOWED_USE_EXPLORATORY, True),
        ("scientific", PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY, False),
        ("exploratory", PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY, True),
        ("toy", PARAMETER_ALLOWED_USE_SOFTWARE_TESTS_ONLY, True),
        ("scientific", "software_tests_only_not_scientific", False),
        ("scientific", "not_scientific", False),
        ("scientific", "", False),
        ("scientific", "scientific_or_exploratory_when_all_other_inputs_are_valid ", False),
        ("scientific", "scientific_or_exploratory_when_all_other_inputs_are_valid_extra", False),
        ("exploratory", "exploratory_simulation", False),
        ("toy", "toy_simulation", False),
        ("exploratory", PARAMETER_ALLOWED_USE_STORAGE_ONLY, False),
        ("scientific", PARAMETER_ALLOWED_USE_STORAGE_ONLY, False),
        ("toy", PARAMETER_ALLOWED_USE_STORAGE_ONLY, False),
    ],
)
def test_parameter_allowed_use_is_a_closed_mode_contract(
    mode: str,
    allowed_use: str,
    permitted: bool,
) -> None:
    registry = load_registry(REGISTRY_INDEX)
    record = replace(registry.parameters[KCAT_RECORD_ID], allowed_use=allowed_use)

    blocker = parameter_record_mode_eligibility_blocker(record, mode=cast(Any, mode))

    assert (blocker is None) is permitted


@pytest.mark.parametrize("mode", ["scientific", "exploratory", "toy"])
def test_nested_curator_evidence_is_mode_independently_ineligible(mode: str) -> None:
    registry = load_registry(REGISTRY_INDEX)
    record = registry.parameters[KCAT_RECORD_ID]
    nested = replace(
        record,
        allowed_use=PARAMETER_ALLOWED_USE_SCIENTIFIC,
        provenance={
            **record.provenance,
            "fungmod_curation": {"source_provenance": {"source_database": "SABIO-RK"}},
        },
    )

    blocker = parameter_record_mode_eligibility_blocker(nested, mode=cast(Any, mode))

    assert blocker is not None
    assert "curator-authoring source evidence" in blocker


@pytest.mark.parametrize(
    ("record_id", "changes", "message"),
    [
        (SURFACE_RECORD_ID, {"process_type": "homogeneous_michaelis_menten"}, "process_type"),
        (SURFACE_RECORD_ID, {"process_type": "invented_process"}, "process_type"),
        (SURFACE_RECORD_ID, {"enzyme_class": "invented_class", "fungus_id": None}, "enzyme_class"),
        (SURFACE_RECORD_ID, {"enzyme_class": "beta_glucosidase", "fungus_id": None}, "enzyme_class"),
        (SURFACE_RECORD_ID, {"substrate_id": "toy_cellulose_like_solid"}, "substrate_id"),
        (KCAT_RECORD_ID, {"substrate_class": "cellulose_film_generic"}, "substrate_class"),
        (KCAT_RECORD_ID, {"substrate_id": "cellulose_film_generic"}, "substrate_id"),
    ],
)
def test_shared_exact_resolver_rejects_process_and_component_drift(
    record_id: str,
    changes: dict[str, Any],
    message: str,
) -> None:
    registry = load_registry(REGISTRY_INDEX)
    registry.parameters[record_id] = replace(registry.parameters[record_id], **changes)
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(ExactTemplateParameterError, match=message):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=compatibility,
            required_roles=tuple(compatibility.parameter_roles),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


def test_shared_exact_resolver_rejects_cross_component_role_swap() -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    record_ids = deepcopy(dict(metadata["parameter_record_ids"]))
    record_ids["surface_rate_constant"] = KCAT_RECORD_ID
    metadata["parameter_record_ids"] = record_ids
    template = replace(template, process_state_metadata=metadata)

    with pytest.raises(ExactTemplateParameterError, match="expected symbol"):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=registry.process_compatibility[CHAIN_COMPATIBILITY_ID],
            required_roles=("surface_rate_constant",),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


def test_shared_exact_resolver_preserves_caller_required_roles_with_compatibility() -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(
        ExactTemplateParameterError,
        match="missing explicit parameter record IDs for: independent_required_role",
    ):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=compatibility,
            required_roles=("independent_required_role",),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


def test_shared_exact_resolver_cross_binds_configured_substrate_entity_id() -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    entities = deepcopy(dict(metadata["entities"]))
    substrates = deepcopy(list(entities["substrates"]))
    substrates[0]["id"] = "rewritten_configured_substrate"
    entities["substrates"] = substrates
    metadata["entities"] = entities
    template = replace(template, process_state_metadata=metadata)
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(
        ExactTemplateParameterError,
        match="declares missing registry substrate entity",
    ):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=compatibility,
            required_roles=tuple(compatibility.parameter_roles),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


def test_shared_exact_resolver_requires_initial_state_semantic_role_key() -> None:
    registry = load_registry(REGISTRY_INDEX)
    _rename_component_role(
        registry,
        component_id="bio002_beta_glucosidase_cellobiose_component",
        old_role="enzyme_initial_concentration",
        new_role="unrelated_initial_role",
    )
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(
        ExactTemplateParameterError,
        match="exact component compatibility role 'enzyme_initial_concentration'",
    ):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=compatibility,
            required_roles=tuple(compatibility.parameter_roles),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


def test_shared_exact_resolver_requires_nested_modifier_semantic_role_key(
    tmp_path: Path,
) -> None:
    registry_index = prepare_reversible_product_inhibition_example_registry(
        tmp_path / "product_inhibition_registry",
        source_registry=REGISTRY_INDEX,
    )
    registry = load_registry(registry_index)
    _rename_component_role(
        registry,
        component_id="bio002_beta_glucosidase_cellobiose_component",
        old_role="inhibition_constant",
        new_role="unrelated_modifier_role",
    )
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(
        ExactTemplateParameterError,
        match="exact component compatibility role 'inhibition_constant'",
    ):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=compatibility,
            required_roles=tuple(compatibility.parameter_roles),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("substrate_entity_id", "missing registry substrate entity"),
        ("same_class_substrate_identity", "must be the exact substrate consumed"),
        ("direct_role_truncation", "exact canonical"),
        ("direct_role_alias", "reuses explicit parameter roles"),
        ("direct_role_rename", "exact canonical"),
        (
            "initial_state_role",
            "exact component compatibility role 'enzyme_initial_concentration'",
        ),
        (
            "nested_modifier_role",
            "exact component compatibility role 'inhibition_constant'",
        ),
    ],
)
def test_identity_and_semantic_role_drift_is_rejected_by_every_public_path(
    tmp_path: Path,
    drift: str,
    message: str,
) -> None:
    valid_index = _prepare_contract_registry(tmp_path / "valid", drift=drift)
    valid_study = VirtualExperiment.from_registry(
        fungi=CHAIN_FIXTURE_FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=valid_index,
    )
    assert valid_study.preflight(mode="exploratory")[0].status in {
        "modelable",
        "exploratory",
    }
    valid_result = valid_study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=23,
        output_dir=tmp_path / "valid_result",
        quicklook=False,
    )
    _apply_contract_drift_in_memory(valid_study.registry, drift=drift)
    with pytest.raises(RegistryCaseBuildError, match=message):
        valid_result.write_tables(tmp_path / "rewritten_tables")

    drifted_index = _prepare_contract_registry(tmp_path / "drifted", drift=drift)
    _apply_contract_drift_in_files(drifted_index.parent, drift=drift)
    registry = load_registry(drifted_index)
    report = assess_modelability(
        fungus_id=CHAIN_FIXTURE_FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="exploratory",
    )
    assert report.status == "underparameterized"
    assert any(message in item.message for item in report.incompatible)

    study = VirtualExperiment.from_registry(
        fungi=CHAIN_FIXTURE_FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=drifted_index,
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
            fungus_id=CHAIN_FIXTURE_FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            registry=registry,
            mode="toy",
        )
    with pytest.raises(EnzymeChainAssemblyError, match=message):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=ENVIRONMENT_ID,
        )


def test_shared_exact_resolver_rejects_coherent_whole_component_role_group_swap() -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = _coherently_swap_second_component(registry)
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(ExactTemplateParameterError, match="exact substrate consumed"):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=compatibility,
            required_roles=tuple(compatibility.parameter_roles),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("shadow_selectors", "component_selectors are unsupported"),
        ("component_binding", "compatibility_record_id values must be unique"),
        ("standalone_component_binding", "intrinsic component-only compatibility"),
        ("component_compatibility", "process_type does not match"),
        ("enzyme_capability", "does not authorize process type"),
        ("state_species", "exact substrate consumed"),
    ],
)
def test_shared_exact_resolver_rejects_each_independent_component_authority_drift(
    drift: str,
    message: str,
) -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    if drift == "shadow_selectors":
        processes = deepcopy(list(metadata["process_templates"]))
        processes[1]["component_selectors"] = {
            "enzyme_class": "cellulase_generic",
            "substrate_class": "cellulose_film_generic",
        }
        metadata["process_templates"] = processes
    elif drift == "component_binding":
        _reuse_outer_component_binding(registry)
    elif drift == "standalone_component_binding":
        _bind_standalone_compatibility(registry)
    elif drift == "component_compatibility":
        _rewrite_bound_component_compatibility(registry)
    elif drift == "enzyme_capability":
        registry.enzyme_classes["beta_glucosidase"] = replace(
            registry.enzyme_classes["beta_glucosidase"],
            compatible_processes=("surface_catalysis",),
        )
    else:
        _swap_component_state_species(metadata)
    template = replace(template, process_state_metadata=metadata)
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(ExactTemplateParameterError, match=message):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=compatibility,
            required_roles=tuple(compatibility.parameter_roles),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


@pytest.mark.parametrize(
    ("role", "record_id", "changes", "message"),
    [
        (
            "cellulase_initial_concentration",
            "bio002_cellulase_initial_concentration",
            {"enzyme_class": "invented_enzyme_class", "fungus_id": None},
            "declared template enzyme component",
        ),
        (
            "solid_substrate_initial_concentration",
            "bio002_initial_solid_cellulose_equivalent_concentration",
            {"substrate_class": "invented_substrate_class", "substrate_id": None},
            "declared template substrate component",
        ),
        (
            "surface_rate_constant",
            SURFACE_RECORD_ID,
            {
                "enzyme_class": "beta_glucosidase",
                "substrate_class": "cellobiose",
                "substrate_id": "cellobiose",
            },
            "bound component value",
        ),
    ],
)
def test_shared_exact_resolver_rejects_coherent_null_id_component_rewrites(
    role: str,
    record_id: str,
    changes: dict[str, Any],
    message: str,
) -> None:
    registry = load_registry(REGISTRY_INDEX)
    registry.parameters[record_id] = replace(registry.parameters[record_id], **changes)
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    contracts = deepcopy(dict(metadata["parameter_role_contracts"]))
    contracts[role] = {**contracts[role], **changes}
    contracts[role].pop("process_type", None)
    metadata["parameter_role_contracts"] = contracts
    template = replace(template, process_state_metadata=metadata)

    with pytest.raises(ExactTemplateParameterError, match=message):
        resolve_exact_template_parameter_records(
            registry=registry,
            template=template,
            compatibility=registry.process_compatibility[CHAIN_COMPATIBILITY_ID],
            required_roles=tuple(registry.process_compatibility[CHAIN_COMPATIBILITY_ID].parameter_roles),
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            mode="exploratory",
            value_requirement="sampleable",
        )


@pytest.mark.parametrize(
    "allowed_use",
    [
        "software_tests_only_not_scientific",
        "not_scientific",
        "",
        "scientific_or_exploratory_when_all_other_inputs_are_valid_extra",
        PARAMETER_ALLOWED_USE_STORAGE_ONLY,
    ],
)
def test_scientific_public_paths_reject_noncanonical_allowed_use(
    tmp_path: Path,
    allowed_use: str,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    payload = _yaml_mapping(parameter_path)
    records = cast(list[dict[str, Any]], payload["records"])
    for record in records:
        if record["record_id"] == KCAT_RECORD_ID:
            record["allowed_use"] = allowed_use
        if record.get("parameter_symbol") == "enzyme_concentration_beta_glucosidase" and record.get(
            "maturity"
        ) == "literature_processed":
            record["value"] = {
                "kind": "exact",
                "value": 0.01,
                "units": "mM",
                "source": "Test-owned deterministic concentration fixture",
                "confidence_level": "testing",
                "notes": "Software-test value only; not empirical evidence.",
            }
    parameter_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    study = VirtualExperiment.from_registry(
        fungi="sabiork_beta_glucosidase_source",
        substrates="cellobiose",
        environments=ENVIRONMENT_ID,
        registry=registry_dir / "registry_index.yml",
    )

    report = study.preflight(mode="scientific")[0]
    assert report.status == "underparameterized"
    assert any("allowed_use" in item.message for item in report.incompatible)
    with pytest.raises(VirtualExperimentError, match="allowed_use|storage-only"):
        study.simulate(
            mode="scientific",
            output_dir=tmp_path / "blocked_scientific",
            quicklook=False,
        )
    with pytest.raises(RegistryCaseBuildError, match="modelability status"):
        build_model_config_from_registry_case(
            fungus_id="sabiork_beta_glucosidase_source",
            substrate_id="cellobiose",
            environment_id=ENVIRONMENT_ID,
            registry=load_registry(registry_dir / "registry_index.yml"),
            mode="scientific",
        )


def test_exact_template_drift_is_rejected_by_every_chain_path_and_reporting(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path / "valid")
    valid_study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=registry_dir / "registry_index.yml",
    )
    valid_result = valid_study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=7,
        output_dir=tmp_path / "valid_result",
        quicklook=False,
    )
    valid_study.registry.parameters[SURFACE_RECORD_ID] = replace(
        valid_study.registry.parameters[SURFACE_RECORD_ID],
        process_type="homogeneous_michaelis_menten",
    )
    with pytest.raises(RegistryCaseBuildError, match="Result reconstruction rejected"):
        valid_result.write_tables(tmp_path / "rewritten_tables")

    drifted_dir = _copy_registry(tmp_path / "drifted")
    _replace_parameter_field(
        drifted_dir,
        record_id=SURFACE_RECORD_ID,
        field="process_type",
        value="homogeneous_michaelis_menten",
    )
    _remove_process_compatibility(
        drifted_dir,
        record_id="bio001_cellulase_cellulose_film_surface_catalysis",
    )
    registry = load_registry(drifted_dir / "registry_index.yml")
    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="exploratory",
    )
    assert report.status == "underparameterized"
    assert any("exact case-template parameter mapping" in item.message.casefold() for item in report.incompatible)
    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=drifted_dir / "registry_index.yml",
    )
    with pytest.raises(VirtualExperimentError, match="process_type"):
        study.simulate(
            mode="exploratory",
            n_samples=1,
            output_dir=tmp_path / "blocked_runtime",
            quicklook=False,
        )
    with pytest.raises(RegistryCaseBuildError):
        build_model_config_from_registry_case(
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            registry=registry,
            mode="toy",
        )
    with pytest.raises(EnzymeChainAssemblyError, match="process_type"):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=ENVIRONMENT_ID,
        )


def test_coherent_whole_component_role_group_swap_is_rejected_by_every_public_path(
    tmp_path: Path,
) -> None:
    valid_registry_dir = _copy_registry(tmp_path / "valid")
    valid_study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=valid_registry_dir / "registry_index.yml",
    )
    valid_result = valid_study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=11,
        output_dir=tmp_path / "valid_result",
        quicklook=False,
    )
    valid_study.registry.case_templates[CHAIN_TEMPLATE_ID] = _coherently_swap_second_component(
        valid_study.registry
    )
    with pytest.raises(
        RegistryValidationError,
        match="process_type does not match|exact substrate consumed",
    ):
        valid_result.write_tables(tmp_path / "rewritten_tables")

    registry = valid_study.registry
    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="exploratory",
    )
    assert report.status == "unsupported"
    assert any(
        "process_type does not match" in item.message
        or "exact substrate consumed" in item.message
        for item in report.incompatible
    )

    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=registry,
    )
    with pytest.raises(
        VirtualExperimentError,
        match="process_type does not match|exact substrate consumed",
    ):
        study.simulate(
            mode="exploratory",
            n_samples=1,
            output_dir=tmp_path / "blocked_runtime",
            quicklook=False,
        )
    with pytest.raises(RegistryCaseBuildError, match="modelability status"):
        build_model_config_from_registry_case(
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            registry=registry,
            mode="toy",
        )
    with pytest.raises(
        EnzymeChainAssemblyError,
        match="process_type does not match|exact substrate consumed",
    ):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=ENVIRONMENT_ID,
        )


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _prepare_contract_registry(tmp_path: Path, *, drift: str) -> Path:
    if drift == "nested_modifier_role":
        registry_index = prepare_reversible_product_inhibition_example_registry(
            tmp_path / "data_registry",
            source_registry=REGISTRY_INDEX,
        )
        registry_dir = registry_index.parent
    else:
        registry_dir = _copy_registry(tmp_path)
        registry_index = registry_dir / "registry_index.yml"
    _add_chain_only_public_fixture(registry_dir)
    return registry_index


def _add_chain_only_public_fixture(registry_dir: Path) -> None:
    enzyme_path = registry_dir / "enzymes" / "enzyme_classes.yml"
    enzyme_payload = _yaml_mapping(enzyme_path)
    cast(list[dict[str, Any]], enzyme_payload["records"]).insert(
        0,
        {
            "record_id": "exact_chain_test_class",
            "name": "Exact chain test class",
            "maturity": "toy_development",
            "provenance": {
                "source": "Parameter-resolution contract test fixture",
                "confidence_level": "testing",
                "notes": "Copied-registry chain-selection fixture only.",
            },
            "target_bond_classes": ["beta_1_4_glycosidic"],
            "compatible_substrate_classes": ["cellulose_film_generic"],
            "compatible_processes": [
                "surface_catalysis",
                "extracellular_enzyme_chain",
            ],
            "notes": "Software-test selector only; not biological evidence.",
        },
    )
    enzyme_path.write_text(
        yaml.safe_dump(enzyme_payload, sort_keys=False),
        encoding="utf-8",
    )

    fungus_path = registry_dir / "fungi" / "fungi.yml"
    fungus_payload = _yaml_mapping(fungus_path)
    cast(list[dict[str, Any]], fungus_payload["records"]).insert(
        0,
        {
            "record_id": CHAIN_FIXTURE_FUNGUS_ID,
            "name": "Exact chain test source",
            "maturity": "toy_development",
            "provenance": {
                "source": "Parameter-resolution contract test fixture",
                "confidence_level": "testing",
                "notes": "Copied-registry chain-selection fixture only.",
            },
            "enzyme_classes": ["exact_chain_test_class"],
            "assimilable_products": [],
            "notes": "Software-test selector only; not a biological source claim.",
        },
    )
    fungus_path.write_text(
        yaml.safe_dump(fungus_payload, sort_keys=False),
        encoding="utf-8",
    )

    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_payload = _yaml_mapping(template_path)
    template = next(
        record
        for record in cast(list[dict[str, Any]], template_payload["records"])
        if record["record_id"] == CHAIN_TEMPLATE_ID
    )
    metadata = cast(dict[str, Any], template["process_state_metadata"])
    enzyme_entities = cast(list[dict[str, Any]], metadata["entities"]["enzymes"])
    cellulase_entity = next(
        entity for entity in enzyme_entities if entity["id"] == "cellulase_generic"
    )
    cellulase_entity["id"] = "exact_chain_test_class"
    cellulase_entity["data"]["enzyme_class"] = "exact_chain_test_class"
    substrate_entities = cast(
        list[dict[str, Any]],
        metadata["entities"]["substrates"],
    )
    substrate_entities[0]["data"]["required_enzyme_classes"] = [
        "exact_chain_test_class"
    ]
    metadata["state_species"]["cellulase_concentration"]["species"] = (
        "exact_chain_test_class"
    )
    contracts = cast(
        dict[str, dict[str, Any]],
        metadata["parameter_role_contracts"],
    )
    first_component_roles = {
        role
        for role, contract in contracts.items()
        if contract.get("enzyme_class") == "cellulase_generic"
    }
    for role in first_component_roles:
        contracts[role]["enzyme_class"] = "exact_chain_test_class"
        contracts[role]["fungus_id"] = CHAIN_FIXTURE_FUNGUS_ID
    template_path.write_text(
        yaml.safe_dump(template_payload, sort_keys=False),
        encoding="utf-8",
    )

    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    parameter_payload = _yaml_mapping(parameter_path)
    first_component_record_ids = {
        metadata["parameter_record_ids"][role] for role in first_component_roles
    }
    for record in cast(list[dict[str, Any]], parameter_payload["records"]):
        if record["record_id"] in first_component_record_ids:
            record["enzyme_class"] = "exact_chain_test_class"
            record["fungus_id"] = CHAIN_FIXTURE_FUNGUS_ID
    parameter_path.write_text(
        yaml.safe_dump(parameter_payload, sort_keys=False),
        encoding="utf-8",
    )

    process_path = registry_dir / "processes" / "process_compatibility.yml"
    process_payload = _yaml_mapping(process_path)
    outer = next(
        record
        for record in cast(list[dict[str, Any]], process_payload["records"])
        if record["record_id"] == CHAIN_COMPATIBILITY_ID
    )
    outer["enzyme_class"] = "exact_chain_test_class"
    component = next(
        record
        for record in cast(list[dict[str, Any]], process_payload["records"])
        if record["record_id"]
        == "bio002_cellulase_cellulose_surface_component"
    )
    component["enzyme_class"] = "exact_chain_test_class"
    standalone = deepcopy(component)
    standalone["record_id"] = "exact_chain_test_surface_compatibility"
    standalone["name"] = "Exact chain test standalone surface compatibility"
    standalone.pop("compatibility_scope")
    cast(list[dict[str, Any]], process_payload["records"]).append(standalone)
    process_path.write_text(
        yaml.safe_dump(process_payload, sort_keys=False),
        encoding="utf-8",
    )


def _apply_contract_drift_in_memory(
    registry: FungModRegistry,
    *,
    drift: str,
) -> None:
    if drift == "substrate_entity_id":
        template = registry.case_templates[CHAIN_TEMPLATE_ID]
        metadata = deepcopy(dict(template.process_state_metadata))
        entities = deepcopy(dict(metadata["entities"]))
        substrates = deepcopy(list(entities["substrates"]))
        substrates[0]["id"] = "rewritten_configured_substrate"
        entities["substrates"] = substrates
        metadata["entities"] = entities
        registry.case_templates[CHAIN_TEMPLATE_ID] = replace(
            template,
            process_state_metadata=metadata,
        )
        return
    if drift == "same_class_substrate_identity":
        _replace_outer_substrate_with_same_class_alternate(registry)
        return
    if drift in {"direct_role_truncation", "direct_role_alias", "direct_role_rename"}:
        _mutate_direct_kcat_contract(registry, mutation=drift)
        return
    _rename_component_role(
        registry,
        component_id="bio002_beta_glucosidase_cellobiose_component",
        old_role=(
            "enzyme_initial_concentration"
            if drift == "initial_state_role"
            else "inhibition_constant"
        ),
        new_role=(
            "unrelated_initial_role"
            if drift == "initial_state_role"
            else "unrelated_modifier_role"
        ),
    )


def _apply_contract_drift_in_files(registry_dir: Path, *, drift: str) -> None:
    if drift == "substrate_entity_id":
        path = registry_dir / "case_templates" / "case_templates.yml"
        payload = _yaml_mapping(path)
        template = next(
            record
            for record in cast(list[dict[str, Any]], payload["records"])
            if record["record_id"] == CHAIN_TEMPLATE_ID
        )
        substrates = cast(
            list[dict[str, Any]],
            template["process_state_metadata"]["entities"]["substrates"],
        )
        substrates[0]["id"] = "rewritten_configured_substrate"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return
    if drift == "same_class_substrate_identity":
        _replace_outer_substrate_with_same_class_alternate_in_files(registry_dir)
        return
    if drift in {"direct_role_truncation", "direct_role_alias", "direct_role_rename"}:
        _mutate_direct_kcat_contract_in_files(registry_dir, mutation=drift)
        return
    path = registry_dir / "processes" / "process_compatibility.yml"
    payload = _yaml_mapping(path)
    component = next(
        record
        for record in cast(list[dict[str, Any]], payload["records"])
        if record["record_id"] == "bio002_beta_glucosidase_cellobiose_component"
    )
    roles = cast(dict[str, str], component["parameter_roles"])
    old_role = (
        "enzyme_initial_concentration"
        if drift == "initial_state_role"
        else "inhibition_constant"
    )
    new_role = (
        "unrelated_initial_role"
        if drift == "initial_state_role"
        else "unrelated_modifier_role"
    )
    roles[new_role] = roles.pop(old_role)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _coherently_swap_second_component(
    registry: FungModRegistry,
) -> CaseTemplateRecord:
    selectors = {
        "enzyme_class": "cellulase_generic",
        "substrate_class": "cellulose_film_generic",
        "fungus_id": None,
        "substrate_id": "cellulose_film_generic",
    }
    for record_id in (BETA_INITIAL_RECORD_ID, KM_RECORD_ID, KCAT_RECORD_ID):
        registry.parameters[record_id] = replace(
            registry.parameters[record_id],
            **selectors,
        )

    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    contracts = deepcopy(dict(metadata["parameter_role_contracts"]))
    for role in ("beta_glucosidase_initial_concentration", "km", "kcat"):
        contracts[role] = {**contracts[role], **selectors}
    metadata["parameter_role_contracts"] = contracts
    _swap_component_state_species(metadata)
    _rewrite_bound_component_compatibility(registry)
    return replace(template, process_state_metadata=metadata)


def _replace_outer_substrate_with_same_class_alternate(
    registry: FungModRegistry,
) -> None:
    alternate_id = "alternate_cellulose_film_same_class"
    registry.substrates[alternate_id] = replace(
        registry.substrates[SUBSTRATE_ID],
        record_id=alternate_id,
        name="Alternate same-class cellulose film test identity",
    )
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    state_species = deepcopy(dict(metadata["state_species"]))
    state_species["solid_cellulose_equivalent_concentration"]["species"] = alternate_id
    state_species["beta_D_glucose_concentration"] = {
        "species": SUBSTRATE_ID,
        "entity_type": "substrate",
    }
    metadata["state_species"] = state_species
    registry.case_templates[CHAIN_TEMPLATE_ID] = replace(
        template,
        process_state_metadata=metadata,
    )


def _replace_outer_substrate_with_same_class_alternate_in_files(
    registry_dir: Path,
) -> None:
    alternate_id = "alternate_cellulose_film_same_class"
    substrate_path = registry_dir / "substrates" / "substrates.yml"
    substrate_payload = _yaml_mapping(substrate_path)
    substrates = cast(list[dict[str, Any]], substrate_payload["records"])
    canonical = next(record for record in substrates if record["record_id"] == SUBSTRATE_ID)
    alternate = deepcopy(canonical)
    alternate["record_id"] = alternate_id
    alternate["name"] = "Alternate same-class cellulose film test identity"
    substrates.append(alternate)
    substrate_path.write_text(
        yaml.safe_dump(substrate_payload, sort_keys=False),
        encoding="utf-8",
    )

    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_payload = _yaml_mapping(template_path)
    template = next(
        record
        for record in cast(list[dict[str, Any]], template_payload["records"])
        if record["record_id"] == CHAIN_TEMPLATE_ID
    )
    state_species = template["process_state_metadata"]["state_species"]
    state_species["solid_cellulose_equivalent_concentration"]["species"] = alternate_id
    state_species["beta_D_glucose_concentration"] = {
        "species": SUBSTRATE_ID,
        "entity_type": "substrate",
    }
    template_path.write_text(
        yaml.safe_dump(template_payload, sort_keys=False),
        encoding="utf-8",
    )


def _mutate_direct_kcat_contract(
    registry: FungModRegistry,
    *,
    mutation: str,
) -> None:
    template = registry.case_templates[CHAIN_TEMPLATE_ID]
    metadata = deepcopy(dict(template.process_state_metadata))
    process = cast(list[dict[str, Any]], metadata["process_templates"])[1]
    roles = cast(dict[str, str], process["parameter_roles"])
    if mutation == "direct_role_alias":
        roles["kcat"] = roles["km"]
    else:
        if mutation == "direct_role_rename":
            roles.pop("kcat")
            roles["unrelated_kcat"] = "unrelated_kcat"
            _rename_template_role(metadata, old_role="kcat", new_role="unrelated_kcat")
            _rename_compatibility_role(
                registry,
                record_id=CHAIN_COMPATIBILITY_ID,
                old_role="kcat",
                new_role="unrelated_kcat",
            )
            _rename_compatibility_role(
                registry,
                record_id="bio002_beta_glucosidase_cellobiose_component",
                old_role="kcat",
                new_role="unrelated_kcat",
            )
        else:
            roles.pop("kcat")
            _remove_template_role(metadata, role="kcat")
            _remove_compatibility_role(
                registry,
                record_id=CHAIN_COMPATIBILITY_ID,
                role="kcat",
            )
            _remove_compatibility_role(
                registry,
                record_id="bio002_beta_glucosidase_cellobiose_component",
                role="kcat",
            )
    registry.case_templates[CHAIN_TEMPLATE_ID] = replace(
        template,
        process_state_metadata=metadata,
    )


def _mutate_direct_kcat_contract_in_files(
    registry_dir: Path,
    *,
    mutation: str,
) -> None:
    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_payload = _yaml_mapping(template_path)
    template = next(
        record
        for record in cast(list[dict[str, Any]], template_payload["records"])
        if record["record_id"] == CHAIN_TEMPLATE_ID
    )
    metadata = cast(dict[str, Any], template["process_state_metadata"])
    process = cast(list[dict[str, Any]], metadata["process_templates"])[1]
    roles = cast(dict[str, str], process["parameter_roles"])
    if mutation == "direct_role_alias":
        roles["kcat"] = roles["km"]
    elif mutation == "direct_role_rename":
        roles.pop("kcat")
        roles["unrelated_kcat"] = "unrelated_kcat"
        _rename_template_role(metadata, old_role="kcat", new_role="unrelated_kcat")
    else:
        roles.pop("kcat")
        _remove_template_role(metadata, role="kcat")
    template_path.write_text(
        yaml.safe_dump(template_payload, sort_keys=False),
        encoding="utf-8",
    )
    if mutation == "direct_role_alias":
        return

    process_path = registry_dir / "processes" / "process_compatibility.yml"
    process_payload = _yaml_mapping(process_path)
    for record in cast(list[dict[str, Any]], process_payload["records"]):
        if record["record_id"] not in {
            CHAIN_COMPATIBILITY_ID,
            "bio002_beta_glucosidase_cellobiose_component",
        }:
            continue
        compatibility_roles = cast(dict[str, str], record["parameter_roles"])
        symbol = compatibility_roles.pop("kcat")
        if mutation == "direct_role_rename":
            compatibility_roles["unrelated_kcat"] = symbol
        else:
            cast(list[str], record["required_parameters"]).remove(symbol)
    process_path.write_text(
        yaml.safe_dump(process_payload, sort_keys=False),
        encoding="utf-8",
    )


def _rename_template_role(
    metadata: dict[str, Any],
    *,
    old_role: str,
    new_role: str,
) -> None:
    record_ids = cast(dict[str, Any], metadata["parameter_record_ids"])
    contracts = cast(dict[str, Any], metadata["parameter_role_contracts"])
    record_ids[new_role] = record_ids.pop(old_role)
    contracts[new_role] = contracts.pop(old_role)


def _remove_template_role(metadata: dict[str, Any], *, role: str) -> None:
    cast(dict[str, Any], metadata["parameter_record_ids"]).pop(role)
    cast(dict[str, Any], metadata["parameter_role_contracts"]).pop(role)


def _rename_compatibility_role(
    registry: FungModRegistry,
    *,
    record_id: str,
    old_role: str,
    new_role: str,
) -> None:
    record = registry.process_compatibility[record_id]
    roles = dict(record.parameter_roles)
    roles[new_role] = roles.pop(old_role)
    registry.process_compatibility[record_id] = replace(record, parameter_roles=roles)


def _remove_compatibility_role(
    registry: FungModRegistry,
    *,
    record_id: str,
    role: str,
) -> None:
    record = registry.process_compatibility[record_id]
    roles = dict(record.parameter_roles)
    symbol = roles.pop(role)
    registry.process_compatibility[record_id] = replace(
        record,
        parameter_roles=roles,
        required_parameters=tuple(
            value for value in record.required_parameters if value != symbol
        ),
    )


def _reuse_outer_component_binding(registry: FungModRegistry) -> None:
    outer = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]
    registry.process_compatibility[CHAIN_COMPATIBILITY_ID] = replace(
        outer,
        component_bindings=(
            outer.component_bindings[0],
            replace(
                outer.component_bindings[1],
                compatibility_record_id=outer.component_bindings[0].compatibility_record_id,
            ),
        ),
    )


def _rename_component_role(
    registry: FungModRegistry,
    *,
    component_id: str,
    old_role: str,
    new_role: str,
) -> None:
    component = registry.process_compatibility[component_id]
    roles = dict(component.parameter_roles)
    symbol = roles.pop(old_role)
    roles[new_role] = symbol
    registry.process_compatibility[component_id] = replace(
        component,
        parameter_roles=roles,
    )


def _bind_standalone_compatibility(registry: FungModRegistry) -> None:
    outer = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]
    registry.process_compatibility[CHAIN_COMPATIBILITY_ID] = replace(
        outer,
        component_bindings=(
            outer.component_bindings[0],
            replace(
                outer.component_bindings[1],
                compatibility_record_id="beta_glucosidase_cellobiose_homogeneous_mm",
            ),
        ),
    )


def _rewrite_bound_component_compatibility(registry: FungModRegistry) -> None:
    record_id = "bio002_beta_glucosidase_cellobiose_component"
    registry.process_compatibility[record_id] = replace(
        registry.process_compatibility[record_id],
        enzyme_class="cellulase_generic",
        substrate_class="cellulose_film_generic",
        process_type="surface_catalysis",
    )


def _swap_component_state_species(metadata: dict[str, Any]) -> None:
    state_species = deepcopy(dict(metadata["state_species"]))
    surface_enzyme = state_species["cellulase_concentration"]
    homogeneous_enzyme = state_species["beta_glucosidase_concentration"]
    surface_substrate = state_species["solid_cellulose_equivalent_concentration"]
    homogeneous_substrate = state_species["cellobiose_concentration"]
    state_species["cellulase_concentration"] = homogeneous_enzyme
    state_species["beta_glucosidase_concentration"] = surface_enzyme
    state_species["solid_cellulose_equivalent_concentration"] = homogeneous_substrate
    state_species["cellobiose_concentration"] = surface_substrate
    metadata["state_species"] = state_species


def _replace_parameter_field(
    registry_dir: Path,
    *,
    record_id: str,
    field: str,
    value: Any,
) -> None:
    path = registry_dir / "parameters" / "parameter_records.yml"
    payload = _yaml_mapping(path)
    for record in cast(list[dict[str, Any]], payload["records"]):
        if record["record_id"] == record_id:
            record[field] = value
            path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            return
    raise AssertionError(f"Missing parameter record {record_id!r}")


def _remove_process_compatibility(registry_dir: Path, *, record_id: str) -> None:
    path = registry_dir / "processes" / "process_compatibility.yml"
    payload = _yaml_mapping(path)
    records = cast(list[dict[str, Any]], payload["records"])
    filtered = [record for record in records if record["record_id"] != record_id]
    assert len(filtered) == len(records) - 1
    payload["records"] = filtered
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)
