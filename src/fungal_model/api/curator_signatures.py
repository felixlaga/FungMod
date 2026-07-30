"""Ed25519 authentication for owned CURATION-001 artifact bundles."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from fungal_model.api.curation import LoadedCurationBundle, load_curation_bundle


CURATOR_SIGNATURE_SCHEMA_VERSION = "1.0.0"
CURATOR_SIGNATURE_KIND = "fungmod_curation_bundle_signature"
CURATOR_SIGNATURE_ALGORITHM = "ed25519"
_SIGNED_ARTIFACT = "curation_manifest.json"
_SIGNATURE_SUFFIX = ".curation-signature.json"
_DOMAIN_SEPARATOR = (
    b"FungMod CURATION-001 curation_manifest.json Ed25519 signature v1\x00"
)
_SIGNATURE_FIELDS = {
    "kind",
    "schema_version",
    "algorithm",
    "curator_id",
    "key_id",
    "public_key_sha256",
    "signed_artifact",
    "signed_artifact_sha256",
    "signature_base64",
    "production_registry_mutated",
    "scientific_validation_claimed",
    "simulation_authorized",
}


class CuratorSignatureError(ValueError):
    """Raised when curator signing or trusted verification fails."""


@dataclass(frozen=True)
class TrustedCuratorKey:
    """Caller-trusted binding from one curator identity to an Ed25519 key."""

    curator_id: str
    key_id: str
    public_key_pem: bytes

    def __post_init__(self) -> None:
        _canonical_identifier(self.curator_id, field_name="curator_id")
        _canonical_identifier(self.key_id, field_name="key_id")
        _load_public_key(self.public_key_pem)

    @classmethod
    def from_public_key(
        cls,
        *,
        curator_id: str,
        key_id: str,
        public_key: Ed25519PublicKey,
    ) -> "TrustedCuratorKey":
        """Create an explicit trust binding from an Ed25519 public key."""

        if not isinstance(public_key, Ed25519PublicKey):
            raise CuratorSignatureError(
                "Trusted curator keys must use Ed25519 public keys."
            )
        return cls(
            curator_id=curator_id,
            key_id=key_id,
            public_key_pem=public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )

    def public_key(self) -> Ed25519PublicKey:
        """Return the validated Ed25519 public key."""

        return _load_public_key(self.public_key_pem)

    @property
    def public_key_sha256(self) -> str:
        """Return a stable digest of the canonical DER public key."""

        return _public_key_sha256(self.public_key())


@dataclass(frozen=True)
class CuratorSignatureWriteResult:
    """Sidecar written for one exact curation manifest."""

    signature_path: Path
    curator_id: str
    key_id: str
    signed_artifact_sha256: str
    signature_sha256: str


@dataclass(frozen=True)
class CuratorSignatureVerification:
    """Verified curator identity and exact signed-manifest evidence."""

    curator_id: str
    key_id: str
    public_key_sha256: str
    signed_artifact_sha256: str
    signature_sha256: str
    algorithm: str = CURATOR_SIGNATURE_ALGORITHM
    schema_version: str = CURATOR_SIGNATURE_SCHEMA_VERSION
    production_registry_mutated: bool = False
    scientific_validation_claimed: bool = False
    simulation_authorized: bool = False


@dataclass(frozen=True)
class AuthenticatedCurationBundle:
    """Checksum-validated bundle plus trusted Ed25519 curator authentication."""

    bundle: LoadedCurationBundle
    signature_path: Path
    trusted_key: TrustedCuratorKey
    verification: CuratorSignatureVerification

    def reload(self) -> "AuthenticatedCurationBundle":
        """Reload current bytes and repeat checksum and signature verification."""

        return load_authenticated_curation_bundle(
            self.bundle.manifest_path,
            trusted_curator_keys={self.trusted_key.key_id: self.trusted_key},
        )


def sign_curation_bundle(
    bundle_or_manifest: str | Path,
    *,
    curator_id: str,
    key_id: str,
    private_key: Ed25519PrivateKey,
) -> CuratorSignatureWriteResult:
    """Sign the exact owned curation manifest with one Ed25519 private key.

    The signature sidecar is a sibling of the owned bundle directory so it
    cannot weaken the bundle's closed internal inventory. The manifest already
    binds every owned artifact checksum.
    """

    _canonical_identifier(curator_id, field_name="curator_id")
    _canonical_identifier(key_id, field_name="key_id")
    if not isinstance(private_key, Ed25519PrivateKey):
        raise CuratorSignatureError(
            "Curation bundle signing requires an Ed25519 private key object."
        )
    bundle, manifest_bytes = _load_bundle_with_stable_manifest(
        bundle_or_manifest
    )
    _validate_decision_curator(bundle, curator_id=curator_id)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    signature = private_key.sign(_signed_message(manifest_bytes))
    public_key = private_key.public_key()
    payload = {
        "kind": CURATOR_SIGNATURE_KIND,
        "schema_version": CURATOR_SIGNATURE_SCHEMA_VERSION,
        "algorithm": CURATOR_SIGNATURE_ALGORITHM,
        "curator_id": curator_id,
        "key_id": key_id,
        "public_key_sha256": _public_key_sha256(public_key),
        "signed_artifact": _SIGNED_ARTIFACT,
        "signed_artifact_sha256": manifest_sha256,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
    }
    signature_path = curation_bundle_signature_path(bundle.manifest_path)
    _write_signature_sidecar(signature_path, payload)
    return CuratorSignatureWriteResult(
        signature_path=signature_path,
        curator_id=curator_id,
        key_id=key_id,
        signed_artifact_sha256=manifest_sha256,
        signature_sha256=hashlib.sha256(signature).hexdigest(),
    )


def load_authenticated_curation_bundle(
    bundle_or_manifest: str | Path,
    *,
    trusted_curator_keys: Mapping[str, TrustedCuratorKey],
) -> AuthenticatedCurationBundle:
    """Load an owned bundle and authenticate its curator against caller trust."""

    if not isinstance(trusted_curator_keys, Mapping) or not trusted_curator_keys:
        raise CuratorSignatureError(
            "Authenticated loading requires at least one caller-trusted curator key."
        )
    if any(
        not isinstance(key_id, str)
        or not isinstance(trusted_key, TrustedCuratorKey)
        or key_id != trusted_key.key_id
        for key_id, trusted_key in trusted_curator_keys.items()
    ):
        raise CuratorSignatureError(
            "Trusted curator key mappings must use each TrustedCuratorKey.key_id."
        )

    bundle, manifest_bytes = _load_bundle_with_stable_manifest(
        bundle_or_manifest
    )
    signature_path = curation_bundle_signature_path(bundle.manifest_path)
    payload = _read_signature_sidecar(signature_path)
    curator_id = payload["curator_id"]
    key_id = payload["key_id"]
    assert isinstance(curator_id, str)
    assert isinstance(key_id, str)
    try:
        trusted_key = trusted_curator_keys[key_id]
    except KeyError as exc:
        raise CuratorSignatureError(
            f"Curation signature key {key_id!r} is not trusted by this caller."
        ) from exc
    if trusted_key.curator_id != curator_id:
        raise CuratorSignatureError(
            "Curation signature curator identity disagrees with the trusted key binding."
        )
    if not hmac.compare_digest(
        trusted_key.public_key_sha256,
        str(payload["public_key_sha256"]),
    ):
        raise CuratorSignatureError(
            "Curation signature public key disagrees with the trusted key binding."
        )

    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if not hmac.compare_digest(
        manifest_sha256,
        str(payload["signed_artifact_sha256"]),
    ):
        raise CuratorSignatureError(
            "Curation signature does not bind the current manifest bytes."
        )
    signature = _decode_signature(payload["signature_base64"])
    try:
        trusted_key.public_key().verify(signature, _signed_message(manifest_bytes))
    except InvalidSignature as exc:
        raise CuratorSignatureError(
            "Curation bundle Ed25519 signature verification failed."
        ) from exc
    reloaded_bundle, reloaded_manifest_bytes = _load_bundle_with_stable_manifest(
        bundle.manifest_path
    )
    if not hmac.compare_digest(manifest_bytes, reloaded_manifest_bytes):
        raise CuratorSignatureError(
            "Curation manifest changed during signature verification."
        )
    bundle = reloaded_bundle
    _validate_decision_curator(bundle, curator_id=curator_id)
    verification = CuratorSignatureVerification(
        curator_id=curator_id,
        key_id=key_id,
        public_key_sha256=trusted_key.public_key_sha256,
        signed_artifact_sha256=manifest_sha256,
        signature_sha256=hashlib.sha256(signature).hexdigest(),
    )
    return AuthenticatedCurationBundle(
        bundle=bundle,
        signature_path=signature_path,
        trusted_key=trusted_key,
        verification=verification,
    )


def curation_bundle_signature_path(bundle_or_manifest: str | Path) -> Path:
    """Return the deterministic sibling signature path for one bundle."""

    value = Path(bundle_or_manifest)
    manifest = value / _SIGNED_ARTIFACT if value.is_dir() else value
    if manifest.name != _SIGNED_ARTIFACT:
        raise CuratorSignatureError(
            "Curation signature input must be a bundle directory or "
            "curation_manifest.json."
        )
    try:
        manifest = manifest.resolve(strict=True)
    except OSError as exc:
        raise CuratorSignatureError(
            f"Curation manifest does not exist: {manifest}"
        ) from exc
    bundle_root = manifest.parent
    return bundle_root.with_name(f"{bundle_root.name}{_SIGNATURE_SUFFIX}")


def _validate_decision_curator(
    bundle: LoadedCurationBundle,
    *,
    curator_id: str,
) -> None:
    explicit = tuple(
        record
        for record in bundle.result.records
        if record.explicit_decision
    )
    if not explicit:
        raise CuratorSignatureError(
            "A curator signature requires at least one explicit curation decision."
        )
    mismatched = tuple(
        record.record_id for record in explicit if record.curator != curator_id
    )
    if mismatched:
        raise CuratorSignatureError(
            "Curation signature identity must match every explicit decision curator: "
            + ", ".join(sorted(mismatched))
        )


def _load_bundle_with_stable_manifest(
    bundle_or_manifest: str | Path,
) -> tuple[LoadedCurationBundle, bytes]:
    bundle = load_curation_bundle(bundle_or_manifest)
    try:
        manifest_bytes = bundle.manifest_path.read_bytes()
        parsed_manifest = json.loads(manifest_bytes)
        repeated_bytes = bundle.manifest_path.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise CuratorSignatureError(
            "Curation manifest could not be read consistently for signing."
        ) from exc
    if parsed_manifest != bundle.manifest or not hmac.compare_digest(
        manifest_bytes,
        repeated_bytes,
    ):
        raise CuratorSignatureError(
            "Curation manifest changed during checksum validation."
        )
    return bundle, manifest_bytes


def _read_signature_sidecar(path: Path) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CuratorSignatureError(
            f"Owned curator-signature sidecar does not exist as a regular file: {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CuratorSignatureError(
            f"Malformed curator-signature sidecar {path}: {exc}"
        ) from exc
    if not isinstance(payload, Mapping) or set(payload) != _SIGNATURE_FIELDS:
        raise CuratorSignatureError(
            "Curator-signature fields do not match the owned schema."
        )
    expected = {
        "kind": CURATOR_SIGNATURE_KIND,
        "schema_version": CURATOR_SIGNATURE_SCHEMA_VERSION,
        "algorithm": CURATOR_SIGNATURE_ALGORITHM,
        "signed_artifact": _SIGNED_ARTIFACT,
        "production_registry_mutated": False,
        "scientific_validation_claimed": False,
        "simulation_authorized": False,
    }
    for field_name, value in expected.items():
        if payload.get(field_name) != value:
            raise CuratorSignatureError(
                f"Curator-signature field {field_name!r} is invalid."
            )
    for field_name in (
        "curator_id",
        "key_id",
        "public_key_sha256",
        "signed_artifact_sha256",
        "signature_base64",
    ):
        _canonical_identifier(payload.get(field_name), field_name=field_name)
    for field_name in ("public_key_sha256", "signed_artifact_sha256"):
        value = payload[field_name]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise CuratorSignatureError(
                f"Curator-signature field {field_name!r} must be lowercase SHA-256."
            )
    return payload


def _write_signature_sidecar(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _read_signature_sidecar(path)
        if existing.get("kind") != CURATOR_SIGNATURE_KIND:
            raise CuratorSignatureError(
                f"Refusing to replace an unowned signature path: {path}"
            )
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _decode_signature(value: Any) -> bytes:
    if not isinstance(value, str):
        raise CuratorSignatureError(
            "Curator-signature signature_base64 must be text."
        )
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CuratorSignatureError(
            "Curator-signature signature_base64 is malformed."
        ) from exc
    if len(signature) != 64:
        raise CuratorSignatureError(
            "An Ed25519 signature must contain exactly 64 bytes."
        )
    return signature


def _load_public_key(value: bytes) -> Ed25519PublicKey:
    if not isinstance(value, bytes) or not value:
        raise CuratorSignatureError(
            "Trusted curator public_key_pem must be nonempty bytes."
        )
    try:
        public_key = serialization.load_pem_public_key(value)
    except (TypeError, ValueError) as exc:
        raise CuratorSignatureError(
            "Trusted curator public_key_pem is not a valid PEM public key."
        ) from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise CuratorSignatureError(
            "Trusted curator public_key_pem must contain an Ed25519 public key."
        )
    return public_key


def _public_key_sha256(public_key: Ed25519PublicKey) -> str:
    return hashlib.sha256(
        public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).hexdigest()


def _signed_message(manifest_bytes: bytes) -> bytes:
    return _DOMAIN_SEPARATOR + manifest_bytes


def _canonical_identifier(value: Any, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise CuratorSignatureError(
            f"{field_name} must be canonical nonblank text without control characters."
        )
    return value


__all__ = [
    "AuthenticatedCurationBundle",
    "CURATOR_SIGNATURE_ALGORITHM",
    "CURATOR_SIGNATURE_KIND",
    "CURATOR_SIGNATURE_SCHEMA_VERSION",
    "CuratorSignatureError",
    "CuratorSignatureVerification",
    "CuratorSignatureWriteResult",
    "TrustedCuratorKey",
    "curation_bundle_signature_path",
    "load_authenticated_curation_bundle",
    "sign_curation_bundle",
]
