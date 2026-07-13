from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

import fungal_model
import fungal_model.api.registry_promotion as promotion_module
from fungal_model import (
    CurationResult,
    RegistryPromotionPlan,
    RegistryPromotionPlanError,
    plan_registry_promotion,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    CurationRecord,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_REGISTRY = ROOT / "data_registry"


def _copy_registry(tmp_path: Path) -> Path:
    registry = tmp_path / "registry"
    shutil.copytree(DATA_REGISTRY, registry)
    return registry / "registry_index.yml"


def _registry_snapshot(registry_index: Path) -> dict[str, bytes]:
    root = registry_index.parent
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _synthetic_parameter(record_id: str = "synthetic_promotion_parameter") -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": "Synthetic promotion-plan parameter",
        "maturity": "synthetic_fixture",
        "provenance": {
            "source": "Synthetic software fixture.",
            "confidence_level": "testing",
            "notes": "Not scientific or validation data.",
        },
        "parameter_symbol": "synthetic_plan_rate",
        "process_type": "first_order",
        "enzyme_class": None,
        "substrate_class": "synthetic_fixture",
        "fungus_id": None,
        "substrate_id": None,
        "environment_id": None,
        "value": {
            "kind": "exact",
            "units": "1 / second",
            "value": 1.0,
            "lower": None,
            "upper": None,
            "distribution": None,
            "parameters": {},
            "source": "Synthetic software fixture.",
            "confidence_level": "testing",
            "notes": "Not scientific or validation data.",
        },
        "range_scope": "synthetic_fixture",
        "range_interpretation": "software_test_only",
        "allowed_use": "synthetic_fixture_only",
        "notes": "Synthetic software fixture for registry promotion-plan tests only.",
    }


def _curation_record(
    record_type: str,
    payload: dict[str, Any],
    *,
    decision: str = "accept",
    explicit_decision: bool = True,
    missing_fields: tuple[str, ...] = (),
    reasons: tuple[str, ...] = (),
    source_provenance: dict[str, Any] | None = None,
    curation_date: str | None = None,
) -> CurationRecord:
    return CurationRecord(
        record_type=record_type,
        record_id=str(payload["record_id"]),
        proposed_record=deepcopy(payload),
        classification="eligible_for_review",
        missing_fields=missing_fields,
        reasons=reasons,
        decision=decision,  # type: ignore[arg-type]
        explicit_decision=explicit_decision,
        curator="Synthetic Test Curator" if explicit_decision else None,
        decision_reason=(
            "Synthetic record accepted for promotion-plan software testing."
            if explicit_decision
            else ""
        ),
        curation_date=(
            curation_date
            if curation_date is not None
            else "2026-07-13" if explicit_decision else ""
        ),
        allowed_use=(
            CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION
            if decision == "accept"
            else CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY
        ),
        limitations=("Synthetic software fixture; no scientific validation is claimed.",),
        source_provenance=(
            {
                "source_database": "synthetic_fixture",
                "source_entry_ids": ["fixture-1"],
                "source_snapshot_path": "synthetic/software/fixture.json",
            }
            if source_provenance is None
            else deepcopy(source_provenance)
        ),
    )


def _curation_result(*records: CurationRecord) -> CurationResult:
    return CurationResult(
        source_query="synthetic software fixture",
        source_snapshot_path="synthetic/software/fixture.json",
        proposal_limitations=("Synthetic software fixture; not scientific data.",),
        records=tuple(records),
    )


def _read_target_records(registry_index: Path, key: str) -> tuple[Path, dict[str, Any]]:
    index = yaml.safe_load(registry_index.read_text(encoding="utf-8"))
    target = registry_index.parent / index["records"][key]
    return target, yaml.safe_load(target.read_text(encoding="utf-8"))


def _write_index(registry_index: Path, payload: dict[str, Any]) -> None:
    registry_index.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _bundle_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_schema_valid_parameter_is_addable_without_registry_mutation(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    before = _registry_snapshot(registry_index)
    payload = _synthetic_parameter()
    result = _curation_result(_curation_record("parameter_records", payload))

    plan = plan_registry_promotion(result, registry_index=registry_index)

    assert isinstance(plan, RegistryPromotionPlan)
    assert plan.summary() == {
        "schema_version": "2.0.0",
        "accepted_records_considered": 1,
        "addable_count": 1,
        "exact_duplicate_count": 0,
        "conflict_count": 0,
        "blocked_unsupported_count": 0,
        "prospective_file_count": 1,
        "prospective_registry_validated": True,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "apply_available": True,
        "apply_policy": "digest_confirmed_transactional_registry_root_swap",
        "version_policy": "strict_next_numeric_patch_version",
    }
    candidate = plan.candidates[0]
    assert candidate.registry_key == "parameters"
    assert candidate.classification == "addable"
    target_path = candidate.target_path
    assert target_path == registry_index.parent / "parameters/parameter_records.yml"
    assert target_path is not None
    assert candidate.before_sha256 == hashlib.sha256(target_path.read_bytes()).hexdigest()
    assert candidate.after_sha256 == plan.prospective_files[0].after_sha256
    expected_promoted = deepcopy(payload)
    expected_promoted["provenance"]["fungmod_curation"] = {
        "curator": "Synthetic Test Curator",
        "curation_date": "2026-07-13",
        "decision": "accept",
        "decision_reason": "Synthetic record accepted for promotion-plan software testing.",
        "limitations": ["Synthetic software fixture; no scientific validation is claimed."],
        "source_provenance": {
            "source_database": "synthetic_fixture",
            "source_entry_ids": ["fixture-1"],
            "source_snapshot_path": "synthetic/software/fixture.json",
        },
        "allowed_use_decision": CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    }
    assert candidate.target_record == expected_promoted
    assert plan.before_registry_digest != plan.prospective_registry_digest

    prospective = yaml.safe_load(plan.prospective_files[0].content)
    assert prospective["record_type"] == "parameters"
    assert prospective["records"][-1] == expected_promoted
    assert _registry_snapshot(registry_index) == before


def test_plan_and_review_bundle_are_byte_for_byte_registry_immutable(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    before = _registry_snapshot(registry_index)
    result = _curation_result(
        _curation_record("parameter_records", _synthetic_parameter())
    )

    plan = plan_registry_promotion(result, registry_index=registry_index)
    write_result = plan.write(tmp_path / "review_bundle")

    assert write_result.paths["promotion_plan"].is_file()
    assert write_result.paths["candidate_classifications"].is_file()
    assert write_result.paths["prospective:parameters/parameter_records.yml"].is_file()
    assert _registry_snapshot(registry_index) == before


def test_exact_duplicate_is_a_no_op(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    _, target = _read_target_records(registry_index, "parameters")
    existing = deepcopy(target["records"][0])
    result = _curation_result(_curation_record("parameter_records", existing))

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "exact_duplicate"
    assert candidate.reason == "exact_record_content_already_present_no_op"
    assert candidate.before_sha256 == candidate.after_sha256
    assert plan.prospective_files == ()
    assert plan.before_registry_digest == plan.prospective_registry_digest
    assert plan.summary()["apply_available"] is False


@pytest.mark.parametrize("candidate_value", [True, 1], ids=["bool", "int"])
def test_non_float_scalar_is_not_an_exact_duplicate_of_raw_float_content(
    tmp_path: Path,
    candidate_value: bool | int,
) -> None:
    registry_index = _copy_registry(tmp_path)
    _, target = _read_target_records(registry_index, "parameters")
    existing = next(
        deepcopy(record)
        for record in target["records"]
        if type(record.get("value", {}).get("value")) is float
        and record["value"]["value"] == 1.0
    )
    existing["value"]["value"] = candidate_value
    result = _curation_result(_curation_record("parameter_records", existing))

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "conflict"
    assert candidate.reason == "record_id_already_exists_with_different_content_no_overwrite"
    assert plan.prospective_files == ()


def test_same_id_with_different_content_is_conflict_and_never_overwritten(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    before = _registry_snapshot(registry_index)
    _, target = _read_target_records(registry_index, "parameters")
    conflicting = deepcopy(target["records"][0])
    conflicting["name"] = "Different synthetic conflict name"
    result = _curation_result(_curation_record("parameter_records", conflicting))

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "conflict"
    assert candidate.reason == "record_id_already_exists_with_different_content_no_overwrite"
    assert candidate.after_sha256 is None
    assert plan.prospective_files == ()
    assert plan.summary()["apply_available"] is False
    assert _registry_snapshot(registry_index) == before


def test_product_map_is_blocked_pending_destination_contract(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    product_map = {
        "record_id": "synthetic_product_map",
        "product_map_type": "synthetic_fixture",
    }
    result = _curation_result(_curation_record("product_maps", product_map))

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "blocked_unsupported"
    assert candidate.reason == "unsupported_pending_destination_contract"
    assert candidate.registry_key is None
    assert candidate.target_path is None
    assert plan.prospective_files == ()
    assert plan.summary()["apply_available"] is False


def test_apply_available_allows_addable_with_exact_duplicate_only(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    _, target = _read_target_records(registry_index, "parameters")
    exact_duplicate = deepcopy(target["records"][0])
    plan = plan_registry_promotion(
        _curation_result(
            _curation_record("parameter_records", _synthetic_parameter()),
            _curation_record("parameter_records", exact_duplicate),
        ),
        registry_index=registry_index,
    )

    assert {item.classification for item in plan.candidates} == {
        "addable",
        "exact_duplicate",
    }
    assert plan.summary()["apply_available"] is True


def test_apply_available_is_false_when_addable_coexists_with_conflict(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    _, target = _read_target_records(registry_index, "parameters")
    conflict = deepcopy(target["records"][0])
    conflict["name"] = "Conflicting record that forbids the whole apply set"
    plan = plan_registry_promotion(
        _curation_result(
            _curation_record("parameter_records", _synthetic_parameter()),
            _curation_record("parameter_records", conflict),
        ),
        registry_index=registry_index,
    )

    assert {item.classification for item in plan.candidates} == {
        "addable",
        "conflict",
    }
    assert plan.summary()["apply_available"] is False


@pytest.mark.parametrize("written_bundle", [False, True])
@pytest.mark.parametrize(
    ("target_identity", "curation_identity", "conflicting_field"),
    [
        (
            {"source_database": "other_database"},
            {
                "source_database": "synthetic_fixture",
                "source_entry_ids": ["fixture-1"],
                "source_snapshot_path": "synthetic/software/fixture.json",
            },
            "source_database",
        ),
        (
            {"source_entry_id": "other-entry"},
            {
                "source_database": "synthetic_fixture",
                "source_entry_ids": ["fixture-1"],
                "source_snapshot_path": "synthetic/software/fixture.json",
            },
            "source_entry_ids",
        ),
        (
            {"source_snapshot_path": "other/snapshot.json"},
            {
                "source_database": "synthetic_fixture",
                "source_entry_ids": ["fixture-1"],
                "source_snapshot_path": "synthetic/software/fixture.json",
            },
            "source_snapshot_path",
        ),
        (
            {"source_url": "https://example.test/other"},
            {
                "source_database": "synthetic_fixture",
                "source_entry_ids": ["fixture-1"],
                "source_snapshot_path": "",
                "source_url": "https://example.test/fixture-1",
            },
            "source_url",
        ),
    ],
    ids=["database", "entry-ids", "snapshot", "url"],
)
def test_contradictory_target_and_curation_source_identity_is_blocked(
    tmp_path: Path,
    written_bundle: bool,
    target_identity: dict[str, Any],
    curation_identity: dict[str, Any],
    conflicting_field: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    payload = _synthetic_parameter()
    payload["provenance"].update(target_identity)
    result = _curation_result(
        _curation_record(
            "parameter_records",
            payload,
            source_provenance=curation_identity,
        )
    )
    curation_input: CurationResult | Path = result
    if written_bundle:
        curation_input = result.write(tmp_path / "curation_bundle").output_directory

    plan = plan_registry_promotion(curation_input, registry_index=registry_index)

    assert plan.candidates[0].classification == "blocked_unsupported"
    assert plan.candidates[0].reason == (
        f"curation_source_identity_conflict: {conflicting_field}"
    )
    assert plan.summary()["apply_available"] is False
    assert plan.prospective_files == ()


def test_singular_and_plural_source_entry_identity_normalize_exactly(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    payload = _synthetic_parameter()
    payload["provenance"].update(
        {
            "source_database": "synthetic_fixture",
            "source_entry_id": "fixture-1",
            "source_snapshot_path": "synthetic/software/fixture.json",
        }
    )

    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", payload)),
        registry_index=registry_index,
    )

    assert plan.candidates[0].classification == "addable"
    assert plan.summary()["apply_available"] is True


def test_rejected_deferred_and_implicit_records_are_not_considered(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    accepted = _curation_record("parameter_records", _synthetic_parameter("accepted_fixture"))
    rejected = _curation_record(
        "parameter_records",
        _synthetic_parameter("rejected_fixture"),
        decision="reject",
    )
    deferred = _curation_record(
        "parameter_records",
        _synthetic_parameter("deferred_fixture"),
        decision="defer",
    )
    implicit = _curation_record(
        "parameter_records",
        _synthetic_parameter("implicit_fixture"),
        decision="defer",
        explicit_decision=False,
    )

    plan = plan_registry_promotion(
        _curation_result(accepted, rejected, deferred, implicit),
        registry_index=registry_index,
    )

    assert [item.record_id for item in plan.candidates] == ["accepted_fixture"]


def test_written_owned_curation_bundle_maps_parameter_records_and_verifies_artifacts(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    result = _curation_result(
        _curation_record("parameter_records", _synthetic_parameter())
    )
    curation_bundle = result.write(tmp_path / "curation_bundle").output_directory

    plan = plan_registry_promotion(curation_bundle, registry_index=registry_index)

    assert plan.input_kind == "written_curation_bundle"
    assert plan.candidates[0].record_type == "parameter_records"
    assert plan.candidates[0].registry_key == "parameters"
    promoted = deepcopy(plan.candidates[0].target_record)
    audit = promoted["provenance"].pop("fungmod_curation")
    assert promoted == _synthetic_parameter()
    assert audit["curator"] == "Synthetic Test Curator"
    assert audit["source_provenance"]["source_entry_ids"] == ["fixture-1"]
    assert plan.candidates[0].curation_metadata["decision"] == "accept"


@pytest.mark.parametrize("written_bundle", [False, True])
def test_accepted_curation_with_blockers_is_rejected_for_memory_and_owned_bundle(
    tmp_path: Path,
    written_bundle: bool,
) -> None:
    registry_index = _copy_registry(tmp_path)
    before = _registry_snapshot(registry_index)
    result = _curation_result(
        _curation_record(
            "parameter_records",
            _synthetic_parameter(),
            missing_fields=("value.units",),
            reasons=("synthetic unresolved blocker",),
        )
    )
    curation_input: CurationResult | Path = result
    if written_bundle:
        curation_input = result.write(tmp_path / "blocked_curation_bundle").output_directory

    with pytest.raises(
        RegistryPromotionPlanError,
        match="requires empty curation missing_fields and reasons",
    ):
        plan_registry_promotion(curation_input, registry_index=registry_index)

    assert _registry_snapshot(registry_index) == before


@pytest.mark.parametrize("written_bundle", [False, True])
def test_accepted_curation_with_empty_provenance_is_rejected_for_memory_and_owned_bundle(
    tmp_path: Path,
    written_bundle: bool,
) -> None:
    registry_index = _copy_registry(tmp_path)
    before = _registry_snapshot(registry_index)
    result = _curation_result(
        _curation_record(
            "parameter_records",
            _synthetic_parameter(),
            source_provenance={},
        )
    )
    curation_input: CurationResult | Path = result
    if written_bundle:
        curation_input = result.write(tmp_path / "provenance_curation_bundle").output_directory

    with pytest.raises(
        RegistryPromotionPlanError,
        match="incomplete source provenance.*source_database.*source_entry_ids",
    ):
        plan_registry_promotion(curation_input, registry_index=registry_index)

    assert _registry_snapshot(registry_index) == before


@pytest.mark.parametrize("written_bundle", [False, True])
def test_accepted_curation_with_invalid_iso_date_is_rejected_for_both_inputs(
    tmp_path: Path,
    written_bundle: bool,
) -> None:
    registry_index = _copy_registry(tmp_path)
    before = _registry_snapshot(registry_index)
    result = _curation_result(
        _curation_record(
            "parameter_records",
            _synthetic_parameter(),
            curation_date="not-an-iso-date",
        )
    )
    curation_input: CurationResult | Path = result
    if written_bundle:
        curation_input = result.write(tmp_path / "dated_curation_bundle").output_directory

    with pytest.raises(
        RegistryPromotionPlanError,
        match="requires curation_date in YYYY-MM-DD form",
    ):
        plan_registry_promotion(curation_input, registry_index=registry_index)

    assert _registry_snapshot(registry_index) == before


def test_tampered_declared_written_bundle_artifact_is_rejected_before_records_are_trusted(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    result = _curation_result(
        _curation_record("parameter_records", _synthetic_parameter())
    )
    curation_bundle = result.write(tmp_path / "curation_bundle").output_directory
    report = curation_bundle / "curation_report.md"
    report.write_text(report.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(
        RegistryPromotionPlanError,
        match="checksum mismatch for 'curation_report.md'",
    ):
        plan_registry_promotion(curation_bundle, registry_index=registry_index)


@pytest.mark.parametrize(
    "payload, match",
    [
        ("{not-json", "Malformed curation manifest"),
        (
            json.dumps({"kind": "not_owned", "schema_version": "1.0.0"}),
            "not an owned curation bundle",
        ),
    ],
)
def test_malformed_or_non_owned_written_bundle_is_rejected(
    tmp_path: Path,
    payload: str,
    match: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    bundle = tmp_path / "bad_bundle"
    bundle.mkdir()
    (bundle / "curation_manifest.json").write_text(payload, encoding="utf-8")

    with pytest.raises(RegistryPromotionPlanError, match=match):
        plan_registry_promotion(bundle, registry_index=registry_index)


def test_registry_index_path_traversal_is_rejected(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    traversal = registry_index.parent / "nested" / ".." / "registry_index.yml"

    with pytest.raises(RegistryPromotionPlanError, match="index path traversal"):
        plan_registry_promotion(_curation_result(), registry_index=traversal)


def test_registry_index_symlink_destination_is_rejected(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    index = yaml.safe_load(registry_index.read_text(encoding="utf-8"))
    original = registry_index.parent / index["records"]["parameters"]
    link = registry_index.parent / "parameters/parameter_records_link.yml"
    link.symlink_to(original)
    index["records"]["parameters"] = "parameters/parameter_records_link.yml"
    _write_index(registry_index, index)

    with pytest.raises(RegistryPromotionPlanError, match="contains a symlink component"):
        plan_registry_promotion(_curation_result(), registry_index=registry_index)


@pytest.mark.parametrize(
    "destination, match",
    [
        ("../outside.yml", "destination traversal"),
        ("ABSOLUTE", "must be relative to the registry root"),
    ],
)
def test_registry_index_out_of_root_destinations_are_rejected(
    tmp_path: Path,
    destination: str,
    match: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    index = yaml.safe_load(registry_index.read_text(encoding="utf-8"))
    outside = tmp_path / "outside.yml"
    outside.write_text("kind: fungmod_registry_records\nrecord_type: parameters\nrecords: []\n", encoding="utf-8")
    index["records"]["parameters"] = str(outside) if destination == "ABSOLUTE" else destination
    _write_index(registry_index, index)

    with pytest.raises(RegistryPromotionPlanError, match=match):
        plan_registry_promotion(_curation_result(), registry_index=registry_index)


def test_target_loader_schema_failure_is_blocked_unsupported(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    invalid = _synthetic_parameter()
    invalid["name"] = ""
    result = _curation_result(_curation_record("parameter_records", invalid))

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "blocked_unsupported"
    assert candidate.reason.startswith("target_schema_validation_failed: RegistryValidationError:")
    assert "Registry record name is required" in candidate.reason
    assert plan.prospective_files == ()


def test_target_loader_fidelity_blocks_silently_ignored_unknown_field(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    candidate_payload = _synthetic_parameter()
    candidate_payload["unknown_production_field"] = "would be silently dropped"
    result = _curation_result(
        _curation_record("parameter_records", candidate_payload)
    )

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "blocked_unsupported"
    assert candidate.reason.startswith("target_loader_fidelity_failed:")
    assert "silently_dropped_fields=['unknown_production_field']" in candidate.reason
    assert plan.prospective_files == ()


def test_target_loader_fidelity_blocks_omitted_defaulted_production_field(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    candidate_payload = _synthetic_parameter()
    del candidate_payload["range_scope"]
    result = _curation_result(
        _curation_record("parameter_records", candidate_payload)
    )

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "blocked_unsupported"
    assert candidate.reason.startswith("target_loader_fidelity_failed:")
    assert "synthesized_or_defaulted_fields=['range_scope']" in candidate.reason
    assert plan.prospective_files == ()


@pytest.mark.parametrize("candidate_value", [True, 1], ids=["bool", "int"])
def test_target_loader_fidelity_blocks_scalar_converted_to_float(
    tmp_path: Path,
    candidate_value: bool | int,
) -> None:
    registry_index = _copy_registry(tmp_path)
    candidate_payload = _synthetic_parameter()
    candidate_payload["value"]["value"] = candidate_value
    result = _curation_result(
        _curation_record("parameter_records", candidate_payload)
    )

    plan = plan_registry_promotion(result, registry_index=registry_index)

    candidate = plan.candidates[0]
    assert candidate.classification == "blocked_unsupported"
    assert candidate.reason.startswith("target_loader_fidelity_failed:")
    assert "changed_fields=['value.value']" in candidate.reason
    assert plan.prospective_files == ()


def test_prospective_full_registry_validation_failure_aborts_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    result = _curation_result(
        _curation_record("parameter_records", _synthetic_parameter())
    )
    real_load_registry = promotion_module.load_registry

    def fail_only_full_stage(path: str | Path):
        if "fungmod-registry-promotion-full-" in str(path):
            raise ValueError("synthetic prospective full-registry validator failure")
        return real_load_registry(path)

    monkeypatch.setattr(promotion_module, "load_registry", fail_only_full_stage)

    with pytest.raises(
        RegistryPromotionPlanError,
        match="Prospective full-registry validation failed.*synthetic prospective",
    ):
        plan_registry_promotion(result, registry_index=registry_index)


def test_plan_digest_and_written_artifacts_are_deterministic(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    result = _curation_result(
        _curation_record("parameter_records", _synthetic_parameter())
    )

    first = plan_registry_promotion(result, registry_index=registry_index)
    second = plan_registry_promotion(result, registry_index=registry_index)
    first_output = first.write(tmp_path / "first_plan").output_directory
    second_output = second.write(tmp_path / "second_plan").output_directory

    assert first.plan_digest == second.plan_digest
    assert first.prospective_registry_digest == second.prospective_registry_digest
    assert first.prospective_files == second.prospective_files
    assert _bundle_bytes(first_output) == _bundle_bytes(second_output)


def test_mutated_nested_plan_mapping_is_rejected_before_any_output_is_written(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(
            _curation_record("parameter_records", _synthetic_parameter())
        ),
        registry_index=registry_index,
    )
    target_record = plan.candidates[0].target_record
    assert isinstance(target_record, dict)
    target_record["name"] = "Mutated after plan construction"
    output = tmp_path / "mutated_plan_output"

    with pytest.raises(
        RegistryPromotionPlanError,
        match="contents changed after construction",
    ):
        plan.write(output)

    assert not output.exists()


def test_safe_owned_output_replacement_removes_stale_files_and_rejects_unowned(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(
            _curation_record("parameter_records", _synthetic_parameter())
        ),
        registry_index=registry_index,
    )
    output = tmp_path / "promotion_plan"
    first = plan.write(output)
    first_bytes = _bundle_bytes(first.output_directory)
    (output / "stale.txt").write_text("stale", encoding="utf-8")

    second = plan.write(output)

    assert not (output / "stale.txt").exists()
    assert _bundle_bytes(second.output_directory) == first_bytes

    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "keep.txt").write_text("user file", encoding="utf-8")
    with pytest.raises(RegistryPromotionPlanError, match="readable owned promotion-plan manifest"):
        plan.write(unowned)
    assert (unowned / "keep.txt").read_text(encoding="utf-8") == "user file"


def test_plan_write_refuses_registry_root_destination(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(_curation_result(), registry_index=registry_index)

    with pytest.raises(RegistryPromotionPlanError, match="overlaps a registry root"):
        plan.write(registry_index.parent / "review")


def test_plan_write_refuses_owned_output_ancestor_containing_registry(
    tmp_path: Path,
) -> None:
    output = tmp_path / "owned_plan_parent"
    registry_root = output / "registry"
    shutil.copytree(DATA_REGISTRY, registry_root)
    registry_index = registry_root / "registry_index.yml"
    plan = plan_registry_promotion(_curation_result(), registry_index=registry_index)
    (output / "promotion_plan.json").write_text(
        json.dumps(
            {
                "kind": promotion_module.REGISTRY_PROMOTION_PLAN_MANIFEST_KIND,
                "schema_version": promotion_module.REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION,
            }
        ),
        encoding="utf-8",
    )
    before = _registry_snapshot(registry_index)

    with pytest.raises(RegistryPromotionPlanError, match="overlaps a registry root"):
        plan.write(output)

    assert registry_index.is_file()
    assert _registry_snapshot(registry_index) == before


def test_public_export_exposes_plan_api_without_a_mutating_plan_method() -> None:
    assert fungal_model.plan_registry_promotion is plan_registry_promotion
    assert fungal_model.RegistryPromotionPlan is RegistryPromotionPlan
    assert not hasattr(RegistryPromotionPlan, "apply")
