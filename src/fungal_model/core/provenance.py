"""Provenance-related types and exceptions."""

from __future__ import annotations

from typing import Literal

ConfidenceLevel = Literal["unknown", "low", "medium", "high", "testing"]


class ProvenanceError(ValueError):
    """Raised when required provenance is missing."""


class UnknownParameterError(ValueError):
    """Raised when a required parameter is explicitly unknown."""


def has_text(value: str | None) -> bool:
    """Return ``True`` for non-empty provenance text."""

    return value is not None and str(value).strip() != ""


__all__ = [
    "ConfidenceLevel",
    "ProvenanceError",
    "UnknownParameterError",
    "has_text",
]

