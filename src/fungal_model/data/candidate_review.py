"""Schema-first candidate reviews before adding real datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import yaml

from fungal_model.core.validators import ValidationResult
from fungal_model.data.datasets import ALLOWED_DATASET_MATURITIES

CANDIDATE_REVIEW_KIND = "dataset_candidate_review"
CANDIDATE_REVIEW_STATUSES = frozenset(
    {
        "proposed",
        "selected_for_schema_review",
        "rejected",
        "approved_for_ingestion",
    }
)
CANDIDATE_SOURCE_TYPES = frozenset({"literature", "synthetic", "internal_test", "unknown"})
FORBIDDEN_DATA_FIELDS = frozenset(
    {
        "measurements",
        "measurement_series",
        "observations",
        "data_file",
        "csv_path",
        "csv_files",
        "data_rows",
    }
)
REQUIRED_SCHEMA_GATE_FLAGS = (
    "requires_units",
    "requires_uncertainty",
    "requires_preprocessing",
    "requires_no_real_data_in_review",
)


class DatasetCandidateReviewLoadError(ValueError):
    """Raised when a dataset candidate review file is invalid."""


@dataclass(frozen=True)
class DatasetCandidateReview:
    """Review metadata for a possible future dataset before data insertion."""

    candidate_id: str
    name: str
    status: str
    dataset_maturity: str
    source: Mapping[str, Any]
    intended_use: Mapping[str, Any]
    schema_gate: Mapping[str, Any]
    review: Mapping[str, Any]
    notes: str
    raw: Mapping[str, Any]
    path: Path | None = None

    def validate(self) -> ValidationResult:
        return validate_dataset_candidate_review(self.raw)[0]

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(self.raw)


def load_dataset_candidate_review(path: str | Path) -> DatasetCandidateReview:
    """Load and validate a schema-first dataset candidate review."""

    review_path = Path(path)
    data = _load_yaml_mapping(review_path)
    validation = validate_dataset_candidate_review(data)[0]
    if not validation.passed:
        raise DatasetCandidateReviewLoadError(
            f"Dataset candidate review {review_path} failed validation: {validation.details}"
        )
    return DatasetCandidateReview(
        candidate_id=str(data["candidate_id"]),
        name=str(data["name"]),
        status=str(data["status"]),
        dataset_maturity=str(data["dataset_maturity"]),
        source=cast(Mapping[str, Any], data["source"]),
        intended_use=cast(Mapping[str, Any], data["intended_use"]),
        schema_gate=cast(Mapping[str, Any], data["schema_gate"]),
        review=cast(Mapping[str, Any], data["review"]),
        notes=str(data["notes"]),
        raw=dict(data),
        path=review_path,
    )


def validate_dataset_candidate_review(data: Mapping[str, Any]) -> tuple[ValidationResult, ...]:
    """Validate a proposed dataset candidate before any observations are added."""

    issues: list[dict[str, Any]] = []
    _reject_forbidden_data_fields(data, issues)
    _require_equal(data, "kind", CANDIDATE_REVIEW_KIND, issues)
    for field in ("candidate_id", "name", "status", "dataset_maturity", "notes"):
        _require_value(data, field, issues)

    status = data.get("status")
    if status is not None and status not in CANDIDATE_REVIEW_STATUSES:
        issues.append(
            {
                "field": "status",
                "message": "Dataset candidate review status is not supported.",
                "allowed": sorted(CANDIDATE_REVIEW_STATUSES),
                "value": status,
            }
        )

    maturity = data.get("dataset_maturity")
    if maturity is not None and maturity not in ALLOWED_DATASET_MATURITIES:
        issues.append(
            {
                "field": "dataset_maturity",
                "message": "Dataset candidate maturity is not supported.",
                "allowed": sorted(ALLOWED_DATASET_MATURITIES),
                "value": maturity,
            }
        )

    source = _require_mapping(data, "source", issues)
    if source is not None:
        _validate_source(source, issues)

    intended_use = _require_mapping(data, "intended_use", issues)
    if intended_use is not None:
        _validate_intended_use(intended_use, issues)

    schema_gate = _require_mapping(data, "schema_gate", issues)
    if schema_gate is not None:
        _validate_schema_gate(schema_gate, source, issues)

    review = _require_mapping(data, "review", issues)
    if review is not None:
        for field in ("selected_by", "review_date", "decision_notes"):
            _require_value(review, field, issues, prefix="review")
        if status == "approved_for_ingestion" and review.get("schema_result") != "passed":
            issues.append(
                {
                    "field": "review.schema_result",
                    "message": "approved_for_ingestion requires review.schema_result: passed.",
                }
            )

    return (
        ValidationResult(
            name="dataset_candidate_review_schema",
            passed=not issues,
            message=(
                "Dataset candidate review schema passed."
                if not issues
                else "Dataset candidate review schema failed."
            ),
            details={"issues": issues},
        ),
    )


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise DatasetCandidateReviewLoadError(f"Dataset candidate review does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise DatasetCandidateReviewLoadError(f"Dataset candidate review YAML must be a mapping: {path}")
    return cast(Mapping[str, Any], data)


def _validate_source(source: Mapping[str, Any], issues: list[dict[str, Any]]) -> None:
    source_type = source.get("type")
    _require_value(source, "type", issues, prefix="source")
    if source_type is not None and source_type not in CANDIDATE_SOURCE_TYPES:
        issues.append(
            {
                "field": "source.type",
                "message": "Dataset candidate source type is not supported.",
                "allowed": sorted(CANDIDATE_SOURCE_TYPES),
                "value": source_type,
            }
        )
    _require_value(source, "notes", issues, prefix="source")
    if source_type == "literature":
        for field in ("citation", "authors", "year"):
            _require_value(source, field, issues, prefix="source")
        if _is_missing(source.get("doi")) and _is_missing(source.get("url")):
            issues.append(
                {
                    "field": "source.doi_or_url",
                    "message": "Literature candidates require at least one of source.doi or source.url.",
                }
            )


def _validate_intended_use(intended_use: Mapping[str, Any], issues: list[dict[str, Any]]) -> None:
    for field in ("purpose", "measured_quantities", "model_targets", "not_for"):
        _require_value(intended_use, field, issues, prefix="intended_use")


def _validate_schema_gate(
    schema_gate: Mapping[str, Any],
    source: Mapping[str, Any] | None,
    issues: list[dict[str, Any]],
) -> None:
    for flag in REQUIRED_SCHEMA_GATE_FLAGS:
        if schema_gate.get(flag) is not True:
            issues.append(
                {
                    "field": f"schema_gate.{flag}",
                    "message": "Dataset candidate schema-gate flags must be explicitly true.",
                    "value": schema_gate.get(flag),
                }
            )
    if source is not None and source.get("type") == "literature":
        if schema_gate.get("requires_literature_schema") is not True:
            issues.append(
                {
                    "field": "schema_gate.requires_literature_schema",
                    "message": "Literature candidates must require literature schema validation.",
                    "value": schema_gate.get("requires_literature_schema"),
                }
            )


def _reject_forbidden_data_fields(data: Mapping[str, Any], issues: list[dict[str, Any]]) -> None:
    for field in sorted(FORBIDDEN_DATA_FIELDS.intersection(data)):
        issues.append(
            {
                "field": field,
                "message": (
                    "Dataset candidate reviews must not contain observations, "
                    "measurement series, CSV paths, or data rows."
                ),
            }
        )


def _require_mapping(
    data: Mapping[str, Any],
    field: str,
    issues: list[dict[str, Any]],
) -> Mapping[str, Any] | None:
    value = data.get(field)
    if not isinstance(value, Mapping):
        issues.append({"field": field, "message": f"{field} must be present as a mapping."})
        return None
    return cast(Mapping[str, Any], value)


def _require_equal(data: Mapping[str, Any], field: str, expected: str, issues: list[dict[str, Any]]) -> None:
    value = data.get(field)
    if value != expected:
        issues.append({"field": field, "message": f"Expected {field}: {expected}.", "value": value})


def _require_value(
    data: Mapping[str, Any],
    field: str,
    issues: list[dict[str, Any]],
    *,
    prefix: str | None = None,
) -> None:
    if _is_missing(data.get(field)):
        issues.append(
            {
                "field": field if prefix is None else f"{prefix}.{field}",
                "message": "Required dataset candidate review field is missing or empty.",
            }
        )


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, Mapping):
        return not value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value) == 0
    return False


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    return value


__all__ = [
    "CANDIDATE_REVIEW_KIND",
    "CANDIDATE_REVIEW_STATUSES",
    "DatasetCandidateReview",
    "DatasetCandidateReviewLoadError",
    "load_dataset_candidate_review",
    "validate_dataset_candidate_review",
]
