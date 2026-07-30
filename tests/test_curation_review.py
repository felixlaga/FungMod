from __future__ import annotations

import hashlib
import json
import socket
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn

import pytest
import yaml

import fungal_model
from fungal_model import (
    CurationDecision,
    CurationError,
    LoadedCurationBundle,
    load_curation_bundle,
    review_source_proposal,
    source_proposal,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    CURATION_MANIFEST_KIND,
)


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "source_snapshots" / "sabiork"
DATA_REGISTRY = ROOT / "data_registry"
PARAMETER_ID = "proposed_sabiork_parameter_618_35622_kcat_cellobiose"
REJECTED_PRODUCT_MAP_ID = "proposed_sabiork_product_map_618_35622"
BLOCKED_SUBSTRATE_ID = "proposed_sabiork_substrate_cellobiose"
CASE_TEMPLATE_ID = "proposed_sabiork_case_template_618_35622_homogeneous_michaelis_menten"


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
        allowed_use=(
            CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION
            if decision == "accept"
            else CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY
        ),
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
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return manifest


def _payload_with_complete_parameter() -> dict[str, Any]:
    payload = _proposal().to_dict()
    parameter = next(
        record
        for record in payload["proposed_records"]["parameter_records"]
        if record["record_id"] == PARAMETER_ID
    )
    parameter["original_value"] = parameter["source_value"]
    parameter["original_units"] = parameter["source_units"]
    parameter["converted_value"] = parameter["normalized_start_value"]
    parameter["converted_units"] = parameter["normalized_units"]
    parameter["conversion_method"] = "source_adapter_explicit_conversion"
    return payload


def _reverse_mapping_keys(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _reverse_mapping_keys(item)
            for key, item in reversed(tuple(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_mapping_keys(item) for item in value]
    return value


def _reverse_set_like_sequences(value: object, *, field_name: str | None = None) -> object:
    set_like_fields = {
        "aliases",
        "enzyme_classes",
        "limitations",
        "required_parameters",
        "source_entry_ids",
        "source_reaction_ids",
    }
    if isinstance(value, dict):
        return {
            key: _reverse_set_like_sequences(item, field_name=key)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        items = [_reverse_set_like_sequences(item) for item in value]
        return list(reversed(items)) if field_name in set_like_fields else items
    return value


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
        "eligible_for_review_count": 3,
        "blocked_excluded_count": 9,
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
    parameter = next(record for record in result.records if record.record_id == PARAMETER_ID)
    assert parameter.classification == "blocked_excluded"
    assert parameter.missing_fields == (
        "conversion_method",
        "converted_units",
        "converted_value",
        "original_units",
        "original_value",
    )


def test_explicit_accept_reject_decisions_require_metadata_and_preserve_provenance(
    tmp_path: Path,
) -> None:
    proposal_bundle = tmp_path / "proposal"
    _write_manifest(proposal_bundle, _payload_with_complete_parameter())
    result = review_source_proposal(
        proposal_bundle,
        curator="Dr Curator",
        decisions={
            PARAMETER_ID: _decision("accept", "Source value and units were checked against the snapshot."),
            REJECTED_PRODUCT_MAP_ID: _decision("reject", "The product mapping needs a separate mechanistic review."),
        },
    )

    assert [record.record_id for record in result.accepted_records] == [PARAMETER_ID]
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
    assert accepted_payload["allowed_use"] == CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY
    assert accepted_payload["proposal_limitations"] == list(result.proposal_limitations)
    assert accepted_record["source_value"] == accepted.proposed_record["source_value"]
    assert accepted_record["source_units"] == accepted.proposed_record["source_units"]
    assert accepted_record["normalized_start_value"] == accepted.proposed_record["normalized_start_value"]
    assert accepted_record["normalized_units"] == accepted.proposed_record["normalized_units"]
    assert accepted_record["original_value"] == accepted.proposed_record["original_value"]
    assert accepted_record["original_units"] == accepted.proposed_record["original_units"]
    assert accepted_record["converted_value"] == accepted.proposed_record["converted_value"]
    assert accepted_record["converted_units"] == accepted.proposed_record["converted_units"]
    assert accepted_record["conversion_method"] == accepted.proposed_record["conversion_method"]
    assert accepted_record["curation"]["allowed_use"] == CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION
    assert accepted_record["curation"]["promotion_status"] == "not_promoted_to_production_registry"
    assert rejected_payload["records"][0]["curation"]["decision"] == "reject"


def test_written_proposal_bundle_uses_same_review_logic_and_preserves_conversion_metadata(
    tmp_path: Path,
) -> None:
    payload = _payload_with_complete_parameter()
    parameter = next(
        record
        for record in payload["proposed_records"]["parameter_records"]
        if record["record_id"] == PARAMETER_ID
    )
    bundle = tmp_path / "proposal"
    _write_manifest(bundle, payload)

    from_memory = review_source_proposal(_proposal())
    from_bundle = review_source_proposal(bundle)
    record = next(item for item in from_bundle.records if item.record_id == PARAMETER_ID)

    assert from_bundle.summary()["eligible_for_review_count"] == 4
    assert from_memory.summary()["eligible_for_review_count"] == 3
    assert record.proposed_record["original_value"] == parameter["original_value"]
    assert record.proposed_record["original_units"] == parameter["original_units"]
    assert record.proposed_record["converted_value"] == parameter["converted_value"]
    assert record.proposed_record["converted_units"] == parameter["converted_units"]
    assert record.proposed_record["conversion_method"] == parameter["conversion_method"]


def test_normal_sabiork_parameter_cannot_be_accepted_without_conversion_metadata() -> None:
    with pytest.raises(
        CurationError,
        match="cannot be accepted.*conversion_method.*converted_units.*original_value",
    ):
        review_source_proposal(
            _proposal(),
            curator="Dr Curator",
            decisions={PARAMETER_ID: _decision("accept", "Attempted acceptance")},
        )


def test_record_type_schema_validation_blocks_malformed_content(tmp_path: Path) -> None:
    payload = _payload_with_complete_parameter()
    payload["proposed_records"]["fungi"][0]["enzyme_classes"] = [""]
    payload["proposed_records"]["product_maps"][0]["substrates"] = [{"entry_id": "35622"}]
    parameter = next(
        record
        for record in payload["proposed_records"]["parameter_records"]
        if record["record_id"] == PARAMETER_ID
    )
    parameter["converted_value"] = "0.13"
    payload["proposed_records"]["case_templates"][0]["state_roles"] = {"substrate": 1}
    bundle = tmp_path / "malformed_types"
    _write_manifest(bundle, payload)

    result = review_source_proposal(bundle)
    by_id = {record.record_id: record for record in result.records}

    fungus = next(record for record in result.records if record.record_type == "fungi")
    assert "field 'enzyme_classes' must be nonempty sequence of nonblank text" in fungus.reasons
    assert (
        "field 'substrates' must be nonempty participant sequence with finite positive numeric stoichiometry"
        in by_id[REJECTED_PRODUCT_MAP_ID].reasons
    )
    assert "field 'converted_value' must be finite number" in by_id[PARAMETER_ID].reasons
    assert "field 'state_roles' must be nonempty nonblank text mapping" in by_id[CASE_TEMPLATE_ID].reasons
    assert all(
        record.classification == "blocked_excluded"
        for record in (fungus, by_id[REJECTED_PRODUCT_MAP_ID], by_id[PARAMETER_ID], by_id[CASE_TEMPLATE_ID])
    )

    with pytest.raises(CurationError, match="cannot be accepted.*finite number"):
        review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={PARAMETER_ID: _decision("accept", "Attempted malformed acceptance")},
        )


def test_valid_product_map_stoichiometry_and_yield_are_review_eligible() -> None:
    result = review_source_proposal(_proposal())
    product_map = next(record for record in result.records if record.record_id == REJECTED_PRODUCT_MAP_ID)

    assert product_map.classification == "eligible_for_review"
    assert product_map.reasons == ()


@pytest.mark.parametrize("participant_group", ["substrates", "products"])
@pytest.mark.parametrize(
    "stoichiometry",
    ["not-a-number", "0", "-1", "nan", "inf"],
    ids=["nonnumeric", "zero", "negative", "nan", "infinite"],
)
def test_product_map_blocks_invalid_participant_stoichiometry(
    tmp_path: Path,
    participant_group: str,
    stoichiometry: str,
) -> None:
    payload = _proposal().to_dict()
    product_map = payload["proposed_records"]["product_maps"][0]
    product_map[participant_group][0]["stoichiometry"] = stoichiometry
    bundle = tmp_path / f"{participant_group}_{stoichiometry.replace('-', 'minus')}"
    _write_manifest(bundle, payload)

    result = review_source_proposal(bundle)
    blocked = next(record for record in result.records if record.record_id == REJECTED_PRODUCT_MAP_ID)

    assert blocked.classification == "blocked_excluded"
    assert (
        f"field {participant_group!r} must be nonempty participant sequence with finite positive numeric stoichiometry"
        in blocked.reasons
    )
    with pytest.raises(CurationError, match="cannot be accepted.*positive numeric stoichiometry"):
        review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision("accept", "Attempted invalid acceptance")},
        )


@pytest.mark.parametrize(
    "yield_value",
    ["not-a-number", 0.0, -1.0, float("nan"), float("inf")],
    ids=["nonnumeric", "zero", "negative", "nan", "infinite"],
)
def test_product_map_blocks_invalid_stoichiometric_yield_values(
    tmp_path: Path,
    yield_value: object,
) -> None:
    payload = _proposal().to_dict()
    yields = payload["proposed_records"]["product_maps"][0]["stoichiometric_yields"]
    yield_key = next(iter(yields))
    yields[yield_key] = yield_value
    bundle = tmp_path / "invalid_yield"
    _write_manifest(bundle, payload)

    result = review_source_proposal(bundle)
    blocked = next(record for record in result.records if record.record_id == REJECTED_PRODUCT_MAP_ID)

    assert blocked.classification == "blocked_excluded"
    assert "field 'stoichiometric_yields' must be positive finite numeric mapping" in blocked.reasons
    with pytest.raises(CurationError, match="cannot be accepted.*positive finite numeric mapping"):
        review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision("accept", "Attempted invalid acceptance")},
        )


def test_product_map_blocks_oversized_participant_stoichiometry_without_aborting(
    tmp_path: Path,
) -> None:
    payload = _proposal().to_dict()
    payload["proposed_records"]["product_maps"][0]["products"][0]["stoichiometry"] = 10**400
    bundle = tmp_path / "oversized_participant"
    _write_manifest(bundle, payload)

    result = review_source_proposal(bundle)
    blocked = next(record for record in result.records if record.record_id == REJECTED_PRODUCT_MAP_ID)
    assert blocked.classification == "blocked_excluded"
    assert any("finite positive numeric stoichiometry" in reason for reason in blocked.reasons)

    for decision in ("reject", "defer"):
        reviewed = review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision(decision, "Oversized stoichiometry is malformed")},
        )
        reviewed_map = next(record for record in reviewed.records if record.record_id == REJECTED_PRODUCT_MAP_ID)
        assert reviewed_map.decision == decision
        assert reviewed_map.explicit_decision is True
        assert reviewed_map.classification == "blocked_excluded"

    with pytest.raises(CurationError, match="cannot be accepted.*finite positive numeric stoichiometry"):
        review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision("accept", "Attempted oversized acceptance")},
        )


def test_product_map_blocks_oversized_yield_without_aborting(tmp_path: Path) -> None:
    payload = _proposal().to_dict()
    yields = payload["proposed_records"]["product_maps"][0]["stoichiometric_yields"]
    yields[next(iter(yields))] = 10**400
    bundle = tmp_path / "oversized_yield"
    _write_manifest(bundle, payload)

    result = review_source_proposal(bundle)
    blocked = next(record for record in result.records if record.record_id == REJECTED_PRODUCT_MAP_ID)
    assert blocked.classification == "blocked_excluded"
    assert "field 'stoichiometric_yields' must be positive finite numeric mapping" in blocked.reasons

    for decision in ("reject", "defer"):
        reviewed = review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision(decision, "Oversized yield is malformed")},
        )
        reviewed_map = next(record for record in reviewed.records if record.record_id == REJECTED_PRODUCT_MAP_ID)
        assert reviewed_map.decision == decision
        assert reviewed_map.explicit_decision is True
        assert reviewed_map.classification == "blocked_excluded"

    with pytest.raises(CurationError, match="cannot be accepted.*positive finite numeric mapping"):
        review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision("accept", "Attempted oversized acceptance")},
        )


def test_product_map_yield_consistency_uses_tight_tolerance(tmp_path: Path) -> None:
    payload = _proposal().to_dict()
    yields = payload["proposed_records"]["product_maps"][0]["stoichiometric_yields"]
    yield_key = next(iter(yields))
    yields[yield_key] = 2.0 + 1e-13
    within_tolerance = tmp_path / "within_tolerance"
    _write_manifest(within_tolerance, payload)

    valid = review_source_proposal(within_tolerance)
    valid_map = next(record for record in valid.records if record.record_id == REJECTED_PRODUCT_MAP_ID)
    assert valid_map.classification == "eligible_for_review"

    yields[yield_key] = 3.0
    inconsistent_bundle = tmp_path / "inconsistent"
    _write_manifest(inconsistent_bundle, payload)
    inconsistent = review_source_proposal(inconsistent_bundle)
    blocked = next(record for record in inconsistent.records if record.record_id == REJECTED_PRODUCT_MAP_ID)
    assert blocked.classification == "blocked_excluded"
    assert any("must match product participant stoichiometry 2.0" in reason for reason in blocked.reasons)

    for decision in ("reject", "defer"):
        reviewed = review_source_proposal(
            inconsistent_bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision(decision, "Yield requires source review")},
        )
        reviewed_map = next(record for record in reviewed.records if record.record_id == REJECTED_PRODUCT_MAP_ID)
        assert reviewed_map.explicit_decision is True
        assert reviewed_map.decision == decision
        assert reviewed_map.classification == "blocked_excluded"

    with pytest.raises(CurationError, match="cannot be accepted.*must match product participant"):
        review_source_proposal(
            inconsistent_bundle,
            curator="Dr Curator",
            decisions={REJECTED_PRODUCT_MAP_ID: _decision("accept", "Attempted inconsistent acceptance")},
        )


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
    assert manifest["proposal_limitations"] == list(result.proposal_limitations)
    for filename, digest in manifest["files"].items():
        assert hashlib.sha256((repeated.output_directory / filename).read_bytes()).hexdigest() == digest


def test_public_curation_bundle_loader_reconstructs_verified_result(tmp_path: Path) -> None:
    result = review_source_proposal(_proposal())
    written = result.write(tmp_path / "curation")

    loaded = load_curation_bundle(written.output_directory)
    loaded_from_manifest = load_curation_bundle(written.paths["curation_manifest"])

    assert isinstance(loaded, LoadedCurationBundle)
    assert loaded.result.summary() == result.summary()
    assert loaded_from_manifest.result.summary() == result.summary()
    assert loaded.output_directory == written.output_directory
    assert loaded.paths == written.paths
    assert loaded.manifest["production_registry_mutated"] is False
    assert loaded.manifest["scientific_validation_claimed"] is False
    assert loaded.accepted_records_payload["records"] == []
    round_trip = loaded.result.write(tmp_path / "round_trip")
    assert {path.name: path.read_bytes() for path in round_trip.paths.values()} == {
        path.name: path.read_bytes() for path in written.paths.values()
    }
    assert fungal_model.load_curation_bundle is load_curation_bundle
    assert fungal_model.LoadedCurationBundle is LoadedCurationBundle


def test_public_curation_bundle_loader_rejects_checksum_and_semantic_drift(
    tmp_path: Path,
) -> None:
    result = review_source_proposal(_proposal())
    checksum_bundle = result.write(tmp_path / "checksum").output_directory
    report = checksum_bundle / "curation_report.md"
    report.write_text(report.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(CurationError, match="checksum mismatch for 'curation_report.md'"):
        load_curation_bundle(checksum_bundle)

    semantic_bundle = result.write(tmp_path / "semantic").output_directory
    proposed_path = semantic_bundle / "proposed_registry_records.yml"
    proposed = yaml.safe_load(proposed_path.read_text(encoding="utf-8"))
    original_classification = proposed["records"][0]["curation"]["classification"]
    proposed["records"][0]["curation"]["classification"] = (
        "blocked_excluded"
        if original_classification == "eligible_for_review"
        else "eligible_for_review"
    )
    proposed_path.write_text(yaml.safe_dump(proposed, sort_keys=False), encoding="utf-8")
    manifest_path = semantic_bundle / "curation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][proposed_path.name] = hashlib.sha256(proposed_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CurationError, match="eligible_records.csv.*disagrees"):
        load_curation_bundle(semantic_bundle)


def test_public_curation_bundle_loader_rejects_extra_and_symlinked_inputs(
    tmp_path: Path,
) -> None:
    result = review_source_proposal(_proposal())
    bundle = result.write(tmp_path / "curation").output_directory
    (bundle / "undeclared.txt").write_text("not owned\n", encoding="utf-8")

    with pytest.raises(CurationError, match="owned artifact inventory"):
        load_curation_bundle(bundle)

    clean_bundle = result.write(tmp_path / "clean").output_directory
    link = tmp_path / "curation_link"
    link.symlink_to(clean_bundle, target_is_directory=True)
    with pytest.raises(CurationError, match="contains a symlink component"):
        load_curation_bundle(link)


def test_curation_refuses_to_replace_unowned_existing_directory(tmp_path: Path) -> None:
    result = review_source_proposal(_proposal())
    destination = tmp_path / "researcher_files"
    destination.mkdir()
    sentinel = destination / "sentinel.txt"
    sentinel.write_text("must remain", encoding="utf-8")

    with pytest.raises(CurationError, match="Refusing to replace.*owned curation manifest"):
        result.write(destination)

    assert sentinel.read_text(encoding="utf-8") == "must remain"
    assert sorted(path.name for path in destination.iterdir()) == ["sentinel.txt"]


def test_curation_refuses_wrong_owned_manifest_kind_or_version(tmp_path: Path) -> None:
    result = review_source_proposal(_proposal())
    for field, value in (("kind", "other_bundle"), ("schema_version", "99.0.0")):
        destination = tmp_path / field
        destination.mkdir()
        sentinel = destination / "sentinel.txt"
        sentinel.write_text("must remain", encoding="utf-8")
        manifest = {
            "kind": CURATION_MANIFEST_KIND,
            "schema_version": "1.0.0",
        }
        manifest[field] = value
        (destination / "curation_manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        with pytest.raises(CurationError, match="not owned by this curation bundle kind/version"):
            result.write(destination)

        assert sentinel.read_text(encoding="utf-8") == "must remain"


def test_reordered_input_mapping_keys_write_identical_artifacts(tmp_path: Path) -> None:
    payload = _payload_with_complete_parameter()
    first_bundle = tmp_path / "proposal_first"
    second_bundle = tmp_path / "proposal_second"
    _write_manifest(first_bundle, payload)
    reordered = _reverse_set_like_sequences(_reverse_mapping_keys(payload))
    _write_manifest(second_bundle, reordered)

    first = review_source_proposal(first_bundle).write(tmp_path / "curation_first")
    second = review_source_proposal(second_bundle).write(tmp_path / "curation_second")

    assert {path.name: path.read_bytes() for path in first.paths.values()} == {
        path.name: path.read_bytes() for path in second.paths.values()
    }


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
        ({PARAMETER_ID: _decision("trust", "invalid decision")}, "Dr Curator", "Unknown decision"),
        ({PARAMETER_ID: _decision("accept", "complete")}, None, "curator identity"),
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
        "allowed_use": CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
        "limitations": ["not promoted"],
    }
    for missing_field in ("reason", "curation_date", "allowed_use", "limitations"):
        decision = deepcopy(fields)
        decision.pop(missing_field)
        with pytest.raises(CurationError, match=missing_field):
            review_source_proposal(
                _proposal(),
                curator="Dr Curator",
                decisions={PARAMETER_ID: decision},
            )


@pytest.mark.parametrize(
    "decision",
    [
        CurationDecision(
            decision="accept",
            reason="unsupported use",
            curation_date="2026-07-13",
            allowed_use="scientific_simulation_and_validation",
            limitations=("not allowed",),
        ),
        CurationDecision(
            decision="accept",
            reason="wrong review state",
            curation_date="2026-07-13",
            allowed_use=CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
            limitations=("not promoted",),
        ),
        CurationDecision(
            decision="reject",
            reason="wrong pending state",
            curation_date="2026-07-13",
            allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
            limitations=("not promoted",),
        ),
    ],
)
def test_decision_allowed_use_is_closed_and_decision_specific(decision: CurationDecision) -> None:
    with pytest.raises(CurationError, match="allowed_use"):
        review_source_proposal(
            _proposal(),
            curator="Dr Curator",
            decisions={CASE_TEMPLATE_ID: decision},
        )


def test_blocked_record_cannot_be_accepted() -> None:
    with pytest.raises(CurationError, match="cannot be accepted.*blocked/excluded"):
        review_source_proposal(
            _proposal(),
            curator="Dr Curator",
            decisions={BLOCKED_SUBSTRATE_ID: _decision("accept", "Attempted acceptance")},
        )


def test_reject_and_defer_preserve_source_provenance_blockers(tmp_path: Path) -> None:
    payload = _payload_with_complete_parameter()
    parameter = next(
        record
        for record in payload["proposed_records"]["parameter_records"]
        if record["record_id"] == PARAMETER_ID
    )
    parameter["provenance"].pop("source_entry_ids")
    bundle = tmp_path / "missing_provenance"
    _write_manifest(bundle, payload)

    deferred = review_source_proposal(bundle)
    blocked = next(record for record in deferred.records if record.record_id == PARAMETER_ID)
    assert blocked.classification == "blocked_excluded"
    assert blocked.missing_fields == ("source_provenance.source_entry_ids",)
    assert blocked.reasons == ("missing source provenance: source_entry_ids",)

    rejected = review_source_proposal(
        bundle,
        curator="Dr Curator",
        decisions={PARAMETER_ID: _decision("reject", "Cannot verify the source entry")},
    )
    rejected_record = next(record for record in rejected.records if record.record_id == PARAMETER_ID)
    assert rejected_record.explicit_decision is True
    assert rejected_record.decision == "reject"
    assert rejected_record.classification == "blocked_excluded"
    assert rejected_record.reasons == blocked.reasons

    explicitly_deferred = review_source_proposal(
        bundle,
        curator="Dr Curator",
        decisions={PARAMETER_ID: _decision("defer", "Source entry provenance must be recovered")},
    )
    deferred_record = next(record for record in explicitly_deferred.records if record.record_id == PARAMETER_ID)
    assert deferred_record.explicit_decision is True
    assert deferred_record.decision == "defer"
    assert deferred_record.reasons == blocked.reasons

    with pytest.raises(CurationError, match="cannot be accepted.*source provenance"):
        review_source_proposal(
            bundle,
            curator="Dr Curator",
            decisions={PARAMETER_ID: _decision("accept", "Attempted acceptance")},
        )


def test_parameter_accepts_strict_source_url_provenance_without_snapshot(tmp_path: Path) -> None:
    payload = _payload_with_complete_parameter()
    parameter = next(
        record
        for record in payload["proposed_records"]["parameter_records"]
        if record["record_id"] == PARAMETER_ID
    )
    parameter["provenance"]["source_snapshot_path"] = ""
    parameter["provenance"]["source_url"] = "https://sabiork.h-its.org/kineticlaws/35622"
    bundle = tmp_path / "url_provenance"
    _write_manifest(bundle, payload)

    accepted = review_source_proposal(
        bundle,
        curator="Dr Curator",
        decisions={PARAMETER_ID: _decision("accept", "Source URL and conversion metadata checked")},
    )
    accepted_record = accepted.accepted_records[0]
    assert accepted_record.record_id == PARAMETER_ID
    assert accepted_record.source_provenance["source_snapshot_path"] == ""
    assert accepted_record.source_provenance["source_url"] == "https://sabiork.h-its.org/kineticlaws/35622"

    parameter["provenance"]["source_database"] = " "
    parameter["provenance"]["source_entry_ids"] = "35622"
    malformed_bundle = tmp_path / "malformed_url_provenance"
    _write_manifest(malformed_bundle, payload)
    blocked = review_source_proposal(malformed_bundle)
    blocked_record = next(record for record in blocked.records if record.record_id == PARAMETER_ID)
    assert blocked_record.classification == "blocked_excluded"
    assert "source_provenance.source_database" in blocked_record.missing_fields
    assert "source_provenance.source_entry_ids" in blocked_record.missing_fields


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


def test_symlink_in_any_existing_input_or_output_path_component_fails(tmp_path: Path) -> None:
    real_input_parent = tmp_path / "real_input"
    proposal_dir = real_input_parent / "proposal"
    _write_manifest(proposal_dir, _proposal().to_dict())
    input_link = tmp_path / "input_link"
    input_link.symlink_to(real_input_parent, target_is_directory=True)

    with pytest.raises(CurationError, match="contains a symlink component"):
        review_source_proposal(input_link / "proposal")

    result = review_source_proposal(proposal_dir)
    real_output_parent = tmp_path / "real_output"
    real_output_parent.mkdir()
    output_link = tmp_path / "output_link"
    output_link.symlink_to(real_output_parent, target_is_directory=True)

    with pytest.raises(CurationError, match="contains a symlink component"):
        result.write(output_link / "curation")

    assert list(real_output_parent.iterdir()) == []
