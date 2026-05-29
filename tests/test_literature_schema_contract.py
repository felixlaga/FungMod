from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LITERATURE_DIR = ROOT / "data" / "experiments" / "literature"


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
