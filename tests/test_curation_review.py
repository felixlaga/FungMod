from __future__ import annotations

import hashlib
import json
import socket
from copy import deepcopy
from pathlib import Path
from typing import NoReturn

import pytest
import yaml

from fungal_model import (
    CurationDecision,
    CurationError,
    review_source_proposal,
    source_proposal,
)
from fungal_model.api.curation import CURATION_BUNDLE_ALLOWED_USE


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "source_snapshots" / "sabiork"
DATA_REGISTRY = ROOT / "data_registry"
ELIGIBLE_PARAMETER_ID = "proposed_sabiork_parameter_618_35622_kcat_cellobiose"
REJECTED_PRODUCT_MAP_ID = "proposed_sabiork_product_map_618_35622"
BLOCKED_SUBSTRATE_ID = "proposed_sabiork_substrate_cellobiose"


def _proposal():
    return source_proposal(
        provider="sabiork",
        reaction_id="618",
        entry_id="35622",
        cache_dir=RAW_DIR,
    )


def _decision(decision: str, reason: str) -> CurationDecision:
    return CurationDecision(
        decision=decision,
        reason=reason,
        curation_date="2026-07-13",
        allowed_use="curator_assessment_only_pending_registry_promotion",
        limitations=("No production registry promotion or scientific validation is implied.",),
    )


def _registry_snapshot() -> dict[str, str]:
    return {
        str(path.relative_to(DATA_REGISTRY)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(DATA_REGISTRY.rglob("*"))
        if path.is_file()
    }


def _write_manifest(path: Path, payload: object) -> Path:
    path.mkdir(parents=True)
    manifest = path / "proposal_manifest.json"
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def test_normal_sabiork_proposal_is_classified_and_all_deferred_by_default() -> None:
    result = review_source_proposal(_proposal())

    assert result.summary() == {
        "schema_version": "1.0.0",
        "source_query": "SabioReactionID:618",
        "source_snapshot_path": str(
            ROOT
            / "data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw/kinlaw_entries_reaction_618.json"
        ),
        "record_count": 12,
        "eligible_for_review_count": 7,
        "blocked_excluded_count": 5,
        "accepted_count": 0,
        "rejected_count": 0,
        "deferred_count": 12,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
    }
    assert all(record.decision == "defer" for record in result.records)
    assert all(not record.explicit_decision for record in result.records)
    blocked = next(record for record in result.records if record.record_id == BLOCKED_SUBSTRATE_ID)
    assert blocked.classification == "blocked_excluded"
    assert blocked.missing_fields == ("bond_classes",)
    assert blocked.reasons == ("missing required fields: bond_classes",)


def test_explicit_accept_reject_decisions_require_metadata_and_preserve_provenance(
    tmp_path: Path,
) -> None:
    result = review_source_proposal(
        _proposal(),
        curator="Dr Curator",
        decisions={
            ELIGIBLE_PARAMETER_ID: _decision("accept", "Source value and units were checked against the snapshot."),
            REJECTED_PRODUCT_MAP_ID: _decision("reject", "The product mapping needs a separate mechanistic review."),
        },
    )

    assert [record.record_id for record in result.accepted_records] == [ELIGIBLE_PARAMETER_ID]
    assert [record.record_id for record in result.rejected_records] == [REJECTED_PRODUCT_MAP_ID]
    accepted = result.accepted_records[0]
    assert accepted.curator == "Dr Curator"
    assert accepted.source_provenance["source_database"] == "SABIO-RK"
    assert accepted.source_provenance["source_entry_ids"] == ["35622"]
    assert accepted.source_provenance["source_snapshot_path"] == result.source_snapshot_path

    write_result = result.write(tmp_path / "curation")
    accepted_payload = yaml.safe_load(write_result.paths["accepted_registry_records"].read_text(encoding="utf-8"))
    rejected_payload = yaml.safe_load(write_result.paths["rejected_registry_records"].read_text(encoding="utf-8"))
    accepted_record = accepted_payload["records"][0]

    assert accepted_payload["production_registry_promotion"] is False
    assert accepted_payload["allowed_use"] == CURATION_BUNDLE_ALLOWED_USE
    assert accepted_record["source_value"] == accepted.proposed_record["source_value"]
    assert accepted_record["source_units"] == accepted.proposed_record["source_units"]
    assert accepted_record["normalized_start_value"] == accepted.proposed_record["normalized_start_value"]
    assert accepted_record["normalized_units"] == accepted.proposed_record["normalized_units"]
    assert accepted_record["curation"]["promotion_status"] == "not_promoted_to_production_registry"
    assert rejected_payload["records"][0]["curation"]["decision"] == "reject"


def test_written_proposal_bundle_uses_same_review_logic_and_preserves_conversion_metadata(
    tmp_path: Path,
) -> None:
    payload = _proposal().to_dict()
    parameter = next(
        record
        for record in payload["proposed_records"]["parameter_records"]
        if record["record_id"] == ELIGIBLE_PARAMETER_ID
    )
    parameter["original_value"] = parameter["source_value"]
    parameter["original_units"] = parameter["source_units"]
    parameter["converted_value"] = parameter["normalized_start_value"]
    parameter["converted_units"] = parameter["normalized_units"]
    parameter["conversion_method"] = "source_adapter_explicit_conversion"
    bundle = tmp_path / "proposal"
    _write_manifest(bundle, payload)

    from_memory = review_source_proposal(_proposal())
    from_bundle = review_source_proposal(bundle)
    record = next(item for item in from_bundle.records if item.record_id == ELIGIBLE_PARAMETER_ID)

    assert from_bundle.summary() == from_memory.summary()
    assert record.proposed_record["original_value"] == parameter["original_value"]
    assert record.proposed_record["original_units"] == parameter["original_units"]
    assert record.proposed_record["converted_value"] == parameter["converted_value"]
    assert record.proposed_record["converted_units"] == parameter["converted_units"]
    assert record.proposed_record["conversion_method"] == parameter["conversion_method"]


def test_curation_write_is_deterministic_transactional_and_checksummed(tmp_path: Path) -> None:
    result = review_source_proposal(_proposal())
    first = result.write(tmp_path / "first")
    second = result.write(tmp_path / "second")

    first_bytes = {path.name: path.read_bytes() for path in first.paths.values()}
    second_bytes = {path.name: path.read_bytes() for path in second.paths.values()}
    assert first_bytes == second_bytes

    stale = first.output_directory / "stale.txt"
    stale.write_text("must disappear", encoding="utf-8")
    repeated = result.write(first.output_directory)
    assert not stale.exists()
    assert {path.name: path.read_bytes() for path in repeated.paths.values()} == first_bytes

    manifest = json.loads(repeated.paths["curation_manifest"].read_text(encoding="utf-8"))
    assert manifest["production_registry_mutated"] is False
    assert manifest["scientific_validation_claimed"] is False
    for filename, digest in manifest["files"].items():
        assert hashlib.sha256((repeated.output_directory / filename).read_bytes()).hexdigest() == digest


def test_curation_is_offline_and_never_mutates_production_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    before = _registry_snapshot()

    def forbidden_connect(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("CURATION-001 review must remain offline")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    proposal = _proposal()
    proposal_bundle = proposal.write(tmp_path / "proposal")
    result = review_source_proposal(proposal_bundle.output_directory)
    result.write(tmp_path / "curation")

    assert _registry_snapshot() == before


@pytest.mark.parametrize(
    ("decisions", "curator", "message"),
    [
        ({ELIGIBLE_PARAMETER_ID: _decision("trust", "invalid decision")}, "Dr Curator", "Unknown decision"),
        ({ELIGIBLE_PARAMETER_ID: _decision("accept", "complete")}, None, "curator identity"),
        ({"missing-record": _decision("reject", "not present")}, "Dr Curator", "unknown record IDs"),
    ],
)
def test_unknown_or_incomplete_decisions_fail(
    decisions: dict[str, CurationDecision],
    curator: str | None,
    message: str,
) -> None:
    with pytest.raises(CurationError, match=message):
        review_source_proposal(_proposal(), curator=curator, decisions=decisions)


def test_explicit_decision_requires_reason_date_allowed_use_and_limitations() -> None:
    fields = {
        "decision": "accept",
        "reason": "checked",
        "curation_date": "2026-07-13",
        "allowed_use": "review only",
        "limitations": ["not promoted"],
    }
    for missing_field in ("reason", "curation_date", "allowed_use", "limitations"):
        decision = deepcopy(fields)
        decision.pop(missing_field)
        with pytest.raises(CurationError, match=missing_field):
            review_source_proposal(
                _proposal(),
                curator="Dr Curator",
                decisions={ELIGIBLE_PARAMETER_ID: decision},
            )


def test_blocked_record_cannot_be_accepted() -> None:
    with pytest.raises(CurationError, match="cannot be accepted.*blocked/excluded"):
        review_source_proposal(
            _proposal(),
            curator="Dr Curator",
            decisions={BLOCKED_SUBSTRATE_ID: _decision("accept", "Attempted acceptance")},
        )


def test_explicit_decisions_require_source_entry_provenance(tmp_path: Path) -> None:
    payload = _proposal().to_dict()
    parameter = next(
        record
        for record in payload["proposed_records"]["parameter_records"]
        if record["record_id"] == ELIGIBLE_PARAMETER_ID
    )
    parameter["provenance"].pop("source_entry_ids")
    bundle = tmp_path / "missing_provenance"
    _write_manifest(bundle, payload)

    deferred = review_source_proposal(bundle)
    blocked = next(record for record in deferred.records if record.record_id == ELIGIBLE_PARAMETER_ID)
    assert blocked.classification == "blocked_excluded"
    assert blocked.missing_fields == ("source_provenance.source_entry_ids",)
    assert blocked.reasons == ("missing source provenance: source_entry_ids",)

    with pytest.raises(CurationError, match="cannot receive an explicit decision.*source provenance"):
        review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={ELIGIBLE_PARAMETER_ID: _decision("reject", "Cannot verify the source entry")},
        )


def test_malformed_duplicate_and_path_inputs_fail(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "proposal_manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CurationError, match="Malformed proposal bundle"):
        review_source_proposal(malformed)

    payload = _proposal().to_dict()
    duplicate = deepcopy(payload["proposed_records"]["product_maps"][0])
    payload["proposed_records"]["fungi"].append(duplicate)
    duplicate_bundle = tmp_path / "duplicate"
    _write_manifest(duplicate_bundle, payload)
    with pytest.raises(CurationError, match="Duplicate proposal record ID"):
        review_source_proposal(duplicate_bundle)

    with pytest.raises(CurationError, match="path traversal"):
        review_source_proposal(tmp_path / "duplicate" / "..")

    result = review_source_proposal(_proposal())
    with pytest.raises(CurationError, match="path traversal"):
        result.write(tmp_path / "output" / ".." / "escaped")
    with pytest.raises(CurationError, match="cannot be written inside data_registry"):
        result.write(DATA_REGISTRY / "curation_should_not_exist")
    assert not (DATA_REGISTRY / "curation_should_not_exist").exists()
