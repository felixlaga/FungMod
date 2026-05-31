"""Machine-readable schema checks for future literature datasets.

This module validates metadata shape only. It does not load paper-derived data
and does not encode biological assumptions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fungal_model.core.validators import ValidationResult

LITERATURE_MATURITIES = frozenset({"literature_raw", "literature_processed"})


def validate_literature_dataset_metadata(data: Mapping[str, Any]) -> tuple[ValidationResult, ...]:
    """Validate metadata required before a literature dataset may be added."""

    issues: list[dict[str, Any]] = []
    _require_value(data, "kind", issues)
    if data.get("kind") != "experiment_dataset":
        issues.append(
            {
                "field": "kind",
                "message": "Literature metadata must use kind: experiment_dataset.",
                "value": data.get("kind"),
            }
        )
    maturity = data.get("maturity")
    if maturity not in LITERATURE_MATURITIES:
        issues.append(
            {
                "field": "maturity",
                "message": "Literature datasets must use literature_raw or literature_processed maturity.",
                "value": maturity,
            }
        )

    source = _require_mapping(data, "source", issues)
    if source is not None:
        _require_equal(source, "type", "literature", issues)
        for field in (
            "citation",
            "authors",
            "year",
            "figure_or_table",
            "extraction_method",
            "extraction_tool",
            "extracted_by",
            "extraction_date",
            "raw_units",
            "notes",
        ):
            _require_value(source, field, issues, prefix="source")
        if _is_missing(source.get("doi")) and _is_missing(source.get("url")):
            issues.append(
                {
                    "field": "source.doi_or_url",
                    "message": "At least one of source.doi or source.url is required.",
                }
            )

    measurement_definitions = _require_mapping(data, "measurement_definitions", issues)
    if measurement_definitions is not None:
        for field in (
            "measured_quantity",
            "units",
            "uncertainty_definition",
            "measurement_method",
        ):
            _require_value(measurement_definitions, field, issues, prefix="measurement_definitions")

    preprocessing = _require_mapping(data, "preprocessing", issues)
    if preprocessing is not None:
        for field in ("status", "steps", "unit_conversions", "notes"):
            _require_value(preprocessing, field, issues, prefix="preprocessing")
        _require_value(
            preprocessing,
            "excluded_points",
            issues,
            prefix="preprocessing",
            allow_empty_sequence=True,
        )

    has_digitization = isinstance(data.get("digitization"), Mapping)
    has_table = isinstance(data.get("table"), Mapping)
    has_supplementary = isinstance(data.get("supplementary_data"), Mapping)
    if not (has_digitization or has_table or has_supplementary):
        issues.append(
            {
                "field": "digitization_or_table_or_supplementary_data",
                "message": (
                    "Literature metadata must include digitization, table, or "
                    "supplementary_data provenance."
                ),
            }
        )
    if has_digitization:
        _validate_digitization(data["digitization"], issues)
    if has_table:
        _validate_table(data["table"], issues)
    if has_supplementary:
        _validate_supplementary(data["supplementary_data"], issues)
    if source is not None:
        figure_or_table = str(source.get("figure_or_table", "")).lower()
        if ("figure" in figure_or_table or "fig." in figure_or_table) and not has_digitization:
            issues.append(
                {
                    "field": "digitization",
                    "message": "Figure-derived literature data require digitization metadata.",
                }
            )
        if "table" in figure_or_table and not has_table:
            issues.append(
                {
                    "field": "table",
                    "message": "Table-derived literature data require table metadata.",
                }
            )

    return (
        ValidationResult(
            name="literature_dataset_metadata_schema",
            passed=not issues,
            message=(
                "Literature dataset metadata schema passed."
                if not issues
                else "Literature dataset metadata schema failed."
            ),
            details={"issues": issues},
        ),
    )


def _validate_digitization(data: Any, issues: list[dict[str, Any]]) -> None:
    if not isinstance(data, Mapping):
        issues.append({"field": "digitization", "message": "digitization must be a mapping."})
        return
    for field in (
        "software",
        "axis_calibration",
        "estimated_digitization_error",
        "included_points",
        "exclusion_reason",
    ):
        _require_value(data, field, issues, prefix="digitization")
    _require_value(
        data,
        "excluded_points",
        issues,
        prefix="digitization",
        allow_empty_sequence=True,
    )


def _validate_table(data: Any, issues: list[dict[str, Any]]) -> None:
    if not isinstance(data, Mapping):
        issues.append({"field": "table", "message": "table must be a mapping."})
        return
    for field in ("table_number", "row_definitions", "column_definitions"):
        _require_value(data, field, issues, prefix="table")


def _validate_supplementary(data: Any, issues: list[dict[str, Any]]) -> None:
    if not isinstance(data, Mapping):
        issues.append({"field": "supplementary_data", "message": "supplementary_data must be a mapping."})
        return
    for field in ("file_name", "source_url_or_doi", "checksum", "access_date", "notes"):
        _require_value(data, field, issues, prefix="supplementary_data")


def _require_mapping(
    data: Mapping[str, Any],
    field: str,
    issues: list[dict[str, Any]],
) -> Mapping[str, Any] | None:
    value = data.get(field)
    if not isinstance(value, Mapping):
        issues.append({"field": field, "message": f"{field} must be present as a mapping."})
        return None
    return value


def _require_equal(
    data: Mapping[str, Any],
    field: str,
    expected: str,
    issues: list[dict[str, Any]],
) -> None:
    value = data.get(field)
    if value != expected:
        issues.append(
            {
                "field": f"source.{field}",
                "message": f"Expected source.{field}: {expected}.",
                "value": value,
            }
        )


def _require_value(
    data: Mapping[str, Any],
    field: str,
    issues: list[dict[str, Any]],
    *,
    prefix: str | None = None,
    allow_empty_sequence: bool = False,
) -> None:
    if _is_missing(data.get(field), allow_empty_sequence=allow_empty_sequence):
        issues.append(
            {
                "field": field if prefix is None else f"{prefix}.{field}",
                "message": "Required literature metadata field is missing or empty.",
            }
        )


def _is_missing(value: Any, *, allow_empty_sequence: bool = False) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, Mapping):
        return not value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return False if allow_empty_sequence else len(value) == 0
    return False


__all__ = [
    "LITERATURE_MATURITIES",
    "validate_literature_dataset_metadata",
]
