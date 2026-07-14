from __future__ import annotations

import inspect
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

import fungal_model
from fungal_model import SourceProviderError, source_proposal
from fungal_model.sources.sabiork import (
    PROPOSAL_STATUS,
    REVIEW_ONLY_ALLOWED_USE,
    SabioRKSource,
    frozen_source_urls,
)
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
MINIMAL_EXPORT = ROOT / "tests" / "fixtures" / "sabiork_reaction_618_export_minimal.json"
DATA_REGISTRY = ROOT / "data_registry"
REACTION_618_SOURCE_URL = (
    "https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?"
    "q=SabioReactionID%3A618&page=1&pageSize=1000"
)


def test_minimal_top_level_sabiork_call_uses_frozen_snapshot_without_key() -> None:
    proposal = source_proposal(provider="sabiork", reaction_id="618", cache_dir=RAW_DIR)

    assert proposal.proposal_status == PROPOSAL_STATUS
    assert proposal.source_query == "SabioReactionID:618"
    assert proposal.source_snapshot_path == str(REACTION_618_EXPORT)
    assert proposal.reaction_records
    parameter = next(
        item
        for item in proposal.proposed_records()["parameter_records"]
        if item["record_id"] == "proposed_sabiork_parameter_618_35622_kcat_cellobiose"
    )
    assert parameter["provenance"]["source_url"] == REACTION_618_SOURCE_URL
    assert parameter["provenance"]["source_urls"] == [REACTION_618_SOURCE_URL]
    assert frozen_source_urls(proposal.source_snapshot_path) == (REACTION_618_SOURCE_URL,)
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

    export_path = Path(proposal.source_snapshot_path)
    bundle_dir = export_path.parent.parent
    raw_path = bundle_dir / "raw" / "page_0001.json"
    metadata_path = bundle_dir / "fetch_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    query = parse_qs(urlparse(requested_urls[0]).query)

    assert export_path.name == "combined_export.json"
    assert raw_path.read_text(encoding="utf-8") == MINIMAL_EXPORT.read_text(encoding="utf-8")
    assert metadata["query"] == "SabioReactionID:618"
    assert metadata["http_status"] == 200
    assert metadata["source_urls"] == requested_urls
    assert metadata["immutable_snapshot_bundle"] is True
    assert metadata["raw_pages"][0]["path"] == "raw/page_0001.json"
    assert metadata["derived_export"]["path"] == "derived/combined_export.json"
    assert "credential" not in json.dumps(metadata).lower()
    assert "credential" not in json.dumps(proposal.to_dict()).lower()
    assert query["q"] == ["SabioReactionID:618"]
    assert proposal.source_snapshot_path == str(export_path)


@pytest.mark.parametrize(
    ("selector", "expected_query"),
    [
        ({"reaction_id": "618"}, "SabioReactionID:618"),
        ({"entry_id": "35622"}, "EntryID:35622"),
        ({"ec_number": "3.2.1.21"}, 'ECNumber:"3.2.1.21"'),
        ({"enzyme": "beta-glucosidase"}, 'Enzymename:"beta-glucosidase"'),
        ({"substrate": "cellobiose"}, 'Substrate:"cellobiose"'),
        ({"organism": "Oryza sativa"}, 'Organism:"Oryza sativa"'),
    ],
)
def test_friendly_fields_derive_sabiork_queries_without_raw_solr(
    tmp_path: Path,
    selector: dict[str, str],
    expected_query: str,
) -> None:
    queries: list[str] = []

    def fake_transport(url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
        assert timeout_seconds == 30.0
        queries.extend(parse_qs(urlparse(url).query)["q"])
        return HTTPResponseSnapshot(
            body=REACTION_618_EXPORT.read_text(encoding="utf-8"),
            http_status=200,
            url=url,
        )

    proposal = source_proposal(
        provider="sabiork",
        refresh=True,
        cache_dir=tmp_path,
        transport=fake_transport,
        **selector,
    )

    assert queries == [expected_query]
    assert proposal.reaction_records


def test_text_selector_quotes_escape_solr_syntax_per_official_sabio_semantics(
    tmp_path: Path,
) -> None:
    queries: list[str] = []
    selector = 'oxidase "alpha"\\beta AND substrate:ATP OR NOT'

    def fake_transport(url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
        assert timeout_seconds == 30.0
        queries.extend(parse_qs(urlparse(url).query)["q"])
        return HTTPResponseSnapshot(
            body=MINIMAL_EXPORT.read_text(encoding="utf-8"),
            http_status=200,
            url=url,
        )

    with pytest.raises(SourceProviderError, match="No SABIO-RK entries matched"):
        source_proposal(
            provider="sabiork",
            enzyme=selector,
            refresh=True,
            cache_dir=tmp_path,
            transport=fake_transport,
        )

    assert queries == ['Enzymename:"oxidase \\"alpha\\"\\\\beta AND substrate:ATP OR NOT"']


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reaction_id", " 618"),
        ("reaction_id", "+618"),
        ("reaction_id", "618 OR *:*"),
        ("reaction_id", 0),
        ("entry_id", "1.0"),
        ("entry_id", "-1"),
        ("entry_id", True),
    ],
)
def test_sabio_identifiers_require_positive_unquoted_decimal_forms(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    with pytest.raises(SourceProviderError, match="positive decimal SABIO-RK identifier"):
        source_proposal(
            provider="sabiork",
            refresh=True,
            cache_dir=tmp_path,
            **{field: value},
        )

    assert list(tmp_path.iterdir()) == []


def test_sequential_queries_create_distinct_immutable_bundles_with_paired_metadata(
    tmp_path: Path,
) -> None:
    body = REACTION_618_EXPORT.read_text(encoding="utf-8")

    def fake_transport(url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
        assert timeout_seconds == 30.0
        return HTTPResponseSnapshot(body=body, http_status=200, url=url)

    reaction_proposal = source_proposal(
        provider="sabiork",
        reaction_id="618",
        refresh=True,
        cache_dir=tmp_path,
        transport=fake_transport,
    )
    reaction_export = Path(reaction_proposal.source_snapshot_path)
    reaction_metadata = reaction_export.parent.parent / "fetch_metadata.json"
    reaction_metadata_before = reaction_metadata.read_bytes()

    ec_proposal = source_proposal(
        provider="sabiork",
        ec_number="3.2.1.21",
        refresh=True,
        cache_dir=tmp_path,
        transport=fake_transport,
    )
    ec_export = Path(ec_proposal.source_snapshot_path)
    ec_metadata = ec_export.parent.parent / "fetch_metadata.json"

    reaction_snapshot = SabioRKSource().load_kinlaw_entries(reaction_export)
    ec_snapshot = SabioRKSource().load_kinlaw_entries(ec_export)

    assert reaction_export != ec_export
    assert reaction_export.parents[2] != ec_export.parents[2]
    assert reaction_metadata != ec_metadata
    assert reaction_metadata.read_bytes() == reaction_metadata_before
    assert reaction_snapshot.metadata_path == reaction_metadata
    assert reaction_snapshot.fetch_metadata["query"] == "SabioReactionID:618"
    assert ec_snapshot.metadata_path == ec_metadata
    assert ec_snapshot.fetch_metadata["query"] == 'ECNumber:"3.2.1.21"'


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

    def failing_transport(_url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
        assert timeout_seconds == 30.0
        raise OSError("offline fixture fetch failed")

    with pytest.raises(SourceProviderError, match="offline fixture fetch failed"):
        source_proposal(
            provider="sabiork",
            reaction_id="618",
            refresh=True,
            cache_dir=tmp_path,
            transport=failing_transport,
        )


def test_public_source_proposal_has_no_live_fetcher_escape_hatch() -> None:
    assert "live_fetcher" not in inspect.signature(source_proposal).parameters


def _registry_snapshot() -> dict[str, str]:
    return {
        str(path.relative_to(DATA_REGISTRY)): path.read_text(encoding="utf-8")
        for path in sorted(DATA_REGISTRY.rglob("*"))
        if path.is_file()
    }
