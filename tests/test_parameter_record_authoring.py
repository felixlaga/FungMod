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
from fungal_model import (
    CurationDecision,
    CurationError,
    CurationResult,
    CuratorAuthoredParameterResult,
    ParameterRecordAuthoringError,
    RegistryPromotionPlanError,
    author_parameter_record,
    plan_registry_promotion,
    review_source_proposal,
    source_proposal,
)
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
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


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "source_snapshots" / "sabiork"
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


def _write_proposal_manifest(path: Path, payload: MappingLike) -> Path:
    path.mkdir(parents=True)
    manifest = path / "proposal_manifest.json"
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return manifest


MappingLike = dict[str, Any]


def _accepted_source_curation(tmp_path: Path) -> CurationResult:
    payload = _proposal().to_dict()
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
    assert bridge["source_parameter"] == {
        "parameter_symbol": "kcat_cellobiose",
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
    assert candidate.target_record["provenance"]["fungmod_curation"]["curator"] == CURATOR
    assert _registry_snapshot(registry_index.parent) == copied_before
    assert _registry_snapshot() == production_before


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

    with pytest.raises(ParameterRecordAuthoringError, match="singular source identity aliases"):
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


def test_required_parameter_without_explicit_role_is_not_compatible(tmp_path: Path) -> None:
    source = _accepted_source_curation(tmp_path)
    registry_index = _copy_registry_without_canonical_parameter(tmp_path)
    process_path = registry_index.parent / "processes" / "process_compatibility.yml"
    payload = yaml.safe_load(process_path.read_text(encoding="utf-8"))
    compatibility = next(
        item
        for item in payload["records"]
        if item["record_id"] == "beta_glucosidase_cellobiose_homogeneous_mm"
    )
    del compatibility["parameter_roles"]["kcat"]
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

    with pytest.raises(RegistryPromotionPlanError, match="exactly one effective process compatibility"):
        plan_registry_promotion(authored, registry_index=registry_index)
    with pytest.raises(RegistryPromotionPlanError, match="exactly one effective process compatibility"):
        plan_registry_promotion(bundle.output_directory, registry_index=registry_index)


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
    accepted_path = bundle.paths["accepted_registry_records"]
    accepted_path.write_text(yaml.safe_dump(accepted, sort_keys=False), encoding="utf-8")
    record = deepcopy(accepted["records"][0])
    curation = record.pop("curation")
    summary = manifest["summary"]
    summary["authoring_digest"] = parameter_authoring_digest(
        record,
        curation,
        source_record_id=summary["source_record_id"],
        source_query=summary["source_query"],
        source_snapshot_path=summary["source_snapshot_path"],
        proposal_limitations=tuple(summary["proposal_limitations"]),
    )
    manifest["files"][accepted_path.name] = hashlib.sha256(accepted_path.read_bytes()).hexdigest()
    bundle.paths["curation_manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
