from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qs, urlparse

import pytest

from fungal_model.sources.sabiork import fetch as sabiork_fetch


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


def test_cli_labels_derived_export_without_raw_mislabel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fetcher = _load_fetcher()
    bundle_dir = tmp_path / "query" / "snapshot"
    export_path = bundle_dir / "derived" / "combined_export.json"
    metadata_path = bundle_dir / "fetch_metadata.json"

    def fake_fetch_and_save_export(**_kwargs: object) -> tuple[Path, Path]:
        return export_path, metadata_path

    monkeypatch.setattr(fetcher, "fetch_and_save_export", fake_fetch_and_save_export)

    result = fetcher.main(
        [
            "--query",
            "SabioReactionID:618",
            "--output-dir",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert f"Saved derived combined export: {export_path}" in output
    assert f"Saved snapshot bundle: {bundle_dir}" in output
    assert f"Saved raw pages: {bundle_dir / 'raw'}" in output
    assert f"Saved fetch metadata: {metadata_path}" in output
    assert "Saved raw export:" not in output


def test_paginated_fetch_preserves_each_raw_body_and_writes_derived_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = _load_fetcher()
    page_bodies = {
        1: json.dumps(
            {
                "meta": {"page": 1, "page_size": 1, "total_count": 2, "total_pages": 2},
                "data": [{"EntryID": "1", "SabioReactionID": "618"}],
            },
            separators=(",", ":"),
        ),
        2: json.dumps(
            {
                "meta": {"page": 2, "page_size": 1, "total_count": 2, "total_pages": 2},
                "data": [{"EntryID": "2", "SabioReactionID": "618"}],
            },
            indent=2,
        ),
    }

    def fake_transport(url: str, *, timeout_seconds: float) -> object:
        assert timeout_seconds == 30.0
        page = int(parse_qs(urlparse(url).query)["page"][0])
        return fetcher.HTTPResponseSnapshot(body=page_bodies[page], http_status=200, url=url)

    monkeypatch.setattr(sabiork_fetch, "MIN_REQUEST_INTERVAL_SECONDS", 0.0)
    export_path, metadata_path = fetcher.fetch_and_save_export(
        query="SabioReactionID:618",
        output_dir=tmp_path,
        page_size=1,
        expected_total_count=None,
        transport=fake_transport,
    )

    bundle_dir = export_path.parent.parent
    raw_page_1 = bundle_dir / "raw" / "page_0001.json"
    raw_page_2 = bundle_dir / "raw" / "page_0002.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    derived = json.loads(export_path.read_text(encoding="utf-8"))

    assert export_path == bundle_dir / "derived" / "combined_export.json"
    assert raw_page_1.read_text(encoding="utf-8") == page_bodies[1]
    assert raw_page_2.read_text(encoding="utf-8") == page_bodies[2]
    assert [row["EntryID"] for row in derived["data"]] == ["1", "2"]
    assert derived["meta"]["combined_from_pages"] is True
    assert derived["meta"]["raw_pages_preserved"] is True
    assert [page["path"] for page in metadata["raw_pages"]] == [
        "raw/page_0001.json",
        "raw/page_0002.json",
    ]
    assert metadata["raw_pages"][0]["sha256"] == hashlib.sha256(page_bodies[1].encode()).hexdigest()
    assert metadata["raw_pages"][1]["sha256"] == hashlib.sha256(page_bodies[2].encode()).hexdigest()
    assert metadata["derived_export"]["artifact_role"] == "derived_combined_export"
    assert metadata["derived_export"]["source_page_count"] == 2
    assert metadata["derived_export"]["sha256"] == hashlib.sha256(export_path.read_bytes()).hexdigest()


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
