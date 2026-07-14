"""Identity-only parameter authoring from accepted source curation."""

from __future__ import annotations

import hmac
import json
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fungal_model.api._integrity import (
    canonicalize,
    first_symlink_component,
    round_trip_differences,
    sha256_bytes,
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
    curation_source_provenance_missing,
)
from fungal_model.registry.loaders import load_parameter_record_mapping, load_registry
from fungal_model.registry.store import FungModRegistry, RegistryLookupError
from fungal_model.sources.sabiork import PROPOSAL_STATUS


PARAMETER_AUTHORING_SCHEMA_VERSION = "1.0.0"
PARAMETER_AUTHORING_WORKFLOW = "curator_authored_parameter_record_bridge"
PARAMETER_IDENTITY_CONVERSION_METHOD = "identity_no_conversion"
PARAMETER_AUTHORING_MATURITY = "literature_processed"
PARAMETER_AUTHORING_ALLOWED_USE = "registry_storage_only_no_simulation_authorization"
PARAMETER_AUTHORING_CONFIDENCE_LEVEL = "curator_accepted_identity_transcription_not_validation"
PARAMETER_AUTHORING_RANGE_SCOPE = "single_source_entry"
PARAMETER_AUTHORING_RANGE_INTERPRETATION = "exact_identity_transcription_not_uncertainty"
PARAMETER_BRIDGE_PROVENANCE_KEY = "fungmod_parameter_bridge"

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
    "source_snapshot_sha256",
)
_PROPOSAL_IDENTITY_FIELDS = tuple(
    field for field in _SOURCE_IDENTITY_FIELDS if field != "source_url"
)


class ParameterRecordAuthoringError(ValueError):
    """Raised when parameter authoring would guess, coerce, or lose evidence."""


@dataclass(frozen=True)
class _RegistryContext:
    registry: FungModRegistry
    evidence: Mapping[str, str]


@dataclass(frozen=True)
class CuratorAuthoredParameterResult(CurationResult):
    """One integrity-bound, parameter-only target for promotion planning."""

    source_record_id: str
    authored_record_id: str
    authoring_digest: str

    def summary(self) -> dict[str, Any]:
        return {
            **super().summary(),
            "workflow": PARAMETER_AUTHORING_WORKFLOW,
            "authoring_schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
            "supported_record_types": ["parameter_records"],
            "source_record_id": self.source_record_id,
            "authored_record_id": self.authored_record_id,
            "authoring_digest": self.authoring_digest,
            "identity_conversion_only": True,
            "loader_round_trip_verified": True,
            "selector_compatibility_verified": True,
            "promotion_plan_compatible": True,
            "simulation_authorized": False,
        }

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
    target = deepcopy(dict(parameter_record))
    _validate_target_schema(target, audit_required=False)
    _validate_target_correspondence(source, target)
    context = _load_registry_context(registry_index)
    _validate_selectors(target, context.registry)

    provenance = deepcopy(dict(target["provenance"]))
    provenance[PARAMETER_BRIDGE_PROVENANCE_KEY] = _audit_payload(
        source,
        authored_record_id=str(target["record_id"]),
        registry_evidence=context.evidence,
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
    digest = parameter_authoring_digest(target, curation, source_record_id=source_record_id)
    result = CuratorAuthoredParameterResult(
        source_query=curation_result.source_query,
        source_snapshot_path=curation_result.source_snapshot_path,
        proposal_limitations=tuple(source.limitations),
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
) -> str:
    payload = {
        "kind": PARAMETER_AUTHORING_WORKFLOW,
        "schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "record_type": "parameter_records",
        "source_record_id": source_record_id,
        "target_record": canonicalize(target_record),
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


def is_curator_authored_parameter_record(record: Mapping[str, Any]) -> bool:
    provenance = record.get("provenance")
    return isinstance(provenance, Mapping) and PARAMETER_BRIDGE_PROVENANCE_KEY in provenance


def validate_authored_parameter_record(
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
    *,
    source_record_id: str,
    expected_digest: str,
) -> None:
    actual = parameter_authoring_digest(
        target_record,
        curation_metadata,
        source_record_id=source_record_id,
    )
    if not isinstance(expected_digest, str) or not hmac.compare_digest(actual, expected_digest):
        raise ParameterRecordAuthoringError(
            "Curator-authored parameter result changed after construction or bundle writing."
        )
    _validate_acceptance(curation_metadata, record_id=str(target_record.get("record_id", "")))
    _validate_target_schema(target_record, audit_required=True)
    audit = target_record["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY]
    assert isinstance(audit, Mapping)
    _validate_audit(target_record, curation_metadata, audit, source_record_id=source_record_id)
    _validate_loader_fidelity(target_record)


def validate_parameter_authoring_bundle_record(
    *,
    summary: Mapping[str, Any],
    record_type: str,
    target_record: Mapping[str, Any],
    curation_metadata: Mapping[str, Any],
) -> None:
    expected = {
        "workflow": PARAMETER_AUTHORING_WORKFLOW,
        "authoring_schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "supported_record_types": ["parameter_records"],
    }
    if any(not type_exact_equal(summary.get(key), value) for key, value in expected.items()):
        raise ParameterRecordAuthoringError("Written bundle lacks the parameter-only authoring contract.")
    source_id = summary.get("source_record_id")
    authored_id = summary.get("authored_record_id")
    digest = summary.get("authoring_digest")
    if record_type != "parameter_records" or target_record.get("record_id") != authored_id:
        raise ParameterRecordAuthoringError("Written authoring summary does not match its parameter target.")
    if not _text(source_id) or not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise ParameterRecordAuthoringError("Written authoring summary lacks source identity or digest.")
    assert isinstance(source_id, str)
    validate_authored_parameter_record(
        target_record,
        curation_metadata,
        source_record_id=source_id,
        expected_digest=digest,
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
    _validate_selectors(target_record, context.registry)


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
    if not _text(source.get("parameter_symbol")):
        raise ParameterRecordAuthoringError("Source parameter_symbol must be explicit text.")
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
    has_audit = PARAMETER_BRIDGE_PROVENANCE_KEY in provenance
    if has_audit != audit_required:
        raise ParameterRecordAuthoringError("Reserved parameter bridge audit presence is inconsistent.")
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
    if any(
        field not in provenance
        or not type_exact_equal(provenance[field], source.source_provenance[field])
        for field in _SOURCE_IDENTITY_FIELDS
    ):
        raise ParameterRecordAuthoringError("Target provenance must preserve every source identity field.")
    if not type_exact_equal(provenance.get("curator"), source.curator) or not type_exact_equal(
        provenance.get("curation_date"), source.curation_date
    ):
        raise ParameterRecordAuthoringError("Target provenance must preserve curator identity and date.")


def _audit_payload(
    source: CurationRecord,
    *,
    authored_record_id: str,
    registry_evidence: Mapping[str, str],
) -> dict[str, Any]:
    proposed = source.proposed_record
    return {
        "schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "workflow": PARAMETER_AUTHORING_WORKFLOW,
        "supported_record_type": "parameter_records",
        "source_proposal_record_id": source.record_id,
        "authored_record_id": authored_record_id,
        "conversion_policy": "identity_only_nonidentity_deferred",
        "source_parameter": {
            "parameter_symbol": proposed["parameter_symbol"],
            "proposal_status": proposed["proposal_status"],
            "proposal_allowed_use": proposed["allowed_use"],
            "original_value": proposed["original_value"],
            "original_units": proposed["original_units"],
            "converted_value": proposed["converted_value"],
            "converted_units": proposed["converted_units"],
            "conversion_method": proposed["conversion_method"],
        },
        "source_provenance": deepcopy(dict(source.source_provenance)),
        "acceptance": {
            "classification": source.classification,
            "decision": source.decision,
            "explicit_decision": source.explicit_decision,
            "curator": source.curator,
            "decision_reason": source.decision_reason,
            "curation_date": source.curation_date,
            "allowed_use_decision": source.allowed_use,
            "limitations": list(source.limitations),
        },
        "registry_context": deepcopy(dict(registry_evidence)),
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
) -> None:
    expected = {
        "schema_version": PARAMETER_AUTHORING_SCHEMA_VERSION,
        "workflow": PARAMETER_AUTHORING_WORKFLOW,
        "supported_record_type": "parameter_records",
        "source_proposal_record_id": source_record_id,
        "authored_record_id": target.get("record_id"),
        "conversion_policy": "identity_only_nonidentity_deferred",
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
        "production_registry_mutated": False,
    }
    if any(not type_exact_equal(audit.get(key), value) for key, value in expected.items()):
        raise ParameterRecordAuthoringError("Parameter bridge audit identity or safety flags changed.")
    source_parameter = audit.get("source_parameter")
    if not isinstance(source_parameter, Mapping):
        raise ParameterRecordAuthoringError("Parameter bridge source_parameter audit is missing.")
    value = target["value"]
    assert isinstance(value, Mapping)
    pairs = (
        (source_parameter.get("conversion_method"), PARAMETER_IDENTITY_CONVERSION_METHOD),
        (source_parameter.get("original_value"), source_parameter.get("converted_value")),
        (source_parameter.get("original_units"), source_parameter.get("converted_units")),
        (value.get("value"), source_parameter.get("converted_value")),
        (value.get("units"), source_parameter.get("converted_units")),
    )
    if any(not type_exact_equal(left, right) for left, right in pairs):
        raise ParameterRecordAuthoringError("Parameter bridge audit violates identity correspondence.")
    source_provenance = audit.get("source_provenance")
    if not isinstance(source_provenance, Mapping) or not type_exact_equal(
        source_provenance, curation.get("source_provenance")
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
    expected_acceptance = {
        "classification": curation.get("classification"),
        "decision": curation.get("decision"),
        "explicit_decision": curation.get("explicit_decision"),
        "curator": curation.get("curator"),
        "decision_reason": curation.get("decision_reason"),
        "curation_date": curation.get("curation_date"),
        "allowed_use_decision": curation.get("allowed_use"),
        "limitations": deepcopy(curation.get("limitations")),
    }
    if not type_exact_equal(audit.get("acceptance"), expected_acceptance):
        raise ParameterRecordAuthoringError("Parameter bridge acceptance audit is inconsistent.")
    context = audit.get("registry_context")
    if not isinstance(context, Mapping) or not all(_text(context.get(key)) for key in ("registry_id", "registry_version")):
        raise ParameterRecordAuthoringError("Parameter bridge registry context is incomplete.")
    if not isinstance(context.get("registry_index_sha256"), str) or _SHA256.fullmatch(
        context["registry_index_sha256"]
    ) is None:
        raise ParameterRecordAuthoringError("Parameter bridge registry digest is invalid.")


def _validate_source_provenance(provenance: Mapping[str, Any]) -> None:
    for field in _SOURCE_IDENTITY_FIELDS:
        if field not in provenance:
            raise ParameterRecordAuthoringError(f"Source provenance requires {field}.")
        value = provenance.get(field)
        if field in {"source_entry_ids", "source_reaction_ids"}:
            valid = _text_sequence(value)
        elif field == "source_snapshot_sha256":
            valid = isinstance(value, str) and _SHA256.fullmatch(value) is not None
        elif field == "source_url":
            valid = value is None or _text(value)
        else:
            valid = _text(value)
        if not valid:
            raise ParameterRecordAuthoringError(f"Source provenance requires {field}.")
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
    return _RegistryContext(
        registry=registry,
        evidence={
            "registry_id": registry_id,
            "registry_version": version,
            "registry_index_sha256": sha256_bytes(resolved.read_bytes()),
        },
    )


def _validate_selectors(record: Mapping[str, Any], registry: FungModRegistry) -> None:
    loaded = load_parameter_record_mapping(record)
    if loaded.enzyme_class is not None and loaded.enzyme_class not in registry.enzyme_classes:
        raise ParameterRecordAuthoringError(f"Unknown authored enzyme_class {loaded.enzyme_class!r}.")
    if loaded.substrate_class is not None and not any(
        item.substrate_class == loaded.substrate_class for item in registry.substrates.values()
    ):
        raise ParameterRecordAuthoringError(f"Unknown authored substrate_class {loaded.substrate_class!r}.")
    if loaded.fungus_id is not None:
        fungus = _registry_lookup(registry.get_fungus, loaded.fungus_id)
        if loaded.enzyme_class is not None and loaded.enzyme_class not in fungus.enzyme_classes:
            raise ParameterRecordAuthoringError("Authored fungus_id does not declare enzyme_class.")
    if loaded.substrate_id is not None:
        substrate = _registry_lookup(registry.get_substrate, loaded.substrate_id)
        if loaded.substrate_class is not None and substrate.substrate_class != loaded.substrate_class:
            raise ParameterRecordAuthoringError("Authored substrate_id and substrate_class are incompatible.")
    if loaded.environment_id is not None:
        _registry_lookup(registry.get_environment, loaded.environment_id)
    matches = tuple(
        item
        for item in registry.process_compatibility.values()
        if item.process_type == loaded.process_type
        and (loaded.enzyme_class is None or item.enzyme_class == loaded.enzyme_class)
        and (loaded.substrate_class is None or item.substrate_class == loaded.substrate_class)
    )
    if not matches:
        raise ParameterRecordAuthoringError("No process compatibility matches authored selectors.")
    if not any(loaded.parameter_symbol in item.required_parameters for item in matches):
        raise ParameterRecordAuthoringError("Authored parameter_symbol is not required by a compatible process.")


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
]
