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


def test_literature_schema_contract_documents_real_data_requirements() -> None:
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
    assert "Current datasets" in readme


REVIEWED_SOURCES = {
    "alvarez_gonzalez_2022_free_beta_glucosidase": [
        "alvarez_gonzalez_2022_figure_s1a_filled_squares.csv",
        "alvarez_gonzalez_2022_figure_s1a_open_squares.csv",
        "alvarez_gonzalez_2022_figure_s1a_open_squares.yml",
        "alvarez_gonzalez_2022_figure_s1b_filled_squares.csv",
        "alvarez_gonzalez_2022_figure_s1b_filled_squares.yml",
        "alvarez_gonzalez_2022_figure_s1b_open_squares.csv",
        "alvarez_gonzalez_2022_figure_s1b_open_squares.yml",
        "alvarez_gonzalez_2022_free_beta_glucosidase.yml",
    ],
    "ariaeenejad_2020_persibgl1_cellobiose": [
        "ariaeenejad_2020_figure_6_glucose.csv",
        "ariaeenejad_2020_persibgl1_cellobiose.yml",
    ],
    "cao_2015_bgl6_cellobiose": [
        "cao_2015_figure_5a_bgl6.csv",
        "cao_2015_figure_5a_bgl6.yml",
        "cao_2015_figure_5a_m3.csv",
        "cao_2015_figure_5a_m3.yml",
    ],
}


def test_literature_directory_contains_only_reviewed_dataset_files() -> None:
    """Each literature source directory must hold exactly its reviewed files."""

    directories = sorted(p.name for p in LITERATURE_DIR.iterdir() if p.is_dir())

    assert directories == sorted(REVIEWED_SOURCES)
    for name, expected in REVIEWED_SOURCES.items():
        found = sorted(
            path.name
            for path in (LITERATURE_DIR / name).rglob("*")
            if path.is_file() and path.name != "README.md"
        )
        assert found == sorted(expected), name

    stray = [p.name for p in LITERATURE_DIR.iterdir() if p.is_file() and p.name != "README.md"]
    assert stray == [], f"Unreviewed files at the literature root: {stray}"


def test_every_literature_dataset_file_passes_the_schema() -> None:
    """No literature dataset may sit in the directory without passing the gate."""

    dataset_files = sorted(LITERATURE_DIR.rglob("*.yml"))

    assert dataset_files, "Expected at least one literature dataset."
    for path in dataset_files:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        result = validate_literature_dataset_metadata(data)[0]
        assert result.passed, f"{path.name} failed the literature schema: {result.details['issues']}"


def test_held_out_series_record_their_shared_source_and_unresolved_units() -> None:
    """The held-out series must not be presented as independent replication."""

    held_out = {
        "alvarez_gonzalez_2022_figure_s1a_open_squares.yml": False,
        "alvarez_gonzalez_2022_figure_s1b_filled_squares.yml": True,
        "alvarez_gonzalez_2022_figure_s1b_open_squares.yml": True,
    }
    for name, expects_unit_conflict in held_out.items():
        data = yaml.safe_load((LITERATURE_DIR / "alvarez_gonzalez_2022_free_beta_glucosidase" / name).read_text(encoding="utf-8"))
        assert "not independent experimental replication" in data["source"]["notes"]
        assert data["maturity"] == "literature_raw"
        if expects_unit_conflict:
            # The panel-B caption prints mg/mL where panel A prints mg/L. The
            # record must preserve the printed value rather than silently fixing it.
            assert "UNRESOLVED SOURCE INCONSISTENCY" in data["conditions"]["notes"]
            assert data["conditions"]["free_enzyme_concentration_as_printed"]["units"] == (
                "milligram / milliliter"
            )


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
