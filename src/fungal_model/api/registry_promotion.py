"""Deterministic plans and transactional apply for accepted curation records."""

from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterator, Literal

import yaml

from fungal_model.api._integrity import (
    CURATION_AUDIT_PROVENANCE_KEY as _CURATION_AUDIT_PROVENANCE_KEY,
    canonicalize as _canonicalize,
    first_symlink_component,
    round_trip_differences as _round_trip_differences,
    sha256_bytes as _sha256_bytes,
    tree_file_hashes,
    TreeIntegrityError,
    type_exact_equal as _type_exact_equal,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CurationError,
    CurationRecord,
    CurationResult,
    LoadedCurationBundle,
    _load_curation_bundle_for_promotion,
    curation_date_is_iso,
    curation_source_provenance_missing,
    load_curation_bundle,
)
from fungal_model.resources import default_registry_path
from fungal_model.api.curator_signatures import (
    AuthenticatedCurationBundle,
    CuratorSignatureError,
)
from fungal_model.api.parameter_record_authoring import (
    PARAMETER_AUTHORING_WORKFLOW,
    CuratorAuthoredParameterResult,
    ParameterRecordAuthoringError,
    validate_authored_parameter_against_registry,
    validate_parameter_authoring_bundle_record,
    validate_parameter_authoring_plan_record,
)
from fungal_model.api.registry_record_authoring import (
    REGISTRY_RECORD_AUTHORING_WORKFLOW,
    CuratorAuthoredRegistryResult,
    RegistryRecordAuthoringError,
    validate_registry_record_authoring_bundle,
    validate_registry_record_authoring_plan_record,
)
from fungal_model.provenance import (
    REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY,
    classify_parameter_provenance,
)
from fungal_model.registry.loaders import load_registry
from fungal_model.registry.store import FungModRegistry


REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION = "2.0.0"
REGISTRY_PROMOTION_PLAN_MANIFEST_KIND = "fungmod_registry_promotion_plan_manifest"

_PROMOTION_APPLY_POLICY = "digest_confirmed_transactional_registry_root_swap"
_PROMOTION_VERSION_POLICY = "strict_next_numeric_patch_version"

PromotionClassification = Literal[
    "addable",
    "exact_duplicate",
    "conflict",
    "blocked_unsupported",
]

_CURATION_TO_REGISTRY_KEY: Mapping[str, str] = {
    "fungi": "fungi",
    "substrates": "substrates",
    "enzyme_classes": "enzyme_classes",
    "parameter_records": "parameters",
    "process_compatibility": "process_compatibility",
    "case_templates": "case_templates",
    "product_maps": "product_maps",
}
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_STRICT_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class RegistryPromotionPlanError(ValueError):
    """Raised when a safe deterministic promotion preview cannot be built."""


class RegistryPromotionApplyError(RegistryPromotionPlanError):
    """Raised when a registry promotion cannot be applied or rolled back safely."""


@dataclass(frozen=True)
class RegistryPromotionCandidate:
    """Classification and exact target details for one explicitly accepted record."""

    record_type: str
    registry_key: str | None
    record_id: str
    classification: PromotionClassification
    reason: str
    target_path: Path | None
    target_registry_path: str | None
    before_sha256: str | None
    after_sha256: str | None
    target_record: Mapping[str, Any]
    curation_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "registry_key": self.registry_key,
            "record_id": self.record_id,
            "classification": self.classification,
            "reason": self.reason,
            "target_path": None if self.target_path is None else str(self.target_path),
            "target_registry_path": self.target_registry_path,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "target_record": _canonicalize(self.target_record),
            "curation_metadata": _canonicalize(self.curation_metadata),
        }


@dataclass(frozen=True)
class ProspectiveRegistryFile:
    """Exact validated post-plan content for one affected registry record file."""

    registry_key: str
    target_path: Path
    target_registry_path: str
    before_sha256: str
    after_sha256: str
    content: str

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "registry_key": self.registry_key,
            "target_path": str(self.target_path),
            "target_registry_path": self.target_registry_path,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
        }
        if include_content:
            payload["content"] = self.content
        return payload


@dataclass(frozen=True)
class RegistryPromotionPlanWriteResult:
    """Paths written for an owned deterministic promotion-plan review bundle."""

    output_directory: Path
    paths: Mapping[str, Path]

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in self.paths.items()}


@dataclass(frozen=True)
class RegistryPromotionAppliedFile:
    """One exact file transition committed by registry promotion."""

    registry_path: str
    before_sha256: str
    after_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "registry_path": self.registry_path,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
        }


@dataclass(frozen=True)
class RegistryPromotionApplyResult:
    """Confirmed result of one complete registry-root transaction."""

    registry_index_path: Path
    registry_root: Path
    old_registry_version: str
    new_registry_version: str
    plan_digest: str
    confirmation_digest: str
    before_registry_digest: str
    planned_registry_digest: str
    applied_registry_digest: str
    changed_files: tuple[RegistryPromotionAppliedFile, ...]
    applied_record_ids: tuple[str, ...]
    exact_duplicate_record_ids: tuple[str, ...]
    transaction_status: Literal["committed"]
    rollback_status: Literal["not_required"]
    backup_cleanup_status: Literal["complete"]
    production_registry_mutated: Literal[True]
    scientific_validation_claimed: Literal[False]
    simulation_authorized: Literal[False]

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_index_path": str(self.registry_index_path),
            "registry_root": str(self.registry_root),
            "old_registry_version": self.old_registry_version,
            "new_registry_version": self.new_registry_version,
            "plan_digest": self.plan_digest,
            "confirmation_digest": self.confirmation_digest,
            "before_registry_digest": self.before_registry_digest,
            "planned_registry_digest": self.planned_registry_digest,
            "applied_registry_digest": self.applied_registry_digest,
            "changed_files": [item.to_dict() for item in self.changed_files],
            "applied_record_ids": list(self.applied_record_ids),
            "exact_duplicate_record_ids": list(self.exact_duplicate_record_ids),
            "transaction_status": self.transaction_status,
            "rollback_status": self.rollback_status,
            "backup_cleanup_status": self.backup_cleanup_status,
            "production_registry_mutated": self.production_registry_mutated,
            "scientific_validation_claimed": self.scientific_validation_claimed,
            "simulation_authorized": self.simulation_authorized,
        }


@dataclass(frozen=True)
class RegistryPromotionPlan:
    """Validated preview whose exact digest can authorize transactional apply."""

    input_kind: Literal["curation_result", "written_curation_bundle"]
    registry_index_path: Path
    registry_root: Path
    registry_index_sha256: str
    before_registry_digest: str
    prospective_registry_digest: str
    candidates: tuple[RegistryPromotionCandidate, ...]
    prospective_files: tuple[ProspectiveRegistryFile, ...]
    plan_digest: str

    @property
    def addable_records(self) -> tuple[RegistryPromotionCandidate, ...]:
        return tuple(item for item in self.candidates if item.classification == "addable")

    @property
    def exact_duplicates(self) -> tuple[RegistryPromotionCandidate, ...]:
        return tuple(item for item in self.candidates if item.classification == "exact_duplicate")

    @property
    def conflicts(self) -> tuple[RegistryPromotionCandidate, ...]:
        return tuple(item for item in self.candidates if item.classification == "conflict")

    @property
    def blocked_records(self) -> tuple[RegistryPromotionCandidate, ...]:
        return tuple(item for item in self.candidates if item.classification == "blocked_unsupported")

    def summary(self) -> dict[str, Any]:
        counts = Counter(item.classification for item in self.candidates)
        return {
            "schema_version": REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION,
            "accepted_records_considered": len(self.candidates),
            "addable_count": counts["addable"],
            "exact_duplicate_count": counts["exact_duplicate"],
            "conflict_count": counts["conflict"],
            "blocked_unsupported_count": counts["blocked_unsupported"],
            "prospective_file_count": len(self.prospective_files),
            "prospective_registry_validated": True,
            "production_registry_mutated": False,
            "scientific_validation_claimed": False,
            "simulation_authorized": False,
            "apply_available": _candidate_set_apply_available(self.candidates),
            "apply_policy": _PROMOTION_APPLY_POLICY,
            "version_policy": _PROMOTION_VERSION_POLICY,
        }

    def write(self, output_dir: str | Path) -> RegistryPromotionPlanWriteResult:
        """Write only an owned review bundle containing this already-validated plan."""

        _verify_plan_digest(self)
        root = _safe_output_path(output_dir, registry_root=self.registry_root)
        root.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(root, label="Promotion-plan output path")
        _validate_replaceable_destination(root)

        staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.promotion-plan-", dir=root.parent))
        try:
            _write_plan_bundle(staging, self)
            _replace_directory(staging, root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        return RegistryPromotionPlanWriteResult(
            output_directory=root,
            paths=_plan_artifact_paths(root, self),
        )


@dataclass(frozen=True)
class _AcceptedRecord:
    record_type: str
    record_id: str
    target_record: Mapping[str, Any]
    curation_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class _TargetFile:
    registry_key: str
    path: Path
    relative_path: str
    before_sha256: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class _RegistryIndex:
    path: Path
    root: Path
    sha256: str
    version: str
    payload: Mapping[str, Any]
    targets: Mapping[str, _TargetFile]


@dataclass
class _ApplyTransactionState:
    transaction_status: Literal["not_started", "failed", "committed"] = "not_started"
    rollback_status: Literal["not_required", "complete", "unproven"] = "not_required"


def _candidate_set_apply_available(
    candidates: Sequence[RegistryPromotionCandidate],
) -> bool:
    classifications = {item.classification for item in candidates}
    return (
        "addable" in classifications
        and "conflict" not in classifications
        and "blocked_unsupported" not in classifications
    )


def plan_registry_promotion(
    curation_bundle_or_result: (
        CurationResult | AuthenticatedCurationBundle | str | Path
    ),
    registry_index: str | Path = "data_registry/registry_index.yml",
) -> RegistryPromotionPlan:
    """Plan accepted-record registry changes without mutating registry files.

    Written curation inputs must be owned CURATION-001 bundles. Every artifact
    declared by their manifest is checksum-verified before accepted records are
    read. Only explicit accepted decisions are considered.
    """

    input_kind, accepted = _accepted_records(curation_bundle_or_result)
    index = _load_registry_index(registry_index)
    _validate_current_registry(index)
    before_registry_digest = _registry_digest(index, overrides={})

    seen_ids: set[str] = set()
    candidates: list[RegistryPromotionCandidate] = []
    accepted_by_key: dict[str, list[_AcceptedRecord]] = {}

    for item in sorted(accepted, key=lambda value: (value.record_type, value.record_id)):
        if item.record_id in seen_ids:
            raise RegistryPromotionPlanError(
                f"Accepted curation input contains duplicate record id {item.record_id!r}."
            )
        seen_ids.add(item.record_id)

        provenance = item.target_record.get("provenance")
        if (
            isinstance(provenance, Mapping)
            and REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY in provenance
        ):
            try:
                validate_registry_record_authoring_plan_record(
                    item.record_type,
                    item.target_record,
                    item.curation_metadata,
                )
            except RegistryRecordAuthoringError as exc:
                raise RegistryPromotionPlanError(
                    f"Authored registry record {item.record_id!r} failed planning "
                    f"revalidation: {exc}"
                ) from exc
        if item.record_type == "parameter_records" and classify_parameter_provenance(
            provenance if isinstance(provenance, Mapping) else None,
            curation_metadata=item.curation_metadata,
        ) == "parameter_bridge":
            try:
                validate_authored_parameter_against_registry(
                    item.target_record,
                    registry_index=index.path,
                )
            except ParameterRecordAuthoringError as exc:
                raise RegistryPromotionPlanError(
                    f"Authored parameter record {item.record_id!r} failed planning-registry "
                    f"revalidation: {exc}"
                ) from exc

        registry_key = _CURATION_TO_REGISTRY_KEY.get(item.record_type)
        if registry_key is None:
            candidates.append(
                _candidate(
                    item,
                    classification="blocked_unsupported",
                    reason="unsupported_curation_record_type",
                )
            )
            continue
        target = index.targets.get(registry_key)
        if target is None:
            candidates.append(
                _candidate(
                    item,
                    registry_key=registry_key,
                    classification="blocked_unsupported",
                    reason="registry_index_destination_missing",
                )
            )
            continue

        try:
            _validate_source_identity_consistency(
                item.record_id,
                target_record=item.target_record,
                curation_metadata=item.curation_metadata,
            )
        except RegistryPromotionPlanError as exc:
            candidates.append(
                _candidate(
                    item,
                    registry_key=registry_key,
                    classification="blocked_unsupported",
                    reason=str(exc),
                    target=target,
                )
            )
            continue

        existing = _record_by_id(target, item.record_id)
        if existing is not None:
            classification: PromotionClassification
            reason: str
            after_sha256: str | None
            if _type_exact_equal(existing, item.target_record):
                classification = "exact_duplicate"
                reason = "exact_record_content_already_present_no_op"
                after_sha256 = target.before_sha256
            else:
                classification = "conflict"
                reason = "record_id_already_exists_with_different_content_no_overwrite"
                after_sha256 = None
            candidates.append(
                _candidate(
                    item,
                    registry_key=registry_key,
                    classification=classification,
                    reason=reason,
                    target=target,
                    after_sha256=after_sha256,
                )
            )
            continue

        try:
            promoted_item = replace(
                item,
                target_record=_target_record_with_curation_audit(item),
            )
        except RegistryPromotionPlanError as exc:
            candidates.append(
                _candidate(
                    item,
                    registry_key=registry_key,
                    classification="blocked_unsupported",
                    reason=str(exc),
                    target=target,
                )
            )
            continue

        candidate_content = _merged_target_content(target, (promoted_item.target_record,))
        validation_error = _staged_candidate_validation_error(
            index,
            target=target,
            candidate=promoted_item,
            overrides={target.relative_path: candidate_content},
        )
        if validation_error is not None:
            candidates.append(
                _candidate(
                    promoted_item,
                    registry_key=registry_key,
                    classification="blocked_unsupported",
                    reason=validation_error,
                    target=target,
                )
            )
            continue

        candidates.append(
            _candidate(
                promoted_item,
                registry_key=registry_key,
                classification="addable",
                reason="accepted_record_is_addable_without_overwrite",
                target=target,
            )
        )
        accepted_by_key.setdefault(registry_key, []).append(promoted_item)

    prospective_files: list[ProspectiveRegistryFile] = []
    overrides: dict[str, str] = {}
    for registry_key in sorted(accepted_by_key):
        target = index.targets[registry_key]
        additions = tuple(
            item.target_record
            for item in sorted(accepted_by_key[registry_key], key=lambda value: value.record_id)
        )
        content = _merged_target_content(target, additions)
        after_sha256 = _sha256_bytes(content.encode("utf-8"))
        overrides[target.relative_path] = content
        prospective_files.append(
            ProspectiveRegistryFile(
                registry_key=registry_key,
                target_path=target.path,
                target_registry_path=target.relative_path,
                before_sha256=target.before_sha256,
                after_sha256=after_sha256,
                content=content,
            )
        )

    full_validation_error = _staged_registry_validation_error(
        index,
        overrides=overrides,
        prefix="fungmod-registry-promotion-full-",
    )
    if full_validation_error is not None:
        raise RegistryPromotionPlanError(
            f"Prospective full-registry validation failed: {full_validation_error}"
        )

    after_by_key = {item.registry_key: item.after_sha256 for item in prospective_files}
    candidates = [
        replace(item, after_sha256=after_by_key[item.registry_key])
        if item.classification == "addable" and item.registry_key is not None
        else item
        for item in candidates
    ]
    prospective_registry_digest = _registry_digest(index, overrides=overrides)
    payload = _plan_digest_payload(
        input_kind=input_kind,
        registry_index_path=index.path,
        registry_root=index.root,
        registry_index_sha256=index.sha256,
        before_registry_digest=before_registry_digest,
        prospective_registry_digest=prospective_registry_digest,
        candidates=candidates,
        prospective_files=prospective_files,
    )
    return RegistryPromotionPlan(
        input_kind=input_kind,
        registry_index_path=index.path,
        registry_root=index.root,
        registry_index_sha256=index.sha256,
        before_registry_digest=before_registry_digest,
        prospective_registry_digest=prospective_registry_digest,
        candidates=tuple(candidates),
        prospective_files=tuple(prospective_files),
        plan_digest=_sha256_json(payload),
    )


def apply_registry_promotion(
    plan_or_written_plan_bundle: RegistryPromotionPlan | str | Path,
    *,
    confirmation_digest: str,
    new_registry_version: str,
    registry_index: str | Path | None = None,
) -> RegistryPromotionApplyResult:
    """Apply one exact plan through a locked, full-registry-root transaction."""

    try:
        return _apply_registry_promotion(
            plan_or_written_plan_bundle,
            confirmation_digest=confirmation_digest,
            new_registry_version=new_registry_version,
            registry_index=registry_index,
        )
    except RegistryPromotionApplyError:
        raise
    except RegistryPromotionPlanError as exc:
        raise RegistryPromotionApplyError(str(exc)) from exc


def _apply_registry_promotion(
    plan_or_written_plan_bundle: RegistryPromotionPlan | str | Path,
    *,
    confirmation_digest: str,
    new_registry_version: str,
    registry_index: str | Path | None = None,
) -> RegistryPromotionApplyResult:
    """Apply one exact plan through a locked, full-registry-root transaction.

    Written bundles require an explicit current ``registry_index``. Absolute
    paths serialized in a bundle are integrity-bound review metadata only and
    are never used as write destinations.
    """

    if isinstance(plan_or_written_plan_bundle, RegistryPromotionPlan):
        plan = plan_or_written_plan_bundle
        selected_index = (
            plan.registry_index_path if registry_index is None else Path(registry_index)
        )
    else:
        plan = _plan_from_written_bundle(plan_or_written_plan_bundle)
        if registry_index is None:
            raise RegistryPromotionApplyError(
                "Applying a written promotion-plan bundle requires an explicit current "
                "registry_index; manifest absolute paths are never trusted as destinations."
            )
        selected_index = Path(registry_index)

    _verify_plan_digest(plan)
    if type(confirmation_digest) is not str or not hmac.compare_digest(
        confirmation_digest,
        plan.plan_digest,
    ):
        raise RegistryPromotionApplyError(
            "confirmation_digest must type- and value-exactly match plan.plan_digest."
        )
    _validate_apply_candidate_set(plan)

    initial_index = _load_registry_index(selected_index)
    transaction_state = _ApplyTransactionState()
    with _registry_apply_lock(
        initial_index.root,
        plan.plan_digest,
        transaction_state=transaction_state,
    ):
        current_index = _load_registry_index(selected_index)
        if current_index.root != initial_index.root:
            raise RegistryPromotionApplyError(
                "Registry index root changed while acquiring the single-writer lock."
            )
        old_version = _validate_version_transition(
            current_index,
            new_registry_version=new_registry_version,
        )
        overrides = _revalidate_plan_against_current_registry(plan, current_index)
        index_content = _updated_registry_index_content(
            current_index,
            new_registry_version=new_registry_version,
        )

        stage_container = Path(
            tempfile.mkdtemp(
                prefix=f".{current_index.root.name}.promotion-stage-",
                dir=current_index.root.parent,
            )
        )
        stage_root = stage_container / current_index.root.name
        stage_body_error: BaseException | None = None
        try:
            if stage_container.stat().st_dev != current_index.root.stat().st_dev:
                raise RegistryPromotionApplyError(
                    "Promotion stage is not on the registry root filesystem."
                )
            _registry_tree_hashes(current_index.root)
            shutil.copytree(
                current_index.root,
                stage_root,
                copy_function=shutil.copy2,
            )
            for relative_path, content in overrides.items():
                destination = stage_root / relative_path
                if not destination.is_file() or destination.is_symlink():
                    raise RegistryPromotionApplyError(
                        f"Staged promotion target is not a safe regular file: {relative_path}"
                    )
                destination.write_text(content, encoding="utf-8")
            staged_index_path = stage_root / current_index.path.relative_to(current_index.root)
            staged_index_path.write_text(index_content, encoding="utf-8")

            staged_index = _load_registry_index(staged_index_path)
            _validate_staged_apply(
                plan,
                source_index=current_index,
                staged_index=staged_index,
                new_registry_version=new_registry_version,
                expected_target_overrides=overrides,
            )
            applied_digest = _registry_digest(staged_index, overrides={})
            changed_files = _applied_file_transitions(
                source_index=current_index,
                staged_index=staged_index,
                expected_target_overrides=overrides,
            )

            # This is intentionally the final source read before the first rename.
            final_source = _load_registry_index(selected_index)
            if final_source.root != current_index.root:
                raise RegistryPromotionApplyError(
                    "Registry root changed before the transactional swap."
                )
            _revalidate_plan_against_current_registry(plan, final_source)
            _validate_current_registry(final_source)
            applied_index = _commit_staged_registry(
                stage_root=stage_root,
                source_root=final_source.root,
                index_relative_path=final_source.path.relative_to(final_source.root),
                before_registry_digest=plan.before_registry_digest,
                applied_registry_digest=applied_digest,
                plan_digest=plan.plan_digest,
                new_registry_version=new_registry_version,
                plan=plan,
                transaction_state=transaction_state,
            )
        except BaseException as exc:
            stage_body_error = exc
            raise
        finally:
            if transaction_state.rollback_status != "unproven":
                try:
                    shutil.rmtree(stage_container)
                except BaseException as exc:
                    detail = _cleanup_failure_detail(
                        transaction_state=transaction_state,
                        cleanup_name="stage_cleanup",
                        cleanup_path_name="stage_path",
                        cleanup_path=stage_container,
                        error=exc,
                        prior_error=stage_body_error,
                    )
                    if not isinstance(exc, Exception):
                        exc.add_note(f"FungMod registry promotion: {detail}")
                        raise
                    raise RegistryPromotionApplyError(
                        detail
                    ) from exc

    return RegistryPromotionApplyResult(
        registry_index_path=applied_index.path,
        registry_root=applied_index.root,
        old_registry_version=old_version,
        new_registry_version=new_registry_version,
        plan_digest=plan.plan_digest,
        confirmation_digest=confirmation_digest,
        before_registry_digest=plan.before_registry_digest,
        planned_registry_digest=plan.prospective_registry_digest,
        applied_registry_digest=applied_digest,
        changed_files=changed_files,
        applied_record_ids=tuple(
            sorted(item.record_id for item in plan.addable_records)
        ),
        exact_duplicate_record_ids=tuple(
            sorted(item.record_id for item in plan.exact_duplicates)
        ),
        transaction_status="committed",
        rollback_status="not_required",
        backup_cleanup_status="complete",
        production_registry_mutated=True,
        scientific_validation_claimed=False,
        simulation_authorized=False,
    )


def _candidate(
    item: _AcceptedRecord,
    *,
    classification: PromotionClassification,
    reason: str,
    registry_key: str | None = None,
    target: _TargetFile | None = None,
    after_sha256: str | None = None,
) -> RegistryPromotionCandidate:
    return RegistryPromotionCandidate(
        record_type=item.record_type,
        registry_key=registry_key,
        record_id=item.record_id,
        classification=classification,
        reason=reason,
        target_path=None if target is None else target.path,
        target_registry_path=None if target is None else target.relative_path,
        before_sha256=None if target is None else target.before_sha256,
        after_sha256=after_sha256,
        target_record=deepcopy(item.target_record),
        curation_metadata=deepcopy(item.curation_metadata),
    )


def _plan_digest_payload(
    *,
    input_kind: Literal["curation_result", "written_curation_bundle"],
    registry_index_path: Path,
    registry_root: Path,
    registry_index_sha256: str,
    before_registry_digest: str,
    prospective_registry_digest: str,
    candidates: Sequence[RegistryPromotionCandidate],
    prospective_files: Sequence[ProspectiveRegistryFile],
) -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION,
        "input_kind": input_kind,
        "registry_index_path": str(registry_index_path),
        "registry_root": str(registry_root),
        "registry_index_sha256": registry_index_sha256,
        "before_registry_digest": before_registry_digest,
        "prospective_registry_digest": prospective_registry_digest,
        "candidates": [item.to_dict() for item in candidates],
        "prospective_files": [item.to_dict() for item in prospective_files],
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "apply_available": _candidate_set_apply_available(candidates),
        "apply_policy": _PROMOTION_APPLY_POLICY,
        "version_policy": _PROMOTION_VERSION_POLICY,
    }


def _verify_plan_digest(plan: RegistryPromotionPlan) -> None:
    if (
        type(plan.plan_digest) is not str
        or _SHA256_PATTERN.fullmatch(plan.plan_digest) is None
        or plan.plan_digest != plan.plan_digest.lower()
    ):
        raise RegistryPromotionPlanError(
            "Registry promotion plan_digest must be a lowercase SHA-256 hex digest."
        )
    payload = _plan_digest_payload(
        input_kind=plan.input_kind,
        registry_index_path=plan.registry_index_path,
        registry_root=plan.registry_root,
        registry_index_sha256=plan.registry_index_sha256,
        before_registry_digest=plan.before_registry_digest,
        prospective_registry_digest=plan.prospective_registry_digest,
        candidates=plan.candidates,
        prospective_files=plan.prospective_files,
    )
    if not hmac.compare_digest(_sha256_json(payload), plan.plan_digest):
        raise RegistryPromotionPlanError(
            "Registry promotion plan contents changed after construction; refusing to write."
        )


def _plan_from_written_bundle(value: str | Path) -> RegistryPromotionPlan:
    manifest_path = _promotion_plan_manifest_path(value)
    manifest = _read_json_mapping(manifest_path, label="Promotion-plan manifest")
    if manifest.get("kind") != REGISTRY_PROMOTION_PLAN_MANIFEST_KIND:
        raise RegistryPromotionApplyError(
            f"Written input is not an owned promotion-plan bundle of kind "
            f"{REGISTRY_PROMOTION_PLAN_MANIFEST_KIND!r}."
        )
    schema_version = manifest.get("schema_version")
    if schema_version != REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION:
        if schema_version == "1.0.0":
            raise RegistryPromotionApplyError(
                "Pre-PR-47 promotion-plan schema '1.0.0' is preview-only and lacks "
                "durable curation audit provenance; regenerate the plan before apply."
            )
        raise RegistryPromotionApplyError(
            f"Unsupported promotion-plan schema version {schema_version!r}."
        )
    _validate_plan_manifest_contract(manifest)

    raw_candidates = manifest.get("candidates")
    raw_prospective = manifest.get("prospective_files")
    if not isinstance(raw_candidates, list) or not isinstance(raw_prospective, list):
        raise RegistryPromotionApplyError(
            "Promotion-plan manifest requires candidates and prospective_files lists."
        )
    candidates = tuple(
        _candidate_from_manifest(item, index=index)
        for index, item in enumerate(raw_candidates)
    )

    root = manifest_path.parent
    prospective_files = tuple(
        _prospective_file_from_manifest(root, item, index=index)
        for index, item in enumerate(raw_prospective)
    )
    expected_artifacts = {
        "promotion_report.md",
        "candidate_classifications.yml",
        *(
            f"prospective_registry/{item.target_registry_path}"
            for item in prospective_files
        ),
    }
    declared = _verify_plan_bundle_artifacts(
        root,
        manifest,
        expected_artifacts=expected_artifacts,
    )
    candidate_payload = _read_yaml_mapping(
        declared["candidate_classifications.yml"],
        label="Promotion candidate classifications",
    )
    if candidate_payload.get("kind") != "fungmod_registry_promotion_plan_candidates":
        raise RegistryPromotionApplyError(
            "Promotion candidate artifact has an unsupported kind."
        )
    if candidate_payload.get("schema_version") != REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION:
        raise RegistryPromotionApplyError(
            "Promotion candidate artifact has an unsupported schema version."
        )
    if candidate_payload.get("plan_digest") != manifest.get("plan_digest"):
        raise RegistryPromotionApplyError(
            "Promotion candidate artifact plan digest does not match its manifest."
        )
    if candidate_payload.get("production_registry_mutated") is not False:
        raise RegistryPromotionApplyError(
            "Promotion candidate artifact must declare production_registry_mutated: false."
        )
    if candidate_payload.get("scientific_validation_claimed") is not False:
        raise RegistryPromotionApplyError(
            "Promotion candidate artifact must declare scientific_validation_claimed: false."
        )
    if not _type_exact_equal(
        candidate_payload.get("records"),
        [item.to_dict() for item in candidates],
    ):
        raise RegistryPromotionApplyError(
            "Promotion candidate artifact does not exactly match manifest candidates."
        )

    input_kind = manifest.get("input_kind")
    if input_kind not in {"curation_result", "written_curation_bundle"}:
        raise RegistryPromotionApplyError(
            f"Promotion-plan manifest has unsupported input_kind {input_kind!r}."
        )
    plan = RegistryPromotionPlan(
        input_kind=input_kind,
        registry_index_path=Path(_required_manifest_string(manifest, "registry_index_path")),
        registry_root=Path(_required_manifest_string(manifest, "registry_root")),
        registry_index_sha256=_required_digest(manifest, "registry_index_sha256"),
        before_registry_digest=_required_digest(manifest, "before_registry_digest"),
        prospective_registry_digest=_required_digest(
            manifest,
            "prospective_registry_digest",
        ),
        candidates=candidates,
        prospective_files=prospective_files,
        plan_digest=_required_digest(manifest, "plan_digest"),
    )
    _verify_plan_digest(plan)
    if not _type_exact_equal(manifest.get("summary"), plan.summary()):
        raise RegistryPromotionApplyError(
            "Promotion-plan manifest summary does not match its exact plan contents."
        )
    if not _type_exact_equal(
        manifest.get("apply_available"),
        plan.summary()["apply_available"],
    ):
        raise RegistryPromotionApplyError(
            "Promotion-plan manifest apply_available does not match its exact candidate set."
        )
    _validate_bundle_candidate_prospective_consistency(plan)
    return plan


def _promotion_plan_manifest_path(value: str | Path) -> Path:
    path = Path(value)
    if ".." in path.parts:
        raise RegistryPromotionApplyError(
            f"Promotion-plan bundle path traversal is not allowed: {path}"
        )
    _reject_symlink_components(path, label="Promotion-plan bundle path")
    manifest = path / "promotion_plan.json" if path.is_dir() else path
    if manifest.name != "promotion_plan.json":
        raise RegistryPromotionApplyError(
            "Written promotion-plan input must be a bundle directory or promotion_plan.json."
        )
    _reject_symlink_components(manifest, label="Promotion-plan manifest path")
    if not manifest.is_file():
        raise RegistryPromotionApplyError(
            f"Promotion-plan manifest does not exist: {manifest}"
        )
    return manifest.resolve(strict=True)


def _validate_plan_manifest_contract(manifest: Mapping[str, Any]) -> None:
    required_values = {
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "apply_policy": _PROMOTION_APPLY_POLICY,
        "version_policy": _PROMOTION_VERSION_POLICY,
    }
    for field, expected in required_values.items():
        if not _type_exact_equal(manifest.get(field), expected):
            raise RegistryPromotionApplyError(
                f"Promotion-plan manifest requires {field}: {expected!r}."
            )


def _candidate_from_manifest(value: Any, *, index: int) -> RegistryPromotionCandidate:
    if not isinstance(value, Mapping):
        raise RegistryPromotionApplyError(
            f"Promotion candidate at index {index} must be a mapping."
        )
    expected_fields = {
        "record_type",
        "registry_key",
        "record_id",
        "classification",
        "reason",
        "target_path",
        "target_registry_path",
        "before_sha256",
        "after_sha256",
        "target_record",
        "curation_metadata",
    }
    if set(value) != expected_fields:
        raise RegistryPromotionApplyError(
            f"Promotion candidate at index {index} has an unexpected field set."
        )
    classification = value.get("classification")
    if classification not in {
        "addable",
        "exact_duplicate",
        "conflict",
        "blocked_unsupported",
    }:
        raise RegistryPromotionApplyError(
            f"Promotion candidate at index {index} has invalid classification."
        )
    target_record = value.get("target_record")
    curation_metadata = value.get("curation_metadata")
    if not isinstance(target_record, Mapping) or not isinstance(curation_metadata, Mapping):
        raise RegistryPromotionApplyError(
            f"Promotion candidate at index {index} requires target and curation mappings."
        )
    registry_key = value.get("registry_key")
    target_path = value.get("target_path")
    target_registry_path = value.get("target_registry_path")
    if registry_key is not None and not isinstance(registry_key, str):
        raise RegistryPromotionApplyError(
            f"Promotion candidate at index {index} has invalid registry_key."
        )
    if target_path is not None and not isinstance(target_path, str):
        raise RegistryPromotionApplyError(
            f"Promotion candidate at index {index} has invalid target_path."
        )
    if target_registry_path is not None:
        _validate_relative_registry_path(
            target_registry_path,
            label=f"Promotion candidate at index {index} target_registry_path",
        )
    return RegistryPromotionCandidate(
        record_type=_required_manifest_string(value, "record_type"),
        registry_key=registry_key,
        record_id=_required_manifest_string(value, "record_id"),
        classification=classification,
        reason=_required_manifest_string(value, "reason"),
        target_path=None if target_path is None else Path(target_path),
        target_registry_path=target_registry_path,
        before_sha256=_optional_manifest_digest(value, "before_sha256"),
        after_sha256=_optional_manifest_digest(value, "after_sha256"),
        target_record=deepcopy(dict(target_record)),
        curation_metadata=deepcopy(dict(curation_metadata)),
    )


def _prospective_file_from_manifest(
    root: Path,
    value: Any,
    *,
    index: int,
) -> ProspectiveRegistryFile:
    if not isinstance(value, Mapping):
        raise RegistryPromotionApplyError(
            f"Prospective registry file at index {index} must be a mapping."
        )
    expected_fields = {
        "registry_key",
        "target_path",
        "target_registry_path",
        "before_sha256",
        "after_sha256",
        "artifact_path",
    }
    if set(value) != expected_fields:
        raise RegistryPromotionApplyError(
            f"Prospective registry file at index {index} has an unexpected field set."
        )
    target_registry_path = _required_manifest_string(value, "target_registry_path")
    _validate_relative_registry_path(
        target_registry_path,
        label=f"Prospective registry file at index {index} target_registry_path",
    )
    artifact_path = _required_manifest_string(value, "artifact_path")
    expected_artifact = f"prospective_registry/{target_registry_path}"
    if artifact_path != expected_artifact:
        raise RegistryPromotionApplyError(
            f"Prospective registry artifact path must be {expected_artifact!r}."
        )
    artifact = root / artifact_path
    _reject_symlink_components(artifact, label="Prospective registry artifact path")
    try:
        content = artifact.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RegistryPromotionApplyError(
            f"Cannot read prospective registry artifact {artifact}: {exc}"
        ) from exc
    after_sha256 = _required_digest(value, "after_sha256")
    if not hmac.compare_digest(
        _sha256_bytes(content.encode("utf-8")),
        after_sha256,
    ):
        raise RegistryPromotionApplyError(
            f"Prospective registry content hash does not match for {target_registry_path!r}."
        )
    return ProspectiveRegistryFile(
        registry_key=_required_manifest_string(value, "registry_key"),
        target_path=Path(_required_manifest_string(value, "target_path")),
        target_registry_path=target_registry_path,
        before_sha256=_required_digest(value, "before_sha256"),
        after_sha256=after_sha256,
        content=content,
    )


def _verify_plan_bundle_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    expected_artifacts: set[str],
) -> dict[str, Path]:
    files = manifest.get("files")
    if not isinstance(files, Mapping) or set(files) != expected_artifacts:
        raise RegistryPromotionApplyError(
            "Promotion-plan manifest artifact set does not match its owned schema."
        )
    actual_hashes = _bundle_tree_hashes(root)
    if set(actual_hashes) != expected_artifacts | {"promotion_plan.json"}:
        raise RegistryPromotionApplyError(
            "Promotion-plan bundle contains missing or undeclared artifacts."
        )
    declared: dict[str, Path] = {}
    for name in sorted(expected_artifacts):
        _validate_relative_registry_path(name, label="Promotion-plan artifact path")
        expected_digest = _required_digest(files, name)
        if not hmac.compare_digest(actual_hashes[name], expected_digest):
            raise RegistryPromotionApplyError(
                f"Promotion-plan artifact checksum mismatch for {name!r}."
            )
        declared[name] = (root / name).resolve(strict=True)
    return declared


def _bundle_tree_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for current_root, raw_directories, raw_files in os.walk(
        root,
        topdown=True,
        onerror=_raise_bundle_walk_error,
        followlinks=False,
    ):
        current = Path(current_root)
        for name in sorted(raw_directories):
            path = current / name
            if path.is_symlink() or not path.is_dir():
                raise RegistryPromotionApplyError(
                    f"Promotion-plan bundle contains an unsafe entry: {path}"
                )
        for name in sorted(raw_files):
            path = current / name
            if path.is_symlink() or not path.is_file():
                raise RegistryPromotionApplyError(
                    f"Promotion-plan bundle contains an unsafe entry: {path}"
                )
            hashes[path.relative_to(root).as_posix()] = _sha256_bytes(path.read_bytes())
    return hashes


def _validate_bundle_candidate_prospective_consistency(
    plan: RegistryPromotionPlan,
) -> None:
    prospective_by_key: dict[str, ProspectiveRegistryFile] = {}
    for prospective in plan.prospective_files:
        if prospective.registry_key in prospective_by_key:
            raise RegistryPromotionApplyError(
                f"Promotion plan repeats prospective registry key {prospective.registry_key!r}."
            )
        prospective_by_key[prospective.registry_key] = prospective

    addable_by_key: dict[str, list[RegistryPromotionCandidate]] = {}
    for candidate in plan.candidates:
        if candidate.classification != "addable":
            continue
        if candidate.registry_key is None:
            raise RegistryPromotionApplyError(
                f"Addable record {candidate.record_id!r} lacks a registry key."
            )
        addable_by_key.setdefault(candidate.registry_key, []).append(candidate)
    if set(prospective_by_key) != set(addable_by_key):
        raise RegistryPromotionApplyError(
            "Promotion plan addable candidates and prospective files do not match."
        )
    for key, candidates in addable_by_key.items():
        prospective = prospective_by_key[key]
        payload = _yaml_mapping_from_text(
            prospective.content,
            label=f"Prospective registry file {prospective.target_registry_path}",
        )
        if payload.get("kind") != "fungmod_registry_records" or payload.get("record_type") != key:
            raise RegistryPromotionApplyError(
                f"Prospective registry content for {key!r} has the wrong kind or record type."
            )
        records = payload.get("records")
        if not isinstance(records, list):
            raise RegistryPromotionApplyError(
                f"Prospective registry content for {key!r} requires a records list."
            )
        for candidate in candidates:
            matches = [
                item
                for item in records
                if isinstance(item, Mapping)
                and _type_exact_equal(item, candidate.target_record)
            ]
            if len(matches) != 1:
                raise RegistryPromotionApplyError(
                    f"Prospective registry content does not contain exactly one exact "
                    f"record for {candidate.record_id!r}."
                )


def _required_manifest_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise RegistryPromotionApplyError(
            f"Promotion-plan field {field!r} must be a non-empty string."
        )
    return item


def _required_digest(value: Mapping[str, Any], field: str) -> str:
    digest = _required_manifest_string(value, field)
    if _SHA256_PATTERN.fullmatch(digest) is None or digest != digest.lower():
        raise RegistryPromotionApplyError(
            f"Promotion-plan field {field!r} must be a lowercase SHA-256 digest."
        )
    return digest


def _optional_manifest_digest(value: Mapping[str, Any], field: str) -> str | None:
    digest = value.get(field)
    if digest is None:
        return None
    return _required_digest(value, field)


def _validate_relative_registry_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryPromotionApplyError(f"{label} must be a non-empty string.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RegistryPromotionApplyError(f"{label} must be a safe relative path.")
    return value


def _yaml_mapping_from_text(value: str, *, label: str) -> Mapping[str, Any]:
    try:
        payload = yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise RegistryPromotionApplyError(f"Malformed {label}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RegistryPromotionApplyError(f"{label} must contain a YAML mapping.")
    return payload


def _validate_apply_candidate_set(plan: RegistryPromotionPlan) -> None:
    if plan.conflicts or plan.blocked_records:
        raise RegistryPromotionApplyError(
            "Promotion apply refuses any plan containing conflict or blocked_unsupported candidates."
        )
    if not plan.addable_records:
        raise RegistryPromotionApplyError(
            "Promotion apply requires at least one addable record; exact duplicates alone are a no-op."
        )
    identifiers = [item.record_id for item in plan.candidates]
    if len(identifiers) != len(set(identifiers)):
        raise RegistryPromotionApplyError(
            "Promotion apply refuses duplicate candidate record IDs."
        )
    for candidate in plan.candidates:
        _validate_accepted_curation(candidate.record_id, candidate.curation_metadata)
        _validate_target_record(candidate.record_id, candidate.target_record)
        provenance = candidate.target_record.get("provenance")
        registry_authored = (
            isinstance(provenance, Mapping)
            and REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY in provenance
        )
        if registry_authored:
            try:
                validate_registry_record_authoring_plan_record(
                    candidate.record_type,
                    candidate.target_record,
                    candidate.curation_metadata,
                )
            except RegistryRecordAuthoringError as exc:
                raise RegistryPromotionApplyError(
                    f"Authored registry candidate {candidate.record_id!r} failed "
                    f"specialized validation during apply: {exc}"
                ) from exc
        provenance_class = (
            classify_parameter_provenance(
                provenance if isinstance(provenance, Mapping) else None,
                curation_metadata=candidate.curation_metadata,
            )
            if candidate.record_type == "parameter_records"
            else "generic"
        )
        if provenance_class == "parameter_bridge":
            try:
                validate_parameter_authoring_plan_record(
                    candidate.target_record,
                    candidate.curation_metadata,
                )
            except ParameterRecordAuthoringError as exc:
                raise RegistryPromotionApplyError(
                    f"Parameter candidate {candidate.record_id!r} failed complete specialized "
                    f"bridge validation during apply: {exc}"
                ) from exc
        _validate_source_identity_consistency(
            candidate.record_id,
            target_record=candidate.target_record,
            curation_metadata=candidate.curation_metadata,
        )
        expected_key = _CURATION_TO_REGISTRY_KEY.get(candidate.record_type)
        if expected_key is None:
            raise RegistryPromotionApplyError(
                f"Promotion apply does not support record type {candidate.record_type!r}."
            )
        if candidate.registry_key != expected_key:
            raise RegistryPromotionApplyError(
                f"Promotion candidate {candidate.record_id!r} has inconsistent registry mapping."
            )
        if candidate.classification == "addable":
            if candidate.reason != "accepted_record_is_addable_without_overwrite":
                raise RegistryPromotionApplyError(
                    f"Addable candidate {candidate.record_id!r} has an unsupported reason."
                )
            _validate_exact_curation_audit(candidate)
        elif candidate.classification == "exact_duplicate":
            if candidate.reason != "exact_record_content_already_present_no_op":
                raise RegistryPromotionApplyError(
                    f"Exact duplicate {candidate.record_id!r} has an unsupported reason."
                )
            if provenance_class != "generic" or registry_authored:
                _validate_exact_curation_audit(candidate)
        else:
            raise RegistryPromotionApplyError(
                f"Promotion apply refuses candidate classification {candidate.classification!r}."
            )
    _validate_bundle_candidate_prospective_consistency(plan)


def _validate_exact_curation_audit(candidate: RegistryPromotionCandidate) -> None:
    provenance = candidate.target_record.get("provenance")
    if not isinstance(provenance, Mapping):
        raise RegistryPromotionApplyError(
            f"Promotion candidate {candidate.record_id!r} lacks mapping provenance."
        )
    audit = provenance.get(_CURATION_AUDIT_PROVENANCE_KEY)
    expected = _curation_audit_payload(candidate.curation_metadata)
    if not _type_exact_equal(audit, expected):
        raise RegistryPromotionApplyError(
            f"Promotion candidate {candidate.record_id!r} lacks exact durable curation audit metadata."
        )


def _validate_version_transition(
    index: _RegistryIndex,
    *,
    new_registry_version: str,
) -> str:
    current_version = index.payload.get("version")
    if type(current_version) is not str:
        raise RegistryPromotionApplyError(
            "Current registry version must be a strict numeric MAJOR.MINOR.PATCH string."
        )
    if type(new_registry_version) is not str:
        raise RegistryPromotionApplyError(
            "new_registry_version must be a strict numeric MAJOR.MINOR.PATCH string."
        )
    current = _strict_version_parts(current_version, label="Current registry version")
    proposed = _strict_version_parts(new_registry_version, label="new_registry_version")
    expected = (current[0], current[1], current[2] + 1)
    if proposed != expected:
        expected_text = ".".join(str(item) for item in expected)
        raise RegistryPromotionApplyError(
            f"new_registry_version must be exactly the next patch version {expected_text!r}."
        )
    return current_version


def _strict_version_parts(value: str, *, label: str) -> tuple[int, int, int]:
    match = _STRICT_VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise RegistryPromotionApplyError(
            f"{label} must be strict numeric MAJOR.MINOR.PATCH without prerelease or leading zeros."
        )
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _revalidate_plan_against_current_registry(
    plan: RegistryPromotionPlan,
    index: _RegistryIndex,
) -> dict[str, str]:
    _validate_current_registry(index)
    if not hmac.compare_digest(index.sha256, plan.registry_index_sha256):
        raise RegistryPromotionApplyError(
            "Registry index SHA changed after planning; refusing stale promotion apply."
        )
    before_digest = _registry_digest(index, overrides={})
    if not hmac.compare_digest(before_digest, plan.before_registry_digest):
        raise RegistryPromotionApplyError(
            "Registry root digest changed after planning; refusing stale promotion apply."
        )

    addable_by_key: dict[str, list[RegistryPromotionCandidate]] = {}
    prospective_by_key = {item.registry_key: item for item in plan.prospective_files}
    if len(prospective_by_key) != len(plan.prospective_files):
        raise RegistryPromotionApplyError("Promotion plan repeats a prospective registry key.")
    for candidate in plan.candidates:
        registry_key = candidate.registry_key
        if registry_key is None:
            raise RegistryPromotionApplyError(
                f"Promotion candidate {candidate.record_id!r} lacks a registry key."
            )
        target = index.targets.get(registry_key)
        if target is None:
            raise RegistryPromotionApplyError(
                f"Current registry index has no destination for {registry_key!r}."
            )
        if candidate.target_registry_path != target.relative_path:
            raise RegistryPromotionApplyError(
                f"Promotion candidate {candidate.record_id!r} destination no longer matches "
                "the current registry index mapping."
            )
        if candidate.before_sha256 != target.before_sha256:
            raise RegistryPromotionApplyError(
                f"Promotion candidate {candidate.record_id!r} target hash is stale."
            )
        provenance = candidate.target_record.get("provenance")
        if (
            isinstance(provenance, Mapping)
            and REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY in provenance
        ):
            try:
                validate_registry_record_authoring_plan_record(
                    candidate.record_type,
                    candidate.target_record,
                    candidate.curation_metadata,
                )
            except RegistryRecordAuthoringError as exc:
                raise RegistryPromotionApplyError(
                    f"Authored registry record {candidate.record_id!r} failed "
                    f"current-registry revalidation during apply: {exc}"
                ) from exc
        if candidate.record_type == "parameter_records" and classify_parameter_provenance(
            provenance if isinstance(provenance, Mapping) else None,
            curation_metadata=candidate.curation_metadata,
        ) == "parameter_bridge":
            try:
                validate_authored_parameter_against_registry(
                    candidate.target_record,
                    registry_index=index.path,
                )
            except ParameterRecordAuthoringError as exc:
                raise RegistryPromotionApplyError(
                    f"Authored parameter record {candidate.record_id!r} failed current-registry "
                    f"revalidation during apply: {exc}"
                ) from exc
        existing = _record_by_id(target, candidate.record_id)
        if candidate.classification == "addable":
            if existing is not None:
                raise RegistryPromotionApplyError(
                    f"Promotion candidate {candidate.record_id!r} now exists; overwrite is forbidden."
                )
            addable_by_key.setdefault(registry_key, []).append(candidate)
        elif candidate.classification == "exact_duplicate":
            if existing is None or not _type_exact_equal(existing, candidate.target_record):
                raise RegistryPromotionApplyError(
                    f"Exact duplicate {candidate.record_id!r} no longer matches raw registry content."
                )
            if candidate.after_sha256 != target.before_sha256:
                raise RegistryPromotionApplyError(
                    f"Exact duplicate {candidate.record_id!r} has inconsistent no-op hashes."
                )

    if set(addable_by_key) != set(prospective_by_key):
        raise RegistryPromotionApplyError(
            "Addable candidate destinations do not match prospective registry files."
        )
    overrides: dict[str, str] = {}
    for registry_key, candidates in sorted(addable_by_key.items()):
        target = index.targets[registry_key]
        prospective = prospective_by_key[registry_key]
        if prospective.target_registry_path != target.relative_path:
            raise RegistryPromotionApplyError(
                f"Prospective destination for {registry_key!r} no longer matches the current index."
            )
        if prospective.before_sha256 != target.before_sha256:
            raise RegistryPromotionApplyError(
                f"Prospective before hash for {registry_key!r} is stale."
            )
        expected_content = _merged_target_content(
            target,
            tuple(
                item.target_record
                for item in sorted(candidates, key=lambda value: value.record_id)
            ),
        )
        if prospective.content != expected_content:
            raise RegistryPromotionApplyError(
                f"Prospective content for {registry_key!r} is not the exact current merge."
            )
        expected_hash = _sha256_bytes(expected_content.encode("utf-8"))
        if not hmac.compare_digest(expected_hash, prospective.after_sha256):
            raise RegistryPromotionApplyError(
                f"Prospective after hash for {registry_key!r} does not match its content."
            )
        if any(item.after_sha256 != expected_hash for item in candidates):
            raise RegistryPromotionApplyError(
                f"Addable candidate after hashes for {registry_key!r} are inconsistent."
            )
        overrides[target.relative_path] = expected_content
    planned_digest = _registry_digest(index, overrides=overrides)
    if not hmac.compare_digest(planned_digest, plan.prospective_registry_digest):
        raise RegistryPromotionApplyError(
            "Recomputed prospective registry digest does not match the confirmed plan."
        )
    return overrides


def _updated_registry_index_content(
    index: _RegistryIndex,
    *,
    new_registry_version: str,
) -> str:
    payload = deepcopy(dict(index.payload))
    payload["version"] = new_registry_version
    content = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
    )
    reloaded = _yaml_mapping_from_text(content, label="Updated registry index")
    if not _type_exact_equal(reloaded, payload):
        raise RegistryPromotionApplyError(
            "Updated registry index did not round-trip type-exactly."
        )
    return content


@contextmanager
def _registry_apply_lock(
    root: Path,
    plan_digest: str,
    *,
    transaction_state: _ApplyTransactionState,
) -> Iterator[Path]:
    lock_path = root.parent / f".{root.name}.fungmod-registry-promotion.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except FileExistsError as exc:
        raise RegistryPromotionApplyError(
            f"Registry promotion single-writer lock is already held: {lock_path}"
        ) from exc
    payload = (
        json.dumps(
            {"pid": os.getpid(), "plan_digest": plan_digest},
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    initialization_error: OSError | None = None
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError("single-writer lock payload was only partially written")
    except OSError as exc:
        initialization_error = exc
    try:
        os.close(descriptor)
    except OSError as exc:
        if initialization_error is None:
            initialization_error = exc
    if initialization_error is not None:
        try:
            lock_path.unlink()
        except BaseException as cleanup_error:
            detail = _cleanup_failure_detail(
                transaction_state=transaction_state,
                cleanup_name="lock_cleanup",
                cleanup_path_name="lock_path",
                cleanup_path=lock_path,
                error=cleanup_error,
                prior_error=initialization_error,
            )
            if not isinstance(cleanup_error, Exception):
                cleanup_error.add_note(f"FungMod registry promotion: {detail}")
                raise
            raise RegistryPromotionApplyError(
                detail
            ) from cleanup_error
        raise RegistryPromotionApplyError(
            f"Registry promotion lock initialization failed at {lock_path}: "
            f"{initialization_error}"
        ) from initialization_error
    body_error: BaseException | None = None
    try:
        yield lock_path
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        try:
            lock_path.unlink()
        except BaseException as exc:
            detail = _cleanup_failure_detail(
                transaction_state=transaction_state,
                cleanup_name="lock_cleanup",
                cleanup_path_name="lock_path",
                cleanup_path=lock_path,
                error=exc,
                prior_error=body_error,
            )
            if not isinstance(exc, Exception):
                exc.add_note(f"FungMod registry promotion: {detail}")
                raise
            raise RegistryPromotionApplyError(
                detail
            ) from exc


def _cleanup_failure_detail(
    *,
    transaction_state: _ApplyTransactionState,
    cleanup_name: str,
    cleanup_path_name: str,
    cleanup_path: Path,
    error: BaseException,
    prior_error: BaseException | None = None,
) -> str:
    cleanup_status = "failed" if isinstance(error, Exception) else "interrupted"
    prior_detail = "" if prior_error is None else f"; prior_error={prior_error}"
    return (
        f"transaction_status={transaction_state.transaction_status}; "
        f"rollback_status={transaction_state.rollback_status}; "
        f"{cleanup_name}_status={cleanup_status}; "
        f"{cleanup_path_name}={cleanup_path}; cause={error}{prior_detail}"
    )


def _validate_staged_apply(
    plan: RegistryPromotionPlan,
    *,
    source_index: _RegistryIndex,
    staged_index: _RegistryIndex,
    new_registry_version: str,
    expected_target_overrides: Mapping[str, str],
) -> None:
    if staged_index.version != new_registry_version:
        raise RegistryPromotionApplyError(
            "Staged registry index does not contain the requested new version."
        )
    expected_index_payload = deepcopy(dict(source_index.payload))
    expected_index_payload["version"] = new_registry_version
    if not _type_exact_equal(staged_index.payload, expected_index_payload):
        raise RegistryPromotionApplyError(
            "Staged registry index changed fields other than version."
        )
    source_hashes = _registry_tree_hashes(source_index.root)
    staged_hashes = _registry_tree_hashes(staged_index.root)
    if set(source_hashes) != set(staged_hashes):
        raise RegistryPromotionApplyError(
            "Staged registry is not a complete copy of the source registry root."
        )
    index_relative_path = source_index.path.relative_to(source_index.root).as_posix()
    allowed_changes = {index_relative_path, *expected_target_overrides}
    unexpected_changes = sorted(
        path
        for path in source_hashes
        if source_hashes[path] != staged_hashes[path] and path not in allowed_changes
    )
    if unexpected_changes:
        raise RegistryPromotionApplyError(
            f"Staged registry changed unplanned files: {unexpected_changes}."
        )
    for relative_path, content in expected_target_overrides.items():
        if staged_hashes[relative_path] != _sha256_bytes(content.encode("utf-8")):
            raise RegistryPromotionApplyError(
                f"Staged target content hash mismatch for {relative_path!r}."
            )

    try:
        registry = load_registry(staged_index.path)
    except Exception as exc:
        raise RegistryPromotionApplyError(
            f"Full staged registry validation failed: {_format_validation_error(exc)}"
        ) from exc
    if registry.version != new_registry_version:
        raise RegistryPromotionApplyError(
            "Full staged registry loader returned the wrong version."
        )
    _validate_runtime_promoted_records(plan, registry, label="Staged runtime registry")


def _validate_runtime_promoted_records(
    plan: RegistryPromotionPlan,
    registry: FungModRegistry,
    *,
    label: str,
) -> None:
    for candidate in plan.addable_records:
        assert candidate.registry_key is not None
        runtime_records = getattr(registry, candidate.registry_key, None)
        if not isinstance(runtime_records, Mapping):
            raise RegistryPromotionApplyError(
                f"{label} lacks mapping {candidate.registry_key!r}."
            )
        runtime_record = runtime_records.get(candidate.record_id)
        if runtime_record is None or not hasattr(runtime_record, "to_dict"):
            raise RegistryPromotionApplyError(
                f"{label} lacks promoted record {candidate.record_id!r}."
            )
        if not _type_exact_equal(runtime_record.to_dict(), candidate.target_record):
            raise RegistryPromotionApplyError(
                f"{label} promoted record {candidate.record_id!r} lost loader fidelity."
            )


def _applied_file_transitions(
    *,
    source_index: _RegistryIndex,
    staged_index: _RegistryIndex,
    expected_target_overrides: Mapping[str, str],
) -> tuple[RegistryPromotionAppliedFile, ...]:
    source_hashes = _registry_tree_hashes(source_index.root)
    staged_hashes = _registry_tree_hashes(staged_index.root)
    index_relative_path = source_index.path.relative_to(source_index.root).as_posix()
    changed_paths = sorted({index_relative_path, *expected_target_overrides})
    transitions = tuple(
        RegistryPromotionAppliedFile(
            registry_path=path,
            before_sha256=source_hashes[path],
            after_sha256=staged_hashes[path],
        )
        for path in changed_paths
    )
    if any(item.before_sha256 == item.after_sha256 for item in transitions):
        raise RegistryPromotionApplyError(
            "Promotion transaction contains a declared changed file with identical hashes."
        )
    return transitions


def _commit_staged_registry(
    *,
    stage_root: Path,
    source_root: Path,
    index_relative_path: Path,
    before_registry_digest: str,
    applied_registry_digest: str,
    plan_digest: str,
    new_registry_version: str,
    plan: RegistryPromotionPlan,
    transaction_state: _ApplyTransactionState,
) -> _RegistryIndex:
    backup = source_root.parent / (
        f".{source_root.name}.promotion-backup-{plan_digest[:12]}"
    )
    if os.path.lexists(backup):
        raise RegistryPromotionApplyError(
            f"Refusing transaction while a promotion backup path already exists: {backup}"
        )
    pre_swap_index = _load_registry_index(source_root / index_relative_path)
    pre_swap_digest = _registry_digest(pre_swap_index, overrides={})
    if not hmac.compare_digest(pre_swap_digest, before_registry_digest):
        raise RegistryPromotionApplyError(
            "Registry root digest changed immediately before the transactional swap."
        )
    try:
        _replace_registry_path(source_root, backup, phase="backup")
        _replace_registry_path(stage_root, source_root, phase="install")
        installed_index = _load_registry_index(source_root / index_relative_path)
        installed_registry = load_registry(installed_index.path)
        if installed_registry.version != new_registry_version:
            raise RegistryPromotionApplyError(
                "Installed registry runtime version differs from the confirmed new version."
            )
        if _registry_digest(installed_index, overrides={}) != applied_registry_digest:
            raise RegistryPromotionApplyError(
                "Installed registry digest differs from the validated stage."
            )
        _validate_runtime_promoted_records(
            plan,
            installed_registry,
            label="Installed runtime registry",
        )
    except BaseException as transaction_error:
        transaction_state.transaction_status = "failed"
        try:
            _reconcile_failed_registry_transaction(
                source_root=source_root,
                backup=backup,
                stage_root=stage_root,
                index_relative_path=index_relative_path,
                before_registry_digest=before_registry_digest,
                applied_registry_digest=applied_registry_digest,
                transaction_state=transaction_state,
            )
        except BaseException as rollback_error:
            transaction_state.rollback_status = "unproven"
            raise RegistryPromotionApplyError(
                "transaction_status=failed; rollback_status=unproven; "
                f"backup_path={backup}; stage_path={stage_root}; "
                f"cause={transaction_error}"
            ) from rollback_error
        if not isinstance(transaction_error, Exception):
            transaction_error.add_note(
                "FungMod registry promotion: transaction_status=failed; "
                f"rollback_status={transaction_state.rollback_status}."
            )
            raise
        raise RegistryPromotionApplyError(
            f"transaction_status=failed; rollback_status={transaction_state.rollback_status}; "
            f"cause={transaction_error}"
        ) from transaction_error

    transaction_state.transaction_status = "committed"
    transaction_state.rollback_status = "not_required"
    try:
        shutil.rmtree(backup)
    except BaseException as exc:
        detail = _cleanup_failure_detail(
            transaction_state=transaction_state,
            cleanup_name="backup_cleanup",
            cleanup_path_name="backup_path",
            cleanup_path=backup,
            error=exc,
        )
        if not isinstance(exc, Exception):
            exc.add_note(f"FungMod registry promotion: {detail}")
            raise
        raise RegistryPromotionApplyError(
            detail
        ) from exc
    return installed_index


def _reconcile_failed_registry_transaction(
    *,
    source_root: Path,
    backup: Path,
    stage_root: Path,
    index_relative_path: Path,
    before_registry_digest: str,
    applied_registry_digest: str,
    transaction_state: _ApplyTransactionState,
) -> None:
    source_digest = _registry_copy_digest(source_root, index_relative_path)
    backup_digest = _registry_copy_digest(backup, index_relative_path)
    stage_digest = _registry_copy_digest(stage_root, index_relative_path)

    if source_digest == before_registry_digest and backup_digest is None:
        transaction_state.rollback_status = "not_required"
        return
    if backup_digest != before_registry_digest:
        raise RegistryPromotionApplyError(
            "Cannot prove the backup contains the exact pre-transaction registry."
        )

    if source_digest is None:
        if stage_digest not in {None, applied_registry_digest}:
            raise RegistryPromotionApplyError(
                "Staged registry digest changed during transaction recovery."
            )
    elif source_digest == applied_registry_digest:
        if stage_digest is not None:
            raise RegistryPromotionApplyError(
                "Both active and staged registry paths exist during transaction recovery."
            )
        _replace_registry_path(
            source_root,
            stage_root,
            phase="remove_failed_install",
        )
    else:
        raise RegistryPromotionApplyError(
            "Active registry digest is neither the before nor applied transaction state."
        )

    _replace_registry_path(backup, source_root, phase="rollback")
    restored_index = _load_registry_index(source_root / index_relative_path)
    _validate_current_registry(restored_index)
    restored_digest = _registry_digest(restored_index, overrides={})
    if restored_digest != before_registry_digest:
        raise RegistryPromotionApplyError(
            "Restored registry digest does not match the pre-transaction digest."
        )
    transaction_state.rollback_status = "complete"


def _registry_copy_digest(root: Path, index_relative_path: Path) -> str | None:
    if not os.path.lexists(root):
        return None
    index = _load_registry_index(root / index_relative_path)
    return _registry_digest(index, overrides={})


def _replace_registry_path(source: Path, destination: Path, *, phase: str) -> None:
    del phase
    source.replace(destination)


def _accepted_records(
    value: CurationResult | AuthenticatedCurationBundle | str | Path,
) -> tuple[Literal["curation_result", "written_curation_bundle"], tuple[_AcceptedRecord, ...]]:
    if isinstance(value, CurationResult):
        if isinstance(value, CuratorAuthoredRegistryResult):
            try:
                value.verify_integrity()
            except RegistryRecordAuthoringError as exc:
                raise RegistryPromotionPlanError(str(exc)) from exc
        elif isinstance(value, CuratorAuthoredParameterResult):
            try:
                value.verify_integrity()
            except ParameterRecordAuthoringError as exc:
                raise RegistryPromotionPlanError(str(exc)) from exc
        elif any(
            isinstance(item.proposed_record.get("provenance"), Mapping)
            and REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY
            in item.proposed_record["provenance"]
            for item in value.accepted_records
        ):
            raise RegistryPromotionPlanError(
                "In-memory registry-authoring records require "
                "CuratorAuthoredRegistryResult integrity metadata."
            )
        elif any(
            item.record_type == "parameter_records"
            and classify_parameter_provenance(
                item.proposed_record.get("provenance")
                if isinstance(item.proposed_record.get("provenance"), Mapping)
                else None,
                curation_metadata=item.to_dict()["curation"],
            )
            == "parameter_bridge"
            for item in value.accepted_records
        ):
            raise RegistryPromotionPlanError(
                "In-memory parameter-authoring records require CuratorAuthoredParameterResult "
                "integrity metadata."
            )
        records = tuple(_accepted_record_from_memory(item) for item in value.accepted_records)
        return "curation_result", records
    if isinstance(value, AuthenticatedCurationBundle):
        try:
            authenticated = value.reload()
        except (CurationError, CuratorSignatureError) as exc:
            raise RegistryPromotionPlanError(
                "Authenticated curation input failed current checksum or "
                "signature revalidation."
            ) from exc
        return (
            "written_curation_bundle",
            _accepted_records_from_validated_bundle(authenticated.bundle),
        )
    return "written_curation_bundle", _accepted_records_from_bundle(value)


def _accepted_record_from_memory(record: CurationRecord) -> _AcceptedRecord:
    if record.classification != "eligible_for_review":
        raise RegistryPromotionPlanError(
            f"Explicitly accepted record {record.record_id!r} is not eligible for promotion review."
        )
    curation = record.to_dict().get("curation")
    if not isinstance(curation, Mapping):
        raise RegistryPromotionPlanError(
            f"Explicitly accepted record {record.record_id!r} lacks curation metadata."
        )
    _validate_accepted_curation(record.record_id, curation)
    target_record = deepcopy(dict(record.proposed_record))
    _validate_target_record(record.record_id, target_record)
    return _AcceptedRecord(
        record_type=record.record_type,
        record_id=record.record_id,
        target_record=target_record,
        curation_metadata=deepcopy(dict(curation)),
    )


def _accepted_records_from_bundle(value: str | Path) -> tuple[_AcceptedRecord, ...]:
    try:
        bundle = _load_curation_bundle_for_promotion(value)
    except CurationError as exc:
        raise RegistryPromotionPlanError(str(exc)) from exc
    return _accepted_records_from_validated_bundle(bundle)


def _accepted_records_from_validated_bundle(
    bundle: LoadedCurationBundle,
) -> tuple[_AcceptedRecord, ...]:
    accepted = _accepted_records_from_loaded_bundle(bundle)
    summary = bundle.manifest.get("summary")
    if not isinstance(summary, Mapping):
        raise RegistryPromotionPlanError("Curation manifest requires a summary mapping.")
    has_parameter_authoring_summary = (
        isinstance(summary, Mapping) and summary.get("workflow") == PARAMETER_AUTHORING_WORKFLOW
    )
    has_registry_authoring_summary = (
        summary.get("workflow") == REGISTRY_RECORD_AUTHORING_WORKFLOW
    )
    requires_parameter_authoring = any(
        item.record_type == "parameter_records"
        and classify_parameter_provenance(
            item.target_record.get("provenance")
            if isinstance(item.target_record.get("provenance"), Mapping)
            else None,
            curation_metadata=item.curation_metadata,
        )
        == "parameter_bridge"
        for item in accepted
    )
    requires_registry_authoring = any(
        isinstance(item.target_record.get("provenance"), Mapping)
        and REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY
        in item.target_record["provenance"]
        for item in accepted
    )
    if (
        not has_parameter_authoring_summary
        and not requires_parameter_authoring
        and not has_registry_authoring_summary
        and not requires_registry_authoring
    ):
        try:
            bundle = load_curation_bundle(bundle.manifest_path)
        except CurationError as exc:
            raise RegistryPromotionPlanError(str(exc)) from exc
        accepted = _accepted_records_from_loaded_bundle(bundle)
    if has_parameter_authoring_summary or requires_parameter_authoring:
        if len(accepted) != 1:
            raise RegistryPromotionPlanError(
                "A written parameter-authoring bundle must contain exactly one accepted parameter target."
            )
        item = accepted[0]
        try:
            validate_parameter_authoring_bundle_record(
                summary=summary,
                manifest=bundle.manifest,
                proposed_payload=bundle.proposed_records_payload,
                accepted_payload=bundle.accepted_records_payload,
                rejected_payload=bundle.rejected_records_payload,
                eligible_records_csv_payload=bundle.eligible_records_csv_payload,
                excluded_records_csv_payload=bundle.excluded_records_csv_payload,
                record_type=item.record_type,
                target_record=item.target_record,
                curation_metadata=item.curation_metadata,
                curation_report=bundle.curation_report,
            )
        except ParameterRecordAuthoringError as exc:
            raise RegistryPromotionPlanError(str(exc)) from exc
    elif has_registry_authoring_summary or requires_registry_authoring:
        try:
            validate_registry_record_authoring_bundle(
                summary=summary,
                manifest=bundle.manifest,
                proposed_payload=bundle.proposed_records_payload,
                accepted_payload=bundle.accepted_records_payload,
                rejected_payload=bundle.rejected_records_payload,
                eligible_records_csv_payload=bundle.eligible_records_csv_payload,
                excluded_records_csv_payload=bundle.excluded_records_csv_payload,
                records=tuple(
                    (
                        item.record_type,
                        item.target_record,
                        item.curation_metadata,
                    )
                    for item in accepted
                ),
                curation_report=bundle.curation_report,
            )
        except RegistryRecordAuthoringError as exc:
            raise RegistryPromotionPlanError(str(exc)) from exc
    return accepted


def _accepted_records_from_loaded_bundle(
    bundle: LoadedCurationBundle,
) -> tuple[_AcceptedRecord, ...]:
    record_types = _accepted_record_types_from_csv_payload(
        bundle.eligible_records_csv_payload
    )
    raw_records = bundle.accepted_records_payload.get("records")
    if not isinstance(raw_records, list):
        raise RegistryPromotionPlanError("Accepted curation artifact requires a records list.")
    accepted: list[_AcceptedRecord] = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            raise RegistryPromotionPlanError(
                f"Accepted curation record at index {index} must be a mapping."
            )
        record_payload = deepcopy(dict(raw_record))
        curation = record_payload.pop("curation", None)
        record_id = record_payload.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise RegistryPromotionPlanError(
                f"Accepted curation record at index {index} requires a non-empty record_id."
            )
        if not isinstance(curation, Mapping):
            raise RegistryPromotionPlanError(
                f"Accepted curation record {record_id!r} lacks curation metadata."
            )
        _validate_accepted_curation(record_id, curation)
        try:
            record_type = record_types[record_id]
        except KeyError as exc:
            raise RegistryPromotionPlanError(
                f"Accepted curation record {record_id!r} lacks a matching "
                "accepted eligible-record row."
            ) from exc
        _validate_target_record(record_id, record_payload)
        accepted.append(
            _AcceptedRecord(
                record_type=record_type,
                record_id=record_id,
                target_record=record_payload,
                curation_metadata=deepcopy(dict(curation)),
            )
        )

    accepted_ids = [item.record_id for item in accepted]
    if len(accepted_ids) != len(set(accepted_ids)):
        raise RegistryPromotionPlanError(
            "Accepted curation artifact contains duplicate record IDs."
        )
    if set(accepted_ids) != set(record_types):
        raise RegistryPromotionPlanError(
            "Accepted curation YAML and eligible-record CSV accepted decisions do not match."
        )
    return tuple(accepted)


def _accepted_record_types_from_csv_payload(
    payload: Mapping[str, Any],
) -> dict[str, str]:
    rows = payload.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise RegistryPromotionPlanError("Eligible-record CSV requires structured rows.")
    accepted: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise RegistryPromotionPlanError("Eligible-record CSV rows must be mappings.")
        if row.get("decision") != "accept" or row.get("explicit_decision") != "true":
            continue
        if row.get("classification") != "eligible_for_review":
            raise RegistryPromotionPlanError(
                f"Eligible-record CSV marks accepted record {row.get('record_id')!r} as blocked."
            )
        raw_record_id = row.get("record_id")
        raw_record_type = row.get("record_type")
        record_id = raw_record_id.strip() if isinstance(raw_record_id, str) else ""
        record_type = raw_record_type.strip() if isinstance(raw_record_type, str) else ""
        if not record_id or not record_type:
            raise RegistryPromotionPlanError(
                "Eligible-record CSV accepted rows require record_id and record_type."
            )
        if record_id in accepted:
            raise RegistryPromotionPlanError(
                f"Eligible-record CSV contains duplicate accepted id {record_id!r}."
            )
        accepted[record_id] = record_type
    return accepted


def _validate_accepted_curation(record_id: str, curation: Mapping[str, Any]) -> None:
    if curation.get("classification") != "eligible_for_review":
        raise RegistryPromotionPlanError(
            f"Accepted record {record_id!r} must be eligible_for_review."
        )
    if curation.get("decision") != "accept" or curation.get("explicit_decision") is not True:
        raise RegistryPromotionPlanError(
            f"Record {record_id!r} is not an explicit accepted curation decision."
        )
    if curation.get("allowed_use") != CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION:
        raise RegistryPromotionPlanError(
            f"Accepted record {record_id!r} must use pending registry-promotion review policy."
        )
    if curation.get("promotion_status") != "not_promoted_to_production_registry":
        raise RegistryPromotionPlanError(
            f"Accepted record {record_id!r} has an unsupported promotion status."
        )
    for field in ("curator", "decision_reason", "curation_date"):
        value = curation.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RegistryPromotionPlanError(
                f"Accepted record {record_id!r} requires non-empty curation.{field}."
            )
    curation_date = curation.get("curation_date")
    assert isinstance(curation_date, str)
    if not curation_date_is_iso(curation_date):
        raise RegistryPromotionPlanError(
            f"Accepted record {record_id!r} requires curation_date in YYYY-MM-DD form."
        )
    limitations = curation.get("limitations")
    if not _nonempty_string_sequence(limitations):
        raise RegistryPromotionPlanError(
            f"Accepted record {record_id!r} requires explicit curation limitations."
        )
    for field in ("missing_fields", "reasons"):
        value = curation.get(field)
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes, bytearray))
            or bool(value)
        ):
            raise RegistryPromotionPlanError(
                f"Accepted record {record_id!r} requires empty curation "
                "missing_fields and reasons."
            )
    provenance = curation.get("source_provenance")
    provenance_missing = curation_source_provenance_missing(
        provenance if isinstance(provenance, Mapping) else {}
    )
    if provenance_missing:
        raise RegistryPromotionPlanError(
            f"Accepted record {record_id!r} has incomplete source provenance: "
            f"{', '.join(provenance_missing)}."
        )


def _validate_target_record(record_id: str, record: Mapping[str, Any]) -> None:
    if record.get("record_id") != record_id:
        raise RegistryPromotionPlanError(
            f"Accepted record id {record_id!r} does not match its target record payload."
        )
    _require_string_mapping_keys(record, label=f"Accepted record {record_id!r}")


def _target_record_with_curation_audit(record: _AcceptedRecord) -> Mapping[str, Any]:
    _validate_source_identity_consistency(
        record.record_id,
        target_record=record.target_record,
        curation_metadata=record.curation_metadata,
    )
    target_record = deepcopy(dict(record.target_record))
    provenance = target_record.get("provenance")
    if not isinstance(provenance, Mapping):
        raise RegistryPromotionPlanError(
            "curation_audit_requires_mapping_target_provenance"
        )
    if _CURATION_AUDIT_PROVENANCE_KEY in provenance:
        raise RegistryPromotionPlanError(
            "curation_audit_provenance_key_already_exists_no_overwrite"
        )
    updated_provenance = deepcopy(dict(provenance))
    updated_provenance[_CURATION_AUDIT_PROVENANCE_KEY] = _curation_audit_payload(
        record.curation_metadata
    )
    target_record["provenance"] = updated_provenance
    return target_record


def _curation_audit_payload(curation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "curator": curation.get("curator"),
        "curation_date": curation.get("curation_date"),
        "decision": curation.get("decision"),
        "decision_reason": curation.get("decision_reason"),
        "limitations": deepcopy(curation.get("limitations")),
        "source_provenance": deepcopy(curation.get("source_provenance")),
        "allowed_use_decision": curation.get("allowed_use"),
    }


def _validate_source_identity_consistency(
    record_id: str,
    *,
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
) -> None:
    target_provenance = target_record.get("provenance")
    curation_provenance = curation_metadata.get("source_provenance")
    if not isinstance(target_provenance, Mapping) or not isinstance(
        curation_provenance,
        Mapping,
    ):
        return
    target_identity = _canonical_source_identity(
        target_provenance,
        label=f"Target record {record_id!r} provenance",
    )
    curation_identity = _canonical_source_identity(
        curation_provenance,
        label=f"Curation record {record_id!r} source provenance",
    )
    for field in sorted(set(target_identity) & set(curation_identity)):
        if not _type_exact_equal(target_identity[field], curation_identity[field]):
            raise RegistryPromotionPlanError(
                f"curation_source_identity_conflict: {field}"
            )


def _canonical_source_identity(
    provenance: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, str | tuple[str, ...]]:
    identity: dict[str, str | tuple[str, ...]] = {}
    for field in ("source_database", "source_snapshot_path", "source_url"):
        if field not in provenance:
            continue
        value = provenance[field]
        if field in {"source_snapshot_path", "source_url"} and (
            value is None or value == ""
        ):
            continue
        if not isinstance(value, str) or not value.strip():
            raise RegistryPromotionPlanError(
                f"{label} has invalid source identity field {field!r}."
            )
        identity[field] = value

    plural_ids: tuple[str, ...] | None = None
    if "source_entry_ids" in provenance:
        raw_ids = provenance["source_entry_ids"]
        if not _nonempty_string_sequence(raw_ids):
            raise RegistryPromotionPlanError(
                f"{label} has invalid source identity field 'source_entry_ids'."
            )
        assert isinstance(raw_ids, Sequence) and not isinstance(
            raw_ids,
            (str, bytes, bytearray),
        )
        plural_ids = tuple(sorted(raw_ids))

    singular_ids: tuple[str, ...] | None = None
    if "source_entry_id" in provenance:
        raw_id = provenance["source_entry_id"]
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise RegistryPromotionPlanError(
                f"{label} has invalid source identity field 'source_entry_id'."
            )
        singular_ids = (raw_id,)

    if plural_ids is not None and singular_ids is not None:
        if not _type_exact_equal(plural_ids, singular_ids):
            raise RegistryPromotionPlanError(
                f"{label} has contradictory source_entry_id/source_entry_ids values."
            )
    entry_ids = plural_ids if plural_ids is not None else singular_ids
    if entry_ids is not None:
        identity["source_entry_ids"] = entry_ids
    return identity


def _load_registry_index(value: str | Path) -> _RegistryIndex:
    path = Path(value)
    if ".." in path.parts:
        raise RegistryPromotionPlanError(f"Registry index path traversal is not allowed: {path}")
    _reject_symlink_components(path, label="Registry index path")
    try:
        index_path = path.resolve(strict=True)
    except OSError as exc:
        raise RegistryPromotionPlanError(f"Registry index does not exist: {path}") from exc
    if not index_path.is_file():
        raise RegistryPromotionPlanError(f"Registry index is not a file: {index_path}")
    payload = _read_yaml_mapping(index_path, label="Registry index")
    if payload.get("kind") != "fungmod_registry_index":
        raise RegistryPromotionPlanError(
            f"Registry index {index_path} must use kind: fungmod_registry_index."
        )
    records = payload.get("records")
    if not isinstance(records, Mapping):
        raise RegistryPromotionPlanError(f"Registry index {index_path} requires a records mapping.")

    root = index_path.parent.resolve(strict=True)
    targets: dict[str, _TargetFile] = {}
    used_paths: dict[Path, str] = {}
    for raw_key in sorted(records, key=lambda item: str(item)):
        key = str(raw_key)
        raw_destination = records[raw_key]
        if not isinstance(raw_destination, str) or not raw_destination.strip():
            raise RegistryPromotionPlanError(
                f"Registry index records.{key} must be a non-empty relative path."
            )
        relative = Path(raw_destination)
        if relative.is_absolute():
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} must be relative to the registry root."
            )
        if ".." in relative.parts:
            raise RegistryPromotionPlanError(
                f"Registry destination traversal is not allowed for records.{key}: {raw_destination}"
            )
        destination = root / relative
        _reject_symlink_components(destination, label=f"Registry destination records.{key}")
        try:
            resolved = destination.resolve(strict=True)
        except OSError as exc:
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} does not exist: {destination}"
            ) from exc
        if root != resolved.parent and root not in resolved.parents:
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} resolves outside the registry root: {resolved}"
            )
        if not resolved.is_file():
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} is not a regular file: {resolved}"
            )
        if resolved == index_path:
            raise RegistryPromotionPlanError(f"Registry destination records.{key} cannot be the index file.")
        if resolved in used_paths:
            raise RegistryPromotionPlanError(
                f"Registry destinations records.{used_paths[resolved]} and records.{key} share one file."
            )
        used_paths[resolved] = key
        target_payload = _read_yaml_mapping(resolved, label=f"Registry records.{key}")
        if target_payload.get("kind") != "fungmod_registry_records":
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} must use kind: fungmod_registry_records."
            )
        if target_payload.get("record_type") != key:
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} has record_type {target_payload.get('record_type')!r}."
            )
        raw_records = target_payload.get("records")
        if not isinstance(raw_records, list) or not all(
            isinstance(item, Mapping) for item in raw_records
        ):
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} requires a records list of mappings."
            )
        ids = [item.get("record_id") for item in raw_records]
        if any(not isinstance(record_id, str) or not record_id for record_id in ids):
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} contains a missing or invalid record_id."
            )
        if len(ids) != len(set(ids)):
            raise RegistryPromotionPlanError(
                f"Registry destination records.{key} contains duplicate record IDs."
            )
        relative_path = resolved.relative_to(root).as_posix()
        targets[key] = _TargetFile(
            registry_key=key,
            path=resolved,
            relative_path=relative_path,
            before_sha256=_sha256_bytes(resolved.read_bytes()),
            payload=target_payload,
        )

    raw_version = payload.get("version")
    version = raw_version if isinstance(raw_version, str) else ""
    return _RegistryIndex(
        path=index_path,
        root=root,
        sha256=_sha256_bytes(index_path.read_bytes()),
        version=version,
        payload=payload,
        targets=targets,
    )


def _validate_current_registry(index: _RegistryIndex) -> None:
    try:
        load_registry(index.path)
    except Exception as exc:
        raise RegistryPromotionPlanError(
            f"Target registry is invalid before planning: {_format_validation_error(exc)}"
        ) from exc


def _record_by_id(target: _TargetFile, record_id: str) -> Mapping[str, Any] | None:
    records = target.payload["records"]
    if not isinstance(records, list):  # guarded when the target is loaded
        raise RegistryPromotionPlanError(f"Registry target {target.path} has no records list.")
    for record in records:
        if isinstance(record, Mapping) and record.get("record_id") == record_id:
            return record
    return None


def _merged_target_content(
    target: _TargetFile,
    additions: Sequence[Mapping[str, Any]],
) -> str:
    payload = deepcopy(dict(target.payload))
    records = payload.get("records")
    if not isinstance(records, list):
        raise RegistryPromotionPlanError(f"Registry target {target.path} has no records list.")
    records.extend(deepcopy(dict(item)) for item in additions)
    canonical = _canonicalize(payload)
    return yaml.safe_dump(
        canonical,
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
    )


def _staged_candidate_validation_error(
    index: _RegistryIndex,
    *,
    target: _TargetFile,
    candidate: _AcceptedRecord,
    overrides: Mapping[str, str],
) -> str | None:
    with _staged_registry(
        index,
        overrides=overrides,
        prefix="fungmod-registry-promotion-candidate-",
    ) as (staged_index, stage):
        try:
            registry = load_registry(staged_index)
        except Exception as exc:
            return f"target_schema_validation_failed: {_format_validation_error(exc, stage=stage)}"

        runtime_records = getattr(registry, target.registry_key, None)
        if not isinstance(runtime_records, Mapping):
            return (
                "target_loader_fidelity_failed: runtime registry has no mapping for "
                f"{target.registry_key!r}"
            )
        runtime_record = runtime_records.get(candidate.record_id)
        if runtime_record is None or not hasattr(runtime_record, "to_dict"):
            return (
                "target_loader_fidelity_failed: runtime record was not recoverable after "
                "the staged load"
            )
        runtime_payload = runtime_record.to_dict()
        dropped, synthesized, changed = _round_trip_differences(
            candidate.target_record,
            runtime_payload,
        )
        if dropped or synthesized or changed:
            return (
                "target_loader_fidelity_failed: "
                f"silently_dropped_fields={list(dropped)}, "
                f"synthesized_or_defaulted_fields={list(synthesized)}, "
                f"changed_fields={list(changed)}"
            )
    return None


def _staged_registry_validation_error(
    index: _RegistryIndex,
    *,
    overrides: Mapping[str, str],
    prefix: str,
) -> str | None:
    with _staged_registry(index, overrides=overrides, prefix=prefix) as (staged_index, stage):
        try:
            load_registry(staged_index)
        except Exception as exc:
            return _format_validation_error(exc, stage=stage)
    return None


@contextmanager
def _staged_registry(
    index: _RegistryIndex,
    *,
    overrides: Mapping[str, str],
    prefix: str,
) -> Iterator[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        _registry_tree_hashes(index.root)
        stage = Path(temp_dir) / index.root.name
        shutil.copytree(index.root, stage, copy_function=shutil.copy2)
        staged_index = stage / index.path.relative_to(index.root)
        for relative_path, content in overrides.items():
            destination = stage / relative_path
            if not destination.is_file():
                raise RegistryPromotionPlanError(
                    f"Prospective registry override is not an existing regular file: {relative_path}"
                )
            destination.write_text(content, encoding="utf-8")
        yield staged_index, stage


def _registry_digest(index: _RegistryIndex, *, overrides: Mapping[str, str]) -> str:
    file_hashes = _registry_tree_hashes(index.root)
    for relative_path, content in overrides.items():
        if relative_path not in file_hashes:
            raise RegistryPromotionPlanError(
                f"Registry digest override is not an existing regular file: {relative_path}"
            )
        file_hashes[relative_path] = _sha256_bytes(content.encode("utf-8"))
    return _sha256_json(file_hashes)


def _registry_tree_hashes(root: Path) -> dict[str, str]:
    try:
        return tree_file_hashes(root, label="Registry root")
    except TreeIntegrityError as exc:
        raise RegistryPromotionPlanError(str(exc)) from exc


def _raise_bundle_walk_error(error: OSError) -> None:
    raise RegistryPromotionApplyError(
        f"Cannot inspect promotion-plan bundle safely: {error}"
    ) from error


def _write_plan_bundle(root: Path, plan: RegistryPromotionPlan) -> None:
    paths = _plan_artifact_paths(root, plan)
    candidates_payload = {
        "kind": "fungmod_registry_promotion_plan_candidates",
        "schema_version": REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION,
        "plan_digest": plan.plan_digest,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "records": [item.to_dict() for item in plan.candidates],
    }
    paths["candidate_classifications"].write_text(
        yaml.safe_dump(
            _canonicalize(candidates_payload),
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    paths["promotion_report"].write_text(_promotion_report(plan), encoding="utf-8")
    for item in plan.prospective_files:
        artifact = paths[f"prospective:{item.target_registry_path}"]
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(item.content, encoding="utf-8")

    manifest_path = paths["promotion_plan"]
    artifact_checksums = {
        path.relative_to(root).as_posix(): _sha256_bytes(path.read_bytes())
        for key, path in sorted(paths.items())
        if key != "promotion_plan"
    }
    prospective_metadata = []
    for item in plan.prospective_files:
        metadata = item.to_dict(include_content=False)
        metadata["artifact_path"] = f"prospective_registry/{item.target_registry_path}"
        prospective_metadata.append(metadata)
    manifest = {
        "kind": REGISTRY_PROMOTION_PLAN_MANIFEST_KIND,
        "schema_version": REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION,
        "plan_digest": plan.plan_digest,
        "input_kind": plan.input_kind,
        "registry_index_path": str(plan.registry_index_path),
        "registry_root": str(plan.registry_root),
        "registry_index_sha256": plan.registry_index_sha256,
        "before_registry_digest": plan.before_registry_digest,
        "prospective_registry_digest": plan.prospective_registry_digest,
        "summary": plan.summary(),
        "candidates": [item.to_dict() for item in plan.candidates],
        "prospective_files": prospective_metadata,
        "files": artifact_checksums,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "apply_available": plan.summary()["apply_available"],
        "apply_policy": _PROMOTION_APPLY_POLICY,
        "version_policy": _PROMOTION_VERSION_POLICY,
    }
    manifest_path.write_text(
        json.dumps(_canonicalize(manifest), indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _plan_artifact_paths(root: Path, plan: RegistryPromotionPlan) -> dict[str, Path]:
    paths = {
        "promotion_plan": root / "promotion_plan.json",
        "promotion_report": root / "promotion_report.md",
        "candidate_classifications": root / "candidate_classifications.yml",
    }
    for item in plan.prospective_files:
        paths[f"prospective:{item.target_registry_path}"] = (
            root / "prospective_registry" / item.target_registry_path
        )
    return paths


def _promotion_report(plan: RegistryPromotionPlan) -> str:
    summary = plan.summary()
    lines = [
        "# CURATION-001 Registry Promotion Plan",
        "",
        f"- Schema version: `{REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION}`",
        f"- Registry index: `{plan.registry_index_path}`",
        f"- Registry index SHA-256: `{plan.registry_index_sha256}`",
        f"- Before registry digest: `{plan.before_registry_digest}`",
        f"- Prospective registry digest: `{plan.prospective_registry_digest}`",
        f"- Plan digest: `{plan.plan_digest}`",
        f"- Explicitly accepted records considered: {summary['accepted_records_considered']}",
        f"- Addable: {summary['addable_count']}",
        f"- Exact duplicate/no-op: {summary['exact_duplicate_count']}",
        f"- Conflict: {summary['conflict_count']}",
        f"- Blocked/unsupported: {summary['blocked_unsupported_count']}",
        f"- Apply available: {str(summary['apply_available']).lower()}",
        "",
        "## Scope",
        "",
        "This is a deterministic preview and confirmation artifact. It does not mutate the production registry, authorize simulation, or claim scientific validation. Applying it requires the exact plan digest, the exact next numeric patch version, a safe current registry index, and the separate transactional apply operation.",
        "",
        "## Candidate Classifications",
        "",
        "| Record type | Record ID | Classification | Target | Before SHA-256 | After SHA-256 | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if plan.candidates:
        lines.extend(
            "| "
            f"{_md(item.record_type)} | `{_md(item.record_id)}` | {item.classification} | "
            f"{_md('' if item.target_path is None else str(item.target_path))} | "
            f"{item.before_sha256 or ''} | {item.after_sha256 or ''} | {_md(item.reason)} |"
            for item in plan.candidates
        )
    else:
        lines.append("| none | none | none | none | none | none | no explicit accepted decisions |")
    lines.extend(["", "## Prospective Files", ""])
    if plan.prospective_files:
        lines.extend(
            f"- `{item.target_path}`: `{item.before_sha256}` -> `{item.after_sha256}`"
            for item in plan.prospective_files
        )
    else:
        lines.append("- No target file content changes are planned.")
    return "\n".join(lines) + "\n"


def _safe_output_path(output_dir: str | Path, *, registry_root: Path) -> Path:
    path = Path(output_dir)
    if ".." in path.parts:
        raise RegistryPromotionPlanError(
            f"Promotion-plan output path traversal is not allowed: {path}"
        )
    _reject_symlink_components(path, label="Promotion-plan output path")
    resolved = path.resolve(strict=False)
    package_registry = default_registry_path().parent.resolve(strict=False)
    for forbidden in {registry_root.resolve(strict=False), package_registry}:
        if (
            resolved == forbidden
            or forbidden in resolved.parents
            or resolved in forbidden.parents
        ):
            raise RegistryPromotionPlanError(
                "Promotion-plan output path overlaps a registry root."
            )
    return resolved


def _validate_replaceable_destination(destination: Path) -> None:
    if not destination.exists():
        return
    if not destination.is_dir():
        raise RegistryPromotionPlanError(
            f"Promotion-plan output path exists and is not a directory: {destination}"
        )
    manifest_path = destination / "promotion_plan.json"
    _reject_symlink_components(manifest_path, label="Existing promotion-plan manifest path")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryPromotionPlanError(
            "Refusing to replace an existing directory without a readable owned "
            f"promotion-plan manifest: {destination}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise RegistryPromotionPlanError(
            f"Refusing to replace existing directory with a non-object manifest: {destination}"
        )
    if (
        manifest.get("kind") != REGISTRY_PROMOTION_PLAN_MANIFEST_KIND
        or manifest.get("schema_version") != REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION
    ):
        raise RegistryPromotionPlanError(
            "Refusing to replace an existing directory not owned by this promotion-plan "
            f"kind/version: {destination}"
        )


def _replace_directory(staging: Path, destination: Path) -> None:
    if not destination.exists():
        staging.replace(destination)
        return
    backup = staging.with_name(staging.name + ".previous")
    destination.replace(backup)
    try:
        staging.replace(destination)
    except Exception:
        backup.replace(destination)
        raise
    shutil.rmtree(backup)


def _read_json_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryPromotionPlanError(f"Malformed {label.lower()} {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RegistryPromotionPlanError(f"{label} {path} must contain a JSON object.")
    return payload


def _read_yaml_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RegistryPromotionPlanError(f"Malformed {label.lower()} {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RegistryPromotionPlanError(f"{label} {path} must contain a YAML mapping.")
    return payload


def _read_utf8_text(path: Path, *, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RegistryPromotionPlanError(f"Malformed {label.lower()} {path}: {exc}") from exc


def _reject_symlink_components(path: Path, *, label: str) -> None:
    symlink = first_symlink_component(path)
    if symlink is not None:
        raise RegistryPromotionPlanError(f"{label} contains a symlink component: {symlink}")


def _require_string_mapping_keys(value: Any, *, label: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RegistryPromotionPlanError(f"{label} contains a non-string mapping key.")
            _require_string_mapping_keys(item, label=label)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _require_string_mapping_keys(item, label=label)


def _format_validation_error(exc: Exception, *, stage: Path | None = None) -> str:
    message = " ".join(str(exc).split())
    if stage is not None:
        message = message.replace(str(stage), "<staged_registry>")
    return f"{type(exc).__name__}: {message}"


def _sha256_json(value: Any) -> str:
    try:
        encoded = json.dumps(
            _canonicalize(value),
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RegistryPromotionPlanError(
            f"Promotion plan contains non-canonical data: {exc}"
        ) from exc
    return _sha256_bytes(encoded)


def _nonempty_string_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "ProspectiveRegistryFile",
    "REGISTRY_PROMOTION_PLAN_MANIFEST_KIND",
    "REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION",
    "RegistryPromotionAppliedFile",
    "RegistryPromotionApplyError",
    "RegistryPromotionApplyResult",
    "RegistryPromotionCandidate",
    "RegistryPromotionPlan",
    "RegistryPromotionPlanError",
    "RegistryPromotionPlanWriteResult",
    "apply_registry_promotion",
    "plan_registry_promotion",
]
