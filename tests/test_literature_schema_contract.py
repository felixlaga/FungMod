from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import yaml

from fungal_model.data import validate_literature_dataset_metadata


ROOT = Path(__file__).resolve().parents[1]
LITERATURE_DIR = ROOT / "data" / "experiments" / "literature"
FAKE_SCHEMA_EXAMPLE = (
    ROOT
    / "data"
    / "experiments"
    / "literature_schema_examples"
    / "fake_literature_dataset.yml"
)


def test_literature_schema_contract_exists_before_real_data() -> None:
    readme = (LITERATURE_DIR / "README.md").read_text(encoding="utf-8")

    required_terms = (
        "citation",
        "DOI or URL",
        "authors",
        "year",
        "figure or table",
        "extraction method",
        "extracted_by",
        "extraction_date",
        "raw units",
        "digitization metadata",
        "table metadata",
        "unit-conversion notes",
        "excluded points",
        "preprocessing steps",
        "preprocessing notes",
        "literature_raw",
        "literature_processed",
        "machine-readable schema",
        "fake examples are schema tests only",
    )
    for term in required_terms:
        assert term in readme
    assert "No real literature data are included yet" in readme


def test_literature_directory_contains_no_real_data_yet() -> None:
    data_files = [
        path
        for path in LITERATURE_DIR.rglob("*")
        if path.is_file() and path.name != "README.md"
    ]

    assert data_files == []


def test_valid_fake_literature_metadata_passes_schema() -> None:
    result = validate_literature_dataset_metadata(_fake_metadata())[0]

    assert result.passed


def test_missing_citation_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["source"]["citation"] = ""

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "source.citation")


def test_missing_doi_and_url_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["source"]["doi"] = None
    data["source"]["url"] = None

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "source.doi_or_url")


def test_missing_authors_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["source"]["authors"] = []

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "source.authors")


def test_missing_year_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["source"]["year"] = None

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "source.year")


def test_missing_extraction_method_or_tool_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["source"]["extraction_method"] = ""
    data["source"]["extraction_tool"] = ""

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "source.extraction_method")
    assert _has_issue(result.details["issues"], "source.extraction_tool")


def test_missing_raw_units_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["source"]["raw_units"] = {}

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "source.raw_units")


def test_missing_uncertainty_definition_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["measurement_definitions"]["uncertainty_definition"] = None

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "measurement_definitions.uncertainty_definition")


def test_missing_preprocessing_notes_fails_literature_schema() -> None:
    data = _fake_metadata()
    data["preprocessing"]["notes"] = ""

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "preprocessing.notes")


def test_missing_digitization_table_and_supplementary_data_fails_literature_schema() -> None:
    data = _fake_metadata()
    data.pop("digitization")

    result = validate_literature_dataset_metadata(data)[0]

    assert _has_issue(result.details["issues"], "digitization_or_table_or_supplementary_data")
    assert _has_issue(result.details["issues"], "digitization")


def test_fake_schema_examples_are_not_real_literature_datasets() -> None:
    data = _fake_metadata()

    assert "fake" in str(data["notes"]).lower()
    assert LITERATURE_DIR not in FAKE_SCHEMA_EXAMPLE.parents


def _fake_metadata() -> dict[str, Any]:
    data = yaml.safe_load(FAKE_SCHEMA_EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return deepcopy(cast(dict[str, Any], data))


def _has_issue(issues: list[dict[str, Any]], field: str) -> bool:
    return any(issue["field"] == field for issue in issues)
