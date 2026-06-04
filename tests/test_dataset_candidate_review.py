from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.data import (
    DatasetCandidateReview,
    DatasetCandidateReviewLoadError,
    load_dataset_candidate_review,
    validate_dataset_candidate_review,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = ROOT / "data" / "experiments" / "candidate_reviews"
FAKE_CANDIDATE = CANDIDATE_DIR / "fake_candidate_review.yml"
RESA_BUCKIN_CANDIDATE = CANDIDATE_DIR / "resa_buckin_2011_cellobiose_hydrolysis_review.yml"
LITERATURE_DIR = ROOT / "data" / "experiments" / "literature"


def test_valid_fake_candidate_review_loads() -> None:
    review = load_dataset_candidate_review(FAKE_CANDIDATE)

    assert isinstance(review, DatasetCandidateReview)
    assert review.candidate_id == "fake_schema_candidate_only"
    assert review.status == "proposed"
    assert review.dataset_maturity == "literature_raw"
    assert review.validate().passed


def test_candidate_review_to_dict_is_json_safe() -> None:
    review = load_dataset_candidate_review(FAKE_CANDIDATE)

    encoded = json.dumps(review.to_dict())

    assert "fake_schema_candidate_only" in encoded
    assert "schema-test-only" in encoded


def test_real_time_course_candidate_review_loads_without_observations() -> None:
    review = load_dataset_candidate_review(RESA_BUCKIN_CANDIDATE)

    assert review.candidate_id == "resa_buckin_2011_cellobiose_hydrolysis"
    assert review.status == "selected_for_schema_review"
    assert review.dataset_maturity == "literature_raw"
    assert review.source["doi"] == "10.1016/j.ab.2011.03.003"
    assert review.review["schema_result"] == "blocked_missing_extraction_metadata"
    assert "glucose released over time" in review.intended_use["measured_quantities"]
    assert "beta_D_glucose_concentration" in review.intended_use["model_targets"]
    assert review.schema_gate["requires_no_real_data_in_review"] is True
    assert "observations" not in review.raw
    assert "measurements" not in review.raw
    assert "csv_path" not in review.raw
    assert review.validate().passed


def test_real_time_course_candidate_schema_review_blocks_ingestion_until_extracted() -> None:
    review = load_dataset_candidate_review(RESA_BUCKIN_CANDIDATE)
    schema_review = review.raw["schema_review"]

    assert schema_review["decision"] == "blocked_do_not_ingest"
    assert "figure_or_table identifier for extractable observations" in schema_review[
        "missing_for_experiment_dataset"
    ]
    assert "machine-readable observation CSV" in schema_review["missing_for_experiment_dataset"]
    assert "full text or supplementary data" in schema_review["next_action"]
    assert "observations" not in schema_review
    assert "measurements" not in schema_review


def test_missing_kind_fails_candidate_review_schema() -> None:
    data = _fake_candidate_data()
    data.pop("kind")

    result = validate_dataset_candidate_review(data)[0]

    assert _has_issue(result.details["issues"], "kind")


def test_invalid_status_fails_candidate_review_schema() -> None:
    data = _fake_candidate_data()
    data["status"] = "just_add_it"

    result = validate_dataset_candidate_review(data)[0]

    assert _has_issue(result.details["issues"], "status")


def test_literature_candidate_missing_citation_fails() -> None:
    data = _fake_candidate_data()
    data["source"]["citation"] = ""

    result = validate_dataset_candidate_review(data)[0]

    assert _has_issue(result.details["issues"], "source.citation")


def test_literature_candidate_missing_doi_and_url_fails() -> None:
    data = _fake_candidate_data()
    data["source"]["doi"] = None
    data["source"]["url"] = None

    result = validate_dataset_candidate_review(data)[0]

    assert _has_issue(result.details["issues"], "source.doi_or_url")


def test_missing_intended_use_fails() -> None:
    data = _fake_candidate_data()
    data["intended_use"] = {}

    result = validate_dataset_candidate_review(data)[0]

    assert _has_issue(result.details["issues"], "intended_use.purpose")
    assert _has_issue(result.details["issues"], "intended_use.not_for")


def test_candidate_review_rejects_embedded_measurement_data(tmp_path: Path) -> None:
    data = _fake_candidate_data()
    data["measurements"] = [{"data_file": "not_allowed.csv"}]
    path = tmp_path / "bad_candidate.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(DatasetCandidateReviewLoadError, match="measurements"):
        load_dataset_candidate_review(path)


def test_candidate_review_requires_no_real_data_schema_gate() -> None:
    data = _fake_candidate_data()
    data["schema_gate"]["requires_no_real_data_in_review"] = False

    result = validate_dataset_candidate_review(data)[0]

    assert _has_issue(result.details["issues"], "schema_gate.requires_no_real_data_in_review")


def test_candidate_review_directory_contains_only_review_files() -> None:
    files = sorted(path.name for path in CANDIDATE_DIR.iterdir() if path.is_file())

    assert files == [
        "README.md",
        "fake_candidate_review.yml",
        "resa_buckin_2011_cellobiose_hydrolysis_review.yml",
    ]


def test_literature_directory_still_contains_no_real_data_files() -> None:
    data_files = [
        path
        for path in LITERATURE_DIR.rglob("*")
        if path.is_file() and path.name != "README.md"
    ]

    assert data_files == []


def _fake_candidate_data() -> dict[str, Any]:
    data = yaml.safe_load(FAKE_CANDIDATE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return deepcopy(cast(dict[str, Any], data))


def _has_issue(issues: list[dict[str, Any]], field: str) -> bool:
    return any(issue["field"] == field for issue in issues)
