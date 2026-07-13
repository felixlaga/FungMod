"""Human review and decision bundles for source registry proposals."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

from fungal_model.sources.sabiork import PROPOSAL_STATUS, RegistryProposal


CURATION_SCHEMA_VERSION = "1.0.0"
CURATION_MANIFEST_KIND = "fungmod_curation_decision_bundle_manifest"
CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY = "review_only_not_simulation_registry"
CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION = "pending_registry_promotion_review"
CURATION_DECISION_ALLOWED_USES = frozenset(
    {
        CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    }
)
_DECISIONS = {"accept", "reject", "defer"}
_RECORD_TYPES = (
    "fungi",
    "substrates",
    "enzyme_classes",
    "product_maps",
    "parameter_records",
    "process_compatibility",
    "case_templates",
)
_TYPE_REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "fungi": ("scientific_name", "enzyme_classes"),
    "substrates": ("substrate_class", "products"),
    "enzyme_classes": ("ec_number", "compatible_processes"),
    "product_maps": (
        "product_map_type",
        "source_entry_id",
        "substrates",
        "products",
        "stoichiometric_yields",
    ),
    "parameter_records": (
        "parameter_symbol",
        "original_value",
        "original_units",
        "converted_value",
        "converted_units",
        "conversion_method",
        "provenance.source_field",
    ),
    "process_compatibility": (
        "process_type",
        "enzyme_class",
        "substrate_class",
        "required_parameters",
        "parameter_roles",
    ),
    "case_templates": (
        "process_type",
        "state_roles",
        "product_map",
        "stoichiometric_yields",
        "limitations",
    ),
}
_FIELD_RULES: Mapping[str, Mapping[str, str]] = {
    "fungi": {
        "scientific_name": "nonblank text",
        "enzyme_classes": "nonempty sequence of nonblank text",
    },
    "substrates": {
        "substrate_class": "nonblank text",
        "products": "nonempty sequence of nonblank text",
    },
    "enzyme_classes": {
        "ec_number": "nonblank text",
        "compatible_processes": "nonempty sequence of nonblank text",
    },
    "product_maps": {
        "product_map_type": "nonblank text",
        "source_entry_id": "nonblank text",
        "substrates": "nonempty participant sequence",
        "products": "nonempty participant sequence",
        "stoichiometric_yields": "positive finite numeric mapping",
    },
    "parameter_records": {
        "parameter_symbol": "nonblank text",
        "original_value": "finite number",
        "original_units": "nonblank text",
        "converted_value": "finite number",
        "converted_units": "nonblank text",
        "conversion_method": "nonblank text",
        "provenance.source_field": "nonblank text",
    },
    "process_compatibility": {
        "process_type": "nonblank text",
        "enzyme_class": "nonblank text",
        "substrate_class": "nonblank text",
        "required_parameters": "nonempty sequence of nonblank text",
        "parameter_roles": "nonempty nonblank text mapping",
    },
    "case_templates": {
        "process_type": "nonblank text",
        "state_roles": "nonempty nonblank text mapping",
        "product_map": "case-template product-map mapping",
        "stoichiometric_yields": "positive finite numeric mapping",
        "limitations": "nonempty sequence of nonblank text",
    },
}
_CANONICAL_SCALAR_SEQUENCE_KEYS = {
    "aliases",
    "compatible_processes",
    "compatible_substrate_classes",
    "enzyme_classes",
    "limitations",
    "missing_fields",
    "products",
    "reasons",
    "required_bond_classes",
    "required_parameters",
    "review_required_fields",
    "source_entry_ids",
    "source_reaction_ids",
    "validity_notes",
}
_CSV_FIELDS = (
    "record_type",
    "record_id",
    "classification",
    "decision",
    "explicit_decision",
    "missing_fields",
    "reasons",
    "source_database",
    "source_entry_ids",
    "source_snapshot_path",
    "allowed_use",
)


class CurationError(ValueError):
    """Raised when a proposal cannot be reviewed without guessing or unsafe IO."""


@dataclass(frozen=True)
class CurationDecision:
    """Complete human decision metadata for one proposed record."""

    decision: Literal["accept", "reject", "defer"] | str
    reason: str
    curation_date: str
    allowed_use: str
    limitations: tuple[str, ...] | Sequence[str]


@dataclass(frozen=True)
class CurationRecord:
    """Schema-review and curator-decision result for one proposed record."""

    record_type: str
    record_id: str
    proposed_record: Mapping[str, Any]
    classification: Literal["eligible_for_review", "blocked_excluded"]
    missing_fields: tuple[str, ...]
    reasons: tuple[str, ...]
    decision: Literal["accept", "reject", "defer"]
    explicit_decision: bool
    curator: str | None
    decision_reason: str
    curation_date: str
    allowed_use: str
    limitations: tuple[str, ...]
    source_provenance: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            **deepcopy(dict(self.proposed_record)),
            "curation": {
                "schema_version": CURATION_SCHEMA_VERSION,
                "classification": self.classification,
                "missing_fields": list(self.missing_fields),
                "reasons": list(self.reasons),
                "decision": self.decision,
                "explicit_decision": self.explicit_decision,
                "curator": self.curator,
                "decision_reason": self.decision_reason,
                "curation_date": self.curation_date,
                "allowed_use": self.allowed_use,
                "limitations": list(self.limitations),
                "source_provenance": deepcopy(dict(self.source_provenance)),
                "promotion_status": "not_promoted_to_production_registry",
            },
        }


@dataclass(frozen=True)
class CurationWriteResult:
    """Paths written for a deterministic CURATION-001 decision bundle."""

    output_directory: Path
    paths: Mapping[str, Path]

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in self.paths.items()}


@dataclass(frozen=True)
class CurationResult:
    """Structured proposal review that never mutates the production registry."""

    source_query: str
    source_snapshot_path: str
    proposal_limitations: tuple[str, ...]
    records: tuple[CurationRecord, ...]

    @property
    def eligible_records(self) -> tuple[CurationRecord, ...]:
        return tuple(record for record in self.records if record.classification == "eligible_for_review")

    @property
    def excluded_records(self) -> tuple[CurationRecord, ...]:
        return tuple(record for record in self.records if record.classification == "blocked_excluded")

    @property
    def accepted_records(self) -> tuple[CurationRecord, ...]:
        return tuple(record for record in self.records if record.explicit_decision and record.decision == "accept")

    @property
    def rejected_records(self) -> tuple[CurationRecord, ...]:
        return tuple(record for record in self.records if record.explicit_decision and record.decision == "reject")

    @property
    def deferred_records(self) -> tuple[CurationRecord, ...]:
        return tuple(record for record in self.records if record.decision == "defer")

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": CURATION_SCHEMA_VERSION,
            "source_query": self.source_query,
            "source_snapshot_path": self.source_snapshot_path,
            "record_count": len(self.records),
            "eligible_for_review_count": len(self.eligible_records),
            "blocked_excluded_count": len(self.excluded_records),
            "accepted_count": len(self.accepted_records),
            "rejected_count": len(self.rejected_records),
            "deferred_count": len(self.deferred_records),
            "production_registry_mutated": False,
            "scientific_validation_claimed": False,
        }

    def write(self, output_dir: str | Path) -> CurationWriteResult:
        """Transactionally replace a deterministic, review-only artifact bundle."""

        root = _safe_output_path(output_dir)
        root.parent.mkdir(parents=True, exist_ok=True)
        _validate_replaceable_destination(root)

        staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.curation-", dir=root.parent))
        try:
            _write_bundle(staging, self)
            _replace_directory(staging, root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        return CurationWriteResult(output_directory=root, paths=_artifact_paths(root))


def review_source_proposal(
    proposal_or_path: RegistryProposal | str | Path,
    *,
    curator: str | None = None,
    decisions: Mapping[str, CurationDecision | Mapping[str, Any]] | None = None,
) -> CurationResult:
    """Validate and review a source proposal without trusting or promoting it.

    Omitted decisions always remain deferred. Every explicit decision requires
    complete curator metadata, and blocked records cannot be accepted.
    """

    payload = _proposal_payload(proposal_or_path)
    source_query, source_snapshot_path, limitations, grouped_records = _validate_proposal(payload)
    normalized_decisions = _normalize_decisions(decisions or {}, curator=curator)

    known_ids = {
        str(record["record_id"])
        for records in grouped_records.values()
        for record in records
    }
    unknown_ids = sorted(set(normalized_decisions) - known_ids)
    if unknown_ids:
        raise CurationError(f"Decisions reference unknown record IDs: {', '.join(unknown_ids)}")

    reviewed: list[CurationRecord] = []
    for record_type in _RECORD_TYPES:
        for proposed_record in grouped_records[record_type]:
            record_id = str(proposed_record["record_id"])
            missing_fields, reasons, provenance = _review_record(
                record_type,
                proposed_record,
                source_snapshot_path=source_snapshot_path,
            )
            classification: Literal["eligible_for_review", "blocked_excluded"] = (
                "blocked_excluded" if reasons else "eligible_for_review"
            )
            decision = normalized_decisions.get(record_id)
            if decision is not None and decision.decision == "accept" and reasons:
                raise CurationError(
                    f"Record {record_id!r} cannot be accepted because it is blocked/excluded: "
                    f"{'; '.join(reasons)}"
                )
            reviewed.append(
                CurationRecord(
                    record_type=record_type,
                    record_id=record_id,
                    proposed_record=deepcopy(proposed_record),
                    classification=classification,
                    missing_fields=missing_fields,
                    reasons=reasons,
                    decision="defer" if decision is None else decision.decision,  # type: ignore[arg-type]
                    explicit_decision=decision is not None,
                    curator=None if decision is None else curator.strip() if curator is not None else None,
                    decision_reason="" if decision is None else decision.reason,
                    curation_date="" if decision is None else decision.curation_date,
                    allowed_use=(
                        CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY
                        if decision is None
                        else decision.allowed_use
                    ),
                    limitations=(
                        limitations
                        if decision is None
                        else tuple(sorted(str(value).strip() for value in decision.limitations))
                    ),
                    source_provenance=provenance,
                )
            )

    return CurationResult(
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=limitations,
        records=tuple(sorted(reviewed, key=lambda item: (item.record_type, item.record_id))),
    )


def _proposal_payload(proposal_or_path: RegistryProposal | str | Path) -> Mapping[str, Any]:
    if isinstance(proposal_or_path, RegistryProposal):
        return proposal_or_path.to_dict()
    path = Path(proposal_or_path)
    if ".." in path.parts:
        raise CurationError(f"Proposal path traversal is not allowed: {path}")
    _reject_symlink_components(path, label="Proposal path")
    manifest = path / "proposal_manifest.json" if path.is_dir() else path
    if manifest.name != "proposal_manifest.json":
        raise CurationError("A written proposal input must be a bundle directory or proposal_manifest.json.")
    _reject_symlink_components(manifest, label="Proposal manifest path")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CurationError(f"Malformed proposal bundle {manifest}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CurationError("Proposal manifest must contain a JSON object.")
    return payload


def _validate_proposal(
    payload: Mapping[str, Any],
) -> tuple[str, str, tuple[str, ...], dict[str, list[dict[str, Any]]]]:
    if payload.get("kind") != "fungmod_sabiork_registry_proposal":
        raise CurationError("Proposal kind must be 'fungmod_sabiork_registry_proposal'.")
    if payload.get("proposal_status") != PROPOSAL_STATUS:
        raise CurationError(f"Proposal status must be {PROPOSAL_STATUS!r}.")
    source_query = _required_text(payload, "source_query", scope="proposal")
    source_snapshot_path = _required_text(payload, "source_snapshot_path", scope="proposal")
    limitations_value = payload.get("limitations")
    if not _nonempty_string_sequence(limitations_value):
        raise CurationError("Proposal field 'limitations' must be a non-empty list of explicit limitations.")
    assert isinstance(limitations_value, Sequence)
    limitations = tuple(sorted(str(value).strip() for value in limitations_value))

    proposed_records = payload.get("proposed_records")
    if not isinstance(proposed_records, Mapping):
        raise CurationError("Proposal field 'proposed_records' must be a mapping.")
    unexpected = sorted(set(proposed_records) - set(_RECORD_TYPES))
    missing_types = sorted(set(_RECORD_TYPES) - set(proposed_records))
    if unexpected or missing_types:
        details = []
        if unexpected:
            details.append(f"unknown record groups: {', '.join(unexpected)}")
        if missing_types:
            details.append(f"missing record groups: {', '.join(missing_types)}")
        raise CurationError("Malformed proposal record groups; " + "; ".join(details) + ".")

    grouped: dict[str, list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()
    for record_type in _RECORD_TYPES:
        value = proposed_records[record_type]
        if not isinstance(value, list):
            raise CurationError(f"Proposal record group {record_type!r} must be a list.")
        grouped[record_type] = []
        for index, record in enumerate(value):
            if not isinstance(record, Mapping):
                raise CurationError(f"{record_type}[{index}] must be a mapping.")
            record_copy = deepcopy(dict(record))
            record_id = record_copy.get("record_id")
            if not isinstance(record_id, str) or not record_id.strip():
                raise CurationError(f"{record_type}[{index}] requires a non-empty record_id.")
            if record_id in seen_ids:
                raise CurationError(f"Duplicate proposal record ID: {record_id}")
            seen_ids.add(record_id)
            grouped[record_type].append(record_copy)
    return source_query, source_snapshot_path, limitations, grouped


def _review_record(
    record_type: str,
    record: Mapping[str, Any],
    *,
    source_snapshot_path: str,
) -> tuple[tuple[str, ...], tuple[str, ...], Mapping[str, Any]]:
    required_fields = (
        "proposal_status",
        "review_required",
        "allowed_use",
        *_TYPE_REQUIRED_FIELDS[record_type],
    )
    missing = {field for field in required_fields if _is_missing(_nested_value(record, field))}
    review_required_fields = record.get("review_required_fields", [])
    if not isinstance(review_required_fields, Sequence) or isinstance(review_required_fields, (str, bytes)):
        review_required_fields = []
    for field in review_required_fields:
        if isinstance(field, str) and _is_missing(_nested_value(record, field)):
            missing.add(field)

    reasons: list[str] = []
    if record.get("proposal_status") != PROPOSAL_STATUS:
        reasons.append(f"proposal_status must be {PROPOSAL_STATUS!r}")
    if record.get("review_required") is not True:
        reasons.append("review_required must be true")
    if record.get("allowed_use") != CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY:
        reasons.append(
            f"allowed_use must be {CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY!r} while proposed"
        )
    if "review_required_fields" in record and not _nonempty_string_sequence(record["review_required_fields"]):
        reasons.append("review_required_fields must be a nonempty sequence of nonblank text when present")
    reasons.extend(_record_schema_issues(record_type, record))
    if missing:
        reasons.append("missing required fields: " + ", ".join(sorted(missing)))

    provenance = _source_provenance(record, source_snapshot_path=source_snapshot_path)
    provenance_missing = _provenance_missing(provenance)
    if provenance_missing:
        missing.update(f"source_provenance.{field}" for field in provenance_missing)
        reasons.append("missing source provenance: " + ", ".join(provenance_missing))
    return tuple(sorted(missing)), tuple(sorted(set(reasons))), provenance


def _source_provenance(record: Mapping[str, Any], *, source_snapshot_path: str) -> Mapping[str, Any]:
    nested = record.get("provenance")
    has_nested = isinstance(nested, Mapping)
    provenance = deepcopy(dict(nested)) if has_nested else {}
    source_database = (
        provenance.get("source_database")
        if has_nested
        else record.get("source_database")
    )
    entry_ids = provenance.get("source_entry_ids") if has_nested else None
    if entry_ids is None and not _is_missing(record.get("source_entry_id")):
        entry_ids = [str(record["source_entry_id"])]
    snapshot = (
        provenance.get("source_snapshot_path", source_snapshot_path)
        if has_nested
        else source_snapshot_path
    )
    source_url = provenance.get("source_url") if has_nested else record.get("source_url")
    if _nonempty_string_sequence(entry_ids):
        assert isinstance(entry_ids, Sequence) and not isinstance(entry_ids, (str, bytes))
        entry_ids = sorted(str(value).strip() for value in entry_ids)
    return {
        **provenance,
        "source_database": source_database,
        "source_entry_ids": entry_ids,
        "source_snapshot_path": snapshot,
        "source_url": source_url,
    }


def _provenance_missing(provenance: Mapping[str, Any]) -> tuple[str, ...]:
    missing: list[str] = []
    if not _nonblank_text(provenance.get("source_database")):
        missing.append("source_database")
    if not _nonempty_string_sequence(provenance.get("source_entry_ids")):
        missing.append("source_entry_ids")
    if not (
        _nonblank_text(provenance.get("source_snapshot_path"))
        or _nonblank_text(provenance.get("source_url"))
    ):
        missing.append("source_snapshot_path_or_source_url")
    return tuple(missing)


def _record_schema_issues(record_type: str, record: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for field, rule in _FIELD_RULES[record_type].items():
        value = _nested_value(record, field)
        if _is_missing(value):
            continue
        if not _field_matches_rule(value, rule):
            issues.append(f"field {field!r} must be {rule}")
    return issues


def _field_matches_rule(value: Any, rule: str) -> bool:
    if rule == "nonblank text":
        return _nonblank_text(value)
    if rule == "nonempty sequence of nonblank text":
        return _nonempty_string_sequence(value)
    if rule == "nonempty participant sequence":
        return _participant_sequence(value)
    if rule == "positive finite numeric mapping":
        return _positive_numeric_mapping(value)
    if rule == "finite number":
        return _finite_number(value)
    if rule == "nonempty nonblank text mapping":
        return _nonblank_text_mapping(value)
    if rule == "nonempty mapping":
        return isinstance(value, Mapping) and bool(value)
    if rule == "case-template product-map mapping":
        return _case_template_product_map(value)
    raise AssertionError(f"Unknown curation field rule: {rule}")


def _participant_sequence(value: Any) -> bool:
    required = ("entry_id", "reaction_id", "role", "compound_name", "stoichiometry")
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and bool(value)
        and all(
            isinstance(item, Mapping)
            and all(_nonblank_text(item.get(field)) for field in required)
            for item in value
        )
    )


def _positive_numeric_mapping(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(
            _nonblank_text(key) and _finite_number(item) and float(item) > 0.0
            for key, item in value.items()
        )
    )


def _nonblank_text_mapping(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(_nonblank_text(key) and _nonblank_text(item) for key, item in value.items())
    )


def _case_template_product_map(value: Any) -> bool:
    required = ("id", "product_map_type", "substrate_state_role", "product_state_role")
    return isinstance(value, Mapping) and all(_nonblank_text(value.get(field)) for field in required)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _normalize_decisions(
    decisions: Mapping[str, CurationDecision | Mapping[str, Any]],
    *,
    curator: str | None,
) -> dict[str, CurationDecision]:
    if decisions and (not isinstance(curator, str) or not curator.strip()):
        raise CurationError("A non-empty curator identity is required for explicit decisions.")
    normalized: dict[str, CurationDecision] = {}
    for record_id, value in decisions.items():
        if not isinstance(record_id, str) or not record_id.strip():
            raise CurationError("Decision record IDs must be non-empty strings.")
        if isinstance(value, CurationDecision):
            decision = value
        elif isinstance(value, Mapping):
            try:
                decision = CurationDecision(
                    decision=value["decision"],
                    reason=value["reason"],
                    curation_date=value["curation_date"],
                    allowed_use=value["allowed_use"],
                    limitations=value["limitations"],
                )
            except KeyError as exc:
                raise CurationError(
                    f"Decision for {record_id!r} is missing required field {exc.args[0]!r}."
                ) from exc
        else:
            raise CurationError(f"Decision for {record_id!r} must be CurationDecision or a mapping.")
        _validate_decision(record_id, decision)
        normalized[record_id] = decision
    return normalized


def _validate_decision(record_id: str, decision: CurationDecision) -> None:
    if decision.decision not in _DECISIONS:
        raise CurationError(
            f"Unknown decision {decision.decision!r} for {record_id!r}; expected accept, reject, or defer."
        )
    for field, value in (("reason", decision.reason), ("curation_date", decision.curation_date), ("allowed_use", decision.allowed_use)):
        if not isinstance(value, str) or not value.strip():
            raise CurationError(f"Decision for {record_id!r} requires non-empty {field}.")
    if decision.allowed_use not in CURATION_DECISION_ALLOWED_USES:
        allowed = ", ".join(sorted(CURATION_DECISION_ALLOWED_USES))
        raise CurationError(
            f"Decision for {record_id!r} has unknown allowed_use {decision.allowed_use!r}; "
            f"expected one of: {allowed}."
        )
    expected_allowed_use = (
        CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION
        if decision.decision == "accept"
        else CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY
    )
    if decision.allowed_use != expected_allowed_use:
        raise CurationError(
            f"Decision {decision.decision!r} for {record_id!r} requires allowed_use "
            f"{expected_allowed_use!r}."
        )
    try:
        date.fromisoformat(decision.curation_date)
    except ValueError as exc:
        raise CurationError(f"Decision for {record_id!r} requires curation_date in YYYY-MM-DD form.") from exc
    if not _nonempty_string_sequence(decision.limitations):
        raise CurationError(f"Decision for {record_id!r} requires explicit non-empty limitations.")


def _write_bundle(root: Path, result: CurationResult) -> None:
    paths = _artifact_paths(root)
    _write_csv(paths["eligible_records"], result.eligible_records)
    _write_csv(paths["excluded_records"], result.excluded_records)
    _write_yaml(paths["proposed_registry_records"], _records_payload("proposed", result.records, result))
    _write_yaml(paths["accepted_registry_records"], _records_payload("accepted", result.accepted_records, result))
    _write_yaml(paths["rejected_registry_records"], _records_payload("rejected", result.rejected_records, result))
    paths["curation_report"].write_text(_report_markdown(result), encoding="utf-8")

    checksums = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in paths.items()
        if key != "curation_manifest"
    }
    manifest = {
        "kind": CURATION_MANIFEST_KIND,
        "schema_version": CURATION_SCHEMA_VERSION,
        "source_query": result.source_query,
        "source_snapshot_path": result.source_snapshot_path,
        "summary": result.summary(),
        "files": checksums,
        "allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
    }
    paths["curation_manifest"].write_text(
        json.dumps(_canonicalize(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _artifact_paths(root: Path) -> dict[str, Path]:
    return {
        "curation_report": root / "curation_report.md",
        "eligible_records": root / "eligible_records.csv",
        "excluded_records": root / "excluded_records.csv",
        "proposed_registry_records": root / "proposed_registry_records.yml",
        "accepted_registry_records": root / "accepted_registry_records.yml",
        "rejected_registry_records": root / "rejected_registry_records.yml",
        "curation_manifest": root / "curation_manifest.json",
    }


def _records_payload(
    bundle_status: str,
    records: Sequence[CurationRecord],
    result: CurationResult,
) -> Mapping[str, Any]:
    return {
        "kind": "fungmod_curation_decision_records",
        "schema_version": CURATION_SCHEMA_VERSION,
        "bundle_status": bundle_status,
        "allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "source_query": result.source_query,
        "source_snapshot_path": result.source_snapshot_path,
        "production_registry_promotion": False,
        "records": [record.to_dict() for record in records],
    }


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(yaml.safe_dump(_canonicalize(payload), sort_keys=False), encoding="utf-8")


def _write_csv(path: Path, records: Sequence[CurationRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for record in records:
            provenance = record.source_provenance
            writer.writerow(
                {
                    "record_type": record.record_type,
                    "record_id": record.record_id,
                    "classification": record.classification,
                    "decision": record.decision,
                    "explicit_decision": str(record.explicit_decision).lower(),
                    "missing_fields": "; ".join(record.missing_fields),
                    "reasons": "; ".join(record.reasons),
                    "source_database": provenance.get("source_database", ""),
                    "source_entry_ids": "; ".join(
                        sorted(str(value) for value in provenance.get("source_entry_ids", []))
                    ),
                    "source_snapshot_path": provenance.get("source_snapshot_path", ""),
                    "allowed_use": record.allowed_use,
                }
            )


def _report_markdown(result: CurationResult) -> str:
    summary = result.summary()
    lines = [
        "# CURATION-001 Proposal Review",
        "",
        f"- Schema version: `{CURATION_SCHEMA_VERSION}`",
        f"- Source query: `{result.source_query}`",
        f"- Source snapshot: `{result.source_snapshot_path}`",
        f"- Total proposed records: {summary['record_count']}",
        f"- Eligible for review: {summary['eligible_for_review_count']}",
        f"- Blocked/excluded: {summary['blocked_excluded_count']}",
        f"- Explicitly accepted: {summary['accepted_count']}",
        f"- Explicitly rejected: {summary['rejected_count']}",
        f"- Deferred, including all records without an explicit decision: {summary['deferred_count']}",
        "",
        "## Scope",
        "",
        "Acceptance in this bundle is a curator decision only. It is not production registry promotion, scientific validation, or permission for simulation. No `data_registry/` records were written or changed.",
        "",
        "## Blocked Or Excluded Records",
        "",
        "| Record type | Record ID | Missing fields | Reasons |",
        "| --- | --- | --- | --- |",
    ]
    if result.excluded_records:
        lines.extend(
            f"| {_md(record.record_type)} | `{_md(record.record_id)}` | {_md('; '.join(record.missing_fields))} | {_md('; '.join(record.reasons))} |"
            for record in result.excluded_records
        )
    else:
        lines.append("| none | none | none | none |")
    lines.extend(["", "## Explicit Decisions", "", "| Record ID | Decision | Curator | Date | Reason | Allowed use |", "| --- | --- | --- | --- | --- | --- |"])
    explicit = [record for record in result.records if record.explicit_decision]
    if explicit:
        lines.extend(
            f"| `{_md(record.record_id)}` | {record.decision} | {_md(record.curator or '')} | {record.curation_date} | {_md(record.decision_reason)} | {_md(record.allowed_use)} |"
            for record in explicit
        )
    else:
        lines.append("| none | defer | not supplied | not supplied | no explicit decisions supplied | review only |")
    lines.extend(["", "## Proposal Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in result.proposal_limitations)
    return "\n".join(lines) + "\n"


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


def _validate_replaceable_destination(destination: Path) -> None:
    if not destination.exists():
        return
    if not destination.is_dir():
        raise CurationError(f"Curation output path exists and is not a directory: {destination}")
    manifest_path = destination / "curation_manifest.json"
    _reject_symlink_components(manifest_path, label="Existing curation manifest path")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CurationError(
            "Refusing to replace an existing directory without a readable owned curation manifest: "
            f"{destination}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise CurationError(
            f"Refusing to replace existing directory with non-object curation manifest: {destination}"
        )
    if (
        manifest.get("kind") != CURATION_MANIFEST_KIND
        or manifest.get("schema_version") != CURATION_SCHEMA_VERSION
    ):
        raise CurationError(
            "Refusing to replace an existing directory not owned by this curation bundle "
            f"kind/version: {destination}"
        )


def _safe_output_path(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if ".." in path.parts:
        raise CurationError(f"Curation output path traversal is not allowed: {path}")
    _reject_symlink_components(path, label="Curation output path")
    resolved = path.resolve(strict=False)
    registry = (Path(__file__).resolve().parents[3] / "data_registry").resolve(strict=False)
    if resolved == registry or registry in resolved.parents:
        raise CurationError("CURATION-001 decision bundles cannot be written inside data_registry/.")
    return resolved


def _reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise CurationError(f"{label} contains a symlink component: {current}")


def _canonicalize(value: Any, *, field_name: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _canonicalize(value[key], field_name=str(key))
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [_canonicalize(item) for item in value]
        if field_name in _CANONICAL_SCALAR_SEQUENCE_KEYS and all(
            not isinstance(item, (Mapping, list, tuple)) for item in items
        ):
            return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
        return items
    return value


def _required_text(payload: Mapping[str, Any], field: str, *, scope: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CurationError(f"{scope.capitalize()} field {field!r} must be a non-empty string.")
    return value


def _nested_value(record: Mapping[str, Any], field: str) -> Any:
    value: Any = record
    for part in field.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {} or value == ()


def _nonblank_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_string_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "CURATION_DECISION_ALLOWED_USES",
    "CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION",
    "CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY",
    "CURATION_MANIFEST_KIND",
    "CURATION_SCHEMA_VERSION",
    "CurationDecision",
    "CurationError",
    "CurationRecord",
    "CurationResult",
    "CurationWriteResult",
    "review_source_proposal",
]
