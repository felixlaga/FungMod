"""Integrity-bound authoring for index-backed non-parameter registry records."""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fungal_model.api._integrity import (
    CURATION_AUDIT_PROVENANCE_KEY,
    RESERVED_PROVENANCE_KEYS,
    canonicalize,
    round_trip_differences,
    sha256_bytes,
    type_exact_equal,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_SCHEMA_VERSION,
    CurationError,
    CurationRecord,
    CurationResult,
    CurationWriteResult,
    LoadedCurationBundle,
    canonicalize_curation_artifact_value,
    curation_date_is_iso,
    curation_manifest_payload,
    curation_records_csv_payload,
    curation_records_payload,
    curation_source_provenance_missing,
    load_curation_bundle,
    render_curation_report,
    validate_reviewable_source_record,
)
from fungal_model.api.curator_signatures import (
    AuthenticatedCurationBundle,
    CuratorSignatureError,
)
from fungal_model.provenance import REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY
from fungal_model.registry.loaders import (
    RegistryLoadError,
    load_registry_record_mapping,
)


REGISTRY_RECORD_AUTHORING_SCHEMA_VERSION = "1.0.0"
REGISTRY_RECORD_AUTHORING_WORKFLOW = "curator_authored_registry_records"
SUPPORTED_AUTHORED_REGISTRY_RECORD_TYPES = (
    "fungi",
    "substrates",
    "enzyme_classes",
    "process_compatibility",
    "case_templates",
    "product_maps",
)
REGISTRY_RECORD_AUTHORING_ALLOWED_MATURITIES = (
    "exploratory_metadata",
    "literature_metadata",
)
_REGISTRY_KEY_BY_RECORD_TYPE: Mapping[str, str] = {
    "fungi": "fungi",
    "substrates": "substrates",
    "enzyme_classes": "enzyme_classes",
    "process_compatibility": "process_compatibility",
    "case_templates": "case_templates",
    "product_maps": "product_maps",
}
_AUDIT_FIELDS = {
    "schema_version",
    "workflow",
    "supported_record_type",
    "source_proposal_record_id",
    "authored_record_id",
    "target_registry_key",
    "target_policy",
    "source_provenance",
    "result_provenance",
    "record_digest",
    "scientific_validation_claimed",
    "simulation_authorized",
    "production_registry_mutated",
}


class RegistryRecordAuthoringError(ValueError):
    """Raised when a source proposal cannot yield an exact registry target."""


@dataclass(frozen=True)
class CuratorAuthoredRegistryResult(CurationResult):
    """Integrity-bound non-parameter records ready only for promotion planning."""

    source_record_ids: tuple[str, ...]
    authored_record_ids: tuple[str, ...]
    authoring_digest: str

    def summary(self) -> dict[str, Any]:
        return _registry_authoring_summary(
            source_query=self.source_query,
            source_snapshot_path=self.source_snapshot_path,
            proposal_limitations=self.proposal_limitations,
            records=self.records,
            source_record_ids=self.source_record_ids,
            authored_record_ids=self.authored_record_ids,
            authoring_digest=self.authoring_digest,
        )

    def verify_integrity(self) -> None:
        _validate_authored_result(
            records=self.records,
            source_record_ids=self.source_record_ids,
            authored_record_ids=self.authored_record_ids,
            source_query=self.source_query,
            source_snapshot_path=self.source_snapshot_path,
            proposal_limitations=self.proposal_limitations,
            expected_digest=self.authoring_digest,
        )

    def write(self, output_dir: str | Path) -> CurationWriteResult:
        self.verify_integrity()
        return super().write(output_dir)


def author_registry_records(
    curation_result: (
        CurationResult | LoadedCurationBundle | AuthenticatedCurationBundle
    ),
    *,
    registry_records: Mapping[str, Mapping[str, Any]],
) -> CuratorAuthoredRegistryResult:
    """Author complete index-backed targets from explicitly accepted proposals.

    ``registry_records`` maps each accepted source proposal ID to one complete
    production record. The bridge validates exact production-loader round trips,
    preserves source identity in a reserved audit namespace, and does not write
    or mutate the production registry.
    """

    source_result = _authoring_source_result(curation_result)
    if not isinstance(registry_records, Mapping) or not registry_records:
        raise RegistryRecordAuthoringError("author_registry_records requires at least one source-to-target mapping.")
    if any(not isinstance(key, str) or not key.strip() for key in registry_records):
        raise RegistryRecordAuthoringError("Registry authoring source IDs must be nonblank text.")

    result_provenance = _result_provenance(
        source_query=source_result.source_query,
        source_snapshot_path=source_result.source_snapshot_path,
        proposal_limitations=source_result.proposal_limitations,
    )
    authored: list[CurationRecord] = []
    target_ids: set[str] = set()
    for source_record_id in sorted(registry_records):
        source = _accepted_source(source_result, source_record_id)
        _validate_source_record(
            source,
            source_query=source_result.source_query,
            source_snapshot_path=source_result.source_snapshot_path,
        )
        target_value = registry_records[source_record_id]
        if not isinstance(target_value, Mapping):
            raise RegistryRecordAuthoringError(f"Target for source {source_record_id!r} must be a mapping.")
        canonical_target = canonicalize_curation_artifact_value(target_value)
        if not isinstance(canonical_target, Mapping):
            raise RegistryRecordAuthoringError(f"Target for source {source_record_id!r} must remain a mapping.")
        target = deepcopy(dict(canonical_target))
        target_id = target.get("record_id")
        if not isinstance(target_id, str) or not target_id.strip():
            raise RegistryRecordAuthoringError(f"Target for source {source_record_id!r} requires a nonblank record_id.")
        if target_id in target_ids:
            raise RegistryRecordAuthoringError(f"Authored target record ID {target_id!r} is duplicated.")
        target_ids.add(target_id)
        _validate_target_maturity(target, record_id=target_id)
        provenance = target.get("provenance")
        if not isinstance(provenance, Mapping) or not provenance:
            raise RegistryRecordAuthoringError(f"Authored target {target_id!r} requires mapping provenance.")
        reserved = sorted(RESERVED_PROVENANCE_KEYS & set(provenance))
        if reserved:
            raise RegistryRecordAuthoringError(
                f"Authored target {target_id!r} may not pre-populate reserved provenance keys: {', '.join(reserved)}."
            )
        _validate_source_identity(
            target_id,
            target_provenance=provenance,
            source_provenance=source.source_provenance,
        )

        updated_provenance = deepcopy(dict(provenance))
        updated_provenance[REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY] = _audit_payload(
            source,
            target_record=target,
            result_provenance=result_provenance,
        )
        target["provenance"] = updated_provenance
        _validate_loader_fidelity(source.record_type, target)

        record = CurationRecord(
            record_type=source.record_type,
            record_id=target_id,
            proposed_record=deepcopy(target),
            classification="eligible_for_review",
            missing_fields=(),
            reasons=(),
            decision="accept",
            explicit_decision=True,
            curator=source.curator,
            decision_reason=source.decision_reason,
            curation_date=source.curation_date,
            allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
            limitations=tuple(source.limitations),
            source_provenance=deepcopy(dict(source.source_provenance)),
        )
        curation = _curation_metadata(record)
        audit = updated_provenance[REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY]
        assert isinstance(audit, dict)
        audit["record_digest"] = registry_record_authoring_digest(
            target,
            curation,
            source_record_id=source_record_id,
            record_type=source.record_type,
            result_provenance=result_provenance,
        )
        target["provenance"] = updated_provenance
        authored.append(replace(record, proposed_record=deepcopy(target)))

    ordered = tuple(sorted(authored, key=lambda item: (item.record_type, item.record_id)))
    source_ids = tuple(_record_audit(item.proposed_record)["source_proposal_record_id"] for item in ordered)
    authored_ids = tuple(item.record_id for item in ordered)
    digest = _result_digest(
        records=ordered,
        source_record_ids=source_ids,
        authored_record_ids=authored_ids,
        result_provenance=result_provenance,
    )
    result = CuratorAuthoredRegistryResult(
        source_query=source_result.source_query,
        source_snapshot_path=source_result.source_snapshot_path,
        proposal_limitations=tuple(source_result.proposal_limitations),
        records=ordered,
        source_record_ids=source_ids,
        authored_record_ids=authored_ids,
        authoring_digest=digest,
    )
    result.verify_integrity()
    return result


def registry_record_authoring_digest(
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
    *,
    source_record_id: str,
    record_type: str,
    result_provenance: Mapping[str, Any],
) -> str:
    """Return the exact digest for one authored target and its acceptance."""

    payload = {
        "kind": REGISTRY_RECORD_AUTHORING_WORKFLOW,
        "schema_version": REGISTRY_RECORD_AUTHORING_SCHEMA_VERSION,
        "record_type": record_type,
        "source_record_id": source_record_id,
        "target_record": canonicalize(_target_for_digest(target_record)),
        "curation": canonicalize(curation_metadata),
        "result_provenance": canonicalize(result_provenance),
    }
    return _sha256_json(payload)


def validate_registry_record_authoring_plan_record(
    record_type: str,
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
) -> None:
    """Independently revalidate one authored promotion candidate."""

    clean_target = deepcopy(dict(target_record))
    provenance = clean_target.get("provenance")
    if not isinstance(provenance, dict):
        raise RegistryRecordAuthoringError("Authored registry candidate provenance must be a mapping.")
    provenance.pop(CURATION_AUDIT_PROVENANCE_KEY, None)
    audit = provenance.get(REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY)
    if not isinstance(audit, Mapping):
        raise RegistryRecordAuthoringError("Authored registry candidate lacks its specialized authoring audit.")
    result_provenance = audit.get("result_provenance")
    source_record_id = audit.get("source_proposal_record_id")
    expected_digest = audit.get("record_digest")
    if not isinstance(result_provenance, Mapping) or not _text(source_record_id) or not _text(expected_digest):
        raise RegistryRecordAuthoringError("Authored registry candidate lacks source, result, or digest evidence.")
    assert isinstance(source_record_id, str)
    assert isinstance(expected_digest, str)
    _validate_authored_record(
        record_type=record_type,
        target_record=clean_target,
        curation_metadata=curation_metadata,
        source_record_id=source_record_id,
        result_provenance=result_provenance,
        expected_digest=expected_digest,
    )


def validate_registry_record_authoring_bundle(
    *,
    summary: Mapping[str, Any],
    manifest: Mapping[str, Any],
    proposed_payload: Mapping[str, Any],
    accepted_payload: Mapping[str, Any],
    rejected_payload: Mapping[str, Any],
    eligible_records_csv_payload: Mapping[str, Any],
    excluded_records_csv_payload: Mapping[str, Any],
    records: Sequence[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
    curation_report: str,
) -> None:
    """Validate the exact closed artifact set for a written authoring result."""

    source_query = summary.get("source_query")
    source_snapshot_path = summary.get("source_snapshot_path")
    proposal_limitations = summary.get("proposal_limitations")
    source_record_ids = summary.get("source_record_ids")
    authored_record_ids = summary.get("authored_record_ids")
    expected_digest = summary.get("authoring_digest")
    if (
        not _text(source_query)
        or not _text(source_snapshot_path)
        or not _text_sequence(proposal_limitations)
        or not _text_sequence(source_record_ids)
        or not _text_sequence(authored_record_ids)
        or not _text(expected_digest)
    ):
        raise RegistryRecordAuthoringError("Written registry-authoring summary lacks identity or digest evidence.")
    assert isinstance(source_query, str)
    assert isinstance(source_snapshot_path, str)
    assert isinstance(proposal_limitations, Sequence)
    assert isinstance(source_record_ids, Sequence)
    assert isinstance(authored_record_ids, Sequence)
    assert isinstance(expected_digest, str)

    reconstructed_records = tuple(
        _curation_record_from_metadata(
            record_type=record_type,
            target_record=target_record,
            curation_metadata=curation_metadata,
        )
        for record_type, target_record, curation_metadata in records
    )
    reconstructed = CuratorAuthoredRegistryResult(
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=tuple(proposal_limitations),
        records=reconstructed_records,
        source_record_ids=tuple(source_record_ids),
        authored_record_ids=tuple(authored_record_ids),
        authoring_digest=expected_digest,
    )
    reconstructed.verify_integrity()
    if not type_exact_equal(summary, reconstructed.summary()):
        raise RegistryRecordAuthoringError("Written bundle lacks the closed registry-authoring summary contract.")
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise RegistryRecordAuthoringError("Written registry-authoring manifest requires its checksum mapping.")
    expected_artifacts: Mapping[str, Any] = {
        "curation_manifest.json": curation_manifest_payload(reconstructed, files),
        "proposed_registry_records.yml": curation_records_payload("proposed", reconstructed.records, reconstructed),
        "accepted_registry_records.yml": curation_records_payload(
            "accepted", reconstructed.accepted_records, reconstructed
        ),
        "rejected_registry_records.yml": curation_records_payload(
            "rejected", reconstructed.rejected_records, reconstructed
        ),
        "eligible_records.csv": curation_records_csv_payload(reconstructed.eligible_records),
        "excluded_records.csv": curation_records_csv_payload(reconstructed.excluded_records),
        "curation_report.md": render_curation_report(reconstructed),
    }
    actual_artifacts: Mapping[str, Any] = {
        "curation_manifest.json": manifest,
        "proposed_registry_records.yml": proposed_payload,
        "accepted_registry_records.yml": accepted_payload,
        "rejected_registry_records.yml": rejected_payload,
        "eligible_records.csv": eligible_records_csv_payload,
        "excluded_records.csv": excluded_records_csv_payload,
        "curation_report.md": curation_report,
    }
    for name, expected in expected_artifacts.items():
        if not type_exact_equal(actual_artifacts[name], expected):
            raise RegistryRecordAuthoringError(
                f"Written bundle artifact {name!r} disagrees with the deterministic registry-authoring result."
            )


def _validate_authored_result(
    *,
    records: Sequence[CurationRecord],
    source_record_ids: Sequence[str],
    authored_record_ids: Sequence[str],
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
    expected_digest: str,
) -> None:
    if not records:
        raise RegistryRecordAuthoringError("An authored registry result must contain at least one record.")
    if tuple(records) != tuple(sorted(records, key=lambda item: (item.record_type, item.record_id))):
        raise RegistryRecordAuthoringError("Authored registry records must use deterministic type-and-ID order.")
    if len(set(authored_record_ids)) != len(authored_record_ids):
        raise RegistryRecordAuthoringError("Authored registry record IDs must be unique.")
    result_provenance = _result_provenance(
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
    )
    actual_source_ids: list[str] = []
    actual_authored_ids: list[str] = []
    for record in records:
        audit = _record_audit(record.proposed_record)
        source_record_id = audit.get("source_proposal_record_id")
        expected_record_digest = audit.get("record_digest")
        if not _text(source_record_id) or not _text(expected_record_digest):
            raise RegistryRecordAuthoringError(f"Authored target {record.record_id!r} lacks source or digest identity.")
        assert isinstance(source_record_id, str)
        assert isinstance(expected_record_digest, str)
        _validate_authored_record(
            record_type=record.record_type,
            target_record=record.proposed_record,
            curation_metadata=_curation_metadata(record),
            source_record_id=source_record_id,
            result_provenance=result_provenance,
            expected_digest=expected_record_digest,
        )
        actual_source_ids.append(source_record_id)
        actual_authored_ids.append(record.record_id)
    if not type_exact_equal(tuple(actual_source_ids), tuple(source_record_ids)):
        raise RegistryRecordAuthoringError("Authored source record identities changed.")
    if not type_exact_equal(tuple(actual_authored_ids), tuple(authored_record_ids)):
        raise RegistryRecordAuthoringError("Authored target record identities changed.")
    actual_digest = _result_digest(
        records=records,
        source_record_ids=source_record_ids,
        authored_record_ids=authored_record_ids,
        result_provenance=result_provenance,
    )
    if not isinstance(expected_digest, str) or not hmac.compare_digest(actual_digest, expected_digest):
        raise RegistryRecordAuthoringError("Curator-authored registry result changed after construction or writing.")


def _validate_authored_record(
    *,
    record_type: str,
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
    source_record_id: str,
    result_provenance: Mapping[str, Any],
    expected_digest: str,
) -> None:
    if record_type not in SUPPORTED_AUTHORED_REGISTRY_RECORD_TYPES:
        raise RegistryRecordAuthoringError(f"Registry authoring does not support record type {record_type!r}.")
    _validate_acceptance(curation_metadata, record_id=str(target_record.get("record_id", "")))
    audit = _record_audit(target_record)
    expected_audit = {
        "schema_version": REGISTRY_RECORD_AUTHORING_SCHEMA_VERSION,
        "workflow": REGISTRY_RECORD_AUTHORING_WORKFLOW,
        "supported_record_type": record_type,
        "source_proposal_record_id": source_record_id,
        "authored_record_id": target_record.get("record_id"),
        "target_registry_key": _REGISTRY_KEY_BY_RECORD_TYPE[record_type],
        "target_policy": _target_policy(target_record),
        "source_provenance": curation_metadata.get("source_provenance"),
        "result_provenance": result_provenance,
        "record_digest": expected_digest,
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "production_registry_mutated": False,
    }
    if set(audit) != _AUDIT_FIELDS or not type_exact_equal(audit, expected_audit):
        raise RegistryRecordAuthoringError(
            f"Authored target {target_record.get('record_id')!r} has changed audit evidence."
        )
    actual_digest = registry_record_authoring_digest(
        target_record,
        curation_metadata,
        source_record_id=source_record_id,
        record_type=record_type,
        result_provenance=result_provenance,
    )
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise RegistryRecordAuthoringError(
            f"Authored target {target_record.get('record_id')!r} changed after construction."
        )
    provenance = target_record.get("provenance")
    assert isinstance(provenance, Mapping)
    source_provenance = curation_metadata.get("source_provenance")
    assert isinstance(source_provenance, Mapping)
    _validate_source_identity(
        str(target_record.get("record_id")),
        target_provenance=provenance,
        source_provenance=source_provenance,
    )
    _validate_loader_fidelity(record_type, target_record)


def _audit_payload(
    source: CurationRecord,
    *,
    target_record: Mapping[str, Any],
    result_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_RECORD_AUTHORING_SCHEMA_VERSION,
        "workflow": REGISTRY_RECORD_AUTHORING_WORKFLOW,
        "supported_record_type": source.record_type,
        "source_proposal_record_id": source.record_id,
        "authored_record_id": target_record.get("record_id"),
        "target_registry_key": _REGISTRY_KEY_BY_RECORD_TYPE[source.record_type],
        "target_policy": _target_policy(target_record),
        "source_provenance": deepcopy(dict(source.source_provenance)),
        "result_provenance": deepcopy(dict(result_provenance)),
        "record_digest": "",
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "production_registry_mutated": False,
    }


def _record_audit(target_record: Mapping[str, Any]) -> Mapping[str, Any]:
    provenance = target_record.get("provenance")
    audit = provenance.get(REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY) if isinstance(provenance, Mapping) else None
    if not isinstance(audit, Mapping):
        raise RegistryRecordAuthoringError(
            f"Authored target {target_record.get('record_id')!r} lacks its audit namespace."
        )
    return audit


def _target_for_digest(target_record: Mapping[str, Any]) -> Mapping[str, Any]:
    target = deepcopy(dict(target_record))
    provenance = target.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop(CURATION_AUDIT_PROVENANCE_KEY, None)
        audit = provenance.get(REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY)
        if isinstance(audit, dict):
            audit["record_digest"] = ""
    return target


def _result_digest(
    *,
    records: Sequence[CurationRecord],
    source_record_ids: Sequence[str],
    authored_record_ids: Sequence[str],
    result_provenance: Mapping[str, Any],
) -> str:
    return _sha256_json(
        {
            "kind": REGISTRY_RECORD_AUTHORING_WORKFLOW,
            "schema_version": REGISTRY_RECORD_AUTHORING_SCHEMA_VERSION,
            "source_record_ids": list(source_record_ids),
            "authored_record_ids": list(authored_record_ids),
            "record_digests": [_record_audit(record.proposed_record)["record_digest"] for record in records],
            "result_provenance": canonicalize(result_provenance),
        }
    )


def _registry_authoring_summary(
    *,
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
    records: Sequence[CurationRecord],
    source_record_ids: Sequence[str],
    authored_record_ids: Sequence[str],
    authoring_digest: str,
) -> dict[str, Any]:
    record_types = sorted({record.record_type for record in records})
    return {
        "schema_version": CURATION_SCHEMA_VERSION,
        "source_query": source_query,
        "source_snapshot_path": source_snapshot_path,
        "record_count": len(records),
        "eligible_for_review_count": len(records),
        "blocked_excluded_count": 0,
        "accepted_count": len(records),
        "rejected_count": 0,
        "deferred_count": 0,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "proposal_limitations": list(proposal_limitations),
        "workflow": REGISTRY_RECORD_AUTHORING_WORKFLOW,
        "authoring_schema_version": REGISTRY_RECORD_AUTHORING_SCHEMA_VERSION,
        "supported_record_types": record_types,
        "source_record_ids": list(source_record_ids),
        "authored_record_ids": list(authored_record_ids),
        "authoring_digest": authoring_digest,
        "production_loader_round_trip_verified": True,
        "target_maturity_policy": list(
            REGISTRY_RECORD_AUTHORING_ALLOWED_MATURITIES
        ),
        "promotion_plan_compatible": True,
        "simulation_authorized": False,
    }


def _authoring_source_result(
    value: CurationResult | LoadedCurationBundle | AuthenticatedCurationBundle,
) -> CurationResult:
    if isinstance(value, AuthenticatedCurationBundle):
        try:
            return value.reload().bundle.result
        except (CurationError, CuratorSignatureError) as exc:
            raise RegistryRecordAuthoringError(
                "Authenticated curation source failed current checksum or "
                "signature validation."
            ) from exc
    if isinstance(value, LoadedCurationBundle):
        try:
            return load_curation_bundle(value.manifest_path).result
        except CurationError as exc:
            raise RegistryRecordAuthoringError(
                f"Written curation source failed current integrity validation: {exc}"
            ) from exc
    if isinstance(value, CurationResult):
        return value
    raise RegistryRecordAuthoringError(
        "author_registry_records requires a validated in-memory CurationResult "
        "or checksum-loaded LoadedCurationBundle/AuthenticatedCurationBundle."
    )


def _accepted_source(result: CurationResult, record_id: str) -> CurationRecord:
    matches = [record for record in result.accepted_records if record.record_id == record_id]
    if len(matches) != 1:
        raise RegistryRecordAuthoringError(
            f"Source proposal {record_id!r} must identify exactly one explicitly accepted record."
        )
    return matches[0]


def _validate_source_record(
    source: CurationRecord,
    *,
    source_query: str,
    source_snapshot_path: str,
) -> None:
    if source.record_type not in SUPPORTED_AUTHORED_REGISTRY_RECORD_TYPES:
        raise RegistryRecordAuthoringError(f"Registry authoring does not support source type {source.record_type!r}.")
    _validate_acceptance(_curation_metadata(source), record_id=source.record_id)
    if source.proposed_record.get("record_id") != source.record_id:
        raise RegistryRecordAuthoringError("Source proposal record identity is inconsistent.")
    try:
        reviewed_provenance = validate_reviewable_source_record(
            source.record_type,
            source.proposed_record,
            source_snapshot_path=source_snapshot_path,
        )
    except CurationError as exc:
        raise RegistryRecordAuthoringError(str(exc)) from exc
    if not type_exact_equal(reviewed_provenance, source.source_provenance):
        raise RegistryRecordAuthoringError(
            f"Source proposal {source.record_id!r} and accepted curation provenance disagree."
        )
    if (
        source.source_provenance.get("source_query") != source_query
        or source.source_provenance.get("source_snapshot_path") != source_snapshot_path
    ):
        raise RegistryRecordAuthoringError(
            f"Source proposal {source.record_id!r} result identity is inconsistent."
        )


def _validate_acceptance(curation: Mapping[str, Any], *, record_id: str) -> None:
    if (
        curation.get("classification") != "eligible_for_review"
        or curation.get("decision") != "accept"
        or curation.get("explicit_decision") is not True
        or curation.get("allowed_use") != CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION
    ):
        raise RegistryRecordAuthoringError(
            f"Record {record_id!r} requires an explicit eligible pending-promotion acceptance."
        )
    for field in ("curator", "decision_reason", "curation_date"):
        if not _text(curation.get(field)):
            raise RegistryRecordAuthoringError(f"Record {record_id!r} requires nonblank curation.{field}.")
    curation_date = curation.get("curation_date")
    assert isinstance(curation_date, str)
    if not curation_date_is_iso(curation_date):
        raise RegistryRecordAuthoringError(f"Record {record_id!r} requires curation_date in YYYY-MM-DD form.")
    if not _text_sequence(curation.get("limitations")):
        raise RegistryRecordAuthoringError(f"Record {record_id!r} requires explicit curation limitations.")
    if curation.get("missing_fields") not in ([], ()) or curation.get("reasons") not in (
        [],
        (),
    ):
        raise RegistryRecordAuthoringError(f"Record {record_id!r} cannot carry unresolved missing fields or reasons.")
    provenance = curation.get("source_provenance")
    missing = curation_source_provenance_missing(provenance if isinstance(provenance, Mapping) else {})
    if missing:
        raise RegistryRecordAuthoringError(
            f"Record {record_id!r} has incomplete source provenance: {', '.join(missing)}."
        )


def _validate_loader_fidelity(
    record_type: str,
    target_record: Mapping[str, Any],
) -> None:
    try:
        loaded = load_registry_record_mapping(
            record_type,  # type: ignore[arg-type]
            target_record,
        )
    except (RegistryLoadError, TypeError, ValueError) as exc:
        raise RegistryRecordAuthoringError(
            f"Authored {record_type} target failed the production loader: {exc}"
        ) from exc
    dropped, synthesized, changed = round_trip_differences(
        target_record,
        loaded.to_dict(),
    )
    if dropped or synthesized or changed:
        raise RegistryRecordAuthoringError(
            "Authored target failed exact production-loader fidelity: "
            f"silently_dropped_fields={list(dropped)}, "
            f"synthesized_or_defaulted_fields={list(synthesized)}, "
            f"changed_fields={list(changed)}"
        )


def _validate_target_maturity(
    target_record: Mapping[str, Any],
    *,
    record_id: str,
) -> None:
    maturity = target_record.get("maturity")
    if maturity not in REGISTRY_RECORD_AUTHORING_ALLOWED_MATURITIES:
        raise RegistryRecordAuthoringError(
            f"Authored target {record_id!r} maturity must be one of "
            f"{list(REGISTRY_RECORD_AUTHORING_ALLOWED_MATURITIES)!r}; "
            "authoring cannot claim validated or unrestricted maturity."
        )


def _target_policy(target_record: Mapping[str, Any]) -> dict[str, Any]:
    _validate_target_maturity(
        target_record,
        record_id=str(target_record.get("record_id", "")),
    )
    return {
        "maturity": target_record.get("maturity"),
        "allowed_maturities": list(REGISTRY_RECORD_AUTHORING_ALLOWED_MATURITIES),
        "curation_allowed_use": CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    }


def _validate_source_identity(
    record_id: str,
    *,
    target_provenance: Mapping[str, Any],
    source_provenance: Mapping[str, Any],
) -> None:
    target = _source_identity(target_provenance, label=f"Target {record_id!r}")
    source = _source_identity(source_provenance, label=f"Source {record_id!r}")
    for field in sorted(set(target) & set(source)):
        if not type_exact_equal(target[field], source[field]):
            raise RegistryRecordAuthoringError(
                f"Authored target {record_id!r} conflicts with source identity field {field!r}."
            )


def _source_identity(
    provenance: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, str | tuple[str, ...]]:
    identity: dict[str, str | tuple[str, ...]] = {}
    for field in ("source_database", "source_snapshot_path", "source_url"):
        value = provenance.get(field)
        if value in (None, "") and field in {"source_snapshot_path", "source_url"}:
            continue
        if value is None:
            continue
        if not _text(value):
            raise RegistryRecordAuthoringError(f"{label} has invalid source identity field {field!r}.")
        assert isinstance(value, str)
        identity[field] = value
    raw_ids = provenance.get("source_entry_ids")
    if raw_ids is not None:
        if not _text_sequence(raw_ids):
            raise RegistryRecordAuthoringError(f"{label} has invalid source identity field 'source_entry_ids'.")
        assert isinstance(raw_ids, Sequence)
        identity["source_entry_ids"] = tuple(sorted(raw_ids))
    raw_id = provenance.get("source_entry_id")
    if raw_id is not None:
        if not _text(raw_id):
            raise RegistryRecordAuthoringError(f"{label} has invalid source identity field 'source_entry_id'.")
        assert isinstance(raw_id, str)
        singular = (raw_id,)
        plural = identity.get("source_entry_ids")
        if plural is not None and not type_exact_equal(plural, singular):
            raise RegistryRecordAuthoringError(f"{label} has contradictory source entry identities.")
        identity["source_entry_ids"] = singular
    return identity


def _result_provenance(
    *,
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
) -> dict[str, Any]:
    if not _text(source_query) or not _text(source_snapshot_path) or not _text_sequence(proposal_limitations):
        raise RegistryRecordAuthoringError("Authored result requires source query, snapshot path, and limitations.")
    return {
        "source_query": source_query,
        "source_snapshot_path": source_snapshot_path,
        "proposal_limitations": list(proposal_limitations),
    }


def _curation_metadata(record: CurationRecord) -> Mapping[str, Any]:
    curation = record.to_dict().get("curation")
    if not isinstance(curation, Mapping):
        raise RegistryRecordAuthoringError(f"Record {record.record_id!r} lacks curation metadata.")
    return curation


def _curation_record_from_metadata(
    *,
    record_type: str,
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
) -> CurationRecord:
    return CurationRecord(
        record_type=record_type,
        record_id=str(target_record.get("record_id", "")),
        proposed_record=deepcopy(dict(target_record)),
        classification=curation_metadata.get("classification"),  # type: ignore[arg-type]
        missing_fields=tuple(curation_metadata.get("missing_fields", ())),
        reasons=tuple(curation_metadata.get("reasons", ())),
        decision=curation_metadata.get("decision"),  # type: ignore[arg-type]
        explicit_decision=curation_metadata.get("explicit_decision") is True,
        curator=curation_metadata.get("curator"),  # type: ignore[arg-type]
        decision_reason=str(curation_metadata.get("decision_reason", "")),
        curation_date=str(curation_metadata.get("curation_date", "")),
        allowed_use=str(curation_metadata.get("allowed_use", "")),
        limitations=tuple(curation_metadata.get("limitations", ())),
        source_provenance=deepcopy(dict(curation_metadata.get("source_provenance", {}))),
    )


def _sha256_json(value: Any) -> str:
    try:
        encoded = json.dumps(
            canonicalize(value),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RegistryRecordAuthoringError(f"Authored registry data is not canonical: {exc}") from exc
    return sha256_bytes(encoded)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and bool(value)
        and all(_text(item) for item in value)
    )


__all__ = [
    "CuratorAuthoredRegistryResult",
    "REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY",
    "REGISTRY_RECORD_AUTHORING_ALLOWED_MATURITIES",
    "REGISTRY_RECORD_AUTHORING_SCHEMA_VERSION",
    "REGISTRY_RECORD_AUTHORING_WORKFLOW",
    "RegistryRecordAuthoringError",
    "SUPPORTED_AUTHORED_REGISTRY_RECORD_TYPES",
    "author_registry_records",
    "registry_record_authoring_digest",
]
