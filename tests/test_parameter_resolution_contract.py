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
from fungal_model.registry import FungModRegistry, load_registry
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


def test_shared_exact_resolver_rejects_coherent_whole_component_role_group_swap() -> None:
    registry = load_registry(REGISTRY_INDEX)
    template = _coherently_swap_second_component(registry)
    compatibility = registry.process_compatibility[CHAIN_COMPATIBILITY_ID]

    with pytest.raises(ExactTemplateParameterError, match="requires process_type"):
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
        ("component_binding", "unique component compatibility"),
        ("standalone_component_binding", "without a case_template_id"),
        ("component_compatibility", "requires process_type"),
        ("enzyme_capability", "does not authorize process type"),
        ("state_species", "state identities require component pair"),
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
    with pytest.raises(RegistryCaseBuildError, match="requires process_type"):
        valid_result.write_tables(tmp_path / "rewritten_tables")

    drifted_dir = _copy_registry(tmp_path / "drifted")
    _coherently_swap_second_component_files(drifted_dir)
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
    assert any("requires process_type" in item.message for item in report.incompatible)

    study = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID,
        substrates=SUBSTRATE_ID,
        environments=ENVIRONMENT_ID,
        registry=drifted_dir / "registry_index.yml",
    )
    with pytest.raises(VirtualExperimentError, match="requires process_type"):
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
    with pytest.raises(EnzymeChainAssemblyError, match="requires process_type"):
        build_extracellular_enzyme_chain_config(
            registry=registry,
            environment_id=ENVIRONMENT_ID,
        )


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


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


def _coherently_swap_second_component_files(registry_dir: Path) -> None:
    selectors = {
        "enzyme_class": "cellulase_generic",
        "substrate_class": "cellulose_film_generic",
        "fungus_id": None,
        "substrate_id": "cellulose_film_generic",
    }
    parameter_path = registry_dir / "parameters" / "parameter_records.yml"
    parameter_payload = _yaml_mapping(parameter_path)
    for record in cast(list[dict[str, Any]], parameter_payload["records"]):
        if record["record_id"] in {BETA_INITIAL_RECORD_ID, KM_RECORD_ID, KCAT_RECORD_ID}:
            record.update(selectors)
    parameter_path.write_text(
        yaml.safe_dump(parameter_payload, sort_keys=False),
        encoding="utf-8",
    )

    template_path = registry_dir / "case_templates" / "case_templates.yml"
    template_payload = _yaml_mapping(template_path)
    templates = cast(list[dict[str, Any]], template_payload["records"])
    template = next(
        record for record in templates if record["record_id"] == CHAIN_TEMPLATE_ID
    )
    contracts = cast(
        dict[str, dict[str, Any]],
        template["process_state_metadata"]["parameter_role_contracts"],
    )
    for role in ("beta_glucosidase_initial_concentration", "km", "kcat"):
        contracts[role].update(selectors)
    metadata = cast(dict[str, Any], template["process_state_metadata"])
    _swap_component_state_species(metadata)
    template_path.write_text(
        yaml.safe_dump(template_payload, sort_keys=False),
        encoding="utf-8",
    )

    compatibility_path = registry_dir / "processes" / "process_compatibility.yml"
    compatibility_payload = _yaml_mapping(compatibility_path)
    records = cast(list[dict[str, Any]], compatibility_payload["records"])
    component = next(
        record
        for record in records
        if record["record_id"] == "bio002_beta_glucosidase_cellobiose_component"
    )
    component["enzyme_class"] = "cellulase_generic"
    component["substrate_class"] = "cellulose_film_generic"
    component["process_type"] = "surface_catalysis"
    compatibility_path.write_text(
        yaml.safe_dump(compatibility_payload, sort_keys=False),
        encoding="utf-8",
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
