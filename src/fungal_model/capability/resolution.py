"""Resolve enzymatic capability from a genome CAZyme annotation.

This is the breadth layer. It answers one question — *which enzymatic
capabilities does this organism plausibly encode* — and deliberately answers no
others. It never returns a rate, a kinetic constant, an expression level, or a
claim that an enzyme is secreted under any particular condition. A genome states
what an organism *can* encode, not what it is doing.

Two distinctions carry the honesty of this module:

Capability versus modellability
    An organism can encode a capability FungMod cannot yet model. Those cases
    are reported separately rather than dropped, because silently discarding
    them would make a partial model look complete.

Diagnostic versus polyspecific families
    Many CAZy families carry several distinct activities. A polyspecific
    assignment is a candidate capability, not a confirmed one, and is reported
    under its own heading so a caller can require diagnostic evidence only.

Resolution is offline and deterministic. Annotations are supplied as files with
their own provenance rather than fetched at run time, so a result can be
reproduced exactly from the recorded inputs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.resources import default_registry_path

DIAGNOSTIC = "family_diagnostic"
POLYSPECIFIC = "family_polyspecific"
SPECIFICITY_LEVELS = frozenset({DIAGNOSTIC, POLYSPECIFIC})


class CapabilityResolutionError(ValueError):
    """Raised when capability cannot be resolved honestly from the inputs."""


@dataclass(frozen=True)
class FamilyMapping:
    """One curated CAZy family to enzyme-class assignment."""

    family: str
    enzyme_class: str
    specificity: str
    notes: str = ""

    def __post_init__(self) -> None:
        if self.specificity not in SPECIFICITY_LEVELS:
            raise CapabilityResolutionError(
                f"Family {self.family!r} has unknown specificity {self.specificity!r}; "
                f"expected one of {sorted(SPECIFICITY_LEVELS)}."
            )

    @property
    def is_diagnostic(self) -> bool:
        return self.specificity == DIAGNOSTIC


@dataclass(frozen=True)
class CazymeFamilyMap:
    """The curated family-to-enzyme-class table."""

    mappings: tuple[FamilyMapping, ...]
    sources: tuple[str, ...]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CazymeFamilyMap":
        resolved = (
            Path(path)
            if path is not None
            else default_registry_path().parent / "cazyme_families" / "cazyme_family_map.yml"
        )
        data = yaml.safe_load(Path(resolved).read_text(encoding="utf-8"))
        if not isinstance(data, Mapping) or data.get("record_type") != "cazyme_family_map":
            raise CapabilityResolutionError(f"{resolved} is not a cazyme_family_map record file.")
        sources = tuple(str(s) for s in data.get("provenance", {}).get("sources", ()))
        if not sources:
            raise ProvenanceError("The CAZy family map requires provenance sources.")
        mappings = tuple(
            FamilyMapping(
                family=str(record["family"]).strip().upper(),
                enzyme_class=str(record["enzyme_class"]).strip(),
                specificity=str(record["specificity"]).strip(),
                notes=str(record.get("notes", "")),
            )
            for record in data.get("records", ())
        )
        if not mappings:
            raise CapabilityResolutionError("The CAZy family map contains no records.")
        return cls(mappings=mappings, sources=sources)

    def for_family(self, family: str) -> tuple[FamilyMapping, ...]:
        key = family.strip().upper()
        return tuple(m for m in self.mappings if m.family == key)


@dataclass(frozen=True)
class CazymeAnnotation:
    """A provenance-bearing CAZyme annotation for one organism.

    The families are what an annotation tool reported for a genome or proteome.
    Provenance is mandatory: without the organism, the sequence source, and the
    tool that produced the call, the result is not reproducible and must not be
    used.
    """

    organism: str
    families: tuple[str, ...]
    genome_accession: str
    annotation_tool: str
    annotation_tool_version: str
    annotation_date: str
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("organism", "genome_accession", "annotation_tool", "annotation_tool_version", "annotation_date"):
            if not has_text(getattr(self, name)):
                raise ProvenanceError(
                    f"CAZyme annotation requires a nonblank {name}; capability resolution "
                    "must be reproducible from recorded inputs."
                )
        if not self.families:
            raise CapabilityResolutionError(
                f"CAZyme annotation for {self.organism!r} lists no families."
            )
        object.__setattr__(
            self, "families", tuple(sorted({f.strip().upper() for f in self.families if has_text(f)}))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "organism": self.organism,
            "families": list(self.families),
            "genome_accession": self.genome_accession,
            "annotation_tool": self.annotation_tool,
            "annotation_tool_version": self.annotation_tool_version,
            "annotation_date": self.annotation_date,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ResolvedCapability:
    """One capability inferred from one or more annotated families."""

    enzyme_class: str
    families: tuple[str, ...]
    specificity: str
    modellable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "enzyme_class": self.enzyme_class,
            "families": list(self.families),
            "specificity": self.specificity,
            "modellable": self.modellable,
        }


@dataclass(frozen=True)
class CapabilityResolution:
    """The complete, auditable result of resolving one annotation."""

    organism: str
    annotation: CazymeAnnotation
    capabilities: tuple[ResolvedCapability, ...]
    unmapped_families: tuple[str, ...]
    registry_enzyme_classes: tuple[str, ...] = field(default=())

    @property
    def modellable_enzyme_classes(self) -> tuple[str, ...]:
        """Capabilities FungMod can actually assemble a process for."""

        return tuple(sorted({c.enzyme_class for c in self.capabilities if c.modellable}))

    @property
    def capabilities_without_model(self) -> tuple[str, ...]:
        """Capabilities the organism plausibly has that FungMod cannot yet model."""

        return tuple(sorted({c.enzyme_class for c in self.capabilities if not c.modellable}))

    @property
    def diagnostic_enzyme_classes(self) -> tuple[str, ...]:
        """Capabilities supported by at least one family-diagnostic assignment."""

        return tuple(sorted({c.enzyme_class for c in self.capabilities if c.specificity == DIAGNOSTIC}))

    def require_modellable(self) -> tuple[str, ...]:
        """Return modellable classes, refusing explicitly when there are none."""

        classes = self.modellable_enzyme_classes
        if not classes:
            missing = ", ".join(self.capabilities_without_model) or "none resolved"
            raise CapabilityResolutionError(
                f"No modellable enzyme class resolved for {self.organism!r}. "
                f"Capabilities found but not modellable: {missing}. "
                f"Unmapped CAZy families: {', '.join(self.unmapped_families) or 'none'}. "
                "Add a registry enzyme-class record before simulating this organism."
            )
        return classes

    def to_dict(self) -> dict[str, Any]:
        return {
            "organism": self.organism,
            "annotation": self.annotation.to_dict(),
            "capabilities": [c.to_dict() for c in self.capabilities],
            "modellable_enzyme_classes": list(self.modellable_enzyme_classes),
            "capabilities_without_model": list(self.capabilities_without_model),
            "diagnostic_enzyme_classes": list(self.diagnostic_enzyme_classes),
            "unmapped_families": list(self.unmapped_families),
            "claim_boundary": (
                "Capability presence inferred from genome annotation. This states what the "
                "organism can encode, not what it expresses, secretes, or how fast. No rate, "
                "kinetic constant, or expression level is implied."
            ),
        }


@dataclass(frozen=True)
class CapabilityResolver:
    """Join a CAZyme annotation to FungMod enzyme classes."""

    family_map: CazymeFamilyMap
    registry_enzyme_classes: tuple[str, ...]

    @classmethod
    def from_registry(
        cls,
        *,
        registry_path: str | Path | None = None,
        family_map_path: str | Path | None = None,
    ) -> "CapabilityResolver":
        registry_root = Path(registry_path) if registry_path else default_registry_path()
        classes_file = registry_root.parent / "enzymes" / "enzyme_classes.yml"
        data = yaml.safe_load(classes_file.read_text(encoding="utf-8"))
        known = tuple(sorted(str(r["record_id"]) for r in data.get("records", ())))
        return cls(
            family_map=CazymeFamilyMap.load(family_map_path),
            registry_enzyme_classes=known,
        )

    def resolve(
        self,
        annotation: CazymeAnnotation,
        *,
        require_diagnostic: bool = False,
    ) -> CapabilityResolution:
        """Resolve an annotation into capabilities.

        With `require_diagnostic=True`, polyspecific family assignments are
        discarded rather than reported, for callers that need stronger evidence
        than family membership alone.
        """

        by_class: dict[str, list[FamilyMapping]] = {}
        unmapped: list[str] = []
        for family in annotation.families:
            matches = self.family_map.for_family(family)
            if not matches:
                unmapped.append(family)
                continue
            for mapping in matches:
                if require_diagnostic and not mapping.is_diagnostic:
                    continue
                by_class.setdefault(mapping.enzyme_class, []).append(mapping)

        capabilities: list[ResolvedCapability] = []
        for enzyme_class, mappings in sorted(by_class.items()):
            # A class is diagnostic overall if any supporting family is diagnostic.
            specificity = DIAGNOSTIC if any(m.is_diagnostic for m in mappings) else POLYSPECIFIC
            capabilities.append(
                ResolvedCapability(
                    enzyme_class=enzyme_class,
                    families=tuple(sorted(m.family for m in mappings)),
                    specificity=specificity,
                    modellable=enzyme_class in self.registry_enzyme_classes,
                )
            )
        return CapabilityResolution(
            organism=annotation.organism,
            annotation=annotation,
            capabilities=tuple(capabilities),
            unmapped_families=tuple(sorted(unmapped)),
            registry_enzyme_classes=self.registry_enzyme_classes,
        )


__all__ = [
    "DIAGNOSTIC",
    "POLYSPECIFIC",
    "SPECIFICITY_LEVELS",
    "CapabilityResolution",
    "CapabilityResolutionError",
    "CapabilityResolver",
    "CazymeAnnotation",
    "CazymeFamilyMap",
    "FamilyMapping",
    "ResolvedCapability",
]
