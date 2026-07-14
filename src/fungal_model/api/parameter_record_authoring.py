"""Identity-only parameter authoring from accepted source curation."""

from __future__ import annotations

import hmac
import json
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from fungal_model.api._integrity import (
    PARAMETER_BRIDGE_PROVENANCE_KEY,
    RESERVED_PROVENANCE_KEYS,
    TreeIntegrityError,
    canonicalize,
    first_symlink_component,
    round_trip_differences,
    sha256_bytes,
    tree_content_digest,
    type_exact_equal,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    CURATION_SCHEMA_VERSION,
    CurationRecord,
    CurationResult,
    CurationWriteResult,
    curation_date_is_iso,
    curation_manifest_payload,
    curation_records_csv_payload,
    curation_records_payload,
    curation_source_provenance_missing,
    render_curation_report,
)
from fungal_model.registry.loaders import load_parameter_record_mapping, load_registry
from fungal_model.registry.records import PARAMETER_ALLOWED_USE_STORAGE_ONLY
from fungal_model.registry.store import FungModRegistry, RegistryLookupError
from fungal_model.provenance import CURATION_AUDIT_PROVENANCE_KEY
from fungal_model.sources.sabiork import (
    PROPOSAL_STATUS,
    frozen_source_urls,
)


PARAMETER_AUTHORING_SCHEMA_VERSION = "1.0.0"
PARAMETER_AUTHORING_WORKFLOW = "curator_authored_parameter_record_bridge"
PARAMETER_IDENTITY_CONVERSION_METHOD = "identity_no_conversion"
PARAMETER_AUTHORING_MATURITY = "literature_processed"
PARAMETER_AUTHORING_ALLOWED_USE = PARAMETER_ALLOWED_USE_STORAGE_ONLY
PARAMETER_AUTHORING_CONFIDENCE_LEVEL = "curator_accepted_identity_transcription_not_validation"
PARAMETER_AUTHORING_RANGE_SCOPE = "single_source_entry"
PARAMETER_AUTHORING_RANGE_INTERPRETATION = "exact_identity_transcription_not_uncertainty"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_FIELDS = {
    "record_id",
    "name",
    "maturity",
    "provenance",
    "notes",
    "parameter_symbol",
    "process_type",
    "enzyme_class",
    "substrate_class",
    "fungus_id",
    "substrate_id",
    "environment_id",
    "value",
    "range_scope",
    "range_interpretation",
    "allowed_use",
}
_OPTIONAL_FIELDS = {
    "display_name",
    "scientific_name",
    "aliases",
    "external_refs",
    "ec_number",
    "database_ids",
}
_VALUE_FIELDS = {
    "kind",
    "units",
    "value",
    "lower",
    "upper",
    "distribution",
    "parameters",
    "source",
    "confidence_level",
    "notes",
}
_SOURCE_IDENTITY_FIELDS = (
    "source_database",
    "source_entry_ids",
    "source_reaction_ids",
    "source_query",
    "source_field",
    "source_snapshot_path",
    "source_url",
    "source_urls",
    "source_snapshot_sha256",
)
_PROPOSAL_IDENTITY_FIELDS = _SOURCE_IDENTITY_FIELDS
_SOURCE_PROVENANCE_FIELDS = frozenset((*_SOURCE_IDENTITY_FIELDS, "proposal_status", "notes"))
_SOURCE_ALIAS_FIELDS = frozenset({"source_reaction_id", "selected_kinlaw_entry_id"})
_RESULT_PROVENANCE_FIELDS = frozenset({"source_query", "source_snapshot_path", "proposal_limitations"})
_CURATION_FIELDS = frozenset(
    {
        "schema_version",
        "classification",
        "missing_fields",
        "reasons",
        "decision",
        "explicit_decision",
        "curator",
        "decision_reason",
        "curation_date",
        "allowed_use",
        "limitations",
        "source_provenance",
        "promotion_status",
    }
)
_SOURCE_PARAMETER_AUDIT_FIELDS = frozenset(
    {
        "parameter_symbol",
        "parameter_role",
        "proposal_status",
        "proposal_allowed_use",
        "original_value",
        "original_units",
        "source_value",
        "source_units",
        "normalized_start_value",
        "normalized_units",
        "converted_value",
        "converted_units",
        "target_value",
        "target_units",
        "conversion_method",
    }
)
_ACCEPTANCE_AUDIT_FIELDS = frozenset(
    {
        "classification",
        "decision",
        "explicit_decision",
        "curator",
        "decision_reason",
        "curation_date",
        "allowed_use_decision",
        "limitations",
    }
)
_TARGET_POLICY_AUDIT_FIELDS = frozenset(
    {
        "maturity",
        "allowed_use",
        "range_scope",
        "range_interpretation",
        "value_kind",
        "confidence_level",
    }
)
_REGISTRY_CONTEXT_FIELDS = frozenset(
    {"registry_id", "registry_version", "registry_index_sha256", "registry_content_sha256"}
)
_SELECTOR_RESOLUTION_FIELDS = frozenset(
    {
        "fungus_id",
        "effective_enzyme_classes",
        "substrate_id",
        "effective_substrate_class",
        "environment_id",
        "process_type",
        "parameter_symbol",
        "parameter_role",
        "process_compatibility_id",
    }
)
_AUDIT_FIELDS = frozenset(
    {
        "schema_version",
        "workflow",
        "supported_record_type",
        "source_proposal_record_id",
        "authored_record_id",
        "authoring_digest",
        "conversion_policy",
        "source_parameter",
        "source_provenance",
        "source_aliases",
        "acceptance",
        "result_provenance",
        "target_policy",
        "registry_context",
        "selector_resolution",
        "scientific_validation_claimed",
        "simulation_authorized",
        "production_registry_mutated",
    }
)
_OUTER_PROVENANCE_SAFETY_FIELDS = frozenset(
    {
        "production_registry_mutated",
        "registry_mutated",
        "scientific_validation_claimed",
        "simulation_authorized",
    }
)


class ParameterRecordAuthoringError(ValueError):
    """Raised when parameter authoring would guess, coerce, or lose evidence."""


@dataclass(frozen=True)
class _RegistryContext:
    registry: FungModRegistry
    evidence: Mapping[str, str]


@dataclass(frozen=True)
class _ResolvedParameterCompatibility:
    fungus_id: str | None
    effective_enzyme_classes: tuple[str, ...]
    substrate_id: str | None
    effective_substrate_class: str
    environment_id: str | None
    process_type: str
    parameter_symbol: str
    parameter_role: str
    process_compatibility_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus_id": self.fungus_id,
            "effective_enzyme_classes": list(self.effective_enzyme_classes),
            "substrate_id": self.substrate_id,
            "effective_substrate_class": self.effective_substrate_class,
            "environment_id": self.environment_id,
            "process_type": self.process_type,
            "parameter_symbol": self.parameter_symbol,
            "parameter_role": self.parameter_role,
            "process_compatibility_id": self.process_compatibility_id,
        }


@dataclass(frozen=True)
class CuratorAuthoredParameterResult(CurationResult):
    """One integrity-bound, parameter-only target for promotion planning."""

    source_record_id: str
    authored_record_id: str
    authoring_digest: str

    def summary(self) -> dict[str, Any]:
        return _parameter_authoring_summary(
            source_query=self.source_query,
            source_snapshot_path=self.source_snapshot_path,
            proposal_limitations=self.proposal_limitations,
            source_record_id=self.source_record_id,
            authored_record_id=self.authored_record_id,
            authoring_digest=self.authoring_digest,
        )

    def verify_integrity(self) -> None:
        if len(self.records) != 1 or self.records[0].record_type != "parameter_records":
            raise ParameterRecordAuthoringError(
                "An authored parameter result must contain exactly one parameter_records target."
            )
        record = self.records[0]
        if record.record_id != self.authored_record_id:
            raise ParameterRecordAuthoringError("Authored record identity changed after construction.")
        validate_authored_parameter_record(
            record.proposed_record,
            _curation_metadata(record),
            source_record_id=self.source_record_id,
            source_query=self.source_query,
            source_snapshot_path=self.source_snapshot_path,
            proposal_limitations=self.proposal_limitations,
            expected_digest=self.authoring_digest,
        )

    def write(self, output_dir: str | Path) -> CurationWriteResult:
        self.verify_integrity()
        return super().write(output_dir)


def author_parameter_record(
    curation_result: CurationResult,
    *,
    source_record_id: str,
    parameter_record: Mapping[str, Any],
    registry_index: str | Path,
) -> CuratorAuthoredParameterResult:
    """Build one production ParameterRecord without conversion or registry mutation."""

    source = _accepted_source(curation_result, source_record_id)
    _validate_source_record(
        source,
        source_query=curation_result.source_query,
        source_snapshot_path=curation_result.source_snapshot_path,
    )
    result_provenance = _result_provenance(
        source_query=curation_result.source_query,
        source_snapshot_path=curation_result.source_snapshot_path,
        proposal_limitations=curation_result.proposal_limitations,
    )
    target = deepcopy(dict(parameter_record))
    _validate_target_schema(target, audit_required=False)
    _validate_target_correspondence(source, target)
    context = _load_registry_context(registry_index)
    selector_resolution = _resolve_parameter_compatibility(target, context.registry)

    provenance = deepcopy(dict(target["provenance"]))
    provenance[PARAMETER_BRIDGE_PROVENANCE_KEY] = _audit_payload(
        source,
        target=target,
        authored_record_id=str(target["record_id"]),
        registry_evidence=context.evidence,
        selector_resolution=selector_resolution,
        result_provenance=result_provenance,
    )
    target["provenance"] = provenance
    _validate_loader_fidelity(target)

    authored = CurationRecord(
        record_type="parameter_records",
        record_id=str(target["record_id"]),
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
    curation = _curation_metadata(authored)
    digest = parameter_authoring_digest(
        target,
        curation,
        source_record_id=source_record_id,
        source_query=curation_result.source_query,
        source_snapshot_path=curation_result.source_snapshot_path,
        proposal_limitations=curation_result.proposal_limitations,
    )
    audit = provenance[PARAMETER_BRIDGE_PROVENANCE_KEY]
    assert isinstance(audit, dict)
    audit["authoring_digest"] = digest
    target["provenance"] = provenance
    authored = replace(authored, proposed_record=deepcopy(target))
    result = CuratorAuthoredParameterResult(
        source_query=curation_result.source_query,
        source_snapshot_path=curation_result.source_snapshot_path,
        proposal_limitations=tuple(curation_result.proposal_limitations),
        records=(authored,),
        source_record_id=source_record_id,
        authored_record_id=authored.record_id,
        authoring_digest=digest,
    )
    result.verify_integrity()
    return result


def parameter_authoring_digest(
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
    *,
    source_record_id: str,
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
) -> str:
    payload = {
        "kind": PARAMETER_AUTHORING_WORKFLOW,
        "schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "record_type": "parameter_records",
        "source_record_id": source_record_id,
        "result_provenance": canonicalize(
            _result_provenance(
                source_query=source_query,
                source_snapshot_path=source_snapshot_path,
                proposal_limitations=proposal_limitations,
            )
        ),
        "target_record": canonicalize(_target_record_for_authoring_digest(target_record)),
        "curation_metadata": canonicalize(curation_metadata),
    }
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ParameterRecordAuthoringError(f"Authored parameter contains non-canonical data: {exc}") from exc
    return sha256_bytes(encoded)


def _target_record_for_authoring_digest(record: Mapping[str, Any]) -> Mapping[str, Any]:
    target = deepcopy(dict(record))
    provenance = target.get("provenance")
    if isinstance(provenance, dict):
        audit = provenance.get(PARAMETER_BRIDGE_PROVENANCE_KEY)
        if isinstance(audit, dict):
            audit.pop("authoring_digest", None)
    return target


def validate_authored_parameter_record(
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
    *,
    source_record_id: str,
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
    expected_digest: str,
) -> None:
    actual = parameter_authoring_digest(
        target_record,
        curation_metadata,
        source_record_id=source_record_id,
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
    )
    if not isinstance(expected_digest, str) or not hmac.compare_digest(actual, expected_digest):
        raise ParameterRecordAuthoringError(
            "Curator-authored parameter result changed after construction or bundle writing."
        )
    _validate_acceptance(curation_metadata, record_id=str(target_record.get("record_id", "")))
    _validate_target_schema(target_record, audit_required=True)
    audit = target_record["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY]
    assert isinstance(audit, Mapping)
    result_provenance = _result_provenance(
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
    )
    _validate_result_provenance(curation_metadata, result_provenance)
    _validate_audit(
        target_record,
        curation_metadata,
        audit,
        source_record_id=source_record_id,
        result_provenance=result_provenance,
        expected_digest=expected_digest,
    )
    _validate_loader_fidelity(target_record)


def validate_parameter_authoring_plan_record(
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
) -> None:
    """Independently revalidate one bridge-derived promotion-plan candidate."""

    provenance = target_record.get("provenance")
    audit = (
        provenance.get(PARAMETER_BRIDGE_PROVENANCE_KEY)
        if isinstance(provenance, Mapping)
        else None
    )
    if not isinstance(audit, Mapping):
        raise ParameterRecordAuthoringError(
            "Bridge-derived parameter candidate lacks a complete specialized bridge audit."
        )
    result_provenance = audit.get("result_provenance")
    if not isinstance(result_provenance, Mapping):
        raise ParameterRecordAuthoringError(
            "Bridge-derived parameter candidate lacks exact result provenance."
        )
    source_record_id = audit.get("source_proposal_record_id")
    source_query = result_provenance.get("source_query")
    source_snapshot_path = result_provenance.get("source_snapshot_path")
    proposal_limitations = result_provenance.get("proposal_limitations")
    expected_digest = audit.get("authoring_digest")
    if (
        not _text(source_record_id)
        or not _text(source_query)
        or not _text(source_snapshot_path)
        or not _text_sequence(proposal_limitations)
        or not isinstance(expected_digest, str)
        or _SHA256.fullmatch(expected_digest) is None
    ):
        raise ParameterRecordAuthoringError(
            "Bridge-derived parameter candidate has incomplete identity or digest evidence."
        )
    assert isinstance(source_record_id, str)
    assert isinstance(source_query, str)
    assert isinstance(source_snapshot_path, str)
    assert isinstance(proposal_limitations, Sequence) and not isinstance(
        proposal_limitations, (str, bytes)
    )
    clean_target = deepcopy(dict(target_record))
    clean_provenance = clean_target.get("provenance")
    if not isinstance(clean_provenance, dict):
        raise ParameterRecordAuthoringError(
            "Bridge-derived parameter candidate provenance must be a mapping."
        )
    clean_provenance.pop(CURATION_AUDIT_PROVENANCE_KEY, None)
    validate_authored_parameter_record(
        clean_target,
        curation_metadata,
        source_record_id=source_record_id,
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
        expected_digest=expected_digest,
    )


def validate_parameter_authoring_bundle_record(
    *,
    summary: Mapping[str, Any],
    manifest: Mapping[str, Any],
    proposed_payload: Mapping[str, Any],
    accepted_payload: Mapping[str, Any],
    rejected_payload: Mapping[str, Any],
    eligible_records_csv_payload: Mapping[str, Any],
    excluded_records_csv_payload: Mapping[str, Any],
    record_type: str,
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
    curation_report: str,
) -> None:
    source_id = summary.get("source_record_id")
    authored_id = summary.get("authored_record_id")
    digest = summary.get("authoring_digest")
    if record_type != "parameter_records" or target_record.get("record_id") != authored_id:
        raise ParameterRecordAuthoringError("Written authoring summary does not match its parameter target.")
    if (
        not _text(source_id)
        or not _text(authored_id)
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
    ):
        raise ParameterRecordAuthoringError("Written authoring summary lacks source identity or digest.")
    assert isinstance(source_id, str) and isinstance(authored_id, str)
    source_query = summary.get("source_query")
    source_snapshot_path = summary.get("source_snapshot_path")
    proposal_limitations = summary.get("proposal_limitations")
    if not _text(source_query) or not _text(source_snapshot_path) or not _text_sequence(
        proposal_limitations
    ):
        raise ParameterRecordAuthoringError("Written authoring summary lacks result provenance.")
    assert isinstance(source_query, str) and isinstance(source_snapshot_path, str)
    assert isinstance(proposal_limitations, Sequence) and not isinstance(
        proposal_limitations, (str, bytes)
    )
    expected_summary = _parameter_authoring_summary(
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
        source_record_id=source_id,
        authored_record_id=authored_id,
        authoring_digest=digest,
    )
    if not type_exact_equal(summary, expected_summary):
        raise ParameterRecordAuthoringError(
            "Written bundle lacks the closed parameter-only authoring summary contract."
        )
    validate_authored_parameter_record(
        target_record,
        curation_metadata,
        source_record_id=source_id,
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
        expected_digest=digest,
    )
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise ParameterRecordAuthoringError(
            "Written bundle manifest requires its exact checksum mapping."
        )
    reconstructed = _authored_curation_result(
        target_record=target_record,
        curation_metadata=curation_metadata,
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
        source_record_id=source_id,
        authored_record_id=authored_id,
        authoring_digest=digest,
    )
    expected_artifacts: Mapping[str, Any] = {
        "curation_manifest.json": curation_manifest_payload(reconstructed, files),
        "proposed_registry_records.yml": curation_records_payload(
            "proposed", reconstructed.records, reconstructed
        ),
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
            raise ParameterRecordAuthoringError(
                f"Written bundle artifact {name!r} disagrees with the shared curation "
                "builders and deterministic machine-readable record."
            )


def validate_authored_parameter_against_registry(
    target_record: Mapping[str, Any],
    *,
    registry_index: str | Path,
) -> None:
    context = _load_registry_context(registry_index)
    provenance = target_record.get("provenance")
    audit = provenance.get(PARAMETER_BRIDGE_PROVENANCE_KEY) if isinstance(provenance, Mapping) else None
    if not isinstance(audit, Mapping) or not type_exact_equal(
        audit.get("registry_context"), context.evidence
    ):
        raise ParameterRecordAuthoringError(
            "Authored parameter registry context does not match the planning registry."
        )
    current_resolution = _resolve_parameter_compatibility(target_record, context.registry).to_dict()
    if not type_exact_equal(audit.get("selector_resolution"), current_resolution):
        raise ParameterRecordAuthoringError(
            "Authored parameter selector resolution does not match the planning registry."
        )


def _result_provenance(
    *,
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
) -> dict[str, Any]:
    if not _text(source_query) or not _text(source_snapshot_path) or not _text_sequence(
        proposal_limitations
    ):
        raise ParameterRecordAuthoringError(
            "Authored result requires source query, snapshot path, and explicit limitations."
        )
    return {
        "source_query": source_query,
        "source_snapshot_path": source_snapshot_path,
        "proposal_limitations": list(proposal_limitations),
    }


def _parameter_authoring_summary(
    *,
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
    source_record_id: str,
    authored_record_id: str,
    authoring_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": CURATION_SCHEMA_VERSION,
        "source_query": source_query,
        "source_snapshot_path": source_snapshot_path,
        "record_count": 1,
        "eligible_for_review_count": 1,
        "blocked_excluded_count": 0,
        "accepted_count": 1,
        "rejected_count": 0,
        "deferred_count": 0,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "proposal_limitations": list(proposal_limitations),
        "workflow": PARAMETER_AUTHORING_WORKFLOW,
        "authoring_schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "supported_record_types": ["parameter_records"],
        "source_record_id": source_record_id,
        "authored_record_id": authored_record_id,
        "authoring_digest": authoring_digest,
        "identity_conversion_only": True,
        "loader_round_trip_verified": True,
        "selector_compatibility_verified": True,
        "promotion_plan_compatible": True,
        "simulation_authorized": False,
    }


def _authored_curation_result(
    *,
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
    source_query: str,
    source_snapshot_path: str,
    proposal_limitations: Sequence[str],
    source_record_id: str,
    authored_record_id: str,
    authoring_digest: str,
) -> CuratorAuthoredParameterResult:
    source_provenance = curation_metadata.get("source_provenance")
    curator = curation_metadata.get("curator")
    decision_reason = curation_metadata.get("decision_reason")
    curation_date = curation_metadata.get("curation_date")
    limitations = curation_metadata.get("limitations")
    if (
        not isinstance(source_provenance, Mapping)
        or not _text(curator)
        or not _text(decision_reason)
        or not _text(curation_date)
        or not _text_sequence(limitations)
    ):
        raise ParameterRecordAuthoringError(
            "Written bundle cannot reconstruct its deterministic curation report."
        )
    assert isinstance(curator, str)
    assert isinstance(decision_reason, str)
    assert isinstance(curation_date, str)
    assert isinstance(limitations, Sequence) and not isinstance(limitations, (str, bytes))
    record = CurationRecord(
        record_type="parameter_records",
        record_id=str(target_record.get("record_id")),
        proposed_record=deepcopy(dict(target_record)),
        classification="eligible_for_review",
        missing_fields=(),
        reasons=(),
        decision="accept",
        explicit_decision=True,
        curator=curator,
        decision_reason=decision_reason,
        curation_date=curation_date,
        allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
        limitations=tuple(limitations),
        source_provenance=deepcopy(dict(source_provenance)),
    )
    return CuratorAuthoredParameterResult(
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=tuple(proposal_limitations),
        records=(record,),
        source_record_id=source_record_id,
        authored_record_id=authored_record_id,
        authoring_digest=authoring_digest,
    )


def _validate_result_provenance(
    curation: Mapping[str, Any],
    result_provenance: Mapping[str, Any],
) -> None:
    source_provenance = curation.get("source_provenance")
    if not isinstance(source_provenance, Mapping) or any(
        not type_exact_equal(source_provenance.get(field), result_provenance.get(field))
        for field in ("source_query", "source_snapshot_path")
    ):
        raise ParameterRecordAuthoringError(
            "Authored result provenance disagrees with accepted curation evidence."
        )


def _accepted_source(result: CurationResult, record_id: str) -> CurationRecord:
    if not isinstance(result, CurationResult):
        raise ParameterRecordAuthoringError(
            "author_parameter_record requires a validated in-memory CurationResult."
        )
    matches = [record for record in result.records if record.record_id == record_id]
    if len(matches) != 1:
        raise ParameterRecordAuthoringError(
            f"Curation result must contain exactly one source record {record_id!r}."
        )
    if not _text(result.source_query) or not _text(result.source_snapshot_path):
        raise ParameterRecordAuthoringError("Curation result requires source query and snapshot path.")
    record = deepcopy(matches[0])
    if record.record_type != "parameter_records":
        raise ParameterRecordAuthoringError("PR-48 supports accepted parameter_records only.")
    _validate_acceptance(_curation_metadata(record), record_id=record.record_id)
    return record


def _validate_acceptance(curation: Mapping[str, Any], *, record_id: str) -> None:
    if set(curation) != _CURATION_FIELDS:
        raise ParameterRecordAuthoringError(
            f"Source record {record_id!r} curation metadata must match the closed bridge schema."
        )
    exact = {
        "schema_version": CURATION_SCHEMA_VERSION,
        "classification": "eligible_for_review",
        "decision": "accept",
        "explicit_decision": True,
        "allowed_use": CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
        "promotion_status": "not_promoted_to_production_registry",
    }
    if any(not type_exact_equal(curation.get(key), value) for key, value in exact.items()):
        raise ParameterRecordAuthoringError(
            f"Source record {record_id!r} is not an explicit unblocked accepted curation decision."
        )
    if any(curation.get(field) not in ([], ()) for field in ("missing_fields", "reasons")):
        raise ParameterRecordAuthoringError(f"Source record {record_id!r} retains curation blockers.")
    if not all(_text(curation.get(field)) for field in ("curator", "decision_reason", "curation_date")):
        raise ParameterRecordAuthoringError(f"Source record {record_id!r} lacks curator provenance.")
    date_value = curation["curation_date"]
    assert isinstance(date_value, str)
    if not curation_date_is_iso(date_value) or not _text_sequence(curation.get("limitations")):
        raise ParameterRecordAuthoringError(f"Source record {record_id!r} lacks dated limitations.")
    provenance = curation.get("source_provenance")
    missing = curation_source_provenance_missing(provenance if isinstance(provenance, Mapping) else {})
    if missing:
        raise ParameterRecordAuthoringError(
            f"Source record {record_id!r} has incomplete source provenance: {', '.join(missing)}."
        )


def _validate_source_record(
    record: CurationRecord,
    *,
    source_query: str,
    source_snapshot_path: str,
) -> None:
    source = record.proposed_record
    if source.get("record_id") != record.record_id:
        raise ParameterRecordAuthoringError("Source proposal record identity is inconsistent.")
    expected = {
        "proposal_status": PROPOSAL_STATUS,
        "review_required": True,
        "allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "conversion_method": PARAMETER_IDENTITY_CONVERSION_METHOD,
    }
    if any(not type_exact_equal(source.get(key), value) for key, value in expected.items()):
        raise ParameterRecordAuthoringError(
            "Source must remain review-only and use identity_no_conversion; nonidentity is deferred."
        )
    proposed_provenance = source.get("provenance")
    if not isinstance(proposed_provenance, Mapping):
        raise ParameterRecordAuthoringError("Source proposal provenance must be a mapping.")
    if any(
        field not in proposed_provenance
        or field not in record.source_provenance
        or not type_exact_equal(record.source_provenance[field], proposed_provenance[field])
        for field in _PROPOSAL_IDENTITY_FIELDS
    ) or any(
        key not in record.source_provenance
        or not type_exact_equal(record.source_provenance[key], value)
        for key, value in proposed_provenance.items()
    ):
        raise ParameterRecordAuthoringError("Source proposal and accepted curation provenance disagree.")
    _validate_source_provenance(record.source_provenance)
    if record.source_provenance["source_query"] != source_query:
        raise ParameterRecordAuthoringError("Source query is inconsistent across curation evidence.")
    if record.source_provenance["source_snapshot_path"] != source_snapshot_path:
        raise ParameterRecordAuthoringError("Source snapshot path is inconsistent across curation evidence.")

    numeric_fields = ("original_value", "converted_value", "source_value", "normalized_start_value")
    text_fields = ("original_units", "converted_units", "source_units", "normalized_units")
    for field in numeric_fields:
        _finite_float(source.get(field), field=f"source.{field}")
    if not all(_text(source.get(field)) for field in text_fields):
        raise ParameterRecordAuthoringError("Source original and normalized units must be explicit text.")
    if not _text(source.get("parameter_symbol")) or not _text(source.get("parameter_role")):
        raise ParameterRecordAuthoringError(
            "Source parameter_symbol and parameter_role must be explicit text."
        )
    pairs = (
        ("original_value", "source_value"),
        ("converted_value", "source_value"),
        ("normalized_start_value", "source_value"),
        ("original_units", "source_units"),
        ("converted_units", "source_units"),
        ("normalized_units", "source_units"),
    )
    if any(not type_exact_equal(source[left], source[right]) for left, right in pairs):
        raise ParameterRecordAuthoringError(
            "Identity conversion requires exact source/original/normalized/converted correspondence."
        )


def _validate_target_schema(record: Mapping[str, Any], *, audit_required: bool) -> None:
    _require_string_keys(record)
    keys = set(record)
    missing = sorted(_REQUIRED_FIELDS - keys)
    unknown = sorted(keys - _REQUIRED_FIELDS - _OPTIONAL_FIELDS)
    if missing or unknown:
        raise ParameterRecordAuthoringError(
            f"ParameterRecord must match the complete loader-emitted schema; missing={missing}, unknown={unknown}."
        )
    if not all(_text(record.get(field)) for field in ("record_id", "name", "parameter_symbol", "process_type", "notes")):
        raise ParameterRecordAuthoringError("ParameterRecord identity, process, symbol, and notes are required.")
    policies = {
        "maturity": PARAMETER_AUTHORING_MATURITY,
        "allowed_use": PARAMETER_AUTHORING_ALLOWED_USE,
        "range_scope": PARAMETER_AUTHORING_RANGE_SCOPE,
        "range_interpretation": PARAMETER_AUTHORING_RANGE_INTERPRETATION,
    }
    if any(record.get(key) != value for key, value in policies.items()):
        raise ParameterRecordAuthoringError("ParameterRecord maturity, allowed-use, and range policies are closed.")
    selectors = ("enzyme_class", "substrate_class", "fungus_id", "substrate_id", "environment_id")
    if any(record.get(field) is not None and not _text(record.get(field)) for field in selectors):
        raise ParameterRecordAuthoringError("Every selector must be an explicit null or nonblank string.")
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping) or not provenance:
        raise ParameterRecordAuthoringError("ParameterRecord provenance must be a non-empty mapping.")
    present_reserved = set(provenance) & RESERVED_PROVENANCE_KEYS
    expected_reserved = {PARAMETER_BRIDGE_PROVENANCE_KEY} if audit_required else set()
    if present_reserved != expected_reserved:
        raise ParameterRecordAuthoringError(
            "ParameterRecord reserved provenance keys are authoring-owned and cannot collide."
        )
    conflicting_safety = set(provenance) & _OUTER_PROVENANCE_SAFETY_FIELDS
    if conflicting_safety:
        raise ParameterRecordAuthoringError(
            "ParameterRecord outer provenance cannot supply authoring-owned safety claims: "
            + ", ".join(sorted(conflicting_safety))
            + "."
        )
    value = record.get("value")
    if not isinstance(value, Mapping) or set(value) != _VALUE_FIELDS:
        raise ParameterRecordAuthoringError("Exact target must explicitly author every ValueSpec field.")
    if value.get("kind") != "exact":
        raise ParameterRecordAuthoringError("PR-48 accepts exact ValueSpec targets only.")
    _finite_float(value.get("value"), field="parameter_record.value.value")
    if not _text(value.get("units")) or not all(
        _text(value.get(field)) for field in ("source", "notes")
    ):
        raise ParameterRecordAuthoringError("Exact ValueSpec units and provenance text are required.")
    if value.get("confidence_level") != PARAMETER_AUTHORING_CONFIDENCE_LEVEL:
        raise ParameterRecordAuthoringError(
            "Exact ValueSpec confidence_level is closed to identity transcription without validation."
        )
    if any(value.get(field) is not None for field in ("lower", "upper", "distribution")):
        raise ParameterRecordAuthoringError("Exact ValueSpec lower, upper, and distribution must be null.")
    if value.get("parameters") != {}:
        raise ParameterRecordAuthoringError("Exact ValueSpec parameters must be an empty mapping.")


def _validate_target_correspondence(source: CurationRecord, target: Mapping[str, Any]) -> None:
    source_record = source.proposed_record
    value = target["value"]
    provenance = target["provenance"]
    assert isinstance(value, Mapping) and isinstance(provenance, Mapping)
    if not type_exact_equal(value.get("value"), source_record.get("converted_value")):
        raise ParameterRecordAuthoringError("Target value must match converted_value type-exactly.")
    if not type_exact_equal(value.get("units"), source_record.get("converted_units")):
        raise ParameterRecordAuthoringError("Target units must match converted_units exactly.")
    if not type_exact_equal(target.get("parameter_symbol"), source_record.get("parameter_symbol")):
        raise ParameterRecordAuthoringError("Target parameter_symbol must match the selected source record.")
    if not type_exact_equal(provenance.get("parameter_role"), source_record.get("parameter_role")):
        raise ParameterRecordAuthoringError(
            "Target provenance parameter_role must match the selected source role contract."
        )
    if any(
        field not in provenance
        or not type_exact_equal(provenance[field], source.source_provenance[field])
        for field in _SOURCE_IDENTITY_FIELDS
    ):
        raise ParameterRecordAuthoringError("Target provenance must preserve every source identity field.")
    expected_aliases = _source_aliases(source.source_provenance)
    if any(
        field not in provenance or not type_exact_equal(provenance[field], expected)
        for field, expected in expected_aliases.items()
    ):
        raise ParameterRecordAuthoringError(
            "Target singular source identity aliases must be present and match accepted plural identity."
        )
    if not type_exact_equal(provenance.get("curator"), source.curator) or not type_exact_equal(
        provenance.get("curation_date"), source.curation_date
    ):
        raise ParameterRecordAuthoringError("Target provenance must preserve curator identity and date.")


def _source_aliases(provenance: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_reaction_id": _single_source_id(
            provenance.get("source_reaction_ids"), field="source_reaction_ids"
        ),
        "selected_kinlaw_entry_id": _single_source_id(
            provenance.get("source_entry_ids"), field="source_entry_ids"
        ),
    }


def _acceptance_audit(curation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "classification": curation.get("classification"),
        "decision": curation.get("decision"),
        "explicit_decision": curation.get("explicit_decision"),
        "curator": curation.get("curator"),
        "decision_reason": curation.get("decision_reason"),
        "curation_date": curation.get("curation_date"),
        "allowed_use_decision": curation.get("allowed_use"),
        "limitations": deepcopy(curation.get("limitations")),
    }


def _target_policy(target: Mapping[str, Any]) -> dict[str, Any]:
    value = target["value"]
    assert isinstance(value, Mapping)
    return {
        "maturity": target.get("maturity"),
        "allowed_use": target.get("allowed_use"),
        "range_scope": target.get("range_scope"),
        "range_interpretation": target.get("range_interpretation"),
        "value_kind": value.get("kind"),
        "confidence_level": value.get("confidence_level"),
    }


def _audit_payload(
    source: CurationRecord,
    *,
    target: Mapping[str, Any],
    authored_record_id: str,
    registry_evidence: Mapping[str, str],
    selector_resolution: _ResolvedParameterCompatibility,
    result_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    proposed = source.proposed_record
    target_value = target["value"]
    assert isinstance(target_value, Mapping)
    curation = _curation_metadata(source)
    return {
        "schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "workflow": PARAMETER_AUTHORING_WORKFLOW,
        "supported_record_type": "parameter_records",
        "source_proposal_record_id": source.record_id,
        "authored_record_id": authored_record_id,
        "conversion_policy": "identity_only_nonidentity_deferred",
        "source_parameter": {
            "parameter_symbol": proposed["parameter_symbol"],
            "parameter_role": proposed["parameter_role"],
            "proposal_status": proposed["proposal_status"],
            "proposal_allowed_use": proposed["allowed_use"],
            "original_value": proposed["original_value"],
            "original_units": proposed["original_units"],
            "source_value": proposed["source_value"],
            "source_units": proposed["source_units"],
            "normalized_start_value": proposed["normalized_start_value"],
            "normalized_units": proposed["normalized_units"],
            "converted_value": proposed["converted_value"],
            "converted_units": proposed["converted_units"],
            "target_value": target_value["value"],
            "target_units": target_value["units"],
            "conversion_method": proposed["conversion_method"],
        },
        "source_provenance": deepcopy(dict(source.source_provenance)),
        "source_aliases": _source_aliases(source.source_provenance),
        "acceptance": _acceptance_audit(curation),
        "result_provenance": deepcopy(dict(result_provenance)),
        "target_policy": _target_policy(target),
        "registry_context": deepcopy(dict(registry_evidence)),
        "selector_resolution": selector_resolution.to_dict(),
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "production_registry_mutated": False,
    }


def _validate_audit(
    target: Mapping[str, Any],
    curation: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    source_record_id: str,
    result_provenance: Mapping[str, Any],
    expected_digest: str,
) -> None:
    expected = {
        "schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "workflow": PARAMETER_AUTHORING_WORKFLOW,
        "supported_record_type": "parameter_records",
        "source_proposal_record_id": source_record_id,
        "authored_record_id": target.get("record_id"),
        "authoring_digest": expected_digest,
        "conversion_policy": "identity_only_nonidentity_deferred",
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "production_registry_mutated": False,
    }
    if set(audit) != _AUDIT_FIELDS or any(
        not type_exact_equal(audit.get(key), value) for key, value in expected.items()
    ):
        raise ParameterRecordAuthoringError("Parameter bridge audit identity or safety flags changed.")
    source_parameter = audit.get("source_parameter")
    if not isinstance(source_parameter, Mapping) or set(source_parameter) != _SOURCE_PARAMETER_AUDIT_FIELDS:
        raise ParameterRecordAuthoringError("Parameter bridge source_parameter audit is missing.")
    value = target["value"]
    assert isinstance(value, Mapping)
    numeric_fields = (
        "original_value",
        "source_value",
        "normalized_start_value",
        "converted_value",
        "target_value",
    )
    unit_fields = (
        "original_units",
        "source_units",
        "normalized_units",
        "converted_units",
        "target_units",
    )
    for field in numeric_fields:
        _finite_float(source_parameter.get(field), field=f"audit.source_parameter.{field}")
    parameter_expected = {
        "parameter_symbol": target.get("parameter_symbol"),
        "parameter_role": target["provenance"].get("parameter_role"),
        "proposal_status": PROPOSAL_STATUS,
        "proposal_allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "target_value": value.get("value"),
        "target_units": value.get("units"),
        "conversion_method": PARAMETER_IDENTITY_CONVERSION_METHOD,
    }
    if (
        any(
            not type_exact_equal(source_parameter.get(field), source_parameter.get(numeric_fields[0]))
            for field in numeric_fields[1:]
        )
        or any(not _text(source_parameter.get(field)) for field in unit_fields)
        or any(
            not type_exact_equal(source_parameter.get(field), source_parameter.get(unit_fields[0]))
            for field in unit_fields[1:]
        )
        or any(
            not type_exact_equal(source_parameter.get(field), expected_value)
            for field, expected_value in parameter_expected.items()
        )
    ):
        raise ParameterRecordAuthoringError("Parameter bridge audit violates identity correspondence.")
    source_provenance = audit.get("source_provenance")
    if (
        not isinstance(source_provenance, Mapping)
        or set(source_provenance) != _SOURCE_PROVENANCE_FIELDS
        or not type_exact_equal(
            source_provenance, curation.get("source_provenance")
        )
    ):
        raise ParameterRecordAuthoringError("Parameter bridge and curation source provenance disagree.")
    _validate_source_provenance(source_provenance)
    target_provenance = target["provenance"]
    assert isinstance(target_provenance, Mapping)
    if any(
        not type_exact_equal(target_provenance.get(field), source_provenance.get(field))
        for field in _SOURCE_IDENTITY_FIELDS
    ):
        raise ParameterRecordAuthoringError("Target no longer preserves complete source identity.")
    expected_aliases = _source_aliases(source_provenance)
    aliases = audit.get("source_aliases")
    if (
        not isinstance(aliases, Mapping)
        or set(aliases) != _SOURCE_ALIAS_FIELDS
        or not type_exact_equal(aliases, expected_aliases)
        or any(
            not type_exact_equal(target_provenance.get(field), expected_value)
            for field, expected_value in expected_aliases.items()
        )
    ):
        raise ParameterRecordAuthoringError("Parameter bridge singular source identity aliases disagree.")
    expected_acceptance = _acceptance_audit(curation)
    acceptance = audit.get("acceptance")
    if (
        not isinstance(acceptance, Mapping)
        or set(acceptance) != _ACCEPTANCE_AUDIT_FIELDS
        or not type_exact_equal(acceptance, expected_acceptance)
    ):
        raise ParameterRecordAuthoringError("Parameter bridge acceptance audit is inconsistent.")
    audited_result_provenance = audit.get("result_provenance")
    if (
        not isinstance(audited_result_provenance, Mapping)
        or set(audited_result_provenance) != _RESULT_PROVENANCE_FIELDS
        or not type_exact_equal(audited_result_provenance, result_provenance)
    ):
        raise ParameterRecordAuthoringError("Parameter bridge result provenance is inconsistent.")
    expected_target_policy = _target_policy(target)
    target_policy = audit.get("target_policy")
    if (
        not isinstance(target_policy, Mapping)
        or set(target_policy) != _TARGET_POLICY_AUDIT_FIELDS
        or not type_exact_equal(target_policy, expected_target_policy)
    ):
        raise ParameterRecordAuthoringError("Parameter bridge target policy is inconsistent.")
    context = audit.get("registry_context")
    if (
        not isinstance(context, Mapping)
        or set(context) != _REGISTRY_CONTEXT_FIELDS
        or not all(_text(context.get(key)) for key in ("registry_id", "registry_version"))
    ):
        raise ParameterRecordAuthoringError("Parameter bridge registry context is incomplete.")
    if not isinstance(context.get("registry_index_sha256"), str) or _SHA256.fullmatch(
        context["registry_index_sha256"]
    ) is None:
        raise ParameterRecordAuthoringError("Parameter bridge registry digest is invalid.")
    if not isinstance(context.get("registry_content_sha256"), str) or _SHA256.fullmatch(
        context["registry_content_sha256"]
    ) is None:
        raise ParameterRecordAuthoringError("Parameter bridge full registry digest is invalid.")
    resolution = audit.get("selector_resolution")
    if (
        not isinstance(resolution, Mapping)
        or set(resolution) != _SELECTOR_RESOLUTION_FIELDS
        or not _text_sequence(resolution.get("effective_enzyme_classes"))
        or not all(
            _text(resolution.get(field))
            for field in (
                "effective_substrate_class",
                "process_type",
                "parameter_symbol",
                "parameter_role",
                "process_compatibility_id",
            )
        )
        or any(
            resolution.get(field) is not None and not _text(resolution.get(field))
            for field in ("fungus_id", "substrate_id", "environment_id")
        )
        or not type_exact_equal(resolution.get("fungus_id"), target.get("fungus_id"))
        or not type_exact_equal(resolution.get("substrate_id"), target.get("substrate_id"))
        or not type_exact_equal(resolution.get("environment_id"), target.get("environment_id"))
        or not type_exact_equal(resolution.get("process_type"), target.get("process_type"))
        or not type_exact_equal(resolution.get("parameter_symbol"), target.get("parameter_symbol"))
        or not type_exact_equal(
            resolution.get("parameter_role"), target_provenance.get("parameter_role")
        )
    ):
        raise ParameterRecordAuthoringError(
            "Parameter bridge selector and compatibility resolution is inconsistent."
        )


def _validate_source_provenance(provenance: Mapping[str, Any]) -> None:
    if set(provenance) != _SOURCE_PROVENANCE_FIELDS:
        raise ParameterRecordAuthoringError("Source provenance fields must match the closed bridge schema.")
    for field in _SOURCE_IDENTITY_FIELDS:
        if field not in provenance:
            raise ParameterRecordAuthoringError(f"Source provenance requires {field}.")
        value = provenance.get(field)
        if field in {"source_entry_ids", "source_reaction_ids", "source_urls"}:
            valid = _text_sequence(value)
        elif field == "source_snapshot_sha256":
            valid = isinstance(value, str) and _SHA256.fullmatch(value) is not None
        elif field == "source_url":
            valid = value is None or _text(value)
        else:
            valid = _text(value)
        if not valid:
            raise ParameterRecordAuthoringError(f"Source provenance requires {field}.")
    source_urls = provenance["source_urls"]
    assert isinstance(source_urls, Sequence) and not isinstance(source_urls, (str, bytes))
    source_url = provenance["source_url"]
    valid_url_cardinality = (
        len(source_urls) == 1
        and type_exact_equal(source_url, source_urls[0])
    ) or (len(source_urls) > 1 and source_url is None)
    if not valid_url_cardinality:
        raise ParameterRecordAuthoringError(
            "Source provenance URL cardinality requires one URL in both forms or multiple "
            "ordered source_urls with source_url null."
        )
    if provenance["source_database"] == "SABIO-RK":
        try:
            frozen_urls = list(frozen_source_urls(str(provenance["source_snapshot_path"])))
        except (OSError, ValueError) as exc:
            raise ParameterRecordAuthoringError(
                f"Frozen SABIO-RK source URL evidence is unreadable: {exc}"
            ) from exc
        if not type_exact_equal(provenance["source_urls"], frozen_urls):
            raise ParameterRecordAuthoringError(
                "Source provenance URL identity disagrees with frozen SABIO-RK fetch metadata."
            )
    if provenance.get("proposal_status") != PROPOSAL_STATUS or not _text(provenance.get("notes")):
        raise ParameterRecordAuthoringError("Source provenance status and notes are incomplete.")
    _verify_snapshot(provenance)


def _validate_loader_fidelity(record: Mapping[str, Any]) -> None:
    try:
        loaded = load_parameter_record_mapping(record)
        validation = loaded.validate()
    except (OverflowError, TypeError, ValueError) as exc:
        raise ParameterRecordAuthoringError(f"ParameterRecord failed production loading: {exc}") from exc
    if not validation.passed:
        raise ParameterRecordAuthoringError(
            f"ParameterRecord failed production validation: {validation.details.get('issues', [])}"
        )
    loaded_mapping = loaded.to_dict()
    if not type_exact_equal(record, loaded_mapping):
        dropped, synthesized, changed = round_trip_differences(record, loaded_mapping)
        raise ParameterRecordAuthoringError(
            "ParameterRecord changed during production-loader round trip: "
            f"dropped={list(dropped)}, synthesized={list(synthesized)}, changed={list(changed)}"
        )


def _load_registry_context(registry_index: str | Path) -> _RegistryContext:
    path = Path(registry_index)
    if ".." in path.parts:
        raise ParameterRecordAuthoringError(f"Registry index path traversal is not allowed: {path}")
    _reject_symlinks(path, label="Registry index path")
    try:
        resolved = path.resolve(strict=True)
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ParameterRecordAuthoringError(f"Registry index is unreadable: {path}: {exc}") from exc
    if not resolved.is_file() or not isinstance(payload, Mapping):
        raise ParameterRecordAuthoringError("Registry index must be a regular YAML mapping.")
    if payload.get("kind") != "fungmod_registry_index":
        raise ParameterRecordAuthoringError("Registry index kind is unsupported.")
    registry_id = payload.get("registry_id")
    version = payload.get("version")
    if not _text(registry_id) or not _text(version):
        raise ParameterRecordAuthoringError("Registry index identity and version are required.")
    assert isinstance(registry_id, str) and isinstance(version, str)
    try:
        registry = load_registry(resolved)
    except (OSError, TypeError, ValueError) as exc:
        raise ParameterRecordAuthoringError(f"Registry failed production loading: {exc}") from exc
    try:
        content_digest = tree_content_digest(resolved.parent, label="Registry root")
    except (OSError, TreeIntegrityError) as exc:
        raise ParameterRecordAuthoringError(f"Registry content cannot be hashed safely: {exc}") from exc
    return _RegistryContext(
        registry=registry,
        evidence={
            "registry_id": registry_id,
            "registry_version": version,
            "registry_index_sha256": sha256_bytes(resolved.read_bytes()),
            "registry_content_sha256": content_digest,
        },
    )


def _resolve_parameter_compatibility(
    record: Mapping[str, Any],
    registry: FungModRegistry,
) -> _ResolvedParameterCompatibility:
    loaded = load_parameter_record_mapping(record)
    provenance = record.get("provenance")
    parameter_role = provenance.get("parameter_role") if isinstance(provenance, Mapping) else None
    if not _text(parameter_role):
        raise ParameterRecordAuthoringError(
            "Curator-authored provenance requires one explicit parameter_role."
        )
    assert isinstance(parameter_role, str)
    effective_enzyme_classes: set[str] = set()
    if loaded.enzyme_class is not None:
        if loaded.enzyme_class not in registry.enzyme_classes:
            raise ParameterRecordAuthoringError(
                f"Unknown authored enzyme_class {loaded.enzyme_class!r}."
            )
        effective_enzyme_classes.add(loaded.enzyme_class)
    if loaded.substrate_class is not None and not any(
        item.substrate_class == loaded.substrate_class for item in registry.substrates.values()
    ):
        raise ParameterRecordAuthoringError(f"Unknown authored substrate_class {loaded.substrate_class!r}.")
    if loaded.fungus_id is not None:
        fungus = _registry_lookup(registry.get_fungus, loaded.fungus_id)
        for enzyme_class in fungus.enzyme_classes:
            _registry_lookup(registry.get_enzyme_class, enzyme_class)
        if loaded.enzyme_class is not None and loaded.enzyme_class not in fungus.enzyme_classes:
            raise ParameterRecordAuthoringError("Authored fungus_id does not declare enzyme_class.")
        effective_enzyme_classes = (
            {loaded.enzyme_class}
            if loaded.enzyme_class is not None
            else set(fungus.enzyme_classes)
        )
    if not effective_enzyme_classes:
        raise ParameterRecordAuthoringError(
            "Authored selectors must resolve at least one effective enzyme class."
        )
    effective_substrate_class = loaded.substrate_class
    if loaded.substrate_id is not None:
        substrate = _registry_lookup(registry.get_substrate, loaded.substrate_id)
        if loaded.substrate_class is not None and substrate.substrate_class != loaded.substrate_class:
            raise ParameterRecordAuthoringError("Authored substrate_id and substrate_class are incompatible.")
        effective_substrate_class = substrate.substrate_class
    if effective_substrate_class is None:
        raise ParameterRecordAuthoringError(
            "Authored selectors must resolve one effective substrate class."
        )
    if loaded.environment_id is not None:
        _registry_lookup(registry.get_environment, loaded.environment_id)
    matches = tuple(
        item
        for item in registry.process_compatibility.values()
        if item.process_type == loaded.process_type
        and item.enzyme_class in effective_enzyme_classes
        and item.substrate_class == effective_substrate_class
        and loaded.parameter_symbol in item.required_parameters
        and item.parameter_roles.get(parameter_role) == loaded.parameter_symbol
        and tuple(
            role
            for role, symbol in item.parameter_roles.items()
            if symbol == loaded.parameter_symbol
        )
        == (parameter_role,)
    )
    if len(matches) != 1:
        raise ParameterRecordAuthoringError(
            "Authored selectors and parameter role require exactly one effective process "
            f"compatibility record; found {len(matches)}."
        )
    return _ResolvedParameterCompatibility(
        fungus_id=loaded.fungus_id,
        effective_enzyme_classes=tuple(sorted(effective_enzyme_classes)),
        substrate_id=loaded.substrate_id,
        effective_substrate_class=effective_substrate_class,
        environment_id=loaded.environment_id,
        process_type=loaded.process_type,
        parameter_symbol=loaded.parameter_symbol,
        parameter_role=parameter_role,
        process_compatibility_id=matches[0].record_id,
    )


def _registry_lookup(function: Any, record_id: str) -> Any:
    try:
        return function(record_id)
    except RegistryLookupError as exc:
        raise ParameterRecordAuthoringError(str(exc)) from exc


def _verify_snapshot(provenance: Mapping[str, Any]) -> None:
    path = Path(str(provenance["source_snapshot_path"]))
    if ".." in path.parts:
        raise ParameterRecordAuthoringError("Frozen source snapshot path traversal is not allowed.")
    _reject_symlinks(path, label="Frozen source snapshot path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ParameterRecordAuthoringError(f"Frozen source snapshot does not exist: {path}") from exc
    if not resolved.is_file():
        raise ParameterRecordAuthoringError(f"Frozen source snapshot is not a file: {resolved}")
    actual = sha256_bytes(resolved.read_bytes())
    if not hmac.compare_digest(actual, str(provenance["source_snapshot_sha256"])):
        raise ParameterRecordAuthoringError("Frozen source snapshot checksum mismatch.")


def _curation_metadata(record: CurationRecord) -> Mapping[str, Any]:
    curation = record.to_dict().get("curation")
    if not isinstance(curation, Mapping):
        raise ParameterRecordAuthoringError("Accepted record lacks curation metadata.")
    return curation


def _require_string_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ParameterRecordAuthoringError("ParameterRecord mappings require string keys.")
            _require_string_keys(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _require_string_keys(item)


def _finite_float(value: Any, *, field: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ParameterRecordAuthoringError(
            f"{field} must be an explicit finite float; bool, int, string, and nonfinite values are rejected."
        )
    return value


def _single_source_id(value: Any, *, field: str) -> str:
    if not _text_sequence(value) or len(value) != 1:
        raise ParameterRecordAuthoringError(
            f"Source provenance {field} must contain exactly one explicit identity."
        )
    item = value[0]
    assert isinstance(item, str)
    return item


def _reject_symlinks(path: Path, *, label: str) -> None:
    symlink = first_symlink_component(path)
    if symlink is not None:
        raise ParameterRecordAuthoringError(f"{label} contains a symlink component: {symlink}")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and bool(value)
        and all(_text(item) for item in value)
    )


__all__ = [
    "CuratorAuthoredParameterResult",
    "PARAMETER_AUTHORING_ALLOWED_USE",
    "PARAMETER_AUTHORING_CONFIDENCE_LEVEL",
    "PARAMETER_AUTHORING_MATURITY",
    "PARAMETER_AUTHORING_RANGE_INTERPRETATION",
    "PARAMETER_AUTHORING_RANGE_SCOPE",
    "PARAMETER_AUTHORING_SCHEMA_VERSION",
    "PARAMETER_AUTHORING_WORKFLOW",
    "PARAMETER_BRIDGE_PROVENANCE_KEY",
    "PARAMETER_IDENTITY_CONVERSION_METHOD",
    "ParameterRecordAuthoringError",
    "author_parameter_record",
    "validate_parameter_authoring_plan_record",
]
