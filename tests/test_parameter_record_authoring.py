from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import fungal_model
import fungal_model.api.registry_promotion as promotion_module
import fungal_model.sources.sabiork.fetch as sabiork_fetch
from fungal_model import (
    CurationDecision,
    CurationError,
    CurationResult,
    CuratorAuthoredParameterResult,
    ParameterRecordAuthoringError,
    RegistryPromotionApplyError,
    RegistryPromotionPlanError,
    VirtualExperimentError,
    author_parameter_record,
    apply_registry_promotion,
    plan_registry_promotion,
    review_source_proposal,
    source_proposal,
    virtual_experiment,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    CurationRecord,
)
from fungal_model.api.parameter_record_authoring import (
    PARAMETER_AUTHORING_ALLOWED_USE,
    PARAMETER_AUTHORING_CONFIDENCE_LEVEL,
    PARAMETER_AUTHORING_MATURITY,
    PARAMETER_AUTHORING_RANGE_INTERPRETATION,
    PARAMETER_AUTHORING_RANGE_SCOPE,
    PARAMETER_AUTHORING_WORKFLOW,
    PARAMETER_BRIDGE_PROVENANCE_KEY,
    PARAMETER_IDENTITY_CONVERSION_METHOD,
    parameter_authoring_digest,
)
from fungal_model.sources.sabiork.fetch import HTTPResponseSnapshot
from fungal_model.sources.sabiork import SabioRKSourceError, frozen_source_urls
from fungal_model.provenance import classify_parameter_provenance
from fungal_model.registry.loaders import load_parameter_record_mapping, load_registry
from fungal_model.registry.records import parameter_simulation_authorization_blocker


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "source_snapshots" / "sabiork"
REACTION_618_EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)
DATA_REGISTRY = ROOT / "data_registry"
SOURCE_PARAMETER_ID = "proposed_sabiork_parameter_618_35622_kcat_cellobiose"
CANONICAL_PARAMETER_ID = "sabiork_reaction_618_kcat_cellobiose"
CURATOR = "PR-48 Test Curator"
CURATION_DATE = "2026-07-14"
SABIO_SOURCE_URL = (
    "https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json?"
    "q=SabioReactionID%3A618&page=1&pageSize=1000"
)


def _proposal():
    return source_proposal(
        provider="sabiork",
        reaction_id="618",
        entry_id="35622",
        cache_dir=RAW_DIR,
    )


def _two_page_proposal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first_page = json.loads(REACTION_618_EXPORT.read_text(encoding="utf-8"))
    first_page["meta"]["page"] = 1
    first_page["meta"]["total_pages"] = 2
    second_page = {
        "meta": {**first_page["meta"], "page": 2},
        "data": [],
    }
    requested_urls: list[str] = []

    def fake_transport(url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
        assert timeout_seconds == 30.0
        requested_urls.append(url)
        payload = second_page if "page=2" in url else first_page
        return HTTPResponseSnapshot(
            body=json.dumps(payload),
            http_status=200,
            url=url,
        )

    monkeypatch.setattr(sabiork_fetch, "MIN_REQUEST_INTERVAL_SECONDS", 0.0)
    proposal = source_proposal(
        provider="sabiork",
        reaction_id="618",
        entry_id="35622",
        refresh=True,
        cache_dir=tmp_path / "two_page_snapshots",
        transport=fake_transport,
    )
    assert len(requested_urls) == 2
    return proposal, requested_urls


def _write_proposal_manifest(path: Path, payload: MappingLike) -> Path:
    path.mkdir(parents=True)
    manifest = path / "proposal_manifest.json"
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return manifest


MappingLike = dict[str, Any]


def _accepted_source_curation(tmp_path: Path, *, proposal: Any | None = None) -> CurationResult:
    payload = (proposal or _proposal()).to_dict()
    parameter = next(
        item
        for item in payload["proposed_records"]["parameter_records"]
        if item["record_id"] == SOURCE_PARAMETER_ID
    )
    snapshot = Path(parameter["provenance"]["source_snapshot_path"])
    parameter["provenance"]["source_snapshot_sha256"] = hashlib.sha256(
        snapshot.read_bytes()
    ).hexdigest()
    parameter["original_value"] = parameter["source_value"]
    parameter["original_units"] = parameter["source_units"]
    parameter["converted_value"] = parameter["source_value"]
    parameter["converted_units"] = parameter["source_units"]
    parameter["conversion_method"] = PARAMETER_IDENTITY_CONVERSION_METHOD
    proposal_dir = tmp_path / "completed_source_proposal"
    _write_proposal_manifest(proposal_dir, payload)
    return review_source_proposal(
        proposal_dir,
        curator=CURATOR,
        decisions={
            SOURCE_PARAMETER_ID: CurationDecision(
                decision="accept",
                reason="Identity transcription checked against the frozen SABIO-RK snapshot.",
                curation_date=CURATION_DATE,
                allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
                limitations=(
                    "Source transcription is not validation, calibration, prediction evidence, or simulation authorization.",
                ),
            )
        },
    )


def _canonical_parameter_target(source: CurationResult) -> dict[str, Any]:
    accepted = source.accepted_records[0]
    provenance = accepted.source_provenance
    return {
        "record_id": CANONICAL_PARAMETER_ID,
        "name": "SABIO-RK Reaction 618 kcat for cellobiose",
        "maturity": PARAMETER_AUTHORING_MATURITY,
        "provenance": {
            "source_database": provenance["source_database"],
            "source_entry_ids": deepcopy(provenance["source_entry_ids"]),
            "source_reaction_ids": deepcopy(provenance["source_reaction_ids"]),
            "source_query": provenance["source_query"],
            "source_field": provenance["source_field"],
            "source_snapshot_path": provenance["source_snapshot_path"],
            "source_url": provenance["source_url"],
            "source_urls": deepcopy(provenance["source_urls"]),
            "source_snapshot_sha256": provenance["source_snapshot_sha256"],
            "parameter_role": accepted.proposed_record["parameter_role"],
            "curator": CURATOR,
            "curation_date": CURATION_DATE,
            "source_reaction_id": "618",
            "selected_kinlaw_entry_id": "35622",
            "kinetic_record": (
                "data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/"
                "curated/kinetic_record.yml"
            ),
        },
        "parameter_symbol": "kcat_cellobiose",
        "process_type": "homogeneous_michaelis_menten",
        "enzyme_class": "beta_glucosidase",
        "substrate_class": "cellobiose",
        "fungus_id": "sabiork_beta_glucosidase_source",
        "substrate_id": "cellobiose",
        "environment_id": "sabiork_reaction_618_selected_conditions",
        "value": {
            "kind": "exact",
            "units": "s^(-1)",
            "value": 0.13,
            "lower": None,
            "upper": None,
            "distribution": None,
            "parameters": {},
            "source": "SABIO-RK Reaction 618 selected kinetic law",
            "confidence_level": PARAMETER_AUTHORING_CONFIDENCE_LEVEL,
            "notes": (
                "Identity-transcribed from frozen SABIO-RK EntryID 35622; not validated "
                "science or simulation authorization."
            ),
        },
        "range_scope": PARAMETER_AUTHORING_RANGE_SCOPE,
        "range_interpretation": PARAMETER_AUTHORING_RANGE_INTERPRETATION,
        "allowed_use": PARAMETER_AUTHORING_ALLOWED_USE,
        "notes": (
            "Canonical kcat identity re-authored for PR-48 copied-registry planning only; "
            "not validated science."
        ),
    }


def _copy_registry_without_canonical_parameter(tmp_path: Path) -> Path:
    registry = tmp_path / "registry"
    shutil.copytree(DATA_REGISTRY, registry)
    target = registry / "parameters" / "parameter_records.yml"
    payload = yaml.safe_load(target.read_text(encoding="utf-8"))
    before_count = len(payload["records"])
    payload["records"] = [
        record for record in payload["records"] if record["record_id"] != CANONICAL_PARAMETER_ID
    ]
    assert len(payload["records"]) == before_count - 1
    target.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return registry / "registry_index.yml"


def _registry_snapshot(root: Path = DATA_REGISTRY) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _author(tmp_path: Path) -> tuple[CurationResult, Path, dict[str, Any], CuratorAuthoredParameterResult]:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    authored = author_parameter_record(
        source,
        source_record_id=SOURCE_PARAMETER_ID,
        parameter_record=target,
        registry_index=registry_index,
    )
    return source, registry_index, target, authored


def test_real_frozen_sabio_identity_path_is_addable_only_on_a_copied_registry(
    tmp_path: Path,
) -> None:
    production_before = _registry_snapshot()
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    copied_before = _registry_snapshot(registry_index.parent)

    authored = author_parameter_record(
        source,
        source_record_id=SOURCE_PARAMETER_ID,
        parameter_record=_canonical_parameter_target(source),
        registry_index=registry_index,
    )
    authored_bundle = authored.write(tmp_path / "authored_parameter")
    plan = plan_registry_promotion(
        authored_bundle.output_directory,
        registry_index=registry_index,
    )

    assert isinstance(authored, CuratorAuthoredParameterResult)
    assert authored.summary()["workflow"] == PARAMETER_AUTHORING_WORKFLOW
    assert authored.summary()["supported_record_types"] == ["parameter_records"]
    assert authored.summary()["identity_conversion_only"] is True
    assert authored.summary()["production_registry_mutated"] is False
    assert authored.summary()["scientific_validation_claimed"] is False
    assert authored.summary()["simulation_authorized"] is False
    assert plan.summary()["addable_count"] == 1
    assert plan.summary()["apply_available"] is True
    candidate = plan.addable_records[0]
    assert candidate.record_id == CANONICAL_PARAMETER_ID
    assert candidate.record_type == "parameter_records"
    assert candidate.target_record["value"]["value"] == 0.13
    assert candidate.target_record["value"]["units"] == "s^(-1)"
    assert candidate.target_record["allowed_use"] == PARAMETER_AUTHORING_ALLOWED_USE
    bridge = candidate.target_record["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY]
    assert bridge["source_proposal_record_id"] == SOURCE_PARAMETER_ID
    assert bridge["authoring_digest"] == authored.authoring_digest
    assert bridge["source_parameter"] == {
        "parameter_symbol": "kcat_cellobiose",
        "parameter_role": "kcat",
        "proposal_status": "proposed_review_required",
        "proposal_allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
        "original_value": 0.13,
        "original_units": "s^(-1)",
        "source_value": 0.13,
        "source_units": "s^(-1)",
        "normalized_start_value": 0.13,
        "normalized_units": "s^(-1)",
        "converted_value": 0.13,
        "converted_units": "s^(-1)",
        "target_value": 0.13,
        "target_units": "s^(-1)",
        "conversion_method": PARAMETER_IDENTITY_CONVERSION_METHOD,
    }
    assert bridge["scientific_validation_claimed"] is False
    assert bridge["simulation_authorized"] is False
    assert bridge["source_provenance"]["source_url"] == SABIO_SOURCE_URL
    assert bridge["source_provenance"]["source_urls"] == [SABIO_SOURCE_URL]
    assert bridge["source_aliases"] == {
        "source_reaction_id": "618",
        "selected_kinlaw_entry_id": "35622",
    }
    assert bridge["result_provenance"] == {
        "source_query": source.source_query,
        "source_snapshot_path": source.source_snapshot_path,
        "proposal_limitations": list(source.proposal_limitations),
    }
    assert bridge["selector_resolution"] == {
        "fungus_id": "sabiork_beta_glucosidase_source",
        "effective_enzyme_classes": ["beta_glucosidase"],
        "substrate_id": "cellobiose",
        "effective_substrate_class": "cellobiose",
        "environment_id": "sabiork_reaction_618_selected_conditions",
        "process_type": "homogeneous_michaelis_menten",
        "parameter_symbol": "kcat_cellobiose",
        "parameter_role": "kcat",
        "process_compatibility_id": "beta_glucosidase_cellobiose_homogeneous_mm",
    }
    assert len(bridge["registry_context"]["registry_content_sha256"]) == 64
    assert candidate.target_record["provenance"]["fungmod_curation"]["curator"] == CURATOR
    assert _registry_snapshot(registry_index.parent) == copied_before
    assert _registry_snapshot() == production_before


def test_removed_outer_bindings_cannot_reclassify_component_for_authoring(
    tmp_path: Path,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    path = registry_index.parent / "processes" / "process_compatibility.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    outer = next(
        record
        for record in cast(list[dict[str, Any]], payload["records"])
        if record["record_id"]
        == "bio002_cellulase_cellulose_film_extracellular_chain"
    )
    outer.pop("component_bindings")
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ParameterRecordAuthoringError,
        match="exactly one owner binding; found 0",
    ):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_offline_two_page_sabio_urls_survive_proposal_curation_and_authoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, source_urls = _two_page_proposal(tmp_path, monkeypatch)
    proposed = next(
        item
        for item in proposal.proposed_records()["parameter_records"]
        if item["record_id"] == SOURCE_PARAMETER_ID
    )
    assert proposed["provenance"]["source_url"] is None
    assert proposed["provenance"]["source_urls"] == source_urls

    source = _accepted_source_curation(tmp_path, proposal=proposal)
    accepted = source.accepted_records[0]
    assert accepted.source_provenance["source_url"] is None
    assert accepted.source_provenance["source_urls"] == source_urls
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    authored = author_parameter_record(
        source,
        source_record_id=SOURCE_PARAMETER_ID,
        parameter_record=_canonical_parameter_target(source),
        registry_index=registry_index,
    )
    authored_provenance = authored.records[0].proposed_record["provenance"]
    assert authored_provenance["source_url"] is None
    assert authored_provenance["source_urls"] == source_urls

    tampered_proposed = deepcopy(dict(accepted.proposed_record))
    tampered_proposed["provenance"]["source_urls"] = list(reversed(source_urls))
    tampered_record = replace(
        accepted,
        proposed_record=tampered_proposed,
        source_provenance={
            **accepted.source_provenance,
            "source_urls": list(reversed(source_urls)),
        },
    )
    tampered = replace(source, records=(tampered_record,))
    with pytest.raises(ParameterRecordAuthoringError, match="frozen SABIO-RK fetch metadata"):
        author_parameter_record(
            tampered,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_collapsed_two_page_frozen_metadata_is_rejected_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, source_urls = _two_page_proposal(tmp_path, monkeypatch)
    source = _accepted_source_curation(tmp_path / "accepted", proposal=proposal)
    metadata_path = Path(proposal.source_snapshot_path).parent.parent / "fetch_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["total_pages"] == 2
    assert len(metadata["raw_pages"]) == 2
    metadata["source_urls"] = source_urls[:1]
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(SabioRKSourceError, match="total_pages, requests_made, and source_urls"):
        frozen_source_urls(proposal.source_snapshot_path)

    registry_index = _copy_registry_without_canonical_parameter(tmp_path / "registry_copy")
    with pytest.raises(ParameterRecordAuthoringError, match="Frozen SABIO-RK source URL evidence"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_two_page_frozen_metadata_rejects_raw_page_path_aliasing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, _ = _two_page_proposal(tmp_path, monkeypatch)
    metadata_path = Path(proposal.source_snapshot_path).parent.parent / "fetch_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    first = metadata["raw_pages"][0]
    second = metadata["raw_pages"][1]
    second["path"] = first["path"]
    second["sha256"] = first["sha256"]
    second["size_bytes"] = first["size_bytes"]
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SabioRKSourceError, match="uniquely match raw/page_NNNN"):
        frozen_source_urls(proposal.source_snapshot_path)


def test_in_memory_result_is_directly_promotion_plan_compatible(tmp_path: Path) -> None:
    _, registry_index, _, authored = _author(tmp_path)

    plan = plan_registry_promotion(authored, registry_index=registry_index)

    assert plan.addable_records[0].record_id == CANONICAL_PARAMETER_ID
    assert plan.summary()["production_registry_mutated"] is False


def test_authoring_source_input_is_intentionally_in_memory_only(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    source_bundle = source.write(tmp_path / "source_bundle")
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)

    with pytest.raises(ParameterRecordAuthoringError, match="validated in-memory CurationResult"):
        author_parameter_record(
            cast(Any, source_bundle.output_directory),
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_written_outputs_are_deterministic_and_checksum_declared(tmp_path: Path) -> None:
    _, _, _, authored = _author(tmp_path)

    first = authored.write(tmp_path / "first")
    second = authored.write(tmp_path / "second")
    first_bytes = {
        path.name: path.read_bytes() for path in first.output_directory.iterdir() if path.is_file()
    }
    second_bytes = {
        path.name: path.read_bytes() for path in second.output_directory.iterdir() if path.is_file()
    }

    assert first_bytes == second_bytes
    manifest = json.loads(first.paths["curation_manifest"].read_text(encoding="utf-8"))
    assert manifest["summary"]["workflow"] == PARAMETER_AUTHORING_WORKFLOW
    assert manifest["summary"]["authoring_digest"] == authored.authoring_digest
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((first.output_directory / name).read_bytes()).hexdigest() == digest


def test_rechecksummed_summary_cannot_claim_mutation_validation_or_simulation(
    tmp_path: Path,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / "forged_summary_safety")
    manifest = json.loads(bundle.paths["curation_manifest"].read_text(encoding="utf-8"))
    manifest["summary"].update(
        {
            "simulation_authorized": True,
            "scientific_validation_claimed": True,
            "production_registry_mutated": True,
            "registry_mutated": True,
        }
    )
    manifest["files"] = {
        name: hashlib.sha256((bundle.output_directory / name).read_bytes()).hexdigest()
        for name in manifest["files"]
    }
    bundle.paths["curation_manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RegistryPromotionPlanError, match="closed parameter-only authoring summary"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


@pytest.mark.parametrize(
    "malformation",
    [
        "manifest_extra_safety_claim",
        "accepted_extra_safety_claim",
        "curation_extra_safety_claim",
        "rewritten_report_scope",
        "combined",
    ],
)
def test_rechecksummed_written_bundle_rejects_extra_claims_and_report_rewrites(
    tmp_path: Path,
    malformation: str,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / f"closed_envelope_{malformation}")
    accepted, manifest = _bundle_payloads(bundle)
    if malformation in {"manifest_extra_safety_claim", "combined"}:
        manifest["simulation_authorized"] = True
    if malformation in {"accepted_extra_safety_claim", "combined"}:
        accepted["scientific_validation_claimed"] = True
    if malformation in {"curation_extra_safety_claim", "combined"}:
        accepted["records"][0]["curation"]["simulation_authorized"] = True
    if malformation in {"rewritten_report_scope", "combined"}:
        report_path = bundle.paths["curation_report"]
        report = report_path.read_text(encoding="utf-8").replace(
            "It is not production registry promotion, scientific validation, or permission for simulation.",
            "It is scientific validation and permission for simulation.",
        )
        report_path.write_text(report, encoding="utf-8")
    _redigest_bundle(bundle, accepted, manifest)

    with pytest.raises(
        RegistryPromotionPlanError,
        match="shared curation builders|closed bridge schema|deterministic machine-readable record",
    ):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


@pytest.mark.parametrize(
    "artifact",
    [
        "proposed",
        "accepted",
        "rejected",
        "eligible_decisions",
        "excluded_decisions",
        "manifest",
        "report",
        "combined",
    ],
)
def test_rechecksummed_authored_bundle_closes_every_semantic_artifact(
    tmp_path: Path,
    artifact: str,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / f"semantic_artifact_{artifact}")
    targets = (
        (
            "proposed",
            "accepted",
            "rejected",
            "eligible_decisions",
            "excluded_decisions",
            "manifest",
            "report",
        )
        if artifact == "combined"
        else (artifact,)
    )
    for target in targets:
        _mutate_semantic_bundle_artifact(bundle, target)
    _refresh_bundle_checksums(bundle)

    with pytest.raises(RegistryPromotionPlanError, match="shared curation builder"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


def test_partial_bridge_marker_is_rejected_at_plan_and_reconstructed_apply(
    tmp_path: Path,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / "partial_bridge_marker")
    accepted, manifest = _bundle_payloads(bundle)
    accepted["records"][0]["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY] = {}
    _redigest_bundle(bundle, accepted, manifest)

    before = _registry_snapshot(registry_index.parent)
    with pytest.raises(RegistryPromotionPlanError, match="bridge audit|identity or digest"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)
    assert _registry_snapshot(registry_index.parent) == before

    valid_plan = plan_registry_promotion(authored, registry_index=registry_index)
    malformed_target = deepcopy(valid_plan.addable_records[0].target_record)
    malformed_target["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY] = {}
    reconstructed = _reconstructed_plan_with_target(
        valid_plan,
        registry_index,
        malformed_target,
    )
    with pytest.raises(RegistryPromotionApplyError, match="specialized bridge validation"):
        apply_registry_promotion(
            reconstructed,
            confirmation_digest=reconstructed.plan_digest,
            new_registry_version="0.1.1",
            registry_index=registry_index,
        )
    assert _registry_snapshot(registry_index.parent) == before


def test_bridge_shape_cannot_be_downgraded_to_generic_promotion_or_runtime_authority(
    tmp_path: Path,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / "downgraded_bridge_bundle")
    accepted, manifest = _bundle_payloads(bundle)
    target = accepted["records"][0]
    target["provenance"].pop(PARAMETER_BRIDGE_PROVENANCE_KEY)
    target["allowed_use"] = "exploratory_simulation"
    target["value"]["confidence_level"] = "literature_curated"
    generic_summary_fields = {
        "schema_version",
        "source_query",
        "source_snapshot_path",
        "record_count",
        "eligible_for_review_count",
        "blocked_excluded_count",
        "accepted_count",
        "rejected_count",
        "deferred_count",
        "production_registry_mutated",
        "scientific_validation_claimed",
    }
    manifest["summary"] = {
        key: value for key, value in manifest["summary"].items() if key in generic_summary_fields
    }
    accepted_path = bundle.paths["accepted_registry_records"]
    accepted_path.write_text(yaml.safe_dump(accepted, sort_keys=False), encoding="utf-8")
    manifest["files"][accepted_path.name] = hashlib.sha256(accepted_path.read_bytes()).hexdigest()
    bundle.paths["curation_manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    registry_before = _registry_snapshot(registry_index.parent)

    with pytest.raises(RegistryPromotionPlanError, match="authoring summary|source identity"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)
    assert _registry_snapshot(registry_index.parent) == registry_before

    valid_plan = plan_registry_promotion(authored, registry_index=registry_index)
    legacy_target = deepcopy(valid_plan.addable_records[0].target_record)
    legacy_target["provenance"].pop(PARAMETER_BRIDGE_PROVENANCE_KEY)
    legacy_target["allowed_use"] = "exploratory_simulation"
    legacy_target["value"]["confidence_level"] = "literature_curated"
    legacy_plan = _reconstructed_plan_with_target(valid_plan, registry_index, legacy_target)
    with pytest.raises(RegistryPromotionApplyError, match="specialized bridge validation"):
        apply_registry_promotion(
            legacy_plan,
            confirmation_digest=legacy_plan.plan_digest,
            new_registry_version="0.1.1",
            registry_index=registry_index,
        )
    assert _registry_snapshot(registry_index.parent) == registry_before

    curation = authored.records[0].to_dict()["curation"]
    generic_record = replace(
        authored.records[0],
        proposed_record=deepcopy(target),
        source_provenance=deepcopy(curation["source_provenance"]),
    )
    generic_result = CurationResult(
        source_query=authored.source_query,
        source_snapshot_path=authored.source_snapshot_path,
        proposal_limitations=authored.proposal_limitations,
        records=(generic_record,),
    )
    with pytest.raises(RegistryPromotionPlanError, match="require CuratorAuthoredParameterResult"):
        plan_registry_promotion(generic_result, registry_index=registry_index)

    parameters_path = registry_index.parent / "parameters" / "parameter_records.yml"
    parameter_payload = yaml.safe_load(parameters_path.read_text(encoding="utf-8"))
    toy_target = next(
        item for item in parameter_payload["records"] if item["record_id"] == "toy_param_k_surface_exact"
    )
    toy_target["provenance"] = deepcopy(target["provenance"])
    toy_target["maturity"] = "literature_processed"
    toy_target["allowed_use"] = "exploratory_simulation"
    parameters_path.write_text(yaml.safe_dump(parameter_payload, sort_keys=False), encoding="utf-8")
    process_path = registry_index.parent / "processes" / "process_compatibility.yml"
    process_payload = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    process_payload["records"][0]["required_parameters"] = [
        "k_surface_exact",
        "k_ads_exact",
        "A_surface_exact",
    ]
    process_payload["records"][0]["parameter_roles"] = {
        "surface_rate_constant": "k_surface_exact",
        "adsorption_constant": "k_ads_exact",
        "accessible_surface_area": "A_surface_exact",
    }
    process_path.write_text(yaml.safe_dump(process_payload, sort_keys=False), encoding="utf-8")
    study = virtual_experiment(
        fungi="toy_fungus_alpha",
        substrates="toy_cellulose_like_solid",
        environments="toy_lab_environment",
        registry=registry_index,
    )
    report = study.preflight(mode="exploratory")[0]
    assert any("curator-authoring source evidence" in item.message for item in report.incompatible)
    with pytest.raises(VirtualExperimentError, match="curator-authoring source evidence"):
        study.simulate(mode="exploratory", output_dir=tmp_path / "blocked_runtime", quicklook=False)


def test_nested_curation_source_evidence_cannot_bypass_plan_apply_or_runtime(
    tmp_path: Path,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    valid_plan = plan_registry_promotion(authored, registry_index=registry_index)
    target = deepcopy(valid_plan.addable_records[0].target_record)
    curation = deepcopy(valid_plan.addable_records[0].curation_metadata)
    target["provenance"].pop(PARAMETER_BRIDGE_PROVENANCE_KEY)
    target["provenance"]["fungmod_curation"] = {
        "source_provenance": deepcopy(curation["source_provenance"]),
    }
    target["allowed_use"] = "exploratory_simulation"
    target["value"]["confidence_level"] = "literature_curated"
    assert classify_parameter_provenance(target["provenance"]) == "parameter_bridge"

    generic_record = replace(
        authored.records[0],
        proposed_record=deepcopy(target),
        source_provenance=deepcopy(curation["source_provenance"]),
    )
    generic_result = CurationResult(
        source_query=authored.source_query,
        source_snapshot_path=authored.source_snapshot_path,
        proposal_limitations=authored.proposal_limitations,
        records=(generic_record,),
    )
    before = _registry_snapshot(registry_index.parent)
    with pytest.raises(RegistryPromotionPlanError, match="require CuratorAuthoredParameterResult"):
        plan_registry_promotion(generic_result, registry_index=registry_index)

    reconstructed = _reconstructed_plan_with_target(valid_plan, registry_index, target)
    with pytest.raises(RegistryPromotionApplyError, match="specialized bridge validation"):
        apply_registry_promotion(
            reconstructed,
            confirmation_digest=reconstructed.plan_digest,
            new_registry_version="0.1.1",
            registry_index=registry_index,
        )
    assert _registry_snapshot(registry_index.parent) == before

    parameters_path = registry_index.parent / "parameters" / "parameter_records.yml"
    parameter_payload = yaml.safe_load(parameters_path.read_text(encoding="utf-8"))
    toy_target = next(
        item for item in parameter_payload["records"] if item["record_id"] == "toy_param_k_surface_exact"
    )
    toy_target["provenance"] = deepcopy(target["provenance"])
    toy_target["allowed_use"] = "exploratory_simulation"
    parameters_path.write_text(yaml.safe_dump(parameter_payload, sort_keys=False), encoding="utf-8")
    runtime = load_registry(registry_index)
    blocker = parameter_simulation_authorization_blocker(
        runtime.parameters["toy_param_k_surface_exact"]
    )
    assert blocker is not None and "curator-authoring source evidence" in blocker

    process_path = registry_index.parent / "processes" / "process_compatibility.yml"
    process_payload = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    process_payload["records"][0]["required_parameters"] = [
        "k_surface_exact",
        "k_ads_exact",
        "A_surface_exact",
    ]
    process_payload["records"][0]["parameter_roles"] = {
        "surface_rate_constant": "k_surface_exact",
        "adsorption_constant": "k_ads_exact",
        "accessible_surface_area": "A_surface_exact",
    }
    process_path.write_text(yaml.safe_dump(process_payload, sort_keys=False), encoding="utf-8")
    study = virtual_experiment(
        fungi="toy_fungus_alpha",
        substrates="toy_cellulose_like_solid",
        environments="toy_lab_environment",
        registry=registry_index,
    )
    assert any(
        "curator-authoring source evidence" in item.message
        for item in study.preflight(mode="exploratory")[0].incompatible
    )
    with pytest.raises(VirtualExperimentError, match="curator-authoring source evidence"):
        study.simulate(mode="exploratory", output_dir=tmp_path / "nested_runtime", quicklook=False)


@pytest.mark.parametrize(
    "outer_metadata",
    [
        {"curator": "Generic Test Curator"},
        {"curation_date": "2026-07-14"},
        {"parameter_role": "surface_rate_constant"},
        {
            "curator": "Generic Test Curator",
            "curation_date": "2026-07-14",
            "parameter_role": "surface_rate_constant",
        },
    ],
    ids=["curator", "date", "role", "combined"],
)
def test_ordinary_curator_metadata_remains_generic_for_planning_and_runtime(
    tmp_path: Path,
    outer_metadata: dict[str, str],
) -> None:
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    runtime = load_registry(registry_index)
    target = runtime.parameters["toy_param_k_surface_exact"].to_dict()
    target["record_id"] = "ordinary_curator_metadata_parameter"
    target["provenance"] = {
        "source": "Synthetic generic provenance classifier fixture.",
        "confidence_level": "testing",
        "notes": "Not scientific data.",
        **outer_metadata,
    }
    assert classify_parameter_provenance(target["provenance"]) == "generic"
    loaded = load_parameter_record_mapping(target)
    assert parameter_simulation_authorization_blocker(loaded) is None

    curation_record = CurationRecord(
        record_type="parameter_records",
        record_id=target["record_id"],
        proposed_record=deepcopy(target),
        classification="eligible_for_review",
        missing_fields=(),
        reasons=(),
        decision="accept",
        explicit_decision=True,
        curator="Generic Promotion Test Curator",
        decision_reason="Accepted as a synthetic generic promotion fixture.",
        curation_date="2026-07-14",
        allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
        limitations=("Synthetic software fixture; no scientific claim.",),
        source_provenance={
            "source_database": "synthetic_fixture",
            "source_entry_ids": ["ordinary-curator-metadata"],
            "source_snapshot_path": "synthetic/ordinary-curator-metadata.json",
        },
    )
    result = CurationResult(
        source_query="synthetic ordinary curator metadata",
        source_snapshot_path="synthetic/ordinary-curator-metadata.json",
        proposal_limitations=("Synthetic software fixture; no scientific claim.",),
        records=(curation_record,),
    )
    plan = plan_registry_promotion(result, registry_index=registry_index)
    assert plan.summary()["addable_count"] == 1
    if len(outer_metadata) == 3:
        malformed_input = deepcopy(target)
        malformed_input["provenance"]["fungmod_curation"] = {}
        malformed_result = replace(
            result,
            records=(replace(curation_record, proposed_record=malformed_input),),
        )
        blocked_plan = plan_registry_promotion(malformed_result, registry_index=registry_index)
        assert blocked_plan.summary()["apply_available"] is False
        assert "curation_audit_provenance_key_already_exists" in blocked_plan.blocked_records[0].reason

        malformed_target = deepcopy(plan.addable_records[0].target_record)
        malformed_target["provenance"]["fungmod_curation"] = {}
        assert classify_parameter_provenance(
            malformed_target["provenance"]
        ) == "curation_audited"
        malformed_loaded = load_parameter_record_mapping(malformed_target)
        assert parameter_simulation_authorization_blocker(malformed_loaded) is not None
        before = _registry_snapshot(registry_index.parent)
        reconstructed = _reconstructed_plan_with_target(
            plan,
            registry_index,
            malformed_target,
        )
        with pytest.raises(RegistryPromotionApplyError, match="durable curation audit"):
            apply_registry_promotion(
                reconstructed,
                confirmation_digest=reconstructed.plan_digest,
                new_registry_version="0.1.1",
                registry_index=registry_index,
            )
        assert _registry_snapshot(registry_index.parent) == before

    parameters_path = registry_index.parent / "parameters" / "parameter_records.yml"
    parameter_payload = yaml.safe_load(parameters_path.read_text(encoding="utf-8"))
    runtime_target = next(
        item for item in parameter_payload["records"] if item["record_id"] == "toy_param_k_surface_exact"
    )
    runtime_target["provenance"].update(outer_metadata)
    parameters_path.write_text(yaml.safe_dump(parameter_payload, sort_keys=False), encoding="utf-8")
    process_path = registry_index.parent / "processes" / "process_compatibility.yml"
    process_payload = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    process_payload["records"][0]["required_parameters"] = [
        "k_surface_exact",
        "k_ads_exact",
        "A_surface_exact",
    ]
    process_payload["records"][0]["parameter_roles"] = {
        "surface_rate_constant": "k_surface_exact",
        "adsorption_constant": "k_ads_exact",
        "accessible_surface_area": "A_surface_exact",
    }
    process_path.write_text(yaml.safe_dump(process_payload, sort_keys=False), encoding="utf-8")
    study = virtual_experiment(
        fungi="toy_fungus_alpha",
        substrates="toy_cellulose_like_solid",
        environments="toy_lab_environment",
        registry=registry_index,
    )
    study.simulate(
        mode="exploratory",
        output_dir=tmp_path / "ordinary_metadata_runtime",
        quicklook=False,
    )


def test_rechecksummed_authored_bundle_mutation_is_rejected_by_authoring_digest(
    tmp_path: Path,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / "authored_bundle")
    accepted_path = bundle.paths["accepted_registry_records"]
    accepted = yaml.safe_load(accepted_path.read_text(encoding="utf-8"))
    accepted["records"][0]["value"]["notes"] = "Mutated after authoring."
    accepted_path.write_text(yaml.safe_dump(accepted, sort_keys=False), encoding="utf-8")
    manifest_path = bundle.paths["curation_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][accepted_path.name] = hashlib.sha256(accepted_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(RegistryPromotionPlanError, match="changed after construction"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source_query", "SabioReactionID:999"),
        ("source_snapshot_path", "/forged/source/snapshot.json"),
        ("proposal_limitations", ("Forged result-level limitation.",)),
    ],
)
def test_result_level_provenance_mutation_is_rejected_everywhere(
    tmp_path: Path,
    field: str,
    replacement: Any,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    forged = replace(authored, **{field: replacement})
    output = tmp_path / f"forged_{field}"

    with pytest.raises(ParameterRecordAuthoringError, match="changed after construction"):
        forged.verify_integrity()
    with pytest.raises(ParameterRecordAuthoringError, match="changed after construction"):
        forged.write(output)
    assert not output.exists()
    with pytest.raises(RegistryPromotionPlanError, match="changed after construction"):
        plan_registry_promotion(forged, registry_index=registry_index)


@pytest.mark.parametrize("field", ["source_query", "source_snapshot_path", "proposal_limitations"])
def test_redigested_written_result_envelope_mutation_is_rejected_by_planning(
    tmp_path: Path,
    field: str,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / f"written_envelope_{field}")
    accepted, manifest = _bundle_payloads(bundle)
    replacement: Any = (
        ["Forged result-level limitation."]
        if field == "proposal_limitations"
        else "SabioReactionID:999"
        if field == "source_query"
        else "/forged/source/snapshot.json"
    )
    manifest["summary"][field] = replacement
    if field in {"source_query", "source_snapshot_path"}:
        manifest[field] = replacement
        accepted[field] = replacement
    _redigest_bundle(bundle, accepted, manifest)

    with pytest.raises(RegistryPromotionPlanError, match="result provenance|curation|audit"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


def test_refreshed_checksums_cannot_hide_report_limitations_disagreement(
    tmp_path: Path,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / "forged_limitations_with_refreshed_checksums")
    accepted, manifest = _bundle_payloads(bundle)
    forged = ["Forged limitation that is absent from the deterministic report."]
    manifest["proposal_limitations"] = forged
    manifest["summary"]["proposal_limitations"] = forged
    accepted["proposal_limitations"] = forged
    accepted["records"][0]["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY][
        "result_provenance"
    ]["proposal_limitations"] = forged
    _redigest_bundle(bundle, accepted, manifest)

    with pytest.raises(RegistryPromotionPlanError, match="deterministic machine-readable record"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


@pytest.mark.parametrize(
    "malformation",
    [
        "missing_source_value",
        "extra_predictive_claim",
        "changed_parameter_symbol",
        "changed_proposal_status",
        "changed_proposal_allowed_use",
        "changed_target_policy",
        "extra_top_level_claim",
    ],
)
def test_redigested_malformed_identity_audit_is_rejected_by_planning(
    tmp_path: Path,
    malformation: str,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / f"malformed_audit_{malformation}")
    accepted, manifest = _bundle_payloads(bundle)
    audit = accepted["records"][0]["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY]
    source_parameter = audit["source_parameter"]
    if malformation == "missing_source_value":
        del source_parameter["source_value"]
    elif malformation == "extra_predictive_claim":
        source_parameter["predictive_current_value"] = 0.13
    elif malformation == "changed_parameter_symbol":
        source_parameter["parameter_symbol"] = "validated_kcat"
    elif malformation == "changed_proposal_status":
        source_parameter["proposal_status"] = "current_validated"
    elif malformation == "changed_proposal_allowed_use":
        source_parameter["proposal_allowed_use"] = "predictive_simulation"
    elif malformation == "changed_target_policy":
        audit["target_policy"]["allowed_use"] = "scientific_simulation"
    else:
        audit["current_source_claim"] = True
    _redigest_bundle(bundle, accepted, manifest)

    with pytest.raises(RegistryPromotionPlanError, match="audit|policy|identity"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


def test_redigested_source_url_tampering_is_rejected_against_frozen_metadata(
    tmp_path: Path,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / "tampered_source_url")
    accepted, manifest = _bundle_payloads(bundle)
    record = accepted["records"][0]
    forged_url = "https://example.test/forged-sabio-source"
    for provenance in (
        record["provenance"],
        record["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY]["source_provenance"],
        record["curation"]["source_provenance"],
    ):
        provenance["source_url"] = forged_url
        provenance["source_urls"] = [forged_url]
    _redigest_bundle(bundle, accepted, manifest)

    with pytest.raises(RegistryPromotionPlanError, match="frozen SABIO-RK fetch metadata"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


def test_input_mutation_after_authoring_does_not_change_result(tmp_path: Path) -> None:
    source, registry_index, target, authored = _author(tmp_path)
    target["value"]["value"] = 9.0
    source_record = source.accepted_records[0]
    source_payload = cast(dict[str, Any], source_record.proposed_record)
    source_payload["converted_value"] = 8.0

    result_payload = authored.records[0].proposed_record
    assert result_payload["value"]["value"] == 0.13
    assert result_payload["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY]["source_parameter"][
        "converted_value"
    ] == 0.13
    assert plan_registry_promotion(authored, registry_index=registry_index).summary()[
        "addable_count"
    ] == 1


def test_mutating_authored_result_is_rejected_before_write_and_plan(tmp_path: Path) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    payload = cast(dict[str, Any], authored.records[0].proposed_record)
    payload["value"]["notes"] = "Mutated result."

    with pytest.raises(ParameterRecordAuthoringError, match="changed after construction"):
        authored.write(tmp_path / "must_not_exist")
    assert not (tmp_path / "must_not_exist").exists()
    with pytest.raises(RegistryPromotionPlanError, match="changed after construction"):
        plan_registry_promotion(authored, registry_index=registry_index)


@pytest.mark.parametrize(
    "replacement",
    [True, 1, "0.13", float("nan"), float("inf")],
)
def test_target_rejects_bool_coercion_strings_integers_and_nonfinite_values(
    tmp_path: Path,
    replacement: Any,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["value"]["value"] = replacement

    with pytest.raises(ParameterRecordAuthoringError, match="explicit finite float"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize("field", ["environment_id", "range_scope", "allowed_use"])
def test_target_requires_all_always_emitted_parameter_fields(tmp_path: Path, field: str) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    del target[field]

    with pytest.raises(ParameterRecordAuthoringError, match="complete loader-emitted schema"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_target_requires_complete_exact_value_spec_without_defaults(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    del target["value"]["lower"]

    with pytest.raises(ParameterRecordAuthoringError, match="every ValueSpec field"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize("kind", ["unknown", "range", "distribution"])
def test_target_rejects_nonexact_value_specs(tmp_path: Path, kind: str) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["value"]["kind"] = kind

    with pytest.raises(ParameterRecordAuthoringError, match="exact ValueSpec targets only"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_target_rejects_value_or_unit_mismatch(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["value"]["units"] = "1 / minute"

    with pytest.raises(ParameterRecordAuthoringError, match="converted_units"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )

    target = _canonical_parameter_target(source)
    target["parameter_symbol"] = "Km_cellobiose"
    with pytest.raises(ParameterRecordAuthoringError, match="selected source record"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_nonidentity_conversion_is_explicitly_deferred(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    selected = source.accepted_records[0]
    proposed = deepcopy(dict(selected.proposed_record))
    proposed["conversion_method"] = "multiply_seconds_to_minutes"
    changed = replace(selected, proposed_record=proposed)
    source = replace(
        source,
        records=tuple(changed if item.record_id == SOURCE_PARAMETER_ID else item for item in source.records),
    )
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)

    with pytest.raises(ParameterRecordAuthoringError, match="nonidentity is deferred"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_source_original_and_normalized_fields_must_match_exactly(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    selected = source.accepted_records[0]
    proposed = deepcopy(dict(selected.proposed_record))
    proposed["original_value"] = 0.14
    changed = replace(selected, proposed_record=proposed)
    source = replace(
        source,
        records=tuple(changed if item.record_id == SOURCE_PARAMETER_ID else item for item in source.records),
    )
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)

    with pytest.raises(
        ParameterRecordAuthoringError,
        match="exact source/original/normalized/converted correspondence",
    ):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


@pytest.mark.parametrize("replacement", [True, 1, "0.13", float("nan")])
def test_source_rejects_implicit_or_nonfinite_numeric_values(
    tmp_path: Path,
    replacement: Any,
) -> None:
    source = _accepted_source_curation(tmp_path)
    selected = source.accepted_records[0]
    proposed = deepcopy(dict(selected.proposed_record))
    proposed["source_value"] = replacement
    changed = replace(selected, proposed_record=proposed)
    source = replace(
        source,
        records=tuple(changed if item.record_id == SOURCE_PARAMETER_ID else item for item in source.records),
    )
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)

    with pytest.raises(ParameterRecordAuthoringError, match="explicit finite float"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_missing_or_inconsistent_source_identity_is_rejected(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    selected = source.accepted_records[0]
    source_provenance = deepcopy(dict(selected.source_provenance))
    source_provenance["source_entry_ids"] = ["99999"]
    changed = replace(selected, source_provenance=source_provenance)
    source = replace(
        source,
        records=tuple(changed if item.record_id == SOURCE_PARAMETER_ID else item for item in source.records),
    )
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)

    with pytest.raises(ParameterRecordAuthoringError, match="provenance disagree"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_source_snapshot_digest_must_match_frozen_bytes(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    selected = source.accepted_records[0]
    proposed = deepcopy(dict(selected.proposed_record))
    proposed_provenance = cast(dict[str, Any], proposed["provenance"])
    proposed_provenance["source_snapshot_sha256"] = "0" * 64
    source_provenance = deepcopy(dict(selected.source_provenance))
    source_provenance["source_snapshot_sha256"] = "0" * 64
    changed = replace(
        selected,
        proposed_record=proposed,
        source_provenance=source_provenance,
    )
    source = replace(
        source,
        records=tuple(changed if item.record_id == SOURCE_PARAMETER_ID else item for item in source.records),
    )
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)

    with pytest.raises(ParameterRecordAuthoringError, match="snapshot checksum mismatch"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_target_provenance_must_preserve_full_source_identity_and_curator(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["provenance"]["source_query"] = "SabioReactionID:999"

    with pytest.raises(ParameterRecordAuthoringError, match="preserve every source identity field"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )

    target = _canonical_parameter_target(source)
    target["provenance"]["source_url"] = "https://example.test/forged"
    with pytest.raises(ParameterRecordAuthoringError, match="preserve every source identity field"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source_reaction_id", "35622"),
        ("selected_kinlaw_entry_id", "618"),
    ],
)
def test_singular_source_identity_aliases_cannot_be_swapped(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["provenance"][field] = replacement

    with pytest.raises(ParameterRecordAuthoringError, match="singular source identity aliases"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize("field", ["source_reaction_id", "selected_kinlaw_entry_id"])
def test_singular_source_identity_aliases_are_mandatory(tmp_path: Path, field: str) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    del target["provenance"][field]

    with pytest.raises(ParameterRecordAuthoringError, match="closed identity-only authoring schema"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize("reserved_key", [PARAMETER_BRIDGE_PROVENANCE_KEY, "fungmod_curation"])
def test_authoring_rejects_reserved_provenance_key_collisions(
    tmp_path: Path,
    reserved_key: str,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["provenance"][reserved_key] = {"attacker_supplied": True}

    with pytest.raises(ParameterRecordAuthoringError, match="reserved provenance"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize(
    "safety_field",
    [
        "production_registry_mutated",
        "registry_mutated",
        "scientific_validation_claimed",
        "simulation_authorized",
    ],
)
def test_authoring_rejects_outer_provenance_safety_claims(
    tmp_path: Path,
    safety_field: str,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["provenance"][safety_field] = False

    with pytest.raises(ParameterRecordAuthoringError, match="closed identity-only authoring schema"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize(
    ("field", "claim"),
    [
        ("confidence_level", "empirically_validated"),
        ("validation_status", "validated"),
        ("calibration_status", "calibrated"),
        ("empirically_validated", True),
        ("calibrated", True),
        ("simulation_ready", True),
        ("scientific_assessment", {"simulation_ready": True}),
    ],
)
def test_authoring_closed_provenance_rejects_scientific_claim_aliases(
    tmp_path: Path,
    field: str,
    claim: Any,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["provenance"][field] = claim

    with pytest.raises(ParameterRecordAuthoringError, match="closed identity-only authoring schema"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_authoring_closed_provenance_accepts_owned_identity_metadata(
    tmp_path: Path,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    authored = author_parameter_record(
        source,
        source_record_id=SOURCE_PARAMETER_ID,
        parameter_record=_canonical_parameter_target(source),
        registry_index=registry_index,
    )

    plan = plan_registry_promotion(authored, registry_index=registry_index)

    assert plan.summary()["addable_count"] == 1
    assert plan.summary()["apply_available"] is True


@pytest.mark.parametrize(
    ("field", "claim"),
    [
        ("confidence_level", "empirically_validated"),
        ("validation_status", "validated"),
        ("calibration_status", "calibrated"),
        ("simulation_ready", True),
        ("scientific_assessment", {"simulation_ready": True}),
    ],
)
def test_rechecksummed_claim_alias_cannot_become_addable_promotion(
    tmp_path: Path,
    field: str,
    claim: Any,
) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    bundle = authored.write(tmp_path / f"forged_outer_claim_{field}")
    accepted, manifest = _bundle_payloads(bundle)
    accepted["records"][0]["provenance"][field] = claim
    _redigest_bundle(bundle, accepted, manifest)

    with pytest.raises(
        RegistryPromotionPlanError,
        match="closed identity-only authoring schema|shared curation builder",
    ):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


def test_conservative_maturity_and_allowed_use_are_closed_policies(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["allowed_use"] = "scientific_simulation_and_validation"

    with pytest.raises(
        ParameterRecordAuthoringError,
        match="maturity, allowed-use, and range policies are closed",
    ):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )

    target = _canonical_parameter_target(source)
    target["value"]["confidence_level"] = "validated"
    with pytest.raises(ParameterRecordAuthoringError, match="identity transcription without validation"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )

    target = _canonical_parameter_target(source)
    target["maturity"] = "validated"
    with pytest.raises(
        ParameterRecordAuthoringError,
        match="maturity, allowed-use, and range policies are closed",
    ):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_loader_round_trip_coercion_and_unknown_fields_are_rejected(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["aliases"] = "canonical-kcat"

    with pytest.raises(ParameterRecordAuthoringError, match="changed during production-loader"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )

    target = _canonical_parameter_target(source)
    target["unsupported_field"] = "must not be dropped"
    with pytest.raises(ParameterRecordAuthoringError, match="unknown=.*unsupported_field"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("enzyme_class", "missing_enzyme", "Unknown authored enzyme_class"),
        ("substrate_id", "missing_substrate", "Unknown substrate registry record"),
        ("environment_id", "missing_environment", "Unknown environment registry record"),
    ],
)
def test_nonnull_selectors_must_resolve(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target[field] = value

    with pytest.raises(ParameterRecordAuthoringError, match=message):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_selector_combination_and_parameter_role_must_be_compatible(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    selected = source.accepted_records[0]
    proposed = deepcopy(dict(selected.proposed_record))
    proposed["parameter_symbol"] = "not_required_by_process"
    changed = replace(selected, proposed_record=proposed)
    source = replace(
        source,
        records=tuple(changed if item.record_id == SOURCE_PARAMETER_ID else item for item in source.records),
    )
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["parameter_symbol"] = "not_required_by_process"

    with pytest.raises(ParameterRecordAuthoringError, match="exactly one effective process compatibility"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_parameter_symbol_under_a_different_role_key_is_not_compatible(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    process_path = registry_index.parent / "processes" / "process_compatibility.yml"
    payload = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    compatibility = next(
        item
        for item in payload["records"]
        if item["record_id"] == "beta_glucosidase_cellobiose_homogeneous_mm"
    )
    compatibility["parameter_roles"]["turnover"] = compatibility["parameter_roles"].pop("kcat")
    process_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ParameterRecordAuthoringError, match="exactly one effective process compatibility"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(source),
            registry_index=registry_index,
        )


def test_null_class_selectors_resolve_from_entity_ids(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["enzyme_class"] = None
    target["substrate_class"] = None

    authored = author_parameter_record(
        source,
        source_record_id=SOURCE_PARAMETER_ID,
        parameter_record=target,
        registry_index=registry_index,
    )

    assert authored.records[0].proposed_record["enzyme_class"] is None
    assert authored.records[0].proposed_record["substrate_class"] is None


def test_null_classes_cannot_borrow_unrelated_compatibility(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["fungus_id"] = "toy_fungus_alpha"
    target["enzyme_class"] = None
    target["substrate_class"] = None

    with pytest.raises(ParameterRecordAuthoringError, match="exactly one effective process compatibility"):
        author_parameter_record(
            source,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=target,
            registry_index=registry_index,
        )


def test_planning_rejects_effective_compatibility_registry_drift(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["enzyme_class"] = None
    target["substrate_class"] = None
    authored = author_parameter_record(
        source,
        source_record_id=SOURCE_PARAMETER_ID,
        parameter_record=target,
        registry_index=registry_index,
    )
    bundle = authored.write(tmp_path / "authored_before_registry_drift")
    process_path = registry_index.parent / "processes" / "process_compatibility.yml"
    process_payload = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    matching = next(
        item
        for item in process_payload["records"]
        if item["process_type"] == "homogeneous_michaelis_menten"
        and item["enzyme_class"] == "beta_glucosidase"
        and item["substrate_class"] == "cellobiose"
    )
    duplicate = deepcopy(matching)
    duplicate["record_id"] = "drifted_duplicate_beta_glucosidase_cellobiose"
    process_payload["records"].append(duplicate)
    process_path.write_text(yaml.safe_dump(process_payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(RegistryPromotionPlanError, match="invalid before planning"):
        plan_registry_promotion(authored, registry_index=registry_index)
    with pytest.raises(RegistryPromotionPlanError, match="invalid before planning"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


@pytest.mark.parametrize("drift", ["coherent_entity_reclassification", "parameter_role_rename"])
def test_full_registry_and_exact_role_context_rejects_planning_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    target = _canonical_parameter_target(source)
    target["enzyme_class"] = None
    target["substrate_class"] = None
    authored = author_parameter_record(
        source,
        source_record_id=SOURCE_PARAMETER_ID,
        parameter_record=target,
        registry_index=registry_index,
    )
    bundle = authored.write(tmp_path / f"before_{drift}")
    audit = authored.records[0].proposed_record["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY]
    assert audit["selector_resolution"]["effective_enzyme_classes"] == ["beta_glucosidase"]
    assert audit["selector_resolution"]["parameter_role"] == "kcat"
    assert (
        audit["selector_resolution"]["process_compatibility_id"]
        == "beta_glucosidase_cellobiose_homogeneous_mm"
    )

    process_path = registry_index.parent / "processes" / "process_compatibility.yml"
    process_payload = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    compatibility = next(
        item
        for item in process_payload["records"]
        if item["record_id"] == "beta_glucosidase_cellobiose_homogeneous_mm"
    )
    if drift == "coherent_entity_reclassification":
        fungi_path = registry_index.parent / "fungi" / "fungi.yml"
        fungi_payload = yaml.safe_load(fungi_path.read_text(encoding="utf-8"))
        fungus = next(
            item
            for item in fungi_payload["records"]
            if item["record_id"] == "sabiork_beta_glucosidase_source"
        )
        fungus["enzyme_classes"] = ["toy_cellulase"]
        compatibility["enzyme_class"] = "toy_cellulase"
        fungi_path.write_text(yaml.safe_dump(fungi_payload, sort_keys=False), encoding="utf-8")
    else:
        compatibility["parameter_roles"]["turnover"] = compatibility["parameter_roles"].pop("kcat")
    process_path.write_text(yaml.safe_dump(process_payload, sort_keys=False), encoding="utf-8")

    for planning_input in (authored, bundle.output_directory):
        with pytest.raises(RegistryPromotionPlanError, match="registry context"):
            plan_registry_promotion(planning_input, registry_index=registry_index)


def test_deferred_rejected_blocked_and_unsupported_sources_are_rejected(tmp_path: Path) -> None:
    incomplete = review_source_proposal(_proposal())
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    with pytest.raises(
        ParameterRecordAuthoringError,
        match="not an explicit unblocked accepted curation decision",
    ):
        author_parameter_record(
            incomplete,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(_accepted_source_curation(tmp_path / "accepted")),
            registry_index=registry_index,
        )

    accepted = _accepted_source_curation(tmp_path / "accepted_two")
    selected = accepted.accepted_records[0]
    rejected = replace(
        selected,
        decision="reject",
        allowed_use=CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    )
    rejected_result = replace(
        accepted,
        records=tuple(rejected if item.record_id == SOURCE_PARAMETER_ID else item for item in accepted.records),
    )
    with pytest.raises(
        ParameterRecordAuthoringError,
        match="not an explicit unblocked accepted curation decision",
    ):
        author_parameter_record(
            rejected_result,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(accepted),
            registry_index=registry_index,
        )

    blocked = replace(selected, classification="blocked_excluded", reasons=("blocked",))
    blocked_result = replace(
        accepted,
        records=tuple(blocked if item.record_id == SOURCE_PARAMETER_ID else item for item in accepted.records),
    )
    with pytest.raises(
        ParameterRecordAuthoringError,
        match="not an explicit unblocked accepted curation decision",
    ):
        author_parameter_record(
            blocked_result,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(accepted),
            registry_index=registry_index,
        )

    unsupported = replace(selected, record_type="fungi")
    unsupported_result = replace(
        accepted,
        records=tuple(unsupported if item.record_id == SOURCE_PARAMETER_ID else item for item in accepted.records),
    )
    with pytest.raises(ParameterRecordAuthoringError, match="supports accepted parameter_records only"):
        author_parameter_record(
            unsupported_result,
            source_record_id=SOURCE_PARAMETER_ID,
            parameter_record=_canonical_parameter_target(accepted),
            registry_index=registry_index,
        )


def test_output_paths_reject_traversal_symlinks_unowned_and_registry_paths(
    tmp_path: Path,
) -> None:
    _, _, _, authored = _author(tmp_path)
    with pytest.raises(CurationError, match="traversal"):
        authored.write(tmp_path / ".." / "escape")

    real_parent = tmp_path / "real_parent"
    real_parent.mkdir()
    link = tmp_path / "linked_parent"
    link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(CurationError, match="symlink component"):
        authored.write(link / "output")

    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(CurationError, match="owned curation manifest"):
        authored.write(unowned)
    assert (unowned / "keep.txt").read_text(encoding="utf-8") == "keep"

    with pytest.raises(CurationError, match="data_registry"):
        authored.write(DATA_REGISTRY / "forbidden_parameter_authoring_output")
    assert not (DATA_REGISTRY / "forbidden_parameter_authoring_output").exists()


def test_planning_registry_context_and_selectors_are_revalidated(tmp_path: Path) -> None:
    _, registry_index, _, authored = _author(tmp_path)
    audit = cast(
        dict[str, Any],
        authored.records[0].proposed_record["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY],
    )
    audit["registry_context"]["registry_version"] = "999.0.0"

    with pytest.raises(RegistryPromotionPlanError, match="changed after construction"):
        plan_registry_promotion(authored, registry_index=registry_index)


def test_public_exports_are_parameter_specific() -> None:
    assert fungal_model.author_parameter_record is author_parameter_record
    assert fungal_model.CuratorAuthoredParameterResult is CuratorAuthoredParameterResult
    assert fungal_model.ParameterRecordAuthoringError is ParameterRecordAuthoringError
    assert not hasattr(fungal_model, "author_registry_record")


def _bundle_payloads(bundle: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted = yaml.safe_load(bundle.paths["accepted_registry_records"].read_text(encoding="utf-8"))
    manifest = json.loads(bundle.paths["curation_manifest"].read_text(encoding="utf-8"))
    assert isinstance(accepted, dict) and isinstance(manifest, dict)
    return accepted, manifest


def _redigest_bundle(
    bundle: Any,
    accepted: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    record = deepcopy(accepted["records"][0])
    curation = record.pop("curation")
    summary = manifest["summary"]
    digest = parameter_authoring_digest(
        record,
        curation,
        source_record_id=summary["source_record_id"],
        source_query=summary["source_query"],
        source_snapshot_path=summary["source_snapshot_path"],
        proposal_limitations=tuple(summary["proposal_limitations"]),
    )
    summary["authoring_digest"] = digest
    accepted["records"][0]["provenance"][PARAMETER_BRIDGE_PROVENANCE_KEY][
        "authoring_digest"
    ] = digest
    accepted_path = bundle.paths["accepted_registry_records"]
    accepted_path.write_text(yaml.safe_dump(accepted, sort_keys=False), encoding="utf-8")
    manifest["files"] = {
        name: hashlib.sha256((bundle.output_directory / name).read_bytes()).hexdigest()
        for name in manifest["files"]
    }
    bundle.paths["curation_manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _mutate_semantic_bundle_artifact(bundle: Any, artifact: str) -> None:
    yaml_paths = {
        "proposed": bundle.paths["proposed_registry_records"],
        "accepted": bundle.paths["accepted_registry_records"],
        "rejected": bundle.paths["rejected_registry_records"],
    }
    if artifact in yaml_paths:
        path = yaml_paths[artifact]
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        payload["simulation_authorized"] = True
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return
    if artifact in {"eligible_decisions", "excluded_decisions"}:
        key = "eligible_records" if artifact == "eligible_decisions" else "excluded_records"
        path = bundle.paths[key]
        content = path.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in content else "\n"
        lines = content.splitlines()
        lines[0] += ",simulation_authorized"
        for index in range(1, len(lines)):
            lines[index] += ",true"
        path.write_bytes((newline.join(lines) + newline).encode("utf-8"))
        return
    if artifact == "manifest":
        path = bundle.paths["curation_manifest"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["simulation_authorized"] = True
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    if artifact == "report":
        path = bundle.paths["curation_report"]
        content = path.read_text(encoding="utf-8").replace(
            "It is not production registry promotion, scientific validation, or permission for simulation.",
            "It is scientific validation and permission for simulation.",
        )
        path.write_text(content, encoding="utf-8")
        return
    raise AssertionError(f"Unknown semantic artifact fixture: {artifact}")


def _refresh_bundle_checksums(bundle: Any) -> None:
    path = bundle.paths["curation_manifest"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"] = {
        name: hashlib.sha256((bundle.output_directory / name).read_bytes()).hexdigest()
        for name in manifest["files"]
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _reconstructed_plan_with_target(plan: Any, registry_index: Path, target: dict[str, Any]):
    index = promotion_module._load_registry_index(registry_index)
    registry_target = index.targets["parameters"]
    content = promotion_module._merged_target_content(registry_target, (target,))
    after_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    candidate = replace(
        plan.addable_records[0],
        target_record=deepcopy(target),
        after_sha256=after_sha256,
    )
    prospective = replace(
        plan.prospective_files[0],
        content=content,
        after_sha256=after_sha256,
    )
    prospective_digest = promotion_module._registry_digest(
        index,
        overrides={registry_target.relative_path: content},
    )
    reconstructed = replace(
        plan,
        candidates=(candidate,),
        prospective_files=(prospective,),
        prospective_registry_digest=prospective_digest,
    )
    payload = promotion_module._plan_digest_payload(
        input_kind=reconstructed.input_kind,
        registry_index_path=reconstructed.registry_index_path,
        registry_root=reconstructed.registry_root,
        registry_index_sha256=reconstructed.registry_index_sha256,
        before_registry_digest=reconstructed.before_registry_digest,
        prospective_registry_digest=reconstructed.prospective_registry_digest,
        candidates=reconstructed.candidates,
        prospective_files=reconstructed.prospective_files,
    )
    return replace(reconstructed, plan_digest=promotion_module._sha256_json(payload))
