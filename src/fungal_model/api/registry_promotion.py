"""Deterministic preview plans for accepted curation records.

This module intentionally has no production registry mutation or apply API.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
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

from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    CURATION_MANIFEST_KIND,
    CURATION_SCHEMA_VERSION,
    CurationRecord,
    CurationResult,
    curation_date_is_iso,
    curation_source_provenance_missing,
)
from fungal_model.registry.loaders import load_registry


REGISTRY_PROMOTION_PLAN_SCHEMA_VERSION = "1.0.0"
REGISTRY_PROMOTION_PLAN_MANIFEST_KIND = "fungmod_registry_promotion_plan_manifest"

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
}
_CURATION_BUNDLE_FILES = frozenset(
    {
        "curation_report.md",
        "eligible_records.csv",
        "excluded_records.csv",
        "proposed_registry_records.yml",
        "accepted_registry_records.yml",
        "rejected_registry_records.yml",
    }
)
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class RegistryPromotionPlanError(ValueError):
    """Raised when a safe deterministic promotion preview cannot be built."""


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
class RegistryPromotionPlan:
    """Validated preview of accepted records without a registry apply operation."""

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
            "apply_available": False,
            "apply_policy": "deferred_to_pr47_digest_confirmed_transactional_apply",
            "version_policy": "not_defined_deferred_to_later_apply_contract",
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
    targets: Mapping[str, _TargetFile]


def plan_registry_promotion(
    curation_bundle_or_result: CurationResult | str | Path,
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

        if item.record_type == "product_maps":
            candidates.append(
                _candidate(
                    item,
                    classification="blocked_unsupported",
                    reason="unsupported_pending_destination_contract",
                )
            )
            continue

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

        candidate_content = _merged_target_content(target, (item.target_record,))
        validation_error = _staged_candidate_validation_error(
            index,
            target=target,
            candidate=item,
            overrides={target.relative_path: candidate_content},
        )
        if validation_error is not None:
            candidates.append(
                _candidate(
                    item,
                    registry_key=registry_key,
                    classification="blocked_unsupported",
                    reason=validation_error,
                    target=target,
                )
            )
            continue

        candidates.append(
            _candidate(
                item,
                registry_key=registry_key,
                classification="addable",
                reason="accepted_record_is_addable_without_overwrite",
                target=target,
            )
        )
        accepted_by_key.setdefault(registry_key, []).append(item)

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
        "apply_available": False,
        "apply_policy": "deferred_to_pr47_digest_confirmed_transactional_apply",
        "version_policy": "not_defined_deferred_to_later_apply_contract",
    }


def _verify_plan_digest(plan: RegistryPromotionPlan) -> None:
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


def _accepted_records(
    value: CurationResult | str | Path,
) -> tuple[Literal["curation_result", "written_curation_bundle"], tuple[_AcceptedRecord, ...]]:
    if isinstance(value, CurationResult):
        records = tuple(_accepted_record_from_memory(item) for item in value.accepted_records)
        return "curation_result", records
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
    manifest_path = _curation_manifest_path(value)
    manifest = _read_json_mapping(manifest_path, label="Curation manifest")
    if manifest.get("kind") != CURATION_MANIFEST_KIND:
        raise RegistryPromotionPlanError(
            f"Written input is not an owned curation bundle of kind {CURATION_MANIFEST_KIND!r}."
        )
    if manifest.get("schema_version") != CURATION_SCHEMA_VERSION:
        raise RegistryPromotionPlanError(
            f"Unsupported curation bundle schema version {manifest.get('schema_version')!r}."
        )
    if manifest.get("production_registry_mutated") is not False:
        raise RegistryPromotionPlanError("Curation bundle must declare production_registry_mutated: false.")
    if manifest.get("scientific_validation_claimed") is not False:
        raise RegistryPromotionPlanError("Curation bundle must declare scientific_validation_claimed: false.")

    root = manifest_path.parent
    declared = _verify_declared_curation_artifacts(root, manifest)
    accepted_path = declared["accepted_registry_records.yml"]
    eligible_path = declared["eligible_records.csv"]
    accepted_payload = _read_yaml_mapping(accepted_path, label="Accepted curation records")
    if accepted_payload.get("kind") != "fungmod_curation_decision_records":
        raise RegistryPromotionPlanError("Accepted curation artifact has an unsupported kind.")
    if accepted_payload.get("schema_version") != CURATION_SCHEMA_VERSION:
        raise RegistryPromotionPlanError("Accepted curation artifact has an unsupported schema version.")
    if accepted_payload.get("bundle_status") != "accepted":
        raise RegistryPromotionPlanError("Accepted curation artifact must use bundle_status: accepted.")
    if accepted_payload.get("allowed_use") != CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY:
        raise RegistryPromotionPlanError("Accepted curation artifact must remain review-only at bundle level.")
    if accepted_payload.get("production_registry_promotion") is not False:
        raise RegistryPromotionPlanError("Accepted curation artifact must not claim registry promotion.")

    record_types = _accepted_record_types_from_csv(eligible_path)
    raw_records = accepted_payload.get("records")
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
                f"Accepted curation record {record_id!r} lacks a matching accepted eligible-record row."
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
        raise RegistryPromotionPlanError("Accepted curation artifact contains duplicate record IDs.")
    if set(accepted_ids) != set(record_types):
        raise RegistryPromotionPlanError(
            "Accepted curation YAML and eligible-record CSV accepted decisions do not match."
        )
    summary = manifest.get("summary")
    if not isinstance(summary, Mapping) or summary.get("accepted_count") != len(accepted):
        raise RegistryPromotionPlanError("Curation manifest accepted_count does not match accepted artifacts.")
    return tuple(accepted)


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


def _curation_manifest_path(value: str | Path) -> Path:
    path = Path(value)
    if ".." in path.parts:
        raise RegistryPromotionPlanError(f"Curation bundle path traversal is not allowed: {path}")
    _reject_symlink_components(path, label="Curation bundle path")
    manifest = path / "curation_manifest.json" if path.is_dir() else path
    if manifest.name != "curation_manifest.json":
        raise RegistryPromotionPlanError(
            "Written curation input must be a bundle directory or curation_manifest.json."
        )
    _reject_symlink_components(manifest, label="Curation manifest path")
    if not manifest.is_file():
        raise RegistryPromotionPlanError(f"Curation manifest does not exist: {manifest}")
    return manifest.resolve(strict=True)


def _verify_declared_curation_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Path]:
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise RegistryPromotionPlanError("Curation manifest requires a files checksum mapping.")
    names = {str(name) for name in files}
    if names != _CURATION_BUNDLE_FILES:
        missing = sorted(_CURATION_BUNDLE_FILES - names)
        unexpected = sorted(names - _CURATION_BUNDLE_FILES)
        raise RegistryPromotionPlanError(
            "Curation manifest artifact set does not match its owned schema; "
            f"missing={missing}, unexpected={unexpected}."
        )

    declared: dict[str, Path] = {}
    for name in sorted(names):
        digest = files[name]
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise RegistryPromotionPlanError(
                f"Curation manifest checksum for {name!r} must be a SHA-256 hex digest."
            )
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RegistryPromotionPlanError(
                f"Curation manifest artifact path is unsafe: {name!r}."
            )
        artifact = root / relative
        _reject_symlink_components(artifact, label="Curation artifact path")
        try:
            resolved = artifact.resolve(strict=True)
        except OSError as exc:
            raise RegistryPromotionPlanError(
                f"Declared curation artifact does not exist: {artifact}"
            ) from exc
        if root != resolved.parent and root not in resolved.parents:
            raise RegistryPromotionPlanError(
                f"Declared curation artifact resolves outside its bundle: {name!r}."
            )
        if not resolved.is_file():
            raise RegistryPromotionPlanError(f"Declared curation artifact is not a file: {artifact}")
        actual = _sha256_bytes(resolved.read_bytes())
        if not hmac.compare_digest(actual, digest.lower()):
            raise RegistryPromotionPlanError(
                f"Curation artifact checksum mismatch for {name!r}: expected {digest.lower()}, got {actual}."
            )
        declared[name] = resolved
    return declared


def _accepted_record_types_from_csv(path: Path) -> dict[str, str]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = tuple(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise RegistryPromotionPlanError(f"Malformed eligible-record CSV {path}: {exc}") from exc
    accepted: dict[str, str] = {}
    for row in rows:
        if row.get("decision") != "accept" or row.get("explicit_decision") != "true":
            continue
        if row.get("classification") != "eligible_for_review":
            raise RegistryPromotionPlanError(
                f"Eligible-record CSV marks accepted record {row.get('record_id')!r} as blocked."
            )
        record_id = row.get("record_id", "").strip()
        record_type = row.get("record_type", "").strip()
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

    return _RegistryIndex(
        path=index_path,
        root=root,
        sha256=_sha256_bytes(index_path.read_bytes()),
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
        stage = Path(temp_dir)
        staged_index = stage / index.path.name
        shutil.copyfile(index.path, staged_index)
        for target in index.targets.values():
            destination = stage / target.relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            override = overrides.get(target.relative_path)
            if override is None:
                shutil.copyfile(target.path, destination)
            else:
                destination.write_text(override, encoding="utf-8")
        yield staged_index, stage


def _round_trip_differences(
    expected: Any,
    actual: Any,
    *,
    path: str = "",
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    dropped: list[str] = []
    synthesized: list[str] = []
    changed: list[str] = []
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        expected_keys = {str(key) for key in expected}
        actual_keys = {str(key) for key in actual}
        dropped.extend(_field_path(path, key) for key in sorted(expected_keys - actual_keys))
        synthesized.extend(_field_path(path, key) for key in sorted(actual_keys - expected_keys))
        for key in sorted(expected_keys & actual_keys):
            nested_dropped, nested_synthesized, nested_changed = _round_trip_differences(
                expected[key],
                actual[key],
                path=_field_path(path, key),
            )
            dropped.extend(nested_dropped)
            synthesized.extend(nested_synthesized)
            changed.extend(nested_changed)
    elif not _type_exact_equal(expected, actual):
        changed.append(path or "<record>")
    return tuple(dropped), tuple(synthesized), tuple(changed)


def _field_path(parent: str, field: str) -> str:
    return field if not parent else f"{parent}.{field}"


def _registry_digest(index: _RegistryIndex, *, overrides: Mapping[str, str]) -> str:
    file_hashes = {index.path.name: index.sha256}
    for target in index.targets.values():
        override = overrides.get(target.relative_path)
        file_hashes[target.relative_path] = (
            target.before_sha256
            if override is None
            else _sha256_bytes(override.encode("utf-8"))
        )
    return _sha256_json(file_hashes)


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
        "apply_available": False,
        "apply_policy": "deferred_to_pr47_digest_confirmed_transactional_apply",
        "version_policy": "not_defined_deferred_to_later_apply_contract",
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
        "",
        "## Scope",
        "",
        "This is a deterministic preview only. It does not mutate the production registry, authorize simulation, claim scientific validation, define a registry version bump, or provide an apply operation. Digest-confirmed transactional apply and version policy remain later concerns.",
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
    package_registry = (Path(__file__).resolve().parents[3] / "data_registry").resolve(
        strict=False
    )
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


def _reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise RegistryPromotionPlanError(f"{label} contains a symlink component: {current}")


def _require_string_mapping_keys(value: Any, *, label: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RegistryPromotionPlanError(f"{label} contains a non-string mapping key.")
            _require_string_mapping_keys(item, label=label)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _require_string_mapping_keys(item, label=label)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonicalize(item) for item in value]
    return value


def _type_exact_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            return False
        if len(left) != len(right):
            return False
        for left_key, left_value in left.items():
            matching_keys = [
                right_key
                for right_key in right
                if type(left_key) is type(right_key) and left_key == right_key
            ]
            if len(matching_keys) != 1:
                return False
            if not _type_exact_equal(left_value, right[matching_keys[0]]):
                return False
        return True

    left_is_sequence = isinstance(left, Sequence) and not isinstance(
        left, (str, bytes, bytearray)
    )
    right_is_sequence = isinstance(right, Sequence) and not isinstance(
        right, (str, bytes, bytearray)
    )
    if left_is_sequence or right_is_sequence:
        if not left_is_sequence or not right_is_sequence or len(left) != len(right):
            return False
        return all(_type_exact_equal(a, b) for a, b in zip(left, right))

    return type(left) is type(right) and left == right


def _format_validation_error(exc: Exception, *, stage: Path | None = None) -> str:
    message = " ".join(str(exc).split())
    if stage is not None:
        message = message.replace(str(stage), "<staged_registry>")
    return f"{type(exc).__name__}: {message}"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
    "RegistryPromotionCandidate",
    "RegistryPromotionPlan",
    "RegistryPromotionPlanError",
    "RegistryPromotionPlanWriteResult",
    "plan_registry_promotion",
]
