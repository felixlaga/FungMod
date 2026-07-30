"""Human review and decision bundles for source registry proposals."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import math
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

from fungal_model.api._integrity import (
    first_symlink_component,
    type_exact_equal as _type_exact_equal,
)
from fungal_model.sources.sabiork import PROPOSAL_STATUS, RegistryProposal, stable_sabiork_token


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
_STOICHIOMETRY_RELATIVE_TOLERANCE = 1e-12
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
        "substrates": "nonempty participant sequence with finite positive numeric stoichiometry",
        "products": "nonempty participant sequence with finite positive numeric stoichiometry",
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
_CURATION_RECORD_METADATA_FIELDS = frozenset(
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
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


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


@dataclass(frozen=True)
class LoadedCurationBundle:
    """Checksum-validated structured view of one written curation bundle."""

    output_directory: Path
    manifest_path: Path
    paths: Mapping[str, Path]
    manifest: Mapping[str, Any]
    result: CurationResult
    accepted_records: tuple[CurationRecord, ...]
    proposed_records_payload: Mapping[str, Any]
    accepted_records_payload: Mapping[str, Any]
    rejected_records_payload: Mapping[str, Any]
    eligible_records_csv_payload: Mapping[str, Any]
    excluded_records_csv_payload: Mapping[str, Any]
    curation_report: str


def load_curation_bundle(bundle_or_manifest: str | Path) -> LoadedCurationBundle:
    """Load one owned written curation bundle after complete integrity checks.

    The loader verifies bundle ownership, schema version, the exact artifact
    inventory, every declared SHA-256 checksum, path containment, and the
    deterministic shared curation YAML/CSV/report contracts. These checks prove
    internal bundle consistency only; they do not authenticate a curator,
    promote records, mutate a registry, or authorize simulation.
    """

    return _load_curation_bundle(bundle_or_manifest, validate_shared_semantics=True)


def _load_curation_bundle_for_promotion(
    bundle_or_manifest: str | Path,
) -> LoadedCurationBundle:
    """Load shared integrity data while leaving extension checks to promotion."""

    return _load_curation_bundle(bundle_or_manifest, validate_shared_semantics=False)


def _load_curation_bundle(
    bundle_or_manifest: str | Path,
    *,
    validate_shared_semantics: bool,
) -> LoadedCurationBundle:
    manifest_path = _curation_manifest_path(bundle_or_manifest)
    manifest = _read_json_mapping(manifest_path, label="Curation manifest")
    _validate_loaded_manifest_envelope(manifest)
    root = manifest_path.parent
    paths = _verify_declared_curation_artifacts(root, manifest)

    proposed_payload = _read_yaml_mapping(
        paths["proposed_registry_records.yml"],
        label="Proposed curation records",
    )
    accepted_payload = _read_yaml_mapping(
        paths["accepted_registry_records.yml"],
        label="Accepted curation records",
    )
    rejected_payload = _read_yaml_mapping(
        paths["rejected_registry_records.yml"],
        label="Rejected curation records",
    )
    eligible_csv_payload = _read_curation_csv_payload(
        paths["eligible_records.csv"],
        label="Eligible curation records",
    )
    excluded_csv_payload = _read_curation_csv_payload(
        paths["excluded_records.csv"],
        label="Excluded curation records",
    )
    report = _read_utf8_text(paths["curation_report.md"], label="Curation report")

    result, accepted_records = _curation_result_from_written_payloads(
        manifest=manifest,
        proposed_payload=proposed_payload,
        accepted_payload=accepted_payload,
        rejected_payload=rejected_payload,
        eligible_csv_payload=eligible_csv_payload,
        excluded_csv_payload=excluded_csv_payload,
        report=report,
        validate_shared_semantics=validate_shared_semantics,
    )
    return LoadedCurationBundle(
        output_directory=root,
        manifest_path=manifest_path,
        paths={
            **{_artifact_key(name): path for name, path in paths.items()},
            "curation_manifest": manifest_path,
        },
        manifest=deepcopy(dict(manifest)),
        result=result,
        accepted_records=accepted_records,
        proposed_records_payload=deepcopy(dict(proposed_payload)),
        accepted_records_payload=deepcopy(dict(accepted_payload)),
        rejected_records_payload=deepcopy(dict(rejected_payload)),
        eligible_records_csv_payload=deepcopy(dict(eligible_csv_payload)),
        excluded_records_csv_payload=deepcopy(dict(excluded_csv_payload)),
        curation_report=report,
    )


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
    provenance_missing = curation_source_provenance_missing(provenance)
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


def curation_source_provenance_missing(
    provenance: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return missing fields under the CURATION-001 source-provenance contract."""

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
    if record_type == "product_maps":
        issues.extend(_product_map_consistency_issues(record))
    return issues


def _field_matches_rule(value: Any, rule: str) -> bool:
    if rule == "nonblank text":
        return _nonblank_text(value)
    if rule == "nonempty sequence of nonblank text":
        return _nonempty_string_sequence(value)
    if rule == "nonempty participant sequence with finite positive numeric stoichiometry":
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
    required = ("entry_id", "reaction_id", "role", "compound_name")
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and bool(value)
        and all(
            isinstance(item, Mapping)
            and all(_nonblank_text(item.get(field)) for field in required)
            and _parsed_positive_number(item.get("stoichiometry")) is not None
            for item in value
        )
    )


def _product_map_consistency_issues(record: Mapping[str, Any]) -> list[str]:
    products = record.get("products")
    yields = record.get("stoichiometric_yields")
    if not _participant_sequence(products) or not _positive_numeric_mapping(yields):
        return []
    assert isinstance(products, Sequence) and not isinstance(products, (str, bytes))
    assert isinstance(yields, Mapping)

    aliases_by_index: list[set[str]] = []
    product_values: list[float] = []
    for product in products:
        assert isinstance(product, Mapping)
        aliases = {stable_sabiork_token(product["compound_name"])}
        if _nonblank_text(product.get("compound_id")):
            aliases.add(stable_sabiork_token(product["compound_id"]))
        aliases_by_index.append(aliases)
        parsed = _parsed_positive_number(product["stoichiometry"])
        assert parsed is not None
        product_values.append(parsed)

    matched_products: set[int] = set()
    issues: list[str] = []
    for yield_key, yield_value in yields.items():
        canonical_key = stable_sabiork_token(yield_key)
        matches = [index for index, aliases in enumerate(aliases_by_index) if canonical_key in aliases]
        if len(matches) != 1:
            issues.append(
                f"stoichiometric_yields key {str(yield_key)!r} must match exactly one product participant"
            )
            continue
        index = matches[0]
        if index in matched_products:
            issues.append(
                f"multiple stoichiometric_yields entries match product participant {canonical_key!r}"
            )
            continue
        matched_products.add(index)
        if not math.isclose(
            float(yield_value),
            product_values[index],
            rel_tol=_STOICHIOMETRY_RELATIVE_TOLERANCE,
            abs_tol=0.0,
        ):
            issues.append(
                f"stoichiometric_yields value for {str(yield_key)!r} must match product participant "
                f"stoichiometry {product_values[index]!r}"
            )
    for index, aliases in enumerate(aliases_by_index):
        if index not in matched_products:
            issues.append(
                "product participant has no matching stoichiometric_yields entry: "
                + ", ".join(sorted(aliases))
            )
    return issues


def _parsed_positive_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0.0 else None


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
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        parsed = float(value)
    except (OverflowError, TypeError, ValueError):
        return False
    return math.isfinite(parsed)


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
    if not curation_date_is_iso(decision.curation_date):
        raise CurationError(
            f"Decision for {record_id!r} requires curation_date in YYYY-MM-DD form."
        )
    if not _nonempty_string_sequence(decision.limitations):
        raise CurationError(f"Decision for {record_id!r} requires explicit non-empty limitations.")


def curation_date_is_iso(value: str) -> bool:
    """Return whether a curation date satisfies the CURATION-001 ISO-date rule."""

    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _write_bundle(root: Path, result: CurationResult) -> None:
    paths = _artifact_paths(root)
    _write_csv(paths["eligible_records"], result.eligible_records)
    _write_csv(paths["excluded_records"], result.excluded_records)
    _write_yaml(
        paths["proposed_registry_records"],
        curation_records_payload("proposed", result.records, result),
    )
    _write_yaml(
        paths["accepted_registry_records"],
        curation_records_payload("accepted", result.accepted_records, result),
    )
    _write_yaml(
        paths["rejected_registry_records"],
        curation_records_payload("rejected", result.rejected_records, result),
    )
    paths["curation_report"].write_text(render_curation_report(result), encoding="utf-8")

    checksums = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in paths.items()
        if key != "curation_manifest"
    }
    manifest = curation_manifest_payload(result, checksums)
    paths["curation_manifest"].write_text(
        json.dumps(_canonicalize(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def curation_manifest_payload(
    result: CurationResult,
    checksums: Mapping[str, str],
) -> Mapping[str, Any]:
    """Build the exact deterministic manifest written for a curation result."""

    return {
        "kind": CURATION_MANIFEST_KIND,
        "schema_version": CURATION_SCHEMA_VERSION,
        "source_query": result.source_query,
        "source_snapshot_path": result.source_snapshot_path,
        "proposal_limitations": list(result.proposal_limitations),
        "summary": result.summary(),
        "files": dict(checksums),
        "allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
    }


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


def _artifact_key(filename: str) -> str:
    keys = {
        "curation_report.md": "curation_report",
        "eligible_records.csv": "eligible_records",
        "excluded_records.csv": "excluded_records",
        "proposed_registry_records.yml": "proposed_registry_records",
        "accepted_registry_records.yml": "accepted_registry_records",
        "rejected_registry_records.yml": "rejected_registry_records",
    }
    return keys[filename]


def _curation_manifest_path(value: str | Path) -> Path:
    path = Path(value)
    if ".." in path.parts:
        raise CurationError(f"Curation bundle path traversal is not allowed: {path}")
    _reject_symlink_components(path, label="Curation bundle path")
    manifest = path / "curation_manifest.json" if path.is_dir() else path
    if manifest.name != "curation_manifest.json":
        raise CurationError(
            "Written curation input must be a bundle directory or curation_manifest.json."
        )
    _reject_symlink_components(manifest, label="Curation manifest path")
    if not manifest.is_file():
        raise CurationError(f"Curation manifest does not exist: {manifest}")
    return manifest.resolve(strict=True)


def _validate_loaded_manifest_envelope(manifest: Mapping[str, Any]) -> None:
    if manifest.get("kind") != CURATION_MANIFEST_KIND:
        raise CurationError(
            f"Written input is not an owned curation bundle of kind {CURATION_MANIFEST_KIND!r}."
        )
    if manifest.get("schema_version") != CURATION_SCHEMA_VERSION:
        raise CurationError(
            f"Unsupported curation bundle schema version {manifest.get('schema_version')!r}."
        )
    if manifest.get("allowed_use") != CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY:
        raise CurationError("Curation bundle must remain review-only at bundle level.")
    if manifest.get("production_registry_mutated") is not False:
        raise CurationError("Curation bundle must declare production_registry_mutated: false.")
    if manifest.get("scientific_validation_claimed") is not False:
        raise CurationError("Curation bundle must declare scientific_validation_claimed: false.")


def _verify_declared_curation_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Path]:
    files = manifest.get("files")
    if not isinstance(files, Mapping) or any(not isinstance(name, str) for name in files):
        raise CurationError("Curation manifest requires a string-keyed files checksum mapping.")
    names = set(files)
    if names != _CURATION_BUNDLE_FILES:
        missing = sorted(_CURATION_BUNDLE_FILES - names)
        unexpected = sorted(names - _CURATION_BUNDLE_FILES)
        raise CurationError(
            "Curation manifest artifact set does not match its owned schema; "
            f"missing={missing}, unexpected={unexpected}."
        )

    try:
        actual_names = {path.name for path in root.iterdir()}
    except OSError as exc:
        raise CurationError(f"Cannot inspect curation bundle directory {root}: {exc}") from exc
    expected_names = set(names) | {"curation_manifest.json"}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise CurationError(
            "Curation bundle directory does not match its owned artifact inventory; "
            f"missing={missing}, unexpected={unexpected}."
        )

    declared: dict[str, Path] = {}
    for name in sorted(names):
        digest = files[name]
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise CurationError(
                f"Curation manifest checksum for {name!r} must be a SHA-256 hex digest."
            )
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise CurationError(f"Curation manifest artifact path is unsafe: {name!r}.")
        artifact = root / relative
        _reject_symlink_components(artifact, label="Curation artifact path")
        try:
            resolved = artifact.resolve(strict=True)
        except OSError as exc:
            raise CurationError(f"Declared curation artifact does not exist: {artifact}") from exc
        if resolved.parent != root:
            raise CurationError(
                f"Declared curation artifact resolves outside its bundle: {name!r}."
            )
        if not resolved.is_file():
            raise CurationError(f"Declared curation artifact is not a file: {artifact}")
        try:
            actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as exc:
            raise CurationError(f"Cannot read declared curation artifact: {artifact}") from exc
        if not hmac.compare_digest(actual, digest.lower()):
            raise CurationError(
                f"Curation artifact checksum mismatch for {name!r}: "
                f"expected {digest.lower()}, got {actual}."
            )
        declared[name] = resolved
    return declared


def _curation_result_from_written_payloads(
    *,
    manifest: Mapping[str, Any],
    proposed_payload: Mapping[str, Any],
    accepted_payload: Mapping[str, Any],
    rejected_payload: Mapping[str, Any],
    eligible_csv_payload: Mapping[str, Any],
    excluded_csv_payload: Mapping[str, Any],
    report: str,
    validate_shared_semantics: bool,
) -> tuple[CurationResult, tuple[CurationRecord, ...]]:
    if validate_shared_semantics:
        _validate_loaded_records_envelope(proposed_payload, bundle_status="proposed")
        _validate_loaded_records_envelope(accepted_payload, bundle_status="accepted")
        _validate_loaded_records_envelope(rejected_payload, bundle_status="rejected")

    source_query = _required_text(
        proposed_payload,
        "source_query",
        scope="written curation bundle",
    )
    source_snapshot_path = _required_text(
        proposed_payload,
        "source_snapshot_path",
        scope="written curation bundle",
    )
    proposal_limitations = _loaded_string_sequence(
        proposed_payload.get("proposal_limitations"),
        field="proposal_limitations",
        allow_empty=False,
    )
    record_types = _loaded_record_types(
        eligible_csv_payload,
        excluded_csv_payload,
        validate_schema=validate_shared_semantics,
    )
    raw_records = proposed_payload.get("records")
    if not isinstance(raw_records, list):
        raise CurationError("Proposed curation artifact requires a records list.")

    records: list[CurationRecord] = []
    seen_ids: set[str] = set()
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            raise CurationError(f"Proposed curation record at index {index} must be a mapping.")
        record_id = raw_record.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise CurationError(
                f"Proposed curation record at index {index} requires a non-empty record_id."
            )
        if record_id in seen_ids:
            raise CurationError(f"Proposed curation artifact contains duplicate id {record_id!r}.")
        seen_ids.add(record_id)
        try:
            record_type = record_types[record_id]
        except KeyError as exc:
            raise CurationError(
                f"Proposed curation record {record_id!r} lacks a matching CSV row."
            ) from exc
        records.append(
            _loaded_curation_record(
                raw_record,
                record_type=record_type,
                index=index,
                allow_extra_metadata=not validate_shared_semantics,
            )
        )
    if seen_ids != set(record_types):
        raise CurationError("Proposed curation YAML and eligible/excluded CSV rows do not match.")

    result = CurationResult(
        source_query=source_query,
        source_snapshot_path=source_snapshot_path,
        proposal_limitations=proposal_limitations,
        records=tuple(records),
    )
    accepted_records = (
        result.accepted_records
        if validate_shared_semantics
        else _loaded_records_from_payload(
            accepted_payload,
            record_types=record_types,
            label="Accepted curation artifact",
            allow_extra_metadata=True,
        )
    )
    if not validate_shared_semantics:
        return result, accepted_records

    expected_payloads = {
        "proposed_registry_records.yml": curation_records_payload(
            "proposed",
            result.records,
            result,
        ),
        "accepted_registry_records.yml": curation_records_payload(
            "accepted",
            result.accepted_records,
            result,
        ),
        "rejected_registry_records.yml": curation_records_payload(
            "rejected",
            result.rejected_records,
            result,
        ),
        "eligible_records.csv": curation_records_csv_payload(result.eligible_records),
        "excluded_records.csv": curation_records_csv_payload(result.excluded_records),
    }
    actual_payloads = {
        "proposed_registry_records.yml": proposed_payload,
        "accepted_registry_records.yml": accepted_payload,
        "rejected_registry_records.yml": rejected_payload,
        "eligible_records.csv": eligible_csv_payload,
        "excluded_records.csv": excluded_csv_payload,
    }
    for name, expected in expected_payloads.items():
        if not _type_exact_equal(actual_payloads[name], expected):
            raise CurationError(
                f"Written bundle artifact {name!r} disagrees with the shared "
                "curation builders and reconstructed result."
            )

    files = manifest.get("files")
    assert isinstance(files, Mapping)
    expected_manifest = curation_manifest_payload(result, files)
    if set(manifest) != set(expected_manifest):
        raise CurationError("Curation manifest fields do not match the owned bundle schema.")
    for field, expected in expected_manifest.items():
        if field == "summary":
            continue
        if not _type_exact_equal(manifest.get(field), expected):
            raise CurationError(
                f"Curation manifest field {field!r} disagrees with its reconstructed result."
            )

    summary = manifest.get("summary")
    if not isinstance(summary, Mapping):
        raise CurationError("Curation manifest requires a summary mapping.")
    base_summary = result.summary()
    for field, expected in base_summary.items():
        if field not in summary or not _type_exact_equal(summary[field], expected):
            raise CurationError(
                f"Curation manifest summary field {field!r} disagrees with its artifacts."
            )
    extra_summary_fields = set(summary) - set(base_summary)
    if extra_summary_fields:
        workflow = summary.get("workflow")
        if not isinstance(workflow, str) or not workflow.strip():
            raise CurationError(
                "Extended curation summary fields require an explicit workflow contract."
            )
        validate_curation_report_limitations(report, result.proposal_limitations)
    elif report != render_curation_report(result):
        raise CurationError(
            "Curation report disagrees with the shared deterministic report builder."
        )
    return result, accepted_records


def _validate_loaded_records_envelope(
    payload: Mapping[str, Any],
    *,
    bundle_status: str,
) -> None:
    expected_fields = {
        "kind",
        "schema_version",
        "bundle_status",
        "allowed_use",
        "source_query",
        "source_snapshot_path",
        "proposal_limitations",
        "production_registry_promotion",
        "records",
    }
    if set(payload) != expected_fields:
        raise CurationError(
            f"{bundle_status.capitalize()} curation artifact fields do not match its schema."
        )
    if payload.get("kind") != "fungmod_curation_decision_records":
        raise CurationError(
            f"{bundle_status.capitalize()} curation artifact has an unsupported kind."
        )
    if payload.get("schema_version") != CURATION_SCHEMA_VERSION:
        raise CurationError(
            f"{bundle_status.capitalize()} curation artifact has an unsupported schema version."
        )
    if payload.get("bundle_status") != bundle_status:
        raise CurationError(
            f"{bundle_status.capitalize()} curation artifact must use "
            f"bundle_status: {bundle_status}."
        )
    if payload.get("allowed_use") != CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY:
        raise CurationError(
            f"{bundle_status.capitalize()} curation artifact must remain review-only."
        )
    if payload.get("production_registry_promotion") is not False:
        raise CurationError(
            f"{bundle_status.capitalize()} curation artifact must not claim registry promotion."
        )


def _loaded_record_types(
    eligible_payload: Mapping[str, Any],
    excluded_payload: Mapping[str, Any],
    *,
    validate_schema: bool,
) -> dict[str, str]:
    record_types: dict[str, str] = {}
    for label, payload in (
        ("Eligible", eligible_payload),
        ("Excluded", excluded_payload),
    ):
        if validate_schema and payload.get("fieldnames") != list(_CSV_FIELDS):
            raise CurationError(f"{label}-record CSV header does not match its schema.")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise CurationError(f"{label}-record CSV requires structured rows.")
        for row in rows:
            if not isinstance(row, Mapping):
                raise CurationError(f"{label}-record CSV rows must be mappings.")
            record_id = row.get("record_id")
            record_type = row.get("record_type")
            if not isinstance(record_id, str) or not record_id.strip():
                raise CurationError(f"{label}-record CSV row requires record_id.")
            if not isinstance(record_type, str) or record_type not in _RECORD_TYPES:
                raise CurationError(
                    f"{label}-record CSV row {record_id!r} has unsupported record_type."
                )
            if record_id in record_types:
                raise CurationError(
                    f"Curation CSV artifacts contain duplicate record id {record_id!r}."
                )
            record_types[record_id] = record_type
    return record_types


def _loaded_curation_record(
    raw_record: Mapping[str, Any],
    *,
    record_type: str,
    index: int,
    allow_extra_metadata: bool,
) -> CurationRecord:
    payload = deepcopy(dict(raw_record))
    curation = payload.pop("curation", None)
    record_id = payload.get("record_id")
    assert isinstance(record_id, str)
    _require_string_mapping_keys(payload, label=f"Proposed curation record {record_id!r}")
    if not isinstance(curation, Mapping):
        raise CurationError(f"Proposed curation record {record_id!r} lacks curation metadata.")
    metadata_fields = set(curation)
    if (
        not _CURATION_RECORD_METADATA_FIELDS.issubset(metadata_fields)
        if allow_extra_metadata
        else metadata_fields != _CURATION_RECORD_METADATA_FIELDS
    ):
        raise CurationError(
            f"Proposed curation record {record_id!r} has an unsupported curation envelope."
        )
    if curation.get("schema_version") != CURATION_SCHEMA_VERSION:
        raise CurationError(
            f"Proposed curation record {record_id!r} has an unsupported schema version."
        )
    classification = curation.get("classification")
    if classification not in {"eligible_for_review", "blocked_excluded"}:
        raise CurationError(
            f"Proposed curation record {record_id!r} has an unsupported classification."
        )
    decision = curation.get("decision")
    if decision not in _DECISIONS:
        raise CurationError(
            f"Proposed curation record {record_id!r} has an unsupported decision."
        )
    explicit_decision = curation.get("explicit_decision")
    if type(explicit_decision) is not bool:
        raise CurationError(
            f"Proposed curation record {record_id!r} requires boolean explicit_decision."
        )
    curator = curation.get("curator")
    if curator is not None and not isinstance(curator, str):
        raise CurationError(
            f"Proposed curation record {record_id!r} has invalid curator metadata."
        )
    decision_reason = curation.get("decision_reason")
    curation_date = curation.get("curation_date")
    allowed_use = curation.get("allowed_use")
    if not all(isinstance(value, str) for value in (decision_reason, curation_date, allowed_use)):
        raise CurationError(
            f"Proposed curation record {record_id!r} has invalid decision text metadata."
        )
    assert isinstance(decision_reason, str)
    assert isinstance(curation_date, str)
    assert isinstance(allowed_use, str)
    if allowed_use not in CURATION_DECISION_ALLOWED_USES:
        raise CurationError(
            f"Proposed curation record {record_id!r} has unsupported allowed_use."
        )
    if curation.get("promotion_status") != "not_promoted_to_production_registry":
        raise CurationError(
            f"Proposed curation record {record_id!r} has unsupported promotion status."
        )
    source_provenance = curation.get("source_provenance")
    if not isinstance(source_provenance, Mapping):
        raise CurationError(
            f"Proposed curation record {record_id!r} requires source provenance."
        )
    _require_string_mapping_keys(
        source_provenance,
        label=f"Proposed curation record {record_id!r} source provenance",
    )
    return CurationRecord(
        record_type=record_type,
        record_id=record_id,
        proposed_record=payload,
        classification=classification,
        missing_fields=_loaded_string_sequence(
            curation.get("missing_fields"),
            field=f"records[{index}].curation.missing_fields",
            allow_empty=True,
        ),
        reasons=_loaded_string_sequence(
            curation.get("reasons"),
            field=f"records[{index}].curation.reasons",
            allow_empty=True,
        ),
        decision=decision,
        explicit_decision=explicit_decision,
        curator=curator,
        decision_reason=decision_reason,
        curation_date=curation_date,
        allowed_use=allowed_use,
        limitations=_loaded_string_sequence(
            curation.get("limitations"),
            field=f"records[{index}].curation.limitations",
            allow_empty=False,
        ),
        source_provenance=deepcopy(dict(source_provenance)),
    )


def _loaded_records_from_payload(
    payload: Mapping[str, Any],
    *,
    record_types: Mapping[str, str],
    label: str,
    allow_extra_metadata: bool,
) -> tuple[CurationRecord, ...]:
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise CurationError(f"{label} requires a records list.")
    records: list[CurationRecord] = []
    seen_ids: set[str] = set()
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            raise CurationError(f"{label} record at index {index} must be a mapping.")
        record_id = raw_record.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise CurationError(f"{label} record at index {index} requires record_id.")
        if record_id in seen_ids:
            raise CurationError(f"{label} contains duplicate record id {record_id!r}.")
        seen_ids.add(record_id)
        try:
            record_type = record_types[record_id]
        except KeyError as exc:
            raise CurationError(
                f"{label} record {record_id!r} lacks a matching CSV row."
            ) from exc
        records.append(
            _loaded_curation_record(
                raw_record,
                record_type=record_type,
                index=index,
                allow_extra_metadata=allow_extra_metadata,
            )
        )
    return tuple(records)


def _loaded_string_sequence(
    value: Any,
    *,
    field: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        qualifier = "a string sequence" if allow_empty else "a non-empty string sequence"
        raise CurationError(f"Written curation field {field!r} must be {qualifier}.")
    return tuple(value)


def _read_json_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CurationError(f"Malformed {label.lower()} {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CurationError(f"{label} {path} must contain a JSON object.")
    return payload


def _read_yaml_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CurationError(f"Malformed {label.lower()} {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CurationError(f"{label} {path} must contain a YAML mapping.")
    return payload


def _read_curation_csv_payload(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
            fieldnames = list(reader.fieldnames or ())
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CurationError(f"Malformed {label.lower()} CSV {path}: {exc}") from exc
    return {"fieldnames": fieldnames, "rows": rows}


def _read_utf8_text(path: Path, *, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CurationError(f"Malformed {label.lower()} {path}: {exc}") from exc


def _require_string_mapping_keys(value: Any, *, label: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CurationError(f"{label} contains a non-string mapping key.")
            _require_string_mapping_keys(item, label=label)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _require_string_mapping_keys(item, label=label)


def curation_records_payload(
    bundle_status: str,
    records: Sequence[CurationRecord],
    result: CurationResult,
) -> Mapping[str, Any]:
    """Build one exact deterministic decision-record payload."""

    return {
        "kind": "fungmod_curation_decision_records",
        "schema_version": CURATION_SCHEMA_VERSION,
        "bundle_status": bundle_status,
        "allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "source_query": result.source_query,
        "source_snapshot_path": result.source_snapshot_path,
        "proposal_limitations": list(result.proposal_limitations),
        "production_registry_promotion": False,
        "records": [record.to_dict() for record in records],
    }


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(yaml.safe_dump(_canonicalize(payload), sort_keys=False), encoding="utf-8")


def _write_csv(path: Path, records: Sequence[CurationRecord]) -> None:
    path.write_text(render_curation_records_csv(records), encoding="utf-8")


def render_curation_records_csv(records: Sequence[CurationRecord]) -> str:
    """Render one deterministic eligible/excluded decision table."""

    payload = curation_records_csv_payload(records)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=payload["fieldnames"])
    writer.writeheader()
    writer.writerows(payload["rows"])
    return output.getvalue()


def curation_records_csv_payload(records: Sequence[CurationRecord]) -> Mapping[str, Any]:
    """Build the exact header and rows for one curation decision table."""

    rows = []
    for record in records:
        provenance = record.source_provenance
        rows.append(
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
    return {"fieldnames": list(_CSV_FIELDS), "rows": rows}


def render_curation_report(result: CurationResult) -> str:
    """Render the deterministic human-readable report for a curation result."""

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


def validate_curation_report_limitations(
    report_text: str,
    proposal_limitations: Sequence[str],
) -> None:
    """Require the deterministic report's final limitations section to match exactly."""

    if not isinstance(report_text, str) or not _nonempty_string_sequence(proposal_limitations):
        raise CurationError("Curation report and proposal limitations must be explicit text.")
    expected = "## Proposal Limitations\n\n" + "\n".join(
        f"- {limitation}" for limitation in proposal_limitations
    ) + "\n"
    if not report_text.endswith(expected):
        raise CurationError(
            "Curation report proposal limitations disagree with the machine-readable bundle envelope."
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
    symlink = first_symlink_component(path)
    if symlink is not None:
        raise CurationError(f"{label} contains a symlink component: {symlink}")


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
    "LoadedCurationBundle",
    "curation_manifest_payload",
    "curation_records_csv_payload",
    "curation_records_payload",
    "load_curation_bundle",
    "render_curation_records_csv",
    "render_curation_report",
    "review_source_proposal",
    "validate_curation_report_limitations",
]
