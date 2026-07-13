from __future__ import annotations

import hashlib
import json
import os
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

import fungal_model
import fungal_model.api.registry_promotion as promotion_module
from fungal_model import (
    CurationResult,
    RegistryPromotionAppliedFile,
    RegistryPromotionApplyError,
    RegistryPromotionApplyResult,
    apply_registry_promotion,
    plan_registry_promotion,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CurationRecord,
)
from fungal_model.registry.loaders import load_registry


ROOT = Path(__file__).resolve().parents[1]
DATA_REGISTRY = ROOT / "data_registry"


def _copy_registry(tmp_path: Path) -> Path:
    root = tmp_path / "registry"
    shutil.copytree(DATA_REGISTRY, root)
    return root / "registry_index.yml"


def _snapshot(registry_index: Path) -> dict[str, bytes]:
    root = registry_index.parent
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _synthetic_parameter(record_id: str = "apply_parameter") -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": "Synthetic apply parameter",
        "maturity": "synthetic_fixture",
        "provenance": {
            "source": "Synthetic software fixture.",
            "confidence_level": "testing",
            "notes": "Not scientific or validation data.",
        },
        "parameter_symbol": "synthetic_apply_rate",
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
        "notes": "Synthetic software fixture for transactional apply tests only.",
    }


def _synthetic_fungus(record_id: str = "apply_fungus") -> dict[str, Any]:
    return {
        "record_id": record_id,
        "name": "Synthetic apply fungus",
        "maturity": "synthetic_fixture",
        "provenance": {
            "source": "Synthetic software fixture.",
            "confidence_level": "testing",
            "notes": "Not scientific or validation data.",
        },
        "notes": "Synthetic software fixture for transactional apply tests only.",
        "enzyme_classes": ["synthetic_enzyme_class"],
        "assimilable_products": ["synthetic_product"],
    }


def _curation_record(record_type: str, payload: dict[str, Any]) -> CurationRecord:
    return CurationRecord(
        record_type=record_type,
        record_id=str(payload["record_id"]),
        proposed_record=deepcopy(payload),
        classification="eligible_for_review",
        missing_fields=(),
        reasons=(),
        decision="accept",
        explicit_decision=True,
        curator="Transactional Apply Test Curator",
        decision_reason="Accepted for synthetic transactional apply software testing.",
        curation_date="2026-07-13",
        allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
        limitations=("Synthetic software fixture; no scientific validation is claimed.",),
        source_provenance={
            "source_database": "synthetic_fixture",
            "source_entry_ids": [f"fixture:{payload['record_id']}"],
            "source_snapshot_path": "synthetic/software/apply-fixture.json",
        },
    )


def _curation_result(*records: CurationRecord) -> CurationResult:
    return CurationResult(
        source_query="synthetic transactional apply fixture",
        source_snapshot_path="synthetic/software/apply-fixture.json",
        proposal_limitations=("Synthetic software fixture; not scientific data.",),
        records=tuple(records),
    )


def _parameter_target(registry_index: Path) -> tuple[Path, dict[str, Any]]:
    index = yaml.safe_load(registry_index.read_text(encoding="utf-8"))
    target = registry_index.parent / index["records"]["parameters"]
    return target, yaml.safe_load(target.read_text(encoding="utf-8"))


def _write_index(registry_index: Path, payload: dict[str, Any]) -> None:
    registry_index.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _redigest(plan):
    payload = promotion_module._plan_digest_payload(
        input_kind=plan.input_kind,
        registry_index_path=plan.registry_index_path,
        registry_root=plan.registry_root,
        registry_index_sha256=plan.registry_index_sha256,
        before_registry_digest=plan.before_registry_digest,
        prospective_registry_digest=plan.prospective_registry_digest,
        candidates=plan.candidates,
        prospective_files=plan.prospective_files,
    )
    return replace(plan, plan_digest=promotion_module._sha256_json(payload))


def _assert_no_transaction_debris(registry_index: Path) -> None:
    debris = [
        path.name
        for path in registry_index.parent.parent.iterdir()
        if "promotion-stage" in path.name
        or "promotion-backup" in path.name
        or "fungmod-registry-promotion.lock" in path.name
    ]
    assert debris == []


def test_in_memory_apply_commits_two_record_types_and_preserves_unrelated_files(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    unrelated = registry_index.parent / "operator-notes.txt"
    unrelated.write_bytes(b"preserve this unrelated regular file byte-for-byte\n")
    parameter = _synthetic_parameter()
    fungus = _synthetic_fungus()
    _, parameter_records = _parameter_target(registry_index)
    exact_duplicate = deepcopy(parameter_records["records"][0])
    plan = plan_registry_promotion(
        _curation_result(
            _curation_record("parameter_records", parameter),
            _curation_record("fungi", fungus),
            _curation_record("parameter_records", exact_duplicate),
        ),
        registry_index=registry_index,
    )

    result = apply_registry_promotion(
        plan,
        confirmation_digest=plan.plan_digest,
        new_registry_version="0.1.1",
    )

    assert isinstance(result, RegistryPromotionApplyResult)
    assert result.old_registry_version == "0.1.0"
    assert result.new_registry_version == "0.1.1"
    assert result.plan_digest == plan.plan_digest
    assert result.confirmation_digest == plan.plan_digest
    assert result.to_dict()["plan_digest"] == result.to_dict()["confirmation_digest"]
    assert result.before_registry_digest == plan.before_registry_digest
    assert result.planned_registry_digest == plan.prospective_registry_digest
    assert result.applied_registry_digest != result.planned_registry_digest
    assert result.applied_record_ids == ("apply_fungus", "apply_parameter")
    assert result.exact_duplicate_record_ids == (exact_duplicate["record_id"],)
    assert result.transaction_status == "committed"
    assert result.rollback_status == "not_required"
    assert result.backup_cleanup_status == "complete"
    assert result.production_registry_mutated is True
    assert result.scientific_validation_claimed is False
    assert result.simulation_authorized is False
    assert {item.registry_path for item in result.changed_files} == {
        "fungi/fungi.yml",
        "parameters/parameter_records.yml",
        "registry_index.yml",
    }
    assert all(isinstance(item, RegistryPromotionAppliedFile) for item in result.changed_files)
    assert unrelated.read_bytes() == b"preserve this unrelated regular file byte-for-byte\n"

    runtime = load_registry(registry_index)
    assert runtime.version == "0.1.1"
    runtime_parameter = runtime.parameters[parameter["record_id"]].to_dict()
    audit = runtime_parameter["provenance"].pop("fungmod_curation")
    assert runtime_parameter == parameter
    assert audit == {
        "curator": "Transactional Apply Test Curator",
        "curation_date": "2026-07-13",
        "decision": "accept",
        "decision_reason": "Accepted for synthetic transactional apply software testing.",
        "limitations": ["Synthetic software fixture; no scientific validation is claimed."],
        "source_provenance": {
            "source_database": "synthetic_fixture",
            "source_entry_ids": ["fixture:apply_parameter"],
            "source_snapshot_path": "synthetic/software/apply-fixture.json",
        },
        "allowed_use_decision": CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    }
    assert runtime.parameters[parameter["record_id"]].allowed_use == parameter["allowed_use"]
    _assert_no_transaction_debris(registry_index)


def test_written_plan_bundle_applies_only_with_explicit_current_index(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    bundle = plan.write(tmp_path / "review_bundle").output_directory

    with pytest.raises(RegistryPromotionApplyError, match="requires an explicit current"):
        apply_registry_promotion(
            bundle,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    result = apply_registry_promotion(
        bundle,
        confirmation_digest=plan.plan_digest,
        new_registry_version="0.1.1",
        registry_index=registry_index,
    )
    assert result.applied_record_ids == ("apply_parameter",)
    assert load_registry(registry_index).version == "0.1.1"


@pytest.mark.parametrize(
    "confirmation",
    ["", "0" * 64, b"not-a-string"],
    ids=["empty", "wrong-value", "wrong-type"],
)
def test_confirmation_digest_is_type_and_value_exact(
    tmp_path: Path,
    confirmation: Any,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before = _snapshot(registry_index)

    with pytest.raises(RegistryPromotionApplyError, match="type- and value-exactly"):
        apply_registry_promotion(
            plan,
            confirmation_digest=confirmation,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before


def test_mutated_in_memory_plan_is_rejected_before_lock_or_write(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    target_record = plan.candidates[0].target_record
    assert isinstance(target_record, dict)
    target_record["name"] = "tampered after planning"
    before = _snapshot(registry_index)

    with pytest.raises(RegistryPromotionApplyError, match="contents changed after construction"):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before
    _assert_no_transaction_debris(registry_index)


def test_apply_revalidates_curation_metadata_even_for_a_redigested_plan(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    curation = deepcopy(plan.candidates[0].curation_metadata)
    curation["curation_date"] = "not-an-iso-date"
    candidate = replace(plan.candidates[0], curation_metadata=curation)
    redigested = _redigest(replace(plan, candidates=(candidate,)))
    before = _snapshot(registry_index)

    with pytest.raises(RegistryPromotionApplyError, match="curation_date in YYYY-MM-DD"):
        apply_registry_promotion(
            redigested,
            confirmation_digest=redigested.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before


@pytest.mark.parametrize("tamper_kind", ["checksum", "content_hash", "undeclared"])
def test_written_bundle_tampering_is_rejected(
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    bundle = plan.write(tmp_path / "review_bundle").output_directory
    manifest_path = bundle / "promotion_plan.json"
    if tamper_kind == "checksum":
        report = bundle / "promotion_report.md"
        report.write_text(report.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    elif tamper_kind == "content_hash":
        prospective = bundle / "prospective_registry/parameters/parameter_records.yml"
        prospective.write_text(
            prospective.read_text(encoding="utf-8") + "# tampered\n",
            encoding="utf-8",
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_name = "prospective_registry/parameters/parameter_records.yml"
        manifest["files"][artifact_name] = hashlib.sha256(prospective.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        (bundle / "undeclared.txt").write_text("undeclared", encoding="utf-8")
    before = _snapshot(registry_index)

    with pytest.raises(RegistryPromotionApplyError):
        apply_registry_promotion(
            bundle,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
            registry_index=registry_index,
        )

    assert _snapshot(registry_index) == before


def test_pre_pr47_written_plan_schema_is_explicitly_rejected(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    bundle = plan.write(tmp_path / "review_bundle").output_directory
    manifest_path = bundle / "promotion_plan.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "1.0.0"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(RegistryPromotionApplyError, match="Pre-PR-47.*preview-only"):
        apply_registry_promotion(
            bundle,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
            registry_index=registry_index,
        )


@pytest.mark.parametrize("drift_kind", ["index", "target", "unrelated"])
def test_any_registry_drift_refuses_apply_without_partial_changes(
    tmp_path: Path,
    drift_kind: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(
            _curation_record("parameter_records", _synthetic_parameter()),
            _curation_record("fungi", _synthetic_fungus()),
        ),
        registry_index=registry_index,
    )
    if drift_kind == "index":
        registry_index.write_text(
            registry_index.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
    elif drift_kind == "target":
        target, _ = _parameter_target(registry_index)
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    else:
        unrelated = registry_index.parent / "operator-notes.txt"
        unrelated.write_text("created after planning\n", encoding="utf-8")
    drifted = _snapshot(registry_index)

    with pytest.raises(RegistryPromotionApplyError, match="changed after planning"):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == drifted


def test_source_digest_is_rechecked_inside_the_swap_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    real_commit = promotion_module._commit_staged_registry
    unrelated = registry_index.parent / "late-operator-change.txt"

    def drift_then_commit(**kwargs: Any):
        unrelated.write_text("changed at the commit boundary\n", encoding="utf-8")
        return real_commit(**kwargs)

    monkeypatch.setattr(
        promotion_module,
        "_commit_staged_registry",
        drift_then_commit,
    )

    with pytest.raises(
        RegistryPromotionApplyError,
        match="changed immediately before the transactional swap",
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert load_registry(registry_index).version == "0.1.0"
    assert "apply_parameter" not in load_registry(registry_index).parameters
    assert unrelated.read_text(encoding="utf-8") == "changed at the commit boundary\n"
    _assert_no_transaction_debris(registry_index)


def test_registry_tree_scan_errors_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    real_walk = promotion_module.os.walk

    def fail_registry_walk(
        root: str | Path,
        *,
        topdown: bool,
        onerror,
        followlinks: bool,
    ):
        if Path(root) == registry_index.parent:
            assert topdown is True
            assert followlinks is False
            onerror(PermissionError("injected registry scan failure"))
        yield from real_walk(
            root,
            topdown=topdown,
            onerror=onerror,
            followlinks=followlinks,
        )

    monkeypatch.setattr(promotion_module.os, "walk", fail_registry_walk)

    with pytest.raises(
        promotion_module.RegistryPromotionPlanError,
        match="Cannot inspect registry root safely",
    ):
        plan_registry_promotion(
            _curation_result(
                _curation_record("parameter_records", _synthetic_parameter())
            ),
            registry_index=registry_index,
        )


@pytest.mark.parametrize("candidate_kind", ["conflict", "blocked", "duplicate_only"])
def test_conflict_blocked_and_no_addable_plans_are_refused(
    tmp_path: Path,
    candidate_kind: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    _, target_payload = _parameter_target(registry_index)
    existing = deepcopy(target_payload["records"][0])
    if candidate_kind == "conflict":
        existing["name"] = "conflicting replacement forbidden"
        record = _curation_record("parameter_records", existing)
    elif candidate_kind == "blocked":
        record = _curation_record(
            "product_maps",
            {"record_id": "blocked_product_map", "product_map_type": "synthetic"},
        )
    else:
        record = _curation_record("parameter_records", existing)
    plan = plan_registry_promotion(_curation_result(record), registry_index=registry_index)
    before = _snapshot(registry_index)

    with pytest.raises(RegistryPromotionApplyError):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before


@pytest.mark.parametrize(
    "new_version",
    [
        "0.1.0",
        "0.1.2",
        "0.0.1",
        "1.0.0",
        "0.1.1-alpha",
        "0.1",
        "00.1.1",
        101,
    ],
    ids=["same", "jump", "downgrade", "major", "prerelease", "short", "leading-zero", "non-string"],
)
def test_version_policy_accepts_only_exact_next_numeric_patch(
    tmp_path: Path,
    new_version: Any,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before = _snapshot(registry_index)

    with pytest.raises(RegistryPromotionApplyError):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version=new_version,
        )

    assert _snapshot(registry_index) == before


def test_non_numeric_current_registry_version_is_refused(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    index = yaml.safe_load(registry_index.read_text(encoding="utf-8"))
    index["version"] = "development"
    _write_index(registry_index, index)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )

    with pytest.raises(RegistryPromotionApplyError, match="strict numeric"):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )


@pytest.mark.parametrize("unsafe_kind", ["traversal", "absolute", "symlink", "shared"])
def test_live_index_destination_safety_is_revalidated_at_apply(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    index = yaml.safe_load(registry_index.read_text(encoding="utf-8"))
    if unsafe_kind == "traversal":
        index["records"]["parameters"] = "../outside.yml"
    elif unsafe_kind == "absolute":
        outside = tmp_path / "outside.yml"
        outside.write_text("kind: fungal_registry_records\n", encoding="utf-8")
        index["records"]["parameters"] = str(outside)
    elif unsafe_kind == "shared":
        index["records"]["parameters"] = index["records"]["fungi"]
    else:
        original = registry_index.parent / index["records"]["parameters"]
        link = registry_index.parent / "parameters/unsafe-link.yml"
        link.symlink_to(original)
        index["records"]["parameters"] = "parameters/unsafe-link.yml"
    _write_index(registry_index, index)

    with pytest.raises(RegistryPromotionApplyError):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )


@pytest.mark.parametrize("unsafe_kind", ["unindexed_symlink", "special_file"])
def test_unindexed_unsafe_registry_entries_are_rejected_before_staging(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before_index = registry_index.read_bytes()
    target, _ = _parameter_target(registry_index)
    before_target = target.read_bytes()
    unsafe = registry_index.parent / (
        "unindexed-link.yml" if unsafe_kind == "unindexed_symlink" else "unindexed.fifo"
    )
    if unsafe_kind == "unindexed_symlink":
        unsafe.symlink_to(target)
    else:
        os.mkfifo(unsafe)

    with pytest.raises(RegistryPromotionApplyError, match="unsafe (symlink|special entry)"):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert registry_index.read_bytes() == before_index
    assert target.read_bytes() == before_target
    unsafe.unlink()
    _assert_no_transaction_debris(registry_index)


def test_written_manifest_absolute_target_paths_are_never_write_destinations(
    tmp_path: Path,
) -> None:
    registry_index = _copy_registry(tmp_path)
    outside = tmp_path / "must-not-be-written.yml"
    outside.write_text("outside remains unchanged\n", encoding="utf-8")
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    candidate = replace(plan.candidates[0], target_path=outside)
    prospective = replace(plan.prospective_files[0], target_path=outside)
    relocated_metadata_plan = _redigest(
        replace(plan, candidates=(candidate,), prospective_files=(prospective,))
    )
    bundle = relocated_metadata_plan.write(tmp_path / "review_bundle").output_directory

    result = apply_registry_promotion(
        bundle,
        confirmation_digest=relocated_metadata_plan.plan_digest,
        new_registry_version="0.1.1",
        registry_index=registry_index,
    )

    assert result.applied_record_ids == ("apply_parameter",)
    assert outside.read_text(encoding="utf-8") == "outside remains unchanged\n"


def test_candidate_and_prospective_bundle_inconsistency_is_rejected(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    changed_record = deepcopy(plan.candidates[0].target_record)
    changed_record["name"] = "digest-bound but inconsistent with prospective content"
    candidate = replace(plan.candidates[0], target_record=changed_record)
    inconsistent = _redigest(replace(plan, candidates=(candidate,)))
    bundle = inconsistent.write(tmp_path / "review_bundle").output_directory

    with pytest.raises(RegistryPromotionApplyError, match="does not contain exactly one exact"):
        apply_registry_promotion(
            bundle,
            confirmation_digest=inconsistent.plan_digest,
            new_registry_version="0.1.1",
            registry_index=registry_index,
        )


def test_full_staged_loader_failure_rolls_back_without_debris(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before = _snapshot(registry_index)
    real_load_registry = promotion_module.load_registry

    def fail_staged(path: str | Path):
        if "promotion-stage" in str(path):
            raise ValueError("injected complete staged loader failure")
        return real_load_registry(path)

    monkeypatch.setattr(promotion_module, "load_registry", fail_staged)

    with pytest.raises(RegistryPromotionApplyError, match="Full staged registry validation failed"):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before
    _assert_no_transaction_debris(registry_index)


def test_injected_commit_failure_rolls_back_byte_for_byte_without_debris(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    (registry_index.parent / "unrelated.bin").write_bytes(b"\x00\x01preserve")
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before = _snapshot(registry_index)
    real_replace = promotion_module._replace_registry_path

    def fail_install(source: Path, destination: Path, *, phase: str) -> None:
        if phase == "install":
            raise OSError("injected install rename failure")
        real_replace(source, destination, phase=phase)

    monkeypatch.setattr(promotion_module, "_replace_registry_path", fail_install)

    with pytest.raises(
        RegistryPromotionApplyError,
        match="transaction_status=failed; rollback_status=complete",
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before
    _assert_no_transaction_debris(registry_index)


def test_installed_runtime_verification_failure_rolls_back_before_backup_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before = _snapshot(registry_index)
    real_replace = promotion_module._replace_registry_path
    real_load_registry = promotion_module.load_registry
    installed = False
    fail_once = True

    def track_install(source: Path, destination: Path, *, phase: str) -> None:
        nonlocal installed
        real_replace(source, destination, phase=phase)
        if phase == "install":
            installed = True

    def fail_first_installed_load(path: str | Path):
        nonlocal fail_once
        if installed and fail_once and Path(path).parent == registry_index.parent:
            fail_once = False
            raise ValueError("injected installed runtime verification failure")
        return real_load_registry(path)

    monkeypatch.setattr(promotion_module, "_replace_registry_path", track_install)
    monkeypatch.setattr(promotion_module, "load_registry", fail_first_installed_load)

    with pytest.raises(
        RegistryPromotionApplyError,
        match="transaction_status=failed; rollback_status=complete",
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before
    _assert_no_transaction_debris(registry_index)


def test_backup_cleanup_failure_reports_committed_active_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    real_rmtree = promotion_module.shutil.rmtree

    def fail_backup_cleanup(path: str | Path, *args: Any, **kwargs: Any) -> None:
        if "promotion-backup" in Path(path).name:
            raise OSError("injected backup cleanup failure")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(promotion_module.shutil, "rmtree", fail_backup_cleanup)

    with pytest.raises(
        RegistryPromotionApplyError,
        match=(
            "transaction_status=committed; rollback_status=not_required; "
            "backup_cleanup_status=failed"
        ),
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert load_registry(registry_index).version == "0.1.1"
    assert "apply_parameter" in load_registry(registry_index).parameters
    assert len(list(tmp_path.glob(".registry.promotion-backup-*"))) == 1


def test_stage_cleanup_failure_reports_committed_active_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    real_rmtree = promotion_module.shutil.rmtree

    def fail_stage_cleanup(path: str | Path, *args: Any, **kwargs: Any) -> None:
        if "promotion-stage" in Path(path).name:
            raise OSError("injected stage cleanup failure")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(promotion_module.shutil, "rmtree", fail_stage_cleanup)

    with pytest.raises(
        RegistryPromotionApplyError,
        match=(
            "transaction_status=committed; rollback_status=not_required; "
            "stage_cleanup_status=failed"
        ),
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert load_registry(registry_index).version == "0.1.1"
    assert "apply_parameter" in load_registry(registry_index).parameters
    stage_containers = list(tmp_path.glob(".registry.promotion-stage-*"))
    assert len(stage_containers) == 1
    real_rmtree(stage_containers[0])


def test_lock_cleanup_failure_reports_committed_active_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    lock_path = tmp_path / ".registry.fungmod-registry-promotion.lock"
    real_unlink = Path.unlink

    def fail_lock_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path == lock_path:
            raise OSError("injected lock cleanup failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_lock_unlink)

    with pytest.raises(
        RegistryPromotionApplyError,
        match=(
            "transaction_status=committed; rollback_status=not_required; "
            "lock_cleanup_status=failed"
        ),
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert load_registry(registry_index).version == "0.1.1"
    assert "apply_parameter" in load_registry(registry_index).parameters
    assert lock_path.is_file()
    real_unlink(lock_path)


def test_lock_initialization_cleanup_failure_reports_uncommitted_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before = _snapshot(registry_index)
    lock_path = tmp_path / ".registry.fungmod-registry-promotion.lock"
    real_unlink = Path.unlink

    def fail_write(descriptor: int, payload: bytes) -> int:
        del descriptor, payload
        raise OSError("injected lock initialization failure")

    def fail_lock_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path == lock_path:
            raise OSError("injected initialization cleanup failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(promotion_module.os, "write", fail_write)
    monkeypatch.setattr(Path, "unlink", fail_lock_unlink)

    with pytest.raises(
        RegistryPromotionApplyError,
        match=(
            "transaction_status=not_started; rollback_status=not_required; "
            "lock_cleanup_status=failed"
        ),
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before
    assert lock_path.is_file()
    real_unlink(lock_path)


def test_injected_rollback_failure_is_surfaced_with_backup_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    real_replace = promotion_module._replace_registry_path

    def fail_install_and_rollback(source: Path, destination: Path, *, phase: str) -> None:
        if phase in {"install", "rollback"}:
            raise OSError(f"injected {phase} failure")
        real_replace(source, destination, phase=phase)

    monkeypatch.setattr(
        promotion_module,
        "_replace_registry_path",
        fail_install_and_rollback,
    )

    with pytest.raises(
        RegistryPromotionApplyError,
        match="rollback_status=unproven; backup_path=",
    ):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    backups = list(tmp_path.glob(".registry.promotion-backup-*"))
    assert len(backups) == 1
    assert not registry_index.parent.exists()


def test_existing_single_writer_lock_refuses_concurrent_apply(tmp_path: Path) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    before = _snapshot(registry_index)
    lock = tmp_path / ".registry.fungmod-registry-promotion.lock"
    lock.write_text("held by another writer\n", encoding="utf-8")

    with pytest.raises(RegistryPromotionApplyError, match="single-writer lock is already held"):
        apply_registry_promotion(
            plan,
            confirmation_digest=plan.plan_digest,
            new_registry_version="0.1.1",
        )

    assert _snapshot(registry_index) == before
    lock.unlink()


def test_reentrant_apply_is_refused_while_outer_transaction_can_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_index = _copy_registry(tmp_path)
    plan = plan_registry_promotion(
        _curation_result(_curation_record("parameter_records", _synthetic_parameter())),
        registry_index=registry_index,
    )
    real_validate = promotion_module._validate_version_transition
    nested_errors: list[str] = []

    def validate_with_reentry(index, *, new_registry_version: str):
        try:
            apply_registry_promotion(
                plan,
                confirmation_digest=plan.plan_digest,
                new_registry_version=new_registry_version,
            )
        except RegistryPromotionApplyError as exc:
            nested_errors.append(str(exc))
        return real_validate(index, new_registry_version=new_registry_version)

    monkeypatch.setattr(
        promotion_module,
        "_validate_version_transition",
        validate_with_reentry,
    )

    result = apply_registry_promotion(
        plan,
        confirmation_digest=plan.plan_digest,
        new_registry_version="0.1.1",
    )

    assert result.transaction_status == "committed"
    assert nested_errors and "single-writer lock is already held" in nested_errors[0]
    _assert_no_transaction_debris(registry_index)


def test_apply_api_is_publicly_exported() -> None:
    assert fungal_model.apply_registry_promotion is apply_registry_promotion
    assert fungal_model.RegistryPromotionApplyResult is RegistryPromotionApplyResult
    assert fungal_model.RegistryPromotionApplyError is RegistryPromotionApplyError
    assert fungal_model.RegistryPromotionAppliedFile is RegistryPromotionAppliedFile
