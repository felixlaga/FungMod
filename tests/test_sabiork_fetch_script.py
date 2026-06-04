from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sabiork_reaction_618_export_minimal.json"


def test_build_url_uses_required_query_parameters() -> None:
    fetcher = _load_fetcher()

    url = fetcher.build_kinlaw_url(
        base_url=fetcher.BASE_URL,
        endpoint=fetcher.ENDPOINT,
        query="SabioReactionID:618",
        page=1,
        page_size=1000,
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert url.startswith("https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?")
    assert query["q"] == ["SabioReactionID:618"]
    assert query["page"] == ["1"]
    assert query["pageSize"] == ["1000"]


def test_valid_fixture_export_passes_minimal_validation() -> None:
    fetcher = _load_fetcher()
    payload = _fixture_payload()

    fetcher.validate_kinlaw_export(payload, reaction_id="618")


def test_missing_meta_or_data_fails_validation() -> None:
    fetcher = _load_fetcher()

    with pytest.raises(fetcher.SabioRKFetchError, match="meta"):
        fetcher.validate_kinlaw_export({"data": []}, reaction_id="618")
    with pytest.raises(fetcher.SabioRKFetchError, match="data"):
        fetcher.validate_kinlaw_export({"meta": {"total_count": 0}}, reaction_id="618")


def test_reaction_id_mismatch_fails_when_field_is_present() -> None:
    fetcher = _load_fetcher()
    payload = _fixture_payload()
    payload["data"][0]["SabioReactionID"] = "999"

    with pytest.raises(fetcher.SabioRKFetchError, match="SabioReactionID"):
        fetcher.validate_kinlaw_export(payload, reaction_id="618")


def test_nested_reaction_id_is_validated_when_present() -> None:
    fetcher = _load_fetcher()
    payload = _fixture_payload()
    payload["data"] = [
        {
            "id": 123,
            "reaction": {
                "id": 999,
                "equation": "Cellobiose + H2O = 2 beta-D-Glucose",
            },
        }
    ]

    with pytest.raises(fetcher.SabioRKFetchError, match="SabioReactionID"):
        fetcher.validate_kinlaw_export(payload, reaction_id="618")


def test_fetch_metadata_records_warning_for_total_count_drift() -> None:
    fetcher = _load_fetcher()

    metadata = fetcher.build_fetch_metadata(
        base_url=fetcher.BASE_URL,
        endpoint=fetcher.ENDPOINT,
        query="SabioReactionID:618",
        page=1,
        page_size=1000,
        fetched_at="2026-06-04T00:00:00Z",
        http_status=200,
        total_count=2,
        expected_total_count=29,
        total_pages=1,
        requests_made=1,
        urls=("https://example.test/export",),
    )

    assert metadata["pageSize"] == 1000
    assert metadata["total_count"] == 2
    assert metadata["warnings"] == [
        "SABIO-RK total_count differs from the browser count supplied for this milestone: expected 29, got 2."
    ]
    json.dumps(metadata)


def _fixture_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _load_fetcher() -> ModuleType:
    path = ROOT / "scripts" / "fetch_sabiork_kinlaw_entries.py"
    spec = importlib.util.spec_from_file_location("fetch_sabiork_kinlaw_entries", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
