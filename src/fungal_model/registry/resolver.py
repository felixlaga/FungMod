"""Strict name and alias resolution for FungMod registry records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fungal_model.registry.records import RegistryRecord
from fungal_model.registry.store import FungModRegistry


@dataclass(frozen=True)
class ResolvedRecord:
    """One successful registry name/alias resolution."""

    record_type: str
    query: str
    record_id: str
    record: RegistryRecord
    matched_field: str
    matched_value: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "query": self.query,
            "record_id": self.record_id,
            "matched_field": self.matched_field,
            "matched_value": self.matched_value,
            "confidence": self.confidence,
            "record": self.record.to_dict(),
        }


class ResolutionError(ValueError):
    """Raised when a registry name or alias cannot be resolved."""

    def __init__(
        self,
        message: str,
        *,
        record_type: str,
        query: str,
        known_terms: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.record_type = record_type
        self.query = query
        self.known_terms = known_terms


class AmbiguousResolutionError(ResolutionError):
    """Raised when a registry name or alias matches multiple records."""

    def __init__(
        self,
        *,
        record_type: str,
        query: str,
        candidates: tuple[ResolvedRecord, ...],
    ) -> None:
        self.candidates = candidates
        candidate_text = ", ".join(
            f"{candidate.record_id} ({candidate.record.name})"
            for candidate in candidates
        )
        super().__init__(
            f"Ambiguous {record_type} resolution for {query!r}. Candidates: {candidate_text}.",
            record_type=record_type,
            query=query,
            known_terms=tuple(candidate.record_id for candidate in candidates),
        )


class RegistryResolver:
    """Resolve researcher-facing names and aliases against a loaded registry."""

    def __init__(self, registry: FungModRegistry) -> None:
        self.registry = registry

    def resolve_fungus(self, query: str) -> ResolvedRecord:
        """Resolve a fungus/source ID, name, or alias."""

        return self._resolve("fungus", self.registry.fungi, query)

    def resolve_substrate(self, query: str) -> ResolvedRecord:
        """Resolve a substrate ID, name, or alias."""

        return self._resolve("substrate", self.registry.substrates, query)

    def resolve_environment(self, query: str) -> ResolvedRecord:
        """Resolve an environment ID, name, or alias."""

        return self._resolve("environment", self.registry.environments, query)

    def resolve_enzyme_class(self, query: str) -> ResolvedRecord:
        """Resolve an enzyme-class ID, name, alias, or EC number."""

        return self._resolve("enzyme_class", self.registry.enzyme_classes, query)

    def resolve_any(self, query: str) -> ResolvedRecord:
        """Resolve a query across first-class registry record types when unambiguous."""

        candidates = (
            *self._matches("fungus", self.registry.fungi, query),
            *self._matches("substrate", self.registry.substrates, query),
            *self._matches("environment", self.registry.environments, query),
            *self._matches("enzyme_class", self.registry.enzyme_classes, query),
        )
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise AmbiguousResolutionError(record_type="registry record", query=query, candidates=candidates)
        raise self._unknown_error(
            "registry record",
            query,
            {
                **self.registry.fungi,
                **self.registry.substrates,
                **self.registry.environments,
                **self.registry.enzyme_classes,
            },
        )

    def _resolve(
        self,
        record_type: str,
        records: Mapping[str, RegistryRecord],
        query: str,
    ) -> ResolvedRecord:
        candidates = self._matches(record_type, records, query)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise AmbiguousResolutionError(record_type=record_type, query=query, candidates=candidates)
        raise self._unknown_error(record_type, query, records)

    def _matches(
        self,
        record_type: str,
        records: Mapping[str, RegistryRecord],
        query: str,
    ) -> tuple[ResolvedRecord, ...]:
        text = str(query).strip()
        if not text:
            return ()
        exact = _matching_records(
            record_type=record_type,
            records=records,
            query=text,
            normalized=False,
        )
        if exact:
            return exact
        return _matching_records(
            record_type=record_type,
            records=records,
            query=text,
            normalized=True,
        )

    def _unknown_error(
        self,
        record_type: str,
        query: str,
        records: Mapping[str, RegistryRecord],
    ) -> ResolutionError:
        known_terms = _known_terms(records)
        preview = ", ".join(known_terms[:12])
        suffix = "" if len(known_terms) <= 12 else f", ... ({len(known_terms)} total)"
        return ResolutionError(
            f"Could not resolve {record_type} {query!r}. No registry ID, name, display name, "
            f"scientific name, alias, EC number, or database ID matched. Known {record_type} "
            f"terms include: {preview}{suffix}.",
            record_type=record_type,
            query=query,
            known_terms=known_terms,
        )


def _matching_records(
    *,
    record_type: str,
    records: Mapping[str, RegistryRecord],
    query: str,
    normalized: bool,
) -> tuple[ResolvedRecord, ...]:
    matches: dict[str, ResolvedRecord] = {}
    target = _normalize(query) if normalized else query
    for record_id, record in records.items():
        for field_name, value in _record_terms(record_id, record):
            candidate = _normalize(value) if normalized else value
            if candidate != target:
                continue
            matches[record.record_id] = ResolvedRecord(
                record_type=record_type,
                query=query,
                record_id=record.record_id,
                record=record,
                matched_field=field_name,
                matched_value=value,
                confidence="case_insensitive_exact" if normalized else "exact",
            )
            break
    return tuple(matches.values())


def _record_terms(record_id: str, record: RegistryRecord) -> tuple[tuple[str, str], ...]:
    terms: list[tuple[str, str]] = [
        ("record_id", record_id),
        ("record_id", record.record_id),
        ("name", record.name),
    ]
    if record.display_name:
        terms.append(("display_name", record.display_name))
    if record.scientific_name:
        terms.append(("scientific_name", record.scientific_name))
    terms.extend(("alias", alias) for alias in record.aliases)
    if record.ec_number:
        terms.append(("ec_number", record.ec_number))
        terms.append(("ec_number", f"EC {record.ec_number}"))
    for key, raw_values in record.database_ids.items():
        for value in raw_values:
            terms.append((f"database_ids.{key}", value))
            terms.append((f"database_ids.{key}", f"{key}:{value}"))
    for key, value in record.external_refs.items():
        if isinstance(value, str):
            terms.append((f"external_refs.{key}", value))
    return tuple((field, value.strip()) for field, value in terms if value.strip())


def _known_terms(records: Mapping[str, RegistryRecord]) -> tuple[str, ...]:
    terms = {
        value
        for record_id, record in records.items()
        for _, value in _record_terms(record_id, record)
    }
    return tuple(sorted(terms, key=str.casefold))


def _normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


__all__ = [
    "AmbiguousResolutionError",
    "RegistryResolver",
    "ResolutionError",
    "ResolvedRecord",
]
