"""Shared provenance classification for parameter promotion and simulation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from fungal_model.mechanism_sources import load_mechanism_source, validate_mechanism_source_links


CURATION_AUDIT_PROVENANCE_KEY = "fungmod_curation"
PARAMETER_BRIDGE_PROVENANCE_KEY = "fungmod_parameter_bridge"
REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY = "fungmod_registry_record_authoring"
# Records generated from user-supplied tables (``fungal_model.api.user_data``)
# carry this namespace. It is reserved so curator authoring cannot relabel a
# user-dataset record as curated evidence; it does not change how
# ``classify_parameter_provenance`` classifies the record.
USER_DATASET_PROVENANCE_KEY = "fungmod_user_dataset"
RESERVED_PROVENANCE_KEYS = frozenset(
    {
        CURATION_AUDIT_PROVENANCE_KEY,
        PARAMETER_BRIDGE_PROVENANCE_KEY,
        REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY,
        USER_DATASET_PROVENANCE_KEY,
    }
)

ParameterProvenanceClass = Literal[
    "generic",
    "curation_audited",
    "parameter_bridge",
]

_DISTINCTIVE_PARAMETER_SOURCE_FIELDS = frozenset(
    {
        "source_reaction_ids",
        "source_query",
        "source_field",
        "source_urls",
        "source_snapshot_sha256",
    }
)
_DISTINCTIVE_PARAMETER_SOURCE_FIELD_THRESHOLD = 3


def classify_parameter_provenance(
    provenance: Mapping[str, Any] | None,
    *,
    curation_metadata: Mapping[str, Any] | None = None,
) -> ParameterProvenanceClass:
    """Classify generic, curated, and source-bridge parameter provenance.

    Reserved namespaces are evidence even when malformed. Distinctive source
    evidence requires a multi-field structure so ordinary curator metadata is
    not mistaken for the PARAMETER bridge contract.
    """

    if not isinstance(provenance, Mapping):
        provenance = {}
    if PARAMETER_BRIDGE_PROVENANCE_KEY in provenance:
        return "parameter_bridge"
    if _has_distinctive_parameter_source_evidence(provenance):
        return "parameter_bridge"

    curation_audit = provenance.get(CURATION_AUDIT_PROVENANCE_KEY)
    if isinstance(curation_audit, Mapping) and _has_distinctive_parameter_source_evidence(
        curation_audit.get("source_provenance")
    ):
        return "parameter_bridge"

    if isinstance(curation_metadata, Mapping) and _has_distinctive_parameter_source_evidence(
        curation_metadata.get("source_provenance")
    ):
        return "parameter_bridge"
    if CURATION_AUDIT_PROVENANCE_KEY in provenance:
        return "curation_audited"
    return "generic"


def _has_distinctive_parameter_source_evidence(value: Any) -> bool:
    return isinstance(value, Mapping) and len(
        _DISTINCTIVE_PARAMETER_SOURCE_FIELDS & set(value)
    ) >= _DISTINCTIVE_PARAMETER_SOURCE_FIELD_THRESHOLD


__all__ = [
    "CURATION_AUDIT_PROVENANCE_KEY",
    "PARAMETER_BRIDGE_PROVENANCE_KEY",
    "REGISTRY_RECORD_AUTHORING_PROVENANCE_KEY",
    "RESERVED_PROVENANCE_KEYS",
    "USER_DATASET_PROVENANCE_KEY",
    "ParameterProvenanceClass",
    "classify_parameter_provenance",
    "load_mechanism_source",
    "validate_mechanism_source_links",
]
