from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn
from urllib.parse import parse_qs, urlparse

import pytest

import fungal_model
from fungal_model import SourceProviderError, source_proposal
from fungal_model.sources.sabiork import PROPOSAL_STATUS, REVIEW_ONLY_ALLOWED_USE
from fungal_model.sources.sabiork.fetch import HTTPResponseSnapshot


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
)
REACTION_618_EXPORT = RAW_DIR / "kinlaw_entries_reaction_618.json"
FETCH_METADATA = RAW_DIR / "fetch_metadata.json"
MINIMAL_EXPORT = ROOT / "tests" / "fixtures" / "sabiork_reaction_618_export_minimal.json"
DATA_REGISTRY = ROOT / "data_registry"


def test_minimal_top_level_sabiork_call_uses_frozen_snapshot_without_key() -> None:
    proposal = source_proposal(provider="sabiork", reaction_id="618", cache_dir=RAW_DIR)

    assert proposal.proposal_status == PROPOSAL_STATUS
    assert proposal.source_query == "SabioReactionID:618"
    assert proposal.source_snapshot_path == str(REACTION_618_EXPORT)
    assert proposal.reaction_records
    assert fungal_model.source_proposal is source_proposal
    assert "source_proposal" in fungal_model.__all__


def test_explicit_refresh_freezes_raw_response_and_metadata_with_fake_transport(
    tmp_path: Path,
) -> None:
    requested_urls: list[str] = []

    def fake_transport(url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
        requested_urls.append(url)
        assert timeout_seconds == 30.0
        return HTTPResponseSnapshot(
            body=MINIMAL_EXPORT.read_text(encoding="utf-8"),
            http_status=200,
            url=url,
        )

    proposal = source_proposal(
        provider="sabiork",
        reaction_id="618",
        refresh=True,
        cache_dir=tmp_path / "snapshots",
        transport=fake_transport,
    )

    raw_dir = tmp_path / "snapshots" / "raw"
    export_path = raw_dir / "kinlaw_entries_reaction_618.json"
    metadata_path = raw_dir / "fetch_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    query = parse_qs(urlparse(requested_urls[0]).query)

    assert export_path.read_text(encoding="utf-8") == MINIMAL_EXPORT.read_text(encoding="utf-8")
    assert metadata["query"] == "SabioReactionID:618"
    assert metadata["http_status"] == 200
    assert metadata["source_urls"] == requested_urls
    assert query["q"] == ["SabioReactionID:618"]
    assert proposal.source_snapshot_path == str(export_path)


@pytest.mark.parametrize(
    ("selector", "expected_query"),
    [
        ({"reaction_id": "618"}, "SabioReactionID:618"),
        ({"ec_number": "3.2.1.21"}, "ECNumber:3.2.1.21"),
        ({"enzyme": "beta-glucosidase"}, "EnzymeName:beta-glucosidase"),
        ({"substrate": "cellobiose"}, "Substrate:cellobiose"),
        ({"organism": "Oryza sativa"}, "Organism:Oryza sativa"),
    ],
)
def test_friendly_fields_derive_sabiork_queries_without_raw_solr(
    tmp_path: Path,
    selector: dict[str, str],
    expected_query: str,
) -> None:
    queries: list[str] = []

    def fake_fetcher(query: str, output_dir: Path) -> tuple[Path, Path]:
        queries.append(query)
        output_dir.mkdir(parents=True, exist_ok=True)
        export_path = output_dir / "kinlaw_entries_fixture.json"
        metadata_path = output_dir / "fetch_metadata.json"
        export_path.write_text(REACTION_618_EXPORT.read_text(encoding="utf-8"), encoding="utf-8")
        metadata_path.write_text(FETCH_METADATA.read_text(encoding="utf-8"), encoding="utf-8")
        return export_path, metadata_path

    proposal = source_proposal(
        provider="sabiork",
        refresh=True,
        cache_dir=tmp_path,
        live_fetcher=fake_fetcher,
        **selector,
    )

    assert queries == [expected_query]
    assert proposal.reaction_records


def test_sabiork_rejects_unused_credential_without_persisting_or_revealing_secret(
    tmp_path: Path,
) -> None:
    secret = "sabiork-secret-that-must-never-persist"

    with pytest.raises(SourceProviderError) as caught:
        source_proposal(
            provider="sabiork",
            reaction_id="618",
            credential=secret,
            refresh=True,
            cache_dir=tmp_path,
        )

    assert secret not in str(caught.value)
    assert secret not in repr(caught.value)
    assert "does not require or accept a credential" in str(caught.value)
    assert list(tmp_path.iterdir()) == []


def test_source_proposal_remains_review_only_and_does_not_mutate_registry(
    tmp_path: Path,
) -> None:
    before = _registry_snapshot()
    proposal = source_proposal(provider="sabiork", reaction_id="618", cache_dir=RAW_DIR)

    write_result = proposal.write(tmp_path / "review_only")
    records = proposal.proposed_records()

    assert proposal.proposal_status == PROPOSAL_STATUS
    assert all(
        record["allowed_use"] == REVIEW_ONLY_ALLOWED_USE
        for record in records["parameter_records"]
    )
    assert all(record["review_required"] is True for record in records["case_templates"])
    assert write_result.paths["proposal_manifest"].exists()
    assert _registry_snapshot() == before


def test_unknown_provider_lists_only_implemented_provider() -> None:
    with pytest.raises(SourceProviderError, match="Available providers: sabiork") as caught:
        source_proposal(provider="brenda", reaction_id="618")

    assert "brenda" in str(caught.value)
    assert "cazy" not in str(caught.value).lower()


def test_source_provider_failures_are_explicit_and_offline(tmp_path: Path) -> None:
    with pytest.raises(SourceProviderError, match="at least one scientific selector"):
        source_proposal(provider="sabiork", cache_dir=tmp_path)

    def failing_fetcher(_query: str, _output_dir: Path) -> NoReturn:
        raise OSError("offline fixture fetch failed")

    with pytest.raises(SourceProviderError, match="offline fixture fetch failed"):
        source_proposal(
            provider="sabiork",
            reaction_id="618",
            refresh=True,
            cache_dir=tmp_path,
            live_fetcher=failing_fetcher,
        )


def _registry_snapshot() -> dict[str, str]:
    return {
        str(path.relative_to(DATA_REGISTRY)): path.read_text(encoding="utf-8")
        for path in sorted(DATA_REGISTRY.rglob("*"))
        if path.is_file()
    }
