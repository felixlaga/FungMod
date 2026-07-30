from __future__ import annotations

import base64
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import fungal_model
from fungal_model.api.curation import (
    CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
    CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
    CurationRecord,
    CurationResult,
)
from fungal_model.api.curator_signatures import (
    CURATOR_SIGNATURE_ALGORITHM,
    AuthenticatedCurationBundle,
    CuratorSignatureError,
    TrustedCuratorKey,
    load_authenticated_curation_bundle,
    sign_curation_bundle,
)
from fungal_model.api.registry_promotion import plan_registry_promotion
from fungal_model.api.registry_record_authoring import author_registry_records
from fungal_model.sources.sabiork import PROPOSAL_STATUS


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
CURATOR_ID = "Dr Curator"
KEY_ID = "dr-curator-ed25519-2026"


def _source_provenance() -> dict[str, object]:
    return {
        "source_database": "signature-test-source",
        "source_query": "signature contract fixture",
        "source_entry_ids": ["source_fungus"],
        "source_snapshot_path": "tests/fixtures/signature-source.yml",
        "source_url": None,
        "proposal_status": PROPOSAL_STATUS,
        "notes": "Review-only signature fixture; not scientific data.",
    }


def _source_result(*, curator: str | None = CURATOR_ID) -> CurationResult:
    provenance = _source_provenance()
    source = CurationRecord(
        record_type="fungi",
        record_id="source_fungus",
        proposed_record={
            "record_id": "source_fungus",
            "proposal_status": PROPOSAL_STATUS,
            "review_required": True,
            "allowed_use": CURATION_DECISION_ALLOWED_USE_REVIEW_ONLY,
            "scientific_name": "Testus signatureensis",
            "enzyme_classes": ["test_enzyme"],
            "provenance": deepcopy(provenance),
        },
        classification="eligible_for_review",
        missing_fields=(),
        reasons=(),
        decision="accept",
        explicit_decision=True,
        curator=curator,
        decision_reason="Explicit signature contract acceptance.",
        curation_date="2026-07-30",
        allowed_use=CURATION_DECISION_ALLOWED_USE_PENDING_PROMOTION,
        limitations=("Signature contract fixture only.",),
        source_provenance=provenance,
    )
    return CurationResult(
        source_query="signature contract fixture",
        source_snapshot_path="tests/fixtures/signature-source.yml",
        proposal_limitations=("No scientific validation is claimed.",),
        records=(source,),
    )


def _target() -> dict[str, object]:
    return {
        "record_id": "authored_signature_fungus",
        "name": "Authored signature fungus fixture",
        "scientific_name": "Testus signatureensis",
        "maturity": "literature_metadata",
        "provenance": _source_provenance(),
        "notes": "Storage and signature contract fixture only.",
        "enzyme_classes": ["test_enzyme"],
        "assimilable_products": [],
    }


def _key_and_trust() -> tuple[Ed25519PrivateKey, TrustedCuratorKey]:
    private_key = Ed25519PrivateKey.generate()
    trusted_key = TrustedCuratorKey.from_public_key(
        curator_id=CURATOR_ID,
        key_id=KEY_ID,
        public_key=private_key.public_key(),
    )
    return private_key, trusted_key


def _signed_source(
    tmp_path: Path,
) -> tuple[AuthenticatedCurationBundle, Ed25519PrivateKey, TrustedCuratorKey]:
    written = _source_result().write(tmp_path / "source_curation")
    private_key, trusted_key = _key_and_trust()
    signature = sign_curation_bundle(
        written.output_directory,
        curator_id=CURATOR_ID,
        key_id=KEY_ID,
        private_key=private_key,
    )
    authenticated = load_authenticated_curation_bundle(
        written.output_directory,
        trusted_curator_keys={KEY_ID: trusted_key},
    )
    assert signature.signature_path == authenticated.signature_path
    assert signature.signature_path.parent == written.output_directory.parent
    assert signature.signature_path.parent != written.output_directory
    return authenticated, private_key, trusted_key


def test_authenticated_source_revalidates_for_authoring_and_promotion(
    tmp_path: Path,
) -> None:
    authenticated, private_key, trusted_key = _signed_source(tmp_path)

    authored = author_registry_records(
        authenticated,
        registry_records={"source_fungus": _target()},
    )
    written = authored.write(tmp_path / "authored_curation")
    sign_curation_bundle(
        written.output_directory,
        curator_id=CURATOR_ID,
        key_id=KEY_ID,
        private_key=private_key,
    )
    authenticated_authored = load_authenticated_curation_bundle(
        written.output_directory,
        trusted_curator_keys={KEY_ID: trusted_key},
    )
    plan = plan_registry_promotion(authenticated_authored, REGISTRY_INDEX)

    assert plan.addable_records[0].record_id == "authored_signature_fungus"
    assert authenticated.verification.algorithm == CURATOR_SIGNATURE_ALGORITHM
    assert authenticated.verification.curator_id == CURATOR_ID
    assert authenticated.verification.key_id == KEY_ID
    assert authenticated.verification.production_registry_mutated is False
    assert authenticated.verification.scientific_validation_claimed is False
    assert authenticated.verification.simulation_authorized is False
    assert authenticated.reload().verification == authenticated.verification


def test_signature_sidecar_authenticates_exact_manifest_bytes(tmp_path: Path) -> None:
    authenticated, _, trusted_key = _signed_source(tmp_path)
    manifest = authenticated.bundle.manifest_path
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        CuratorSignatureError,
        match="does not bind the current manifest bytes",
    ):
        load_authenticated_curation_bundle(
            manifest,
            trusted_curator_keys={KEY_ID: trusted_key},
        )


def test_authenticated_load_rejects_owned_artifact_checksum_drift(
    tmp_path: Path,
) -> None:
    authenticated, _, trusted_key = _signed_source(tmp_path)
    artifact = authenticated.bundle.paths["proposed_registry_records"]
    artifact.write_text(
        artifact.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checksum"):
        load_authenticated_curation_bundle(
            authenticated.bundle.manifest_path,
            trusted_curator_keys={KEY_ID: trusted_key},
        )


def test_signature_bytes_and_untrusted_keys_fail_closed(tmp_path: Path) -> None:
    authenticated, _, trusted_key = _signed_source(tmp_path)
    payload = json.loads(
        authenticated.signature_path.read_text(encoding="utf-8")
    )
    signature = bytearray(base64.b64decode(payload["signature_base64"]))
    signature[0] ^= 1
    payload["signature_base64"] = base64.b64encode(signature).decode("ascii")
    authenticated.signature_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CuratorSignatureError, match="verification failed"):
        load_authenticated_curation_bundle(
            authenticated.bundle.manifest_path,
            trusted_curator_keys={KEY_ID: trusted_key},
        )

    other_private = Ed25519PrivateKey.generate()
    other_trust = TrustedCuratorKey.from_public_key(
        curator_id=CURATOR_ID,
        key_id="other-key",
        public_key=other_private.public_key(),
    )
    with pytest.raises(CuratorSignatureError, match="is not trusted"):
        load_authenticated_curation_bundle(
            authenticated.bundle.manifest_path,
            trusted_curator_keys={"other-key": other_trust},
        )


def test_signature_envelope_cannot_claim_validation_or_authorization(
    tmp_path: Path,
) -> None:
    authenticated, _, trusted_key = _signed_source(tmp_path)
    payload = json.loads(
        authenticated.signature_path.read_text(encoding="utf-8")
    )
    payload["scientific_validation_claimed"] = True
    authenticated.signature_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        CuratorSignatureError,
        match="scientific_validation_claimed.*invalid",
    ):
        load_authenticated_curation_bundle(
            authenticated.bundle.manifest_path,
            trusted_curator_keys={KEY_ID: trusted_key},
        )


def test_signing_identity_must_match_every_explicit_decision(
    tmp_path: Path,
) -> None:
    written = _source_result(curator="Different Curator").write(
        tmp_path / "different_curator"
    )
    private_key, _ = _key_and_trust()

    with pytest.raises(
        CuratorSignatureError,
        match="match every explicit decision curator",
    ):
        sign_curation_bundle(
            written.output_directory,
            curator_id=CURATOR_ID,
            key_id=KEY_ID,
            private_key=private_key,
        )


def test_signing_identity_also_binds_explicit_defer_decisions(
    tmp_path: Path,
) -> None:
    source = _source_result()
    explicit_defer = replace(
        source.records[0],
        decision="defer",
        curator="Different Curator",
    )
    written = replace(source, records=(explicit_defer,)).write(
        tmp_path / "explicit_defer"
    )
    private_key, _ = _key_and_trust()

    with pytest.raises(
        CuratorSignatureError,
        match="match every explicit decision curator",
    ):
        sign_curation_bundle(
            written.output_directory,
            curator_id=CURATOR_ID,
            key_id=KEY_ID,
            private_key=private_key,
        )


def test_curator_signature_api_is_available_from_package_root() -> None:
    assert fungal_model.sign_curation_bundle is sign_curation_bundle
    assert (
        fungal_model.load_authenticated_curation_bundle
        is load_authenticated_curation_bundle
    )
    assert fungal_model.TrustedCuratorKey is TrustedCuratorKey
