from __future__ import annotations

import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest

import fungal_model
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    CurationRecord,
    CurationResult,
    load_curation_bundle,
)
from fungal_model.sources.sabiork import PROPOSAL_STATUS
from fungal_model.api.registry_promotion import (
    RegistryPromotionPlanError,
    apply_registry_promotion,
    plan_registry_promotion,
)
from fungal_model.api.registry_record_authoring import (
    REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY,
    REGISTRY_RECORD_AUTHORING_WORKFLOW,
    RegistryRecordAuthoringError,
    author_registry_records,
)
from fungal_model.registry.loaders import load_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
SUPPORTED_TYPES = (
    "fungi",
    "substrates",
    "enzyme_classes",
    "process_compatibility",
    "case_templates",
)


def _source_provenance(source_id: str) -> dict[str, Any]:
    return {
        "source_database": "authoring-test-source",
        "source_query": "authoring contract fixture",
        "source_entry_ids": [source_id],
        "source_snapshot_path": "tests/fixtures/authoring-source.yml",
        "source_url": None,
        "proposal_status": PROPOSAL_STATUS,
        "notes": "Review-only source fixture; not production registry data.",
    }


def _source_record(record_type: str) -> CurationRecord:
    source_id = f"source_{record_type}"
    provenance = _source_provenance(source_id)
    proposed_record: dict[str, Any] = {
        "record_id": source_id,
        "proposal_status": PROPOSAL_STATUS,
        "review_required": True,
        "allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "provenance": deepcopy(provenance),
    }
    required_fields: dict[str, Mapping[str, Any]] = {
        "fungi": {
            "scientific_name": "Testus authoringensis",
            "enzyme_classes": ["test_enzyme_class"],
        },
        "substrates": {
            "substrate_class": "test_substrate_class",
            "products": ["test_product"],
        },
        "enzyme_classes": {
            "ec_number": "3.2.1.999",
            "compatible_processes": ["homogeneous_michaelis_menten"],
        },
        "process_compatibility": {
            "process_type": "homogeneous_michaelis_menten",
            "enzyme_class": "test_enzyme_class",
            "substrate_class": "test_substrate_class",
            "required_parameters": ["test_parameter"],
            "parameter_roles": {"rate": "test_parameter"},
        },
        "case_templates": {
            "process_type": "homogeneous_michaelis_menten",
            "state_roles": {"substrate": "test_substrate", "product": "test_product"},
            "product_map": {
                "id": "test_product_map",
                "product_map_type": "stoichiometric",
                "substrate_state_role": "substrate",
                "product_state_role": "product",
            },
            "stoichiometric_yields": {"product": 1.0},
            "limitations": ["Review contract fixture only."],
        },
        "product_maps": {
            "product_map_type": "stoichiometric",
            "source_entry_id": source_id,
            "substrates": [
                {
                    "entry_id": source_id,
                    "reaction_id": "test_reaction",
                    "role": "substrate",
                    "compound_name": "test_substrate",
                    "stoichiometry": 1.0,
                }
            ],
            "products": [
                {
                    "entry_id": source_id,
                    "reaction_id": "test_reaction",
                    "role": "product",
                    "compound_name": "test_product",
                    "stoichiometry": 1.0,
                }
            ],
            "stoichiometric_yields": {"test_product": 1.0},
        },
    }
    proposed_record.update(required_fields[record_type])
    return CurationRecord(
        record_type=record_type,
        record_id=source_id,
        proposed_record=proposed_record,
        classification="eligible_for_review",
        missing_fields=(),
        reasons=(),
        decision="accept",
        explicit_decision=True,
        curator="Dr Curator",
        decision_reason="Complete production target authored from reviewed source evidence.",
        curation_date="2026-07-30",
        allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
        limitations=("Authoring contract test; no scientific validation is claimed.",),
        source_provenance=provenance,
    )


def _source_result(*record_types: str) -> CurationResult:
    return CurationResult(
        source_query="authoring contract fixture",
        source_snapshot_path="tests/fixtures/authoring-source.yml",
        proposal_limitations=("Fixture evidence exercises storage and promotion contracts only.",),
        records=tuple(_source_record(record_type) for record_type in record_types),
    )


def _targets() -> dict[str, dict[str, Any]]:
    registry = load_registry(REGISTRY_INDEX)
    fixtures = {
        "fungi": deepcopy(next(iter(registry.fungi.values())).to_dict()),
        "substrates": deepcopy(next(iter(registry.substrates.values())).to_dict()),
        "enzyme_classes": deepcopy(next(iter(registry.enzyme_classes.values())).to_dict()),
        "process_compatibility": deepcopy(
            registry.process_compatibility["beta_glucosidase_cellobiose_homogeneous_mm"].to_dict()
        ),
        "case_templates": deepcopy(registry.case_templates["toy_surface_catalysis_registry_template"].to_dict()),
    }
    targets: dict[str, dict[str, Any]] = {}
    for record_type, target in fixtures.items():
        source_id = f"source_{record_type}"
        target_id = f"authored_{record_type}"
        target["record_id"] = target_id
        target["name"] = f"Authored {record_type} contract fixture"
        target["maturity"] = "literature_metadata"
        target["provenance"] = _source_provenance(source_id)
        if record_type == "case_templates":
            target["case_template_id"] = target_id
        targets[source_id] = target
    return targets


def _author_all():
    return author_registry_records(
        _source_result(*SUPPORTED_TYPES),
        registry_records=_targets(),
    )


def test_authors_all_index_backed_non_parameter_families_without_mutation(
    tmp_path: Path,
) -> None:
    before = {
        path.relative_to(ROOT).as_posix(): path.read_bytes()
        for path in sorted((ROOT / "data_registry").rglob("*"))
        if path.is_file()
    }

    result = _author_all()

    assert result.summary()["workflow"] == REGISTRY_RECORD_AUTHORING_WORKFLOW
    assert result.summary()["supported_record_types"] == sorted(SUPPORTED_TYPES)
    assert result.summary()["production_loader_round_trip_verified"] is True
    assert result.summary()["simulation_authorized"] is False
    assert {record.record_type for record in result.records} == set(SUPPORTED_TYPES)
    for record in result.records:
        audit = record.proposed_record["provenance"][REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY]
        assert audit["supported_record_type"] == record.record_type
        assert audit["target_registry_key"] in SUPPORTED_TYPES
        assert audit["scientific_validation_claimed"] is False
        assert audit["simulation_authorized"] is False
        assert audit["production_registry_mutated"] is False

    plan = plan_registry_promotion(result, REGISTRY_INDEX)
    assert len(plan.addable_records) == len(SUPPORTED_TYPES)
    assert not plan.blocked_records
    assert not plan.conflicts

    written = result.write(tmp_path / "authored_registry_records")
    written_plan = plan_registry_promotion(written.output_directory, REGISTRY_INDEX)
    assert [item.to_dict() for item in written_plan.candidates] == [item.to_dict() for item in plan.candidates]
    assert [item.to_dict() for item in written_plan.prospective_files] == [
        item.to_dict() for item in plan.prospective_files
    ]
    after = {
        path.relative_to(ROOT).as_posix(): path.read_bytes()
        for path in sorted((ROOT / "data_registry").rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_accepts_checksum_loaded_written_source(tmp_path: Path) -> None:
    source = _source_result("fungi")
    written = source.write(tmp_path / "source_curation")
    loaded = load_curation_bundle(written.output_directory)
    target = _targets()["source_fungi"]

    result = author_registry_records(
        loaded,
        registry_records={"source_fungi": target},
    )

    assert result.source_record_ids == ("source_fungi",)
    assert result.authored_record_ids == ("authored_fungi",)


def test_authored_families_survive_transactional_apply(tmp_path: Path) -> None:
    registry_root = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", registry_root)
    registry_index = registry_root / "registry_index.yml"
    plan = plan_registry_promotion(_author_all(), registry_index)

    applied = apply_registry_promotion(
        plan,
        confirmation_digest=plan.plan_digest,
        new_registry_version="0.1.1",
    )

    registry = load_registry(registry_index)
    assert applied.applied_record_ids == tuple(sorted(f"authored_{record_type}" for record_type in SUPPORTED_TYPES))
    assert "authored_fungi" in registry.fungi
    assert "authored_substrates" in registry.substrates
    assert "authored_enzyme_classes" in registry.enzyme_classes
    assert "authored_process_compatibility" in registry.process_compatibility
    assert "authored_case_templates" in registry.case_templates


def test_rejects_raw_written_source_path(tmp_path: Path) -> None:
    written = _source_result("fungi").write(tmp_path / "source_curation")

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="CurationResult or checksum-loaded LoadedCurationBundle",
    ):
        author_registry_records(
            written.output_directory,  # type: ignore[arg-type]
            registry_records={"source_fungi": _targets()["source_fungi"]},
        )


def test_reloads_checksum_loaded_source_at_authoring_time(tmp_path: Path) -> None:
    written = _source_result("fungi").write(tmp_path / "source_curation")
    loaded = load_curation_bundle(written.output_directory)
    accepted = written.paths["accepted_registry_records"]
    accepted.write_text(accepted.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="failed current integrity validation",
    ):
        author_registry_records(
            loaded,
            registry_records={"source_fungi": _targets()["source_fungi"]},
        )


def test_rejects_unsupported_product_map_source() -> None:
    source = _source_result("product_maps")

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="does not support source type 'product_maps'",
    ):
        author_registry_records(
            source,
            registry_records={
                "source_product_maps": {
                    "record_id": "authored_product_map",
                    "provenance": _source_provenance("source_product_maps"),
                }
            },
        )


def test_rejects_target_fields_silently_dropped_by_production_loader() -> None:
    target = _targets()["source_fungi"]
    target["proposal_status"] = "review_only_not_registry"

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="silently_dropped_fields=.*proposal_status",
    ):
        author_registry_records(
            _source_result("fungi"),
            registry_records={"source_fungi": target},
        )


def test_rejects_source_identity_conflict() -> None:
    target = _targets()["source_fungi"]
    target["provenance"]["source_entry_ids"] = ["different-source-entry"]

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="conflicts with source identity field 'source_entry_ids'",
    ):
        author_registry_records(
            _source_result("fungi"),
            registry_records={"source_fungi": target},
        )


def test_rejects_unbounded_or_validated_target_maturity() -> None:
    target = _targets()["source_fungi"]
    target["maturity"] = "scientifically_validated"

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="authoring cannot claim validated or unrestricted maturity",
    ):
        author_registry_records(
            _source_result("fungi"),
            registry_records={"source_fungi": target},
        )


def test_revalidates_source_proposal_schema_instead_of_trusting_result_type() -> None:
    result = _source_result("fungi")
    source = result.records[0]
    proposed = deepcopy(dict(source.proposed_record))
    proposed.pop("scientific_name")
    spoofed = replace(
        result,
        records=(replace(source, proposed_record=proposed),),
    )

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="not reviewable.*missing required fields: scientific_name",
    ):
        author_registry_records(
            spoofed,
            registry_records={"source_fungi": _targets()["source_fungi"]},
        )


def test_result_integrity_detects_target_tampering() -> None:
    result = _author_all()
    first = result.records[0]
    changed = deepcopy(dict(first.proposed_record))
    changed["name"] = "Changed after authoring"
    tampered = replace(
        result,
        records=(replace(first, proposed_record=changed), *result.records[1:]),
    )

    with pytest.raises(
        RegistryRecordAuthoringError,
        match="changed after construction",
    ):
        tampered.verify_integrity()
    with pytest.raises(RegistryPromotionPlanError, match="changed after construction"):
        plan_registry_promotion(tampered, REGISTRY_INDEX)


def test_generic_curation_result_cannot_spoof_authoring_namespace() -> None:
    result = _author_all()
    spoofed = CurationResult(
        source_query=result.source_query,
        source_snapshot_path=result.source_snapshot_path,
        proposal_limitations=result.proposal_limitations,
        records=result.records,
    )

    with pytest.raises(
        RegistryPromotionPlanError,
        match="require CuratorAuthoredRegistryResult",
    ):
        plan_registry_promotion(spoofed, REGISTRY_INDEX)


def test_registry_authoring_is_available_from_root_api() -> None:
    assert fungal_model.author_registry_records is author_registry_records
